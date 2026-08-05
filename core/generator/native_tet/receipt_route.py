"""Strict Native Tet surface-receipt read-back glue.

The hot-path geometry checks remain in the C++ extension.  This module only
maps the generator's returned point ids to the receipt's canonical ids and
passes the actual Tet boundary census to that extension.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


def _consumer() -> Any | None:
    try:
        return importlib.import_module("native_tet_surface_boundary_receipt_consumer")
    except Exception:
        build_dir = Path(__file__).resolve().parents[2] / ".." / "auto_tessell_core" / "build"
        build_dir = build_dir.resolve()
        if build_dir.is_dir() and str(build_dir) not in sys.path:
            sys.path.insert(0, str(build_dir))
        try:
            return importlib.import_module("native_tet_surface_boundary_receipt_consumer")
        except Exception:
            return None


def _boundary_faces(tets: np.ndarray) -> np.ndarray | None:
    if tets.ndim != 2 or tets.shape[1] != 4 or tets.shape[0] == 0:
        return None
    faces = np.concatenate(
        [tets[:, [0, 1, 2]], tets[:, [0, 1, 3]],
         tets[:, [0, 2, 3]], tets[:, [1, 2, 3]]],
        axis=0,
    )
    canonical = np.sort(faces, axis=1)
    unique, counts = np.unique(canonical, axis=0, return_counts=True)
    return np.asarray(unique[counts == 1], dtype=np.int64)


def verify_surface_receipt_output(
    receipt: Mapping[str, Any],
    result: Any,
    source_vertices: Any,
    source_faces: Any,
    requested_layers: int,
) -> dict[str, Any]:
    """Validate actual harness arrays against the sealed surface receipt.

    This is read-back evidence only.  It never marks the candidate publishable;
    atomic staging/commit and release corpus gates remain separate.
    """
    module = _consumer()
    if module is None:
        return {"accepted": False, "reason": "receipt_consumer_unavailable"}
    points = np.asarray(getattr(result, "tet_points", None), dtype=np.float64)
    tets = np.asarray(getattr(result, "tets", None), dtype=np.int64)
    source = np.asarray(source_vertices, dtype=np.float64)
    faces = np.asarray(source_faces, dtype=np.int64)
    if points.ndim != 2 or points.shape[1] != 3 or tets.ndim != 2 or tets.shape[1] != 4:
        return {"accepted": False, "reason": "tet_output_arrays_unavailable"}
    boundary = _boundary_faces(tets)
    if boundary is None:
        return {"accepted": False, "reason": "tet_output_boundary_unavailable"}
    interfaces = receipt.get("interface_triangles")
    if not isinstance(interfaces, list) or not interfaces:
        return {"accepted": False, "reason": "surface_receipt_interface_missing"}
    source_count = int(source.shape[0])
    if source.ndim != 2 or source.shape[1] != 3 or points.shape[0] < source_count:
        return {"accepted": False, "reason": "tet_output_source_identity_unavailable"}
    if not np.array_equal(points[:source_count], source):
        return {"accepted": False, "reason": "tet_output_source_prefix_identity_mismatch"}
    source_ids = list(range(source_count))

    output_interfaces: list[dict[str, Any]] = []
    binding: list[dict[str, Any]] = []
    for ordinal, raw in enumerate(interfaces):
        if not isinstance(raw, Mapping):
            return {"accepted": False, "reason": "surface_receipt_interface_row_invalid"}
        triangle = raw.get("triangle")
        if not isinstance(triangle, (list, tuple)) or len(triangle) != 3:
            return {"accepted": False, "reason": "surface_receipt_interface_triangle_invalid"}
        try:
            mapped = [source_ids[int(vertex)] for vertex in triangle]
        except (IndexError, TypeError, ValueError):
            return {"accepted": False, "reason": "surface_receipt_interface_source_id_invalid"}
        row = dict(raw)
        row["triangle"] = mapped
        output_interfaces.append(row)
        binding.append({
            "source_face": str(raw.get("source_face", "")),
            "output_face": str(raw.get("output_face", f"receipt-face-{ordinal}")),
            "volume_boundary_face": f"tet-boundary-{ordinal}",
            "volume_face_vertices": mapped,
            "feature": str(raw.get("feature", "")),
            "patch": str(raw.get("patch", "")),
            "physical_group": str(raw.get("physical_group", "")),
            "component": str(raw.get("component", "")),
            "provenance": str(raw.get("provenance", "")),
        })
    output_receipt = dict(receipt)
    output_receipt["interface_triangles"] = output_interfaces
    output_receipt["runtime_route"] = "native_tet_production_receipt"
    try:
        verified = dict(module.consume_surface_boundary_receipt(
            output_receipt, binding, boundary, int(requested_layers)
        ))
    except Exception as exc:
        return {"accepted": False, "reason": f"receipt_output_exception:{type(exc).__name__}"}
    verified["external_boundary_face_count"] = int(boundary.shape[0])
    verified["publication_eligible"] = False
    return verified
