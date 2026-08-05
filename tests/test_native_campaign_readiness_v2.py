from __future__ import annotations

import json
from pathlib import Path

from core.evaluator.native_campaign_readiness_v2 import (
    SCHEMA,
    audit_native_campaign_config_v2,
    build_corpus_seal,
)
from core.evaluator.native_semantic_manifest import build_semantic_manifest, build_source_certificate
from tests.test_native_semantic_manifest import _ledger, _rows


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _fixture(tmp_path: Path) -> Path:
    source = tmp_path / "source.stl"
    source.write_bytes(b"cube-source")
    ledger = _ledger(source)
    semantic_result = build_semantic_manifest(ledger, "stl_facet", _rows())
    assert semantic_result["accepted"] is True
    semantic = semantic_result["manifest"]
    certificate_result = build_source_certificate(
        source, ledger, semantic, parser_name="fixture-parser", parser_version="1",
        authority_statement={"attested": True, "issuer": "repo-owner", "basis": "owned-cube-fixture"},
    )
    assert certificate_result["accepted"] is True
    certificate = certificate_result["certificate"]
    provenance = {
        "complete": True,
        "source_sha256": ledger["source_digest"],
        "semantic_manifest_sha256": semantic["manifest_sha256"],
        "certificate_sha256": certificate["certificate_sha256"],
    }
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        (baseline / name).write_text(name, encoding="utf-8")
    seal_result = build_corpus_seal("cube", source, ledger, semantic, certificate, provenance, baseline)
    assert seal_result["accepted"] is True
    paths = {}
    for name, payload in (("source_ledger", ledger), ("semantic", semantic), ("authority", certificate), ("provenance", provenance), ("seal", seal_result["seal"])):
        path = tmp_path / f"{name}.json"
        _write(path, payload)
        paths[name] = path
    config = tmp_path / "config.json"
    _write(config, {
        "schema": SCHEMA, "version": 2, "corpus_id": "cube-v2",
        "cases": [{"id": "cube", "source": str(source), "baseline": str(baseline), **{name: str(path) for name, path in paths.items()}}],
    })
    return config


def test_v2_accepts_recomputed_complete_case(tmp_path: Path) -> None:
    result = audit_native_campaign_config_v2(_fixture(tmp_path))
    assert result["accepted"] is True, result
    assert result["cases"][0]["ready"] is True


def test_v1_hash_only_config_is_explicitly_refused(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    _write(path, {"corpus_id": "legacy", "cases": [{"id": "cube", "authoritative": True}]})
    result = audit_native_campaign_config_v2(path)
    assert result["accepted"] is False
    assert result["reasons"] == ["legacy_hash_only_evidence"]


def test_v2_rejects_certificate_tamper_and_does_not_repair(tmp_path: Path) -> None:
    config = _fixture(tmp_path)
    payload = json.loads(config.read_text())
    certificate_path = Path(payload["cases"][0]["authority"])
    certificate = json.loads(certificate_path.read_text())
    certificate["source_size_bytes"] += 1
    _write(certificate_path, certificate)
    result = audit_native_campaign_config_v2(config)
    assert result["accepted"] is False
    assert any("certificate:" in reason for reason in result["reasons"])
    assert certificate["source_size_bytes"] == len(b"cube-source") + 1
