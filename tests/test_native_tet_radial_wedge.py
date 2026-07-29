"""Radial sphere wedge rescue regressions."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.radial_wedge import build_radial_wedges


def _octahedron() -> tuple[np.ndarray, np.ndarray]:
    points = np.array(
        [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]],
        dtype=np.float64,
    )
    faces = np.array(
        [[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4],
         [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]],
        dtype=np.int64,
    )
    return points, faces


def test_sphere_builds_star_core_and_radial_shells() -> None:
    points, faces = _octahedron()

    mesh = build_radial_wedges(points, faces)

    assert mesh is not None
    assert mesh.n_components == 1
    assert mesh.n_radial_shells == 3
    assert len(mesh.cell_faces) == 4 * len(faces)


def test_tiny_convex_component_is_preserved_as_poly_cell() -> None:
    points, faces = _octahedron()
    tiny = 0.01 * np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64
    ) + np.array([2.0, 0.0, 0.0])
    tiny_faces = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]])

    mesh = build_radial_wedges(
        np.vstack((points, tiny)),
        np.vstack((faces, tiny_faces + len(points))),
    )

    assert mesh is not None
    assert mesh.n_components == 2
    assert len(mesh.cell_faces) == 4 * len(faces) + 1


def test_radial_shell_count_tracks_final_cell_budget() -> None:
    points, faces = _octahedron()

    mesh = build_radial_wedges(
        points,
        faces,
        target_cells=100,
        bl_layers=3,
    )

    assert mesh is not None
    predicted_final = len(mesh.cell_faces) + 3 * mesh.n_sphere_faces
    assert 85 <= predicted_final <= 115
