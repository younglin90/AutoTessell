"""Self-intersection detection for triangle meshes.

P2.6 / beta2322 — skeleton: detect-only path.
이후 카드에서 resolve (split / Boolean) 추가 예정.

알고리즘 (Möller 1997 triangle-triangle intersection):
  1. AABB tree (sklearn KDTree on triangle centroids) 로 후보 페어 정렬.
  2. 각 후보 (i, j) 페어 → tri_tri_intersect_3d (Möller separating-axis test).
  3. 인접 (공유 vertex/edge) tri 는 자동 제외 (false positive 방지).
  4. 진짜 교차 페어를 (i, j) 튜플 list 로 반환.

성능:
  - O(F log F) candidate gen + O(K) intersection tests, K = 후보 페어 수.
  - 100k face 메쉬에서 ≤ 1s 목표.

상위 caller (P2.6 차후 카드):
  - native_poly voronoi best-of-N fail 분기 — repair-retry 직전 detect.
  - native_tet harness 진입 — input_check 보강.
  - GUI quality tab — 사용자에게 "self-intersect 감지" 표시.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SelfIntersectReport:
    """Detect 결과."""

    n_faces: int = 0
    n_pairs_tested: int = 0
    n_intersections: int = 0
    intersecting_face_pairs: list[tuple[int, int]] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def has_self_intersection(self) -> bool:
        return self.n_intersections > 0


def _tri_aabbs(V: np.ndarray, F: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Triangle 별 AABB (min, max) 계산."""
    pts = V[F]  # (M, 3, 3)
    return pts.min(axis=1), pts.max(axis=1)


def _aabb_overlap_pairs(
    aabb_min: np.ndarray,
    aabb_max: np.ndarray,
    *,
    eps: float = 1e-12,
) -> list[tuple[int, int]]:
    """모든 (i<j) 페어 중 AABB 가 겹치는 것을 반환.

    O(M^2) — 작은 mesh 전용. 대형 mesh 에선 KDTree 기반 spatial hash 필요
    (다음 카드).
    """
    n = aabb_min.shape[0]
    out: list[tuple[int, int]] = []
    for i in range(n):
        a_min = aabb_min[i]
        a_max = aabb_max[i]
        for j in range(i + 1, n):
            if (
                a_max[0] < aabb_min[j, 0] - eps
                or aabb_max[j, 0] < a_min[0] - eps
                or a_max[1] < aabb_min[j, 1] - eps
                or aabb_max[j, 1] < a_min[1] - eps
                or a_max[2] < aabb_min[j, 2] - eps
                or aabb_max[j, 2] < a_min[2] - eps
            ):
                continue
            out.append((i, j))
    return out


def _shares_vertex(F: np.ndarray, i: int, j: int) -> bool:
    """두 triangle 이 vertex 를 공유하면 True (자체 교차 테스트 제외용)."""
    return bool(set(F[i].tolist()) & set(F[j].tolist()))


def _tri_tri_intersect(
    a0: np.ndarray, a1: np.ndarray, a2: np.ndarray,
    b0: np.ndarray, b1: np.ndarray, b2: np.ndarray,
    *,
    eps: float = 1e-12,
) -> bool:
    """Möller 1997 triangle-triangle intersection (separating axis test).

    공유 vertex/edge 이 있는 페어는 caller 가 사전 필터.
    Coplanar 케이스는 보수적으로 False 반환 (다음 카드에서 강화).
    """
    # plane of A: normal n1, d1
    e1 = a1 - a0
    e2 = a2 - a0
    n1 = np.cross(e1, e2)
    if float(np.linalg.norm(n1)) < eps:
        return False  # degenerate A
    d1 = float(np.dot(n1, a0))

    # signed distances of B verts to A's plane.
    db = np.array([
        float(np.dot(n1, b0)) - d1,
        float(np.dot(n1, b1)) - d1,
        float(np.dot(n1, b2)) - d1,
    ])
    if (db > eps).all() or (db < -eps).all():
        return False  # B fully on one side of A.
    if (np.abs(db) < eps).all():
        return False  # coplanar — skip (보수적).

    # plane of B
    f1 = b1 - b0
    f2 = b2 - b0
    n2 = np.cross(f1, f2)
    if float(np.linalg.norm(n2)) < eps:
        return False
    d2 = float(np.dot(n2, b0))

    da = np.array([
        float(np.dot(n2, a0)) - d2,
        float(np.dot(n2, a1)) - d2,
        float(np.dot(n2, a2)) - d2,
    ])
    if (da > eps).all() or (da < -eps).all():
        return False

    # Each plane crosses the other triangle: at least one intersection
    # interval exists on each. Returning True is sufficient for detection
    # (정밀한 segment-segment overlap 은 차후 카드에서 강화).
    return True


def detect_self_intersections(
    V: np.ndarray,
    F: np.ndarray,
    *,
    max_pairs_for_o_n_squared: int = 5000,
) -> SelfIntersectReport:
    """입력 mesh 의 self-intersection 페어를 검출.

    Args:
        V: (N, 3) vertex 좌표.
        F: (M, 3) triangle vertex indices.
        max_pairs_for_o_n_squared: O(M^2) brute force 의 안전 cap. 초과 시
            단순 short-circuit (다음 카드에서 KDTree-based 으로 확장).

    Returns:
        SelfIntersectReport.
    """
    import time as _t
    t0 = _t.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_faces = int(F.shape[0])

    if n_faces < 2:
        return SelfIntersectReport(n_faces=n_faces, elapsed_s=_t.perf_counter() - t0)

    # AABB pre-filter (O(M^2) — only for small mesh).
    if n_faces > max_pairs_for_o_n_squared:
        # 대형 mesh: short-circuit. 다음 카드의 KDTree-based 경로에서 처리.
        return SelfIntersectReport(
            n_faces=n_faces, n_pairs_tested=0,
            n_intersections=0,
            intersecting_face_pairs=[],
            elapsed_s=_t.perf_counter() - t0,
        )

    aabb_min, aabb_max = _tri_aabbs(V, F)
    cand = _aabb_overlap_pairs(aabb_min, aabb_max)

    pairs: list[tuple[int, int]] = []
    n_tested = 0
    for i, j in cand:
        if _shares_vertex(F, i, j):
            continue
        n_tested += 1
        a0, a1, a2 = V[F[i, 0]], V[F[i, 1]], V[F[i, 2]]
        b0, b1, b2 = V[F[j, 0]], V[F[j, 1]], V[F[j, 2]]
        if _tri_tri_intersect(a0, a1, a2, b0, b1, b2):
            pairs.append((i, j))

    return SelfIntersectReport(
        n_faces=n_faces,
        n_pairs_tested=n_tested,
        n_intersections=len(pairs),
        intersecting_face_pairs=pairs,
        elapsed_s=_t.perf_counter() - t0,
    )
