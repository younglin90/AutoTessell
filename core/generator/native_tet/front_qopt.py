"""Python orchestration for the C++ native Tet wall-front qopt kernel."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from core.layers.native_bl import _write_points
from core.utils.native_extensions import import_native_extension
from core.utils.polymesh_reader import parse_foam_points


def optimize_actual_tet_wall_front(
    case_dir: Path,
    *,
    authority: dict[str, Any],
    requested_layers: int,
    max_iterations: int = 8,
    correction_cap: float = 0.25,
) -> dict[str, Any]:
    if requested_layers == 0:
        return {
            "accepted": True,
            "status": "native_tet_bl_front_qopt_bl0_identity",
            "candidate_discarded": False,
        }
    if authority.get("source_authority_status") != "SOURCE_VERIFIED" or authority.get("provisional") is True:
        return {
            "accepted": False,
            "reason": "native_tet_bl_front_qopt_unavailable:authority_unsealed",
            "candidate_discarded": True,
        }

    lineage_path = case_dir / "native_bl_lineage.json"
    poly_dir = case_dir / "constant" / "polyMesh"
    if not lineage_path.is_file():
        return {
            "accepted": False,
            "reason": "native_tet_bl_front_qopt_unavailable:wall_sector_incomplete",
            "candidate_discarded": True,
        }
    lineage = json.loads(lineage_path.read_text())
    records = lineage.get("records", [])
    if not records:
        return {
            "accepted": False,
            "reason": "native_tet_bl_front_qopt_unavailable:wall_sector_incomplete",
            "candidate_discarded": True,
        }

    points = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    global_ids: dict[int, int] = {}
    wall_ids: list[int] = []
    for rec in records:
        layer_ids = rec.get("layer_point_ids", [])
        if len(layer_ids) < 2 or any(len(row) != 3 for row in layer_ids):
            return {
                "accepted": False,
                "reason": "native_tet_bl_front_qopt_unavailable:wall_sector_incomplete",
                "candidate_discarded": True,
            }
        for value in layer_ids[0]:
            iv = int(value)
            if iv not in global_ids:
                global_ids[iv] = len(wall_ids)
                wall_ids.append(iv)
    local_of = global_ids
    wall = points[wall_ids].copy()
    front = np.zeros_like(wall)
    seen_front: set[int] = set()
    for rec in records:
        layer_ids = rec["layer_point_ids"]
        for wall_id, front_id in zip(layer_ids[0], layer_ids[-1], strict=True):
            wi = local_of[int(wall_id)]
            fi = int(front_id)
            if fi < 0 or fi >= len(points):
                return {
                    "accepted": False,
                    "reason": "native_tet_bl_front_qopt_unavailable:final_point_id_unresolved",
                    "candidate_discarded": True,
                }
            if wi in seen_front and not np.allclose(front[wi], points[fi]):
                return {
                    "accepted": False,
                    "reason": "native_tet_bl_front_qopt_unavailable:wall_sector_incomplete",
                    "candidate_discarded": True,
                }
            front[wi] = points[fi]
            seen_front.add(wi)

    edge_rows: list[list[int]] = []
    normals: list[list[float]] = []
    feature_names: list[str] = []
    patch_names: list[str] = []
    physical_groups: list[str] = []
    components: list[str] = []
    for face_index, rec in enumerate(records):
        layer_ids = rec["layer_point_ids"][0]
        local = [local_of[int(value)] for value in layer_ids]
        front_ids = [int(value) for value in rec["layer_point_ids"][-1]]
        try:
            normal = np.cross(points[front_ids[1]] - points[front_ids[0]], points[front_ids[2]] - points[front_ids[0]])
            normal = normal / np.linalg.norm(normal)
        except (IndexError, ValueError, FloatingPointError):
            return {
                "accepted": False,
                "reason": "native_tet_bl_front_qopt_unavailable:normal_cone_empty",
                "candidate_discarded": True,
            }
        if not np.all(np.isfinite(normal)):
            return {
                "accepted": False,
                "reason": "native_tet_bl_front_qopt_unavailable:normal_cone_empty",
                "candidate_discarded": True,
            }
        normals.append(normal.tolist())
        meta = {}
        source_records = authority.get("source_face_records", {})
        if isinstance(source_records, dict):
            meta = source_records.get(str(rec.get("source_face")), source_records.get(int(rec.get("source_face", -1)), {})) or {}
        feature_names.append(str(meta.get("feature", authority.get("feature", "native_tet_wall"))))
        patch_names.append(str(meta.get("patch", authority.get("patch", "wall"))))
        physical_groups.append(str(meta.get("physical_group", authority.get("physical_group", "fluid"))))
        components.append(str(meta.get("component", authority.get("component", "main"))))
        for edge_index, (a, b) in enumerate(((0, 1), (1, 2), (2, 0))):
            edge_rows.append([
                local[a], local[b], face_index,
                int(rec.get("source_face", 0)) * 3 + edge_index,
            ])

    try:
        module = import_native_extension("native_tet_bl_front_qopt")
        result = dict(module.optimize_native_tet_wall_front(
            wall, front, np.asarray(edge_rows, dtype=np.int64),
            np.asarray(normals, dtype=float), feature_names, patch_names,
            physical_groups, components, int(requested_layers),
            int(max_iterations), float(correction_cap), 1e-10,
        ))
    except Exception as exc:
        return {
            "accepted": False,
            "reason": "native_tet_bl_front_qopt_unavailable:kernel_error:" + type(exc).__name__,
            "candidate_discarded": True,
        }
    if not result.get("accepted"):
        return result

    corrections = np.asarray(result["corrections"], dtype=float)
    for rec in records:
        layer_ids = rec["layer_point_ids"]
        for layer_index, row in enumerate(layer_ids):
            fraction = 1.0 - (float(layer_index) / float(len(layer_ids) - 1))
            for point_id, wall_id in zip(row, layer_ids[0], strict=True):
                local_index = local_of[int(wall_id)]
                points[int(point_id)] += corrections[local_index] * fraction
    _write_points(poly_dir / "points", points)
    (case_dir / "native_tet_bl_qopt.json").write_text(
        json.dumps({
            "schema": "native-tet-bl-front-qopt/v1",
            "quality": result.get("quality", {}),
            "requested_layers": int(requested_layers),
            "wall_vertex_count": len(wall_ids),
            "edge_count": len(edge_rows),
        }, sort_keys=True, separators=(",", ":")) + "\n"
    )
    return result
