"""Camera motion estimation between frames using phase correlation."""
from __future__ import annotations

import cv2
import numpy as np


def estimate_camera_path(frames: list[np.ndarray], cuts: list[int] | None = None) -> list[dict]:
    """Estimate accumulated 2D camera translation across the sequence.

    Returns a list of {dx, dy, magnitude} per frame, in pixels relative to the
    previous frame. Phase correlation is robust to lighting changes and cheap.
    """
    path: list[dict] = []
    if not frames:
        return path
    path.append({"dx": 0.0, "dy": 0.0, "magnitude": 0.0, "cut": False})
    cut_set = set(cuts or [])
    prev = None
    for i, frame in enumerate(frames):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        if i in cut_set:
            # Don't infer camera motion across a shot boundary.
            prev = gray
            path.append({"dx": 0.0, "dy": 0.0, "magnitude": 0.0, "cut": True})
            continue
        if prev is None:
            prev = gray
            continue
        shift, response = cv2.phaseCorrelate(prev, gray)
        dx, dy = float(shift[0]), float(shift[1])
        if not np.isfinite(dx) or not np.isfinite(dy) or response < 0.15:
            dx, dy = 0.0, 0.0
        # Clamp outliers (cuts, flashes) so the parallax path stays smooth.
        dx = max(-12.0, min(12.0, dx))
        dy = max(-12.0, min(12.0, dy))
        path.append({"dx": dx, "dy": dy, "magnitude": float(np.hypot(dx, dy))})
        prev = gray
    return path
