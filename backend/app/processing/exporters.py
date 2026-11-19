"""Real artifact exporters: GLB (glTF 2.0), BVH, and helpers.

These turn pipeline output into formats users can actually open in Blender,
Three.js, or a game engine — rather than advertising formats we don't emit.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import cv2
import numpy as np


def _pad4(data: bytes, fill: bytes = b"\x00") -> bytes:
    return data + fill * ((4 - len(data) % 4) % 4)


def _write_glb(path: Path, gltf: dict, binary: bytes) -> Path:
    binary = _pad4(binary)
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js = _pad4(js, b" ")
    total = 12 + 8 + len(js) + 8 + len(binary)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(binary), b"BIN\x00"))
        f.write(binary)
    return path


class _BufferBuilder:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.views: list[dict] = []

    def add(self, data: bytes, target: int | None = None) -> int:
        data = _pad4(data)
        offset = sum(len(c) for c in self.chunks)
        self.chunks.append(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        self.views.append(view)
        return len(self.views) - 1


def export_point_cloud_glb(points: np.ndarray, colors: np.ndarray, out_path: Path) -> Path:
    """Write a binary glTF2 point cloud (POSITION + COLOR_0, primitive mode 0)."""
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    cols = np.asarray(colors, dtype=np.uint8).reshape(-1, 3)
    n = len(pts)
    bb = _BufferBuilder()
    pview = bb.add(pts.tobytes(), 34962)
    cview = bb.add(cols.tobytes(), 34962)
    mins = pts.min(axis=0).tolist()
    maxs = pts.max(axis=0).tolist()

    gltf = {
        "asset": {"version": "2.0", "generator": "Video to 3D Studio"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "reconstructed_points"}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0, "COLOR_0": 1},
            "mode": 0,
            "material": 0,
        }]}],
        "materials": [{
            "name": "vertex_colors",
            "doubleSided": True,
            "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1],
                                     "metallicFactor": 0, "roughnessFactor": 1},
        }],
        "buffers": [{"byteLength": sum(len(c) for c in bb.chunks)}],
        "bufferViews": bb.views,
        "accessors": [
            {"bufferView": pview, "componentType": 5126, "count": n,
             "type": "VEC3", "min": mins, "max": maxs},
            {"bufferView": cview, "componentType": 5121, "count": n,
             "type": "VEC3", "normalized": True},
        ],
    }
    return _write_glb(out_path, gltf, b"".join(bb.chunks))


def export_parallax_glb(image_path: Path, depth: np.ndarray, out_path: Path,
                        strength: float = 0.35, segments: tuple[int, int] = (96, 54)) -> Path:
    """Export a textured, depth-displaced mesh as GLB (opens in Blender/Three.js)."""
    img = cv2.imread(str(image_path))
    if img is None:
        raise RuntimeError("Could not read keyframe for GLB export")
    h, w = img.shape[:2]
    d = cv2.resize(depth, (w, h)).astype(np.float32)
    cols, rows = segments
    xs = np.linspace(-1.6, 1.6, cols, dtype=np.float32)
    ys = np.linspace(0.9, -0.9, rows, dtype=np.float32)
    gx, gy = np.meshgrid(xs, ys)
    gd = cv2.resize(d, (cols, rows))
    verts = np.stack([gx, gy, (gd - 0.45) * strength], axis=1).astype(np.float32)
    uvs = np.stack([np.linspace(0, 1, cols, dtype=np.float32)] * rows, axis=0)
    vvs = np.stack([np.linspace(1, 0, rows, dtype=np.float32)] * cols, axis=1)
    uvs = np.stack([uvs, vvs], axis=-1).astype(np.float32)

    idx = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            a = r * cols + c
            idx.extend([a, a + 1, a + cols, a + 1, a + cols + 1, a + cols])
    indices = np.asarray(idx, dtype=np.uint16)

    ok, buf = cv2.imencode(".jpg", img)
    if not ok:
        raise RuntimeError("Could not encode texture")
    texture = buf.tobytes()

    bb = _BufferBuilder()
    pview = bb.add(verts.tobytes(), 34962)
    uvview = bb.add(uvs.tobytes(), 34962)
    iview = bb.add(indices.tobytes(), 34963)
    tview = bb.add(texture)

    gltf = {
        "asset": {"version": "2.0", "generator": "Video to 3D Studio"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "parallax_surface"}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0, "TEXCOORD_0": 1},
            "indices": 2, "mode": 4, "material": 0,
        }]}],
        "materials": [{
            "name": "frame",
            "doubleSided": True,
            "pbrMetallicRoughness": {"baseColorTexture": {"index": 0},
                                     "metallicFactor": 0, "roughnessFactor": 1},
        }],
        "textures": [{"sampler": 0, "source": 0}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
        "images": [{"bufferView": tview, "mimeType": "image/jpeg", "name": "keyframe"}],
        "buffers": [{"byteLength": sum(len(c) for c in bb.chunks)}],
        "bufferViews": bb.views,
        "accessors": [
            {"bufferView": pview, "componentType": 5126, "count": len(verts),
             "type": "VEC3", "min": verts.min(axis=0).tolist(), "max": verts.max(axis=0).tolist()},
            {"bufferView": uvview, "componentType": 5126, "count": len(uvs), "type": "VEC2"},
            {"bufferView": iview, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
    }
    return _write_glb(out_path, gltf, b"".join(bb.chunks))


BVH_JOINTS = [
    ("Hips", 0), ("Head", 0), ("Neck", 1),
    ("LeftShoulder", 11), ("LeftElbow", 13), ("LeftWrist", 15),
    ("RightShoulder", 12), ("RightElbow", 14), ("RightWrist", 16),
    ("LeftHipProxy", 5), ("RightHipProxy", 6),
]


def export_bvh(pose_frames: list[list[list[float]]], out_path: Path, fps: int = 12) -> Path:
    """Write a BVH animation with one positional joint per tracked landmark."""
    lines = ["HIERARCHY", "ROOT Hips", "{"]
    for i, (name, _) in enumerate(BVH_JOINTS):
        if i == 0:
            lines += ["  OFFSET 0 0 0", "  CHANNELS 3 Xposition Yposition Zposition"]
            continue
        lines += [f"  JOINT {name}", "  {", "    OFFSET 0 0 0",
                  "    CHANNELS 3 Xposition Yposition Zposition"]
        if i == len(BVH_JOINTS) - 1:
            lines += ["    End Site", "    {", "      OFFSET 0 -0.1 0", "    }"]
        lines.append("  }")
    lines += ["}", "MOTION", f"Frames: {len(pose_frames)}", f"Frame Time: {1.0 / fps:.6f}"]

    for frame in pose_frames:
        values = []
        for _, idx in BVH_JOINTS:
            p = frame[idx] if idx < len(frame) else [0.5, 0.5, 0.0]
            values += [f"{(p[0] - 0.5) * 3:.5f}", f"{(0.5 - p[1]) * 3:.5f}",
                       f"{(p[2] or 0) * 3:.5f}"]
        lines.append(" ".join(values))
    out_path.write_text("\n".join(lines) + "\n")
    return out_path
