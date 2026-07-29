"""L0 source-edge recovery precondition contracts."""

from __future__ import annotations

from core.generator.native_tet.chen_source_edge_presence_l0 import (
    audit_source_edge_presence_l0,
)


def test_audit_requires_exact_input_edges_not_merely_segment_traversal() -> None:
    tets = ((0, 1, 2, 3), (0, 2, 3, 4))
    accepted = audit_source_edge_presence_l0(5, ((0, 1), (1, 2), (0, 2)), tets)
    missing = audit_source_edge_presence_l0(5, ((0, 1), (1, 4)), tets)
    assert accepted.accepted
    assert missing.reason == "source_edges_missing_from_tet_complex"
    assert missing.missing_edges == ((1, 4),)
    assert not missing.production_mesh_changed
