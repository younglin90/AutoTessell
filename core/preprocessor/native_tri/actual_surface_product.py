"""Explicit Native Tri CAD-surface product adapter.

This adapter owns product identity and refusal semantics only. The hot
wall-edge front, quality, transaction, and evidence-pack kernels remain in
the existing C++23 bridge under ``core/evaluator``. STL and authority-free
inputs are deliberately not converted into guessed wall edges.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _refuse(reason: str, *, product: str = "native_tri_surface") -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "native_tri_surface_product_refused",
        "reason": reason,
        "product": product,
        "route_selected": product == "native_tri_surface",
        "independent_route": False,
        "publication_eligible": False,
        "artifact_emitted": False,
        "candidate_discarded": True,
    }


def run_native_tri_actual_cad_surface_product(
    source_path: str | Path,
    target_root: str | Path,
    *,
    explicit_mapping: Sequence[Mapping[str, Any]] | None,
    owner_face_by_edge: Mapping[int, int] | None,
    requested_layers: int,
    first_height: float | None = None,
    growth_ratio: float = 1.0,
    product: str = "native_tri_surface",
    explicit_route: bool = False,
    domain_side_authority_fixture: bool = False,
) -> dict[str, Any]:
    """Run the actual CAD/BRep triangle wall-edge product when fully bound.

    The function refuses before touching the target when product identity,
    route opt-in, source format, or explicit authority mapping is absent.
    ``publication_eligible`` remains whatever the evidence writer proves; the
    current bridge intentionally keeps the product private/default-off.
    """
    if product != "native_tri_surface":
        return _refuse("product_boundary_mismatch", product=product)
    if not explicit_route:
        return _refuse("explicit_product_route_required")
    source = Path(source_path)
    if source.suffix.lower() not in {".step", ".stp", ".iges", ".igs", ".brep"}:
        return _refuse("native_tri_actual_surface_requires_cad_brep_source")
    if requested_layers < 0:
        return _refuse("negative_layer_count")
    if not explicit_mapping:
        return _refuse("explicit_surface_wall_edge_mapping_required")
    if not owner_face_by_edge:
        return _refuse("explicit_owner_face_by_edge_required")
    try:
        from core.evaluator.native_surface_brep_evidence_pack_bridge import (
            write_actual_brep_surface_evidence_pack_v2,
        )

        result = write_actual_brep_surface_evidence_pack_v2(
            target_root,
            source,
            explicit_mapping=[dict(row) for row in explicit_mapping],
            owner_face_by_edge={int(key): int(value) for key, value in owner_face_by_edge.items()},
            requested_layers=int(requested_layers),
            first_height=first_height,
            growth_ratio=float(growth_ratio),
            domain_side_authority_fixture=bool(domain_side_authority_fixture),
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return _refuse(f"native_tri_actual_surface_exception:{type(exc).__name__}")
    accepted = bool(result.get("accepted"))
    return {
        **dict(result),
        "product": "native_tri_surface",
        "route_selected": True,
        "independent_route": accepted,
        "publication_eligible": bool(result.get("publication_eligible", False)),
        "artifact_emitted": bool(result.get("evidence_root")),
        "release_claim": False,
    }


__all__ = ["run_native_tri_actual_cad_surface_product"]
