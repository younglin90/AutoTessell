"""L0 worklist tests: direct presence and a finite strict Chen intersection."""

from __future__ import annotations

from core.generator.native_tet.chen_source_facet_worklist_l0 import (
    build_source_facet_recovery_worklist_l0,
)


def test_worklist_is_empty_when_the_source_face_is_a_direct_tet_face() -> None:
    points = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))

    result = build_source_facet_recovery_worklist_l0(points, ((0, 1, 2, 3),), ((0, 1, 2),))

    assert result.accepted
    assert result.reason == "no_direct_missing_source_faces"
    assert result.items == ()
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_worklist_records_a_missing_face_with_a_strict_finite_intersection() -> None:
    points = (
        (-2, -2, 0), (2, -2, 0), (0, 2, 0),
        (0, 0, 1), (-1, -1, -1), (1, -1, -1), (0, 1, -1),
    )

    result = build_source_facet_recovery_worklist_l0(
        points, ((3, 4, 5, 6),), ((0, 1, 2),)
    )

    assert result.accepted
    assert result.missing_face_indices == (0,)
    assert len(result.items) == 1
    item = result.items[0]
    assert item.source_face == (0, 1, 2)
    assert item.unique_tet_ids == (0,)
    assert item.ambiguous_tet_ids == ()
