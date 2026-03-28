"""
STL loading, bounding-box extraction, and repair.

Dependencies (all MIT/MPL, commercial-safe):
  trimesh  — pip install trimesh
  (pure-Python fallback if trimesh is unavailable)
"""

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class BBox:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @property
    def size_x(self) -> float:
        return self.max_x - self.min_x

    @property
    def size_y(self) -> float:
        return self.max_y - self.min_y

    @property
    def size_z(self) -> float:
        return self.max_z - self.min_z

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2

    @property
    def center_z(self) -> float:
        return (self.min_z + self.max_z) / 2

    @property
    def characteristic_length(self) -> float:
        """Longest bounding-box dimension — used to size the CFD domain."""
        return max(self.size_x, self.size_y, self.size_z)

    def __repr__(self) -> str:
        return (
            f"BBox(min=({self.min_x:.4g}, {self.min_y:.4g}, {self.min_z:.4g}) "
            f"max=({self.max_x:.4g}, {self.max_y:.4g}, {self.max_z:.4g}) "
            f"L={self.characteristic_length:.4g})"
        )


def get_bbox(stl_path: Path) -> BBox:
    """
    Extract bounding box from an STL file.
    Uses trimesh if available for accuracy; falls back to pure-Python parsing.
    """
    try:
        import trimesh
        mesh = trimesh.load(str(stl_path), force="mesh")
        lo, hi = mesh.bounds
        return BBox(lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])
    except ImportError:
        pass

    content = stl_path.read_bytes()
    if _is_ascii_stl(content):
        return _ascii_bbox(content)
    return _binary_bbox(content)


def repair_stl_to_path(stl_path: Path, output_path: Path) -> bool:
    """
    Attempt to repair a non-watertight STL using trimesh.
    Returns True if the result is watertight, False otherwise.
    Falls back to copying the original if trimesh is unavailable.
    """
    try:
        import trimesh
        from trimesh import repair as tr
        mesh = trimesh.load(str(stl_path), force="mesh")
        tr.fill_holes(mesh)
        tr.fix_winding(mesh)
        tr.fix_normals(mesh)
        mesh.export(str(output_path))
        return mesh.is_watertight
    except ImportError:
        import shutil
        shutil.copy2(stl_path, output_path)
        return False


# ---------------------------------------------------------------------------
# Pure-Python STL parsers (no dependencies)
# ---------------------------------------------------------------------------

def _is_ascii_stl(content: bytes) -> bool:
    try:
        header = content[:256].decode("ascii", errors="strict").strip().lower()
        return header.startswith("solid")
    except (UnicodeDecodeError, ValueError):
        return False


def _ascii_bbox(content: bytes) -> BBox:
    text = content.decode("ascii", errors="replace")
    coords = re.findall(
        r"vertex\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)", text
    )
    if not coords:
        raise ValueError("No vertices found in ASCII STL")
    xs = [float(c[0]) for c in coords]
    ys = [float(c[1]) for c in coords]
    zs = [float(c[2]) for c in coords]
    return BBox(min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _binary_bbox(content: bytes) -> BBox:
    num_tri = struct.unpack_from("<I", content, 80)[0]
    inf = float("inf")
    min_x = min_y = min_z = inf
    max_x = max_y = max_z = -inf

    for i in range(num_tri):
        # Each triangle: 12-byte normal + 3×12-byte vertices + 2-byte attr = 50 bytes
        base = 84 + i * 50 + 12  # skip normal
        for v in range(3):
            x, y, z = struct.unpack_from("<3f", content, base + v * 12)
            if x < min_x: min_x = x
            if y < min_y: min_y = y
            if z < min_z: min_z = z
            if x > max_x: max_x = x
            if y > max_y: max_y = y
            if z > max_z: max_z = z

    return BBox(min_x, min_y, min_z, max_x, max_y, max_z)
