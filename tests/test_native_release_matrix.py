"""L0 acceptance/rejection contracts for the native release matrix."""

from __future__ import annotations

from core.evaluator.native_release_matrix import (
    RELEASE_MATRIX_SCHEMA,
    REQUIRED_RELEASE_CASES,
    validate_native_release_matrix,
)


def _case(case_id: str) -> dict[str, object]:
    source = "a" * 64
    output = "b" * 64
    return {
        "id": case_id,
        "engine": case_id.split("-")[1],
        "fixture": case_id.rsplit("-", 1)[-1],
        "route": "native-independent-release-route",
        "source_authority": {"authoritative": True, "sha256": source},
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


def test_cube_only_matrix_is_rejected() -> None:
    value = {"schema": RELEASE_MATRIX_SCHEMA, "cases": [_case("native-tet-cube")]}

    report = validate_native_release_matrix(value)

    assert not report.valid
    assert len(report.missing_cases) == len(REQUIRED_RELEASE_CASES) - 1
    assert report.status == "unverified"


def test_complete_matrix_accepts_zero_topology_and_positive_bl_evidence() -> None:
    value = {
        "schema": RELEASE_MATRIX_SCHEMA,
        "cases": [_case(case_id) for case_id in sorted(REQUIRED_RELEASE_CASES)],
    }

    report = validate_native_release_matrix(value)

    assert report.valid
    assert report.status == "measured_complete"
    assert report.reasons == ()


def test_incomplete_topology_is_rejected_even_with_repeatability() -> None:
    value = {
        "schema": RELEASE_MATRIX_SCHEMA,
        "cases": [_case(case_id) for case_id in sorted(REQUIRED_RELEASE_CASES)],
    }
    next(case for case in value["cases"] if case["id"] == "native-hex-cube")["strict_topology"]["n_inverted_cells"] = 1

    report = validate_native_release_matrix(value)

    assert not report.valid
    assert report.invalid_cases == ("native-hex-cube",)
    assert "strict_topology_not_zero_or_unverified" in report.reasons[0]
