"""Exact source-edge subsegment-chain contracts."""

from __future__ import annotations

from core.generator.native_tet.chen_source_edge_chain_l1 import audit_source_edge_chain_l1


def test_accepts_an_exact_two_subedge_chain() -> None:
    points = ((0, 0, 0), (2, 0, 0), (1, 0, 0), (0, 1, 1), (0, -1, 1))
    result = audit_source_edge_chain_l1(points, (0, 1), ((0, 2, 3, 4), (2, 1, 3, 4)))
    assert result.accepted
    assert result.chain_edges == ((0, 2), (1, 2))
    assert result.source_points_unchanged and not result.production_mesh_changed


def test_rejects_a_direct_edge_that_skips_an_on_segment_mesh_vertex() -> None:
    points = ((0, 0, 0), (2, 0, 0), (1, 0, 0), (0, 1, 1), (0, -1, 1))
    result = audit_source_edge_chain_l1(points, (0, 1), ((0, 1, 3, 4),))
    assert not result.accepted
    assert result.reason == "source_edge_partition_gap"
