"""beta72 — GUI TIER_PARAM_SPECS 에 native_bl Phase 2 config 필드 등록 회귀.

beta63~65 에서 추가된 `BLConfig` 6 필드를 AutoTessellWindow 파라미터 스펙에 노출.
"""
from __future__ import annotations

import pytest


_EXPECTED_BL_PHASE2_KEYS = {
    "bl_collision_safety",
    "bl_collision_safety_factor",
    "bl_feature_lock",
    "bl_feature_angle_deg",
    "bl_feature_reduction_ratio",
    "bl_quality_check_enabled",
    "bl_aspect_ratio_threshold",
}


def _load_spec_keys() -> set[str]:
    from desktop.qt_app.main_window import AutoTessellWindow
    return {row[0] for row in AutoTessellWindow.TIER_PARAM_SPECS}


def test_tier_param_specs_includes_all_phase2_keys() -> None:
    """7 필드 모두 TIER_PARAM_SPECS 에 등록됨."""
    keys = _load_spec_keys()
    missing = _EXPECTED_BL_PHASE2_KEYS - keys
    assert not missing, f"누락된 필드: {missing}"


def test_bl_collision_safety_is_bool() -> None:
    from desktop.qt_app.main_window import AutoTessellWindow
    for row in AutoTessellWindow.TIER_PARAM_SPECS:
        if row[0] == "bl_collision_safety":
            assert row[2] == "bool"
            assert row[3] == "true"
            return
    pytest.fail("bl_collision_safety not found")


def test_bl_feature_angle_deg_default_45() -> None:
    from desktop.qt_app.main_window import AutoTessellWindow
    for row in AutoTessellWindow.TIER_PARAM_SPECS:
        if row[0] == "bl_feature_angle_deg":
            assert row[2] == "float"
            assert row[3] == "45.0"
            return
    pytest.fail("bl_feature_angle_deg not found")


def test_bl_aspect_ratio_threshold_default_50() -> None:
    from desktop.qt_app.main_window import AutoTessellWindow
    for row in AutoTessellWindow.TIER_PARAM_SPECS:
        if row[0] == "bl_aspect_ratio_threshold":
            assert row[2] == "float"
            assert row[3] == "50.0"
            return
    pytest.fail("bl_aspect_ratio_threshold not found")


def test_existing_bl_phase1_keys_still_present() -> None:
    """Phase 2 추가하면서 Phase 1 필드 (bl_num_layers 등) 를 지우지 않았는지."""
    keys = _load_spec_keys()
    for k in ("bl_num_layers", "bl_first_thickness", "bl_growth_ratio",
              "bl_feature_angle"):
        assert k in keys, f"phase 1 필드 {k} 가 누락됨"
