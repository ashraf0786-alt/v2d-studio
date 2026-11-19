"""Lightning-fast sparse video sampling.

Work is bounded by the number of sampled frames (~96), not the file size.
Each frame is fetched with an independent ffmpeg seek and decoded in parallel
straight into memory via a raw pipe — no intermediate files, no full decode.
"""
from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from ..config import settings

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
TARGET_LONG_EDGE = 480
MAX_FRAMES = 96
WORKERS = 8


def probe_metadata(path: Path) -> dict:
    """Fast ffprobe: duration, dimensions, rotation, codec — tolerant of missing fields."""
    meta = {"duration": 0.0, "width": 0, "height": 0, "rotation": 0, "codec": "", "fps": 0.0}
    try:
        cp = subprocess.run([
            FFPROBE, "-v", "error", "-analyzeduration", "20M", "-probesize", "20M",
            "-show_entries",
            "format=duration:stream=width,height,codec_name,avg_frame_rate,side_data_list:stream_tags=rotate",
            "-of", "json", str(path),
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if cp.returncode == 0:
            d = json.loads(cp.stdout.decode(errors="ignore"))
            fmt = d.get("format", {})
            streams = d.get("streams", [])
            v = next((s for s in streams if s.get("width")), streams[0] if streams else {})
            meta["width"] = int(v.get("width") or 0)
            meta["height"] = int(v.get("height") or 0)
            meta["codec"] = v.get("codec_name", "")
            try:
                meta["duration"] = float(fmt.get("duration") or 0)
            except (TypeError, ValueError):
                pass
            fps = v.get("avg_frame_rate", "0/0")
            try:
                a, b = fps.split("/")
                meta["fps"] = float(a) / float(b) if float(b) else 0.0
            except Exception:
                pass
            for sd in v.get("side_data_list", []) or []:
                if "rotation" in sd:
                    try: meta["rotation"] = int(float(sd["rotation"]))
                    except Exception: pass
            rot = (v.get("tags") or {}).get("rotate")
            if rot is not None:
                try: meta["rotation"] = int(float(rot))
                except Exception: pass
    except Exception:
        pass

    # Fallback duration estimate from file size and a rough bitrate.
    if meta["duration"] <= 0 and meta["width"]:
        size = path.stat().st_size
        meta["duration"] = min(3600.0, size / max(200_000, meta["width"] * meta["height"] * 0.25))
    return meta


def _target_size(meta: dict) -> tuple[int, int]:
    w, h = meta["width"], meta["height"]
    if not w or not h:
        return TARGET_LONG_EDGE, TARGET_LONG_EDGE
    # Rotation swaps effective orientation.
    if abs(meta["rotation"]) in (90, 270):
        w, h = h, w
    if w >= h:
        tw = TARGET_LONG_EDGE
        th = max(2, round(h * tw / w / 2) * 2)
    else:
        th = TARGET_LONG_EDGE
        tw = max(2, round(w * th / h / 2) * 2)
    return tw, th


def _decode_at(path: Path, t: float, tw: int, th: int, rotation: int) -> np.ndarray | None:
    """Decode a single frame near timestamp t via raw pipe."""
    vf = f"scale={tw}:{th}:flags=fast_bilinear"
    if rotation:
        vf += f",transpose={1 if rotation == 90 else 2 if rotation == 270 else 0}"
    cmd = [
        FFMPEG, "-y", "-loglevel", "error",
        "-ss", f"{t:.3f}", "-i", str(path),
        "-an", "-frames:v", "1", "-vf", vf,
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    try:
        cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
        size = tw * th * 3
        if len(cp.stdout) < size:
            return None
        frame = np.frombuffer(cp.stdout[:size], dtype=np.uint8).reshape((th, tw, 3))
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _single_pass(path: Path, meta: dict, tw: int, th: int, n: int) -> list[np.ndarray]:
    """One ffmpeg pass, decoding keyframes only, sampling via the fps filter."""
    duration = meta["duration"]
    fps = max(0.1, n / duration) if duration else 1.0
    vf = f"fps={fps:.4f},scale={tw}:{th}:flags=fast_bilinear"
    if meta["rotation"]:
        vf += f",transpose={1 if meta['rotation'] == 90 else 2 if meta['rotation'] == 270 else 0}"
    cmd = [
        FFMPEG, "-y", "-loglevel", "error",
        "-skip_frame", "nokey", "-i", str(path),
        "-an", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=180)
    size = tw * th * 3
    count = len(cp.stdout) // size
    frames = []
    for i in range(min(count, n)):
        raw = cp.stdout[i * size:(i + 1) * size]
        rgb = np.frombuffer(raw, dtype=np.uint8).reshape((th, tw, 3))
        frames.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return frames


def sparse_extract(path: Path, max_frames: int = MAX_FRAMES) -> tuple[list[np.ndarray], dict]:
    """Extract ~max_frames frames. Work is bounded by frame count, not file size."""
    meta = probe_metadata(path)
    tw, th = _target_size(meta)
    duration = meta["duration"]
    size_gb = path.stat().st_size / 1e9

    n = max(1, min(max_frames, int(duration * 8) if duration else max_frames))
    n = min(n, max_frames)

    frames: list[np.ndarray] = []
    # Small/medium files: one fast keyframe-only pass. Huge/long files: parallel seeks
    # avoid scanning gigabytes end-to-end.
    if size_gb < 2.0 and duration < 900:
        try:
            frames = _single_pass(path, meta, tw, th, n)
        except Exception:
            frames = []
    if len(frames) < max(4, n // 3):
        timestamps = [duration * i / (n + 1) for i in range(1, n + 1)] if n > 1 else [duration / 2]
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futures = {ex.submit(_decode_at, path, t, tw, th, meta["rotation"]): i
                       for i, t in enumerate(timestamps)}
            results: dict[int, np.ndarray] = {}
            for fut in as_completed(futures):
                i = futures[fut]
                fr = fut.result()
                if fr is not None:
                    results[i] = fr
        frames = [results[i] for i in sorted(results)]

    if not frames:
        raise RuntimeError("No frames could be decoded — check the video codec/format")
    meta["sampled_frames"] = len(frames)
    meta["target_size"] = [tw, th]
    return frames, meta


_FRAME_CACHE: dict[str, tuple[list[np.ndarray], dict]] = {}


def sparse_extract_cached(path: Path, max_frames: int = MAX_FRAMES) -> tuple[list[np.ndarray], dict]:
    """Cache decoded frames by content fingerprint so repeat jobs are instant."""
    key = f"{file_fingerprint(path)}-{max_frames}"
    if key in _FRAME_CACHE:
        return _FRAME_CACHE[key]
    result = sparse_extract(path, max_frames)
    if len(_FRAME_CACHE) >= 4:
        _FRAME_CACHE.pop(next(iter(_FRAME_CACHE)))
    _FRAME_CACHE[key] = result
    return result


def file_fingerprint(path: Path) -> str:
    import hashlib
    st = path.stat()
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))
        f.seek(-min(1024 * 1024, st.st_size), 2)
        h.update(f.read(1024 * 1024))
    return h.hexdigest()[:16]
