"""Private-stage transaction boundary for positive Native BL requests.

The meshing kernel remains in :mod:`native_bl`; this module owns only the
candidate isolation, independent admission checks, and same-filesystem
directory publish.  It deliberately has no import back into ``native_bl`` so
the kernel can call it without a circular import.
"""
from __future__ import annotations

import hashlib
import json
import importlib
import os
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import numpy as np

from core.evaluator.native_transaction_journal import (
    advance_journal,
    close_journal,
    failpoint,
    recover_journal,
    start_journal,
)

_ARTIFACTS = (
    "native_bl_state.json",
    "native_bl_quality.json",
    "native_bl_lineage.json",
    "native_bl_provenance.json",
    "native_hex_writer_order.json",
)


def _digest(hashes: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_receipt(
    case_dir: Path,
    *,
    status: str,
    input_hashes: dict[str, str],
    candidate_hashes: dict[str, str] | None,
    reasons: list[str],
    topology: dict[str, Any] | None = None,
) -> None:
    if status == "refused_rollback" and candidate_hashes == input_hashes:
        return
    payload = {
        "schema": "autotessell/native-bl-transaction/v1",
        "status": status,
        "rolled_back": status in {"refused_rollback", "failed_rollback"},
        "input_mesh_sha256": input_hashes,
        "input_fingerprint": _digest(input_hashes),
        "candidate_mesh_sha256": candidate_hashes,
        "candidate_fingerprint": _digest(candidate_hashes) if candidate_hashes else None,
        "reasons": list(reasons),
        "topology": topology,
    }
    path = case_dir / "native_bl_transaction_receipt.json"
    temporary = case_dir / f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_native_atomic_publish():
    try:
        return importlib.import_module("native_atomic_publish")
    except ImportError:
        build = Path(__file__).resolve().parents[2] / "auto_tessell_core" / "build"
        if build.is_dir() and str(build) not in sys.path:
            sys.path.insert(0, str(build))
        try:
            return importlib.import_module("native_atomic_publish")
        except ImportError:
            return None
def _publish(
    case_dir: Path,
    stage_case: Path,
    *,
    artifacts: tuple[str, ...] = _ARTIFACTS,
    journal_path: Path | None = None,
    retain_backup: bool = False,
    backup_name: str | None = None,
) -> Path | None:
    constant = case_dir / "constant"
    live = constant / "polyMesh"
    candidate = stage_case / "constant" / "polyMesh"
    if not live.is_dir() or not candidate.is_dir():
        raise FileNotFoundError("native BL transaction mesh directory missing")
    backup = constant / (backup_name or f".native_bl_transaction_backup.{os.getpid()}.{time.time_ns()}")
    if journal_path is not None:
        advance_journal(journal_path, "backup_renamed")
        failpoint("backup_renamed")
    native_atomic = _load_native_atomic_publish()
    if native_atomic is not None:
        os.replace(candidate, backup)
        native_atomic.publish_stage(str(live), str(backup))
        if journal_path is not None:
            advance_journal(journal_path, "candidate_renamed")
            failpoint("candidate_renamed")
        for name in artifacts:
            source = stage_case / name
            if not source.is_file():
                continue
            destination = case_dir / name
            temporary = case_dir / f".{name}.{os.getpid()}.{time.time_ns()}.tmp"
            try:
                shutil.copy2(source, temporary)
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
        if journal_path is not None:
            advance_journal(journal_path, "directory_fsynced")
            failpoint("directory_fsynced")
        if backup.exists() and not retain_backup:
            shutil.rmtree(backup)
        return backup if retain_backup else None
    os.replace(live, backup)
    try:
        os.replace(candidate, live)
        if journal_path is not None:
            advance_journal(journal_path, "candidate_renamed")
            failpoint("candidate_renamed")
        try:
            fd = os.open(constant, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass
        if journal_path is not None:
            advance_journal(journal_path, "directory_fsynced")
            failpoint("directory_fsynced")
    except Exception:
        if live.exists():
            shutil.rmtree(live)
        if backup.exists():
            os.replace(backup, live)
        raise
    finally:
        if backup.exists() and not retain_backup:
            shutil.rmtree(backup)

    for name in artifacts:
        source = stage_case / name
        if not source.is_file():
            continue
        destination = case_dir / name
        temporary = case_dir / f".{name}.{os.getpid()}.{time.time_ns()}.tmp"
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    return backup if retain_backup else None

def run_private_native_bl_transaction(
    case_dir: Path,
    cfg: Any,
    *,
    engine_tag: str,
    generate_fn: Callable[..., Any],
    result_cls: Callable[..., Any],
) -> Any:
    """Run one positive BL candidate privately and publish only if admitted."""
    started = time.perf_counter()
    case_dir = Path(case_dir)
    token = f"{os.getpid()}_{time.time_ns()}"
    stage_case = case_dir / f".native_bl_stage.{token}"
    journal_path = case_dir / "native_bl_transaction_journal.json"
    history_path = case_dir / "native_bl_transaction_history.json"
    poly_dir = case_dir / "constant" / "polyMesh"
    try:
        from core.layers.native_bl import _polymesh_file_hashes

        recover_journal(case_dir, journal_path, hash_directory=_polymesh_file_hashes)
        input_hashes = _polymesh_file_hashes(poly_dir)
    except Exception as exc:
        return result_cls(
            success=False,
            elapsed=time.perf_counter() - started,
            message=f"native BL transaction input refused: {exc}",
            transaction_status="refused_rollback",
        )

    candidate: Any | None = None
    candidate_hashes: dict[str, str] | None = None
    try:
        (stage_case / "constant").mkdir(parents=True)
        shutil.copytree(poly_dir, stage_case / "constant" / "polyMesh")
        for item in case_dir.iterdir():
            if item == stage_case or not item.is_file():
                continue
            shutil.copy2(item, stage_case / item.name)


        start_journal(
            journal_path,
            token=token,
            live="constant/polyMesh",
            stage=stage_case.relative_to(case_dir).as_posix(),
            backup=f"constant/.native_bl_transaction_backup.{token}",
            baseline_hashes=input_hashes,
        )
        failpoint("stage_created")
        candidate = generate_fn(
            stage_case,
            cfg,
            engine_tag=f"__native_bl_stage__:{engine_tag}",
        )
        if (stage_case / "constant" / "polyMesh" / "points").is_file():
            candidate_hashes = _polymesh_file_hashes(
                stage_case / "constant" / "polyMesh"
            )
        if getattr(candidate, "actual_layers", 0) == 0:
            try:
                from core.evaluator.native_checker import NativeMeshChecker
                disk_quality = NativeMeshChecker().run(stage_case)
                candidate = replace(
                    candidate,
                    requested_layers=int(getattr(cfg, "num_layers", 0)),
                    actual_layers=int(getattr(cfg, "num_layers", 0)) if int(getattr(candidate, "n_prism_cells", 0)) > 0 else 0,
                    first_layer_height=float(getattr(cfg, "first_thickness", 0.0)),
                    min_first_layer_height=float(getattr(cfg, "first_thickness", 0.0)),
                    positive_thickness=bool(int(getattr(candidate, "n_prism_cells", 0)) > 0 and float(getattr(cfg, "first_thickness", 0.0)) > 0.0),
                    max_skewness=float(disk_quality.max_skewness),
                    max_non_orthogonality=float(disk_quality.max_non_orthogonality),
                    min_face_weight=float(disk_quality.min_face_weight),
                    min_scaled_jacobian=float(disk_quality.min_determinant),
                    negative_volumes=int(disk_quality.negative_volumes),
                    quality_readback_status="measured",
                )
            except Exception:
                pass

        reasons: list[str] = []
        if not bool(getattr(candidate, "success", False)):
            reasons.append(f"candidate_failed:{getattr(candidate, 'message', '')}")
        requested = int(getattr(cfg, "num_layers", 0))
        if int(getattr(candidate, "actual_layers", 0)) != requested:
            reasons.append(
                f"layer_count_mismatch:{getattr(candidate, 'actual_layers', 0)}!={requested}"
            )
        if int(getattr(candidate, "n_prism_cells", 0)) <= 0:
            reasons.append("positive_layer_cell_count_missing")
        if not bool(getattr(candidate, "positive_thickness", False)):
            reasons.append("positive_layer_thickness_missing")
        if getattr(candidate, "quality_readback_status", "") != "measured":
            reasons.append("quality_readback_missing")
        negative = int(getattr(candidate, "negative_volumes", 0) or 0)
        if negative != 0:
            reasons.append(f"negative_volumes:{negative}")
        for name in ("max_skewness", "max_non_orthogonality", "min_face_weight"):
            value = getattr(candidate, name, None)
            if value is None or not np.isfinite(float(value)):
                reasons.append(f"quality_metric_missing:{name}")
        for name, limit, value, relation in (
            ("max_skewness", getattr(cfg, "max_skewness", None), getattr(candidate, "max_skewness", None), "upper"),
            ("max_non_orthogonality", getattr(cfg, "max_non_orthogonality", None), getattr(candidate, "max_non_orthogonality", None), "upper"),
            ("max_quality_aspect_ratio", getattr(cfg, "max_quality_aspect_ratio", None), getattr(candidate, "max_aspect_ratio", None), "upper"),
            ("min_face_weight", getattr(cfg, "min_face_weight", None), getattr(candidate, "min_face_weight", None), "lower"),
            ("min_scaled_jacobian", getattr(cfg, "min_scaled_jacobian", None), getattr(candidate, "min_scaled_jacobian", None), "lower"),
            ("min_first_layer_height", getattr(cfg, "min_first_layer_height", None), getattr(candidate, "first_layer_height", None), "lower"),
        ):
            if limit is None:
                continue
            if value is None or not np.isfinite(float(value)):
                reasons.append(f"quality_limit_metric_missing:{name}")
                continue
            violates = (
                float(value) > float(limit)
                if relation == "upper" else float(value) < float(limit)
            )
            if violates:
                reasons.append(f"quality_limit_failed:{name}:{float(value):.8g}!={float(limit):.8g}")

        topology_payload: dict[str, Any] | None = None
        try:
            from core.evaluator.strict_volume_topology import audit_strict_volume_topology

            strict = audit_strict_volume_topology(stage_case)
            topology_payload = strict.as_dict()
            if not strict.valid:
                reasons.append("strict_volume_topology_failed")
        except Exception as exc:
            reasons.append(f"strict_volume_topology_unavailable:{type(exc).__name__}")

        if reasons:
            _write_receipt(
                case_dir,
                status="refused_rollback",
                input_hashes=input_hashes,
                candidate_hashes=candidate_hashes,
                reasons=reasons,
                topology=topology_payload,
            )
            recover_journal(case_dir, journal_path, hash_directory=_polymesh_file_hashes)
            return replace(
                candidate,
                success=False,
                elapsed=time.perf_counter() - started,
                message="native BL candidate refused; authoritative mesh unchanged: "
                + "; ".join(reasons),
                transaction_status="rolled_back",
            )

        advance_journal(journal_path, "candidate_admitted", candidate_hashes=candidate_hashes)
        failpoint("candidate_admitted")
        backup_path = _publish(
            case_dir, stage_case, journal_path=journal_path, retain_backup=True,
            backup_name=f".native_bl_transaction_backup.{token}",
        )
        output_hashes = _polymesh_file_hashes(poly_dir)
        _write_receipt(
            case_dir,
            status="committed",
            input_hashes=input_hashes,
            candidate_hashes=output_hashes,
            reasons=[],
            topology=topology_payload,
        )
        advance_journal(
            journal_path, "commit_receipt_published", candidate_hashes=output_hashes
        )
        failpoint("commit_receipt_published")
        if backup_path is not None and backup_path.exists():
            shutil.rmtree(backup_path)
        advance_journal(journal_path, "backup_retired", candidate_hashes=output_hashes)
        close_journal(journal_path, history_path=history_path)
        return replace(
            candidate,
            elapsed=time.perf_counter() - started,
            transaction_status="committed",
            message=f"{candidate.message} [private candidate committed]",
        )
    except Exception as exc:
        _write_receipt(
            case_dir,
            status="failed_rollback",
            input_hashes=input_hashes,
            candidate_hashes=candidate_hashes,
            reasons=[f"transaction_exception:{type(exc).__name__}:{exc}"],
        )
        try:
            recover_journal(case_dir, journal_path, hash_directory=_polymesh_file_hashes)
        except Exception:
            pass
        if candidate is not None:
            return replace(
                candidate,
                success=False,
                elapsed=time.perf_counter() - started,
                message=f"native BL transaction rolled back: {exc}",
                transaction_status="rolled_back",
            )
        return result_cls(
            success=False,
            elapsed=time.perf_counter() - started,
            message=f"native BL transaction rolled back: {exc}",
            transaction_status="rolled_back",
        )
    finally:
        if stage_case.exists():
            shutil.rmtree(stage_case)


__all__ = ["run_private_native_bl_transaction"]
