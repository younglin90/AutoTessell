"""L1 extraction contracts before any constrained-cavity mutation."""

from __future__ import annotations

from core.generator.native_tet.chen_source_missing_region_extraction_l1 import (
    extract_source_missing_region_l1,
)


def _one_sided_hole() -> (
    tuple[tuple[tuple[int, int, int], ...], tuple[tuple[int, int, int, int], ...]]
):
    points = (
        (0, 0, 0),
        (2, 0, 0),
        (0, 2, 0),
        (0, 0, 1),
        (2, 2, 2),
    )
    tets = (
        (0, 1, 3, 4),
        (1, 2, 3, 4),
        (2, 0, 3, 4),
    )
    return points, tets


def test_extracts_one_subface_region_with_one_selected_shell() -> None:
    points, tets = _one_sided_hole()
    result = extract_source_missing_region_l1(points, (0, 1, 2), tets)
    assert result.accepted
    assert result.plan is not None and result.plan.selected_side == 1
    assert result.crossing_tet_ids == ()


def test_rejects_direct_present_source_face_and_two_sided_shell() -> None:
    points, tets = _one_sided_hole()
    direct = extract_source_missing_region_l1(points, (0, 1, 2), (*tets, (0, 1, 2, 4)))
    two_sided = extract_source_missing_region_l1(
        (*points, (0, 0, -1), (2, 2, -2)),
        (0, 1, 2),
        (*tets, (0, 1, 5, 6), (1, 2, 5, 6), (2, 0, 5, 6)),
    )
    assert direct.reason == "source_face_already_present"
    assert two_sided.reason == "two_sided_source_shell"
