"""Narrow explicit STEPCAF/XDE authority ledger for the folded surface route."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import numpy as np


_PREFIXES = ("feature", "patch", "physical-group", "component")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=list).encode()
    ).hexdigest()


def _layer_value(layers: tuple[str, ...], prefix: str) -> str | None:
    marker = f"autotessell/{prefix}/"
    values = [value[len(marker):] for value in layers if value.startswith(marker)]
    return values[0] if len(values) == 1 and values[0] else None


def build_explicit_xde_folded_profile(cad: Any) -> dict[str, Any]:
    """Accept exactly two authoritative XDE faces with one shared B-Rep edge."""
    provenance = cad.provenance
    if provenance.face_count != 2:
        return {"accepted": False, "reason": "folded_xde_requires_two_brep_faces"}
    if not (
        provenance.face_ordinals_authoritative
        and provenance.face_orientation_authoritative
        and provenance.seam_connectivity_authoritative
        and provenance.xde_layer_authoritative
    ):
        return {"accepted": False, "reason": "folded_xde_authority_flags_incomplete"}
    triangle_ordinals = np.asarray(provenance.triangle_face_ordinals, dtype=np.int64)
    if triangle_ordinals.size != 2 or sorted(triangle_ordinals.tolist()) != [0, 1]:
        return {"accepted": False, "reason": "folded_xde_requires_one_triangle_per_face"}
    canonical_ids = np.asarray(provenance.canonical_vertex_source_ids, dtype=np.int64)
    canonical_faces = np.asarray(provenance.oriented_canonical_faces, dtype=np.int64)
    if canonical_ids.ndim != 1 or canonical_faces.shape != (2, 3):
        return {"accepted": False, "reason": "folded_xde_canonical_triangle_contract_missing"}
    positions = np.asarray(cad.vertices, dtype=np.float64)[canonical_ids]
    if not np.isfinite(positions).all() or np.unique(np.round(positions, 12), axis=0).shape[0] != positions.shape[0]:
        return {"accepted": False, "reason": "folded_xde_canonical_positions_invalid"}

    edge_faces: dict[int, set[int]] = {}
    for record in provenance.brep_edge_face_direction_records or ():
        edge_faces.setdefault(int(record["edge_id"]), set()).add(int(record["face_id"]))
    shared = sorted(edge_id for edge_id, faces in edge_faces.items() if faces == {0, 1})
    if len(shared) != 1:
        return {"accepted": False, "reason": "folded_xde_shared_edge_ambiguous", "shared_edge_candidates": shared}
    shared_edge = shared[0]
    edge_ids = np.asarray(provenance.triangle_brep_edge_ids, dtype=np.int64)
    if edge_ids.shape != (2, 3):
        return {"accepted": False, "reason": "folded_xde_triangle_edge_identity_missing"}
    raw_faces = np.asarray(cad.faces, dtype=np.int64)
    seam_ids = np.asarray(provenance.seam_vertex_ids, dtype=np.int64)
    ridge: tuple[int, int] | None = None
    for face_id in range(2):
        triangle_index = int(np.flatnonzero(triangle_ordinals == face_id)[0])
        raw_triangle = seam_ids[raw_faces[triangle_index]]
        matches = np.flatnonzero(edge_ids[triangle_index] == shared_edge)
        if matches.size != 1:
            return {"accepted": False, "reason": "folded_xde_shared_edge_face_binding_invalid", "face": face_id}
        index = int(matches[0])
        pair = (
            int(raw_triangle[index]),
            int(raw_triangle[(index + 1) % 3]),
        )
        if ridge is None:
            ridge = pair
        elif set(ridge) != set(pair):
            return {"accepted": False, "reason": "folded_xde_shared_edge_canonical_mismatch"}
    assert ridge is not None

    semantic_rows: list[dict[str, str]] = []
    for face_id, layers in enumerate(provenance.xde_layer_names):
        values = {prefix: _layer_value(tuple(layers), prefix) for prefix in _PREFIXES}
        if any(value is None for value in values.values()):
            return {
                "accepted": False,
                "reason": "folded_xde_explicit_semantic_mapping_incomplete",
                "face": face_id,
            }
        semantic_rows.append(
            {
                "source_edge": str(shared_edge),
                "source_face": str(face_id),
                "feature": str(values["feature"]),
                "patch": str(values["patch"]),
                "physical_group": str(values["physical-group"]),
                "component": str(values["component"]),
                "provenance": "stepcaf-xde-face-edge-ledger",
            }
        )

    normals: list[list[float]] = []
    for face in canonical_faces:
        a, b, c = positions[face]
        normal = np.cross(b - a, c - a)
        magnitude = float(np.linalg.norm(normal))
        if not magnitude or not np.isfinite(magnitude):
            return {"accepted": False, "reason": "folded_xde_face_normal_invalid"}
        normals.append((normal / magnitude).tolist())

    payload = {
        "canonical_positions": positions.tolist(),
        "canonical_triangles": canonical_faces.tolist(),
        "ridge_endpoints": list(ridge),
        "normals": normals,
        "semantic_rows": semantic_rows,
        "shared_edge": shared_edge,
        "source_face_count": int(provenance.face_count),
        "source_edge_count": int(provenance.topological_edge_count),
        "xde_metadata_sha256": provenance.xde_metadata_sha256,
        "seam_connectivity_sha256": provenance.seam_connectivity_sha256,
        "orientation_sha256": provenance.ordered_orientation_sha256,
    }
    return {
        "accepted": True,
        "profile": "NativeSurface/ExplicitSTEPCAF-XDE-FoldedPlate/v1",
        **payload,
        "source_geometry_sha256": _digest(np.asarray(cad.vertices, dtype=np.float64).tolist()),
        "source_triangle_sha256": _digest(np.asarray(cad.faces, dtype=np.int64).tolist()),
        "canonical_geometry_sha256": _digest(positions.tolist()),
        "canonical_triangle_sha256": _digest(canonical_faces.tolist()),
        "semantic_sha256": _digest(semantic_rows),
        "authority_sha256": _digest(payload),
    }


__all__ = ["build_explicit_xde_folded_profile"]
