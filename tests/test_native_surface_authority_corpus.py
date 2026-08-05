from __future__ import annotations

from core.evaluator.native_surface_authority_corpus import (
    validate_surface_authority_corpus,
)


def _sidecar(source: bytes = b"surface-source", *, kind: str = "stl") -> dict:
    return {
        "schema": "NativeSurfaceAuthoritySidecar/v1",
        "source_kind": kind,
        "source_sha256": __import__("hashlib").sha256(source).hexdigest(),
        "provenance": "authored-sidecar",
        "entity_count": 2,
        "entities": [
            {
                "entity_id": 0,
                "patch": "wall",
                "feature": "smooth",
                "physical_group": "fluid_wall",
                "component": "main",
            },
            {
                "entity_id": 1,
                "patch": "outer",
                "feature": "smooth",
                "physical_group": "fluid_outer",
                "component": "main",
            },
        ],
        "directed_wall_curves": [
            {
                "curve_id": "wall-0",
                "owner_face": 0,
                "directed_edges": [[10, 11, 0]],
                "patch": "wall",
                "feature": "smooth",
                "physical_group": "fluid_wall",
                "component": "main",
            }
        ],
        "physical_group_map": {"fluid_wall": 1, "fluid_outer": 2},
        **({"cad_entity_map": {"face-0": 0, "face-1": 1}} if kind == "step" else {}),
    }


def test_source_authored_sidecar_seals_deterministically():
    source = b"surface-source"
    first = validate_surface_authority_corpus(source, "stl", _sidecar(source=source), 2)
    second = validate_surface_authority_corpus(source, "stl", _sidecar(source=source), 2)
    assert first == second
    assert first["accepted"] is True
    assert first["eligible_for_surface_bl"] is True
    assert first["wall_curve_count"] == 1
    assert first["runtime_route"] == "private_default_off"
    assert first["route_calls"] == 0


def test_missing_or_invented_authority_refuses_without_route_call():
    source = b"surface-source"
    missing_curve = _sidecar(source=source)
    missing_curve["directed_wall_curves"] = []
    refused = validate_surface_authority_corpus(source, "stl", missing_curve, 2)
    assert refused["accepted"] is False
    assert refused["reason"] == "directed_wall_curve_missing"
    assert refused["eligible_for_surface_bl"] is False
    assert refused["candidate_discarded"] is True

    mismatch = _sidecar(source=source)
    mismatch["source_sha256"] = "not-the-source"
    refused = validate_surface_authority_corpus(source, "stl", mismatch, 2)
    assert refused["accepted"] is False
    assert refused["reason"] == "source_digest_or_kind_mismatch"
    assert refused["route_calls"] == 0


def test_cad_requires_explicit_brep_entity_map_and_rejects_reversed_edge():
    source = b"cad-source"
    sidecar = _sidecar(source=source, kind="step")
    sidecar.pop("cad_entity_map")
    refused = validate_surface_authority_corpus(source, "step", sidecar, 2)
    assert refused["accepted"] is False
    assert refused["reason"] == "cad_entity_map_missing"

    sidecar = _sidecar(source=source)
    sidecar["directed_wall_curves"].append(
        {
            "curve_id": "wall-reverse",
            "owner_face": 0,
            "directed_edges": [[11, 10, 0]],
            "patch": "wall",
            "feature": "smooth",
            "physical_group": "fluid_wall",
            "component": "main",
        }
    )
    refused = validate_surface_authority_corpus(source, "stl", sidecar, 2)
    assert refused["accepted"] is False
    assert refused["reason"] == "wall_curve_duplicate_or_reversed_edge"
