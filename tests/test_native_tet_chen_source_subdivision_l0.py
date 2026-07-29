"""L0 exact source-triangle subdivision audit tests."""

from __future__ import annotations

from core.generator.native_tet.chen_source_subdivision_l0 import (
    audit_source_triangle_subdivision_l0,
    audit_source_triangle_subdivision_l1,
)


def test_three_coplanar_subtriangles_preserve_one_source_triangle_exactly() -> None:
    points = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1 / 2, 0, 0), (1 / 2, 1 / 2, 0), (0, 1 / 2, 0))
    result = audit_source_triangle_subdivision_l0(
        points,
        ((0, 1, 2),),
        ((0, 3, 5), (3, 1, 4), (5, 4, 2), (3, 4, 5)),
    )

    assert result.accepted, result.reason
    assert result.candidate_source_owner == (0, 0, 0, 0)
    assert result.per_source_area_vector_preserved
    assert result.all_candidate_faces_have_one_source_owner
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_candidate_outside_or_opposite_to_source_rejects() -> None:
    points = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (2, 0, 0))
    outside = audit_source_triangle_subdivision_l0(points, ((0, 1, 2),), ((0, 1, 3),))
    reversed_face = audit_source_triangle_subdivision_l0(points, ((0, 1, 2),), ((0, 2, 1),))

    assert not outside.accepted
    assert outside.reason == "candidate_not_on_exactly_one_source_face"
    assert not reversed_face.accepted
    assert reversed_face.reason == "candidate_orientation_not_source_aligned"


def test_area_vector_l0_alone_cannot_detect_duplicate_half_coverage() -> None:
    # Two identical half-area triangles have the correct total area vector but
    # leave the other half of the source triangle uncovered. This is the L1
    # topological-coverage counterexample, not an accepted production proof.
    points = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1 / 2, 1 / 2, 0))
    result = audit_source_triangle_subdivision_l0(
        points,
        ((0, 1, 2),),
        ((0, 1, 3), (0, 1, 3)),
    )

    assert result.accepted
    assert result.per_source_area_vector_preserved


def test_l1_requires_exact_boundary_intervals_and_rejects_duplicate_half_coverage() -> None:
    points = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1 / 2, 1 / 2, 0))
    result = audit_source_triangle_subdivision_l1(
        points,
        ((0, 1, 2),),
        ((0, 1, 3), (0, 1, 3)),
    )

    assert not result.accepted
    assert result.l0.accepted
    assert not result.source_boundary_edge_incidence_preserved
    assert not result.source_boundary_interval_partition_preserved
    assert not result.production_mesh_changed


def test_l1_accepts_a_conforming_exact_source_triangle_partition() -> None:
    points = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1 / 2, 0, 0), (1 / 2, 1 / 2, 0), (0, 1 / 2, 0))
    result = audit_source_triangle_subdivision_l1(
        points,
        ((0, 1, 2),),
        ((0, 3, 5), (3, 1, 4), (5, 4, 2), (3, 4, 5)),
    )

    assert result.accepted, result.reason
    assert result.candidate_edges_conforming
    assert result.interior_edge_incidence_preserved
    assert result.source_boundary_edge_incidence_preserved
    assert result.source_boundary_interval_partition_preserved
    assert not result.production_mesh_changed
