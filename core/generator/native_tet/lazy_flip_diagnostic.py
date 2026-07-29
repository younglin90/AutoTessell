"""Read-only TET-LAZY-2 measurements for native tetrahedral meshes.

This module deliberately stops at measurement.  It reuses the existing
``fsl_wave1.general_edge_removal`` lazy candidate generator, but never calls
the native mesher and never returns an edited mesh.  A candidate is simulated
on a private copy and is only allowed into the simulated sequence when the
existing minimum-quality gate, the existing volume-tiling gate, the boundary
face-set gate, and an additional signed-volume orientation guard all pass.

The diagnostic follows the frozen-boundary subset of Dassi et al. (2018):
interior edge rings only, deterministic serial traversal, and no surface
vertex movement.  The two local criteria alternate by round:

* ``angle``: maximize the cavity/global minimum dihedral while minimizing the
  maximum dihedral, without regressing either quantity;
* ``aspect``: minimize the Dassi ``sqrt(2/3) * L / h`` aspect ratio.

The raw before/after cavity arrays are retained in the report so a rejected
candidate is still useful evidence.  A whole simulated sequence is marked for
rollback unless its final global metrics improve without regressing the hard
quality and boundary checks.  Because this is a diagnostic, even a sequence
marked ``would_accept`` is not applied to caller-owned arrays.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import numpy as np

from core.generator.native_tet.boundary_invariant import check_boundary_invariant
from core.generator.native_tet.fsl_wave1 import (
    _boundary_edges_from_fmap,
    _edge_to_tets_map,
    _face_map_vectorized,
    general_edge_removal,
)
from core.generator.native_tet.near_wall import boundary_face_keys
from core.generator.native_tet.quality import tet_shape_quality
from core.generator.native_tet.validate import signed_volume6


# This is the current general_edge_removal gate.  TET-LAZY-2 must not make it
# easier to accept a candidate merely because it is running as a diagnostic.
MIN_QUALITY_IMPROVEMENT = 1e-4
MIN_ABS_SIGNED_VOLUME6 = 1e-18
VOLUME_TILING_REL_TOL = 1e-9
METRIC_TOL = 1e-12


def _json_float(value: float) -> float | None:
    value = float(value)
    return value if np.isfinite(value) else None


def _json_array(values: np.ndarray) -> list[float | None]:
    return [_json_float(float(value)) for value in np.asarray(values).reshape(-1)]


def _digest_bytes(value: np.ndarray) -> str:
    return sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _face_digest(faces: set[tuple[int, int, int]]) -> str:
    if not faces:
        return sha256(b"").hexdigest()
    arr = np.asarray(sorted(faces), dtype=np.int64)
    return _digest_bytes(arr)


def _validate_input(points: np.ndarray, tets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    pts = np.asarray(points, dtype=np.float64)
    cells = np.asarray(tets, dtype=np.int64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("points must have shape (N, 3)")
    if cells.ndim != 2 or cells.shape[1] != 4:
        raise ValueError("tets must have shape (M, 4)")
    if not np.isfinite(pts).all():
        raise ValueError("points must be finite")
    if cells.size and (int(cells.min()) < 0 or int(cells.max()) >= len(pts)):
        raise ValueError("tets contain an out-of-range vertex index")
    return pts, cells


def _dihedral_bounds(points: np.ndarray, tets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the six-angle minimum and maximum for every tet."""
    cells = np.asarray(tets, dtype=np.int64)
    if cells.size == 0:
        empty = np.zeros(0, dtype=np.float64)
        return empty, empty
    v = points[cells]
    a, b, c, d = v[:, 0], v[:, 1], v[:, 2], v[:, 3]

    def unit_normal(p: np.ndarray, q: np.ndarray, r: np.ndarray) -> np.ndarray:
        normal = np.cross(q - p, r - p)
        norm = np.linalg.norm(normal, axis=1, keepdims=True)
        return normal / np.where(norm > 1e-30, norm, 1.0)

    normals = (
        unit_normal(a, b, c),
        unit_normal(a, b, d),
        unit_normal(a, c, d),
        unit_normal(b, c, d),
    )

    def dihedral(first: np.ndarray, second: np.ndarray) -> np.ndarray:
        dot = np.clip(np.einsum("ij,ij->i", first, second), -1.0, 1.0)
        return 180.0 - np.rad2deg(np.arccos(dot))

    n_abc, n_abd, n_acd, n_bcd = normals
    angles = np.stack(
        [
            dihedral(n_abc, n_abd),
            dihedral(n_abc, n_acd),
            dihedral(n_abd, n_acd),
            dihedral(n_abc, n_bcd),
            dihedral(n_abd, n_bcd),
            dihedral(n_acd, n_bcd),
        ],
        axis=1,
    )
    return angles.min(axis=1), angles.max(axis=1)


def _dassi_aspect_ratio(points: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """Return ``sqrt(2/3) * longest_edge / minimum_altitude`` per tet."""
    cells = np.asarray(tets, dtype=np.int64)
    if cells.size == 0:
        return np.zeros(0, dtype=np.float64)
    v = points[cells]
    edge_vectors = np.stack(
        [
            v[:, 1] - v[:, 0],
            v[:, 2] - v[:, 0],
            v[:, 3] - v[:, 0],
            v[:, 2] - v[:, 1],
            v[:, 3] - v[:, 1],
            v[:, 3] - v[:, 2],
        ],
        axis=1,
    )
    longest = np.linalg.norm(edge_vectors, axis=2).max(axis=1)
    vol6 = np.abs(signed_volume6(points, cells))
    faces = (
        v[:, [1, 2, 3]],
        v[:, [0, 2, 3]],
        v[:, [0, 1, 3]],
        v[:, [0, 1, 2]],
    )
    face_areas = np.stack(
        [0.5 * np.linalg.norm(np.cross(face[:, 1] - face[:, 0], face[:, 2] - face[:, 0]), axis=1)
         for face in faces],
        axis=1,
    )
    min_height = np.full(cells.shape[0], np.inf, dtype=np.float64)
    valid_area = face_areas > 1e-30
    heights = np.divide(
        vol6[:, None],
        2.0 * face_areas,
        out=np.full_like(face_areas, np.inf),
        where=valid_area,
    )
    min_height = heights.min(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.sqrt(2.0 / 3.0) * longest / min_height
    return np.asarray(result, dtype=np.float64)


def _metric_summary(points: np.ndarray, tets: np.ndarray) -> dict[str, float | None]:
    quality = tet_shape_quality(points, tets)
    min_dih, max_dih = _dihedral_bounds(points, tets)
    aspect = _dassi_aspect_ratio(points, tets)
    return {
        "n_tets": int(len(tets)),
        "min_quality": _json_float(float(quality.min())) if quality.size else 0.0,
        "mean_quality": _json_float(float(quality.mean())) if quality.size else 0.0,
        "min_dihedral_deg": _json_float(float(min_dih.min())) if min_dih.size else 0.0,
        "max_dihedral_deg": _json_float(float(max_dih.max())) if max_dih.size else 0.0,
        "max_aspect_ratio": _json_float(float(aspect.max())) if aspect.size else 0.0,
    }


def _cavity_snapshot(
    points: np.ndarray,
    tets: np.ndarray,
    *,
    owner_tet_ids: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    cells = np.asarray(tets, dtype=np.int64)
    volumes = signed_volume6(points, cells)
    quality = tet_shape_quality(points, cells)
    min_dih, max_dih = _dihedral_bounds(points, cells)
    aspect = _dassi_aspect_ratio(points, cells)
    faces = boundary_face_keys(cells)
    signs = np.sign(volumes).astype(np.int8, copy=False)
    return {
        "tet_ids": [int(value) for value in owner_tet_ids] if owner_tet_ids is not None else None,
        "tets": cells.tolist(),
        "signed_volume6": _json_array(volumes),
        "signed_volume6_sign": [int(value) for value in signs.tolist()],
        "abs_signed_volume6_sum": _json_float(float(np.abs(volumes).sum())),
        "quality": _json_array(quality),
        "min_dihedral_deg_per_tet": _json_array(min_dih),
        "max_dihedral_deg_per_tet": _json_array(max_dih),
        "dassi_aspect_ratio": _json_array(aspect),
        "boundary_faces": [list(face) for face in sorted(faces)],
        "metrics": _metric_summary(points, cells),
    }


def _interior_edges(tets: np.ndarray) -> list[tuple[int, int]]:
    cells = np.asarray(tets, dtype=np.int64)
    if cells.size == 0:
        return []
    edge_map = _edge_to_tets_map(cells)
    boundary_edges = _boundary_edges_from_fmap(_face_map_vectorized(cells))
    return sorted(
        edge
        for edge, owners in edge_map.items()
        if len(owners) >= 3 and edge not in boundary_edges
    )


def _owner_ids(tets: np.ndarray, edge: tuple[int, int]) -> tuple[int, ...]:
    owners = _edge_to_tets_map(np.asarray(tets, dtype=np.int64)).get(edge, [])
    return tuple(sorted(int(value) for value in owners))


def _candidate_rows(
    before_tets: np.ndarray,
    after_tets: np.ndarray,
    owner_tet_ids: tuple[int, ...],
) -> np.ndarray | None:
    """Extract the candidate suffix produced by ``general_edge_removal``."""
    n_new = 2 * len(owner_tet_ids) - 4
    prefix_len = len(before_tets) - len(owner_tet_ids)
    if n_new <= 0 or prefix_len < 0 or after_tets.shape[0] != prefix_len + n_new:
        return None
    return np.asarray(after_tets[prefix_len:], dtype=np.int64).copy()


def _signed_volume_guard(
    before: np.ndarray,
    after: np.ndarray,
) -> tuple[bool, dict[str, Any]]:
    old_v = signed_volume6(np.zeros((0, 3)), np.zeros((0, 4), dtype=np.int64))
    del old_v
    # The points are deliberately supplied by the caller through the arrays'
    # already computed values below; this helper only compares recorded data.
    old_signs = np.sign(before).astype(np.int8)
    new_signs = np.sign(after).astype(np.int8)
    nonzero = bool(
        np.all(np.abs(before) > MIN_ABS_SIGNED_VOLUME6)
        and np.all(np.abs(after) > MIN_ABS_SIGNED_VOLUME6)
    )
    old_sum = float(np.abs(before).sum())
    new_sum = float(np.abs(after).sum())
    tiling_ok = abs(new_sum - old_sum) <= VOLUME_TILING_REL_TOL * max(old_sum, 1e-30)
    old_sign_set = sorted(int(value) for value in set(old_signs.tolist()))
    new_sign_set = sorted(int(value) for value in set(new_signs.tolist()))
    orientation_provable = len(old_sign_set) == 1 and old_sign_set[0] != 0
    orientation_ok = orientation_provable and new_sign_set == old_sign_set
    detail = {
        "nonzero": nonzero,
        "volume_tiling_ok": bool(tiling_ok),
        "orientation_provable": orientation_provable,
        "orientation_ok": bool(orientation_ok),
        "before_sign_set": old_sign_set,
        "after_sign_set": new_sign_set,
        "before_abs_sum": _json_float(old_sum),
        "after_abs_sum": _json_float(new_sum),
        "abs_sum_delta": _json_float(new_sum - old_sum),
    }
    return bool(nonzero and tiling_ok and orientation_ok), detail


def _criterion_improves(
    before: dict[str, float | None],
    after: dict[str, float | None],
    criterion: str,
) -> bool:
    if criterion == "angle":
        old_min = float(before["min_dihedral_deg"] or 0.0)
        new_min = float(after["min_dihedral_deg"] or 0.0)
        old_max = float(before["max_dihedral_deg"] or 0.0)
        new_max = float(after["max_dihedral_deg"] or 0.0)
        safe = new_min >= old_min - METRIC_TOL and new_max <= old_max + METRIC_TOL
        strict = new_min > old_min + METRIC_TOL or new_max < old_max - METRIC_TOL
        return bool(safe and strict)
    if criterion == "aspect":
        old_aspect = float(before["max_aspect_ratio"] or 0.0)
        new_aspect = float(after["max_aspect_ratio"] or 0.0)
        return bool(new_aspect <= old_aspect + METRIC_TOL and new_aspect < old_aspect - METRIC_TOL)
    raise ValueError(f"unsupported TET-LAZY-2 criterion: {criterion}")


def _sequence_improves(
    before: dict[str, float | None],
    after: dict[str, float | None],
    accepted_count: int,
) -> bool:
    if accepted_count == 0:
        return False
    old_q = float(before["min_quality"] or 0.0)
    new_q = float(after["min_quality"] or 0.0)
    old_min = float(before["min_dihedral_deg"] or 0.0)
    new_min = float(after["min_dihedral_deg"] or 0.0)
    old_max = float(before["max_dihedral_deg"] or 0.0)
    new_max = float(after["max_dihedral_deg"] or 0.0)
    old_aspect = float(before["max_aspect_ratio"] or 0.0)
    new_aspect = float(after["max_aspect_ratio"] or 0.0)
    safe = (
        new_q >= old_q - METRIC_TOL
        and new_min >= old_min - METRIC_TOL
        and new_max <= old_max + METRIC_TOL
        and new_aspect <= old_aspect + METRIC_TOL
    )
    strict = (
        new_q > old_q + METRIC_TOL
        or new_min > old_min + METRIC_TOL
        or new_max < old_max - METRIC_TOL
        or new_aspect < old_aspect - METRIC_TOL
    )
    return bool(safe and strict)


def run_lazy_flip_diagnostic(
    points: np.ndarray,
    tets: np.ndarray,
    *,
    n_surface_vertices: int | None = None,
    max_rounds: int = 2,
    max_edges: int | None = 128,
    max_no_progress: int = 1,
) -> dict[str, Any]:
    """Measure deterministic, serial TET-LAZY-2 candidates without editing input.

    ``max_edges`` caps the sorted interior-edge census per round.  ``None``
    means all edges; the bounded default keeps raw cavity evidence manageable.
    The inherited minimum-quality threshold is fixed at ``1e-4`` and is not a
    caller-tunable argument, so this diagnostic cannot silently relax it.
    """
    pts, input_tets = _validate_input(points, tets)
    if max_rounds < 1:
        raise ValueError("max_rounds must be >= 1")
    if max_edges is not None and max_edges < 1:
        raise ValueError("max_edges must be >= 1 or None")
    if max_no_progress < 1:
        raise ValueError("max_no_progress must be >= 1")
    if n_surface_vertices is not None and not 0 <= n_surface_vertices <= len(pts):
        raise ValueError("n_surface_vertices is outside points")

    input_points_digest = _digest_bytes(pts)
    input_tets_digest = _digest_bytes(input_tets)
    initial_boundary = boundary_face_keys(input_tets)
    baseline_metrics = _metric_summary(pts, input_tets)
    working = input_tets.copy()
    candidate_records: list[dict[str, Any]] = []
    attempted_edges: list[tuple[int, int]] = []
    no_progress: dict[tuple[int, int], int] = {}
    criteria_seen: list[str] = []

    for round_index in range(max_rounds):
        criterion = "angle" if round_index % 2 == 0 else "aspect"
        criteria_seen.append(criterion)
        round_accepted = 0
        edges = _interior_edges(working)
        if max_edges is not None:
            edges = edges[:max_edges]
        for edge in edges:
            if no_progress.get(edge, 0) >= max_no_progress:
                continue
            attempted_edges.append(edge)
            before_full = working.copy()
            owners = _owner_ids(before_full, edge)
            if len(owners) < 3:
                no_progress[edge] = no_progress.get(edge, 0) + 1
                continue
            before_local = before_full[np.asarray(owners, dtype=np.int64)]
            before_snapshot = _cavity_snapshot(
                pts,
                before_local,
                owner_tet_ids=owners,
            )
            proposal, info = general_edge_removal(
                pts,
                before_full,
                edge[0],
                edge[1],
                min_quality_improvement=MIN_QUALITY_IMPROVEMENT,
                exhaustive=False,
            )
            record: dict[str, Any] = {
                "round": int(round_index),
                "criterion": criterion,
                "edge": [int(edge[0]), int(edge[1])],
                "owner_tet_ids": [int(value) for value in owners],
                "proposal": {str(key): value for key, value in info.items()},
                "before": before_snapshot,
                "after": None,
                "accepted_into_simulated_sequence": False,
                "guard_reasons": [],
            }
            if proposal is None:
                record["guard_reasons"] = [str(info.get("reason", "proposal_rejected"))]
                candidate_records.append(record)
                no_progress[edge] = no_progress.get(edge, 0) + 1
                continue

            after_local = _candidate_rows(before_full, proposal, owners)
            if after_local is None:
                record["guard_reasons"] = ["candidate_suffix_unavailable"]
                candidate_records.append(record)
                no_progress[edge] = no_progress.get(edge, 0) + 1
                continue
            after_snapshot = _cavity_snapshot(pts, after_local)
            record["after"] = after_snapshot
            old_volumes = signed_volume6(pts, before_local)
            new_volumes = signed_volume6(pts, after_local)
            signed_ok, signed_detail = _signed_volume_guard(old_volumes, new_volumes)
            record["signed_volume_guard"] = signed_detail

            old_faces = boundary_face_keys(before_local)
            new_faces = boundary_face_keys(after_local)
            local_boundary_ok = old_faces == new_faces
            record["cavity_boundary_face_set"] = {
                "before": [list(face) for face in sorted(old_faces)],
                "after": [list(face) for face in sorted(new_faces)],
                "equal": bool(local_boundary_ok),
            }

            global_boundary = check_boundary_invariant(
                pts,
                before_full,
                pts,
                proposal,
                f"tet_lazy2_round{round_index}_edge{edge[0]}_{edge[1]}",
                log_only=True,
            )
            before_global_faces = boundary_face_keys(before_full)
            after_global_faces = boundary_face_keys(proposal)
            global_boundary_ok = bool(global_boundary.preserved and before_global_faces == after_global_faces)
            record["global_boundary"] = {
                "face_set_equal": bool(before_global_faces == after_global_faces),
                "face_set_digest_before": _face_digest(before_global_faces),
                "face_set_digest_after": _face_digest(after_global_faces),
                "face_count_before": int(len(before_global_faces)),
                "face_count_after": int(len(after_global_faces)),
                "area_equal": bool(global_boundary.area_equal),
                "preserved": global_boundary_ok,
            }
            criterion_ok = _criterion_improves(
                before_snapshot["metrics"],
                after_snapshot["metrics"],
                criterion,
            )
            record["criterion_improved"] = bool(criterion_ok)
            reasons: list[str] = []
            if not signed_ok:
                reasons.append("signed_volume_guard")
            if not local_boundary_ok:
                reasons.append("cavity_boundary_face_set")
            if not global_boundary_ok:
                reasons.append("global_boundary_invariant")
            if not criterion_ok:
                reasons.append("criterion_not_improved")
            record["guard_reasons"] = reasons
            if reasons:
                candidate_records.append(record)
                no_progress[edge] = no_progress.get(edge, 0) + 1
                continue

            working = proposal.copy()
            round_accepted += 1
            no_progress[edge] = 0
            record["accepted_into_simulated_sequence"] = True
            candidate_records.append(record)
        if round_accepted == 0:
            break

    final_metrics = _metric_summary(pts, working)
    sequence_improved = _sequence_improves(baseline_metrics, final_metrics, sum(
        1 for record in candidate_records if record["accepted_into_simulated_sequence"]
    ))
    sequence_rolled_back = not sequence_improved
    surface_digest = None
    if n_surface_vertices is not None:
        surface_digest = _digest_bytes(pts[:n_surface_vertices])
    return {
        "card": "TET-LAZY-2",
        "mode": "read-only-reversible-diagnostic",
        "production_route_touched": False,
        "parallel": False,
        "deterministic_order": "sorted interior edges; angle then aspect rounds; serial",
        "min_quality_improvement": MIN_QUALITY_IMPROVEMENT,
        "max_rounds": int(max_rounds),
        "max_edges": int(max_edges) if max_edges is not None else None,
        "max_no_progress": int(max_no_progress),
        "n_surface_vertices": int(n_surface_vertices) if n_surface_vertices is not None else None,
        "surface_vertex_digest": surface_digest,
        "initial_boundary_face_count": int(len(initial_boundary)),
        "initial_boundary_face_digest": _face_digest(initial_boundary),
        "baseline_metrics": baseline_metrics,
        "sequence_after_metrics": final_metrics,
        "criteria_seen": criteria_seen,
        "n_interior_edges_first_round": int(len(_interior_edges(input_tets))),
        "attempted_edges": [list(edge) for edge in attempted_edges],
        "n_candidate_records": int(len(candidate_records)),
        "n_accepted_candidates": int(sum(
            1 for record in candidate_records if record["accepted_into_simulated_sequence"]
        )),
        "sequence_improved": bool(sequence_improved),
        "sequence_decision": "would_accept" if sequence_improved else "rollback",
        "sequence_rolled_back": bool(sequence_rolled_back),
        "candidates": candidate_records,
        "input_unchanged": bool(
            _digest_bytes(pts) == input_points_digest
            and _digest_bytes(input_tets) == input_tets_digest
        ),
        "surface_vertices_moved": False,
        "input_points_digest": input_points_digest,
        "input_tets_digest": input_tets_digest,
    }
