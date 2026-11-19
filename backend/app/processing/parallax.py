"""2.5D parallax renderer: depth-based image warping driven by camera motion."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .video import encode_video


def _accumulated_path(path: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    tx, ty = 0.0, 0.0
    xs, ys = [], []
    for step in path:
        tx += step["dx"]
        ty += step["dy"]
        xs.append(tx)
        ys.append(ty)
    return np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.float32)


def render_parallax(
    frames: list[np.ndarray],
    depth: np.ndarray,
    camera_path: list[dict],
    out_dir: Path,
    fps: int = 24,
    output_seconds: float = 4.0,
    strength: float = 1.4,
    keyframe_index: int | None = None,
    watermark: bool = False,
    formats: tuple[str, ...] = ("webm",),
) -> dict:
    """Render a looping parallax animation from a keyframe + depth + camera path."""
    if not frames:
        raise RuntimeError("Cannot render parallax without frames")
    ref = frames[keyframe_index] if keyframe_index is not None else frames[len(frames) // 3]
    h, w = ref.shape[:2]
    depth = cv2.resize(depth, (w, h)).astype(np.float32)
    depth = np.clip(depth, 0.0, 1.0)

    xs, ys = _accumulated_path(camera_path)
    total = float(np.hypot(xs[-1] - xs[0], ys[-1] - ys[0])) if len(xs) > 1 else 0.0
    # If the source camera is static, synthesize a gentle dolly so depth is visible.
    if total < 2.0:
        xs = np.linspace(0, 26.0, len(xs), dtype=np.float32)
        ys = np.linspace(0, -10.0, len(ys), dtype=np.float32)

    n_frames = max(24, int(fps * output_seconds))
    grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    rendered: list[np.ndarray] = []

    for i in range(n_frames):
        phase = i / n_frames
        # Ping-pong motion makes a seamless loop.
        t = 1.0 - abs(2.0 * phase - 1.0)
        idx = t * (len(xs) - 1)
        cx = float(np.interp(idx, np.arange(len(xs)), xs))
        cy = float(np.interp(idx, np.arange(len(ys)), ys))

        # Near pixels (depth ~1) shift most, distant pixels barely move.
        map_x = grid_x - cx * strength * depth
        map_y = grid_y - cy * strength * depth
        warped = cv2.remap(ref, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REPLICATE)

        if watermark:
            cv2.putText(warped, "Made with Video to 3D Studio", (12, h - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        rendered.append(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))

    videos: dict[str, str] = {}
    for fmt in formats:
        if fmt not in {"webm", "mp4", "mkv"}:
            continue
        name = f"parallax.{fmt}"
        encode_video(rendered, out_dir / name, fps=fps)
        videos[fmt] = name
    if not videos:
        raise RuntimeError("No supported video export format was requested")

    # Side artifacts for the interactive viewer.
    cv2.imwrite(str(out_dir / "keyframe.jpg"), ref)
    cv2.imwrite(str(out_dir / "depth.png"), (depth * 255).astype(np.uint8))
    with open(out_dir / "camera_path.json", "w") as f:
        json.dump({"x": xs.tolist(), "y": ys.tolist()}, f)

    extras: dict = {}
    if "glb" in formats:
        from .exporters import export_parallax_glb
        export_parallax_glb(out_dir / "keyframe.jpg", depth, out_dir / "parallax.glb")
        extras["glb"] = "parallax.glb"

    return {
        **extras,
        "video": videos.get("mp4") or videos.get("webm") or next(iter(videos.values())),
        "videos": videos,
        "keyframe": "keyframe.jpg",
        "depth": "depth.png",
        "camera_path": "camera_path.json",
        "width": w,
        "height": h,
        "fps": fps,
        "frames": n_frames,
        "depth_backend": "warp",
    }
