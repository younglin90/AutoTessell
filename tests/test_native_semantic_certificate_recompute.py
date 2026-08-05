from __future__ import annotations

from pathlib import Path

from core.evaluator.native_semantic_manifest import (
    build_semantic_manifest,
    build_source_certificate,
    validate_source_certificate,
)
from tests.test_native_semantic_manifest import _ledger, _rows


def test_certificate_is_recomputed_from_source_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(b"source")
    ledger = _ledger(source)
    manifest = build_semantic_manifest(ledger, "stl_facet", _rows())["manifest"]
    built = build_source_certificate(
        source,
        ledger,
        manifest,
        parser_name="parser",
        parser_version="1",
        authority_statement={"attested": True, "issuer": "owner", "basis": "explicit"},
    )
    assert built["accepted"] is True, built
    checked = validate_source_certificate(built["certificate"], source, ledger, manifest)
    assert checked["accepted"] is True, checked
    built["certificate"]["source_size_bytes"] += 1
    rejected = validate_source_certificate(built["certificate"], source, ledger, manifest)
    assert rejected["accepted"] is False
    assert "certificate_recomputed_value_mismatch" in rejected["reasons"]
