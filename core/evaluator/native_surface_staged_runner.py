"""C++-published, quality/audit-gated surface artifact staging."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.evaluator.native_artifact_tree import fingerprint_staged_artifact_tree
from core.utils.native_extensions import import_native_extension


@dataclass(frozen=True)
class StagedSurfaceArtifactEvidence:
    runs: tuple[Mapping[str, Any], ...]
    audits: tuple[Mapping[str, Any], ...]
    publish: Mapping[str, Any] | None
    stage_case: str
    published: bool
    artifact_fingerprint: Mapping[str, Any] | None = None
    refused_reason: str | None = None


def _authority_sealed(authority: Mapping[str, Any] | None) -> bool:
    if not isinstance(authority, Mapping):
        return False
    digest = str(authority.get("source_sha256", ""))
    return (
        authority.get("accepted") is True
        and authority.get("receipt_sealed") is True
        and authority.get("direct_lineage") is True
        and authority.get("wall_edge_eligible") is True
        and authority.get("source_authority_status") == "SOURCE_VERIFIED"
        and authority.get("provisional") is not True
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest.lower())
    )


def _audit_ok(value: Any) -> bool:
    return bool(
        isinstance(value, Mapping)
        and (value.get("accepted") is True or value.get("valid") is True)
    )


def run_surface_artifact_in_private_stage(
    destination: str | Path,
    *,
    writer_callback: Callable[[Path, int], Mapping[str, Any]],
    audit_callback: Callable[[Path, Mapping[str, Any]], Mapping[str, Any]],
    source_authority: Mapping[str, Any] | None,
    requested_layers: int,
) -> StagedSurfaceArtifactEvidence:
    """Run three deterministic surface writes and publish only after audit.

    The callback owns format-specific mesh serialization. This runner owns the
    transaction boundary, BL identity rule, repeatability fingerprint, and
    C++ atomic publish. Failed stages are discarded and never replace the
    destination.
    """
    target = Path(destination)
    if requested_layers < 0:
        return StagedSurfaceArtifactEvidence((), (), None, "", False, refused_reason="negative_layer_count")
    if not target.parent.is_dir():
        return StagedSurfaceArtifactEvidence((), (), None, "", False, refused_reason="destination_parent_missing")
    if requested_layers > 0 and not _authority_sealed(source_authority):
        return StagedSurfaceArtifactEvidence((), (), None, "", False, refused_reason="surface_positive_bl_authority_missing")

    kernel = import_native_extension("native_atomic_publish")
    stages: list[Path] = []
    runs: list[Mapping[str, Any]] = []
    audits: list[Mapping[str, Any]] = []
    first_fingerprint: Mapping[str, Any] | None = None
    published = False
    try:
        for run_index in range(1, 4):
            if run_index == 1:
                stage = Path(kernel.make_stage(str(target)))
            else:
                stage = Path(tempfile.mkdtemp(prefix=".autotessell-surface-run-", dir=str(target.parent)))
            stages.append(stage)
            result = dict(writer_callback(stage, run_index))
            actual_layers = result.get("actual_layers", 0)
            if result.get("accepted") is not True:
                return StagedSurfaceArtifactEvidence(tuple(runs), tuple(audits), None, str(stage), False, refused_reason="surface_writer_refused")
            if actual_layers != requested_layers:
                return StagedSurfaceArtifactEvidence(tuple(runs), tuple(audits), None, str(stage), False, refused_reason="surface_actual_layer_count_mismatch")
            if requested_layers == 0:
                if result.get("bl_sidecar_created") is True or actual_layers != 0:
                    return StagedSurfaceArtifactEvidence(tuple(runs), tuple(audits), None, str(stage), False, refused_reason="surface_bl0_sidecar_forbidden")
            else:
                if not result.get("source_authority_bound") or not result.get("provenance"):
                    return StagedSurfaceArtifactEvidence(tuple(runs), tuple(audits), None, str(stage), False, refused_reason="surface_positive_bl_evidence_missing")
                if float(result.get("positive_thickness", 0.0)) <= 0.0:
                    return StagedSurfaceArtifactEvidence(tuple(runs), tuple(audits), None, str(stage), False, refused_reason="surface_positive_thickness_missing")
            before = fingerprint_staged_artifact_tree(stage)
            audit = dict(audit_callback(stage, result))
            if not _audit_ok(audit):
                return StagedSurfaceArtifactEvidence(tuple(runs), tuple(audits), None, str(stage), False, before, "surface_independent_audit_refused")
            after = fingerprint_staged_artifact_tree(stage)
            if before.get("tree_sha256") != after.get("tree_sha256") or before.get("entry_count") != after.get("entry_count"):
                return StagedSurfaceArtifactEvidence(tuple(runs), tuple(audits), None, str(stage), False, after, "surface_artifact_changed_after_audit")
            if first_fingerprint is None:
                first_fingerprint = after
            elif after.get("tree_sha256") != first_fingerprint.get("tree_sha256") or after.get("entry_count") != first_fingerprint.get("entry_count"):
                return StagedSurfaceArtifactEvidence(tuple(runs), tuple(audits), None, str(stage), False, after, "surface_repeatability_mismatch")
            runs.append(result)
            audits.append(audit)
        assert first_fingerprint is not None
        publish = dict(kernel.publish_stage(str(target), str(stages[0])))
        published = True
        return StagedSurfaceArtifactEvidence(tuple(runs), tuple(audits), publish, str(stages[0]), True, first_fingerprint)
    finally:
        if not published:
            for stage in stages:
                if stage.exists():
                    if stage.name.startswith(".autotessell-stage-"):
                        kernel.discard_stage(str(stage))
                    elif stage.name.startswith(".autotessell-surface-run-"):
                        shutil.rmtree(stage, ignore_errors=True)
        else:
            for stage in stages[1:]:
                if stage.exists():
                    shutil.rmtree(stage, ignore_errors=True)


__all__ = ["StagedSurfaceArtifactEvidence", "run_surface_artifact_in_private_stage"]
