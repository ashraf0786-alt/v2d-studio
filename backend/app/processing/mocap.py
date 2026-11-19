"""Avatar mocap mode: 2D/3D body pose extraction per frame.

Uses MediaPipe Pose when available. A clearly-flagged procedural fallback keeps
the mode functional on platforms where MediaPipe has no wheel (e.g. some ARM
builds), so the pipeline can still be demonstrated end-to-end.
"""
from __future__ import annotations

import json
import platform
from pathlib import Path

import cv2
import numpy as np

from ..config import settings

# MediaPipe Pose body part connections (pairs of landmark indices).
CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (17, 18), (18, 19), (19, 20),
]


def _procedural_pose(t: float) -> list[list[float]]:
    """A simple waving humanoid used only when MediaPipe is unavailable."""
    p = [[0.5, 0.5, 0.0] for _ in range(21)]
    p[0] = [0.5, 0.2, 0.0]     # head
    p[1] = [0.5, 0.3, 0.0]
    p[2] = [0.5, 0.42, 0.0]
    p[3] = [0.5, 0.58, 0.0]
    p[4] = [0.5, 0.72, 0.0]
    p[5], p[6] = [0.42, 0.35, 0.0], [0.34, 0.5, 0.0]
    p[11], p[12] = [0.58, 0.35, 0.0], [0.68, 0.45 + 0.08 * np.sin(t * 4), 0.0]
    p[13], p[14] = [0.36, 0.52, 0.0], [0.28, 0.66, 0.0]
    p[15], p[16] = [0.64, 0.52, 0.0], [0.74, 0.66 + 0.05 * np.sin(t * 4), 0.0]
    return p


def extract_mocap(frames: list[np.ndarray], out_dir: Path, fps: int = 12,
                  formats: tuple[str, ...] = ("json",)) -> dict:
    sequences: list[list[list[float]]] = []
    demo = False

    backend = settings.POSE_BACKEND.lower()
    if backend == "auto" and platform.machine().lower() in ("aarch64", "arm64"):
        backend = "demo"  # MediaPipe Tasks is unstable on some ARM builds

    try:  # pragma: no cover - depends on optional dependency + model asset
        if backend == "demo":
            raise RuntimeError("demo backend selected")
        import mediapipe as mp
        model_path = settings.pose_model_path
        if not model_path.exists():
            raise FileNotFoundError(f"Pose model not found at {model_path}")

        if hasattr(mp, "solutions"):  # legacy API (x86 wheels)
            detector = mp.solutions.pose.Pose(static_image_mode=True, model_complexity=0)
            for frame in frames:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = detector.process(rgb)
                lm = res.pose_landmarks.landmark if res.pose_landmarks else None
                sequences.append([[p.x, p.y, p.z] for p in lm] if lm
                                 else [[0.5, 0.5, 0.0] for _ in range(21)])
            detector.close()
        else:  # MediaPipe Tasks API (newer / ARM wheels)
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
            opts = vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=1,
            )
            detector = vision.PoseLandmarker.create_from_options(opts)
            for frame in frames:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
                lm = res.pose_landmarks[0] if res.pose_landmarks else None
                sequences.append([[p.x, p.y, p.z] for p in lm[:21]] if lm
                                 else [[0.5, 0.5, 0.0] for _ in range(21)])
            detector.close()
    except Exception as exc:
        demo = True
        sequences = [_procedural_pose(i / max(1, len(frames))) for i in range(len(frames))]
        print(f"[mocap] Real pose estimation unavailable ({exc}); using procedural demo animation.")

    with open(out_dir / "pose.json", "w") as f:
        json.dump({
            "fps": fps,
            "frames": sequences,
            "connections": CONNECTIONS,
            "landmark_count": 21,
            "demo": demo,
        }, f)
    extra: dict = {}
    if "bvh" in formats:
        from .exporters import export_bvh
        export_bvh(sequences, out_dir / "motion.bvh", fps)
        extra["bvh"] = "motion.bvh"

    return {
        **extra,
        "pose": "pose.json",
        "frames": len(sequences),
        "fps": fps,
        "demo": demo,
        "connections": CONNECTIONS,
    }
