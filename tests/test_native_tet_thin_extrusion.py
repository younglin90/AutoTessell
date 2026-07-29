"""Extreme extrusion wedge rescue regressions."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.thin_extrusion import (
    build_thin_extrusion_wedges,
)


def _box_surface(extents: tuple[float, float, float]) -> tuple[np.ndarray, np.ndarray]:
    x, y, z = extents
    points = np.array(
        [
            [0, 0, 0], [x, 0, 0], [x, y, 0], [0, y, 0],
            [0, 0, z], [x, 0, z], [x, y, z], [0, y, z],
        ],
        dtype=np.float64,
    )
    faces = np.array(
        [
            [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
            [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
        ],
        dtype=np.int64,
    )
    return points, faces


def test_flat_extrusion_refines_cap_and_uses_three_slabs() -> None:
    points, faces = _box_surface((2.0, 2.0, 0.01))

    mesh = build_thin_extrusion_wedges(points, faces, target_cells=200)

    assert mesh is not None
    assert mesh.extrusion_axis == 2
    assert mesh.n_slabs == 3
    assert mesh.n_cap_triangles > 2
    assert len(mesh.cell_faces) == mesh.n_slabs * mesh.n_cap_triangles


def test_nearly_axis_aligned_thin_plate_uses_pca_cap_detection() -> None:
    points, faces = _box_surface((2.0, 2.0, 0.01))
    angle = np.deg2rad(1.0)
    rotate_x = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, np.cos(angle), -np.sin(angle)],
            [0.0, np.sin(angle), np.cos(angle)],
        ],
        dtype=np.float64,
    )
    rotate_y = np.array(
        [
            [np.cos(angle), 0.0, np.sin(angle)],
            [0.0, 1.0, 0.0],
            [-np.sin(angle), 0.0, np.cos(angle)],
        ],
        dtype=np.float64,
    )
    points = points @ rotate_x.T @ rotate_y.T

    mesh = build_thin_extrusion_wedges(points, faces, target_cells=200)

    assert mesh is not None
    assert mesh.extrusion_axis == 2
    assert mesh.n_cap_triangles > 2


def test_long_extrusion_uses_budget_for_axial_slabs() -> None:
    points, faces = _box_surface((0.02, 0.02, 10.0))

    mesh = build_thin_extrusion_wedges(points, faces, target_cells=200)

    assert mesh is not None
    assert mesh.extrusion_axis == 2
    predicted_final = len(mesh.cell_faces) + 4 * mesh.n_cap_triangles
    assert predicted_final == 200


def test_compact_geometry_does_not_activate_extrusion_rescue() -> None:
    points, faces = _box_surface((1.0, 1.0, 1.0))

    assert build_thin_extrusion_wedges(points, faces, target_cells=200) is None
