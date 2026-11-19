"""3D scene mode: fuse depth maps into a colored point cloud (PLY).

This is the CPU-friendly foundation for the 3D mode. On GPU machines the same
output augments Gaussian splatting; the PLY is directly viewable in Three.js.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .depth import DepthEstimator


def _write_binary_ply(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    n = len(points)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    ).encode()
    xyz = points.astype(np.float32)
    rgb = colors.astype(np.uint8)
    packed = np.zeros(n, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                ("r", "u1"), ("g", "u1"), ("b", "u1")])
    packed["x"], packed["y"], packed["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    packed["r"], packed["g"], packed["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    with open(path, "wb") as f:
        f.write(header)
        f.write(packed.tobytes())


def build_point_cloud(
    frames: list[np.ndarray],
    estimator: DepthEstimator,
    out_dir: Path,
    max_points: int = 180_000,
    step: int = 4,
    formats: tuple[str, ...] = ("ply",),
) -> dict:
    if not frames:
        raise RuntimeError("Cannot reconstruct a scene without frames")

    first = frames[0]
    h, w = first.shape[:2]
    fx = fy = 0.9 * w
    cx, cy = w / 2.0, h / 2.0
    max_depth = 4.0

    all_points: list[np.ndarray] = []
    all_colors: list[np.ndarray] = []
    budget = max(1, max_points // max(1, len(frames[::step])))

    for fi, frame in enumerate(frames[::step]):
        depth = estimator.estimate(frame)
        depth_img = (depth * 255).astype(np.uint8)
        if fi == 0:
            cv2.imwrite(str(out_dir / "scene_depth.png"), depth_img)

        ys, xs = np.mgrid[0:h, 0:w]
        mask = (depth > 0.08) & (xs % max(1, w // int(np.sqrt(budget))) == 0) & \
               (ys % max(1, h // int(np.sqrt(budget))) == 0)
        xs, ys, d = xs[mask], ys[mask], depth[mask]
        if len(xs) == 0:
            continue
        z = d * max_depth + fi * 0.04
        x = (xs - cx) * z / fx
        y = -(ys - cy) * z / fy
        pts = np.stack([x, y, z], axis=1).astype(np.float32)
        cols = frame[ys, xs][:, ::-1]  # BGR -> RGB
        all_points.append(pts)
        all_colors.append(cols)

    if not all_points:
        raise RuntimeError("Point cloud reconstruction produced no points")
    points = np.concatenate(all_points, axis=0)
    colors = np.concatenate(all_colors, axis=0)
    if len(points) > max_points:
        sel = np.linspace(0, len(points) - 1, max_points).astype(int)
        points, colors = points[sel], colors[sel]

    outputs: dict[str, str] = {}
    if "ply" in formats:
        _write_binary_ply(out_dir / "scene.ply", points, colors)
        outputs["ply"] = "scene.ply"
    if "glb" in formats:
        from .exporters import export_point_cloud_glb
        export_point_cloud_glb(points, colors, out_dir / "scene.glb")
        outputs["glb"] = "scene.glb"
    if not outputs:
        raise RuntimeError("No supported 3D export format was requested")

    with open(out_dir / "scene_meta.json", "w") as f:
        json.dump({
            "points": int(len(points)),
            "width": w,
            "height": h,
            "intrinsics": {"fx": fx, "fy": fy, "cx": cx, "cy": cy},
            "depth_backend": estimator.name,
        }, f)

    return {
        "point_cloud": outputs.get("ply") or next(iter(outputs.values())),
        "formats": outputs,
        "depth": "scene_depth.png",
        "meta": "scene_meta.json",
        "points": int(len(points)),
        "width": w,
        "height": h,
    }
