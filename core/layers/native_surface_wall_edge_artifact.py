"""Canonical, default-off surface wall-edge BL artifact contract."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

import numpy as np

from core.utils.native_extensions import import_native_extension

from .native_bl_atomic_certificate import canonical_bytes


_LINEAGE_FIELDS = (
    "source_wall_edge",
    "source_face",
    "side",
    "layer",
    "patch",
    "feature",
    "physical_group",
    "component",
    "provenance",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _geometry_digest(points: np.ndarray, triangles: np.ndarray) -> str:
    return _digest({"points": points.tolist(), "triangles": triangles.tolist()})


def _face_digest(triangles: np.ndarray) -> str:
    canonical = sorted(tuple(sorted(int(value) for value in row)) for row in triangles.tolist())
    return _digest(canonical)


def _refuse(reason: str, *, requested_layers: int, source_digest: str | None = None) -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "refused_rollback",
        "reason": reason,
        "requested_layers": requested_layers,
        "actual_layers": 0,
        "source_geometry_digest": source_digest,
        "runtime_route": "default_off",
    }


def _arrays(
    points: Any, triangles: Any
) -> tuple[np.ndarray, np.ndarray] | None:
    point_array = np.ascontiguousarray(np.asarray(points, dtype=np.float64))
    triangle_array = np.ascontiguousarray(np.asarray(triangles, dtype=np.int64))
    if point_array.ndim != 2 or point_array.shape[1:] != (3,):
        return None
    if triangle_array.ndim != 2 or triangle_array.shape[1:] != (3,):
        return None
    if not np.isfinite(point_array).all():
        return None
    if len(triangle_array) == 0 or np.any(triangle_array < 0) or np.any(triangle_array >= len(point_array)):
        return None
    return point_array, triangle_array


def build_surface_wall_edge_artifact(
    source_points: Any,
    source_triangles: Any,
    candidate_points: Any,
    candidate_triangles: Any,
    candidate_normals: Any,
    provenance: list[Mapping[str, Any]],
    wall_edges: list[str] | tuple[str, ...],
    *,
    requested_layers: int,
    authoritative_source: bool,
    source_labels: Any = None,
    candidate_labels: Any = None,
    volume_artifact: bool = False,
) -> dict[str, Any]:
    """Build evidence and refuse unless every applicable surface gate passes."""
    source = _arrays(source_points, source_triangles)
    candidate = _arrays(candidate_points, candidate_triangles)
    if requested_layers < 0:
        return _refuse("negative_layer_count", requested_layers=requested_layers)
    if source is None or candidate is None:
        return _refuse("invalid_surface_arrays", requested_layers=requested_layers)
    source_v, source_t = source
    candidate_v, candidate_t = candidate
    source_digest = _geometry_digest(source_v, source_t)
    candidate_digest = _geometry_digest(candidate_v, candidate_t)
    result: dict[str, Any] = {
        "schema": "NativeSurfaceWallEdgeBLArtifact/v1",
        "runtime_route": "default_off",
        "source_geometry_digest": source_digest,
        "candidate_geometry_digest": candidate_digest,
        "source_boundary_digest": _face_digest(source_t),
        "outer_front_boundary_digest": _face_digest(candidate_t),
        "requested_layers": requested_layers,
        "actual_layers": 0,
        "wall_edges": [str(edge) for edge in wall_edges],
        "authoritative_source": bool(authoritative_source),
    }
    if not authoritative_source:
        return {**result, **_refuse("missing_authoritative_source", requested_layers=requested_layers, source_digest=source_digest)}

    if requested_layers == 0:
        labels_equal = (
            (source_labels is None and candidate_labels is None)
            or (source_labels is not None and candidate_labels is not None and np.array_equal(source_labels, candidate_labels))
        )
        if not np.array_equal(source_v, candidate_v) or not np.array_equal(source_t, candidate_t) or not labels_equal:
            return {**result, **_refuse("bl0_identity_mismatch", requested_layers=0, source_digest=source_digest)}
        return {
            **result,
            "accepted": True,
            "status": "disabled_identity",
            "reason": "disabled_identity",
            "actual_layers": 0,
            "provenance_complete": True,
            "quality": None,
            "independent": None,
        }

    if not wall_edges:
        return {**result, **_refuse("empty_authoritative_wall_edge_set", requested_layers=requested_layers, source_digest=source_digest)}
    if not isinstance(provenance, list) or not provenance:
        return {**result, **_refuse("missing_surface_lineage", requested_layers=requested_layers, source_digest=source_digest)}
    if len(provenance) != len(candidate_t):
        return {**result, **_refuse("provenance_triangle_count_mismatch", requested_layers=requested_layers, source_digest=source_digest)}
    if not all(isinstance(item, Mapping) and all(item.get(field) is not None for field in _LINEAGE_FIELDS) for item in provenance):
        return {**result, **_refuse("incomplete_surface_lineage", requested_layers=requested_layers, source_digest=source_digest)}
    source_faces = {tuple(sorted(int(value) for value in row)) for row in source_t.tolist()}
    candidate_faces = {tuple(sorted(int(value) for value in row)) for row in candidate_t.tolist()}
    if not source_faces.issubset(candidate_faces):
        return {**result, **_refuse("source_faces_not_preserved", requested_layers=requested_layers, source_digest=source_digest)}
    edge_layers = {(str(item["source_wall_edge"]), int(item["layer"])) for item in provenance}
    missing = [
        (str(edge), layer)
        for edge in wall_edges
        for layer in range(1, requested_layers + 1)
        if (str(edge), layer) not in edge_layers
    ]
    if missing:
        return {**result, **_refuse("incomplete_requested_edge_layers", requested_layers=requested_layers, source_digest=source_digest)}
    try:
        independent = import_native_extension("native_surface_bl_independent_verifier")
        quality = import_native_extension("native_surface_bl_quality")
        independent_result = independent.verify_surface_artifact(
            candidate_v, candidate_t, np.ascontiguousarray(np.asarray(candidate_normals, dtype=np.float64)), provenance, True, volume_artifact
        )
        quality_result = quality.evaluate_surface_quality(
            candidate_v, candidate_t, np.ascontiguousarray(np.asarray(candidate_normals, dtype=np.float64)), provenance
        )
    except Exception as exc:  # noqa: BLE001
        return {**result, **_refuse(f"native_surface_gate_unavailable:{type(exc).__name__}", requested_layers=requested_layers, source_digest=source_digest)}
    accepted = independent_result.get("verdict") == "PASS_FOR_REVIEW" and quality_result.get("accepted") is True
    return {
        **result,
        "accepted": bool(accepted),
        "status": "committed" if accepted else "refused_rollback",
        "reason": "surface_gates_passed" if accepted else "independent_topology_or_quality_gate_failed",
        "actual_layers": requested_layers if accepted else 0,
        "independent": independent_result,
        "quality": quality_result,
        "provenance_complete": True,
    }


__all__ = ["build_surface_wall_edge_artifact"]
