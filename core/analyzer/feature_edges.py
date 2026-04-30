"""L3 / beta2642 — geometry feature edge extraction.

Sharp dihedral edges + boundary edges + vertex-classification.
mesh_type 추천 / snap 후보 / sharp corner 점검 등에 활용.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class FeatureEdgeResult:
    n_feature_edges: int = 0
    n_boundary_edges: int = 0
    n_sharp_dihedral_edges: int = 0
    n_corner_vertices: int = 0      # >= 3 feature edge incident.
    feature_angle_deg: float = 30.0
    elapsed_s: float = 0.0
    edge_pairs: list[tuple[int, int]] | None = None


def extract_feature_edges(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    feature_angle_deg: float = 30.0,
    return_edges: bool = False,
) -> FeatureEdgeResult:
    """Sharp / boundary edge 추출.

    feature edge 정의:
        - boundary edge (1 incident face).
        - dihedral angle > feature_angle_deg between two adjacent face normals.

    Args:
        V: (N, 3) coords.
        F: (M, 3) tri indices.
        feature_angle_deg: dihedral threshold.
        return_edges: True 면 result.edge_pairs 에 (v0, v1) tuple list 반환.
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_f = int(F.shape[0])

    if n_f == 0:
        return FeatureEdgeResult(
            feature_angle_deg=feature_angle_deg,
            elapsed_s=time.perf_counter() - t0,
        )

    # face normals.
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    fn = np.cross(e1, e2)
    fn_len = np.linalg.norm(fn, axis=1, keepdims=True)
    fn = fn / np.maximum(fn_len, 1e-30)

    # edge → face adjacency.
    edges_per_face = np.stack([
        F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]],
    ], axis=1).reshape(-1, 2)
    edges_canon = np.sort(edges_per_face, axis=1)
    face_ids = np.arange(n_f, dtype=np.int64).repeat(3)
    ord_idx = np.lexsort((edges_canon[:, 1], edges_canon[:, 0]))
    sorted_edges = edges_canon[ord_idx]
    sorted_faces = face_ids[ord_idx]
    eq_prev = (
        np.diff(sorted_edges[:, 0]) != 0
    ) | (
        np.diff(sorted_edges[:, 1]) != 0
    )
    run_starts = np.concatenate(([0], np.where(eq_prev)[0] + 1))
    run_ends = np.concatenate((run_starts[1:], [len(sorted_edges)]))

    cos_thresh = float(np.cos(np.deg2rad(feature_angle_deg)))
    n_bnd = 0
    n_sharp = 0
    edge_pairs: list[tuple[int, int]] = []
    vert_feature_count: dict[int, int] = {}

    for s, e in zip(run_starts.tolist(), run_ends.tolist()):
        a = int(sorted_edges[s, 0])
        b = int(sorted_edges[s, 1])
        fl = sorted_faces[s:e].tolist()
        is_feature = False
        if len(fl) == 1:
            n_bnd += 1
            is_feature = True
        elif len(fl) == 2:
            cos_a = float(np.clip(np.dot(fn[fl[0]], fn[fl[1]]), -1.0, 1.0))
            if cos_a < cos_thresh:
                n_sharp += 1
                is_feature = True
        if is_feature:
            if return_edges:
                edge_pairs.append((a, b))
            vert_feature_count[a] = vert_feature_count.get(a, 0) + 1
            vert_feature_count[b] = vert_feature_count.get(b, 0) + 1

    n_corners = sum(1 for c in vert_feature_count.values() if c >= 3)
    n_feature = n_bnd + n_sharp

    return FeatureEdgeResult(
        n_feature_edges=n_feature,
        n_boundary_edges=n_bnd,
        n_sharp_dihedral_edges=n_sharp,
        n_corner_vertices=n_corners,
        feature_angle_deg=feature_angle_deg,
        elapsed_s=time.perf_counter() - t0,
        edge_pairs=edge_pairs if return_edges else None,
    )
