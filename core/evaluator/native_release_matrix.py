"""Fail-closed release corpus and authority contract for native engines.

This contract is evidence-only.  It does not generate a mesh or promote a
route.  Its purpose is to make a cube-only result, a sidecar-only result, or a
report with missing source/feature/BL bindings mechanically ineligible for a
native release claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

RELEASE_MATRIX_SCHEMA: Final = "autotessell/native-release-matrix/v1"
REQUIRED_RELEASE_CASES: Final[frozenset[str]] = frozenset(
    {
        "native-tet-cube",
        "native-tet-sphere",
        "native-tet-naca",
        "native-tet-complex",
        "native-hex-cube",
        "native-hex-sphere",
        "native-hex-naca",
        "native-hex-gear",
        "native-poly-cube",
        "native-poly-sphere",
        "native-poly-naca",
        "native-poly-gear",
        "native-tri-cube",
        "native-tri-sphere",
        "native-tri-naca",
        "native-tri-cad",
        "strict-quad-cube",
        "strict-quad-complex",
        "tri-quad-cube",
        "tri-quad-complex",
    }
)
_ZERO_FIELDS: Final[tuple[str, ...]] = (
    "n_duplicate_faces",
    "n_nonmanifold_faces",
    "n_nonmanifold_cell_edges",
    "n_open_cell_edges",
    "n_inverted_cells",
)


@dataclass(frozen=True, slots=True)
class NativeReleaseMatrixAudit:
    """Machine-readable result of the release matrix contract."""

    valid: bool
    status: str
    missing_cases: tuple[str, ...] = ()
    extra_cases: tuple[str, ...] = ()
    invalid_cases: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "status": self.status,
            "missing_cases": list(self.missing_cases),
            "extra_cases": list(self.extra_cases),
            "invalid_cases": list(self.invalid_cases),
            "reasons": list(self.reasons),
            "required_case_count": len(REQUIRED_RELEASE_CASES),
        }


def _sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _strict_topology_valid(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("valid") is not True or value.get("status") != "measured":
        return False
    if not value.get("boundary_surface_valid") is True:
        return False
    if not _sha256(value.get("artifact_sha256")):
        return False
    kind = value.get("kind", "volume")
    if kind == "surface":
        surface_zero_fields = (
            "n_duplicate_faces",
            "n_nonmanifold_edges",
            "n_open_edges",
            "n_degenerate_faces",
            "n_inverted_faces",
        )
        return (
            value.get("surface_topology_valid") is True
            and all(value.get(field) == 0 for field in surface_zero_fields)
        )
    if kind != "volume":
        return False
    return all(value.get(field) == 0 for field in _ZERO_FIELDS)


def _case_valid(case: object) -> tuple[bool, str]:
    if not isinstance(case, dict):
        return False, "case_not_object"
    required = {
        "id",
        "engine",
        "fixture",
        "route",
        "source_authority",
        "strict_topology",
        "surface",
        "features",
        "boundary_layer",
        "repeatability",
    }
    if set(case) != required:
        return False, "case_fields_incomplete"
    authority = case["source_authority"]
    if not isinstance(authority, dict):
        return False, "source_authority_missing"
    if authority.get("authoritative") is not True or not _sha256(authority.get("sha256")):
        return False, "source_authority_not_authoritative"
    topology = case["strict_topology"]
    if not _strict_topology_valid(topology):
        return False, "strict_topology_not_zero_or_unverified"
    artifact_sha256 = topology["artifact_sha256"]
    surface = case["surface"]
    if not isinstance(surface, dict) or surface.get("valid") is not True:
        return False, "surface_validity_missing"
    if surface.get("source_sha256") != authority["sha256"]:
        return False, "surface_source_binding_mismatch"
    if surface.get("output_sha256") != artifact_sha256:
        return False, "surface_output_binding_mismatch"
    features = case["features"]
    feature_fields = (
        "authoritative",
        "critical_missing",
        "physical_groups_authoritative",
        "patch_mapping_complete",
        "provenance_complete",
        "component_bijection",
    )
    if not isinstance(features, dict) or any(
        features.get(field) != (0 if field == "critical_missing" else True)
        for field in feature_fields
    ):
        return False, "feature_or_provenance_binding_incomplete"
    boundary_layer = case["boundary_layer"]
    if not isinstance(boundary_layer, dict):
        return False, "boundary_layer_evidence_missing"
    layers = boundary_layer.get("layers")
    if isinstance(layers, bool) or not isinstance(layers, int) or layers < 0:
        return False, "boundary_layer_count_invalid"
    if layers > 0 and not (
        isinstance(boundary_layer.get("positive_first_layer_height"), (int, float))
        and boundary_layer["positive_first_layer_height"] > 0.0
        and isinstance(boundary_layer.get("positive_cell_count"), int)
        and boundary_layer["positive_cell_count"] > 0
    ):
        return False, "positive_boundary_layer_not_measured"
    repeatability = case["repeatability"]
    if not isinstance(repeatability, dict):
        return False, "repeatability_missing"
    run_count = repeatability.get("run_count")
    if (
        isinstance(run_count, bool)
        or not isinstance(run_count, int)
        or run_count < 3
        or repeatability.get("byte_identical") is not True
        or repeatability.get("independent_route") is not True
        or repeatability.get("artifact_sha256") != [artifact_sha256] * run_count
    ):
        return False, "repeatability_or_route_independence_incomplete"
    return True, ""


def validate_native_release_matrix(value: object) -> NativeReleaseMatrixAudit:
    """Validate the complete multi-engine release evidence matrix."""
    if not isinstance(value, dict) or value.get("schema") != RELEASE_MATRIX_SCHEMA:
        return NativeReleaseMatrixAudit(False, "invalid_schema", reasons=("schema",))
    cases = value.get("cases")
    if not isinstance(cases, list):
        return NativeReleaseMatrixAudit(False, "invalid_cases", reasons=("cases",))
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(set(ids)):
        return NativeReleaseMatrixAudit(False, "duplicate_case_id", reasons=("case_id",))
    observed = {case_id for case_id in ids if isinstance(case_id, str)}
    missing = tuple(sorted(REQUIRED_RELEASE_CASES - observed))
    extra = tuple(sorted(observed - REQUIRED_RELEASE_CASES))
    invalid: list[str] = []
    reasons: list[str] = []
    for case in cases:
        case_id = case.get("id") if isinstance(case, dict) else "<malformed>"
        valid, reason = _case_valid(case)
        if not valid:
            invalid.append(str(case_id))
            reasons.append(f"{case_id}:{reason}")
    valid = not missing and not extra and not invalid
    return NativeReleaseMatrixAudit(
        valid=valid,
        status="measured_complete" if valid else "unverified",
        missing_cases=missing,
        extra_cases=extra,
        invalid_cases=tuple(sorted(invalid)),
        reasons=tuple(sorted(reasons)),
    )


__all__ = [
    "RELEASE_MATRIX_SCHEMA",
    "REQUIRED_RELEASE_CASES",
    "NativeReleaseMatrixAudit",
    "validate_native_release_matrix",
]
