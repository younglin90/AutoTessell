"""Measured source/output authority gate for the native release matrix."""

from __future__ import annotations

from dataclasses import dataclass

from core.evaluator.native_release_matrix import (
    NativeReleaseMatrixAudit,
    validate_native_release_matrix,
)


@dataclass(frozen=True, slots=True)
class NativeReleaseAuthorityAudit:
    """Combined base-matrix and measured-authority result."""

    valid: bool
    status: str
    matrix: NativeReleaseMatrixAudit
    invalid_cases: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "status": self.status,
            "matrix": self.matrix.as_dict(),
            "invalid_cases": list(self.invalid_cases),
            "reasons": list(self.reasons),
        }


def _sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _authority_valid(case: object) -> tuple[bool, str]:
    if not isinstance(case, dict):
        return False, "case_not_object"
    source = case.get("source_authority")
    certificate = case.get("source_output_authority")
    if not isinstance(source, dict) or source.get("authoritative") is not True:
        return False, "source_authority_not_authoritative"
    if not isinstance(certificate, dict) or certificate.get("authoritative") is not True:
        return False, "measured_source_output_authority_missing"
    required_hashes = (
        "source_sha256",
        "source_shape_sha256",
        "output_shape_sha256",
        "feature_sha256",
        "patch_sha256",
        "physical_group_sha256",
        "provenance_sha256",
    )
    if any(not _sha256(certificate.get(field)) for field in required_hashes):
        return False, "measured_source_output_authority_incomplete"
    if certificate.get("source_sha256") != source.get("sha256"):
        return False, "measured_source_output_source_binding_mismatch"
    kind = (
        case.get("strict_topology", {}).get("kind", "volume")
        if isinstance(case.get("strict_topology"), dict)
        else "volume"
    )
    shape_preserved = certificate.get("shape_preserved")
    if shape_preserved is None:
        shape_preserved = certificate.get("source_vertices_preserved")
    if shape_preserved is not True:
        return False, "measured_source_output_shape_preservation_incomplete"
    if kind == "surface":
        required_flags = (
            "feature_preserved",
            "patch_preserved",
            "physical_groups_preserved",
            "component_bijection",
            "provenance_complete",
        )
        if any(certificate.get(field) is not True for field in required_flags):
            return False, "measured_surface_source_output_preservation_incomplete"
        if not (
            certificate.get("source_face_provenance") is True
            or certificate.get("source_faces_preserved") is True
        ):
            return False, "measured_surface_face_provenance_incomplete"
        return True, ""
    engine = str(case.get("engine", ""))
    if engine in {"hex", "poly"}:
        # Curved boundary products may approximate source points; their
        # measured shape/boundary binding is authoritative instead of point
        # identity. All provenance and label flags remain mandatory.
        required_flags = (
            "source_faces_preserved",
            "feature_preserved",
            "patch_preserved",
            "physical_groups_preserved",
            "component_bijection",
            "provenance_complete",
        )
    else:
        required_flags = (
            "source_vertices_preserved",
            "source_faces_preserved",
            "feature_preserved",
            "patch_preserved",
            "physical_groups_preserved",
            "component_bijection",
            "provenance_complete",
        )
    if any(certificate.get(field) is not True for field in required_flags):
        return False, "measured_source_output_preservation_incomplete"
    return True, ""


def _base_matrix_value(value: object) -> object:
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list):
        return value
    cases = [
        {key: field for key, field in case.items() if key != "source_output_authority"}
        if isinstance(case, dict)
        else case
        for case in value["cases"]
    ]
    return {key: field for key, field in value.items() if key != "cases"} | {"cases": cases}


def validate_native_release_authority_matrix(value: object) -> NativeReleaseAuthorityAudit:
    """Require the complete base matrix plus measured authority in every row."""
    matrix = validate_native_release_matrix(_base_matrix_value(value))
    if not matrix.valid:
        return NativeReleaseAuthorityAudit(False, "matrix_unverified", matrix)
    cases = value.get("cases") if isinstance(value, dict) else None
    if not isinstance(cases, list):
        return NativeReleaseAuthorityAudit(False, "matrix_cases_invalid", matrix)
    invalid: list[str] = []
    reasons: list[str] = []
    for case in cases:
        case_id = case.get("id") if isinstance(case, dict) else "<malformed>"
        valid, reason = _authority_valid(case)
        if not valid:
            invalid.append(str(case_id))
            reasons.append(f"{case_id}:{reason}")
    if invalid:
        return NativeReleaseAuthorityAudit(
            False,
            "authority_unverified",
            matrix,
            tuple(sorted(invalid)),
            tuple(sorted(reasons)),
        )
    return NativeReleaseAuthorityAudit(True, "measured_authority_complete", matrix)


__all__ = ["NativeReleaseAuthorityAudit", "validate_native_release_authority_matrix"]
