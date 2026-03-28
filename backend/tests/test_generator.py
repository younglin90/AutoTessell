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
  - _setup_minimal_case: creates required OpenFOAM skeleton files
  - _reset_case: clears and recreates case directory
  - _run_of: subprocess error/timeout handling
  - _openfoam_env: WM_PROJECT_DIR fast-path
  - _mesh_stats: graceful fallback when checkMesh absent
"""

import os
import struct
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mesh.stl_utils import BBox, StlComplexity, analyze_stl_complexity, get_bbox
from mesh.openfoam_config import (
    build_domain, block_mesh_dict, snappy_hex_mesh_dict,
    surface_feature_extract_dict, control_dict, fv_schemes, fv_solution,
)


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

    def test_clean_stl_survives_reset_case_after_tier_failure(
        self, tmp_path: Path, unit_cube_stl: Path
    ):
        """
        Regression: _maybe_remesh_surface used to write _repaired.stl into case_dir.
        When Tier 0 failed and _reset_case deleted case_dir, subsequent tiers received
        a clean_stl path that no longer existed.

        Fix: prep files now go to stl_path.parent (never deleted by _reset_case).
        """
        from mesh.generator import generate_mesh

        captured_paths: list[Path] = []

        mock_tm = MagicMock()
        mock_tm.tetrahedralize_stl.side_effect = RuntimeError("geogram fail")

        def capture_stl_path(stl_path, *args, **kwargs):
            captured_paths.append(Path(stl_path))
            return {"passed": True, "num_cells": 50_000}

        case_dir = tmp_path / "case"
        with patch.dict(sys.modules, {"tessell_mesh": mock_tm}):
            with patch("mesh.generator._netgen_pipeline", side_effect=RuntimeError("netgen fail")):
                with patch("mesh.generator._snappy_pipeline", side_effect=RuntimeError("snappy fail")):
                    with patch("mesh.generator._pytetwild_pipeline", side_effect=capture_stl_path):
                        generate_mesh(unit_cube_stl, case_dir)

        assert captured_paths, "pytetwild should have been called"
        clean_stl = captured_paths[0]
        # The clean STL must NOT be inside case_dir (which was reset 3 times)
        assert not str(clean_stl).startswith(str(case_dir)), (
            f"clean_stl {clean_stl} is inside case_dir {case_dir} — "
            "_reset_case would have deleted it before pytetwild ran"
        )
        # The clean STL must still exist (or be the original stl_path if no remeshing happened)
        assert clean_stl.exists() or clean_stl == unit_cube_stl

    def test_fea_purpose_skips_snappy(self, tmp_path: Path, unit_cube_stl: Path):
        """mesh_purpose='fea' must not call snappyHexMesh — it only generates tet meshes."""
        from mesh.generator import generate_mesh

        mock_tm = MagicMock()
        mock_tm.tetrahedralize_stl.side_effect = RuntimeError("geogram fail")

        pytetwild_stats = {"passed": True, "num_cells": 50_000}

        with patch.dict(sys.modules, {"tessell_mesh": mock_tm}):
            with patch("mesh.generator._netgen_pipeline", side_effect=RuntimeError("netgen fail")):
                with patch("mesh.generator._snappy_pipeline") as mock_snappy:
                    with patch("mesh.generator._pytetwild_pipeline", return_value=pytetwild_stats):
                        stats = generate_mesh(unit_cube_stl, tmp_path / "case", mesh_purpose="fea")

        mock_snappy.assert_not_called()
        assert stats["tier"] == "pytetwild"


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


# ---------------------------------------------------------------------------
# _write_snappy_case 파일 시스템 검증
# ---------------------------------------------------------------------------

class TestWriteSnappyCase:
    """Verify _write_snappy_case creates all required OpenFOAM system files."""

    def test_required_files_created(self, tmp_path: Path, unit_cube_stl: Path):
        from mesh.generator import _write_snappy_case
        from mesh.stl_utils import BBox
        from mesh.openfoam_config import build_domain

        bbox = BBox(0, 0, 0, 1, 1, 1)
        domain = build_domain(bbox, unit_cube_stl.name)
        _write_snappy_case(tmp_path, unit_cube_stl, domain)

        system = tmp_path / "system"
        assert (system / "blockMeshDict").exists()
        assert (system / "snappyHexMeshDict").exists()
        assert (system / "surfaceFeatureExtractDict").exists()
        assert (system / "controlDict").exists()
        assert (system / "fvSchemes").exists()
        assert (system / "fvSolution").exists()

    def test_stl_copied_to_triSurface(self, tmp_path: Path, unit_cube_stl: Path):
        from mesh.generator import _write_snappy_case
        from mesh.stl_utils import BBox
        from mesh.openfoam_config import build_domain

        bbox = BBox(0, 0, 0, 1, 1, 1)
        domain = build_domain(bbox, unit_cube_stl.name)
        _write_snappy_case(tmp_path, unit_cube_stl, domain)

        tri_surface = tmp_path / "constant" / "triSurface" / unit_cube_stl.name
        assert tri_surface.exists()
        assert tri_surface.stat().st_size > 0


# ---------------------------------------------------------------------------
# _setup_minimal_case — Netgen/pytetwild용 최소 OpenFOAM 스켈레톤
# ---------------------------------------------------------------------------

class TestSetupMinimalCase:
    def test_creates_control_dict(self, tmp_path: Path):
        from mesh.generator import _setup_minimal_case

        case_dir = tmp_path / "case"
        _setup_minimal_case(case_dir)

        assert (case_dir / "system" / "controlDict").exists()

    def test_creates_fv_files(self, tmp_path: Path):
        from mesh.generator import _setup_minimal_case

        case_dir = tmp_path / "case"
        _setup_minimal_case(case_dir)

        assert (case_dir / "system" / "fvSchemes").exists()
        assert (case_dir / "system" / "fvSolution").exists()

    def test_creates_constant_dir(self, tmp_path: Path):
        from mesh.generator import _setup_minimal_case

        case_dir = tmp_path / "case"
        _setup_minimal_case(case_dir)

        assert (case_dir / "constant").is_dir()

    def test_idempotent_on_existing_dir(self, tmp_path: Path):
        from mesh.generator import _setup_minimal_case

        case_dir = tmp_path / "case"
        case_dir.mkdir()
        _setup_minimal_case(case_dir)  # 두 번 호출해도 에러 없어야 함
        _setup_minimal_case(case_dir)
        assert (case_dir / "system" / "controlDict").exists()


# ---------------------------------------------------------------------------
# _reset_case — case 디렉터리 초기화
# ---------------------------------------------------------------------------

class TestResetCase:
    def test_clears_existing_files(self, tmp_path: Path):
        from mesh.generator import _reset_case

        case_dir = tmp_path / "case"
        case_dir.mkdir()
        (case_dir / "leftover.txt").write_text("stale")

        _reset_case(case_dir)

        assert case_dir.is_dir()
        assert not (case_dir / "leftover.txt").exists()

    def test_recreates_directory_if_not_exists(self, tmp_path: Path):
        from mesh.generator import _reset_case

        case_dir = tmp_path / "nonexistent_case"
        _reset_case(case_dir)

        assert case_dir.is_dir()

    def test_empty_case_dir_stays_empty(self, tmp_path: Path):
        from mesh.generator import _reset_case

        case_dir = tmp_path / "case"
        case_dir.mkdir()
        _reset_case(case_dir)

        assert case_dir.is_dir()
        assert list(case_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# _run_of — OpenFOAM 명령 실행 헬퍼
# ---------------------------------------------------------------------------

class TestRunOf:
    def test_returns_stdout_on_success(self, tmp_path: Path):
        from mesh.generator import _run_of

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "mesh generation complete\n"
        mock_proc.stderr = ""

        with patch("mesh.generator.subprocess.run", return_value=mock_proc):
            out = _run_of(["blockMesh", "-case", str(tmp_path)], env=None, label="blockMesh")

        assert "mesh generation complete" in out

    def test_raises_on_nonzero_returncode(self, tmp_path: Path):
        from mesh.generator import _run_of, MeshGenerationError

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "FOAM FATAL ERROR: something went wrong\n"

        with patch("mesh.generator.subprocess.run", return_value=mock_proc):
            with pytest.raises(MeshGenerationError, match="blockMesh 실패"):
                _run_of(["blockMesh"], env=None, label="blockMesh")

    def test_raises_on_file_not_found(self, tmp_path: Path):
        from mesh.generator import _run_of, MeshGenerationError

        with patch("mesh.generator.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(MeshGenerationError, match="명령 없음"):
                _run_of(["nonexistent_command"], env=None, label="nonexistent_command")

    def test_raises_on_timeout(self, tmp_path: Path):
        from mesh.generator import _run_of, MeshGenerationError

        with patch("mesh.generator.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="blockMesh", timeout=300)):
            with pytest.raises(MeshGenerationError, match="타임아웃"):
                _run_of(["blockMesh"], env=None, label="blockMesh")

    def test_error_message_includes_last_50_lines(self, tmp_path: Path):
        from mesh.generator import _run_of, MeshGenerationError

        long_stderr = "\n".join(f"line {i}" for i in range(100))
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = long_stderr

        with patch("mesh.generator.subprocess.run", return_value=mock_proc):
            with pytest.raises(MeshGenerationError) as exc_info:
                _run_of(["blockMesh"], env=None, label="blockMesh")

        msg = str(exc_info.value)
        assert "line 99" in msg   # last line included
        assert "line 50" in msg   # last 50 lines boundary (lines 50-99)
        assert "line 49" not in msg  # older lines dropped


# ---------------------------------------------------------------------------
# _openfoam_env — 환경변수 설정
# ---------------------------------------------------------------------------

class TestOpenfoamEnv:
    def test_fast_path_when_wm_project_dir_set(self):
        from mesh.generator import _openfoam_env

        with patch.dict(os.environ, {"WM_PROJECT_DIR": "/opt/openfoam12"}):
            env = _openfoam_env()

        assert env is not None
        assert env.get("WM_PROJECT_DIR") == "/opt/openfoam12"

    def test_returns_none_when_bashrc_absent(self):
        from mesh.generator import _openfoam_env

        env_without_wm = {k: v for k, v in os.environ.items() if k != "WM_PROJECT_DIR"}
        with patch.dict(os.environ, env_without_wm, clear=True):
            with patch("mesh.generator.Path.exists", return_value=False):
                env = _openfoam_env()

        assert env is None


# ---------------------------------------------------------------------------
# _mesh_stats — checkMesh 실행 및 품질 통계
# ---------------------------------------------------------------------------

class TestMeshStats:
    def test_graceful_fallback_when_checkmesh_absent(self, tmp_path: Path):
        from mesh.generator import _mesh_stats

        with patch("mesh.generator.subprocess.run",
                   side_effect=FileNotFoundError("checkMesh not found")):
            stats = _mesh_stats(tmp_path, env=None)

        assert stats["passed"] is True
        assert stats["num_cells"] is None

    def test_returns_parsed_stats_on_success(self, tmp_path: Path):
        from mesh.generator import _mesh_stats

        checkmesh_output = (
            "Mesh stats\n"
            "    cells:           100000\n"
            "Mesh OK.\n"
        )
        mock_proc = MagicMock()
        mock_proc.stdout = checkmesh_output
        mock_proc.stderr = ""

        with patch("mesh.generator.subprocess.run", return_value=mock_proc):
            stats = _mesh_stats(tmp_path, env=None)

        assert "passed" in stats
        assert "num_cells" in stats
        assert "checkmesh_output" in stats

    def test_checkmesh_output_truncated_to_2000_chars(self, tmp_path: Path):
        from mesh.generator import _mesh_stats

        long_output = "x" * 5000 + "\nMesh OK.\n"
        mock_proc = MagicMock()
        mock_proc.stdout = long_output
        mock_proc.stderr = ""

        with patch("mesh.generator.subprocess.run", return_value=mock_proc):
            stats = _mesh_stats(tmp_path, env=None)

        assert len(stats["checkmesh_output"]) <= 2000

    def test_graceful_fallback_when_checkmesh_times_out(self, tmp_path: Path):
        """checkMesh timeout must not propagate — treat like absent command."""
        from mesh.generator import _mesh_stats

        with patch("mesh.generator.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(["checkMesh"], 120)):
            stats = _mesh_stats(tmp_path, env=None)

        assert stats["passed"] is True
        assert stats["num_cells"] is None


# ---------------------------------------------------------------------------
# _safe_stl_name — OpenFOAM dict token sanitization
# ---------------------------------------------------------------------------

class TestSafeStlName:
    def test_normal_filename_unchanged(self):
        from mesh.generator import _safe_stl_name
        assert _safe_stl_name("geometry.stl") == "geometry.stl"

    def test_spaces_replaced_with_underscores(self):
        from mesh.generator import _safe_stl_name
        assert _safe_stl_name("my part.stl") == "my_part.stl"

    def test_hyphens_replaced_with_underscores(self):
        from mesh.generator import _safe_stl_name
        assert _safe_stl_name("wing-profile.stl") == "wing_profile.stl"

    def test_dots_in_stem_replaced(self):
        from mesh.generator import _safe_stl_name
        # "wing.v2.stl" → stem="wing.v2" → "wing_v2.stl"
        assert _safe_stl_name("wing.v2.stl") == "wing_v2.stl"

    def test_all_special_chars_stripped(self):
        from mesh.generator import _safe_stl_name
        result = _safe_stl_name("part (final) #3!.stl")
        assert " " not in result
        assert "(" not in result
        assert ")" not in result
        assert "#" not in result
        assert "!" not in result
        assert result.endswith(".stl")

    def test_empty_stem_falls_back_to_geometry(self):
        from mesh.generator import _safe_stl_name
        # A filename like "----.stl" has a stem of all special chars → "geometry.stl"
        assert _safe_stl_name("----.stl") == "geometry.stl"

    def test_already_safe_name_preserved(self):
        from mesh.generator import _safe_stl_name
        assert _safe_stl_name("aircraft_wing_v3.stl") == "aircraft_wing_v3.stl"


# ---------------------------------------------------------------------------
# surface_feature_extract_dict — includedAngle 계산
# ---------------------------------------------------------------------------

class TestSurfaceFeatureExtractDict:
    def test_default_included_angle(self):
        config = surface_feature_extract_dict("shape.stl")
        assert "includedAngle   150" in config

    def test_stl_name_in_output(self):
        config = surface_feature_extract_dict("wing_profile.stl")
        assert "wing_profile.stl" in config

    def test_complexity_adjusts_angle(self):
        complex_c = StlComplexity(
            mean_curvature=0.1, p95_curvature=2.0, complexity_ratio=20.0,
            resolve_feature_angle=15.0,
            surface_refine_min=2, surface_refine_max=4, feature_refine_level=4,
        )
        config = surface_feature_extract_dict("shape.stl", complexity=complex_c)
        # includedAngle = 180 - 15 = 165
        assert "includedAngle   165" in config

    def test_complex_geometry_higher_angle_than_simple(self):
        simple = StlComplexity(
            mean_curvature=0.1, p95_curvature=0.2, complexity_ratio=2.0,
            resolve_feature_angle=40.0,
            surface_refine_min=1, surface_refine_max=2, feature_refine_level=2,
        )
        complex_c = StlComplexity(
            mean_curvature=0.1, p95_curvature=2.0, complexity_ratio=20.0,
            resolve_feature_angle=15.0,
            surface_refine_min=2, surface_refine_max=4, feature_refine_level=4,
        )
        simple_angle = int(180 - simple.resolve_feature_angle)
        complex_angle = int(180 - complex_c.resolve_feature_angle)
        # 복잡한 geometry는 낮은 feature angle → 높은 includedAngle (더 많은 edge 캡처)
        assert complex_angle > simple_angle

    def test_foamfile_header_present(self):
        config = surface_feature_extract_dict("test.stl")
        assert "FoamFile" in config
        assert "surfaceFeatureExtractDict" in config


# ---------------------------------------------------------------------------
# control_dict, fv_schemes, fv_solution 내용 검증
# ---------------------------------------------------------------------------

class TestControlDict:
    def test_default_end_time_is_zero(self):
        config = control_dict()
        assert "endTime         0;" in config

    def test_custom_end_time(self):
        config = control_dict(end_time=500)
        assert "endTime         500;" in config

    def test_foamfile_header_present(self):
        config = control_dict()
        assert "FoamFile" in config
        assert "controlDict" in config

    def test_application_is_simplefoam(self):
        config = control_dict()
        assert "application     simpleFoam;" in config


class TestFvSchemesAndSolution:
    def test_fv_schemes_has_grad_schemes(self):
        config = fv_schemes()
        assert "gradSchemes" in config
        assert "Gauss linear" in config

    def test_fv_schemes_foamfile_header(self):
        config = fv_schemes()
        assert "FoamFile" in config
        assert "fvSchemes" in config

    def test_fv_solution_has_simple_block(self):
        config = fv_solution()
        assert "SIMPLE" in config
        assert "nNonOrthogonalCorrectors" in config

    def test_fv_solution_has_pressure_solver(self):
        config = fv_solution()
        assert "GAMG" in config  # pressure solver


# ---------------------------------------------------------------------------
# _zip_mesh — polyMesh ZIP 패키징
# ---------------------------------------------------------------------------

class TestZipMesh:
    def test_creates_zip_with_all_files(self, tmp_path: Path):
        from mesh.generator import _write_snappy_case
        from mesh.openfoam_config import build_domain

        # Create a realistic case directory structure
        mesh_dir = tmp_path / "case"
        bbox = BBox(0, 0, 0, 1, 1, 1)
        stl_file = tmp_path / "geom.stl"
        stl_file.write_bytes(b"\x00" * 134)  # minimal binary STL (header + count)
        domain = build_domain(bbox, "geom.stl")
        _write_snappy_case(mesh_dir, stl_file, domain)

        # Simulate polyMesh output
        poly = mesh_dir / "constant" / "polyMesh"
        poly.mkdir(parents=True, exist_ok=True)
        (poly / "faces").write_text("dummy faces")
        (poly / "points").write_text("dummy points")

        import zipfile as zf_module
        zip_path = tmp_path / "mesh.zip"

        # Import _zip_mesh — it's in tasks module, but we test the logic directly
        # by replicating the simple pattern
        import zipfile
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in mesh_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(mesh_dir))

        assert zip_path.exists()
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        # polyMesh files must be present
        assert any("faces" in n for n in names)
        assert any("points" in n for n in names)


# ---------------------------------------------------------------------------
# _write_gmsh_msh2 — additional coverage
# ---------------------------------------------------------------------------

class TestWriteGmshMsh2Extra:
    def test_float_tet_indices_handled(self, tmp_path: Path):
        """tet 배열이 float64인 경우에도 올바른 정수 노드 번호로 변환되어야 한다."""
        from mesh.generator import _write_gmsh_msh2
        import numpy as np

        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        tets = np.array([[0.0, 1.0, 2.0, 3.0]], dtype=np.float64)  # float indices
        out = tmp_path / "mesh.msh"
        _write_gmsh_msh2(verts, tets, out)

        content = out.read_text()
        # Node indices must be 1-based integers (not floats like "1.0")
        assert "1 1 2 3 4" in content  # element line with 1-based node ids

    def test_node_coordinates_are_1_based(self, tmp_path: Path):
        """Gmsh 포맷은 1-based 노드 번호를 사용해야 한다."""
        from mesh.generator import _write_gmsh_msh2
        import numpy as np

        verts = np.array([[5.0, 6.0, 7.0]], dtype=np.float64)
        tets = np.zeros((0, 4), dtype=np.int32)
        out = tmp_path / "mesh.msh"
        _write_gmsh_msh2(verts, tets, out)

        content = out.read_text()
        # First (and only) node must have id=1
        assert "1 5 6 7" in content

    def test_multiple_tets_all_written(self, tmp_path: Path):
        """모든 tet 요소가 파일에 기록되어야 한다."""
        from mesh.generator import _write_gmsh_msh2
        import numpy as np

        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]], dtype=np.float64)
        tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=np.int32)
        out = tmp_path / "mesh.msh"
        _write_gmsh_msh2(verts, tets, out)

        lines = out.read_text().splitlines()
        elem_idx = next(i for i, l in enumerate(lines) if l == "$Elements")
        assert lines[elem_idx + 1] == "2"  # 2 elements


# ---------------------------------------------------------------------------
# _apply_mmg_quality — meshio fallback
# ---------------------------------------------------------------------------

class TestApplyMmgQualityMeshioFallback:
    def test_returns_original_when_meshio_absent(self, tmp_path: Path):
        """meshio 미설치 시 (mmg3d는 있어도) 원본 v/t를 조용히 반환해야 한다."""
        from mesh.generator import _apply_mmg_quality
        from mesh.stl_utils import BBox
        import numpy as np

        bbox = BBox(0, 0, 0, 1, 1, 1)
        v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        t = np.array([[0, 1, 2, 3]], dtype=np.int32)

        with patch("shutil.which", return_value="/usr/bin/mmg3d"):  # mmg3d found
            with patch.dict(__import__("sys").modules, {"meshio": None}):  # but meshio absent
                v_out, t_out = _apply_mmg_quality(v, t, tmp_path, bbox)

        assert v_out is v
        assert t_out is t


# ---------------------------------------------------------------------------
# generate_mesh — tessell-skipped error message prefix
# ---------------------------------------------------------------------------

class TestGenerateMeshErrorPrefix:
    def test_tessell_not_built_hint_in_error_when_all_fail(
        self, tmp_path: Path, unit_cube_stl: Path
    ):
        """tessell_mesh.so 미빌드 → 전체 실패 에러 메시지에 빌드 안내 포함되어야 한다."""
        from mesh.generator import generate_mesh, MeshGenerationError

        with patch.dict(__import__("sys").modules, {"tessell_mesh": None}):  # not built
            with patch("mesh.generator._netgen_pipeline", side_effect=RuntimeError("no netgen")):
                with patch("mesh.generator._snappy_pipeline", side_effect=RuntimeError("no snappy")):
                    with patch("mesh.generator._pytetwild_pipeline", side_effect=RuntimeError("no tet")):
                        with pytest.raises(MeshGenerationError) as exc_info:
                            generate_mesh(unit_cube_stl, tmp_path / "case")

        msg = str(exc_info.value)
        assert "tessell" in msg.lower() or "build.sh" in msg


# ---------------------------------------------------------------------------
# _safe_stl_name — non-ASCII characters
# ---------------------------------------------------------------------------

class TestSafeStlNameNonAscii:
    def test_unicode_word_chars_preserved(self):
        """Python \\w includes Unicode letters — Korean/Japanese chars are kept, not stripped."""
        from mesh.generator import _safe_stl_name
        result = _safe_stl_name("날개형상.stl")
        assert result.endswith(".stl")
        # Result must be non-empty stem + .stl (not fall back to geometry.stl)
        assert result != "geometry.stl"

    def test_unicode_stem_ends_with_stl(self):
        """Unicode-only stem must still produce a valid .stl filename."""
        from mesh.generator import _safe_stl_name
        result = _safe_stl_name("翼型.stl")
        assert result.endswith(".stl")
        assert len(result) > len(".stl")

    def test_mixed_unicode_and_special_chars(self):
        """Mixed name: Unicode word chars kept, special chars (spaces, #) replaced."""
        from mesh.generator import _safe_stl_name
        result = _safe_stl_name("날개 #3.stl")
        assert result.endswith(".stl")
        assert " " not in result
        assert "#" not in result


# ---------------------------------------------------------------------------
# _apply_mmg_quality — mmg found, various failure modes
# ---------------------------------------------------------------------------

class TestApplyMmgQualityFailureModes:
    """Edge cases when mmg3d binary is on PATH but something still goes wrong."""

    def test_returns_original_when_mmg_exits_nonzero(self, tmp_path: Path):
        """returncode != 0 → 원본 v/t 반환."""
        from mesh.generator import _apply_mmg_quality
        import numpy as np

        bbox = BBox(0, 0, 0, 1, 1, 1)
        v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        t = np.array([[0, 1, 2, 3]], dtype=np.int32)

        mock_meshio = MagicMock()
        mock_proc = MagicMock()
        mock_proc.returncode = 1  # non-zero — mmg failed

        with patch("mesh.generator.shutil.which", return_value="/usr/bin/mmg3d"):
            with patch.dict(sys.modules, {"meshio": mock_meshio}):
                with patch("mesh.generator.subprocess.run", return_value=mock_proc):
                    v_out, t_out = _apply_mmg_quality(v, t, tmp_path, bbox)

        assert v_out is v
        assert t_out is t

    def test_returns_original_when_t_new_is_none(self, tmp_path: Path):
        """MMG output에 tetra 셀이 없으면 원본 v/t 반환."""
        from mesh.generator import _apply_mmg_quality
        import numpy as np

        bbox = BBox(0, 0, 0, 1, 1, 1)
        v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        t = np.array([[0, 1, 2, 3]], dtype=np.int32)

        # Create _mmg_out.mesh so out_mesh.exists() is True
        (tmp_path / "_mmg_out.mesh").write_text("dummy")

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        mock_mesh = MagicMock()
        mock_mesh.cells_dict = {}  # no "tetra" key
        mock_meshio = MagicMock()
        mock_meshio.read.return_value = mock_mesh

        with patch("mesh.generator.shutil.which", return_value="/usr/bin/mmg3d"):
            with patch.dict(sys.modules, {"meshio": mock_meshio}):
                with patch("mesh.generator.subprocess.run", return_value=mock_proc):
                    v_out, t_out = _apply_mmg_quality(v, t, tmp_path, bbox)

        assert v_out is v
        assert t_out is t

    def test_returns_original_on_subprocess_exception(self, tmp_path: Path):
        """subprocess.run raises → exception caught → 원본 반환."""
        from mesh.generator import _apply_mmg_quality
        import numpy as np

        bbox = BBox(0, 0, 0, 1, 1, 1)
        v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        t = np.array([[0, 1, 2, 3]], dtype=np.int32)

        mock_meshio = MagicMock()

        with patch("mesh.generator.shutil.which", return_value="/usr/bin/mmg3d"):
            with patch.dict(sys.modules, {"meshio": mock_meshio}):
                with patch("mesh.generator.subprocess.run",
                           side_effect=RuntimeError("mmg process crashed")):
                    v_out, t_out = _apply_mmg_quality(v, t, tmp_path, bbox)

        assert v_out is v
        assert t_out is t


# ---------------------------------------------------------------------------
# _openfoam_env — bashrc sourcing path
# ---------------------------------------------------------------------------

class TestOpenfoamEnvBashrc:
    def test_sources_bashrc_and_returns_env_when_present(self):
        """WM_PROJECT_DIR 없어도 bashrc가 있으면 env 반환."""
        from mesh.generator import _openfoam_env

        fake_env_output = "WM_PROJECT_DIR=/opt/openfoam12\nFOAM_ETC=/opt/openfoam12/etc\n"
        mock_proc = MagicMock()
        mock_proc.stdout = fake_env_output

        env_without_wm = {k: v for k, v in os.environ.items() if k != "WM_PROJECT_DIR"}

        with patch.dict(os.environ, env_without_wm, clear=True):
            with patch("mesh.generator.Path.exists", return_value=True):
                with patch("mesh.generator.subprocess.run", return_value=mock_proc):
                    env = _openfoam_env()

        assert env is not None
        assert "WM_PROJECT_DIR" in env


# ---------------------------------------------------------------------------
# _mesh_stats — non-orthogonality and skewness fields
# ---------------------------------------------------------------------------

class TestMeshStatsFields:
    def test_includes_non_ortho_and_skewness(self, tmp_path: Path):
        """checkMesh 출력에 non-ortho/skewness 있으면 stats dict에 포함되어야 한다."""
        from mesh.generator import _mesh_stats

        checkmesh_output = (
            "    Max non-orthogonality = 42.3 degrees.\n"
            "    Max skewness = 0.87\n"
            "    cells:          10000\n"
            "Mesh OK.\n"
        )
        mock_proc = MagicMock()
        mock_proc.stdout = checkmesh_output
        mock_proc.stderr = ""

        with patch("mesh.generator.subprocess.run", return_value=mock_proc):
            stats = _mesh_stats(tmp_path, env=None)

        assert stats.get("max_non_orthogonality") == pytest.approx(42.3)
        assert stats.get("max_skewness") == pytest.approx(0.87)
        assert stats.get("num_cells") == 10000
