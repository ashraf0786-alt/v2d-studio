"""Depth estimation with a pluggable backend.

Default is a CPU heuristic that produces a usable near/far map. Set
DEPTH_BACKEND=depth_anything (and install torch + transformers) to use a real
monocular depth model — the interface is identical so no pipeline changes are
needed when upgrading to GPU inference.
"""
from __future__ import annotations

import cv2
import numpy as np

from ..config import settings


class DepthEstimator:
    name = "base"

    def estimate(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Return float32 depth in [0, 1] where 1 = closest to camera."""
        raise NotImplementedError


class HeuristicDepthEstimator(DepthEstimator):
    """Vertical-prior + radial depth: ground/center near, sky/corners far.

    Fast, dependency-free, and gives stable parallax for typical footage.
    """
    name = "heuristic-vertical-radial"

    def estimate(self, frame_bgr: np.ndarray) -> np.ndarray:
        h, w = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

        # Vertical prior: lower in frame -> nearer.
        ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
        vertical = np.broadcast_to(ys, (h, w))

        # Radial prior: image center marginally nearer.
        xs = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
        yy = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
        radial = np.sqrt(xs ** 2 + yy ** 2) / np.sqrt(2.0)

        # Texture: high local contrast tends to be foreground detail.
        blur = cv2.GaussianBlur(gray, (0, 0), 3)
        texture = cv2.GaussianBlur(np.abs(gray - blur), (0, 0), 8)
        texture = texture / (texture.max() + 1e-6)

        depth = 0.55 * vertical + 0.20 * (1.0 - radial) + 0.25 * texture
        depth = cv2.GaussianBlur(depth, (0, 0), min(h, w) / 90.0)
        dmin, dmax = depth.min(), depth.max()
        return ((depth - dmin) / (dmax - dmin + 1e-6)).astype(np.float32)


class DepthAnythingEstimator(DepthEstimator):
    """Optional real monocular depth via HuggingFace depth-anything-v2."""
    name = "depth-anything-v2"

    def __init__(self) -> None:
        from transformers import pipeline  # type: ignore
        self.pipe = pipeline("depth-estimation", model=settings.DEPTH_ANYTHING_MODEL)

    def estimate(self, frame_bgr: np.ndarray) -> np.ndarray:
        from PIL import Image
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self.pipe(Image.fromarray(rgb))
        d = np.asarray(result["depth"], dtype=np.float32)
        d = cv2.resize(d, (frame_bgr.shape[1], frame_bgr.shape[0]))
        dmin, dmax = d.min(), d.max()
        return (d - dmin) / (dmax - dmin + 1e-6)


def get_estimator() -> DepthEstimator:
    if settings.DEPTH_BACKEND == "depth_anything":
        try:
            return DepthAnythingEstimator()
        except Exception as exc:  # pragma: no cover - depends on optional deps
            print(f"[depth] Depth Anything unavailable ({exc}); falling back to heuristic.")
    return HeuristicDepthEstimator()
