"""Thin adapter for the private C++ content-addressed L2 evidence audit."""
from __future__ import annotations
from typing import Any, Sequence
from core.utils.native_extensions import import_native_extension

def _rows(value: Any) -> list[list[Any]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [list(row) for row in value]

def audit_native_l2_evidence(
    engine: str,
    source_bytes: bytes,
    output_bytes: bytes,
    authority_receipt: dict[str, Any],
    authoritative_ledger: dict[str, Any],
    manifest: dict[str, Any],
    boundary_binding: Sequence[dict[str, Any]],
    points: Any,
    triangles: Any,
    quads: Any,
    cells: Any,
    requested_layers: int,
    actual_layers: int,
    baseline_digest: str,
    candidate_digest: str,
) -> dict[str, Any]:
    try:
        module = import_native_extension("native_l2_evidence_audit")
        return dict(module.audit_native_l2_evidence(
            str(engine), bytes(source_bytes), bytes(output_bytes),
            dict(authority_receipt), dict(authoritative_ledger), dict(manifest),
            [dict(row) for row in boundary_binding],
            _rows(points), _rows(triangles), _rows(quads), _rows(cells),
            int(requested_layers), int(actual_layers),
            str(baseline_digest), str(candidate_digest),
        ))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "native_l2_evidence_audit_unavailable",
            "reason": f"native_l2_evidence_audit_unavailable:{type(exc).__name__}",
            "runtime_route": "default_off",
            "publication_eligible": False,
            "candidate_discarded": True,
            "atomic_rollback": True,
        }



def audit_native_l2_persisted_evidence(evidence_root: str) -> dict[str, Any]:
    """Audit a persisted evidence root; geometry stays inside the C++ reader."""
    try:
        module = import_native_extension("native_l2_evidence_audit")
        return dict(module.audit_native_l2_persisted_evidence(str(evidence_root)))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "native_l2_persisted_evidence_unavailable",
            "reason": f"native_l2_persisted_evidence_unavailable:{type(exc).__name__}",
            "runtime_route": "default_off",
            "publication_eligible": False,
            "candidate_discarded": True,
            "atomic_rollback": True,
        }



def audit_native_tet_polymesh_persisted_evidence(evidence_root: str) -> dict[str, Any]:
    """Audit a persisted OpenFOAM ASCII polyMesh Tet artifact in native C++."""
    try:
        module = import_native_extension("native_l2_evidence_audit")
        return dict(module.audit_native_tet_polymesh_persisted_evidence(str(evidence_root)))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "native_tet_polymesh_persisted_evidence_unavailable",
            "reason": f"native_tet_polymesh_persisted_evidence_unavailable:{type(exc).__name__}",
            "runtime_route": "default_off",
            "publication_eligible": False,
            "candidate_discarded": True,
            "atomic_rollback": True,
        }

__all__ = ["audit_native_l2_evidence", "audit_native_l2_persisted_evidence", "audit_native_tet_polymesh_persisted_evidence"]
