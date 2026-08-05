"""L0 contract tests for the surface native-plan atomic adapter."""

from __future__ import annotations

import copy

from core.layers.native_bl_atomic_certificate import SourceAuthority
from core.layers.surface_bl_atomic_adapter import certify_and_persist_surface_plan


def _inputs() -> tuple[dict[str, object], SourceAuthority, dict[str, object], dict[str, object], dict[str, object]]:
    source = {"vertices": [[0, 0, 0], [1, 0, 0]], "faces": ["wall-face"]}
    authority = SourceAuthority(
        topology="surface-topo", source="surface-source", feature="ridge-lock",
        patch="wall", physical_group="wall-group", provenance="surface-ledger",
        wall_edges=("17",),
    )
    plan = {
        "accepted": True, "status": "candidate_plan_ready", "source_immutable": True,
        "requested_layers": 1, "actual_layers": 1,
        "generated_vertices": [{"id": 0, "x": 0.0, "y": 0.0, "z": 0.2}, {"id": 1, "x": 1.0, "y": 0.0, "z": 0.2}],
        "generated_faces": [{"source_a": 0, "source_b": 1}, {"source_a": 1, "source_b": 0}],
        "provenance": [{"source_wall_edge": "17", "layer": 1, "candidate_ordinal": 0}],
    }
    topology = {"invalid": 0, "inverted": 0, "duplicate": 0, "non_manifold": 0, "self_intersecting": 0}
    quality = {"min_jacobian": 0.1, "min_area": 0.2, "max_non_orthogonality": 25.0, "max_skewness": 0.2, "metric_distortion": 1.1, "metric_aspect_ratio": 1.5}
    return source, authority, plan, topology, quality


def _authority_evidence(source: dict[str, object], authority: SourceAuthority) -> dict[str, object]:
    from core.layers.surface_bl_atomic_adapter import _hash
    from dataclasses import asdict

    return {"source_sha256": _hash(source), "authority_sha256": _hash(asdict(authority)), "wall_edges": ["17"]}


def test_bl0_bypasses_native_plan_and_is_byte_identical() -> None:
    source, authority, _, topology, quality = _inputs()
    destination = copy.deepcopy(source)
    certificate = certify_and_persist_surface_plan(
        source, authority, None, destination, requested_layers=0, first_height=0.0,
        growth_ratio=1.0, authority_evidence=None, topology_evidence=topology,
        quality_evidence=quality,
    )
    assert certificate.accepted
    assert destination == source


def test_bl1_adapter_commits_exact_lineage_and_is_repeatable() -> None:
    source, authority, plan, topology, quality = _inputs()
    evidence = _authority_evidence(source, authority)
    outputs = []
    for _ in range(2):
        destination = copy.deepcopy(source)
        certificate = certify_and_persist_surface_plan(
            source, authority, plan, destination, requested_layers=1, first_height=0.2,
            growth_ratio=1.0, authority_evidence=evidence, topology_evidence=topology,
            quality_evidence=quality,
        )
        assert certificate.accepted
        assert certificate.actual_layers == 1
        outputs.append(certificate.serialized())
    assert outputs[0] == outputs[1]


def test_missing_gate_and_persistence_failure_never_mutate_destination() -> None:
    source, authority, plan, topology, quality = _inputs()
    destination = copy.deepcopy(source)
    missing = certify_and_persist_surface_plan(
        source, authority, plan, destination, requested_layers=1, first_height=0.2,
        growth_ratio=1.0, authority_evidence=None, topology_evidence=topology,
        quality_evidence=quality,
    )
    assert not missing.accepted and missing.reasons == ("missing_authority_evidence",)
    assert destination == source

    def fail(_: object) -> None:
        raise RuntimeError("injected")

    failed = certify_and_persist_surface_plan(
        source, authority, plan, destination, requested_layers=1, first_height=0.2,
        growth_ratio=1.0, authority_evidence=_authority_evidence(source, authority),
        topology_evidence=topology, quality_evidence=quality, persist=fail,
    )
    assert not failed.accepted and failed.rolled_back
    assert destination == source
