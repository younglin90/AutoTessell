"""Private C++23 authority-bound planar Native Tri BL template adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.utils.native_extensions import import_native_extension


def _refusal(reason: str, requested_layers: int = 0) -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "native_tri_planar_triangle_bl_template_refused",
        "reason": reason,
        "requested_layers": int(requested_layers),
        "actual_layers": 0,
        "writer_invoked": False,
        "artifact_emitted": False,
        "publication_eligible": False,
        "release_eligible": False,
        "candidate_discarded": True,
        "atomic_rollback": True,
        "runtime_route": "private_default_off",
        "generated_vertices": [],
        "generated_faces": [],
        "output_vertices": [],
        "output_faces": [],
        "provenance": [],
        "generated_provenance": [],
        "quality_witness": [],
    }


def _certificate(source_certificate: Mapping[str, Any]) -> Mapping[str, Any]:
    value = source_certificate.get("certificate", source_certificate)
    if not isinstance(value, Mapping):
        raise ValueError("tri_planar_source_certificate_payload_invalid")
    return value


def make_planar_triangle_template_anchor(
    source_certificate: Mapping[str, Any],
    edge_anchor: Mapping[str, Any],
    preflight_receipt: Mapping[str, Any],
    *,
    source_face_id: int,
    wall_edge_ids: Sequence[str],
    feature: str,
    patch: str,
    physical_group: str,
    component: str,
    provenance: str,
    template_id: str = "native-tri-planar-triangle-v1",
) -> dict[str, Any]:
    """Create an explicit template registration; it never infers geometry or labels."""

    certificate = _certificate(source_certificate)
    digest = str(preflight_receipt.get("preflight_digest", ""))
    if not digest or not preflight_receipt.get("preflight_accepted", False):
        raise ValueError("tri_planar_preflight_receipt_required")
    if len(tuple(wall_edge_ids)) != 3:
        raise ValueError("tri_planar_wall_edge_count_required")
    return {
        "schema": "NativeTriPlanarTriangleTemplate/v1",
        "template_id": str(template_id),
        "source_certificate_sha256": str(certificate["certificate_sha256"]),
        "edge_ledger_sha256": str(edge_anchor["edge_ledger_sha256"]),
        "preflight_digest": digest,
        "issuer": str(edge_anchor["issuer"]),
        "key_id": str(edge_anchor["key_id"]),
        "cavity_source_face_id": int(source_face_id),
        "wall_edge_ids": [str(value) for value in wall_edge_ids],
        "active_sector_face_ids": [int(source_face_id)] * 3,
        "feature": str(feature),
        "patch": str(patch),
        "physical_group": str(physical_group),
        "component": str(component),
        "provenance": str(provenance),
    }


def write_native_tri_planar_triangle_bl(
    source_certificate: Mapping[str, Any],
    edge_ledger: Sequence[Mapping[str, Any]],
    edge_anchor: Mapping[str, Any],
    template_anchor: Mapping[str, Any],
    *,
    requested_layers: int,
    first_height: float = 0.0,
    growth_ratio: float = 1.0,
) -> dict[str, Any]:
    """Run the private actual planar template with atomic C++ rollback."""

    if requested_layers < 0:
        return _refusal("tri_planar_requested_layers_invalid", requested_layers)
    try:
        kernel = import_native_extension("native_tri_planar_triangle_bl_template")
        return dict(
            kernel.write_native_tri_planar_triangle_bl(
                dict(source_certificate),
                [dict(row) for row in edge_ledger],
                dict(edge_anchor),
                dict(template_anchor),
                int(requested_layers),
                float(first_height),
                float(growth_ratio),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _refusal(
            f"native_tri_planar_triangle_bl_template_unavailable:{type(exc).__name__}",
            requested_layers,
        )


__all__ = [
    "make_planar_triangle_template_anchor",
    "write_native_tri_planar_triangle_bl",
]
