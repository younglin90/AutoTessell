"""beta67 — ENGINE_PARAM_REGISTRY 에 native_* 엔진 spec 등록 검증."""
from __future__ import annotations

import pytest

from desktop.qt_app.widgets.engine_params_spec import (
    ENGINE_KEY_ALIASES,
    ENGINE_PARAM_REGISTRY,
    EngineParamSpec,
    get_specs_for_engine,
    resolve_engine_key,
)


# ---------------------------------------------------------------------------
# native_* 엔진 등록 확인
# ---------------------------------------------------------------------------


def test_native_tet_registered_in_registry() -> None:
    assert "native_tet" in ENGINE_PARAM_REGISTRY
    specs = ENGINE_PARAM_REGISTRY["native_tet"]
    keys = {s.key for s in specs}
    assert "seed_density" in keys
    assert "sliver_quality_threshold" in keys  # beta62


def test_native_hex_registered_with_beta61_and_beta66_params() -> None:
    specs = ENGINE_PARAM_REGISTRY["native_hex"]
    keys = {s.key for s in specs}
    assert "max_cells_per_axis" in keys  # beta61
    assert "snap_boundary" in keys
    assert "preserve_features" in keys   # beta66
    assert "feature_angle_deg" in keys   # beta66


def test_native_poly_registered_with_beta56_param() -> None:
    specs = ENGINE_PARAM_REGISTRY["native_poly"]
    keys = {s.key for s in specs}
    assert "max_tet_cells" in keys  # beta56
    assert "seed_density" in keys
    assert "max_iter" in keys


# ---------------------------------------------------------------------------
# Tier alias → engine key
# ---------------------------------------------------------------------------


def test_tier_native_tet_alias_maps_to_native_tet() -> None:
    assert ENGINE_KEY_ALIASES["tier_native_tet"] == "native_tet"


def test_tier_native_hex_alias_maps_to_native_hex() -> None:
    assert ENGINE_KEY_ALIASES["tier_native_hex"] == "native_hex"


def test_tier_native_poly_alias_maps_to_native_poly() -> None:
    assert ENGINE_KEY_ALIASES["tier_native_poly"] == "native_poly"


def test_resolve_engine_key_accepts_tier_and_alias() -> None:
    """resolve_engine_key 가 tier 와 alias 양쪽을 받아들임."""
    assert resolve_engine_key("tier_native_hex") == "native_hex"
    assert resolve_engine_key("native_hex") == "native_hex"


# ---------------------------------------------------------------------------
# get_specs_for_engine 반환 형식
# ---------------------------------------------------------------------------


def test_get_specs_for_engine_returns_list_of_specs() -> None:
    specs = get_specs_for_engine("native_hex")
    assert isinstance(specs, list)
    assert all(isinstance(s, EngineParamSpec) for s in specs)


def test_get_specs_for_engine_unknown_returns_empty() -> None:
    assert get_specs_for_engine("xyz_unknown") == []


# ---------------------------------------------------------------------------
# spec 필드 타입 sanity (기본값이 올바른 type 인지)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine", ["native_tet", "native_hex", "native_poly"])
def test_native_spec_defaults_match_kind(engine: str) -> None:
    for s in ENGINE_PARAM_REGISTRY[engine]:
        if s.kind == "int":
            assert isinstance(s.default, int), f"{engine}.{s.key} default type"
        elif s.kind == "float":
            assert isinstance(s.default, (int, float)), f"{engine}.{s.key}"
        elif s.kind == "bool":
            assert isinstance(s.default, bool), f"{engine}.{s.key}"
