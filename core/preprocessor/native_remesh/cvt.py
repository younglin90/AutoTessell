"""Lloyd CVT relaxation — 단순화된 Centroidal Voronoi Tessellation.

각 vertex 를 1-ring 인접 face 의 centroid (area-weighted) 로 이동시켜 정삼각형
근사와 균일 분포를 얻는다. 본 구현은 topology 변경 없음 — vertex 위치만 갱신.

옵션으로 원본 표면 KDTree 로 사영할 수 있다 (`original_surface` 인자).
"""
from __future__ import annotations

import numpy as np


def _face_centroids_areas(V: np.ndarray, F: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if F.size == 0:
        return np.zeros((0, 3)), np.zeros(0)
    v = V[F]
    centroids = v.mean(axis=1)
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    areas = 0.5 * np.linalg.norm(n, axis=1)
    return centroids, areas


def lloyd_cvt(
    vertices: np.ndarray, faces: np.ndarray,
    *,
    n_iter: int = 10,
    lam: float = 0.5,
    original_surface: tuple[np.ndarray, np.ndarray] | None = None,
) -> np.ndarray:
    """각 vertex 를 인접 face 의 area-weighted centroid 로 이동.

    Args:
        vertices: (V, 3).
        faces: (F, 3).
        n_iter: relaxation 반복 횟수.
        lam: 이동 강도 (0..1). 0.5 = 중간값으로.
        original_surface: (V_orig, F_orig) 표면 — 주어지면 매 iteration 후 vertex
            를 원본 surface 의 가장 가까운 점으로 사영 (geometric drift 방지).

    Returns:
        갱신된 vertices (F 는 변하지 않음).
    """
    V = np.asarray(vertices, dtype=np.float64).copy()
    F = np.asarray(faces, dtype=np.int64)
    if F.size == 0 or V.size == 0:
        return V

    # KDTree (옵션)
    tree = None
    orig_V = None
    if original_surface is not None:
        try:
            from core.utils.kdtree import NumpyKDTree  # noqa: PLC0415
            orig_V, _ = original_surface
            tree = NumpyKDTree(orig_V)
        except Exception:
            tree = None

    # Vectorized scatter: build (n_faces*3,) index and weight arrays once
    F_flat = F.ravel()  # shape (3*nF,)
    # For each face-vertex pair, the weight is the face area
    # We'll scatter-accumulate weighted centroids and total weights per vertex
    n_verts = V.shape[0]

    for _ in range(max(1, int(n_iter))):
        centroids, areas = _face_centroids_areas(V, F)
        # Each face contributes its area-weighted centroid to its 3 vertices
        # face_idx for each (face, local_vert) pair
        face_idx = np.repeat(np.arange(len(F), dtype=np.int64), 3)  # (3*nF,)
        w_flat = areas[face_idx]  # weight per (face, vert) pair

        w_centroids = centroids[face_idx] * w_flat[:, np.newaxis]  # (3*nF, 3)

        weighted_sum = np.zeros((n_verts, 3), dtype=np.float64)
        weight_total = np.zeros(n_verts, dtype=np.float64)
        np.add.at(weighted_sum, F_flat, w_centroids)
        np.add.at(weight_total, F_flat, w_flat)

        valid = weight_total > 1e-30
        target = np.where(valid[:, np.newaxis], weighted_sum / np.where(valid[:, np.newaxis], weight_total[:, np.newaxis], 1.0), V)
        V = V + lam * (target - V)

        if tree is not None and orig_V is not None:
            _, idx = tree.query(V, k=1)
            V = orig_V[idx]

    return V
