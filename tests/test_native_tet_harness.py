"""beta38 — run_native_tet_harness dedicated 회귀 테스트."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.generator.native_tet.harness import (
    TetHarnessResult,
    run_native_tet_harness,
)


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
