"""Report-only TET-THIN-SECTION-1 diagnostics."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.thin_section import estimate_boundary_thickness


def _box_mesh(height: float) -> tuple[np.ndarray, np.ndarray]:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, height],
            [1.0, 0.0, height],
            [1.0, 1.0, height],
            [0.0, 1.0, height],
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [
            [0, 1, 3, 4],
            [1, 2, 3, 6],
            [1, 3, 4, 6],
            [1, 4, 5, 6],
            [3, 4, 6, 7],
        ],
        dtype=np.int64,
    )
    return points, tets


def test_thin_section_census_detects_box_thickness() -> None:
    points, tets = _box_mesh(0.05)
    before_points = points.copy()
    before_tets = tets.copy()

    report = estimate_boundary_thickness(points, tets)

    assert report.n_boundary_faces == 12
    assert report.n_ray_hits > 0
    assert report.min_thickness is not None
    assert report.min_thickness >= 0.049999
    assert report.min_thickness <= 0.050001
    assert report.min_through_thickness_cells is not None
    assert report.min_through_thickness_cells >= 1
    assert report.max_through_thickness_cells is not None
    assert report.max_through_thickness_cells >= report.min_through_thickness_cells
    assert len(report.through_thickness_cell_counts) == report.n_ray_hits
    assert np.array_equal(points, before_points)
    assert np.array_equal(tets, before_tets)


def test_thin_section_census_is_deterministic() -> None:
    points, tets = _box_mesh(1.0)

    first = estimate_boundary_thickness(points, tets).as_dict()
    second = estimate_boundary_thickness(points, tets).as_dict()

    assert first == second
    assert first["n_boundary_faces"] == 12
    assert first["min_thickness"] is not None
    assert first["min_thickness"] >= 0.999999
    assert first["max_thickness"] <= 1.000001
    assert first["min_through_thickness_cells"] >= 1
    assert first["max_through_thickness_cells"] >= first["min_through_thickness_cells"]


def test_open_or_empty_mesh_reports_unknown_without_guessing() -> None:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)

    report = estimate_boundary_thickness(points, tets)

    assert report.n_boundary_faces == 4
    assert report.n_ray_hits == 0
    assert report.n_unknown_rays == 4
    assert report.min_thickness is None
    assert report.min_through_thickness_cells is None
    assert report.through_thickness_cell_counts == ()
