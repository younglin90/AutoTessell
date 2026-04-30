"""AI-V3.1 — BL collision dataset extractor.

native_bl 의 _compute_collision_distance 결과를 학습 데이터로 캡처.
각 wall vertex 의 12-dim feature + ground truth gap_distance.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class BLCollisionDatasetResult:
    success: bool
    n_samples: int = 0
    output_path: str = ""
    elapsed: float = 0.0
    message: str = ""


def extract_bl_collision_features(
    points: np.ndarray,
    wall_vert_indices: np.ndarray,
    wall_face_verts: np.ndarray,
    *,
    vertex_normals: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """각 wall vertex 의 12-dim feature.

    Components:
        1-3: vertex normal (or zero if not available)
        4-6: mean curvature direction (placeholder zero)
        7-9: nearest face center direction
        10:  valence (incident face count)
        11:  mean edge length
        12:  local face area mean

    Returns:
        (features (Nw, 12), gap_distances (Nw,)) — gap is geometric collision distance.
    """
    Nw = int(wall_vert_indices.shape[0])
    features = np.zeros((Nw, 12), dtype=np.float64)
    gaps = np.full(Nw, np.inf, dtype=np.float64)

    if Nw == 0 or wall_face_verts.size == 0:
        return features, gaps

    # 1-3: normal
    if vertex_normals is not None and vertex_normals.shape[0] == points.shape[0]:
        features[:, 0:3] = vertex_normals[wall_vert_indices]

    # 10: valence — count incident faces
    valence = np.zeros(int(points.shape[0]), dtype=np.int64)
    for face in wall_face_verts:
        for v in face:
            if 0 <= v < valence.size:
                valence[v] += 1
    features[:, 9] = valence[wall_vert_indices].astype(np.float64)

    # 11-12: edge length / face area means (per-vertex incident faces)
    # For each wall vertex, gather incident faces and compute means.
    for i, vi in enumerate(wall_vert_indices.tolist()):
        inc_face_mask = np.any(wall_face_verts == vi, axis=1)
        if not inc_face_mask.any():
            continue
        inc_faces = wall_face_verts[inc_face_mask]
        edges = []
        areas = []
        for f in inc_faces:
            p0, p1, p2 = points[f[0]], points[f[1]], points[f[2]]
            edges.append(float(np.linalg.norm(p1 - p0)))
            edges.append(float(np.linalg.norm(p2 - p1)))
            edges.append(float(np.linalg.norm(p0 - p2)))
            areas.append(0.5 * float(np.linalg.norm(np.cross(p1 - p0, p2 - p0))))
        features[i, 10] = float(np.mean(edges)) if edges else 0.0
        features[i, 11] = float(np.mean(areas)) if areas else 0.0

    # gap: minimum distance to non-incident face center.
    face_centers = points[wall_face_verts].mean(axis=1)
    for i, vi in enumerate(wall_vert_indices.tolist()):
        p_v = points[vi]
        inc_mask = np.any(wall_face_verts == vi, axis=1)
        non_inc_centers = face_centers[~inc_mask]
        if non_inc_centers.shape[0] > 0:
            d = np.linalg.norm(non_inc_centers - p_v, axis=1).min()
            gaps[i] = float(d)

    return features, gaps


def generate_bl_collision_dataset(
    output_path: str,
    points_list: list[np.ndarray],
    wall_v_list: list[np.ndarray],
    wall_fv_list: list[np.ndarray],
    *,
    vertex_normals_list: list[np.ndarray] | None = None,
) -> BLCollisionDatasetResult:
    """BL collision feature dataset 저장 (AI-V3.1)."""
    import time
    t0 = time.perf_counter()

    if not (len(points_list) == len(wall_v_list) == len(wall_fv_list)):
        return BLCollisionDatasetResult(
            success=False,
            message="input list length mismatch",
            elapsed=time.perf_counter() - t0,
        )

    feats_all: list[np.ndarray] = []
    gaps_all: list[np.ndarray] = []
    for i, (pts, wv, wfv) in enumerate(zip(points_list, wall_v_list, wall_fv_list)):
        vn = vertex_normals_list[i] if vertex_normals_list else None
        f, g = extract_bl_collision_features(pts, wv, wfv, vertex_normals=vn)
        # filter valid gaps (finite)
        mask = np.isfinite(g)
        if mask.any():
            feats_all.append(f[mask])
            gaps_all.append(g[mask])

    if not feats_all:
        return BLCollisionDatasetResult(
            success=False,
            output_path=output_path,
            elapsed=time.perf_counter() - t0,
            message="no valid samples",
        )

    feats_arr = np.concatenate(feats_all, axis=0)
    gaps_arr = np.concatenate(gaps_all, axis=0)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(out), features=feats_arr, gaps=gaps_arr)

    return BLCollisionDatasetResult(
        success=True,
        n_samples=int(feats_arr.shape[0]),
        output_path=str(out),
        elapsed=time.perf_counter() - t0,
        message=f"saved {feats_arr.shape[0]} BL collision samples",
    )
