"""L1 localization of sphere component/facet debt before the first CVT call."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPHERE = _ROOT / "tests" / "benchmarks" / "sphere.stl"
_L1_TIMEOUT_SECONDS = 480
_DETAILED_DEBT_ORDER = (
    "n_missing_source_vertices",
    "n_missing_source_faces",
    "n_unowned_candidate_faces",
    "n_uncovered_source_patches",
    "n_area_mismatch_patches",
    "n_feature_boundary_mismatches",
    "n_overlap_pairs",
)
_EXPECTED_COUNTS = {
    "n_missing_source_vertices": 636,
    "n_missing_source_faces": 1280,
    "n_unowned_candidate_faces": 1280,
    "n_uncovered_source_patches": 1280,
    "n_area_mismatch_patches": 0,
    "n_feature_boundary_mismatches": 0,
    "n_overlap_pairs": 0,
}


def _first_detailed_debt(record: dict[str, object]) -> str | None:
    """Return first nonzero existing metric in fixed diagnostic display order."""
    for metric in _DETAILED_DEBT_ORDER:
        value = record[metric]
        if not isinstance(value, int):
            raise TypeError(f"{metric} must be an int")
        if value > 0:
            return metric
    return None


def test_l0_detailed_debt_order_is_not_an_acceptance_policy() -> None:
    record = {
        "n_missing_source_vertices": 0,
        "n_missing_source_faces": 3,
        "n_unowned_candidate_faces": 4,
        "n_uncovered_source_patches": 5,
        "n_area_mismatch_patches": 0,
        "n_feature_boundary_mismatches": 0,
        "n_overlap_pairs": 0,
    }
    assert _first_detailed_debt(record) == "n_missing_source_faces"


def _worker_payload(repeat: int, case_dir: Path) -> dict[str, object]:
    import core.generator.native_tet.cvt3d as cvt3d
    from core.analyzer.readers import read_stl
    from core.generator.native_tet.initial_overlap_source_l1 import (
        capture_initial_strict_overlap_source_l1,
    )
    from core.generator.native_tet.mesher import generate_native_tet

    mesh = read_stl(_SPHERE)
    source_points = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    source_faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    records: list[dict[str, object]] = []
    original_cvt = cvt3d.lloyd_cvt_3d

    def traced_cvt(
        points: np.ndarray, tets: np.ndarray, *args: object, **kwargs: object
    ) -> tuple[np.ndarray, object]:
        if not records:
            records.append(
                capture_initial_strict_overlap_source_l1(
                    fixture="sphere",
                    repeat=repeat,
                    audit_call_index=0,
                    source_points=source_points,
                    source_faces=source_faces,
                    candidate_points=np.ascontiguousarray(points),
                    candidate_tets=np.ascontiguousarray(tets),
                ).as_json()
            )
        return original_cvt(points, tets, *args, **kwargs)

    cvt3d.lloyd_cvt_3d = traced_cvt
    try:
        result = generate_native_tet(
            source_points,
            source_faces,
            case_dir,
            target_cells=2000,
            enable_bsp_insertion=False,
            enable_edge_recovery=False,
            enable_phase_b=False,
            enable_phase_c=False,
        )
    finally:
        cvt3d.lloyd_cvt_3d = original_cvt

    record = records[0] if records else None
    return {
        "repeat": repeat,
        "result": {
            "success": result.success,
            "message": result.message,
            "n_cells": result.n_cells,
            "writer_artifact_exists": (case_dir / "constant" / "polyMesh").exists(),
        },
        "first_pre_cvt_record": record,
        "first_detailed_component_or_facet_debt": (
            _first_detailed_debt(record) if isinstance(record, dict) else None
        ),
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
            f"sphere pre-CVT provenance worker timed out after {_L1_TIMEOUT_SECONDS}s "
            f"for repeat {repeat}; evidence is UNVERIFIED: {error}"
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


def test_l1_sphere_pre_cvt_component_and_facet_debt_is_deterministic(
    tmp_path: Path,
) -> None:
    payloads = tuple(_run_worker(tmp_path, repeat) for repeat in range(3))
    for payload in payloads:
        result = payload["result"]
        record = payload["first_pre_cvt_record"]
        assert isinstance(result, dict) and isinstance(record, dict)
        assert result["success"] is False
        assert result["writer_artifact_exists"] is False
        assert record["component_bijective"] is False
        assert record["source_faces_preserved"] is False
        assert record["n_source_components"] == 1
        assert record["n_candidate_boundary_components"] == 1
        assert record["n_same_side_internal_faces"] == 108
        assert record["n_ambiguous_internal_faces"] == 0
        assert record["overlap_source_class"] == "same_side_overlap_source_provenance_debt"
        assert {metric: record[metric] for metric in _DETAILED_DEBT_ORDER} == _EXPECTED_COUNTS
        assert payload["first_detailed_component_or_facet_debt"] == "n_missing_source_vertices"
    signatures = tuple(
        (
            payload["result"],
            payload["first_detailed_component_or_facet_debt"],
            tuple(
                sorted(
                    (key, value)
                    for key, value in record.items()
                    if key != "repeat"
                )
            ),
        )
        for payload in payloads
        if isinstance(record := payload["first_pre_cvt_record"], dict)
    )
    assert signatures == (signatures[0], signatures[0], signatures[0])


def _main() -> None:
    if len(sys.argv) != 5 or sys.argv[1] != "--worker":
        raise SystemExit(
            "usage: test_native_tet_sphere_pre_cvt_provenance_l1.py "
            "--worker repeat case evidence"
        )
    repeat_text, case_text, evidence_text = sys.argv[2:]
    payload = _worker_payload(int(repeat_text), Path(case_text))
    Path(evidence_text).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    _main()
