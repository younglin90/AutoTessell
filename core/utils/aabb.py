"""Phase C1 — Triangle soup BVH (AABB tree) for fast closest-point queries.

점 → 표면까지의 거리 계산을 O(F) → O(log F) 로 가속. envelope-based
preservation, winding number 초기화, feature snap 등에서 핵심.

구현 방침
    - scipy.spatial.cKDTree 가 점-점은 빠르지만 점-triangle 거리에는 부적합.
    - 본 모듈은 간단한 AABB 이진 BVH 를 직접 구현 (numpy only). 중대형 메쉬
      (≤500k tri) 에서 충분히 빠름.

레퍼런스
    - Ericson 2005, "Real-Time Collision Detection" §6.1, §5.1 (point-triangle
      closest-point formula). 본 파일은 표준 공식의 직접 구현.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def _closest_point_on_triangle(
    p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Ericson §5.1.5 — 점 p 에서 triangle abc 까지의 closest point + 거리."""
    ab = b - a
    ac = c - a
    ap = p - a

    d1 = float(np.dot(ab, ap))
    d2 = float(np.dot(ac, ap))
    if d1 <= 0.0 and d2 <= 0.0:
        cp = a
        return cp, float(np.linalg.norm(p - cp))

    bp = p - b
    d3 = float(np.dot(ab, bp))
    d4 = float(np.dot(ac, bp))
    if d3 >= 0.0 and d4 <= d3:
        cp = b
        return cp, float(np.linalg.norm(p - cp))

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        cp = a + v * ab
        return cp, float(np.linalg.norm(p - cp))

    cp2 = p - c
    d5 = float(np.dot(ab, cp2))
    d6 = float(np.dot(ac, cp2))
    if d6 >= 0.0 and d5 <= d6:
        cp = c
        return cp, float(np.linalg.norm(p - cp))

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        cp = a + w * ac
        return cp, float(np.linalg.norm(p - cp))

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        cp = b + w * (c - b)
        return cp, float(np.linalg.norm(p - cp))

    denom = 1.0 / (va + vb + vc)
    v = vb * denom
    w = vc * denom
    cp = a + ab * v + ac * w
    return cp, float(np.linalg.norm(p - cp))


@dataclass
class _BVHNode:
    aabb_min: np.ndarray
    aabb_max: np.ndarray
    left: int = -1    # child node index
    right: int = -1
    tri_start: int = -1  # leaf 일 때 tri 배열 시작
    tri_end: int = -1


@dataclass
class TriangleBVH:
    """Triangle soup 위의 AABB BVH.

    사용:
        bvh = TriangleBVH.build(V, F)
        cp, d = bvh.closest_point(np.array([x,y,z]))
        d_arr = bvh.signed_distance_unsigned(points)
    """

    V: np.ndarray
    F: np.ndarray
    nodes: list[_BVHNode] = field(default_factory=list)
    tri_order: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    leaf_size: int = 8

    @classmethod
    def build(
        cls, V: np.ndarray, F: np.ndarray, leaf_size: int = 8,
    ) -> "TriangleBVH":
        V = np.asarray(V, dtype=np.float64)
        F = np.asarray(F, dtype=np.int64)
        bvh = cls(V=V, F=F, leaf_size=int(leaf_size))
        if F.shape[0] == 0:
            return bvh

        # triangle centroid + per-tri AABB.
        tri_pts = V[F]   # (T, 3, 3)
        tri_min = tri_pts.min(axis=1)
        tri_max = tri_pts.max(axis=1)
        tri_centroid = tri_pts.mean(axis=1)

        order = np.arange(F.shape[0], dtype=np.int64)

        def _build(lo: int, hi: int) -> int:
            # nodes 에 하나 추가, 자체 index 반환.
            idxs = order[lo:hi]
            tmin = tri_min[idxs].min(axis=0)
            tmax = tri_max[idxs].max(axis=0)
            node = _BVHNode(aabb_min=tmin, aabb_max=tmax)
            node_idx = len(bvh.nodes)
            bvh.nodes.append(node)
            n = hi - lo
            if n <= bvh.leaf_size:
                node.tri_start = lo
                node.tri_end = hi
                return node_idx
            # split: longest axis, median.
            ext = tmax - tmin
            axis = int(np.argmax(ext))
            cents = tri_centroid[idxs, axis]
            sorted_sub = np.argsort(cents) + lo
            order[lo:hi] = sorted_sub
            mid = lo + n // 2
            node.left = _build(lo, mid)
            node.right = _build(mid, hi)
            return node_idx

        _build(0, F.shape[0])
        bvh.tri_order = order
        return bvh

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def _aabb_dist_lower(self, p: np.ndarray, node: _BVHNode) -> float:
        """점 p 와 node aabb 의 lower-bound 거리."""
        d = np.maximum(node.aabb_min - p, 0) + np.maximum(p - node.aabb_max, 0)
        return float(np.linalg.norm(d))

    def closest_point(self, p: np.ndarray) -> tuple[np.ndarray, float, int]:
        """p 에서 가장 가까운 triangle 과 그 위의 closest-point + tri index."""
        if not self.nodes:
            return p.copy(), float("inf"), -1
        p = np.asarray(p, dtype=np.float64)

        best_d = float("inf")
        best_cp = p.copy()
        best_tri = -1

        stack = [0]
        while stack:
            ni = stack.pop()
            node = self.nodes[ni]
            if self._aabb_dist_lower(p, node) >= best_d:
                continue
            if node.tri_start >= 0:
                for ti in self.tri_order[node.tri_start:node.tri_end]:
                    ti_int = int(ti)
                    a = self.V[self.F[ti_int, 0]]
                    b = self.V[self.F[ti_int, 1]]
                    c = self.V[self.F[ti_int, 2]]
                    cp, d = _closest_point_on_triangle(p, a, b, c)
                    if d < best_d:
                        best_d = d
                        best_cp = cp
                        best_tri = ti_int
            else:
                # 가까운 자식 먼저.
                l_node = self.nodes[node.left]
                r_node = self.nodes[node.right]
                dl = self._aabb_dist_lower(p, l_node)
                dr = self._aabb_dist_lower(p, r_node)
                if dl < dr:
                    stack.append(node.right)
                    stack.append(node.left)
                else:
                    stack.append(node.left)
                    stack.append(node.right)
        return best_cp, best_d, best_tri

    def unsigned_distances(self, points: np.ndarray) -> np.ndarray:
        """각 점의 표면까지 distance (unsigned)."""
        points = np.asarray(points, dtype=np.float64)
        out = np.zeros(points.shape[0], dtype=np.float64)
        for i in range(points.shape[0]):
            _, d, _ = self.closest_point(points[i])
            out[i] = d
        return out

    def inside_envelope(
        self, points: np.ndarray, envelope: float,
    ) -> np.ndarray:
        """각 점이 envelope 반지름 안에 있는지 bool array."""
        d = self.unsigned_distances(points)
        return d <= float(envelope)
