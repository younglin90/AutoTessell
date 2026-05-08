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


def test_build_bl_config_smesh_set_ignore_faces() -> None:
    cfg = _build_bl_config(
        BLConfig,
        {
            "post_layers_wall_patch_names": "body_wall, nacelle",
            "post_layers_set_faces": "10,11;12",
            "post_layers_ignore_faces": [11, "13"],
            "post_layers_ignore_patch_names": "farfield",
            "post_layers_ignore_patch_prefixes": "domain_,symmetry_",
        },
        3, 1.2, 0.001,
    )
    assert cfg.wall_patch_names == ["body_wall", "nacelle"]
    assert cfg.set_faces == [10, 11, 12]
    assert cfg.ignore_faces == [11, 13]
    assert cfg.ignore_patch_names == ["farfield"]
    assert cfg.ignore_patch_prefixes == ["domain_", "symmetry_"]


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
    # beta2253 에서 1000.0 으로 raise (shrink_iter=1 + 큰 임계값으로 e_outer/h ↓).
    assert cfg.aspect_ratio_threshold == pytest.approx(1000.0)


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


# ---------------------------------------------------------------------------
# beta2287 — y+ in-engine flow params propagation
# ---------------------------------------------------------------------------


def test_build_bl_config_target_y_plus_propagated() -> None:
    """beta2287 회귀: bl_target_y_plus 가 BLConfig.target_y_plus 로 전달되어
    in-engine 자동 first_thickness 역산 경로가 작동해야 함."""
    cfg = _build_bl_config(
        BLConfig, {"bl_target_y_plus": 1.0}, 3, 1.2, 0.001,
    )
    assert cfg.target_y_plus == pytest.approx(1.0)


def test_build_bl_config_target_y_plus_default_none() -> None:
    cfg = _build_bl_config(BLConfig, {}, 3, 1.2, 0.001)
    assert cfg.target_y_plus is None


def test_build_bl_config_flow_velocity_propagated() -> None:
    cfg = _build_bl_config(
        BLConfig, {"bl_flow_velocity": 25.0}, 3, 1.2, 0.001,
    )
    assert cfg.flow_velocity == pytest.approx(25.0)


def test_build_bl_config_flow_kinematic_viscosity_propagated() -> None:
    cfg = _build_bl_config(
        BLConfig, {"bl_flow_kinematic_viscosity": 1.0e-6}, 3, 1.2, 0.001,
    )
    assert cfg.flow_kinematic_viscosity == pytest.approx(1.0e-6)


def test_build_bl_config_flow_characteristic_length_propagated() -> None:
    cfg = _build_bl_config(
        BLConfig, {"bl_flow_characteristic_length": 0.5}, 3, 1.2, 0.001,
    )
    assert cfg.flow_characteristic_length == pytest.approx(0.5)


def test_build_bl_config_flow_fluid_preset_propagated() -> None:
    cfg = _build_bl_config(
        BLConfig, {"bl_flow_fluid_preset": "water_20C"}, 3, 1.2, 0.001,
    )
    assert cfg.flow_fluid_preset == "water_20C"


def test_build_bl_config_fine_quality_uses_strict_feature_angle() -> None:
    """beta2347 + beta2348 — quality_level='fine' 시 feature_angle_deg=30 +
    safety_factor=0.4 + aspect_ratio_threshold=300 (cfMesh/T-Rex 정렬)."""
    cfg = _build_bl_config(BLConfig, {}, 3, 1.2, 0.001, quality_level="fine")
    assert cfg.feature_angle_deg == pytest.approx(30.0)
    assert cfg.collision_safety_factor == pytest.approx(0.4)
    # beta2348 — 1000 (default) → 300 (fine).
    assert cfg.aspect_ratio_threshold == pytest.approx(300.0)


def test_build_bl_config_draft_quality_keeps_default() -> None:
    """beta2347 — draft / standard / 미설정 시 BLConfig default 유지 (45° / 0.5)."""
    for ql in ("draft", "standard", "", None):
        cfg = _build_bl_config(BLConfig, {}, 3, 1.2, 0.001, quality_level=ql)
        assert cfg.feature_angle_deg == pytest.approx(45.0), f"ql={ql}"
        assert cfg.collision_safety_factor == pytest.approx(0.5), f"ql={ql}"


def test_build_bl_config_explicit_override_wins_over_quality_default() -> None:
    """beta2347 — 사용자 명시 override (params 키) 가 quality default 보다 우선."""
    params = {
        "bl_feature_angle_deg": 60.0,
        "bl_collision_safety_factor": 0.7,
    }
    cfg = _build_bl_config(BLConfig, params, 3, 1.2, 0.001, quality_level="fine")
    assert cfg.feature_angle_deg == pytest.approx(60.0)
    assert cfg.collision_safety_factor == pytest.approx(0.7)


def test_build_bl_config_y_plus_full_chain() -> None:
    """y+ + 모든 flow_* 필드 동시 propagation."""
    params = {
        "bl_target_y_plus": 30.0,
        "bl_flow_velocity": 5.0,
        "bl_flow_kinematic_viscosity": 1.5e-5,
        "bl_flow_characteristic_length": 1.0,
        "bl_flow_fluid_preset": "air_20C",
    }
    cfg = _build_bl_config(BLConfig, params, 5, 1.3, 0.001)
    assert cfg.target_y_plus == pytest.approx(30.0)
    assert cfg.flow_velocity == pytest.approx(5.0)
    assert cfg.flow_kinematic_viscosity == pytest.approx(1.5e-5)
    assert cfg.flow_characteristic_length == pytest.approx(1.0)
    assert cfg.flow_fluid_preset == "air_20C"
