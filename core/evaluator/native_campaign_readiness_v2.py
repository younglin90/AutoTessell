"""Strict v2 release-corpus readiness audit.

Version 1 evidence is diagnostic only. This v2 auditor requires recomputed
source/semantic/certificate evidence and an immutable baseline seal; it never
repairs or infers missing files.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.evaluator.native_semantic_manifest import (
    validate_semantic_manifest,
    validate_source_certificate,
)

SCHEMA = "autotessell/native-campaign-readiness/v2"
SEAL_SCHEMA = "autotessell/native-corpus-seal/v1"
REQUIRED_BASELINE_FILES = ("points", "faces", "owner", "neighbour", "boundary")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(payload.encode())


def _json(path: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "json_invalid"
    return (value, None) if isinstance(value, Mapping) else (None, "json_object_required")


def _tree_digest(root: Path) -> tuple[str | None, list[dict[str, Any]], str | None]:
    if root.is_symlink() or not root.is_dir():
        return None, [], "baseline_directory_missing"
    records: list[dict[str, Any]] = []
    try:
        paths = sorted(path for path in root.rglob("*") if path.is_file() or path.is_symlink())
        for path in paths:
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                return None, records, "baseline_symlink_forbidden"
            digest = _sha256_file(path)
            if digest is None:
                return None, records, "baseline_file_unreadable"
            records.append({"path": relative, "sha256": digest, "size": path.stat().st_size})
    except OSError:
        return None, records, "baseline_tree_unreadable"
    return _digest(records), records, None


def build_corpus_seal(
    case_id: str,
    source_path: str | Path,
    ledger: Mapping[str, Any],
    semantic_manifest: Mapping[str, Any],
    certificate: Mapping[str, Any],
    provenance: Mapping[str, Any],
    baseline_path: str | Path,
) -> dict[str, Any]:
    """Create a seal from already explicit evidence; no source is modified."""
    source_sha = _sha256_file(Path(source_path))
    tree_sha, records, tree_reason = _tree_digest(Path(baseline_path))
    if source_sha is None or tree_sha is None:
        return {"accepted": False, "reasons": [tree_reason or "source_file_missing"]}
    payload = {
        "schema": SEAL_SCHEMA,
        "case_id": case_id,
        "source_sha256": source_sha,
        "source_ledger_sha256": ledger.get("ledger_digest"),
        "semantic_manifest_sha256": semantic_manifest.get("manifest_sha256"),
        "certificate_sha256": certificate.get("certificate_sha256"),
        "provenance_sha256": _digest(provenance),
        "baseline_tree_sha256": tree_sha,
        "baseline_entry_count": len(records),
        "baseline_tree_repeats": [tree_sha, tree_sha, tree_sha],
    }
    seal = dict(payload)
    seal["seal_sha256"] = _digest(payload)
    return {"accepted": True, "seal": seal, "seal_sha256": seal["seal_sha256"]}


def _audit_case(case: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    case_id = case.get("id")
    source_path = Path(case["source"]) if isinstance(case.get("source"), str) else None
    source_sha = _sha256_file(source_path) if source_path is not None else None
    if source_sha is None:
        reasons.append("source_missing_or_symlink")

    baseline_path = Path(case["baseline"]) if isinstance(case.get("baseline"), str) else None
    if baseline_path is None or baseline_path.is_symlink() or not baseline_path.is_dir():
        reasons.append("baseline_directory_missing")
    else:
        for name in REQUIRED_BASELINE_FILES:
            candidate = baseline_path / name
            if not candidate.is_file() or candidate.is_symlink():
                reasons.append(f"baseline_{name}_missing_or_symlink")

    def load(name: str) -> Mapping[str, Any] | None:
        value = case.get(name)
        if not isinstance(value, str):
            reasons.append(f"{name}_path_missing")
            return None
        payload, error = _json(Path(value))
        if error:
            reasons.append(f"{name}_{error}")
        return payload

    ledger = load("source_ledger")
    semantic = load("semantic")
    certificate = load("authority")
    provenance = load("provenance")
    seal = load("seal")
    if ledger is not None:
        if ledger.get("source_digest") != source_sha:
            reasons.append("ledger_source_digest_mismatch")
        source = ledger.get("source")
        if not isinstance(source, Mapping) or source.get("sha256") != source_sha:
            reasons.append("ledger_source_sha256_mismatch")
    if ledger is not None and semantic is not None:
        check = validate_semantic_manifest(semantic, ledger)
        if check["accepted"] is not True:
            reasons.extend(f"semantic:{reason}" for reason in check["reasons"])
    if ledger is not None and semantic is not None and certificate is not None and source_path is not None:
        check = validate_source_certificate(certificate, source_path, ledger, semantic)
        if check["accepted"] is not True:
            reasons.extend(f"certificate:{reason}" for reason in check["reasons"])
    if provenance is not None:
        if provenance.get("complete") is not True:
            reasons.append("provenance_incomplete")
        if provenance.get("source_sha256") != source_sha:
            reasons.append("provenance_source_digest_mismatch")
        if semantic is not None and provenance.get("semantic_manifest_sha256") != semantic.get("manifest_sha256"):
            reasons.append("provenance_semantic_digest_mismatch")
        if certificate is not None and provenance.get("certificate_sha256") != certificate.get("certificate_sha256"):
            reasons.append("provenance_certificate_digest_mismatch")
    if seal is not None and baseline_path is not None and source_sha is not None:
        tree_sha, records, tree_reason = _tree_digest(baseline_path)
        if tree_reason:
            reasons.append(tree_reason)
        seal_payload = {key: value for key, value in seal.items() if key != "seal_sha256"}
        if seal.get("schema") != SEAL_SCHEMA or seal.get("case_id") != case_id:
            reasons.append("seal_identity_mismatch")
        if seal.get("source_sha256") != source_sha:
            reasons.append("seal_source_digest_mismatch")
        if ledger is not None and seal.get("source_ledger_sha256") != ledger.get("ledger_digest"):
            reasons.append("seal_ledger_digest_mismatch")
        if semantic is not None and seal.get("semantic_manifest_sha256") != semantic.get("manifest_sha256"):
            reasons.append("seal_semantic_digest_mismatch")
        if certificate is not None and seal.get("certificate_sha256") != certificate.get("certificate_sha256"):
            reasons.append("seal_certificate_digest_mismatch")
        if provenance is not None and seal.get("provenance_sha256") != _digest(provenance):
            reasons.append("seal_provenance_digest_mismatch")
        if seal.get("baseline_tree_sha256") != tree_sha:
            reasons.append("seal_baseline_tree_digest_mismatch")
        if seal.get("baseline_entry_count") != len(records):
            reasons.append("seal_baseline_entry_count_mismatch")
        if seal.get("baseline_tree_repeats") != [tree_sha, tree_sha, tree_sha]:
            reasons.append("seal_baseline_repeatability_incomplete")
        if seal.get("seal_sha256") != _digest(seal_payload):
            reasons.append("seal_digest_mismatch")
    return {
        "id": case_id,
        "ready": not reasons,
        "reasons": sorted(set(reasons)),
        "source": {"path": case.get("source"), "sha256": source_sha},
        "baseline": {"path": case.get("baseline")},
        "source_ledger": {"path": case.get("source_ledger")},
        "semantic": {"path": case.get("semantic")},
        "authority": {"path": case.get("authority")},
        "provenance": {"path": case.get("provenance")},
        "seal": {"path": case.get("seal")},
    }


def audit_native_campaign_config_v2(config_path: str | Path) -> dict[str, Any]:
    """Audit only v2 configs; legacy/hash-only configs are explicit refusals."""
    path = Path(config_path)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"schema": SCHEMA, "accepted": False, "reasons": ["config_invalid"], "cases": []}
    if not isinstance(config, Mapping) or config.get("schema") != SCHEMA or config.get("version") != 2:
        return {"schema": SCHEMA, "accepted": False, "reasons": ["legacy_hash_only_evidence"], "cases": []}
    raw_cases = config.get("cases")
    if not isinstance(raw_cases, list):
        return {"schema": SCHEMA, "accepted": False, "reasons": ["config_cases_invalid"], "cases": []}
    cases = [_audit_case(case) for case in raw_cases if isinstance(case, Mapping)]
    reasons = [f"{case['id']}:{reason}" for case in cases for reason in case["reasons"]]
    if len(cases) != len(raw_cases):
        reasons.append("case_not_object")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        reasons.append("case_id_duplicate")
    return {
        "schema": SCHEMA,
        "version": 2,
        "corpus_id": config.get("corpus_id"),
        "accepted": not reasons and bool(cases),
        "reasons": sorted(set(reasons)),
        "cases": cases,
    }


__all__ = ["REQUIRED_BASELINE_FILES", "SCHEMA", "SEAL_SCHEMA", "audit_native_campaign_config_v2", "build_corpus_seal"]
