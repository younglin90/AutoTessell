"""Fail-closed, non-promoting evidence substrate for Gate-4 fidelity.

This module binds a Gate-4 comparison to an exact byte snapshot of the
caller-provided source and to one stable OpenFOAM ``polyMesh`` artifact.  It
intentionally does not decide Gate 4: the legacy geometry metric is incomplete
for the Gate-4 contract, so every result remains ``UNVERIFIED``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from core.schemas import (
    Gate4FidelityEvidence,
    Gate4OutputArtifactIdentity,
    Gate4SourceIdentity,
)

if TYPE_CHECKING:
    from core.evaluator.fidelity import GeometryFidelityChecker


_REQUIRED_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")


def capture_immutable_source(
    source_path: Path,
    snapshot_dir: Path,
) -> Gate4SourceIdentity:
    """Write one exact source-byte snapshot before pipeline mutations begin."""
    resolved = source_path.resolve(strict=True)
    source_bytes = resolved.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    suffix = resolved.suffix or ".bin"
    snapshot_path = snapshot_dir / f"gate4-original-{source_sha256}{suffix}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    if snapshot_path.exists():
        if snapshot_path.is_symlink() or snapshot_path.read_bytes() != source_bytes:
            raise ValueError("immutable Gate-4 source snapshot collision")
    else:
        snapshot_path.write_bytes(source_bytes)

    return Gate4SourceIdentity(
        original_path=str(resolved),
        snapshot_path=str(snapshot_path.resolve()),
        byte_count=len(source_bytes),
        sha256=source_sha256,
    )


def _inspect_output_artifact(case_dir: Path) -> Gate4OutputArtifactIdentity | None:
    poly_mesh = case_dir / "constant" / "polyMesh"
    if not poly_mesh.is_dir() or poly_mesh.is_symlink():
        return None

    files: dict[str, str] = {}
    for name in _REQUIRED_POLYMESH_FILES:
        candidate = poly_mesh / name
        if not candidate.is_file() or candidate.is_symlink():
            return None
        files[name] = hashlib.sha256(candidate.read_bytes()).hexdigest()

    aggregate = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return Gate4OutputArtifactIdentity(
        poly_mesh_path=str(poly_mesh.resolve()),
        file_sha256=files,
        sha256=aggregate,
    )


def evaluate_gate4_fidelity_evidence(
    *,
    source: Gate4SourceIdentity | None,
    source_status: str,
    case_dir: Path,
    diagonal: float | None,
    checker: GeometryFidelityChecker,
) -> Gate4FidelityEvidence:
    """Return structured Gate-4 evidence without issuing a Gate verdict."""
    if source is None:
        return Gate4FidelityEvidence(
            status=source_status,
            metric_status="not_attempted",
            gate4_pass=False,
        )

    snapshot_path = Path(source.snapshot_path)
    if (
        not snapshot_path.is_file()
        or snapshot_path.is_symlink()
        or hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != source.sha256
    ):
        return Gate4FidelityEvidence(
            status="unverified_source_snapshot_changed",
            source=source,
            metric_status="not_attempted",
            gate4_pass=False,
        )

    before = _inspect_output_artifact(case_dir)
    if before is None:
        return Gate4FidelityEvidence(
            status="unverified_output_artifact_missing",
            source=source,
            metric_status="not_attempted",
            gate4_pass=False,
        )

    try:
        metric = checker.compute(
            original_stl=snapshot_path,
            case_dir=case_dir,
            diagonal=max(float(diagonal or 0.0), 1.0e-30),
        )
    except Exception:  # noqa: BLE001
        metric = None

    after = _inspect_output_artifact(case_dir)
    if after is None or after.sha256 != before.sha256:
        return Gate4FidelityEvidence(
            status="unverified_output_artifact_changed",
            source=source,
            output=before,
            metric_status="not_attempted",
            gate4_pass=False,
        )
    if metric is None:
        return Gate4FidelityEvidence(
            status="unverified_metric_missing",
            source=source,
            output=before,
            metric_status="missing",
            gate4_pass=False,
        )
    return Gate4FidelityEvidence(
        status="unverified_metric_incomplete",
        source=source,
        output=before,
        metric_status="legacy_partial",
        geometry_fidelity=metric,
        gate4_pass=False,
    )
