from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.evaluator.native_campaign_readiness import audit_native_campaign_config


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _ready_config(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    source = root / "source.stl"
    baseline = root / "baseline"
    authority = root / "authority.json"
    semantic = root / "semantic.json"
    provenance = root / "provenance.json"
    root.mkdir()
    source.write_bytes(b"source")
    baseline.mkdir()
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        (baseline / name).write_text(name, encoding="utf-8")
    source_sha = _sha(source)
    _write_json(authority, {"authoritative": True, "source_sha256": source_sha})
    _write_json(semantic, {
        "source_sha256": source_sha, "mapping_table_sha256": "a" * 64,
        "features_sha256": "a" * 64, "patches_sha256": "a" * 64,
        "physical_groups_sha256": "a" * 64, "components_sha256": "a" * 64,
        "provenance_sha256": "a" * 64, "coverage_complete": True, "bijection": True,
    })
    _write_json(provenance, {"complete": True, "source_sha256": source_sha})
    config = root / "config.json"
    _write_json(config, {"corpus_id": "test", "cases": [{
        "id": "cube", "source": str(source), "baseline": str(baseline),
        "authority": str(authority), "semantic": str(semantic), "provenance": str(provenance),
    }]})
    return config


def test_readiness_accepts_only_complete_explicit_evidence(tmp_path):
    result = audit_native_campaign_config(_ready_config(tmp_path))
    assert result["accepted"] is True
    assert result["cases"][0]["ready"] is True


def test_readiness_reports_missing_ledgers_without_repairing_or_copying(tmp_path):
    config = _ready_config(tmp_path)
    payload = json.loads(config.read_text())
    payload["cases"][0]["semantic"] = str(tmp_path / "missing-semantic.json")
    config.write_text(json.dumps(payload), encoding="utf-8")
    result = audit_native_campaign_config(config)
    assert result["accepted"] is False
    assert "cube:semantic:file_missing" in result["reasons"]
    assert not (tmp_path / "missing-semantic.json").exists()
