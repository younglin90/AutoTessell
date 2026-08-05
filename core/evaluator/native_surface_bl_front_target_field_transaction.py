"""Private, fail-closed consumer for a sealed wall-edge BL target receipt.

The target-field optimizer intentionally stops before geometry publication.  This
module is the next private transaction: it consumes the optimizer's direct-ID
receipt, reconstructs one shared point per ``(source_vertex, sector, layer)``
key, and hands the candidate to the C++23 strip writer.  It does not alter a
production route.  A writer refusal is an atomic rollback with no generated
faces or provenance returned to the caller.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from core.layers.native_bl_atomic_certificate import sha256
from core.evaluator.native_surface_bl_strip_writer import (
    write_authoritative_surface_wall_edge_planar_cavity,
    write_authoritative_surface_wall_edge_strip,
)


_TOL = 1.0e-8
_DOT_FLOOR = 0.25


def _empty(reason: str, requested_layers: int) -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "refused_rollback",
        "reason": reason,
        "requested_layers": requested_layers,
        "actual_layers": 0,
        "generated_vertices": [],
        "generated_faces": [],
        "provenance": [],
        "runtime_route": "default_off",
        "publication_eligible": False,
        "route_calls": 0,
        "candidate_discarded": True,
        "transaction_atomic": True,
    }


def _jsonable(value: Any) -> Any:
    """Convert numpy/scalar containers before deterministic hashing."""
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _text(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    text = str(value)
    return text if text else ""


def _int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean_is_not_integer")
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return int(value)
    raise ValueError("integer_field_required")


def _float(value: Any) -> float:
    number = float(value)
    if not np.isfinite(number):
        raise ValueError("finite_float_required")
    return number


def _source_authority(certificate: Mapping[str, Any]) -> dict[str, str]:
    required = ("source_kind", "raw_sha256", "brep_hash", "authority", "provenance")
    if any(not _text(certificate.get(key)) for key in required):
        raise ValueError("source_authority_incomplete")
    return {
        "source_kind": _text(certificate["source_kind"]),
        "source_sha256": _text(certificate.get("source_sha256", certificate["raw_sha256"])),
        "boundary_mapping_sha256": _text(
            certificate.get("boundary_mapping_sha256", certificate["brep_hash"])
        ),
        # Older C101 ledgers use the sealed provenance digest as the group
        # binding.  Newer ledgers may provide a dedicated field.
        "physical_group_sha256": _text(
            certificate.get("physical_group_sha256", certificate["provenance"])
        ),
        "provenance": _text(certificate["provenance"]),
    }


def _source_rows(
    edges: np.ndarray, edge_provenance: Sequence[Mapping[str, Any]]
) -> tuple[list[int], list[dict[str, Any]], dict[tuple[int, int, int, int], int]]:
    if len(edge_provenance) != int(edges.shape[0]):
        raise ValueError("source_edge_lineage_count_mismatch")
    required = (
        "source_edge",
        "source_face",
        "wall_edge",
        "output_face",
        "feature",
        "patch",
        "physical_group",
        "component",
        "provenance",
    )
    rows: list[dict[str, Any]] = []
    for item in edge_provenance:
        if not isinstance(item, Mapping):
            raise ValueError("source_edge_lineage_not_mapping")
        row = dict(item)
        if any(not _text(row.get(key)) for key in required):
            raise ValueError("source_edge_lineage_incomplete")
        rows.append(row)
    order = sorted(
        range(int(edges.shape[0])),
        key=lambda index: (
            int(edges[index, 0]),
            int(edges[index, 3]),
            int(edges[index, 1]),
            int(edges[index, 2]),
            index,
        ),
    )
    edge_lookup: dict[tuple[int, int, int, int], int] = {}
    for index in order:
        edge_id, vertex_a, vertex_b, face_id = (int(value) for value in edges[index])
        key = (edge_id, face_id, vertex_a, vertex_b)
        base_key = key
        if base_key in edge_lookup:
            raise ValueError("duplicate_source_edge_sector")
        row = rows[index]
        if _text(row["source_edge"]) != str(edge_id) or _text(row["source_face"]) != str(face_id):
            raise ValueError("source_edge_lineage_id_mismatch")
        edge_lookup[base_key] = index
    return order, rows, edge_lookup


def _receipt_digest(receipt: Mapping[str, Any]) -> str:
    snapshot = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    return sha256(_jsonable(snapshot))


def _quality_from_decisions(decisions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values: dict[str, list[float]] = {
        "skewness": [],
        "triangle_aspect_ratio": [],
        "non_orthogonality": [],
    }
    for decision in decisions:
        for source, target in (
            ("skewness", "skewness"),
            ("metric_aspect_ratio", "triangle_aspect_ratio"),
            ("non_orthogonality", "non_orthogonality"),
        ):
            if source in decision:
                values[target].append(_float(decision[source]))
    quality: dict[str, Any] = {}
    for name, series in values.items():
        if not series:
            continue
        quality[f"max_{name}"] = max(series)
        quality[f"p95_{name}"] = float(np.percentile(series, 95))
        quality[f"p99_{name}"] = float(np.percentile(series, 99))
    quality["triangle_gate"] = {
        "max_skewness": 0.50,
        "max_triangle_aspect_ratio": 10.0,
        "max_non_orthogonality_degrees": 75.0,
    }
    return quality


def transact_surface_wall_edge_target_field(
    points: Any,
    source_triangles: Any,
    wall_edges: Any,
    face_normals: Any,
    target_receipt: Mapping[str, Any] | None,
    source_certificate: Mapping[str, Any] | None,
    edge_provenance: Sequence[Mapping[str, Any]] | None,
    requested_layers: int,
    *,
    planar_cavity_replacement: bool = False,
    strict_quality: bool = False,
) -> dict[str, Any]:
    """Consume a target receipt and atomically attempt a private surface strip.

    The function is deliberately not connected to the public meshing route.
    ``requested_layers == 0`` validates source authority and returns identity
    without consuming the receipt or calling the writer. The optional
    planar_cavity_replacement path is private and requires a C104 v3
    directed-frame receipt with one to three layers. When strict_quality is true,
    the private planar writer applies the strict quality promotion gate.
    """
    try:
        layers = _int(requested_layers)
        if layers < 0:
            return _empty("negative_layer_count", layers)
        point_array = np.ascontiguousarray(np.asarray(points, dtype=np.float64))
        triangle_array = np.ascontiguousarray(np.asarray(source_triangles, dtype=np.int64))
        edge_array = np.ascontiguousarray(np.asarray(wall_edges, dtype=np.int64))
        normal_array = np.ascontiguousarray(np.asarray(face_normals, dtype=np.float64))
        if (
            point_array.ndim != 2
            or point_array.shape[1] != 3
            or triangle_array.ndim != 2
            or triangle_array.shape[1] != 3
            or edge_array.ndim != 2
            or edge_array.shape[1] != 4
            or normal_array.ndim != 2
            or normal_array.shape[1] != 3
            or not np.isfinite(point_array).all()
            or not np.isfinite(normal_array).all()
        ):
            return _empty("transaction_input_shape_or_finiteness", layers)
        if not isinstance(source_certificate, Mapping) or edge_provenance is None:
            return _empty("source_authority_incomplete", layers)
        authority = _source_authority(source_certificate)
        order, source_rows, edge_lookup = _source_rows(edge_array, edge_provenance)
        sorted_edges = np.ascontiguousarray(edge_array[np.asarray(order, dtype=np.int64)])
        source_digest = sha256(
            {
                "points": _jsonable(point_array),
                "source_triangles": _jsonable(triangle_array),
                "wall_edges": _jsonable(sorted_edges),
                "source_authority": authority,
            }
        )

        if layers == 0:
            result = _empty("disabled_identity", 0)
            result.update(
                {
                    "accepted": True,
                    "status": "surface_bl_front_target_field_transaction_bl0_identity",
                    "reason": "disabled_identity",
                    "candidate_discarded": False,
                    "source_authority_bound": True,
                    "authority_checked": True,
                    "receipt_consumed": False,
                    "receipt_digest": None,
                    "source_digest": source_digest,
                    "output_digest": source_digest,
                    "source_triangles_unchanged": True,
                    "topology_invalid": 0,
                    "topology_inverted": 0,
                    "topology_duplicate": 0,
                    "topology_non_manifold": 0,
                    "strict_quality": bool(strict_quality),
                }
            )
            return result

        if not isinstance(target_receipt, Mapping):
            return _empty("target_receipt_missing", layers)
        receipt = dict(target_receipt)
        digest = _receipt_digest(receipt)
        supplied_digest = receipt.get("receipt_digest")
        if supplied_digest is not None and _text(supplied_digest) != digest:
            return _empty("target_receipt_digest_mismatch", layers) | {"receipt_digest": digest}
        required_receipt = {
            "accepted": True,
            "status": "target_field_receipt_sealed",
            "receipt_sealed": True,
            "source_authority_bound": True,
            "authority_checked": True,
            "target_field": True,
            "runtime_route": "default_off",
            "publication_eligible": False,
            "route_calls": 0,
        }
        for key, expected in required_receipt.items():
            if receipt.get(key) != expected:
                return _empty(f"target_receipt_contract_{key}", layers) | {"receipt_digest": digest}
        if _int(receipt.get("requested_layers", -1)) != layers or _int(receipt.get("actual_layers", -1)) != layers:
            return _empty("target_receipt_layer_count_mismatch", layers) | {"receipt_digest": digest}
        v3_frame = receipt.get("receipt_version") == "target_field_receipt_v3_directed_frame"
        if planar_cavity_replacement and not 1 <= layers <= 3:
            return _empty("planar_cavity_supports_one_to_three_layers", layers) | {"receipt_digest": digest}
        if planar_cavity_replacement and not v3_frame:
            return _empty("planar_cavity_requires_v3_frame", layers) | {"receipt_digest": digest}
        if v3_frame:
            if receipt.get("curved_strip_frame_mode") is not True:
                return _empty("target_frame_mode_missing", layers) | {"receipt_digest": digest}
            if _int(receipt.get("source_triangle_count", -1)) != int(triangle_array.shape[0]):
                return _empty("target_frame_triangle_count_mismatch", layers) | {"receipt_digest": digest}
            if _text(receipt.get("source_triangle_digest")) != sha256(_jsonable(triangle_array)):
                return _empty("target_frame_triangle_digest_mismatch", layers) | {"receipt_digest": digest}
            cycle_ids = receipt.get("frame_cycle_edge_ids")
            if not isinstance(cycle_ids, Sequence) or isinstance(cycle_ids, (str, bytes)):
                return _empty("target_frame_cycle_missing", layers) | {"receipt_digest": digest}
            cycle_values = [_int(value) for value in cycle_ids]
            source_edge_ids = [int(value) for value in sorted_edges[:, 0]]
            if len(cycle_values) != len(source_edge_ids) or len(set(cycle_values)) != len(cycle_values) or set(cycle_values) != set(source_edge_ids):
                return _empty("target_frame_cycle_mismatch", layers) | {"receipt_digest": digest}
            closure = _float(receipt.get("frame_closure_residual"))
            side = _float(receipt.get("frame_min_side_dot"))
            if closure > 1.0e-6 or side <= 0.0:
                return _empty("target_frame_witness_invalid", layers) | {"receipt_digest": digest}
        target_vertices = receipt.get("target_vertices")
        target_edges = receipt.get("target_edges")
        if not isinstance(target_vertices, Sequence) or isinstance(target_vertices, (str, bytes)):
            return _empty("target_vertex_rows_missing", layers) | {"receipt_digest": digest}
        if not isinstance(target_edges, Sequence) or isinstance(target_edges, (str, bytes)):
            return _empty("target_edge_rows_missing", layers) | {"receipt_digest": digest}
        if len(target_edges) != layers * int(edge_array.shape[0]):
            return _empty("target_edge_rows_incomplete", layers) | {"receipt_digest": digest}

        vertex_rows: dict[tuple[int, str, int], dict[str, Any]] = {}
        for item in target_vertices:
            if not isinstance(item, Mapping):
                return _empty("target_vertex_row_invalid", layers) | {"receipt_digest": digest}
            row = dict(item)
            vertex = _int(row.get("vertex", -1))
            sector = _text(row.get("sector"))
            layer = _int(row.get("layer", -1))
            predecessor = _int(row.get("predecessor_layer", -2))
            if vertex < 0 or vertex >= point_array.shape[0] or not sector or not 1 <= layer <= layers or predecessor != layer - 1:
                return _empty("target_vertex_key_invalid", layers) | {"receipt_digest": digest}
            key = (vertex, sector, layer)
            if key in vertex_rows:
                return _empty("target_vertex_key_duplicate", layers) | {"receipt_digest": digest}
            height = _float(row.get("accepted_height"))
            requested = _float(row.get("requested_height"))
            direction = np.asarray(
                [_float(row.get("direction_x")), _float(row.get("direction_y")), _float(row.get("direction_z"))],
                dtype=np.float64,
            )
            direction_norm = float(np.linalg.norm(direction))
            if not np.isfinite(direction_norm) or abs(direction_norm - 1.0) > _TOL or height <= 0.0 or requested <= 0.0:
                return _empty("target_vertex_geometry_invalid", layers) | {"receipt_digest": digest}
            source_edge_ids = row.get("source_edge_ids")
            if not isinstance(source_edge_ids, Sequence) or isinstance(source_edge_ids, (str, bytes)):
                return _empty("target_vertex_incidence_missing", layers) | {"receipt_digest": digest}
            if v3_frame:
                frame = np.asarray(
                    [_float(row.get("frame_x")), _float(row.get("frame_y")), _float(row.get("frame_z"))],
                    dtype=np.float64,
                )
                if np.linalg.norm(frame - direction) > _TOL:
                    return _empty("target_frame_vertex_direction_mismatch", layers) | {"receipt_digest": digest}
                row["_frame"] = frame
            row["_direction"] = direction
            row["_source_edge_ids"] = {_int(value) for value in source_edge_ids}
            vertex_rows[key] = row

        edge_rows: dict[tuple[int, int], dict[str, Any]] = {}
        edge_sector_incidence: dict[tuple[int, str], set[int]] = {}
        for item in target_edges:
            if not isinstance(item, Mapping):
                return _empty("target_edge_row_invalid", layers) | {"receipt_digest": digest}
            row = dict(item)
            edge_id = _int(row.get("source_edge_id", -1))
            face_id = _int(row.get("source_face_id", -1))
            vertex_a = _int(row.get("source_vertex_a", -1))
            vertex_b = _int(row.get("source_vertex_b", -1))
            layer = _int(row.get("layer", -1))
            predecessor = _int(row.get("predecessor_layer", -2))
            sector = _text(row.get("sector"))
            base_key = (edge_id, face_id, vertex_a, vertex_b)
            source_index = edge_lookup.get(base_key)
            if source_index is None:
                return _empty("target_edge_source_id_mismatch", layers) | {"receipt_digest": digest}
            sorted_index = order.index(source_index)
            edge_key = (sorted_index, layer)
            if edge_key in edge_rows or not sector or not 1 <= layer <= layers or predecessor != layer - 1:
                return _empty("target_edge_key_invalid_or_duplicate", layers) | {"receipt_digest": digest}
            source_row = source_rows[source_index]
            for direct_key in ("source_edge", "source_face", "wall_edge", "output_face", "component", "provenance"):
                if _text(row.get(direct_key)) != _text(source_row.get(direct_key)):
                    return _empty("target_edge_provenance_mismatch", layers) | {"receipt_digest": digest}
            for value in (row.get("accepted_height"), row.get("accepted_height_a"), row.get("accepted_height_b")):
                if _float(value) <= 0.0:
                    return _empty("target_edge_height_invalid", layers) | {"receipt_digest": digest}
            for value in (row.get("metric_aspect"), row.get("height_skew"), row.get("tangential_target")):
                if _float(value) < 0.0:
                    return _empty("target_edge_metric_invalid", layers) | {"receipt_digest": digest}
            direction = np.asarray(
                [_float(row.get("direction_x")), _float(row.get("direction_y")), _float(row.get("direction_z"))],
                dtype=np.float64,
            )
            direction_norm = float(np.linalg.norm(direction))
            if abs(direction_norm - 1.0) > _TOL:
                return _empty("target_edge_direction_invalid", layers) | {"receipt_digest": digest}
            if v3_frame:
                raw_direction = np.asarray(
                    [_float(row.get("raw_direction_x")), _float(row.get("raw_direction_y")), _float(row.get("raw_direction_z"))],
                    dtype=np.float64,
                )
                transported = np.asarray(
                    [_float(row.get("transport_direction_x")), _float(row.get("transport_direction_y")), _float(row.get("transport_direction_z"))],
                    dtype=np.float64,
                )
                if abs(float(np.linalg.norm(raw_direction)) - 1.0) > _TOL or abs(float(np.linalg.norm(transported)) - 1.0) > _TOL:
                    return _empty("target_frame_edge_direction_invalid", layers) | {"receipt_digest": digest}
                if float(np.dot(transported, raw_direction)) <= 0.0:
                    return _empty("target_frame_edge_side_failure", layers) | {"receipt_digest": digest}
                row["_raw_direction"] = raw_direction
                row["_transport_direction"] = transported
            row["_source_index"] = source_index
            row["_sorted_index"] = sorted_index
            row["_direction"] = direction
            row["_base_key"] = base_key
            row["_sector"] = sector
            edge_rows[edge_key] = row
            edge_sector_incidence.setdefault((vertex_a, sector), set()).add(edge_id)
            edge_sector_incidence.setdefault((vertex_b, sector), set()).add(edge_id)

        expected_vertex_keys: set[tuple[int, str, int]] = set()
        for (sorted_index, layer), row in edge_rows.items():
            _, a, b, _ = (int(value) for value in sorted_edges[sorted_index])
            sector = row["_sector"]
            expected_vertex_keys.add((a, sector, layer))
            expected_vertex_keys.add((b, sector, layer))
            for vertex in (a, b):
                key = (vertex, sector, layer)
                vertex_row = vertex_rows.get(key)
                if vertex_row is None:
                    return _empty("target_vertex_key_missing", layers) | {"receipt_digest": digest}
                if vertex_row["_source_edge_ids"] != edge_sector_incidence[(vertex, sector)]:
                    return _empty("target_vertex_incidence_mismatch", layers) | {"receipt_digest": digest}
                if abs(float(np.dot(vertex_row["_direction"], row["_direction"]))) < _DOT_FLOOR:
                    return _empty("target_edge_sector_direction_mismatch", layers) | {"receipt_digest": digest}
        if set(vertex_rows) != expected_vertex_keys:
            return _empty("target_vertex_key_set_mismatch", layers) | {"receipt_digest": digest}

        generated: dict[tuple[int, str, int], np.ndarray] = {}
        generated_ids: dict[tuple[int, str, int], int] = {}
        generated_records: list[dict[str, Any]] = []
        sorted_keys = sorted(vertex_rows, key=lambda key: (key[2], key[0], key[1]))
        for key in sorted_keys:
            vertex, sector, layer = key
            row = vertex_rows[key]
            previous_key = (vertex, sector, layer - 1)
            previous = point_array[vertex] if layer == 1 else generated.get(previous_key)
            if previous is None:
                return _empty("target_vertex_predecessor_missing", layers) | {"receipt_digest": digest}
            candidate = previous + row["_direction"] * _float(row["accepted_height"])
            if not np.isfinite(candidate).all():
                return _empty("target_vertex_candidate_nonfinite", layers) | {"receipt_digest": digest}
            generated[key] = candidate
            generated_ids[key] = int(point_array.shape[0]) + len(generated_records)
            generated_records.append(
                {
                    "id": generated_ids[key],
                    "source_vertex": vertex,
                    "sector": sector,
                    "layer": layer,
                    "predecessor_id": vertex if layer == 1 else generated_ids[previous_key],
                    "x": float(candidate[0]),
                    "y": float(candidate[1]),
                    "z": float(candidate[2]),
                }
            )

        candidate_points = np.ascontiguousarray(
            np.vstack([point_array, np.asarray([generated[key] for key in sorted_keys], dtype=np.float64)])
        )
        layer_ids = np.empty((layers, len(order), 2), dtype=np.int64)
        writer_provenance: list[dict[str, Any]] = []
        for layer in range(1, layers + 1):
            for sorted_index, source_index in enumerate(order):
                edge_id, vertex_a, vertex_b, face_id = (int(value) for value in sorted_edges[sorted_index])
                row = edge_rows.get((sorted_index, layer))
                if row is None:
                    return _empty("target_edge_layer_missing", layers) | {"receipt_digest": digest}
                sector = row["_sector"]
                key_a = (vertex_a, sector, layer)
                key_b = (vertex_b, sector, layer)
                layer_ids[layer - 1, sorted_index] = (generated_ids[key_a], generated_ids[key_b])
                source_row = dict(source_rows[source_index])
                source_row.update(
                    {
                        "source_wall_edge": source_row["wall_edge"],
                        "layer": layer,
                        "source_edge_id": edge_id,
                        "source_face_id": face_id,
                        "source_vertex_a": vertex_a,
                        "source_vertex_b": vertex_b,
                        "sector": sector,
                        "requested_height": _float(row["requested_height"]),
                        "accepted_height": _float(row["accepted_height"]),
                        "accepted_height_a": _float(row["accepted_height_a"]),
                        "accepted_height_b": _float(row["accepted_height_b"]),
                        "target_receipt_digest": digest,
                    }
                )
                vertex_height_a = _float(vertex_rows[key_a]["accepted_height"])
                vertex_height_b = _float(vertex_rows[key_b]["accepted_height"])
                if (
                    abs(_float(row["accepted_height_a"]) - vertex_height_a) > _TOL
                    or abs(_float(row["accepted_height_b"]) - vertex_height_b) > _TOL
                ):
                    return _empty("target_edge_vertex_height_mismatch", layers) | {"receipt_digest": digest}
                writer_provenance.append(source_row)

        candidate_snapshot = {
            "receipt_digest": digest,
            "source_digest": source_digest,
            "requested_layers": layers,
            "points": _jsonable(candidate_points),
            "source_triangles": _jsonable(triangle_array),
            "wall_edges": _jsonable(sorted_edges),
            "layer_point_ids": _jsonable(layer_ids),
            "source_authority": authority,
            "provenance": writer_provenance,
            "strict_quality": bool(strict_quality),
        }
        candidate_digest = sha256(candidate_snapshot)
        if planar_cavity_replacement:
            writer_result = write_authoritative_surface_wall_edge_planar_cavity(
                candidate_points,
                triangle_array,
                sorted_edges,
                layer_ids,
                normal_array,
                authority,
                writer_provenance,
                layers,
                bool(strict_quality),
            )
        else:
            writer_result = write_authoritative_surface_wall_edge_strip(
                candidate_points,
                triangle_array,
                sorted_edges,
                layer_ids,
                normal_array,
                authority,
                writer_provenance,
                layers,
            )
        if not bool(writer_result.get("accepted", False)):
            result = _empty(_text(writer_result.get("reason")) or "writer_refused", layers)
            result.update(
                {
                    "writer_status": writer_result.get("status"),
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                    "source_digest": source_digest,
                    "source_authority_bound": True,
                    "authority_checked": True,
                    "receipt_consumed": True,
                    "source_triangles_unchanged": True,
                    "transaction_mode": "planar_cavity" if planar_cavity_replacement else "append_strip",
                    "quality": {"writer_refusal": writer_result.get("reason")},
                    "strict_quality": bool(strict_quality),
                }
            )
            return result

        subdivision_factor = _int(
            writer_result.get("subdivision_factor", 1)
        )
        if subdivision_factor < 1 or subdivision_factor > 16:
            return _empty("writer_subdivision_factor_invalid", layers) | {
                "receipt_digest": digest,
                "candidate_digest": candidate_digest,
            }

        source_edge_ids = {int(row[0]) for row in sorted_edges.tolist()}
        raw_counts = writer_result.get("count_ledger", [])
        if raw_counts is None:
            raw_counts = []
        count_by_group: dict[tuple[int, int], int] = {}
        if raw_counts:
            if not isinstance(raw_counts, Sequence) or isinstance(raw_counts, (str, bytes)):
                return _empty("writer_count_ledger_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            for item in raw_counts:
                if not isinstance(item, Mapping):
                    return _empty("writer_count_ledger_invalid", layers) | {
                        "receipt_digest": digest,
                        "candidate_digest": candidate_digest,
                    }
                edge_id = _int(item.get("source_edge_id"))
                layer = _int(item.get("layer"))
                count = _int(item.get("count"))
                key = (edge_id, layer)
                if (
                    edge_id not in source_edge_ids
                    or not 0 <= layer <= layers
                    or not 1 <= count <= 16
                    or key in count_by_group
                    or _text(item.get("source_wall_edge")) != str(edge_id)
                ):
                    return _empty("writer_count_ledger_invalid", layers) | {
                        "receipt_digest": digest,
                        "candidate_digest": candidate_digest,
                    }
                count_by_group[key] = count
            expected_count_keys = {
                (edge_id, layer)
                for edge_id in source_edge_ids
                for layer in range(layers + 1)
            }
            if set(count_by_group) != expected_count_keys:
                return _empty("writer_count_ledger_coverage", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
        else:
            count_by_group = {
                (edge_id, layer): subdivision_factor
                for edge_id in source_edge_ids
                for layer in range(layers + 1)
            }

        raw_lineage = writer_result.get("generated_vertex_lineage", [])
        if raw_lineage is None:
            raw_lineage = []
        if not isinstance(raw_lineage, Sequence) or isinstance(raw_lineage, (str, bytes)):
            return _empty("writer_vertex_lineage_invalid", layers) | {
                "receipt_digest": digest,
                "candidate_digest": candidate_digest,
            }
        generated_id_set = {int(record["id"]) for record in generated_records}
        known_parent_ids = set(range(int(point_array.shape[0]))) | generated_id_set
        lineage_by_id: dict[int, dict[str, Any]] = {}
        for item in raw_lineage:
            if not isinstance(item, Mapping):
                return _empty("writer_vertex_lineage_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            row = dict(item)
            lineage_id = _int(row.get("id"))
            if lineage_id in generated_id_set or lineage_id in lineage_by_id:
                return _empty("writer_vertex_lineage_duplicate", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            source_edge_id = _int(row.get("source_edge_id"))
            source_face_id = _int(row.get("source_face_id"))
            layer = _int(row.get("layer"))
            parameter = _float(row.get("parameter"))
            if source_edge_id not in source_edge_ids or not 0 <= source_face_id < int(triangle_array.shape[0]):
                return _empty("writer_vertex_lineage_source_mismatch", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            if not 0 <= layer <= layers or not 0.0 < parameter < 1.0:
                return _empty("writer_vertex_lineage_geometry_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            if _text(row.get("source_wall_edge")) != str(source_edge_id):
                return _empty("writer_vertex_lineage_source_mismatch", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            parent_ids = row.get("parent_vertex_ids")
            if (
                not isinstance(parent_ids, Sequence)
                or isinstance(parent_ids, (str, bytes))
                or len(parent_ids) != 2
            ):
                return _empty("writer_vertex_lineage_parent_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            parent_tuple = (_int(parent_ids[0]), _int(parent_ids[1]))
            if parent_tuple[0] not in known_parent_ids or parent_tuple[1] not in known_parent_ids:
                return _empty("writer_vertex_lineage_parent_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            parameter_numerator = _int(row.get("parameter_numerator", -1))
            expected_count = count_by_group.get((source_edge_id, layer))
            parameter_denominator = _int(
                row.get("parameter_denominator", expected_count or subdivision_factor)
            )
            if (
                expected_count is None
                or parameter_denominator != expected_count
                or parameter_numerator <= 0
                or parameter_numerator >= parameter_denominator
                or abs(
                    parameter
                    - parameter_numerator / float(parameter_denominator)
                )
                > _TOL
            ):
                return _empty("writer_vertex_lineage_parameter_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            if _text(row.get("lineage_role")) != "subdivided_front_vertex":
                return _empty("writer_vertex_lineage_role_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            if not _text(row.get("target_receipt_digest")):
                return _empty("writer_vertex_lineage_receipt_missing", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            row.update(
                {
                    "id": lineage_id,
                    "source_edge_id": source_edge_id,
                    "source_face_id": source_face_id,
                    "layer": layer,
                    "parameter": parameter,
                    "parameter_numerator": parameter_numerator,
                    "parameter_denominator": parameter_denominator,
                    "parent_vertex_ids": list(parent_tuple),
                }
            )
            lineage_by_id[lineage_id] = row

        raw_point_updates = writer_result.get("point_updates", [])
        if raw_point_updates is None:
            raw_point_updates = []
        if not isinstance(raw_point_updates, Sequence) or isinstance(raw_point_updates, (str, bytes)):
            return _empty("writer_point_update_invalid", layers) | {
                "receipt_digest": digest,
                "candidate_digest": candidate_digest,
            }
        allowed_update_ids = generated_id_set | set(lineage_by_id)
        updates_by_id: dict[int, tuple[float, float, float]] = {}
        for item in raw_point_updates:
            if not isinstance(item, Mapping):
                return _empty("writer_point_update_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            update_id = _int(item.get("id"))
            if update_id not in allowed_update_ids or update_id in updates_by_id:
                return _empty("writer_point_update_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            coordinates = (
                _float(item.get("x")),
                _float(item.get("y")),
                _float(item.get("z")),
            )
            updates_by_id[update_id] = coordinates
        for lineage_id in lineage_by_id:
            if lineage_id not in updates_by_id:
                return _empty("writer_vertex_lineage_coordinate_missing", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
        for record in generated_records:
            coordinates = updates_by_id.get(int(record["id"]))
            if coordinates is not None:
                record["x"], record["y"], record["z"] = coordinates
        for lineage_id in sorted(lineage_by_id):
            lineage = lineage_by_id[lineage_id]
            x, y, z = updates_by_id[lineage_id]
            record = dict(lineage)
            record.update({"x": x, "y": y, "z": z})
            generated_records.append(record)

        raw_intervals = writer_result.get("interval_ledger", [])
        if raw_intervals is None:
            raw_intervals = []
        if not isinstance(raw_intervals, Sequence) or isinstance(raw_intervals, (str, bytes)):
            return _empty("writer_interval_ledger_invalid", layers) | {
                "receipt_digest": digest,
                "candidate_digest": candidate_digest,
            }
        interval_groups: dict[tuple[int, int], list[tuple[float, float, int]]] = {}
        for item in raw_intervals:
            if not isinstance(item, Mapping):
                return _empty("writer_interval_ledger_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            edge_id = _int(item.get("source_edge_id"))
            layer = _int(item.get("layer"))
            factor = _int(item.get("subdivision_factor"))
            t0 = _float(item.get("t0"))
            t1 = _float(item.get("t1"))
            interval_index = _int(item.get("interval_index"))
            t0_numerator = _int(item.get("t0_numerator", interval_index))
            t1_numerator = _int(item.get("t1_numerator", interval_index + 1))
            expected_count = count_by_group.get((edge_id, layer))
            denominator = _int(
                item.get("parameter_denominator", expected_count or subdivision_factor)
            )
            if (
                expected_count is None
                or not 0 <= layer <= layers
                or factor != expected_count
                or denominator != expected_count
                or t0_numerator != interval_index
                or t1_numerator != interval_index + 1
                or not 0.0 <= t0 < t1 <= 1.0
                or abs(t0 - t0_numerator / float(denominator)) > _TOL
                or abs(t1 - t1_numerator / float(denominator)) > _TOL
            ):
                return _empty("writer_interval_ledger_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            if _text(item.get("source_wall_edge")) != str(edge_id):
                return _empty("writer_interval_ledger_invalid", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            key = (edge_id, layer)
            rows = interval_groups.setdefault(key, [])
            if any(existing[2] == interval_index for existing in rows):
                return _empty("writer_interval_ledger_duplicate", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            rows.append((t0, t1, interval_index))
        expected_lineage_count = sum(
            max(0, count - 1) for count in count_by_group.values()
        )
        if len(lineage_by_id) != expected_lineage_count:
                return _empty("writer_vertex_lineage_coverage", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
        expected_interval_keys = {
            key for key, count in count_by_group.items() if count > 1
        }
        if set(interval_groups) != expected_interval_keys:
            return _empty("writer_interval_ledger_coverage", layers) | {
                "receipt_digest": digest,
                "candidate_digest": candidate_digest,
            }
        for rows in interval_groups.values():
            rows.sort(key=lambda value: (value[0], value[1], value[2]))
            key = next(
                key for key, candidate_rows in interval_groups.items()
                if candidate_rows is rows
            )
            if len(rows) != count_by_group[key] or abs(rows[0][0]) > _TOL or abs(rows[-1][1] - 1.0) > _TOL:
                return _empty("writer_interval_ledger_coverage", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            for left, right in zip(rows, rows[1:]):
                if abs(left[1] - right[0]) > _TOL:
                    return _empty("writer_interval_ledger_gap_or_overlap", layers) | {
                        "receipt_digest": digest,
                        "candidate_digest": candidate_digest,
                    }
        optimized_front_scale = _float(
            writer_result.get("optimized_front_scale", 1.0)
        )
        if optimized_front_scale <= 0.0:
            return _empty("writer_point_update_invalid", layers) | {
                "receipt_digest": digest,
                "candidate_digest": candidate_digest,
            }

        decisions = writer_result.get("diagonal_decisions", [])
        quality = (
            dict(writer_result.get("quality", {}))
            if planar_cavity_replacement
            else _quality_from_decisions(decisions)
        )
        if planar_cavity_replacement:
            audit = writer_result.get("independent_long_double_audit", {})
            if not isinstance(audit, Mapping) or audit.get("accepted") is not True:
                return _empty("writer_long_double_audit_missing", layers) | {
                    "receipt_digest": digest,
                    "candidate_digest": candidate_digest,
                }
            if strict_quality:
                for key, limit in (
                    ("max_skewness", 0.30),
                    ("max_aspect_ratio", 10.0 / 7.0),
                    ("max_non_orthogonality_degrees", 30.0),
                ):
                    if _float(audit.get(key)) > limit + _TOL:
                        return _empty("writer_long_double_strict_quality_failure", layers) | {
                            "receipt_digest": digest,
                            "candidate_digest": candidate_digest,
                        }
            quality["strict_triangle_aspect_derived_limit"] = 10.0 / 7.0
            quality["independent_long_double_audit"] = _jsonable(audit)
        output_snapshot = {
            "candidate_digest": candidate_digest,
            "generated_vertices": _jsonable(generated_records),
            "generated_faces": _jsonable(writer_result.get("generated_faces", [])),
            "provenance": _jsonable(writer_result.get("provenance", [])),
            "diagonal_decisions": _jsonable(decisions),
            "quality_witness": _jsonable(writer_result.get("quality_witness", [])),
            "point_updates": _jsonable(raw_point_updates),
            "generated_vertex_lineage": _jsonable(raw_lineage),
            "interval_ledger": _jsonable(raw_intervals),
            "count_ledger": _jsonable(raw_counts),
            "subdivision_factor": subdivision_factor,
            "optimized_front_scale": optimized_front_scale,
            "phase_offset": _float(writer_result.get("phase_offset", 0.0)),
            "independent_long_double_audit": _jsonable(
                writer_result.get("independent_long_double_audit", {})
            ),
            "strict_quality": bool(strict_quality),
        }
        result = dict(writer_result)
        result.update(
            {
                "accepted": True,
                "status": (
                    "surface_bl_front_target_field_planar_cavity_transaction_sealed"
                    if planar_cavity_replacement
                    else "surface_bl_front_target_field_transaction_sealed"
                ),
                "reason": (
                    "planar_cavity_replacement_writer_passed"
                    if planar_cavity_replacement
                    else "target_field_bound_strip_writer_passed"
                ),
                "requested_layers": layers,
                "actual_layers": layers,
                "generated_vertices": generated_records,
                "quality": quality,
                "receipt_digest": digest,
                "candidate_digest": candidate_digest,
                "output_digest": sha256(output_snapshot),
                "source_digest": source_digest,
                "source_authority_bound": True,
                "authority_checked": True,
                "direct_lineage": True,
                "shared_front": True,
                "receipt_consumed": True,
                "runtime_route": "default_off",
                "publication_eligible": False,
                "route_calls": 0,
                "transaction_atomic": True,
                "source_triangles_unchanged": not planar_cavity_replacement,
                "transaction_mode": "planar_cavity" if planar_cavity_replacement else "append_strip",
                "candidate_discarded": False,
                "count_is_report_only": True,
                "strict_quality": bool(strict_quality),
                "subdivision_factor": subdivision_factor,
            }
        )
        return result
    except Exception as exc:  # noqa: BLE001 - all malformed candidates fail closed
        return _empty(f"transaction_input_invalid:{type(exc).__name__}", int(requested_layers))


__all__ = ["transact_surface_wall_edge_target_field"]
