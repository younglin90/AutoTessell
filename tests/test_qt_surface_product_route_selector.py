"""Headless contracts for the explicit native surface-product GUI choices."""

from __future__ import annotations

from desktop.qt_app.main_window import AutoTessellWindow


class _RouteCombo:
    def __init__(self, data: object, text: str) -> None:
        self._data = data
        self._text = text

    def currentData(self) -> object:
        return self._data

    def currentText(self) -> str:
        return self._text


def test_gui_surface_product_items_are_distinct_and_truthfully_deferred() -> None:
    items = AutoTessellWindow._SURFACE_PRODUCT_ROUTE_ITEMS

    assert tuple(route for _, route in items) == (
        "native_tri",
        "native_strict_quad",
        "native_tri_quad",
    )
    assert "fail-closed" in items[0][0]
    assert "certificate required" in items[1][0]
    assert "certificate required" in items[2][0]
    assert all("native_quad_dominant" not in item for item in items)


def test_gui_remesh_selector_prefers_explicit_route_value_over_display_label() -> None:
    window = AutoTessellWindow()
    window._remesh_engine_combo = _RouteCombo(
        "native_strict_quad",
        "Native Strict QUAD — certificate required (deferred)",
    )

    assert window._remesh_engine_text() == "native_strict_quad"


def test_gui_remesh_selector_keeps_legacy_text_fallback() -> None:
    window = AutoTessellWindow()
    window._remesh_engine_combo = _RouteCombo(None, "native_isotropic")

    assert window._remesh_engine_text() == "native_isotropic"
