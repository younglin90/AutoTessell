"""L1 source-triangle to no-H Table-11 matching tests; no mesh mutation."""

from __future__ import annotations

import pytest

from core.generator.native_tet.chen_staged_state_l0 import certify_atomic_staged_replacement
from core.generator.native_tet.chen_thr_edg_source_match_l1 import (
    certify_thr_edg_source_match_l1,
)

_TET = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
_THR_TRIANGLE = ((-1, -1, 2 / 5), (2, -1, 2 / 5), (-1, 2, 2 / 5))


@pytest.mark.parametrize("subcase", ("S2/Z1", "S1/Z2"))  # type: ignore[untyped-decorator]
def test_finite_thr_edg_source_derives_documented_ad_bd_cd_intersections(subcase: str) -> None:
    result = certify_thr_edg_source_match_l1(_TET, _THR_TRIANGLE, subcase=subcase)  # type: ignore[arg-type]

    assert result.accepted, result.reason
    assert result.subcase == subcase
    assert result.candidate is not None
    assert result.candidate.intersection_points_on_documented_edges
    assert result.candidate.external_boundary_preserved
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_non_thr_or_wrong_cut_edge_pattern_rejects_before_candidate_exposure() -> None:
    result = certify_thr_edg_source_match_l1(
        _TET,
        ((-1, -1, 2 / 5), (1 / 3, -1, 2 / 5), (-1, 1 / 3, 2 / 5)),
        subcase="S2/Z1",
    )

    assert not result.accepted
    assert result.reason == "reject_clusterel_not_documented_ad_bd_cd_thr_edg"
    assert result.candidate is None
    assert result.subcase is None


def test_source_match_is_value_identical_on_repeat() -> None:
    first = certify_thr_edg_source_match_l1(_TET, _THR_TRIANGLE, subcase="S2/Z1")
    second = certify_thr_edg_source_match_l1(_TET, _THR_TRIANGLE, subcase="S2/Z1")

    assert first == second


def test_key_identity_staging_rejects_a_geometrically_exact_table11_subdivision() -> None:
    source_match = certify_thr_edg_source_match_l1(_TET, _THR_TRIANGLE, subcase="S2/Z1")
    assert source_match.accepted and source_match.candidate is not None

    # The candidate has exactly the parent volume and documented subdivided
    # exterior, but the current staging adapter compares raw triangle keys and
    # therefore cannot yet certify a source-face subdivision.
    points = (
        (0, 0, 0),
        (1, 0, 0),
        (0, 1, 0),
        (0, 0, 1),
        (0, 0, 2 / 5),
        (3 / 5, 0, 2 / 5),
        (0, 3 / 5, 2 / 5),
    )
    ids = {"A": 0, "B": 1, "C": 2, "D": 3, "P1": 4, "P2": 5, "P3": 6}
    staged = certify_atomic_staged_replacement(
        points,
        {0: (0, 1, 2, 3)},
        ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)),
        {
            0: tuple(
                tuple(ids[label] for label in tet)
                for tet in source_match.candidate.oriented_children
            )
        },
    )

    assert not staged.accepted
    assert staged.reason == "staged_contract_failed"
    assert not staged.boundary_preserved
    assert staged.volume_preserved
    assert staged.all_positive
