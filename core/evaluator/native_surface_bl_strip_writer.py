"""Fail-closed adapter for the private authoritative surface BL strip writer."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from core.utils.native_extensions import import_native_extension
from core.evaluator.native_surface_release_route import admit_authoritative_surface_release


def _array(value: Any, dtype: Any, ndim: int, last_width: int | None = None) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(value, dtype=dtype))
    if result.ndim != ndim or (last_width is not None and result.shape[-1] != last_width):
        raise ValueError("native_surface_bl_strip_array_shape")
    return result


def write_authoritative_surface_wall_edge_strip(
    points: Any,
    source_triangles: Any,
    wall_edges: Any,
    layer_point_ids: Any,
    face_normals: Any,
    source_authority: Mapping[str, Any],
    edge_provenance: Sequence[Mapping[str, Any]],
    requested_layers: int,
) -> dict[str, Any]:
    """Write a quality-gated strip without publishing or changing the default route.

    The caller owns source and layer-point identity. The C++ writer may only emit
    source triangles unchanged plus direct-ID strip triangles, or return a refusal.
    """
    if requested_layers < 0:
        return {
            "accepted": False,
            "status": "surface_bl_actual_strip_writer_refused",
            "reason": "requested_layers_invalid",
            "candidate_discarded": True,
            "publication_eligible": False,
            "runtime_route": "private_default_off",
            "generated_faces": [],
            "provenance": [],
        }
    try:
        kernel = import_native_extension("native_surface_bl_strip_writer")
        result = dict(
            kernel.write_authoritative_surface_bl_strip(
                _array(points, np.float64, 2, 3),
                _array(source_triangles, np.int64, 2, 3),
                _array(wall_edges, np.int64, 2, 4),
                _array(layer_point_ids, np.int64, 3, 2),
                _array(face_normals, np.float64, 2, 3),
                dict(source_authority),
                [dict(item) for item in edge_provenance],
                int(requested_layers),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "surface_bl_actual_strip_writer_refused",
            "reason": f"native_surface_bl_strip_writer_unavailable:{type(exc).__name__}",
            "candidate_discarded": True,
            "publication_eligible": False,
            "runtime_route": "private_default_off",
            "generated_faces": [],
            "provenance": [],
        }
    result["runtime_route"] = "private_default_off"
    result["publication_eligible"] = False
    return result


def write_authoritative_surface_wall_edge_planar_cavity(
    points: Any,
    source_triangles: Any,
    wall_edges: Any,
    layer_point_ids: Any,
    face_normals: Any,
    source_authority: Mapping[str, Any],
    edge_provenance: Sequence[Mapping[str, Any]],
    requested_layers: int,
    strict_quality: bool = False,
) -> dict[str, Any]:
    """Replace one certified planar source cavity with a quality-gated BL patch."""
    if requested_layers < 0:
        return {
            "accepted": False,
            "status": "surface_bl_planar_cavity_writer_refused",
            "reason": "requested_layers_invalid",
            "candidate_discarded": True,
            "publication_eligible": False,
            "generated_faces": [],
            "provenance": [],
        }
    try:
        kernel = import_native_extension("native_surface_bl_strip_writer")
        result = dict(
            kernel.write_authoritative_surface_bl_planar_cavity(
                _array(points, np.float64, 2, 3),
                _array(source_triangles, np.int64, 2, 3),
                _array(wall_edges, np.int64, 2, 4),
                _array(layer_point_ids, np.int64, 3, 2),
                _array(face_normals, np.float64, 2, 3),
                dict(source_authority),
                [dict(item) for item in edge_provenance],
                int(requested_layers),
                1.0e-12,
                bool(strict_quality),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "surface_bl_planar_cavity_writer_refused",
            "reason": f"native_surface_bl_planar_cavity_writer_unavailable:{type(exc).__name__}",
            "candidate_discarded": True,
            "publication_eligible": False,
            "generated_faces": [],
            "provenance": [],
        }
    result["runtime_route"] = "private_default_off"
    result["publication_eligible"] = False
    result["strict_quality"] = bool(strict_quality)
    return result


def write_authoritative_surface_wall_edge_release_candidate(
    points: Any,
    source_triangles: Any,
    wall_edges: Any,
    layer_point_ids: Any,
    face_normals: Any,
    source_authority: Mapping[str, Any],
    edge_provenance: Sequence[Mapping[str, Any]],
    requested_layers: int,
    *,
    parameter_digest: str | None,
    packaging_receipt: Mapping[str, Any] | None,
    explicit_route: bool = False,
) -> dict[str, Any]:
    """Run the real C++ writer, then apply the release authority gate.

    The writer remains a private/default-off product today. This adapter is
    deliberately incapable of upgrading that result by itself; it returns the
    writer receipt alongside the gate refusal for durable evidence.
    """
    candidate = write_authoritative_surface_wall_edge_strip(
        points, source_triangles, wall_edges, layer_point_ids, face_normals,
        source_authority, edge_provenance, requested_layers,
    )
    normalized = dict(candidate)
    normalized.setdefault("actual_layers", requested_layers if candidate.get("accepted") else 0)
    normalized.setdefault("source_authority_bound", bool(candidate.get("accepted")))
    normalized.setdefault("authority_checked", bool(candidate.get("accepted")))
    normalized.setdefault("transaction_atomic", True)
    admission = admit_authoritative_surface_release(
        normalized,
        source_certificate=source_authority,
        parameter_digest=parameter_digest,
        packaging_receipt=packaging_receipt,
        requested_layers=requested_layers,
        explicit_route=explicit_route,
    )
    admission["writer_candidate"] = normalized
    return admission


__all__ = [
    "write_authoritative_surface_wall_edge_strip",
    "write_authoritative_surface_wall_edge_planar_cavity",
    "write_authoritative_surface_wall_edge_release_candidate",
]
