from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.input_contract import normalize_input_contract, project_legacy_parameters
from desktop.server import _build_run_kwargs, app


def test_explicit_zero_boundary_layer_is_identity_and_preserved() -> None:
    result = normalize_input_contract(
        {
            "schema_version": "1.0",
            "target": {"mode": "soft", "count": 0},
            "boundary_layers": [{"layers": 0, "growth_rate": 1.4}],
        },
        engine="native_tet",
    )
    assert result.config["target"]["count"] == 0
    entry = result.config["boundary_layers"][0]
    assert entry["layers"] == 0
    assert entry["status"] == "disabled_identity"
    assert entry["actual_layers"] == 0
    assert "boundary_layers[0]" in result.report["ignored_by_policy"]


@pytest.mark.parametrize(
    ("mode", "values"),
    [
        ("first_and_growth", {"first_height": 0.001, "growth_rate": 1.2}),
        ("first_and_total", {"first_height": 0.001, "total_thickness": 0.01}),
        ("total_and_growth", {"total_thickness": 0.01, "growth_rate": 1.2}),
        ("last_and_growth", {"last_height": 0.003, "growth_rate": 1.2}),
    ],
)
def test_boundary_layer_spacing_modes_accept_exact_pair(mode: str, values: dict[str, float]) -> None:
    values = {**values, "layers": 3, "spacing_mode": mode, "selector": {"physical_group": "wall"}}
    result = normalize_input_contract(
        {"schema_version": "1.0", "target": {"mode": "soft"}, "boundary_layers": [values]},
        engine="native_tet",
    )
    assert not result.report["errors"]


def test_boundary_layer_spacing_rejects_three_geometric_values() -> None:
    with pytest.raises(ValueError, match="requires exactly"):
        normalize_input_contract(
            {
                "schema_version": "1.0",
                "boundary_layers": [{
                    "layers": 2,
                    "spacing_mode": "first_and_growth",
                    "first_height": 0.001,
                    "growth_rate": 1.2,
                    "total_thickness": 0.01,
                    "selector": {"physical_group": "wall"},
                }],
            },
            engine="native_tet",
        )


def test_units_and_null_are_normalized_without_dropping_zero() -> None:
    result = normalize_input_contract(
        {
            "schema_version": "1.0",
            "input": {"units": "mm", "scale_factor": 2.0},
            "target": {"mode": "soft", "count": 0, "tolerance": None},
            "sizing": {"base_size": 10.0, "min_size": None},
        }
    )
    assert result.config["sizing"]["base_size"] == pytest.approx(0.02)
    assert result.config["sizing"]["min_size"] is None
    assert result.config["target"]["count"] == 0
    assert result.config["input"]["units"] == "m"


def test_target_hard_is_rejected_and_unknown_engine_option_is_reported() -> None:
    with pytest.raises(ValueError, match="target.mode"):
        normalize_input_contract({"schema_version": "1.0", "target": {"mode": "hard"}})
    result = normalize_input_contract(
        {
            "schema_version": "1.0",
            "engine_options": {"native_tet": {"future_option": 7}},
        },
        engine="native_tet",
    )
    assert "engine_options.native_tet.future_option" in result.report["unsupported"]


def test_legacy_mapping_preserves_explicit_bl_zero() -> None:
    mapped = _build_run_kwargs("standard", "native_tet", "tet", 1, {"bl_layers": 0})
    tsp = mapped["tier_specific_params"]
    assert tsp["bl_layers"] == 0
    assert tsp["cfmesh_bl_n_layers"] == 0
    assert mapped["input_config"]["boundary_layers"][0]["layers"] == 0


def test_nested_contract_reaches_run_kwargs_and_projection() -> None:
    mapped = _build_run_kwargs(
        "standard", "native_hex", "hex_dominant", 1,
        {"input_config": {
            "schema_version": "1.0",
            "target": {"mode": "soft", "count": 500},
            "sizing": {"base_size": 0.25},
            "engine_options": {"native_hex": {"snap_boundary": True}},
        }},
    )
    assert mapped["input_config"]["target"]["count"] == 500
    assert mapped["tier_specific_params"]["target_cells"] == 500
    assert mapped["tier_specific_params"]["snap_boundary"] is True
    assert mapped["tier_specific_params"]["input_parameter_report"]["schema_version"] == "1.0"


def test_legacy_projection_keeps_false_and_empty_values_as_contract_data() -> None:
    result = normalize_input_contract(
        {"schema_version": "1.0", "input": {"preserve_features": False}, "local_controls": []}
    )
    assert result.config["input"]["preserve_features"] is False
    assert result.config["local_controls"] == []


def test_server_schema_endpoint_is_authoritative() -> None:
    with TestClient(app) as client:
        response = client.get("/api/input-schema/v1")
    assert response.status_code == 200
    document = response.json()
    assert document["schema_version"] == "1.0"
    assert "boundary_layers.layers" in document["field_catalog"]
    assert document["target_modes"] == ["soft"]
