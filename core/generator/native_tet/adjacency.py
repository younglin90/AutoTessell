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
        tets = np.asarray(tets, dtype=np.int64)
        adj = cls(tets=tets)
        for ti in range(tets.shape[0]):
            a, b, c, d = (int(x) for x in tets[ti])
            # 4 faces
            for tri in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
                key = _sorted3(*tri)
                adj.face_to_tets.setdefault(key, []).append(ti)
            # 6 edges
            for e in ((a, b), (a, c), (a, d), (b, c), (b, d), (c, d)):
                adj.edge_to_tets.setdefault(_sorted2(*e), []).append(ti)
            # vertices
            for v in (a, b, c, d):
                adj.vertex_to_tets.setdefault(v, []).append(ti)
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
