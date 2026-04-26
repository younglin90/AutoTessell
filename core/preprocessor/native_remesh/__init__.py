"""AutoTessell 자체 L2 remesh (pyACVD / pymeshlab / geogram 의존 제거 로드맵).

목표: edge length 를 target 에 맞추고 삼각형 품질 (정삼각형에 가까움) 을 향상.

제공:
    isotropic_remesh (Botsch & Kobbelt 2004):
        반복
         1) edge split  (길이 > 4/3 * target)
         2) edge collapse (길이 < 4/5 * target)
         3) edge flip    (vertex valence 6 기준 편차 개선)
         4) tangential relocation (vertex 를 이웃 centroid 로 이동, 표면 사영)

    lloyd_cvt:
        단순화된 CVT (Centroidal Voronoi Tessellation) — 각 vertex 를 인접
        face centroid 의 area-weighted 평균 위치로 이동. 표면 사영은 입력 surface
        기준 KDTree 근사.

두 함수 모두 (vertices, faces) → (vertices, faces) 를 반환한다.
"""
from __future__ import annotations

import numpy as np

from core.preprocessor.native_remesh.cvt import lloyd_cvt
from core.preprocessor.native_remesh.isotropic import isotropic_remesh

_UUU1_SI_DETECT = True


def _detect_self_intersections(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Triangle AABB pair 탐색 → Möller tri-tri intersect → intersecting face index pair (M,2) 반환.

    Parameters
    ----------
    V : np.ndarray, shape (N, 3)
        Vertex positions.
    F : np.ndarray, shape (T, 3)
        Triangle face indices.

    Returns
    -------
    np.ndarray, shape (M, 2)
        Pairs of face indices that intersect each other.
    """
    n = len(F)
    tris = V[F]  # (T, 3, 3)

    # AABB per triangle
    aabb_min = tris.min(axis=1)  # (T, 3)
    aabb_max = tris.max(axis=1)  # (T, 3)

    pairs: list[tuple[int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            # skip adjacent triangles sharing an edge or vertex
            shared = np.intersect1d(F[i], F[j])
            if len(shared) >= 2:
                continue
            # AABB overlap test
            if np.any(aabb_min[i] > aabb_max[j]) or np.any(aabb_min[j] > aabb_max[i]):
                continue
            # Möller 1997 triangle-triangle intersection test
            if _moller_tri_tri(tris[i], tris[j]):
                pairs.append((i, j))

    if not pairs:
        return np.empty((0, 2), dtype=np.intp)
    return np.array(pairs, dtype=np.intp)


def _moller_tri_tri(t1: np.ndarray, t2: np.ndarray) -> bool:
    """Möller 1997 triangle-triangle intersection (no coplanar handling).

    Parameters
    ----------
    t1 : np.ndarray, shape (3, 3)
    t2 : np.ndarray, shape (3, 3)

    Returns
    -------
    bool
        True if the two triangles intersect.
    """
    _EPS = 1e-10

    def _signed_dists(tri: np.ndarray, n: np.ndarray, d: float) -> np.ndarray:
        return tri @ n - d

    n1 = np.cross(t1[1] - t1[0], t1[2] - t1[0])
    d1 = n1 @ t1[0]
    sd2 = _signed_dists(t2, n1, d1)
    if np.all(sd2 > _EPS) or np.all(sd2 < -_EPS):
        return False

    n2 = np.cross(t2[1] - t2[0], t2[2] - t2[0])
    d2 = n2 @ t2[0]
    sd1 = _signed_dists(t1, n2, d2)
    if np.all(sd1 > _EPS) or np.all(sd1 < -_EPS):
        return False

    # intersection line direction
    D = np.cross(n1, n2)
    D_norm = np.linalg.norm(D)
    if D_norm < _EPS:
        return False  # coplanar — skip
    D = D / D_norm

    def _interval(tri: np.ndarray, sd: np.ndarray) -> tuple[float, float]:
        p = tri @ D
        # two vertices on same side
        idx_same = np.where(sd * sd[0] > 0)[0]
        idx_diff = np.where(sd * sd[0] <= 0)[0]
        if len(idx_same) == 2:
            # vertex 0 is alone
            alone, others = 0, [1, 2]
        else:
            alone = int(idx_diff[0]) if len(idx_diff) == 1 else int(idx_same[0])
            others = [k for k in range(3) if k != alone]
        t_vals = []
        for o in others:
            denom = sd[alone] - sd[o]
            if abs(denom) < _EPS:
                t_vals.append(p[alone])
            else:
                t_vals.append(p[o] + (p[alone] - p[o]) * sd[o] / denom)
        return (min(t_vals), max(t_vals))

    lo1, hi1 = _interval(t1, sd1)
    lo2, hi2 = _interval(t2, sd2)
    return hi1 >= lo2 - _EPS and hi2 >= lo1 - _EPS


__all__ = ["isotropic_remesh", "lloyd_cvt", "_UUU1_SI_DETECT", "_detect_self_intersections"]
