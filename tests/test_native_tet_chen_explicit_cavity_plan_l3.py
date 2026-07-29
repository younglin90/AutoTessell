"""L3 explicit-documentation cavity-plan tests; no implicit S/Z selection."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_explicit_cavity_plan_l3 import (
    ChenCavityTemplateInstruction,
    certify_explicit_cavity_template_plan_l3,
)

_POINTS = (
    (-1, 0, Fraction(-1, 2)),
    (1, 0, Fraction(1, 2)),
    (0, -1, -1),
    (0, 1, -1),
    (0, 0, 1),
)
_SOURCE = ((-2, -2, 0), (2, -2, 0), (0, 2, 0))
_PLAN = (
    ChenCavityTemplateInstruction(0, (0, 2, 3, 4), "THR_S2_Z1"),
    ChenCavityTemplateInstruction(1, (1, 4, 2, 3), "FOU_SSSS"),
)


def test_explicit_documented_two_parent_plan_certifies_one_atomic_cavity_shell() -> None:
    result = certify_explicit_cavity_template_plan_l3(_POINTS, _SOURCE, _PLAN)

    assert result.accepted, result.reason
    assert result.template_sequence == ("THR_S2_Z1", "FOU_SSSS")
    assert result.constructed_points == 5
    assert result.staging is not None and result.staging.accepted
    assert len(result.staging.committed_tets) == 10
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_undocumented_local_order_rejects_before_staging_candidate_exposure() -> None:
    bad_plan = (
        _PLAN[0],
        ChenCavityTemplateInstruction(1, (1, 2, 4, 3), "FOU_SSSS"),
    )

    result = certify_explicit_cavity_template_plan_l3(_POINTS, _SOURCE, bad_plan)

    assert not result.accepted
    assert result.reason == "template_does_not_match_documented_finite_clusterel"
    assert result.staging is None


def test_explicit_cavity_plan_is_value_identical_on_repeat() -> None:
    assert certify_explicit_cavity_template_plan_l3(
        _POINTS, _SOURCE, _PLAN
    ) == certify_explicit_cavity_template_plan_l3(_POINTS, _SOURCE, _PLAN)
