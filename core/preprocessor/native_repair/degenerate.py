"""퇴화된 삼각형 제거 (면적 작음 + 중복 face)."""
from __future__ import annotations

import numpy as np


def _face_areas(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    if F.size == 0:
        return np.zeros(0)
    v = V[F]
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    return 0.5 * np.linalg.norm(n, axis=1)


def remove_degenerate_faces(
    vertices: np.ndarray, faces: np.ndarray,
    *, area_tol: float = 1e-18,
) -> tuple[np.ndarray, int]:
    """삼각형 면적 < area_tol 또는 중복된 face 를 제거.

    중복 판정은 vertex set 동일성 기준 (정렬된 tuple 이 같으면 중복).

    Returns:
        (new_faces, n_removed).
    """
    F = np.asarray(faces, dtype=np.int64)
    if F.size == 0:
        return F, 0

    V = np.asarray(vertices, dtype=np.float64)
    areas = _face_areas(V, F)
    keep_area = areas >= area_tol

    # dedupe by sorted vertex tuple — axis=0 로 직접 (numpy >=1.13)
    sorted_F = np.sort(F, axis=1)
    _, first_idx = np.unique(sorted_F, axis=0, return_index=True)
    keep_unique = np.zeros(F.shape[0], dtype=bool)
    keep_unique[first_idx] = True

    keep = keep_area & keep_unique
    new_F = F[keep]
    return new_F, int(F.shape[0] - new_F.shape[0])
