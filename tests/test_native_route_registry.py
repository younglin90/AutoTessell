from core.evaluator.native_route_registry import (
    ROUTE_REGISTRY,
    native_route_registry_manifest,
    select_native_route,
)


def test_registry_covers_all_native_products_and_is_json_safe():
    assert set(ROUTE_REGISTRY) == {
        "native-tet", "native-hex", "native-poly", "native-tri",
        "strict-quad", "tri-quad",
    }
    manifest = native_route_registry_manifest()
    assert manifest["schema"] == "autotessell/native-route-registry/v1"
    assert manifest["products"]["native-tet"]["boundary_layers"] == [0, 1, 5]


def test_volume_routes_select_positive_bl_but_still_require_gate4():
    result = select_native_route("native-tet", boundary_layers=5, source_kind="stl")
    assert result["accepted"] is True
    assert result["positive_boundary_layer_witness_required"] is True
    assert result["gate4_evidence_required"] is True
    assert result["release_claim_eligible"] is False


def test_surface_routes_refuse_unimplemented_positive_bl_explicitly():
    for product in ("native-tri", "strict-quad", "tri-quad"):
        result = select_native_route(product, boundary_layers=1, source_kind="stl")
        assert result["accepted"] is False
        assert result["release_claim_eligible"] is False
        assert result["reasons"] == ["boundary_layers_unsupported_by_route"]


def test_hex_requires_cad_source_and_unknown_values_fail_closed():
    assert select_native_route("native-hex", boundary_layers=0, source_kind="stl")["accepted"] is False
    assert select_native_route("missing", boundary_layers=0, source_kind="cad")["reasons"] == ["product_unknown"]
    assert select_native_route("native-tet", boundary_layers=-1, source_kind="stl")["reasons"] == ["boundary_layers_invalid"]
