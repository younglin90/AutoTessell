"""BLR-9c-d-p-9 — anti-invert cap helper unit tests."""
from __future__ import annotations

import numpy as np

from core.layers.native_bl_anti_invert import compute_anti_invert_caps


def _single_tet_polymesh():
    """Build a 1-cell polyMesh of the canonical tet (0,0,0)-(1,0,0)-(0,1,0)-(0,0,1).

    Faces (each outward-CCW from cell 0 by inspection):
      F0 = (0, 1, 2)  — z = 0 base, normal = (0,0,-1) outward.
      F1 = (0, 3, 1)  — y = 0, normal = (0,-1,0) outward.
      F2 = (1, 3, 2)  — x+y+z=1, normal = (1,1,1)/√3 outward.
      F3 = (2, 3, 0)  — x = 0, normal = (-1,0,0) outward.
    All boundary (no neighbour).
    """
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    return points, faces, owner, neighbour


def test_anti_invert_cap_inward_motion_caps_at_distance_to_opposite_face() -> None:
    """Wall vertex 0 = (0,0,0), motion = +(1,1,1)/√3 (toward the
    x+y+z=1 face).  Geometric: vertex 0 reaches that plane at
    distance 1/√3 ≈ 0.577 along the unit motion direction.  With
    0.95 safety the cap should be ≈ 0.548."""
    pts, faces, own, nbr = _single_tet_polymesh()
    motion = {0: np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0)}
    caps = compute_anti_invert_caps(
        pts, faces, own, nbr, [0], motion,
        safety_factor=0.95,
    )
    # cap[0] is the distance from vertex 0 to the opposite face,
    # times safety. The other three faces are not "opposite to
    # vertex 0" (they all contain vertex 0).
    expected = (1.0 / np.sqrt(3.0)) * 0.95
    assert abs(caps[0] - expected) < 1e-6


def test_anti_invert_cap_outward_motion_returns_infinity() -> None:
    """Motion pointing away from the opposite face plane never
    causes inversion → cap should be ``inf``."""
    pts, faces, own, nbr = _single_tet_polymesh()
    motion = {0: -np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0)}
    caps = compute_anti_invert_caps(
        pts, faces, own, nbr, [0], motion,
    )
    assert caps[0] == float("inf")


def test_anti_invert_cap_zero_motion_returns_infinity() -> None:
    """Zero-magnitude motion direction → cap = inf (no extrusion
    means no inversion can occur)."""
    pts, faces, own, nbr = _single_tet_polymesh()
    motion = {0: np.zeros(3)}
    caps = compute_anti_invert_caps(
        pts, faces, own, nbr, [0], motion,
    )
    assert caps[0] == float("inf")


def test_anti_invert_cap_takes_min_over_adjacent_tets() -> None:
    """Two tets sharing wall vertex 0; the helper picks the
    *minimum* safe extrusion distance across both."""
    # Two tets pointing in different directions, sharing vertex 0.
    # Tet A: 0(0,0,0), 1(1,0,0), 2(0,1,0), 3(0,0,1)  → opposite of 0 is the (1,2,3) face plane x+y+z=1.
    # Tet B: 0(0,0,0), 4(2,0,0), 5(0,2,0), 6(0,0,2)  → opposite of 0 is plane x+y+z=2 (further away).
    points = np.array(
        [
            [0.0, 0.0, 0.0],   # 0
            [1.0, 0.0, 0.0],   # 1
            [0.0, 1.0, 0.0],   # 2
            [0.0, 0.0, 1.0],   # 3
            [2.0, 0.0, 0.0],   # 4
            [0.0, 2.0, 0.0],   # 5
            [0.0, 0.0, 2.0],   # 6
        ],
        dtype=np.float64,
    )
    # Both tets, all faces boundary.
    faces = [
        # Tet A
        [0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0],
        # Tet B
        [0, 4, 5], [0, 6, 4], [4, 6, 5], [5, 6, 0],
    ]
    owner = np.array([0, 0, 0, 0, 1, 1, 1, 1], dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    motion = {0: np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0)}
    caps = compute_anti_invert_caps(
        points, faces, owner, neighbour, [0], motion,
        safety_factor=1.0,
    )
    # Tet A constraint: distance 1/√3 ≈ 0.577.
    # Tet B constraint: distance 2/√3 ≈ 1.155.
    # Min wins → cap[0] ≈ 0.577 (with safety 1.0).
    assert abs(caps[0] - (1.0 / np.sqrt(3.0))) < 1e-6


def test_anti_invert_cap_no_motion_dir_for_vertex_returns_infinity() -> None:
    """A wall vertex with no entry in motion_dirs → cap = inf."""
    pts, faces, own, nbr = _single_tet_polymesh()
    caps = compute_anti_invert_caps(
        pts, faces, own, nbr, [1], {},   # vertex 1 not in motion_dirs
    )
    assert caps[1] == float("inf")
