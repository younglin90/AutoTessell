"""beta76 — native_bl Phase 2 메트릭이 QualityReport 에 통합되는지 검증."""
from __future__ import annotations

import pytest

from core.schemas import AdditionalMetrics, NativeBLPhase2Stats


def test_native_bl_phase2_stats_defaults() -> None:
    s = NativeBLPhase2Stats()
    assert s.n_prism_cells == 0
    assert s.max_aspect_ratio == 0.0
    assert s.collision_safety_triggered is False
    assert s.feature_lock_triggered is False


def test_native_bl_phase2_stats_all_fields() -> None:
    s = NativeBLPhase2Stats(
        n_prism_cells=1024,
        n_wall_faces=512,
        n_wall_verts=256,
        total_thickness=0.05,
        n_degenerate_prisms=3,
        max_aspect_ratio=45.7,
        collision_safety_triggered=True,
        collision_scale_factor=0.82,
        feature_lock_triggered=True,
        n_feature_verts_locked=18,
    )
    assert s.n_prism_cells == 1024
    assert s.collision_safety_triggered is True
    assert s.feature_lock_triggered is True
    assert s.n_feature_verts_locked == 18


def test_additional_metrics_has_native_bl_phase2_field() -> None:
    """AdditionalMetrics 에 native_bl_phase2 필드 존재."""
    m = AdditionalMetrics()
    assert hasattr(m, "native_bl_phase2")
    assert m.native_bl_phase2 is None


def test_additional_metrics_with_bl_phase2() -> None:
    s = NativeBLPhase2Stats(n_prism_cells=500, max_aspect_ratio=12.0)
    m = AdditionalMetrics(native_bl_phase2=s)
    assert m.native_bl_phase2 is not None
    assert m.native_bl_phase2.n_prism_cells == 500


def test_extract_bl_phase2_stats_from_native_bl_result() -> None:
    """_extract_bl_phase2_stats 가 NativeBLResult 로부터 stats 변환."""
    from core.generator.tier_layers_post import _extract_bl_phase2_stats

    class FakeRes:
        success = True
        n_prism_cells = 200
        n_wall_faces = 100
        n_wall_verts = 50
        total_thickness = 0.01
        n_degenerate_prisms = 0
        max_aspect_ratio = 8.5
        message = "native_bl Phase 2 OK — collision_safety_scaled..."

    stats = _extract_bl_phase2_stats(FakeRes())
    assert stats is not None
    assert stats.n_prism_cells == 200
    assert stats.max_aspect_ratio == pytest.approx(8.5)
    assert stats.collision_safety_triggered is True


def test_extract_bl_phase2_stats_none_input() -> None:
    from core.generator.tier_layers_post import _extract_bl_phase2_stats
    assert _extract_bl_phase2_stats(None) is None


def test_tier_attempt_has_native_bl_phase2_field() -> None:
    from core.schemas import TierAttempt
    # Pydantic model_fields 로 확인
    assert "native_bl_phase2" in TierAttempt.model_fields


def test_tier_attempt_native_bl_phase2_assignable() -> None:
    from core.schemas import TierAttempt
    s = NativeBLPhase2Stats(n_prism_cells=100)
    t = TierAttempt(tier="t", status="success", time_seconds=0.1, native_bl_phase2=s)
    assert t.native_bl_phase2.n_prism_cells == 100
