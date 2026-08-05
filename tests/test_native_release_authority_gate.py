"""Measured authority is a hard gate above the base release matrix."""

from __future__ import annotations

from core.evaluator.native_release_authority_gate import (
    validate_native_release_authority_matrix,
)
from core.evaluator.native_release_matrix import RELEASE_MATRIX_SCHEMA, REQUIRED_RELEASE_CASES


def _case(case_id: str, *, authority: bool) -> dict[str, object]:
    source = "a" * 64
    output = "b" * 64
    certificate = {
        "authoritative": authority,
        "source_sha256": source,
        "source_shape_sha256": "c" * 64,
        "output_shape_sha256": "d" * 64,
        "feature_sha256": "e" * 64,
        "patch_sha256": "f" * 64,
        "physical_group_sha256": "1" * 64,
        "provenance_sha256": "2" * 64,
        "source_vertices_preserved": True,
        "source_faces_preserved": True,
        "feature_preserved": True,
        "patch_preserved": True,
        "physical_groups_preserved": True,
        "component_bijection": True,
        "provenance_complete": True,
        "native_artifact_digest": {
            "valid": True,
            "status": "native_recomputed",
            "algorithm": "SHA-256",
            "implementation": "native_artifact_fingerprint",
            "root_relative": "constant/polyMesh",
            "tree_sha256": "3" * 64,
            "witness_repeats": ["3" * 64] * 3,
            "entry_count": 4,
            "entry_counts": [4] * 3,
            "recomputed": True,
        },
    }
    return {
        "id": case_id,
        "engine": case_id.split("-")[1],
        "fixture": case_id.rsplit("-", 1)[-1],
        "route": "native-independent-release-route",
        "source_authority": {"authoritative": True, "sha256": source},
        "source_output_authority": certificate,
        "strict_topology": {
            "status": "measured",
            "valid": True,
            "artifact_sha256": output,
            "boundary_surface_valid": True,
            "n_duplicate_faces": 0,
            "n_nonmanifold_faces": 0,
            "n_nonmanifold_cell_edges": 0,
            "n_open_cell_edges": 0,
            "n_inverted_cells": 0,
        },
        "surface": {"valid": True, "source_sha256": source, "output_sha256": output},
        "features": {
            "authoritative": True,
            "critical_missing": 0,
            "physical_groups_authoritative": True,
            "patch_mapping_complete": True,
            "provenance_complete": True,
            "component_bijection": True,
        },
        "boundary_layer": {
            "layers": 1,
            "positive_first_layer_height": 0.01,
            "positive_cell_count": 8,
        },
        "repeatability": {
            "run_count": 3,
            "byte_identical": True,
            "independent_route": True,
            "artifact_sha256": [output, output, output],
        },
    }


def _matrix(*, authority: bool) -> dict[str, object]:
    return {
        "schema": RELEASE_MATRIX_SCHEMA,
        "cases": [_case(case_id, authority=authority) for case_id in sorted(REQUIRED_RELEASE_CASES)],  # noqa: E501
    }


def test_complete_base_matrix_without_measured_authority_is_rejected() -> None:
    report = validate_native_release_authority_matrix(_matrix(authority=False))

    assert report.valid is False
    assert report.status == "authority_unverified"
    assert len(report.invalid_cases) == len(REQUIRED_RELEASE_CASES)
    assert report.reasons[0].endswith(":measured_source_output_authority_missing")


def test_complete_measured_authority_matrix_is_eligible() -> None:
    report = validate_native_release_authority_matrix(_matrix(authority=True))

    assert report.valid is True
    assert report.status == "measured_authority_complete"
    assert report.invalid_cases == ()
    assert report.reasons == ()

def test_strict_release_mode_requires_volume_quality_witness() -> None:
    report = validate_native_release_authority_matrix(
        _matrix(authority=True), require_quality_witness=True
    )

    assert report.valid is False
    assert report.status == "authority_unverified"
    assert any(reason.endswith(":quality_witness_missing") for reason in report.reasons)


def test_surface_matrix_accepts_shape_and_face_provenance_contract() -> None:
    value = _matrix(authority=True)
    case = value["cases"][0]
    case["strict_topology"] = {
        "kind": "surface",
        "status": "measured",
        "valid": True,
        "artifact_sha256": "b" * 64,
        "boundary_surface_valid": True,
        "surface_topology_valid": True,
        "n_duplicate_faces": 0,
        "n_nonmanifold_edges": 0,
        "n_open_edges": 0,
        "n_degenerate_faces": 0,
        "n_inverted_faces": 0,
    }
    certificate = case["source_output_authority"]
    certificate["shape_preserved"] = True
    certificate["source_vertices_preserved"] = False
    certificate["source_faces_preserved"] = False
    certificate["source_face_provenance"] = True
    case["boundary_layer"]["layers"] = 0
    certificate["surface_quality"] = {
        "accepted": True,
        "source_sha256": "a" * 64,
        "output_sha256": "b" * 64,
        "witness_sha256": "c" * 64,
        "witness_repeats": ["c" * 64] * 3,
        "topology": {
            "closed_manifold": True,
            "boundary_edges": 0,
            "nonmanifold_edges": 0,
            "duplicate_faces": 0,
        },
        "quality": {},
        "n_triangles": 0,
        "n_quads": 1,
        "source_face_lineage": [0],
        "patch_ids": ["wall"],
        "physical_groups": ["fluid"],
        "feature_ids": [0],
        "boundary_layer": {"requested_layers": 0, "actual_layers": 0},
    }
    report = validate_native_release_authority_matrix(value)
    assert report.valid is True



def _quality_witness() -> dict[str, object]:
    return {
        "accepted": True,
        "source_sha256": "a" * 64,
        "output_sha256": "b" * 64,
        "witness_sha256": "c" * 64,
        "witness_repeats": ["c" * 64] * 3,
        "quality": {
            "internal_non_orthogonality": {"p95": 0.0, "max": 0.0},
            "release_skew": {"p95": 0.0, "max": 0.0},
        },
        "volume_quality": {"positive_geometry": True},
    }


def test_quality_witness_is_bound_into_authority_gate() -> None:
    value = _matrix(authority=True)
    case = value["cases"][0]
    certificate = case["source_output_authority"]
    certificate["output_sha256"] = "b" * 64
    certificate["quality_witness"] = _quality_witness()
    report = validate_native_release_authority_matrix(value)
    assert report.valid is True


def test_quality_witness_nonorthogonality_p95_blocks_authority() -> None:
    value = _matrix(authority=True)
    case = value["cases"][0]
    certificate = case["source_output_authority"]
    certificate["output_sha256"] = "b" * 64
    witness = _quality_witness()
    witness["quality"]["internal_non_orthogonality"]["p95"] = 65.0001
    certificate["quality_witness"] = witness
    report = validate_native_release_authority_matrix(value)
    assert report.valid is False
    assert report.status == "authority_unverified"
    assert report.reasons[0].endswith(":quality_witness_internal_non_orthogonality_p95_gate_failed")


def test_missing_native_digest_blocks_authority() -> None:
    value = _matrix(authority=True)
    del value["cases"][0]["source_output_authority"]["native_artifact_digest"]
    report = validate_native_release_authority_matrix(value)
    assert report.valid is False
    assert report.reasons[0].endswith(":native_artifact_digest_missing")


def test_nonrepeating_native_digest_blocks_authority() -> None:
    value = _matrix(authority=True)
    witness = value["cases"][0]["source_output_authority"]["native_artifact_digest"]
    witness["witness_repeats"][1] = "4" * 64
    report = validate_native_release_authority_matrix(value)
    assert report.valid is False
    assert report.reasons[0].endswith(":native_artifact_digest_repeatability_incomplete")
