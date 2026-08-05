"""Thin read-only adapter for the native route evidence matrix."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.utils.native_extensions import import_native_extension

MATRIX_PRODUCTS = (
    "tet",
    "hex",
    "poly",
    "tri",
    "strict_quad",
    "tri_plus_quad",
    "surface",
)


def evaluate_route_evidence_matrix(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Classify existing evidence without invoking a route or publisher."""
    immutable_rows = [dict(row) for row in rows]
    try:
        kernel = import_native_extension("native_bl_identity")
        return dict(kernel.evaluate_route_evidence_matrix_v1(immutable_rows))
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "matrix_unavailable",
            "rows": [],
            "counts": {"incomplete": len(immutable_rows)},
            "publication_eligible": False,
            "runtime_route": "default_off",
            "route_calls": 0,
            "reason": f"native_route_evidence_matrix_unavailable:{type(exc).__name__}",
        }


__all__ = ["MATRIX_PRODUCTS", "evaluate_route_evidence_matrix"]
