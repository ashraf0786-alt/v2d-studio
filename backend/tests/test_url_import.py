"""URL import and sparse-processing tests."""
from __future__ import annotations

import functools
import http.server
import threading
import time
from pathlib import Path

import pytest

from app import url_import
from app.processing.fast_video import probe_metadata, sparse_extract


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    p = d / "sample.mp4"
    import subprocess
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
        "-i", "testsrc=size=320x180:rate=24:duration=4", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", str(p),
    ], check=True)
    return p


def test_sparse_extract(sample_video):
    frames, meta = sparse_extract(sample_video, max_frames=24)
    assert len(frames) >= 8
    assert meta["duration"] > 3
    assert meta["sampled_frames"] == len(frames)
    assert frames[0].shape[1] <= 480


def test_probe_metadata(sample_video):
    meta = probe_metadata(sample_video)
    assert meta["width"] == 320 and meta["height"] == 180
    assert meta["codec"] == "h264"


def test_ssrf_blocked():
    with pytest.raises(url_import.UrlImportError):
        url_import._validate_url("http://127.0.0.1/secret")
    with pytest.raises(url_import.UrlImportError):
        url_import._validate_url("http://169.254.169.254/latest/meta-data/")


def test_direct_url_import(sample_video, tmp_path, monkeypatch):
    # Allow localhost only for this test's local file server.
    monkeypatch.setattr(url_import, "_is_safe_host", lambda host: True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(sample_video.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/{sample_video.name}"
        dest = tmp_path / "downloaded.mp4"
        path, source = url_import.fetch_url(url, dest)
        assert path.exists() and path.stat().st_size > 1000
        assert source == "direct URL"
    finally:
        server.shutdown()


def test_url_endpoint(client, owner_headers, sample_video, monkeypatch):
    monkeypatch.setattr(url_import, "_is_safe_host", lambda host: True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(sample_video.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/{sample_video.name}"
        r = client.post("/api/jobs/url", headers=owner_headers,
                        json={"url": url, "mode": "parallax"})
        assert r.status_code == 200, r.text
        jid = r.json()["id"]
        for _ in range(120):
            j = client.get(f"/api/jobs/{jid}", headers=owner_headers).json()
            if j["status"] in ("completed", "failed"):
                break
            time.sleep(0.25)
        assert j["status"] == "completed", j["error"]
        assert j["result"]["sampling"] == "sparse-parallel"
    finally:
        server.shutdown()
