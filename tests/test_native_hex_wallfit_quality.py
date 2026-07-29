"""Unit tests for the opt-in wall-fit candidate quality census."""

from __future__ import annotations

import numpy as np

from core.generator.native_hex.wallfit_quality import (
    CandidateQualityAudit,
    enabled,
    pareto_frontier,
    snapshot,
)

_POINTS = np.asarray(
    [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 1.0],
        [0.0, 1.0, 1.0],
    ],
    dtype=np.float64,
)
_CELL_FACES = [
    [
        [0, 1, 2, 3],
        [4, 5, 6, 7],
        [0, 4, 5, 1],
        [1, 5, 6, 2],
        [2, 6, 7, 3],
        [3, 7, 4, 0],
    ]
]


def test_candidate_snapshot_is_read_only_and_has_boundary_contract() -> None:
    before_points = _POINTS.copy()
    before = snapshot(_POINTS, _CELL_FACES, [0])
    assert np.array_equal(_POINTS, before_points)
    assert before.cell_indices == (0,)
    assert before.boundary_keys
    assert before.boundary_area == 6.0
    assert before.min_abs_normal_distance == 0.5
    assert before.n_near_zero_normal_distance == 0
    assert before.n_negative_signed_volume >= 0


def test_candidate_audit_reports_quality_and_area_delta() -> None:
    before = snapshot(_POINTS, _CELL_FACES, [0])
    moved = _POINTS.copy()
    moved[0] = [0.1, 0.1, 0.1]
    after = snapshot(moved, _CELL_FACES, [0])
    audit = CandidateQualityAudit()
    audit.record(
        vertex=0,
        outcome="full",
        before=before,
        trial=after,
        after=after,
        distance_before=1.0,
        distance_after=0.0,
    )
    report = audit.to_dict()
    assert report["n_candidates"] == 1
    assert report["n_full"] == 1
    assert report["n_applied_regression"] == 1
    assert report["n_boundary_key_change"] == 0
    assert report["n_boundary_area_change"] == 1
    assert report["n_applied_distance_improved"] == 1
    assert report["n_distance_improved_quality_regression"] == 1
    assert report["max_abs_boundary_area_delta"] > 0.0
    assert report["pareto_frontier_size"] == 1
    assert report["samples"]


def test_candidate_quality_flag_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG", raising=False)
    assert enabled() is False
    monkeypatch.setenv("AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG", "1")
    assert enabled() is True


def test_pareto_frontier_keeps_only_non_dominated_candidates() -> None:
    records = [
        {
            "vertex": 3,
            "distance_reduction": 2.0,
            "applied_skew_delta": 0.2,
            "applied_warpage_delta": 0.1,
            "boundary_area_delta": 0.0,
            "negative_signed_volume_delta": 0.0,
        },
        {
            "vertex": 4,
            "distance_reduction": 1.0,
            "applied_skew_delta": 0.4,
            "applied_warpage_delta": 0.2,
            "boundary_area_delta": 0.1,
            "negative_signed_volume_delta": 0.0,
        },
        {
            "vertex": 5,
            "distance_reduction": 1.5,
            "applied_skew_delta": 0.1,
            "applied_warpage_delta": 0.1,
            "boundary_area_delta": 0.0,
            "negative_signed_volume_delta": 0.0,
        },
    ]
    frontier = pareto_frontier(records)
    assert [record["vertex"] for record in frontier] == [3, 5]
