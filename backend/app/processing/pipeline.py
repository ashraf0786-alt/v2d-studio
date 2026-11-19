"""Mode dispatcher and progress reporting for a single job (fast sparse path)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import mocap, parallax, scene
from .camera import estimate_camera_path
from .depth import get_estimator
from .fast_video import sparse_extract_cached
from .video import detect_shots

ProgressCb = Callable[[int, str], None]


def _longest_shot_keyframe(n: int, cuts: list[int]) -> int:
    if n <= 0:
        return 0
    bounds = [0] + list(cuts) + [n]
    best_len, best_start = -1, 0
    for a, b in zip(bounds, bounds[1:]):
        if b - a > best_len:
            best_len, best_start = b - a, a
    return best_start + best_len // 2


def run_job(
    mode: str,
    input_path: Path,
    out_dir: Path,
    params: dict,
    progress: ProgressCb,
) -> dict:
    progress(6, "Sparse sampling video…")
    frames, meta = sparse_extract_cached(input_path)
    duration = meta["duration"]
    progress(28, f"Sampled {len(frames)} frames")

    cuts = detect_shots(frames)
    keyframe_idx = _longest_shot_keyframe(len(frames), cuts)
    if cuts:
        progress(32, f"Detected {len(cuts)} shot transition(s)")

    estimator = get_estimator()
    progress(42, f"Estimating depth ({estimator.name})…")
    formats = tuple(params.get("exports", ["webm", "mp4", "glb", "ply", "json", "bvh"]))

    if mode == "parallax":
        depth = estimator.estimate(frames[keyframe_idx])
        progress(55, "Tracking camera motion…")
        camera_path = estimate_camera_path(frames, cuts)
        progress(64, "Rendering parallax animation…")
        result = parallax.render_parallax(
            frames, depth, camera_path, out_dir,
            watermark=bool(params.get("watermark", False)),
            formats=formats,
            keyframe_index=keyframe_idx,
            output_seconds=4.0,
            fps=12,
        )
        result["depth_backend"] = estimator.name
    elif mode == "mocap":
        progress(55, "Extracting body pose…")
        result = mocap.extract_mocap(frames, out_dir, fps=meta.get("fps", 12) or 12, formats=formats)
    elif mode == "scene":
        progress(50, "Fusing depth into a point cloud…")
        result = scene.build_point_cloud(frames, estimator, out_dir, formats=formats, step=1)
    else:
        raise RuntimeError(f"Unknown mode: {mode}")

    progress(92, "Finalizing artifacts…")
    result.update({
        "duration_seconds": round(duration, 2),
        "source_resolution": max(meta["width"], meta["height"]),
        "source_codec": meta["codec"],
        "frame_count": len(frames),
        "shots": len(cuts) + 1,
        "cut_frames": cuts,
        "keyframe_index": keyframe_idx,
        "sampling": "sparse-parallel",
    })
    progress(100, "Complete")
    return result
