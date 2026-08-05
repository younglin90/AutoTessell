"""Validation of the user-declared source-binding ledger."""

from core.layers.native_tet_surface_source_ledger import validate_native_tet_surface_ledger


def test_user_declared_ledger_binds_real_sources_but_is_not_release_authority() -> None:
    result = validate_native_tet_surface_ledger(
        "docs/qa/authority/native_tet_surface_source_ledgers_v1.json", "."
    )
    assert result["valid_source_binding"] is True, result
    assert result["status"] == "USER_DECLARED_PROVISIONAL"
    assert result["release_eligible"] is False
    assert result["runtime_route"] == "default_off"
    assert result["feature_authority"] is False
    assert result["wall_edge_authority"] is False
