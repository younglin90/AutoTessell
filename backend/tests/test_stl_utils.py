"""
Unit tests for mesh/stl_utils.py

Covers:
  - BBox computed properties (size_x/y/z, center_x/y/z, characteristic_length)
  - BBox __repr__
  - _is_ascii_stl: detection of ASCII vs binary STL headers
  - _ascii_bbox: bounding box from ASCII STL
  - _binary_bbox: bounding box from binary STL
  - analyze_stl_complexity: fallback defaults when trimesh fails
  - repair_stl_to_path: fallback copy when trimesh is absent
  - remesh_surface_uniform: returns False when pyacvd is absent
  - reconstruct_surface_poisson: returns False when open3d is absent
"""

import struct
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Pre-load optional dependencies so sys.modules has them cached before any
# patch.dict(sys.modules, {"trimesh": None}) test removes them. Without this,
# the restore after the patch would delete the key rather than restore it,
# causing fresh re-imports that fail on Python 3.14 with loaded C extensions.
try:
    import trimesh as _trimesh_preload  # noqa: F401
    import numpy as _numpy_preload  # noqa: F401
except ImportError:
    pass

from mesh.stl_utils import (
    BBox,
    StlComplexity,
    _ascii_bbox,
    _binary_bbox,
    _is_ascii_stl,
    analyze_stl_complexity,
    reconstruct_surface_poisson,
    remesh_surface_uniform,
    repair_stl_to_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_binary_stl(triangles: list) -> bytes:
    """Build a minimal valid binary STL from a list of (v0, v1, v2) tuples."""
    header = b"\x00" * 80
    count = struct.pack("<I", len(triangles))
    body = b""
    for v0, v1, v2 in triangles:
        body += struct.pack("<3f", 0.0, 0.0, 1.0)  # normal
        for vx, vy, vz in (v0, v1, v2):
            body += struct.pack("<3f", vx, vy, vz)
        body += b"\x00\x00"  # attr byte count
    return header + count + body


def _simple_triangle_stl() -> bytes:
    """Single triangle spanning (0,0,0)-(5,0,0)-(0,3,2)."""
    return _make_binary_stl([((0, 0, 0), (5, 0, 0), (0, 3, 2))])


def _ascii_stl_text() -> str:
    return (
        "solid test_shape\n"
        "  facet normal 0 0 1\n"
        "    outer loop\n"
        "      vertex 1.0 2.0 0.0\n"
        "      vertex 4.0 0.0 0.0\n"
        "      vertex 0.0 5.0 3.0\n"
        "    endloop\n"
        "  endfacet\n"
        "endsolid test_shape\n"
    )


# ---------------------------------------------------------------------------
# BBox properties
# ---------------------------------------------------------------------------

class TestBBoxProperties:
    def _box(self) -> BBox:
        return BBox(min_x=1.0, min_y=2.0, min_z=3.0, max_x=4.0, max_y=6.0, max_z=9.0)

    def test_size_x(self):
        assert self._box().size_x == pytest.approx(3.0)

    def test_size_y(self):
        assert self._box().size_y == pytest.approx(4.0)

    def test_size_z(self):
        assert self._box().size_z == pytest.approx(6.0)

    def test_center_x(self):
        assert self._box().center_x == pytest.approx(2.5)

    def test_center_y(self):
        assert self._box().center_y == pytest.approx(4.0)

    def test_center_z(self):
        assert self._box().center_z == pytest.approx(6.0)

    def test_characteristic_length_is_max_dim(self):
        # size_z=6 is the largest
        assert self._box().characteristic_length == pytest.approx(6.0)

    def test_characteristic_length_equals_largest_dimension(self):
        b = BBox(0, 0, 0, 10, 3, 5)
        assert b.characteristic_length == pytest.approx(10.0)

    def test_unit_cube_characteristic_length(self):
        b = BBox(0, 0, 0, 1, 1, 1)
        assert b.characteristic_length == pytest.approx(1.0)

    def test_repr_contains_min_max(self):
        b = BBox(1, 2, 3, 4, 5, 6)
        r = repr(b)
        assert "BBox" in r
        assert "min=" in r
        assert "max=" in r

    def test_repr_contains_characteristic_length(self):
        b = BBox(0, 0, 0, 5, 1, 1)
        r = repr(b)
        assert "L=" in r
        # L should be 5
        assert "5" in r


# ---------------------------------------------------------------------------
# _is_ascii_stl
# ---------------------------------------------------------------------------

class TestIsAsciiStl:
    def test_ascii_stl_detected(self):
        content = b"solid myshape\nfacet normal 0 0 1\n..."
        assert _is_ascii_stl(content) is True

    def test_binary_stl_not_detected(self):
        content = _simple_triangle_stl()
        # Binary STL header is 80 bytes of zeros — does not start with "solid"
        assert _is_ascii_stl(content) is False

    def test_solid_with_leading_space_detected(self):
        content = b"  solid myshape\nfacet..."
        # Strip() is applied — should detect
        assert _is_ascii_stl(content) is True

    def test_binary_with_non_ascii_header(self):
        content = bytes([0xFF, 0xFE, 0x00, 0x00] + [0] * 76 + [1, 0, 0, 0])
        assert _is_ascii_stl(content) is False

    def test_empty_bytes_returns_false(self):
        assert _is_ascii_stl(b"") is False

    def test_solid_uppercase_detected(self):
        # After .lower() "SOLID" → "solid"
        content = b"SOLID shape\n..."
        assert _is_ascii_stl(content) is True


# ---------------------------------------------------------------------------
# _ascii_bbox
# ---------------------------------------------------------------------------

class TestAsciiBbox:
    def test_correct_bounds(self):
        content = _ascii_stl_text().encode()
        bbox = _ascii_bbox(content)
        assert bbox.min_x == pytest.approx(0.0)
        assert bbox.max_x == pytest.approx(4.0)
        assert bbox.min_y == pytest.approx(0.0)
        assert bbox.max_y == pytest.approx(5.0)
        assert bbox.min_z == pytest.approx(0.0)
        assert bbox.max_z == pytest.approx(3.0)

    def test_single_vertex_bbox(self):
        content = b"solid\n facet normal 0 0 1\n outer loop\n vertex 7.0 8.0 9.0\n vertex 7.0 8.0 9.0\n vertex 7.0 8.0 9.0\n endloop\nendfacet\nendsolid\n"
        bbox = _ascii_bbox(content)
        assert bbox.min_x == pytest.approx(7.0)
        assert bbox.max_x == pytest.approx(7.0)

    def test_raises_on_no_vertices(self):
        with pytest.raises(ValueError, match="vertex"):
            _ascii_bbox(b"solid empty\nendsolid\n")

    def test_scientific_notation_vertices(self):
        content = b"solid\nfacet normal 0 0 1\nouter loop\nvertex 1e2 2.0e1 3.0\nvertex 0 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid\n"
        bbox = _ascii_bbox(content)
        assert bbox.max_x == pytest.approx(100.0)
        assert bbox.max_y == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# _binary_bbox
# ---------------------------------------------------------------------------

class TestBinaryBbox:
    def test_single_triangle_bounds(self):
        content = _simple_triangle_stl()
        bbox = _binary_bbox(content)
        assert bbox.min_x == pytest.approx(0.0)
        assert bbox.max_x == pytest.approx(5.0)
        assert bbox.min_y == pytest.approx(0.0)
        assert bbox.max_y == pytest.approx(3.0)
        assert bbox.min_z == pytest.approx(0.0)
        assert bbox.max_z == pytest.approx(2.0)

    def test_two_triangle_bounds(self):
        tris = [
            ((0, 0, 0), (1, 0, 0), (0, 1, 0)),
            ((2, 3, 4), (5, 0, 0), (0, 0, 6)),
        ]
        bbox = _binary_bbox(_make_binary_stl(tris))
        assert bbox.max_x == pytest.approx(5.0)
        assert bbox.max_y == pytest.approx(3.0)
        assert bbox.max_z == pytest.approx(6.0)

    def test_zero_triangle_count(self):
        content = b"\x00" * 80 + struct.pack("<I", 0)
        # No triangles — but _binary_bbox would return inf/-inf for all
        # bounds. It should not raise.
        bbox = _binary_bbox(content)
        # With zero triangles the loop doesn't execute; values stay inf/-inf
        import math
        assert math.isinf(bbox.min_x)


# ---------------------------------------------------------------------------
# analyze_stl_complexity — fallback behavior when trimesh raises
# ---------------------------------------------------------------------------

class TestAnalyzeStlComplexityFallback:
    def test_returns_defaults_when_trimesh_absent(self, tmp_path: Path):
        stl = tmp_path / "shape.stl"
        stl.write_bytes(_simple_triangle_stl())
        with patch.dict(sys.modules, {"trimesh": None}):
            result = analyze_stl_complexity(stl)
        assert isinstance(result, StlComplexity)
        assert result.surface_refine_min >= 1
        assert result.surface_refine_max >= 1
        assert result.complexity_ratio >= 0.0

    def test_returns_defaults_when_file_is_degenerate(self, tmp_path: Path):
        # Empty binary STL (0 triangles) — trimesh may raise
        stl = tmp_path / "empty.stl"
        stl.write_bytes(b"\x00" * 80 + struct.pack("<I", 0))
        # Should not raise; returns a StlComplexity with default values
        result = analyze_stl_complexity(stl)
        assert isinstance(result, StlComplexity)

    def test_fallback_complexity_ratio_is_sane(self, tmp_path: Path):
        stl = tmp_path / "shape.stl"
        stl.write_bytes(_simple_triangle_stl())
        with patch.dict(sys.modules, {"trimesh": None}):
            result = analyze_stl_complexity(stl)
        assert 0.0 <= result.complexity_ratio <= 1000.0


# ---------------------------------------------------------------------------
# repair_stl_to_path — fallback when trimesh is not available
# ---------------------------------------------------------------------------

class TestRepairStlToPathFallback:
    def test_copies_file_when_trimesh_absent(self, tmp_path: Path):
        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        content = _simple_triangle_stl()
        src.write_bytes(content)

        with patch.dict(sys.modules, {"trimesh": None}):
            result = repair_stl_to_path(src, dst)

        assert dst.exists()
        assert dst.read_bytes() == content
        assert result is False  # trimesh not available → not watertight

    def test_copies_file_when_trimesh_raises(self, tmp_path: Path):
        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        content = _simple_triangle_stl()
        src.write_bytes(content)

        # Patch trimesh.load (already imported in this process) to raise
        import trimesh as _trimesh
        with patch.object(_trimesh, "load", side_effect=RuntimeError("load failed")):
            result = repair_stl_to_path(src, dst)

        assert dst.exists()
        assert dst.read_bytes() == content
        assert result is False


# ---------------------------------------------------------------------------
# remesh_surface_uniform — returns False when pyacvd is absent
# ---------------------------------------------------------------------------

class TestRemeshSurfaceUniformFallback:
    def test_returns_false_when_pyacvd_absent(self, tmp_path: Path):
        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        src.write_bytes(_simple_triangle_stl())

        with patch.dict(sys.modules, {"pyacvd": None, "pyvista": None}):
            result = remesh_surface_uniform(src, dst)

        assert result is False
        assert not dst.exists()


# ---------------------------------------------------------------------------
# reconstruct_surface_poisson — returns False when open3d is absent
# ---------------------------------------------------------------------------

class TestReconstructSurfacePoissonFallback:
    def test_returns_false_when_open3d_absent(self, tmp_path: Path):
        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        src.write_bytes(_simple_triangle_stl())

        with patch.dict(sys.modules, {"open3d": None}):
            result = reconstruct_surface_poisson(src, dst)

        assert result is False
        assert not dst.exists()
