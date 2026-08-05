"""STL edge-incidence evidence for provisional wall-edge candidates."""

from pathlib import Path

from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger


def test_real_stl_edge_ledgers_are_deterministic_and_not_feature_authority() -> None:
    paths = (
        Path("tests/benchmarks/cube.stl"),
        Path("tests/benchmarks/sphere_watertight.stl"),
        Path("tests/benchmarks/naca0012.stl"),
        Path("tests/benchmarks/trimesh_duct.stl"),
    )
    for path in paths:
        first = build_stl_edge_ledger(path)
        second = build_stl_edge_ledger(path)
        print(path.name, {key: first[key] for key in ("facet_count", "edge_count", "boundary_edge_count", "non_manifold_edge_count", "edge_digest")})
        assert first["status"] == "USER_DECLARED_PROVISIONAL_EDGE_LEDGER"
        assert first["source_sha256"] == second["source_sha256"]
        assert first["edge_digest"] == second["edge_digest"]
        assert first["feature_authority"] is False
        assert first["wall_edge_authority"] is False


def test_malformed_stl_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bad.stl"
    path.write_bytes(b"solid bad\nfacet normal 0 0 1\n")
    result = build_stl_edge_ledger(path)
    assert result["status"] == "REFUSED"
    assert result["release_eligible"] is False
