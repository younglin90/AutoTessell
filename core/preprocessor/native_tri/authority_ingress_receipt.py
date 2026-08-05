"""Fail-closed adapter for Native Tri source authority receipts."""

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
        raise ValueError("native_tri_authority_array_shape")
    return result


def _array_digest(value: np.ndarray) -> str:
    payload = {"dtype": str(value.dtype), "shape": list(value.shape), "c_order_bytes_hex": value.tobytes(order="C").hex()}
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _refuse(reason: str) -> dict[str, Any]:
    return {"accepted": False, "status": "native_tri_authority_ingress_refused", "reason": reason,
            "eligible_for_tri_bl": False, "actual_layers": 0, "publication_eligible": False,
            "candidate_discarded": True, "runtime_route": "private_default_off", "route_calls": 0}


def validate_native_tri_authority_ingress(
    source: bytes | bytearray | memoryview | str | Path,
    points: Any,
    triangles: Any,
    orientation: Any,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    raw = _source_bytes(source)
    point_array = _array(points, np.float64, 2, 3)
    triangle_array = _array(triangles, np.int64, 2, 3)
    orientation_array = np.ascontiguousarray(np.asarray(orientation, dtype=np.bool_))
    if orientation_array.ndim != 1 or len(orientation_array) != len(triangle_array):
        return _refuse("tri_orientation_shape_invalid")
    receipt_value = dict(receipt)
    expected = {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_byte_count": len(raw),
        "point_digest": _array_digest(point_array),
        "triangle_digest": _array_digest(triangle_array),
        "orientation_digest": _array_digest(orientation_array),
    }
    for key, value in expected.items():
        if receipt_value.get(key) != value:
            return _refuse(f"tri_receipt_{key}_mismatch")
    try:
        kernel = import_native_extension("native_tri_authority_ingress_receipt")
        return dict(kernel.validate_native_tri_authority_ingress(
            expected["source_sha256"], len(raw), point_array.tolist(), triangle_array.tolist(),
            orientation_array.tolist(), receipt_value,
        ))
    except Exception as exc:  # noqa: BLE001
        return {**_refuse(f"native_tri_authority_ingress_unavailable:{type(exc).__name__}"),
                "source_sha256": expected["source_sha256"]}


__all__ = ["validate_native_tri_authority_ingress"]
