"""Report-only attribution of first native-tet same-side audit evidence.

No generator imports this module.  Existing L1 records identify strict-audit
call order but intentionally contain no mutation-boundary marker; this module
therefore returns ``DEFER`` instead of inventing pre/post causality.  L0 event
metadata demonstrates the exact evidence required for a future remedy card.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from numbers import Integral

from .initial_overlap_source_l1 import InitialStrictOverlapSourceRecord


class MutationPhase(StrEnum):
    """Position of an audit relative to a named non-source candidate mutation."""

    PRE = "pre"
    POST = "post"
    UNATTRIBUTED = "unattributed"


class SameSideMutationAttribution(StrEnum):
    """Evidence-only result; none is a runtime topology classification."""

    NO_SAME_SIDE_OBSERVED = "no_same_side_observed"
    PRE_NAMED_NON_SOURCE_MUTATION = "pre_named_non_source_mutation"
    POST_NAMED_NON_SOURCE_MUTATION = "post_named_non_source_mutation"
    DEFER_INSUFFICIENT_MUTATION_METADATA = "defer_insufficient_mutation_metadata"


@dataclass(frozen=True, slots=True)
class SameSideAuditCallMetadata:
    """Immutable audit-call facts supplied by test-only instrumentation."""

    audit_call_index: int
    n_same_side_internal_faces: int
    mutation_name: str | None
    mutation_phase: MutationPhase


@dataclass(frozen=True, slots=True)
class FirstSameSideMutationEvidence:
    """First same-side attribution result, explicitly non-authoritative at runtime."""

    attribution: SameSideMutationAttribution
    audit_call_index: int | None
    mutation_name: str | None
    mutation_phase: MutationPhase | None
    n_same_side_internal_faces: int
    runtime_classification_unchanged: bool = True
    same_side_relaxation_authorized: bool = False

    def as_json(self) -> dict[str, object]:
        """Return scalar-only evidence for deterministic L1 comparison."""
        return asdict(self)


def metadata_from_initial_overlap_records(
    records: tuple[InitialStrictOverlapSourceRecord, ...],
) -> tuple[SameSideAuditCallMetadata, ...]:
    """Expose current L1 call order while preserving its missing marker honestly."""
    return tuple(
        SameSideAuditCallMetadata(
            audit_call_index=record.audit_call_index,
            n_same_side_internal_faces=record.n_same_side_internal_faces,
            mutation_name=None,
            mutation_phase=MutationPhase.UNATTRIBUTED,
        )
        for record in records
    )


def attribute_first_same_side_mutation_l0(
    events: tuple[SameSideAuditCallMetadata, ...],
) -> FirstSameSideMutationEvidence:
    """Classify only explicit mutation metadata; missing provenance means DEFER."""
    if not isinstance(events, tuple):
        raise TypeError("events must be a tuple of SameSideAuditCallMetadata")
    for event in events:
        if not isinstance(event, SameSideAuditCallMetadata):
            raise TypeError("events must contain SameSideAuditCallMetadata")
        if (
            isinstance(event.audit_call_index, bool)
            or not isinstance(event.audit_call_index, Integral)
            or int(event.audit_call_index) < 0
        ):
            raise ValueError("audit_call_index must be a non-negative integer")
        if (
            isinstance(event.n_same_side_internal_faces, bool)
            or not isinstance(event.n_same_side_internal_faces, Integral)
            or int(event.n_same_side_internal_faces) < 0
        ):
            raise ValueError("n_same_side_internal_faces must be a non-negative integer")
        if not isinstance(event.mutation_phase, MutationPhase):
            raise ValueError("mutation_phase must be a MutationPhase")
        if event.mutation_name is not None and (
            not isinstance(event.mutation_name, str) or not event.mutation_name.strip()
        ):
            raise ValueError("mutation_name must be None or a nonblank string")
        if event.mutation_phase is MutationPhase.UNATTRIBUTED:
            if event.mutation_name is not None:
                raise ValueError("unattributed metadata must not name a mutation")
        elif event.mutation_name is None:
            raise ValueError("pre/post metadata requires a named mutation")
    ordered = tuple(sorted(events, key=lambda event: event.audit_call_index))
    if len({event.audit_call_index for event in ordered}) != len(ordered):
        raise ValueError("audit call indices must be unique")
    first = next(
        (event for event in ordered if event.n_same_side_internal_faces > 0), None
    )
    if first is None:
        return FirstSameSideMutationEvidence(
            SameSideMutationAttribution.NO_SAME_SIDE_OBSERVED,
            None,
            None,
            None,
            0,
        )
    if first.mutation_name is None or first.mutation_phase is MutationPhase.UNATTRIBUTED:
        return FirstSameSideMutationEvidence(
            SameSideMutationAttribution.DEFER_INSUFFICIENT_MUTATION_METADATA,
            first.audit_call_index,
            first.mutation_name,
            first.mutation_phase,
            first.n_same_side_internal_faces,
        )
    attribution = (
        SameSideMutationAttribution.PRE_NAMED_NON_SOURCE_MUTATION
        if first.mutation_phase is MutationPhase.PRE
        else SameSideMutationAttribution.POST_NAMED_NON_SOURCE_MUTATION
    )
    return FirstSameSideMutationEvidence(
        attribution,
        first.audit_call_index,
        first.mutation_name,
        first.mutation_phase,
        first.n_same_side_internal_faces,
    )


__all__ = [
    "FirstSameSideMutationEvidence",
    "MutationPhase",
    "SameSideAuditCallMetadata",
    "SameSideMutationAttribution",
    "attribute_first_same_side_mutation_l0",
    "metadata_from_initial_overlap_records",
]
