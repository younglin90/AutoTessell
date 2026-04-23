"""beta96 — y⁺ 자동 BL 두께 계산 회귀 테스트."""
from __future__ import annotations

import math
import pytest
from core.utils.yplus import estimate_first_layer_thickness, FLUID_PROPERTIES


def test_air_y1_reasonable_first_thickness() -> None:
    """공기 10 m/s, L=1 m, y⁺=1 → y_first ≈ 수 μm 범위."""
    r = estimate_first_layer_thickness(10.0, 1.0, fluid="air", y_plus_target=1.0)
    assert r.y_first > 0
    assert 1e-7 < r.y_first < 1e-3, f"y_first={r.y_first} 범위 초과"


def test_water_y1_smaller_than_air() -> None:
    """물은 동점성 계수가 낮아 공기보다 y_first 가 작다."""
    r_air = estimate_first_layer_thickness(1.0, 0.1, fluid="air")
    r_water = estimate_first_layer_thickness(1.0, 0.1, fluid="water")
    assert r_water.y_first < r_air.y_first


def test_higher_velocity_thinner_first_layer() -> None:
    """속도 높을수록 첫 층이 얇아진다."""
    r_slow = estimate_first_layer_thickness(1.0, 1.0)
    r_fast = estimate_first_layer_thickness(50.0, 1.0)
    assert r_fast.y_first < r_slow.y_first


def test_higher_yplus_thicker_first_layer() -> None:
    """y⁺ 타깃이 높을수록 첫 층이 두꺼워진다."""
    r1 = estimate_first_layer_thickness(10.0, 1.0, y_plus_target=1.0)
    r30 = estimate_first_layer_thickness(10.0, 1.0, y_plus_target=30.0)
    assert r30.y_first == pytest.approx(r1.y_first * 30.0, rel=0.01)


def test_custom_kinematic_viscosity() -> None:
    """custom nu 직접 지정 → fluid 무시."""
    nu = 3e-5
    r = estimate_first_layer_thickness(10.0, 1.0, kinematic_viscosity=nu)
    assert r.y_first > 0


def test_invalid_velocity_raises() -> None:
    with pytest.raises(ValueError, match="flow_velocity"):
        estimate_first_layer_thickness(-1.0, 1.0)


def test_invalid_length_raises() -> None:
    with pytest.raises(ValueError, match="characteristic_length"):
        estimate_first_layer_thickness(10.0, 0.0)


def test_unknown_fluid_raises() -> None:
    with pytest.raises(ValueError, match="알 수 없는 fluid"):
        estimate_first_layer_thickness(10.0, 1.0, fluid="helium")


def test_fluid_properties_has_air_water() -> None:
    assert "air" in FLUID_PROPERTIES
    assert "water" in FLUID_PROPERTIES
    assert FLUID_PROPERTIES["air"]["kinematic_viscosity"] == pytest.approx(1.516e-5, rel=0.1)


def test_low_re_uses_blasius() -> None:
    """Re < 5e5 → Blasius 층류 Cf (u_tau 매우 작음, y_first 매우 큼)."""
    # U=0.001, L=0.01 → Re << 5e5
    r = estimate_first_layer_thickness(0.001, 0.01, fluid="air", y_plus_target=1.0)
    assert r.re_l < 5e5
    assert r.y_first > 0


def test_message_contains_key_info() -> None:
    r = estimate_first_layer_thickness(5.0, 0.5, fluid="water", y_plus_target=5.0)
    assert "y⁺=5.0" in r.message
    assert "y_first=" in r.message
    assert "fluid=water" in r.message
