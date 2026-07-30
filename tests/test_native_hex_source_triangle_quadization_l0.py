"""L0 contracts for the report-only exact source triangle quadizer."""

from __future__ import annotations

import numpy as np

from core.generator.native_hex.source_triangle_quadization_l0 import (
    all_quad_ball_precheck_l1,
    quadize_triangles_exact_l0,
)


_TETRA_POINTS = np.array(
    ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
)
_TETRA_FACES = np.array(((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)), dtype=np.int64)


def test_closed_oriented_tetrahedron_becomes_exact_three_quads_per_triangle() -> None:
    points, faces = _TETRA_POINTS.copy(), _TETRA_FACES.copy()
    result = quadize_triangles_exact_l0(points, faces, (("solid", "wall"),) * len(faces))

    assert result.accepted
    assert result.reason == "accepted_exact_three_quad_subdivision"
    assert len(result.quads) == 3 * len(faces)
    assert np.array_equal(result.points[: len(points)], points)
    assert np.array_equal(points, _TETRA_POINTS)
    assert np.array_equal(faces, _TETRA_FACES)
    assert result.max_support_distance == 0.0
    assert result.max_relative_area_error == 0.0
    assert all_quad_ball_precheck_l1(result.points, result.quads) == (True, 2)


def test_rejects_open_inconsistently_oriented_and_degenerate_source_triangles() -> None:
    entities = (("solid", "wall"),) * len(_TETRA_FACES)
    open_result = quadize_triangles_exact_l0(_TETRA_POINTS, _TETRA_FACES[:3], entities[:3])
    inconsistent = _TETRA_FACES.copy()
    inconsistent[0] = inconsistent[0, ::-1]
    inconsistent_result = quadize_triangles_exact_l0(_TETRA_POINTS, inconsistent, entities)
    degenerate = _TETRA_FACES.copy()
    degenerate[0] = (0, 0, 1)
    degenerate_result = quadize_triangles_exact_l0(_TETRA_POINTS, degenerate, entities)

    assert not open_result.accepted and open_result.reason == "source_not_oriented_closed_manifold"
    assert not inconsistent_result.accepted and inconsistent_result.reason == "source_not_oriented_closed_manifold"
    assert not degenerate_result.accepted and degenerate_result.reason == "source_not_oriented_closed_manifold"


def test_quadization_is_deterministic_and_rejects_nonintegral_connectivity() -> None:
    entities = (("solid", "wall"),) * len(_TETRA_FACES)
    first = quadize_triangles_exact_l0(_TETRA_POINTS, _TETRA_FACES, entities)
    second = quadize_triangles_exact_l0(_TETRA_POINTS, _TETRA_FACES, entities)
    rejected = quadize_triangles_exact_l0(_TETRA_POINTS, _TETRA_FACES.astype(float), entities)

    assert np.array_equal(first.points, second.points)
    assert np.array_equal(first.quads, second.quads)
    assert np.array_equal(first.source_face_ids, second.source_face_ids)
    assert not rejected.accepted and rejected.reason == "invalid_source_input"
