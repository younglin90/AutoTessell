"""TET-SHAPE-2 -- boundary-pinned interior GSM/AMIPS smoothing.

This is the native-tet implementation of the interior-only part of Ni et al.
(2017).  The paper's boundary resampling and surface sliding are deliberately
not imported: only interior vertices may move and the input boundary is a
hard, bitwise lock.

For a tetrahedron with template edge length ``a_hat``, the GSM term is the
inverse-height equation from Ni et al. Eq. (8)::

    E_gsm = (a_hat**2 / 18) * sum_i |S_i|**2 / |V|**2
          = (a_hat**2 / 2) * sum_i 1 / h_i**2

The pass blends this term with the scale-free AMIPS shape energy.  The
template edge is frozen per tetrahedron for a pass; when no sizing target is
provided, the input tetrahedron's RMS edge length is used.  This keeps GSM
dimensionless without pushing a graded mesh toward one global size.

Every accepted vertex move is checked transactionally.  A cheap floating
signed-volume test can only reject a candidate; exact Shewchuk ``orient3d``
signs decide whether it is valid.  The whole pass is rolled back if any
boundary, orientation, or requested quality guard fails.  ``measure_only`` is
provided solely for offline A/B experiments: it returns the guarded candidate
even when the strict plan axes reject it, while reporting ``accepted=False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from core.generator.native_tet.boundary_invariant import check_boundary_invariant
from core.generator.native_tet.quality import tet_min_dihedral_deg, tet_shape_quality
from core.utils.logging import get_logger

log = get_logger(__name__)

_REF = np.array(
    [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.5, np.sqrt(3.0) / 2.0, 0.0],
        [0.5, np.sqrt(3.0) / 6.0, np.sqrt(2.0 / 3.0)],
    ],
    dtype=np.float64,
)
_REF_INV = np.linalg.inv(
    np.stack([_REF[1] - _REF[0], _REF[2] - _REF[0], _REF[3] - _REF[0]], axis=1)
)
_EDGE_PAIRS = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
_FACES_OPPOSITE = ((1, 2, 3), (0, 2, 3), (0, 1, 3), (0, 1, 2))
_BACKTRACK = 0.618
_MAX_BACKTRACK = 12
_EPS = 1e-30


@dataclass
class Shape2Report:
    """Offline and pipeline-facing before/after measurements."""

    n_tets: int = 0
    n_free_vertices: int = 0
    n_candidate_vertices: int = 0
    n_moved: int = 0
    n_backtracks: int = 0
    n_sweeps: int = 0
    max_displacement: float = 0.0
    amips_weight: float = 0.0
    gsm_weight: float = 0.0
    min_q_before: float = 0.0
    min_q_after: float = 0.0
    p10_q_before: float = 0.0
    p10_q_after: float = 0.0
    mean_q_before: float = 0.0
    mean_q_after: float = 0.0
    n_q_below_001_before: int = 0
    n_q_below_001_after: int = 0
    sigma_dihedral_before: float = 0.0
    sigma_dihedral_after: float = 0.0
    min_dihedral_before: float = 0.0
    min_dihedral_after: float = 0.0
    max_skew_before: float = 0.0
    max_skew_after: float = 0.0
    blend_energy_before: float = 0.0
    blend_energy_after: float = 0.0
    boundary_preserved: bool = True
    boundary_vertices_bitwise_equal: bool = True
    exact_orientation_preserved: bool = True
    strict_axes_pass: bool = False
    accepted: bool = False
    reject_reason: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        out = {key: value for key, value in self.__dict__.items() if key != "extra"}
        out.update(self.extra)
        return out


def _signed_volume6(pts: NDArray[Any], tets: NDArray[Any]) -> NDArray[Any]:
    corners = np.asarray(pts, dtype=np.float64)[np.asarray(tets, dtype=np.int64)]
    return np.einsum(
        "ij,ij->i",
        corners[:, 1] - corners[:, 0],
        np.cross(corners[:, 2] - corners[:, 0], corners[:, 3] - corners[:, 0]),
    )


def _exact_orientation_signs(pts: NDArray[Any], tets: NDArray[Any]) -> NDArray[Any]:
    """Return exact Shewchuk orientation signs for all tetrahedra."""
    from core.utils._shewchuk import orient3d

    if orient3d is None:
        raise RuntimeError("Shewchuk orient3d is unavailable")
    corners = np.asarray(tets, dtype=np.int64)
    signs = np.empty(corners.shape[0], dtype=np.int64)
    for index, tet in enumerate(corners):
        signs[index] = int(orient3d(pts[tet[0]], pts[tet[1]], pts[tet[2]], pts[tet[3]]))
    return signs


def _exact_orientation_subset(
    pts: NDArray[Any], tets: NDArray[Any], indices: NDArray[Any]
) -> NDArray[Any]:
    return _exact_orientation_signs(pts, np.asarray(tets, dtype=np.int64)[indices])


def _boundary_vertex_mask(tets: NDArray[Any], n_points: int) -> NDArray[Any]:
    """Find boundary vertices from the tetrahedral face incidence only."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(n_points, dtype=bool)
    faces = np.concatenate(
        [tets[:, [0, 1, 2]], tets[:, [0, 1, 3]], tets[:, [0, 2, 3]], tets[:, [1, 2, 3]]],
        axis=0,
    )
    canonical = np.sort(faces, axis=1)
    _, first, counts = np.unique(canonical, axis=0, return_index=True, return_counts=True)
    boundary_faces = canonical[first[counts == 1]]
    mask = np.zeros(n_points, dtype=bool)
    if boundary_faces.size:
        mask[np.unique(boundary_faces)] = True
    return mask


def _vertex_incidence(
    tets: NDArray[Any], n_points: int
) -> tuple[NDArray[Any], NDArray[Any], NDArray[Any]]:
    flat_vertices = np.asarray(tets, dtype=np.int64).reshape(-1)
    flat_tets = np.repeat(np.arange(tets.shape[0], dtype=np.int64), 4)
    flat_slots = np.tile(np.arange(4, dtype=np.int64), tets.shape[0])
    order = np.lexsort((flat_slots, flat_tets, flat_vertices))
    counts = np.bincount(flat_vertices[order], minlength=n_points)
    offsets = np.zeros(n_points + 1, dtype=np.int64)
    np.cumsum(counts, out=offsets[1:])
    return offsets, flat_tets[order], flat_slots[order]


def _edge_rms_squared(corners: NDArray[Any]) -> NDArray[Any]:
    result = np.zeros(corners.shape[0], dtype=np.float64)
    for first, second in _EDGE_PAIRS:
        edge = corners[:, second] - corners[:, first]
        result += np.einsum("ij,ij->i", edge, edge)
    return result / 6.0


def _template_edge_squared(
    pts: NDArray[Any], tets: NDArray[Any], template_edge_length: float | None
) -> NDArray[Any]:
    if template_edge_length is not None:
        value = float(template_edge_length)
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError("template_edge_length must be finite and positive")
        return np.full(tets.shape[0], value * value, dtype=np.float64)
    corners = np.asarray(pts, dtype=np.float64)[np.asarray(tets, dtype=np.int64)]
    return np.maximum(_edge_rms_squared(corners), _EPS)


def _area_squared_and_gradients(corners: NDArray[Any]) -> tuple[NDArray[Any], NDArray[Any]]:
    """Return sum face-area-squares and its gradient per tet/vertex."""
    n_tets = corners.shape[0]
    area_sum = np.zeros(n_tets, dtype=np.float64)
    gradients = np.zeros((n_tets, 4, 3), dtype=np.float64)
    for ia, ib, ic in _FACES_OPPOSITE:
        u = corners[:, ib] - corners[:, ia]
        v = corners[:, ic] - corners[:, ia]
        cross_uv = np.cross(u, v)
        area_sum += 0.25 * np.einsum("ij,ij->i", cross_uv, cross_uv)
        grad_b = 0.5 * np.cross(v, cross_uv)
        grad_c = 0.5 * np.cross(cross_uv, u)
        gradients[:, ib] += grad_b
        gradients[:, ic] += grad_c
        gradients[:, ia] -= grad_b + grad_c
    return area_sum, gradients


def _volume_and_gradients(corners: NDArray[Any]) -> tuple[NDArray[Any], NDArray[Any]]:
    a, b, c, d = (corners[:, index] for index in range(4))
    volume6 = np.einsum("ij,ij->i", b - a, np.cross(c - a, d - a))
    gradients = np.zeros((corners.shape[0], 4, 3), dtype=np.float64)
    gradients[:, 1] = np.cross(c - a, d - a) / 6.0
    gradients[:, 2] = np.cross(d - a, b - a) / 6.0
    gradients[:, 3] = np.cross(b - a, c - a) / 6.0
    gradients[:, 0] = -gradients[:, 1] - gradients[:, 2] - gradients[:, 3]
    return volume6 / 6.0, gradients


def gsm_score(
    pts: NDArray[Any], tets: NDArray[Any], template_edge_squared: NDArray[Any]
) -> NDArray[Any]:
    """Evaluate Ni et al. Eq. (8), with one frozen template scale per tet."""
    corners = np.asarray(pts, dtype=np.float64)[np.asarray(tets, dtype=np.int64)]
    area_sum, _ = _area_squared_and_gradients(corners)
    volume, _ = _volume_and_gradients(corners)
    safe = np.abs(volume) > _EPS
    score = np.full(corners.shape[0], np.inf, dtype=np.float64)
    score[safe] = (
        template_edge_squared[safe] / 18.0 * area_sum[safe] / (volume[safe] * volume[safe])
    )
    return score


def _amips_score_and_gradient(
    corners: NDArray[Any], local_slots: NDArray[Any]
) -> tuple[NDArray[Any], NDArray[Any]]:
    """Scale-free AMIPS ``tr(F.T F)/|det(F)|^(2/3)`` and d/d(vertex)."""
    a, b, c, d = (corners[:, index] for index in range(4))
    jacobian = np.stack([b - a, c - a, d - a], axis=2)
    F = jacobian @ _REF_INV
    det = np.linalg.det(F)
    abs_det = np.abs(det)
    trace = np.einsum("...ij,...ij->...", F, F)
    score = np.full(corners.shape[0], np.inf, dtype=np.float64)
    safe = abs_det > _EPS
    score[safe] = trace[safe] / np.power(abs_det[safe], 2.0 / 3.0)

    gradient = np.zeros((corners.shape[0], 3), dtype=np.float64)
    if safe.any():
        safe_F = F[safe]
        safe_det = det[safe]
        safe_abs_det = abs_det[safe]
        safe_trace = trace[safe]
        inverse = np.linalg.inv(safe_F)
        cofactor = np.swapaxes(inverse, 1, 2) * safe_det[:, None, None]
        dD_dF = (
            2.0 * safe_F / np.power(safe_abs_det, 2.0 / 3.0)[:, None, None]
            - ((2.0 / 3.0) * safe_trace * np.sign(safe_det) / np.power(safe_abs_det, 5.0 / 3.0))[
                :, None, None
            ]
            * cofactor
        )
        dD_dJ = np.einsum("...dc,kc->...dk", dD_dF, _REF_INV)
        slots = local_slots[safe]
        selected = np.zeros_like(dD_dJ[:, :, 0])
        for slot in range(4):
            selected[slots == slot] = {
                0: -dD_dJ[:, :, 0] - dD_dJ[:, :, 1] - dD_dJ[:, :, 2],
                1: dD_dJ[:, :, 0],
                2: dD_dJ[:, :, 1],
                3: dD_dJ[:, :, 2],
            }[slot][slots == slot]
        gradient[safe] = selected
    return score, gradient


def _gsm_score_and_gradient(
    corners: NDArray[Any],
    local_slots: NDArray[Any],
    template_edge_squared: NDArray[Any],
) -> tuple[NDArray[Any], NDArray[Any]]:
    area_sum, area_grad = _area_squared_and_gradients(corners)
    volume, volume_grad = _volume_and_gradients(corners)
    safe = np.abs(volume) > _EPS
    score = np.full(corners.shape[0], np.inf, dtype=np.float64)
    gradient = np.zeros((corners.shape[0], 3), dtype=np.float64)
    if safe.any():
        v = volume[safe]
        s = area_sum[safe]
        coeff = template_edge_squared[safe] / 18.0
        score[safe] = coeff * s / (v * v)
        d_score = coeff[:, None, None] * (
            area_grad[safe] / (v * v)[:, None, None]
            - 2.0 * s[:, None, None] * volume_grad[safe] / (v * v * v)[:, None, None]
        )
        slots = local_slots[safe]
        gradient[safe] = d_score[np.arange(slots.size), slots]
    return score, gradient


def _blend_local_energy_and_gradient(
    pts: NDArray[Any],
    tets: NDArray[Any],
    ring: NDArray[Any],
    slots: NDArray[Any],
    template_edge_squared: NDArray[Any],
    gsm_weight: float,
) -> tuple[float, NDArray[Any]]:
    corners = pts[np.asarray(tets, dtype=np.int64)[ring]]
    amips, amips_grad = _amips_score_and_gradient(corners, slots)
    gsm, gsm_grad = _gsm_score_and_gradient(corners, slots, template_edge_squared[ring])
    scores = (1.0 - gsm_weight) * amips + gsm_weight * gsm
    gradients = (1.0 - gsm_weight) * amips_grad + gsm_weight * gsm_grad
    finite = np.isfinite(scores) & np.isfinite(gradients).all(axis=1)
    if not finite.any():
        return float("inf"), np.zeros(3, dtype=np.float64)
    if not finite.all():
        return float("inf"), np.zeros(3, dtype=np.float64)
    return float(scores.sum()), np.asarray(gradients.sum(axis=0), dtype=np.float64)


def _max_skew_proxy(pts: NDArray[Any], tets: NDArray[Any]) -> float:
    """Evaluator-compatible max centroid-to-face projection skew proxy."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return 0.0
    faces = np.concatenate(
        [tets[:, [0, 1, 2]], tets[:, [0, 1, 3]], tets[:, [0, 2, 3]], tets[:, [1, 2, 3]]], axis=0
    )
    owners = np.tile(np.arange(tets.shape[0], dtype=np.int64), 4)
    canonical = np.sort(faces, axis=1)
    unique, inverse, counts = np.unique(canonical, axis=0, return_inverse=True, return_counts=True)
    grouped = owners[np.argsort(inverse, kind="stable")]
    starts = np.zeros(counts.shape[0], dtype=np.int64)
    starts[1:] = np.cumsum(counts)[:-1]
    centres = np.asarray(pts, dtype=np.float64)[tets].mean(axis=1)
    face_centres = np.asarray(pts, dtype=np.float64)[unique].mean(axis=1)
    worst = 0.0
    for wanted_count in (1, 2):
        indices = np.flatnonzero(counts == wanted_count)
        for face_index in indices:
            own = centres[grouped[starts[face_index]]]
            face = face_centres[face_index]
            if wanted_count == 2:
                other = centres[grouped[starts[face_index] + 1]]
                direction = other - own
                denominator = float(np.linalg.norm(direction))
                if denominator <= _EPS:
                    continue
                projection = (
                    own
                    + float(np.dot(face - own, direction)) / (denominator * denominator) * direction
                )
                worst = max(worst, float(np.linalg.norm(face - projection) / denominator))
            else:
                tri = np.asarray(pts, dtype=np.float64)[unique[face_index]]
                normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
                normal_norm = float(np.linalg.norm(normal))
                if normal_norm <= _EPS:
                    continue
                signed_distance = float(np.dot(face - own, normal / normal_norm))
                denominator = max(abs(signed_distance), _EPS)
                projection = own + signed_distance * normal / normal_norm
                worst = max(worst, float(np.linalg.norm(face - projection) / denominator))
    return worst


def _metrics(pts: NDArray[Any], tets: NDArray[Any]) -> dict[str, float | int]:
    quality = np.asarray(tet_shape_quality(pts, tets), dtype=np.float64)
    dihedral = np.asarray(tet_min_dihedral_deg(pts, tets), dtype=np.float64)
    if quality.size == 0:
        return {
            "min_q": 0.0,
            "p10_q": 0.0,
            "mean_q": 0.0,
            "n_q_below_001": 0,
            "sigma_dihedral": 0.0,
            "min_dihedral": 0.0,
            "max_skew": 0.0,
        }
    return {
        "min_q": float(np.min(quality)),
        "p10_q": float(np.percentile(quality, 10.0)),
        "mean_q": float(np.mean(quality)),
        "n_q_below_001": int(np.count_nonzero(quality < 0.01)),
        "sigma_dihedral": float(np.std(dihedral)),
        "min_dihedral": float(np.min(dihedral)),
        "max_skew": float(_max_skew_proxy(pts, tets)),
    }


def _set_report_metrics(report: Shape2Report, prefix: str, values: dict[str, float | int]) -> None:
    for key, value in values.items():
        setattr(report, f"{key}_{prefix}", value)


def _strict_axes_pass(report: Shape2Report, tolerance: float) -> tuple[bool, list[str]]:
    scale = max(abs(report.min_q_before), abs(report.p10_q_before), 1.0)
    q_tol = tolerance * scale
    reasons: list[str] = []
    if not report.sigma_dihedral_after < report.sigma_dihedral_before - tolerance:
        reasons.append("sigma_dihedral_not_decreased")
    if not report.p10_q_after > report.p10_q_before + q_tol:
        reasons.append("p10_q_not_increased")
    if report.mean_q_after < report.mean_q_before - q_tol:
        reasons.append("mean_q_regressed")
    if report.n_q_below_001_after > report.n_q_below_001_before:
        reasons.append("q_below_001_increased")
    if report.min_dihedral_after < report.min_dihedral_before - tolerance:
        reasons.append("min_dihedral_regressed")
    if report.max_skew_after > report.max_skew_before + tolerance:
        reasons.append("max_skew_regressed")
    if report.min_q_after < report.min_q_before - q_tol:
        reasons.append("min_q_regressed")
    return not reasons, reasons


def run_shape2_pass(
    pts: NDArray[Any],
    tets: NDArray[Any],
    *,
    locked_vertex_ids: NDArray[Any] | None = None,
    n_surface_vertices: int | None = None,
    n_sweeps: int = 3,
    gsm_weight: float = 0.35,
    template_edge_length: float | None = None,
    step_cap_frac: float = 0.01,
    max_backtrack: int = _MAX_BACKTRACK,
    metric_tolerance: float = 1e-12,
    measure_only: bool = False,
) -> tuple[NDArray[Any], Shape2Report]:
    """Run a deterministic, transactional TET-SHAPE-2 pass.

    ``measure_only=True`` is intentionally not a production mode; it exposes
    the candidate for offline A/B reporting when strict quality axes reject it.
    Production callers should use the default, which returns the original
    points on any failed guard.
    """
    points = np.asarray(pts, dtype=np.float64)
    cells = np.ascontiguousarray(np.asarray(tets, dtype=np.int64))
    report = Shape2Report(
        n_tets=int(cells.shape[0]),
        n_sweeps=max(0, int(n_sweeps)),
        gsm_weight=float(gsm_weight),
        amips_weight=float(1.0 - gsm_weight),
    )
    if points.ndim != 2 or points.shape[1:] != (3,) or cells.ndim != 2 or cells.shape[1:] != (4,):
        report.reject_reason = "invalid_shape"
        return points, report
    if not 0.0 < float(gsm_weight) < 1.0:
        report.reject_reason = "gsm_weight_out_of_range"
        return points, report
    if cells.shape[0] == 0:
        report.reject_reason = "empty"
        return points, report

    template_squared = _template_edge_squared(points, cells, template_edge_length)
    before_metrics = _metrics(points, cells)
    _set_report_metrics(report, "before", before_metrics)
    report.blend_energy_before = float(
        np.sum(
            (1.0 - gsm_weight)
            * _amips_score_and_gradient(points[cells], np.zeros(cells.shape[0], dtype=np.int64))[0]
            + gsm_weight * gsm_score(points, cells, template_squared)
        )
    )

    locked = _boundary_vertex_mask(cells, points.shape[0])
    if locked_vertex_ids is not None:
        ids = np.asarray(locked_vertex_ids, dtype=np.int64).reshape(-1)
        locked[ids[(ids >= 0) & (ids < points.shape[0])]] = True
    if n_surface_vertices is not None and int(n_surface_vertices) > 0:
        locked[: min(int(n_surface_vertices), points.shape[0])] = True
    free = ~locked
    report.n_free_vertices = int(np.count_nonzero(free))
    if report.n_free_vertices == 0:
        report.reject_reason = "no_free_vertices"
        return points, report

    offsets, incident_tets, incident_slots = _vertex_incidence(cells, points.shape[0])
    base_signs = _exact_orientation_signs(points, cells)
    edge_lengths = np.concatenate(
        [
            np.linalg.norm(points[cells[:, second]] - points[cells[:, first]], axis=1)
            for first, second in _EDGE_PAIRS
        ]
    )
    step_cap = float(step_cap_frac) * float(np.mean(edge_lengths))
    if not np.isfinite(step_cap) or step_cap <= 0.0:
        report.reject_reason = "invalid_step_cap"
        return points, report

    work = points.copy()
    quality_work = np.asarray(tet_shape_quality(work, cells), dtype=np.float64)
    p10_work = float(np.percentile(quality_work, 10.0))
    n_q_below_work = int(np.count_nonzero(quality_work < 0.01))
    n_moved = 0
    n_backtracks = 0
    max_displacement = 0.0
    for _ in range(max(0, int(n_sweeps))):
        candidates: list[tuple[float, int]] = []
        for vertex in np.flatnonzero(free):
            lo, hi = int(offsets[vertex]), int(offsets[vertex + 1])
            ring = incident_tets[lo:hi]
            if ring.size == 0:
                continue
            local_q = tet_shape_quality(work, cells[ring])
            if local_q.size and np.isfinite(local_q).all():
                candidates.append((float(np.min(local_q)), int(vertex)))
        if not candidates:
            break
        candidates.sort(key=lambda item: (item[0], item[1]))
        report.n_candidate_vertices = max(report.n_candidate_vertices, len(candidates))
        moved_this_sweep = 0
        for _, vertex in candidates:
            lo, hi = int(offsets[vertex]), int(offsets[vertex + 1])
            ring = incident_tets[lo:hi]
            slots = incident_slots[lo:hi]
            if np.any(base_signs[ring] == 0):
                continue
            old_energy, gradient = _blend_local_energy_and_gradient(
                work, cells, ring, slots, template_squared, float(gsm_weight)
            )
            norm = float(np.linalg.norm(gradient))
            if not np.isfinite(old_energy) or not np.isfinite(norm) or norm <= _EPS:
                continue
            direction = -gradient / norm
            saved = work[vertex].copy()
            tau = step_cap
            accepted = False
            for _ in range(max(1, int(max_backtrack))):
                candidate = saved + tau * direction
                if not np.isfinite(candidate).all():
                    tau *= _BACKTRACK
                    n_backtracks += 1
                    continue
                work[vertex] = candidate
                ring_cells = cells[ring]
                float_signs = np.sign(_signed_volume6(work, ring_cells))
                expected_float_signs = np.sign(_signed_volume6(points, ring_cells))
                if np.array_equal(float_signs, expected_float_signs):
                    new_energy, _ = _blend_local_energy_and_gradient(
                        work, cells, ring, slots, template_squared, float(gsm_weight)
                    )
                    exact = _exact_orientation_subset(work, cells, ring)
                    quality_candidate = np.asarray(tet_shape_quality(work, cells), dtype=np.float64)
                    p10_candidate = float(np.percentile(quality_candidate, 10.0))
                    n_q_below_candidate = int(np.count_nonzero(quality_candidate < 0.01))
                    if (
                        np.array_equal(exact, base_signs[ring])
                        and np.isfinite(new_energy)
                        and new_energy < old_energy - 1e-13 * max(1.0, abs(old_energy))
                        and p10_candidate >= p10_work - float(metric_tolerance)
                        and n_q_below_candidate <= n_q_below_work
                    ):
                        accepted = True
                        quality_work = quality_candidate
                        p10_work = p10_candidate
                        n_q_below_work = n_q_below_candidate
                        moved_this_sweep += 1
                        n_moved += 1
                        max_displacement = max(
                            max_displacement,
                            float(np.linalg.norm(candidate - saved)),
                        )
                        break
                work[vertex] = saved
                tau *= _BACKTRACK
                n_backtracks += 1
            if not accepted:
                work[vertex] = saved
        if moved_this_sweep == 0:
            break

    report.n_moved = int(n_moved)
    report.n_backtracks = int(n_backtracks)
    report.max_displacement = float(max_displacement)
    if n_moved == 0:
        report.reject_reason = "no_move_accepted"
        return points, report

    after_metrics = _metrics(work, cells)
    _set_report_metrics(report, "after", after_metrics)
    report.blend_energy_after = float(
        np.sum(
            (1.0 - gsm_weight)
            * _amips_score_and_gradient(work[cells], np.zeros(cells.shape[0], dtype=np.int64))[0]
            + gsm_weight * gsm_score(work, cells, template_squared)
        )
    )
    report.boundary_vertices_bitwise_equal = bool(np.array_equal(work[locked], points[locked]))
    boundary = check_boundary_invariant(
        points, cells, work, cells, "native_tet_shape2", log_only=True
    )
    report.boundary_preserved = bool(boundary.preserved)
    final_signs = _exact_orientation_signs(work, cells)
    report.exact_orientation_preserved = bool(np.array_equal(final_signs, base_signs))
    report.strict_axes_pass, axis_reasons = _strict_axes_pass(report, float(metric_tolerance))

    reasons: list[str] = []
    if not report.boundary_vertices_bitwise_equal:
        reasons.append("boundary_vertex_moved")
    if not report.boundary_preserved:
        reasons.append("boundary_invariant")
    if not report.exact_orientation_preserved:
        reasons.append("orientation_changed")
    if not report.strict_axes_pass:
        reasons.extend(axis_reasons)
    report.reject_reason = "+".join(dict.fromkeys(reasons))
    report.accepted = not reasons
    if report.accepted or measure_only:
        return work, report
    log.info("native_tet_shape2_reverted", reason=report.reject_reason, n_moved=report.n_moved)
    return points, report
