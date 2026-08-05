from __future__ import annotations

from types import SimpleNamespace

from core.native_option_capabilities import capability, receipt_for_run


def test_native_receipt_marks_only_known_forwarded_option_verified() -> None:
    assert capability("native_tet", "seed_density") is not None
    receipt = receipt_for_run(
        engine="native_tet",
        forwarded={"seed_density": 20, "future_option": 7},
        success=True,
        result=SimpleNamespace(route="tet_harness"),
    )
    assert "/engine_options/tet/seed_density" in receipt["applied_verified"]
    assert "/engine_options/tet/future_option" in receipt["unsupported"]


def test_unrouted_surface_products_are_not_native_capabilities() -> None:
    assert capability("native_tri", "seed_density") is None
    receipt = receipt_for_run(
        engine="native_tri",
        forwarded={"seed_density": 10},
        success=True,
        result=SimpleNamespace(),
    )
    assert receipt["records"][0]["status"] == "unsupported"
