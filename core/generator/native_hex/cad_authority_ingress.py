"""Fail-closed adapter for Native Hex source-authored CAD authority sidecars."""

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


def validate_native_hex_cad_authority(
    source: bytes | bytearray | memoryview | str | Path,
    canonical_snapshot_sha256: str,
    sidecar: Mapping[str, Any],
    face_count: int,
) -> dict[str, Any]:
    """Validate STEP/CAD authority without reading or inferring geometry semantics."""
    raw = _source_bytes(source)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    sidecar_value = dict(sidecar)
    sidecar_sha256 = hashlib.sha256(canonical_bytes(sidecar_value)).hexdigest()
    try:
        kernel = import_native_extension("native_hex_cad_authority_corpus")
        return dict(
            kernel.validate_native_hex_cad_authority(
                raw_sha256,
                str(canonical_snapshot_sha256),
                sidecar_value,
                sidecar_sha256,
                int(face_count),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "native_hex_cad_authority_refused",
            "reason": f"native_hex_cad_authority_unavailable:{type(exc).__name__}",
            "eligible_for_hex_bl": False,
            "runtime_route": "private_default_off",
            "route_calls": 0,
            "candidate_discarded": True,
            "actual_layers": 0,
            "source_sha256": raw_sha256,
            "canonical_snapshot_sha256": str(canonical_snapshot_sha256),
            "sidecar_sha256": sidecar_sha256,
        }


__all__ = ["validate_native_hex_cad_authority"]
