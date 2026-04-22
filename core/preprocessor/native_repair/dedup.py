"""중복 vertex 병합 + face 리인덱싱."""
from __future__ import annotations

import numpy as np


def dedup_vertices(
    vertices: np.ndarray, faces: np.ndarray, *, tol: float = 1e-9,
) -> tuple[np.ndarray, np.ndarray, int]:
    """좌표 grid 양자화로 중복 vertex 를 병합하고 face 를 리인덱싱.

    Args:
        vertices: (V, 3).
        faces: (F, 3) int.
        tol: 양자화 단위 (좌표를 round(x / tol) * tol 로 snap).

    Returns:
        (new_vertices, new_faces, n_merged).
    """
    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    if V.size == 0:
        return V.reshape(0, 3), F.reshape(0, 3) if F.size else F, 0

    scale = 1.0 / max(tol, 1e-30)
    keys = np.round(V * scale).astype(np.int64)
    _, unique_idx, inverse = np.unique(
        keys, axis=0, return_index=True, return_inverse=True,
    )
    # numpy >=2.0 에서는 inverse 가 (V, 1) 로 올 수 있어 평평화
    inverse = np.asarray(inverse, dtype=np.int64).reshape(-1)
    n_before = V.shape[0]
    new_V = V[unique_idx]
    n_merged = n_before - new_V.shape[0]
    if F.size == 0:
        return new_V, F, n_merged
    new_F = inverse[F].astype(np.int64).reshape(F.shape)
    return new_V, new_F, int(n_merged)
