"""Bounded multi-face reconstruction helpers for native tet.

This module is deliberately standalone.  It proposes local edge-cavity
retriangulations only; callers decide when to hook it into a mesher pass.

Paper basis:
    - Misztal et al., Multi-face retriangulation, local cavity reconnection.
    - Ma/Wang, MFRC, larger-than-flip reconstruction when flips plateau.
    - Klingner/Shewchuk, quality-vector acceptance for local operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations

import numpy as np

from core.generator.native_tet.quality import tet_shape_quality


Face = tuple[int, int, int]
Edge = tuple[int, int]


def _sorted2(a: int, b: int) -> Edge:
    return (a, b) if a < b else (b, a)


def _sorted3(a: int, b: int, c: int) -> Face:
    x, y, z = sorted((int(a), int(b), int(c)))
    return (x, y, z)


def _tet_faces(tet: tuple[int, int, int, int]) -> tuple[Face, Face, Face, Face]:
    a, b, c, d = tet
    return (
        _sorted3(a, b, c),
        _sorted3(a, b, d),
        _sorted3(a, c, d),
        _sorted3(b, c, d),
    )


def _boundary_faces(tets: np.ndarray) -> frozenset[Face]:
    counts: dict[Face, int] = {}
    for row in np.asarray(tets, dtype=np.int64):
        tet = tuple(int(v) for v in row)
        for face in _tet_faces(tet):
            counts[face] = counts.get(face, 0) + 1
    return frozenset(face for face, count in counts.items() if count == 1)


def _signed_vol6(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0, dtype=np.float64)
    a = pts[tets[:, 0]]
    b = pts[tets[:, 1]]
    c = pts[tets[:, 2]]
    d = pts[tets[:, 3]]
    return np.einsum("ij,ij->i", b - a, np.cross(c - a, d - a))


def _quality_vector_improves(
    old_quality: np.ndarray,
    new_quality: np.ndarray,
    *,
    eps: float,
) -> bool:
    old_sorted = np.sort(np.asarray(old_quality, dtype=np.float64))
    new_sorted = np.sort(np.asarray(new_quality, dtype=np.float64))
    tol = max(0.0, float(eps))
    improved = False
    for old_value, new_value in zip(old_sorted, new_sorted, strict=False):
        if new_value + tol < old_value:
            return False
        if new_value > old_value + tol:
            improved = True
    return improved


def _quality_rank(old_quality: np.ndarray, new_quality: np.ndarray) -> tuple[float, ...]:
    old_sorted = np.sort(np.asarray(old_quality, dtype=np.float64))
    new_sorted = np.sort(np.asarray(new_quality, dtype=np.float64))
    n = min(old_sorted.shape[0], new_sorted.shape[0])
    delta = tuple(float(new_sorted[i] - old_sorted[i]) for i in range(n))
    return delta + (float(old_sorted.shape[0] - new_sorted.shape[0]),)


@lru_cache(maxsize=256)
def _polygon_triangulations(vertices: tuple[int, ...]) -> tuple[tuple[Face, ...], ...]:
    """All triangulations of an ordered polygon, bounded by caller ring size."""
    n = len(vertices)
    if n < 3:
        return tuple()
    if n == 3:
        return (((vertices[0], vertices[1], vertices[2]),),)

    out: list[tuple[Face, ...]] = []
    root = vertices[0]
    for i in range(1, n - 1):
        left = vertices[: i + 1]
        right = (root,) + vertices[i + 1 :]
        left_tris = (tuple(),) if len(left) < 3 else _polygon_triangulations(left)
        right_tris = (tuple(),) if len(right) < 3 else _polygon_triangulations(right)
        mid = (root, vertices[i], vertices[i + 1])
        for lt in left_tris:
            for rt in right_tris:
                out.append(tuple(lt) + (mid,) + tuple(rt))
    return tuple(out)


@dataclass(frozen=True)
class EdgeCavity:
    edge: Edge
    owner_tet_ids: tuple[int, ...]
    ring_vertices: tuple[int, ...]
    boundary_faces: frozenset[Face]
    old_tets: np.ndarray


@dataclass(frozen=True)
class MfrcCandidate:
    edge: Edge
    owner_tet_ids: tuple[int, ...]
    old_tets: np.ndarray
    new_tets: np.ndarray
    old_quality: np.ndarray
    new_quality: np.ndarray
    boundary_faces: frozenset[Face]
    quality_rank: tuple[float, ...]
    accepted: bool
    reason: str

    @property
    def min_quality_before(self) -> float:
        return float(np.min(self.old_quality)) if self.old_quality.size else 0.0

    @property
    def min_quality_after(self) -> float:
        return float(np.min(self.new_quality)) if self.new_quality.size else 0.0


def _order_ring_from_pairs(pairs: list[tuple[int, int]]) -> tuple[int, ...] | None:
    graph: dict[int, list[int]] = {}
    for a, b in pairs:
        if a == b:
            return None
        graph.setdefault(int(a), []).append(int(b))
        graph.setdefault(int(b), []).append(int(a))
    if len(graph) < 3 or any(len(nbrs) != 2 for nbrs in graph.values()):
        return None

    start = min(graph)
    order = [start]
    prev = -1
    cur = start
    while True:
        nxts = [v for v in graph[cur] if v != prev]
        if not nxts:
            return None
        nxt = min(nxts) if prev < 0 else nxts[0]
        if nxt == start:
            return tuple(order) if len(order) == len(graph) else None
        if nxt in order:
            return None
        order.append(nxt)
        prev, cur = cur, nxt


def extract_edge_cavity(
    tets: np.ndarray,
    edge: tuple[int, int],
    *,
    max_ring_vertices: int = 8,
) -> EdgeCavity | None:
    """Extract an internal edge-ring cavity for bounded MFRC.

    The cavity is valid when all owner tetrahedra around ``edge`` form one
    closed ring. Boundary faces are preserved by candidate validation.
    """
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return None
    u, v = _sorted2(int(edge[0]), int(edge[1]))
    owner_ids: list[int] = []
    ring_pairs: list[tuple[int, int]] = []
    for ti, row in enumerate(tets):
        verts = [int(x) for x in row]
        if u not in verts or v not in verts:
            continue
        opp = [x for x in verts if x != u and x != v]
        if len(opp) != 2:
            return None
        owner_ids.append(ti)
        ring_pairs.append((opp[0], opp[1]))
    if len(owner_ids) < 3:
        return None
    ring = _order_ring_from_pairs(ring_pairs)
    if ring is None or len(ring) > int(max_ring_vertices):
        return None
    old = tets[np.asarray(owner_ids, dtype=np.int64)]
    return EdgeCavity(
        edge=(u, v),
        owner_tet_ids=tuple(owner_ids),
        ring_vertices=ring,
        boundary_faces=_boundary_faces(old),
        old_tets=old.copy(),
    )


def enumerate_edge_mfrc_candidates(
    pts: np.ndarray,
    tets: np.ndarray,
    edge: tuple[int, int],
    *,
    max_ring_vertices: int = 8,
    max_triangulations: int = 256,
    min_abs_vol6: float = 1e-20,
    min_quality_improvement: float = 1e-4,
) -> list[MfrcCandidate]:
    """Enumerate bounded edge-removal MFRC candidates.

    Each polygon triangulation of the ring builds two tet fans, one from each
    endpoint of the removed edge. Invalid volume or boundary-mismatch
    candidates are kept with rejection reason for tests/diagnostics.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    cavity = extract_edge_cavity(tets, edge, max_ring_vertices=max_ring_vertices)
    if cavity is None:
        return []

    old_quality = tet_shape_quality(pts, cavity.old_tets)
    old_vol = float(np.abs(_signed_vol6(pts, cavity.old_tets)).sum())
    out: list[MfrcCandidate] = []
    u, v = cavity.edge
    triangulations = _polygon_triangulations(cavity.ring_vertices)
    for tris in triangulations[: int(max_triangulations)]:
        new_rows: list[tuple[int, int, int, int]] = []
        for a, b, c in tris:
            new_rows.append((u, int(a), int(b), int(c)))
            new_rows.append((v, int(a), int(b), int(c)))
        new_tets = np.asarray(new_rows, dtype=np.int64)
        new_vol6 = _signed_vol6(pts, new_tets)
        new_boundary = _boundary_faces(new_tets)
        new_quality = tet_shape_quality(pts, new_tets)

        reason = "accepted"
        accepted = True
        if any(len(set(map(int, row))) != 4 for row in new_tets):
            accepted = False
            reason = "duplicate_vertex"
        elif np.any(np.abs(new_vol6) <= float(min_abs_vol6)):
            accepted = False
            reason = "degenerate_volume"
        elif new_boundary != cavity.boundary_faces:
            accepted = False
            reason = "boundary_mismatch"
        else:
            new_vol = float(np.abs(new_vol6).sum())
            tol = 1e-9 * max(old_vol, 1e-30)
            if abs(new_vol - old_vol) > tol:
                accepted = False
                reason = "volume_mismatch"
            elif not _quality_vector_improves(
                old_quality,
                new_quality,
                eps=float(min_quality_improvement),
            ):
                accepted = False
                reason = "quality_not_improved"

        out.append(
            MfrcCandidate(
                edge=cavity.edge,
                owner_tet_ids=cavity.owner_tet_ids,
                old_tets=cavity.old_tets.copy(),
                new_tets=new_tets,
                old_quality=old_quality.copy(),
                new_quality=new_quality,
                boundary_faces=cavity.boundary_faces,
                quality_rank=_quality_rank(old_quality, new_quality),
                accepted=accepted,
                reason=reason,
            )
        )
    return out


def propose_edge_mfrc(
    pts: np.ndarray,
    tets: np.ndarray,
    edge: tuple[int, int],
    **kwargs,
) -> MfrcCandidate | None:
    """Return best accepted bounded MFRC candidate for an edge cavity."""
    candidates = enumerate_edge_mfrc_candidates(pts, tets, edge, **kwargs)
    accepted = [candidate for candidate in candidates if candidate.accepted]
    if not accepted:
        return None
    return max(accepted, key=lambda candidate: candidate.quality_rank)


def apply_edge_mfrc(
    pts: np.ndarray,
    tets: np.ndarray,
    edge: tuple[int, int],
    **kwargs,
) -> tuple[np.ndarray, MfrcCandidate | None]:
    """Apply best bounded MFRC candidate to a copy of ``tets``.

    No mesher hook calls this yet. This helper exists so integration can stay
    small and rollback-friendly when enabled later.
    """
    tets = np.asarray(tets, dtype=np.int64)
    candidate = propose_edge_mfrc(pts, tets, edge, **kwargs)
    if candidate is None:
        return tets.copy(), None
    remove = set(candidate.owner_tet_ids)
    keep = [row for i, row in enumerate(tets) if i not in remove]
    if keep:
        out = np.vstack([np.asarray(keep, dtype=np.int64), candidate.new_tets])
    else:
        out = candidate.new_tets.copy()
    return out.astype(np.int64, copy=False), candidate
