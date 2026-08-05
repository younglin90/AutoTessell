"""Fail-closed source-owned authority ledger for Native Poly ingress."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.evaluator.native_poly_bl_producer_certificate import canonical_sha256

SCHEMA = "native-poly-source-ledger/v1"
AUTHORITY_KEYS = ("source_face", "wall_edge", "patch", "feature", "physical_group", "component")


class SourceLedgerRefusal(ValueError):
    """Raised when an upstream ledger cannot establish authority."""


def ledger_sha256(ledger: Mapping[str, Any]) -> str:
    payload = dict(ledger)
    payload.pop("ledger_sha256", None)
    return canonical_sha256(payload)


def validate_source_ledger(
    ledger: Mapping[str, Any], source_polymesh_sha256: Mapping[str, str]
) -> dict[str, Any]:
    """Validate and return a normalized immutable source ledger copy.

    No values are inferred.  The returned copy is safe for a private producer
    callback to inspect, while the original mapping remains untouched.
    """
    if not isinstance(ledger, Mapping):
        raise SourceLedgerRefusal("source_ledger_missing")
    if ledger.get("schema") != SCHEMA:
        raise SourceLedgerRefusal("source_ledger_schema_invalid")
    if ledger.get("immutable") is not True:
        raise SourceLedgerRefusal("source_ledger_not_immutable")
    if not isinstance(ledger.get("producer"), str) or not ledger["producer"]:
        raise SourceLedgerRefusal("source_ledger_producer_missing")
    if ledger.get("source_kind") not in ("stl", "cad_step"):
        raise SourceLedgerRefusal("source_ledger_source_kind_invalid")
    raw_source = ledger.get("raw_source_sha256")
    if not isinstance(raw_source, str) or len(raw_source) != 64 or any(c not in "0123456789abcdef" for c in raw_source):
        raise SourceLedgerRefusal("source_ledger_raw_source_digest_missing")
    importer = ledger.get("importer")
    if not isinstance(importer, Mapping) or not isinstance(importer.get("name"), str) or not isinstance(importer.get("version"), str):
        raise SourceLedgerRefusal("source_ledger_importer_missing")
    authority_source = ledger.get("authority_source")
    if (
        not isinstance(authority_source, Mapping)
        or authority_source.get("status") != "source_authored"
        or not isinstance(authority_source.get("id"), str)
        or authority_source.get("raw_source_sha256") != raw_source
    ):
        raise SourceLedgerRefusal("source_ledger_authority_source_missing")
    if ledger.get("lineage_mode") not in ("primal_1_to_1", "dual_1_to_n"):
        raise SourceLedgerRefusal("source_ledger_lineage_mode_invalid")
    if ledger.get("lineage_mode") == "dual_1_to_n":
        raise SourceLedgerRefusal("source_ledger_dual_lineage_not_supported")
    if ledger.get("polymesh_sha256") != dict(source_polymesh_sha256):
        raise SourceLedgerRefusal("source_ledger_polymesh_digest_mismatch")
    expected_source_digest = canonical_sha256(dict(source_polymesh_sha256))
    if ledger.get("source_sha256") != expected_source_digest:
        raise SourceLedgerRefusal("source_ledger_source_digest_mismatch")
    if ledger.get("ledger_sha256") != ledger_sha256(ledger):
        raise SourceLedgerRefusal("source_ledger_digest_invalid")
    authority = ledger.get("authority")
    if not isinstance(authority, Mapping) or any(authority.get(key) is not True for key in AUTHORITY_KEYS):
        raise SourceLedgerRefusal("source_ledger_authority_incomplete")

    selected = ledger.get("selected_polymesh_face_indices")
    faces = ledger.get("source_faces")
    if not isinstance(selected, Sequence) or isinstance(selected, (str, bytes)) or not selected:
        raise SourceLedgerRefusal("source_ledger_selected_faces_missing")
    if not isinstance(faces, Sequence) or isinstance(faces, (str, bytes)):
        raise SourceLedgerRefusal("source_ledger_faces_missing")
    selected_ids = [int(value) for value in selected]
    if any(isinstance(value, bool) or value < 0 for value in selected_ids) or len(selected_ids) != len(set(selected_ids)):
        raise SourceLedgerRefusal("source_ledger_selected_faces_invalid")
    if len(faces) != len(selected_ids):
        raise SourceLedgerRefusal("source_ledger_face_bijection_incomplete")
    seen_faces: set[int] = set()
    source_face_ids: set[int] = set()
    normalized_faces: list[dict[str, Any]] = []
    for expected_index, raw in zip(sorted(selected_ids), faces, strict=True):
        if not isinstance(raw, Mapping):
            raise SourceLedgerRefusal("source_ledger_face_record_invalid")
        required = ("polymesh_face_index", "source_face_id", "ordered_vertex_ids", "canonical_vertex_ids", "patch_id", "feature_id", "physical_group", "component_id")
        if any(key not in raw for key in required):
            raise SourceLedgerRefusal("source_ledger_face_authority_incomplete")
        record = dict(raw)
        if record["polymesh_face_index"] != expected_index:
            raise SourceLedgerRefusal("source_ledger_face_bijection_invalid")
        source_id = record["source_face_id"]
        if isinstance(source_id, bool) or not isinstance(source_id, int) or source_id < 0 or source_id in source_face_ids:
            raise SourceLedgerRefusal("source_ledger_source_face_id_invalid")
        ordered = record["ordered_vertex_ids"]
        canonical = record["canonical_vertex_ids"]
        if not isinstance(ordered, list) or not isinstance(canonical, list) or len(ordered) < 3:
            raise SourceLedgerRefusal("source_ledger_face_vertices_invalid")
        if canonical != sorted(set(ordered)):
            raise SourceLedgerRefusal("source_ledger_face_vertices_mismatch")
        if any(record[key] is None for key in ("patch_id", "feature_id", "physical_group", "component_id")):
            raise SourceLedgerRefusal("source_ledger_face_authority_incomplete")
        seen_faces.add(expected_index)
        source_face_ids.add(source_id)
        normalized_faces.append(record)

    edges = ledger.get("wall_edges")
    if not isinstance(edges, Sequence) or isinstance(edges, (str, bytes)) or not edges:
        raise SourceLedgerRefusal("source_ledger_edges_missing")
    seen_edges: set[int] = set()
    normalized_edges: list[dict[str, Any]] = []
    for raw in edges:
        if not isinstance(raw, Mapping) or any(key not in raw for key in ("edge_id", "vertex_ids", "incident_source_face_ids")):
            raise SourceLedgerRefusal("source_ledger_edge_authority_incomplete")
        record = dict(raw)
        edge_id = record["edge_id"]
        vertices = record["vertex_ids"]
        incidents = record["incident_source_face_ids"]
        if isinstance(edge_id, bool) or not isinstance(edge_id, int) or edge_id < 0 or edge_id in seen_edges:
            raise SourceLedgerRefusal("source_ledger_edge_id_invalid")
        if not isinstance(vertices, list) or len(vertices) != 2 or vertices[0] == vertices[1] or vertices != sorted(vertices):
            raise SourceLedgerRefusal("source_ledger_edge_vertices_invalid")
        if not isinstance(incidents, list) or not incidents or not set(incidents).issubset(source_face_ids):
            raise SourceLedgerRefusal("source_ledger_edge_incidence_invalid")
        seen_edges.add(edge_id)
        record["incident_source_face_ids"] = sorted(set(incidents))
        normalized_edges.append(record)

    normalized = dict(ledger)
    normalized["selected_polymesh_face_indices"] = sorted(selected_ids)
    normalized["source_faces"] = sorted(normalized_faces, key=lambda item: item["polymesh_face_index"])
    normalized["wall_edges"] = sorted(normalized_edges, key=lambda item: item["edge_id"])
    return normalized


__all__ = ["AUTHORITY_KEYS", "SCHEMA", "SourceLedgerRefusal", "ledger_sha256", "validate_source_ledger"]
