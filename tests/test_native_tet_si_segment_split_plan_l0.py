"""Deterministic, report-only Si Rule-1 midpoint contracts."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.si_segment_split_plan_l0 import plan_si_segment_split_l0


def test_rule1_midpoint_branch_is_exact_and_deterministic() -> None:
    points = ((0, 0, 0), (2, 0, 0), (1, Fraction(1, 2), 0), (1, Fraction(-1, 2), 0))
    first = plan_si_segment_split_l0(points, (0, 1), ((0, 1),))
    second = plan_si_segment_split_l0(points, (0, 1), ((0, 1),))
    assert first.accepted and first == second
    # Equal-distance encroachers use lexicographic exact coordinates before ID.
    assert first.chosen_encroacher_index == 3
    assert first.candidate_parameter == Fraction(1, 2)
    assert first.candidate_point == (Fraction(1), Fraction(0), Fraction(0))
    assert not first.production_mesh_changed


def test_type1_and_distance_offset_branches_fail_closed() -> None:
    type1 = plan_si_segment_split_l0(
        ((0, 0, 0), (2, 0, 0), (1, Fraction(1, 2), 0), (1, 1, 0)),
        (0, 1),
        ((0, 1), (0, 3)),
    )
    offset = plan_si_segment_split_l0(
        ((0, 0, 0), (2, 0, 0), (Fraction(1, 4), 0, 0)),
        (0, 1),
        ((0, 1),),
    )
    assert type1.reason == "type1_requires_lfs_rule2_or_rule3"
    assert offset.reason == "rule1_distance_offset_requires_algebraic_coordinate"
