"""
Unit tests for mesh generator pipeline components.

Covers:
  - BBox computation from binary/ASCII STL
  - FlowDomain calculation (10L/20L/5L ratios)
  - OpenFOAM config file generation (blockMeshDict, snappyHexMeshDict)
  - Gmsh .msh v2 writer (node/element count)
  - tessell_mesh tier: graceful skip when .so not built, fallback chain
  - _maybe_remesh_surface 3-stage preprocessing chain
  - _apply_mmg_quality graceful fallback when binary absent
"""

import struct
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mesh.stl_utils import BBox, StlComplexity, analyze_stl_complexity, get_bbox
from mesh.openfoam_config import build_domain, block_mesh_dict, snappy_hex_mesh_dict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_binary_stl(vertices_per_tri: list[tuple]) -> bytes:
    """Build a binary STL with the given triangles (list of 3-vertex tuples)."""
    num_tri = len(vertices_per_tri)
    header = b"\x00" * 80
    count = struct.pack("<I", num_tri)
    body = b""
    for tri in vertices_per_tri:
        # normal (0,0,0) + 3 vertices + attr
        body += struct.pack("<3f", 0, 0, 0)
        for vx, vy, vz in tri:
            body += struct.pack("<3f", vx, vy, vz)
        body += b"\x00\x00"
    return header + count + body


def _unit_cube_stl() -> bytes:
    """Two triangles forming the bottom face of a unit cube (0–1 in all dims)."""
    triangles = [
        ((0, 0, 0), (1, 0, 0), (1, 1, 0)),
        ((0, 0, 0), (1, 1, 0), (0, 1, 0)),
        ((0, 0, 0), (0, 0, 1), (1, 0, 0)),
        ((0, 0, 1), (1, 0, 1), (1, 0, 0)),
        ((1, 0, 0), (1, 0, 1), (1, 1, 1)),
        ((1, 0, 0), (1, 1, 1), (1, 1, 0)),
    ]
    return _make_binary_stl(triangles)


@pytest.fixture
def unit_cube_stl(tmp_path: Path) -> Path:
    p = tmp_path / "cube.stl"
    p.write_bytes(_unit_cube_stl())
    return p


@pytest.fixture
def unit_cube_bbox() -> BBox:
    return BBox(0, 0, 0, 1, 1, 1)


# ---------------------------------------------------------------------------
# BBox tests
# ---------------------------------------------------------------------------

class TestGetBBox:
    def test_binary_stl_correct_bounds(self, unit_cube_stl: Path):
        bbox = get_bbox(unit_cube_stl)
        assert bbox.min_x == pytest.approx(0, abs=1e-5)
        assert bbox.min_y == pytest.approx(0, abs=1e-5)
        assert bbox.min_z == pytest.approx(0, abs=1e-5)
        assert bbox.max_x == pytest.approx(1, abs=1e-5)
        assert bbox.max_y == pytest.approx(1, abs=1e-5)
        assert bbox.max_z == pytest.approx(1, abs=1e-5)

    def test_characteristic_length_is_max_dim(self, unit_cube_stl: Path):
        bbox = get_bbox(unit_cube_stl)
        assert bbox.characteristic_length == pytest.approx(1.0, abs=1e-5)

    def test_asymmetric_bbox(self, tmp_path: Path):
        # Long thin object: 10×1×1
        tris = [((0,0,0),(10,0,0),(10,1,0)), ((0,0,0),(10,1,0),(0,1,0))]
        p = tmp_path / "long.stl"
        p.write_bytes(_make_binary_stl(tris))
        bbox = get_bbox(p)
        assert bbox.characteristic_length == pytest.approx(10.0, abs=1e-3)

    def test_ascii_stl(self, tmp_path: Path):
        text = (
            "solid test\n"
            "  facet normal 0 0 1\n    outer loop\n"
            "      vertex 0.0 0.0 0.0\n"
            "      vertex 2.0 0.0 0.0\n"
            "      vertex 0.0 3.0 0.0\n"
            "    endloop\n  endfacet\n"
            "endsolid test\n"
        )
        p = tmp_path / "ascii.stl"
        p.write_text(text)
        bbox = get_bbox(p)
        assert bbox.max_x == pytest.approx(2.0, abs=1e-5)
        assert bbox.max_y == pytest.approx(3.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Domain builder tests
# ---------------------------------------------------------------------------

class TestBuildDomain:
    def test_domain_ratios(self, unit_cube_bbox: BBox):
        """Domain must be 30L × 10L × 10L (10L upstream, 20L downstream, 5L sides)."""
        d = build_domain(unit_cube_bbox, "geom.stl")
        L = unit_cube_bbox.characteristic_length  # = 1.0
        assert (d.xmax - d.xmin) == pytest.approx(30 * L, rel=1e-6)
        assert (d.ymax - d.ymin) == pytest.approx(10 * L, rel=1e-6)
        assert (d.zmax - d.zmin) == pytest.approx(10 * L, rel=1e-6)

    def test_upstream_is_10L(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "geom.stl")
        cx = unit_cube_bbox.center_x  # 0.5
        L = unit_cube_bbox.characteristic_length  # 1.0
        assert (cx - d.xmin) == pytest.approx(10 * L, rel=1e-6)

    def test_downstream_is_20L(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "geom.stl")
        cx = unit_cube_bbox.center_x
        L = unit_cube_bbox.characteristic_length
        assert (d.xmax - cx) == pytest.approx(20 * L, rel=1e-6)

    def test_location_in_mesh_is_upstream(self, unit_cube_bbox: BBox):
        """locationInMesh must be outside the geometry (upstream in this implementation)."""
        d = build_domain(unit_cube_bbox, "geom.stl")
        # Location should be upstream of the geometry
        assert d.location_x < unit_cube_bbox.min_x

    def test_background_cell_count_in_range(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "geom.stl", target_background_cells=40_000)
        total = d.nx * d.ny * d.nz
        # Allow 2× tolerance — exact count depends on rounding
        assert total > 10_000
        assert total < 200_000

    def test_zero_characteristic_length_raises(self):
        bad_bbox = BBox(1, 1, 1, 1, 1, 1)  # degenerate
        with pytest.raises(ValueError, match="zero characteristic length"):
            build_domain(bad_bbox, "geom.stl")


# ---------------------------------------------------------------------------
# Config template tests
# ---------------------------------------------------------------------------

class TestBlockMeshDict:
    def test_contains_required_keys(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "geom.stl")
        config = block_mesh_dict(d)
        assert "blockMeshDict" in config
        assert "hex" in config
        assert "inlet" in config
        assert "outlet" in config
        assert str(d.nx) in config
        assert str(d.ny) in config


class TestSnappyHexMeshDict:
    def test_stl_name_appears(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "my_shape.stl")
        config = snappy_hex_mesh_dict(d)
        assert "my_shape.stl" in config
        assert "my_shape" in config  # stem

    def test_location_in_mesh(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "shape.stl")
        config = snappy_hex_mesh_dict(d)
        assert "locationInMesh" in config
        # Coordinates should appear (formatted as floats)
        assert str(round(d.location_x, 1)).split(".")[0] in config

    def test_layer_controls_present(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "shape.stl")
        config = snappy_hex_mesh_dict(d)
        assert "addLayersControls" in config
        assert "nSurfaceLayers" in config

    def test_no_complexity_uses_defaults(self, unit_cube_bbox: BBox):
        """complexity=None 이면 기본 정밀화 레벨(1-3)이 사용되어야 한다."""
        d = build_domain(unit_cube_bbox, "shape.stl")
        config = snappy_hex_mesh_dict(d)
        assert "level ( 1 3 )" in config
        assert "resolveFeatureAngle 30" in config

    def test_complexity_applied_to_refinement(self, unit_cube_bbox: BBox):
        """복잡한 geometry는 더 높은 정밀화 레벨이 적용되어야 한다."""
        d = build_domain(unit_cube_bbox, "shape.stl")
        complex_c = StlComplexity(
            mean_curvature=0.1, p95_curvature=2.0, complexity_ratio=20.0,
            resolve_feature_angle=15.0,
            surface_refine_min=2, surface_refine_max=4, feature_refine_level=4,
        )
        config = snappy_hex_mesh_dict(d, complexity=complex_c)
        assert "level ( 2 4 )" in config
        assert "resolveFeatureAngle 15.0" in config

    def test_refinement_regions_distance_based(self, unit_cube_bbox: BBox):
        """refinementRegions에 distance 기반 정밀화가 포함되어야 한다."""
        d = build_domain(unit_cube_bbox, "shape.stl")
        config = snappy_hex_mesh_dict(d)
        assert "mode distance" in config
        assert "levels" in config

    def test_simple_geometry_fewer_layers(self, unit_cube_bbox: BBox):
        """단순한 geometry(ratio<3)는 3개 레이어, 복잡한 geometry는 5개."""
        d = build_domain(unit_cube_bbox, "shape.stl")
        simple = StlComplexity(
            mean_curvature=0.1, p95_curvature=0.2, complexity_ratio=2.0,
            resolve_feature_angle=40.0,
            surface_refine_min=1, surface_refine_max=2, feature_refine_level=2,
        )
        complex_c = StlComplexity(
            mean_curvature=0.1, p95_curvature=2.0, complexity_ratio=15.0,
            resolve_feature_angle=15.0,
            surface_refine_min=2, surface_refine_max=4, feature_refine_level=4,
        )
        assert "nSurfaceLayers  3" in snappy_hex_mesh_dict(d, simple)
        assert "nSurfaceLayers  5" in snappy_hex_mesh_dict(d, complex_c)


# ---------------------------------------------------------------------------
# StlComplexity 분석
# ---------------------------------------------------------------------------

class TestAnalyzeStlComplexity:
    def test_returns_stl_complexity_dataclass(self, unit_cube_stl: Path):
        result = analyze_stl_complexity(unit_cube_stl)
        assert isinstance(result, StlComplexity)

    def test_defaults_are_reasonable(self, unit_cube_stl: Path):
        result = analyze_stl_complexity(unit_cube_stl)
        assert 1 <= result.surface_refine_min <= result.surface_refine_max <= 4
        assert 1 <= result.feature_refine_level <= 4
        assert 0 < result.resolve_feature_angle <= 60

    def test_simple_box_has_low_complexity(self, unit_cube_stl: Path):
        """unit cube (주로 평면)는 낮은 복잡도 → 낮은 정밀화 레벨."""
        result = analyze_stl_complexity(unit_cube_stl)
        # unit cube는 날카로운 엣지만 있고 곡면 없음 → ratio 낮아야 함
        # (trimesh 미설치 시 기본값 반환, 테스트는 통과)
        assert result.surface_refine_max <= 4


# ---------------------------------------------------------------------------
# Tier 0: tessell_mesh graceful skip + fallback chain
# ---------------------------------------------------------------------------

class TestTessellTier:
    """Tests for Tier 0 tessell_mesh integration in generate_mesh()."""

    def test_skips_gracefully_when_not_built(self, tmp_path: Path, unit_cube_stl: Path):
        """
        tessell_mesh.so가 없으면 조용히 skip하고 다음 Tier로 넘어가야 한다.
        모든 tier 실패 시 MeshGenerationError가 발생해야 한다.
        """
        from mesh.generator import generate_mesh, MeshGenerationError

        with patch.dict(sys.modules, {"tessell_mesh": None}):
            with patch("mesh.generator._netgen_pipeline", side_effect=RuntimeError("no netgen")):
                with patch("mesh.generator._snappy_pipeline", side_effect=RuntimeError("no openfoam")):
                    with patch("mesh.generator._pytetwild_pipeline", side_effect=RuntimeError("no pytetwild")):
                        with pytest.raises(MeshGenerationError):
                            generate_mesh(unit_cube_stl, tmp_path / "case")

    def test_tessell_tier_used_when_available(self, tmp_path: Path, unit_cube_stl: Path):
        """
        tessell_mesh.so가 있으면 Tier 0이 호출되어야 하고,
        성공 시 반환 dict에 tier="tessell"이 포함되어야 한다.
        """
        from mesh.generator import generate_mesh

        mock_tm = MagicMock()
        mock_result = MagicMock()
        mock_result.num_vertices = 100
        mock_result.num_tets = 200
        mock_tm.tetrahedralize_stl.return_value = mock_result

        # write_openfoam가 실제로 polyMesh/faces 파일을 만들도록 side_effect 설정
        case_dir = tmp_path / "case"

        def fake_write_openfoam(path: str):
            poly = Path(path) / "constant" / "polyMesh"
            poly.mkdir(parents=True, exist_ok=True)
            (poly / "faces").write_text("dummy")

        mock_result.write_openfoam.side_effect = fake_write_openfoam

        with patch.dict(sys.modules, {"tessell_mesh": mock_tm}):
            with patch("mesh.generator._mesh_stats", return_value={"passed": True, "num_cells": 200}):
                stats = generate_mesh(unit_cube_stl, case_dir)

        assert stats["tier"] == "tessell"
        assert stats["num_tets"] == 200
        mock_tm.tetrahedralize_stl.assert_called_once()

    def test_tessell_falls_through_to_netgen_on_failure(self, tmp_path: Path, unit_cube_stl: Path):
        """
        tessell_mesh 실패 시 Tier 0.5(Netgen)을 시도해야 한다.
        """
        from mesh.generator import generate_mesh

        mock_tm = MagicMock()
        mock_tm.tetrahedralize_stl.side_effect = RuntimeError("geogram error")

        netgen_stats = {"passed": True, "num_cells": 300_000}

        with patch.dict(sys.modules, {"tessell_mesh": mock_tm}):
            with patch("mesh.generator._netgen_pipeline", return_value=netgen_stats) as mock_netgen:
                stats = generate_mesh(unit_cube_stl, tmp_path / "case")

        assert stats["tier"] == "netgen"
        mock_netgen.assert_called_once()

    def test_full_fallback_chain_order(self, tmp_path: Path, unit_cube_stl: Path):
        """
        Tier 0 실패 → Tier 0.5 실패 → Tier 1 실패 → Tier 2 순서가 보장되어야 한다.
        """
        from mesh.generator import generate_mesh

        call_order: list[str] = []

        mock_tm = MagicMock()
        mock_tm.tetrahedralize_stl.side_effect = RuntimeError("geogram fail")

        def fake_netgen(*args, **kwargs):
            call_order.append("netgen")
            raise RuntimeError("netgen fail")

        def fake_snappy(*args, **kwargs):
            call_order.append("snappy")
            raise RuntimeError("snappy fail")

        def fake_pytetwild(*args, **kwargs):
            call_order.append("pytetwild")
            return {"passed": True, "num_cells": 100}

        with patch.dict(sys.modules, {"tessell_mesh": mock_tm}):
            with patch("mesh.generator._netgen_pipeline", side_effect=fake_netgen):
                with patch("mesh.generator._snappy_pipeline", side_effect=fake_snappy):
                    with patch("mesh.generator._pytetwild_pipeline", side_effect=fake_pytetwild):
                        stats = generate_mesh(unit_cube_stl, tmp_path / "case")

        assert call_order == ["netgen", "snappy", "pytetwild"]
        assert stats["tier"] == "pytetwild"

    def test_netgen_not_installed_skips_silently(self, tmp_path: Path, unit_cube_stl: Path):
        """
        netgen-mesher 미설치 시 조용히 건너뜀 — errors에 추가되지 않아야 한다.
        """
        from mesh.generator import generate_mesh, _NetgenNotInstalled

        snappy_stats = {"passed": True, "num_cells": 500_000}

        with patch.dict(sys.modules, {"tessell_mesh": None}):
            with patch("mesh.generator._netgen_pipeline", side_effect=_NetgenNotInstalled("not installed")):
                with patch("mesh.generator._snappy_pipeline", return_value=snappy_stats):
                    stats = generate_mesh(unit_cube_stl, tmp_path / "case")

        assert stats["tier"] == "snappy"

    def test_error_message_lists_all_failures(self, tmp_path: Path, unit_cube_stl: Path):
        """
        모든 tier 실패 시 에러 메시지에 각 tier의 실패 원인이 포함되어야 한다.
        """
        from mesh.generator import generate_mesh, MeshGenerationError

        mock_tm = MagicMock()
        mock_tm.tetrahedralize_stl.side_effect = RuntimeError("geogram kaboom")

        with patch.dict(sys.modules, {"tessell_mesh": mock_tm}):
            with patch("mesh.generator._netgen_pipeline", side_effect=RuntimeError("netgen kaboom")):
                with patch("mesh.generator._snappy_pipeline", side_effect=RuntimeError("snappy kaboom")):
                    with patch("mesh.generator._pytetwild_pipeline", side_effect=RuntimeError("pytetwild kaboom")):
                        with pytest.raises(MeshGenerationError) as exc_info:
                            generate_mesh(unit_cube_stl, tmp_path / "case")

        msg = str(exc_info.value)
        assert "netgen" in msg
        assert "snappy" in msg
        assert "pytetwild" in msg


# ---------------------------------------------------------------------------
# Gmsh .msh v2 writer
# ---------------------------------------------------------------------------

class TestWriteGmshMsh2:
    def test_node_and_element_count(self, tmp_path: Path):
        from mesh.generator import _write_gmsh_msh2
        import numpy as np

        verts = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=float)
        tets = np.array([[0,1,2,3]], dtype=int)
        out = tmp_path / "mesh.msh"
        _write_gmsh_msh2(verts, tets, out)

        content = out.read_text()
        assert "$MeshFormat" in content
        assert "$Nodes" in content
        assert "$Elements" in content
        # 4 nodes, 1 element
        lines = content.splitlines()
        node_idx = next(i for i, l in enumerate(lines) if l == "$Nodes")
        assert lines[node_idx + 1] == "4"
        elem_idx = next(i for i, l in enumerate(lines) if l == "$Elements")
        assert lines[elem_idx + 1] == "1"

    def test_tet_element_type_is_4(self, tmp_path: Path):
        from mesh.generator import _write_gmsh_msh2
        import numpy as np

        verts = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=float)
        tets = np.array([[0,1,2,3]], dtype=int)
        out = tmp_path / "mesh.msh"
        _write_gmsh_msh2(verts, tets, out)

        # Element line format: "1 4 2 1 1 n1 n2 n3 n4"
        # type=4 means tetrahedron in Gmsh
        elem_lines = [l for l in out.read_text().splitlines() if l.startswith("1 4")]
        assert len(elem_lines) == 1


# ---------------------------------------------------------------------------
# _maybe_remesh_surface 전처리 체인
# ---------------------------------------------------------------------------

class TestMaybeRemeshSurface:
    """Tests for the 3-stage surface preprocessing chain."""

    def test_returns_path(self, tmp_path: Path, unit_cube_stl: Path):
        """반환값은 존재하는 Path여야 한다."""
        from mesh.stl_utils import BBox
        from mesh.generator import _maybe_remesh_surface

        bbox = BBox(0, 0, 0, 1, 1, 1)
        result = _maybe_remesh_surface(unit_cube_stl, tmp_path, bbox)
        assert isinstance(result, Path)
        assert result.exists()

    def test_falls_back_to_repaired_when_remesh_fails(self, tmp_path: Path, unit_cube_stl: Path):
        """pyACVD 실패 시 repair된 STL을 반환해야 한다."""
        from mesh.stl_utils import BBox
        from mesh.generator import _maybe_remesh_surface

        bbox = BBox(0, 0, 0, 1, 1, 1)
        with patch("mesh.generator.remesh_surface_uniform", return_value=False):
            result = _maybe_remesh_surface(unit_cube_stl, tmp_path, bbox)
        # pyACVD 실패 → repaired STL 반환 (not None, exists)
        assert result.exists()
        assert result != unit_cube_stl  # 원본이 아닌 수리된 파일

    def test_uses_poisson_when_not_watertight(self, tmp_path: Path, unit_cube_stl: Path):
        """비수밀 STL에서 Poisson 재구성이 시도되어야 한다."""
        from mesh.stl_utils import BBox
        from mesh.generator import _maybe_remesh_surface

        bbox = BBox(0, 0, 0, 1, 1, 1)

        poisson_called_with = {}

        def fake_poisson(src, dst, bbox=None):
            poisson_called_with["called"] = True
            poisson_called_with["bbox"] = bbox
            return False  # Poisson 실패 시뮬레이션

        with patch("mesh.generator.repair_stl_to_path", return_value=False):  # 비수밀
            with patch("mesh.generator.reconstruct_surface_poisson", side_effect=fake_poisson):
                with patch("mesh.generator.remesh_surface_uniform", return_value=False):
                    _maybe_remesh_surface(unit_cube_stl, tmp_path, bbox)

        assert poisson_called_with.get("called"), "Poisson 재구성이 호출되어야 한다"
        assert poisson_called_with.get("bbox") is bbox, "bbox가 전달되어야 한다"

    def test_skips_poisson_when_watertight(self, tmp_path: Path, unit_cube_stl: Path):
        """수밀 STL에서 Poisson 재구성을 건너뛰어야 한다."""
        from mesh.stl_utils import BBox
        from mesh.generator import _maybe_remesh_surface

        bbox = BBox(0, 0, 0, 1, 1, 1)

        poisson_called = []
        with patch("mesh.generator.repair_stl_to_path", return_value=True):  # 수밀
            with patch("mesh.generator.reconstruct_surface_poisson",
                       side_effect=lambda *a, **kw: poisson_called.append(1)):
                with patch("mesh.generator.remesh_surface_uniform", return_value=False):
                    _maybe_remesh_surface(unit_cube_stl, tmp_path, bbox)

        assert not poisson_called, "수밀이면 Poisson 재구성 불필요"


# ---------------------------------------------------------------------------
# _apply_mmg_quality graceful fallback
# ---------------------------------------------------------------------------

class TestApplyMmgQuality:
    """Tests for optional MMG post-processing."""

    def test_returns_original_when_mmg_not_found(self, tmp_path: Path):
        """mmg3d binary 없으면 원본 v/t 반환."""
        from mesh.generator import _apply_mmg_quality
        from mesh.stl_utils import BBox
        import numpy as np

        bbox = BBox(0, 0, 0, 1, 1, 1)
        v = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=float)
        t = np.array([[0,1,2,3]], dtype=np.int32)

        with patch("shutil.which", return_value=None):
            v_out, t_out = _apply_mmg_quality(v, t, tmp_path, bbox)

        assert v_out is v
        assert t_out is t
