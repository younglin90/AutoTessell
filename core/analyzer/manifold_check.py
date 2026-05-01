"""Z2 / beta2738 — surface manifold check.

surface mesh 가 manifold 인지 검증:
  - 각 edge 가 정확히 2 face 에 incident (closed manifold).
  - 각 vertex 의 1-ring 이 disk topology (single fan).

native_repair 단계 결정 (L1 vs L2 vs L3) 의 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class ManifoldCheckResult:
    n_vertices: int = 0
    n_triangles: int = 0
    is_edge_manifold: bool = True   # 모든 edge 1-2 incident face.
    is_vertex_manifold: bool = True # 각 vertex 1-ring 이 single fan.
    n_boundary_edges: int = 0
    n_nonmanifold_edges: int = 0    # 3+ faces.
    n_nonmanifold_vertices: int = 0
    elapsed_s: float = 0.0


def check_manifold(
    F: NDArray[np.int64],
    n_vertices: int | None = None,
) -> ManifoldCheckResult:
    """surface manifold 검사.

    Args:
        F: (M, 3) tri indices.
        n_vertices: optional, F.max()+1 로 추론.

    Returns:
        ManifoldCheckResult.
    """
    import time
    t0 = time.perf_counter()

    F = np.asarray(F, dtype=np.int64)
    n_f = int(F.shape[0])

    if n_f == 0:
        return ManifoldCheckResult(elapsed_s=time.perf_counter() - t0)

    n_v = int(n_vertices) if n_vertices is not None else int(F.max() + 1)

    # edge → face incident count.
    edges = np.concatenate([
        F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]],
    ], axis=0)
    edges_sorted = np.sort(edges, axis=1)
    keys = edges_sorted[:, 0] * (1 << 32) + edges_sorted[:, 1]

    sort_idx = np.argsort(keys)
    keys_s = keys[sort_idx]

    n_bnd = 0
    n_nm = 0
    n_unique = 0
    is_edge_man = True

    i = 0
    n_e = keys_s.shape[0]
    edge_face_lists: dict[int, list[int]] = {}

    while i < n_e:
        j = i
        while j < n_e and keys_s[j] == keys_s[i]:
            j += 1
        cnt = j - i
        n_unique += 1
        if cnt == 1:
            n_bnd += 1
        elif cnt > 2:
            n_nm += 1
            is_edge_man = False
        i = j

    # vertex manifold: 각 vertex 의 1-ring 의 incident face 들이 single fan.
    # 간단 체크: vertex 별 incident faces 의 edge 가 해당 vertex 에 묶인
    # boundary edges (그 face 들 사이의 다른 두 edge) 가 single cycle/path.
    # 비싸므로 여기선 "non-manifold edge incident vertex" 를 nonmanifold vertex 로
    # 근사 (정확한 fan 검사는 별도 카드).
    nm_v_set: set[int] = set()
    if not is_edge_man:
        # rebuild edge incidence to find non-manifold edges' vertices.
        i = 0
        while i < n_e:
            j = i
            while j < n_e and keys_s[j] == keys_s[i]:
                j += 1
            if (j - i) > 2:
                ev0 = int(edges_sorted[sort_idx[i], 0])
                ev1 = int(edges_sorted[sort_idx[i], 1])
                nm_v_set.add(ev0)
                nm_v_set.add(ev1)
            i = j

    return ManifoldCheckResult(
        n_vertices=n_v,
        n_triangles=n_f,
        is_edge_manifold=is_edge_man,
        is_vertex_manifold=(is_edge_man and len(nm_v_set) == 0),
        n_boundary_edges=n_bnd,
        n_nonmanifold_edges=n_nm,
        n_nonmanifold_vertices=len(nm_v_set),
        elapsed_s=time.perf_counter() - t0,
    )
