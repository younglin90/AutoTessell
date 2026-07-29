"""Fail-closed exact incidence record for one Chen source-edge segment.

Chen source edges have two incompatible ownership modes: an open segment
traverses tetrahedron interiors, while a cofacial segment is owned by one
facet and its incident tetrahedra.  This module unifies their *record* without
inventing partial ownership or modifying connectivity.  A caller receives one
fully certified mode or no incidence at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from core.generator.native_tet.chen_boundary_aligned_l1 import (
    ChenBoundaryAlignedIncidence,
    classify_boundary_aligned_source_segment,
)
from core.generator.native_tet.chen_source_edge_worklist_l1 import (
    ChenSourcePipel,
    build_source_edge_pipel_worklist,
)


@dataclass(frozen=True)
class ChenSourceEdgeIncidence:
    """Exactly one exhaustive ownership representation for a source segment."""

    mode: Literal["interior", "boundary_aligned"]
    interior_pipels: tuple[ChenSourcePipel, ...]
    boundary_incidence: ChenBoundaryAlignedIncidence | None


@dataclass(frozen=True)
class ChenSourceEdgeIncidenceResult:
    """Fail-closed result; rejected segments deliberately expose no ownership."""

    accepted: bool
    reason: str
    incidence: ChenSourceEdgeIncidence | None


def build_source_edge_incidence(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_start: Sequence[float | int | Fraction],
    source_end: Sequence[float | int | Fraction],
) -> ChenSourceEdgeIncidenceResult:
    """Classify one complete segment as interior or uniquely facet-sided.

    Interior traversal has priority only after its exact gap-free coverage
    proof succeeds.  A cofacial rejection is the sole condition under which
    the facet ledger is queried; all other failed interior proofs remain
    rejected rather than silently changing route.
    """
    interior = build_source_edge_pipel_worklist(points, parent_tets, source_start, source_end)
    if interior.accepted:
        return ChenSourceEdgeIncidenceResult(
            True,
            "accepted_interior",
            ChenSourceEdgeIncidence("interior", interior.pipels, None),
        )
    if interior.reason != "cofacial_or_noninterior_pipel_segment":
        return ChenSourceEdgeIncidenceResult(False, f"interior_rejected:{interior.reason}", None)

    boundary = classify_boundary_aligned_source_segment(
        points, parent_tets, source_start, source_end
    )
    if not boundary.accepted:
        return ChenSourceEdgeIncidenceResult(
            False,
            f"boundary_aligned_rejected:{boundary.reason}",
            None,
        )
    assert boundary.incidence is not None
    return ChenSourceEdgeIncidenceResult(
        True,
        "accepted_boundary_aligned",
        ChenSourceEdgeIncidence("boundary_aligned", (), boundary.incidence),
    )
