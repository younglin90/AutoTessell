"""FSL Wave 1 -- TET-LAZY-1 (Dassi 2018 lazy compound flips) + TET-SHAPE-3(a)
(Ni 2017 / Shewchuk multi-face removal), diagnostic-first.

Target: the 61 "core-unflippable" flat wedges FSL1 finds on dual_torus
(``core/generator/native_tet/validate.py::flat_allsurf_sliver_candidates``,
``n_core_unflippable``) -- all-surface tets with exactly 2 boundary faces
whose 2 interior faces both fail the plain 2-3 flip bipyramid test.

Literature basis (see docs/references/literature/native_tet/):
    - Dassi, Kamenski, Farrell, Si 2018 -- lazy searching flips (``flipnm``):
      an edge [a,b] shared by n>=3 tets is removed by shrinking its tet ring
      one vertex at a time via internal 2-3 flips (Step 2), recursing on an
      *adjacent* edge (Step 3) if no ring vertex is directly shrinkable.
    - Ni et al. 2017 (citing Shewchuk, unpublished, "Two discrete
      optimization algorithms...") -- multi-face / edge removal, strictly
      stronger than plain 2-3/3-2/4-4 because it searches all
      re-triangulations of the edge's tet ring, not just adjacent-face pairs.

Both mechanisms reduce to the same combinatorial primitive: replace the n
tets sharing an interior edge (a, b) with a re-triangulation of the ring.
``general_edge_removal`` implements that primitive for arbitrary ring size n
(generalizing the fixed n=3/4/5/7 patterns already in ``flip.py``), and is
used two ways:
    - "lazy" (``exhaustive=False``): stop at the first improving candidate
      -- this is the Dassi flavour, cheap and depth-bounded (this module's
      ``max_depth in {1, 2}``).
    - "exhaustive" (``exhaustive=True``): search every pivot/split -- the
      Ni/Shewchuk flavour, strictly more powerful, used as the last resort.

Every attempt is transactional: the input arrays are never mutated, guards
(same-sign volume, exact volume-tiling identity, strict local min-quality
improvement) gate acceptance, and ``check_boundary_invariant`` verifies zero
boundary-face change before a candidate is accepted. Failed attempts change
nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.generator.native_tet.boundary_invariant import check_boundary_invariant
from core.generator.native_tet.flip import (
    _boundary_edges_from_fmap,
    _edge_to_tets_map,
    _face_map_vectorized,
    _tet_quality_batch_arr,
    _tet_signed_vol6_batch_arr,
)
from core.utils.logging import get_logger

log = get_logger(__name__)

_MAX_RING_SIZE = 24  # diagnostic safety bound -- FSL wedges are tiny local rings.


def _sv(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> float:
    return float(np.dot(b - a, np.cross(c - a, d - a)))


def find_core_unflippable_wedges(
    pts: np.ndarray,
    tets: np.ndarray,
    n_surface_vertices: int,
    *,
    q_flat: float = 0.01,
) -> list[dict[str, Any]]:
    """Same classification as FSL1's ``n_core_unflippable`` count, but returns
    the actual wedge records (tet index + the two edges needed for Wave 1)
    instead of just a count.

    A "core-unflippable wedge" is an all-surface tet with quality < q_flat,
    exactly 2 boundary faces, and both interior faces failing the plain 2-3
    flip bipyramid test (mirrors
    ``validate.flat_allsurf_sliver_candidates``'s ``n_core_unflippable``
    branch exactly; kept as an independent read-only implementation so this
    diagnostic module has no write-access coupling to the tested FSL1 code).

    Returns
    -------
    list[dict] each with keys: tet_index, verts (4-tuple), ridge_edge (the
    edge shared by the 2 boundary faces), far_edge (the edge shared by the 2
    interior faces -- the edge Wave 1 attempts to remove), quality.
    """
    tets = np.asarray(tets, dtype=np.int64)
    pts = np.asarray(pts, dtype=np.float64)
    if tets.size == 0:
        return []

    v = pts[tets]
    all_surface = (tets < int(n_surface_vertices)).all(axis=1)
    e = [
        np.linalg.norm(v[:, i] - v[:, j], axis=1)
        for i, j in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    ]
    edge_max = np.maximum.reduce(e)
    vol = np.abs(
        np.einsum(
            "ij,ij->i", v[:, 1] - v[:, 0],
            np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
        )
    ) / 6.0
    q = np.zeros_like(edge_max)
    safe = edge_max > 1e-30
    q[safe] = 8.48 * vol[safe] / (edge_max[safe] ** 3)

    cand = np.where(all_surface & (q < float(q_flat)))[0]
    if cand.size == 0:
        return []

    local = np.array([[1, 2, 3], [0, 2, 3], [0, 1, 3], [0, 1, 2]])
    sorted_faces = np.sort(tets[:, local].reshape(-1, 3), axis=1)
    order = np.lexsort((sorted_faces[:, 2], sorted_faces[:, 1], sorted_faces[:, 0]))
    sk = sorted_faces[order]
    match_next = np.all(sk[1:] == sk[:-1], axis=1)
    partner = np.full(order.size, -1, dtype=np.int64)
    pi = np.where(match_next)[0]
    partner[order[pi]] = order[pi + 1]
    partner[order[pi + 1]] = order[pi]

    wedges: list[dict[str, Any]] = []
    for ti in cand.tolist():
        boundary_lf: list[int] = []
        interior_lf: list[int] = []
        flip_ok = False
        for lf in range(4):
            nb_flat = partner[4 * ti + lf]
            s0, s1, s2 = tets[ti, local[lf]]
            if nb_flat < 0:
                boundary_lf.append(lf)
                continue
            interior_lf.append(lf)
            nb_tet, nb_lf = divmod(int(nb_flat), 4)
            apex1, apex2 = tets[ti, lf], tets[nb_tet, nb_lf]
            p_s0, p_s1, p_s2 = pts[s0], pts[s1], pts[s2]
            p1, p2 = pts[apex1], pts[apex2]
            vols = [_sv(p_s0, p_s1, p1, p2), _sv(p_s1, p_s2, p1, p2), _sv(p_s2, p_s0, p1, p2)]
            if all(abs(x) > 1e-18 for x in vols) and (
                all(x > 0 for x in vols) or all(x < 0 for x in vols)
            ):
                flip_ok = True

        if flip_ok or len(boundary_lf) != 2 or len(interior_lf) != 2:
            continue

        bf0, bf1 = boundary_lf
        bset0 = set(tets[ti, local[bf0]].tolist())
        bset1 = set(tets[ti, local[bf1]].tolist())
        ridge = tuple(sorted(bset0 & bset1))
        if0, if1 = interior_lf
        iset0 = set(tets[ti, local[if0]].tolist())
        iset1 = set(tets[ti, local[if1]].tolist())
        far = tuple(sorted(iset0 & iset1))
        if len(ridge) != 2 or len(far) != 2:
            continue

        wedges.append({
            "tet_index": int(ti),
            "verts": tuple(int(x) for x in tets[ti]),
            "ridge_edge": (int(ridge[0]), int(ridge[1])),
            "far_edge": (int(far[0]), int(far[1])),
            "quality": float(q[ti]),
        })
    return wedges


def _order_ring(pts: np.ndarray, a: int, b: int, ring_verts: list[int]) -> list[int] | None:
    """Order ring vertices cyclically by angle around the (a, b) axis."""
    axis = pts[b] - pts[a]
    axis_len = float(np.linalg.norm(axis))
    if axis_len < 1e-20:
        return None
    axis_n = axis / axis_len
    ring_pts = pts[ring_verts]
    ref = pts[a]
    proj = ring_pts - ref - np.outer(np.dot(ring_pts - ref, axis_n), axis_n)
    perp = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(axis_n, perp))) > 0.9:
        perp = np.array([0.0, 1.0, 0.0])
    perp = perp - float(np.dot(perp, axis_n)) * axis_n
    perp_len = float(np.linalg.norm(perp))
    if perp_len < 1e-20:
        return None
    perp = perp / perp_len
    perp2 = np.cross(axis_n, perp)
    angles = np.arctan2(proj @ perp2, proj @ perp)
    order = np.argsort(angles)
    return [ring_verts[i] for i in order.tolist()]


def general_edge_removal(
    pts: np.ndarray,
    tets: np.ndarray,
    a: int,
    b: int,
    *,
    min_quality_improvement: float = 1e-4,
    exhaustive: bool = True,
    _precomputed_edge_owners: dict[tuple[int, int], list[int]] | None = None,
    _precomputed_face_owners: dict[tuple[int, int, int], list[int]] | None = None,
    _precomputed_boundary_edges: set[tuple[int, int]] | None = None,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Remove interior edge (a, b) by re-triangulating its tet ring.

    The n tets sharing edge (a, b) tile exactly the double pyramid (bipyramid)
    over the ring polygon r[0..n-1] with apexes a and b. The standard generic
    edge-removal (Dassi 2018 Sec. 3 endpoint case n=3; Shewchuk's unpublished
    "two discrete optimization algorithms" for general n) re-tiles that same
    bipyramid without the (a, b) diagonal: fan-triangulate the ring from a
    pivot r[d] into (n-2) triangles, then pair *every* triangle with *both*
    apexes -- pyramid(a, fan) union pyramid(b, fan) -- giving 2n-4 new tets
    that provably cover the identical region (this is why the volume-tiling
    identity check below is exact, not approximate) and contain no (a, b)
    edge. n=3 reduces to exactly ``flip_edges_32``'s 2-tet result.

    Different pivots r[d] give different (generally non-congruent) fans, so
    quality varies with d; this is the search space. ``exhaustive=False``
    accepts the first pivot whose resulting min quality improves by >=
    ``min_quality_improvement`` over the old ring's min quality (Dassi-style
    lazy search). ``exhaustive=True`` tries every pivot and keeps the best
    (Ni/Shewchuk-style stronger, non-lazy search).

    Guards (never violated, or the candidate is rejected): every new tet is
    non-degenerate and consistently oriented for its apex side; the summed
    |signed volume| of the new tets equals that of the old ring tets exactly
    (tiling identity -- catches inverted/overlapping candidates a pure
    same-sign check would miss); (a, b) must be a genuinely interior edge
    (its key must not appear in the boundary-edge set).

    Returns (new_tets, info) where new_tets is None on failure/no-op (input
    ``tets`` is *never mutated* either way).
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return None, {"reason": "empty_mesh"}

    key = (a, b) if a < b else (b, a)
    e2t = _precomputed_edge_owners or _edge_to_tets_map(tets)
    owners = e2t.get(key)
    if not owners or len(owners) < 3:
        return None, {"reason": "ring_too_small", "n": 0 if not owners else len(owners)}
    n = len(owners)
    if n > _MAX_RING_SIZE:
        return None, {"reason": "ring_too_large", "n": n}

    fmap = _precomputed_face_owners or _face_map_vectorized(tets)
    boundary_edges = (
        _precomputed_boundary_edges
        if _precomputed_boundary_edges is not None
        else _boundary_edges_from_fmap(fmap)
    )
    if key in boundary_edges:
        return None, {"reason": "boundary_edge", "n": n}

    ring_v: set[int] = set()
    for ti in owners:
        rest = [int(x) for x in tets[ti].tolist() if x != a and x != b]
        if len(rest) != 2:
            return None, {"reason": "malformed_ring", "n": n}
        ring_v.update(rest)
    if len(ring_v) != n:
        return None, {"reason": "ring_mismatch", "n_owners": n, "n_ring_verts": len(ring_v)}

    r = _order_ring(pts, a, b, sorted(ring_v))
    if r is None:
        return None, {"reason": "degenerate_axis", "n": n}

    old_tets = np.asarray([tets[ti] for ti in owners], dtype=np.int64)
    q_old = float(_tet_quality_batch_arr(pts, old_tets).min())
    vol_old = float(np.abs(_tet_signed_vol6_batch_arr(pts, old_tets)).sum())

    n_tri = n - 2
    best: list[tuple[int, int, int, int]] | None = None
    best_q = -1.0
    for d in range(n):
        tris = [(r[(d + 1 + k) % n], r[(d + 2 + k) % n]) for k in range(n_tri)]
        a_tets = [(a, r[d], *tri) for tri in tris]
        b_tets = [(b, r[d], *tri) for tri in tris]
        cand = a_tets + b_tets
        if any(len(set(t)) != 4 for t in cand):
            continue
        cand_arr = np.asarray(cand, dtype=np.int64)
        v6 = _tet_signed_vol6_batch_arr(pts, cand_arr)
        if np.any(np.abs(v6) < 1e-18):
            continue
        if abs(float(np.abs(v6).sum()) - vol_old) > 1e-9 * max(vol_old, 1e-30):
            continue
        q_cand = float(_tet_quality_batch_arr(pts, cand_arr).min())
        if q_cand > best_q:
            best_q, best = q_cand, cand
        if not exhaustive and q_cand >= q_old + min_quality_improvement:
            break

    if best is None or best_q < q_old + float(min_quality_improvement):
        return None, {
            "reason": "no_improving_retriangulation",
            "n": n, "q_old": q_old,
            "best_q": best_q if best is not None else None,
        }

    alive = np.ones(tets.shape[0], dtype=bool)
    for ti in owners:
        alive[ti] = False
    new_tets = np.concatenate([tets[alive], np.asarray(best, dtype=np.int64)], axis=0)
    return new_tets, {
        "reason": "applied", "n": n, "q_old": q_old, "q_new": best_q,
        "n_new_tets": len(best), "exhaustive": exhaustive,
    }


def _guarded_removal(
    pts: np.ndarray, tets: np.ndarray, a: int, b: int, label: str, *, exhaustive: bool,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """``general_edge_removal`` + boundary-invariant check. Rolls back (returns
    None) if the boundary is touched -- belt-and-suspenders on top of the
    interior-edge-only guard already inside ``general_edge_removal``."""
    new_tets, info = general_edge_removal(pts, tets, a, b, exhaustive=exhaustive)
    if new_tets is None:
        return None, info
    report = check_boundary_invariant(pts, tets, pts, new_tets, label, log_only=True)
    if not report.preserved:
        info = dict(info)
        info["reason"] = "boundary_invariant_violated"
        return None, info
    return new_tets, info


@dataclass
class WedgeDiagnosis:
    tet_index: int
    far_edge: tuple[int, int]
    ridge_edge: tuple[int, int]
    # "combinatorially_unlocked" | "structurally_blocked" | "collateral_resolved"
    classification: str
    method: str | None = None  # "dassi_depth1" | "dassi_depth2" | "shewchuk_mfr" | None
    reason: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def diagnose_wedge(
    pts: np.ndarray, tets: np.ndarray, wedge: dict[str, Any], *, max_depth: int = 2,
) -> tuple[np.ndarray, WedgeDiagnosis]:
    """Try Dassi-style lazy compound flips (depth 1, then depth 2) on one
    core-unflippable wedge, then Ni/Shewchuk-style exhaustive multi-face
    removal as the last resort. Fully transactional -- returns the input
    ``tets`` unchanged unless a fix that passes every guard is found.
    """
    a, b = wedge["far_edge"]
    ridge = wedge["ridge_edge"]
    label_base = f"fsl_wave1_wedge{wedge['tet_index']}"

    pts = np.asarray(pts, dtype=np.float64)
    tets0 = np.asarray(tets, dtype=np.int64)

    # Collateral case: an earlier wedge's fix already consumed this wedge's
    # own tet as a side effect (shared ring vertex). Detect via vertex-set
    # membership, since tet *indices* shift after any removal.
    target_vset = frozenset(wedge["verts"])
    still_present = any(frozenset(t.tolist()) == target_vset for t in tets0)
    if not still_present:
        return tets0, WedgeDiagnosis(
            wedge["tet_index"], (a, b), ridge, "collateral_resolved",
            reason="wedge_tet_no_longer_present",
        )

    # --- Dassi depth 1: lazy attempt directly on the wedge's own far edge ---
    new_tets, info = _guarded_removal(pts, tets0, a, b, f"{label_base}_depth1", exhaustive=False)
    if new_tets is not None:
        return new_tets, WedgeDiagnosis(
            wedge["tet_index"], (a, b), ridge, "combinatorially_unlocked",
            method="dassi_depth1", detail=info,
        )
    depth1_reason = info.get("reason")

    # --- Dassi depth 2: reshape one adjacent (side) edge first, then retry ---
    if max_depth >= 2:
        for (u, v) in ((a, ridge[0]), (a, ridge[1]), (b, ridge[0]), (b, ridge[1])):
            side_tets, side_info = _guarded_removal(
                pts, tets0, u, v, f"{label_base}_side_{u}_{v}", exhaustive=False,
            )
            if side_tets is None:
                continue
            retry_tets, retry_info = _guarded_removal(
                pts, side_tets, a, b, f"{label_base}_depth2", exhaustive=False,
            )
            if retry_tets is None:
                continue
            return retry_tets, WedgeDiagnosis(
                wedge["tet_index"], (a, b), ridge, "combinatorially_unlocked",
                method="dassi_depth2",
                detail={"side_edge": (u, v), "side_info": side_info, "retry_info": retry_info},
            )

    # --- Ni/Shewchuk multi-face removal: exhaustive one-shot on far edge ---
    mfr_tets, mfr_info = _guarded_removal(pts, tets0, a, b, f"{label_base}_mfr", exhaustive=True)
    if mfr_tets is not None:
        return mfr_tets, WedgeDiagnosis(
            wedge["tet_index"], (a, b), ridge, "combinatorially_unlocked",
            method="shewchuk_mfr", detail=mfr_info,
        )

    return tets0, WedgeDiagnosis(
        wedge["tet_index"], (a, b), ridge, "structurally_blocked",
        reason=mfr_info.get("reason", depth1_reason), detail={"depth1": info, "mfr": mfr_info},
    )


def run_wave1_diagnostic(
    pts: np.ndarray,
    tets: np.ndarray,
    n_surface_vertices: int,
    *,
    q_flat: float = 0.01,
    max_depth: int = 2,
    apply_fixes: bool = True,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Classify + (optionally) fix every FSL1 core-unflippable wedge.

    Runs ``diagnose_wedge`` on the wedge list found in the *initial* mesh
    (indices are only used for reporting/labels; every attempt re-resolves
    the target edge against the current, possibly-already-modified mesh, so
    cascading fixes are handled correctly). If ``apply_fixes`` is False, runs
    read-only (classification only, input tets returned unchanged).

    Returns (tets_out, report) where report has:
        n_wedges, n_combinatorially_unlocked, n_structurally_blocked,
        n_collateral_resolved, by_method (dict), wedges (per-wedge detail).
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets0 = np.asarray(tets, dtype=np.int64)
    wedges = find_core_unflippable_wedges(pts, tets0, n_surface_vertices, q_flat=q_flat)

    cur_tets = tets0.copy()
    n_unlocked = n_blocked = n_collateral = 0
    by_method: dict[str, int] = {}
    diagnoses: list[WedgeDiagnosis] = []

    for w in wedges:
        candidate_tets, diag = diagnose_wedge(pts, cur_tets, w, max_depth=max_depth)
        diagnoses.append(diag)
        if diag.classification == "combinatorially_unlocked":
            n_unlocked += 1
            by_method[diag.method or "?"] = by_method.get(diag.method or "?", 0) + 1
            if apply_fixes:
                cur_tets = candidate_tets
        elif diag.classification == "collateral_resolved":
            n_collateral += 1
        else:
            n_blocked += 1

    report = {
        "n_wedges": len(wedges),
        "n_combinatorially_unlocked": n_unlocked,
        "n_structurally_blocked": n_blocked,
        "n_collateral_resolved": n_collateral,
        "by_method": by_method,
        "applied_fixes": bool(apply_fixes and n_unlocked > 0),
        "wedges": [
            {
                "tet_index": d.tet_index, "far_edge": d.far_edge,
                "ridge_edge": d.ridge_edge, "classification": d.classification,
                "method": d.method, "reason": d.reason,
            }
            for d in diagnoses
        ],
    }
    log.info(
        "native_tet_fsl_wave1_diagnostic",
        n_wedges=report["n_wedges"],
        n_combinatorially_unlocked=n_unlocked,
        n_structurally_blocked=n_blocked,
        n_collateral_resolved=n_collateral,
        by_method=by_method,
        applied_fixes=report["applied_fixes"],
    )
    return (cur_tets if apply_fixes else tets0), report
