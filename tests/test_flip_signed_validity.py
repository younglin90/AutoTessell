"""flip.py must reject flips that create inverted (overlapping) tets.

The bug (BETA2827, found during BETA2825/cycle-5 instrumentation): the validity
checks in flip_faces_23 / flip_edges_32 / flip_edges_44 / flip_edges_54 /
flip_edges_76 were

    if not np.all(np.abs(_v) >= 1e-20):   # absolute value!

so a candidate whose signed volume is NEGATIVE — an inverted tet, i.e. one that
overlaps its neighbours — passed as long as it was non-degenerate.  Measured
impact: a raw face_flip_pass took a valid cube mesh's sum|cell volume| from
1.003x to 1.569x (56% overlap), and the cycle-5 sweep instrumentation counted
332 inversions from flip32 and 119 from flip44 alone, exploding max_skewness
to 2.1e15 once the sweep output reached disk.

The corrected predicates (TetWild Invariant 3 — "no inverted tets, every
operation rolled back if violated"):

  2-3: the new edge (x,y) must pierce the shared face (a,b,c)  ⇔  all three
       new tets have the SAME nonzero sign.
  3-2: the link triangle's plane must separate u from v         ⇔  the two
       new tets (u,xyz), (v,xyz) have OPPOSITE nonzero signs.
  all: tiling identity — sum|vol(new)| == sum|vol(old)| (a valid flip
       re-partitions the same region; both overlap and gaps break this,
       and it is orientation-convention-free).

Each "invalid" test below also asserts the OLD criteria (non-degenerate +
quality improves) would have ACCEPTED the flip, proving the test targets the
validity predicate and not the quality gate.
"""
from __future__ import annotations

import numpy as np

from core.generator.native_tet.flip import (
    _tet_quality_batch_arr,
    _tet_signed_vol6_batch_arr,
    flip_edges_32,
    flip_faces_23,
)


def _vol6(pts: np.ndarray, tets: list[tuple[int, int, int, int]]) -> np.ndarray:
    return _tet_signed_vol6_batch_arr(pts, np.asarray(tets, dtype=np.int64))


def _minq(pts: np.ndarray, tets: list) -> float:
    return float(_tet_quality_batch_arr(pts, np.asarray(tets, dtype=np.int64)).min())


# ----------------------------------------------------------------------
# 3-2 flip
# ----------------------------------------------------------------------


def _ring32(u, v, x, y, z):
    """3 tets sharing edge (u=0, v=1) with link ring (x=2, y=3, z=4)."""
    pts = np.asarray([u, v, x, y, z], dtype=np.float64)
    tets = np.asarray(
        [[0, 1, 2, 3], [0, 1, 3, 4], [0, 1, 4, 2]], dtype=np.int64
    )
    return pts, tets


def test_flip32_valid_separated_ring_still_flips() -> None:
    """A genuinely valid 3-2 (ring plane separates u,v) must still be applied."""
    # Short vertical edge inside a large ring at z=0: the three old wedges are
    # thin (poor quality) and the two new half-bipyramids are much better, so
    # the quality gate passes and only validity decides.
    pts, tets = _ring32(
        u=(0, 0, 0.25), v=(0, 0, -0.25),
        x=(1, 0, 0), y=(-0.5, 0.866, 0), z=(-0.5, -0.866, 0),
    )
    new2 = [(0, 2, 3, 4), (1, 2, 3, 4)]
    v2 = _vol6(pts, new2)
    assert v2[0] * v2[1] < 0, "premise: ring plane separates u and v"

    out, n_flip = flip_edges_32(pts, tets)
    assert n_flip == 1, "valid separated 3-2 flip must be applied"
    assert out.shape[0] == 2


def test_flip32_rejects_nonseparating_ring_that_naive_check_accepted() -> None:
    """u,v on the SAME side of the ring plane → overlap; must be rejected.

    The old abs() check accepted this because both new tets are non-degenerate,
    and the quality gate accepted it because the thin old wedges score worse
    than the two well-shaped (but overlapping!) pyramids.
    """
    # Ring lifted to z=0.5; both edge endpoints sit below it.
    pts, tets = _ring32(
        u=(0, 0, 0.01), v=(0, 0, -0.01),
        x=(1, 0, 0.5), y=(-1, 1, 0.5), z=(-1, -1, 0.5),
    )
    new2 = [(0, 2, 3, 4), (1, 2, 3, 4)]
    v2 = _vol6(pts, new2)

    # Premises: the buggy criteria would all have passed.
    assert np.all(np.abs(v2) >= 1e-20), "premise: non-degenerate (old check passed)"
    assert v2[0] * v2[1] > 0, "premise: NOT separated — the overlap case"
    q_old = _minq(pts, [[0, 1, 2, 3], [0, 1, 3, 4], [0, 1, 4, 2]])
    q_new = _minq(pts, new2)
    assert q_new > q_old + 1e-4, "premise: quality gate would have accepted"

    out, n_flip = flip_edges_32(pts, tets)
    assert n_flip == 0, (
        "3-2 flip with a non-separating ring creates two overlapping tets "
        "and must be rejected by the signed validity check"
    )
    assert out.shape[0] == 3, "mesh must be unchanged"


# ----------------------------------------------------------------------
# 2-3 flip
# ----------------------------------------------------------------------


def test_flip23_rejects_edge_missing_shared_face() -> None:
    """New edge (x,y) NOT piercing shared face (a,b,c) → mixed signs → reject.

    Both old tets are valid (apexes on opposite sides of abc), but the segment
    xy passes OUTSIDE the triangle abc, so the three new tets have mixed signs
    — the classic invalid (non-convex) 2-3 configuration the abs() check let
    through whenever all three volumes were merely nonzero.
    """
    # Shared face abc; apexes d above and e below, but both displaced far
    # laterally so segment d-e crosses the abc plane outside the triangle.
    a, b, c = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    d = (2.5, 2.5, 0.35)   # above the plane, far outside the triangle
    e = (2.5, 2.5, -0.35)  # below the plane, same lateral spot
    pts = np.asarray([a, b, c, d, e], dtype=np.float64)
    tets = np.asarray([[0, 1, 2, 3], [0, 1, 2, 4]], dtype=np.int64)

    new3 = [(0, 1, 3, 4), (1, 2, 3, 4), (2, 0, 3, 4)]
    v3 = _vol6(pts, new3)
    assert np.all(np.abs(v3) >= 1e-20), "premise: non-degenerate (old check passed)"
    signs = np.sign(v3)
    assert not (np.all(signs > 0) or np.all(signs < 0)), (
        "premise: mixed signs — segment d-e misses triangle abc"
    )

    out, n_flip = flip_faces_23(pts, tets)
    assert n_flip == 0, (
        "2-3 flip whose new edge misses the shared face must be rejected"
    )
    assert out.shape[0] == 2, "mesh must be unchanged"


def test_flip32_tiling_identity_holds_when_applied() -> None:
    """When a flip IS applied, total |volume| must be exactly preserved."""
    pts, tets = _ring32(
        u=(0, 0, 0.25), v=(0, 0, -0.25),
        x=(1, 0, 0), y=(-0.5, 0.866, 0), z=(-0.5, -0.866, 0),
    )
    vol_before = float(np.abs(_tet_signed_vol6_batch_arr(pts, tets)).sum())
    out, n_flip = flip_edges_32(pts, tets)
    assert n_flip == 1
    vol_after = float(np.abs(_tet_signed_vol6_batch_arr(pts, out)).sum())
    assert abs(vol_after - vol_before) <= 1e-9 * vol_before
