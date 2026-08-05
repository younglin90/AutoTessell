"""Explicit native product route and boundary-layer support registry.

Route selection is not release authority.  A selected route still requires an
actual staged Gate4 certificate, quality witness, and repeatability evidence.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "autotessell/native-route-registry/v1"

ROUTE_REGISTRY: dict[str, dict[str, Any]] = {
    "native-tet": {
        "route": "native_tet_independent_release",
        "topology": "volume", "source_kinds": ("stl", "cad"),
        "boundary_layers": (0, 1, 5), "independent": True,
    },
    "native-hex": {
        "route": "native_hex_cad_brep_independent_release",
        "topology": "volume", "source_kinds": ("cad",),
        "boundary_layers": (0, 1, 5), "independent": True,
    },
    "native-poly": {
        "route": "native_poly_independent_release",
        "topology": "volume", "source_kinds": ("stl", "cad"),
        "boundary_layers": (0, 1, 5), "independent": True,
    },
    "native-tri": {
        "route": "native_tri_independent_surface_release",
        "topology": "surface", "source_kinds": ("stl", "cad"),
        "boundary_layers": (0,), "independent": True,
    },
    "strict-quad": {
        "route": "strict_quad_independent_fixed_pair_release",
        "topology": "surface", "source_kinds": ("surface_snapshot", "stl", "cad"),
        "boundary_layers": (0,), "independent": True,
    },
    "tri-quad": {
        "route": "tri_quad_independent_fixed_pair_release",
        "topology": "surface", "source_kinds": ("surface_snapshot", "stl", "cad"),
        "boundary_layers": (0,), "independent": True,
    },
}


def native_route_registry_manifest() -> dict[str, Any]:
    """Return a JSON-safe copy for provenance and audit logs."""
    return {
        "schema": SCHEMA,
        "products": {
            product: {
                **spec,
                "source_kinds": list(spec["source_kinds"]),
                "boundary_layers": list(spec["boundary_layers"]),
            }
            for product, spec in sorted(ROUTE_REGISTRY.items())
        },
    }


def select_native_route(product: str, *, boundary_layers: int,
                        source_kind: str) -> dict[str, Any]:
    """Select an explicitly supported route, or return a mechanical refusal."""
    spec = ROUTE_REGISTRY.get(product)
    if spec is None:
        return {"schema": SCHEMA, "accepted": False,
                "release_claim_eligible": False, "reasons": ["product_unknown"]}
    if isinstance(boundary_layers, bool) or not isinstance(boundary_layers, int) or boundary_layers < 0:
        return {"schema": SCHEMA, "accepted": False,
                "release_claim_eligible": False, "reasons": ["boundary_layers_invalid"]}
    if source_kind not in spec["source_kinds"]:
        return {"schema": SCHEMA, "accepted": False,
                "release_claim_eligible": False,
                "reasons": ["source_kind_unsupported_by_route"]}
    if boundary_layers not in spec["boundary_layers"]:
        return {"schema": SCHEMA, "accepted": False,
                "release_claim_eligible": False,
                "reasons": ["boundary_layers_unsupported_by_route"]}
    return {
        "schema": SCHEMA, "accepted": True, "release_claim_eligible": False,
        "reasons": [], "product": product, "route": spec["route"],
        "topology": spec["topology"], "source_kind": source_kind,
        "boundary_layers": boundary_layers,
        "independent_route_required": spec["independent"],
        "gate4_evidence_required": True,
        "positive_boundary_layer_witness_required": boundary_layers > 0,
    }


__all__ = ["SCHEMA", "ROUTE_REGISTRY", "native_route_registry_manifest", "select_native_route"]
