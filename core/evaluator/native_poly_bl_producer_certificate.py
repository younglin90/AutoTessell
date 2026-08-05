"""Producer-owned Native Poly BL v2 provenance and cell-partition contract.

The builder is intentionally pure until ``write_producer_certificate`` is
called.  It accepts only records captured by the producer from the source and
final arrays; it never reconstructs source authority from output labels.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "native-poly-bl-producer-certificate/v2"
PARTITION_SCHEMA = "native-poly-cell-partitions/v2"
REQUIRED_SOURCE_FACE_FIELDS = (
    "source_face_id",
    "ordered_vertex_ids",
    "canonical_vertex_ids",
    "patch_id",
    "feature_id",
    "physical_group",
    "component_id",
)
REQUIRED_EDGE_FIELDS = ("edge_id", "vertex_ids", "incident_source_face_ids")
REQUIRED_LINEAGE_DIGESTS = (
    "source_sha256",
    "candidate_source_sha256",
    "producer_mapping_sha256",
    "wall_edge_layer_sha256",
    "source_face_preservation_sha256",
    "outer_front_sha256",
)
PARTITIONS = ("core", "boundary_layer", "transition")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _integer_list(value: Any, *, name: str) -> list[int]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name}_must_be_sequence")
    result = [int(item) for item in value]
    if any(isinstance(item, bool) or item < 0 for item in result):
        raise ValueError(f"{name}_contains_invalid_id")
    return result


def _source_face_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError("source_faces_missing")
    records: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in value:
        if not isinstance(raw, Mapping) or any(field not in raw for field in REQUIRED_SOURCE_FACE_FIELDS):
            raise ValueError("source_face_authority_incomplete")
        record = dict(raw)
        source_id = record["source_face_id"]
        if isinstance(source_id, bool) or not isinstance(source_id, int) or source_id < 0 or source_id in seen:
            raise ValueError("source_face_id_duplicate_or_invalid")
        if any(record[field] is None for field in ("patch_id", "feature_id", "physical_group", "component_id")):
            raise ValueError("source_face_authority_incomplete")
        record["ordered_vertex_ids"] = _integer_list(record["ordered_vertex_ids"], name="ordered_vertex_ids")
        record["canonical_vertex_ids"] = sorted(_integer_list(record["canonical_vertex_ids"], name="canonical_vertex_ids"))
        if len(record["ordered_vertex_ids"]) < 3 or record["canonical_vertex_ids"] != sorted(set(record["ordered_vertex_ids"])):
            raise ValueError("source_face_vertex_record_invalid")
        seen.add(source_id)
        records.append(record)
    return sorted(records, key=lambda item: item["source_face_id"])


def _edge_records(value: Any, source_ids: set[int]) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError("wall_edges_missing")
    records: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in value:
        if not isinstance(raw, Mapping) or any(field not in raw for field in REQUIRED_EDGE_FIELDS):
            raise ValueError("wall_edge_authority_incomplete")
        record = dict(raw)
        edge_id = record["edge_id"]
        if isinstance(edge_id, bool) or not isinstance(edge_id, int) or edge_id < 0 or edge_id in seen:
            raise ValueError("wall_edge_id_duplicate_or_invalid")
        vertices = _integer_list(record["vertex_ids"], name="edge_vertex_ids")
        incidents = _integer_list(record["incident_source_face_ids"], name="edge_incident_source_face_ids")
        if len(vertices) != 2 or vertices[0] == vertices[1] or not set(incidents).issubset(source_ids):
            raise ValueError("wall_edge_record_invalid")
        record["vertex_ids"] = sorted(vertices)
        record["incident_source_face_ids"] = sorted(set(incidents))
        seen.add(edge_id)
        records.append(record)
    return sorted(records, key=lambda item: item["edge_id"])


def _partitions(value: Any, final_cell_ids: Sequence[int], transition_not_applicable: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(PARTITIONS):
        raise ValueError("cell_partitions_incomplete")
    final = _integer_list(list(final_cell_ids), name="final_cell_ids")
    if len(final) != len(set(final)):
        raise ValueError("final_cell_ids_duplicate")
    normalized: dict[str, list[int]] = {}
    seen: set[int] = set()
    for name in PARTITIONS:
        ids = sorted(_integer_list(value[name], name=f"{name}_cell_ids"))
        if len(ids) != len(set(ids)) or seen.intersection(ids):
            raise ValueError("cell_partition_overlap_or_duplicate")
        seen.update(ids)
        normalized[name] = ids
    if set(seen) != set(final):
        raise ValueError("cell_partition_coverage_mismatch")
    if not normalized["boundary_layer"]:
        raise ValueError("boundary_layer_partition_empty")
    if not normalized["transition"] and not transition_not_applicable:
        raise ValueError("transition_not_applicable_certificate_missing")
    return {
        "schema": PARTITION_SCHEMA,
        "cell_ids": normalized,
        "final_cell_ids": sorted(final),
        "transition_not_applicable": bool(transition_not_applicable),
        "partition_sha256": canonical_sha256({"cell_ids": normalized, "final_cell_ids": sorted(final)}),
    }


def build_producer_certificate(
    *,
    source_faces: Sequence[Mapping[str, Any]],
    wall_edges: Sequence[Mapping[str, Any]],
    layer_entities: Sequence[Mapping[str, Any]],
    outer_front: Sequence[Mapping[str, Any]],
    cell_partitions: Mapping[str, Sequence[int]],
    final_cell_ids: Sequence[int],
    requested_layers: int,
    actual_layers: int,
    total_thickness: float,
    source_sha256: str,
    candidate_file_sha256: Mapping[str, str],
    transition_not_applicable: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate producer records and return provenance + partition sidecars."""
    if requested_layers < 1 or actual_layers != requested_layers or total_thickness <= 0.0:
        raise ValueError("positive_bl_state_invalid")
    if not _digest(source_sha256):
        raise ValueError("source_sha256_invalid")
    if not isinstance(candidate_file_sha256, Mapping) or not candidate_file_sha256:
        raise ValueError("candidate_file_digests_missing")
    if any(not isinstance(name, str) or not _digest(value) for name, value in candidate_file_sha256.items()):
        raise ValueError("candidate_file_digest_invalid")
    faces = _source_face_records(source_faces)
    face_ids = {record["source_face_id"] for record in faces}
    edges = _edge_records(wall_edges, face_ids)
    layers = [dict(item) for item in layer_entities]
    if not layers:
        raise ValueError("layer_entities_missing")
    for item in layers:
        if not isinstance(item, Mapping) or not isinstance(item.get("layer"), int) or item["layer"] < 1:
            raise ValueError("layer_entity_invalid")
        if item.get("source_face_id") not in face_ids:
            raise ValueError("layer_source_face_missing")
        for key in ("generated_vertex_ids", "generated_face_ids", "generated_cell_ids"):
            _integer_list(item.get(key), name=key)
    front = [dict(item) for item in outer_front]
    if not front:
        raise ValueError("outer_front_missing")
    for item in front:
        if any(key not in item for key in ("final_face_id", "source_face_id", "layer", "cell_id")):
            raise ValueError("outer_front_record_incomplete")
        if item["source_face_id"] not in face_ids:
            raise ValueError("outer_front_source_face_missing")
    partition = _partitions(cell_partitions, final_cell_ids, transition_not_applicable)
    mapping_payload = {"faces": faces, "edges": edges, "layers": layers, "outer_front": front, "partition": partition}
    mapping_sha = canonical_sha256(mapping_payload)
    candidate_source_sha = canonical_sha256({"source_sha256": source_sha256, "candidate_files": dict(sorted(candidate_file_sha256.items())), "mapping_sha256": mapping_sha})
    provenance = {
        "schema": SCHEMA,
        "producer": "core.layers.native_bl",
        "lineage_complete": True,
        "requested_layers": int(requested_layers),
        "actual_layers": int(actual_layers),
        "total_thickness": float(total_thickness),
        "source_sha256": source_sha256,
        "candidate_source_sha256": candidate_source_sha,
        "producer_mapping_sha256": mapping_sha,
        "wall_edge_layer_sha256": canonical_sha256({"edges": edges, "layers": layers}),
        "source_face_preservation_sha256": canonical_sha256({"faces": faces, "outer_front": front}),
        "outer_front_sha256": canonical_sha256(front),
        "candidate_file_sha256": dict(sorted(candidate_file_sha256.items())),
        "source_faces": faces,
        "wall_edges": edges,
        "layer_entities": layers,
        "outer_front": front,
    }
    for name in REQUIRED_LINEAGE_DIGESTS:
        if not _digest(provenance[name]):
            raise ValueError(f"generated_digest_invalid:{name}")
    return provenance, partition


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_producer_certificate(stage_dir: str | Path, provenance: Mapping[str, Any], partition: Mapping[str, Any]) -> tuple[Path, Path]:
    """Write the two producer-owned sidecars inside an already-private stage."""
    stage = Path(stage_dir)
    if not stage.is_dir():
        raise ValueError("certificate_stage_missing")
    provenance_path = stage / "native_bl_provenance.v2.json"
    partition_path = stage / "native_cell_partitions.v2.json"
    _atomic_json(provenance_path, provenance)
    _atomic_json(partition_path, partition)
    return provenance_path, partition_path


__all__ = ["PARTITIONS", "REQUIRED_LINEAGE_DIGESTS", "build_producer_certificate", "canonical_sha256", "write_producer_certificate"]
