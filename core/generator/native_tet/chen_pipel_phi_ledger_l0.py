"""Test-only Chen--Zheng-2006 ``Phi`` neighbor-ledger certificate.

The one-edge Table-5 split must agree across every already-decomposed neighbor
that shares an original face containing the cut edge.  This module records that
face-to-child-face mapping deterministically.  It is a local conformity proof,
not an end-to-end missing-source-edge recovery worklist.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_pipe_cluster_l0 import IndexTet
from core.generator.native_tet.chen_pipel_one_edge_l0 import (
    ChenOneEdgePipelResult,
    certify_one_edge_pipel_template,
)

FaceKey = tuple[int, int, int]
FaceSplit = tuple[FaceKey, FaceKey]


@dataclass(frozen=True)
class ChenPhiLedgerResult:
    """Read-only schedule-independent face-subdivision certificate."""

    accepted: bool
    reason: str
    replacement_tets: tuple[IndexTet, ...]
    face_ledger: tuple[tuple[FaceKey, FaceSplit], ...]
    local_certificate: ChenOneEdgePipelResult


def _face_key(vertices: Sequence[int]) -> FaceKey:
    ordered = sorted(int(vertex) for vertex in vertices)
    if len(ordered) != 3 or len(set(ordered)) != 3:
        raise ValueError("a face must contain three distinct vertices")
    return ordered[0], ordered[1], ordered[2]


def _face_split(first: FaceKey, second: FaceKey) -> FaceSplit:
    """Return the two replacement faces in a deterministic fixed-size tuple."""
    return (first, second) if first <= second else (second, first)


def _template_face_splits(
    tet: Sequence[int], edge: tuple[int, int], intersection: int
) -> tuple[tuple[FaceKey, FaceSplit], tuple[FaceKey, FaceSplit]]:
    opposite = sorted(int(vertex) for vertex in tet if int(vertex) not in edge)
    if len(opposite) != 2:
        raise ValueError("parent tet does not contain exactly one cut edge")
    first, second = opposite
    start, end = edge
    # Table 5: ABCP/APCD, with P on B-D.  The two original faces
    # containing B-D therefore receive the following deterministic splits.
    return (
        (
            _face_key((first, start, end)),
            _face_split(
                _face_key((first, start, intersection)),
                _face_key((first, intersection, end)),
            ),
        ),
        (
            _face_key((second, start, end)),
            _face_split(
                _face_key((second, start, intersection)),
                _face_key((second, intersection, end)),
            ),
        ),
    )


def certify_one_edge_phi_ledger(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    cut_edge: tuple[int, int],
    intersection_point: int,
    *,
    processing_order: Sequence[int] | None = None,
) -> ChenPhiLedgerResult:
    """Certify Table-5 shared-face agreement under a deterministic schedule."""
    local = certify_one_edge_pipel_template(points, parent_tets, cut_edge, intersection_point)
    if not local.accepted:
        return ChenPhiLedgerResult(False, local.reason, (), (), local)
    edge_start, edge_end = sorted((int(cut_edge[0]), int(cut_edge[1])))
    edge: tuple[int, int] = (edge_start, edge_end)
    if processing_order is None:
        order = tuple(range(len(parent_tets)))
    else:
        order = tuple(int(index) for index in processing_order)
    if tuple(sorted(order)) != tuple(range(len(parent_tets))):
        return ChenPhiLedgerResult(False, "invalid_processing_order", (), (), local)

    expected_contributors: Counter[FaceKey] = Counter()
    for tet in parent_tets:
        for face, _split in _template_face_splits(tet, edge, int(intersection_point)):
            expected_contributors[face] += 1

    ledger: dict[FaceKey, FaceSplit] = {}
    contributors: Counter[FaceKey] = Counter()
    for index in order:
        for face, split in _template_face_splits(parent_tets[index], edge, int(intersection_point)):
            prior = ledger.get(face)
            if prior is not None and prior != split:
                return ChenPhiLedgerResult(False, "shared_face_split_conflict", (), (), local)
            ledger[face] = split
            contributors[face] += 1
    if any(count != 2 for count in expected_contributors.values()):
        return ChenPhiLedgerResult(False, "cut_edge_pipe_not_closed", (), (), local)
    if contributors != expected_contributors:
        return ChenPhiLedgerResult(False, "incomplete_neighbor_ledger", (), (), local)
    return ChenPhiLedgerResult(
        True,
        "accepted",
        local.replacement_tets,
        tuple(sorted(ledger.items())),
        local,
    )
