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


def _aabb_lower_batch(points: np.ndarray, amin: np.ndarray, amax: np.ndarray) -> np.ndarray:
    """N 개 점 각각에 대해 주어진 하나의 AABB 까지의 lower-bound 거리."""
    d = np.maximum(amin - points, 0) + np.maximum(points - amax, 0)
    return np.linalg.norm(d, axis=1)


def _closest_points_on_triangles_batch(
    p: np.ndarray, tri_pts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """단일 점 p 와 k 개 triangle 에 대한 closest-point.

    tri_pts: (k, 3, 3).
    반환: (closest_points (k, 3), distances (k,)).
    공식: Ericson §5.1.5 의 scalar 분기를 벡터로.
    """
    k = tri_pts.shape[0]
    A = tri_pts[:, 0]; B = tri_pts[:, 1]; C = tri_pts[:, 2]
    AB = B - A; AC = C - A
    AP = p - A
    d1 = np.einsum("ij,ij->i", AB, AP)
    d2 = np.einsum("ij,ij->i", AC, AP)
    BP = p - B
    d3 = np.einsum("ij,ij->i", AB, BP)
    d4 = np.einsum("ij,ij->i", AC, BP)
    CP = p - C
    d5 = np.einsum("ij,ij->i", AB, CP)
    d6 = np.einsum("ij,ij->i", AC, CP)

    out = np.zeros_like(A)
    done = np.zeros(k, dtype=bool)

    # Region A vertex.
    ra = (d1 <= 0) & (d2 <= 0) & ~done
    out[ra] = A[ra]; done |= ra
    # Region B.
    rb = (d3 >= 0) & (d4 <= d3) & ~done
    out[rb] = B[rb]; done |= rb
    # Edge AB.
    vc = d1 * d4 - d3 * d2
    rab = (vc <= 0) & (d1 >= 0) & (d3 <= 0) & ~done
    if rab.any():
        denom = np.where(d1[rab] - d3[rab] != 0, d1[rab] - d3[rab], 1.0)
        v = d1[rab] / denom
        out[rab] = A[rab] + v[:, None] * AB[rab]
        done |= rab
    # Region C.
    rc = (d6 >= 0) & (d5 <= d6) & ~done
    out[rc] = C[rc]; done |= rc
    # Edge AC.
    vb = d5 * d2 - d1 * d6
    rac = (vb <= 0) & (d2 >= 0) & (d6 <= 0) & ~done
    if rac.any():
        denom = np.where(d2[rac] - d6[rac] != 0, d2[rac] - d6[rac], 1.0)
        w = d2[rac] / denom
        out[rac] = A[rac] + w[:, None] * AC[rac]
        done |= rac
    # Edge BC.
    va = d3 * d6 - d5 * d4
    rbc = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0) & ~done
    if rbc.any():
        denom = np.where(
            (d4[rbc] - d3[rbc]) + (d5[rbc] - d6[rbc]) != 0,
            (d4[rbc] - d3[rbc]) + (d5[rbc] - d6[rbc]),
            1.0,
        )
        w = (d4[rbc] - d3[rbc]) / denom
        out[rbc] = B[rbc] + w[:, None] * (C[rbc] - B[rbc])
        done |= rbc
    # Interior.
    rem = ~done
    if rem.any():
        denom = va[rem] + vb[rem] + vc[rem]
        denom = np.where(denom != 0, denom, 1.0)
        v = vb[rem] / denom
        w = vc[rem] / denom
        out[rem] = A[rem] + v[:, None] * AB[rem] + w[:, None] * AC[rem]

    ds = np.linalg.norm(p - out, axis=1)
    return out, ds


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
        """각 점의 표면까지 distance (unsigned).

        beta470: closest_points_all_shared 경유 — 전면 shared-stack BVH 로
        Python overhead 감소.
        """
        points = np.asarray(points, dtype=np.float64)
        if points.shape[0] == 0 or not self.nodes:
            return np.zeros(points.shape[0], dtype=np.float64)
        cps, ds, _tis = self.closest_points_all_shared(points)
        return ds

    def closest_points_all_shared(
        self, points: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """N 개 query 가 stack 을 공유하는 전면-batch BVH.

        per-point closest_points_batch 는 query 당 독립 stack 이라 Python
        overhead 가 N 배. 여기서는:
            - 각 query 에 대해 best_d 배열 유지.
            - node 방문 큐: (node_idx, active_mask).
            - 노드 AABB 의 per-query lower-bound 거리 → 각 query 별로 prune.

        leaf 에 도달하면 active 인 모든 query × leaf 내 모든 tri 를 브로드캐스트
        로 한꺼번에 평가.
        """
        points = np.asarray(points, dtype=np.float64)
        N = points.shape[0]
        if N == 0 or not self.nodes:
            return (
                points.copy(),
                np.zeros(N, dtype=np.float64),
                -np.ones(N, dtype=np.int64),
            )

        best_d = np.full(N, np.inf, dtype=np.float64)
        best_cp = points.copy()
        best_ti = -np.ones(N, dtype=np.int64)

        # stack of (node_idx, active_mask).
        stack: list[tuple[int, np.ndarray]] = [
            (0, np.ones(N, dtype=bool))
        ]

        while stack:
            ni, active = stack.pop()
            if not active.any():
                continue
            node = self.nodes[ni]
            # per-query AABB lower-bound.
            d_low = _aabb_lower_batch(points, node.aabb_min, node.aabb_max)
            prune = d_low >= best_d
            sub_active = active & ~prune
            if not sub_active.any():
                continue
            if node.tri_start >= 0:
                tri_ids = self.tri_order[node.tri_start:node.tri_end]
                if tri_ids.size == 0:
                    continue
                # per-query × per-tri brute.
                tri_pts = self.V[self.F[tri_ids]]
                active_idx = np.where(sub_active)[0]
                # 각 active query 당 leaf tri 모두 평가.
                for qi in active_idx:
                    cps, ds = _closest_points_on_triangles_batch(
                        points[qi], tri_pts,
                    )
                    if ds.size:
                        j = int(np.argmin(ds))
                        if ds[j] < best_d[qi]:
                            best_d[qi] = float(ds[j])
                            best_cp[qi] = cps[j]
                            best_ti[qi] = int(tri_ids[j])
            else:
                # push both children (RHS popped first).
                stack.append((node.right, sub_active))
                stack.append((node.left, sub_active))

        return best_cp, best_d, best_ti

    def closest_points_batch(
        self, points: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """N 개 점에 대해 closest_point 일괄 계산.

        각 leaf 방문 시 해당 leaf 의 triangle 목록을 모든 query 점에 대해
        한꺼번에 브로드캐스트 검사 (numpy). leaf 방문 순서는 per-point
        이지만 leaf 당 batch 가속으로 python 오버헤드 감소.

        fallback: closest_point 를 점별 호출. small N (< 32) 면 그냥 순회.
        """
        points = np.asarray(points, dtype=np.float64)
        N = points.shape[0]
        if N == 0 or not self.nodes:
            return (
                points.copy(),
                np.zeros(N, dtype=np.float64),
                -np.ones(N, dtype=np.int64),
            )

        best_d = np.full(N, np.inf, dtype=np.float64)
        best_cp = points.copy()
        best_ti = -np.ones(N, dtype=np.int64)

        # 각 query 를 per-node stack 으로 병렬 탐색. N 이 큰 경우 공간 많이
        # 쓰지 않도록 per-point loop + 각 leaf 내에서 numpy.
        for i in range(N):
            p = points[i]
            stack = [0]
            bd = float("inf")
            bcp = p.copy()
            bti = -1
            while stack:
                ni = stack.pop()
                node = self.nodes[ni]
                if self._aabb_dist_lower(p, node) >= bd:
                    continue
                if node.tri_start >= 0:
                    # leaf: batch 대신 loop (tri 수 ≤ leaf_size).
                    tri_ids = self.tri_order[node.tri_start:node.tri_end]
                    # vectorize across triangles: 한 점 vs N_tri 삼각형.
                    t_pts = self.V[self.F[tri_ids]]   # (k, 3, 3)
                    cps, ds = _closest_points_on_triangles_batch(p, t_pts)
                    if ds.size:
                        j = int(np.argmin(ds))
                        if ds[j] < bd:
                            bd = float(ds[j])
                            bcp = cps[j]
                            bti = int(tri_ids[j])
                else:
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
            best_d[i] = bd
            best_cp[i] = bcp
            best_ti[i] = bti
        return best_cp, best_d, best_ti

    def inside_envelope(
        self, points: np.ndarray, envelope: float,
    ) -> np.ndarray:
        """각 점이 envelope 반지름 안에 있는지 bool array."""
        d = self.unsigned_distances(points)
        return d <= float(envelope)
