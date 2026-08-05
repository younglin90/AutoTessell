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


def _native_artifact_digest_valid(certificate: dict) -> tuple[bool, str]:
    """Require a native recomputation witness for the published artifact tree."""
    witness = certificate.get("native_artifact_digest")
    if not isinstance(witness, dict):
        return False, "native_artifact_digest_missing"
    if (
        witness.get("valid") is not True
        or witness.get("status") != "native_recomputed"
        or witness.get("algorithm") != "SHA-256"
        or witness.get("implementation") != "native_artifact_fingerprint"
        or witness.get("recomputed") is not True
        or not _sha256(witness.get("tree_sha256"))
    ):
        return False, "native_artifact_digest_unverified"
    entry_count = witness.get("entry_count")
    entry_counts = witness.get("entry_counts")
    repeats = witness.get("witness_repeats")
    if (
        isinstance(entry_count, bool)
        or not isinstance(entry_count, int)
        or entry_count < 1
        or not isinstance(entry_counts, list)
        or any(isinstance(item, bool) or not isinstance(item, int) for item in entry_counts)
        or entry_counts != [entry_count] * 3
        or not isinstance(repeats, list)
        or repeats != [witness.get("tree_sha256")] * 3
    ):
        return False, "native_artifact_digest_repeatability_incomplete"
    if any(not _sha256(item) for item in repeats):
        return False, "native_artifact_digest_malformed"
    root_relative = witness.get("root_relative")
    if not isinstance(root_relative, str) or not root_relative:
        return False, "native_artifact_digest_root_missing"
    return True, ""


def _quality_witness_valid(
    case: dict,
    source: dict,
    certificate: dict,
    *,
    required: bool = False,
) -> tuple[bool, str]:
    witness = certificate.get("quality_witness")
    if witness is None:
        if required:
            return False, "quality_witness_missing"
        return True, ""
    if not isinstance(witness, dict) or witness.get("accepted") is not True:
        return False, "quality_witness_unverified"
    if witness.get("source_sha256") != source.get("sha256"):
        return False, "quality_witness_source_binding_mismatch"
    output_sha = certificate.get("output_sha256") or certificate.get("output_shape_sha256")
    if witness.get("output_sha256") != output_sha:
        return False, "quality_witness_output_binding_mismatch"
    repeats = witness.get("witness_repeats")
    digest = witness.get("witness_sha256")
    if not _sha256(digest) or not isinstance(repeats, list) or len(repeats) != 3 or repeats != [digest] * 3:
        return False, "quality_witness_repeatability_incomplete"
    quality = witness.get("quality")
    if not isinstance(quality, dict):
        return False, "quality_witness_metrics_missing"
    for name, limit in (("internal_non_orthogonality", 75.0), ("release_skew", 0.5)):
        report = quality.get(name)
        if not isinstance(report, dict):
            return False, f"quality_witness_{name}_missing"
        value = report.get("max")
        if value is not None and (not isinstance(value, (int, float)) or value > limit):
            return False, f"quality_witness_{name}_gate_failed"
        p95 = report.get("p95")
        if p95 is not None and (not isinstance(p95, (int, float)) or p95 > (65.0 if name == "internal_non_orthogonality" else 0.25)):
            return False, f"quality_witness_{name}_p95_gate_failed"
    if witness.get("volume_quality", {}).get("positive_geometry") is not True:
        return False, "quality_witness_positive_geometry_missing"
    return True, ""


def _poly_quality_relocation_valid(certificate: dict) -> tuple[bool, str]:
    """Keep an accepted-but-bad Poly relocation out of production authority."""
    report = certificate.get("quality_relocation")
    if report is None:
        return True, ""
    if not isinstance(report, dict) or report.get("accepted") is not True:
        return False, "poly_quality_relocation_unverified"
    topology = report.get("strict_topology")
    if not isinstance(topology, dict) or topology.get("valid") is not True:
        return False, "poly_quality_relocation_topology_gate_failed"
    quality = report.get("quality_after")
    if not isinstance(quality, dict):
        return False, "poly_quality_relocation_metrics_missing"
    limits = (
        ("internal_non_orthogonality", 65.0),
        ("release_skew", 4.0),
        ("aspect_ratio", 100.0),
    )
    for name, limit in limits:
        metric = quality.get(name)
        value = metric.get("max") if isinstance(metric, dict) else None
        if not isinstance(value, (int, float)):
            return False, f"poly_quality_relocation_{name}_missing"
        if value > limit:
            return False, f"poly_quality_relocation_{name}_gate_failed"
    return True, ""


def _authority_valid(
    case: object,
    *,
    require_quality_witness: bool = False,
) -> tuple[bool, str]:
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
    relocation_valid, relocation_reason = _poly_quality_relocation_valid(certificate)
    if not relocation_valid:
        return False, relocation_reason
    native_valid, native_reason = _native_artifact_digest_valid(certificate)
    if not native_valid:
        return False, native_reason
    if certificate.get("source_sha256") != source.get("sha256"):
        return False, "measured_source_output_source_binding_mismatch"
    kind = (
        case.get("strict_topology", {}).get("kind", "volume")
        if isinstance(case.get("strict_topology"), dict)
        else "volume"
    )
    quality_valid, quality_reason = _quality_witness_valid(
        case, source, certificate, required=require_quality_witness and kind != "surface"
    )
    if not quality_valid:
        return False, quality_reason
    shape_preserved = certificate.get("shape_preserved")
    if shape_preserved is None:
        shape_preserved = certificate.get("source_vertices_preserved")
    if shape_preserved is not True:
        return False, "measured_source_output_shape_preservation_incomplete"
    if kind == "surface":
        surface_quality_valid, surface_quality_reason = _surface_quality_valid(case, source, certificate)
        if not surface_quality_valid:
            return False, surface_quality_reason
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


def validate_native_release_authority_matrix(
    value: object,
    *,
    require_quality_witness: bool = False,
) -> NativeReleaseAuthorityAudit:
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
        valid, reason = _authority_valid(
            case, require_quality_witness=require_quality_witness
        )
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


def _surface_quality_valid(case: object, source: dict, certificate: dict) -> tuple[bool, str]:
    quality = certificate.get("surface_quality")
    if not isinstance(quality, dict) or quality.get("accepted") is not True:
        return False, "surface_quality_witness_missing"
    if quality.get("source_sha256") != source.get("sha256"):
        return False, "surface_quality_source_binding_mismatch"
    topology = case.get("strict_topology") if isinstance(case, dict) else None
    artifact = topology.get("artifact_sha256") if isinstance(topology, dict) else None
    if quality.get("output_sha256") != artifact:
        return False, "surface_quality_output_binding_mismatch"
    witness_digest = quality.get("witness_sha256")
    if not _sha256(witness_digest):
        return False, "surface_quality_witness_digest_missing"
    repeats = quality.get("witness_repeats")
    if (
        not isinstance(repeats, list)
        or len(repeats) != 3
        or any(not _sha256(item) for item in repeats)
        or repeats != [witness_digest] * 3
    ):
        return False, "surface_quality_repeatability_incomplete"

    topology_witness = quality.get("topology")
    if not isinstance(topology_witness, dict):
        return False, "surface_quality_topology_missing"
    if (
        topology_witness.get("closed_manifold") is not True
        or topology_witness.get("boundary_edges") != 0
        or topology_witness.get("nonmanifold_edges") != 0
        or topology_witness.get("duplicate_faces") != 0
    ):
        return False, "surface_quality_topology_gate_failed"

    metrics = quality.get("quality")
    if not isinstance(metrics, dict):
        return False, "surface_quality_metrics_missing"

    def measured(name: str) -> dict | None:
        value = metrics.get(name)
        if not isinstance(value, dict):
            return None
        return value if value.get("status") == "measured" else None

    tri_ratio = measured("tri_mean_ratio")
    if tri_ratio is not None:
        value = tri_ratio.get("min")
        if not isinstance(value, (int, float)) or value < 0.05:
            return False, "surface_quality_triangle_shape_gate_failed"
    tri_min_angle = measured("tri_min_angle")
    if tri_min_angle is not None:
        value = tri_min_angle.get("min")
        if not isinstance(value, (int, float)) or value < 10.0:
            return False, "surface_quality_triangle_angle_gate_failed"
    tri_max_angle = measured("tri_max_angle")
    if tri_max_angle is not None:
        value = tri_max_angle.get("max")
        if not isinstance(value, (int, float)) or value > 150.0:
            return False, "surface_quality_triangle_angle_gate_failed"

    quad_jacobian = measured("quad_scaled_jacobian")
    if quad_jacobian is not None:
        value = quad_jacobian.get("min")
        if not isinstance(value, (int, float)) or value < 0.5:
            return False, "surface_quality_quad_jacobian_gate_failed"
    quad_aspect = measured("quad_aspect_ratio")
    if quad_aspect is not None:
        value = quad_aspect.get("max")
        if not isinstance(value, (int, float)) or value > 10.0:
            return False, "surface_quality_quad_aspect_gate_failed"
    quad_min_angle = measured("quad_min_angle")
    if quad_min_angle is not None:
        value = quad_min_angle.get("min")
        if not isinstance(value, (int, float)) or value < 45.0:
            return False, "surface_quality_quad_angle_gate_failed"
    quad_max_angle = measured("quad_max_angle")
    if quad_max_angle is not None:
        value = quad_max_angle.get("max")
        if not isinstance(value, (int, float)) or value > 135.0:
            return False, "surface_quality_quad_angle_gate_failed"
    quad_warpage = measured("quad_warpage")
    if quad_warpage is not None:
        value = quad_warpage.get("max")
        if not isinstance(value, (int, float)) or value > 0.1:
            return False, "surface_quality_quad_warpage_gate_failed"

    angle = measured("surface_angle_deviation")
    if angle is not None:
        value = angle.get("max")
        if not isinstance(value, (int, float)) or value > 90.0:
            return False, "surface_quality_normal_orientation_gate_failed"

    lineage = quality.get("source_face_lineage")
    patches = quality.get("patch_ids")
    groups = quality.get("physical_groups")
    features = quality.get("feature_ids")
    if not all(isinstance(value, list) and value for value in (lineage, patches, groups, features)):
        return False, "surface_quality_semantic_lineage_missing"
    face_count = int(quality.get("n_triangles", 0)) + int(quality.get("n_quads", 0))
    if not (
        len(lineage) == face_count
        and len(patches) == face_count
        and len(groups) == face_count
        and len(features) == face_count
    ):
        return False, "surface_quality_semantic_lineage_incomplete"

    boundary_layer = quality.get("boundary_layer")
    if not isinstance(boundary_layer, dict):
        return False, "surface_quality_boundary_layer_missing"
    requested = boundary_layer.get("requested_layers")
    actual = boundary_layer.get("actual_layers")
    if (
        isinstance(requested, bool)
        or isinstance(actual, bool)
        or not isinstance(requested, int)
        or not isinstance(actual, int)
        or requested < 0
        or actual != requested
    ):
        return False, "surface_quality_boundary_layer_contract_invalid"
    if requested == 0:
        if boundary_layer != {"requested_layers": 0, "actual_layers": 0}:
            return False, "surface_quality_bl0_identity_binding_failed"
        return True, ""

    if boundary_layer.get("positive_thickness") is not True:
        return False, "surface_quality_positive_thickness_missing"
    wall_quality = quality.get("wall_edge_quality")
    if not isinstance(wall_quality, dict) or wall_quality.get("accepted") is not True:
        return False, "surface_quality_positive_bl_unverified"
    if wall_quality.get("actual_layers") != requested:
        return False, "surface_quality_positive_layer_count_mismatch"
    return True, ""



def validate_native_surface_quality_binding(case: object) -> dict[str, object]:
    """Validate one surface row's producer witness binding independently."""
    if not isinstance(case, dict):
        return {"valid": False, "reason": "case_not_object"}
    source = case.get("source_authority")
    certificate = case.get("source_output_authority")
    if not isinstance(source, dict) or not isinstance(certificate, dict):
        return {"valid": False, "reason": "surface_authority_fields_missing"}
    valid, reason = _surface_quality_valid(case, source, certificate)
    return {"valid": valid, "reason": reason}
