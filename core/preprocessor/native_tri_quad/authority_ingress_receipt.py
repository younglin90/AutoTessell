"""Fail-closed adapter for mixed Native TRI+QUAD source authority receipts."""

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


def _array(value: Any, dtype: Any, width: int) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(value, dtype=dtype))
    if result.ndim != 2 or result.shape[-1] != width:
        raise ValueError("native_tri_quad_authority_array_shape")
    return result


def _digest(value: np.ndarray) -> str:
    return hashlib.sha256(canonical_bytes({
        "dtype": str(value.dtype),
        "shape": list(value.shape),
        "c_order_bytes_hex": value.tobytes(order="C").hex(),
    })).hexdigest()


def _refuse(reason: str) -> dict[str, Any]:
    return {"accepted": False, "status": "tri_quad_authority_ingress_refused",
            "reason": reason, "eligible_for_tri_quad_bl": False,
            "actual_layers": 0, "publication_eligible": False,
            "candidate_discarded": True, "runtime_route": "private_default_off",
            "route_calls": 0}


def validate_native_tri_quad_authority_ingress(
    source: bytes | bytearray | memoryview | str | Path,
    points: Any,
    triangles: Any,
    quads: Any,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    raw = _source_bytes(source)
    point_array = _array(points, np.float64, 3)
    triangle_array = _array(triangles, np.int64, 3)
    quad_array = _array(quads, np.int64, 4)
    receipt_value = dict(receipt)
    expected = {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_byte_count": len(raw),
        "point_digest": _digest(point_array),
        "triangle_digest": _digest(triangle_array),
        "quad_digest": _digest(quad_array),
    }
    for key, value in expected.items():
        if receipt_value.get(key) != value:
            return _refuse(f"tri_quad_receipt_{key}_mismatch")
    try:
        kernel = import_native_extension("native_tri_quad_authority_ingress_receipt")
        return dict(kernel.validate_tri_quad_authority_ingress(
            expected["source_sha256"], len(raw), point_array.tolist(),
            triangle_array.tolist(), quad_array.tolist(), receipt_value,
        ))
    except Exception as exc:  # noqa: BLE001
        return {**_refuse(f"tri_quad_authority_ingress_unavailable:{type(exc).__name__}"),
                "source_sha256": expected["source_sha256"]}


__all__ = ["validate_native_tri_quad_authority_ingress"]
