"""Immutable source-to-Native-Poly transaction certificate."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "native-poly-source-transaction/v1"


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_certificate(
    source_identity: object,
    *,
    source_authority_ledger: Mapping[str, Any] | None,
    input_config: Mapping[str, Any] | None,
    boundary_layer_profile: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a digest-bound certificate without copying source bytes."""
    source_ledger_digest = (
        canonical_sha256(dict(source_authority_ledger))
        if isinstance(source_authority_ledger, Mapping)
        else None
    )
    body: dict[str, Any] = {
        "schema": SCHEMA,
        "immutable": True,
        "original_path": str(getattr(source_identity, "original_path", "")),
        "snapshot_path": str(getattr(source_identity, "snapshot_path", "")),
        "raw_source_sha256": str(getattr(source_identity, "sha256", "")),
        "source_byte_count": int(getattr(source_identity, "byte_count", 0) or 0),
        "source_kind": Path(str(getattr(source_identity, "original_path", ""))).suffix.lower().lstrip(".") or "unknown",
        "source_authority_ledger_sha256": source_ledger_digest,
        "source_authority_ledger_status": "provided" if source_ledger_digest else "missing",
        "authority_chain_complete": bool(source_ledger_digest),
        "user_parameter_sha256": canonical_sha256(dict(input_config or {})),
        "boundary_layer_profile": dict(boundary_layer_profile or {}),
    }
    body["certificate_sha256"] = canonical_sha256(body)
    return body


def write_certificate_atomic(path: Path, certificate: Mapping[str, Any]) -> None:
    """Write one certificate atomically inside the caller-owned evidence dir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(dict(certificate), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


__all__ = ["SCHEMA", "build_certificate", "canonical_sha256", "write_certificate_atomic"]
