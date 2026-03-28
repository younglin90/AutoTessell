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
from unittest.mock import MagicMock, patch

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
    get_bbox,
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
        # No triangles — _binary_bbox returns inf/-inf for all bounds, not an error.
        bbox = _binary_bbox(content)
        import math
        assert math.isinf(bbox.min_x)

    def test_content_too_short_for_header_raises(self):
        # Only 80 bytes — not enough for the 4-byte triangle count field.
        with pytest.raises(ValueError, match="too short"):
            _binary_bbox(b"\x00" * 80)

    def test_truncated_content_raises(self):
        # Header claims 10 triangles but file contains none of them.
        content = b"\x00" * 80 + struct.pack("<I", 10)  # claims 10 tris, 0 data
        with pytest.raises(ValueError, match="truncated"):
            _binary_bbox(content)


# ---------------------------------------------------------------------------
# get_bbox — public API (trimesh fallback path)
# ---------------------------------------------------------------------------

class TestGetBboxPurePython:
    """get_bbox() without trimesh — exercises the pure-Python parsers."""

    def test_ascii_stl_returns_correct_bbox(self, tmp_path: Path):
        stl = tmp_path / "shape.stl"
        stl.write_bytes(_ascii_stl_text().encode())
        with patch.dict(sys.modules, {"trimesh": None}):
            bbox = get_bbox(stl)
        assert bbox.min_x == pytest.approx(0.0)
        assert bbox.max_x == pytest.approx(4.0)

    def test_binary_stl_returns_correct_bbox(self, tmp_path: Path):
        stl = tmp_path / "shape.stl"
        stl.write_bytes(_simple_triangle_stl())
        with patch.dict(sys.modules, {"trimesh": None}):
            bbox = get_bbox(stl)
        assert bbox.max_x == pytest.approx(5.0)
        assert bbox.max_y == pytest.approx(3.0)
        assert bbox.max_z == pytest.approx(2.0)

    def test_binary_stl_with_solid_header_falls_through_to_binary_parser(self, tmp_path: Path):
        """Many CAD tools write binary STLs whose 80-byte header starts with
        'solid <name>'.  _is_ascii_stl() returns True, but _ascii_bbox raises
        ValueError (no vertex tokens).  get_bbox() must fall through to
        _binary_bbox() and still return correct bounds."""
        # Build a binary STL whose header starts with "solid mypart"
        solid_header = b"solid mypart" + b"\x00" * (80 - len(b"solid mypart"))
        tris = [((0, 0, 0), (7, 0, 0), (0, 4, 3))]
        count = struct.pack("<I", len(tris))
        body = b""
        for v0, v1, v2 in tris:
            body += struct.pack("<3f", 0.0, 0.0, 1.0)
            for vx, vy, vz in (v0, v1, v2):
                body += struct.pack("<3f", vx, vy, vz)
            body += b"\x00\x00"
        content = solid_header + count + body
        stl = tmp_path / "binary_solid_header.stl"
        stl.write_bytes(content)

        with patch.dict(sys.modules, {"trimesh": None}):
            bbox = get_bbox(stl)

        assert bbox.max_x == pytest.approx(7.0)
        assert bbox.max_y == pytest.approx(4.0)
        assert bbox.max_z == pytest.approx(3.0)


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

class TestAnalyzeStlComplexityFallbackExact:
    def test_fallback_exact_defaults(self, tmp_path: Path):
        """trimesh 미설치 시 정확한 기본값을 반환해야 한다."""
        stl = tmp_path / "shape.stl"
        stl.write_bytes(_simple_triangle_stl())
        with patch.dict(sys.modules, {"trimesh": None}):
            result = analyze_stl_complexity(stl)
        assert result.complexity_ratio == pytest.approx(1.0)
        assert result.surface_refine_min == 1
        assert result.surface_refine_max == 3
        assert result.feature_refine_level == 3
        assert result.resolve_feature_angle == pytest.approx(30.0)
        assert result.mean_curvature == pytest.approx(0.0)
        assert result.p95_curvature == pytest.approx(0.0)


class TestRepairStlToPathHappyPath:
    def test_watertight_mesh_returns_true(self, tmp_path: Path):
        """trimesh가 성공적으로 repair하면 mesh.is_watertight 결과를 반환해야 한다."""
        import trimesh as _trimesh

        src = tmp_path / "tet.stl"
        dst = tmp_path / "tet_out.stl"
        src.write_bytes(_simple_triangle_stl())

        # Mock the trimesh mesh object and repair functions
        mock_mesh = MagicMock()
        mock_mesh.is_watertight = True
        mock_repair = MagicMock()

        with patch.object(_trimesh, "load", return_value=mock_mesh):
            with patch.object(_trimesh, "repair", mock_repair):
                result = repair_stl_to_path(src, dst)

        assert result is True
        mock_mesh.export.assert_called_once_with(str(dst))


class TestRepairStlToPathNonWatertight:
    """repair_stl_to_path — trimesh succeeds but mesh is not watertight → returns False."""

    def test_non_watertight_mesh_returns_false(self, tmp_path: Path):
        """trimesh repair runs successfully, but mesh.is_watertight == False → return False."""
        import trimesh as _trimesh

        src = tmp_path / "open.stl"
        dst = tmp_path / "open_out.stl"
        src.write_bytes(_simple_triangle_stl())

        mock_mesh = MagicMock()
        mock_mesh.is_watertight = False
        mock_repair = MagicMock()

        with patch.object(_trimesh, "load", return_value=mock_mesh):
            with patch.object(_trimesh, "repair", mock_repair):
                result = repair_stl_to_path(src, dst)

        assert result is False
        mock_mesh.export.assert_called_once_with(str(dst))


# ---------------------------------------------------------------------------
# analyze_stl_complexity — feature angle capping in medium and low branches
# ---------------------------------------------------------------------------

class TestAnalyzeStlComplexityFeatureAngleCapping:
    """
    Verify the per-branch feature angle caps trigger when actual adjacency angles
    are high:
      medium (3 < ratio ≤ 10): feat_angle = min(feat_angle, 30.0) → 30.0
      low    (ratio ≤ 3)      : feat_angle = min(feat_angle, 40.0) → 40.0

    The previous tests in TestAnalyzeStlComplexityFaceAdjacency only exercised
    the empty-adjacency path (feat_angle default 30.0) and the high-ratio cap (20°).
    """

    def _make_stl(self, tmp_path: Path) -> Path:
        p = tmp_path / "shape.stl"
        p.write_bytes(_simple_triangle_stl())
        return p

    def _mock_mesh_with_angles(self, angle_rad: float):
        """Return a trimesh-like mock with 3 identical face adjacency angles."""
        import numpy as np
        mock_mesh = MagicMock()
        mock_mesh.vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        mock_mesh.scale = 1.0
        # Three equal angles, all > the relevant cap, so p10 ≈ angle_rad
        mock_mesh.face_adjacency_angles = np.array([angle_rad, angle_rad, angle_rad])
        return mock_mesh

    def test_medium_ratio_caps_feature_angle_at_30(self, tmp_path: Path):
        """3 < ratio ≤ 10 + large adjacency angle → feat_angle capped at ≤ 30°."""
        import numpy as np
        import trimesh as real_trimesh

        stl = self._make_stl(tmp_path)
        # ≈ 60° in radians — p10 → 60°, clip([15,60]) → 60°, then min(60, 30) = 30
        mock_mesh = self._mock_mesh_with_angles(1.047)
        medium_curv = np.array([1e-5] * 80 + [100.0] * 20)  # 3 < ratio ≤ 10

        with patch("trimesh.load", return_value=mock_mesh):
            with patch.object(
                real_trimesh.curvature,
                "discrete_mean_curvature_measure",
                return_value=medium_curv,
            ):
                result = analyze_stl_complexity(stl)

        assert result.resolve_feature_angle <= 30.0

    def test_low_ratio_caps_feature_angle_at_40(self, tmp_path: Path):
        """ratio ≤ 3 + large adjacency angle → feat_angle capped at ≤ 40°."""
        import numpy as np
        import trimesh as real_trimesh

        stl = self._make_stl(tmp_path)
        # ≈ 60° in radians — p10 → 60°, clip([15,60]) → 60°, then min(60, 40) = 40
        mock_mesh = self._mock_mesh_with_angles(1.047)
        low_curv = np.array([1e-5] * 50 + [100.0] * 50)  # ratio ≤ 3

        with patch("trimesh.load", return_value=mock_mesh):
            with patch.object(
                real_trimesh.curvature,
                "discrete_mean_curvature_measure",
                return_value=low_curv,
            ):
                result = analyze_stl_complexity(stl)

        assert result.resolve_feature_angle <= 40.0


class TestBinaryBboxNegativeCoords:
    def test_negative_coordinates(self):
        """음수 좌표가 포함된 바이너리 STL bbox 추출이 정확해야 한다."""
        tris = [((-2.0, -3.0, -4.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0))]
        bbox = _binary_bbox(_make_binary_stl(tris))
        assert pytest.approx(bbox.min_x) == -2.0
        assert pytest.approx(bbox.min_y) == -3.0
        assert pytest.approx(bbox.min_z) == -4.0
        assert pytest.approx(bbox.max_x) == 1.0
        assert pytest.approx(bbox.max_y) == 2.0
        assert pytest.approx(bbox.max_z) == 0.0


class TestRemeshSurfaceUniformException:
    def test_returns_false_when_pyacvd_raises_during_operation(self, tmp_path: Path):
        """pyacvd가 설치되어 있지만 remeshing 도중 예외를 발생시키면 False를 반환해야 한다."""
        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        src.write_bytes(_simple_triangle_stl())

        mock_pyacvd = MagicMock()
        mock_pyvista = MagicMock()
        mock_pyvista.read.side_effect = RuntimeError("mesh read failed")

        with patch.dict(sys.modules, {"pyacvd": mock_pyacvd, "pyvista": mock_pyvista}):
            result = remesh_surface_uniform(src, dst)

        assert result is False


class TestReconstructSurfacePoissonException:
    def test_returns_false_when_open3d_raises_during_operation(self, tmp_path: Path):
        """open3d가 설치되어 있지만 처리 도중 예외를 발생시키면 False를 반환해야 한다."""
        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        src.write_bytes(_simple_triangle_stl())

        mock_o3d = MagicMock()
        mock_o3d.io.read_triangle_mesh.side_effect = RuntimeError("o3d failed")

        mock_np = MagicMock()

        with patch.dict(sys.modules, {"open3d": mock_o3d, "numpy": mock_np}):
            result = reconstruct_surface_poisson(src, dst)

        assert result is False


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


# ---------------------------------------------------------------------------
# reconstruct_surface_poisson — empty mesh vertices path
# ---------------------------------------------------------------------------

class TestReconstructSurfacePoissonEmptyVertices:
    def test_returns_false_when_read_mesh_has_no_vertices(self, tmp_path: Path):
        """o3d.io.read_triangle_mesh returns a mesh with zero vertices → returns False."""
        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        src.write_bytes(_simple_triangle_stl())

        mock_o3d = MagicMock()
        mock_mesh = MagicMock()
        mock_mesh.vertices = []  # len == 0 → early return False
        mock_o3d.io.read_triangle_mesh.return_value = mock_mesh

        with patch.dict(sys.modules, {"open3d": mock_o3d}):
            result = reconstruct_surface_poisson(src, dst)

        assert result is False
        assert not dst.exists()


# ---------------------------------------------------------------------------
# analyze_stl_complexity — three ratio branches (high / medium / low)
# ---------------------------------------------------------------------------

class TestAnalyzeStlComplexityBranches:
    """
    Verify the three complexity-ratio branches produce the correct refinement levels.

    Strategy: patch trimesh.curvature.discrete_mean_curvature_measure to return
    controlled numpy arrays whose p95/mean ratio falls in the desired range, then
    let the real numpy code derive the StlComplexity fields.

    Distributions chosen so that the 95th-percentile value is 100.0 regardless
    of branch, while the mean varies:

      High  (ratio ≈ 16) : [1e-5]*94 + [100]*6  → mean ≈ 6,   p95 = 100
      Medium(ratio ≈ 5)  : [1e-5]*80 + [100]*20 → mean ≈ 20,  p95 = 100
      Low   (ratio ≈ 2)  : [1e-5]*50 + [100]*50 → mean ≈ 50,  p95 = 100
    """

    def _make_stl(self, tmp_path: Path) -> Path:
        p = tmp_path / "shape.stl"
        p.write_bytes(_simple_triangle_stl())
        return p

    def test_high_ratio_gives_fine_refinement(self, tmp_path: Path):
        """ratio > 10 → surface_refine_min=2, surface_refine_max=4, feature_refine_level=4."""
        import numpy as np
        import trimesh as real_trimesh

        stl = self._make_stl(tmp_path)
        high_ratio_curv = np.array([1e-5] * 94 + [100.0] * 6)

        with patch.object(
            real_trimesh.curvature,
            "discrete_mean_curvature_measure",
            return_value=high_ratio_curv,
        ):
            result = analyze_stl_complexity(stl)

        assert result.surface_refine_min == 2
        assert result.surface_refine_max == 4
        assert result.feature_refine_level == 4

    def test_medium_ratio_gives_moderate_refinement(self, tmp_path: Path):
        """3 < ratio ≤ 10 → surface_refine_min=1, surface_refine_max=3, feature_refine_level=3."""
        import numpy as np
        import trimesh as real_trimesh

        stl = self._make_stl(tmp_path)
        medium_ratio_curv = np.array([1e-5] * 80 + [100.0] * 20)

        with patch.object(
            real_trimesh.curvature,
            "discrete_mean_curvature_measure",
            return_value=medium_ratio_curv,
        ):
            result = analyze_stl_complexity(stl)

        assert result.surface_refine_min == 1
        assert result.surface_refine_max == 3
        assert result.feature_refine_level == 3

    def test_low_ratio_gives_coarse_refinement(self, tmp_path: Path):
        """ratio ≤ 3 → surface_refine_min=1, surface_refine_max=2, feature_refine_level=2."""
        import numpy as np
        import trimesh as real_trimesh

        stl = self._make_stl(tmp_path)
        low_ratio_curv = np.array([1e-5] * 50 + [100.0] * 50)

        with patch.object(
            real_trimesh.curvature,
            "discrete_mean_curvature_measure",
            return_value=low_ratio_curv,
        ):
            result = analyze_stl_complexity(stl)

        assert result.surface_refine_min == 1
        assert result.surface_refine_max == 2
        assert result.feature_refine_level == 2


# ---------------------------------------------------------------------------
# analyze_stl_complexity — face_adjacency_angles edge cases
# ---------------------------------------------------------------------------

class TestAnalyzeStlComplexityFaceAdjacency:
    """
    Tests for the face_adjacency_angles guard (lines 298-302 in stl_utils.py).

    When the mesh has no face-adjacency angles (e.g. a degenerate surface with a
    single triangle) the code falls into the `else: feat_angle = 30.0` branch.
    The branch clipping (`min(feat_angle, threshold)`) then caps that 30.0 value.
    """

    def _make_stl(self, tmp_path: Path) -> Path:
        p = tmp_path / "shape.stl"
        p.write_bytes(_simple_triangle_stl())
        return p

    def test_empty_face_adjacency_uses_default_feat_angle_30(self, tmp_path: Path):
        """mesh.face_adjacency_angles == [] → feat_angle defaults to 30.0."""
        import numpy as np
        import trimesh as real_trimesh

        stl = self._make_stl(tmp_path)

        mock_mesh = MagicMock()
        mock_mesh.vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        mock_mesh.scale = 1.0
        mock_mesh.face_adjacency_angles = np.array([])  # empty → else branch

        medium_curv = np.array([1e-5] * 80 + [100.0] * 20)  # ratio > 3 (medium)

        with patch("trimesh.load", return_value=mock_mesh):
            with patch.object(
                real_trimesh.curvature,
                "discrete_mean_curvature_measure",
                return_value=medium_curv,
            ):
                result = analyze_stl_complexity(stl)

        # Medium branch: feat_angle = min(30.0_default, 30.0) = 30.0
        assert result.resolve_feature_angle == pytest.approx(30.0)

    def test_high_ratio_feature_angle_capped_at_20(self, tmp_path: Path):
        """High-ratio branch caps resolve_feature_angle at 20.0."""
        import numpy as np
        import trimesh as real_trimesh

        stl = self._make_stl(tmp_path)

        mock_mesh = MagicMock()
        mock_mesh.vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        mock_mesh.scale = 1.0
        # Provide a high face adjacency angle (e.g. 45°) — high-ratio branch caps to 20°
        mock_mesh.face_adjacency_angles = np.array([0.785, 0.785, 0.785])  # ≈45° in radians

        high_ratio_curv = np.array([1e-5] * 94 + [100.0] * 6)  # ratio > 10

        with patch("trimesh.load", return_value=mock_mesh):
            with patch.object(
                real_trimesh.curvature,
                "discrete_mean_curvature_measure",
                return_value=high_ratio_curv,
            ):
                result = analyze_stl_complexity(stl)

        # High branch: feat_angle = min(p10_of_45deg_angles, 20.0) ≤ 20.0
        assert result.resolve_feature_angle <= 20.0


# ---------------------------------------------------------------------------
# reconstruct_surface_poisson — empty reconstructed mesh vertices path
# ---------------------------------------------------------------------------

class TestReconstructSurfacePoissonReconEmpty:
    """
    Tests the len(recon.vertices) == 0 guard (lines 220-221 in stl_utils.py).

    This fires when the Poisson reconstruction itself produces an empty mesh,
    which is distinct from the input mesh having no vertices.
    """

    def test_returns_false_when_reconstructed_mesh_has_no_vertices(self, tmp_path: Path):
        """After Poisson reconstruction, if recon.vertices is empty → returns False."""
        import numpy as np

        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        src.write_bytes(_simple_triangle_stl())

        mock_o3d = MagicMock()

        # Input mesh has vertices (passes the first guard)
        mock_in_mesh = MagicMock()
        mock_in_mesh.vertices = [1, 2, 3]  # len > 0

        # Reconstructed mesh has NO vertices (triggers the second guard)
        mock_recon = MagicMock()
        mock_recon.vertices = []
        densities = np.array([0.5, 0.6, 0.7])  # real numpy so percentile works

        mock_o3d.io.read_triangle_mesh.return_value = mock_in_mesh
        mock_o3d.geometry.TriangleMesh.create_from_point_cloud_poisson.return_value = (
            mock_recon,
            densities,
        )

        with patch.dict(sys.modules, {"open3d": mock_o3d}):
            result = reconstruct_surface_poisson(src, dst)

        assert result is False
        assert not dst.exists()


# ---------------------------------------------------------------------------
# reconstruct_surface_poisson — happy path
# ---------------------------------------------------------------------------

class TestReconstructSurfacePoissonHappyPath:
    def _make_happy_mocks(self):
        import numpy as np

        mock_o3d = MagicMock()
        mock_in_mesh = MagicMock()
        mock_in_mesh.vertices = [1, 2, 3]  # non-empty → passes first guard

        mock_recon = MagicMock()
        mock_recon.vertices = [1, 2, 3]  # non-empty → passes second guard
        densities = np.array([0.1, 0.3, 0.5, 0.7, 0.9])

        mock_o3d.io.read_triangle_mesh.return_value = mock_in_mesh
        mock_o3d.geometry.TriangleMesh.create_from_point_cloud_poisson.return_value = (
            mock_recon,
            densities,
        )
        return mock_o3d, mock_in_mesh

    def test_returns_true_and_writes_output_when_bbox_provided(self, tmp_path: Path):
        """bbox provided → normal_radius derived from bbox span, returns True."""
        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        src.write_bytes(_simple_triangle_stl())

        mock_o3d, _ = self._make_happy_mocks()
        bbox = BBox(0.0, 0.0, 0.0, 2.0, 1.0, 1.0)

        with patch.dict(sys.modules, {"open3d": mock_o3d}):
            result = reconstruct_surface_poisson(src, dst, bbox=bbox)

        assert result is True
        mock_o3d.io.write_triangle_mesh.assert_called_once()

    def test_bbox_none_uses_aabb_for_normal_radius(self, tmp_path: Path):
        """bbox=None → function calls get_axis_aligned_bounding_box on the mesh."""
        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        src.write_bytes(_simple_triangle_stl())

        mock_o3d, mock_in_mesh = self._make_happy_mocks()
        mock_aabb = MagicMock()
        mock_aabb.get_extent.return_value = [2.0, 1.0, 1.5]
        mock_in_mesh.get_axis_aligned_bounding_box.return_value = mock_aabb

        with patch.dict(sys.modules, {"open3d": mock_o3d}):
            result = reconstruct_surface_poisson(src, dst, bbox=None)

        assert result is True
        mock_in_mesh.get_axis_aligned_bounding_box.assert_called_once()


# ---------------------------------------------------------------------------
# remesh_surface_uniform — happy path
# ---------------------------------------------------------------------------

class TestRemeshSurfaceUniformHappyPath:
    def test_returns_true_on_success(self, tmp_path: Path):
        """pyacvd available and clustering succeeds → returns True."""
        src = tmp_path / "input.stl"
        dst = tmp_path / "output.stl"
        src.write_bytes(_simple_triangle_stl())

        mock_pyacvd = MagicMock()
        mock_pyvista = MagicMock()
        mock_clus = MagicMock()
        mock_pyacvd.Clustering.return_value = mock_clus

        with patch.dict(sys.modules, {"pyacvd": mock_pyacvd, "pyvista": mock_pyvista}):
            result = remesh_surface_uniform(src, dst)

        assert result is True
        mock_clus.subdivide.assert_called_once_with(3)
        mock_clus.cluster.assert_called_once()


# ---------------------------------------------------------------------------
# get_bbox — trimesh-present path
# ---------------------------------------------------------------------------

class TestGetBboxWithTrimesh:
    """
    Exercises the trimesh branch of get_bbox() (stl_utils.py lines 105-110).

    All tests in TestGetBboxPurePython patch trimesh to None, so the pure-Python
    fallback paths are covered there.  These tests explicitly call get_bbox()
    with a mocked-but-present trimesh so that the `import trimesh` inside
    get_bbox() succeeds and `mesh.bounds` is used to build the BBox.
    """

    def _mock_trimesh_bounds(self, lo, hi):
        """Return a mock trimesh mesh whose .bounds == (lo, hi)."""
        import numpy as np
        mock_mesh = MagicMock()
        mock_mesh.bounds = (np.array(lo), np.array(hi))
        return mock_mesh

    def test_ascii_stl_uses_trimesh_bounds(self, tmp_path: Path):
        """ASCII STL: get_bbox returns BBox built from trimesh mesh.bounds."""
        import trimesh as real_trimesh

        stl = tmp_path / "shape.stl"
        stl.write_bytes(_ascii_stl_text().encode())

        lo, hi = [1.0, 2.0, 3.0], [4.0, 5.0, 6.0]
        mock_mesh = self._mock_trimesh_bounds(lo, hi)

        with patch.object(real_trimesh, "load", return_value=mock_mesh):
            bbox = get_bbox(stl)

        assert bbox.min_x == pytest.approx(1.0)
        assert bbox.min_y == pytest.approx(2.0)
        assert bbox.min_z == pytest.approx(3.0)
        assert bbox.max_x == pytest.approx(4.0)
        assert bbox.max_y == pytest.approx(5.0)
        assert bbox.max_z == pytest.approx(6.0)

    def test_binary_stl_uses_trimesh_bounds(self, tmp_path: Path):
        """Binary STL: get_bbox returns BBox built from trimesh mesh.bounds."""
        import trimesh as real_trimesh

        stl = tmp_path / "shape.stl"
        stl.write_bytes(_simple_triangle_stl())

        lo, hi = [0.0, 0.0, 0.0], [10.0, 20.0, 30.0]
        mock_mesh = self._mock_trimesh_bounds(lo, hi)

        with patch.object(real_trimesh, "load", return_value=mock_mesh):
            bbox = get_bbox(stl)

        assert bbox.max_x == pytest.approx(10.0)
        assert bbox.max_y == pytest.approx(20.0)
        assert bbox.max_z == pytest.approx(30.0)

    def test_trimesh_bounds_take_priority_over_pure_python(self, tmp_path: Path):
        """
        When trimesh is available, get_bbox must use trimesh bounds
        (not the pure-Python parser).  The two results may differ because
        trimesh can correct winding/normals; this test verifies trimesh wins.
        """
        import trimesh as real_trimesh

        stl = tmp_path / "shape.stl"
        stl.write_bytes(_ascii_stl_text().encode())

        # trimesh claims different bounds than pure-Python would return
        lo, hi = [0.5, 0.5, 0.5], [3.5, 4.5, 2.5]
        mock_mesh = self._mock_trimesh_bounds(lo, hi)

        with patch.object(real_trimesh, "load", return_value=mock_mesh):
            bbox = get_bbox(stl)

        assert bbox.min_x == pytest.approx(0.5)
        assert bbox.max_x == pytest.approx(3.5)

    def test_returns_bbox_instance(self, tmp_path: Path):
        """get_bbox with trimesh must return a BBox dataclass instance."""
        import trimesh as real_trimesh

        stl = tmp_path / "shape.stl"
        stl.write_bytes(_simple_triangle_stl())

        mock_mesh = self._mock_trimesh_bounds([0.0, 0.0, 0.0], [1.0, 1.0, 1.0])

        with patch.object(real_trimesh, "load", return_value=mock_mesh):
            bbox = get_bbox(stl)

        assert isinstance(bbox, BBox)
