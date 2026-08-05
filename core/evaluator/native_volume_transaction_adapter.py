"""Staged, fail-closed publication adapter for native volume artifacts."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .native_authority_transaction_gate import (
    NativeAuthorityTransactionResult,
    evaluate_native_authority_transaction,
)


_TOPOLOGY_FIELDS = (
    "invalid",
    "duplicate",
    "non_manifold",
    "self_intersecting",
    "inverted",
    "negative_measure",
)
_QUALITY_FIELDS = (
    "non_orthogonality_p95",
    "non_orthogonality_max",
    "skewness_p95",
    "skewness_max",
    "metric_distortion_max",
)


@dataclass(frozen=True, slots=True)
class NativeVolumePublishResult:
    transaction: NativeAuthorityTransactionResult
    published: bool
    destination: str
    rollback_witness: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "transaction": self.transaction.as_dict(),
            "published": self.published,
            "destination": self.destination,
            "rollback_witness": self.rollback_witness,
        }


def _missing(evidence: Mapping[str, Any], names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if name not in evidence)


def _refusal(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    requested_layers: int,
    actual_layers: int,
    reason: str,
) -> NativeAuthorityTransactionResult:
    from .native_authority_transaction_gate import canonical_sha256

    return NativeAuthorityTransactionResult(
        accepted=False,
        status="refused_rollback",
        reasons=(reason,),
        baseline_sha256=canonical_sha256(baseline),
        candidate_sha256=canonical_sha256(candidate),
        committed=False,
        rolled_back=True,
        requested_layers=requested_layers,
        actual_layers=0,
    )


def evaluate_and_publish_native_volume_artifact(
    destination: str | Path,
    staged_artifact: str | Path,
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    requested_layers: int,
    actual_layers: int,
    evidence: Mapping[str, Any],
    baseline_manifest: Mapping[str, Any] | None = None,
    candidate_manifest: Mapping[str, Any] | None = None,
) -> NativeVolumePublishResult:
    """Publish a staged artifact only after complete evidence passes.

    ``staged_artifact`` must be a directory in the same filesystem as
    ``destination``.  Refusal never touches either destination or staged data.
    A successful swap retains a temporary sibling only until the new directory
    is visible; a failed swap attempts to restore the original directory.
    """
    destination_path = Path(destination)
    staged_path = Path(staged_artifact)
    missing = _missing(evidence, _TOPOLOGY_FIELDS + _QUALITY_FIELDS + ("source_sha256", "candidate_source_sha256", "authority_complete", "collision_free"))
    if missing:
        tx = _refusal(
            baseline,
            candidate,
            requested_layers=requested_layers,
            actual_layers=actual_layers,
            reason=f"missing_required_evidence:{','.join(missing)}",
        )
        return NativeVolumePublishResult(tx, False, str(destination_path), "destination_unchanged")
    if not staged_path.is_dir():
        tx = _refusal(
            baseline,
            candidate,
            requested_layers=requested_layers,
            actual_layers=actual_layers,
            reason="staged_artifact_missing",
        )
        return NativeVolumePublishResult(tx, False, str(destination_path), "destination_unchanged")

    tx = evaluate_native_authority_transaction(
        baseline,
        candidate,
        requested_layers=requested_layers,
        actual_layers=actual_layers,
        source_sha256=evidence["source_sha256"],
        candidate_source_sha256=evidence["candidate_source_sha256"],
        topology={name: evidence[name] for name in _TOPOLOGY_FIELDS},
        quality={name: evidence[name] for name in _QUALITY_FIELDS},
        authority_complete=evidence["authority_complete"] is True,
        collision_free=evidence["collision_free"] is True,
        baseline_manifest=baseline_manifest,
        candidate_manifest=candidate_manifest,
    )
    if not tx.accepted:
        return NativeVolumePublishResult(tx, False, str(destination_path), "destination_unchanged")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    try:
        if destination_path.exists():
            backup_path = Path(tempfile.mkdtemp(prefix=f".{destination_path.name}.rollback-", dir=destination_path.parent))
            backup_path.rmdir()
            os.replace(destination_path, backup_path)
        os.replace(staged_path, destination_path)
    except OSError:
        if destination_path.exists() and destination_path.is_dir():
            shutil.rmtree(destination_path)
        if backup_path is not None and backup_path.exists():
            os.replace(backup_path, destination_path)
        return NativeVolumePublishResult(tx, False, str(destination_path), "swap_failed_restored")
    if backup_path is not None and backup_path.exists():
        shutil.rmtree(backup_path)
    return NativeVolumePublishResult(tx, True, str(destination_path), None)


__all__ = ["NativeVolumePublishResult", "evaluate_and_publish_native_volume_artifact"]
