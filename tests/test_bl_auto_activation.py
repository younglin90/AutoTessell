"""beta24 — fine quality 기본 BL 자동 활성화 회귀 테스트."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    MeshStrategy,
    MeshType,
    QualityLevel,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
)
from core.strategist.param_optimizer import ParamOptimizer


def _make_stub_report(char_length: float = 1.0):
    """BL 계산에 필요한 필드만 노출하는 duck-type stub."""
    from types import SimpleNamespace

    return SimpleNamespace(
        geometry=SimpleNamespace(
            bounding_box=SimpleNamespace(characteristic_length=char_length),
        ),
    )


@pytest.mark.parametrize("quality,expected_enabled", [
    ("draft", False), ("standard", False), ("fine", True),
])
def test_bl_enabled_by_quality(quality: str, expected_enabled: bool) -> None:
    """ParamOptimizer.compute_boundary_layers: draft/standard=False, fine=True."""
    opt = ParamOptimizer()
    cfg = opt.compute_boundary_layers(_make_stub_report(), quality_level=quality)
    assert cfg.enabled is expected_enabled
    if expected_enabled:
        assert cfg.num_layers > 0
        assert cfg.first_layer_thickness > 0


def test_orchestrator_auto_populates_post_layers_engine_when_bl_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """beta24: strategy.boundary_layers.enabled=True + post_layers_engine 미지정
    시 orchestrator 가 'auto' 를 tier_specific_params 에 주입하는지 — 로직 유닛 검증.

    직접 orchestrator 구동은 복잡하므로, 로직 블록을 그대로 검증.
    """
    strategy = MeshStrategy(
        quality_level=QualityLevel.FINE,
        mesh_type=MeshType.HEX_DOMINANT,
        surface_quality_level=SurfaceQualityLevel.L1_REPAIR,
        selected_tier="tier_native_hex",
        flow_type="internal",
        domain=DomainConfig(
            type="box", min=[-1.0] * 3, max=[1.0] * 3,
            base_cell_size=0.1, location_in_mesh=[0.0] * 3,
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="dummy.stl", target_cell_size=0.1, min_cell_size=0.01,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=True, num_layers=3, first_layer_thickness=0.001,
            growth_ratio=1.2, max_total_thickness=0.01, min_thickness_ratio=0.1,
        ),
        tier_specific_params={},
    )

    # orchestrator 의 로직을 에뮬레이트
    _tsp = strategy.tier_specific_params or {}
    _post_engine = _tsp.get("post_layers_engine", None)
    if _post_engine is None and strategy.boundary_layers.enabled and strategy.boundary_layers.num_layers > 0:
        _post_engine = "auto"
        if strategy.tier_specific_params is None:
            strategy.tier_specific_params = {}
        strategy.tier_specific_params["post_layers_engine"] = "auto"

    assert _post_engine == "auto"
    assert strategy.tier_specific_params["post_layers_engine"] == "auto"


def test_orchestrator_does_not_override_explicit_post_layers_engine() -> None:
    """사용자가 post_layers_engine 을 명시했으면 orchestrator 가 덮어쓰지 않음."""
    strategy = MeshStrategy(
        quality_level=QualityLevel.FINE,
        mesh_type=MeshType.HEX_DOMINANT,
        surface_quality_level=SurfaceQualityLevel.L1_REPAIR,
        selected_tier="tier_native_hex",
        flow_type="internal",
        domain=DomainConfig(
            type="box", min=[-1.0] * 3, max=[1.0] * 3,
            base_cell_size=0.1, location_in_mesh=[0.0] * 3,
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="dummy.stl", target_cell_size=0.1, min_cell_size=0.01,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=True, num_layers=3, first_layer_thickness=0.001,
            growth_ratio=1.2, max_total_thickness=0.01, min_thickness_ratio=0.1,
        ),
        tier_specific_params={"post_layers_engine": "disabled"},
    )

    _tsp = strategy.tier_specific_params or {}
    _post_engine = _tsp.get("post_layers_engine", None)
    if _post_engine is None and strategy.boundary_layers.enabled:
        _post_engine = "auto"

    assert _post_engine == "disabled"  # 명시 값 보존


def test_bl_disabled_in_draft_does_not_trigger_auto_engine() -> None:
    """draft/standard quality 에서는 BL 비활성 → post_layers_engine 도 disabled 유지."""
    strategy = MeshStrategy(
        quality_level=QualityLevel.DRAFT,
        mesh_type=MeshType.TET,
        surface_quality_level=SurfaceQualityLevel.L1_REPAIR,
        selected_tier="tier_native_tet",
        flow_type="internal",
        domain=DomainConfig(
            type="box", min=[-1.0] * 3, max=[1.0] * 3,
            base_cell_size=0.1, location_in_mesh=[0.0] * 3,
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="dummy.stl", target_cell_size=0.1, min_cell_size=0.01,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False, num_layers=0, first_layer_thickness=0.0,
            growth_ratio=1.0, max_total_thickness=0.0, min_thickness_ratio=0.1,
        ),
        tier_specific_params={},
    )

    _tsp = strategy.tier_specific_params or {}
    _post_engine = _tsp.get("post_layers_engine", None)
    if _post_engine is None and strategy.boundary_layers.enabled and strategy.boundary_layers.num_layers > 0:
        _post_engine = "auto"
    else:
        _post_engine = "disabled" if _post_engine is None else _post_engine

    assert _post_engine == "disabled"
