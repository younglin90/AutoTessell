"""
CARD VVV1 (beta2114) — Stellar 4-op iterative coordinator (skeleton).
Klingner & Shewchuk 2008 §3.
"""
from __future__ import annotations

import time

import numpy as np

# VVV1: skeleton only — default OFF, no call path added
_VVV1_STELLAR_QUEUE: bool = True


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
    """
    queue: list[dict] = []
    for i, tet in enumerate(tets):
        q = _tet_quality(pts, tet)
        candidate_ops: list[str] = []
        if q < 0.3:
            candidate_ops = ["collapse", "split", "swap", "smooth"]
        elif q < 0.6:
            candidate_ops = ["swap", "smooth"]
        else:
            candidate_ops = ["smooth"]
        queue.append({"quality": q, "tet_idx": i, "candidate_ops": candidate_ops})
    queue.sort(key=lambda x: x["quality"])
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

    # Collect worst-tier tet indices (quality < 0.3, queue is sorted ascending).
    worst_entries = [e for e in queue if e["quality"] < 0.3]
    if not worst_entries:
        return pts, tets, 0

    # Gather candidate edges from worst tets, dedup.
    candidate_edge_set: set[tuple[int, int]] = set()
    for entry in worst_entries:
        ti = entry["tet_idx"]
        if ti >= tets.shape[0]:
            continue
        tet = tets[ti]
        for i in range(4):
            for j in range(i + 1, 4):
                u, v = int(tet[i]), int(tet[j])
                if u > v:
                    u, v = v, u
                candidate_edge_set.add((u, v))

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

    # Compute quality for all tets.
    qualities = np.array([_tet_quality(pts, tets[i]) for i in range(n_tets)], dtype=np.float64)

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

    # Detect slivers.
    sliver_edges: list[tuple[int, int]] = []
    seen_edges: set[tuple[int, int]] = set()
    for ti in range(n_tets):
        vol, lmax, ei, ej = _vol_and_lmax(pts, tets[ti])
        if lmax < 1e-15:
            continue
        score = vol / (lmax ** 3)
        if score < sliver_ratio:
            u, v = (ei, ej) if ei < ej else (ej, ei)
            if (u, v) not in seen_edges:
                seen_edges.add((u, v))
                sliver_edges.append((u, v))

    n_sliver_detected = len(sliver_edges)

    pts_list = list(pts)
    tets_list = list(tets)
    n_split = 0

    for edge_i, edge_j in sliver_edges:
        if n_split >= max_splits:
            break

        # Find all tets incident to this edge.
        incident: list[int] = []
        for ti, tet in enumerate(tets_list):
            tet_set = set(int(v) for v in tet)
            if edge_i in tet_set and edge_j in tet_set:
                incident.append(ti)

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
        else:
            # Revert: pop midpoint.
            pts_list.pop()

    pts_out = np.array(pts_list)
    tets_out = np.array(tets_list, dtype=tets.dtype)
    return pts_out, tets_out, n_split


# expose sliver detection count for logging
def _count_slivers(pts: np.ndarray, tets: np.ndarray, sliver_ratio: float = 1e-3) -> int:
    """Count sliver tets by V/L_max^3 < sliver_ratio."""
    count = 0
    for i in range(tets.shape[0]):
        a, b, c, d = pts[tets[i, 0]], pts[tets[i, 1]], pts[tets[i, 2]], pts[tets[i, 3]]
        e0, e1, e2 = b - a, c - a, d - a
        vol = abs(float(np.dot(e0, np.cross(e1, e2)))) / 6.0
        verts = [a, b, c, d]
        pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
        lmax = max(float(np.dot(verts[pi] - verts[pj], verts[pi] - verts[pj])) ** 0.5
                   for pi, pj in pairs)
        if lmax < 1e-15:
            continue
        if vol / (lmax ** 3) < sliver_ratio:
            count += 1
    return count


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
        return np.array([_tet_quality(p, t[i]) for i in range(t.shape[0])], dtype=np.float64)

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

    for edge_i, edge_j in aniso_edges:
        if n_split >= max_splits:
            break

        # Find all tets incident to this edge.
        incident: list[int] = []
        for ti, tet in enumerate(tets_list):
            tet_set = set(int(v) for v in tet)
            if edge_i in tet_set and edge_j in tet_set:
                incident.append(ti)

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
        else:
            # Revert.
            pts_list.pop()

    pts_out = np.array(pts_list)
    tets_out = np.array(tets_list, dtype=tets.dtype)
    return pts_out, tets_out, n_split


def _count_anisotropic(
    pts: np.ndarray, tets: np.ndarray, ar_threshold: float = 5.0
) -> int:
    """Count anisotropic tets (AR > ar_threshold AND quality < 0.3)."""
    _PAIRS = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    count = 0
    for i in range(tets.shape[0]):
        q = _tet_quality(pts, tets[i])
        if q >= 0.3:
            continue
        verts = [pts[tets[i, k]] for k in range(4)]
        lengths = [float(np.dot(verts[pi] - verts[pj], verts[pi] - verts[pj])) ** 0.5
                   for pi, pj in _PAIRS]
        l_min = min(lengths)
        l_max = max(lengths)
        ar = l_max / l_min if l_min > 1e-15 else float("inf")
        if ar > ar_threshold:
            count += 1
    return count


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

    _FACES = [(0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 3, 1), (1, 2, 3, 0)]  # (a,b,c, opp)

    def _face_badness(p: np.ndarray, va: np.ndarray, vb: np.ndarray, vc: np.ndarray) -> float:
        """1 / (area / circumradius) of triangle — higher = worse."""
        ab, ac = vb - va, vc - va
        cross = np.cross(ab, ac)
        area = float(np.linalg.norm(cross)) * 0.5
        if area < 1e-30:
            return 1e30
        # Circumradius of triangle: R = |a||b||c| / (4*area)
        la = float(np.linalg.norm(vb - vc))
        lb = float(np.linalg.norm(va - vc))
        lc = float(np.linalg.norm(va - vb))
        R = la * lb * lc / (4.0 * area)
        if R < 1e-30:
            return 1e30
        return R / area  # inverse of area/R

    # Build face → tet adjacency for finding shared faces.
    face_to_tets: dict[tuple[int, int, int], list[int]] = {}
    for ti in range(n_tets):
        tet = tets[ti]
        for fi, fj, fk, _opp in _FACES:
            key = tuple(sorted([int(tet[fi]), int(tet[fj]), int(tet[fk])]))
            face_to_tets.setdefault(key, []).append(ti)  # type: ignore[arg-type]

    qualities = np.array([_tet_quality(pts, tets[i]) for i in range(n_tets)], dtype=np.float64)
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

        # Find worst face of this tet.
        pts_arr = np.array(pts_list)
        worst_face_idx = -1
        worst_badness = -1.0
        for fi, fj, fk, opp_local in _FACES:
            va, vb, vc = pts_arr[verts[fi]], pts_arr[verts[fj]], pts_arr[verts[fk]]
            bad = _face_badness(pts_arr, va, vb, vc)
            if bad > worst_badness:
                worst_badness = bad
                worst_face_idx = (fi, fj, fk, opp_local)  # type: ignore[assignment]

        fi, fj, fk, opp_local = worst_face_idx  # type: ignore[misc]
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
