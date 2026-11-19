"""Video probing and frame extraction via ffmpeg/ffprobe."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

from ..config import settings


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def probe_duration(path: Path) -> float:
    """Return video duration in seconds using ffprobe (authoritative)."""
    cp = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(path),
    ])
    if cp.returncode == 0:
        try:
            return float(json.loads(cp.stdout.decode())["format"]["duration"])
        except Exception:
            pass
    # Fallback: OpenCV
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    return frames / fps if fps else 0.0


def probe_resolution(path: Path) -> int:
    """Longest edge of the video frame."""
    cp = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(path),
    ])
    if cp.returncode == 0:
        try:
            s = json.loads(cp.stdout.decode())["streams"][0]
            return max(int(s["width"]), int(s["height"]))
        except Exception:
            pass
    cap = cv2.VideoCapture(str(path))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return max(w, h)


def extract_frames(path: Path, out_dir: Path, max_width: int = 720, max_frames: int | None = None) -> list[Path]:
    """Decode video to a sampled sequence of PNG frames."""
    out_dir.mkdir(parents=True, exist_ok=True)
    max_frames = max_frames or settings.MAX_FRAMES
    fps = settings.DEFAULT_FPS
    vf = f"fps={fps},scale='min({max_width},iw)':-2"
    pattern = str(out_dir / "frame_%05d.png")
    cp = _run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
        "-vf", vf, "-frames:v", str(max_frames), pattern,
    ])
    if cp.returncode != 0:
        raise RuntimeError(f"ffmpeg frame extraction failed: {cp.stderr.decode()[:500]}")
    return sorted(out_dir.glob("frame_*.png"))


def detect_shots(frames: list[np.ndarray], threshold: float = 0.35) -> list[int]:
    """Detect hard cuts using normalized grayscale histogram correlation.

    Returns the frame index of each detected cut (the first frame of a new shot).
    """
    cuts: list[int] = []
    prev = None
    for i, frame in enumerate(frames):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
        cv2.normalize(hist, hist)
        if prev is not None:
            corr = cv2.compareHist(prev, hist, cv2.HISTCMP_CORREL)
            if corr < threshold:
                cuts.append(i)
        prev = hist
    return cuts


def load_frames(paths: list[Path]) -> list[np.ndarray]:
    frames = []
    for p in paths:
        img = cv2.imread(str(p))
        if img is not None:
            frames.append(img)
    return frames


def encode_video(frames_rgb: list[np.ndarray], out_path: Path, fps: int = 24) -> Path:
    """Encode RGB frames to a video file. Falls back between supported codecs."""
    if not frames_rgb:
        raise RuntimeError("No frames to encode")
    h, w = frames_rgb[0].shape[:2]
    ext = out_path.suffix.lower()
    codecs = {
        ".webm": ["libvpx-vp9", "libvpx"],
        ".mp4": ["libx264", "mpeg4"],
        ".mkv": ["libx264", "mpeg4"],
    }.get(ext, ["libx264", "mpeg4"])

    last_err = b""
    for codec in codecs:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
            "-i", "-", "-an", "-c:v", codec,
        ]
        if codec == "libvpx-vp9":
            cmd += ["-deadline", "realtime", "-cpu-used", "5", "-b:v", "0", "-crf", "33"]
        elif codec == "libvpx":
            cmd += ["-deadline", "realtime", "-cpu-used", "8", "-b:v", "2M"]
        elif codec == "libx264":
            cmd += ["-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
        cmd += ["-movflags", "+faststart", str(out_path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for fr in frames_rgb:
                proc.stdin.write(fr.astype(np.uint8).tobytes())
            proc.stdin.close()
            err = proc.stderr.read()
            proc.wait(timeout=120)
            if proc.returncode == 0:
                return out_path
            last_err = err
        except Exception as e:  # pragma: no cover
            try:
                proc.kill()
            except Exception:
                pass
            last_err = str(e).encode()
    raise RuntimeError(f"Video encoding failed: {last_err.decode(errors='ignore')[:500]}")


def make_sample_video(out_path: Path, seconds: int = 8, width: int = 640, height: int = 360) -> Path:
    """Generate a synthetic clip with parallax-friendly moving shapes for demos."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i",
        f"color=c=0x0b1020:s={width}x{height}:d={seconds}:r=24",
        "-vf",
        (
            f"drawbox=x='{width/2}-60+40*sin(t)':y='{height/2}-40':w=120:h=80:color=0x4cc9f0:t=fill,"
            f"drawbox=x='{width/2}-20+90*sin(t*0.7)':y='{height/2}+30':w=40:h=40:color=0xf72585:t=fill,"
            f"drawbox=x='{width/2}-100+120*sin(t*0.4)':y='{height/2}-120':w=25:h=25:color=0xffd166:t=fill"
        ),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(out_path),
    ]
    cp = _run(cmd)
    if cp.returncode != 0:
        raise RuntimeError(f"Sample generation failed: {cp.stderr.decode()[:400]}")
    return out_path
