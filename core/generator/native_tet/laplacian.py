"""VVV7 — interior Laplacian smoothing targeting top-K worst-quality tets.

Only vertices that are ≥2 rings from any boundary face are moved.
Per-vertex strict quality guard: accept move only if min_q of incident tets
improves by at least min_quality_improvement.

Reference: Freitag & Ollivier-Gooch 1997, "Tetrahedral mesh improvement using
swapping and smoothing" — §3 local quality-improving Laplacian.
"""
from __future__ import annotations

import numpy as np

# ── TET_CACHE1 (beta2152) — boundary-face memo ────────────────────────────────
# LRU-1: cache last boundary-face computation keyed by tets.tobytes().
# Avoids redundant O(T) dict build across VVV7 / VVV8 / TET_QUALITY1 post-passes
# when tets array has not changed (smoothing only moves pts, not topology).
_BF_CACHE_KEY: bytes | None = None
_BF_CACHE_VAL: "tuple[dict[tuple[int,int,int],int], set[int]] | None" = None


def _compute_boundary_faces_cached(
    tets: np.ndarray,
) -> "tuple[dict[tuple[int,int,int],int], set[int]]":
    """Return (face_count, boundary_verts) for tets, using a 1-entry memo cache.

    face_count: maps sorted 3-tuple → int (1 = boundary, 2 = interior).
    boundary_verts: set of vertex indices on boundary faces.
    Cache is invalidated whenever tets.tobytes() changes (topology mutation).
    """
    global _BF_CACHE_KEY, _BF_CACHE_VAL  # noqa: PLW0603
    key = tets.tobytes()
    if key == _BF_CACHE_KEY and _BF_CACHE_VAL is not None:
        return _BF_CACHE_VAL

    face_count: dict[tuple[int, int, int], int] = {}
    for tet in tets:
        for combo in (
            (tet[0], tet[1], tet[2]),
            (tet[0], tet[1], tet[3]),
            (tet[0], tet[2], tet[3]),
            (tet[1], tet[2], tet[3]),
        ):
            f: tuple[int, int, int] = tuple(sorted(combo))  # type: ignore[assignment]
            face_count[f] = face_count.get(f, 0) + 1

    boundary_verts: set[int] = set()
    for f, cnt in face_count.items():
        if cnt == 1:
            boundary_verts.update(f)

    _BF_CACHE_KEY = key
    _BF_CACHE_VAL = (face_count, boundary_verts)
    return _BF_CACHE_VAL


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
    # TET_CACHE1: reuse cached result when tets topology hasn't changed.
    _fc, boundary_verts = _compute_boundary_faces_cached(tets)

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


# ── TET_QUALITY1 (beta2141) ────────────────────────────────────────────────────


def _tet_face_nonortho(
    pts: np.ndarray,
    tet_a: np.ndarray,
    tet_b: np.ndarray,
    shared_face: tuple[int, int, int],
) -> float:
    """Non-orthogonality (degrees) between face normal and cell-cell vector."""
    c0 = pts[tet_a].mean(axis=0)
    c1 = pts[tet_b].mean(axis=0)
    cc = c1 - c0
    cc_len = float(np.linalg.norm(cc))
    if cc_len < 1e-30:
        return 0.0
    a, b, c = pts[shared_face[0]], pts[shared_face[1]], pts[shared_face[2]]
    n_vec = np.cross(b - a, c - a)
    n_len = float(np.linalg.norm(n_vec))
    if n_len < 1e-30:
        return 0.0
    cos_a = abs(float(np.dot(n_vec / n_len, cc / cc_len)))
    cos_a = min(1.0, cos_a)
    return float(np.degrees(np.arccos(cos_a)))


def reduce_nonortho_tet(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    threshold_deg: float = 60.0,
    top_k: int = 20,
    min_improve_deg: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, int]:
    """TET_QUALITY1: non-orthogonality local post-pass for tet meshes.

    For internal faces with non-ortho > threshold_deg (top_k worst), nudge
    incident face verts along the cell-cell vector projection (0.1x scale).
    STRICT GUARD: revert if local max non-ortho does not decrease by at least
    min_improve_deg.  Boundary faces are skipped.

    Returns (pts_out, tets_unchanged, n_moved).
    """
    pts = np.array(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    if n_tets == 0:
        return pts, tets, 0

    # ── 1. Build face -> owner tets ──────────────────────────────────────────
    _TET_FACES = ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))
    face_owners: dict[tuple[int, int, int], list[int]] = {}
    for ti in range(n_tets):
        for fl in _TET_FACES:
            key = tuple(sorted(int(tets[ti, k]) for k in fl))
            face_owners.setdefault(key, []).append(ti)  # type: ignore[arg-type]

    # ── 2. Collect internal faces with non-ortho > threshold ─────────────────
    bad: list[tuple[float, tuple[int, int, int], int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for ti in range(n_tets):
        for fl in _TET_FACES:
            key2: tuple[int, int, int] = tuple(sorted(int(tets[ti, k]) for k in fl))  # type: ignore[assignment]
            if key2 in seen:
                continue
            seen.add(key2)
            owners = face_owners.get(key2, [])
            if len(owners) < 2:
                continue  # boundary face
            ang = _tet_face_nonortho(pts, tets[owners[0]], tets[owners[1]], key2)
            if ang > threshold_deg:
                bad.append((ang, key2, owners[0], owners[1]))

    if not bad:
        return pts, tets, 0

    bad.sort(key=lambda t: t[0], reverse=True)
    bad = bad[:top_k]

    # ── 3. Helper: local max non-ortho over faces incident to two tet cells ──
    def _local_max_no(ti0: int, ti1: int) -> float:
        incident: set[tuple[int, int, int]] = set()
        for ci in (ti0, ti1):
            for fl in _TET_FACES:
                k2: tuple[int, int, int] = tuple(sorted(int(tets[ci, k]) for k in fl))  # type: ignore[assignment]
                incident.add(k2)
        vals = []
        for k2 in incident:
            ow = face_owners.get(k2, [])
            if len(ow) == 2:
                vals.append(_tet_face_nonortho(pts, tets[ow[0]], tets[ow[1]], k2))
        return max(vals) if vals else 0.0

    all_bad_keys = {entry[1] for entry in bad}
    pre_global_max = max(e[0] for e in bad)

    # ── 4. Per-face nudge with strict guard ───────────────────────────────────
    n_moved = 0
    for _ang_pre, face_key, ci0, ci1 in bad:
        c0 = pts[tets[ci0]].mean(axis=0)
        c1 = pts[tets[ci1]].mean(axis=0)
        cc = c1 - c0
        cc_len = float(np.linalg.norm(cc))
        if cc_len < 1e-30:
            continue

        fvp = pts[list(face_key)]
        n_vec = np.cross(fvp[1] - fvp[0], fvp[2] - fvp[0])
        n_len = float(np.linalg.norm(n_vec))
        if n_len < 1e-30:
            continue
        n_hat = n_vec / n_len
        proj = float(np.dot(cc / cc_len, n_hat))
        delta = 0.1 * proj * n_hat * cc_len

        pre_local = _local_max_no(ci0, ci1)

        orig = {vi: pts[vi].copy() for vi in face_key}
        for vi in face_key:
            pts[vi] = pts[vi] + delta

        post_local = _local_max_no(ci0, ci1)

        # Triple monotone guard: local improves AND global does not regress.
        post_global = max(
            (
                _tet_face_nonortho(pts, tets[fo[0]], tets[fo[1]], k2)
                for k2 in all_bad_keys
                if len((fo := face_owners.get(k2, []))) == 2
            ),
            default=0.0,
        )

        if (post_local <= pre_local - min_improve_deg
                and post_global <= pre_global_max):
            n_moved += 1
            pre_global_max = post_global
        else:
            for vi, p in orig.items():
                pts[vi] = p

    return pts, tets, n_moved


def _point_to_triangle_distance(p: np.ndarray, tri_pts: np.ndarray) -> tuple[float, np.ndarray]:
    """Closest point on triangle to p. tri_pts shape (3,3)."""
    a, b, c = tri_pts[0], tri_pts[1], tri_pts[2]
    ab = b - a; ac = c - a; ap = p - a
    d1 = np.dot(ab, ap); d2 = np.dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return float(np.linalg.norm(p - a)), a
    bp = p - b; d3 = np.dot(ab, bp); d4 = np.dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return float(np.linalg.norm(p - b)), b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3); cp = a + v * ab
        return float(np.linalg.norm(p - cp)), cp
    cp2 = p - c; d5 = np.dot(ab, cp2); d6 = np.dot(ac, cp2)
    if d6 >= 0 and d5 <= d6:
        return float(np.linalg.norm(p - c)), c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6); cp = a + w * ac
        return float(np.linalg.norm(p - cp)), cp
    va = d3 * d6 - d5 * d4
    w2 = d4 - d3; w3 = d5 - d6
    if va <= 0 and w2 >= 0 and w3 >= 0:
        denom = w2 + w3
        if denom > 1e-30:
            v = w2 / denom; cp = b + v * (c - b)
            return float(np.linalg.norm(p - cp)), cp
    denom2 = 1.0 / (va + vb + vc + 1e-300)
    v2 = vb * denom2; w4 = vc * denom2
    cp = a + v2 * ab + w4 * ac
    return float(np.linalg.norm(p - cp)), cp


def _nearest_surface_point(p: np.ndarray, surface_pts: np.ndarray, surface_faces: np.ndarray) -> np.ndarray:
    """O(F) point-to-triangle scan; returns nearest point on surface."""
    tri_pts = surface_pts[surface_faces]  # (F,3,3)
    # vectorised squared-distance to face centroids for quick bbox pruning
    centroids = tri_pts.mean(axis=1)  # (F,3)
    dists_c = np.linalg.norm(centroids - p, axis=1)
    coarse_k = min(64, len(surface_faces))
    top_idx = np.argpartition(dists_c, coarse_k - 1)[:coarse_k]
    best_dist = np.inf
    best_cp = p.copy()
    for fi in top_idx:
        d, cp = _point_to_triangle_distance(p, tri_pts[fi])
        if d < best_dist:
            best_dist = d
            best_cp = cp
    return best_cp


def smooth_boundary_envelope(
    pts: np.ndarray,
    tets: np.ndarray,
    surface_pts: np.ndarray,
    surface_faces: np.ndarray,
    *,
    top_k: int = 20,
    n_iter: int = 1,
    min_quality_improvement: float = 1e-6,
    envelope_eps: float | None = None,
) -> tuple[np.ndarray, np.ndarray, int]:
    """VVV8 — boundary Laplacian + envelope projection (Loseille 2013 §3.2).

    For boundary verts incident to the top-K worst tets:
      candidate = centroid of 1-ring boundary neighbors.
      project candidate to nearest surface point.
      Accept iff min_q over incident tets improves by min_quality_improvement.

    Returns (pts_out, tets_unchanged, n_moved).
    """
    pts = np.array(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    surface_pts = np.asarray(surface_pts, dtype=np.float64)
    surface_faces = np.asarray(surface_faces, dtype=np.int64)
    n_verts = pts.shape[0]
    n_tets = tets.shape[0]

    if n_tets == 0 or n_verts == 0 or surface_faces.shape[0] == 0:
        return pts, tets, 0

    # ── 1. Build adjacency ────────────────────────────────────────────────────
    vert_tets: list[list[int]] = [[] for _ in range(n_verts)]
    for ti, tet in enumerate(tets):
        for v in tet:
            vert_tets[v].append(ti)

    # TET_CACHE1: reuse cached boundary-face result when tets topology unchanged.
    _fc2, boundary_verts = _compute_boundary_faces_cached(tets)

    if not boundary_verts:
        return pts, tets, 0

    # ── 2. Vert neighbors (edge-connected) ───────────────────────────────────
    vert_neighbors: list[set[int]] = [set() for _ in range(n_verts)]
    for tet in tets:
        for i in range(4):
            for j in range(i + 1, 4):
                vert_neighbors[tet[i]].add(tet[j])
                vert_neighbors[tet[j]].add(tet[i])

    # ── 3. Candidate verts: boundary + incident to top-K worst tets ──────────
    q_all = _tet_shape_quality(pts, tets)
    k = min(top_k, n_tets)
    worst_ti = np.argpartition(q_all, k - 1)[:k] if k < n_tets else np.arange(n_tets)

    candidate_verts: set[int] = set()
    for ti in worst_ti:
        for v in tets[ti]:
            if int(v) in boundary_verts:
                candidate_verts.add(int(v))

    if not candidate_verts:
        return pts, tets, 0

    # ── 4. Smoothing with projection + strict quality guard ───────────────────
    n_moved = 0
    for _it in range(n_iter):
        for v in candidate_verts:
            bdy_nbs = [nb for nb in vert_neighbors[v] if nb in boundary_verts]
            if not bdy_nbs:
                continue

            candidate = np.mean(pts[bdy_nbs], axis=0)
            projected = _nearest_surface_point(candidate, surface_pts, surface_faces)

            if envelope_eps is not None:
                dist_to_surf = float(np.linalg.norm(projected - candidate))
                if dist_to_surf > envelope_eps:
                    continue

            inc_tets = vert_tets[v]
            if not inc_tets:
                continue
            q_before = _tet_shape_quality(pts, tets[inc_tets])
            q_min_before = float(q_before.min())

            p_old = pts[v].copy()
            pts[v] = projected

            q_after = _tet_shape_quality(pts, tets[inc_tets])
            q_min_after = float(q_after.min())

            if q_min_after >= q_min_before + min_quality_improvement:
                n_moved += 1  # accept
            else:
                pts[v] = p_old  # revert

    return pts, tets, n_moved
