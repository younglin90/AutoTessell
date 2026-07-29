"""Exact local provenance closure for a Chen--Zheng Table-5 transaction.

The boundary-aligned source record identifies the two facet owners.  Table 5
then names the only additional parent pipels required by its documented Phi
queries.  A candidate may replace exactly that closure, never an arbitrary
extra parent, before immutable whole-boundary staging is considered.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_nod_edg_txn_l1 import (
    ChenNodEdgTransactionResult,
    certify_local_nod_edg_transaction,
)


@dataclass(frozen=True)
class ChenTable5ProvenanceClosureResult:
    """Fail-closed local closure; a rejected result authorizes no parents."""

    accepted: bool
    reason: str
    authorized_parent_ids: tuple[int, ...]
    transaction: ChenNodEdgTransactionResult | None


def certify_table5_provenance_closure(
    points: Sequence[Sequence[float | int | Fraction]],
    active_parents: Mapping[int, Sequence[int]],
    source_boundary_faces: Sequence[Sequence[int]],
    candidate_children: Mapping[int, Sequence[Sequence[int]]],
    *,
    target_parent: int,
    source_node: int,
    cut_edge: tuple[int, int],
    intersection_point: int,
) -> ChenTable5ProvenanceClosureResult:
    """Require candidates to be exactly the source-owner plus Phi closure."""
    transaction = certify_local_nod_edg_transaction(
        points,
        active_parents,
        source_boundary_faces,
        candidate_children,
        target_parent=target_parent,
        source_node=source_node,
        cut_edge=cut_edge,
        intersection_point=intersection_point,
    )
    if not transaction.accepted or transaction.source_incidence is None:
        return ChenTable5ProvenanceClosureResult(
            False,
            f"local_transaction_rejected:{transaction.reason}",
            (),
            None,
        )
    boundary = transaction.source_incidence.boundary_incidence
    if transaction.source_incidence.mode != "boundary_aligned" or boundary is None:
        return ChenTable5ProvenanceClosureResult(
            False, "table5_requires_boundary_aligned_source_incidence", (), None
        )
    parent_ids = tuple(sorted(int(identifier) for identifier in active_parents))
    if any(position < 0 or position >= len(parent_ids) for position in boundary.owner_tets):
        return ChenTable5ProvenanceClosureResult(
            False, "source_owner_position_out_of_range", (), None
        )
    phi_positions = tuple(result.neighbor_tet for result in transaction.phi_results)
    if any(
        position is None or position < 0 or position >= len(parent_ids)
        for position in phi_positions
    ):
        return ChenTable5ProvenanceClosureResult(
            False, "phi_neighbor_position_out_of_range", (), None
        )
    authorized = tuple(
        sorted(
            {
                int(target_parent),
                *(parent_ids[position] for position in boundary.owner_tets),
                *(parent_ids[position] for position in phi_positions if position is not None),
            }
        )
    )
    candidate_ids = tuple(sorted(int(identifier) for identifier in candidate_children))
    if candidate_ids != authorized:
        return ChenTable5ProvenanceClosureResult(
            False, "candidate_parent_set_not_exact_phi_closure", (), None
        )
    return ChenTable5ProvenanceClosureResult(True, "accepted", authorized, transaction)
