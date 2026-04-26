"""VVV7 — interior Laplacian smoothing targeting top-K worst-quality tets.

Only vertices that are ≥2 rings from any boundary face are moved.
Per-vertex strict quality guard: accept move only if min_q of incident tets
improves by at least min_quality_improvement.

Reference: Freitag & Ollivier-Gooch 1997, "Tetrahedral mesh improvement using
swapping and smoothing" — §3 local quality-improving Laplacian.
"""
from __future__ import annotations

import numpy as np


def _tet_shape_quality(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """Per-tet shape quality in [0,1]. Regular tet ≈ 1."""
    v = pts[tets]
    e01 = np.linalg.norm(v[:, 1] - v[:, 0], axis=1)
    e02 = np.linalg.norm(v[:, 2] - v[:, 0], axis=1)
    e03 = np.linalg.norm(v[:, 3] - v[:, 0], axis=1)
    e12 = np.linalg.norm(v[:, 2] - v[:, 1], axis=1)
    e13 = np.linalg.norm(v[:, 3] - v[:, 1], axis=1)
    e23 = np.linalg.norm(v[:, 3] - v[:, 2], axis=1)
    emax = np.maximum.reduce([e01, e02, e03, e12, e13, e23])
    vol = np.abs(
        np.einsum(
            "ij,ij->i",
            v[:, 1] - v[:, 0],
            np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
        )
    ) / 6.0
    q = np.zeros(len(tets))
    safe = emax > 1e-30
    q[safe] = 8.48 * vol[safe] / emax[safe] ** 3
    return q


def smooth_interior_laplacian(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    top_k: int = 20,
    n_iter: int = 1,
    min_quality_improvement: float = 1e-6,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Pure centroid-of-1-ring Laplacian for top-K worst-tet incident vertices.

    Only interior-safe vertices (≥2 rings from boundary) are candidates.
    Each candidate vertex is moved only if the minimum quality of its incident
    tets strictly improves by at least min_quality_improvement.

    Returns (pts_out, tets_unchanged, n_moved).
    """
    pts = np.array(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_verts = pts.shape[0]
    n_tets = tets.shape[0]

    if n_tets == 0 or n_verts == 0:
        return pts, tets, 0

    # ── 1. Build vert → incident-tet adjacency ────────────────────────────────
    # List[List[int]]: vert_tets[v] = list of tet indices containing v.
    vert_tets: list[list[int]] = [[] for _ in range(n_verts)]
    for ti, tet in enumerate(tets):
        for v in tet:
            vert_tets[v].append(ti)

    # ── 2. Identify boundary faces (appear in exactly 1 tet) ─────────────────
    face_count: dict[tuple[int, int, int], int] = {}
    for tet in tets:
        faces = [
            tuple(sorted((tet[0], tet[1], tet[2]))),
            tuple(sorted((tet[0], tet[1], tet[3]))),
            tuple(sorted((tet[0], tet[2], tet[3]))),
            tuple(sorted((tet[1], tet[2], tet[3]))),
        ]
        for f in faces:
            face_count[f] = face_count.get(f, 0) + 1

    boundary_verts: set[int] = set()
    for f, cnt in face_count.items():
        if cnt == 1:
            boundary_verts.update(f)

    # ── 3. 2-ring BFS from boundary to mark interior-safe verts ──────────────
    # Build vert → neighbor verts adjacency (edges shared in tets).
    vert_neighbors: list[set[int]] = [set() for _ in range(n_verts)]
    for tet in tets:
        for i in range(4):
            for j in range(i + 1, 4):
                vert_neighbors[tet[i]].add(tet[j])
                vert_neighbors[tet[j]].add(tet[i])

    # BFS: depth[v] = min ring distance from any boundary vert.
    depth = np.full(n_verts, n_verts, dtype=np.int64)
    queue: list[int] = []
    for v in boundary_verts:
        depth[v] = 0
        queue.append(v)
    head = 0
    while head < len(queue):
        v = queue[head]; head += 1
        d1 = depth[v] + 1
        for nb in vert_neighbors[v]:
            if d1 < depth[nb]:
                depth[nb] = d1
                queue.append(nb)

    interior_safe = set(int(v) for v in range(n_verts) if depth[v] >= 2)

    if not interior_safe:
        return pts, tets, 0

    # ── 4. Identify candidate verts from top-K worst tets ────────────────────
    q_all = _tet_shape_quality(pts, tets)
    k = min(top_k, n_tets)
    worst_ti = np.argpartition(q_all, k - 1)[:k] if k < n_tets else np.arange(n_tets)

    candidate_verts: set[int] = set()
    for ti in worst_ti:
        for v in tets[ti]:
            if int(v) in interior_safe:
                candidate_verts.add(int(v))

    if not candidate_verts:
        return pts, tets, 0

    # ── 5. Per-vertex smoothing with strict quality guard ─────────────────────
    n_moved = 0
    for _it in range(n_iter):
        for v in candidate_verts:
            nbs = vert_neighbors[v]
            if not nbs:
                continue

            # Centroid of 1-ring neighbors (exclude self).
            p_new = np.mean(pts[list(nbs)], axis=0)

            # Quality before move.
            inc_tets = vert_tets[v]
            if not inc_tets:
                continue
            q_before = _tet_shape_quality(pts, tets[inc_tets])
            q_min_before = float(q_before.min())

            # Tentative move.
            p_old = pts[v].copy()
            pts[v] = p_new

            # Quality after candidate move.
            q_after = _tet_shape_quality(pts, tets[inc_tets])
            q_min_after = float(q_after.min())

            if q_min_after >= q_min_before + min_quality_improvement:
                n_moved += 1  # accept
            else:
                pts[v] = p_old  # revert

    return pts, tets, n_moved
