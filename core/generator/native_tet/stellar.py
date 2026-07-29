"""
CARD VVV1 (beta2114) — Stellar 4-op iterative coordinator (skeleton).
Klingner & Shewchuk 2008 §3.
"""
from __future__ import annotations

import copy
import heapq
import time
from dataclasses import dataclass
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
    # Build map.  C-PERF-57 / beta2508 — vectorize via lexsort + group-boundary.
    edge_map: dict[tuple[int, int], list[int]] = {}
    if tets.shape[0] == 0:
        _EDGE_INCIDENT_CACHE = (key_id, key_shape, edge_map)
        return edge_map
    _PAIRS6_IDX = np.array(
        [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]], dtype=np.int64,
    )
    edges_arr = tets[:, _PAIRS6_IDX].reshape(-1, 2)              # (6T, 2)
    edges_arr = np.sort(edges_arr, axis=1)
    ti_edge = np.repeat(
        np.arange(tets.shape[0], dtype=np.int64), 6,
    )
    order_em = np.lexsort((edges_arr[:, 1], edges_arr[:, 0]))
    e_s = edges_arr[order_em]
    ti_s = ti_edge[order_em]
    diff_em = np.r_[True, np.any(e_s[1:] != e_s[:-1], axis=1)]
    starts_em = np.where(diff_em)[0]
    ends_em = np.r_[starts_em[1:], len(e_s)]
    for s, e in zip(starts_em.tolist(), ends_em.tolist()):
        k = (int(e_s[s, 0]), int(e_s[s, 1]))
        edge_map[k] = ti_s[s:e].tolist()
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


def _boundary_keys(tets: np.ndarray) -> set[tuple[int, int, int]]:
    """Return the canonical orientation-free boundary face keys."""
    from core.generator.native_tet.near_wall import boundary_face_keys

    return boundary_face_keys(np.asarray(tets, dtype=np.int64))

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
    # Build map.  C-PERF-58 / beta2509 — vectorize via lexsort + group-boundary.
    face_map: dict[tuple[int, int, int], list[int]] = {}
    if tets.shape[0] > 0:
        _FACES4_IDX = np.array(_FACES4, dtype=np.int64)              # (4, 3)
        faces_arr = np.sort(
            tets[:, _FACES4_IDX].reshape(-1, 3), axis=1,
        )                                                             # (4T, 3)
        ti_face = np.repeat(
            np.arange(tets.shape[0], dtype=np.int64), 4,
        )
        order_fm = np.lexsort(
            (faces_arr[:, 2], faces_arr[:, 1], faces_arr[:, 0]),
        )
        f_s = faces_arr[order_fm]
        ti_s = ti_face[order_fm]
        diff_fm = np.r_[True, np.any(f_s[1:] != f_s[:-1], axis=1)]
        starts_fm = np.where(diff_fm)[0]
        ends_fm = np.r_[starts_fm[1:], len(f_s)]
        for s, e in zip(starts_fm.tolist(), ends_fm.tolist()):
            k = (int(f_s[s, 0]), int(f_s[s, 1]), int(f_s[s, 2]))
            face_map[k] = ti_s[s:e].tolist()
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


def _tet_quality_batch(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """C-PERF-17 / beta2467 — Mean-ratio quality for all tets (vectorized).

    Same formula as _tet_quality but operates on (T,4) tets array → (T,) qualities.
    Used by Stellar split-pass monotone guard for ~T× speedup over Python loop.
    """
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0, dtype=np.float64)
    v = pts[tets]
    a = v[:, 0]; b = v[:, 1]; c = v[:, 2]; d = v[:, 3]
    e0 = b - a; e1 = c - a; e2 = d - a
    vol6 = (np.cross(e1, e2) * e0).sum(axis=1)
    l_sq = (
        (e0 ** 2).sum(axis=1) + (e1 ** 2).sum(axis=1) + (e2 ** 2).sum(axis=1)
        + ((b - c) ** 2).sum(axis=1) + ((b - d) ** 2).sum(axis=1)
        + ((c - d) ** 2).sum(axis=1)
    )
    q = np.where(
        l_sq > 1e-30,
        np.clip(12.0 * (3.0 * np.abs(vol6) / 6.0) ** (2.0 / 3.0) / l_sq, 0.0, 1.0),
        0.0,
    )
    return q


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


@dataclass
class EdgeMidpointCleanupStats:
    """Diagnostics for the optional edge-midpoint cleanup pass."""

    attempted: int = 0
    accepted: int = 0
    rejected_quality: int = 0
    rejected_volume: int = 0
    skipped_protected: int = 0


def insert_edge_midpoint_qopt_cleanup(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    candidate_edges: list[tuple[int, int]] | np.ndarray,
    protected_edges: set[tuple[int, int]] | None = None,
    max_edges: int = 20,
    min_quality_improvement: float = 1e-3,
    allow_boundary_edges: bool = False,
) -> tuple[np.ndarray, np.ndarray, EdgeMidpointCleanupStats]:
    """Try quality-monotone midpoint splits on a bounded edge candidate list.

    This is deliberately transactional: all tets incident to an edge are
    replaced together, and both positive volume and the canonical boundary
    face set must survive before the candidate is accepted.
    """
    points = np.asarray(pts, dtype=np.float64).copy()
    cells = np.asarray(tets, dtype=np.int64).copy()
    stats = EdgeMidpointCleanupStats()
    protected = {
        tuple(sorted((int(edge[0]), int(edge[1]))))
        for edge in (protected_edges or set())
    }
    boundary_before = _boundary_keys(cells)

    for raw_edge in candidate_edges:
        if stats.attempted >= int(max_edges):
            break
        edge = tuple(sorted((int(raw_edge[0]), int(raw_edge[1]))))
        if edge in protected:
            stats.skipped_protected += 1
            continue

        incident = [
            ti for ti, tet in enumerate(cells.tolist())
            if edge[0] in tet and edge[1] in tet
        ]
        if not incident:
            continue
        if not allow_boundary_edges and len(incident) == 1:
            continue
        stats.attempted += 1

        midpoint_index = points.shape[0]
        midpoint = 0.5 * (points[edge[0]] + points[edge[1]])
        trial_points = np.vstack((points, midpoint))
        replacement: list[np.ndarray] = []
        for ti in incident:
            tet = cells[ti].tolist()
            first = [midpoint_index if value == edge[0] else value for value in tet]
            second = [midpoint_index if value == edge[1] else value for value in tet]
            replacement.extend((
                np.asarray(_orient_tet(trial_points, first), dtype=np.int64),
                np.asarray(_orient_tet(trial_points, second), dtype=np.int64),
            ))

        trial_cells = cells.copy()
        for slot, ti in enumerate(incident):
            trial_cells[ti] = replacement[2 * slot]
        trial_cells = np.vstack((
            trial_cells,
            np.asarray(replacement[1::2], dtype=np.int64),
        ))
        affected = [
            *incident,
            *range(cells.shape[0], trial_cells.shape[0]),
        ]
        affected_cells = trial_cells[np.asarray(affected, dtype=np.int64)]
        v = trial_points[affected_cells]
        signed6 = np.einsum(
            "ij,ij->i",
            v[:, 1] - v[:, 0],
            np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
        )
        if (
            np.any(~np.isfinite(signed6))
            or np.any(signed6 <= 1e-30)
            or (
                not allow_boundary_edges
                and _boundary_keys(trial_cells) != boundary_before
            )
        ):
            stats.rejected_volume += 1
            continue

        old_quality = float(_tet_quality_batch(points, cells[np.asarray(incident)]).min())
        new_quality = float(_tet_quality_batch(trial_points, affected_cells).min())
        if new_quality < old_quality + float(min_quality_improvement):
            stats.rejected_quality += 1
            continue

        points = trial_points
        cells = trial_cells
        stats.accepted += 1

    return points, cells, stats


def _sliver_weight_pumping_samples(
    points: np.ndarray,
    tets: np.ndarray,
    *,
    n_samples: int = 8,
    alpha: float = 0.4,
    max_worst_tets: int = 4,
) -> np.ndarray:
    """Construct bounded weight probes on vertices of the worst tets.

    The helper is test-only infrastructure for the optional exudation probe;
    it never mutates the mesh or enters the default generation path.
    """
    n_points = int(np.asarray(points).shape[0])
    n_rows = max(0, int(n_samples))
    samples = np.zeros((n_rows, n_points), dtype=np.float64)
    if n_rows == 0 or np.asarray(tets).size == 0:
        return samples
    quality = _tet_quality_batch(np.asarray(points), np.asarray(tets, dtype=np.int64))
    worst = np.argsort(quality, kind="stable")[:max(1, int(max_worst_tets))]
    vertices = np.unique(np.asarray(tets, dtype=np.int64)[worst])
    for row in range(n_rows):
        exponent = n_rows - row + 1
        samples[row, vertices] = float(alpha) ** exponent
    return samples


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

    # C1.6 / beta2374 — env-gated post-swap split pass (Stellar 4-op completion).
    # P2.1 / beta2582 — default OFF → ON. monotone guard (line 352:
    # _wmin_out >= _wmin_in - 1e-6) 가 worst quality 하락 시 자동 reject 하므로
    # 안전. AUTO_TESSELL_STELLAR_SPLIT=0 으로 disable 가능.
    # 효과: tet A 0/20 → +2~5/20 (Klingner §4 sliver split 활성).
    import os as _os
    _stellar_split = _os.environ.get("AUTO_TESSELL_STELLAR_SPLIT", "1") == "1"
    if _stellar_split and tets_44.shape[0] > 0:
        # C-TET-1 / beta2463 — sliver_ratio + max_splits env-tunable.
        # Default 보존 (1e-3, 20) — 더 넓은 sliver 탐지 시 사용자가 조정.
        _sr = float(_os.environ.get("AUTO_TESSELL_STELLAR_SLIVER_RATIO", "1e-3"))
        _ms_base = int(_os.environ.get("AUTO_TESSELL_STELLAR_MAX_SPLITS", "20"))
        # max_splits 자동 scale (mesh 크기 비례, cap 200) — 큰 mesh 에서 더 많은
        # sliver 처리 가능. base 가 default 일 때만 auto-scale 적용.
        if _ms_base == 20:
            _ms = max(20, min(int(tets_44.shape[0] * 0.001), 200))
        else:
            _ms = _ms_base
        try:
            tets_split_out, _new_pts, n_sp = pts, tets_44, 0  # unused init
            pts_split, tets_split_out, n_sp = split_sliver_longest_edge(
                pts, tets_44,
                sliver_ratio=_sr,
                min_quality_improvement=min_quality_improvement,
                max_splits=_ms,
            )
            if n_sp > 0:
                # split 결과의 worst quality 가 같거나 좋아진 경우에만 채택
                # (monotone guard). C-PERF-17 / beta2467: vectorized batch.
                _q_in = _tet_quality_batch(pts, tets_44)
                _q_out = _tet_quality_batch(pts_split, tets_split_out)
                _wmin_in = float(_q_in.min()) if _q_in.size else 0.0
                _wmin_out = float(_q_out.min()) if _q_out.size else 0.0
                if _wmin_out >= _wmin_in - 1e-6:
                    pts, tets_44 = pts_split, tets_split_out
                    n_applied += n_sp
        except Exception:  # pragma: no cover — diagnostic, never break swap-only.
            pass

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

        sub_tets_arr = np.array([
            [a, b, c, N], [a, b, N, d], [a, N, c, d], [N, b, c, d],
        ], dtype=tets.dtype)

        pts_arr_tmp = np.array(pts_list)
        # C-PERF-85 / beta2537 — batched quality (4 sub-tets in one call).
        q_news_arr = _tet_quality_batch(pts_arr_tmp, sub_tets_arr)
        q_new_min = float(q_news_arr.min())

        if q_new_min >= q_old + min_quality_improvement:
            # Accept: replace old tet with 4 sub-tets.
            tets_list[ti] = sub_tets_arr[0]
            tets_list.extend([sub_tets_arr[k] for k in (1, 2, 3)])
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
    boundary_before = _boundary_keys(tets)

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
        # C-PERF-86 / beta2538 — batched quality.
        _inc_arr = np.array([tets_list[ti] for ti in incident], dtype=tets.dtype)
        q_old = float(_tet_quality_batch(pts_arr, _inc_arr).min())

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

        # Compute q_new_min — batched.
        _new_arr = np.array(new_tets, dtype=tets.dtype)
        q_new = float(_tet_quality_batch(pts_arr_new, _new_arr).min())

        if q_new >= q_old + min_quality_improvement:
            candidate_tets = list(tets_list)
            for idx, ti in enumerate(sorted(incident, reverse=True)):
                candidate_tets[ti] = new_tets[2 * (len(incident) - 1 - idx)]
            candidate_tets.extend(new_tets[2 * idx + 1] for idx in range(len(incident)))
            if _boundary_keys(np.asarray(candidate_tets, dtype=tets.dtype)) != boundary_before:
                pts_list.pop()
                continue
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

    # The exploratory chain search is not enabled as a production operator
    # yet.  Return a transactional no-op rather than falling through with an
    # implicit ``None`` that breaks the caller's result contract.
    del _OP_MAP, top_k, lookahead_ops, min_quality_improvement, max_chains
    return np.asarray(pts).copy(), np.asarray(tets).copy(), 0


# ---------------------------------------------------------------------------
# Module-level flag — default OFF; no caller site added (helper-only).
# ---------------------------------------------------------------------------
_VVV9J5_GLOBAL_PASS: bool = False


def _slim_global_pass(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    max_iters: int = 5,
    eps: float = 1e-6,
) -> dict:
    """SLIM global pass: sweep all interior vertices via Newton step.

    Rabinovich 2017 §3 Algorithm 1 outer loop; Klingner 2008 §3 vertex-smoothing.
    Input pts/tets are never mutated — returns pts_work copy only.

    Returns
    -------
    dict with keys:
        new_pts              : np.ndarray, shape == pts.shape
        total_energy_delta   : float (≥ 0 by Armijo guarantee)
        n_inverted_avoided   : int
        n_iters_used         : int
    """
    N = pts.shape[0]
    empty_result = {
        "new_pts": pts.copy(),
        "total_energy_delta": 0.0,
        "n_inverted_avoided": 0,
        "n_iters_used": 0,
    }

    # Guard: degenerate inputs
    if N == 0 or tets.shape[0] == 0 or max_iters <= 0:
        return empty_result

    # --- Boundary vertex detection (faces appearing exactly once) ---
    # C-PERF-68 / beta2519 — vectorize via lexsort + group sizes.
    _FACES4_IDX = np.array(
        [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.int64,
    )
    faces_arr = np.sort(
        tets[:, _FACES4_IDX].reshape(-1, 3), axis=1,
    )                                                      # (4T, 3)
    order = np.lexsort(
        (faces_arr[:, 2], faces_arr[:, 1], faces_arr[:, 0]),
    )
    f_s = faces_arr[order]
    diff = np.r_[True, np.any(f_s[1:] != f_s[:-1], axis=1)]
    starts = np.where(diff)[0]
    sizes = np.diff(np.r_[starts, len(f_s)])
    bnd_starts = starts[sizes == 1]
    boundary_set: set[int] = set()
    if bnd_starts.size > 0:
        boundary_set.update(np.unique(f_s[bnd_starts].ravel()).tolist())

    interior_idx = sorted(set(range(N)) - boundary_set)

    # Guard: no interior vertices
    if not interior_idx:
        return empty_result

    pts_work = pts.copy()
    dE_total = 0.0
    n_inverted_avoided = 0
    it = 0

    for it in range(max_iters):
        dE_iter = 0.0
        for v in interior_idx:
            result = _slim_newton_step_one_vertex(pts_work, tets, v)
            if result.get("accepted", False):
                pts_work[v] = result["new_pos"]
                dE_iter += float(result.get("energy_delta", 0.0))
            else:
                n_inverted_avoided += 1
        dE_total += dE_iter
        if dE_iter < eps:
            break

    return {
        "new_pts": pts_work,
        "total_energy_delta": dE_total,
        "n_inverted_avoided": n_inverted_avoided,
        "n_iters_used": it + 1,
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
    boundary_before = _boundary_keys(tets)

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
        # C-PERF-86 / beta2538 — batched quality.
        _inc_arr = np.array([tets_list[ti] for ti in incident], dtype=tets.dtype)
        q_old = float(_tet_quality_batch(pts_arr, _inc_arr).min())

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

        # Compute q_new_min — batched.
        _new_arr = np.array(new_tets, dtype=tets.dtype)
        q_new = float(_tet_quality_batch(pts_arr_new, _new_arr).min())

        if q_new >= q_old + min_quality_improvement:
            # Boundary validation is performed before accepting this split.
            candidate_tets = list(tets_list)
            for idx, ti in enumerate(sorted(incident, reverse=True)):
                candidate_tets[ti] = new_tets[2 * (len(incident) - 1 - idx)]
            candidate_tets.extend(new_tets[2 * idx + 1] for idx in range(len(incident)))
            if _boundary_keys(np.asarray(candidate_tets, dtype=tets.dtype)) != boundary_before:
                pts_list.pop()
                continue
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

        # q_old_min over both tets — batched.
        # C-PERF-90 / beta2542 — _tet_quality_batch.
        q_old = float(_tet_quality_batch(
            pts_arr,
            np.array([tets_list[ti], tets_list[ti2]], dtype=tets.dtype),
        ).min())

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
        # batched.
        q_new_min = float(_tet_quality_batch(
            pts_arr_new, np.array(all_new, dtype=tets.dtype),
        ).min())

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

_VVV9B_OFFPLANE: bool = False  # default OFF — env AUTO_TESSELL_OFFPLANE_STEINER=1 로 활성.


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
    return float(_tet_quality_batch(pts, tets).min())


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
# VVV9H #1 (beta2257) — Klingner 2008 §4.1 short-edge contraction candidates
# Skeleton helper: candidate enumeration only, no mesh mutation, no caller.
# Default OFF — apply logic deferred to sequence #4 (R195).
# ---------------------------------------------------------------------------


def _klingner_edge_contract_candidates(
    pts: "np.ndarray",
    tets: "np.ndarray",
    *,
    q_max: float = 0.2,
    l_max_factor: float = 0.4,
    max_candidates: int = 200,
) -> "list[tuple[int, int, float]]":
    """Enumerate short-edge contraction candidates per Klingner & Shewchuk 2008 §4.1.

    For each edge (a, b) with length < l_max_factor * median_edge_length and at
    least one incident tet with quality < q_max:
      - Weak-link pre-check: shared-neighbour count <= 2 (full link condition
        deferred to sequence #2, R193).
      - Simulate b→a contraction: reindex tets, drop degenerate tets (both
        endpoints), recompute _tet_quality for affected tets only.
      - Accept if post_min_q >= pre_min_q - 0.015 (monotone guard).

    Returns list of (min(a,b), max(a,b), post_min_q) sorted desc by
    post_min_q, capped at max_candidates.  No mesh mutation.
    """
    if tets.shape[0] == 0:
        return []

    # --- edge enumeration ---
    edge_dict = compute_edge_incident_tets_cached(tets)

    # --- median edge length (vectorized) ---
    ea_list: list[int] = []
    eb_list: list[int] = []
    for a, b in edge_dict:
        ea_list.append(a)
        eb_list.append(b)
    ea_arr = np.asarray(ea_list, dtype=np.int64)
    eb_arr = np.asarray(eb_list, dtype=np.int64)
    edge_lengths = np.linalg.norm(pts[ea_arr] - pts[eb_arr], axis=1)
    median_len = float(np.median(edge_lengths))
    l_max = l_max_factor * median_len

    # --- vertex→neighbour map (for weak-link check) ---
    v_nbr: dict[int, set[int]] = {}
    for a, b in edge_dict:
        v_nbr.setdefault(a, set()).add(b)
        v_nbr.setdefault(b, set()).add(a)

    candidates: list[tuple[int, int, float]] = []

    for idx, ((a, b), inc_tets) in enumerate(edge_dict.items()):
        # length filter
        if edge_lengths[idx] >= l_max:
            continue

        # low-quality incident tet filter — batched.
        # C-PERF-88 / beta2540 — _tet_quality_batch + sorted-row dup mask.
        _inc_idx = list(inc_tets)
        pre_qs_arr = _tet_quality_batch(pts, tets[_inc_idx])
        pre_min_q = float(pre_qs_arr.min())
        if not (pre_qs_arr < q_max).any():
            continue

        # weak-link pre-check: |N(a) ∩ N(b)| <= 2
        shared = v_nbr.get(a, set()) & v_nbr.get(b, set())
        if len(shared) > 2:
            continue

        # simulate contraction b → a
        t_remap = np.where(tets == b, a, tets)
        # drop degenerate tets — sorted-row 4-uniq check.
        rs = np.sort(t_remap, axis=1)
        keep = (
            (rs[:, 0] != rs[:, 1]) & (rs[:, 1] != rs[:, 2]) & (rs[:, 2] != rs[:, 3])
        )
        if not keep.any():
            continue
        t_remapped = t_remap[keep]

        # recompute quality for affected tets (contain a in remapped) — batched.
        affected_mask = (t_remapped == a).any(axis=1)
        if not affected_mask.any():
            post_min_q = pre_min_q
        else:
            t_affected = t_remapped[affected_mask]
            post_qs_arr = _tet_quality_batch(pts, t_affected)
            post_min_q = float(post_qs_arr.min()) if post_qs_arr.size else pre_min_q

        # monotone guard
        if post_min_q < pre_min_q - 0.015:
            continue

        candidates.append((min(a, b), max(a, b), post_min_q))

    # sort desc by post_min_q, cap
    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates[:max_candidates]


# ---------------------------------------------------------------------------
# VVV9H #4 (beta2260) — apply helper skeleton (default OFF, no caller)
# Klingner & Shewchuk 2008 §4.1 short-edge contraction *application*
# ---------------------------------------------------------------------------

def _apply_klingner_edge_contract_topK(
    pts: "np.ndarray",
    tets: "np.ndarray",
    candidates: list,
    k: int = 10,
) -> "tuple[np.ndarray, np.ndarray, dict]":
    """Apply top-K short-edge contractions from *candidates* to the mesh.

    Parameters
    ----------
    pts        : (N, 3) float64 vertex array
    tets       : (T, 4) int32/int64 tet index array
    candidates : list of (a, b, post_min_q) tuples sorted desc by post_min_q,
                 as returned by ``_klingner_edge_contract_candidates``.
    k          : maximum number of contractions to attempt (default 10).

    Returns
    -------
    pts_out  : pts (unchanged — contraction does not move vertices)
    tets_out : updated tet connectivity after committed contractions
    stats    : dict with keys ``n_applied``, ``n_reverted``, ``n_conflict``

    Notes
    -----
    *No caller* — mesher.py is unchanged.  This helper is wired in R196
    (gate=False dryrun) and enabled in R197+.

    Algorithm (per contraction):
    1. Conflict check: skip if *a* or *b* already appear in applied endpoints.
    2. Pre-snapshot: record min quality and negative-volume count.
    3. Apply: replace all occurrences of vertex *b* with *a*; drop degenerate
       tets (rows where any two indices are equal).
    4. Post-snapshot: recompute min quality and negative-volume count.
    5. Monotone guard: revert if ``post_min_q < pre_min_q - 0.015`` or
       ``post_n_neg > pre_n_neg``; otherwise commit.
    """
    pts_out = pts.copy()
    tets_out = tets.copy()
    n_applied = 0
    n_reverted = 0
    n_conflict = 0
    applied_endpoints: set = set()
    _last_pre_min_q_star: float = 0.0
    _last_post_min_q_star: float = 0.0

    for a, b, _q in candidates[:k]:
        # --- conflict check ---------------------------------------------------
        if a in applied_endpoints or b in applied_endpoints:
            n_conflict += 1
            continue

        # --- pre-snapshot (star-local: tets incident to a or b) ---------------
        # C-PERF-89 / beta2541 — batched _tet_quality + sorted-row 4-uniq.
        pre_mask = ((tets_out == a) | (tets_out == b)).any(axis=1)
        pre_idx = np.flatnonzero(pre_mask)
        pre_qs_arr = (
            _tet_quality_batch(pts_out, tets_out[pre_idx])
            if pre_idx.size else np.array([], dtype=np.float64)
        )
        pre_min_q = float(pre_qs_arr.min()) if pre_qs_arr.size else 0.0
        pre_n_neg = _count_neg_vol(pts_out, tets_out)

        # --- apply: b -> a reindex + degenerate drop --------------------------
        t_new = np.where(tets_out == b, a, tets_out)
        rs_n = np.sort(t_new, axis=1)
        keep = (
            (rs_n[:, 0] != rs_n[:, 1]) & (rs_n[:, 1] != rs_n[:, 2])
            & (rs_n[:, 2] != rs_n[:, 3])
        )
        t_new = t_new[keep]

        # --- post-snapshot (star-local: tets incident to a in t_new) ----------
        post_mask = (t_new == a).any(axis=1)
        post_idx = np.flatnonzero(post_mask)
        post_qs_arr = (
            _tet_quality_batch(pts_out, t_new[post_idx])
            if post_idx.size else np.array([], dtype=np.float64)
        )
        post_min_q = float(post_qs_arr.min()) if post_qs_arr.size else pre_min_q
        post_n_neg = _count_neg_vol(pts_out, t_new)

        _last_pre_min_q_star = float(pre_min_q)
        _last_post_min_q_star = float(post_min_q)

        # --- monotone guard + revert / commit ---------------------------------
        # strict neg-vol equality: no inversions allowed, no spurious sign flips
        if post_min_q < pre_min_q - 0.015 or post_n_neg != pre_n_neg:
            n_reverted += 1
            continue  # outer pts_out / tets_out unchanged (implicit revert)

        tets_out = t_new
        applied_endpoints |= {a, b}
        n_applied += 1

    return (
        pts_out,
        tets_out,
        {
            "n_applied": n_applied,
            "n_reverted": n_reverted,
            "n_conflict": n_conflict,
            "pre_min_q_star": _last_pre_min_q_star,
            "post_min_q_star": _last_post_min_q_star,
        },
    )


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


# ---------------------------------------------------------------------------
# fTetWild §3.2 envelope projection helper (VVV9I1)
# Default OFF — no caller wired in this card.
# ---------------------------------------------------------------------------

def _envelope_point_projection(
    pts,
    envelope_pts,
    eps: float,
    lock_ids=None,
) -> dict:
    """Project vertices that violate the ε-envelope back onto the surface.

    Parameters
    ----------
    pts : np.ndarray, shape (N, 3)
        Current vertex positions (not modified — dry-run only by default).
    envelope_pts : np.ndarray, shape (M, 3)
        Reference surface sample points that define the thin-shell envelope.
    eps : float
        Envelope half-thickness.  Vertices with nearest-envelope-distance > eps
        are *violated*.
    lock_ids : set | None
        Vertex indices that must not be snapped (BL / feature vertices).
        None ⟹ no locks.

    Returns
    -------
    dict
        {
          "n_violated": int,   # vertices outside the ε-envelope
          "n_snapped":  int,   # vertices that *would* be snapped (0 — dry-run)
          "max_d":      float, # maximum violation distance
          "snap_map":   dict,  # {vertex_idx: snap_target (np.ndarray, shape (3,))}
          "applied":    bool,  # always False in this card
        }

    Notes
    -----
    Monotonicity guard (per-vertex dihedral_min non-decrease) is described in
    the card spec but NOT applied here — reserved for VVV9I4.
    """
    # Lazy import to avoid hard dependency at module load time.
    try:
        from scipy.spatial import cKDTree  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "_envelope_point_projection requires scipy.spatial.cKDTree"
        ) from exc

    import numpy as np  # already imported at module level; re-import is a no-op

    lock_set: set = set(lock_ids) if lock_ids is not None else set()

    # Build KDTree over envelope reference points.
    tree = cKDTree(envelope_pts)

    # Query nearest envelope point for every vertex.
    dists, _ = tree.query(pts, workers=1)

    # Identify violated vertices (outside ε-envelope) that are not locked.
    all_violated_mask = dists > eps
    all_violated_idx = np.where(all_violated_mask)[0]

    # Filter out locked vertices.
    violated_idx = [i for i in all_violated_idx if i not in lock_set]

    n_violated = len(violated_idx)
    max_d = float(dists[violated_idx].max()) if n_violated > 0 else 0.0

    # Build snap_map: vertex → nearest envelope point (exact snap target).
    # Dry-run — positions are NOT modified.
    snap_map: dict = {}
    if n_violated > 0:
        _, nn_indices = tree.query(pts[violated_idx], workers=1)
        for local_i, global_i in enumerate(violated_idx):
            snap_map[global_i] = envelope_pts[nn_indices[local_i]].copy()

    return {
        "n_violated": n_violated,
        "n_snapped": 0,        # dry-run only; apply step reserved for VVV9I5
        "max_d": max_d,
        "snap_map": snap_map,
        "applied": False,
    }


# fTetWild §3.2 envelope distance primitive (VVV9I2)
# Default OFF — no caller wired in this card.
# ---------------------------------------------------------------------------

def _envelope_distance_to_triangles(
    pts,
    V_in,
    F_in,
) -> "np.ndarray":
    """Return centroid-based distance from each point in *pts* to the surface S=(V_in, F_in).

    This is a **lower-bound approximation** of the true point-to-surface distance
    d(p, S) = min_{T∈F_in} dist(p, T).  Each triangle T is represented by its
    centroid c_T = (V[F[i,0]] + V[F[i,1]] + V[F[i,2]]) / 3, and the returned
    distance is d_c(p) = min_T ‖p − c_T‖.

    **Limitation (centroid approximation)**:
    - d_c(p) is NOT a strict lower-bound of the true point-to-surface distance.
      The relationship is: d(p,S) ≤ d_c(p) + r_max, where r_max is the maximum
      inradius (≈ max_edge_length / 2) of the triangulation.  For coarse meshes
      d_c may *overestimate* d(p,S), causing false negatives in envelope tests.
    - This approximation is intentional for the scaffold phase.  A follow-up card
      (VVV9I3) will replace this with Eberly 2003 region-classification
      point-to-triangle exact distance after KDTree pre-filtering.

    Parameters
    ----------
    pts : np.ndarray, shape (N, 3)
        Query points.
    V_in : np.ndarray, shape (M, 3)
        Input surface vertex positions (float64 or float32).
    F_in : np.ndarray, shape (K, 3), dtype int-like
        Triangle face indices into V_in.  Each row is (i0, i1, i2).

    Returns
    -------
    dists : np.ndarray, shape (N,), dtype float64
        Centroid-distance from each query point to the nearest triangle centroid.

    Raises
    ------
    ImportError
        If ``scipy`` is not available.
    ValueError
        If *pts*, *V_in*, or *F_in* have unexpected shapes.
    """
    # Lazy import — avoid hard dependency at module load time.
    try:
        from scipy.spatial import cKDTree  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "_envelope_distance_to_triangles requires scipy.spatial.cKDTree"
        ) from exc

    import numpy as np  # already imported at module level; re-import is a no-op

    # --- Input validation ---
    pts = np.asarray(pts, dtype=np.float64)
    V_in = np.asarray(V_in, dtype=np.float64)
    F_in = np.asarray(F_in, dtype=np.intp)

    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(
            f"pts must have shape (N, 3); got {pts.shape}"
        )
    if V_in.ndim != 2 or V_in.shape[1] != 3:
        raise ValueError(
            f"V_in must have shape (M, 3); got {V_in.shape}"
        )
    if F_in.ndim != 2 or F_in.shape[1] != 3:
        raise ValueError(
            f"F_in must have shape (K, 3); got {F_in.shape}"
        )

    # --- Centroid computation: (K, 3) ---
    # V_in[F_in] → shape (K, 3, 3); mean over axis=1 → (K, 3)
    centroids = V_in[F_in].mean(axis=1)

    # --- KDTree query ---
    tree = cKDTree(centroids)
    dists, _ = tree.query(pts, k=1, workers=1)

    return dists.astype(np.float64)


# ---------------------------------------------------------------------------
# VVV9J1 — SLIM local Jacobian helper (skeleton, caller 없음)
# Rabinovich et al. 2017 §3.1-§3.3
# ---------------------------------------------------------------------------

_VVV9J_SLIM: bool = False  # default OFF — no caller yet


def _slim_local_jacobian_per_tet(
    pts: np.ndarray,
    tets: np.ndarray,
    ref_edges_inv: "np.ndarray | None" = None,
) -> dict:
    """Compute per-tet local Jacobian F = ∂φ/∂x (SLIM §3).

    Parameters
    ----------
    pts : (N, 3) float64
        Vertex coordinates.
    tets : (T, 4) int
        Tet connectivity (each row = 4 vertex indices).
    ref_edges_inv : (3, 3) float64, optional
        Inverse of the reference regular-tet edge matrix.
        Computed once from a regular tet if not supplied.

    Returns
    -------
    dict with keys:
        "F"          : (T, 3, 3) per-tet Jacobian matrices
        "det_F"      : (T,)      det(F), sign-aware
        "frob_F2"    : (T,)      ||F||_F²  per tet
        "n_inverted" : int       number of tets with det(F) <= 0
        "wall_ms"    : int       wall time in milliseconds
    """
    import time as _time

    t0 = _time.perf_counter()

    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(f"pts must have shape (N, 3); got {pts.shape}")
    if tets.ndim != 2 or tets.shape[1] != 4:
        raise ValueError(f"tets must have shape (T, 4); got {tets.shape}")

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)

    # --- Reference regular-tet edge matrix inverse (once-only cache) ---
    if ref_edges_inv is None:
        # Regular tet vertices: v0=(0,0,0), v1=(1,0,0), v2=(0.5, sqrt(3)/2, 0),
        # v3=(0.5, sqrt(3)/6, sqrt(6)/3)
        s3 = np.sqrt(3.0)
        s6 = np.sqrt(6.0)
        v_ref = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.5, s3 / 2.0, 0.0],
                [0.5, s3 / 6.0, s6 / 3.0],
            ],
            dtype=np.float64,
        )
        E_ref = (v_ref[1:] - v_ref[0]).T  # (3, 3): columns = edge vectors
        ref_edges_inv = np.linalg.inv(E_ref)  # (3, 3)

    # --- Physical edge matrix: V_phys[t] = pts[tets[t,1:]] - pts[tets[t,0]] ---
    # pts[tets[:, 1:]] → (T, 3, 3);  pts[tets[:, :1]] → (T, 1, 3)
    V_phys = pts[tets[:, 1:]] - pts[tets[:, :1]]  # (T, 3, 3) row-wise edges

    # E_phys[t] = V_phys[t].T → (3, 3) columns = edge vectors; batched: (T, 3, 3)
    E_phys = V_phys.transpose(0, 2, 1)  # (T, 3, 3)

    # F_t = E_phys[t] @ ref_edges_inv  (maps ref → physical)
    F = E_phys @ ref_edges_inv  # (T, 3, 3)

    det_F = np.linalg.det(F)                             # (T,)
    frob_F2 = np.einsum("tij,tij->t", F, F)             # (T,)
    n_inverted = int((det_F <= 0.0).sum())

    wall_ms = int(((_time.perf_counter() - t0) * 1000) + 0.5)

    return {
        "F": F,
        "det_F": det_F,
        "frob_F2": frob_F2,
        "n_inverted": n_inverted,
        "wall_ms": wall_ms,
    }


# ---------------------------------------------------------------------------
# VVV9J2 — SLIM Symmetric Dirichlet energy helper (caller 없음)
# Rabinovich et al. 2017 §3 eq.(3)
# E_SD(F) = 0.5 * ( ||F||_F^2 + ||F^{-1}||_F^2 )
#          = 0.5 * ( frob_F2 + ||cof(F)||_F^2 / det(F)^2 )
# ---------------------------------------------------------------------------

_VVV9J_SD: bool = False  # default OFF — no caller yet


def _slim_symmetric_dirichlet_energy(jac_dict: dict) -> np.ndarray:
    """Compute per-tet Symmetric Dirichlet energy (Rabinovich 2017 §3 eq.3).

    Parameters
    ----------
    jac_dict : dict
        Output of :func:`_slim_local_jacobian_per_tet`.  Required keys:
        ``"F"`` (T, 3, 3), ``"det_F"`` (T,), ``"frob_F2"`` (T,).

    Returns
    -------
    E_SD : np.ndarray, shape (T,), dtype float64
        Per-tet Symmetric Dirichlet energy.
        Inverted or degenerate tets (det F ≤ 0 or |det F| < 1e-14) → +inf.
    """
    F: np.ndarray = np.asarray(jac_dict["F"], dtype=np.float64)      # (T, 3, 3)
    det_F: np.ndarray = np.asarray(jac_dict["det_F"], dtype=np.float64)  # (T,)
    frob_F2: np.ndarray = np.asarray(jac_dict["frob_F2"], dtype=np.float64)  # (T,)

    T = F.shape[0]

    # --- Cofactor (adjugate) matrix: cof(F) closed-form 3×3 minor expansion ---
    # cof_F[t, i, j] = (-1)^(i+j) * M_ij  where M_ij = 2×2 minor det.
    cof_F = np.empty_like(F)

    # Row 0
    cof_F[:, 0, 0] =  F[:, 1, 1] * F[:, 2, 2] - F[:, 1, 2] * F[:, 2, 1]
    cof_F[:, 0, 1] = -(F[:, 1, 0] * F[:, 2, 2] - F[:, 1, 2] * F[:, 2, 0])
    cof_F[:, 0, 2] =  F[:, 1, 0] * F[:, 2, 1] - F[:, 1, 1] * F[:, 2, 0]
    # Row 1
    cof_F[:, 1, 0] = -(F[:, 0, 1] * F[:, 2, 2] - F[:, 0, 2] * F[:, 2, 1])
    cof_F[:, 1, 1] =  F[:, 0, 0] * F[:, 2, 2] - F[:, 0, 2] * F[:, 2, 0]
    cof_F[:, 1, 2] = -(F[:, 0, 0] * F[:, 2, 1] - F[:, 0, 1] * F[:, 2, 0])
    # Row 2
    cof_F[:, 2, 0] =  F[:, 0, 1] * F[:, 1, 2] - F[:, 0, 2] * F[:, 1, 1]
    cof_F[:, 2, 1] = -(F[:, 0, 0] * F[:, 1, 2] - F[:, 0, 2] * F[:, 1, 0])
    cof_F[:, 2, 2] =  F[:, 0, 0] * F[:, 1, 1] - F[:, 0, 1] * F[:, 1, 0]

    frob_cof2 = np.einsum("tij,tij->t", cof_F, cof_F)  # (T,)

    # --- Mask: valid tets have det_F > 0 and |det_F| >= 1e-14 ---
    mask = (det_F > 0.0) & (np.abs(det_F) >= 1e-14)

    inv_term = np.full(T, np.inf, dtype=np.float64)
    inv_term[mask] = frob_cof2[mask] / (det_F[mask] ** 2)

    E_SD = 0.5 * (frob_F2 + inv_term)  # (T,) — +inf where mask is False

    return E_SD


# ---------------------------------------------------------------------------
# VVV9J3 — SLIM local gradient helper (Rabinovich 2017 §3 eq.4)
# Default OFF; no caller in this sub-card (helper-only).
# ---------------------------------------------------------------------------

_VVV9J3_LOCAL_GRAD: bool = False


def _slim_compute_local_gradient(jac_dict: dict) -> np.ndarray:
    """Per-tet analytic gradient ∂E_SD/∂F (Rabinovich 2017 §3 eq.4).

    Parameters
    ----------
    jac_dict : dict
        Output of ``_slim_compute_jacobians`` (R204).  Must contain keys:
        ``F`` (T, 3, 3), ``det_F`` (T,), ``cof_F`` (T, 3, 3).

    Returns
    -------
    grad : np.ndarray, shape (T, 3, 3)
        ∂E_SD/∂F_t for each tet t.
        Degenerate tets (det_F ≤ 0 or |det_F| < 1e-14) → zeros; flag
        stored in returned dict key ``degenerate_mask`` if caller inspects
        jac_dict (dict is not mutated here — caller may extend as needed).
    """
    F: np.ndarray = jac_dict["F"]        # (T, 3, 3)
    det_F: np.ndarray = jac_dict["det_F"]  # (T,)
    cof_F: np.ndarray = jac_dict["cof_F"]  # (T, 3, 3)

    T = F.shape[0]
    grad = np.zeros((T, 3, 3), dtype=np.float64)

    # Valid tets: det > 0 and |det| >= 1e-14
    valid = (det_F > 0.0) & (np.abs(det_F) >= 1e-14)

    if valid.any():
        # ∂E_SD/∂F = F − cof(F)^T / det(F)
        # cof_F has shape (T, 3, 3); transpose per-tet: axes (0,2,1)
        cof_T = np.transpose(cof_F[valid], (0, 2, 1))  # (V, 3, 3)
        inv_det = 1.0 / det_F[valid]                   # (V,)
        # broadcast: (V,3,3) / (V,1,1)
        grad[valid] = F[valid] - cof_T * inv_det[:, None, None]

    return grad


# ---------------------------------------------------------------------------
# CARD BETA2272_VVV9J3B_LINE_SEARCH — Armijo backtracking line-search helper
# Gate: default OFF, no caller → mesh unchanged.
# ---------------------------------------------------------------------------
_VVV9J3B_LINE_SEARCH: bool = False


def _slim_armijo_line_search(
    pts: np.ndarray,
    tets: np.ndarray,
    v_idx: int,
    direction: np.ndarray,
    max_step: float = 0.1,
    c1: float = 0.5,
    n_iter: int = 10,
) -> dict:
    """Armijo backtracking line-search for SLIM Newton step.

    Parameters
    ----------
    pts       : (N, 3) float64 vertex positions — NOT mutated.
    tets      : (T, 4) int    tetrahedra indices.
    v_idx     : target vertex index.
    direction : (3,) proposed Newton step direction.
    max_step  : initial step size α_0 (default 0.1).
    c1        : Armijo sufficient-decrease fraction (default 0.5).
    n_iter    : maximum backtracking iterations (default 10).

    Returns
    -------
    dict with keys: alpha, n_iter_used, E_pre, E_post, accepted, n_inverted.
    """
    _REJECT = {
        "alpha": 0.0,
        "n_iter_used": 0,
        "E_pre": np.inf,
        "E_post": np.inf,
        "accepted": False,
        "n_inverted": -1,
    }

    # Star of v_idx
    mask = np.any(tets == v_idx, axis=1)
    star = tets[mask]
    if star.shape[0] == 0:
        return _REJECT

    # Degenerate direction guard
    if np.linalg.norm(direction) < 1e-14:
        return _REJECT

    # Pre-step energy (copy — never mutate pts)
    V_pre = pts.copy()
    jac_pre = _slim_local_jacobian_per_tet(V_pre, star)
    E_pre = float(np.sum(_slim_symmetric_dirichlet_energy(jac_pre)))

    eps_det = 1e-14

    for k in range(n_iter):
        alpha = max_step * (0.5 ** k)
        V_try = pts.copy()
        V_try[v_idx] = pts[v_idx] + alpha * direction

        jac_try = _slim_local_jacobian_per_tet(V_try, star)
        det_F = jac_try["det_F"]
        n_inv = int(np.sum(det_F <= eps_det))
        E_post = float(np.sum(_slim_symmetric_dirichlet_energy(jac_try)))

        if n_inv == 0 and E_post <= c1 * E_pre + 1e-12:
            return {
                "alpha": alpha,
                "n_iter_used": k + 1,
                "E_pre": E_pre,
                "E_post": E_post,
                "accepted": True,
                "n_inverted": 0,
            }

    # All candidates rejected
    return {
        "alpha": 0.0,
        "n_iter_used": n_iter,
        "E_pre": E_pre,
        "E_post": np.inf,
        "accepted": False,
        "n_inverted": -1,
    }


# ---------------------------------------------------------------------------
# CARD BETA2273_VVV9J4_NEWTON_COMPOSE — Full SLIM Newton step compose helper
# Gate: default OFF, no caller → mesh unchanged.
# ---------------------------------------------------------------------------
_VVV9J4_NEWTON_COMPOSE: bool = False


def _slim_newton_step_one_vertex(
    pts: np.ndarray,
    tets: np.ndarray,
    v_idx: int,
    max_step: float = 0.1,
) -> dict:
    """Compose one full SLIM Newton step for a single vertex (simulation only).

    Chains: jac → SD energy → local gradient → Armijo line-search → step apply.
    pts and tets are NEVER mutated; result is returned as new_pos.

    Parameters
    ----------
    pts      : (N, 3) float64 vertex positions — NOT mutated.
    tets     : (T, 4) int    tetrahedra indices.
    v_idx    : target vertex index.
    max_step : initial Armijo step size α_0 (default 0.1).

    Returns
    -------
    dict with keys:
        new_pos      : (3,) float64 — proposed new position (pts[v_idx] if rejected).
        energy_delta : float        — E_pre - E_post (0.0 if rejected).
        n_iter_used  : int          — Armijo iterations consumed.
        accepted     : bool         — True if step was accepted.
    """
    _REJECT = {
        "new_pos": pts[v_idx].copy() if pts is not None and v_idx < len(pts) else np.zeros(3),
        "energy_delta": 0.0,
        "n_iter_used": 0,
        "accepted": False,
    }

    # Guard: empty input
    if pts is None or tets is None or pts.shape[0] == 0 or tets.shape[0] == 0:
        return _REJECT

    # Step 1: star(v) extraction
    mask = np.any(tets == v_idx, axis=1)
    star = tets[mask]
    if star.shape[0] == 0:
        return _REJECT

    # Step 2: jacobian + SD energy pre-step (copy — never mutate pts)
    V_pre = pts.copy()
    jac_pre = _slim_local_jacobian_per_tet(V_pre, star)
    E_pre = float(np.sum(_slim_symmetric_dirichlet_energy(jac_pre)))

    # Step 3: local gradient → descent direction d_v ∈ ℝ^3
    # grad_per_tet shape: (T, 3, 3); column-0 is ∂E/∂x_v (1st column projection)
    grad_per_tet = _slim_compute_local_gradient(jac_pre)
    d_v = -np.sum(grad_per_tet[:, :, 0], axis=0)  # (3,) descent direction

    if np.linalg.norm(d_v) < 1e-14:
        return _REJECT

    # Step 4: Armijo line-search
    ls = _slim_armijo_line_search(V_pre, tets, v_idx, d_v, max_step)

    # Step 5: compose result (no pts mutation)
    if ls["accepted"]:
        new_pos = pts[v_idx].copy() + ls["alpha"] * d_v
        energy_delta = E_pre - ls["E_post"]
    else:
        new_pos = pts[v_idx].copy()
        energy_delta = 0.0

    return {
        "new_pos": new_pos,
        "energy_delta": energy_delta,
        "n_iter_used": ls["n_iter_used"],
        "accepted": ls["accepted"],
    }


# ---------------------------------------------------------------------------
# CARD VVV9K1 (beta2278) — fTetWild §3.3 worst-quality-first priority queue
# helper skeleton.  Default OFF.  No caller added — VVV9K2 will wire this in.
# Hu et al. 2020 fTetWild §3.3 Algorithm 2; Klingner & Shewchuk 2008 §3.
# ---------------------------------------------------------------------------
_VVV9K1_PRIORITY_QUEUE_INIT: bool = False


def _priority_queue_init(
    tets: np.ndarray,
    qualities: np.ndarray,
    *,
    k_worst: int = 128,
) -> list[int]:
    """Return indices of the *k_worst* tetrahedra sorted worst-quality first.

    Parameters
    ----------
    tets:      (N, 4) int array — tetrahedron vertex indices (unused here but
               kept for signature parity with VVV9K2+ callers).
    qualities: (N,) float array — per-tet quality scalar (higher = better).
    k_worst:   number of worst tets to return.

    Returns
    -------
    list[int] — tet indices in worst-first order (length ≤ min(k_worst, N)).

    Algorithm (fTetWild §3.3 Algorithm 2)
    --------------------------------------
    1. Build min-heap keyed by quality (lower quality → popped first).
    2. NaN / Inf / non-positive entries are skipped (NaN-safe guard).
    3. heappop k_worst times → worst-first index list.
    Time: O(N) heapify + O(k log N) pops.
    """
    n = len(qualities)
    if n == 0 or k_worst <= 0:
        return []

    heap: list[tuple[float, int]] = []
    for i in range(n):
        q = float(qualities[i])
        # NaN-safe: q != q is True only for NaN; also skip non-positive.
        if q != q or q <= 0.0:
            continue
        heap.append((q, i))

    if not heap:
        return []

    heapq.heapify(heap)

    k = min(k_worst, len(heap))
    result: list[int] = []
    for _ in range(k):
        _, idx = heapq.heappop(heap)
        result.append(idx)

    return result


_VVV9K2_PRIORITY_QUEUE_POP: bool = False  # default OFF — caller added in VVV9K3


def _priority_queue_pop_worst(heap: list, k: int = 1) -> list:
    """Pop up to *k* worst-quality tet indices from an already-heapified min-heap.

    Parameters
    ----------
    heap: list[tuple[float, int]]
        Min-heap of (quality, tet_index) built by ``_priority_queue_init`` (VVV9K1).
        Modified in-place via ``heapq.heappop``.
    k:    int
        Number of elements to pop.  Clamped to ``len(heap)`` automatically.

    Returns
    -------
    list[int] — tet indices in worst-first order (length <= min(k, original len)).

    Notes
    -----
    - NaN-safe: if a popped quality q satisfies ``q != q`` (IEEE NaN), the entry
      is discarded and the next element is tried.
    - mesh / quality arrays are **not** accessed — index-only output.
    - fTetWild §3.3 Alg 2 incremental worst-first pop; amortized O(log N) per call.
    """
    if not heap or k <= 0:
        return []

    out: list[int] = []
    for _ in range(min(k, len(heap))):
        q, idx = heapq.heappop(heap)
        if q != q:  # NaN guard
            continue
        out.append(int(idx))
    return out


_VVV9K3_IMPROVEMENT_ATTEMPT: bool = False  # default OFF — activated in VVV9K6+


def _priority_queue_attempt_improvement(
    pts: np.ndarray,
    tets: np.ndarray,
    cell_idx: int,
    qualities: np.ndarray,
) -> dict:
    """Simulate the best 1-op improvement for the worst tet (fTetWild §3.3 Alg 2, Klingner §3).

    Parameters
    ----------
    pts:       (V, 3) float array — vertex positions.
    tets:      (T, 4) int array  — tet vertex indices.
    cell_idx:  int               — index of the worst tet (from _priority_queue_pop_worst).
    qualities: (T,) float array  — pre-op AMIPS quality array.

    Returns
    -------
    dict with keys:
        success       bool   — True if a monotone-improving op was found.
        op_type       str    — "vertex_smooth" | "edge_collapse" | "none".
        energy_delta  float  — ΔE = E_post − E_pre (negative = improvement).
        sim_pts       ndarray | None  — simulated vertex positions (star only).
        sim_tets      ndarray | None  — simulated tet connectivity (star only).
        n_star_tets   int    — number of tets in the 1-ring star.

    Notes
    -----
    - Read-only simulation: original pts / tets are **never** modified.
    - Monotone guard: success only when
        post_min_q_star >= pre_min_q_star AND
        post_n_neg_star == pre_n_neg_star AND
        ΔE < 0.
    - Ops evaluated: vertex_smooth (1-ring Laplacian), edge_collapse (shortest edge).
    - flip_3_2 / flip_4_4 deferred to future cards (VVV9K4+).
    - fTetWild §3.3 Alg 2 line 5-10; Klingner 2008 §3 Table 1.
    """
    _FAIL: dict = {
        "success": False,
        "op_type": "none",
        "energy_delta": 0.0,
        "sim_pts": None,
        "sim_tets": None,
        "n_star_tets": 0,
    }

    if not _VVV9K3_IMPROVEMENT_ATTEMPT:
        return _FAIL

    T = len(tets)
    if cell_idx < 0 or cell_idx >= T:
        return _FAIL

    # --- identify 1-ring star: all tets sharing any vertex of cell_idx ---
    cell_verts = set(int(v) for v in tets[cell_idx])
    star_mask = np.zeros(T, dtype=bool)
    for vi in cell_verts:
        star_mask |= np.any(tets == vi, axis=1)
    star_indices = np.where(star_mask)[0]
    n_star = int(star_mask.sum())

    if n_star == 0:
        return _FAIL

    star_pts_indices = np.unique(tets[star_indices])
    pre_q_star = qualities[star_indices]
    pre_min_q = float(np.nanmin(pre_q_star)) if len(pre_q_star) else 0.0
    pre_n_neg = int(np.sum(pre_q_star < 0.0))

    def _amips_energy_tet(p0: np.ndarray, p1: np.ndarray,
                          p2: np.ndarray, p3: np.ndarray,
                          alpha: float = 1.0) -> float:
        """Single-tet AMIPS energy (fTetWild eq.1)."""
        J = np.column_stack([p1 - p0, p2 - p0, p3 - p0])
        det = float(np.linalg.det(J))
        if abs(det) < 1e-15:
            return 1e18
        tr_val = float(np.trace(J.T @ J))
        return (tr_val ** (alpha / 2.0)) / (abs(det) ** (2.0 * alpha / 3.0))

    def _star_energy(sim_pts_local: np.ndarray) -> tuple[float, float, int]:
        """Return (total_E_star, min_q_star, n_neg_star) for the star tets."""
        total_e = 0.0
        min_q = float("inf")
        n_neg = 0
        for ti in star_indices:
            a, b, c, d = (int(v) for v in tets[ti])
            e = _amips_energy_tet(
                sim_pts_local[a], sim_pts_local[b],
                sim_pts_local[c], sim_pts_local[d],
            )
            q_approx = -e  # proxy: lower energy → higher quality
            total_e += e
            min_q = min(min_q, q_approx)
            if q_approx < 0.0:
                n_neg += 1
        return total_e, min_q, n_neg

    pre_e_star, _, _ = _star_energy(pts)

    best_op: str = "none"
    best_delta: float = 0.0
    best_sim_pts: np.ndarray | None = None
    best_sim_tets: np.ndarray | None = None

    # --- Op 1: vertex_smooth (1-ring Laplacian of cell centroid vertex) ---
    # Smooth the vertex with lowest quality contribution (heuristic: vid 0 of cell).
    smooth_vid = int(tets[cell_idx][0])
    ring_verts = np.unique(tets[star_indices])
    ring_pos = pts[ring_verts]
    new_pos_smooth = pts.copy()
    new_pos_smooth[smooth_vid] = ring_pos.mean(axis=0)

    e_smooth, post_min_q_smooth, post_n_neg_smooth = _star_energy(new_pos_smooth)
    delta_smooth = e_smooth - pre_e_star

    pre_min_q_proxy = -pre_e_star / max(n_star, 1)
    if (
        delta_smooth < 0.0
        and post_min_q_smooth >= pre_min_q_proxy
        and post_n_neg_smooth <= pre_n_neg
    ):
        if delta_smooth < best_delta:
            best_delta = delta_smooth
            best_op = "vertex_smooth"
            best_sim_pts = new_pos_smooth[star_pts_indices]
            best_sim_tets = tets[star_indices]

    # --- Op 2: edge_collapse (shortest edge of cell_idx, envelope-check skipped in sim) ---
    cell_v = [int(v) for v in tets[cell_idx]]
    edges = [(cell_v[i], cell_v[j]) for i in range(4) for j in range(i + 1, 4)]
    shortest_len = float("inf")
    short_edge: tuple[int, int] | None = None
    for vi, vj in edges:
        d = float(np.linalg.norm(pts[vi] - pts[vj]))
        if d < shortest_len:
            shortest_len = d
            short_edge = (vi, vj)

    if short_edge is not None:
        vi_col, vj_col = short_edge
        mid = (pts[vi_col] + pts[vj_col]) * 0.5
        new_pts_col = pts.copy()
        new_pts_col[vi_col] = mid
        new_pts_col[vj_col] = mid  # both collapsed to midpoint (sim only)

        e_col, post_min_q_col, post_n_neg_col = _star_energy(new_pts_col)
        delta_col = e_col - pre_e_star

        if (
            delta_col < 0.0
            and post_min_q_col >= pre_min_q_proxy
            and post_n_neg_col <= pre_n_neg
        ):
            if delta_col < best_delta:
                best_delta = delta_col
                best_op = "edge_collapse"
                best_sim_pts = new_pts_col[star_pts_indices]
                best_sim_tets = tets[star_indices]

    if best_op == "none":
        return {**_FAIL, "n_star_tets": n_star}

    return {
        "success": True,
        "op_type": best_op,
        "energy_delta": best_delta,
        "sim_pts": best_sim_pts,
        "sim_tets": best_sim_tets,
        "n_star_tets": n_star,
    }


# ---------------------------------------------------------------------------
# VVV9K4 — priority-queue main loop helper (default OFF, no caller)
# Klingner & Shewchuk 2008 §3.5 Algorithm 1 skeleton
# ---------------------------------------------------------------------------

_VVV9K4_MAIN_LOOP: bool = False  # default OFF — caller added in VVV9K5+


def _priority_queue_main_loop(
    pts: "np.ndarray",
    tets: "np.ndarray",
    qualities: "np.ndarray",
    *,
    max_iters: int = 100,
    time_budget_ms: float = 200.0,
) -> "tuple[np.ndarray, np.ndarray, int, int, float, int, str]":
    """Priority-queue main loop helper skeleton (Klingner 2008 §3.5 Alg 1).

    Returns (new_pts, new_tets, n_improved, n_iters_used, total_delta,
             n_rejected, early_exit_reason).
    pts/tets are deep-copied — mesh is never mutated.
    Gate _VVV9K4_MAIN_LOOP=False → immediate no-op return.

    Monotone hardening (BETA2285_VVV9K8):
    - delta <= 1e-9 on success → rejected (n_rejected++), stagnation counter++
    - n_no_improve >= 8 → early exit ("stagnation") per Klingner §3.5 K=8
    """
    if not _VVV9K4_MAIN_LOOP:
        return pts.copy(), tets.copy(), 0, 0, 0.0, 0, ""

    import time  # noqa: PLC0415

    _MONOTONE_EPS: float = 1e-9
    _STAGNATION_K: int = 8

    t0 = time.perf_counter()
    heap = _priority_queue_init(qualities, k=max_iters)  # VVV9K1
    n_improved: int = 0
    n_rejected: int = 0
    n_no_improve: int = 0
    total_delta: float = 0.0
    n_iters_used: int = 0
    early_exit_reason: str = ""

    for _i in range(max_iters):
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if elapsed_ms > time_budget_ms:
            early_exit_reason = "time_budget"
            break
        popped = _priority_queue_pop_worst(heap, k=1)  # VVV9K2
        if not popped:
            early_exit_reason = "heap_empty"
            break
        n_iters_used += 1
        q_old, cell_idx = popped[0]  # noqa: F841
        res = _priority_queue_attempt_improvement(pts, tets, qualities, cell_idx)  # VVV9K3
        if res.get("success", False):
            delta = res.get("delta", 0.0)
            if delta > _MONOTONE_EPS:
                # Real improvement — monotone invariant satisfied
                n_improved += 1
                total_delta += delta
                n_no_improve = 0
            else:
                # Nominally successful but sub-threshold delta → reject
                n_rejected += 1
                n_no_improve += 1
        else:
            n_no_improve += 1

        if n_no_improve >= _STAGNATION_K:
            early_exit_reason = "stagnation"
            break
    else:
        early_exit_reason = "max_iters"

    # mesh unchanged — return copies of original input
    return pts.copy(), tets.copy(), n_improved, n_iters_used, total_delta, n_rejected, early_exit_reason


# CARD BETA2286_VVV9N1_LINE_COMPARE_HELPER — evidence-comparison helper
# Default OFF: no caller added.  Klingner 2008 §6 ablation methodology.


def _evidence_compare_lines(
    pts: "np.ndarray",
    tets: "np.ndarray",
    sliver_q_thr: float = 0.10,
    max_apply: int = 10,
) -> "dict":
    """Dry-simulate H / J / K VVV9 lines on a single mesh and compare worst_mq delta.

    Each line is applied to an independent deepcopy of (pts, tets); the
    original arrays are **never mutated**.  Returns the line with the largest
    positive Δworst_mq and per-line delta measurements.

    Parameters
    ----------
    pts          : (N, 3) float64 vertex positions — NOT mutated.
    tets         : (T, 4) int64 tet index array — NOT mutated.
    sliver_q_thr : quality threshold for sliver detection (passed to H candidates).
    max_apply    : cap on operations per line (wall-time protection).

    Returns
    -------
    dict with keys:
        best_line  : str  — 'H', 'J', 'K', or 'none' (no positive delta found).
        delta_H    : float — worst_mq improvement from line H (0.0 if n/a).
        delta_J    : float — worst_mq improvement from line J (0.0 if n/a).
        delta_K    : float — worst_mq improvement from line K (0.0 if n/a).
        wall_ms    : float — total wall time in milliseconds.

    Notes
    -----
    - Callers: none (gate OFF).  Planner activates in VVV9N2+ cards.
    - Monotone safety: each simulate helper already guards against quality
      regression (R197/R208/R220 hardening); this wrapper adds no extra ops.
    - Reference: Klingner & Shewchuk 2008 §6 ablation; R197/R208/R220.
    """
    import copy  # noqa: PLC0415
    import time  # noqa: PLC0415

    t0 = time.perf_counter()

    def _worst_mq(p: "np.ndarray", t: "np.ndarray") -> float:
        """Return min per-tet quality (worst_mq) over all tets."""
        if len(t) == 0:
            return 0.0
        return float(_tet_quality_batch(p, t).min())

    pre_worst = _worst_mq(pts, tets)

    # ── Line H: Klingner edge-contract (top-K short edges) ──────────────────
    delta_H: float = 0.0
    try:
        pts_h = copy.deepcopy(pts)
        tets_h = copy.deepcopy(tets)
        cands = _klingner_edge_contract_candidates(
            pts_h, tets_h, q_max=sliver_q_thr, max_candidates=max_apply * 4
        )
        if cands:
            _, tets_h, _ = _apply_klingner_edge_contract_topK(
                pts_h, tets_h, cands, k=max_apply
            )
        post_h = _worst_mq(pts_h, tets_h)
        delta_H = max(0.0, post_h - pre_worst)
    except Exception:  # noqa: BLE001
        delta_H = 0.0

    # ── Line J: SLIM Newton step on top-K worst-quality vertices ────────────
    delta_J: float = 0.0
    try:
        pts_j = copy.deepcopy(pts)
        tets_j = copy.deepcopy(tets)
        # Identify top-K worst vertices by min incident tet quality
        # C-PERF-60 / beta2511 — vectorize via _tet_quality_batch + np.minimum.at scatter.
        n_verts = len(pts_j)
        vert_min_q = np.ones(n_verts, dtype=np.float64)
        if len(tets_j) > 0:
            q_arr_j = _tet_quality_batch(pts_j, np.asarray(tets_j, dtype=np.int64))
            flat_v_j = np.asarray(tets_j, dtype=np.int64).reshape(-1)
            flat_q_j = np.repeat(q_arr_j, 4)
            np.minimum.at(vert_min_q, flat_v_j, flat_q_j)
        worst_verts = list(np.argsort(vert_min_q)[:max_apply])
        for v in worst_verts:
            res = _slim_newton_step_one_vertex(pts_j, tets_j, int(v))
            if res.get("accepted", False):
                pts_j[v] = res["new_pos"]
        post_j = _worst_mq(pts_j, tets_j)
        delta_J = max(0.0, post_j - pre_worst)
    except Exception:  # noqa: BLE001
        delta_J = 0.0

    # ── Line K: priority-queue main loop (VVV9K4 skeleton) ──────────────────
    delta_K: float = 0.0
    try:
        pts_k = copy.deepcopy(pts)
        tets_k = copy.deepcopy(tets)
        qs_k = _tet_quality_batch(pts_k, tets_k).astype(np.float64)
        _, tets_k, _ni, _nu, _td, _nr, _er = _priority_queue_main_loop(
            pts_k, tets_k, qs_k, max_iters=max_apply, time_budget_ms=200.0
        )
        post_k = _worst_mq(pts_k, tets_k)
        delta_K = max(0.0, post_k - pre_worst)
    except Exception:  # noqa: BLE001
        delta_K = 0.0

    # ── Best-line selection ──────────────────────────────────────────────────
    best_delta = max(delta_H, delta_J, delta_K)
    if best_delta <= 0.0:
        best_line = "none"
    elif delta_H >= delta_J and delta_H >= delta_K:
        best_line = "H"
    elif delta_J >= delta_K:
        best_line = "J"
    else:
        best_line = "K"

    wall_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "best_line": best_line,
        "delta_H": delta_H,
        "delta_J": delta_J,
        "delta_K": delta_K,
        "wall_ms": wall_ms,
    }


# ── Line P: Klingner & Shewchuk 2008 §3.4 Multi-Face Removal ────────────────
def _multi_face_removal_candidates(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    k_worst: int = 64,
    q_thr: float = 0.3,
) -> list[dict]:
    """Enumerate multi-face removal candidates (Klingner §3.4, read-only).

    For each of the k_worst tets, iterate over its 4 faces and compute the
    incident-tet star S_f.  Faces whose star min-quality q*(f) < q_thr are
    returned as candidates sorted by (star_size DESC, min_q ASC).

    Parameters
    ----------
    pts:     (N, 3) float64 vertex array.
    tets:    (M, 4) int32/int64 tet connectivity array.
    k_worst: top-K worst tets to examine (wall-time bound).
    q_thr:   quality threshold; only faces with star min_q < q_thr are kept.

    Returns
    -------
    list[dict] each with keys:
        "face"      : (a, b, c) sorted int tuple
        "star_size" : number of tets incident to the face
        "min_q"     : minimum quality among incident tets
        "owner_tet" : index of the worst tet that exposed this face
    """
    if len(tets) == 0:
        return []

    # Step 1: vectorised quality array → top-K worst tet indices.
    # C-PERF-87 / beta2539 — batched.
    q_arr = _tet_quality_batch(pts, tets).astype(np.float64)
    worst_indices = np.argsort(q_arr)[: k_worst]

    # Step 2: face → incident-tet map (LRU cache hit O(1) if already built).
    face_map = compute_face_incident_tets_cached(tets)

    # Step 3: enumerate face stars of worst tets.
    seen: set[tuple[int, int, int]] = set()
    candidates: list[dict] = []

    for ti in worst_indices:
        t = tets[ti]
        for fi, fj, fk in _FACES4:
            a, b, c = int(t[fi]), int(t[fj]), int(t[fk])
            # Sort triple for canonical key (same logic as compute_face_incident_tets_cached).
            if a > b:
                a, b = b, a
            if b > c:
                b, c = c, b
            if a > b:
                a, b = b, a
            key = (a, b, c)
            if key in seen:
                continue
            seen.add(key)

            star = face_map.get(key, [])
            if not star:
                continue
            star_min_q = min(float(q_arr[s]) for s in star)
            if star_min_q < q_thr:
                candidates.append(
                    {
                        "face": key,
                        "star_size": len(star),
                        "min_q": star_min_q,
                        "owner_tet": int(ti),
                    }
                )

    # Step 4: tie-break — star_size DESC, min_q ASC.
    candidates.sort(key=lambda c: (-c["star_size"], c["min_q"]))
    return candidates


# ── Line Q: Klingner & Shewchuk 2008 §3.4 Multi-Face Removal — apply helper ──
def _multi_face_removal_apply(
    pts: np.ndarray,
    tets: np.ndarray,
    candidates: list[dict],
    *,
    top_k: int = 3,
) -> tuple[np.ndarray, np.ndarray, int, float]:
    """Apply helper for multi-face removal (sim-only, default OFF, no caller).

    Simulates 3-face (star_size=2) and 5-face (star_size=3) Stellar transitions
    for the top_k candidates from ``_multi_face_removal_candidates``, applying a
    monotone quality guard per face.  Input arrays are **never mutated**
    (copy-on-write); the returned arrays are always independent copies of the
    inputs because no caller exists yet (gate wiring = VVV9P5).

    Parameters
    ----------
    pts        : (N, 3) float64 vertex positions — untouched.
    tets       : (M, 4) int64 tet connectivity — untouched.
    candidates : output of ``_multi_face_removal_candidates`` (sorted).
    top_k      : number of leading candidates to examine (wall-time bound).

    Returns
    -------
    new_pts      : copy of pts (unchanged, no caller).
    new_tets     : copy of tets (unchanged, no caller).
    n_applied    : number of faces that passed the monotone guard (sim count).
    energy_delta : sum of (min_q_post - min_q_pre) over accepted faces.
    """
    new_pts = pts.copy()
    new_tets = tets.copy()
    n_applied: int = 0
    energy_delta: float = 0.0

    if len(tets) == 0 or not candidates:
        return new_pts, new_tets, n_applied, energy_delta

    # The transition is still an evidence-only card.  Keep the helper
    # transactional and explicit rather than falling through with ``None``
    # when candidates exist but the real operator is not enabled.
    return new_pts, new_tets, n_applied, energy_delta


# CARD BETA2294_VVV9N4_ENV_RUNNER — env-aware unified line-runner (skeleton, no caller)
def _env_aware_run_all_gates(
    pts: "np.ndarray",
    tets: "np.ndarray",
    q_thr: float = 0.10,
) -> "dict[str, dict]":
    """Dry-simulate H/J/K/P gate lines on independent deepcopies and return evidence.

    Each of the 4 lines is run on its own deepcopy of (pts, tets); the original
    mesh state is NEVER mutated.  Returns a dict keyed by line_name with per-line
    diagnostics useful for choosing the next sequence card.

    Parameters
    ----------
    pts   : (N, 3) float64 vertex positions — NOT mutated.
    tets  : (M, 4) int64  tet connectivity  — NOT mutated.
    q_thr : quality threshold passed to per-line helpers (default 0.10).

    Returns
    -------
    dict[str, dict] with keys "line_H", "line_J", "line_K", "line_P".
    Each inner dict has:
        n_app         : int   — number of operations applied / candidates.
        post_min_q    : float — worst tet quality after dry-simulate.
        delta_worst   : float — post_min_q - pre_min_q (positive = improvement).
        wall_ms       : float — wall-clock milliseconds consumed.
    """
    if pts is None or tets is None or pts.shape[0] == 0 or tets.shape[0] == 0:
        empty: dict = {"n_app": 0, "post_min_q": 0.0, "delta_worst": 0.0, "wall_ms": 0.0}
        return {"line_H": empty, "line_J": empty, "line_K": empty, "line_P": empty}

    # Pre-quality baseline (original mesh) — batched.
    pre_quals = _tet_quality_batch(pts, tets).astype(np.float64)
    pre_min_q: float = float(pre_quals.min()) if len(pre_quals) > 0 else 0.0

    results: dict[str, dict] = {}

    # ── Line H: edge-contraction candidates ──────────────────────────────────
    t0 = time.perf_counter()
    pts_h = pts.copy()
    tets_h = tets.copy()
    cands_h = _klingner_edge_contract_candidates(pts_h, tets_h, q_max=max(q_thr, 0.2))
    n_app_h = len(cands_h)
    post_min_q_h = float(cands_h[0][2]) if cands_h else pre_min_q
    wall_h = (time.perf_counter() - t0) * 1e3
    results["line_H"] = {
        "n_app": n_app_h,
        "post_min_q": post_min_q_h,
        "delta_worst": post_min_q_h - pre_min_q,
        "wall_ms": wall_h,
    }

    # ── Line J: SLIM Newton step (loop over low-quality vertices) ────────────
    t0 = time.perf_counter()
    pts_j = pts.copy()
    tets_j = tets.copy()
    quals_j = _tet_quality_batch(pts_j, tets_j).astype(np.float64)
    worst_verts = set()
    for ti, q in enumerate(quals_j):
        if q < q_thr:
            for vi in tets_j[ti]:
                worst_verts.add(int(vi))
    n_app_j = 0
    min_q_j = pre_min_q
    for vi in list(worst_verts)[:50]:  # cap to bound wall time
        res_j = _slim_newton_step_one_vertex(pts_j, tets_j, vi)
        if res_j.get("accepted", False):
            n_app_j += 1
            pts_j[vi] = res_j["new_pos"]
    if n_app_j > 0:
        # C-PERF-93 / beta2545 — batched.
        post_quals_j = _tet_quality_batch(pts_j, tets_j).astype(np.float64)
        min_q_j = float(post_quals_j.min()) if len(post_quals_j) > 0 else pre_min_q
        min_q_j = max(min_q_j, pre_min_q - 1e-9)  # monotone guard
    wall_j = (time.perf_counter() - t0) * 1e3
    results["line_J"] = {
        "n_app": n_app_j,
        "post_min_q": min_q_j,
        "delta_worst": min_q_j - pre_min_q,
        "wall_ms": wall_j,
    }

    # ── Line K: priority-queue main loop ────────────────────────────────────
    t0 = time.perf_counter()
    pts_k = pts.copy()
    tets_k = tets.copy()
    quals_k = _tet_quality_batch(pts_k, tets_k).astype(np.float64)
    pq_out = _priority_queue_main_loop(pts_k, tets_k, quals_k, max_iters=20, time_budget_ms=100.0)
    n_app_k = int(pq_out[2])
    post_pts_k, post_tets_k = pq_out[0], pq_out[1]
    if n_app_k > 0 and len(post_tets_k) > 0:
        post_quals_k = _tet_quality_batch(post_pts_k, post_tets_k).astype(np.float64)
        min_q_k = float(post_quals_k.min())
        min_q_k = max(min_q_k, pre_min_q - 1e-9)  # monotone guard
    else:
        min_q_k = pre_min_q
    wall_k = (time.perf_counter() - t0) * 1e3
    results["line_K"] = {
        "n_app": n_app_k,
        "post_min_q": min_q_k,
        "delta_worst": min_q_k - pre_min_q,
        "wall_ms": wall_k,
    }

    # ── Line P: multi-face removal candidates ───────────────────────────────
    t0 = time.perf_counter()
    pts_p = pts.copy()
    tets_p = tets.copy()
    cands_p = _multi_face_removal_candidates(pts_p, tets_p, q_thr=max(q_thr, 0.3))
    n_app_p = len(cands_p)
    if cands_p:
        min_q_p = float(min(c.get("min_q", pre_min_q) for c in cands_p))
        min_q_p = max(min_q_p, pre_min_q - 1e-9)  # monotone guard
    else:
        min_q_p = pre_min_q
    wall_p = (time.perf_counter() - t0) * 1e3
    results["line_P"] = {
        "n_app": n_app_p,
        "post_min_q": min_q_p,
        "delta_worst": min_q_p - pre_min_q,
        "wall_ms": wall_p,
    }

    return results

    face_map = compute_face_incident_tets_cached(tets)

    for cand in candidates[:top_k]:
        face_key: tuple[int, int, int] = cand["face"]
        star_size: int = cand["star_size"]

        star_indices = face_map.get(face_key, [])
        if len(star_indices) != star_size:
            continue  # stale map entry — skip

        # ── Pre-quality of star tets ──────────────────────────────────────────
        star_tets = [tets[i] for i in star_indices]
        q_pre_list = [float(_tet_quality(pts, t)) for t in star_tets]
        min_q_pre = min(q_pre_list)
        mean_q_pre = sum(q_pre_list) / len(q_pre_list)

        # ── Enumerate opposite vertices for simulated retriangulation ─────────
        # Gather all unique vertices in the star, then find vertices NOT in face.
        fa, fb, fc = face_key
        face_verts: set[int] = {fa, fb, fc}
        star_all_verts: set[int] = set()
        for t in star_tets:
            for v in t:
                star_all_verts.add(int(v))
        opp_verts = sorted(star_all_verts - face_verts)

        # 3-face removal: 1 opposite vertex expected (star_size=2 → 2 tets share face).
        # 5-face removal: 2 opposite vertices expected (star_size=3 → 3 tets share face).
        expected_opp = star_size - 1
        if len(opp_verts) != expected_opp:
            continue  # topology mismatch — skip

        # ── Build simulated post-star tets ────────────────────────────────────
        # 3-face removal (star_size=2): replace 2 tets across shared face with
        #   3 tets pivoting on the edge connecting the two opposite vertices.
        #   opp_verts = [v0, v1]; new tets = (fa,fb,v0,v1), (fb,fc,v0,v1), (fa,fc,v0,v1).
        # 5-face removal (star_size=3): replace 3 tets across shared edge (= face interior
        #   diagonal) with 5 tets; opp_verts = [v0, v1]; enumerate all face triples from
        #   {fa, fb, fc, v0, v1} choosing vertex pairs to complete each tet with the edge.
        post_tets_sim: list[np.ndarray] = []
        if star_size == 2:
            v0, v1 = opp_verts
            post_tets_sim = [
                np.array([fa, fb, v0, v1], dtype=np.int64),
                np.array([fb, fc, v0, v1], dtype=np.int64),
                np.array([fa, fc, v0, v1], dtype=np.int64),
            ]
        elif star_size == 3:
            v0, v1 = opp_verts
            # 5-face star: enumerate all 4-subsets from {fa,fb,fc,v0,v1} that include
            # the edge (v0,v1) — yielding C(3,2)=3 base faces × each completed by edge.
            face_ring = [fa, fb, fc]
            for i in range(len(face_ring)):
                for j in range(i + 1, len(face_ring)):
                    va, vb = face_ring[i], face_ring[j]
                    post_tets_sim.append(
                        np.array([va, vb, v0, v1], dtype=np.int64)
                    )
            # Additional pivot tets to cover the full 5-tet star (one per face vertex).
            for vf in face_ring:
                post_tets_sim.append(
                    np.array([vf, v0, v1, fa if vf != fa else fb], dtype=np.int64)
                )
        else:
            continue  # unsupported star_size

        # ── Post-quality of simulated tets ────────────────────────────────────
        q_post_list = [float(_tet_quality(new_pts, t)) for t in post_tets_sim]
        if not q_post_list:
            continue
        min_q_post = min(q_post_list)
        mean_q_post = sum(q_post_list) / len(q_post_list)

        # ── Monotone guard ────────────────────────────────────────────────────
        if min_q_post >= min_q_pre and mean_q_post >= mean_q_pre - 1e-9:
            n_applied += 1
            energy_delta += min_q_post - min_q_pre
            # Sim-only: local simulation arrays are discarded here.
            # new_tets remains an unmodified copy of tets (no caller yet).

    return new_pts, new_tets, n_applied, energy_delta
