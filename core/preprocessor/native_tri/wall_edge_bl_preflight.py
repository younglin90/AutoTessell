"""C++23-backed Native Tri wall-edge BL authority preflight.

This module validates an explicit, externally registered wall-edge ledger. It
never infers wall edges, generates a BL, or promotes a release route.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from core.utils.native_extensions import import_native_extension


def _refusal(reason: str) -> dict[str, Any]:
    return {
        "accepted": False,
        "preflight_accepted": False,
        "status": "native_tri_wall_edge_bl_preflight_refused",
        "reason": reason,
        "actual_layers": 0,
        "writer_invoked": False,
        "preflight_only": True,
        "artifact_emitted": False,
        "release_eligible": False,
        "publication_eligible": False,
        "candidate_discarded": True,
        "runtime_route": "private_default_off",
        "route_calls": 0,
        "generated_vertices": [],
        "generated_faces": [],
        "provenance": [],
        "wall_edges": [],
        "layer_heights": [],
    }


def _field(value: object) -> str:
    text = str(value)
    return f"{len(text)}:{text}|"


def _edge_stream(
    ledger: Sequence[Mapping[str, Any]],
    loop_policy: str,
    loop_endpoints: Sequence[int],
) -> str:
    rows = sorted(ledger, key=lambda row: str(row["edge_id"]))
    parts = ["loop_policy=", _field(loop_policy)]
    parts.append(f"loop_endpoints={len(loop_endpoints)}|")
    parts.append("".join(f"{int(value)}," for value in loop_endpoints))
    parts.append("|")
    parts.append(f"rows={len(rows)}|")
    for row in rows:
        parts.append(_field(row["edge_id"]))
        endpoints = [int(value) for value in row["endpoint_vertex_ids"]]
        parts.append(f"{endpoints[0]},{endpoints[1]}|")
        incident = [int(value) for value in row["incident_face_ids"]]
        parts.append(f"{len(incident)}|")
        parts.append("".join(f"{value}," for value in incident))
        parts.append("|")
        sector_faces = [int(value) for value in row["directed_sector_face_ids"]]
        parts.append(f"{len(sector_faces)}|")
        parts.append("".join(f"{value}," for value in sector_faces))
        parts.append("|")
        sectors = [str(value) for value in row["directed_sector_ids"]]
        parts.append(f"{len(sectors)}|")
        parts.extend(_field(value) for value in sectors)
        for key in (
            "wall_role",
            "patch_boundary_role",
            "feature",
            "patch",
            "physical_group",
            "component",
            "provenance",
        ):
            parts.append(_field(row[key]))
    return "".join(parts)


def edge_ledger_sha256(
    ledger: Sequence[Mapping[str, Any]],
    *,
    loop_policy: str,
    loop_endpoint_vertex_ids: Sequence[int] = (),
) -> str:
    """Return the C++ preflight's canonical edge-ledger digest."""

    stream = _edge_stream(ledger, loop_policy, loop_endpoint_vertex_ids)
    return hashlib.sha256(stream.encode("utf-8")).hexdigest()


def make_external_edge_trust_anchor(
    source_certificate: Mapping[str, Any],
    ledger: Sequence[Mapping[str, Any]],
    *,
    loop_policy: str,
    loop_endpoint_vertex_ids: Sequence[int] = (),
    issuer: str,
    key_id: str,
) -> dict[str, Any]:
    """Create an external registration record; it does not infer edge labels."""

    certificate = source_certificate.get("certificate", source_certificate)
    if not isinstance(certificate, Mapping):
        raise ValueError("tri_wall_edge_source_certificate_payload_invalid")
    required = (
        "source_sha256",
        "source_byte_count",
        "semantic_ledger_sha256",
        "certificate_sha256",
    )
    if any(key not in certificate for key in required):
        raise ValueError("tri_wall_edge_source_certificate_fields_missing")
    endpoints = tuple(int(value) for value in loop_endpoint_vertex_ids)
    return {
        "source_sha256": str(certificate["source_sha256"]),
        "source_byte_count": int(certificate["source_byte_count"]),
        "semantic_ledger_sha256": str(certificate["semantic_ledger_sha256"]),
        "certificate_sha256": str(certificate["certificate_sha256"]),
        "edge_ledger_sha256": edge_ledger_sha256(
            ledger,
            loop_policy=loop_policy,
            loop_endpoint_vertex_ids=endpoints,
        ),
        "issuer": str(issuer),
        "key_id": str(key_id),
        "loop_policy": str(loop_policy),
        "loop_endpoint_vertex_ids": list(endpoints),
    }


def validate_native_tri_wall_edge_bl_preflight(
    source_certificate: Mapping[str, Any],
    edge_ledger: Sequence[Mapping[str, Any]],
    trust_anchor: Mapping[str, Any],
    *,
    requested_layers: int = 0,
    first_height: float = 0.0,
    growth_ratio: float = 1.0,
) -> dict[str, Any]:
    """Validate explicit wall-edge authority through the private C++ module."""

    try:
        module = import_native_extension("native_tri_wall_edge_bl_preflight")
        return dict(
            module.validate_native_tri_wall_edge_bl_preflight(
                dict(source_certificate),
                [dict(row) for row in edge_ledger],
                dict(trust_anchor),
                int(requested_layers),
                float(first_height),
                float(growth_ratio),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _refusal(f"native_tri_wall_edge_preflight_unavailable:{type(exc).__name__}")


__all__ = [
    "edge_ledger_sha256",
    "make_external_edge_trust_anchor",
    "validate_native_tri_wall_edge_bl_preflight",
]
