"""Regression coverage for wall-fit zero-thickness-cell rejection."""

from __future__ import annotations

import numpy as np

from core.generator.native_hex.mesher import _wall_fit_snap


def _quad_area(points: np.ndarray, face: list[int]) -> float:
    p = points[np.asarray(face, dtype=np.int64)]
    base = p[0]
    return sum(
        0.5 * float(np.linalg.norm(np.cross(p[i] - base, p[i + 1] - base)))
        for i in range(1, len(face) - 1)
    )


def test_wall_fit_rejects_zero_thickness_candidate() -> None:
    # One hex whose lower layer is close to a planar surface.  Without the
    # candidate face-area guard, sequential projections can move the lower
    # layer onto z=1 and leave a zero-area side/bottom face.
    points = np.asarray(
        [
            [-0.5, -0.5, 0.5],
            [0.5, -0.5, 0.5],
            [0.5, 0.5, 0.5],
            [-0.5, 0.5, 0.5],
            [-0.5, -0.5, 1.0],
            [0.5, -0.5, 1.0],
            [0.5, 0.5, 1.0],
            [-0.5, 0.5, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 3, 2, 1],
        [4, 5, 6, 7],
        [0, 1, 5, 4],
        [3, 7, 6, 2],
        [0, 4, 7, 3],
        [1, 2, 6, 5],
    ]
    surface_vertices = np.asarray(
        [[-2.0, -2.0, 1.0], [2.0, -2.0, 1.0], [-2.0, 2.0, 1.0], [2.0, 2.0, 1.0]],
        dtype=np.float64,
    )
    surface_faces = np.asarray([[0, 1, 2], [1, 3, 2]], dtype=np.int64)

    out, stats = _wall_fit_snap(
        points,
        [faces],
        surface_vertices,
        surface_faces,
        target_edge=1.0,
        tol=0.01,
        ratio=2.0,
        iters=3,
    )

    assert stats["n_snapped"] + stats["n_snapped_partial"] > 0
    assert stats["n_snapped_partial"] > 0
    assert all(_quad_area(out, face) > 1e-12 for face in faces)
