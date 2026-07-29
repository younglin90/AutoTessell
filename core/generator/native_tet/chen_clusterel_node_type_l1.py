"""Exact Chen clusterel cut-node provenance for the strict-intersection lane.

The paper stores an ``ntypes`` value beside every clusterel edge intersection.
The current finite-triangle classifier deliberately rejects endpoint, extension,
and coplanar contacts, so every accepted cut point must be an interior-edge
``NOD_MID``.  This module makes that restricted fact explicit and binds each
node to the independently clipped positive-area source fragment.  It does not
invent the broader node cases or a Table-5 local label mapping.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from core.generator.native_tet.chen_clusterel_type_l0 import (
    ChenClusterelTypeResult,
    classify_clusterel_type,
)
from core.generator.native_tet.chen_penetration_l0 import RationalPoint
from core.generator.native_tet.chen_source_triangle_fragment_l1 import (
    ChenSourceTriangleFragmentResult,
    audit_source_triangle_fragment_l1,
)

NodeType = Literal["NOD_MID"]


@dataclass(frozen=True)
class ChenClusterelCutNode:
    """One strict source-facet cut point with its paper-compatible node type."""

    local_edge: tuple[int, int]
    point: RationalPoint
    node_type: NodeType
    fragment_vertex_index: int


@dataclass(frozen=True)
class ChenClusterelNodeTypeResult:
    """Read-only strict-node ledger; rejected inputs expose no node records."""

    accepted: bool
    reason: str
    classification: ChenClusterelTypeResult | None
    fragment: ChenSourceTriangleFragmentResult | None
    cut_nodes: tuple[ChenClusterelCutNode, ...]
    source_points_unchanged: bool
    production_mesh_changed: bool


def classify_strict_clusterel_node_types_l1(
    tetrahedron: Sequence[Sequence[float | int | Fraction]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenClusterelNodeTypeResult:
    """Bind each strict edge crossing to an exact fragment vertex and ``NOD_MID``."""
    classification = classify_clusterel_type(tetrahedron, source_triangle)
    if (
        not classification.accepted
        or classification.clusterel_type in {None, "CO_PLAN"}
        or classification.penetration is None
        or classification.penetration.status != "unique"
    ):
        return ChenClusterelNodeTypeResult(
            False,
            "clusterel_has_no_supported_strict_cut_nodes",
            classification,
            None,
            (),
            True,
            False,
        )
    fragment = audit_source_triangle_fragment_l1(tetrahedron, source_triangle)
    if not fragment.accepted:
        return ChenClusterelNodeTypeResult(
            False,
            f"source_fragment_failed:{fragment.reason}",
            classification,
            fragment,
            (),
            fragment.source_points_unchanged,
            False,
        )
    nodes: list[ChenClusterelCutNode] = []
    for edge, point in zip(
        classification.penetration.penetrating_edges,
        classification.penetration.intersection_points,
        strict=True,
    ):
        try:
            fragment_index = fragment.vertices.index(point)
        except ValueError:
            return ChenClusterelNodeTypeResult(
                False,
                "strict_cut_node_is_not_a_source_fragment_vertex",
                classification,
                fragment,
                (),
                fragment.source_points_unchanged,
                False,
            )
        nodes.append(ChenClusterelCutNode(edge, point, "NOD_MID", fragment_index))
    return ChenClusterelNodeTypeResult(
        True,
        "accepted",
        classification,
        fragment,
        tuple(nodes),
        fragment.source_points_unchanged,
        False,
    )
