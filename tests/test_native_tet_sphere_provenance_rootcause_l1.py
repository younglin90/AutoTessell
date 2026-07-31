"""L1 localization of the first sphere provenance-debt mesh stage."""

from __future__ import annotations

import inspect
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


def _provenance_satisfies_current_audit(record: dict[str, object]) -> bool:
    """Return existing component/facet audit conjunction; never changes policy."""
    return bool(
        record["component_bijective"]
        and record["source_faces_preserved"]
        and record["n_unowned_candidate_faces"] == 0
    )


def _worker_payload(repeat: int, case_dir: Path) -> dict[str, object]:
    import scipy.spatial

    import core.generator.native_tet.cvt3d as cvt3d
    import core.generator.native_tet.mesher as mesher
    from core.analyzer.readers import read_stl
    from core.generator.native_tet.initial_overlap_source_l1 import (
        capture_initial_strict_overlap_source_l1,
    )
    from core.generator.native_tet.mesher import generate_native_tet

    mesh = read_stl(_SPHERE)
    source_points = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    source_faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    stage_records: list[dict[str, object]] = []
    inline_stage_records: list[dict[str, object]] = []
    pre_cvt_records: list[dict[str, object]] = []
    original_delaunay = scipy.spatial.Delaunay
    original_cvt = cvt3d.lloyd_cvt_3d

    def traced_delaunay(
        seed_points: np.ndarray, *args: object, **kwargs: object
    ) -> object:
        result = original_delaunay(seed_points, *args, **kwargs)
        caller = inspect.currentframe().f_back
        if caller is not None and caller.f_code.co_name == "_run_delaunay":
            stage_records.append(
                {
                    "stage": f"run_delaunay_{len(stage_records)}",
                    "record": capture_initial_strict_overlap_source_l1(
                        fixture="sphere",
                        repeat=repeat,
                        audit_call_index=len(stage_records),
                        source_points=source_points,
                        source_faces=source_faces,
                        candidate_points=np.ascontiguousarray(seed_points),
                        candidate_tets=np.ascontiguousarray(
                            result.simplices, dtype=np.int64
                        ),
                    ).as_json(),
                }
            )
        return result

    def traced_cvt(
        points: np.ndarray, tets: np.ndarray, *args: object, **kwargs: object
    ) -> tuple[np.ndarray, object]:
        if not pre_cvt_records:
            pre_cvt_records.append(
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

    mesher_path = str(Path(mesher.__file__).resolve())

    def traced_line(frame: object, event: str, _arg: object) -> object:
        if event != "line" or not hasattr(frame, "f_code"):
            return traced_line
        if frame.f_code.co_filename != mesher_path:
            return traced_line
        stage_name = {
            2196: "post_sliver_filter",
            2208: "post_filter_compaction",
        }.get(frame.f_lineno)
        if stage_name is None or any(
            record["stage"] == stage_name for record in inline_stage_records
        ):
            return traced_line
        locals_map = frame.f_locals
        points = locals_map.get("all_pts")
        tets = (
            locals_map.get("kept")
            if stage_name == "post_sliver_filter"
            else locals_map.get("final_tets")
        )
        if not isinstance(points, np.ndarray) or not isinstance(tets, np.ndarray):
            return traced_line
        inline_stage_records.append(
            {
                "stage": stage_name,
                "record": capture_initial_strict_overlap_source_l1(
                    fixture="sphere",
                    repeat=repeat,
                    audit_call_index=len(inline_stage_records) + 1,
                    source_points=source_points,
                    source_faces=source_faces,
                    candidate_points=np.ascontiguousarray(
                        points if stage_name == "post_sliver_filter" else locals_map["final_pts"]
                    ),
                    candidate_tets=np.ascontiguousarray(tets, dtype=np.int64),
                ).as_json(),
            }
        )
        return traced_line

    scipy.spatial.Delaunay = traced_delaunay
    cvt3d.lloyd_cvt_3d = traced_cvt
    previous_trace = sys.gettrace()
    sys.settrace(traced_line)
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
        sys.settrace(previous_trace)
        scipy.spatial.Delaunay = original_delaunay
        cvt3d.lloyd_cvt_3d = original_cvt

    initial_stage = stage_records[0] if stage_records else None
    pre_cvt_record = pre_cvt_records[0] if pre_cvt_records else None
    observed_stages = (*stage_records, *inline_stage_records)
    earliest_failed_stage = next(
        (
            stage["stage"]
            for stage in observed_stages
            if isinstance(stage.get("record"), dict)
            and not _provenance_satisfies_current_audit(stage["record"])
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
        "delaunay_stage_records": stage_records,
        "inline_stage_records": inline_stage_records,
        "base_delaunay_record": initial_stage,
        "first_pre_cvt_record": pre_cvt_record,
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
            f"sphere provenance root-cause worker timed out after {_L1_TIMEOUT_SECONDS}s "
            f"for repeat {repeat}; evidence is UNVERIFIED: {error}"
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


def test_l1_observed_stage_boundaries_defer_first_provenance_root_cause(
    tmp_path: Path,
) -> None:
    payloads = tuple(_run_worker(tmp_path, repeat) for repeat in range(3))
    for payload in payloads:
        result = payload["result"]
        initial = payload["base_delaunay_record"]
        pre_cvt = payload["first_pre_cvt_record"]
        stages = payload["delaunay_stage_records"]
        inline_stages = payload["inline_stage_records"]
        assert isinstance(result, dict)
        assert isinstance(initial, dict) and isinstance(pre_cvt, dict)
        assert isinstance(stages, list) and stages
        assert isinstance(inline_stages, list) and inline_stages
        assert result["success"] is False
        assert result["writer_artifact_exists"] is False
        assert initial["stage"] == "run_delaunay_0"
        initial_record = initial["record"]
        assert isinstance(initial_record, dict)
        assert _provenance_satisfies_current_audit(initial_record) is True
        assert initial_record["n_same_side_internal_faces"] == 0
        assert initial_record["n_ambiguous_internal_faces"] == 184
        for stage in inline_stages:
            assert isinstance(stage, dict)
            stage_record = stage["record"]
            assert isinstance(stage_record, dict)
            assert _provenance_satisfies_current_audit(stage_record) is True
            assert stage_record["n_same_side_internal_faces"] == 0
            assert stage_record["n_ambiguous_internal_faces"] == 184
        assert _provenance_satisfies_current_audit(pre_cvt) is False
        assert pre_cvt["audit_call_index"] == 0
        assert pre_cvt["n_same_side_internal_faces"] == 108
        assert pre_cvt["n_missing_source_vertices"] == 636
        assert pre_cvt["n_missing_source_faces"] == 1280
        assert payload["earliest_observed_failed_stage"] is None
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
                            for key, value in record.items()
                            if key != "repeat"
                        )
                    ),
                )
                for stage in (*payload["delaunay_stage_records"], *payload["inline_stage_records"])
                if isinstance(stage, dict)
                and isinstance(record := stage.get("record"), dict)
            ),
            tuple(
                sorted(
                    (key, value)
                    for key, value in pre_cvt.items()
                    if key != "repeat"
                )
            ),
        )
        for payload in payloads
        if isinstance(initial := payload["base_delaunay_record"], dict)
        and isinstance(pre_cvt := payload["first_pre_cvt_record"], dict)
    )
    assert len(signatures) == 3
    assert signatures == (signatures[0], signatures[0], signatures[0])


def _main() -> None:
    if len(sys.argv) != 5 or sys.argv[1] != "--worker":
        raise SystemExit(
            "usage: test_native_tet_sphere_provenance_rootcause_l1.py "
            "--worker repeat case evidence"
        )
    repeat_text, case_text, evidence_text = sys.argv[2:]
    payload = _worker_payload(int(repeat_text), Path(case_text))
    Path(evidence_text).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    _main()
