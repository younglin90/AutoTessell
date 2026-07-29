"""L0 literal Table-12 FOU_EDG SSSS certificate tests."""

from __future__ import annotations

from core.generator.native_tet.chen_fou_edg_table12_l0 import (
    certify_fou_edg_ssss_table12_l0,
)

_FOU_POINTS = {
    "A": (0, 0, 0),
    "B": (1, 0, 0),
    "C": (0, 1, 0),
    "D": (0, 0, 1),
    "P1": (0, 0, 2 / 5),
    "P2": (3 / 5, 0, 2 / 5),
    "P3": (3 / 5, 2 / 5, 0),
    "P4": (0, 2 / 5, 0),
}


def test_literal_table12_ssss_preserves_parent_and_recovers_coplanar_quad_fragment() -> None:
    result = certify_fou_edg_ssss_table12_l0(_FOU_POINTS)

    assert result.accepted, result.reason
    assert len(result.literal_children) == 6
    assert len(result.oriented_children) == 6
    assert result.parent_volume6 == result.replacement_volume6 == 1
    assert result.intersection_points_on_documented_edges
    assert result.source_fragment_l1_preserved
    assert result.recovered_source_fragment_faces == {
        ("P1", "P2", "P3"),
        ("P1", "P3", "P4"),
    }
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_literal_table12_ssss_rejects_wrong_documented_edge_assignment() -> None:
    points = dict(_FOU_POINTS)
    points["P3"] = (1 / 2, 0, 0)

    result = certify_fou_edg_ssss_table12_l0(points)

    assert not result.accepted
    assert result.reason == "intersection_not_on_documented_ad_bd_bc_ac_edges"
    assert not result.production_mesh_changed


def test_literal_table12_ssss_rejects_non_coplanar_four_edge_intersections() -> None:
    points = dict(_FOU_POINTS)
    points["P4"] = (0, 1 / 3, 0)

    result = certify_fou_edg_ssss_table12_l0(points)

    assert not result.accepted
    assert result.reason == "documented_intersections_not_coplanar"
    assert not result.production_mesh_changed


def test_literal_table12_ssss_is_value_identical_on_repeat() -> None:
    assert certify_fou_edg_ssss_table12_l0(_FOU_POINTS) == certify_fou_edg_ssss_table12_l0(
        _FOU_POINTS
    )
