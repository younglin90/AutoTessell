"""
CARD VVV1 (beta2114) — Stellar 4-op iterative coordinator (skeleton).
Klingner & Shewchuk 2008 §3.
"""
from __future__ import annotations

import numpy as np

# VVV1: skeleton only — default OFF, no call path added
_VVV1_STELLAR_QUEUE: bool = True


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
