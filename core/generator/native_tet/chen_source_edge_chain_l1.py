"""Exact one-dimensional source-edge chain certificate.

A recovered source segment may be subdivided by an on-segment Steiner point.
Checking only whether its original endpoints form one tet edge is therefore too
strict. This report-only ledger requires the current tet 1-skeleton to form an
exact, non-overlapping chain through every mesh vertex lying on that source
segment.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import _cross, _dot, _point, _sub

Point = tuple[Fraction, Fraction, Fraction]
Edge = tuple[int, int]
Tet = tuple[int, int, int, int]


@dataclass(frozen=True)
class ChenSourceEdgeChainAudit:
    """Immutable exact representation certificate for one source segment."""

    accepted: bool
    reason: str
    on_segment_vertex_ids: tuple[int, ...]
    chain_edges: tuple[Edge, ...]
    source_points_unchanged: bool
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


def _parameter_on_segment(point: Point, first: Point, second: Point) -> Fraction | None:
    direction = _sub(second, first)
    length_squared = Fraction(_dot(direction, direction))
    if length_squared == 0 or _cross(direction, _sub(point, first)) != (0, 0, 0):
        return None
    parameter = Fraction(_dot(_sub(point, first), direction)) / length_squared
    return parameter if Fraction(0) <= parameter <= Fraction(1) else None


def audit_source_edge_chain_l1(
    points: Sequence[Sequence[float | int | Fraction]],
    source_edge: Sequence[int],
    current_tets: Sequence[Sequence[int]],
) -> ChenSourceEdgeChainAudit:
    """Require a conforming 1-D tet-edge partition of one exact source edge."""
    rational = tuple(_point(point) for point in points)
    before = rational
    edge_values = tuple(int(index) for index in source_edge)
    tets = tuple(_tet(tet) for tet in current_tets)
    if (
        len(edge_values) != 2
        or edge_values[0] == edge_values[1]
        or not tets
        or any(tet is None for tet in tets)
        or any(index < 0 or index >= len(rational) for index in edge_values)
        or any(
            index < 0 or index >= len(rational) for tet in tets if tet is not None for index in tet
        )
    ):
        return ChenSourceEdgeChainAudit(
            False, "invalid_source_edge_or_tetrahedron", (), (), True, False
        )
    first, second = (rational[index] for index in edge_values)
    parameters = {
        index: _parameter_on_segment(point, first, second) for index, point in enumerate(rational)
    }
    on_segment = tuple(index for index, parameter in parameters.items() if parameter is not None)
    ordered = tuple(sorted(on_segment, key=lambda index: (parameters[index], index)))
    if parameters[edge_values[0]] != 0 or parameters[edge_values[1]] != 1:
        return ChenSourceEdgeChainAudit(
            False, "source_endpoint_not_on_own_segment", (), (), True, False
        )
    if len({parameters[index] for index in ordered}) != len(ordered):
        return ChenSourceEdgeChainAudit(
            False, "duplicate_on_segment_vertex", ordered, (), True, False
        )
    typed_tets = tuple(tet for tet in tets if tet is not None)
    mesh_edges = _tet_edges(typed_tets)
    expected = tuple(_edge(left, right) for left, right in zip(ordered, ordered[1:]))
    expected_set = set(expected)
    chain_edges = tuple(
        sorted(
            edge
            for edge in mesh_edges
            if edge[0] in parameters
            and edge[1] in parameters
            and parameters[edge[0]] is not None
            and parameters[edge[1]] is not None
        )
    )
    chain_set = set(chain_edges)
    if not expected_set.issubset(chain_set):
        return ChenSourceEdgeChainAudit(
            False, "source_edge_partition_gap", ordered, chain_edges, rational == before, False
        )
    if chain_set != expected_set:
        return ChenSourceEdgeChainAudit(
            False,
            "nonconforming_overlapping_source_edge",
            ordered,
            chain_edges,
            rational == before,
            False,
        )
    unchanged = rational == before
    return ChenSourceEdgeChainAudit(
        unchanged,
        "accepted" if unchanged else "source_points_changed",
        ordered,
        chain_edges,
        unchanged,
        False,
    )
