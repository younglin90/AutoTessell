"""L3 before/after source-triangle coverage tests; no production mutation."""

from __future__ import annotations

from core.generator.native_tet.chen_source_triangle_replacement_coverage_l3 import (
    certify_source_triangle_replacement_coverage_l3,
)


_POINTS = ((-2, -2, -1), (2, -2, -1), (0, 2, -1), (0, 0, 2), (0, 0, 0))
_PARENTS = ((0, 1, 2, 3),)
_SOURCE = ((-1 / 2, -1 / 2, 0), (1 / 2, -1 / 2, 0), (0, 1 / 2, 0))
_CENTRAL_INSERTION = {
    0: ((4, 1, 2, 3), (0, 4, 2, 3), (4, 0, 1, 3), (0, 4, 1, 2)),
}


def test_full_positive_cavity_replacement_preserves_exact_source_coverage() -> None:
    result = certify_source_triangle_replacement_coverage_l3(
        _POINTS, _PARENTS, _SOURCE, (0,), _CENTRAL_INSERTION
    )

    assert result.accepted, result.reason
    assert result.staging is not None and result.staging.accepted
    assert result.before_coverage is not None and result.before_coverage.accepted
    assert result.after_coverage is not None and result.after_coverage.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_incomplete_cavity_replacement_rejects_before_after_coverage_is_exposed() -> None:
    result = certify_source_triangle_replacement_coverage_l3(
        _POINTS, _PARENTS, _SOURCE, (0,), {0: (_CENTRAL_INSERTION[0][0],)}
    )

    assert not result.accepted
    assert result.reason == "cavity_staging_failed:subdivided_staged_contract_failed"
    assert result.staging is not None and not result.staging.accepted
    assert result.before_coverage is None
    assert result.after_coverage is None


def test_source_triangle_outside_original_parent_mesh_rejects_before_replacement_claim() -> None:
    result = certify_source_triangle_replacement_coverage_l3(
        _POINTS,
        _PARENTS,
        ((-4, -4, 0), (4, -4, 0), (0, 4, 0)),
        (0,),
        _CENTRAL_INSERTION,
    )

    assert not result.accepted
    assert result.reason == "before_source_coverage_failed:source_fragment_union_failed:source_area_partition_failed"
    assert result.staging is not None and result.staging.accepted
    assert result.before_coverage is not None and not result.before_coverage.accepted
    assert result.after_coverage is None


def test_before_after_source_coverage_certificate_is_value_identical_on_repeat() -> None:
    first = certify_source_triangle_replacement_coverage_l3(
        _POINTS, _PARENTS, _SOURCE, (0,), _CENTRAL_INSERTION
    )
    second = certify_source_triangle_replacement_coverage_l3(
        _POINTS, _PARENTS, _SOURCE, (0,), _CENTRAL_INSERTION
    )

    assert first == second
