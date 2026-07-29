"""Phase 0 native_poly quality measurements and aspect-gate audit."""

from __future__ import annotations

import numpy as np
import pytest

from core.evaluator.native_checker import NativeMeshChecker
from core.evaluator.poly_quality_metrics import (
    _face_planarity_and_normal_spread,
    compute_poly_phase0_metrics,
)
from core.evaluator.report import get_thresholds


def _unit_cube_geometry() -> tuple[np.ndarray, list[list[int]]]:
    points = np.asarray(
        [
            (-0.5, -0.5, -0.5),
            (0.5, -0.5, -0.5),
            (0.5, 0.5, -0.5),
            (-0.5, 0.5, -0.5),
            (-0.5, -0.5, 0.5),
            (0.5, -0.5, 0.5),
            (0.5, 0.5, 0.5),
            (-0.5, 0.5, 0.5),
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2, 3],
        [4, 7, 6, 5],
        [0, 4, 5, 1],
        [1, 5, 6, 2],
        [2, 6, 7, 3],
        [3, 7, 4, 0],
    ]
    return points, faces


def test_phase0_cube_metrics_have_analytic_values() -> None:
    points, faces = _unit_cube_geometry()
    checker = NativeMeshChecker()
    face_centres = checker._compute_face_centres(points, faces)
    face_normals, face_areas = checker._compute_face_normals_areas(points, faces)

    report = compute_poly_phase0_metrics(
        points,
        faces,
        np.zeros(6, dtype=np.int64),
        np.empty(0, dtype=np.int64),
        0,
        np.zeros((1, 3), dtype=np.float64),
        face_centres,
        face_normals,
        face_areas,
        np.ones(1, dtype=np.float64),
    )

    assert report.max_face_planar_deviation == pytest.approx(0.0, abs=1e-14)
    assert report.max_face_normal_spread_deg == pytest.approx(0.0, abs=1e-12)
    assert report.min_cell_h == pytest.approx(1.0)
    assert report.mean_cell_h == pytest.approx(1.0)
    assert report.min_circle_ratio == pytest.approx(1.0 / np.sqrt(3.0))
    assert report.min_sphericity == pytest.approx((np.pi / 6.0) ** (1.0 / 3.0))
    assert report.min_uniformity_factor == pytest.approx(1.0)
    assert report.min_face_pairing_residual == pytest.approx(0.0, abs=1e-14)
    assert report.max_face_pairing_residual == pytest.approx(0.0, abs=1e-14)


def test_phase0_warped_face_reports_planar_deviation_and_normal_spread() -> None:
    warped = np.asarray(
        [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.2), (-1.0, 1.0, 0.0)],
        dtype=np.float64,
    )
    deviation, spread = _face_planarity_and_normal_spread(warped, [0, 1, 2, 3])

    assert deviation > 0.0
    assert spread > 0.0


def test_phase0_juretic_psi_exposes_internal_gate_definition() -> None:
    report = compute_poly_phase0_metrics(
        np.empty((0, 3), dtype=np.float64),
        [],
        np.asarray([0], dtype=np.int64),
        np.asarray([1], dtype=np.int64),
        1,
        np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype=np.float64),
        np.asarray([[1.0, 0.2, 0.0]], dtype=np.float64),
        np.asarray([[1.0, 0.0, 0.0]], dtype=np.float64),
        np.asarray([1.0], dtype=np.float64),
        np.ones(2, dtype=np.float64),
    )

    # d = 2 and the line/face miss is 0.2, hence psi = |m|/|d| = 0.1.
    assert report.max_juretic_psi == pytest.approx(0.1)


def test_phase0_face_pairing_distinguishes_cube_like_and_tet_like_cells() -> None:
    from core.evaluator.poly_quality_metrics import _face_pairing_residual

    cube_normals = np.asarray(
        [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]],
        dtype=np.float64,
    )
    cube_areas = np.ones(6, dtype=np.float64)
    tet_normals = np.asarray(
        [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]],
        dtype=np.float64,
    )
    tet_normals /= np.linalg.norm(tet_normals, axis=1)[:, None]
    tet_areas = np.ones(4, dtype=np.float64)

    assert _face_pairing_residual(cube_normals, cube_areas, list(range(6))) == pytest.approx(0.0)
    assert _face_pairing_residual(tet_normals, tet_areas, list(range(4))) > 0.1


def test_native_checker_wires_phase0_fields_into_checkmesh_report(tmp_path) -> None:
    from core.generator.polymesh_writer import PolyMeshWriter

    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    cells = np.asarray([[0, 1, 2, 3]], dtype=np.int64)
    PolyMeshWriter().write(vertices, cells, tmp_path)

    result = NativeMeshChecker().run(tmp_path)

    assert result.max_face_planar_deviation is not None
    assert result.max_face_normal_spread_deg is not None
    assert result.max_juretic_psi == pytest.approx(0.0)
    assert result.min_cell_h is not None
    assert result.min_circle_ratio is not None
    assert result.min_sphericity is not None
    assert result.min_uniformity_factor is not None
    assert result.skewness_formula_audit is not None


@pytest.mark.parametrize(
    ("quality_level", "aspect_ratio", "accepted"),
    [
        ("draft", 1.0e3, True),
        ("draft", 1.0e6, False),
        ("standard", 1.0e2, True),
        ("standard", 1.0e6, False),
        ("fine", 1.0e2, True),
        ("fine", 1.0e6, False),
    ],
)
def test_synthetic_bl_aspect_gate_audit_is_accept_reject_only(
    quality_level: str,
    aspect_ratio: float,
    accepted: bool,
) -> None:
    """Audit current aspect gate on aligned BL-like stretching, without changing it."""
    threshold = float(get_thresholds(quality_level)["soft_aspect_ratio"])
    current_gate_accepts = aspect_ratio <= threshold
    assert current_gate_accepts is accepted
