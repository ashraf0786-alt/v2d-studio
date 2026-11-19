"""URL import with SSRF protection, streaming download, and yt-dlp support.

Accepts direct file URLs, signed object-store URLs, cloud share links, and
video-platform URLs. Always validates the resolved host to prevent requests
to internal/private infrastructure.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import httpx

from .config import settings

MAX_BYTES = int(os.getenv("URL_IMPORT_MAX_BYTES", 2 * 1024 * 1024 * 1024))  # 2 GB
TIMEOUT = httpx.Timeout(30.0, read=60.0, write=60.0, pool=10.0)

# Cloud share link patterns converted to direct forms where possible.
GDRIVE_RE = re.compile(r"drive\.google\.com/file/d/([^/]+)")
DROPBOX_RE = re.compile(r"www\.dropbox\.com/(.+)\?dl=0?")
ONEDRIVE_RE = re.compile(r"1drv\.ms/.*")

VIDEO_PLATFORMS = (
    "youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "instagram.com",
    "facebook.com", "twitter.com", "x.com", "reddit.com", "twitch.tv",
    "dailymotion.com", "bilibili.com", "soundcloud.com",
)


class UrlImportError(Exception):
    pass


def _is_safe_host(host: str) -> bool:
    """Resolve host and reject private/link-local/loopback addresses."""
    if not host:
        return False
    host = host.lower().rstrip(".")
    if host in ("localhost", "127.0.0.1", "::1") or host.startswith("127."):
        raise UrlImportError(f"Blocked local address: {host}")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UrlImportError(f"Cannot resolve host '{host}': {exc}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or
                ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UrlImportError(f"Blocked private/internal address for '{host}': {ip}")
    return True


def _validate_url(url: str) -> str:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise UrlImportError("URL must start with http:// or https://")
    parsed = urlparse(url)
    if not parsed.netloc:
        raise UrlImportError("Invalid URL")
    if not _is_safe_host(parsed.hostname or ""):
        raise UrlImportError(f"Blocked host: {parsed.hostname}")
    return url


def _looks_like_platform(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(p in host for p in VIDEO_PLATFORMS)


def _maybe_convert_share(url: str) -> str:
    m = GDRIVE_RE.search(url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    m = DROPBOX_RE.search(url)
    if m:
        return f"https://www.dropbox.com/{m.group(1)}?dl=1"
    return url


def _download_direct(url: str, dest: Path, headers: dict | None = None,
                     progress: Callable[[int, str], None] | None = None) -> Path:
    """Stream a direct URL to disk with redirect and SSRF validation."""
    h = {"User-Agent": "V2DStudio/1.0", **(headers or {})}
    total = 0
    seen = set()
    current = url
    with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
        for _ in range(8):
            if current in seen:
                raise UrlImportError("Redirect loop detected")
            seen.add(current)
            _validate_url(current)
            with client.stream("GET", current, headers=h) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    location = r.headers.get("location")
                    if not location:
                        raise UrlImportError("Redirect without location")
                    current = httpx.URL(current).join(location).human_repr()
                    # carry cookies across redirects
                    for k, v in r.cookies.items():
                        h["Cookie"] = f"{h.get('Cookie','')}; {k}={v}".strip("; ")
                    continue
                if r.status_code != 200:
                    raise UrlImportError(f"Download failed with HTTP {r.status_code}")
                ctype = r.headers.get("content-type", "").lower()
                clen = r.headers.get("content-length")
                if clen and int(clen) > MAX_BYTES:
                    raise UrlImportError(f"File too large ({int(clen)/1e9:.1f} GB; limit {MAX_BYTES/1e9:.0f} GB)")
                if "text/html" in ctype and not _looks_like_platform(current):
                    raise UrlImportError("URL returned a web page, not a video file")
                length = int(clen) if clen else 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=256 * 1024):
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise UrlImportError(f"File exceeds {MAX_BYTES/1e9:.0f} GB limit")
                        f.write(chunk)
                        if progress:
                            if length:
                                pct = max(1, min(18, int(total / length * 18)))
                                progress(pct, f"Downloading {total/1e6:.0f}/{length/1e6:.0f} MB")
                            else:
                                progress(5, f"Downloading {total/1e6:.0f} MB")
                return dest
    raise UrlImportError("Too many redirects")


def _download_ytdlp(url: str, dest: Path, headers: dict | None = None,
                    progress: Callable[[int, str], None] | None = None) -> Path:
    """Download via yt-dlp for video platforms and generic pages."""
    cmd = [
        "yt-dlp", "--no-playlist", "--no-warnings",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", str(dest.with_suffix("")) + ".%(ext)s",
    ]
    if headers:
        cmd += ["--add-headers", "\r\n".join(f"{k}: {v}" for k, v in headers.items())]
    cmd.append(url)
    # validate host before handing to yt-dlp
    _validate_url(url)
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    if cp.returncode != 0:
        raise UrlImportError(f"yt-dlp failed: {cp.stderr.decode(errors='ignore')[:400]}")
    files = sorted(dest.parent.glob(dest.stem + ".*"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise UrlImportError("yt-dlp produced no file")
    chosen = max(files, key=lambda p: p.stat().st_size)
    if chosen.stat().st_size > MAX_BYTES:
        raise UrlImportError(f"File too large ({chosen.stat().st_size/1e9:.1f} GB)")
    if chosen != dest:
        chosen.rename(dest)
    return dest


def fetch_url(url: str, dest: Path, headers: dict | None = None,
              progress: Callable[[int, str], None] | None = None) -> tuple[Path, str]:
    """Fetch a URL to a local file. Returns (path, source_description)."""
    url = _validate_url(url)
    converted = _maybe_convert_share(url)
    if _looks_like_platform(converted) or converted != url:
        if progress:
            progress(2, "Fetching from video platform…")
        path = _download_ytdlp(converted, dest, headers, progress)
        return path, "video platform / share link"
    path = _download_direct(converted, dest, headers, progress)
    return path, "direct URL"


def url_fingerprint(url: str, headers: dict | None = None) -> str:
    raw = url + "|" + json.dumps(headers or {}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
