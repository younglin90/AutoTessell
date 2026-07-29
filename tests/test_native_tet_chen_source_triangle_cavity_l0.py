"""L0 exact source-triangle cavity tests; no recovery connectivity is created."""

from __future__ import annotations

from core.generator.native_tet.chen_source_triangle_cavity_l0 import (
    classify_source_triangle_cavity,
)
from core.generator.native_tet.chen_source_triangle_coverage_l2 import (
    certify_source_triangle_coverage_l2,
)


def test_triangle_cavity_records_connected_thr_and_fou_clusterels() -> None:
    # The large z=0 source triangle cuts two tetrahedra sharing BCD.  Neither
    # tet is an edge-only source-pipel: their finite-triangle clusterel types
    # are THR_EDG and FOU_EDG, the first documented S/Z prerequisite.
    points = (
        (-1, 0, -0.5),  # A
        (1, 0, 0.5),  # E
        (0, -1, -1),  # B
        (0, 1, -1),  # C
        (0, 0, 1),  # D
    )
    triangle = ((-2, -2, 0), (2, -2, 0), (0, 2, 0))
    result = classify_source_triangle_cavity(
        points,
        ((0, 2, 3, 4), (1, 2, 3, 4)),
        triangle,
    )

    assert result.accepted, result.reason
    assert tuple(item.parent_index for item in result.clusterels) == (0, 1)
    assert tuple(item.classification.clusterel_type for item in result.clusterels) == (
        "THR_EDG",
        "FOU_EDG",
    )
    assert result.face_connected_components == ((0, 1),)


def test_constraint_boundary_contact_rejects_the_whole_cavity() -> None:
    points = ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1))
    result = classify_source_triangle_cavity(
        points,
        ((0, 1, 2, 3),),
        ((-1, -1, 0), (1, -1, 0), (0, 0, 0)),
    )

    assert not result.accepted
    assert result.reason == "clusterel_rejected:0:constraint_boundary_touch"
    assert not result.clusterels
    assert not result.face_connected_components


def test_complete_parent_mesh_skips_nonintersecting_tets_and_keeps_thr_fou_cavity() -> None:
    # Fixed, non-overlapping tetrahedralisation of an enclosing cube with an
    # interior alternating-sign core tet.  The finite source triangle is
    # entirely covered by the parent mesh, while the core produces FOU_EDG
    # and neighbouring parents produce THR_EDG.  This guards against treating
    # an unrelated parent with no positive source fragment as a bad clusterel.
    points = (
        (-5, -5, -5), (5, -5, -5), (5, 5, -5), (-5, 5, -5),
        (-5, -5, 5), (5, -5, 5), (5, 5, 5), (-5, 5, 5),
        (-1, -1, -1), (1, -1, 1), (0, 1, -1), (0, 0, 1),
    )
    parents = (
        (10, 9, 2, 1), (8, 10, 3, 0), (8, 7, 11, 4), (8, 10, 9, 11),
        (8, 10, 7, 11), (8, 10, 7, 3), (8, 9, 11, 4), (8, 10, 1, 0),
        (8, 10, 9, 1), (6, 10, 9, 2), (6, 10, 9, 11), (6, 10, 7, 11),
        (5, 9, 11, 4), (5, 6, 9, 11), (10, 2, 1, 0), (10, 3, 2, 0),
        (8, 3, 4, 0), (8, 7, 3, 4), (6, 10, 3, 2), (6, 10, 7, 3),
        (5, 6, 7, 11), (5, 7, 11, 4), (5, 8, 1, 0), (5, 8, 9, 1),
        (5, 8, 9, 4), (5, 8, 4, 0), (5, 9, 2, 1), (5, 6, 9, 2),
    )
    source = ((-4, -4, 0), (4, -4, 0), (0, 4, 0))

    coverage = certify_source_triangle_coverage_l2(points, parents, source)
    result = classify_source_triangle_cavity(points, parents, source)

    assert coverage.accepted, coverage.reason
    assert result.accepted, result.reason
    types = {item.classification.clusterel_type for item in result.clusterels}
    assert "THR_EDG" in types
    assert "FOU_EDG" in types
    assert coverage.source_points_unchanged
    assert not coverage.production_mesh_changed


def test_triangle_cavity_is_value_identical_on_repeat() -> None:
    points = ((-1, 0, -0.5), (1, 0, 0.5), (0, -1, -1), (0, 1, -1), (0, 0, 1))
    triangle = ((-2, -2, 0), (2, -2, 0), (0, 2, 0))
    first = classify_source_triangle_cavity(points, ((0, 2, 3, 4), (1, 2, 3, 4)), triangle)
    second = classify_source_triangle_cavity(points, ((0, 2, 3, 4), (1, 2, 3, 4)), triangle)

    assert first == second
