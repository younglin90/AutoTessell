"""L0 literal Table-11 S2/Z1 certificate tests; no native recovery integration."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_thr_edg_table11_l0 import (
    certify_thr_edg_s1_z2_table11_l0,
    certify_thr_edg_s2_z1_table11_l0,
)


def _valid_points() -> dict[str, tuple[Fraction, Fraction, Fraction]]:
    fifth = Fraction(2, 5)
    return {
        "A": (Fraction(0), Fraction(0), Fraction(0)),
        "B": (Fraction(1), Fraction(0), Fraction(0)),
        "C": (Fraction(0), Fraction(1), Fraction(0)),
        "D": (Fraction(0), Fraction(0), Fraction(1)),
        "P1": (Fraction(0), Fraction(0), fifth),
        "P2": (Fraction(1) - fifth, Fraction(0), fifth),
        "P3": (Fraction(0), Fraction(1) - fifth, fifth),
    }


def test_literal_s2_z1_children_preserve_exact_volume_and_subdivided_boundary() -> None:
    result = certify_thr_edg_s2_z1_table11_l0(_valid_points())

    assert result.accepted, result.reason
    assert result.literal_children == (
        ("A", "B", "C", "P1"),
        ("P1", "B", "C", "P2"),
        ("P1", "P2", "C", "P3"),
        ("P1", "P2", "P3", "D"),
    )
    assert len(result.oriented_children) == 4
    assert result.parent_volume6 == result.replacement_volume6 == 1
    assert len(result.boundary_face_keys) == 10
    assert result.intersection_points_on_documented_edges
    assert result.external_boundary_preserved
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_nonincident_intersection_point_rejects_before_exposing_children() -> None:
    points = _valid_points()
    points["P2"] = (Fraction(1, 2), Fraction(1, 8), Fraction(2, 5))
    result = certify_thr_edg_s2_z1_table11_l0(points)

    assert not result.accepted
    assert result.reason == "intersection_not_on_documented_parent_edge"
    assert not result.literal_children
    assert not result.oriented_children


def test_literal_s1_z2_children_preserve_its_distinct_subdivided_boundary() -> None:
    result = certify_thr_edg_s1_z2_table11_l0(_valid_points())

    assert result.accepted, result.reason
    assert result.literal_children == (
        ("A", "B", "C", "P3"),
        ("A", "B", "P3", "P2"),
        ("A", "P2", "P3", "P1"),
        ("P1", "P2", "P3", "D"),
    )
    assert result.parent_volume6 == result.replacement_volume6 == 1
    assert len(result.boundary_face_keys) == 10
    assert result.intersection_points_on_documented_edges
    assert result.external_boundary_preserved
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_literal_s2_z1_certificate_is_value_identical_on_repeat() -> None:
    first = certify_thr_edg_s2_z1_table11_l0(_valid_points())
    second = certify_thr_edg_s2_z1_table11_l0(_valid_points())

    assert first == second
