"""Report-only policy evidence for native-tet strict-overlap diagnostics.

The generator never imports this module.  It turns a previously captured
``InitialStrictOverlapSourceRecord`` into an explicit *future-work* category;
it never changes the runtime sidedness result, threshold, refusal, or writer
decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from .initial_overlap_source_l1 import InitialStrictOverlapSourceRecord


class StrictOverlapPolicyDisposition(StrEnum):
    """Evidence outcomes, deliberately separate from runtime acceptance."""

    NO_STRICT_OVERLAP_OBSERVED = "no_strict_overlap_observed"
    UNRELAXABLE_SAME_SIDE = "unrelaxable_same_side"
    FUTURE_CALIBRATION_ELIGIBLE = "future_calibration_eligible"
    PROVENANCE_REPAIR_REQUIRED = "provenance_repair_required"


@dataclass(frozen=True, slots=True)
class StrictOverlapPolicyEvidence:
    """Immutable policy table output; it grants no runtime permission."""

    disposition: StrictOverlapPolicyDisposition
    reason: str
    fixture: str | None
    audit_call_index: int | None
    overlap_source_class: str | None
    n_same_side_internal_faces: int
    n_ambiguous_internal_faces: int
    source_faces_preserved: bool | None
    n_overlap_pairs: int
    future_calibration_eligible: bool
    runtime_classification_unchanged: bool = True
    runtime_relaxation_authorized: bool = False

    def as_json(self) -> dict[str, object]:
        """Return scalar-only evidence for deterministic L1 comparison."""
        return asdict(self)


def evaluate_strict_overlap_policy_l0(
    record: InitialStrictOverlapSourceRecord | None,
) -> StrictOverlapPolicyEvidence:
    """Classify existing evidence without altering the strict-overlap contract.

    Any same-side internal face is geometric overlap evidence.  It remains
    unrelaxable even when all source-component and facet-provenance checks
    pass, because exact source preservation cannot make two incident cells on
    one face valid.  Ambiguity without same-side overlap is evidence only for a
    separately predeclared future calibration study; it grants no relaxation.
    """
    if record is None:
        return StrictOverlapPolicyEvidence(
            StrictOverlapPolicyDisposition.NO_STRICT_OVERLAP_OBSERVED,
            "no_same_side_internal_face_observed",
            None,
            None,
            None,
            0,
            0,
            None,
            0,
            False,
        )
    common = {
        "fixture": record.fixture,
        "audit_call_index": record.audit_call_index,
        "overlap_source_class": record.overlap_source_class,
        "n_same_side_internal_faces": record.n_same_side_internal_faces,
        "n_ambiguous_internal_faces": record.n_ambiguous_internal_faces,
        "source_faces_preserved": record.source_faces_preserved,
        "n_overlap_pairs": record.n_overlap_pairs,
    }
    if record.n_same_side_internal_faces > 0:
        return StrictOverlapPolicyEvidence(
            StrictOverlapPolicyDisposition.UNRELAXABLE_SAME_SIDE,
            (
                "same_side_overlap_with_source_provenance_preserved"
                if record.source_faces_preserved
                else "same_side_overlap_with_source_provenance_debt"
            ),
            future_calibration_eligible=False,
            **common,
        )
    if not record.source_faces_preserved or record.n_overlap_pairs > 0:
        return StrictOverlapPolicyEvidence(
            StrictOverlapPolicyDisposition.PROVENANCE_REPAIR_REQUIRED,
            "source_provenance_debt_is_not_a_sidedness_threshold_calibration",
            future_calibration_eligible=False,
            **common,
        )
    if record.n_ambiguous_internal_faces > 0:
        return StrictOverlapPolicyEvidence(
            StrictOverlapPolicyDisposition.FUTURE_CALIBRATION_ELIGIBLE,
            "ambiguity_without_same_side_overlap_requires_independent_calibration",
            future_calibration_eligible=True,
            **common,
        )
    return StrictOverlapPolicyEvidence(
        StrictOverlapPolicyDisposition.NO_STRICT_OVERLAP_OBSERVED,
        "no_same_side_or_ambiguity_debt_observed",
        future_calibration_eligible=False,
        **common,
    )


__all__ = [
    "StrictOverlapPolicyDisposition",
    "StrictOverlapPolicyEvidence",
    "evaluate_strict_overlap_policy_l0",
]
