"""Unit tests for exporters, shot detection and depth output."""
from __future__ import annotations

import numpy as np

from app.processing.depth import get_estimator
from app.processing.exporters import export_bvh, export_point_cloud_glb, export_parallax_glb
from app.processing.video import detect_shots


def test_depth_range():
    frame = np.zeros((60, 80, 3), dtype=np.uint8)
    frame[:30] = 200
    depth = get_estimator().estimate(frame)
    assert depth.shape == (60, 80)
    assert 0.0 <= depth.min() <= depth.max() <= 1.0


def test_shot_detection(tmp_path):
    a = np.zeros((40, 60, 3), dtype=np.uint8)
    b = np.full((40, 60, 3), 255, dtype=np.uint8)
    assert detect_shots([a, a, a, b, b]) == [3]


def test_glb_point_cloud(tmp_path):
    points = np.random.rand(100, 3).astype(np.float32)
    colors = np.random.randint(0, 255, (100, 3), dtype=np.uint8)
    out = export_point_cloud_glb(points, colors, tmp_path / "points.glb")
    assert out.read_bytes()[:4] == b"glTF"


def test_bvh_export(tmp_path):
    frames = [[[i / 100, j / 10, 0.0] for j in range(21)] for i in range(10)]
    out = export_bvh(frames, tmp_path / "motion.bvh", fps=10)
    text = out.read_text()
    assert "HIERARCHY" in text and "Frames: 10" in text and "CHANNELS 3" in text


def test_parallax_glb(tmp_path):
    import cv2
    img = np.random.randint(0, 255, (60, 80, 3), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "frame.jpg"), img)
    out = export_parallax_glb(tmp_path / "frame.jpg", np.ones((60, 80), np.float32),
                              tmp_path / "parallax.glb")
    assert out.read_bytes()[:4] == b"glTF"
