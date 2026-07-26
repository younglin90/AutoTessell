"""TET-FLOW-2 -- penalized active-set interior smoothing (Leng et al. 2013).

Phase 2 opening card of
``docs/references/literature/native_tet/native_tet_literature_integrated_development_plan_2026-07-23.md``
(section "Phase 2 -- Smoothing/flip upgrade"), the cheapest [S] card of that
phase and the one the plan's own decision tree says to run first.

Literature basis (``docs/references/literature/native_tet/leng2013_geometric_flow.md``,
FULL_READ 16/16, DOI ``10.1016/j.cad.2013.05.004``), Eqs. 3.13-3.16:

    E = sum_{eta in T_q} (Qbar_eta - q)^p ,   Qbar = 1/Q in [1, inf)
    T_q = { eta : Q_eta <= 1/q }  with  p = 4,  q = 1/0.9

i.e. only tets whose volume-to-length quality ``Q <= 0.9`` are penalized, and
``p = 4`` punishes the worst ones hardest.  Minimization is Gauss-Seidel style,
vertex by vertex, along the negative first variation, with

    - the search direction projected per vertex class (interior -> R^3;
      surface/curve/fixed -> zero here, because boundary motion is
      ``TET-FLOW-1``'s separate card and is forbidden by Governing invariant 1
      without an exact re-projection step),
    - a line search on the step so that the *worst local quality strictly
      improves* (the paper's acceptance rule),
    - the inversion guard of Remark 3.1: ``tau <- 0.618 * tau`` and retry until
      no incident tet inverts,
    - the paper's step control: per-vertex displacement capped at 1% of the
      average edge length,
    - the active set recomputed after every accepted vertex move.

Differences from the paper, deliberate and recorded:

    - ``Q`` here is the smooth volume-to-length-RMS ratio
      ``6*sqrt(2) * |V| / l_rms^3`` (regular tet -> 1).  The engine's canonical
      ``quality.tet_shape_quality`` uses ``e_max`` in the denominator, which is
      not differentiable; the RMS form is the standard volume-length measure
      (Klingner & Shewchuk / Leng) and admits an exact analytic gradient.  The
      canonical ``e_max`` quality is still reported before/after so the number
      is comparable with every other native_tet card.
    - Inversion is decided by the *exact* Shewchuk ``orient3d`` predicate, not
      by a floating-point signed volume: a move is accepted only if every
      incident tet keeps its exact pre-move orientation sign.
    - Vertices whose ring contains an exactly degenerate tet (``orient3d == 0``)
      are skipped entirely.  Restoring a zero-volume tet is a topology problem
      (FSL / insertion cards), not a smoothing problem, and "repairing" it by
      picking an arbitrary sign would silently re-orient the local tiling.

Invariant compliance (plan section 4): moves no boundary vertex, changes no
cell count, deterministic (fixed traversal order, no randomness).  Every pass
is transactional -- ``pts`` is never mutated in place; a candidate array is
returned only after the whole-pass guards (global min-quality monotonicity,
bitwise-unchanged boundary vertex coordinates, ``check_boundary_invariant``)
all pass, otherwise the original array is returned unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.generator.native_tet.boundary_invariant import check_boundary_invariant
from core.utils.logging import get_logger

log = get_logger(__name__)

# Leng 2013 Eq. 3.14 parameters.
_P_EXP = 4
_Q_THRESH = 0.9
# Remark 3.1 backtracking factor and the section "Step control" 1% cap.
_BACKTRACK = 0.618
_STEP_CAP_FRAC = 0.01
_MAX_BACKTRACK = 12
# Regular-tet normalizer for the volume-to-length-RMS quality.
_VL_NORM = 6.0 * np.sqrt(2.0)
# Qbar = 1/Q is clamped only to keep the *weight* finite; the descent direction
# is unit-normalized anyway, so this never changes which way a vertex moves.
_Q_FLOOR = 1e-12

_EDGE_PAIRS = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))


@dataclass
class Flow2Report:
    """Measured before/after record for one ``TET-FLOW-2`` pass."""

    n_tets: int = 0
    n_free_vertices: int = 0
    n_candidate_vertices: int = 0
    n_moved: int = 0
    n_skipped_degenerate: int = 0
    n_backtracks: int = 0
    n_sweeps: int = 0
    max_displacement: float = 0.0
    energy_before: float = 0.0
    energy_after: float = 0.0
    n_active_before: int = 0
    n_active_after: int = 0
    min_q_vl_before: float = 0.0
    min_q_vl_after: float = 0.0
    mean_q_vl_before: float = 0.0
    mean_q_vl_after: float = 0.0
    min_q_canon_before: float = 0.0
    min_q_canon_after: float = 0.0
    mean_q_canon_before: float = 0.0
    mean_q_canon_after: float = 0.0
    n_sliver_before: int = 0
    n_sliver_after: int = 0
    boundary_preserved: bool = True
    boundary_vertices_bitwise_equal: bool = True
    accepted: bool = False
    reject_reason: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        out = {k: v for k, v in self.__dict__.items() if k != "extra"}
        out.update(self.extra)
        return out


# --------------------------------------------------------------------------
# quality + energy
# --------------------------------------------------------------------------
def tet_volume_length_quality(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """Smooth volume-to-length-RMS quality, ``6*sqrt(2)*|V| / l_rms^3``.

    Regular tetrahedron -> 1.0, degenerate -> 0.0.  Unlike the engine's
    ``e_max``-based ``tet_shape_quality`` this is differentiable everywhere the
    tet is non-degenerate, which is what the Leng energy needs.
    """
    tets = np.asarray(tets, dtype=np.int64)
    pts = np.asarray(pts, dtype=np.float64)
    if tets.size == 0:
        return np.zeros(0, dtype=np.float64)
    v = pts[tets]
    vol6 = np.einsum(
        "ij,ij->i",
        v[:, 1] - v[:, 0],
        np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
    )
    l2sum = np.zeros(tets.shape[0], dtype=np.float64)
    for i, j in _EDGE_PAIRS:
        d = v[:, j] - v[:, i]
        l2sum += np.einsum("ij,ij->i", d, d)
    lrms2 = l2sum / 6.0
    denom = lrms2 * np.sqrt(lrms2)  # l_rms^3
    q = np.zeros(tets.shape[0], dtype=np.float64)
    safe = denom > 1e-300
    q[safe] = _VL_NORM * (np.abs(vol6[safe]) / 6.0) / denom[safe]
    return q


def penalized_energy(q: np.ndarray, *, p: int = _P_EXP, q_thresh: float = _Q_THRESH) -> float:
    """Leng Eq. 3.14 energy over the active set ``{Q <= q_thresh}``."""
    q = np.asarray(q, dtype=np.float64)
    if q.size == 0:
        return 0.0
    active = q <= q_thresh
    if not active.any():
        return 0.0
    qa = np.maximum(q[active], _Q_FLOOR)
    return float(np.sum((1.0 / qa - 1.0 / q_thresh) ** p))


# Each row is an EVEN permutation of (0,1,2,3) that puts slot k first, so the
# rotated tet's signed volume equals the original tet's signed volume.
# Parities (inversion counts): 0, 2, 2, 4 -- all even; asserted in the tests.
_ROTATE_TO_FRONT = np.array(
    [
        [0, 1, 2, 3],
        [1, 0, 3, 2],
        [2, 0, 1, 3],
        [3, 0, 2, 1],
    ],
    dtype=np.int64,
)


def _quality_grad_wrt_vertex(corners: np.ndarray, local_idx: np.ndarray) -> np.ndarray:
    """d(Q_vl)/d(x_v) for a batch of tets, ``local_idx`` = v's slot in each tet.

    ``corners`` is ``(m, 4, 3)``.  ``Q_vl = C * |V| / l_rms^3`` with
    ``C = 6*sqrt(2)``; ``|V|`` is differentiated as ``sigma * V_signed`` with
    ``sigma = sign(V_signed)``, which is exact away from ``V == 0`` -- and
    ``V == 0`` tets are excluded by the caller's exact-``orient3d`` screen.
    """
    m = int(corners.shape[0])
    rows = np.arange(m)
    order = _ROTATE_TO_FRONT[local_idx]
    c = corners[rows[:, None], order]  # (m, 4, 3); the differentiated vertex is c[:, 0]
    a, b, cc, d = c[:, 0], c[:, 1], c[:, 2], c[:, 3]

    vol6_signed = np.einsum("ij,ij->i", b - a, np.cross(cc - a, d - a))
    # d(6V)/da = -((cc - b) x (d - b))
    grad_vol6 = -np.cross(cc - b, d - b)
    sigma = np.where(vol6_signed >= 0.0, 1.0, -1.0)
    grad_absvol = sigma[:, None] * grad_vol6 / 6.0

    l2sum = np.zeros(m, dtype=np.float64)
    for i, j in _EDGE_PAIRS:
        e = c[:, j] - c[:, i]
        l2sum += np.einsum("ij,ij->i", e, e)
    lrms2 = l2sum / 6.0
    # d(l_rms^2)/da = (1/3) * (3a - b - cc - d)
    grad_lrms2 = (3.0 * a - b - cc - d) / 3.0

    lrms = np.sqrt(np.maximum(lrms2, 1e-300))
    lrms3 = lrms2 * lrms
    absvol = np.abs(vol6_signed) / 6.0
    # d(l_rms^3)/da = 1.5 * l_rms * d(l_rms^2)/da
    grad_lrms3 = 1.5 * lrms[:, None] * grad_lrms2

    return _VL_NORM * (
        grad_absvol / lrms3[:, None]
        - (absvol / (lrms3 * lrms3))[:, None] * grad_lrms3
    )


# --------------------------------------------------------------------------
# topology helpers
# --------------------------------------------------------------------------
def _vertex_incidence(tets: np.ndarray, n_pts: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """CSR-style vertex -> (tet index, local slot) incidence, deterministic."""
    tets = np.asarray(tets, dtype=np.int64)
    n_t = tets.shape[0]
    flat_v = tets.reshape(-1)
    flat_t = np.repeat(np.arange(n_t, dtype=np.int64), 4)
    flat_s = np.tile(np.arange(4, dtype=np.int64), n_t)
    order = np.lexsort((flat_s, flat_t, flat_v))
    v_sorted = flat_v[order]
    counts = np.bincount(v_sorted, minlength=n_pts)
    offsets = np.zeros(n_pts + 1, dtype=np.int64)
    np.cumsum(counts, out=offsets[1:])
    return offsets, flat_t[order], flat_s[order]


def _boundary_vertex_mask(tets: np.ndarray, n_pts: int) -> np.ndarray:
    from core.generator.native_tet.near_wall import boundary_face_keys

    mask = np.zeros(n_pts, dtype=bool)
    keys = boundary_face_keys(np.asarray(tets, dtype=np.int64))
    if keys:
        idx = np.asarray(sorted(keys), dtype=np.int64).reshape(-1)
        idx = idx[(idx >= 0) & (idx < n_pts)]
        mask[idx] = True
    return mask


def _orient3d_signs(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """Exact Shewchuk ``orient3d`` sign per tet (-1 / 0 / +1)."""
    from core.utils._shewchuk import orient3d

    if orient3d is None:
        raise RuntimeError("Shewchuk orient3d is unavailable")
    tets = np.asarray(tets, dtype=np.int64)
    out = np.zeros(tets.shape[0], dtype=np.int64)
    for i in range(tets.shape[0]):
        t = tets[i]
        out[i] = int(orient3d(pts[t[0]], pts[t[1]], pts[t[2]], pts[t[3]]))
    return out


def _orient3d_signs_subset(pts: np.ndarray, tets: np.ndarray, idx: np.ndarray) -> np.ndarray:
    from core.utils._shewchuk import orient3d

    if orient3d is None:
        raise RuntimeError("Shewchuk orient3d is unavailable")
    out = np.zeros(idx.shape[0], dtype=np.int64)
    for k in range(idx.shape[0]):
        t = tets[idx[k]]
        out[k] = int(orient3d(pts[t[0]], pts[t[1]], pts[t[2]], pts[t[3]]))
    return out


def _float_vol6(pts: np.ndarray, tets_sub: np.ndarray) -> np.ndarray:
    """Cheap float signed volume, used only as a conservative *pre-reject*.

    A move this screen rejects is never applied, so a false reject only costs a
    backtrack; a move it accepts is still decided by exact ``orient3d``.
    """
    v = pts[tets_sub]
    return np.einsum(
        "ij,ij->i",
        v[:, 1] - v[:, 0],
        np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
    )


def _mean_edge_length(pts: np.ndarray, tets: np.ndarray) -> float:
    v = pts[tets]
    total = 0.0
    for i, j in _EDGE_PAIRS:
        total += float(np.linalg.norm(v[:, j] - v[:, i], axis=1).sum())
    n = float(tets.shape[0] * 6)
    return total / n if n > 0 else 0.0


# --------------------------------------------------------------------------
# main pass
# --------------------------------------------------------------------------
def penalized_active_set_smooth(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    locked_vertex_ids: np.ndarray | None = None,
    n_sweeps: int = 3,
    p: int = _P_EXP,
    q_thresh: float = _Q_THRESH,
    step_cap_frac: float = _STEP_CAP_FRAC,
    max_backtrack: int = _MAX_BACKTRACK,
    sliver_q: float = 0.01,
) -> tuple[np.ndarray, Flow2Report]:
    """Run the Leng 2013 penalized active-set smoothing on interior vertices.

    Returns ``(new_pts, report)``.  ``pts`` is never mutated; on any guard
    failure the *original* array object's contents are returned unchanged and
    ``report.accepted`` is ``False``.  Connectivity is never touched.
    """
    pts_in = np.asarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(np.asarray(tets, dtype=np.int64))
    rep = Flow2Report(n_tets=int(tets.shape[0]), n_sweeps=int(n_sweeps))
    if tets.size == 0 or pts_in.shape[0] == 0:
        rep.reject_reason = "empty"
        return pts_in, rep

    from core.generator.native_tet.quality import tet_shape_quality

    n_pts = int(pts_in.shape[0])
    q_vl0 = tet_volume_length_quality(pts_in, tets)
    q_cn0 = tet_shape_quality(pts_in, tets)
    rep.min_q_vl_before = float(q_vl0.min())
    rep.mean_q_vl_before = float(q_vl0.mean())
    rep.min_q_canon_before = float(q_cn0.min())
    rep.mean_q_canon_before = float(q_cn0.mean())
    rep.n_active_before = int((q_vl0 <= q_thresh).sum())
    rep.n_sliver_before = int((q_cn0 < sliver_q).sum())
    rep.energy_before = penalized_energy(q_vl0, p=p, q_thresh=q_thresh)

    # --- free vertices: never boundary, never caller-locked -----------------
    locked = _boundary_vertex_mask(tets, n_pts)
    if locked_vertex_ids is not None:
        ids = np.asarray(locked_vertex_ids, dtype=np.int64).reshape(-1)
        ids = ids[(ids >= 0) & (ids < n_pts)]
        locked[ids] = True
    free = ~locked
    rep.n_free_vertices = int(free.sum())
    if rep.n_free_vertices == 0:
        rep.reject_reason = "no_free_vertices"
        return pts_in, rep

    offsets, inc_tet, inc_slot = _vertex_incidence(tets, n_pts)
    base_signs = _orient3d_signs(pts_in, tets)

    step_cap = step_cap_frac * _mean_edge_length(pts_in, tets)
    if not np.isfinite(step_cap) or step_cap <= 0.0:
        rep.reject_reason = "degenerate_step_cap"
        return pts_in, rep

    work = pts_in.copy()
    q_work = q_vl0.copy()
    n_moved = 0
    n_backtracks = 0
    n_skip_degen = 0
    max_disp = 0.0

    for _sweep in range(max(0, int(n_sweeps))):
        # Deterministic order: worst local quality first, ties by vertex id.
        # The active set is recomputed here and again per accepted move.
        cand: list[int] = []
        keys: list[float] = []
        for v in range(n_pts):
            if not free[v]:
                continue
            lo, hi = int(offsets[v]), int(offsets[v + 1])
            if hi <= lo:
                continue
            ring = inc_tet[lo:hi]
            qr = q_work[ring]
            if not (qr <= q_thresh).any():
                continue  # outside the active set (Leng T_q)
            cand.append(v)
            keys.append(float(qr.min()))
        if not cand:
            break
        cand_arr = np.asarray(cand, dtype=np.int64)
        order = np.lexsort((cand_arr, np.asarray(keys, dtype=np.float64)))
        rep.n_candidate_vertices = max(rep.n_candidate_vertices, len(cand))

        moved_this_sweep = 0
        for oi in order:
            v = int(cand_arr[oi])
            lo, hi = int(offsets[v]), int(offsets[v + 1])
            ring = inc_tet[lo:hi]
            slots = inc_slot[lo:hi]
            signs = base_signs[ring]
            if np.any(signs == 0):
                n_skip_degen += 1
                continue

            q_old = q_work[ring]
            active = q_old <= q_thresh
            if not active.any():
                continue
            q_min_old = float(q_old.min())

            # --- negative first variation of E restricted to this vertex ----
            a_ring = ring[active]
            a_slot = slots[active]
            corners = work[tets[a_ring]]
            gq = _quality_grad_wrt_vertex(corners, a_slot)  # dQ/dx
            qa = np.maximum(q_old[active], _Q_FLOOR)
            # dE/dQ = -p * (1/Q - 1/q_t)^(p-1) / Q^2
            dEdQ = -float(p) * (1.0 / qa - 1.0 / q_thresh) ** (p - 1) / (qa * qa)
            grad = (dEdQ[:, None] * gq).sum(axis=0)
            gnorm = float(np.linalg.norm(grad))
            if not np.isfinite(gnorm) or gnorm <= 0.0:
                continue
            direction = -grad / gnorm  # unit descent direction

            # --- line search: Remark 3.1 backtracking, 1% displacement cap --
            tau = step_cap
            ring_tets = tets[ring]
            float_ok = signs.astype(np.float64)
            for _bt in range(max(1, int(max_backtrack))):
                x_new = work[v] + tau * direction
                if not np.all(np.isfinite(x_new)):
                    tau *= _BACKTRACK
                    n_backtracks += 1
                    continue
                saved = work[v].copy()
                work[v] = x_new
                # Cheap float pre-reject (conservative), then the exact decision.
                fv = _float_vol6(work, ring_tets)
                if np.all(np.sign(fv) == float_ok):
                    q_new = tet_volume_length_quality(work, ring_tets)
                    if float(q_new.min()) > q_min_old * (1.0 + 1e-12) + 1e-16:
                        new_signs = _orient3d_signs_subset(work, tets, ring)
                        if np.array_equal(new_signs, signs):
                            q_work[ring] = q_new
                            n_moved += 1
                            moved_this_sweep += 1
                            max_disp = max(max_disp, float(np.linalg.norm(x_new - saved)))
                            break
                work[v] = saved  # transactional: nothing partially applied
                tau *= _BACKTRACK
                n_backtracks += 1

        if moved_this_sweep == 0:
            break

    rep.n_moved = int(n_moved)
    rep.n_backtracks = int(n_backtracks)
    rep.n_skipped_degenerate = int(n_skip_degen)
    rep.max_displacement = float(max_disp)

    if n_moved == 0:
        rep.reject_reason = "no_move_accepted"
        rep.min_q_vl_after = rep.min_q_vl_before
        rep.mean_q_vl_after = rep.mean_q_vl_before
        rep.min_q_canon_after = rep.min_q_canon_before
        rep.mean_q_canon_after = rep.mean_q_canon_before
        rep.n_active_after = rep.n_active_before
        rep.n_sliver_after = rep.n_sliver_before
        rep.energy_after = rep.energy_before
        return pts_in, rep

    # --- whole-pass guards --------------------------------------------------
    q_vl1 = tet_volume_length_quality(work, tets)
    q_cn1 = tet_shape_quality(work, tets)
    rep.min_q_vl_after = float(q_vl1.min())
    rep.mean_q_vl_after = float(q_vl1.mean())
    rep.min_q_canon_after = float(q_cn1.min())
    rep.mean_q_canon_after = float(q_cn1.mean())
    rep.n_active_after = int((q_vl1 <= q_thresh).sum())
    rep.n_sliver_after = int((q_cn1 < sliver_q).sum())
    rep.energy_after = penalized_energy(q_vl1, p=p, q_thresh=q_thresh)

    bnd_bitwise = bool(np.array_equal(work[locked], pts_in[locked]))
    rep.boundary_vertices_bitwise_equal = bnd_bitwise
    binv = check_boundary_invariant(pts_in, tets, work, tets, "native_tet_flow2", log_only=True)
    rep.boundary_preserved = bool(binv.preserved)

    final_signs = _orient3d_signs(work, tets)
    signs_ok = bool(np.array_equal(final_signs, base_signs))

    reasons = []
    if not bnd_bitwise:
        reasons.append("boundary_vertex_moved")
    if not rep.boundary_preserved:
        reasons.append("boundary_invariant")
    if not signs_ok:
        reasons.append("orientation_changed")
    if rep.min_q_vl_after < rep.min_q_vl_before:
        reasons.append("min_q_regressed")
    if rep.energy_after > rep.energy_before:
        reasons.append("energy_increased")

    if reasons:
        rep.accepted = False
        rep.reject_reason = "+".join(reasons)
        log.warning(
            "native_tet_flow2_reverted",
            reason=rep.reject_reason,
            n_moved=rep.n_moved,
            min_q_vl_before=round(rep.min_q_vl_before, 9),
            min_q_vl_after=round(rep.min_q_vl_after, 9),
        )
        return pts_in, rep

    rep.accepted = True
    return work, rep


def run_flow2_pass(
    pts: np.ndarray,
    tets: np.ndarray,
    n_surface_vertices: int | None = None,
    **kwargs: Any,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Thin pipeline entry point: returns ``(pts, report_dict)``.

    ``n_surface_vertices`` (native_tet's convention that the first
    ``n_surface`` points are surface points) is folded into the lock set on top
    of the topological boundary-vertex mask, so the two definitions can only
    ever over-lock, never under-lock.
    """
    locked = kwargs.pop("locked_vertex_ids", None)
    if n_surface_vertices is not None and int(n_surface_vertices) > 0:
        surf = np.arange(int(n_surface_vertices), dtype=np.int64)
        locked = surf if locked is None else np.concatenate(
            [np.asarray(locked, dtype=np.int64).reshape(-1), surf]
        )
    new_pts, rep = penalized_active_set_smooth(pts, tets, locked_vertex_ids=locked, **kwargs)
    return new_pts, rep.as_dict()
