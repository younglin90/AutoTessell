"""Open STL topological boundary evidence."""

from pathlib import Path

from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger


def test_open_stl_surfaces_report_boundary_candidates_without_authority() -> None:
    for name in ("hemisphere_open.stl", "hemisphere_open_partial.stl"):
        result = build_stl_edge_ledger(Path("tests/benchmarks") / name)
        print(name, {key: result[key] for key in ("facet_count", "edge_count", "boundary_edge_count", "non_manifold_edge_count", "edge_digest")})
        assert result["status"] == "USER_DECLARED_PROVISIONAL_EDGE_LEDGER"
        assert result["boundary_edge_count"] > 0
        assert result["non_manifold_edge_count"] == 0
        assert result["feature_authority"] is False
        assert result["wall_edge_authority"] is False
