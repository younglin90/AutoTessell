"""Fail-closed adapter for Strict Quad fixed-pair authority receipts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from core.layers.native_bl_atomic_certificate import canonical_bytes
from core.utils.native_extensions import import_native_extension


def _source_bytes(source: bytes | bytearray | memoryview | str | Path) -> bytes:
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    return Path(source).read_bytes()


def _array(value: Any, dtype: Any, ndim: int, width: int | None = None) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(value, dtype=dtype))
    if result.ndim != ndim or (width is not None and result.shape[-1] != width):
        raise ValueError("strict_quad_authority_array_shape")
    return result


def _digest(value: np.ndarray) -> str:
    return hashlib.sha256(canonical_bytes({
        "dtype": str(value.dtype),
        "shape": list(value.shape),
        "c_order_bytes_hex": value.tobytes(order="C").hex(),
    })).hexdigest()


def _refuse(reason: str) -> dict[str, Any]:
    return {"accepted": False, "status": "strict_quad_authority_ingress_refused",
            "reason": reason, "eligible_for_strict_quad_bl": False,
            "actual_layers": 0, "publication_eligible": False,
            "candidate_discarded": True, "runtime_route": "private_default_off",
            "route_calls": 0}


def validate_strict_quad_authority_ingress(
    source: bytes | bytearray | memoryview | str | Path,
    points: Any,
    triangles: Any,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    raw = _source_bytes(source)
    point_array = _array(points, np.float64, 2, 3)
    triangle_array = _array(triangles, np.int64, 2, 3)
    receipt_value = dict(receipt)
    expected = {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_byte_count": len(raw),
        "point_digest": _digest(point_array),
        "triangle_digest": _digest(triangle_array),
    }
    for key, value in expected.items():
        if receipt_value.get(key) != value:
            return _refuse(f"strict_quad_receipt_{key}_mismatch")
    try:
        kernel = import_native_extension("native_strict_quad_authority_ingress_receipt")
        return dict(kernel.validate_strict_quad_authority_ingress(
            expected["source_sha256"], len(raw), point_array.tolist(),
            triangle_array.tolist(), receipt_value,
        ))
    except Exception as exc:  # noqa: BLE001
        return {**_refuse(f"strict_quad_authority_ingress_unavailable:{type(exc).__name__}"),
                "source_sha256": expected["source_sha256"]}


__all__ = ["validate_strict_quad_authority_ingress"]
