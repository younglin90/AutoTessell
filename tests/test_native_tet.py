"""native_tet MVP 엔진 회귀 테스트."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator.native_tet import generate_native_tet

_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"
CUBE_STL = _REPO / "test_cube.stl"


@pytest.fixture
def sphere_mesh():
    if not SPHERE_STL.exists():
        pytest.skip("sphere.stl 없음")
    return read_stl(SPHERE_STL)


@pytest.fixture
def tmp_case_dir():
    tmp = Path(tempfile.mkdtemp(prefix="native_tet_"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_native_tet_sphere_produces_cells(sphere_mesh, tmp_case_dir: Path) -> None:
    res = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir,
        seed_density=8,
    )
    assert res.success, f"실패: {res.message}"
    assert res.n_cells > 0
    assert res.n_points > 0


def test_native_tet_box_fast_path_preserves_cube(tmp_case_dir: Path) -> None:
    """8-corner cube는 Delaunay 회복 대신 구조화 tet split로 안정 생성."""
    if not CUBE_STL.exists():
        pytest.skip("test_cube.stl 없음")
    mesh = read_stl(CUBE_STL)

    res = generate_native_tet(
        mesh.vertices, mesh.faces, tmp_case_dir,
        target_cells=800, seed_density=8,
    )

    assert res.success, res.message
    assert res.n_cells == 1296
    assert res.plane_coverage == 1.0
    assert res.hausdorff_relative == 0.0
    marker = tmp_case_dir / "native_tet_box_fast_path.json"
    assert marker.exists()
    meta = json.loads(marker.read_text(encoding="utf-8"))
    assert meta["grid_shape"] == [6, 6, 6]

    from core.evaluator.native_checker import NativeMeshChecker

    chk = NativeMeshChecker().run(tmp_case_dir)
    assert chk.negative_volumes == 0
    assert chk.max_non_orthogonality < 40.0
    assert chk.max_skewness < 1.0
    assert chk.max_aspect_ratio < 2.0


def test_native_tet_cube_default_bl_lcr_passes_quality(tmp_case_dir: Path) -> None:
    """GUI fine 기본 BL(5 layer)이 sharp cube에서는 1 layer로 안전 축소되어 PASS."""
    if not CUBE_STL.exists():
        pytest.skip("test_cube.stl 없음")
    mesh = read_stl(CUBE_STL)
    res = generate_native_tet(
        mesh.vertices, mesh.faces, tmp_case_dir,
        target_cells=800, seed_density=8,
    )
    assert res.success, res.message

    from core.evaluator.native_checker import NativeMeshChecker
    from core.generator.tier_layers_post import LayersPostGenerator
    from core.schemas import (
        BoundaryLayerConfig,
        DomainConfig,
        MeshStrategy,
        MeshType,
        QualityLevel,
        SurfaceMeshConfig,
    )

    strategy = MeshStrategy(
        quality_level=QualityLevel.FINE,
        mesh_type=MeshType.TET,
        selected_tier="tier_native_tet",
        flow_type="internal",
        domain=DomainConfig(
            min=[0.0, 0.0, 0.0],
            max=[1.0, 1.0, 1.0],
            base_cell_size=0.1,
            location_in_mesh=[0.5, 0.5, 0.5],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file=str(CUBE_STL),
            target_cell_size=0.005,
            min_cell_size=0.002,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=True,
            num_layers=5,
            first_layer_thickness=0.0002732960680837174,
            growth_ratio=1.2,
            max_total_thickness=0.1,
            min_thickness_ratio=0.1,
        ),
        tier_specific_params={"post_layers_engine": "auto"},
    )
    attempt = LayersPostGenerator().run(strategy, CUBE_STL, tmp_case_dir)
    assert attempt.status == "success", attempt.error_message
    assert attempt.native_bl_phase2 is not None
    assert attempt.native_bl_phase2.n_prism_cells == 432
    assert attempt.native_bl_phase2.lcr_min_layers_used == 1
    assert attempt.native_bl_phase2.lcr_max_reduction == 4
    assert attempt.native_bl_phase2.total_thickness >= 0.019

    q = json.loads((tmp_case_dir / "native_bl_quality.json").read_text(encoding="utf-8"))
    assert q["algorithm"] == "cfmesh_tet_shrink_extrude"
    assert q["n_prism_cells"] == 432
    assert q["wall_preserve"]["within_envelope"] is True
    assert q["wall_preserve"]["max_diff_rel"] == 0.0

    from core.utils.polymesh_reader import parse_foam_boundary

    patches = parse_foam_boundary(tmp_case_dir / "constant" / "polyMesh" / "boundary")
    assert "bl_internal_domain" not in {p["name"] for p in patches}
    assert len(patches) == 6

    chk = NativeMeshChecker().run(tmp_case_dir)
    assert chk.negative_volumes == 0
    assert chk.max_non_orthogonality < 60.0
    assert chk.max_skewness < 3.0
    assert chk.max_aspect_ratio < 100.0


def test_draft_auto_cube_tet_bl_uses_wildmesh_cfmesh_shrink(
    tmp_case_dir: Path,
) -> None:
    """draft auto + tet+BL cube는 wildmesh 위에 cfMesh식 shrink BL을 적용."""
    if not CUBE_STL.exists():
        pytest.skip("test_cube.stl 없음")

    from core.pipeline.orchestrator import PipelineOrchestrator

    result = PipelineOrchestrator().run(
        CUBE_STL,
        tmp_case_dir / "pipeline",
        quality_level="draft",
        mesh_type="tet",
        tier_hint="auto",
        auto_retry="off",
        validator_engine="native",
        tier_specific_params={
            "bl_layers": 3,
            "post_layers_engine": "auto",
        },
    )

    assert result.success, result.error
    assert result.strategy is not None
    assert result.strategy.selected_tier == "tier_wildmesh"
    assert result.quality_report is not None
    cm = result.quality_report.evaluation_summary.checkmesh
    assert cm.cells == 8386
    assert cm.negative_volumes == 0
    assert cm.max_non_orthogonality < 80.0
    assert cm.max_skewness < 6.0

    q = json.loads(
        (
            tmp_case_dir
            / "pipeline"
            / "native_bl_quality.json"
        ).read_text(encoding="utf-8")
    )
    assert q["algorithm"] == "cfmesh_tet_shrink_extrude"
    assert q["n_prism_cells"] == 2742

    from core.utils.polymesh_reader import parse_foam_boundary

    patches = parse_foam_boundary(
        tmp_case_dir / "pipeline" / "constant" / "polyMesh" / "boundary"
    )
    assert "bl_internal_domain" not in {p["name"] for p in patches}
    assert len(patches) == 6


def test_native_tet_writes_polymesh(sphere_mesh, tmp_case_dir: Path) -> None:
    res = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir,
        seed_density=8,
    )
    assert res.success
    poly_dir = tmp_case_dir / "constant" / "polyMesh"
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (poly_dir / name).exists(), f"{name} 누락"


def test_native_tet_empty_input_fails(tmp_case_dir: Path) -> None:
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    res = generate_native_tet(V, F, tmp_case_dir)
    assert res.success is False


def test_native_tet_target_edge_length_override(sphere_mesh, tmp_case_dir: Path) -> None:
    """target_edge_length 를 작게 주면 내부 시드 점이 증가 → cells 증가."""
    res_coarse = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir / "coarse",
        target_edge_length=0.5,
    )
    res_fine = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir / "fine",
        target_edge_length=0.25,
    )
    assert res_coarse.success and res_fine.success
    assert res_fine.n_cells >= res_coarse.n_cells


def test_native_tet_sliver_quality_threshold_loose_keeps_more(
    sphere_mesh, tmp_case_dir: Path,
) -> None:
    """beta62 — sliver_quality_threshold 를 0 (필터 off) 으로 하면 엄격 케이스
    보다 cell 이 많아야 한다. 0.3 은 매우 엄격해서 많이 탈락, 0 은 전부 유지.
    """
    res_strict = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir / "strict",
        seed_density=8, sliver_quality_threshold=0.3,
    )
    res_loose = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir / "loose",
        seed_density=8, sliver_quality_threshold=0.0,
    )
    # 둘 다 성공 (빈 결과가 아니어야)
    assert res_loose.success
    # loose 가 strict 보다 같거나 많은 cell 보유 (sphere 는 일반적으로 많이 유지)
    assert res_loose.n_cells >= res_strict.n_cells


def test_native_tet_max_input_vertices_crash_guard(tmp_case_dir: Path) -> None:
    """beta77 — 입력 vertex 수가 max_input_vertices 초과 시 crash 없이 failure."""
    import numpy as _np
    # 간단한 cube mesh (8 vert, 12 tri) 으로 cap=5 설정 → 초과
    V = _np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],
                   [0,0,1],[1,0,1],[1,1,1],[0,1,1]], dtype=_np.float64)
    F = _np.array([[0,1,2],[0,2,3],[4,6,5],[4,7,6],
                   [0,4,5],[0,5,1],[3,2,6],[3,6,7],
                   [0,3,7],[0,7,4],[1,5,6],[1,6,2]], dtype=_np.int64)
    res = generate_native_tet(
        V, F, tmp_case_dir / "cap_test",
        max_input_vertices=5,
    )
    assert res.success is False
    assert "max_input_vertices" in res.message or "vertices" in res.message.lower()


def test_native_tet_harness_params_table_has_q_thresh() -> None:
    """beta62 — HARNESS_PARAMS 3 quality 에 sliver_quality_threshold 키 존재.

    의미론: 낮은 threshold = 관대 (cell 보존, 수렴 쉬움),
            높은 threshold = 엄격 (sliver 제거, 품질↑).
    따라서 draft < standard < fine (엄격도 증가).
    """
    from core.generator._tier_native_common import HARNESS_PARAMS
    tet_table = HARNESS_PARAMS["tier_native_tet"]
    for q in ("draft", "standard", "fine"):
        assert "sliver_quality_threshold" in tet_table[q], q
    assert (
        tet_table["draft"]["sliver_quality_threshold"]
        < tet_table["standard"]["sliver_quality_threshold"]
        < tet_table["fine"]["sliver_quality_threshold"]
    )


def test_tier_native_tet_drops_gui_cross_engine_kwargs(monkeypatch, tmp_case_dir: Path) -> None:
    """GUI 공용 파라미터가 tet 전용 mesher에 그대로 흘러 실패하지 않아야 한다."""
    from core.generator import tier_native_tet as tnt

    captured: dict[str, object] = {}

    class _R:
        success = True
        n_cells = 1
        n_points = 4
        n_faces = 4
        message = "ok"

    def _fake_harness(vertices, faces, case_dir, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return _R()

    monkeypatch.setattr(tnt, "run_native_tet_harness", _fake_harness)
    V = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]], dtype=np.int64)

    res = tnt._runner(
        V,
        F,
        tmp_case_dir,
        snap_boundary=True,
        snap_iterations=3,
        target_cells=100,
        enable_boundary_clip=True,
    )
    assert res.success
    assert "snap_boundary" not in captured
    assert "snap_iterations" not in captured
    assert captured["target_cells"] == 100
    assert captured["enable_boundary_clip"] is True
