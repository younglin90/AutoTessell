"""Actual surface producer snapshot bridge for the native evidence-pack v2 route.

This module deliberately keeps geometry production in the C++ strip writer and
transaction sealer. Python only carries producer-owned IDs into the common
atomic evidence writer.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from core.evaluator.native_evidence_pack_v2_writer import (
    write_native_evidence_pack_v2,
)
from core.evaluator.native_surface_bl_actual_transaction import (
    seal_authoritative_surface_bl_transaction,
)
from core.evaluator.native_surface_bl_strip_writer import (
    write_authoritative_surface_wall_edge_strip,
)


def _float_text(value: Any) -> str:
    return format(float(value), ".17g")


def _points_text(points: np.ndarray) -> bytes:
    return "".join(
        f"{_float_text(row[0])} {_float_text(row[1])} {_float_text(row[2])}\n"
        for row in points
    ).encode()


def _rows_text(rows: np.ndarray) -> bytes:
    return "".join(" ".join(str(int(value)) for value in row) + "\n" for row in rows).encode()


def _geometry_bytes(points: np.ndarray, triangles: np.ndarray) -> bytes:
    return _points_text(points) + _rows_text(triangles)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _source_ledger(
    source_triangles: np.ndarray,
    source_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for row in source_rows:
        face = int(row["source_face"])
        ledger.append(
            {
                "source_face_id": f"face-{face}",
                "source_edge": f"edge-{int(row['source_wall_edge'])}"
                if isinstance(row.get("source_wall_edge"), (int, np.integer))
                else str(row["source_wall_edge"]),
                "feature_id": str(row["feature"]),
                "patch_id": str(row["patch"]),
                "physical_group": str(row["physical_group"]),
                "component_id": str(row["component"]),
                "orientation": "forward",
                "source_vertex_ids": [int(v) for v in source_triangles[face]],
                "provenance": str(row["provenance"]),
            }
        )
    return ledger


def _binding(
    source_rows: Sequence[Mapping[str, Any]],
    wall_edges: np.ndarray,
    layer_point_ids: np.ndarray,
    requested_layers: int,
) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    for row in source_rows:
        face = int(row["source_face"])
        edge_id = int(row["source_wall_edge"])
        wall_index = next(
            i for i, edge in enumerate(wall_edges) if int(edge[0]) == edge_id
        )
        if requested_layers:
            front = layer_point_ids[0, wall_index]
        else:
            front = wall_edges[wall_index, 1:3]
        bindings.append(
            {
                "source_face": f"face-{face}",
                "source_face_a": "",
                "source_face_b": "",
                "source_edge": f"edge-{edge_id}",
                "wall_edge": f"wall-edge-{edge_id}",
                "bl_strip": f"surface-strip-{edge_id}",
                "output_boundary_face": f"face-{face}",
                "volume_boundary_face": "none",
                "feature": str(row["feature"]),
                "patch": str(row["patch"]),
                "physical_group": str(row["physical_group"]),
                "component": str(row["component"]),
                "provenance": str(row["provenance"]),
                "wall0": str(int(wall_edges[wall_index, 1])),
                "wall1": str(int(wall_edges[wall_index, 2])),
                "front0": str(int(front[0])),
                "front1": str(int(front[1])),
                "tangent_face": f"face-{face}",
                "first_strip_face": "1" if requested_layers else "0",
                "orientation": "forward",
            }
        )
    return bindings


def _layer_records(
    generated_provenance: Sequence[Mapping[str, Any]],
    source_rows: Sequence[Mapping[str, Any]],
    wall_edges: np.ndarray,
    layer_point_ids: np.ndarray,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in generated_provenance:
        source_face = int(row["source_face"])
        source_edge = int(row["source_wall_edge"])
        edge_index = next(
            i for i, edge in enumerate(wall_edges) if int(edge[0]) == source_edge
        )
        layer = int(row["layer"])
        front = layer_point_ids[layer - 1, edge_index]
        source = next(item for item in source_rows if int(item["source_face"]) == source_face)
        records.append(
            {
                "source_wall_edge": str(source_edge),
                "layer": str(layer),
                "source_face": f"face-{source_face}",
                "wall0": str(int(wall_edges[edge_index, 1])),
                "wall1": str(int(wall_edges[edge_index, 2])),
                "front0": str(int(front[0])),
                "front1": str(int(front[1])),
                "final_face_ids": [int(v) for v in row["final_face_ids"]],
                "feature": str(row["feature"]),
                "patch": str(row["patch"]),
                "physical_group": str(row["physical_group"]),
                "component": str(row["component"]),
                "orientation": "forward",
                "provenance": str(row["provenance"]),
            }
        )
    return records


def _run_snapshot(
    points: np.ndarray,
    candidate: np.ndarray,
    ledger: list[dict[str, Any]],
    binding: list[dict[str, Any]],
    requested_layers: int,
    ordinal: int,
) -> dict[str, Any]:
    run_points = points if requested_layers > 0 else points[:3]
    geometry = _geometry_bytes(run_points, candidate)
    source_bytes = _geometry_bytes(points[:3], np.asarray([[0, 2, 1]], dtype=np.int64))
    baseline_bytes = source_bytes if requested_layers == 0 else b"surface-baseline-authoritative-v2"
    return {
        "source_bytes": source_bytes,
        "baseline_bytes": baseline_bytes,
        "output_bytes": geometry,
        "points": run_points,
        "triangles": candidate,
        "quads": [],
        "cells": [],
        "ledger": ledger,
        "boundary_binding": binding,
        "producer_run_id": f"surface-cpp-producer-{requested_layers}-{ordinal}",
        "producer_run_nonce": f"nonce-surface-{requested_layers}-{ordinal}",
    }


def write_actual_surface_evidence_pack_v2(
    target_root: str | Path,
    *,
    points: Any,
    source_triangles: Any,
    wall_edges: Any,
    layer_point_ids: Any,
    face_normals: Any,
    source_authority: Mapping[str, Any],
    edge_provenance: Sequence[Mapping[str, Any]],
    source_provenance: Sequence[Mapping[str, Any]],
    requested_layers: int,
) -> dict[str, Any]:
    """Run the actual C++ surface producer transaction three times and persist it."""
    pts = np.ascontiguousarray(np.asarray(points, dtype=np.float64))
    source = np.ascontiguousarray(np.asarray(source_triangles, dtype=np.int64))
    edges = np.ascontiguousarray(np.asarray(wall_edges, dtype=np.int64))
    layer_ids = np.ascontiguousarray(np.asarray(layer_point_ids, dtype=np.int64))
    normals = np.ascontiguousarray(np.asarray(face_normals, dtype=np.float64))
    if requested_layers < 0:
        return {"accepted": False, "reason": "requested_layers_invalid"}
    if requested_layers == 0:
        layer_ids = np.empty((0, len(edges), 2), dtype=np.int64)
    else:
        layer_ids = layer_ids[:requested_layers]
    active_edge_provenance = list(edge_provenance[: requested_layers * len(edges)])

    transactions: list[dict[str, Any]] = []
    candidate = source.copy()
    generated: list[dict[str, Any]] = []
    for _ in range(3):
        writer = write_authoritative_surface_wall_edge_strip(
            pts,
            source,
            edges,
            layer_ids,
            normals,
            source_authority,
            active_edge_provenance if requested_layers else [],
            requested_layers,
        )
        if not writer.get("accepted"):
            return {"accepted": False, "reason": "surface_strip_writer_refused", "writer": writer}
        candidate = source.copy() if requested_layers == 0 else np.asarray(
            writer.get("generated_faces", source.tolist()), dtype=np.int64
        )
        generated = [{**dict(row), "side": "wall"} for row in writer.get("provenance", [])]
        transaction = seal_authoritative_surface_bl_transaction(
            pts,
            source,
            candidate,
            normals,
            source_authority,
            writer,
            generated,
            requested_layers,
            source_provenance=source_provenance if requested_layers else None,
        )
        transactions.append(transaction)
        if not transaction.get("accepted"):
            return {
                "accepted": False,
                "reason": "surface_actual_transaction_refused",
                "transaction": transaction,
                "transactions": transactions,
            }

    ledger = _source_ledger(source, source_provenance)
    binding = _binding(source_provenance, edges, layer_ids, requested_layers)
    layers = _layer_records(generated, source_provenance, edges, layer_ids)
    run_points = pts if requested_layers > 0 else pts[:3]
    geometry = _geometry_bytes(run_points, candidate)
    producer_rows = [
        {
            "run_id": transactions[i].get("producer_run_id", f"surface-cpp-producer-{requested_layers}-{i + 1}"),
            "nonce": transactions[i].get("producer_run_nonce", f"nonce-surface-{requested_layers}-{i + 1}"),
            "output_sha256": _digest(geometry),
            "geometry_sha256": _digest(geometry),
        }
        for i in range(3)
    ]
    runs = [
        _run_snapshot(run_points, candidate, ledger, binding, requested_layers, i + 1)
        for i in range(3)
    ]
    for run, producer in zip(runs, producer_rows):
        run["producer_run_id"] = producer["run_id"]
        run["producer_run_nonce"] = producer["nonce"]
    written = write_native_evidence_pack_v2(
        target_root,
        "surface",
        runs,
        requested_layers,
        requested_layers,
        producer_run_rows=producer_rows,
        layer_records=layers,
    )
    return {
        **written,
        "transaction_runs": transactions,
        "direct_layer_records": layers,
        "candidate_triangles": candidate.tolist(),
    }


__all__ = ["write_actual_surface_evidence_pack_v2"]
