"""Actual-route admission must fail closed until all witnesses are measured."""
from __future__ import annotations

from core.evaluator.native_route_admission import admit_native_route_candidate


def _ready() -> dict[str, object]:
    return {"id": "cube", "ready": True, "reasons": []}


def _quality(*, layers: int) -> dict[str, object]:
    return {
        "accepted": True,
        "boundary_layer": {
            "requested_layers": layers,
            "actual_layers": layers,
            "first_layer_height": 0.01 if layers else 0.0,
        },
    }


def test_tet_bl0_is_not_release_without_gate4_and_quality() -> None:
    result = admit_native_route_candidate(
        "native-tet",
        boundary_layers=0,
        source_kind="cad",
        corpus_case=_ready(),
    )

    assert result["status"] == "candidate_refused"
    assert result["publication_eligible"] is False
    assert "gate4_witness_missing" in result["reasons"]
    assert "quality_witness_missing" in result["reasons"]


def test_tet_positive_bl_requires_positive_thickness_and_exact_layer_count() -> None:
    result = admit_native_route_candidate(
        "native-tet",
        boundary_layers=1,
        source_kind="stl",
        corpus_case=_ready(),
        gate4={"accepted": True},
        quality_witness=_quality(layers=0),
    )

    assert result["status"] == "candidate_refused"
    assert "positive_boundary_layer_count_mismatch" in result["reasons"]


def test_ready_tet_bl1_is_admitted_only_with_all_witnesses() -> None:
    result = admit_native_route_candidate(
        "native-tet",
        boundary_layers=1,
        source_kind="cad",
        corpus_case=_ready(),
        gate4={"accepted": True},
        quality_witness=_quality(layers=1),
    )

    assert result["status"] == "candidate_admitted"
    assert result["publication_eligible"] is True
    assert result["release_claim_eligible"] is True


def test_unsupported_positive_surface_route_is_refused_before_witness_checks() -> None:
    result = admit_native_route_candidate(
        "native-tri",
        boundary_layers=1,
        source_kind="stl",
        corpus_case=_ready(),
    )

    assert result["status"] == "route_refused"
    assert result["reasons"] == ["boundary_layers_unsupported_by_route"]
