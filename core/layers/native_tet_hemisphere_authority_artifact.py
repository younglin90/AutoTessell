"""Build and validate durable, provisional evidence for the open hemisphere case."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .native_bl_atomic_certificate import SourceAuthority, canonical_bytes, sha256
from .native_tet_case_atomic_adapter import certify_and_persist_case_bound_surface_plan
from .native_tet_surface_edge_ledger import build_stl_edge_ledger
from .native_tet_surface_wall_edge_policy import apply_user_wall_edge_policy
from .surface_bl_atomic_adapter import _hash


def _replay_inputs(stl_path: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    path = Path(stl_path)
    ledger = build_stl_edge_ledger(path)
    policy = apply_user_wall_edge_policy(ledger)
    selected = [edge for edge in ledger["edges"] if edge["incidence"] == 1]
    authority = SourceAuthority(
        topology="stl-edge-incidence", source=path.name, feature="unclassified_boundary",
        patch="wall", physical_group="fluid_wall", provenance="native-tet-case-ledger",
        wall_edges=tuple(edge["edge_id"] for edge in selected),
    )
    provenance = [{
        "source_wall_edge": edge["edge_id"], "policy_edge_id": edge["edge_id"],
        "source_face": edge["incident_facets"][0], "side": "boundary", "layer": 1,
        "patch": "wall", "feature": "unclassified_boundary", "physical_group": "fluid_wall",
        "component": "hemisphere", "candidate_ordinal": index,
    } for index, edge in enumerate(selected)]
    plan = {
        "accepted": True, "status": "candidate_plan_ready", "source_immutable": True,
        "requested_layers": 1, "actual_layers": 1,
        "generated_vertices": [{"id": index} for index in range(2 * len(provenance))],
        "generated_faces": [{"source_a": index} for index in range(2 * len(provenance))],
        "provenance": provenance,
    }
    source = {"source": path.name, "sha256": ledger["source_sha256"], "facet_count": ledger["facet_count"]}
    source_ledger = {
        "schema": "NativeTetSurfaceSourceLedger/v1", "status": "USER_DECLARED_PROVISIONAL",
        "sources": [{"case": "hemisphere-open", "sha256": ledger["source_sha256"], "entity_count": ledger["facet_count"],
                      "mapping_ranges": [{"start": 0, "end": ledger["facet_count"] - 1, "patch": "wall",
                                           "feature": "unclassified", "physical_group": "fluid_wall",
                                           "component": "hemisphere"}]}],
    }
    policy = dict(policy, case="hemisphere-open", patch="wall", physical_group="fluid_wall")
    topology = {"invalid": 0, "inverted": 0, "duplicate": 0, "non_manifold": 0, "self_intersecting": 0}
    quality = {"min_jacobian": 0.1, "min_area": 0.2, "max_non_orthogonality": 25.0,
               "max_skewness": 0.2, "metric_distortion": 1.1, "metric_aspect_ratio": 1.5}
    evidence = {"source_sha256": _hash(source), "authority_sha256": _hash({
        "topology": authority.topology, "source": authority.source, "feature": authority.feature,
        "patch": authority.patch, "physical_group": authority.physical_group, "provenance": authority.provenance,
        "wall_faces": authority.wall_faces, "wall_edges": authority.wall_edges,
        "ambiguous": authority.ambiguous, "already_layered": authority.already_layered,
    }), "wall_edges": list(authority.wall_edges)}
    return ledger, policy, source_ledger, authority, plan, source, topology, quality, evidence


def build_hemisphere_authority_artifact(stl_path: str | Path) -> dict[str, Any]:
    """Rebuild deterministic actual-corpus evidence; output remains provisional."""
    ledger, policy, source_ledger, authority, plan, source, topology, quality, evidence = _replay_inputs(stl_path)
    destination = dict(source)
    certificate = certify_and_persist_case_bound_surface_plan(
        source, authority, plan, destination, source_ledger=source_ledger, policy=policy,
        case="hemisphere-open", observed_source_sha256=ledger["source_sha256"],
        requested_layers=1, first_height=0.2, growth_ratio=1.0,
        authority_evidence=evidence, topology_evidence=topology, quality_evidence=quality,
    )
    selected_ids = list(policy["selected_edge_ids"])
    body: dict[str, Any] = {
        "schema": "NativeTetHemisphereCaseAuthorityArtifact/v1",
        "case": "hemisphere-open",
        "source": {"path": str(stl_path), "sha256": ledger["source_sha256"], "facet_count": ledger["facet_count"]},
        "edge_ledger": {"edge_digest": ledger["edge_digest"], "edge_count": ledger["edge_count"],
                        "boundary_edge_count": ledger["boundary_edge_count"], "non_manifold_edge_count": ledger["non_manifold_edge_count"]},
        "policy": {"source_sha256": policy["source_sha256"], "selected_edge_count": policy["selected_edge_count"],
                   "selected_edge_digest": policy["selected_edge_digest"], "selected_edge_ids": selected_ids,
                   "feature": policy["feature"], "patch": policy["patch"], "physical_group": policy["physical_group"]},
        "candidate": {"provenance_count": len(plan["provenance"]), "provenance_sha256": sha256(plan["provenance"]),
                      "certificate": certificate.as_dict(), "certificate_sha256": sha256(certificate.as_dict())},
        "authority": {"feature_authority": False, "wall_edge_authority": False,
                      "physical_group_authority": "user_declared_provisional"},
        "release_eligible": False,
        "runtime_route": "default_off",
    }
    body["artifact_sha256"] = sha256(body)
    return body


def validate_hemisphere_authority_artifact(artifact: Mapping[str, Any], stl_path: str | Path) -> dict[str, Any]:
    """Compare stored evidence with a fresh actual-corpus reconstruction."""
    if artifact.get("schema") != "NativeTetHemisphereCaseAuthorityArtifact/v1":
        return {"valid": False, "reason": "schema_mismatch"}
    if artifact.get("release_eligible") is not False or artifact.get("runtime_route") != "default_off":
        return {"valid": False, "reason": "promotion_flag_mismatch"}
    if artifact.get("authority", {}).get("feature_authority") is not False or artifact.get("authority", {}).get("wall_edge_authority") is not False:
        return {"valid": False, "reason": "authority_flag_mismatch"}
    stored = dict(artifact)
    stored_digest = stored.pop("artifact_sha256", None)
    if stored_digest != sha256(stored):
        return {"valid": False, "reason": "artifact_digest_mismatch"}
    rebuilt = build_hemisphere_authority_artifact(stl_path)
    if canonical_bytes(rebuilt) != canonical_bytes(dict(artifact)):
        return {"valid": False, "reason": "live_replay_mismatch"}
    return {"valid": True, "artifact_sha256": stored_digest, "release_eligible": False, "runtime_route": "default_off"}
