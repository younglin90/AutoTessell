"""Read-only shape-gate diagnostics for native_tet phase-0 cards."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.quality import tet_gsm_score
from core.generator.native_tet.validate import classify_flat_sliver_wdel2


def _point(a: float, b: float, c: float) -> np.ndarray:
    return np.asarray([a, b, c], dtype=np.float64)


def test_tet_gsm_score_prefers_regular_over_flat() -> None:
    """정규 tetra 에 비해 평탄 sliver 는 tet_gsm_score가 낮아야 한다."""
    regular = np.array(
        [
            _point(0.0, 0.0, 0.0),
            _point(1.0, 0.0, 0.0),
            _point(0.5, np.sqrt(3) / 2, 0.0),
            _point(0.5, np.sqrt(3) / 6, np.sqrt(2.0 / 3.0)),
        ],
        dtype=np.float64,
    )
    flat = np.array(
        [
            _point(0.0, 0.0, 0.0),
            _point(1.0, 0.0, 0.0),
            _point(0.2, 1.0, 0.0),
            _point(0.3, 0.3, 0.01),
        ],
        dtype=np.float64,
    )

    q_regular = float(tet_gsm_score(regular, np.array([[0, 1, 2, 3]], dtype=np.int64))[0])
    q_flat = float(tet_gsm_score(flat, np.array([[0, 1, 2, 3]], dtype=np.int64))[0])

    assert q_regular > 0.5
    assert q_flat < 0.1
    assert q_regular > q_flat


def test_classify_flat_sliver_wdel2_reports_read_only_pumpable_locked_split() -> None:
    """TET-WDEL-2 분류기는 판독만 수행하고 read-only 이어야 한다."""
    pts = np.array(
        [
            [0.0, 0.0, 0.0],  # 0
            [1.0, 0.0, 0.0],  # 1
            [0.2, 1.0, 0.0],  # 2
            [0.3, 0.3, 0.01],  # 3 -> q≈0.0067 (PUMPABLE 기대)
            [2.0, 0.0, 0.0],  # 4
            [3.0, 0.0, 0.0],  # 5
            [2.00001, 1.0, 0.0],  # 6
            [2.3, 0.3, 1e-5],  # 7 -> q≈5e-6 (LOCKED 기대)
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [
            [0, 1, 2, 3],
            [4, 5, 6, 7],
        ],
        dtype=np.int64,
    )
    tets_before = tets.copy()
    rep = classify_flat_sliver_wdel2(
        pts,
        tets,
        n_surface_vertices=8,
        q_flat=0.01,
        pumpable_ratio_floor=0.05,
    )

    assert np.array_equal(tets, tets_before)
    assert rep["n_candidates"] == 2
    assert rep["n_pumpable"] + rep["n_locked"] == rep["n_candidates"]
    assert rep["n_pumpable"] >= 1
    assert rep["n_locked"] >= 1
    assert rep["status"] == "ok"
    assert isinstance(rep["pumpable_indices"], list)
    assert isinstance(rep["locked_indices"], list)
