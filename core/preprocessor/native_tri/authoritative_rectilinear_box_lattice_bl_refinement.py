"""Private C++23 authority-bound rectilinear-box Native Tri BL adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.utils.native_extensions import import_native_extension


def _refusal(reason: str, requested_layers: int = 0) -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "native_tri_authoritative_rectilinear_box_lattice_bl_refinement_refused",
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
        raise ValueError("rectilinear_box_source_certificate_payload_invalid")
    return value


def make_authoritative_rectilinear_box_lattice_template_anchor(
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
    template_id: str = "native-tri-authoritative-rectilinear-box-lattice-v1",
) -> dict[str, Any]:
    certificate = _certificate(source_certificate)
    faces = tuple(int(value) for value in source_face_ids)
    edges = tuple(str(value) for value in wall_edge_ids)
    active = tuple(int(value) for value in active_sector_face_ids)
    digest = str(preflight_receipt.get("preflight_digest", ""))
    if len(faces) != 2 or faces[0] >= faces[1]:
        raise ValueError("rectilinear_box_source_face_pair_required")
    if len(edges) != 4 or len(active) != 4:
        raise ValueError("rectilinear_box_four_edge_registration_required")
    if not digest or not preflight_receipt.get("preflight_accepted", False):
        raise ValueError("rectilinear_box_preflight_receipt_required")
    return {
        "schema": "NativeTriAuthoritativeRectilinearBoxLatticeBL/v1",
        "template_id": str(template_id),
        "source_certificate_sha256": str(certificate["certificate_sha256"]),
        "edge_ledger_sha256": str(edge_anchor["edge_ledger_sha256"]),
        "preflight_digest": digest,
        "issuer": str(edge_anchor["issuer"]),
        "key_id": str(edge_anchor["key_id"]),
        "source_face_ids": list(faces),
        "wall_edge_ids": list(edges),
        "active_sector_face_ids": list(active),
        "feature": str(feature),
        "patch": str(patch),
        "physical_group": str(physical_group),
        "component": str(component),
        "provenance": str(provenance),
    }


def write_native_tri_authoritative_rectilinear_box_lattice_bl(
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
        return _refusal("rectilinear_box_requested_layers_invalid", requested_layers)
    try:
        kernel = import_native_extension(
            "native_tri_authoritative_rectilinear_box_lattice_bl_refinement"
        )
        return dict(kernel.write_native_tri_authoritative_rectilinear_box_lattice_bl(
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
            f"native_tri_authoritative_rectilinear_box_lattice_unavailable:{type(exc).__name__}",
            requested_layers,
        )


def admit_native_tri_curved_naca_bl(
    source_certificate: Mapping[str, Any],
    *,
    requested_layers: int,
    first_height: float = 0.0,
    growth_ratio: float = 1.0,
) -> dict[str, Any]:
    if requested_layers < 0:
        return _refusal("curved_naca_requested_layers_invalid", requested_layers)
    try:
        kernel = import_native_extension(
            "native_tri_authoritative_rectilinear_box_lattice_bl_refinement"
        )
        return dict(kernel.admit_native_tri_curved_naca_bl(
            dict(source_certificate),
            int(requested_layers),
            float(first_height),
            float(growth_ratio),
        ))
    except Exception as exc:  # noqa: BLE001
        return _refusal(
            f"native_tri_curved_naca_admission_unavailable:{type(exc).__name__}",
            requested_layers,
        )


__all__ = [
    "admit_native_tri_curved_naca_bl",
    "make_authoritative_rectilinear_box_lattice_template_anchor",
    "write_native_tri_authoritative_rectilinear_box_lattice_bl",
]
