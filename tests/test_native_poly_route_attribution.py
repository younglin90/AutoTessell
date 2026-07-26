"""Focused tests for the diagnostic-only POLY-ROUTE-ATTRIB1 harness."""

from __future__ import annotations

from pathlib import Path

from core.generator.native_poly.route_attribution import (
    load_fixed_fixture,
    run_fixture_comparison,
)


def test_fixed_primal_direct_and_tier_routes_are_attributed(tmp_path: Path) -> None:
    fixture = load_fixed_fixture(Path(__file__).parent / "benchmarks" / "cube.stl")
    comparison = run_fixture_comparison(fixture, tmp_path / "cube", repeats=2)

    assert comparison.primal_identity
    assert comparison.direct_tier_identity_equal
    assert comparison.deterministic_repeat_identity == {
        "direct_tet_to_poly_dual": True,
        "tier_native_poly": True,
    }
    assert len(comparison.routes) == 4
    assert all(item.auto_escalate is False for item in comparison.routes)
    assert all(item.fixed_primal_injected for item in comparison.routes)
    assert all(not item.drop.invoked for item in comparison.routes)
    assert all(item.disk_identity_matches_selected for item in comparison.routes)


def test_fixed_primal_records_census_and_quality(tmp_path: Path) -> None:
    fixture = load_fixed_fixture(Path(__file__).parent / "benchmarks" / "cylinder.stl")
    comparison = run_fixture_comparison(fixture, tmp_path / "cylinder", repeats=1)

    assert comparison.error == ""
    assert len(comparison.routes) == 2
    for report in comparison.routes:
        assert report.primal_identity == comparison.primal_identity
        assert report.n_cells > 0
        assert report.n_faces > 0
        assert report.n_boundary_faces > 0
        assert report.n_patches >= 1
        assert report.volume > 0.0
        assert report.surface_area_deviation_pct >= 0.0
        assert "max_non_orthogonality" in report.quality
        assert "max_skewness" in report.quality
