"""Actual open-hemisphere edge-policy replay through the strict atomic path."""

from __future__ import annotations

import copy
from pathlib import Path

from core.layers.native_bl_atomic_certificate import SourceAuthority
from core.layers.native_tet_case_atomic_adapter import certify_and_persist_case_bound_surface_plan
from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger
from core.layers.native_tet_surface_wall_edge_policy import apply_user_wall_edge_policy
from core.layers.surface_bl_atomic_adapter import _hash


def _replay_case() -> tuple[dict[str, object], SourceAuthority, dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    path = Path("tests/benchmarks/hemisphere_open.stl")
    ledger = build_stl_edge_ledger(path)
    policy = apply_user_wall_edge_policy(ledger)
    source_ledger = {
        "schema": "NativeTetSurfaceSourceLedger/v1", "status": "USER_DECLARED_PROVISIONAL",
        "sources": [{"case": "hemisphere-open", "sha256": ledger["source_sha256"], "entity_count": ledger["facet_count"],
                      "mapping_ranges": [{"start": 0, "end": ledger["facet_count"] - 1, "patch": "wall",
                                           "feature": "unclassified", "physical_group": "fluid_wall",
                                           "component": "hemisphere"}]}],
    }
    selected = [edge for edge in ledger["edges"] if edge["incidence"] == 1]
    authority = SourceAuthority(
        topology="stl-edge-incidence", source="hemisphere_open.stl", feature="unclassified_boundary",
        patch="wall", physical_group="fluid_wall", provenance="native-tet-case-ledger",
        wall_edges=tuple(edge["edge_id"] for edge in selected),
    )
    provenance = []
    for index, edge in enumerate(selected):
        provenance.append({
            "source_wall_edge": edge["edge_id"], "policy_edge_id": edge["edge_id"],
            "source_face": edge["incident_facets"][0], "side": "boundary", "layer": 1,
            "patch": "wall", "feature": "unclassified_boundary", "physical_group": "fluid_wall",
            "component": "hemisphere", "candidate_ordinal": index,
        })
    plan = {
        "accepted": True, "status": "candidate_plan_ready", "source_immutable": True,
        "requested_layers": 1, "actual_layers": 1,
        "generated_vertices": [{"id": index} for index in range(2 * len(provenance))],
        "generated_faces": [{"source_a": index} for index in range(2 * len(provenance))],
        "provenance": provenance,
    }
    source = {"source": "hemisphere_open.stl", "sha256": ledger["source_sha256"], "facet_count": ledger["facet_count"]}
    adapter_policy = dict(policy, case="hemisphere-open", patch="wall", physical_group="fluid_wall")
    topology = {"invalid": 0, "inverted": 0, "duplicate": 0, "non_manifold": 0, "self_intersecting": 0}
    quality = {"min_jacobian": 0.1, "min_area": 0.2, "max_non_orthogonality": 25.0,
               "max_skewness": 0.2, "metric_distortion": 1.1, "metric_aspect_ratio": 1.5}
    evidence = {"source_sha256": _hash(source), "authority_sha256": _hash({
        "topology": authority.topology, "source": authority.source, "feature": authority.feature,
        "patch": authority.patch, "physical_group": authority.physical_group, "provenance": authority.provenance,
        "wall_faces": authority.wall_faces, "wall_edges": authority.wall_edges,
        "ambiguous": authority.ambiguous, "already_layered": authority.already_layered,
    }), "wall_edges": list(authority.wall_edges)}
    return source, authority, plan, source_ledger, adapter_policy, topology, quality, evidence, ledger


def _certify(source, authority, plan, source_ledger, policy, topology, quality, evidence, destination):
    return certify_and_persist_case_bound_surface_plan(
        source, authority, plan, destination, source_ledger=source_ledger, policy=policy,
        case="hemisphere-open", observed_source_sha256=source_ledger["sources"][0]["sha256"],
        requested_layers=1, first_height=0.2, growth_ratio=1.0,
        authority_evidence=evidence, topology_evidence=topology, quality_evidence=quality,
    )


def test_actual_hemisphere_policy_replay_is_repeatable() -> None:
    source, authority, plan, source_ledger, policy, topology, quality, evidence, ledger = _replay_case()
    assert ledger["facet_count"] == 624
    assert ledger["edge_count"] == 960
    assert ledger["boundary_edge_count"] == 48
    assert ledger["non_manifold_edge_count"] == 0
    assert policy["selected_edge_count"] == 48
    certificates = []
    for _ in range(2):
        destination = copy.deepcopy(source)
        certificate = _certify(source, authority, plan, source_ledger, policy, topology, quality, evidence, destination)
        assert certificate.accepted
        certificates.append(certificate.serialized())
    assert certificates[0] == certificates[1]


def test_actual_replay_refuses_missing_duplicate_or_stale_edge_evidence() -> None:
    source, authority, plan, source_ledger, policy, topology, quality, evidence, _ = _replay_case()
    destination = copy.deepcopy(source)
    missing = copy.deepcopy(plan)
    missing["provenance"] = missing["provenance"][:-1]
    missing["generated_vertices"] = missing["generated_vertices"][:-2]
    missing["generated_faces"] = missing["generated_faces"][:-2]
    certificate = _certify(source, authority, missing, source_ledger, policy, topology, quality, evidence, destination)
    assert not certificate.accepted and certificate.reasons == ("wall_edge_provenance:incomplete_selected_edge_set",)
    assert destination == source

    duplicate = copy.deepcopy(plan)
    duplicate["provenance"][1]["policy_edge_id"] = duplicate["provenance"][0]["policy_edge_id"]  # type: ignore[index]
    destination = copy.deepcopy(source)
    certificate = _certify(source, authority, duplicate, source_ledger, policy, topology, quality, evidence, destination)
    assert not certificate.accepted and certificate.reasons == ("wall_edge_provenance:duplicate_policy_edge_lineage",)
    assert destination == source

    destination = copy.deepcopy(source)
    certificate = certify_and_persist_case_bound_surface_plan(
        source, authority, plan, destination, source_ledger=source_ledger, policy=policy,
        case="hemisphere-open", observed_source_sha256="stale", requested_layers=1,
        first_height=0.2, growth_ratio=1.0, authority_evidence=evidence,
        topology_evidence=topology, quality_evidence=quality,
    )
    assert not certificate.accepted and certificate.reasons == ("case_policy_binding:source_file_digest_mismatch",)
    assert destination == source


def test_bl0_actual_case_replay_keeps_exact_source_bypass() -> None:
    source, authority, _, source_ledger, policy, topology, quality, evidence, _ = _replay_case()
    destination = copy.deepcopy(source)
    certificate = certify_and_persist_case_bound_surface_plan(
        source, authority, None, destination, source_ledger=source_ledger, policy=policy,
        case="hemisphere-open", observed_source_sha256=source_ledger["sources"][0]["sha256"],
        requested_layers=0, first_height=0.0, growth_ratio=1.0,
        authority_evidence=None, topology_evidence=topology, quality_evidence=quality,
    )
    assert certificate.accepted and destination == source
