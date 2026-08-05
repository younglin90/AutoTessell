"""Thin orchestration adapter for the private C++ v2 snapshot writer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.utils.native_extensions import import_native_extension


def _plain(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def write_native_evidence_pack_v2(
    target_root: str | Path,
    engine: str,
    runs: Sequence[Mapping[str, Any]],
    requested_layers: int,
    actual_layers: int | None = None,
    *,
    producer_run_rows: Sequence[Mapping[str, Any]] | None = None,
    layer_records: Sequence[Mapping[str, Any]] | None = None,
    authority_level: str = "L0_synthetic",
    authority_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist three explicit producer snapshots through the C++ writer."""
    payload_runs: list[dict[str, Any]] = []
    for run in runs:
        row = dict(run)
        for key in ("points", "triangles", "quads", "cells"):
            row[key] = _plain(row[key])
        row["ledger"] = [dict(item) for item in row["ledger"]]
        row["boundary_binding"] = [dict(item) for item in row["boundary_binding"]]
        payload_runs.append(row)
    payload = {
        "engine": str(engine),
        "runs": payload_runs,
        "requested_layers": int(requested_layers),
        "actual_layers": int(requested_layers if actual_layers is None else actual_layers),
        "authority_level": str(authority_level),
    }
    if producer_run_rows is not None:
        payload["producer_run_rows"] = [dict(row) for row in producer_run_rows]
    if layer_records is not None:
        payload["layer_records"] = [dict(row) for row in layer_records]
    if authority_metadata is not None:
        payload["authority_metadata"] = dict(authority_metadata)
    try:
        kernel = import_native_extension("native_evidence_pack_v2_writer")
        return dict(kernel.write_pack(str(Path(target_root)), payload))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "native_evidence_pack_v2_writer_unavailable",
            "reason": f"writer_unavailable:{type(exc).__name__}",
            "publication_eligible": False,
            "candidate_discarded": True,
            "atomic_rollback": True,
        }


__all__ = ["write_native_evidence_pack_v2"]
