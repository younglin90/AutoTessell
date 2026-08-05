"""Explicit STEP/XDE semantic ledger for the restricted Native Hex proof route."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import numpy as np

from core.analyzer.readers.step import CadNativeTriangulation


_FEATURE = re.compile(r"^autotessell/feature/([^/]+)$")
_PATCH = re.compile(r"^autotessell/patch/([^/]+)$")
_GROUP = re.compile(r"^autotessell/physical-group/([^/]+)$")
_COMPONENT = re.compile(r"^autotessell/component/([^/]+)$")


def _digest(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_explicit_xde_hex_profile(cad: CadNativeTriangulation) -> dict[str, Any]:
    """Accept only a six-face, axis-aligned XDE box with explicit semantics.

    Generic STEP/XDE names and layers remain display metadata.  This function
    is the separate, opt-in contract that makes all four semantic namespaces
    explicit and suitable for the experimental Native Hex authority route.
    """
    provenance = cad.provenance
    if provenance.face_count != 6:
        return {"accepted": False, "reason": "explicit_xde_profile_requires_six_brep_faces"}
    if not provenance.face_ordinals_authoritative or not provenance.seam_connectivity_authoritative:
        return {"accepted": False, "reason": "brep_ordinal_or_seam_authority_missing"}
    rows: list[dict[str, Any]] = []
    for face_id in range(6):
        layers = tuple(provenance.xde_layer_names[face_id])
        feature_layers = [m.group(1) for value in layers if (m := _FEATURE.fullmatch(value))]
        feature_name = provenance.face_names[face_id]
        feature = _FEATURE.fullmatch(str(feature_name)) if feature_name is not None else None
        if feature is not None:
            feature_values = [feature.group(1)]
        else:
            feature_values = feature_layers
        patch = [m.group(1) for value in layers if (m := _PATCH.fullmatch(value))]
        group = [m.group(1) for value in layers if (m := _GROUP.fullmatch(value))]
        component = [m.group(1) for value in layers if (m := _COMPONENT.fullmatch(value))]
        if len(feature_values) != 1 or len(patch) != 1 or len(group) != 1 or len(component) != 1:
            return {"accepted": False, "reason": "explicit_feature_patch_group_component_contract_missing", "face": face_id}
        rows.append({
            "face_id": face_id,
            "feature": feature_values[0],
            "patch": patch[0],
            "physical_group": group[0],
            "component": component[0],
            "provenance": "stepcaf-xde-face-label",
        })
    if len({row["feature"] for row in rows}) != 6:
        return {"accepted": False, "reason": "feature_identity_not_unique"}
    if len({row["patch"] for row in rows}) != 6 or len({row["physical_group"] for row in rows}) != 6:
        return {"accepted": False, "reason": "boundary_or_physical_group_identity_not_unique"}

    canonical_ids = np.asarray(provenance.canonical_vertex_source_ids, dtype=np.int64)
    seam_ids = np.asarray(provenance.seam_vertex_ids, dtype=np.int64)
    if canonical_ids.ndim != 1 or canonical_ids.size != 8:
        return {"accepted": False, "reason": "explicit_xde_profile_requires_eight_canonical_corners"}
    positions = np.asarray(cad.vertices, dtype=np.float64)[canonical_ids]
    if np.unique(np.round(positions, 12), axis=0).shape[0] != 8:
        return {"accepted": False, "reason": "canonical_corner_positions_not_unique"}
    lo = positions.min(axis=0)
    hi = positions.max(axis=0)
    extent = hi - lo
    if np.any(extent <= 1.0e-12):
        return {"accepted": False, "reason": "degenerate_box_extent"}
    expected = {tuple(np.round(np.asarray([x, y, z]), 12)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])}
    actual = {tuple(np.round(row, 12)) for row in positions}
    if actual != expected:
        return {"accepted": False, "reason": "source_shape_is_not_axis_aligned_box"}
    triangle_face_ids = np.asarray(provenance.triangle_face_ordinals, dtype=np.int64)
    face_vertices: list[list[int]] = []
    for face_id in range(6):
        triangles = np.asarray(cad.faces[triangle_face_ids == face_id], dtype=np.int64)
        if triangles.size == 0:
            return {"accepted": False, "reason": "source_face_has_no_triangles", "face": face_id}
        unique = sorted({int(value) for value in triangles.reshape(-1)})
        mapped = [int(seam_ids[value]) for value in unique if 0 <= value < len(seam_ids)]
        if len(mapped) != 4:
            return {"accepted": False, "reason": "source_face_is_not_quad", "face": face_id}
        face_vertices.append(mapped)
    payload = {"rows": rows, "canonical_positions": positions.tolist(), "face_vertices": face_vertices}
    return {
        "accepted": True,
        "profile": "NativeHex/ExplicitSTEPCAF-XDE-Box/v1",
        "face_records": rows,
        "canonical_positions": positions.tolist(),
        "face_vertices": face_vertices,
        "feature_sha256": _digest([{**row, "value": row["feature"]} for row in rows]),
        "patch_sha256": _digest([{**row, "value": row["patch"]} for row in rows]),
        "physical_group_sha256": _digest([{**row, "value": row["physical_group"]} for row in rows]),
        "provenance_sha256": _digest(payload["rows"]),
    }


__all__ = ["build_explicit_xde_hex_profile"]
