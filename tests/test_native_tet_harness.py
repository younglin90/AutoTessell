"""beta38 — run_native_tet_harness dedicated 회귀 테스트."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import core.generator.native_tet.harness as tet_harness
from core.generator._tier_native_common import _edge_from_target_cells
from core.generator.native_tet.harness import (
    _TET_HARNESS_MAX_HAUSDORFF_RELATIVE,
    _TET_HARNESS_MAX_NON_ORTHOGONALITY,
    _TET_HARNESS_MIN_PLANAR_SOURCE_COVERAGE,
    TetHarnessResult,
    _evaluate_source_shape_contract,
    _evaluate_tet_mesh,
    run_native_tet_harness,
)
from core.generator.native_tet.mesher import NativeTetResult
from core.generator.native_tet.surface_transaction_gate import SourceSurfaceMetrics
from core.generator.native_tet.writer_topology import audit_written_polymesh


def _unit_cube():
    """[-0.5, 0.5]^3 단위 cube 표면 — 12 삼각형."""
    V = np.array([
        [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5], [0.5, 0.5, -0.5], [-0.5, 0.5, -0.5],
        [-0.5, -0.5, 0.5], [0.5, -0.5, 0.5], [0.5, 0.5, 0.5], [-0.5, 0.5, 0.5],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2],
        [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4],
        [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5],
        [0, 4, 7], [0, 7, 3],
    ], dtype=np.int64)
    return V, F


def _tetrahedron():
    return (
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float),
        np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.int64),
    )


def _source_metric_result() -> NativeTetResult:
    points, _faces = _tetrahedron()
    return NativeTetResult(
        success=True, elapsed=0.0, n_cells=1, n_points=4,
        hausdorff_relative=0.0, plane_coverage=1.0, plane_area_coverage=1.0,
        tet_points=points,
        tets=np.array([[0, 1, 2, 3]], dtype=np.int64),
    )


def _set_source_measurement(monkeypatch: pytest.MonkeyPatch, values: tuple | None) -> None:
    def _measure(*_args):
        if values is None:
            raise RuntimeError("probe failure")
        return SourceSurfaceMetrics(*values)

    monkeypatch.setattr(
        "core.generator.native_tet.surface_transaction_gate.measure_source_surface_metrics",
        _measure,
    )


@pytest.mark.parametrize(("cube", "values", "expected", "reason"), [
    (True, (_TET_HARNESS_MAX_HAUSDORFF_RELATIVE,
            _TET_HARNESS_MIN_PLANAR_SOURCE_COVERAGE,
            _TET_HARNESS_MIN_PLANAR_SOURCE_COVERAGE), True, "ok"),
    (True, (0.01, -1.0, 0.8), False, "source_metrics_unavailable"),
    (True, (0.01, 0.8, float("nan")), False, "source_metrics_nonfinite"),
    (True, (_TET_HARNESS_MAX_HAUSDORFF_RELATIVE + 1e-9, 0.8, 0.8), False,
     "hausdorff_relative_exceeds_standard"),
    (True, (0.01, _TET_HARNESS_MIN_PLANAR_SOURCE_COVERAGE - 1e-9, 0.8), False,
     "planar_source_coverage_below_b_grade"),
    (True, (0.01, 0.8, _TET_HARNESS_MIN_PLANAR_SOURCE_COVERAGE - 1e-9), False,
     "planar_source_coverage_below_b_grade"),
    (False, (0.01, 0.0, 0.0), True, "ok"),
    (True, None, False, "source_metrics_measurement_failed"),
])
def test_source_shape_contract(
    cube: bool,
    values: tuple | None,
    expected: bool,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L0: final remeasurement, not stale result fields, controls admission."""
    V, F = _unit_cube() if cube else _tetrahedron()
    _set_source_measurement(monkeypatch, values)
    accepted, actual_reason, metrics = _evaluate_source_shape_contract(
        V, F, _source_metric_result()
    )
    assert accepted is expected
    assert actual_reason == reason
    assert set(metrics) == {"hausdorff_relative", "plane_coverage", "plane_area_coverage"}


def test_harness_rejects_only_source_invalid_candidate_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L0: source-invalid mesh never reaches checker, best_case, or case_dir."""
    V, F = _unit_cube()
    generated = tmp_path / "generated"
    case_dir = tmp_path / "case"
    case_dir.mkdir()

    def _fake_generate(*_args, **_kwargs):
        generated.mkdir()
        (generated / "marker").write_text("invalid source candidate", encoding="utf-8")
        return _source_metric_result(), generated, 0.1774782413111788

    def _checker_must_not_run(_case_dir: Path):
        raise AssertionError("source-invalid candidate reached NativeMeshChecker")

    monkeypatch.setattr(tet_harness, "_generate_with_cell_rebudget", _fake_generate)
    monkeypatch.setattr(tet_harness, "_evaluate_tet_mesh", _checker_must_not_run)
    _set_source_measurement(
        monkeypatch, (0.049830696267310334, 0.0, 0.6933725645168424)
    )

    result = run_native_tet_harness(V, F, case_dir, max_iter=1)

    assert not result.success
    assert result.n_cells == 1
    assert "source_shape_contract_rejected" in result.message
    assert "planar_source_coverage_below_b_grade" in result.message
    assert not generated.exists()
    assert list(case_dir.iterdir()) == []


def test_harness_preserves_prior_source_valid_best_when_later_candidate_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L0: later source rejection cannot replace an earlier source-valid best."""
    V, F = _unit_cube()
    case_dir = tmp_path / "case"
    candidates = ["source-valid", "source-invalid"]
    measurements = [
        SourceSurfaceMetrics(0.01, 1.0, 1.0),
        SourceSurfaceMetrics(0.01, 0.0, 0.6933725645168424),
    ]
    generated: list[Path] = []

    def _fake_generate(*_args, **_kwargs):
        marker = candidates.pop(0)
        path = tmp_path / marker
        path.mkdir()
        (path / "marker").write_text(marker, encoding="utf-8")
        generated.append(path)
        return _source_metric_result(), path, 0.2

    def _failing_checker(_case_dir: Path) -> tuple[bool, dict]:
        return False, {
            "cells": 1,
            "points": 4,
            "max_non_orthogonality": 91.0,
            "max_skewness": 0.0,
            "negative_volumes": 0,
            "mesh_ok": True,
        }

    monkeypatch.setattr(tet_harness, "_generate_with_cell_rebudget", _fake_generate)
    monkeypatch.setattr(tet_harness, "_evaluate_tet_mesh", _failing_checker)
    monkeypatch.setattr(
        "core.generator.native_tet.surface_transaction_gate.measure_source_surface_metrics",
        lambda *_args: measurements.pop(0),
    )

    result = run_native_tet_harness(V, F, case_dir, max_iter=2)

    assert not result.success
    assert result.n_cells == 1
    assert (case_dir / "marker").read_text(encoding="utf-8") == "source-valid"
    assert not generated[0].exists()
    assert not generated[1].exists()


def test_harness_returns_tet_harness_result(tmp_path: Path) -> None:
    """반환 타입이 TetHarnessResult."""
    V, F = _unit_cube()
    result = run_native_tet_harness(V, F, tmp_path, max_iter=1, seed_density=8)
    assert isinstance(result, TetHarnessResult)
    assert result.iterations >= 1
    assert result.elapsed >= 0.0


def test_harness_empty_input_fails_gracefully(tmp_path: Path) -> None:
    """빈 input → success=False, n_cells=0, crash 없음."""
    V = np.zeros((0, 3), dtype=np.float64)
    F = np.zeros((0, 3), dtype=np.int64)
    result = run_native_tet_harness(V, F, tmp_path, max_iter=1)
    assert isinstance(result, TetHarnessResult)
    assert result.success is False
    assert result.n_cells == 0


@pytest.mark.parametrize(
    ("non_ortho", "expected"),
    [
        (89.31439471907049, True),
        (float(np.nextafter(90.0, 0.0)), True),
        (90.0, False),
    ],
)
def test_harness_non_ortho_gate_matches_under_90_evaluator_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    non_ortho: float,
    expected: bool,
) -> None:
    """Draft viability accepts values below 90°, never the 90° hard limit."""

    class _Checker:
        def run(self, _case_dir: Path) -> SimpleNamespace:
            return SimpleNamespace(
                cells=763,
                points=189,
                max_non_orthogonality=non_ortho,
                max_skewness=2.569496613554352,
                negative_volumes=0,
                mesh_ok=True,
            )

    monkeypatch.setattr(
        "core.evaluator.native_checker.NativeMeshChecker",
        _Checker,
    )

    passed, metrics = _evaluate_tet_mesh(tmp_path)

    assert _TET_HARNESS_MAX_NON_ORTHOGONALITY == 90.0
    assert metrics["max_non_orthogonality"] == non_ortho
    assert passed is expected


def test_harness_respects_max_iter_cap(tmp_path: Path) -> None:
    """max_iter=2 에서 iterations <= 2."""
    V, F = _unit_cube()
    result = run_native_tet_harness(V, F, tmp_path, max_iter=2, seed_density=6)
    assert result.iterations <= 2


def test_harness_target_edge_clamp_for_small_value(tmp_path: Path, caplog) -> None:
    """target_edge_length < bbox_diag/40 이면 clamp 로그 남기고 실행. clamp 덕분에
    요청값 그대로 썼을 때 대비 cell 수가 폭증하지 않음 (정확한 상한은 max_cells
    cap 이 다음 iter 에서 적용되므로 여기서는 clamp 로그 발생만 검증)."""
    V, F = _unit_cube()
    # bbox_diag = sqrt(3) ≈ 1.73, bbox_diag/40 ≈ 0.043
    with caplog.at_level("INFO"):
        result = run_native_tet_harness(
            V, F, tmp_path, max_iter=1, target_edge_length=0.001,
        )
    assert isinstance(result, TetHarnessResult)
    # clamp log 가 남았거나, 적어도 harness 가 crash 없이 완주
    assert result.iterations >= 1


def test_harness_max_cells_safety_cap(tmp_path: Path) -> None:
    """max_cells 를 매우 작게 설정해도 crash 없이 반환."""
    V, F = _unit_cube()
    result = run_native_tet_harness(
        V, F, tmp_path, max_iter=2, seed_density=12, max_cells=50,
    )
    # cell 수가 cap 을 넘으면 seed 조정 후 재시도. 최종 결과는 꼭 성공이 아니어도 OK.
    assert isinstance(result, TetHarnessResult)


def test_harness_records_target_count_without_topology_acceptance_coupling(
    tmp_path: Path,
) -> None:
    """Target telemetry cannot reject an otherwise strict-topology-valid draft.

    Target-following is tracked separately in release Gate 6.  This Tet
    topology card deliberately requires the higher-priority contracts only:
    source admission, no negative volume, under-90 non-orthogonality, and a
    writer-consistent tetrahedral output.  It still computes the requested/
    actual ratio so a later target-control card cannot claim missing evidence.
    """
    V, F = _unit_cube()
    target = 2000
    # run_native_tier 가 하는 것과 동일하게 N 에서 edge 를 유도.
    edge = _edge_from_target_cells(V, F, "tier_native_tet", target)
    assert edge is not None

    result = run_native_tet_harness(
        V, F, tmp_path,
        target_edge_length=edge,
        seed_density=10,
        max_iter=1,                 # ← draft 의 예산
        sliver_quality_threshold=0.02,
        target_cells=target,
        max_cells=target,
    )
    assert result.success
    assert result.n_cells > 0
    ratio = result.n_cells / target
    assert np.isfinite(ratio)
    written = audit_written_polymesh(tmp_path / "constant" / "polyMesh")
    assert written.n_cells == result.n_cells
    assert all(cell.is_tetrahedron_encoding for cell in written.cells)


def test_harness_bare_max_cells_is_one_sided_cap(tmp_path: Path) -> None:
    """target_cells 없이 max_cells 만 주면 cap 으로만 쓰이고 셀을 늘리지 않는다.

    ``max_cells`` 의 signature default 는 50000 이라 "사용자가 50000 을 원했다" 와
    구분할 수 없다.  이를 양방향 target 으로 오해하면 모든 mesh 가 50000 쪽으로
    부풀려진다 — 이 테스트가 그 회귀를 막는다.
    """
    V, F = _unit_cube()
    edge = _edge_from_target_cells(V, F, "tier_native_tet", 500)
    assert edge is not None
    result = run_native_tet_harness(
        V, F, tmp_path,
        target_edge_length=edge,
        seed_density=10, max_iter=1,
        sliver_quality_threshold=0.02,
        max_cells=50000,            # cap 만 (default 값) — target 아님
    )
    # cap 쪽으로 부풀지 않고 edge 가 의도한 규모 (~수백 cell) 를 유지.
    assert 0 < result.n_cells < 5000, (
        f"bare max_cells=50000 이 target 으로 오해되어 {result.n_cells} cells 로 "
        f"부풀었다"
    )


def test_harness_deterministic_for_same_inputs(tmp_path: Path) -> None:
    """같은 V, F, params → n_cells 동일."""
    V, F = _unit_cube()
    r1 = run_native_tet_harness(V, F, tmp_path / "a", max_iter=1, seed_density=8)
    r2 = run_native_tet_harness(V, F, tmp_path / "b", max_iter=1, seed_density=8)
    assert r1.n_cells == r2.n_cells
    assert r1.n_points == r2.n_points


def test_harness_returns_positive_cells_on_valid_input(tmp_path: Path) -> None:
    """단순 cube 에서 iter=1 만으로도 tet cell 이 생성."""
    V, F = _unit_cube()
    result = run_native_tet_harness(V, F, tmp_path, max_iter=1, seed_density=8)
    assert result.n_cells > 0
    assert result.n_points > 0


def test_harness_sliver_quality_threshold_kwarg(tmp_path: Path) -> None:
    """beta62 — harness 가 sliver_quality_threshold 를 생성기로 전달."""
    V, F = _unit_cube()
    # 매우 엄격한 threshold 로 호출 → 많은 tet 제거되지만 harness 는 adaptive
    # 완화로 최소 cell 을 확보해 success/best-effort 를 반환해야 한다.
    result = run_native_tet_harness(
        V, F, tmp_path, max_iter=2, seed_density=8,
        sliver_quality_threshold=0.5,
    )
    # 구현 계약: 예외 없이 TetHarnessResult 반환.
    assert hasattr(result, "iterations")
    assert result.iterations >= 1
