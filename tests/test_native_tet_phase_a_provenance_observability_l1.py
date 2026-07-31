"""L1 report-only source-provenance checkpoints for native-tet Phase A."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPHERE = _ROOT / "tests" / "benchmarks" / "sphere.stl"
_L1_TIMEOUT_SECONDS = 480
_EXPECTED_STAGES = (
    "post_filter_compaction",
    "post_bsp_orient_fix",
    "post_phase_a_smoothing",
    "pre_cvt3d",
)


def _audit_passes(record: dict[str, object]) -> bool:
    """Return existing source-provenance conjunction without changing policy."""
    return bool(
        record["component_bijective"]
        and record["source_faces_preserved"]
        and record["n_unowned_candidate_faces"] == 0
    )


def _worker_payload(repeat: int, case_dir: Path) -> dict[str, object]:
    from core.analyzer.readers import read_stl
    from core.generator.native_tet.initial_overlap_source_l1 import (
        capture_initial_strict_overlap_source_l1,
    )
    from core.generator.native_tet.mesher import generate_native_tet

    mesh = read_stl(_SPHERE)
    source_points = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    source_faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    records: list[dict[str, object]] = []
    observer_failures: list[str] = []

    def observer(checkpoint: Any) -> None:
        arrays = (
            checkpoint.source_points,
            checkpoint.source_faces,
            checkpoint.candidate_points,
            checkpoint.candidate_tets,
        )
        for values in arrays:
            if not values.flags.c_contiguous or values.flags.writeable:
                observer_failures.append("checkpoint arrays must be readonly C-order")
            try:
                values.setflags(write=True)
            except ValueError:
                pass
            else:
                observer_failures.append("checkpoint arrays must remain immutable")
        records.append(
            {
                "stage": checkpoint.stage,
                "record": capture_initial_strict_overlap_source_l1(
                    fixture="sphere",
                    repeat=repeat,
                    audit_call_index=len(records),
                    source_points=checkpoint.source_points,
                    source_faces=checkpoint.source_faces,
                    candidate_points=checkpoint.candidate_points,
                    candidate_tets=checkpoint.candidate_tets,
                ).as_json(),
            }
        )

    result = generate_native_tet(
        source_points,
        source_faces,
        case_dir,
        target_cells=2000,
        enable_bsp_insertion=False,
        enable_edge_recovery=False,
        enable_phase_b=False,
        enable_phase_c=False,
        _phase_a_observer=observer,
    )
    earliest_failed_stage = next(
        (
            stage["stage"]
            for stage in records
            if isinstance(stage.get("record"), dict)
            and not _audit_passes(stage["record"])
        ),
        None,
    )
    return {
        "repeat": repeat,
        "result": {
            "success": result.success,
            "message": result.message,
            "n_cells": result.n_cells,
            "writer_artifact_exists": (case_dir / "constant" / "polyMesh").exists(),
        },
        "records": records,
        "observer_failures": observer_failures,
        "earliest_observed_failed_stage": earliest_failed_stage,
    }


def _run_worker(tmp_path: Path, repeat: int) -> dict[str, object]:
    evidence = tmp_path / f"sphere_{repeat}.json"
    case_dir = tmp_path / f"sphere_{repeat}"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        str(repeat),
        str(case_dir),
        str(evidence),
    ]
    environment = dict(os.environ)
    prior_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        str(_ROOT) if not prior_pythonpath else f"{_ROOT}:{prior_pythonpath}"
    )
    try:
        completed = subprocess.run(
            command,
            cwd=_ROOT,
            check=False,
            capture_output=True,
            env=environment,
            text=True,
            timeout=_L1_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        pytest.fail(
            "Phase-A provenance observer worker timed out after "
            f"{_L1_TIMEOUT_SECONDS}s for repeat {repeat}; evidence UNVERIFIED: {error}"
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


def test_phase_a_observer_locates_only_observed_sphere_boundary_interval(
    tmp_path: Path,
) -> None:
    payloads = tuple(_run_worker(tmp_path, repeat) for repeat in range(3))
    for payload in payloads:
        result = payload["result"]
        records = payload["records"]
        assert isinstance(result, dict)
        assert isinstance(records, list)
        assert payload["observer_failures"] == []
        assert result["success"] is False
        assert result["writer_artifact_exists"] is False
        assert tuple(stage["stage"] for stage in records) == _EXPECTED_STAGES
        for stage in records[:2]:
            record = stage["record"]
            assert isinstance(record, dict)
            assert _audit_passes(record) is True
            assert record["n_same_side_internal_faces"] == 0
            assert record["n_ambiguous_internal_faces"] == 184
        post_smoothing = records[2]["record"]
        assert isinstance(post_smoothing, dict)
        assert _audit_passes(post_smoothing) is True
        assert post_smoothing["n_same_side_internal_faces"] == 120
        assert post_smoothing["n_ambiguous_internal_faces"] == 0
        pre_cvt = records[-1]["record"]
        assert isinstance(pre_cvt, dict)
        assert _audit_passes(pre_cvt) is False
        assert pre_cvt["n_same_side_internal_faces"] == 108
        assert pre_cvt["n_missing_source_vertices"] == 636
        assert pre_cvt["n_missing_source_faces"] == 1280
        assert payload["earliest_observed_failed_stage"] == "pre_cvt3d"
    signatures = tuple(
        (
            payload["result"],
            payload["earliest_observed_failed_stage"],
            tuple(
                (
                    stage["stage"],
                    tuple(
                        sorted(
                            (key, value)
                            for key, value in stage["record"].items()
                            if key != "repeat"
                        )
                    ),
                )
                for stage in payload["records"]
            ),
        )
        for payload in payloads
    )
    assert signatures == (signatures[0], signatures[0], signatures[0])


def _main() -> None:
    if len(sys.argv) != 5 or sys.argv[1] != "--worker":
        raise SystemExit(
            "usage: test_native_tet_phase_a_provenance_observability_l1.py "
            "--worker repeat case evidence"
        )
    repeat_text, case_text, evidence_text = sys.argv[2:]
    payload = _worker_payload(int(repeat_text), Path(case_text))
    Path(evidence_text).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    _main()
