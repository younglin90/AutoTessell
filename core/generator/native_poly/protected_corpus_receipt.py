"""Fail-closed protected Native Poly corpus receipt adapter."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from core.layers.native_bl_atomic_certificate import canonical_bytes
from core.utils.native_extensions import import_native_extension


_PROTECTED_REF = "codex/native-poly-cycle41-solid-volume-timeout-1"
_PROTECTED_COMMIT = "70ce4b9b"


def _source_bytes(source: bytes | bytearray | memoryview | str | Path) -> bytes:
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    return Path(source).read_bytes()


def validate_native_poly_protected_corpus(
    source: bytes | bytearray | memoryview | str | Path,
    protected_tree: str,
    package: Mapping[str, Any],
    requested_layers: int,
    *,
    protected_ref: str = _PROTECTED_REF,
    protected_commit: str = _PROTECTED_COMMIT,
) -> dict[str, Any]:
    """Validate a protected-branch evidence package without accessing that branch."""
    raw = _source_bytes(source)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    package_value = dict(package)
    package_sha256 = hashlib.sha256(canonical_bytes(package_value)).hexdigest()
    try:
        kernel = import_native_extension("native_poly_protected_corpus_receipt")
        return dict(
            kernel.validate_native_poly_protected_corpus(
                str(protected_ref),
                str(protected_commit),
                str(protected_tree),
                raw_sha256,
                package_value,
                package_sha256,
                int(requested_layers),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "native_poly_protected_corpus_refused",
            "reason": f"native_poly_protected_corpus_unavailable:{type(exc).__name__}",
            "actual_layers": 0,
            "publication_eligible": False,
            "candidate_discarded": True,
            "runtime_route": "private_default_off",
            "route_calls": 0,
            "requested_layers": int(requested_layers),
            "raw_source_sha256": raw_sha256,
            "package_sha256": package_sha256,
        }


__all__ = ["validate_native_poly_protected_corpus"]
