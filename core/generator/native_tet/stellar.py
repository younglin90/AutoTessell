"""
CARD VVV1 (beta2114) — Stellar 4-op iterative coordinator (skeleton).
Klingner & Shewchuk 2008 §3.
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

# VVV1: skeleton only — default OFF, no call path added
_VVV1_STELLAR_QUEUE: bool = True

# ---------------------------------------------------------------------------
# PERF3 (beta2166) — edge→incident-tet adjacency cache (single-slot LRU).
# Shared by VVV12 (split_sliver_longest_edge) and VVV13
# (split_anisotropic_tet_edges).  Cache key = id(tets) + tets.shape hash;
# one cache slot is sufficient because both passes are called sequentially.
# ---------------------------------------------------------------------------
_EDGE_INCIDENT_CACHE: Optional[tuple[int, int, dict[tuple[int, int], list[int]]]] = None


def compute_edge_incident_tets_cached(
    tets: np.ndarray,
) -> dict[tuple[int, int], list[int]]:
    """Return edge→[tet_idx] map for *tets*.  Single-slot LRU by tets id+shape.

    Cache hit: O(1).  Cache miss: O(N_tets * 6) to build.
    Invalidated whenever tets object changes (new array after split acceptance).
    """
    global _EDGE_INCIDENT_CACHE
    key_id = id(tets)
    key_shape = tets.shape[0]
    if _EDGE_INCIDENT_CACHE is not None:
        cached_id, cached_shape, cached_map = _EDGE_INCIDENT_CACHE
        if cached_id == key_id and cached_shape == key_shape:
            return cached_map
    # Build map.
    _PAIRS6 = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    edge_map: dict[tuple[int, int], list[int]] = {}
    for ti in range(tets.shape[0]):
        t = tets[ti]
        for pi, pj in _PAIRS6:
            u, v = int(t[pi]), int(t[pj])
            if u > v:
                u, v = v, u
            key = (u, v)
            if key in edge_map:
                edge_map[key].append(ti)
            else:
                edge_map[key] = [ti]
    _EDGE_INCIDENT_CACHE = (key_id, key_shape, edge_map)
    return edge_map


def _invalidate_edge_incident_cache() -> None:
    """Invalidate PERF3 cache (called after accepted split modifies tets_list)."""
    global _EDGE_INCIDENT_CACHE
    _EDGE_INCIDENT_CACHE = None


# ---------------------------------------------------------------------------
# PERF4 (beta2167) — face→incident-tet adjacency cache (single-slot LRU).
# Shared by VVV14 (insert_face_centroid_steiner).  Mirror of PERF3 for edges.
# Cache key = id(tets) + tets.shape[0]; invalidated when tets array changes.
# ---------------------------------------------------------------------------
_FACE_INCIDENT_CACHE: Optional[tuple[int, int, dict[tuple[int, int, int], list[int]]]] = None

_FACES4 = ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))


def compute_face_incident_tets_cached(
    tets: np.ndarray,
) -> dict[tuple[int, int, int], list[int]]:
    """Return sorted-face-tuple→[tet_idx] map for *tets*.  Single-slot LRU.

    Cache hit: O(1).  Cache miss: O(N_tets * 4) to build.
    Invalidated whenever tets object changes (new array after split acceptance).
    """
    global _FACE_INCIDENT_CACHE
    key_id = id(tets)
    key_shape = tets.shape[0]
    if _FACE_INCIDENT_CACHE is not None:
        cached_id, cached_shape, cached_map = _FACE_INCIDENT_CACHE
        if cached_id == key_id and cached_shape == key_shape:
            return cached_map
    # Build map.
    face_map: dict[tuple[int, int, int], list[int]] = {}
    for ti in range(tets.shape[0]):
        t = tets[ti]
        for fi, fj, fk in _FACES4:
            a, b, c = int(t[fi]), int(t[fj]), int(t[fk])
            if a > b:
                a, b = b, a
            if b > c:
                b, c = c, b
            if a > b:
                a, b = b, a
            key = (a, b, c)
            if key in face_map:
                face_map[key].append(ti)
            else:
                face_map[key] = [ti]
    _FACE_INCIDENT_CACHE = (key_id, key_shape, face_map)
    return face_map


def _invalidate_face_incident_cache() -> None:
    """Invalidate PERF4 cache (called after accepted split modifies tets array)."""
    global _FACE_INCIDENT_CACHE
    _FACE_INCIDENT_CACHE = None


def _orient_tet(pts_list: list, tet: list[int]) -> list[int]:
    """VVV12_ORIENT_FIX — ensure positive signed volume; swap last two verts if negative."""
    a, b, c, d = pts_list[tet[0]], pts_list[tet[1]], pts_list[tet[2]], pts_list[tet[3]]
    vol6 = float(np.dot(np.array(b) - np.array(a),
                        np.cross(np.array(c) - np.array(a), np.array(d) - np.array(a))))
    if vol6 < 0.0:
        return [tet[0], tet[1], tet[3], tet[2]]
    return tet


def _tet_quality(pts: np.ndarray, tet: np.ndarray) -> float:
    """Mean-ratio quality for a single tet (0..1, higher is better)."""
    a, b, c, d = pts[tet[0]], pts[tet[1]], pts[tet[2]], pts[tet[3]]
    e0 = b - a
    e1 = c - a
    e2 = d - a
    vol6 = float(np.dot(e0, np.cross(e1, e2)))
    if abs(vol6) < 1e-30:
        return 0.0
    l_sq = (
        np.dot(e0, e0)
        + np.dot(e1, e1)
        + np.dot(e2, e2)
        + np.dot(b - c, b - c)
        + np.dot(b - d, b - d)
        + np.dot(c - d, c - d)
    )
    # mean-ratio: 12*(3*vol)^(2/3) / sum(l^2)
    vol = abs(vol6) / 6.0
    if l_sq < 1e-30:
        return 0.0
    mr = 12.0 * (3.0 * vol) ** (2.0 / 3.0) / l_sq
    return float(np.clip(mr, 0.0, 1.0))


def _build_op_queue(pts: np.ndarray, tets: np.ndarray) -> list[dict]:
    """Build priority queue of candidate ops sorted by quality ascending.

    Returns list of dicts:
        {"quality": float, "tet_idx": int, "candidate_ops": list[str]}
    Lower quality → processed first (worst cells first).

    STELLAR_REMAIN_VEC: vectorized mean-ratio quality for all tets at once.
    """
    n = tets.shape[0]
    if n == 0:
        return []

    # Vectorized mean-ratio quality (mirrors _tet_quality exactly).
    v = pts[tets]  # (N,4,3)
    _a = v[:, 0]; _b = v[:, 1]; _c = v[:, 2]; _d = v[:, 3]
    e0 = _b - _a; e1 = _c - _a; e2 = _d - _a
    vol6 = (np.cross(e1, e2) * e0).sum(axis=1)
    l_sq = (
        (e0 ** 2).sum(1) + (e1 ** 2).sum(1) + (e2 ** 2).sum(1)
        + ((_b - _c) ** 2).sum(1) + ((_b - _d) ** 2).sum(1) + ((_c - _d) ** 2).sum(1)
    )
    q_arr = np.where(
        l_sq > 1e-30,
        np.clip(12.0 * (3.0 * np.abs(vol6) / 6.0) ** (2.0 / 3.0) / l_sq, 0.0, 1.0),
        0.0,
    )

    _OPS_LOW  = ["collapse", "split", "swap", "smooth"]
    _OPS_MID  = ["swap", "smooth"]
    _OPS_HIGH = ["smooth"]

    order = np.argsort(q_arr)
    queue: list[dict] = []
    for i in order:
        q = float(q_arr[i])
        if q < 0.3:
            ops = _OPS_LOW
        elif q < 0.6:
            ops = _OPS_MID
        else:
            ops = _OPS_HIGH
        queue.append({"quality": q, "tet_idx": int(i), "candidate_ops": ops})
    return queue


def _apply_op_queue(
    pts: np.ndarray,
    tets: np.ndarray,
    queue: list[dict],
    *,
    max_swap_attempts: int = 200,
    min_quality_improvement: float = 1e-3,
    protected_edges: "set[tuple[int, int]] | None" = None,
) -> tuple[np.ndarray, np.ndarray, int]:
    """VVV3b: worst-first swap-only apply (Klingner 2008 §3.2).

    Only entries with quality < 0.3 are processed (worst-first, already sorted).
    For each such tet, its 6 edges are collected as candidates; protected_edges
    are excluded.  flip_edges_32 is applied first, then flip_edges_44 on the
    result (chain).  collapse / split / smooth are explicitly passed to honor
    AVOID list (HHH1/JJJ1/LLL1/VVV3-prev).

    Returns (pts, tets_new, n_applied).
    """
    from .flip import flip_edges_32, flip_edges_44  # noqa: PLC0415

    # PERF11: vectorized per-op screening (replaces Python nested loop).
    # Step 1 — filter worst entries (quality < 0.3) and extract valid tet indices.
    n_tets = tets.shape[0]
    worst_entries = [e for e in queue if e["quality"] < 0.3]
    if not worst_entries:
        return pts, tets, 0

    raw_indices = np.array([e["tet_idx"] for e in worst_entries], dtype=np.intp)
    valid_mask = raw_indices < n_tets
    tet_indices = raw_indices[valid_mask]
    if tet_indices.size == 0:
        return pts, tets, 0

    # Step 2 — gather all 6 edge pairs per worst tet via numpy indexing.
    # _EDGE_PAIRS: shape (6,2), the 6 combinations of (i,j) from 4 verts.
    _EDGE_PAIRS = np.array([[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]], dtype=np.intp)
    worst_tets = tets[tet_indices]           # (W, 4)
    # edges shape: (W, 6, 2) — vertex indices for each of the 6 edge slots
    edges = worst_tets[:, _EDGE_PAIRS]       # (W, 6, 2)
    edges = edges.reshape(-1, 2)             # (W*6, 2)
    # Canonical ordering: ensure u < v.
    u = np.minimum(edges[:, 0], edges[:, 1])
    v = np.maximum(edges[:, 0], edges[:, 1])
    # Pack into single int64 for fast dedup (stride = n_pts+1 guarantees unique encoding).
    n_pts = pts.shape[0]
    _stride = np.int64(n_pts + 1)
    packed = u.astype(np.int64) * _stride + v.astype(np.int64)
    unique_packed = np.unique(packed)
    u_uniq = (unique_packed // _stride)
    v_uniq = (unique_packed  % _stride)
    candidate_edge_set: set[tuple[int, int]] = set(zip(u_uniq.tolist(), v_uniq.tolist()))

    # Remove protected edges (input surface edges).
    if protected_edges:
        candidate_edge_set -= protected_edges

    n_candidates = len(candidate_edge_set)
    max_flips = min(n_candidates, max_swap_attempts)

    # --- 3-2 flip pass ---
    tets_32, n32 = flip_edges_32(
        pts,
        tets,
        min_quality_improvement=min_quality_improvement,
        max_flips=max_flips,
        protected_edges=protected_edges,
    )

    # --- 4-4 flip pass (chained on 3-2 result) ---
    tets_44, n44 = flip_edges_44(
        pts,
        tets_32,
        min_quality_improvement=min_quality_improvement,
        max_flips=max_flips,
        protected_edges=protected_edges,
    )

    # Explicit no-ops for AVOID list:
    for op in ("collapse", "split", "smooth"):
        pass  # VVV3b: these ops intentionally excluded (Klingner monotone proof)

    n_applied = n32 + n44
    return pts, tets_44, n_applied


def insert_steiner_flip14(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    top_k: int = 5,
    min_quality_improvement: float = 1e-3,
    max_inserts: int = 10,
) -> tuple[np.ndarray, np.ndarray, int]:
    """VVV9 — non-Delaunay 1→4 flip Steiner insertion (fTetWild §3.4 simplified).

    For each of the top_k worst tets, compute centroid, split into 4 sub-tets,
    accept only if min quality strictly improves.  No scipy Delaunay rebuild.

    Returns (pts_out, tets_out, n_inserted).
    """
    n_tets = tets.shape[0]
    if n_tets == 0:
        return pts, tets, 0

    # PERF8 Step 1 — vectorized per-tet quality screen (mirrors _tet_quality mean-ratio).
    verts_all = pts[tets]                           # (N,4,3)
    _a = verts_all[:, 0]; _b = verts_all[:, 1]
    _c = verts_all[:, 2]; _d = verts_all[:, 3]
    _e0 = _b - _a; _e1 = _c - _a; _e2 = _d - _a
    _vol6 = (np.cross(_e1, _e2) * _e0).sum(axis=1)
    _l_sq = (
        (_e0 ** 2).sum(1) + (_e1 ** 2).sum(1) + (_e2 ** 2).sum(1)
        + ((_b - _c) ** 2).sum(1) + ((_b - _d) ** 2).sum(1) + ((_c - _d) ** 2).sum(1)
    )
    qualities = np.where(
        _l_sq > 1e-30,
        np.clip(12.0 * (3.0 * np.abs(_vol6) / 6.0) ** (2.0 / 3.0) / _l_sq, 0.0, 1.0),
        0.0,
    )

    # Pick top_k worst (ascending quality → smallest first).
    worst_indices = np.argsort(qualities)[: top_k]

    pts_list = list(pts)
    tets_list = list(tets)
    n_inserted = 0
    # Track which tet indices have been invalidated by prior insertions.
    invalidated: set[int] = set()

    for ti in worst_indices:
        if n_inserted >= max_inserts:
            break
        if ti in invalidated:
            continue

        tet = tets_list[ti]
        a, b, c, d = int(tet[0]), int(tet[1]), int(tet[2]), int(tet[3])
        pa, pb, pc, pd = pts_list[a], pts_list[b], pts_list[c], pts_list[d]

        q_old = _tet_quality(np.array(pts_list), np.array([a, b, c, d]))

        # Steiner point = centroid of the 4 vertices.
        centroid = (pa + pb + pc + pd) / 4.0

        N = len(pts_list)
        pts_list.append(centroid)

        sub_tets = [
            np.array([a, b, c, N], dtype=tets.dtype),
            np.array([a, b, N, d], dtype=tets.dtype),
            np.array([a, N, c, d], dtype=tets.dtype),
            np.array([N, b, c, d], dtype=tets.dtype),
        ]

        pts_arr_tmp = np.array(pts_list)
        q_news = [_tet_quality(pts_arr_tmp, st) for st in sub_tets]
        q_new_min = min(q_news)

        if q_new_min >= q_old + min_quality_improvement:
            # Accept: replace old tet with 4 sub-tets.
            tets_list[ti] = sub_tets[0]
            tets_list.extend(sub_tets[1:])
            invalidated.add(ti)
            n_inserted += 1
        else:
            # Revert: pop the appended vertex.
            pts_list.pop()

    pts_out = np.array(pts_list)
    tets_out = np.array(tets_list, dtype=tets.dtype)
    return pts_out, tets_out, n_inserted


def split_sliver_longest_edge(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    sliver_ratio: float = 1e-3,
    min_quality_improvement: float = 1e-3,
    max_splits: int = 20,
) -> tuple[np.ndarray, np.ndarray, int]:
    """VVV12 — sliver tet detection + targeted longest-edge midpoint split.

    For each tet: sliver_score = |V| / L_max^3.  If sliver_score < sliver_ratio,
    find longest edge (i,j), compute midpoint m, split ALL tets incident to that
    edge into 2 sub-tets each (1→2 per tet).  Accept only if q_new_min ≥
    q_old_min + min_quality_improvement over all affected tets; else revert.

    Returns (pts_out, tets_out, n_split).
    """
    n_tets = tets.shape[0]
    if n_tets == 0:
        return pts, tets, 0

    def _vol_and_lmax(p: np.ndarray, tet: np.ndarray) -> tuple[float, float, int, int]:
        """Return (abs_vol, l_max, edge_i, edge_j) for tet."""
        a, b, c, d = p[tet[0]], p[tet[1]], p[tet[2]], p[tet[3]]
        e0, e1, e2 = b - a, c - a, d - a
        vol = abs(float(np.dot(e0, np.cross(e1, e2)))) / 6.0
        verts = [a, b, c, d]
        pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
        best_l = -1.0
        best_i = best_j = 0
        for pi, pj in pairs:
            l = float(np.dot(verts[pi] - verts[pj], verts[pi] - verts[pj]))
            if l > best_l:
                best_l = l
                best_i, best_j = pi, pj
        return vol, float(best_l ** 0.5), tet[best_i], tet[best_j]

    # Detect slivers — PERF5: vectorized numpy screening.
    verts_all = pts[tets]  # (N, 4, 3)
    e0 = verts_all[:, 1] - verts_all[:, 0]
    e1 = verts_all[:, 2] - verts_all[:, 0]
    e2 = verts_all[:, 3] - verts_all[:, 0]
    V_all = np.einsum('ij,ij->i', np.cross(e0, e1), e2) / 6.0
    _e_pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    edge_lengths_all = np.stack(
        [np.linalg.norm(verts_all[:, j] - verts_all[:, i], axis=1) for i, j in _e_pairs],
        axis=1,
    )  # (N, 6)
    L_max_all = edge_lengths_all.max(axis=1)  # (N,)
    sliver_score_all = np.abs(V_all) / np.maximum(L_max_all ** 3, 1e-12)
    candidate_tis = np.where((L_max_all >= 1e-15) & (sliver_score_all < sliver_ratio))[0]

    # Collect unique longest edges for candidate tets.
    sliver_edges: list[tuple[int, int]] = []
    seen_edges: set[tuple[int, int]] = set()
    for ti in candidate_tis:
        _vol, _lmax, ei, ej = _vol_and_lmax(pts, tets[ti])
        u, v = (ei, ej) if ei < ej else (ej, ei)
        if (u, v) not in seen_edges:
            seen_edges.add((u, v))
            sliver_edges.append((u, v))

    n_sliver_detected = len(sliver_edges)

    pts_list = list(pts)
    tets_list = list(tets)
    n_split = 0

    # PERF3: build/reuse edge→incident-tet map (shared with VVV13 via module cache).
    edge_map = compute_edge_incident_tets_cached(tets)

    for edge_i, edge_j in sliver_edges:
        if n_split >= max_splits:
            break

        # Find all tets incident to this edge (use cached map).
        u, v = (edge_i, edge_j) if edge_i < edge_j else (edge_j, edge_i)
        incident: list[int] = [ti for ti in edge_map.get((u, v), [])
                               if ti < len(tets_list)]

        if not incident:
            continue

        # Compute q_old_min over all incident tets.
        pts_arr = np.array(pts_list)
        q_old = min(_tet_quality(pts_arr, np.array(tets_list[ti])) for ti in incident)

        # Midpoint m.
        m = 0.5 * (pts_arr[edge_i] + pts_arr[edge_j])
        m_idx = len(pts_list)
        pts_list.append(m)
        pts_arr_new = np.array(pts_list)

        # Split each incident tet: replace edge_i with m AND edge_j with m.
        new_tets: list[np.ndarray] = []
        for ti in incident:
            tet = list(int(v) for v in tets_list[ti])
            # Sub-tet 1: replace edge_i with m_idx.
            st1 = [m_idx if v == edge_i else v for v in tet]
            # Sub-tet 2: replace edge_j with m_idx.
            st2 = [m_idx if v == edge_j else v for v in tet]
            # VVV12_ORIENT_FIX: ensure positive signed volume.
            st1 = _orient_tet(pts_list, st1)
            st2 = _orient_tet(pts_list, st2)
            new_tets.append(np.array(st1, dtype=tets.dtype))
            new_tets.append(np.array(st2, dtype=tets.dtype))

        # Compute q_new_min.
        q_new = min(_tet_quality(pts_arr_new, nt) for nt in new_tets)

        if q_new >= q_old + min_quality_improvement:
            # Accept: replace incident tets (reverse order to preserve indices).
            for idx, ti in enumerate(sorted(incident, reverse=True)):
                tets_list[ti] = new_tets[2 * (len(incident) - 1 - idx)]
            for idx, ti in enumerate(incident):
                tets_list.append(new_tets[2 * idx + 1])
            n_split += 1
            # PERF3: invalidate module cache (tets_list has changed).
            _invalidate_edge_incident_cache()
        else:
            # Revert: pop midpoint.
            pts_list.pop()

    pts_out = np.array(pts_list)
    tets_out = np.array(tets_list, dtype=tets.dtype)
    return pts_out, tets_out, n_split


# expose sliver detection count for logging
def _count_slivers(pts: np.ndarray, tets: np.ndarray, sliver_ratio: float = 1e-3) -> int:
    """Count sliver tets by V/L_max^3 < sliver_ratio.

    STELLAR_REMAIN_VEC: fully vectorized — no Python loop over tets.
    """
    if tets.shape[0] == 0:
        return 0
    v = pts[tets]  # (N,4,3)
    e0 = v[:, 1] - v[:, 0]; e1 = v[:, 2] - v[:, 0]; e2 = v[:, 3] - v[:, 0]
    vol = np.abs((np.cross(e0, e1) * e2).sum(axis=1)) / 6.0
    _PAIR_I = np.array([0, 0, 0, 1, 1, 2], dtype=np.intp)
    _PAIR_J = np.array([1, 2, 3, 2, 3, 3], dtype=np.intp)
    edge_vecs = v[:, _PAIR_J] - v[:, _PAIR_I]  # (N,6,3)
    l_max = np.sqrt((edge_vecs ** 2).sum(axis=2)).max(axis=1)  # (N,)
    valid = l_max >= 1e-15
    score = np.where(valid, vol / np.maximum(l_max ** 3, 1e-30), 1.0)
    return int((valid & (score < sliver_ratio)).sum())


def lookahead_2flip_chain(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    top_k: int = 5,
    lookahead_ops: tuple[str, ...] = ("flip23", "flip32", "flip44"),
    min_quality_improvement: float = 1e-3,
    max_chains: int = 5,
) -> tuple[np.ndarray, np.ndarray, int]:
    """VVV11 — 2-flip lookahead chain (Klingner 2008 §3.4 multi-step search).

    Escape plateau by allowing flip A even if it temporarily worsens worst_q,
    committing (A, B) only when FINAL worst_q > initial worst_q + min_quality_improvement.

    Returns (pts_out, tets_out, n_chains_committed).
    """
    from .flip import flip_edges_32, flip_edges_44, flip_face_23  # noqa: PLC0415

    _OP_MAP = {
        "flip23": lambda p, t: flip_face_23(p, t, min_quality_improvement=-1.0, max_flips=1),
        "flip32": lambda p, t: (p,) + flip_edges_32(p, t, min_quality_improvement=-1.0, max_flips=1),
        "flip44": lambda p, t: (p,) + flip_edges_44(p, t, min_quality_improvement=-1.0, max_flips=1),
    }

    def _q_arr(p: np.ndarray, t: np.ndarray) -> np.ndarray:
        """PERF10 — vectorized mean-ratio quality for all tets (matches _tet_quality exactly)."""
        if t.shape[0] == 0:
            return np.empty(0, dtype=np.float64)
        v = p[t]  # (N,4,3)
        a = v[:, 0]; b = v[:, 1]; c = v[:, 2]; d = v[:, 3]
        e0 = b - a; e1 = c - a; e2 = d - a
        vol6 = (np.cross(e1, e2) * e0).sum(axis=1)  # scalar triple product
        vol = np.abs(vol6) / 6.0
        l_sq = (
            (e0 ** 2).sum(1) + (e1 ** 2).sum(1) + (e2 ** 2).sum(1)
            + ((b - c) ** 2).sum(1) + ((b - d) ** 2).sum(1) + ((c - d) ** 2).sum(1)
        )
        q = np.where(l_sq > 1e-30, 12.0 * (3.0 * vol) ** (2.0 / 3.0) / l_sq, 0.0)
        return np.clip(q, 0.0, 1.0)

    def _try_first_valid_op(
        p: np.ndarray, t: np.ndarray, ops: tuple[str, ...]
    ) -> tuple[np.ndarray, np.ndarray, int]:
        """Try each op in order; return first result with n_applied > 0."""
        for op in ops:
            fn = _OP_MAP.get(op)
            if fn is None:
                continue
            try:
                result = fn(p, t)
                # flip23 returns (pts, tets, n); flip32/44 return (pts, tets, n) via lambda above
                p_new, t_new, n = result[0], result[1], result[2]
                if n > 0:
                    return p_new, t_new, n
            except Exception:
                continue
        return p, t, 0

    if tets.shape[0] == 0:
        return pts, tets, 0

    qs_pre = _q_arr(pts, tets)
    pre_min = float(qs_pre.min())

    n_chains_committed = 0
    pts_cur, tets_cur = pts.copy(), tets.copy()

    for _ in range(max_chains):
        t0 = time.monotonic()
        qs = _q_arr(pts_cur, tets_cur)
        pre_min_cur = float(qs.min())

        # Snapshot
        pts_snap, tets_snap = pts_cur.copy(), tets_cur.copy()

        # Flip A — no per-flip guard (accept any valid)
        pts_a, tets_a, na = _try_first_valid_op(pts_cur, tets_cur, lookahead_ops)
        if na == 0:
            break  # No valid op A found for any tet
        if time.monotonic() - t0 > 0.05:
            break

        # Flip B — on worst tet after A
        pts_b, tets_b, nb = _try_first_valid_op(pts_a, tets_a, lookahead_ops)
        # nb may be 0 — still evaluate chain quality

        post_min = float(_q_arr(pts_b, tets_b).min())

        # Strict chain guard: commit only if overall improvement
        if post_min >= pre_min_cur + min_quality_improvement:
            pts_cur, tets_cur = pts_b, tets_b
            n_chains_committed += 1
        else:
            # Revert to snapshot
            pts_cur, tets_cur = pts_snap, tets_snap
            break  # No more useful chains from this state

    return pts_cur, tets_cur, n_chains_committed


def split_anisotropic_tet_edges(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    ar_threshold: float = 5.0,
    min_quality_improvement: float = 1e-3,
    max_splits: int = 20,
) -> tuple[np.ndarray, np.ndarray, int]:
    """VVV13 — anisotropic tet detection + longest-edge midpoint split (fTetWild §3.2 style).

    For each tet: edge_length_ratio = max_edge / min_edge (AR).
    If AR > ar_threshold AND tet quality < 0.3 → mark as anisotropic candidate.
    Longest edge of candidate is split at midpoint; all incident tets are replaced.
    Accept only if q_new_min >= q_old_min + min_quality_improvement; else revert.
    Cap total splits at max_splits.

    Returns (pts_out, tets_out, n_split).
    """
    n_tets = tets.shape[0]
    if n_tets == 0:
        return pts, tets, 0

    # PERF2: vectorized AR screening (replaces per-tet Python loop).
    _PAIR_I = np.array([0, 0, 0, 1, 1, 2], dtype=np.intp)
    _PAIR_J = np.array([1, 2, 3, 2, 3, 3], dtype=np.intp)
    _PAIRS = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]

    # --- vectorized screening ---
    verts_all = pts[tets]  # (N,4,3)
    # 6 edge lengths for all tets
    edge_vecs = verts_all[:, _PAIR_J] - verts_all[:, _PAIR_I]  # (N,6,3)
    edge_lens = np.sqrt((edge_vecs ** 2).sum(axis=2))           # (N,6)
    l_max = edge_lens.max(axis=1)
    l_min = edge_lens.min(axis=1)
    ar_all = l_max / np.maximum(l_min, 1e-12)

    # quality for all tets (vectorized mean-ratio, matches _tet_quality exactly)
    a = verts_all[:, 0]; b = verts_all[:, 1]
    c = verts_all[:, 2]; d = verts_all[:, 3]
    e0 = b - a; e1 = c - a; e2 = d - a
    # vol6 = dot(e0, cross(e1,e2)) — scalar triple product
    vol6 = (np.cross(e1, e2) * e0).sum(axis=1)
    # l_sq = sum of all 6 squared edge lengths
    l_sq = ((e0**2).sum(1) + (e1**2).sum(1) + (e2**2).sum(1)
            + ((b-c)**2).sum(1) + ((b-d)**2).sum(1) + ((c-d)**2).sum(1))
    vol = np.abs(vol6) / 6.0
    q_all = np.where(l_sq > 1e-30, 12.0 * (3.0 * vol) ** (2.0/3.0) / l_sq, 0.0)
    q_all = np.clip(q_all, 0.0, 1.0)

    mask = (ar_all > ar_threshold) & (q_all < 0.3)
    cand_indices = np.where(mask)[0]

    # build aniso_edges from candidates (longest edge per tet)
    aniso_edges: list[tuple[int, int]] = []
    seen_edges: set[tuple[int, int]] = set()
    for ti in cand_indices:
        best_pair = int(np.argmax(edge_lens[ti]))
        pi, pj = _PAIRS[best_pair]
        ei, ej = int(tets[ti, pi]), int(tets[ti, pj])
        u, v = (ei, ej) if ei < ej else (ej, ei)
        if (u, v) not in seen_edges:
            seen_edges.add((u, v))
            aniso_edges.append((u, v))

    pts_list = list(pts)
    tets_list = list(tets)
    n_split = 0

    # PERF3: build/reuse edge→incident-tet map (shared with VVV12 via module cache).
    edge_map = compute_edge_incident_tets_cached(tets)

    for edge_i, edge_j in aniso_edges:
        if n_split >= max_splits:
            break

        # Find all tets incident to this edge (use cached map).
        u, v = (edge_i, edge_j) if edge_i < edge_j else (edge_j, edge_i)
        incident: list[int] = [ti for ti in edge_map.get((u, v), [])
                               if ti < len(tets_list)]

        if not incident:
            continue

        # Compute q_old_min over all incident tets.
        pts_arr = np.array(pts_list)
        q_old = min(_tet_quality(pts_arr, np.array(tets_list[ti])) for ti in incident)

        # Midpoint m.
        m = 0.5 * (pts_arr[edge_i] + pts_arr[edge_j])
        m_idx = len(pts_list)
        pts_list.append(m)
        pts_arr_new = np.array(pts_list)

        # Split each incident tet: replace edge_i with m AND edge_j with m.
        new_tets: list[np.ndarray] = []
        for ti in incident:
            tet = list(int(v) for v in tets_list[ti])
            st1 = [m_idx if v == edge_i else v for v in tet]
            st2 = [m_idx if v == edge_j else v for v in tet]
            # VVV12_ORIENT_FIX: ensure positive signed volume.
            st1 = _orient_tet(pts_list, st1)
            st2 = _orient_tet(pts_list, st2)
            new_tets.append(np.array(st1, dtype=tets.dtype))
            new_tets.append(np.array(st2, dtype=tets.dtype))

        # Compute q_new_min.
        q_new = min(_tet_quality(pts_arr_new, nt) for nt in new_tets)

        if q_new >= q_old + min_quality_improvement:
            # Accept.
            for idx, ti in enumerate(sorted(incident, reverse=True)):
                tets_list[ti] = new_tets[2 * (len(incident) - 1 - idx)]
            for idx, ti in enumerate(incident):
                tets_list.append(new_tets[2 * idx + 1])
            n_split += 1
            # PERF3: invalidate module cache (tets_list has changed).
            _invalidate_edge_incident_cache()
        else:
            # Revert.
            pts_list.pop()

    pts_out = np.array(pts_list)
    tets_out = np.array(tets_list, dtype=tets.dtype)
    return pts_out, tets_out, n_split


def _count_anisotropic(
    pts: np.ndarray, tets: np.ndarray, ar_threshold: float = 5.0
) -> int:
    """Count anisotropic tets (AR > ar_threshold AND quality < 0.3).

    STELLAR_REMAIN_VEC: fully vectorized — no Python loop over tets.
    """
    if tets.shape[0] == 0:
        return 0
    v = pts[tets]  # (N,4,3)
    _PAIR_I = np.array([0, 0, 0, 1, 1, 2], dtype=np.intp)
    _PAIR_J = np.array([1, 2, 3, 2, 3, 3], dtype=np.intp)
    edge_vecs = v[:, _PAIR_J] - v[:, _PAIR_I]  # (N,6,3)
    edge_lens = np.sqrt((edge_vecs ** 2).sum(axis=2))  # (N,6)
    l_max = edge_lens.max(axis=1)
    l_min = edge_lens.min(axis=1)
    ar = l_max / np.maximum(l_min, 1e-15)
    # Vectorized mean-ratio quality.
    _a = v[:, 0]; _b = v[:, 1]; _c = v[:, 2]; _d = v[:, 3]
    e0 = _b - _a; e1 = _c - _a; e2 = _d - _a
    vol6 = (np.cross(e1, e2) * e0).sum(axis=1)
    l_sq = (
        (e0 ** 2).sum(1) + (e1 ** 2).sum(1) + (e2 ** 2).sum(1)
        + ((_b - _c) ** 2).sum(1) + ((_b - _d) ** 2).sum(1) + ((_c - _d) ** 2).sum(1)
    )
    q_all = np.where(
        l_sq > 1e-30,
        np.clip(12.0 * (3.0 * np.abs(vol6) / 6.0) ** (2.0 / 3.0) / l_sq, 0.0, 1.0),
        0.0,
    )
    return int(((ar > ar_threshold) & (q_all < 0.3)).sum())


# ---------------------------------------------------------------------------
# VVV14 (beta2154) — face-centroid Steiner insertion (worst-face-fan, 1+1→6)
# ---------------------------------------------------------------------------

def insert_face_centroid_steiner(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    top_k: int = 5,
    min_quality_improvement: float = 1e-3,
    max_inserts: int = 10,
) -> tuple[np.ndarray, np.ndarray, int]:
    """VVV14 — face-centroid Steiner insertion for worst tets.

    Different from VVV9 (cell-centroid → 4 sub-tets), VVV12 (longest-edge midpoint),
    VVV13 (aniso edge midpoint).  VVV14 inserts at the centroid of the WORST FACE
    of a worst tet, splitting both incident tets via the new vertex (1+1→6 sub-tets).

    Algorithm:
      1. Compute per-tet quality; pick top_k worst.
      2. For each worst tet T=[a,b,c,d]:
         - For each of T's 4 faces, compute face_badness = 1 / (face_area / circumradius).
         - Pick worst face f_worst = {a,b,c}, opposite vert = d.
         - Find the OTHER tet T' sharing f_worst (if any); skip if boundary face.
         - Insert m = centroid(f_worst).
         - Replace T  with 3 sub-tets: [a,b,m,d], [b,c,m,d], [c,a,m,d].
         - Replace T' with 3 sub-tets using T''s opposite vert.
         - STRICT GUARD: q_new_min >= q_old_min + min_quality_improvement; else revert.
      3. Cap at max_inserts.

    Returns (pts_out, tets_out, n_inserted).
    """
    n_tets = tets.shape[0]
    if n_tets == 0:
        return pts, tets, 0

    # PERF7: face-local index triples (a,b,c) and opposite index for each of 4 faces.
    # Shape kept as arrays for vectorized worst-face identification below.
    _FACE_ABC = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.intp)  # (4,3)
    _FACE_OPP = np.array([3, 2, 1, 0], dtype=np.intp)  # opposite local index per face

    # PERF4: use cached face→incident-tet map (avoids per-call O(N) rebuild).
    face_to_tets = compute_face_incident_tets_cached(tets)

    # PERF7 Step 1 — vectorized per-tet quality (mirrors _tet_quality mean-ratio formula).
    verts_all = pts[tets]                           # (N,4,3)
    a = verts_all[:, 0]; b = verts_all[:, 1]
    c = verts_all[:, 2]; d = verts_all[:, 3]
    e0 = b - a; e1 = c - a; e2 = d - a
    vol6 = (np.cross(e1, e2) * e0).sum(axis=1)     # scalar triple product × 6
    l_sq = (
        (e0 ** 2).sum(1) + (e1 ** 2).sum(1) + (e2 ** 2).sum(1)
        + ((b - c) ** 2).sum(1) + ((b - d) ** 2).sum(1) + ((c - d) ** 2).sum(1)
    )
    qualities = np.where(
        l_sq > 1e-30,
        np.clip(12.0 * (3.0 * np.abs(vol6) / 6.0) ** (2.0 / 3.0) / l_sq, 0.0, 1.0),
        0.0,
    )
    worst_indices = np.argsort(qualities)[: top_k]

    pts_list = list(pts)
    tets_list = [tets[i].copy() for i in range(n_tets)]
    n_inserted = 0
    invalidated: set[int] = set()

    for ti in worst_indices:
        if n_inserted >= max_inserts:
            break
        if ti in invalidated:
            continue

        tet = tets_list[ti]
        verts = [int(tet[k]) for k in range(4)]

        # PERF7 Step 2 — vectorized worst-face identification over 4 faces.
        # Build (4,3) vertex positions for each face's 3 corners.
        pts_arr = np.array(pts_list)
        verts_np = np.array(verts, dtype=np.intp)          # (4,)
        face_verts = pts_arr[verts_np[_FACE_ABC]]           # (4,3,3)
        va = face_verts[:, 0]; vb = face_verts[:, 1]; vc = face_verts[:, 2]
        ab = vb - va; ac = vc - va
        cross_f = np.cross(ab, ac)                          # (4,3)
        area2 = np.sqrt((cross_f ** 2).sum(axis=1))         # (4,) = 2*area
        area = area2 * 0.5
        la = np.sqrt(((vb - vc) ** 2).sum(axis=1))
        lb = np.sqrt(((va - vc) ** 2).sum(axis=1))
        lc = np.sqrt(((va - vb) ** 2).sum(axis=1))
        R = la * lb * lc / np.maximum(4.0 * area, 1e-30)   # circumradius per face
        badness = np.where(area > 1e-30, R / area, 1e30)   # (4,) R/area = 1/(area/R)
        worst_fi = int(np.argmax(badness))
        fi, fj, fk = _FACE_ABC[worst_fi]
        opp_local = int(_FACE_OPP[worst_fi])
        fi, fj, fk = int(fi), int(fj), int(fk)
        fa, fb, fc = verts[fi], verts[fj], verts[fk]
        d_vert = verts[opp_local]

        # Find the OTHER tet sharing this face.
        face_key: tuple[int, int, int] = tuple(sorted([fa, fb, fc]))  # type: ignore[assignment]
        neighbors = [t for t in face_to_tets.get(face_key, []) if t != ti and t not in invalidated]
        if not neighbors:
            continue  # Boundary face — skip.
        ti2 = neighbors[0]

        tet2 = tets_list[ti2]
        verts2 = [int(tet2[k]) for k in range(4)]
        # Opposite vert of tet2 w.r.t. face {fa,fb,fc}
        face_set = {fa, fb, fc}
        opp2_list = [v for v in verts2 if v not in face_set]
        if not opp2_list:
            continue
        d2_vert = opp2_list[0]

        # q_old_min over both tets.
        q_old = min(
            _tet_quality(pts_arr, np.array(tets_list[ti])),
            _tet_quality(pts_arr, np.array(tets_list[ti2])),
        )

        # Steiner point = centroid of face f_worst.
        m = (pts_arr[fa] + pts_arr[fb] + pts_arr[fc]) / 3.0
        m_idx = len(pts_list)
        pts_list.append(m)
        pts_arr_new = np.array(pts_list)

        dtype = tets.dtype
        sub_T = [
            np.array([fa, fb, m_idx, d_vert], dtype=dtype),
            np.array([fb, fc, m_idx, d_vert], dtype=dtype),
            np.array([fc, fa, m_idx, d_vert], dtype=dtype),
        ]
        sub_T2 = [
            np.array([fa, fb, m_idx, d2_vert], dtype=dtype),
            np.array([fb, fc, m_idx, d2_vert], dtype=dtype),
            np.array([fc, fa, m_idx, d2_vert], dtype=dtype),
        ]

        all_new = sub_T + sub_T2
        q_new_min = min(_tet_quality(pts_arr_new, nt) for nt in all_new)

        if q_new_min >= q_old + min_quality_improvement:
            # Accept: replace both tets.
            tets_list[ti] = sub_T[0]
            tets_list[ti2] = sub_T2[0]
            tets_list.extend(sub_T[1:] + sub_T2[1:])
            invalidated.add(ti)
            invalidated.add(ti2)
            n_inserted += 1
        else:
            # Revert: pop m.
            pts_list.pop()

    pts_out = np.array(pts_list)
    tets_out = np.array(tets_list, dtype=tets.dtype)
    return pts_out, tets_out, n_inserted


# ---------------------------------------------------------------------------
# VVV9B (beta2246) — off-plane sliver Steiner skeleton (default OFF)
# fTetWild §3.4 + Klingner & Shewchuk 2008 §4 + Du & Wang 2003 sliver exudation
# ---------------------------------------------------------------------------

_VVV9B_OFFPLANE: bool = False  # skeleton gate — activated in next card (VVV9C)


def compute_offplane_steiner_point(
    pts: "np.ndarray",
    tet: "np.ndarray",
    *,
    eps_factor: float = 0.05,
    flatness_thresh: float = 1e-2,
) -> "tuple[np.ndarray | None, float]":
    """Compute an off-plane Steiner point for a coplanar (sliver) tet.

    Uses SVD of the centred 4-vertex matrix to find the plane normal (smallest
    singular vector).  Returns (None, flatness) when the tet is *not* coplanar
    enough (flatness >= flatness_thresh).  Otherwise returns
    (c + eps_factor * l_max * n_hat, flatness).

    Parameters
    ----------
    pts:             full point array  (N, 3)
    tet:             4-element index array
    eps_factor:      fraction of l_max to offset Steiner from centroid
    flatness_thresh: flatness ratio above which tet is not considered a sliver

    Returns
    -------
    (steiner_point | None, flatness)
    """
    verts = pts[tet]                            # (4, 3)
    c = verts.mean(axis=0)
    centered = verts - c
    _U, _S, Vt = np.linalg.svd(centered, full_matrices=False)
    n_hat = Vt[-1]                              # smallest-singular-value direction = plane normal
    pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    l_max = max(float(np.linalg.norm(verts[i] - verts[j])) for i, j in pairs)
    h = float(np.abs(centered @ n_hat).max())
    flatness = h / max(l_max, 1e-30)
    if flatness >= flatness_thresh:
        return None, flatness                   # not coplanar enough — skip
    return c + (eps_factor * l_max) * n_hat, flatness


def _count_offplane_sliver_candidates(
    pts: "np.ndarray",
    tets: "np.ndarray",
    *,
    flatness_thresh: float = 1e-2,
) -> int:
    """Count tets whose flatness ratio is below *flatness_thresh* (diagnostic).

    Not called by any active path — reserved for VVV9C activation card.
    """
    count = 0
    for tet in tets:
        _, flatness = compute_offplane_steiner_point(
            pts, tet, flatness_thresh=flatness_thresh
        )
        if flatness < flatness_thresh:
            count += 1
    return count


# ---------------------------------------------------------------------------
# VVV9D (beta2248) — off-plane top-K Steiner action helper (no caller)
# ---------------------------------------------------------------------------

def _apply_offplane_steiner_topK(
    pts: "np.ndarray",
    tets: "np.ndarray",
    *,
    top_k: int = 3,
    eps_factor: float = 0.05,
    flatness_thresh: float = 1e-2,
) -> "tuple[np.ndarray, np.ndarray, int]":
    """Apply off-plane Steiner insertions to the top-K flattest slivers.

    Algorithm: 1-tet local 4-subdivision (no scipy Delaunay rebuild).
    Quality bound: Klingner & Shewchuk 2008 Theorem 4.1.

    **caller 없음** — R184/VVV9E 에서 wire 예정.
    ``_VVV9B_OFFPLANE`` gate 는 False 유지 (이 카드는 정의만).

    Parameters
    ----------
    pts : np.ndarray, shape (N, 3)
    tets : np.ndarray, shape (M, 4)
    top_k : int
        Hard cap on number of Steiner insertions (wall-time bound).
    eps_factor : float
        Offset magnitude passed to ``compute_offplane_steiner_point``.
    flatness_thresh : float
        Candidate gate: only tets with flatness < this value are considered.

    Returns
    -------
    pts_out, tets_out : np.ndarray
        Modified copies (shallow-copy via list round-trip).
    n_inserted : int
        Number of Steiner points actually inserted (≤ top_k).
    """
    pts_list = pts.tolist()
    tets_list = tets.tolist()
    n_inserted = 0

    # --- collect candidates ---
    cands: "list[tuple[float, int]]" = []
    for idx, tet in enumerate(tets_list):
        _, flatness = compute_offplane_steiner_point(
            np.array(pts_list, dtype=pts.dtype),
            tet,
            flatness_thresh=flatness_thresh,
            eps_factor=eps_factor,
        )
        if flatness < flatness_thresh:
            cands.append((flatness, idx))

    # --- top-K flattest first ---
    cands.sort(key=lambda p: p[0])
    cands = cands[:top_k]

    # --- 1-tet local 4-subdivision with sign guard ---
    for _, ti in cands:
        cur_pts = np.array(pts_list, dtype=pts.dtype)
        v0, v1, v2, v3 = tets_list[ti]
        m, _ = compute_offplane_steiner_point(
            cur_pts,
            [v0, v1, v2, v3],
            flatness_thresh=flatness_thresh,
            eps_factor=eps_factor,
        )
        if m is None:
            continue

        mi = len(pts_list)

        def _svol(a: int, b: int, c: int, d: int) -> float:
            p = cur_pts
            e0 = p[b] - p[a]
            e1 = p[c] - p[a]
            e2 = p[d] - p[a]
            return float(np.dot(np.cross(e0, e1), e2))

        s0 = _svol(v0, v1, v2, v3)
        if s0 == 0.0:
            continue

        # temporarily extend pts for sub-tet sign checks
        extended = np.vstack([cur_pts, np.array(m, dtype=pts.dtype).reshape(1, 3)])

        def _svol_ext(a: int, b: int, c: int, d: int) -> float:
            e0 = extended[b] - extended[a]
            e1 = extended[c] - extended[a]
            e2 = extended[d] - extended[a]
            return float(np.dot(np.cross(e0, e1), e2))

        sub_tets = [
            [v0, v1, v2, mi],
            [v0, v1, mi, v3],
            [v0, mi, v2, v3],
            [mi, v1, v2, v3],
        ]
        signs_ok = all(_svol_ext(*st) * s0 > 0 for st in sub_tets)
        if not signs_ok:
            continue  # revert — skip insertion

        pts_list.append(list(m))
        tets_list[ti] = sub_tets[0]
        tets_list.append(sub_tets[1])
        tets_list.append(sub_tets[2])
        tets_list.append(sub_tets[3])
        n_inserted += 1

    return (
        np.array(pts_list, dtype=pts.dtype),
        np.array(tets_list, dtype=tets.dtype),
        n_inserted,
    )


# ---------------------------------------------------------------------------
# VVV9F (beta2251) — Cheng-Dey-Edelsbrunner sliver exudation skeleton
# Reference: Cheng, Dey, Edelsbrunner, Facello, Teng 1999 "Sliver Exudation"
#            (FOCS '99 §3–§4); Cheng-Dey 2002 SIAM JC §2–§3.
# Gate default OFF — no caller yet; activated in subsequent card.
# ---------------------------------------------------------------------------

_VVV9F_EXUDATION: bool = False  # skeleton gate — activated in next card


def _compute_exudation_weight_candidates(
    pts: "np.ndarray",
    tets: "np.ndarray",
    *,
    n_candidates: int = 8,
    alpha: float = 0.3,
    seed: int = 0,
) -> "np.ndarray":
    """Compute per-vertex weight candidates for Cheng-Dey exudation (skeleton).

    Each vertex v receives weight w(v) = (alpha * l_min(v))^2 where l_min(v)
    is the shortest incident edge length.  Paper §4 perturbation model:
    w(v) in [0, omega_0^2 * rho^2].  This card returns zeros (skeleton
    placeholder); actual weight sampling added in the subsequent card.

    Parameters
    ----------
    pts          : (N, 3) float array of vertex positions.
    tets         : (M, 4) int array of tet vertex indices.
    n_candidates : number of random weight vectors to sample (unused here).
    alpha        : perturbation scale factor (unused here).
    seed         : RNG seed (unused here).

    Returns
    -------
    weights : (N,) float array — zeros (placeholder).
    """
    n_verts = pts.shape[0]
    # Skeleton: compute l_min per vertex (incident edge shortest length).
    # Build edge list from tets (6 edges per tet, 4-choose-2).
    _PAIRS = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    if tets.shape[0] > 0:
        l_min = np.full(n_verts, np.inf, dtype=pts.dtype)
        for a, b in _PAIRS:
            va = tets[:, a]
            vb = tets[:, b]
            d = np.linalg.norm(pts[va] - pts[vb], axis=1)
            np.minimum.at(l_min, va, d)
            np.minimum.at(l_min, vb, d)
        l_min[l_min == np.inf] = 0.0
    # Return zeros — actual weight sampling deferred to subsequent card.
    return np.zeros(n_verts, dtype=pts.dtype)


def _evaluate_weighted_quality_proxy(
    pts: "np.ndarray",
    tets: "np.ndarray",
    weights: "np.ndarray",
) -> float:
    """Evaluate worst-q proxy for a given per-vertex weight assignment.

    This is a no-op proxy: weights are validated but ignored; actual
    weighted-Delaunay quality evaluation is deferred to a subsequent card.

    Parameters
    ----------
    pts     : (N, 3) float array of vertex positions.
    tets    : (M, 4) int array of tet vertex indices.
    weights : (N,) float array — per-vertex non-negative weights.

    Returns
    -------
    float : worst aspect-ratio quality (via existing _tet_quality per tet).
    """
    assert weights.shape == (pts.shape[0],), (
        f"weights shape {weights.shape} != (N,) = ({pts.shape[0]},)"
    )
    assert (weights >= 0).all(), "weights must be non-negative"
    if tets.shape[0] == 0:
        return 1.0
    return float(min(_tet_quality(pts, t) for t in tets))


# ---------------------------------------------------------------------------
# VVV9F #2 (beta2253) — Cheng-Dey 1999 §4 Algo 4.1 step 1: weight-space sampling
# Skeleton helper — no caller, no gate variable added (_VVV9F_EXUDATION gates seq).
# ---------------------------------------------------------------------------

def _perturb_weights_topK(
    pts: "np.ndarray",
    tets: "np.ndarray",
    *,
    n_samples: int = 8,
    alpha: float = 0.3,
    seed: int = 0,
) -> "np.ndarray":
    """Sample (n_samples, N) weight matrix for Cheng-Dey sliver exudation.

    For each vertex v, computes ω₀(v) = α · l_min(v) where l_min(v) is the
    minimum edge length incident to v across all tets.  Returns a matrix W of
    shape (n_samples, N) where W[k, v] ~ Uniform(0, ω₀(v)²), matching
    Cheng-Dey-Edelsbrunner-Facello-Teng 1999 §4 Algo 4.1 step 1.

    Skeleton: selection / helper #2 call not performed here.
    Pure function — mesh arrays unchanged.

    Parameters
    ----------
    pts : ndarray, shape (N, 3)
    tets : ndarray, shape (M, 4)
    n_samples : int, >= 1
    alpha : float, > 0   (ω₀ = alpha · l_min fraction)
    seed : int            (numpy default_rng seed for reproducibility)

    Returns
    -------
    W : ndarray, shape (n_samples, N)  — sampled squared weights
    """
    assert pts.ndim == 2 and pts.shape[1] == 3, (
        f"pts must be (N,3), got {pts.shape}"
    )
    assert tets.ndim == 2 and tets.shape[1] == 4, (
        f"tets must be (M,4), got {tets.shape}"
    )
    assert n_samples >= 1, f"n_samples must be >= 1, got {n_samples}"
    assert alpha > 0, f"alpha must be > 0, got {alpha}"

    N = pts.shape[0]
    if tets.shape[0] == 0:
        return np.zeros((n_samples, N))

    # Compute l_min(v): minimum edge length over all 6 pairs per tet
    _EDGE_PAIRS = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    l_min = np.full(N, np.inf)
    for t in tets:
        for i, j in _EDGE_PAIRS:
            d = float(np.linalg.norm(pts[t[i]] - pts[t[j]]))
            if d < l_min[t[i]]:
                l_min[t[i]] = d
            if d < l_min[t[j]]:
                l_min[t[j]] = d
    # Isolated vertices (not in any tet): l_min stays inf → ω₀²=0 → weight=0
    l_min = np.where(np.isinf(l_min), 0.0, l_min)

    omega0_sq = (alpha * l_min) ** 2  # shape (N,)

    rng = np.random.default_rng(seed)
    W = rng.uniform(0.0, omega0_sq, size=(n_samples, N))  # shape (n_samples, N)
    return W


# ---------------------------------------------------------------------------
# VVV9F4 (beta2254) — Cheng-Dey 1999 §4 Algo 4.1 step 2: best-of-K selector
# ---------------------------------------------------------------------------

def _select_best_weight_assignment(
    pts: "np.ndarray",
    tets: "np.ndarray",
    weight_matrix: "np.ndarray",
    *,
    alpha: float = 0.3,
) -> "tuple[int, float]":
    """Select the weight assignment (row) that maximises the worst-tet quality.

    Implements Cheng-Dey-Edelsbrunner-Facello-Teng 1999 §4 Algo 4.1 step 2
    (FOCS '99 pp.291) — max-min weight assignment selection:
        k* = argmax_k  min_t Q(t; W[k, :])

    Cheng-Dey 2002 SIAM JC §3.2 proves best-of-K raises ρ-quality guarantee.

    SKELETON — no caller yet.  pts/tets are read-only; mesh state unchanged.
    Gate: _VVV9F_EXUDATION controls the full sequence (set in a later card).

    Parameters
    ----------
    pts : np.ndarray, shape (N, 3)
    tets : np.ndarray, shape (M, 4)
    weight_matrix : np.ndarray, shape (K, N)  — K candidate assignments
    alpha : float > 0  — passed through for documentation; not used in argmax

    Returns
    -------
    best_idx : int   — row index k* in [0, K)
    best_min_q : float — min-quality of the best assignment
    """
    assert pts.ndim == 2 and pts.shape[1] == 3, "pts must be (N, 3)"
    assert tets.ndim == 2 and tets.shape[1] == 4, "tets must be (M, 4)"
    assert weight_matrix.ndim == 2, "weight_matrix must be 2-D (K, N)"
    N = pts.shape[0]
    K = weight_matrix.shape[0]
    assert weight_matrix.shape[1] == N, "weight_matrix.shape[1] must equal N"
    assert K >= 1, "K must be >= 1"
    assert alpha > 0, "alpha must be positive"
    assert (weight_matrix >= 0).all(), "all weights must be non-negative"

    # Early exit when mesh is empty
    if tets.shape[0] == 0:
        return (0, 1.0)

    best_idx: int = 0
    best_min_q: float = -1.0

    for k in range(K):
        q_k = _evaluate_weighted_quality_proxy(pts, tets, weight_matrix[k])
        if q_k > best_min_q:
            best_min_q = q_k
            best_idx = k

    return (best_idx, best_min_q)


# ---------------------------------------------------------------------------
# VAL1 (beta2147) — global negative-volume tet detection + auto-flip
# ---------------------------------------------------------------------------
# VAL3 (beta2158) — per-pass negative-volume counter
# ---------------------------------------------------------------------------

def _count_neg_vol(pts: "np.ndarray", tets: "np.ndarray") -> int:
    """Return number of tets with negative signed volume (wrong orientation)."""
    if tets.shape[0] == 0:
        return 0
    e0 = pts[tets[:, 1]] - pts[tets[:, 0]]
    e1 = pts[tets[:, 2]] - pts[tets[:, 0]]
    e2 = pts[tets[:, 3]] - pts[tets[:, 0]]
    v = np.einsum("ij,ij->i", np.cross(e0, e1), e2) / 6.0
    return int((v < 0).sum())


# ---------------------------------------------------------------------------

def validate_and_fix_orientations(
    pts: "np.ndarray", tets: "np.ndarray"
) -> "tuple[np.ndarray, int, int]":
    """Scan all tets for V<=0 and fix orientation by swapping last two verts.

    Returns
    -------
    tets_fixed : np.ndarray
        Tet array with flipped orientations for negative-volume tets.
    n_flipped : int
        Number of tets whose orientation was flipped (V<0 -> V>0).
    n_degenerate : int
        Number of tets with V~=0 after attempted fix (left as-is).
    """
    tets_out = tets.copy()

    a = pts[tets_out[:, 0]]
    b = pts[tets_out[:, 1]]
    c = pts[tets_out[:, 2]]
    d = pts[tets_out[:, 3]]
    vols = (1.0 / 6.0) * (
        np.einsum("ij,ij->i", d - a, np.cross(b - a, c - a))
    )

    neg_mask = vols < 0.0

    if neg_mask.any():
        # swap last two verts: [a,b,c,d] -> [a,b,d,c] flips orientation
        tmp = tets_out[neg_mask, 2].copy()
        tets_out[neg_mask, 2] = tets_out[neg_mask, 3]
        tets_out[neg_mask, 3] = tmp

    n_flipped = int(neg_mask.sum())

    # Re-check degenerate after fix
    a2 = pts[tets_out[:, 0]]
    b2 = pts[tets_out[:, 1]]
    c2 = pts[tets_out[:, 2]]
    d2 = pts[tets_out[:, 3]]
    vols2 = (1.0 / 6.0) * (
        np.einsum("ij,ij->i", d2 - a2, np.cross(b2 - a2, c2 - a2))
    )
    n_degenerate = int((np.abs(vols2) < 1e-15).sum())

    return tets_out, n_flipped, n_degenerate
