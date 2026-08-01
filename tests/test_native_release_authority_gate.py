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
    report = validate_native_release_authority_matrix(value)
    assert report.valid is True
