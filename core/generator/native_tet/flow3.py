"""Read-only TET-FLOW-3 candidate ladder diagnostics.

This module is intentionally not wired into the mesher.  It implements the
smallest candidate-level version of Leng et al.'s rising-threshold transform
ladder: bad tets are visited in stable order, all local face/edge candidates
are simulated, and only the candidate with the best local worst quality is
selected.  Every candidate is transactional and must preserve the global
boundary face set, signed-volume tiling, and the pre-candidate global minimum
quality.

The helper is a measurement lane, not a claim that the current native-tet
quality metric is the paper's complete objective.  It deliberately returns a
private result and leaves the caller's arrays untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.generator.native_tet.boundary_invariant import check_boundary_invariant
from core.generator.native_tet.fsl_wave1 import (
    _edge_to_tets_map,
    _face_map_vectorized,
    general_edge_removal,
)
from core.generator.native_tet.near_wall import boundary_face_keys
from core.generator.native_tet.quality import tet_shape_quality
from core.generator.native_tet.validate import signed_volume6


_EPS = 1e-12
_MIN_VOL6 = 1e-18
_DEFAULT_RUNG_EPS = (0.4, 0.5, 0.6, 0.7, 0.8)


@dataclass
class Flow3Report:
    """Stable summary for one private TET-FLOW-3 diagnostic replay."""

    n_tets_before: int = 0
    n_tets_after: int = 0
    candidate_n_tets_after: int = 0
    n_rungs: int = 0
    n_rounds: int = 0
    n_bad_tets_seen: int = 0
    n_candidates_seen: int = 0
    n_candidates_boundary_rejected: int = 0
    n_exact_boundary_checks: int = 0
    n_candidates_volume_rejected: int = 0
    n_candidates_quality_rejected: int = 0
    n_accepted: int = 0
    n_face23: int = 0
    n_edge32_or_general: int = 0
    n_edge44: int = 0
    min_q_before: float = 0.0
    min_q_after: float = 0.0
    mean_q_before: float = 0.0
    mean_q_after: float = 0.0
    candidate_min_q_after: float = 0.0
    candidate_mean_q_after: float = 0.0
    boundary_faces_before: int = 0
    boundary_faces_after: int = 0
    boundary_preserved: bool = True
    input_unchanged: bool = True
    surface_vertices_moved: bool = False
    sequence_decision: str = "rollback"
    rungs: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _face_owners(tets: np.ndarray) -> dict[tuple[int, int, int], list[int]]:
    fmap = _face_map_vectorized(np.asarray(tets, dtype=np.int64))
    return {key: sorted(int(v) for v in owners) for key, owners in fmap.items()}


def _edge_owners(tets: np.ndarray) -> dict[tuple[int, int], list[int]]:
    e2t = _edge_to_tets_map(np.asarray(tets, dtype=np.int64))
    return {key: sorted(int(v) for v in owners) for key, owners in e2t.items()}


def _replace_owners(
    tets: np.ndarray,
    owners: list[int] | tuple[int, ...],
    new_local: np.ndarray,
) -> np.ndarray:
    alive = np.ones(len(tets), dtype=bool)
    alive[np.asarray(owners, dtype=np.int64)] = False
    return np.concatenate([np.asarray(tets, dtype=np.int64)[alive], new_local], axis=0)


def _valid_tiling(
    points: np.ndarray,
    old_local: np.ndarray,
    new_local: np.ndarray,
) -> bool:
    old_v = signed_volume6(points, old_local)
    new_v = signed_volume6(points, new_local)
    if old_v.size == 0 or new_v.size == 0:
        return False
    if np.any(np.abs(old_v) < _MIN_VOL6) or np.any(np.abs(new_v) < _MIN_VOL6):
        return False
    old_sum = float(np.abs(old_v).sum())
    new_sum = float(np.abs(new_v).sum())
    return bool(abs(new_sum - old_sum) <= 1e-9 * max(old_sum, 1e-30))


def _face23_candidate(
    points: np.ndarray,
    tets: np.ndarray,
    face: tuple[int, int, int],
    owners: list[int],
) -> tuple[np.ndarray | None, str]:
    if len(owners) != 2:
        return None, "face_not_two_owner"
    a, b, c = face
    x = [v for v in tets[owners[0]].tolist() if v not in face]
    y = [v for v in tets[owners[1]].tolist() if v not in face]
    if len(x) != 1 or len(y) != 1 or x[0] == y[0]:
        return None, "malformed_face_ring"
    new = np.asarray(
        [(a, b, x[0], y[0]), (b, c, x[0], y[0]), (c, a, x[0], y[0])],
        dtype=np.int64,
    )
    if any(len(set(row.tolist())) != 4 for row in new):
        return None, "duplicate_candidate_tet"
    new_v = signed_volume6(points, new)
    if np.any(np.abs(new_v) < _MIN_VOL6) or not (
        np.all(new_v > _MIN_VOL6) or np.all(new_v < -_MIN_VOL6)
    ):
        return None, "orientation"
    old = np.asarray(tets[owners], dtype=np.int64)
    if not _valid_tiling(points, old, new):
        return None, "volume_tiling"
    return _replace_owners(tets, owners, new), "ok"


def _ring_cycle(ring_pairs: list[tuple[int, int]]) -> list[int] | None:
    """Recover a deterministic 4-cycle from owner tet opposite pairs."""
    graph: dict[int, set[int]] = {}
    for u, v in ring_pairs:
        if u == v:
            return None
        graph.setdefault(int(u), set()).add(int(v))
        graph.setdefault(int(v), set()).add(int(u))
    if len(graph) != 4 or any(len(nbrs) != 2 for nbrs in graph.values()):
        return None
    start = min(graph)
    first = min(graph[start])
    cycle = [start, first]
    previous, current = start, first
    while len(cycle) < 4:
        options = sorted(graph[current] - {previous})
        if not options:
            return None
        nxt = options[0]
        if nxt in cycle:
            return None
        cycle.append(nxt)
        previous, current = current, nxt
    if start not in graph[current]:
        return None
    return cycle


def _edge44_candidate(
    points: np.ndarray,
    tets: np.ndarray,
    edge: tuple[int, int],
    owners: list[int],
) -> tuple[np.ndarray | None, str]:
    if len(owners) != 4:
        return None, "edge_not_four_owner"
    u, v = edge
    pairs: list[tuple[int, int]] = []
    for ti in owners:
        rest = [int(x) for x in tets[ti].tolist() if x not in edge]
        if len(rest) != 2:
            return None, "malformed_edge_ring"
        pairs.append((rest[0], rest[1]))
    ring = _ring_cycle(pairs)
    if ring is None:
        return None, "ring_not_cycle"
    candidates = []
    for r in (ring, [ring[1], ring[0], ring[3], ring[2]]):
        new = np.asarray(
            [
                (u, r[0], r[1], r[2]),
                (u, r[0], r[2], r[3]),
                (v, r[0], r[1], r[2]),
                (v, r[0], r[2], r[3]),
            ],
            dtype=np.int64,
        )
        if any(len(set(row.tolist())) != 4 for row in new):
            continue
        vv = signed_volume6(points, new)
        if np.any(np.abs(vv) < _MIN_VOL6):
            continue
        if float(vv[0]) * float(vv[2]) > 0 or float(vv[1]) * float(vv[3]) > 0:
            continue
        if _valid_tiling(points, np.asarray(tets[owners]), new):
            candidates.append(new)
    if not candidates:
        return None, "orientation_or_volume"
    q = [float(tet_shape_quality(points, c).min()) for c in candidates]
    best = candidates[int(np.argmax(np.asarray(q)))]
    return _replace_owners(tets, owners, best), "ok"


def _candidate_score(
    points: np.ndarray,
    before: np.ndarray,
    after: np.ndarray,
    owners: list[int],
) -> tuple[float, float]:
    old_q = float(tet_shape_quality(points, before[np.asarray(owners)]).min())
    # A candidate's appended suffix is the replacement cavity.  This is
    # deterministic because _replace_owners always appends new rows.
    n_new = len(after) - (len(before) - len(owners))
    new_q = float(tet_shape_quality(points, after[-n_new:]).min())
    return old_q, new_q


def _candidate_global_min(
    points: np.ndarray,
    before_quality: np.ndarray,
    before_tets: np.ndarray,
    after_tets: np.ndarray,
    owners: list[int],
) -> float:
    """Compute global min-Q without reevaluating unaffected tets."""
    keep = np.ones(len(before_tets), dtype=bool)
    keep[np.asarray(owners, dtype=np.int64)] = False
    n_new = len(after_tets) - int(keep.sum())
    if n_new <= 0:
        return float(before_quality[keep].min()) if keep.any() else 0.0
    new_quality = tet_shape_quality(points, after_tets[-n_new:])
    old_min = float(before_quality[keep].min()) if keep.any() else float("inf")
    new_min = float(new_quality.min()) if new_quality.size else float("inf")
    return min(old_min, new_min)


def run_flow3_diagnostic(
    points: np.ndarray,
    tets: np.ndarray,
    *,
    epsilons: tuple[float, ...] = _DEFAULT_RUNG_EPS,
    rounds_per_rung: int = 2,
    max_bad_tets: int = 128,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Run a bounded, private TET-FLOW-3 ladder diagnostic.

    The caller's arrays are never mutated.  The returned tet array is the
    private replay only; production wiring is intentionally absent.  The
    ladder uses stable quality ordering and a deterministic operation tie-break
    ``face23 < edge44 < edge-removal``.
    """
    pts = np.asarray(points, dtype=np.float64)
    original = np.asarray(tets, dtype=np.int64).copy()
    working = original.copy()
    initial_boundary = boundary_face_keys(original)
    q0 = tet_shape_quality(pts, original)
    report = Flow3Report(
        n_tets_before=len(original),
        n_rungs=len(epsilons),
        min_q_before=float(q0.min()) if q0.size else 0.0,
        mean_q_before=float(q0.mean()) if q0.size else 0.0,
        boundary_faces_before=len(initial_boundary),
    )

    for rung_index, epsilon in enumerate(epsilons):
        rung = {"rung": int(rung_index), "epsilon": float(epsilon), "accepted": 0, "rounds": []}
        for round_index in range(max(1, rounds_per_rung)):
            q = tet_shape_quality(pts, working)
            bad = np.flatnonzero(q < float(epsilon))[:max_bad_tets]
            report.n_bad_tets_seen += int(len(bad))
            if bad.size == 0:
                rung["rounds"].append({"round": round_index, "n_bad": 0, "decision": "stop"})
                break
            before_min = float(q.min()) if q.size else 0.0
            face_map = _face_owners(working)
            edge_map = _edge_owners(working)
            boundary_edges = {
                tuple(sorted(edge))
                for face, owners in face_map.items()
                if len(owners) == 1
                for edge in (
                    (face[0], face[1]),
                    (face[0], face[2]),
                    (face[1], face[2]),
                )
            }
            best: tuple[tuple[float, int, tuple[int, ...]], np.ndarray, str, list[int]] | None = None
            local_rejected = 0
            for ti in bad.tolist():
                tet = working[int(ti)]
                faces = [tuple(sorted(int(v) for v in tet if v != tet[slot])) for slot in range(4)]
                edges = [tuple(sorted((int(tet[i]), int(tet[j])))) for i, j in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))]
                candidates: list[tuple[np.ndarray | None, str, list[int], str]] = []
                for face in sorted(set(faces)):
                    owners = face_map.get(face, [])
                    trial, reason = _face23_candidate(pts, working, face, owners)
                    candidates.append((trial, reason, owners, "face23"))
                for edge in sorted(set(edges)):
                    owners = edge_map.get(edge, [])
                    if len(owners) == 4:
                        trial, reason = _edge44_candidate(pts, working, edge, owners)
                        candidates.append((trial, reason, owners, "edge44"))
                    elif len(owners) >= 3:
                        trial, info = general_edge_removal(
                            pts, working, edge[0], edge[1],
                            min_quality_improvement=1e-4, exhaustive=True,
                            _precomputed_edge_owners=edge_map,
                            _precomputed_face_owners=face_map,
                            _precomputed_boundary_edges=boundary_edges,
                        )
                        candidates.append((trial, str(info.get("reason", "rejected")), owners, "edge_remove"))
                for trial, reason, owners, op in candidates:
                    report.n_candidates_seen += 1
                    if trial is None:
                        local_rejected += 1
                        continue
                    n_new = len(trial) - (len(working) - len(owners))
                    new_local = np.asarray(trial[-n_new:], dtype=np.int64)
                    if not _valid_tiling(pts, np.asarray(working[owners]), new_local):
                        report.n_candidates_volume_rejected += 1
                        local_rejected += 1
                        continue
                    if _candidate_global_min(pts, q, working, trial, owners) < before_min - _EPS:
                        report.n_candidates_quality_rejected += 1
                        local_rejected += 1
                        continue
                    old_local, new_local = _candidate_score(pts, working, trial, owners)
                    if new_local <= old_local + 1e-4:
                        report.n_candidates_quality_rejected += 1
                        local_rejected += 1
                        continue
                    rank = {"face23": 0, "edge44": 1, "edge_remove": 2}[op]
                    key = (new_local, -rank, tuple(-int(v) for v in owners))
                    if best is None or key > best[0]:
                        best = (key, trial, op, owners)
            if best is None:
                rung["rounds"].append({"round": round_index, "n_bad": int(len(bad)), "accepted": False, "rejected": local_rejected, "decision": "stop"})
                break
            exact_boundary = check_boundary_invariant(
                pts,
                working,
                pts,
                best[1],
                f"tet_flow3_r{rung_index}_s{round_index}_selected_{best[2]}",
                log_only=True,
            )
            report.n_exact_boundary_checks += 1
            if not exact_boundary.preserved:
                report.n_candidates_boundary_rejected += 1
                rung["rounds"].append({"round": round_index, "n_bad": int(len(bad)), "accepted": False, "rejected": local_rejected + 1, "decision": "boundary_rollback"})
                break
            working = best[1]
            report.n_accepted += 1
            rung["accepted"] += 1
            if best[2] == "face23":
                report.n_face23 += 1
            elif best[2] == "edge44":
                report.n_edge44 += 1
            else:
                report.n_edge32_or_general += 1
            report.n_rounds += 1
            rung["rounds"].append({"round": round_index, "n_bad": int(len(bad)), "accepted": True, "operation": best[2], "local_worst_after": float(best[0][0])})
        report.rungs.append(rung)

    q1 = tet_shape_quality(pts, working)
    final_boundary = boundary_face_keys(working)
    report.candidate_n_tets_after = len(working)
    report.candidate_min_q_after = float(q1.min()) if q1.size else 0.0
    report.candidate_mean_q_after = float(q1.mean()) if q1.size else 0.0
    report.boundary_faces_after = len(final_boundary)
    report.boundary_preserved = bool(final_boundary == initial_boundary)
    report.input_unchanged = bool(np.array_equal(np.asarray(tets), original))
    report.surface_vertices_moved = False
    report.sequence_decision = "would_accept" if report.boundary_preserved and report.candidate_min_q_after >= report.min_q_before - _EPS and report.candidate_min_q_after > report.min_q_before + _EPS else "rollback"
    if report.sequence_decision == "rollback":
        working = original.copy()
    q_returned = tet_shape_quality(pts, working)
    report.n_tets_after = len(working)
    report.min_q_after = float(q_returned.min()) if q_returned.size else 0.0
    report.mean_q_after = float(q_returned.mean()) if q_returned.size else 0.0
    return working, report.as_dict()
