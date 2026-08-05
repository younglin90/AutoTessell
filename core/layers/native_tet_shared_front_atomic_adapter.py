"""Adapt shared-vertex C++ front output without destroying its lineage."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping, MutableMapping

from .native_bl_atomic_certificate import (
    AtomicCertificate,
    BLCandidate,
    GeneratedEntities,
    QualityTuple,
    SharedSurfaceLineage,
    SourceAuthority,
    TopologyChecks,
    certify_and_persist,
)
from .surface_bl_atomic_adapter import (
    _authority_ok,
    _complete_quality,
    _complete_topology,
    _hash,
    _refusal,
    certify_and_persist_surface_plan,
)


def certify_and_persist_shared_surface_plan(
    source_output: Mapping[str, Any],
    authority: SourceAuthority,
    plan: Mapping[str, Any] | None,
    destination: MutableMapping[str, Any],
    *,
    requested_layers: int,
    first_height: float,
    growth_ratio: float,
    authority_evidence: Mapping[str, Any] | None,
    topology_evidence: Mapping[str, Any] | None,
    quality_evidence: Mapping[str, Any] | None,
    candidate_output: Mapping[str, Any] | None = None,
    persist: Any = None,
) -> AtomicCertificate:
    """Certify a shared-front plan with full-layer, shared-ID semantics."""
    if requested_layers == 0:
        return certify_and_persist_surface_plan(
            source_output, authority, plan, destination, requested_layers=0,
            first_height=first_height, growth_ratio=growth_ratio,
            authority_evidence=None, topology_evidence=topology_evidence,
            quality_evidence=quality_evidence, candidate_output=candidate_output, persist=persist,
        )
    if requested_layers < 0:
        return _refusal(source_output, requested_layers, "negative_layer_count")
    if plan is None:
        return _refusal(source_output, requested_layers, "missing_native_candidate_plan")
    if plan.get("accepted") is not True or plan.get("status") != "candidate_plan_ready":
        return _refusal(source_output, requested_layers, f"planner_refused:{plan.get('reason', 'unknown')}", candidate=plan)
    if plan.get("lineage_is_shared") is not True or plan.get("source_immutable") is not True:
        return _refusal(source_output, requested_layers, "shared_front_contract_missing", candidate=plan)
    if plan.get("requested_layers") != requested_layers or plan.get("actual_layers") != requested_layers:
        return _refusal(source_output, requested_layers, "layer_count_mismatch", candidate=plan)
    reason = _authority_ok(source_output, authority, authority_evidence)
    if reason:
        return _refusal(source_output, requested_layers, reason, candidate=plan)
    topology = _complete_topology(topology_evidence or {})
    if isinstance(topology, str):
        return _refusal(source_output, requested_layers, topology, candidate=plan)
    quality = _complete_quality(quality_evidence or {})
    if isinstance(quality, str):
        return _refusal(source_output, requested_layers, quality, candidate=plan)
    vertices = plan.get("generated_vertices")
    faces = plan.get("generated_faces")
    provenance = plan.get("provenance")
    if not isinstance(vertices, list) or not isinstance(faces, list) or not isinstance(provenance, list) or len(faces) != len(provenance):
        return _refusal(source_output, requested_layers, "incomplete_shared_front_artifact", candidate=plan)
    vertex_ids: list[str] = []
    for item in vertices:
        if not isinstance(item, Mapping) or "id" not in item or str(item["id"]) in vertex_ids:
            return _refusal(source_output, requested_layers, "duplicate_shared_generated_vertex", candidate=plan)
        vertex_ids.append(f"v:{item['id']}")
    face_ids = [f"f:{index}" for index in range(len(faces))]
    lineage: list[SharedSurfaceLineage] = []
    for index, item in enumerate(provenance):
        if not isinstance(item, Mapping):
            return _refusal(source_output, requested_layers, "invalid_shared_surface_lineage", candidate=plan)
        generated = item.get("generated_vertices")
        edge = str(item.get("source_wall_edge"))
        layer = item.get("layer")
        if not isinstance(generated, (list, tuple)) or len(generated) != 2 or edge not in authority.wall_edges:
            return _refusal(source_output, requested_layers, "invalid_shared_surface_lineage", candidate=plan)
        if not isinstance(layer, int) or not 1 <= layer <= requested_layers:
            return _refusal(source_output, requested_layers, "invalid_shared_surface_lineage_layer", candidate=plan)
        refs = tuple(f"v:{value}" for value in generated)
        if any(value not in vertex_ids for value in refs):
            return _refusal(source_output, requested_layers, "shared_lineage_vertex_not_generated", candidate=plan)
        lineage.append(SharedSurfaceLineage(edge, layer, refs, face_ids[index]))
    candidate = BLCandidate(
        kind="surface", requested_layers=requested_layers, actual_layers=requested_layers,
        first_height=first_height, growth_ratio=growth_ratio, product_type="mixed_prism_shell",
        authority=authority, topology=topology,
        generated=GeneratedEntities(tuple(vertex_ids), tuple(face_ids)),
        output=dict(candidate_output if candidate_output is not None else plan), quality=quality,
        shared_surface_lineage=tuple(lineage),
    )
    return certify_and_persist(source_output, authority, candidate, destination, persist=persist)
