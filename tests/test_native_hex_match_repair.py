"""HEX-MATCH-2 executable-repair tests.

Synthetic hex meshes only — no pipeline run. Covers the pillow construction's
structural invariants (exact volume partition, conformity, untouched neighbours,
untouched boundary vertices), the node-placement claim that makes the operation
move the metric at all, the chord-collapse boundary guard that turned out to
rule the collapse branch out entirely, and the transaction contract
(never-mutate-the-input, per-candidate rollback, whole-pass rollback).
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from core.generator.native_hex.match_diagnostic import (
    _cell_centroid,
    face_centroid_normal_area,
    run_match_diagnostic,
)
from core.generator.native_hex.match_repair import (
    GateCeiling,
    _boundary_skew,
    _cyclic_face,
    _signed_volume,
    boundary_vertices,
    build_pillow,
    chord_collapse_boundary_conflict,
    face_collapse_pairings,
    mesh_quality,
    run_match_repair,
)
from core.generator.native_hex.metrics import _face_key, _face_owners

Cells = list[list[list[int]]]

# OpenFOAM-order hex face table (mesher._HEX_FACES), inlined so these tests do
# not drag the whole mesher module in.
_HEX_FACES = (
    (0, 3, 2, 1),
    (4, 5, 6, 7),
    (0, 1, 5, 4),
    (3, 7, 6, 2),
    (0, 4, 7, 3),
    (1, 2, 6, 5),
)

_UNIT_HEX = np.array(
    [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
    dtype=np.float64,
)
# Same topology, top face translated +2 in x: a strongly sheared hex whose top
# boundary face measures skewness 2.0 under the project's own formula.
_SHEARED_HEX = np.array(
    [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 1], [3, 0, 1], [3, 1, 1], [2, 1, 1]],
    dtype=np.float64,
)
_TOP_KEY = (4, 5, 6, 7)


def _single_cell() -> Cells:
    return [[[int(v) for v in face] for face in _HEX_FACES]]


def _grid(n: int) -> tuple[np.ndarray, Cells]:
    """An n x n x n unit-hex grid in OpenFOAM vertex order."""
    xs = np.arange(n + 1, dtype=np.float64)
    points = np.stack(np.meshgrid(xs, xs, xs, indexing="ij"), axis=-1).reshape(-1, 3)
    n1 = n + 1

    def vid(i: int, j: int, k: int) -> int:
        return i * n1 * n1 + j * n1 + k

    hexes = [
        [
            vid(i, j, k),
            vid(i + 1, j, k),
            vid(i + 1, j + 1, k),
            vid(i, j + 1, k),
            vid(i, j, k + 1),
            vid(i + 1, j, k + 1),
            vid(i + 1, j + 1, k + 1),
            vid(i, j + 1, k + 1),
        ]
        for i in range(n)
        for j in range(n)
        for k in range(n)
    ]
    cells: Cells = [[[int(h[v]) for v in face] for face in _HEX_FACES] for h in hexes]
    return points, cells


def _damaged_grid() -> tuple[np.ndarray, Cells]:
    """A clean 4^3 grid with one boundary quad's corners slid tangentially.

    This is the damage pattern wall-snapping actually produces — a quad dragged
    sideways relative to the body of its owner cell — rather than uniform noise,
    and it leaves the rest of the mesh clean so the repair has quality headroom.
    """
    points, cells = _grid(4)
    points = points.copy()
    sel = (
        (points[:, 2] >= 4.0 - 1e-9)
        & (points[:, 0] >= 2.0 - 1e-9)
        & (points[:, 0] <= 3.0 + 1e-9)
        & (points[:, 1] >= 2.0 - 1e-9)
        & (points[:, 1] <= 3.0 + 1e-9)
    )
    points[sel, 0] += 2.6
    points[sel, 1] += 1.3
    return points, cells


# A genuine frustum: top face smaller than the bottom, so it is deliberately
# *not* a parallelepiped and the mean-of-face-centres and mean-of-vertices cell
# centres actually differ.
_FRUSTUM_HEX = np.array(
    [
        [0, 0, 0],
        [1, 0, 0],
        [1, 1, 0],
        [0, 1, 0],
        [0.25, 0.25, 1],
        [0.75, 0.25, 1],
        [0.75, 0.75, 1],
        [0.25, 0.75, 1],
    ],
    dtype=np.float64,
)


# ---------------------------------------------------------------------------
# pillow construction — structural invariants
# ---------------------------------------------------------------------------


def test_pillow_partitions_the_owner_cell_exactly() -> None:
    """The 7 pieces must sum back to the original cell's volume, all positive."""
    cells = _single_cell()
    face = _cyclic_face(cells[0], _TOP_KEY)
    new_pts, new_cells = build_pillow(_UNIT_HEX, cells[0], face, 8, 0.55, 0.0, "taper")
    assert len(new_cells) == 7
    assert new_pts.shape == (8, 3)
    allp = np.vstack([_UNIT_HEX, new_pts])
    volumes = [_signed_volume(allp, c) for c in new_cells]
    assert min(volumes) > 0.0
    assert sum(volumes) == pytest.approx(_signed_volume(_UNIT_HEX, cells[0]), rel=1e-12)


def test_pillow_is_conforming_and_all_hex() -> None:
    """18 new internal faces, the 6 original faces still single-owner, all hexes."""
    cells = _single_cell()
    face = _cyclic_face(cells[0], _TOP_KEY)
    _new_pts, new_cells = build_pillow(_UNIT_HEX, cells[0], face, 8, 0.55, 0.0, "taper")
    owners = _face_owners(new_cells)
    assert Counter(len(o) for o in owners.values()) == {2: 18, 1: 6}
    for cell in new_cells:
        assert len(cell) == 6
        assert all(len(f) == 4 for f in cell)
        assert len({v for f in cell for v in f}) == 8
    original = {_face_key(f) for f in cells[0]}
    assert all(len(owners[k]) == 1 for k in original)


def test_pillow_reemits_original_faces_verbatim() -> None:
    """Neighbouring cells must be bit-identical: same vertex list, same winding."""
    cells = _single_cell()
    face = _cyclic_face(cells[0], _TOP_KEY)
    _new_pts, new_cells = build_pillow(_UNIT_HEX, cells[0], face, 8, 0.55, 1.0, "taper")
    emitted = {tuple(f) for cell in new_cells for f in cell}
    for original_face in cells[0]:
        assert tuple(original_face) in emitted


def test_pillow_creates_only_new_interior_points() -> None:
    """No pre-existing vertex is read back out with a different position."""
    cells = _single_cell()
    face = _cyclic_face(cells[0], _TOP_KEY)
    new_pts, new_cells = build_pillow(_SHEARED_HEX, cells[0], face, 8, 0.55, 0.5, "taper")
    allp = np.vstack([_SHEARED_HEX, new_pts])
    assert np.array_equal(allp[:8], _SHEARED_HEX)
    assert {v for cell in new_cells for f in cell for v in f} == set(range(16))


# ---------------------------------------------------------------------------
# node placement — the claim that makes the operation do anything
# ---------------------------------------------------------------------------


def test_plain_shrink_leaves_boundary_skew_exactly_unchanged() -> None:
    """The textbook shrink placement provably cannot move this metric.

    It displaces the inserted slab's centroid along the very ray whose
    tangential/normal ratio the skew formula takes, so the ratio is invariant.
    This is why ``_pillow_interior_points`` applies a tangential correction at
    all, and the test pins the reasoning rather than the implementation.
    """
    cells = _single_cell()
    face = _cyclic_face(cells[0], _TOP_KEY)
    before = _boundary_skew(_SHEARED_HEX, _cell_centroid(_SHEARED_HEX, cells[0]), face)
    assert before == pytest.approx(2.0)
    new_pts, new_cells = build_pillow(_SHEARED_HEX, cells[0], face, 8, 0.55, 0.0, "taper")
    allp = np.vstack([_SHEARED_HEX, new_pts])
    slab = next(c for c in new_cells if any(_face_key(f) == _TOP_KEY for f in c))
    after = _boundary_skew(allp, _cell_centroid(allp, slab), face)
    assert after == pytest.approx(before, rel=1e-12)


@pytest.mark.parametrize("mode", ["taper", "translate"])
def test_full_correction_drives_flagged_face_skew_to_zero(mode: str) -> None:
    cells = _single_cell()
    face = _cyclic_face(cells[0], _TOP_KEY)
    new_pts, new_cells = build_pillow(_SHEARED_HEX, cells[0], face, 8, 0.55, 1.0, mode)
    allp = np.vstack([_SHEARED_HEX, new_pts])
    slab = next(c for c in new_cells if any(_face_key(f) == _TOP_KEY for f in c))
    assert _boundary_skew(allp, _cell_centroid(allp, slab), face) == pytest.approx(0.0, abs=1e-12)


def test_partial_correction_scales_skew_linearly() -> None:
    """skew_after == (1 - correction) * skew_before, the ladder's whole premise."""
    cells = _single_cell()
    face = _cyclic_face(cells[0], _TOP_KEY)
    before = _boundary_skew(_SHEARED_HEX, _cell_centroid(_SHEARED_HEX, cells[0]), face)
    for correction in (0.25, 0.5, 0.75):
        new_pts, new_cells = build_pillow(
            _SHEARED_HEX, cells[0], face, 8, 0.55, correction, "taper"
        )
        allp = np.vstack([_SHEARED_HEX, new_pts])
        slab = next(c for c in new_cells if any(_face_key(f) == _TOP_KEY for f in c))
        after = _boundary_skew(allp, _cell_centroid(allp, slab), face)
        assert after == pytest.approx((1.0 - correction) * before, rel=1e-9)


# ---------------------------------------------------------------------------
# chord collapse — the guard that ruled the branch out
# ---------------------------------------------------------------------------


def test_face_collapse_has_exactly_two_pairings() -> None:
    assert face_collapse_pairings([1, 2, 3, 4]) == (((1, 2), (3, 4)), ((2, 3), (4, 1)))
    assert face_collapse_pairings([1, 2, 3]) == ()


def test_chord_collapse_is_rejected_for_every_boundary_seeded_column() -> None:
    """The HEX-MATCH-2 falsification finding, pinned as a test.

    Every column HEX-MATCH-1 traces is seeded at a flagged *boundary* quad, so
    the chord's first quad has all four nodes on the surface and both available
    face-collapse pairings merge boundary nodes. No depth increase can help —
    the offending quad is the seed itself.
    """
    points, cells = _grid(4)
    owners = _face_owners(cells)
    bnd = boundary_vertices(owners)
    seeds = [
        (owner_list[0], key)
        for key, owner_list in sorted(owners.items())
        if len(owner_list) == 1
    ]
    assert len(seeds) > 0
    for owner, key in seeds:
        conflicted, reason = chord_collapse_boundary_conflict(cells, owners, owner, key, bnd)
        assert conflicted, f"{key} unexpectedly passed the boundary guard"
        assert "boundary vertex" in reason


def test_chord_collapse_guard_passes_when_no_boundary_node_is_merged() -> None:
    """The guard is a precondition, not a blanket refusal — pin that it can pass."""
    points, cells = _grid(2)
    owners = _face_owners(cells)
    seed = _face_key(cells[0][0])
    conflicted, reason = chord_collapse_boundary_conflict(cells, owners, 0, seed, set())
    assert not conflicted
    assert "no boundary vertex" in reason


# ---------------------------------------------------------------------------
# the transaction
# ---------------------------------------------------------------------------


def test_strict_gate_policy_rejects_every_single_cell_pillow() -> None:
    """Pins the card's headline measured result at unit scale.

    Under the default ``"neighbourhood"`` ceiling a repair may not push its own
    neighbourhood past the project's grade-A thresholds. A single-cell pillow
    inflates all six faces of the owner hex, so its rung faces radiate from the
    inserted inner hex and reliably land above 50 deg non-orthogonality whenever
    the cell was skewed enough to be flagged in the first place. Nothing commits
    — on this fixture, and on cylinder/sphere/gear (see the plan doc's
    "2026-07-26 HEX-MATCH-2 result"). The commit-path tests below therefore run
    on the permissive ``"mesh"`` ceiling; if a future shrink-set change (the
    recommended layer-wide pillow) makes the strict policy commit, this test is
    the one that should start failing.
    """
    points, cells = _damaged_grid()
    _new_pts, _new_cells, report = run_match_repair(
        "damaged", points, cells, gate_policy="neighbourhood"
    )
    assert report.pre.n_flagged > 0
    assert report.n_committed == 0
    assert report.count("rejected_quality") == report.pre.n_flagged - report.count("no_candidate")


def test_repair_never_mutates_its_input() -> None:
    points, cells = _damaged_grid()
    points_before = points.copy()
    cells_before = [[list(f) for f in c] for c in cells]
    run_match_repair("damaged", points, cells)
    assert np.array_equal(points, points_before)
    assert cells == cells_before


def test_repair_commits_and_improves_the_targets_it_commits() -> None:
    points, cells = _damaged_grid()
    new_pts, new_cells, report = run_match_repair("damaged", points, cells, gate_policy="mesh")
    committed = [o for o in report.outcomes if o.status == "committed"]
    assert committed, "expected at least one gated commit on the localized-damage fixture"
    for outcome in committed:
        assert outcome.post_face_skew < outcome.pre_face_skew
    # One pillow = +6 cells, +8 points, and the cells stay valid.
    assert report.post.n_cells == report.pre.n_cells + 6 * len(committed)
    assert report.post.n_points == report.pre.n_points + 8 * len(committed)
    # A pillow subdivides, so the smallest cell necessarily shrinks; what must
    # hold is that nothing inverted.
    assert report.pre.min_signed_volume > 0.0
    assert report.post.min_signed_volume > 0.0
    assert len(new_cells) == report.post.n_cells
    assert new_pts.shape[0] == report.post.n_points


def test_repair_never_moves_a_boundary_vertex() -> None:
    """Section 7.3's invariant for this card, checked on positions, not intent."""
    points, cells = _damaged_grid()
    bnd = sorted(boundary_vertices(_face_owners(cells)))
    new_pts, new_cells, report = run_match_repair("damaged", points, cells, gate_policy="mesh")
    assert report.n_committed > 0
    assert np.array_equal(new_pts[bnd], points[bnd])
    # Every original boundary vertex is still on the boundary afterwards.
    assert set(bnd) <= boundary_vertices(_face_owners(new_cells))


def test_repair_output_is_conforming() -> None:
    points, cells = _damaged_grid()
    _new_pts, new_cells, report = run_match_repair("damaged", points, cells, gate_policy="mesh")
    assert report.n_committed > 0
    multiplicity = Counter(len(o) for o in _face_owners(new_cells).values())
    assert set(multiplicity) <= {1, 2}, "a face ended up shared by 3+ cells"


def test_repair_does_not_regress_global_boundary_skew() -> None:
    points, cells = _damaged_grid()
    _new_pts, _new_cells, report = run_match_repair("damaged", points, cells)
    assert report.post.max_boundary_skew <= report.pre.max_boundary_skew + 1e-9
    assert report.post.max_non_ortho_deg <= max(
        report.pre.max_non_ortho_deg, 50.0
    ) + 1e-9


def test_repair_is_deterministic() -> None:
    points, cells = _damaged_grid()
    first = run_match_repair("damaged", points, cells)
    second = run_match_repair("damaged", points, cells)
    assert np.array_equal(first[0], second[0])
    assert first[1] == second[1]
    assert [o.status for o in first[2].outcomes] == [o.status for o in second[2].outcomes]


def test_repair_is_a_no_op_on_a_clean_mesh() -> None:
    points, cells = _grid(4)
    new_pts, new_cells, report = run_match_repair("clean", points, cells)
    assert report.pre.n_flagged == 0
    assert report.outcomes == ()
    assert report.rounds_run == 0
    assert np.array_equal(new_pts, points)
    assert new_cells == cells


def test_repair_targets_exactly_what_the_diagnostic_reports() -> None:
    """The card's falsification check, at unit scale.

    HEX-MATCH-2's round-0 candidate list must be identical to HEX-MATCH-1's own
    report on the pristine input — same faces, same operation, same footprints.
    The real risk this catches is the executor mutating the caller's arrays
    before the diagnostic view is taken.
    """
    points, cells = _damaged_grid()
    _new_pts, _new_cells, report = run_match_repair("damaged", points, cells)
    diagnostic = run_match_diagnostic("damaged", points, cells)
    assert {
        (c.face_key, c.candidate_type, c.footprint_cells) for c in diagnostic.candidates
    } == {(c.face_key, c.candidate_type, c.footprint_cells) for c in report.round0_candidates}


def test_pass_rollback_restores_the_input_exactly() -> None:
    """Force the whole-pass rollback and check it returns the untouched mesh."""
    points, cells = _damaged_grid()
    committed_run = run_match_repair("damaged", points, cells, gate_policy="mesh")
    assert committed_run[2].n_committed > 0

    # A ceiling of zero makes every global comparison a regression.
    import core.generator.native_hex.match_repair as module

    original = module._grade
    module._grade = lambda no, skew, n: "A" if n == len(cells) else "D"
    try:
        new_pts, new_cells, report = run_match_repair("damaged", points, cells, gate_policy="mesh")
    finally:
        module._grade = original
    assert report.pass_rolled_back
    assert "grade dropped" in report.rollback_reason
    assert np.array_equal(new_pts, points)
    assert new_cells == cells
    assert report.post == report.pre


# ---------------------------------------------------------------------------
# metric fidelity — the two match_diagnostic bugs this card found
# ---------------------------------------------------------------------------


def test_face_normal_is_area_weighted_over_the_cyclic_order() -> None:
    """Regression test for the sorted-key / first-triangle normal bug.

    On a warped quad the checker's area-weighted fan normal and the old
    first-triangle-of-the-sorted-key normal genuinely disagree, and the old one
    is not the face's normal at all when the sorted order is the bow-tie
    diagonal.
    """
    warped = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0.8], [0, 1, 0]],
        dtype=np.float64,
    )
    cyclic = [0, 1, 2, 3]
    _cen, n_area, area = face_centroid_normal_area(warped, cyclic)
    first_triangle = np.cross(warped[1] - warped[0], warped[2] - warped[0])
    first_triangle /= np.linalg.norm(first_triangle)
    assert not np.allclose(n_area, first_triangle, atol=1e-3)
    # The area-weighted normal is the mean of both fan triangles, so it must sit
    # between them, and the reported area must be the sum of the two.
    second = np.cross(warped[2] - warped[0], warped[3] - warped[0])
    expected = first_triangle * np.linalg.norm(
        np.cross(warped[1] - warped[0], warped[2] - warped[0])
    ) + second
    expected /= np.linalg.norm(expected)
    assert np.allclose(n_area, expected)
    assert area == pytest.approx(
        0.5
        * np.linalg.norm(
            np.cross(warped[1] - warped[0], warped[2] - warped[0])
            + np.cross(warped[2] - warped[0], warped[3] - warped[0])
        )
    )


def test_cell_centroid_matches_the_checker_and_is_a_no_op_for_hexes() -> None:
    """Pins both halves of the centroid fidelity fix.

    For a topological hex the mean of face centres and the mean of vertices are
    identical — every vertex lies on exactly 3 of the 6 faces — so this change
    provably moves no number on this card's all-hex fixtures. It is not vacuous:
    for a cell with unequal vertex face-degree (a pyramid here, octree
    transition polyhedra in production) the two genuinely differ, and the
    checker uses the face-centre mean.
    """
    cells = _single_cell()
    for fixture in (_UNIT_HEX, _SHEARED_HEX, _FRUSTUM_HEX):
        centroid = _cell_centroid(fixture, cells[0])
        face_centres = np.array(
            [fixture[np.asarray(f, dtype=np.int64)].mean(axis=0) for f in cells[0]]
        )
        assert np.allclose(centroid, face_centres.mean(axis=0))
        assert np.allclose(centroid, fixture.mean(axis=0))

    pyramid_pts = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0.2, 0.3, 1]], dtype=np.float64
    )
    pyramid = [[0, 3, 2, 1], [0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]
    centroid = _cell_centroid(pyramid_pts, pyramid)
    face_centres = np.array(
        [pyramid_pts[np.asarray(f, dtype=np.int64)].mean(axis=0) for f in pyramid]
    )
    assert np.allclose(centroid, face_centres.mean(axis=0))
    assert not np.allclose(centroid, pyramid_pts.mean(axis=0))


def test_gate_ceiling_floors_at_the_projects_own_grade_a_thresholds() -> None:
    points, cells = _grid(4)
    ceiling = GateCeiling.from_mesh(mesh_quality(points, cells))
    assert ceiling.max_internal_skew >= 1.0
    assert ceiling.max_non_ortho_deg >= 50.0
