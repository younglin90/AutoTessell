"""Fail-closed adapter for source-authored surface authority sidecars."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from core.layers.native_bl_atomic_certificate import canonical_bytes
from core.utils.native_extensions import import_native_extension


def _source_bytes(source: bytes | bytearray | memoryview | str | Path) -> bytes:
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    return Path(source).read_bytes()


def validate_surface_authority_corpus(
    source: bytes | bytearray | memoryview | str | Path,
    source_kind: str,
    sidecar: Mapping[str, Any],
    source_entity_count: int,
) -> dict[str, Any]:
    """Validate source/sidecar binding without inferring any wall curve or label."""
    raw = _source_bytes(source)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    sidecar_value = dict(sidecar)
    sidecar_sha256 = hashlib.sha256(canonical_bytes(sidecar_value)).hexdigest()
    try:
        kernel = import_native_extension("native_surface_authority_corpus")
        return dict(
            kernel.validate_surface_authority_corpus(
                str(source_kind),
                raw_sha256,
                sidecar_value,
                sidecar_sha256,
                int(source_entity_count),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "surface_authority_corpus_refused",
            "reason": f"native_surface_authority_corpus_unavailable:{type(exc).__name__}",
            "eligible_for_surface_bl": False,
            "runtime_route": "private_default_off",
            "route_calls": 0,
            "candidate_discarded": True,
            "source_sha256": raw_sha256,
            "sidecar_sha256": sidecar_sha256,
        }


__all__ = ["validate_surface_authority_corpus"]
