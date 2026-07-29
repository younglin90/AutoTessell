"""Exact source-complex canonicalization contracts."""

from __future__ import annotations

from core.generator.native_tet.source_complex_canonicalization_l0 import (
    canonicalize_source_complex_l0,
)


def test_duplicate_stl_coordinates_become_shared_edges_without_dropping_triangles() -> None:
    points = (
        (0, 0, 0),
        (1, 0, 0),
        (0, 1, 0),
        (1, 0, 0),
        (1, 1, 0),
        (0, 1, 0),
    )
    result = canonicalize_source_complex_l0(points, ((0, 1, 2), (3, 4, 5)))
    assert result.accepted
    assert result.canonical_faces == ((0, 1, 2), (1, 3, 2))
    assert result.raw_triangle_count_preserved
    assert result.source_points_unchanged and not result.production_mesh_changed


def test_coordinate_weld_rejects_a_degenerate_raw_triangle() -> None:
    result = canonicalize_source_complex_l0(((0, 0, 0), (0, 0, 0), (1, 0, 0)), ((0, 1, 2),))
    assert not result.accepted
    assert result.reason == "coordinate_weld_would_degenerate_source_triangle"
