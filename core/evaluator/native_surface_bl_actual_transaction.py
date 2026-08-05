"""Default-off actual surface BL authority transaction adapter."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

import numpy as np

from core.layers.native_bl_atomic_certificate import canonical_bytes
from core.utils.native_extensions import import_native_extension


def _array(value: Any, dtype: Any, ndim: int, width: int) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(value, dtype=dtype))
    if result.ndim != ndim or result.shape[-1] != width:
        raise ValueError("native_surface_bl_transaction_array_shape")
    return result


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _unit_normals(points: np.ndarray, faces: np.ndarray) -> np.ndarray:
    result = np.empty((len(faces), 3), dtype=np.float64)
    for i, face in enumerate(faces):
        a, b, c = (points[int(index)] for index in face)
        normal = np.cross(b - a, c - a)
        length = float(np.linalg.norm(normal))
        if not length:
            raise ValueError("native_surface_bl_transaction_degenerate_face")
        result[i] = normal / length
    return result


def seal_authoritative_surface_bl_transaction(
    points: Any,
    source_triangles: Any,
    candidate_triangles: Any,
    source_normals: Any,
    source_authority: Mapping[str, Any],
    writer_receipt: Mapping[str, Any],
    generated_provenance: Sequence[Mapping[str, Any]],
    requested_layers: int,
    *,
    source_provenance: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bind writer output to authority and independent gates without publishing.

    The C++ sealer owns source-prefix, direct-ID, and topology checks. Python only
    adapts arrays and combines independent receipts into a canonical candidate.
    """
    source_points = _array(points, np.float64, 2, 3)
    source_faces = _array(source_triangles, np.int64, 2, 3)
    candidate_faces = _array(candidate_triangles, np.int64, 2, 3)
    normals = _array(source_normals, np.float64, 2, 3)
    if requested_layers < 0:
        return {
            "accepted": False,
            "status": "surface_bl_actual_transaction_refused",
            "reason": "requested_layers_invalid",
            "candidate_discarded": True,
            "publication_eligible": False,
            "runtime_route": "private_default_off",
        }

    try:
        sealer = import_native_extension("native_surface_bl_actual_transaction")
        transaction = dict(
            sealer.seal_surface_bl_actual_transaction(
                source_points,
                source_faces,
                candidate_faces,
                normals,
                dict(source_authority),
                dict(writer_receipt),
                [dict(item) for item in generated_provenance],
                int(requested_layers),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "surface_bl_actual_transaction_refused",
            "reason": f"native_surface_bl_actual_transaction_unavailable:{type(exc).__name__}",
            "candidate_discarded": True,
            "publication_eligible": False,
            "runtime_route": "private_default_off",
        }
    if not transaction.get("accepted"):
        transaction["runtime_route"] = "private_default_off"
        transaction["publication_eligible"] = False
        return transaction

    if requested_layers == 0:
        digest = _digest({"points": source_points.tolist(), "triangles": source_faces.tolist()})
        return {
            **transaction,
            "schema": "NativeSurfaceWallEdgeBLArtifact/v2",
            "accepted": True,
            "artifact_digest": digest,
            "source_geometry_digest": digest,
            "candidate_geometry_digest": digest,
            "authority_digest": _digest(dict(source_authority)),
            "writer_digest": _digest(dict(writer_receipt)),
            "independent": None,
            "quality": None,
            "publication_eligible": False,
            "runtime_route": "private_default_off",
        }

    source_rows = [dict(row) for row in (source_provenance or [])]
    if len(source_rows) != len(source_faces):
        transaction["accepted"] = False
        transaction["status"] = "surface_bl_actual_transaction_refused"
        transaction["reason"] = "source_lineage_length_mismatch"
        transaction["candidate_discarded"] = True
        return transaction
    generated_rows = [dict(row) for row in generated_provenance]
    independent_generated_rows = []
    for row in generated_rows:
        for final_face_id in row.get("final_face_ids", ()):
            expanded = dict(row)
            expanded["final_face_id"] = int(final_face_id)
            independent_generated_rows.append(expanded)
    full_provenance = source_rows + independent_generated_rows
    if any("side" not in row for row in full_provenance):
        transaction["accepted"] = False
        transaction["status"] = "surface_bl_actual_transaction_refused"
        transaction["reason"] = "independent_lineage_side_missing"
        transaction["candidate_discarded"] = True
        return transaction
    try:
        candidate_normals = np.vstack(
            [normals, _unit_normals(source_points, candidate_faces[len(source_faces) :])]
        )
        independent_kernel = import_native_extension("native_surface_bl_independent_verifier")
        quality_kernel = import_native_extension("native_surface_bl_quality")
        independent = dict(
            independent_kernel.verify_surface_artifact(
                source_points,
                candidate_faces,
                candidate_normals,
                full_provenance,
                True,
                False,
            )
        )
        generated_faces = candidate_faces[len(source_faces) :]
        generated_normals = candidate_normals[len(source_faces) :]
        source_quality = dict(
            quality_kernel.evaluate_surface_quality(
                source_points,
                source_faces,
                normals,
                source_rows,
            )
        )
        quality = dict(
            quality_kernel.evaluate_surface_quality(
                source_points,
                generated_faces,
                generated_normals,
                independent_generated_rows,
            )
        )
        quality["source_quality"] = source_quality
    except Exception as exc:  # noqa: BLE001
        transaction["accepted"] = False
        transaction["status"] = "surface_bl_actual_transaction_refused"
        transaction["reason"] = f"independent_surface_gate_unavailable:{type(exc).__name__}"
        transaction["candidate_discarded"] = True
        return transaction

    quality_data = quality.get("quality", {})
    skew = quality_data.get("skewness", {})
    nonorth = quality_data.get("non_orthogonality", {})
    aspect = quality_data.get("metric_aspect_ratio", {})
    quality_ok = (
        quality.get("accepted") is True
        and float(skew.get("p95", float("inf"))) <= 0.30
        and float(skew.get("p99", float("inf"))) <= 0.40
        and float(skew.get("max", float("inf"))) <= 0.50
        and float(nonorth.get("p95", float("inf"))) <= 35.0
        and float(nonorth.get("p99", float("inf"))) <= 50.0
        and float(nonorth.get("max", float("inf"))) <= 75.0
        and float(aspect.get("p95", float("inf"))) <= 3.0
        and float(aspect.get("p99", float("inf"))) <= 5.0
        and float(aspect.get("max", float("inf"))) <= 10.0
    )
    accepted = independent.get("verdict") == "PASS_FOR_REVIEW" and quality_ok
    payload = {
        "schema": "NativeSurfaceWallEdgeBLArtifact/v2",
        "source_geometry": {"points": source_points.tolist(), "triangles": source_faces.tolist()},
        "candidate_triangles": candidate_faces.tolist(),
        "authority": dict(source_authority),
        "writer": dict(writer_receipt),
        "transaction": transaction,
        "independent": independent,
        "quality": quality,
        "provenance": full_provenance,
    }
    result = {
        **transaction,
        "accepted": bool(accepted),
        "status": "surface_bl_actual_artifact_sealed" if accepted else "surface_bl_actual_transaction_refused",
        "reason": "authority_topology_quality_gates_passed" if accepted else "independent_topology_or_quality_gate_failed",
        "candidate_discarded": not accepted,
        "publication_eligible": False,
        "runtime_route": "private_default_off",
        "independent": independent,
        "quality": quality,
        "provenance": generated_rows,
        "artifact_digest": _digest(payload),
        "source_geometry_digest": _digest(payload["source_geometry"]),
        "candidate_geometry_digest": _digest({"points": source_points.tolist(), "triangles": candidate_faces.tolist()}),
        "authority_digest": _digest(dict(source_authority)),
        "writer_digest": _digest(dict(writer_receipt)),
    }
    return result


__all__ = ["seal_authoritative_surface_bl_transaction"]
