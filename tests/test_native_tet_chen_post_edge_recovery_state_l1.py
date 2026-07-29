"""L1 exact-record tests for a Chen post-edge-recovery clusterel state."""

from __future__ import annotations

from core.generator.native_tet.chen_clusterel_node_state_l0 import (
    classify_clusterel_node_states_l0,
)
from core.generator.native_tet.chen_post_edge_recovery_state_l1 import (
    ChenPostEdgeRecoveryClusterelRecord,
    certify_post_edge_recovery_clusterel_state_l1,
)


_POINTS = ((0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2))
_PARENTS = ((0, 1, 3, 4), (1, 2, 3, 4), (2, 0, 3, 4))
_SOURCE_IDS = (0, 1, 2)


def _record() -> ChenPostEdgeRecoveryClusterelRecord:
    nodes = classify_clusterel_node_states_l0(
        tuple(_POINTS[index] for index in _PARENTS[0]), tuple(_POINTS[index] for index in _SOURCE_IDS)
    )
    assert nodes.accepted
    return ChenPostEdgeRecoveryClusterelRecord(0, nodes.nodes)


def test_recovered_source_edges_and_exact_node_record_pass() -> None:
    assert all(not set(_SOURCE_IDS) <= set(parent) for parent in _PARENTS)
    result = certify_post_edge_recovery_clusterel_state_l1(_POINTS, _PARENTS, _SOURCE_IDS, _record())

    assert result.accepted, result.reason
    assert result.regenerated_nodes is not None and result.regenerated_nodes.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_missing_source_edge_rejects_before_trusting_record() -> None:
    result = certify_post_edge_recovery_clusterel_state_l1(
        _POINTS, (_PARENTS[0], _PARENTS[1]), _SOURCE_IDS, _record()
    )

    assert not result.accepted
    assert result.reason == "source_edges_are_not_all_recovered"


def test_fabricated_node_record_rejects_even_with_recovered_source_edges() -> None:
    record = _record()
    result = certify_post_edge_recovery_clusterel_state_l1(
        _POINTS, _PARENTS, _SOURCE_IDS, ChenPostEdgeRecoveryClusterelRecord(0, record.nodes[:-1])
    )

    assert not result.accepted
    assert result.reason == "recorded_nodes_do_not_match_exact_predicate"


def test_post_edge_state_result_is_value_identical_on_repeat() -> None:
    first = certify_post_edge_recovery_clusterel_state_l1(_POINTS, _PARENTS, _SOURCE_IDS, _record())
    second = certify_post_edge_recovery_clusterel_state_l1(_POINTS, _PARENTS, _SOURCE_IDS, _record())

    assert first == second
