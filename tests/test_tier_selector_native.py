"""Strategist native-first tier 매핑 회귀 테스트 (v0.4.0-beta23)."""
from __future__ import annotations

import pytest

from core.strategist.tier_selector import (
    _MESH_TYPE_TIER_MAP,
    _MESH_TYPE_TIER_MAP_NATIVE,
    resolve_mesh_type_tier,
)


@pytest.mark.parametrize("mt", ["tet", "hex_dominant", "poly"])
@pytest.mark.parametrize("ql", ["draft", "standard", "fine"])
def test_resolve_mesh_type_tier_default_uses_legacy_primary(mt: str, ql: str) -> None:
    """prefer_native=False (기본) 는 기존 _MESH_TYPE_TIER_MAP 의 primary 반환."""
    result = resolve_mesh_type_tier(mt, ql, prefer_native=False)
    assert result is not None
    primary, fallbacks = result
    expected_primary = _MESH_TYPE_TIER_MAP[mt][ql][0]
    assert primary == expected_primary


@pytest.mark.parametrize("mt,expected_native", [
    ("tet", "tier_native_tet"),
    ("hex_dominant", "tier_native_hex"),
    ("poly", "tier_native_poly"),
])
@pytest.mark.parametrize("ql", ["draft", "standard", "fine"])
def test_resolve_with_prefer_native_promotes_native_tier(
    mt: str, expected_native: str, ql: str,
) -> None:
    """prefer_native=True 는 native tier 를 primary 로 승격."""
    result = resolve_mesh_type_tier(mt, ql, prefer_native=True)
    assert result is not None
    primary, fallbacks = result
    assert primary == expected_native


def test_resolve_with_prefer_native_keeps_legacy_as_fallback() -> None:
    """prefer_native=True 시 기존 legacy primary 는 fallback 맨 앞."""
    result = resolve_mesh_type_tier("hex_dominant", "fine", prefer_native=True)
    assert result is not None
    primary, fallbacks = result
    assert primary == "tier_native_hex"
    legacy_primary = _MESH_TYPE_TIER_MAP["hex_dominant"]["fine"][0]  # tier1_snappy
    assert fallbacks[0] == legacy_primary


def test_resolve_mesh_type_auto_returns_none() -> None:
    """mesh_type=auto 는 None 반환 (기존 동작)."""
    assert resolve_mesh_type_tier("auto", "fine", prefer_native=True) is None
    assert resolve_mesh_type_tier("", "standard") is None


def test_native_map_covers_all_mesh_types() -> None:
    """_MESH_TYPE_TIER_MAP_NATIVE 가 tet/hex_dominant/poly 모두 커버."""
    assert set(_MESH_TYPE_TIER_MAP_NATIVE) == {"tet", "hex_dominant", "poly"}
    for mt_table in _MESH_TYPE_TIER_MAP_NATIVE.values():
        assert {"draft", "standard", "fine"} <= set(mt_table.keys())


def test_prefer_native_deduplicates_if_already_in_legacy() -> None:
    """legacy fallback 에 이미 native tier 가 포함되어도 중복 없음."""
    # 인위적으로 legacy 에 native_hex 를 fallback 으로 추가
    saved = _MESH_TYPE_TIER_MAP["hex_dominant"]["draft"]
    _MESH_TYPE_TIER_MAP["hex_dominant"]["draft"] = ["tier15_cfmesh", "tier_native_hex", "tier1_snappy"]
    try:
        result = resolve_mesh_type_tier("hex_dominant", "draft", prefer_native=True)
        assert result is not None
        primary, fallbacks = result
        assert primary == "tier_native_hex"
        # native_hex 가 fallbacks 에 또 들어가지 않아야
        assert fallbacks.count("tier_native_hex") == 0
    finally:
        _MESH_TYPE_TIER_MAP["hex_dominant"]["draft"] = saved
