"""Log-only HEX-MATCH-1 targeting-diagnostic tests.

Synthetic hex meshes only (no full pipeline run) — this exercises the
decision-logic branches directly and cheaply: clean interior column-collapse,
thru-boundary pillow fallback, self-intersecting-column pillow fallback,
non-hex-owner rejection, and footprint-conflict rejection. None of these tests
mutate a mesh; ``classify_repair_candidates``/``run_match_diagnostic`` are
pure read-only targeting logic by construction (HEX-MATCH-1, diagnostic-only
per the round-2 synthesis in
``native_hex_literature_integrated_development_plan_2026-07-23.md`` section 7).
"""

from __future__ import annotations

import numpy as np

from core.generator.native_hex.match_diagnostic import (
    BoundaryFaceSkew,
    classify_repair_candidates,
    compute_boundary_face_skew,
    flag_bad_skew_faces,
    run_match_diagnostic,
)

CellFaces = list[list[list[int]]]


def _vid(i: int, j: int, k: int) -> int:
    return i * 4 + j * 2 + k


def _strip_grid(n_cells: int) -> tuple[np.ndarray, CellFaces]:
    """An axis-aligned n_cells x 1 x 1 unit-hex strip along +x.

    A perfectly regular grid: every internal/boundary face is planar and
    every cell is a unit cube, so OpenFOAM-style skewness is ~0 everywhere —
    a clean "no false positive" fixture, and its combinatorial column
    structure (opposite-face pairing along x) is exact.
    """
    n_pts = (n_cells + 1) * 4
    points = np.zeros((n_pts, 3), dtype=np.float64)
    for i in range(n_cells + 1):
        for j in range(2):
            for k in range(2):
                points[_vid(i, j, k)] = (float(i), float(j), float(k))

    cells: CellFaces = []
    for i in range(n_cells):
        c000, c100 = _vid(i, 0, 0), _vid(i + 1, 0, 0)
        c010, c110 = _vid(i, 1, 0), _vid(i + 1, 1, 0)
        c001, c101 = _vid(i, 0, 1), _vid(i + 1, 0, 1)
        c011, c111 = _vid(i, 1, 1), _vid(i + 1, 1, 1)
        bottom = [c000, c100, c110, c010]  # z=0
        top = [c001, c101, c111, c011]  # z=1
        front = [c000, c100, c101, c001]  # y=0
        back = [c010, c110, c111, c011]  # y=1
        left = [c000, c010, c011, c001]  # x=i
        right = [c100, c110, c111, c101]  # x=i+1
        cells.append([bottom, top, front, back, left, right])
    return points, cells


def _face_key(face: list[int]) -> tuple[int, ...]:
    return tuple(sorted(face))


def test_regular_strip_has_no_flagged_faces() -> None:
    """A perfectly axis-aligned grid must not produce false-positive flags."""
    points, cells = _strip_grid(4)
    report = run_match_diagnostic("regular_strip", points, cells)
    assert report.n_boundary_faces > 0
    assert report.n_flagged == 0
    assert report.candidates == ()


def test_deep_clean_column_selects_collapse() -> None:
    """4-cell strip, depth-2 trace never reaches a boundary -> collapse."""
    points, cells = _strip_grid(4)
    left_face = _face_key(cells[0][4])  # cell 0's left (x=0) face — a real boundary face.
    flagged = [BoundaryFaceSkew(face_key=left_face, owner_cell=0, skewness=3.0, area=1.0)]
    candidates = classify_repair_candidates(points, cells, flagged, max_depth=2)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.candidate_type == "collapse"
    assert cand.footprint_cells == (0, 1, 2)
    assert cand.depth_used == 2


def test_short_thru_column_falls_back_to_pillow() -> None:
    """3-cell strip, depth-3 trace exits into the far boundary -> pillow."""
    points, cells = _strip_grid(3)
    left_face = _face_key(cells[0][4])
    flagged = [BoundaryFaceSkew(face_key=left_face, owner_cell=0, skewness=3.0, area=1.0)]
    candidates = classify_repair_candidates(points, cells, flagged, max_depth=3)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.candidate_type == "pillow"
    assert cand.footprint_cells == (0,)
    assert "boundary patch" in cand.reason


def test_footprint_conflict_yields_no_candidate() -> None:
    """Two flagged faces on the same isolated cell -> the second gets 'none'."""
    points, cells = _strip_grid(1)
    left_face = _face_key(cells[0][4])
    front_face = _face_key(cells[0][2])
    flagged = [
        BoundaryFaceSkew(face_key=left_face, owner_cell=0, skewness=3.0, area=1.0),
        BoundaryFaceSkew(face_key=front_face, owner_cell=0, skewness=2.5, area=1.0),
    ]
    candidates = classify_repair_candidates(points, cells, flagged, max_depth=2)
    assert len(candidates) == 2
    assert candidates[0].candidate_type == "pillow"
    assert candidates[1].candidate_type == "none"
    assert "already claimed" in candidates[1].reason


def test_non_hex_owner_yields_no_candidate() -> None:
    """A transition polyhedron (5 faces) owner has no defined Staten operator."""
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]], dtype=np.float64)
    prism_like = [
        [0, 1, 2],
        [0, 1, 3],
        [1, 2, 3],
        [0, 2, 3],
        [1, 2, 4],
    ]  # 5 triangular faces — deliberately not a 6-quad hex.
    cells: CellFaces = [prism_like]
    flagged = [BoundaryFaceSkew(face_key=(0, 1, 2), owner_cell=0, skewness=5.0, area=1.0)]
    candidates = classify_repair_candidates(points, cells, flagged, max_depth=2)
    assert len(candidates) == 1
    assert candidates[0].candidate_type == "none"
    assert "not a clean hex" in candidates[0].reason


def test_self_intersecting_column_falls_back_to_pillow() -> None:
    """Synthetic degenerate 2-cell 'torus' where the column loops back to cell 0.

    Not a realistic boundary flag (F_a is shared, not a true boundary face
    here) — this isolates and directly exercises the self-intersection guard,
    Staten 2010's own named doublet-risk exception, independent of real mesh
    geometry (the check is purely combinatorial on face vertex sets).
    """
    points = np.zeros((8, 3), dtype=np.float64)
    f_a = [0, 1, 2, 3]
    f_b = [4, 5, 6, 7]
    f_c = [0, 1, 5, 4]
    f_d = [3, 2, 6, 7]
    f_e = [0, 3, 7, 4]
    f_f = [1, 2, 6, 5]
    cell0 = [f_a, f_b, f_c, f_d, f_e, f_f]
    # cell1 reuses cell0's vertex ids with F_a and F_b swapped in role, so the
    # column direction wraps back onto cell0 after two hops.
    cell1 = [f_b, f_a, f_c, f_d, f_e, f_f]
    cells: CellFaces = [cell0, cell1]
    flagged = [BoundaryFaceSkew(face_key=_face_key(f_a), owner_cell=0, skewness=4.0, area=1.0)]
    candidates = classify_repair_candidates(points, cells, flagged, max_depth=3)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.candidate_type == "pillow"
    assert cand.footprint_cells == (0,)
    assert "self-intersecting" in cand.reason


def test_compute_boundary_face_skew_zero_on_regular_grid() -> None:
    points, cells = _strip_grid(2)
    faces = compute_boundary_face_skew(points, cells)
    assert faces
    assert all(f.skewness < 1e-9 for f in faces)
    assert flag_bad_skew_faces(faces, threshold=2.0) == []
