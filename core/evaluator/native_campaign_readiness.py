"""Read-only readiness audit for an explicit native release corpus config."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "autotessell/native-campaign-readiness/v1"
REQUIRED_BASELINE_FILES = ("points", "faces", "owner", "neighbour", "boundary")
REQUIRED_SEMANTIC_KEYS = (
    "mapping_table_sha256", "features_sha256", "patches_sha256",
    "physical_groups_sha256", "components_sha256", "provenance_sha256",
    "coverage_complete", "bijection",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file(path: Any) -> tuple[bool, str | None, str | None]:
    candidate = Path(path) if isinstance(path, str) else None
    if candidate is None or candidate.is_symlink():
        return False, "symlink_or_path_invalid", None
    if not candidate.is_file():
        return False, "file_missing", None
    try:
        return True, None, _sha256(candidate)
    except OSError:
        return False, "file_unreadable", None


def _json(path: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "json_invalid"
    if not isinstance(value, Mapping):
        return None, "json_object_required"
    return value, None


def _audit_case(case: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    case_id = case.get("id")
    source_ok, source_reason, source_sha = _file(case.get("source"))
    if not source_ok and source_reason:
        reasons.append(f"source:{source_reason}")

    baseline_path = Path(case["baseline"]) if isinstance(case.get("baseline"), str) else None
    baseline_files: dict[str, bool] = {}
    if baseline_path is None or baseline_path.is_symlink() or not baseline_path.is_dir():
        reasons.append("baseline:directory_missing")
    else:
        for name in REQUIRED_BASELINE_FILES:
            candidate = baseline_path / name
            valid = candidate.is_file() and not candidate.is_symlink()
            baseline_files[name] = valid
            if not valid:
                reasons.append(f"baseline:{name}_missing")

    authority_ok, authority_reason, authority_sha = _file(case.get("authority"))
    authority_payload: Mapping[str, Any] | None = None
    if not authority_ok:
        reasons.append(f"authority:{authority_reason}")
    elif isinstance(case.get("authority"), str):
        authority_payload, parse_reason = _json(Path(case["authority"]))
        if parse_reason:
            reasons.append(f"authority:{parse_reason}")
    if authority_payload is not None:
        if authority_payload.get("authoritative") is not True:
            reasons.append("authority:not_authoritative")
        if source_sha is None or authority_payload.get("source_sha256") != source_sha:
            reasons.append("authority:source_digest_mismatch")

    semantic_ok, semantic_reason, semantic_sha = _file(case.get("semantic"))
    semantic_payload: Mapping[str, Any] | None = None
    if not semantic_ok:
        reasons.append(f"semantic:{semantic_reason}")
    elif isinstance(case.get("semantic"), str):
        semantic_payload, parse_reason = _json(Path(case["semantic"]))
        if parse_reason:
            reasons.append(f"semantic:{parse_reason}")
    if semantic_payload is not None:
        missing = [key for key in REQUIRED_SEMANTIC_KEYS if key not in semantic_payload]
        if missing:
            reasons.append("semantic:fields_missing:" + ",".join(missing))
        if semantic_payload.get("coverage_complete") is not True or semantic_payload.get("bijection") is not True:
            reasons.append("semantic:coverage_or_bijection_incomplete")
        if source_sha is None or semantic_payload.get("source_sha256") != source_sha:
            reasons.append("semantic:source_digest_mismatch")

    provenance_ok, provenance_reason, provenance_sha = _file(case.get("provenance"))
    provenance_payload: Mapping[str, Any] | None = None
    if not provenance_ok:
        reasons.append(f"provenance:{provenance_reason}")
    elif isinstance(case.get("provenance"), str):
        provenance_payload, parse_reason = _json(Path(case["provenance"]))
        if parse_reason:
            reasons.append(f"provenance:{parse_reason}")
    if provenance_payload is not None:
        if provenance_payload.get("complete") is not True:
            reasons.append("provenance:not_complete")
        if source_sha is None or provenance_payload.get("source_sha256") != source_sha:
            reasons.append("provenance:source_digest_mismatch")

    return {
        "id": case_id,
        "ready": not reasons,
        "reasons": sorted(set(reasons)),
        "source": {"path": case.get("source"), "present": source_ok, "sha256": source_sha},
        "baseline": {"path": case.get("baseline"), "present": bool(baseline_files) and all(baseline_files.values()), "files": baseline_files},
        "authority": {"path": case.get("authority"), "present": authority_ok, "sha256": authority_sha},
        "semantic": {"path": case.get("semantic"), "present": semantic_ok, "sha256": semantic_sha},
        "provenance": {"path": case.get("provenance"), "present": provenance_ok, "sha256": provenance_sha},
    }


def audit_native_campaign_config(config_path: str | Path) -> dict[str, Any]:
    """Audit explicit corpus paths without copying or invoking a mesher."""
    path = Path(config_path)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"schema": SCHEMA, "accepted": False, "reasons": ["config_invalid"], "cases": []}
    if not isinstance(config, Mapping) or not isinstance(config.get("cases"), list):
        return {"schema": SCHEMA, "accepted": False, "reasons": ["config_cases_invalid"], "cases": []}
    cases = [_audit_case(case) for case in config["cases"] if isinstance(case, Mapping)]
    reasons: list[str] = []
    if len(cases) != len(config["cases"]):
        reasons.append("case_not_object")
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        reasons.append("case_id_duplicate")
    for case in cases:
        reasons.extend(f"{case['id']}:{reason}" for reason in case["reasons"])
    return {
        "schema": SCHEMA, "corpus_id": config.get("corpus_id"),
        "accepted": not reasons and bool(cases),
        "reasons": sorted(set(reasons)), "cases": cases,
    }


__all__ = ["SCHEMA", "REQUIRED_BASELINE_FILES", "audit_native_campaign_config"]
