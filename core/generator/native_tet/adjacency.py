"""Phase B1 — tet mesh adjacency 구조.

Local operations (edge split/collapse/flip) 를 위해 O(log) 쿼리가 가능한
연결성 맵을 구축. 독립 Python 재구현 (외부 mesh 라이브러리 의존 없음).

레퍼런스
    - Bern & Eppstein 1999, "Mesh generation and optimal triangulation".
    - Botsch et al. 2010, "Polygon Mesh Processing" §1.3 halfedge / mesh
      datastructure — 본 모듈은 간소화된 직접 맵 구조.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def _sorted2(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _sorted3(a: int, b: int, c: int) -> tuple[int, int, int]:
    x, y, z = sorted((a, b, c))
    return (x, y, z)


@dataclass
class TetAdjacency:
    """tet mesh 의 연결성 lookup table.

    tets[i]       = (a, b, c, d) — 한 tet 의 4 vertex.
    face_to_tets[(u,v,w)]  = [ti, ...]  — 해당 face 를 공유하는 tet id (1 or 2).
    edge_to_tets[(u,v)]    = [ti, ...]  — 해당 edge 를 포함하는 tet id (링).
    vertex_to_tets[v]      = [ti, ...]  — 해당 vertex 를 포함하는 tet id.
    """

    tets: np.ndarray
    face_to_tets: dict[tuple[int, int, int], list[int]] = field(default_factory=dict)
    edge_to_tets: dict[tuple[int, int], list[int]] = field(default_factory=dict)
    vertex_to_tets: dict[int, list[int]] = field(default_factory=dict)

    @classmethod
    def build(cls, tets: np.ndarray) -> "TetAdjacency":
        """C-PERF-41 / beta2492 — vectorize adjacency build via group-by-key.

        face_to_tets / edge_to_tets / vertex_to_tets 모두 lexsort + group
        boundary 로 한 번에 빌드. 이전 tet × {4 faces + 6 edges + 4 verts}
        Python loop (14T iterations) 제거.
        """
        tets = np.asarray(tets, dtype=np.int64)
        adj = cls(tets=tets)
        T = int(tets.shape[0])
        if T == 0:
            return adj

        # ── Faces (4 per tet, each sorted 3-tuple). ───────────────────────
        face_idx = np.array([
            [0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3],
        ], dtype=np.int64)
        faces_flat = np.sort(
            tets[:, face_idx].reshape(-1, 3), axis=1,
        )                                                 # (4T, 3)
        ti_face = np.repeat(np.arange(T, dtype=np.int64), 4)
        order_f = np.lexsort(
            (faces_flat[:, 2], faces_flat[:, 1], faces_flat[:, 0]),
        )
        f_s = faces_flat[order_f]
        ti_f = ti_face[order_f]
        diff_f = np.r_[True, np.any(f_s[1:] != f_s[:-1], axis=1)]
        starts_f = np.where(diff_f)[0]
        ends_f = np.r_[starts_f[1:], len(f_s)]
        for s, e in zip(starts_f.tolist(), ends_f.tolist()):
            k = (int(f_s[s, 0]), int(f_s[s, 1]), int(f_s[s, 2]))
            adj.face_to_tets[k] = ti_f[s:e].tolist()

        # ── Edges (6 per tet, each sorted 2-tuple). ───────────────────────
        edge_idx = np.array([
            [0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3],
        ], dtype=np.int64)
        edges_flat = np.sort(
            tets[:, edge_idx].reshape(-1, 2), axis=1,
        )                                                 # (6T, 2)
        ti_edge = np.repeat(np.arange(T, dtype=np.int64), 6)
        order_e = np.lexsort((edges_flat[:, 1], edges_flat[:, 0]))
        e_s = edges_flat[order_e]
        ti_e = ti_edge[order_e]
        diff_e = np.r_[True, np.any(e_s[1:] != e_s[:-1], axis=1)]
        starts_e = np.where(diff_e)[0]
        ends_e = np.r_[starts_e[1:], len(e_s)]
        for s, e in zip(starts_e.tolist(), ends_e.tolist()):
            k2 = (int(e_s[s, 0]), int(e_s[s, 1]))
            adj.edge_to_tets[k2] = ti_e[s:e].tolist()

        # ── Vertices (4 per tet). ─────────────────────────────────────────
        flat_v = tets.reshape(-1)
        ti_vert = np.repeat(np.arange(T, dtype=np.int64), 4)
        order_v = np.argsort(flat_v, kind="stable")
        v_s = flat_v[order_v]
        ti_v = ti_vert[order_v]
        diff_v = np.r_[True, v_s[1:] != v_s[:-1]]
        starts_v = np.where(diff_v)[0]
        ends_v = np.r_[starts_v[1:], len(v_s)]
        for s, e in zip(starts_v.tolist(), ends_v.tolist()):
            adj.vertex_to_tets[int(v_s[s])] = ti_v[s:e].tolist()

        return adj

    def boundary_faces(self) -> list[tuple[int, int, int]]:
        """한 tet 에만 속한 face (= surface boundary)."""
        return [k for k, lst in self.face_to_tets.items() if len(lst) == 1]

    def is_boundary_edge(self, u: int, v: int) -> bool:
        """edge 가 boundary face 에 포함되는지. 간이 판정."""
        # boundary face 를 매번 돌면 느리므로 edge_to_tets 의 원소 수가 적으면
        # 그 tet 들의 face 중 boundary 가 있는지 본다. 실제 사용은 boundary
        # face set 을 미리 계산해 넘기는 게 효율적.
        tri_set = set(self.boundary_faces())
        for ti in self.edge_to_tets.get(_sorted2(u, v), []):
            a, b, c, d = (int(x) for x in self.tets[ti])
            for tri in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
                key = _sorted3(*tri)
                if key in tri_set and u in key and v in key:
                    return True
        return False
