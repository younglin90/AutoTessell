"""Route/contract metadata checks for native tier wrappers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    MeshStrategy,
    QualityLevel,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
)
from core.generator.tier_native_hex import _runner as hex_runner
from core.generator.tier_native_hex import TierNativeHexGenerator
from core.generator.tier_native_poly import _runner as poly_runner
from core.generator.tier_native_poly import TierNativePolyGenerator


def _mk_strategy(selected_tier: str = "tier_native_hex") -> MeshStrategy:
    return MeshStrategy(
        quality_level=QualityLevel.DRAFT,
        surface_quality_level=SurfaceQualityLevel.L1_REPAIR,
        selected_tier=selected_tier,
        flow_type="internal",
        domain=DomainConfig(
            type="box", min=[-1.0] * 3, max=[1.0] * 3,
            base_cell_size=0.1, location_in_mesh=[0.0] * 3,
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="dummy.stl",
            target_cell_size=0.1,
            min_cell_size=0.01,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False,
            num_layers=0,
            first_layer_thickness=0.0,
            growth_ratio=1.0,
            max_total_thickness=0.0,
            min_thickness_ratio=0.0,
        ),
    )


def _mk_mesh():
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=float,
    )
    faces = np.array(
        [
            [0, 1, 2],
        ],
        dtype=np.int64,
    )
    return vertices, faces


def _fake_hex_result(success=True, n_cells=10, message="ok"):
    return SimpleNamespace(
        success=success,
        n_cells=n_cells,
        n_points=5,
        n_faces=8,
        message=message,
    )


def _fake_poly_result(success=True, n_cells=12, n_points=10, n_faces=30, message="ok"):
    return SimpleNamespace(
        success=success,
        n_cells=n_cells,
        n_points=n_points,
        n_faces=n_faces,
        message=message,
    )


def test_hex_runner_attaches_route_and_contract(monkeypatch):
    seen = {}

    def fake_generate(vertices, faces, case_dir, **kwargs):
        seen["kwargs"] = kwargs
        return _fake_hex_result()

    monkeypatch.setattr(
        "core.generator.tier_native_hex.generate_native_hex",
        fake_generate,
    )

    result = hex_runner(
        *_mk_mesh(),
        Path("/tmp/case"),
        target_edge_length=0.25,
        seed_density=11,
        snap_boundary=True,
    )

    assert result.route == "hex_uniform_grid"
    assert result.contract == "native_hex"
    assert result.contract_details == {"seed_density": 11}
    assert seen["kwargs"]["seed_density"] == 11
    assert seen["kwargs"]["target_edge_length"] == 0.25
    assert seen["kwargs"]["snap_boundary"] is True


def test_poly_runner_boolean_route(monkeypatch):
    def fake_voronoi(vertices, faces, case_dir, **kwargs):
        assert kwargs["boolean_input_paths"] == ["b1.stl"]
        return _fake_poly_result()

    monkeypatch.setattr(
        "core.generator.tier_native_poly.generate_native_poly_voronoi",
        fake_voronoi,
    )

    result = poly_runner(
        *_mk_mesh(),
        Path("/tmp/case"),
        boolean_input_paths=["b1.stl"],
        boolean_source_names=["body"],
        boolean_operation="union",
        seed_density=9,
    )

    assert result.route == "poly_voronoi_boolean"
    assert result.contract == "native_poly"
    assert result.contract_details["mode"] == "boolean_budget"
    assert result.contract_details["seed_density"] == 9


def test_poly_runner_budget_route(monkeypatch):
    def fake_voronoi(vertices, faces, case_dir, **kwargs):
        assert kwargs["target_cells"] == 2_000
        assert kwargs["max_cells"] == 2_500
        return _fake_poly_result()

    monkeypatch.setattr(
        "core.generator.tier_native_poly.generate_native_poly_voronoi",
        fake_voronoi,
    )

    result = poly_runner(
        *_mk_mesh(),
        Path("/tmp/case"),
        target_cells=2_000,
        max_cells=2_500,
        seed_density=8,
    )

    assert result.route == "poly_voronoi_budget"
    assert result.contract == "native_poly"
    assert result.contract_details["mode"] == "budget"
    assert result.contract_details["target_cells"] == 2_000
    assert result.contract_details["max_cells"] == 2_500


def test_poly_runner_harness_then_fallback_route(monkeypatch):
    calls = {
        "harness": 0,
        "fallback": 0,
    }

    def fake_harness(vertices, faces, case_dir, **kwargs):
        calls["harness"] += 1
        return _fake_poly_result(success=False, n_cells=0, message="harness failed")

    def fake_voronoi(vertices, faces, case_dir, **kwargs):
        calls["fallback"] += 1
        return _fake_poly_result(success=True, n_cells=20)

    monkeypatch.setattr(
        "core.generator.tier_native_poly.run_native_poly_harness",
        fake_harness,
    )
    monkeypatch.setattr(
        "core.generator.tier_native_poly.generate_native_poly_voronoi",
        fake_voronoi,
    )

    result = poly_runner(
        *_mk_mesh(),
        Path("/tmp/case"),
        seed_density=10,
    )

    assert calls["harness"] == 1
    assert calls["fallback"] == 1
    assert result.route == "poly_voronoi_fallback"
    assert result.contract == "native_poly"
    assert result.fallback_reason == "harness_failed"
    assert result.contract_details["mode"] == "harness_fallback"


def test_tier_native_hex_generator_propagates_route_and_contract(monkeypatch, tmp_path: Path):
    stl = tmp_path / "input.stl"
    stl.write_text(
        "solid t\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n"
        "endloop\nendfacet\nendsolid\n"
    )

    def fake_generate(vertices, faces, case_dir, **kwargs):
        return _fake_hex_result(success=True, n_cells=21)

    monkeypatch.setattr("core.generator.tier_native_hex.generate_native_hex", fake_generate)
    monkeypatch.setattr(
        "core.analyzer.readers.read_stl",
        lambda _path: SimpleNamespace(
            vertices=np.array(
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            ),
            faces=np.array([[0, 1, 2]], dtype=np.int64),
        ),
    )

    attempt = TierNativeHexGenerator().run(_mk_strategy("tier_native_hex"), stl, tmp_path / "case")

    assert attempt.route == "hex_uniform_grid"
    assert attempt.contract == "native_hex"
    assert attempt.mesh_stats is not None
    assert attempt.mesh_stats.num_cells == 21


def test_tier_native_poly_generator_propagates_route_and_contract(monkeypatch, tmp_path: Path):
    stl = tmp_path / "input.stl"
    stl.write_text(
        "solid t\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n"
        "endloop\nendfacet\nendsolid\n"
    )

    def fake_harness(vertices, faces, case_dir, **kwargs):
        return _fake_poly_result(success=True, n_cells=44)

    monkeypatch.setattr("core.generator.tier_native_poly.run_native_poly_harness", fake_harness)
    monkeypatch.setattr(
        "core.analyzer.readers.read_stl",
        lambda _path: SimpleNamespace(
            vertices=np.array(
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            ),
            faces=np.array([[0, 1, 2]], dtype=np.int64),
        ),
    )

    attempt = TierNativePolyGenerator().run(_mk_strategy("tier_native_poly"), stl, tmp_path / "case")

    assert attempt.route == "poly_harness"
    assert attempt.contract == "native_poly"
    assert attempt.mesh_stats is not None
    assert attempt.mesh_stats.num_cells == 44
