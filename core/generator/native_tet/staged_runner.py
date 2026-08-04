from __future__ import annotations

from dataclasses import dataclass
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from core.evaluator.native_artifact_tree import fingerprint_staged_artifact_tree
from core.utils.native_extensions import import_native_extension


@dataclass(frozen=True)
class StagedTetRunEvidence:
    result: Any
    audit: Any | None
    publish: dict[str, Any] | None
    stage_case: str
    published: bool
    artifact_fingerprint: Mapping[str, Any] | None = None
    transaction_journal: Mapping[str, Any] | None = None
    refused_reason: str | None = None
    destination_audit: Any | None = None


def _directory_manifest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not root.is_dir():
        return result
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result
def _audit_is_valid(audit: Any) -> bool:
    if isinstance(audit, Mapping):
        return audit.get("accepted") is True or audit.get("valid") is True
    return bool(getattr(audit, "accepted", False) or getattr(audit, "valid", False))


def run_tet_in_private_stage(
    runner: Callable[..., Any],
    vertices: Any,
    faces: Any,
    case_dir: str | Path,
    *,
    audit_callback: Callable[[Path], Any],
    post_publish_audit_callback: Callable[[Path], Any] | None = None,
    journal_path: str | Path | None = None,
    journal_history_path: str | Path | None = None,
    **kwargs: Any,
) -> StagedTetRunEvidence:
    """Run a Tet callback only in a stage and publish after a complete audit."""
    destination = Path(case_dir)
    if not destination.parent.is_dir():
        raise ValueError("tet_destination_parent_missing")
    kernel = import_native_extension("native_atomic_publish")
    stage = Path(kernel.make_stage(str(destination)))
    published_to_destination = False
    try:
        result = runner(vertices, faces, stage, **kwargs)
        if not bool(getattr(result, "success", False)):
            kernel.discard_stage(str(stage))
            return StagedTetRunEvidence(
                result=result, audit=None, publish=None, stage_case=str(stage),
                published=False, refused_reason="runner_refused",
            )
        seal_stage = getattr(kernel, "seal_stage", None)
        if not callable(seal_stage):
            kernel.discard_stage(str(stage))
            return StagedTetRunEvidence(
                result=result, audit=None, publish=None, stage_case=str(stage),
                published=False, refused_reason="stage_seal_unavailable",
            )
        try:
            seal_stage(str(stage))
        except Exception as exc:
            kernel.discard_stage(str(stage))
            return StagedTetRunEvidence(
                result=result, audit=None, publish=None, stage_case=str(stage),
                published=False,
                refused_reason=f"stage_seal_failed:{type(exc).__name__}",
            )
        before_audit = fingerprint_staged_artifact_tree(stage)
        audit = audit_callback(stage)
        if not _audit_is_valid(audit):
            kernel.discard_stage(str(stage))
            reason = (
                str(audit.get("reason"))
                if isinstance(audit, Mapping) and audit.get("reason")
                else "full_audit_refused"
            )
            return StagedTetRunEvidence(
                result=result, audit=audit, publish=None, stage_case=str(stage),
                published=False, artifact_fingerprint=before_audit,
                refused_reason=reason,
            )
        after_audit = fingerprint_staged_artifact_tree(stage)
        if (
            before_audit.get("tree_sha256") != after_audit.get("tree_sha256")
            or before_audit.get("entry_count") != after_audit.get("entry_count")
        ):
            kernel.discard_stage(str(stage))
            return StagedTetRunEvidence(
                result=result, audit=audit, publish=None, stage_case=str(stage),
                published=False, artifact_fingerprint=after_audit,
                refused_reason="artifact_changed_after_audit",
            )
        transaction = None
        if journal_path is not None:
            from core.generator.native_tet.staged_transaction import StagedTransaction

            transaction = StagedTransaction.start(
                journal_path, destination, stage, journal_history_path
            )
        candidate_manifest = _directory_manifest(stage)
        if transaction is not None:
            transaction.admit(candidate_manifest)
        if transaction is not None and post_publish_audit_callback is None:
            transaction.rolled_back({"reason": "destination_audit_missing"})
            kernel.discard_stage(str(stage))
            transaction_evidence = {
                "path": str(transaction.path),
                "history_path": str(transaction.history_path),
                "state": "backup_retired",
                "outcome": "rolled_back",
                "closed": True,
            }
            return StagedTetRunEvidence(
                result=result, audit=audit, publish=None, stage_case=str(stage),
                published=False, artifact_fingerprint=after_audit,
                transaction_journal=transaction_evidence,
                refused_reason="destination_audit_missing",
            )
        publish = dict(kernel.publish_stage(str(destination), str(stage)))
        published_to_destination = True
        destination_audit = None
        if transaction is not None:
            transaction.published(candidate_manifest, publish)
        if post_publish_audit_callback is not None:
            try:
                destination_audit = post_publish_audit_callback(destination)
            except Exception as exc:
                destination_audit = {
                    "accepted": False,
                    "reason": f"destination_audit_exception:{type(exc).__name__}",
                }
            if _audit_is_valid(destination_audit):
                destination_manifest = _directory_manifest(destination)
                if destination_manifest != candidate_manifest:
                    destination_audit = {
                        "accepted": False,
                        "reason": "destination_manifest_mismatch",
                        "expected_entry_count": len(candidate_manifest),
                        "actual_entry_count": len(destination_manifest),
                    }
            publish["destination_audit"] = destination_audit
            if not _audit_is_valid(destination_audit):
                rollback_backup = publish.get("rollback_backup")
                try:
                    rollback = dict(kernel.rollback_stage(
                        str(destination),
                        "" if rollback_backup is None else str(rollback_backup),
                    ))
                    publish["rollback"] = rollback
                    rollback_ok = rollback.get("restored_baseline") is True
                except Exception as exc:
                    publish["rollback_error"] = f"{type(exc).__name__}:{exc}"
                    rollback_ok = False
                reason = (
                    str(destination_audit.get("reason"))
                    if isinstance(destination_audit, Mapping) and destination_audit.get("reason")
                    else "destination_audit_refused"
                )
                if not rollback_ok:
                    reason = "incomplete_publish:" + reason
                transaction_evidence = None
                if rollback_ok and transaction is not None:
                    transaction.rolled_back({
                        "destination_audit": destination_audit,
                        "rollback": publish.get("rollback"),
                    })
                    transaction_evidence = {
                        "path": str(transaction.path),
                        "history_path": str(transaction.history_path),
                        "state": "backup_retired",
                        "outcome": "rolled_back",
                        "closed": True,
                    }
                    publish["transaction_journal"] = transaction_evidence
                return StagedTetRunEvidence(
                    result=result, audit=audit, publish=publish,
                    stage_case=str(stage), published=False,
                    artifact_fingerprint=after_audit,
                    refused_reason=reason,
                    destination_audit=destination_audit,
                    transaction_journal=transaction_evidence,
                )
        transaction_evidence = None
        if transaction is not None:
            rollback_backup = publish.get("rollback_backup")
            if rollback_backup:
                kernel.discard_stage(str(rollback_backup))
            transaction.committed({"destination_audit": destination_audit})
            transaction_evidence = {
                "path": str(transaction.path),
                "history_path": str(transaction.history_path),
                "state": "backup_retired",
                "closed": True,
            }
            publish["transaction_journal"] = transaction_evidence
        return StagedTetRunEvidence(
            result=result, audit=audit, publish=publish, stage_case=str(stage),
            published=True, artifact_fingerprint=after_audit,
            transaction_journal=transaction_evidence,
            destination_audit=destination_audit,
        )
    except Exception:
        if not published_to_destination and stage.exists() and stage.name.startswith(".autotessell-stage-"):
            kernel.discard_stage(str(stage))
        raise


@dataclass(frozen=True)
class StagedTetBLContractEvidence:
    runs: tuple[Any, ...]
    audits: tuple[Any, ...]
    publish: dict[str, Any] | None
    stage_case: str
    published: bool
    artifact_fingerprint: Mapping[str, Any] | None = None
    refused_reason: str | None = None


def _authority_is_sealed(authority: Mapping[str, Any] | None) -> bool:
    if not isinstance(authority, Mapping):
        return False
    digest = str(authority.get("source_sha256", ""))
    return (
        authority.get("accepted") is True
        and authority.get("receipt_sealed") is True
        and authority.get("direct_lineage") is True
        and len(digest) == 64
        and all(ch in "0123456789abcdef" for ch in digest.lower())
        and authority.get("wall_edge_eligible") is True
        and authority.get("source_authority_status") == "SOURCE_VERIFIED"
        and authority.get("provisional") is not True
    )


def _copy_case_into_stage(source: Path, stage: Path) -> None:
    if not source.is_dir():
        raise ValueError("tet_source_case_missing")
    shutil.copytree(source, stage, dirs_exist_ok=True)


def run_tet_bl_contract_in_private_stage(
    case_dir: str | Path,
    *,
    run_callback: Callable[[Path, Mapping[str, Any], int], Any],
    audit_callback: Callable[[Path], Any],
    source_authority: Mapping[str, Any] | None,
    requested_layers: int,
) -> StagedTetBLContractEvidence:
    """Run actual Tet BL callbacks in three isolated stages before publish."""
    destination = Path(case_dir)
    if not destination.parent.is_dir():
        raise ValueError("tet_destination_parent_missing")
    if requested_layers < 0:
        raise ValueError("negative_layer_count")
    if requested_layers > 0 and not _authority_is_sealed(source_authority):
        return StagedTetBLContractEvidence(
            runs=(), audits=(), publish=None, stage_case="", published=False,
            refused_reason="native_tet_positive_bl_source_authority_missing",
        )
    kernel = import_native_extension("native_atomic_publish")
    run_stages: list[Path] = []
    run_results: list[Any] = []
    audits: list[Any] = []
    first_fingerprint: Mapping[str, Any] | None = None
    published = False
    try:
        for run_index in range(1, 4):
            if run_index == 1:
                stage = Path(kernel.make_stage(str(destination)))
            else:
                stage = Path(tempfile.mkdtemp(
                    prefix=".autotessell-tet-bl-run-",
                    dir=str(destination.parent),
                ))
            run_stages.append(stage)
            _copy_case_into_stage(destination, stage)
            result = (
                run_callback(stage, source_authority or {}, run_index)
                if requested_layers > 0
                else None
            )
            if requested_layers > 0 and not bool(getattr(result, "success", False)):
                return StagedTetBLContractEvidence(
                    tuple(run_results), tuple(audits), None, str(stage), False,
                    refused_reason="native_tet_positive_bl_writer_refused",
                )
            if requested_layers > 0 and not all(
                (stage / name).is_file()
                for name in ("evidence.atne", "ledger.tsv", "binding.tsv", "layers.tsv")
            ):
                return StagedTetBLContractEvidence(
                    tuple(run_results), tuple(audits), None, str(stage), False,
                    refused_reason=(
                        "native_tet_direct_id_capsule_unavailable:"
                        "native_bl_capsule_missing"
                    ),
                )
            if requested_layers > 0:
                from core.generator.native_tet.writer_ledger import (
                    validate_native_tet_writer_ledger,
                )
                ledger = validate_native_tet_writer_ledger(
                    stage / "native_tet_bl_writer_ledger.json",
                    source_sha256=str((source_authority or {}).get("source_sha256", "")),
                    requested_layers=requested_layers,
                )
                if ledger.get("accepted") is not True:
                    return StagedTetBLContractEvidence(
                        tuple(run_results), tuple(audits), None, str(stage), False,
                        refused_reason="native_tet_writer_ledger_refused",
                    )
            if requested_layers == 0 and any(
                (stage / name).exists()
                for name in ("evidence.atne", "ledger.tsv", "binding.tsv", "layers.tsv")
            ):
                return StagedTetBLContractEvidence(
                    tuple(run_results), tuple(audits), None, str(stage), False,
                    refused_reason="native_tet_bl0_sidecar_forbidden",
                )
            before = fingerprint_staged_artifact_tree(stage)
            audit = audit_callback(stage)
            if not _audit_is_valid(audit):
                return StagedTetBLContractEvidence(
                    tuple(run_results), tuple(audits), None, str(stage), False,
                    artifact_fingerprint=before,
                    refused_reason=(
                        str(audit.get("reason"))
                        if isinstance(audit, Mapping) and audit.get("reason")
                        else "native_tet_bl_contract_audit_refused"
                    ),
                )
            after = fingerprint_staged_artifact_tree(stage)
            if (
                before.get("tree_sha256") != after.get("tree_sha256")
                or before.get("entry_count") != after.get("entry_count")
            ):
                return StagedTetBLContractEvidence(
                    tuple(run_results), tuple(audits), None, str(stage), False,
                    artifact_fingerprint=after,
                    refused_reason="artifact_changed_after_audit",
                )
            run_results.append(result)
            audits.append(audit)
            if run_index == 1:
                first_fingerprint = after
            elif first_fingerprint is None or after.get("tree_sha256") != first_fingerprint.get("tree_sha256"):
                return StagedTetBLContractEvidence(
                    tuple(run_results), tuple(audits), None, str(stage), False,
                    artifact_fingerprint=after,
                    refused_reason="native_tet_bl_repeatability_mismatch",
                )
        assert first_fingerprint is not None
        publish = dict(kernel.publish_stage(str(destination), str(run_stages[0])))
        published = True
        for extra in run_stages[1:]:
            shutil.rmtree(extra, ignore_errors=True)
        return StagedTetBLContractEvidence(
            tuple(run_results), tuple(audits), publish, str(run_stages[0]),
            True, artifact_fingerprint=first_fingerprint,
        )
    except Exception:
        raise
    finally:
        if not published:
            for stage in run_stages:
                if stage.exists():
                    if stage.name.startswith(".autotessell-stage-"):
                        kernel.discard_stage(str(stage))
                    elif stage.name.startswith(".autotessell-tet-bl-run-"):
                        shutil.rmtree(stage, ignore_errors=True)


__all__ = [
    "StagedTetRunEvidence",
    "run_tet_in_private_stage",
    "StagedTetBLContractEvidence",
    "run_tet_bl_contract_in_private_stage",
]
