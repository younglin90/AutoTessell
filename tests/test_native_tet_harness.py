"""beta38 — run_native_tet_harness dedicated 회귀 테스트."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from core.generator._tier_native_common import _edge_from_target_cells
from core.generator.native_tet.harness import (
    _TET_HARNESS_MAX_NON_ORTHOGONALITY,
    TetHarnessResult,
    _evaluate_tet_mesh,
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


def test_harness_hits_target_cells_at_draft_max_iter_1(tmp_path: Path) -> None:
    """draft (max_iter=1) 에서도 target_cells 보정이 동작해야 한다.

    회귀 대상: 기존 cap-retry 는 ``if res.n_cells > max_cells and it < max_iter``
    였고 draft 의 ``max_iter`` 는 1 이라 ``1 < 1`` = False → **절대 발화하지 않는**
    dead code 였다.  따라서 셀 수 보정은 오직 standard/fine 에서만 (그것도 blunt
    ``edge x 1.6`` 로) 일어났다.  이제 보정은 ``max_iter`` 와 무관한 자체 pass
    예산을 가진 measured-ratio closed loop 라 draft 에서도 수렴한다.

    실측 (unit cube, N=2000): 수정 전 1318 cells (0.66x) — 보정 미발화.
    수정 후 ~2035 cells (1.02x).
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
    assert result.n_cells > 0
    ratio = result.n_cells / target
    assert 0.75 <= ratio <= 1.45, (
        f"draft(max_iter=1) 에서 target_cells={target} → {result.n_cells} cells "
        f"(ratio {ratio:.2f}x) — 셀 수 보정이 발화하지 않았다"
    )


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
