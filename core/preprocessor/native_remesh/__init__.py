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
_UUU3_REPAIR_CANDIDATES = True
_UUU5_FACE_SPLIT = True  # UUU6 (beta2107) — 활성, mesher 호출부에서 try/except 가드


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


def _si_repair_candidates(V: np.ndarray, F: np.ndarray, si_pairs: np.ndarray) -> list[dict]:
    """SI face pair → repair candidate 분류.
    공유 vertex 0 → {"op":"split","faces":[i,j]}.
    공유 vertex ≥1 → {"op":"merge","faces":[i,j],"shared":k}.
    호출 site 없음 (UUU4 에서 활성)."""
    candidates: list[dict] = []
    for pair in si_pairs:
        i, j = int(pair[0]), int(pair[1])
        shared = np.intersect1d(F[i], F[j])
        if len(shared) == 0:
            candidates.append({"op": "split", "faces": [i, j]})
        else:
            candidates.append({"op": "merge", "faces": [i, j], "shared": int(shared[0])})
    return candidates


def _apply_face_split(
    V: np.ndarray,
    F: np.ndarray,
    candidates: list,
    max_split: int = 20,
) -> tuple:
    """input face split helper (Hu 2018 fTetWild §3.1, UUU5).

    Parameters
    ----------
    V : np.ndarray, shape (N, 3)
        Vertex positions.
    F : np.ndarray, shape (T, 3)
        Triangle face indices.
    candidates : list of dict
        Candidate ops from _si_repair_candidates; only ``op=="split"`` are used.
    max_split : int
        Maximum number of splits to apply (default 20, very conservative).

    Returns
    -------
    V_new : np.ndarray
        Updated vertex array with new midpoints appended.
    F_new : np.ndarray
        Updated face array with split triangles replacing originals.
    n_split : int
        Number of splits actually applied.
    """
    split_ops = [c for c in candidates if c.get("op") == "split"][:max_split]
    if not split_ops:
        return V, F, 0

    V_new = list(V)
    F_list = list(F)
    replaced: set = set()
    n_split = 0

    new_vertex_indices: list = []

    for op in split_ops:
        face_idx = op.get("face")
        if face_idx is None or face_idx in replaced:
            continue
        tri = F_list[face_idx]
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        va, vb, vc = np.array(V_new[a]), np.array(V_new[b]), np.array(V_new[c])
        # longest edge midpoint
        edges = [(a, b, va, vb), (b, c, vb, vc), (a, c, va, vc)]
        ea, eb, p0, p1 = max(edges, key=lambda e: float(np.linalg.norm(e[3] - e[2])))
        m_pos = (p0 + p1) * 0.5
        m_idx = len(V_new)
        V_new.append(m_pos)
        new_vertex_indices.append(m_idx)
        # replace face with 2 new triangles
        # keep vertex not on split edge as third vertex
        third = c if (ea, eb) == (a, b) or (ea, eb) == (b, a) else (a if (ea, eb) in ((b, c), (c, b)) else b)
        F_list[face_idx] = np.array([ea, m_idx, third], dtype=F.dtype)
        F_list.append(np.array([eb, third, m_idx], dtype=F.dtype))
        replaced.add(face_idx)
        n_split += 1

    V_out = np.array(V_new, dtype=V.dtype)
    F_out = np.array(F_list, dtype=F.dtype)

    # 1-pass Laplacian cleanup for new vertices (UUU7)
    hausdorff_tol = float(op.get("hausdorff_tol", 0.0)) if split_ops else 0.0
    if new_vertex_indices:
        # build adjacency for all vertices in V_out
        n_verts = len(V_out)
        adjacency: list = [set() for _ in range(n_verts)]
        for tri in F_out:
            i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
            adjacency[i0].add(i1); adjacency[i0].add(i2)
            adjacency[i1].add(i0); adjacency[i1].add(i2)
            adjacency[i2].add(i0); adjacency[i2].add(i1)

        for m_idx in new_vertex_indices:
            neighbors = adjacency[m_idx]
            if not neighbors:
                continue
            orig_pos = V_out[m_idx].copy()
            avg_pos = np.mean([V_out[nb] for nb in neighbors], axis=0)
            # envelope guard: rollback if Hausdorff distance exceeded
            if hausdorff_tol > 0.0:
                dist = float(np.linalg.norm(avg_pos - orig_pos))
                if dist <= hausdorff_tol:
                    V_out[m_idx] = avg_pos
                # else: keep orig_pos (rollback)
            else:
                V_out[m_idx] = avg_pos

    return V_out, F_out, n_split


__all__ = [
    "isotropic_remesh",
    "lloyd_cvt",
    "_UUU1_SI_DETECT",
    "_detect_self_intersections",
    "_UUU3_REPAIR_CANDIDATES",
    "_si_repair_candidates",
    "_UUU5_FACE_SPLIT",
    "_apply_face_split",
]
