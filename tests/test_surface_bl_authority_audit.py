"""Repository authority audit evidence after the user-declared ledger is added."""

from core.layers.surface_bl_authority_audit import audit_repository_authority


def test_repository_finds_only_the_explicit_provisional_surface_ledger() -> None:
    report = audit_repository_authority(".")
    assert report["route"] == "default_off"
    assert report["authority_found"] is True
    paths = {item["path"] for item in report["usable_ledgers"]}
    assert "docs/qa/authority/native_tet_surface_source_ledgers_v1.json" in paths
