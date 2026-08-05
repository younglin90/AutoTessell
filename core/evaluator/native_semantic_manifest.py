"""Explicit source-semantic manifest and certificate admission.

Geometry readers may prove source bytes and native entity ordinals, but they
must not invent CFD feature, patch, physical-group, component, or provenance
meaning.  This module validates the application-owned manifest that supplies
those meanings and binds it to the source ledger digest.  It is orchestration
code, not a geometry or quality kernel.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SEMANTIC_SCHEMA = "autotessell/native-semantic-manifest/v1"
CERTIFICATE_SCHEMA = "autotessell/native-source-certificate/v1"
SEMANTIC_FIELDS = ("feature", "patch", "physical_group", "component", "provenance")
ENTITY_KINDS = ("stl_facet", "cad_face", "cad_edge")
_PATH_KEYS = {"path", "filename", "filepath", "absolute_path", "source_path"}


def _sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> tuple[str, int] | None:
    if path.is_symlink() or not path.is_file():
        return None
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
    except OSError:
        return None
    return digest.hexdigest(), size


def _contains_path_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in _PATH_KEYS or _contains_path_key(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_path_key(item) for item in value)
    return False


def _ledger_source(ledger: Mapping[str, Any]) -> tuple[str | None, str | None]:
    source = ledger.get("source")
    source_sha = source.get("sha256") if isinstance(source, Mapping) else None
    if source_sha is None:
        source_sha = ledger.get("source_digest")
    ledger_sha = ledger.get("ledger_digest")
    return source_sha if _sha256(source_sha) else None, ledger_sha if _sha256(ledger_sha) else None


def _namespace_ids(namespace: Mapping[str, Any]) -> tuple[int, set[int], list[tuple[int, int]]]:
    count = namespace.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return -1, set(), []
    records = namespace.get("records")
    ids: set[int] = set()
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, Mapping):
                return -1, set(), []
            value = record.get("id")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return -1, set(), []
            ids.add(value)
    ranges: list[tuple[int, int]] = []
    raw_ranges = namespace.get("id_ranges")
    if isinstance(raw_ranges, list):
        for pair in raw_ranges:
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or any(isinstance(item, bool) or not isinstance(item, int) for item in pair)
                or pair[0] < 0
                or pair[1] < pair[0]
            ):
                return -1, set(), []
            ranges.append((pair[0], pair[1]))
    return count, ids, ranges


def _id_in_namespace(value: int, ids: set[int], ranges: list[tuple[int, int]]) -> bool:
    return value in ids or any(start <= value <= end for start, end in ranges)


def _manifest_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "manifest_sha256"}


def validate_semantic_manifest(
    manifest: Mapping[str, Any] | None,
    ledger: Mapping[str, Any] | None,
    *,
    require_digest: bool = True,
) -> dict[str, Any]:
    """Validate explicit semantic rows against a source ledger, without mutation."""
    reasons: list[str] = []
    if not isinstance(manifest, Mapping):
        return {"accepted": False, "reasons": ["manifest_not_object"]}
    if _contains_path_key(manifest):
        reasons.append("path_field_forbidden")
    if manifest.get("schema") != SEMANTIC_SCHEMA:
        reasons.append("schema_mismatch")
    if not isinstance(ledger, Mapping):
        reasons.append("ledger_missing")
        source_sha = ledger_sha = None
        namespace = None
    else:
        source_sha, ledger_sha = _ledger_source(ledger)
        kind = manifest.get("entity_kind")
        namespaces = ledger.get("selector_namespaces")
        namespace = namespaces.get(kind) if isinstance(namespaces, Mapping) else None
        if not _sha256(source_sha):
            reasons.append("ledger_source_digest_missing")
        if not _sha256(ledger_sha):
            reasons.append("ledger_digest_missing")
        if not isinstance(namespace, Mapping) or namespace.get("available") is not True:
            reasons.append("ledger_namespace_unavailable")

    if manifest.get("source_sha256") != source_sha:
        reasons.append("source_digest_mismatch")
    if manifest.get("source_ledger_sha256") != ledger_sha:
        reasons.append("source_ledger_digest_mismatch")
    kind = manifest.get("entity_kind")
    if kind not in ENTITY_KINDS:
        reasons.append("entity_kind_invalid")
    count = manifest.get("entity_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        reasons.append("entity_count_invalid")
    rows = manifest.get("rows")
    if not isinstance(rows, list):
        reasons.append("rows_invalid")
        rows = []
    if manifest.get("coverage_complete") is not True:
        reasons.append("coverage_not_declared_complete")
    if manifest.get("bijection") is not True:
        reasons.append("bijection_not_declared")

    expected_count, ids, ranges = _namespace_ids(namespace) if isinstance(namespace, Mapping) else (-1, set(), [])
    if isinstance(count, int) and count >= 0 and expected_count >= 0 and count != expected_count:
        reasons.append("entity_count_ledger_mismatch")
    seen: set[int] = set()
    previous = -1
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            reasons.append(f"row_{index}_not_object")
            continue
        value = row.get("source_id")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            reasons.append(f"row_{index}_source_id_invalid")
            continue
        if value in seen:
            reasons.append("source_id_duplicate")
        if value <= previous:
            reasons.append("source_ids_not_strictly_sorted")
        previous = value
        seen.add(value)
        if expected_count >= 0 and not _id_in_namespace(value, ids, ranges):
            reasons.append(f"row_{index}_source_id_unavailable")
        for field in SEMANTIC_FIELDS:
            field_value = row.get(field)
            if not isinstance(field_value, str) or not field_value.strip():
                reasons.append(f"row_{index}_{field}_missing_or_empty")
    if isinstance(count, int) and count >= 0 and len(rows) != count:
        reasons.append("semantic_row_count_mismatch")
    if expected_count >= 0 and len(seen) == expected_count and not reasons:
        coverage = True
    else:
        coverage = False
        if expected_count >= 0 and len(seen) != expected_count:
            reasons.append("source_entity_coverage_incomplete")
    if require_digest:
        digest = manifest.get("manifest_sha256")
        if not _sha256(digest):
            reasons.append("manifest_digest_missing")
        elif digest != _digest(_manifest_payload(manifest)):
            reasons.append("manifest_digest_mismatch")
    else:
        digest = _digest(_manifest_payload(manifest))
    return {
        "accepted": not reasons,
        "reasons": sorted(set(reasons)),
        "manifest_sha256": digest,
        "source_sha256": source_sha,
        "source_ledger_sha256": ledger_sha,
        "entity_kind": kind,
        "entity_count": count,
        "coverage_complete": coverage,
        "bijection": coverage and not any("source_id_duplicate" in reason for reason in reasons),
    }


def build_semantic_manifest(
    ledger: Mapping[str, Any] | None,
    entity_kind: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a digest-sealed manifest only from explicit caller-owned rows."""
    source_sha, ledger_sha = _ledger_source(ledger) if isinstance(ledger, Mapping) else (None, None)
    manifest: dict[str, Any] = {
        "schema": SEMANTIC_SCHEMA,
        "source_sha256": source_sha,
        "source_ledger_sha256": ledger_sha,
        "entity_kind": entity_kind,
        "entity_count": len(rows),
        "rows": [dict(row) for row in rows],
        "coverage_complete": True,
        "bijection": True,
    }
    result = validate_semantic_manifest(manifest, ledger, require_digest=False)
    if result["accepted"]:
        manifest["manifest_sha256"] = _digest(_manifest_payload(manifest))
        result = validate_semantic_manifest(manifest, ledger)
    result["manifest"] = manifest
    return result


def build_source_certificate(
    source_path: str | Path,
    ledger: Mapping[str, Any] | None,
    semantic_manifest: Mapping[str, Any] | None,
    *,
    parser_name: str,
    parser_version: str,
    authority_statement: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a source certificate only with an explicit authority attestation."""
    if not isinstance(authority_statement, Mapping) or authority_statement.get("attested") is not True:
        return {"accepted": False, "reasons": ["explicit_authority_attestation_required"]}
    issuer = authority_statement.get("issuer")
    basis = authority_statement.get("basis")
    if not isinstance(issuer, str) or not issuer.strip() or not isinstance(basis, str) or not basis.strip():
        return {"accepted": False, "reasons": ["authority_statement_incomplete"]}
    semantic = validate_semantic_manifest(semantic_manifest, ledger)
    if not semantic["accepted"]:
        return {"accepted": False, "reasons": ["semantic_manifest_refused", *semantic["reasons"]]}
    source = Path(source_path)
    file_digest = _file_sha256(source)
    if file_digest is None:
        return {"accepted": False, "reasons": ["source_file_missing_or_symlink"]}
    source_sha, ledger_sha = _ledger_source(ledger) if isinstance(ledger, Mapping) else (None, None)
    digest, size = file_digest
    if digest != source_sha:
        return {"accepted": False, "reasons": ["source_file_digest_mismatch"]}
    if not isinstance(parser_name, str) or not parser_name.strip() or not isinstance(parser_version, str) or not parser_version.strip():
        return {"accepted": False, "reasons": ["parser_identity_incomplete"]}
    payload: dict[str, Any] = {
        "schema": CERTIFICATE_SCHEMA,
        "authority_status": "SOURCE_VERIFIED",
        "source_sha256": digest,
        "source_size_bytes": size,
        "source_ledger_sha256": ledger_sha,
        "semantic_manifest_sha256": semantic["manifest_sha256"],
        "entity_kind": semantic["entity_kind"],
        "entity_count": semantic["entity_count"],
        "parser": {"name": parser_name, "version": parser_version},
        "authority_statement": {"attested": True, "issuer": issuer, "basis": basis},
    }
    certificate = dict(payload)
    certificate["certificate_sha256"] = _digest(payload)
    return {"accepted": True, "certificate": certificate, "certificate_sha256": certificate["certificate_sha256"]}


def validate_source_certificate(
    certificate: Mapping[str, Any] | None,
    source_path: str | Path,
    ledger: Mapping[str, Any] | None,
    semantic_manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Recompute and compare a sealed certificate; never trust its hashes alone."""
    if not isinstance(certificate, Mapping):
        return {"accepted": False, "reasons": ["certificate_not_object"]}
    if certificate.get("schema") != CERTIFICATE_SCHEMA:
        return {"accepted": False, "reasons": ["certificate_schema_mismatch"]}
    if certificate.get("authority_status") != "SOURCE_VERIFIED":
        return {"accepted": False, "reasons": ["certificate_not_source_verified"]}
    statement = certificate.get("authority_statement")
    if _contains_path_key(statement):
        return {"accepted": False, "reasons": ["certificate_path_field_forbidden"]}
    parser = certificate.get("parser")
    if not isinstance(parser, Mapping):
        return {"accepted": False, "reasons": ["certificate_parser_missing"]}
    expected = build_source_certificate(
        source_path,
        ledger,
        semantic_manifest,
        parser_name=parser.get("name", ""),
        parser_version=parser.get("version", ""),
        authority_statement=statement,
    )
    if expected.get("accepted") is not True:
        return {"accepted": False, "reasons": ["certificate_recompute_refused", *expected.get("reasons", ())]}
    expected_certificate = expected["certificate"]
    if dict(certificate) != expected_certificate:
        return {"accepted": False, "reasons": ["certificate_recomputed_value_mismatch"]}
    if certificate.get("certificate_sha256") != _digest({key: value for key, value in certificate.items() if key != "certificate_sha256"}):
        return {"accepted": False, "reasons": ["certificate_digest_mismatch"]}
    return {"accepted": True, "reasons": [], "certificate_sha256": certificate["certificate_sha256"]}


__all__ = [
    "CERTIFICATE_SCHEMA",
    "ENTITY_KINDS",
    "SEMANTIC_FIELDS",
    "SEMANTIC_SCHEMA",
    "build_semantic_manifest",
    "build_source_certificate",
    "validate_semantic_manifest",
    "validate_source_certificate",
]
