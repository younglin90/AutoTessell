"""Per-case source/policy binding tests for Native Tet surface BL."""

from __future__ import annotations

import copy

from core.layers.native_bl_atomic_certificate import SourceAuthority
from core.layers.native_tet_case_atomic_adapter import certify_and_persist_case_bound_surface_plan
from core.layers.surface_bl_atomic_adapter import _hash


def _case() -> tuple[dict[str, object], SourceAuthority, dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    source = {"vertices": [[0, 0, 0], [1, 0, 0]], "faces": ["wall-face"]}
    authority = SourceAuthority(
        topology="surface-topo", source="surface-source", feature="unclassified_boundary",
        patch="wall", physical_group="fluid_wall", provenance="surface-ledger", wall_edges=("edge:0",),
    )
    plan = {
        "accepted": True, "status": "candidate_plan_ready", "source_immutable": True,
        "requested_layers": 1, "actual_layers": 1,
        "generated_vertices": [{"id": 0}, {"id": 1}],
        "generated_faces": [{"source_a": 0}, {"source_a": 1}],
        "provenance": [{
            "source_wall_edge": "edge:0", "policy_edge_id": "edge:0", "source_face": 0,
            "side": "left", "layer": 1, "patch": "wall", "feature": "unclassified_boundary",
            "physical_group": "fluid_wall", "component": "cube", "candidate_ordinal": 0,
        }],
    }
    ledger = {
        "schema": "NativeTetSurfaceSourceLedger/v1", "status": "USER_DECLARED_PROVISIONAL",
        "sources": [{"case": "cube-stl", "sha256": "file-digest", "entity_count": 1,
                      "mapping_ranges": [{"start": 0, "end": 0, "patch": "wall", "feature": "unclassified",
                                           "physical_group": "fluid_wall", "component": "cube"}]}],
    }
    policy = {"case": "cube-stl", "status": "USER_DECLARED_PROVISIONAL_WALL_EDGE_POLICY",
              "source_sha256": "file-digest", "selected_edge_ids": ["edge:0"], "selected_edge_count": 1,
              "feature": "unclassified_boundary", "patch": "wall", "physical_group": "fluid_wall",
              "release_eligible": False}
    topology = {"invalid": 0, "inverted": 0, "duplicate": 0, "non_manifold": 0, "self_intersecting": 0}
    quality = {"min_jacobian": 0.1, "min_area": 0.2, "max_non_orthogonality": 25.0,
               "max_skewness": 0.2, "metric_distortion": 1.1, "metric_aspect_ratio": 1.5}
    evidence = {"source_sha256": _hash(source), "authority_sha256": _hash({
        "topology": authority.topology, "source": authority.source, "feature": authority.feature,
        "patch": authority.patch, "physical_group": authority.physical_group, "provenance": authority.provenance,
        "wall_faces": authority.wall_faces, "wall_edges": authority.wall_edges, "ambiguous": authority.ambiguous,
        "already_layered": authority.already_layered,
    }), "wall_edges": ["edge:0"]}
    return source, authority, plan, ledger, policy, topology, quality, evidence


def _certify(source, authority, plan, ledger, policy, topology, quality, evidence, destination, **kwargs):
    return certify_and_persist_case_bound_surface_plan(
        source, authority, plan, destination, source_ledger=ledger, policy=policy,
        case="cube-stl", observed_source_sha256="file-digest", requested_layers=1,
        first_height=0.2, growth_ratio=1.0, authority_evidence=evidence,
        topology_evidence=topology, quality_evidence=quality, **kwargs,
    )


def test_valid_case_binding_reaches_atomic_certificate_repeatably() -> None:
    source, authority, plan, ledger, policy, topology, quality, evidence = _case()
    certificates = []
    for _ in range(2):
        destination = copy.deepcopy(source)
        certificate = _certify(source, authority, plan, ledger, policy, topology, quality, evidence, destination)
        assert certificate.accepted
        certificates.append(certificate.serialized())
    assert certificates[0] == certificates[1]


def test_stale_case_or_observation_refuses_before_persistence() -> None:
    source, authority, plan, ledger, policy, topology, quality, evidence = _case()
    destination = copy.deepcopy(source)
    stale_policy = dict(policy, source_sha256="stale")
    certificate = _certify(source, authority, plan, ledger, stale_policy, topology, quality, evidence, destination)
    assert not certificate.accepted and certificate.reasons == ("case_policy_binding:policy_source_digest_mismatch",)
    assert destination == source

    destination = copy.deepcopy(source)
    certificate = certify_and_persist_case_bound_surface_plan(
        source, authority, plan, destination, source_ledger=ledger, policy=policy,
        case="cube-stl", observed_source_sha256="stale", requested_layers=1,
        first_height=0.2, growth_ratio=1.0, authority_evidence=evidence,
        topology_evidence=topology, quality_evidence=quality,
    )
    assert not certificate.accepted and certificate.reasons == ("case_policy_binding:source_file_digest_mismatch",)
    assert destination == source


def test_case_feature_component_and_case_mismatches_refuse() -> None:
    source, authority, plan, ledger, policy, topology, quality, evidence = _case()
    for field, value, reason in (
        ("feature", "sharp_edge", "case_feature_mismatch"),
        ("component", "other", "case_component_mismatch"),
    ):
        destination = copy.deepcopy(source)
        changed = copy.deepcopy(plan)
        changed["provenance"][0][field] = value  # type: ignore[index]
        certificate = _certify(source, authority, changed, ledger, policy, topology, quality, evidence, destination)
        assert not certificate.accepted and certificate.reasons == (f"case_policy_binding:{reason}",)
        assert destination == source

    destination = copy.deepcopy(source)
    certificate = certify_and_persist_case_bound_surface_plan(
        source, authority, plan, destination, source_ledger=ledger, policy=policy,
        case="other", observed_source_sha256="file-digest", requested_layers=1,
        first_height=0.2, growth_ratio=1.0, authority_evidence=evidence,
        topology_evidence=topology, quality_evidence=quality,
    )
    assert not certificate.accepted and certificate.reasons == ("case_policy_binding:source_case_not_unique",)
    assert destination == source
