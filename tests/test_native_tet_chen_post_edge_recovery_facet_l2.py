"""L2 full source-facet state tests after Chen missing-edge recovery."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_clusterel_node_state_l0 import (
    classify_clusterel_node_states_l0,
)
from core.generator.native_tet.chen_post_edge_recovery_facet_l2 import (
    certify_post_edge_recovery_facet_state_l2,
)
from core.generator.native_tet.chen_post_edge_recovery_state_l1 import (
    ChenPostEdgeRecoveryClusterelRecord,
)


_POINTS = ((0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2))
_PARENTS = ((0, 1, 3, 4), (1, 2, 3, 4), (2, 0, 3, 4))
_SOURCE_IDS = (0, 1, 2)


def _records() -> tuple[ChenPostEdgeRecoveryClusterelRecord, ...]:
    source = tuple(_POINTS[index] for index in _SOURCE_IDS)
    return tuple(
        ChenPostEdgeRecoveryClusterelRecord(
            parent_index,
            classify_clusterel_node_states_l0(tuple(_POINTS[index] for index in tet), source).nodes,
        )
        for parent_index, tet in enumerate(_PARENTS)
    )


def test_complete_post_edge_facet_state_has_three_one_edge_clusterels_and_exact_coverage() -> None:
    result = certify_post_edge_recovery_facet_state_l2(_POINTS, _PARENTS, _SOURCE_IDS, _records())

    assert result.accepted, result.reason
    assert result.active_parent_types == ((0, "ONE_EDG"), (1, "ONE_EDG"), (2, "ONE_EDG"))
    assert len(result.records) == 3 and all(record.accepted for record in result.records)
    assert result.coverage is not None and result.coverage.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_omitted_active_parent_record_rejects_before_coverage_claim() -> None:
    result = certify_post_edge_recovery_facet_state_l2(_POINTS, _PARENTS, _SOURCE_IDS, _records()[:2])

    assert not result.accepted
    assert result.reason == "records_must_cover_exactly_all_active_parents"
    assert result.coverage is None


def test_source_face_already_present_is_not_a_missing_facet_state() -> None:
    result = certify_post_edge_recovery_facet_state_l2(
        _POINTS, ((0, 1, 2, 3),), _SOURCE_IDS, ()
    )

    assert not result.accepted
    assert result.reason == "source_face_is_already_a_parent_face"


def test_complete_post_edge_facet_state_is_value_identical_on_repeat() -> None:
    first = certify_post_edge_recovery_facet_state_l2(_POINTS, _PARENTS, _SOURCE_IDS, _records())
    second = certify_post_edge_recovery_facet_state_l2(_POINTS, _PARENTS, _SOURCE_IDS, _records())

    assert first == second


def test_l2_fixture_with_recovered_edges_exposes_two_edge_clusterels_without_source_face() -> None:
    points = (
        (0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2),
        (1, 1, -1), (4, 2, 2), (2, Fraction(4, 3), 0),
        (Fraction(5, 4), Fraction(5, 4), 0),
    )
    parents = (
        (5, 0, 1, 4), (5, 0, 2, 4), (5, 6, 2, 1), (5, 6, 3, 1),
        (5, 0, 3, 1), (5, 6, 3, 2), (5, 0, 3, 2),
    )
    source_ids = (0, 1, 2)
    source = tuple(points[index] for index in source_ids)
    records = tuple(
        ChenPostEdgeRecoveryClusterelRecord(
            index, classify_clusterel_node_states_l0(tuple(points[vertex] for vertex in tet), source).nodes
        )
        for index, tet in enumerate(parents)
        if index in {2, 3, 4, 5, 6}
    )

    result = certify_post_edge_recovery_facet_state_l2(points, parents, source_ids, records)

    assert result.accepted, result.reason
    assert result.active_parent_types == (
        (2, "ONE_EDG"), (3, "TWO_EDG"), (4, "ONE_EDG"),
        (5, "TWO_EDG"), (6, "ONE_EDG"),
    )
    assert result.coverage is not None and result.coverage.accepted


def test_l2_fixture_with_thr_edge_clusterel_preserves_complete_source_coverage() -> None:
    """A full parent mesh may contain THR_EDG after missing-edge recovery.

    This is a read-only census/coverage fixture.  It deliberately stops before
    choosing a Table-11 S/Z row or mutating any production recovery state.
    """
    points = (
        (0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2),
        (4, 1, 2), (1, 0, -1), (3, -1, 4), (4, 4, 4), (2, 1, 3),
    )
    parents = (
        (6, 0, 2, 4), (6, 7, 1, 4), (6, 0, 7, 4), (6, 0, 7, 1),
        (5, 8, 2, 1), (5, 6, 2, 1), (3, 5, 8, 2), (3, 6, 0, 2),
        (3, 5, 6, 2), (9, 0, 7, 1), (9, 5, 7, 1), (9, 5, 8, 7),
        (9, 3, 8, 7), (9, 3, 5, 8), (9, 3, 6, 0), (9, 3, 5, 6),
        (9, 6, 0, 1), (9, 5, 6, 1),
    )
    source_ids = (0, 1, 2)
    source = tuple(points[index] for index in source_ids)
    active = {5, 7, 8, 14, 15, 16, 17}
    records = tuple(
        ChenPostEdgeRecoveryClusterelRecord(
            index,
            classify_clusterel_node_states_l0(tuple(points[vertex] for vertex in tet), source).nodes,
        )
        for index, tet in enumerate(parents)
        if index in active
    )

    result = certify_post_edge_recovery_facet_state_l2(points, parents, source_ids, records)

    assert result.accepted, result.reason
    assert result.active_parent_types == (
        (5, "ONE_EDG"), (7, "ONE_EDG"), (8, "TWO_EDG"),
        (14, "TWO_EDG"), (15, "THR_EDG"), (16, "ONE_EDG"), (17, "TWO_EDG"),
    )
    assert result.coverage is not None and result.coverage.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed
