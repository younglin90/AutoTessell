"""Actual STEP/BRep surface BL evidence-pack bridge.

The reader and BRep v2 evidence builder provide source authority. Python only
orchestrates the C++ ingress, optimizer, producer, transaction sealer, and
common atomic writer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.evaluator.native_evidence_pack_v2_writer import write_native_evidence_pack_v2
from core.evaluator.native_surface_bl_front_actual_v2_ingress import (
    validate_actual_brep_v2_ingress,
)
from core.evaluator.native_surface_bl_front_optimizer import (
    optimize_surface_wall_edge_front,
)
from core.evaluator.native_surface_bl_actual_transaction import (
    seal_authoritative_surface_bl_transaction,
)
from core.layers.native_tet_brep_front_evidence_v2 import build_brep_front_evidence_v2
from core.utils.native_extensions import import_native_extension


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping_digest(mapping: Sequence[Mapping[str, Any]]) -> str:
    raw = json.dumps([dict(row) for row in mapping], sort_keys=True, separators=(",", ":")).encode()
    return _digest(raw)


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


def _selected(mapping: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = [dict(row) for row in mapping if bool(row.get("selected_for_bl", False))]
    if len(selected) != 1:
        raise ValueError("actual_brep_surface_requires_one_selected_wall_edge")
    return selected[0]


def _normal_for_face(evidence: Mapping[str, Any], face_id: int) -> np.ndarray:
    for row in evidence["direction_records"]:
        if int(row["face_id"]) == face_id:
            return np.asarray(row["face_normal"], dtype=np.float64)
    raise ValueError("actual_brep_surface_source_normal_missing")


def _source_arrays(producer: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.ascontiguousarray(np.asarray(producer["points"], dtype=np.float64))
    source = np.ascontiguousarray(np.asarray(producer["source_triangles"], dtype=np.int64))
    candidate = np.ascontiguousarray(np.asarray(producer["triangles"], dtype=np.int64))
    normal = np.ascontiguousarray(np.asarray([producer["face_normal"]], dtype=np.float64))
    return points, source, candidate, normal


def write_actual_brep_surface_evidence_pack_v2(
    target_root: str | Path,
    source_path: str | Path,
    *,
    explicit_mapping: Sequence[Mapping[str, Any]],
    owner_face_by_edge: Mapping[int, int],
    requested_layers: int,
    first_height: float | None = None,
    growth_ratio: float = 1.0,
    domain_side_authority_fixture: bool = False,
) -> dict[str, Any]:
    source = Path(source_path)
    raw = source.read_bytes()
    raw_digest = _digest(raw)
    cad = load_cad_native_with_provenance(source, source.suffix.lower())
    evidence = build_brep_front_evidence_v2(
        cad, source_digest=raw_digest, owner_face_by_edge=owner_face_by_edge
    )
    if domain_side_authority_fixture:
        evidence["direction_records"] = [
            dict(row, domain_side_authority=True) for row in evidence["direction_records"]
        ]
    mapping = [dict(row) for row in explicit_mapping]
    if domain_side_authority_fixture and any(
        str(row.get("physical_group", "")) != "fluid-wall" for row in mapping
    ):
        return {
            "accepted": False,
            "reason": "actual_brep_fixture_physical_group_contract_failed",
            "authority_level": "L0_actual_brep_fixture",
            "publication_eligible": False,
            "candidate_discarded": True,
            "atomic_rollback": True,
        }
    mapping_digest = _mapping_digest(mapping)
    ingress = validate_actual_brep_v2_ingress(
        np.asarray(evidence["canonical_positions"], dtype=np.float64),
        evidence,
        mapping,
        requested_layers,
        raw_digest,
        mapping_digest,
    )
    if not ingress.get("accepted"):
        return {
            "accepted": False,
            "reason": "actual_brep_ingress_refused",
            "ingress": ingress,
            "publication_eligible": False,
            "candidate_discarded": True,
        }
    selected = _selected(mapping)
    selected_edge = next(
        row for row in evidence["edges"] if int(row["brep_edge_id"]) == int(selected["source_edge"])
    )
    endpoints = np.asarray(selected_edge["canonical_endpoints"], dtype=np.int64)
    positions = np.asarray(evidence["canonical_positions"], dtype=np.float64)
    edge_length = float(np.linalg.norm(positions[int(endpoints[1])] - positions[int(endpoints[0])]))
    height = edge_length if first_height is None else float(first_height)
    face_id = int(selected["source_face"])
    normals = _normal_for_face(evidence, face_id)
    edges = np.asarray(
        [[int(selected["source_edge"]), int(endpoints[0]), int(endpoints[1]), face_id]],
        dtype=np.int64,
    )
    patch_names = [str(selected["patch"])]
    feature_names = [str(selected["feature"])]
    groups = [str(selected["physical_group"])]
    certificate = dict(ingress["optimizer_ingress"]["source_certificate"])
    edge_provenance = [selected]
    producer_kernel = import_native_extension("native_surface_bl_front_actual_v2_producer")
    transactions: list[dict[str, Any]] = []
    optimizer_runs: list[dict[str, Any]] = []
    producer_runs: list[dict[str, Any]] = []
    for ordinal in range(1, 4):
        optimizer = optimize_surface_wall_edge_front(
            positions,
            edges,
            np.asarray([normals], dtype=np.float64),
            patch_names,
            feature_names,
            groups,
            requested_layers,
            height,
            growth_ratio,
            certificate,
            edge_provenance,
            max_metric_aspect_ratio=10.0,
        )
        optimizer_runs.append(optimizer)
        producer = dict(
            producer_kernel.produce_actual_brep_wall_strip_v1(
                positions,
                evidence,
                mapping,
                optimizer,
                int(requested_layers),
            )
        )
        if not producer.get("accepted"):
            return {
                "accepted": False,
                "reason": "actual_brep_producer_refused",
                "optimizer": optimizer,
                "producer": producer,
                "transactions": transactions,
                "publication_eligible": False,
                "candidate_discarded": True,
            }
        points, source_triangles, candidate, source_normals = _source_arrays(producer)
        generated = [
            {**dict(row), "side": "wall"} for row in producer["layer_records"]
        ]
        transaction = seal_authoritative_surface_bl_transaction(
            points,
            source_triangles,
            candidate,
            source_normals,
            {
                "source_kind": "cad_brep_v2",
                "source_sha256": raw_digest,
                "boundary_mapping_sha256": mapping_digest,
                "physical_group_sha256": evidence["source_metadata"]["xde_metadata_digest"],
                "provenance": evidence["seam_digest"],
            },
            producer,
            generated,
            requested_layers,
            source_provenance=[dict(row) for row in producer["source_provenance"]],
        )
        transactions.append(transaction)
        if not transaction.get("accepted"):
            return {
                "accepted": False,
                "reason": "actual_brep_surface_transaction_refused",
                "transaction": transaction,
                "transactions": transactions,
                "publication_eligible": False,
                "candidate_discarded": True,
            }
        producer_runs.append(producer)

    points, source_triangles, candidate, _ = _source_arrays(producer_runs[0])
    geometry = _geometry_bytes(points, candidate)
    source_geometry = _geometry_bytes(points[: len(positions)], source_triangles)
    runs = []
    producer_run_rows = []
    for ordinal, producer in enumerate(producer_runs, start=1):
        run_id = f"actual-brep-surface-{requested_layers}-{ordinal}"
        nonce = f"nonce-actual-brep-{requested_layers}-{ordinal}"
        runs.append(
            {
                "source_bytes": raw,
                "baseline_bytes": source_geometry,
                "output_bytes": geometry,
                "points": producer["points"],
                "triangles": producer["triangles"],
                "quads": [],
                "cells": [],
                "ledger": producer["ledger"],
                "boundary_binding": producer["boundary_binding"],
                "producer_run_id": run_id,
                "producer_run_nonce": nonce,
            }
        )
        producer_run_rows.append(
            {
                "run_id": run_id,
                "nonce": nonce,
                "output_sha256": _digest(geometry),
                "geometry_sha256": _digest(geometry),
            }
        )
    written = write_native_evidence_pack_v2(
        target_root,
        "surface",
        runs,
        requested_layers,
        requested_layers,
        producer_run_rows=producer_run_rows,
        layer_records=producer_runs[0]["layer_records"],
        authority_level="L0_actual_brep_fixture",
        authority_metadata={
            "canonical_positions_digest": evidence["canonical_positions_digest"],
            "face_ordinal_digest": evidence["face_ordinal_digest"],
            "orientation_digest": evidence["orientation_digest"],
            "seam_digest": evidence["seam_digest"],
            "mapping_digest": mapping_digest,
        },
    )
    return {
        **written,
        "ingress": ingress,
        "optimizer_runs": optimizer_runs,
        "producer_runs": producer_runs,
        "transactions": transactions,
        "source_digest": raw_digest,
        "mapping_digest": mapping_digest,
        "authority_level": "L0_actual_brep_fixture",
    }


__all__ = ["write_actual_brep_surface_evidence_pack_v2"]
