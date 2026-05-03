"""BETA2827 (B-2v2) — ftetwild_main_loop smoke test.

dedicated fTetWild §3.4 main loop module 의 기본 동작 검증. parity ratio 는
별도 카드 (B-3+) 에서 향상.
"""
from __future__ import annotations

import numpy as np
import pytest


def _cube_VF() -> tuple[np.ndarray, np.ndarray]:
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    return V, F


def test_ftetwild_main_loop_smoke():
    """cube smoke: success + n_iters_used > 0 + 셀 ≥ 1."""
    pytest.importorskip("scipy")
    from core.generator.native_tet.ftetwild_main_loop import ftetwild_main_loop
    V, F = _cube_VF()
    r = ftetwild_main_loop(V, F, edge_length_r=0.1, max_its=5, stop_quality=10.0)
    assert r.success
    assert r.n_iters_used >= 1
    # tets 가 0 이 아니면 OK (winding filter 후 interior 만 남음).
    assert r.tets.shape[0] >= 1
    # split 또는 collapse 또는 swap 중 적어도 하나는 발동.
    assert (r.n_split_total + r.n_collapse_total + r.n_swap_total) > 0


def test_ftetwild_main_loop_target_edge_override():
    """target_edge_length 명시 시 edge_length_r 무시."""
    pytest.importorskip("scipy")
    from core.generator.native_tet.ftetwild_main_loop import ftetwild_main_loop
    V, F = _cube_VF()
    r1 = ftetwild_main_loop(V, F, target_edge_length=0.5, max_its=2)
    r2 = ftetwild_main_loop(V, F, edge_length_r=0.05, max_its=2)
    # 두 호출 모두 성공.
    assert r1.success and r2.success
    # 적어도 collapse 또는 mean_q 가 다르게 나옴 (target 값에 민감).
    diff = (
        r1.n_collapse_total != r2.n_collapse_total
        or r1.pts.shape[0] != r2.pts.shape[0]
        or abs(r1.final_mean_q - r2.final_mean_q) > 1e-6
    )
    assert diff


def test_ftetwild_result_dataclass_fields():
    """FTetWildResult 가 명시된 필드 모두 가짐."""
    from core.generator.native_tet.ftetwild_main_loop import FTetWildResult
    r = FTetWildResult(
        pts=np.zeros((0, 3)), tets=np.zeros((0, 4), dtype=np.int64),
        success=False, n_iters_used=0,
        final_min_q=0.0, final_mean_q=0.0,
        n_split_total=0, n_collapse_total=0, n_swap_total=0,
    )
    for fld in ("pts", "tets", "success", "n_iters_used",
                "final_min_q", "final_mean_q",
                "n_split_total", "n_collapse_total", "n_swap_total"):
        assert hasattr(r, fld), fld
