"""Private-only ingress for producer-owned Native Poly BL traces.

This shell is deliberately separate from ``run_poly_bl_transition`` and the
public ``generate_native_bl`` defaults.  It creates an isolated same-filesystem
stage, verifies the authoritative source ledger, and only then invokes a
producer callback that returns trace records captured from final arrays.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from core.evaluator.native_poly_source_ledger import SourceLedgerRefusal, validate_source_ledger
from core.evaluator.native_poly_bl_producer_certificate import (
    build_producer_certificate,
    canonical_sha256,
    write_producer_certificate,
)

_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
_SOURCE_FACE_KEYS = (
    "source_face_id",
    "ordered_vertex_ids",
    "canonical_vertex_ids",
    "patch_id",
    "feature_id",
    "physical_group",
    "component_id",
)


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def polymesh_hashes(case_dir: str | Path) -> dict[str, str]:
    poly = Path(case_dir) / "constant" / "polyMesh"
    result: dict[str, str] = {}
    for name in _POLYMESH_FILES:
        path = poly / name
        if not path.is_file():
            raise ValueError(f"source_polymesh_file_missing:{name}")
        result[name] = _digest_file(path)
    return result


def _validate_source_ledger(ledger: Mapping[str, Any], source_hashes: Mapping[str, str]) -> str | None:
    try:
        validate_source_ledger(ledger, source_hashes)
    except SourceLedgerRefusal as error:
        return str(error)
    return None


def _same_filesystem(source: Path, stage_parent: Path) -> bool:
    try:
        return os.stat(source).st_dev == os.stat(stage_parent).st_dev
    except OSError:
        return False


def prepare_private_poly_bl_stage(
    source_case_dir: str | Path,
    stage_case_dir: str | Path,
    source_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and clone a source case into a new private sibling stage."""
    source = Path(source_case_dir).resolve()
    stage = Path(stage_case_dir).resolve()
    if source == stage:
        return {"status": "REFUSED", "reason": "stage_equals_source", "destination_unchanged": True}
    if source in stage.parents or stage in source.parents:
        return {"status": "REFUSED", "reason": "stage_source_nested", "destination_unchanged": True}
    if not source.is_dir() or not stage.parent.is_dir():
        return {"status": "REFUSED", "reason": "source_or_stage_parent_missing", "destination_unchanged": True}
    if stage.exists():
        return {"status": "REFUSED", "reason": "stage_must_not_exist", "destination_unchanged": True}
    if not _same_filesystem(source, stage.parent):
        return {"status": "REFUSED", "reason": "stage_cross_filesystem", "destination_unchanged": True}
    try:
        hashes = polymesh_hashes(source)
    except ValueError as error:
        return {"status": "REFUSED", "reason": str(error), "destination_unchanged": True}
    reason = _validate_source_ledger(source_ledger, hashes)
    if reason is not None:
        return {"status": "REFUSED", "reason": reason, "destination_unchanged": True}
    try:
        shutil.copytree(source, stage)
        stage_hashes = polymesh_hashes(stage)
    except (OSError, ValueError) as error:
        if stage.exists():
            shutil.rmtree(stage)
        return {"status": "REFUSED", "reason": f"stage_clone_failed:{type(error).__name__}", "destination_unchanged": True}
    if stage_hashes != hashes:
        shutil.rmtree(stage)
        return {"status": "REFUSED", "reason": "stage_clone_digest_mismatch", "destination_unchanged": True}
    return {
        "status": "PASS",
        "reason": "private_stage_ready",
        "source_case_dir": str(source),
        "stage_case_dir": str(stage),
        "source_polymesh_sha256": hashes,
        "stage_polymesh_sha256": stage_hashes,
        "source_sha256": canonical_sha256(hashes),
        "destination_unchanged": True,
    }


def run_private_poly_bl_trace(
    source_case_dir: str | Path,
    stage_case_dir: str | Path,
    source_ledger: Mapping[str, Any],
    *,
    requested_layers: int,
    producer_callback: Callable[[Path, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    engine_tag: str = "poly",
    apply_bulk_dual: bool = False,
    discard_stage_on_failure: bool = True,
) -> dict[str, Any]:
    """Run a private producer trace callback and emit v2 evidence on success.

    The callback must return producer-captured records accepted by
    ``build_producer_certificate``.  It must not be a post-hoc geometry matcher.
    """
    started = time.perf_counter()
    if engine_tag != "poly":
        return {"status": "REFUSED", "reason": "engine_tag_not_poly", "destination_unchanged": True}
    if apply_bulk_dual:
        return {"status": "REFUSED", "reason": "dualization_not_supported", "destination_unchanged": True}
    if requested_layers < 0:
        return {"status": "REFUSED", "reason": "layer_count_negative", "destination_unchanged": True}
    prepared = prepare_private_poly_bl_stage(source_case_dir, stage_case_dir, source_ledger)
    if prepared.get("status") != "PASS":
        return {**prepared, "elapsed": time.perf_counter() - started}
    stage = Path(prepared["stage_case_dir"])
    source = Path(prepared["source_case_dir"])
    if requested_layers == 0:
        return {
            **prepared,
            "reason": "bl0_certificate_bypass_identity",
            "producer_called": False,
            "elapsed": time.perf_counter() - started,
        }
    if producer_callback is None:
        if discard_stage_on_failure:
            shutil.rmtree(stage)
        return {"status": "REFUSED", "reason": "producer_callback_missing", "destination_unchanged": True}
    ledger_digest_before = canonical_sha256(source_ledger)
    callback_ledger = copy.deepcopy(dict(source_ledger))
    try:
        trace = producer_callback(stage, callback_ledger)
    except TimeoutError as error:
        if discard_stage_on_failure and stage.exists():
            shutil.rmtree(stage)
        return {"status": "TIMEOUT", "reason": "producer_timeout", "error": str(error), "destination_unchanged": True}
    except Exception as error:  # noqa: BLE001
        if discard_stage_on_failure and stage.exists():
            shutil.rmtree(stage)
        return {"status": "REFUSED", "reason": f"producer_exception:{type(error).__name__}", "destination_unchanged": True}
    if canonical_sha256(source_ledger) != ledger_digest_before or canonical_sha256(callback_ledger) != ledger_digest_before:
        if discard_stage_on_failure and stage.exists():
            shutil.rmtree(stage)
        return {"status": "REFUSED", "reason": "source_ledger_mutated", "destination_unchanged": True}
    try:
        if not isinstance(trace, Mapping) or trace.get("unsupported_path"):
            raise ValueError("unsupported_producer_path")
        if polymesh_hashes(source) != prepared["source_polymesh_sha256"]:
            raise ValueError("source_case_mutated")
        provenance, partition = build_producer_certificate(
            source_faces=trace["source_faces"],
            wall_edges=trace["wall_edges"],
            layer_entities=trace["layer_entities"],
            outer_front=trace["outer_front"],
            cell_partitions=trace["cell_partitions"],
            final_cell_ids=trace["final_cell_ids"],
            requested_layers=requested_layers,
            actual_layers=int(trace["actual_layers"]),
            total_thickness=float(trace["total_thickness"]),
            source_sha256=str(prepared["source_sha256"]),
            candidate_file_sha256=trace["candidate_file_sha256"],
            transition_not_applicable=bool(trace.get("transition_not_applicable", False)),
        )
        paths = write_producer_certificate(stage, provenance, partition)
    except (KeyError, TypeError, ValueError) as error:
        if discard_stage_on_failure and stage.exists():
            shutil.rmtree(stage)
        return {"status": "REFUSED", "reason": f"producer_trace_invalid:{error}", "destination_unchanged": True}
    return {
        **prepared,
        "status": "PASS",
        "reason": "private_producer_certificate_emitted",
        "producer_called": True,
        "provenance_path": str(paths[0]),
        "partition_path": str(paths[1]),
        "provenance_sha256": canonical_sha256(provenance),
        "partition_sha256": partition["partition_sha256"],
        "elapsed": time.perf_counter() - started,
        "publish_allowed": False,
    }


__all__ = ["polymesh_hashes", "prepare_private_poly_bl_stage", "run_private_poly_bl_trace"]
