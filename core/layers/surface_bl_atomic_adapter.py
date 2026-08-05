"""Adapter from the native surface BL candidate to the atomic certificate."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict
from typing import Any, Mapping, MutableMapping

from .native_bl_atomic_certificate import (
    AtomicCertificate,
    BLCandidate,
    GeneratedEntities,
    QualityTuple,
    SourceAuthority,
    SurfaceLineage,
    TopologyChecks,
    canonical_bytes,
    certify_and_persist,
)
from .native_tet_wall_edge_provenance_contract import validate_wall_edge_provenance
from core.evaluator.native_authority_transaction_gate import evaluate_native_authority_transaction


_QUALITY_FIELDS = ("min_jacobian", "min_area", "max_non_orthogonality", "max_skewness", "metric_distortion", "metric_aspect_ratio")
_TOPOLOGY_FIELDS = tuple(asdict(TopologyChecks()).keys())


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _refusal(source_output: Mapping[str, Any], requested_layers: int, reason: str, *, candidate: Any = None) -> AtomicCertificate:
    return AtomicCertificate(False, (reason,), _hash(source_output), _hash(candidate if candidate is not None else {"reason": reason}), None, requested_layers, 0, "mixed_prism_shell", QualityTuple().gate_tuple())


def _complete_quality(evidence: Mapping[str, Any]) -> QualityTuple | str:
    if any(name not in evidence for name in _QUALITY_FIELDS):
        return "missing_quality_evidence"
    values: dict[str, float] = {}
    for name in _QUALITY_FIELDS:
        value = evidence[name]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            return f"invalid_quality_{name}"
        values[name] = float(value)
    if values["min_jacobian"] <= 0.0 or values["min_area"] <= 0.0:
        return "non_positive_surface_quality"
    if values["max_non_orthogonality"] > 105.0:
        return "surface_non_orthogonality_gate"
    if values["max_skewness"] > 0.50:
        return "surface_skewness_gate"
    if values["metric_distortion"] <= 0.0 or values["metric_aspect_ratio"] <= 0.0:
        return "invalid_surface_metric"
    return QualityTuple(**values)


def _complete_topology(evidence: Mapping[str, Any]) -> TopologyChecks | str:
    if any(name not in evidence for name in _TOPOLOGY_FIELDS):
        return "missing_topology_evidence"
    values: dict[str, int] = {}
    for name in _TOPOLOGY_FIELDS:
        value = evidence[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return f"invalid_topology_{name}"
        values[name] = value
    return TopologyChecks(**values)


def _authority_ok(source_output: Mapping[str, Any], authority: SourceAuthority, evidence: Mapping[str, Any] | None) -> str | None:
    if evidence is None:
        return "missing_authority_evidence"
    if evidence.get("source_sha256") != _hash(source_output):
        return "source_snapshot_hash_mismatch"
    if evidence.get("authority_sha256") != _hash(asdict(authority)):
        return "authority_hash_mismatch"
    if tuple(str(item) for item in evidence.get("wall_edges", ())) != authority.wall_edges:
        return "wall_edge_authority_mismatch"
    return None


def _wall_edge_policy_ok(source_output: Mapping[str, Any], authority: SourceAuthority, plan: Mapping[str, Any], policy: Mapping[str, Any]) -> str | None:
    """Require a complete provisional policy binding before atomic certification."""
    result = validate_wall_edge_provenance(policy, plan)
    if result.get("status") != "PROVISIONAL_PROVENANCE_READY":
        return f"wall_edge_provenance:{result.get('reason', 'refused')}"
    provenance = plan.get("provenance")
    selected = {str(item) for item in policy.get("selected_edge_ids", ())}
    bound = {str(item.get("policy_edge_id")) for item in provenance if isinstance(item, Mapping)}
    if bound != selected:
        return "wall_edge_provenance:incomplete_selected_edge_set"
    if policy.get("source_sha256") is not None and policy.get("source_sha256") != _hash(source_output):
        return "wall_edge_provenance:source_snapshot_hash_mismatch"
    for item in provenance:
        if not isinstance(item, Mapping):
            return "wall_edge_provenance:missing_policy_edge_identity_or_lineage"
        if str(item.get("source_wall_edge")) != str(item.get("policy_edge_id")):
            return "wall_edge_provenance:atomic_lineage_edge_mismatch"
        if str(item.get("patch")) != authority.patch or str(item.get("physical_group")) != authority.physical_group:
            return "wall_edge_provenance:authority_label_mismatch"
    return None


def _candidate_from_plan(source_output: Mapping[str, Any], authority: SourceAuthority, plan: Mapping[str, Any], requested_layers: int, first_height: float, growth_ratio: float, topology: TopologyChecks, quality: QualityTuple, candidate_output: Mapping[str, Any] | None) -> BLCandidate | str:
    if plan.get("accepted") is not True or plan.get("status") != "candidate_plan_ready":
        return f"planner_refused:{plan.get('reason', 'unknown')}"
    if plan.get("source_immutable") is not True:
        return "planner_source_not_immutable"
    if plan.get("requested_layers") != requested_layers or plan.get("actual_layers") != requested_layers:
        return "layer_count_mismatch"
    vertices, faces, provenance = plan.get("generated_vertices"), plan.get("generated_faces"), plan.get("provenance")
    if not isinstance(vertices, list) or not isinstance(faces, list) or not isinstance(provenance, list):
        return "incomplete_candidate_artifact"
    vertex_ids: list[str] = []
    for item in vertices:
        if not isinstance(item, Mapping) or "id" not in item:
            return "invalid_generated_vertex"
        vertex_ids.append(f"v:{item['id']}")
    face_ids = [f"f:{index}" for index in range(len(faces))]
    if len(set(vertex_ids)) != len(vertex_ids) or len(set(face_ids)) != len(face_ids):
        return "duplicate_generated_id"
    if len(vertices) != 2 * len(provenance) or len(faces) != 2 * len(provenance):
        return "incomplete_candidate_lineage"
    lineages: list[SurfaceLineage] = []
    for index, item in enumerate(provenance):
        if not isinstance(item, Mapping) or item.get("candidate_ordinal") != index or "source_wall_edge" not in item or "layer" not in item:
            return "non_canonical_surface_provenance"
        wall_edge = str(item["source_wall_edge"])
        if wall_edge not in authority.wall_edges:
            return "source_wall_edge_not_authoritative"
        if not isinstance(item["layer"], int) or not 1 <= item["layer"] <= requested_layers:
            return "invalid_surface_lineage_layer"
        begin = 2 * index
        lineages.append(SurfaceLineage(wall_edge, item["layer"], tuple(vertex_ids[begin:begin + 2]), tuple(face_ids[begin:begin + 2])))
    return BLCandidate(
        kind="surface", requested_layers=requested_layers, actual_layers=requested_layers,
        first_height=first_height, growth_ratio=growth_ratio, product_type="mixed_prism_shell",
        authority=authority, topology=topology,
        generated=GeneratedEntities(tuple(vertex_ids), tuple(face_ids)),
        output=dict(candidate_output if candidate_output is not None else plan), quality=quality,
        surface_lineage=tuple(lineages),
    )


def certify_and_persist_surface_plan(source_output: Mapping[str, Any], authority: SourceAuthority, plan: Mapping[str, Any] | None, destination: MutableMapping[str, Any], *, requested_layers: int, first_height: float, growth_ratio: float, authority_evidence: Mapping[str, Any] | None, topology_evidence: Mapping[str, Any] | None, quality_evidence: Mapping[str, Any] | None, candidate_output: Mapping[str, Any] | None = None, persist: Any = None, wall_edge_policy: Mapping[str, Any] | None = None) -> AtomicCertificate:
    """Adapt one native plan and atomically persist it when all gates pass.

    When ``wall_edge_policy`` is supplied, policy-bound wall-edge provenance is
    a mandatory preflight.  Omitting it preserves the generic surface adapter
    contract for non-Tet callers; no runtime route is promoted by this option.
    """
    if requested_layers < 0:
        return _refusal(source_output, requested_layers, "negative_layer_count")
    if requested_layers == 0:
        if plan is not None:
            return _refusal(source_output, requested_layers, "bl0_plan_must_be_bypassed")
        candidate = BLCandidate("surface", 0, 0, 0.0, 1.0, "mixed_prism_shell", authority, TopologyChecks(), GeneratedEntities(), dict(source_output))
        return certify_and_persist(source_output, authority, candidate, destination, persist=persist)
    if plan is None:
        return _refusal(source_output, requested_layers, "missing_native_candidate_plan")
    if wall_edge_policy is not None:
        reason = _wall_edge_policy_ok(source_output, authority, plan, wall_edge_policy)
        if reason:
            return _refusal(source_output, requested_layers, reason, candidate=plan)
    reason = _authority_ok(source_output, authority, authority_evidence)
    if reason:
        return _refusal(source_output, requested_layers, reason, candidate=plan)
    if topology_evidence is None:
        return _refusal(source_output, requested_layers, "missing_topology_evidence", candidate=plan)
    topology = _complete_topology(topology_evidence)
    if isinstance(topology, str):
        return _refusal(source_output, requested_layers, topology, candidate=plan)
    if quality_evidence is None:
        return _refusal(source_output, requested_layers, "missing_quality_evidence", candidate=plan)
    quality = _complete_quality(quality_evidence)
    if isinstance(quality, str):
        return _refusal(source_output, requested_layers, quality, candidate=plan)
    candidate = _candidate_from_plan(source_output, authority, plan, requested_layers, first_height, growth_ratio, topology, quality, candidate_output)
    if isinstance(candidate, str):
        return _refusal(source_output, requested_layers, candidate, candidate=plan)
    common = evaluate_native_authority_transaction(
        source_output,
        candidate.output,
        requested_layers=requested_layers,
        actual_layers=candidate.actual_layers,
        source_sha256=_hash(source_output),
        candidate_source_sha256=_hash(source_output),
        topology=asdict(candidate.topology),
        quality={
            "non_orthogonality_max": candidate.quality.max_non_orthogonality or 0.0,
            "skewness_max": candidate.quality.max_skewness or 0.0,
            "metric_distortion_max": candidate.quality.metric_distortion or 0.0,
        },
        authority_complete=True,
        collision_free=plan.get("collision_free", True) is not False,
    )
    if not common.accepted:
        return _refusal(source_output, requested_layers, common.reasons[0], candidate=plan)
    return certify_and_persist(source_output, authority, candidate, destination, persist=persist)
