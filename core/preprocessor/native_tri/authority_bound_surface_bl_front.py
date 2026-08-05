"""Private C++23 authority-bound non-box surface Native Tri wall-edge BL adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.utils.native_extensions import import_native_extension


def _refusal(reason: str, requested_layers: int = 0) -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "native_tri_authority_bound_surface_bl_front_refused",
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
        raise ValueError("surface_bl_source_certificate_payload_invalid")
    return value


def make_authority_bound_surface_bl_front_template_anchor(
    source_certificate: Mapping[str, Any],
    edge_anchor: Mapping[str, Any],
    preflight_receipt: Mapping[str, Any],
    *,
    source_face_ids: Sequence[int],
    wall_edge_ids: Sequence[str],
    active_sector_face_ids: Sequence[int],
    feature: str,
    patch: str,
    physical_group: str,
    component: str,
    provenance: str,
    template_id: str = "native-tri-authority-bound-surface-bl-front-v1",
) -> dict[str, Any]:
    certificate = _certificate(source_certificate)
    faces = [int(value) for value in source_face_ids]
    edges = [str(value) for value in wall_edge_ids]
    active = [int(value) for value in active_sector_face_ids]
    digest = str(preflight_receipt.get("preflight_digest", ""))
    if not faces:
        raise ValueError("surface_bl_source_face_registration_required")
    if not edges or len(edges) != len(active):
        raise ValueError("surface_bl_wall_edge_registration_invalid")
    if not digest or not preflight_receipt.get("preflight_accepted", False):
        raise ValueError("surface_bl_preflight_receipt_required")
    return {
        "schema": (
            "NativeTriAuthorityBoundSurfaceBL/multiface-v1"
            if "multiface" in str(template_id)
            else "NativeTriAuthorityBoundSurfaceBL/v1"
        ),
        "template_id": str(template_id),
        "source_certificate_sha256": str(certificate["certificate_sha256"]),
        "edge_ledger_sha256": str(edge_anchor["edge_ledger_sha256"]),
        "preflight_digest": digest,
        "issuer": str(edge_anchor["issuer"]),
        "key_id": str(edge_anchor["key_id"]),
        "source_face_ids": faces,
        "wall_edge_ids": edges,
        "active_sector_face_ids": active,
        "feature": str(feature),
        "patch": str(patch),
        "physical_group": str(physical_group),
        "component": str(component),
        "provenance": str(provenance),
    }



def make_authority_bound_multiface_surface_bl_front_template_anchor(
    source_certificate: Mapping[str, Any],
    edge_anchor: Mapping[str, Any],
    preflight_receipt: Mapping[str, Any],
    *,
    source_face_ids: Sequence[int],
    wall_edge_ids: Sequence[str],
    active_sector_face_ids: Sequence[int],
    feature: str,
    patch: str,
    physical_group: str,
    component: str,
    provenance: str,
) -> dict[str, Any]:
    return make_authority_bound_surface_bl_front_template_anchor(
        source_certificate,
        edge_anchor,
        preflight_receipt,
        source_face_ids=source_face_ids,
        wall_edge_ids=wall_edge_ids,
        active_sector_face_ids=active_sector_face_ids,
        feature=feature,
        patch=patch,
        physical_group=physical_group,
        component=component,
        provenance=provenance,
        template_id="native-tri-authority-bound-multiface-surface-bl-front-v1",
    )


def write_native_tri_authority_bound_surface_bl_front(
    source_certificate: Mapping[str, Any],
    edge_ledger: Sequence[Mapping[str, Any]],
    edge_anchor: Mapping[str, Any],
    template_anchor: Mapping[str, Any],
    *,
    requested_layers: int,
    first_height: float = 0.0,
    growth_ratio: float = 1.0,
) -> dict[str, Any]:
    if requested_layers < 0:
        return _refusal("surface_bl_requested_layers_invalid", requested_layers)
    try:
        kernel = import_native_extension(
            "native_tri_authority_bound_surface_bl_front"
        )
        return dict(kernel.write_native_tri_authority_bound_surface_bl_front(
            dict(source_certificate),
            [dict(row) for row in edge_ledger],
            dict(edge_anchor),
            dict(template_anchor),
            int(requested_layers),
            float(first_height),
            float(growth_ratio),
        ))
    except Exception as exc:  # noqa: BLE001
        return _refusal(
            f"native_tri_authority_bound_surface_bl_front_unavailable:{type(exc).__name__}",
            requested_layers,
        )


__all__ = [
    "make_authority_bound_surface_bl_front_template_anchor",
    "write_native_tri_authority_bound_surface_bl_front",
    "make_authority_bound_multiface_surface_bl_front_template_anchor",
]
