"""Test-only named mutation-boundary markers for strict-audit attribution.

The generator never imports this module.  An isolated test wrapper records a
candidate mutation's exact pre/post array fingerprints, then labels only a
strict-audit call that matches exactly one boundary side.  Missing, unchanged,
or ambiguous fingerprints stay ``UNATTRIBUTED`` and therefore defer policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .initial_overlap_source_l1 import array_sha256
from .same_side_mutation_attribution_l0 import (
    MutationPhase,
    SameSideAuditCallMetadata,
)


@dataclass(frozen=True, slots=True)
class NamedMutationBoundaryMarker:
    """Exact before/after candidate arrays from one test-only mutation call."""

    mutation_name: str
    pre_points_sha256: str
    pre_tets_sha256: str
    post_points_sha256: str
    post_tets_sha256: str

    def as_json(self) -> dict[str, object]:
        """Return scalar-only marker evidence for subprocess comparison."""
        return asdict(self)


def marker_from_arrays_l1(
    mutation_name: str,
    pre_points: np.ndarray,
    pre_tets: np.ndarray,
    post_points: np.ndarray,
    post_tets: np.ndarray,
) -> NamedMutationBoundaryMarker | None:
    """Record a changed named candidate; unchanged arrays carry no marker."""
    if not isinstance(mutation_name, str) or not mutation_name.strip():
        raise ValueError("mutation_name must be a nonblank string")
    marker = NamedMutationBoundaryMarker(
        mutation_name,
        array_sha256(pre_points),
        array_sha256(pre_tets),
        array_sha256(post_points),
        array_sha256(post_tets),
    )
    if (
        marker.pre_points_sha256 == marker.post_points_sha256
        and marker.pre_tets_sha256 == marker.post_tets_sha256
    ):
        return None
    return marker


def metadata_for_strict_audit_call_l1(
    audit_call_index: int,
    points: np.ndarray,
    tets: np.ndarray,
    markers: tuple[NamedMutationBoundaryMarker, ...],
) -> SameSideAuditCallMetadata:
    """Return named pre/post metadata only for one unambiguous exact match."""
    points_hash = array_sha256(points)
    tets_hash = array_sha256(tets)
    matches: list[tuple[str, MutationPhase]] = []
    for marker in markers:
        if (points_hash, tets_hash) == (marker.pre_points_sha256, marker.pre_tets_sha256):
            matches.append((marker.mutation_name, MutationPhase.PRE))
        if (points_hash, tets_hash) == (marker.post_points_sha256, marker.post_tets_sha256):
            matches.append((marker.mutation_name, MutationPhase.POST))
    if len(matches) != 1:
        return SameSideAuditCallMetadata(
            audit_call_index,
            0,
            None,
            MutationPhase.UNATTRIBUTED,
        )
    mutation_name, phase = matches[0]
    return SameSideAuditCallMetadata(audit_call_index, 0, mutation_name, phase)


__all__ = [
    "NamedMutationBoundaryMarker",
    "marker_from_arrays_l1",
    "metadata_for_strict_audit_call_l1",
]
