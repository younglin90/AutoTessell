"""Immutable source-edge presence audit before Si--Gärtner facet recovery."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

Edge = tuple[int, int]
Tet = tuple[int, int, int, int]


@dataclass(frozen=True)
class ChenSourceEdgePresenceAudit:
    """Exact index-edge census; it does not treat segment traversal as recovery."""

    accepted: bool
    reason: str
    present_edges: tuple[Edge, ...]
    missing_edges: tuple[Edge, ...]
    production_mesh_changed: bool


def _edge(first: int, second: int) -> Edge:
    return (first, second) if first < second else (second, first)


def _tet(value: Sequence[int]) -> Tet | None:
    result = tuple(int(index) for index in value)
    if len(result) != 4 or len(set(result)) != 4:
        return None
    return result[0], result[1], result[2], result[3]


def _tet_edges(tets: Sequence[Tet]) -> set[Edge]:
    return {
        _edge(tet[first], tet[second])
        for tet in tets
        for first in range(4)
        for second in range(first + 1, 4)
    }


def audit_source_edge_presence_l0(
    point_count: int,
    source_edges: Sequence[Sequence[int]],
    current_tets: Sequence[Sequence[int]],
) -> ChenSourceEdgePresenceAudit:
    """Require every exact input edge to be an edge of the current tet complex."""
    if point_count <= 0:
        return ChenSourceEdgePresenceAudit(False, "invalid_point_count", (), (), False)
    source = tuple(_edge(int(edge[0]), int(edge[1])) for edge in source_edges if len(edge) == 2)
    typed_tets = tuple(_tet(tet) for tet in current_tets)
    if (
        len(source) != len(source_edges)
        or not source
        or not typed_tets
        or any(tet is None for tet in typed_tets)
        or any(index < 0 or index >= point_count for edge in source for index in edge)
        or any(
            index < 0 or index >= point_count
            for tet in typed_tets
            if tet is not None
            for index in tet
        )
    ):
        return ChenSourceEdgePresenceAudit(
            False, "invalid_source_edge_or_tetrahedron", (), (), False
        )
    current = _tet_edges(tuple(tet for tet in typed_tets if tet is not None))
    unique = tuple(sorted(set(source)))
    present = tuple(edge for edge in unique if edge in current)
    missing = tuple(edge for edge in unique if edge not in current)
    return ChenSourceEdgePresenceAudit(
        not missing,
        "accepted" if not missing else "source_edges_missing_from_tet_complex",
        present,
        missing,
        False,
    )
