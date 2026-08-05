from core.input_contract import normalize_input_contract, project_legacy_parameters


def test_versioned_target_count_is_soft_not_a_hidden_hard_cap():
    normalized = normalize_input_contract(
        {
            "schema_version": "1.0",
            "target": {"mode": "soft", "count": 500},
        },
        engine="native_tet",
    )
    projected = project_legacy_parameters(normalized.config, "native_tet")
    assert projected["target_cells"] == 500
    assert "max_cells" not in projected


def test_explicit_hard_max_is_separate_from_soft_target():
    normalized = normalize_input_contract(
        {
            "schema_version": "1.0",
            "target": {"mode": "soft", "count": 500, "hard_max_cells": 700},
        },
        engine="native_tet",
    )
    projected = project_legacy_parameters(normalized.config, "native_tet")
    assert projected["target_cells"] == 500
    assert projected["max_cells"] == 700
