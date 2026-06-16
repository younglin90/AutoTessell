"""Parity checks for the optional native_metrics C++ kernels."""

from __future__ import annotations

import numpy as np
import pytest

from core.evaluator import native_checker as nc
from core.evaluator.native_checker import NativeMeshChecker


def _native_metrics_or_skip():
    module = nc._load_native_metrics()
    if module is None:
        pytest.skip("native_metrics extension is not built")
    return module


def test_native_metrics_face_geometry_matches_python() -> None:
    _native_metrics_or_skip()
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [0, 2, 3],
        [1, 4, 2],
        [1, 3, 4, 2],
    ]

    cpp = NativeMeshChecker._compute_face_geometry(points, faces)
    assert cpp is not None
    centres_cpp, normals_cpp, areas_cpp = cpp

    centres_py = NativeMeshChecker._compute_face_centres(points, faces)
    normals_py, areas_py = NativeMeshChecker._compute_face_normals_areas(points, faces)

    np.testing.assert_allclose(centres_cpp, centres_py, rtol=0.0, atol=1e-15)
    np.testing.assert_allclose(normals_cpp, normals_py, rtol=0.0, atol=1e-15)
    np.testing.assert_allclose(areas_cpp, areas_py, rtol=0.0, atol=1e-15)


def test_native_metrics_cell_centres_match_python_fallback() -> None:
    _native_metrics_or_skip()
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [0, 2, 3],
        [1, 3, 4, 2],
    ]
    owner = np.array([0, 0, 0, 1], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    n_cells = 2

    centres_cpp = NativeMeshChecker._compute_cell_centres_from_vertices(
        points, faces, owner, n_cells, neighbour
    )

    old_module = nc._NATIVE_METRICS
    old_attempted = nc._NATIVE_METRICS_IMPORT_ATTEMPTED
    try:
        nc._NATIVE_METRICS = None
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = True
        centres_py = NativeMeshChecker._compute_cell_centres_from_vertices(
            points, faces, owner, n_cells, neighbour
        )
    finally:
        nc._NATIVE_METRICS = old_module
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = old_attempted

    np.testing.assert_allclose(centres_cpp, centres_py, rtol=0.0, atol=1e-15)


def test_native_metrics_quality_metrics_match_python_fallback() -> None:
    _native_metrics_or_skip()
    checker = NativeMeshChecker()
    face_centres = np.array(
        [
            [0.5, 0.0, 0.0],
            [0.5, 1.0, 0.0],
            [0.5, 0.5, 0.2],
            [0.0, 0.5, 0.0],
        ],
        dtype=np.float64,
    )
    face_normals = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.8, 0.2, 0.0],
            [0.0, 0.0, 1.0],
            [-1.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    cell_centres = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.1, 0.0],
            [0.9, 1.0, 0.1],
        ],
        dtype=np.float64,
    )
    owner = np.array([0, 1, 0, 0], dtype=np.int64)
    neighbour = np.array([1, 2, 2], dtype=np.int64)
    n_internal = 3

    non_ortho_cpp = checker._compute_non_orthogonality(
        face_centres, face_normals, cell_centres, owner, neighbour, n_internal
    )
    skew_cpp = checker._compute_skewness(
        face_centres, cell_centres, owner, neighbour, n_internal
    )
    boundary_skew_cpp = checker._compute_boundary_skewness(
        face_centres, face_normals, cell_centres, owner, n_internal
    )

    old_module = nc._NATIVE_METRICS
    old_attempted = nc._NATIVE_METRICS_IMPORT_ATTEMPTED
    try:
        nc._NATIVE_METRICS = None
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = True
        non_ortho_py = checker._compute_non_orthogonality(
            face_centres, face_normals, cell_centres, owner, neighbour, n_internal
        )
        skew_py = checker._compute_skewness(
            face_centres, cell_centres, owner, neighbour, n_internal
        )
        boundary_skew_py = checker._compute_boundary_skewness(
            face_centres, face_normals, cell_centres, owner, n_internal
        )
    finally:
        nc._NATIVE_METRICS = old_module
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = old_attempted

    np.testing.assert_allclose(non_ortho_cpp, non_ortho_py, rtol=0.0, atol=1e-12)
    assert skew_cpp == pytest.approx(skew_py, abs=1e-15)
    assert boundary_skew_cpp == pytest.approx(boundary_skew_py, abs=1e-15)


def test_native_metrics_cell_volumes_match_python_fallback() -> None:
    _native_metrics_or_skip()
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [0, 2, 3],
        [1, 3, 4, 2],
    ]
    owner = np.array([0, 0, 0, 1], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    n_cells = 2
    n_internal = 1

    face_geometry = NativeMeshChecker._compute_face_geometry(points, faces)
    assert face_geometry is not None
    face_centres, face_normals, face_areas = face_geometry
    cell_centres = NativeMeshChecker._compute_cell_centres_from_vertices(
        points, faces, owner, n_cells, neighbour
    )

    volumes_cpp, negative_cpp = NativeMeshChecker._compute_cell_volumes(
        points,
        faces,
        face_normals,
        face_areas,
        owner,
        neighbour,
        n_cells,
        n_internal,
        cell_centres,
        face_centres,
    )

    old_module = nc._NATIVE_METRICS
    old_attempted = nc._NATIVE_METRICS_IMPORT_ATTEMPTED
    try:
        nc._NATIVE_METRICS = None
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = True
        volumes_py, negative_py = NativeMeshChecker._compute_cell_volumes(
            points,
            faces,
            face_normals,
            face_areas,
            owner,
            neighbour,
            n_cells,
            n_internal,
            cell_centres,
            face_centres,
        )
    finally:
        nc._NATIVE_METRICS = old_module
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = old_attempted

    np.testing.assert_allclose(volumes_cpp, volumes_py, rtol=0.0, atol=1e-15)
    assert negative_cpp == negative_py
