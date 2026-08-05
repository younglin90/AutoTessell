"""Policy-bound wall-edge provenance must precede atomic BL acceptance."""

from __future__ import annotations

import copy

from core.layers.native_bl_atomic_certificate import SourceAuthority
from core.layers.surface_bl_atomic_adapter import _hash, certify_and_persist_surface_plan


def _case() -> tuple[dict[str, object], SourceAuthority, dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    source = {"vertices": [[0, 0, 0], [1, 0, 0]], "faces": ["wall-face"]}
    authority = SourceAuthority(
        topology="surface-topo", source="surface-source", feature="unclassified_boundary",
        patch="wall", physical_group="fluid_wall", provenance="surface-ledger",
        wall_edges=("edge:0",),
    )
    plan = {
        "accepted": True, "status": "candidate_plan_ready", "source_immutable": True,
        "requested_layers": 1, "actual_layers": 1,
        "generated_vertices": [{"id": 0, "x": 0.0, "y": 0.0, "z": 0.2}, {"id": 1, "x": 1.0, "y": 0.0, "z": 0.2}],
        "generated_faces": [{"source_a": 0, "source_b": 1}, {"source_a": 1, "source_b": 0}],
        "provenance": [{
            "source_wall_edge": "edge:0", "policy_edge_id": "edge:0", "source_face": 0,
            "side": "left", "layer": 1, "patch": "wall", "feature": "unclassified_boundary",
            "physical_group": "fluid_wall", "component": "synthetic", "candidate_ordinal": 0,
        }],
    }
    policy = {
        "status": "USER_DECLARED_PROVISIONAL_WALL_EDGE_POLICY", "selected_edge_ids": ["edge:0"],
        "selected_edge_count": 1, "source_sha256": _hash(source), "release_eligible": False,
    }
    topology = {"invalid": 0, "inverted": 0, "duplicate": 0, "non_manifold": 0, "self_intersecting": 0}
    quality = {"min_jacobian": 0.1, "min_area": 0.2, "max_non_orthogonality": 25.0, "max_skewness": 0.2, "metric_distortion": 1.1, "metric_aspect_ratio": 1.5}
    evidence = {"source_sha256": _hash(source), "authority_sha256": _hash({
        "topology": authority.topology, "source": authority.source, "feature": authority.feature,
        "patch": authority.patch, "physical_group": authority.physical_group, "provenance": authority.provenance,
        "wall_faces": authority.wall_faces, "wall_edges": authority.wall_edges, "ambiguous": authority.ambiguous,
        "already_layered": authority.already_layered,
    }), "wall_edges": ["edge:0"]}
    return source, authority, plan, policy, topology, quality, evidence


def test_complete_policy_bound_plan_reaches_atomic_certificate_repeatably() -> None:
    source, authority, plan, policy, topology, quality, evidence = _case()
    certificates = []
    for _ in range(2):
        destination = copy.deepcopy(source)
        certificate = certify_and_persist_surface_plan(
            source, authority, plan, destination, requested_layers=1, first_height=0.2,
            growth_ratio=1.0, authority_evidence=evidence, topology_evidence=topology,
            quality_evidence=quality, wall_edge_policy=policy,
        )
        assert certificate.accepted
        certificates.append(certificate.serialized())
    assert certificates[0] == certificates[1]


def test_policy_refusal_precedes_atomic_certificate_and_preserves_destination() -> None:
    source, authority, plan, policy, topology, quality, evidence = _case()
    destination = copy.deepcopy(source)
    plan["provenance"][0].pop("policy_edge_id")  # type: ignore[index]
    certificate = certify_and_persist_surface_plan(
        source, authority, plan, destination, requested_layers=1, first_height=0.2,
        growth_ratio=1.0, authority_evidence=evidence, topology_evidence=topology,
        quality_evidence=quality, wall_edge_policy=policy,
    )
    assert not certificate.accepted
    assert certificate.reasons == ("wall_edge_provenance:missing_policy_edge_identity_or_lineage",)
    assert destination == source


def test_policy_bound_plan_still_requires_quality_and_zero_topology() -> None:
    source, authority, plan, policy, topology, quality, evidence = _case()
    destination = copy.deepcopy(source)
    incomplete_quality = dict(quality)
    incomplete_quality.pop("max_skewness")
    certificate = certify_and_persist_surface_plan(
        source, authority, plan, destination, requested_layers=1, first_height=0.2,
        growth_ratio=1.0, authority_evidence=evidence, topology_evidence=topology,
        quality_evidence=incomplete_quality, wall_edge_policy=policy,
    )
    assert not certificate.accepted and certificate.reasons == ("missing_quality_evidence",)
    assert destination == source

    bad_topology = dict(topology)
    bad_topology["non_manifold"] = 1
    certificate = certify_and_persist_surface_plan(
        source, authority, plan, destination, requested_layers=1, first_height=0.2,
        growth_ratio=1.0, authority_evidence=evidence, topology_evidence=bad_topology,
        quality_evidence=quality, wall_edge_policy=policy,
    )
    assert not certificate.accepted and certificate.reasons == ("topology_non_manifold",)
    assert destination == source
