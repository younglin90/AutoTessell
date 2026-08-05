"""Common evidence-only authority/transaction barrier for native products.

This module deliberately does not generate or repair mesh geometry.  It makes
the publication decision deterministic after a route has produced a baseline
and a staged candidate.  Geometry hot paths stay in C++; this small contract
is orchestration/evidence code shared by Tet, Hex, Poly, Tri, Quad and surface
boundary-layer adapters.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Hash a finite JSON evidence artifact with stable key ordering."""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class NativeAuthorityTransactionResult:
    accepted: bool
    status: str
    reasons: tuple[str, ...]
    baseline_sha256: str
    candidate_sha256: str
    committed: bool
    rolled_back: bool
    requested_layers: int
    actual_layers: int

    def as_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "status": self.status,
            "reasons": list(self.reasons),
            "baseline_sha256": self.baseline_sha256,
            "candidate_sha256": self.candidate_sha256,
            "committed": self.committed,
            "rolled_back": self.rolled_back,
            "requested_layers": self.requested_layers,
            "actual_layers": self.actual_layers,
        }


_ZERO_TOPOLOGY = (
    "invalid",
    "duplicate",
    "non_manifold",
    "self_intersecting",
    "inverted",
    "negative_measure",
)


def _hard_failures(topology: Mapping[str, Any]) -> list[str]:
    return [
        f"topology:{name}"
        for name in _ZERO_TOPOLOGY
        if topology.get(name, 0) != 0
    ]


def _quality_failures(quality: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if quality.get("non_orthogonality_p95", 0.0) > 35.0:
        failures.append("quality:non_orthogonality_p95")
    if quality.get("non_orthogonality_max", 0.0) > 50.0:
        failures.append("quality:non_orthogonality_max")
    if quality.get("skewness_p95", 0.0) > 0.25:
        failures.append("quality:skewness_p95")
    if quality.get("skewness_max", 0.0) > 0.50:
        failures.append("quality:skewness_max")
    # BL raw aspect is intentionally not a standalone gate.  Routes must
    # provide normal/tangential metric evidence when anisotropy is expected.
    if quality.get("metric_distortion_max", 0.0) > 3.0:
        failures.append("quality:metric_distortion_max")
    return failures


def evaluate_native_authority_transaction(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    requested_layers: int,
    actual_layers: int,
    source_sha256: str,
    candidate_source_sha256: str,
    topology: Mapping[str, Any],
    quality: Mapping[str, Any],
    authority_complete: bool,
    collision_free: bool = True,
    baseline_manifest: Mapping[str, Any] | None = None,
    candidate_manifest: Mapping[str, Any] | None = None,
) -> NativeAuthorityTransactionResult:
    """Evaluate a staged candidate without mutating either input artifact."""
    baseline_hash = canonical_sha256(baseline)
    candidate_hash = canonical_sha256(candidate)
    reasons: list[str] = []
    if (baseline_manifest is None) != (candidate_manifest is None):
        reasons.append("baseline_manifest_pair_required")
    elif baseline_manifest is not None and candidate_manifest is not None:
        from .native_baseline_manifest import (  # noqa: PLC0415
            compare_bl0_candidate_to_baseline,
            validate_baseline_manifest_v1,
        )
        if requested_layers == 0:
            comparison = compare_bl0_candidate_to_baseline(candidate_manifest, baseline_manifest)
            if not comparison["accepted"]:
                reasons.extend(f"baseline_manifest:{item}" for item in comparison["reasons"])
        else:
            for label, manifest in (("baseline", baseline_manifest), ("candidate", candidate_manifest)):
                valid, manifest_reasons = validate_baseline_manifest_v1(manifest)
                if not valid:
                    reasons.extend(f"{label}_manifest:{item}" for item in manifest_reasons)
            if baseline_manifest.get("source") != candidate_manifest.get("source"):
                reasons.append("baseline_manifest:source_authority_mismatch")
    if requested_layers < 0 or actual_layers < 0:
        reasons.append("layer_count_negative")
    if requested_layers != actual_layers:
        reasons.append("layer_count_mismatch")
    if source_sha256 != candidate_source_sha256:
        reasons.append("source_output_binding_mismatch")
    if not authority_complete:
        reasons.append("authority_incomplete")
    if not collision_free:
        reasons.append("collision_or_clearance_failure")
    reasons.extend(_hard_failures(topology))
    reasons.extend(_quality_failures(quality))
    if requested_layers == 0 and candidate_hash != baseline_hash:
        reasons.append("bl0_baseline_identity_mismatch")
    if requested_layers > 0 and actual_layers == 0:
        reasons.append("positive_bl_missing")
    accepted = not reasons
    return NativeAuthorityTransactionResult(
        accepted=accepted,
        status="committed" if accepted else "refused_rollback",
        reasons=tuple(reasons),
        baseline_sha256=baseline_hash,
        candidate_sha256=candidate_hash,
        committed=accepted,
        rolled_back=not accepted,
        requested_layers=requested_layers,
        actual_layers=actual_layers if accepted else 0,
    )


def commit_native_authority_transaction(
    destination: MutableMapping[str, Any],
    candidate: Mapping[str, Any],
    result: NativeAuthorityTransactionResult,
) -> None:
    """Atomically publish a candidate only when its result was accepted."""
    if not result.accepted:
        return
    destination.clear()
    destination.update(copy.deepcopy(dict(candidate)))


__all__ = [
    "NativeAuthorityTransactionResult",
    "canonical_sha256",
    "commit_native_authority_transaction",
    "evaluate_native_authority_transaction",
]
