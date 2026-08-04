"""Python orchestration bridge for the C++ Native Tet BL admission gate.

The C++ extension owns geometry/topology/quality refusal order.  This thin
layer owns the canonical Python full-ledger validator so a positive admission
cannot use a top-level schema stub as provenance evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .full_ledger import validate_native_tet_full_ledger


def _refuse(reason: str, validation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "accepted": False,
        "status": "candidate_refused",
        "runtime_route": "default_off",
        "publication_eligible": False,
        "candidate_discarded": True,
        "rollback_required": True,
        "refusal_stage": "ledger",
        "refusal_reason": reason,
    }
    if validation is not None:
        result["ledger_verification"] = dict(validation)
    return result


def admit_candidate(
    points: Any,
    tets: Any,
    collision_triangles: Any,
    policy: Mapping[str, Any],
    requested_layers: int,
    *,
    base_points: Any | None = None,
    ledger: Mapping[str, Any] | None = None,
    authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the full ledger, then invoke the C++ candidate-only gate.

    BL=0 intentionally bypasses the positive-BL ledger because identity has no
    layer artifact.  Positive BL is fail-closed before geometry is admitted.
    """

    import native_tet_bl_admission as native_gate

    if int(requested_layers) == 0:
        return dict(
            native_gate.admit(
                points,
                tets,
                collision_triangles,
                dict(policy),
                0,
                base_points=base_points,
            )
        )

    if ledger is None:
        return _refuse("full_ledger_v2_required")
    if authority is None or "source_sha256" not in authority:
        return _refuse("authority_digests_required")

    validation = validate_native_tet_full_ledger(
        ledger,
        source_sha256=str(authority["source_sha256"]),
        requested_layers=int(requested_layers),
    )
    if not validation.get("accepted"):
        return _refuse("full_ledger_refused", validation)

    result = dict(
        native_gate.admit(
            points,
            tets,
            collision_triangles,
            dict(policy),
            int(requested_layers),
            base_points=base_points,
            ledger=dict(ledger),
            authority=dict(authority),
        )
    )
    result["ledger_verification"] = validation
    return result



def admit_writer_owned_candidate(
    points: Any,
    tets: Any,
    policy: Mapping[str, Any],
    requested_layers: int,
    *,
    base_points: Any | None = None,
    ledger: Mapping[str, Any] | None = None,
    authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the writer-owned outer-surface candidate route.

    The C++ route derives its collision surface from output Tet incidence and
    requires a sealed, complete user-input parameter digest.  It remains
    candidate-only/default-off; BL=0 uses the ordinary identity gate.
    """
    import numpy as np
    import native_tet_bl_admission as native_gate

    if int(requested_layers) == 0:
        return admit_candidate(
            points, tets, np.empty((0, 3), dtype=np.int64), policy, 0,
            base_points=base_points, ledger=ledger, authority=authority,
        )
    if ledger is None:
        return _refuse("full_ledger_v2_required")
    if authority is None or "source_sha256" not in authority:
        return _refuse("authority_digests_required")
    validation = validate_native_tet_full_ledger(
        ledger, source_sha256=str(authority["source_sha256"]), requested_layers=int(requested_layers)
    )
    if not validation.get("accepted"):
        return _refuse("full_ledger_refused", validation)
    result = dict(native_gate.admit_writer_owned_outer_surface(
        points, tets, dict(policy), int(requested_layers), dict(ledger), dict(authority)
    ))
    result["ledger_verification"] = validation
    return result

__all__ = ["admit_candidate", "admit_writer_owned_candidate"]

