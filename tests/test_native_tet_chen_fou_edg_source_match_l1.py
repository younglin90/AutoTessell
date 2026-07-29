"""L1 finite-source to Table-12 FOU_EDG SSSS binding tests."""

from __future__ import annotations

from core.generator.native_tet.chen_fou_edg_source_match_l1 import (
    certify_fou_edg_source_match_l1,
)

_TET = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
_FOU_TRIANGLE = ((-1, -1, 7 / 5), (3, -1, 7 / 5), (-1, 3, -13 / 5))


def test_finite_fou_edg_source_derives_documented_table12_ssss_intersections() -> None:
    result = certify_fou_edg_source_match_l1(_TET, _FOU_TRIANGLE)

    assert result.accepted, result.reason
    assert result.candidate is not None
    assert result.candidate.intersection_points_on_documented_edges
    assert result.candidate.source_fragment_l1_preserved
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_non_fou_or_different_documented_cut_pattern_rejects_before_candidate_exposure() -> None:
    result = certify_fou_edg_source_match_l1(
        _TET,
        ((-1, -1, 2 / 5), (2, -1, 2 / 5), (-1, 2, 2 / 5)),
    )

    assert not result.accepted
    assert result.reason == "reject_clusterel_not_documented_ac_ad_bc_bd_fou_edg"
    assert result.candidate is None


def test_fou_source_match_is_value_identical_on_repeat() -> None:
    assert certify_fou_edg_source_match_l1(_TET, _FOU_TRIANGLE) == certify_fou_edg_source_match_l1(
        _TET, _FOU_TRIANGLE
    )
