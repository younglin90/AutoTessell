from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.generator._tier_native_common import run_native_tier
from core.generator.native_poly.voronoi import generate_native_poly_voronoi
from core.generator.tier_native_poly import _runner as poly_runner
from core.native_input_runtime import contract_receipt, resolve_native_runtime
from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    MeshStrategy,
    QualityLevel,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
)


def test_common_sizing_and_optimization_are_projected_to_native_runtime() -> None:
    config = {
        "target": {"count": 100},
        "sizing": {"base_size": 0.02, "min_size": 0.01, "max_size": 0.03},
        "optimization": {"smoothing_iterations": 3},
        "engine_options": {"tet": {"enable_amips_smooth": True}},
    }
    projection = resolve_native_runtime(config, "native_tet")
    assert projection.explicit_base_size is True
    assert projection.runner_kwargs["target_edge_length"] == 0.02
    assert projection.runner_kwargs["target_cells"] == 100
    assert projection.runner_kwargs["smooth_iterations"] == 3
    assert projection.runner_kwargs["enable_amips_smooth"] is True
    assert "/sizing/base_size" in projection.applied

    receipt = contract_receipt(
        config,
        projection,
        success=True,
        result=SimpleNamespace(route="tet_harness"),
    )
    assert "/sizing/base_size" in receipt["applied_verified"]
    assert "/target/count" in receipt["applied_verified"]


def test_bl_zero_is_identity_and_does_not_apply_spacing() -> None:
    config = {
        "boundary_layers": [{
            "layers": 0,
            "first_height": 1e-5,
            "growth_rate": 1.2,
        }],
    }
    projection = resolve_native_runtime(config, "native_poly")
    receipt = contract_receipt(
        config,
        projection,
        success=True,
        result=SimpleNamespace(route="poly_harness"),
    )
    assert "/boundary_layers/0" in receipt["ignored_by_policy"]
    assert "/boundary_layers/0/first_height" in receipt["ignored_by_policy"]
    assert "/boundary_layers/0/growth_rate" in receipt["ignored_by_policy"]


def test_native_poly_forwards_harness_controls_that_were_previously_dropped(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_harness(vertices, faces, case_dir, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            success=True,
            n_cells=4,
            n_points=8,
            n_faces=12,
            message="ok",
        )

    monkeypatch.setattr("core.generator.tier_native_poly.run_native_poly_harness", fake_harness)
    poly_runner(
        None,
        None,
        Path("case"),
        target_cells=100,
        max_tet_cells=1234,
        smooth_iters=4,
        smooth_relax=0.2,
    )
    assert seen["max_tet_cells"] == 1234
    assert seen["smooth_iters"] == 4
    assert seen["smooth_relax"] == 0.2

def test_user_quality_limit_is_a_native_route_gate(tmp_path: Path) -> None:
    stl = tmp_path / "tri.stl"
    stl.write_text(
        "solid tri\n"
        "facet normal 0 0 1\n"
        "outer loop\n"
        "vertex 0 0 0\n"
        "vertex 1 0 0\n"
        "vertex 0 1 0\n"
        "endloop\n"
        "endfacet\n"
        "endsolid\n"
    )

    def fake_runner(vertices, faces, case_dir, **kwargs):
        return SimpleNamespace(
            success=True,
            n_cells=1,
            n_points=3,
            n_faces=1,
            max_skewness=0.9,
            max_non_ortho=10.0,
            route="fake_native",
            message="candidate",
        )

    strategy = MeshStrategy(
        quality_level=QualityLevel.DRAFT,
        surface_quality_level=SurfaceQualityLevel.L1_REPAIR,
        selected_tier="tier_native_tet",
        flow_type="internal",
        domain=DomainConfig(
            type="box",
            min=[0.0, 0.0, 0.0],
            max=[1.0, 1.0, 1.0],
            base_cell_size=0.1,
            location_in_mesh=[0.0, 0.0, 0.0],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file=str(stl),
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
        tier_specific_params={
            "input_config": {
                "schema_version": "1.0",
                "quality": {"max_skewness": 0.5},
            },
        },
    )
    attempt = run_native_tier(
        fake_runner,
        "tier_native_tet",
        strategy,
        stl,
        tmp_path / "case",
    )
    assert attempt.status == "failed"
    assert "max_skewness" in (attempt.error_message or "")
    assert "/quality/max_skewness" in attempt.parameter_receipt["rejected"]


def test_native_poly_explicit_edge_escalation_reaches_a_candidate(tmp_path: Path) -> None:
    vertices = __import__("numpy").array(
        [
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ],
        dtype=float,
    )
    faces = __import__("numpy").array(
        [
            [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
            [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2],
            [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0],
        ],
        dtype=int,
    )
    result = generate_native_poly_voronoi(
        vertices,
        faces,
        tmp_path / "case",
        target_edge_length=0.8,
        seed_density=3,
        n_lloyd=0,
        auto_escalate=True,
        auto_escalate_max=4,
        target_cells=15,
        max_cells=100,
        bl_layers=0,
    )
    assert result.success is True
    assert result.n_cells > 2

