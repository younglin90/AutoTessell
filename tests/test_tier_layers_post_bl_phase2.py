"""beta75 — tier_layers_post 가 params dict 에서 native_bl Phase 2 config 를
읽어 BLConfig 에 올바르게 전달하는지 검증 (Ph72 GUI 배선의 백엔드 완성).
"""
from __future__ import annotations

import pytest

from core.generator.tier_layers_post import _build_bl_config, _coerce_bool
from core.layers.native_bl import BLConfig


# ---------------------------------------------------------------------------
# _coerce_bool helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("v,default,expected", [
    (None, True, True),
    (None, False, False),
    (True, False, True),
    (False, True, False),
    ("true", False, True),
    ("TRUE", False, True),
    ("false", True, False),
    ("0", True, False),
    ("1", False, True),
    ("yes", False, True),
    ("no", True, False),
    ("garbage", True, True),  # 알 수 없는 값 → default
    ("garbage", False, False),
])
def test_coerce_bool_matrix(v, default, expected) -> None:
    assert _coerce_bool(v, default) is expected


# ---------------------------------------------------------------------------
# _build_bl_config — Phase 1 필드
# ---------------------------------------------------------------------------


def test_build_bl_config_phase1_basic() -> None:
    cfg = _build_bl_config(BLConfig, {}, 3, 1.2, 0.001)
    assert cfg.num_layers == 3
    assert cfg.growth_ratio == pytest.approx(1.2)
    assert cfg.first_thickness == pytest.approx(0.001)
    assert cfg.max_total_ratio == pytest.approx(0.3)
    assert cfg.backup_original is True


def test_build_bl_config_phase1_wall_patch_names() -> None:
    cfg = _build_bl_config(
        BLConfig,
        {"post_layers_wall_patch_names": ["wall1", "wall2"]},
        2, 1.1, 0.002,
    )
    assert cfg.wall_patch_names == ["wall1", "wall2"]


def test_build_bl_config_phase1_backup_override_false() -> None:
    cfg = _build_bl_config(
        BLConfig, {"post_layers_backup_original": False}, 3, 1.2, 0.001,
    )
    assert cfg.backup_original is False


def test_build_bl_config_phase1_max_total_ratio_override() -> None:
    cfg = _build_bl_config(
        BLConfig, {"post_layers_max_total_ratio": 0.1}, 3, 1.2, 0.001,
    )
    assert cfg.max_total_ratio == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# _build_bl_config — Phase 2 defaults
# ---------------------------------------------------------------------------


def test_build_bl_config_phase2_defaults_preserved() -> None:
    """params 에 Phase 2 키 미존재 → BLConfig 기본값 (collision_safety=True 등)."""
    cfg = _build_bl_config(BLConfig, {}, 3, 1.2, 0.001)
    assert cfg.collision_safety is True
    assert cfg.collision_safety_factor == pytest.approx(0.5)
    assert cfg.feature_lock is True
    assert cfg.feature_angle_deg == pytest.approx(45.0)
    assert cfg.feature_reduction_ratio == pytest.approx(0.5)
    assert cfg.quality_check_enabled is True
    assert cfg.aspect_ratio_threshold == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# _build_bl_config — Phase 2 override
# ---------------------------------------------------------------------------


def test_build_bl_config_phase2_collision_safety_off() -> None:
    """bl_collision_safety=false → collision_safety=False 로 전파."""
    cfg = _build_bl_config(
        BLConfig, {"bl_collision_safety": "false"}, 3, 1.2, 0.001,
    )
    assert cfg.collision_safety is False


def test_build_bl_config_phase2_feature_lock_off() -> None:
    cfg = _build_bl_config(
        BLConfig, {"bl_feature_lock": False}, 3, 1.2, 0.001,
    )
    assert cfg.feature_lock is False


def test_build_bl_config_phase2_feature_angle_override() -> None:
    cfg = _build_bl_config(
        BLConfig, {"bl_feature_angle_deg": 30.0}, 3, 1.2, 0.001,
    )
    assert cfg.feature_angle_deg == pytest.approx(30.0)


def test_build_bl_config_phase2_aspect_ratio_override() -> None:
    cfg = _build_bl_config(
        BLConfig, {"bl_aspect_ratio_threshold": 100.0}, 3, 1.2, 0.001,
    )
    assert cfg.aspect_ratio_threshold == pytest.approx(100.0)


def test_build_bl_config_phase2_all_override_together() -> None:
    params = {
        "bl_collision_safety": False,
        "bl_collision_safety_factor": 0.7,
        "bl_feature_lock": False,
        "bl_feature_angle_deg": 60.0,
        "bl_feature_reduction_ratio": 0.3,
        "bl_quality_check_enabled": False,
        "bl_aspect_ratio_threshold": 80.0,
    }
    cfg = _build_bl_config(BLConfig, params, 3, 1.2, 0.001)
    assert cfg.collision_safety is False
    assert cfg.collision_safety_factor == pytest.approx(0.7)
    assert cfg.feature_lock is False
    assert cfg.feature_angle_deg == pytest.approx(60.0)
    assert cfg.feature_reduction_ratio == pytest.approx(0.3)
    assert cfg.quality_check_enabled is False
    assert cfg.aspect_ratio_threshold == pytest.approx(80.0)
