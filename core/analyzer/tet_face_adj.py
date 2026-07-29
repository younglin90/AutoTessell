"""X1 / beta2723 — Tet face adjacency map.

각 tet 의 4 face 에 대해 인접 tet (또는 -1 = boundary) 를 찾는다.
swap operation / boundary detection / mesh traversal 의 기반.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        build_tet_face_adjacency_stats as _c_build_tet_face_adjacency_stats,
    )
except Exception:  # pragma: no cover - optional native extension
    _c_build_tet_face_adjacency_stats = None


@dataclass
class TetFaceAdjResult:
    n_tets: int = 0
    n_faces_total: int = 0       # T*4 (with double count).
    n_unique_faces: int = 0
    n_boundary_faces: int = 0    # 1 incident tet.
    n_interior_faces: int = 0    # 2 incident tets.
    n_nonmanifold: int = 0       # 3+ tets — 비정상.
    elapsed_s: float = 0.0


# tet 의 4 face: vertex 인덱스 (sorted asc).
_TET_FACES = np.array([
    [1, 2, 3], [0, 2, 3], [0, 1, 3], [0, 1, 2],
], dtype=np.int64)


def build_tet_face_adjacency(
    tets: NDArray[np.int64],
) -> tuple[NDArray[np.int64], TetFaceAdjResult]:
    """tet → adjacent tet per face.

    Returns:
        (adj (T, 4) int64, result).  adj[i, f] = j tet 인덱스 (boundary 시 -1).
    """
    import time
    t0 = time.perf_counter()

    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])
    if n_t == 0:
        return np.zeros((0, 4), dtype=np.int64), TetFaceAdjResult(
            elapsed_s=time.perf_counter() - t0,
        )

    if _c_build_tet_face_adjacency_stats is not None:
        native = _c_build_tet_face_adjacency_stats(tets)
        if native is not None:
            adj, stats = native
            n_unique, n_bnd, n_int, n_nm = stats
            return adj, TetFaceAdjResult(
                n_tets=n_t,
                n_faces_total=n_t * 4,
                n_unique_faces=n_unique,
                n_boundary_faces=n_bnd,
                n_interior_faces=n_int,
                n_nonmanifold=n_nm,
                elapsed_s=time.perf_counter() - t0,
            )

    # build (n_t * 4, 3) face array (sorted), with (tet_idx, face_idx) tag.
    all_faces = np.zeros((n_t * 4, 3), dtype=np.int64)
    tags = np.zeros((n_t * 4, 2), dtype=np.int64)
    for fi in range(4):
        v = tets[:, _TET_FACES[fi]]
        all_faces[fi * n_t : (fi + 1) * n_t] = np.sort(v, axis=1)
        tags[fi * n_t : (fi + 1) * n_t, 0] = np.arange(n_t)
        tags[fi * n_t : (fi + 1) * n_t, 1] = fi

    # group by sorted face.
    keys = all_faces.view([("a", "i8"), ("b", "i8"), ("c", "i8")]).reshape(-1)
    sort_idx = np.argsort(keys, kind="stable")
    keys_s = keys[sort_idx]
    tags_s = tags[sort_idx]

    adj = -np.ones((n_t, 4), dtype=np.int64)

    n_unique = 0
    n_bnd = 0
    n_int = 0
    n_nm = 0

    i = 0
    n_faces = keys_s.shape[0]
    while i < n_faces:
        j = i
        while j < n_faces and keys_s[j] == keys_s[i]:
            j += 1
        cnt = j - i
        n_unique += 1
        if cnt == 1:
            n_bnd += 1
        elif cnt == 2:
            n_int += 1
            t0_idx, f0 = int(tags_s[i, 0]), int(tags_s[i, 1])
            t1_idx, f1 = int(tags_s[i + 1, 0]), int(tags_s[i + 1, 1])
            adj[t0_idx, f0] = t1_idx
            adj[t1_idx, f1] = t0_idx
        else:
            n_nm += 1
        i = j

    return adj, TetFaceAdjResult(
        n_tets=n_t,
        n_faces_total=n_t * 4,
        n_unique_faces=n_unique,
        n_boundary_faces=n_bnd,
        n_interior_faces=n_int,
        n_nonmanifold=n_nm,
        elapsed_s=time.perf_counter() - t0,
    )
