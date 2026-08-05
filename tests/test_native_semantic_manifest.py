from __future__ import annotations

import hashlib
from pathlib import Path

from core.evaluator.native_semantic_manifest import (
    build_semantic_manifest,
    build_source_certificate,
    validate_semantic_manifest,
)


def _ledger(source: Path) -> dict:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return {
        "source_digest": digest,
        "source": {"sha256": digest},
        "ledger_digest": "b" * 64,
        "selector_namespaces": {
            "stl_facet": {
                "available": True,
                "count": 2,
                "id_ranges": [[0, 1]],
                "records": [{"id": 0}, {"id": 1}],
            }
        },
    }


def _rows() -> list[dict[str, object]]:
    return [
        {"source_id": 0, "feature": "f0", "patch": "wall", "physical_group": "fluid", "component": "body", "provenance": "p0"},
        {"source_id": 1, "feature": "f1", "patch": "wall", "physical_group": "fluid", "component": "body", "provenance": "p1"},
    ]


def test_explicit_manifest_and_certificate_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(b"authoritative-source")
    ledger = _ledger(source)
    built = build_semantic_manifest(ledger, "stl_facet", _rows())
    assert built["accepted"] is True, built
    manifest = built["manifest"]
    checked = validate_semantic_manifest(manifest, ledger)
    assert checked["accepted"] is True, checked
    cert = build_source_certificate(
        source,
        ledger,
        manifest,
        parser_name="explicit-stl-ingress",
        parser_version="1",
        authority_statement={"attested": True, "issuer": "test-owner", "basis": "raw-bytes-and-explicit-manifest"},
    )
    assert cert["accepted"] is True, cert
    assert cert["certificate"]["authority_status"] == "SOURCE_VERIFIED"


def test_manifest_rejects_semantic_tamper_and_digest_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(b"source")
    ledger = _ledger(source)
    manifest = build_semantic_manifest(ledger, "stl_facet", _rows())["manifest"]
    manifest["rows"][0]["patch"] = "tampered"
    result = validate_semantic_manifest(manifest, ledger)
    assert result["accepted"] is False
    assert "manifest_digest_mismatch" in result["reasons"]


def test_manifest_rejects_duplicate_or_unavailable_rows_without_repair(tmp_path: Path) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(b"source")
    ledger = _ledger(source)
    rows = _rows()
    rows[1]["source_id"] = 0
    built = build_semantic_manifest(ledger, "stl_facet", rows)
    assert built["accepted"] is False
    assert "source_id_duplicate" in built["reasons"]
    assert built["manifest"]["rows"][1]["source_id"] == 0


def test_certificate_requires_explicit_attestation_and_exact_source_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(b"source")
    ledger = _ledger(source)
    manifest = build_semantic_manifest(ledger, "stl_facet", _rows())["manifest"]
    missing = build_source_certificate(
        source, ledger, manifest, parser_name="p", parser_version="1", authority_statement=None
    )
    assert missing["accepted"] is False
    source.write_bytes(b"tampered")
    mismatch = build_source_certificate(
        source,
        ledger,
        manifest,
        parser_name="p",
        parser_version="1",
        authority_statement={"attested": True, "issuer": "owner", "basis": "explicit"},
    )
    assert mismatch["accepted"] is False
    assert "source_file_digest_mismatch" in mismatch["reasons"]
