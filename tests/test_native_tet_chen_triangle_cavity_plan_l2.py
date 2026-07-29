"""L2 complete-cavity plan binding tests; no automatic S/Z dispatch."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_explicit_cavity_plan_l3 import ChenCavityTemplateInstruction
from core.generator.native_tet.chen_triangle_cavity_plan_l2 import (
    certify_complete_explicit_triangle_cavity_plan_l2,
)


_POINTS = (
    (-1, 0, Fraction(-1, 2)),
    (1, 0, Fraction(1, 2)),
    (0, -1, -1),
    (0, 1, -1),
    (0, 0, 1),
)
_PARENTS = ((0, 2, 3, 4), (1, 2, 3, 4))
_SOURCE = ((-2, -2, 0), (2, -2, 0), (0, 2, 0))
_PLAN = (
    ChenCavityTemplateInstruction(0, (0, 2, 3, 4), "THR_S2_Z1"),
    ChenCavityTemplateInstruction(1, (1, 4, 2, 3), "FOU_SSSS"),
)


def test_complete_documented_plan_covers_every_active_triangle_clusterel() -> None:
    result = certify_complete_explicit_triangle_cavity_plan_l2(_POINTS, _PARENTS, _SOURCE, _PLAN)

    assert result.accepted, result.reason
    assert result.active_parent_indices == (0, 1)
    assert result.face_connected_components == ((0, 1),)
    assert result.plan is not None and result.plan.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_omitted_active_parent_rejects_before_any_l3_candidate_is_exposed() -> None:
    result = certify_complete_explicit_triangle_cavity_plan_l2(
        _POINTS, _PARENTS, _SOURCE, (_PLAN[0],)
    )

    assert not result.accepted
    assert result.reason == "plan_must_cover_exactly_all_active_triangle_clusterels"
    assert result.plan is None


def test_documented_row_cannot_be_applied_to_the_wrong_clusterel_type() -> None:
    wrong_type = (
        _PLAN[0],
        ChenCavityTemplateInstruction(1, (1, 4, 2, 3), "THR_S1_Z2"),
    )
    result = certify_complete_explicit_triangle_cavity_plan_l2(_POINTS, _PARENTS, _SOURCE, wrong_type)

    assert not result.accepted
    assert result.reason == "template_not_certified_for_active_clusterel_type"
    assert result.plan is None


def test_local_documented_order_must_belong_to_its_declared_global_parent() -> None:
    wrong_parent = (
        ChenCavityTemplateInstruction(0, (1, 4, 2, 3), "THR_S2_Z1"),
        _PLAN[1],
    )
    result = certify_complete_explicit_triangle_cavity_plan_l2(_POINTS, _PARENTS, _SOURCE, wrong_parent)

    assert not result.accepted
    assert result.reason == "local_parent_is_not_a_permutation_of_its_global_parent"
    assert result.plan is None


def test_complete_triangle_cavity_plan_is_value_identical_on_repeat() -> None:
    first = certify_complete_explicit_triangle_cavity_plan_l2(_POINTS, _PARENTS, _SOURCE, _PLAN)
    second = certify_complete_explicit_triangle_cavity_plan_l2(_POINTS, _PARENTS, _SOURCE, _PLAN)

    assert first == second
