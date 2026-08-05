"""Fail-closed authority gate for the native surface wall-edge release route.

This is a contract adapter, not a mesher.  It prevents a candidate-only
surface transaction from being called a release artifact until an explicit
route, independent quality receipt, source ledger, parameter digest, and
atomic package receipt are all present.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_SOURCE_KEYS = (
    "raw_sha256",
    "semantic_ledger_sha256",
    "provenance_sha256",
)
_PACKAGE_KEYS = (
    "package_digest",
    "output_geometry_sha256",
    "output_topology_sha256",
    "quality_receipt_sha256",
    "parameter_sha256",
)


def _digest(value: Any) -> bool:
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def _refuse(reason: str, requested_layers: int | None) -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "native_surface_release_route_refused",
        "reason": reason,
        "requested_layers": requested_layers,
        "actual_layers": 0,
        "release_eligible": False,
        "route_selected": False,
        "candidate_discarded": True,
        "runtime_route": "default_off",
    }


def admit_authoritative_surface_release(
    candidate: Mapping[str, Any] | None,
    *,
    source_certificate: Mapping[str, Any] | None,
    parameter_digest: str | None,
    packaging_receipt: Mapping[str, Any] | None,
    requested_layers: int | None,
    explicit_route: bool = False,
) -> dict[str, Any]:
    """Admit only a fully evidenced surface candidate.

    The existing C++ front and Python transaction intentionally return
    ``default_off``.  That result is a correct refusal here.  A future actual
    writer may pass this gate only after it supplies every receipt and opts in
    explicitly; no threshold is relaxed by this adapter.
    """

    if requested_layers is None or not isinstance(requested_layers, int) or requested_layers < 0:
        return _refuse("requested_layers_invalid", requested_layers)
    if not explicit_route:
        return _refuse("explicit_surface_release_route_required", requested_layers)
    if not isinstance(candidate, Mapping):
        return _refuse("candidate_missing", requested_layers)
    if candidate.get("accepted") is not True:
        return _refuse("candidate_not_accepted", requested_layers)
    if candidate.get("candidate_discarded") is True:
        return _refuse("candidate_discarded", requested_layers)
    if candidate.get("runtime_route") in {"default_off", "private_default_off", None}:
        return _refuse("candidate_route_default_off", requested_layers)
    if candidate.get("publication_eligible") is not True:
        return _refuse("candidate_not_publication_eligible", requested_layers)
    if candidate.get("source_authority_bound") is not True or candidate.get("authority_checked") is not True:
        return _refuse("candidate_authority_incomplete", requested_layers)
    if candidate.get("transaction_atomic") is not True:
        return _refuse("candidate_transaction_not_atomic", requested_layers)
    actual_layers = candidate.get("actual_layers")
    if actual_layers != requested_layers:
        return _refuse("candidate_layer_count_mismatch", requested_layers)
    if requested_layers > 0 and not candidate.get("provenance"):
        return _refuse("candidate_wall_edge_provenance_missing", requested_layers)
    if any(candidate.get(key) != 0 for key in (
        "topology_invalid", "topology_inverted", "topology_duplicate", "topology_non_manifold",
    )):
        return _refuse("candidate_topology_gate_failed", requested_layers)

    if not isinstance(source_certificate, Mapping):
        return _refuse("source_certificate_missing", requested_layers)
    if any(not _digest(source_certificate.get(key)) for key in _SOURCE_KEYS):
        return _refuse("source_certificate_digest_incomplete", requested_layers)
    if not _digest(parameter_digest):
        return _refuse("parameter_digest_missing", requested_layers)
    if not isinstance(packaging_receipt, Mapping):
        return _refuse("packaging_receipt_missing", requested_layers)
    if any(not _digest(packaging_receipt.get(key)) for key in _PACKAGE_KEYS):
        return _refuse("packaging_receipt_incomplete", requested_layers)
    if packaging_receipt.get("atomic") is not True or packaging_receipt.get("fsynced") is not True:
        return _refuse("packaging_atomic_receipt_missing", requested_layers)
    if packaging_receipt.get("source_digest") != candidate.get("source_digest"):
        return _refuse("packaging_source_digest_mismatch", requested_layers)
    if packaging_receipt.get("output_digest") != candidate.get("output_digest"):
        return _refuse("packaging_output_digest_mismatch", requested_layers)

    return {
        "accepted": True,
        "status": "native_surface_release_route_admitted",
        "reason": "source_quality_authority_and_packaging_gates_passed",
        "requested_layers": requested_layers,
        "actual_layers": actual_layers,
        "release_eligible": True,
        "route_selected": True,
        "candidate_discarded": False,
        "runtime_route": "native_surface_authority_bound",
        "source_certificate": dict(source_certificate),
        "parameter_digest": parameter_digest,
        "packaging_receipt": dict(packaging_receipt),
    }


__all__ = ["admit_authoritative_surface_release"]
