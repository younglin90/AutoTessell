"""beta55 — _parse_target_edge + run_native_tier edge case 회귀."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.generator._tier_native_common import (
    _parse_target_edge,
    run_native_tier,
)
from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    MeshStrategy,
    QualityLevel,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
)


def _mk_strategy(target_edge: float) -> MeshStrategy:
    return MeshStrategy(
        quality_level=QualityLevel.DRAFT,
        surface_quality_level=SurfaceQualityLevel.L1_REPAIR,
        selected_tier="tier_native_tet",
        flow_type="internal",
        domain=DomainConfig(
            type="box", min=[-1.0] * 3, max=[1.0] * 3,
            base_cell_size=0.1, location_in_mesh=[0.0] * 3,
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="dummy.stl", target_cell_size=target_edge,
            min_cell_size=max(target_edge * 0.1, 1e-6),
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False, num_layers=0, first_layer_thickness=0.0,
            growth_ratio=1.0, max_total_thickness=0.0, min_thickness_ratio=0.0,
        ),
    )


# ---------------------------------------------------------------------------
# _parse_target_edge
# ---------------------------------------------------------------------------


def test_parse_target_edge_positive_value() -> None:
    """양수 target_cell_size → float 반환."""
    s = _mk_strategy(target_edge=0.5)
    assert _parse_target_edge(s) == 0.5


def test_parse_target_edge_zero_returns_none() -> None:
    """0 → None."""
    s = SimpleNamespace(surface_mesh=SimpleNamespace(target_cell_size=0))
    assert _parse_target_edge(s) is None


def test_parse_target_edge_negative_returns_none() -> None:
    """음수 → None."""
    s = SimpleNamespace(surface_mesh=SimpleNamespace(target_cell_size=-0.5))
    assert _parse_target_edge(s) is None


def test_parse_target_edge_non_numeric_returns_none() -> None:
    """숫자로 변환 불가 → None."""
    s = SimpleNamespace(surface_mesh=SimpleNamespace(target_cell_size="abc"))
    assert _parse_target_edge(s) is None


def test_parse_target_edge_missing_attr_returns_none() -> None:
    """surface_mesh / target_cell_size 속성 없음 → None (AttributeError 삼킴)."""
    s = SimpleNamespace()
    assert _parse_target_edge(s) is None


# ---------------------------------------------------------------------------
# run_native_tier edge cases
# ---------------------------------------------------------------------------


def test_run_native_tier_stl_missing_returns_failed(tmp_path: Path) -> None:
    """존재하지 않는 STL → TierAttempt.status='failed' + error_message."""
    def _never_called(vertices, faces, case_dir, **kw):
        raise AssertionError("runner should not be called")

    attempt = run_native_tier(
        _never_called, "tier_native_tet",
        _mk_strategy(0.1),
        preprocessed_path=tmp_path / "not_exist.stl",
        case_dir=tmp_path / "case",
    )
    assert attempt.status == "failed"
    assert "STL" in (attempt.error_message or "") or "읽기" in (attempt.error_message or "")


def test_run_native_tier_runner_exception_returns_failed(tmp_path: Path) -> None:
    """runner_fn 이 예외 → TierAttempt.status='failed'."""
    # 유효 STL 파일 만들기
    stl = tmp_path / "t.stl"
    stl.write_text(
        "solid t\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n"
        "endloop\nendfacet\nendsolid\n"
    )

    def _runner_fail(vertices, faces, case_dir, **kw):
        raise RuntimeError("simulated runner fail")

    attempt = run_native_tier(
        _runner_fail, "tier_native_tet",
        _mk_strategy(0.1), stl, tmp_path / "case",
    )
    assert attempt.status == "failed"
    assert "tier_native_tet" in (attempt.error_message or "")


def test_run_native_tier_runner_zero_cells_marks_failed(tmp_path: Path) -> None:
    """runner 가 success=False + n_cells=0 → failed."""
    stl = tmp_path / "t.stl"
    stl.write_text(
        "solid t\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n"
        "endloop\nendfacet\nendsolid\n"
    )

    def _empty_result(vertices, faces, case_dir, **kw):
        class _R:
            success = False
            n_cells = 0
            n_points = 0
            n_faces = 0
            message = "no cells produced"
        return _R()

    attempt = run_native_tier(
        _empty_result, "tier_native_tet",
        _mk_strategy(0.1), stl, tmp_path / "case",
    )
    assert attempt.status == "failed"


def test_run_native_tier_partial_success_counts_as_success(tmp_path: Path) -> None:
    """runner 가 success=False 여도 n_cells>0 이면 'success' 로 기록 (best-effort)."""
    stl = tmp_path / "t.stl"
    stl.write_text(
        "solid t\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n"
        "endloop\nendfacet\nendsolid\n"
    )

    def _partial_success(vertices, faces, case_dir, **kw):
        class _R:
            success = False
            n_cells = 100
            n_points = 50
            n_faces = 200
            message = "best-effort"
        return _R()

    attempt = run_native_tier(
        _partial_success, "tier_native_tet",
        _mk_strategy(0.1), stl, tmp_path / "case",
    )
    assert attempt.status == "success"
    assert attempt.mesh_stats is not None
    assert attempt.mesh_stats.num_cells == 100
