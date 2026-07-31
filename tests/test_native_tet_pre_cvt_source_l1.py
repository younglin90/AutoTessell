"""L1 evidence for strict same-side debt before the first native-Tet CVT call."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_CUBE = _ROOT / "tests" / "benchmarks" / "cube.stl"
_SPHERE = _ROOT / "tests" / "benchmarks" / "sphere.stl"
_L1_TIMEOUT_SECONDS = 480
_EXPECTED_PRE_CVT_STRICT_DEBT = {
    "cube": (0, 20, "strict_ambiguity_without_same_side_overlap"),
    "sphere": (108, 0, "same_side_overlap_source_provenance_debt"),
}


def _configure_cube() -> None:
    os.environ["AUTO_TESSELL_VVV2_QUEUE"] = "0"
    for name in (
        "AUTO_TESSELL_VVV5B_OFF",
        "AUTO_TESSELL_VVV6_OFF",
        "AUTO_TESSELL_VVV7_OFF",
        "AUTO_TESSELL_VVV8_OFF",
        "AUTO_TESSELL_VVV9_OFF",
        "AUTO_TESSELL_VVV10_OFF",
        "AUTO_TESSELL_VVV11_OFF",
        "AUTO_TESSELL_VVV12_OFF",
        "AUTO_TESSELL_VVV13_OFF",
        "AUTO_TESSELL_VVV14_OFF",
        "AUTO_TESSELL_TET_QUALITY1_OFF",
        "AUTO_TESSELL_STELLAR_KLINGNER",
    ):
        os.environ[name] = "1"
    os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"


def _worker_payload(fixture_name: str, repeat: int, case_dir: Path) -> dict[str, object]:
    if fixture_name == "cube":
        _configure_cube()

    import core.generator.native_tet.cvt3d as cvt3d
    from core.analyzer.readers import read_stl
    from core.generator.native_tet.initial_overlap_source_l1 import (
        capture_initial_strict_overlap_source_l1,
    )
    from core.generator.native_tet.mesher import generate_native_tet

    fixture = {"cube": _CUBE, "sphere": _SPHERE}[fixture_name]
    mesh = read_stl(fixture)
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
                    fixture=fixture_name,
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
        kwargs: dict[str, object] = {"target_cells": 2000}
        if fixture_name == "sphere":
            kwargs.update(
                enable_bsp_insertion=False,
                enable_edge_recovery=False,
                enable_phase_b=False,
                enable_phase_c=False,
            )
        result = generate_native_tet(source_points, source_faces, case_dir, **kwargs)
    finally:
        cvt3d.lloyd_cvt_3d = original_cvt

    return {
        "fixture": fixture_name,
        "repeat": repeat,
        "result": {
            "success": result.success,
            "message": result.message,
            "n_cells": result.n_cells,
            "writer_artifact_exists": (case_dir / "constant" / "polyMesh").exists(),
        },
        "first_pre_cvt_record": records[0] if records else None,
        "first_pre_cvt_call_observed": bool(records),
    }


def _run_worker(tmp_path: Path, fixture_name: str, repeat: int) -> dict[str, object]:
    evidence = tmp_path / f"{fixture_name}_{repeat}.json"
    case_dir = tmp_path / f"{fixture_name}_{repeat}"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        fixture_name,
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
            f"pre-CVT source worker timed out after {_L1_TIMEOUT_SECONDS}s "
            f"for {fixture_name} repeat {repeat}; evidence is UNVERIFIED: {error}"
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture_name", ("cube", "sphere"))
def test_l1_first_cvt_pre_state_is_deterministic_and_output_refusal_is_unchanged(
    fixture_name: str, tmp_path: Path
) -> None:
    payloads = tuple(_run_worker(tmp_path, fixture_name, repeat) for repeat in range(3))
    for payload in payloads:
        result = payload["result"]
        record = payload["first_pre_cvt_record"]
        assert isinstance(result, dict) and isinstance(record, dict)
        assert payload["first_pre_cvt_call_observed"] is True
        assert result["success"] is False
        assert result["writer_artifact_exists"] is False
        assert record["audit_call_index"] == 0
        assert isinstance(record["n_same_side_internal_faces"], int)
        assert isinstance(record["n_ambiguous_internal_faces"], int)
        expected_same_side, expected_ambiguity, expected_class = (
            _EXPECTED_PRE_CVT_STRICT_DEBT[fixture_name]
        )
        assert record["n_same_side_internal_faces"] == expected_same_side
        assert record["n_ambiguous_internal_faces"] == expected_ambiguity
        assert record["overlap_source_class"] == expected_class
    signatures = tuple(
        (
            payload["fixture"],
            payload["result"],
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
    assert len(signatures) == 3
    assert signatures == (signatures[0], signatures[0], signatures[0])


def _main() -> None:
    if len(sys.argv) != 6 or sys.argv[1] != "--worker":
        raise SystemExit(
            "usage: test_native_tet_pre_cvt_source_l1.py "
            "--worker fixture repeat case evidence"
        )
    fixture_name, repeat_text, case_text, evidence_text = sys.argv[2:]
    payload = _worker_payload(fixture_name, int(repeat_text), Path(case_text))
    Path(evidence_text).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    _main()
