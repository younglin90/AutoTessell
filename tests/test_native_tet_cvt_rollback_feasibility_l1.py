"""L1 CVT pre/post feasibility evidence without changing native-Tet policy."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from core.generator.native_tet.cvt_rollback_feasibility_l1 import (
    capture_cvt_rollback_feasibility_l1,
)

_ROOT = Path(__file__).resolve().parents[1]
_CUBE = _ROOT / "tests" / "benchmarks" / "cube.stl"
_SPHERE = _ROOT / "tests" / "benchmarks" / "sphere.stl"
_L1_TIMEOUT_SECONDS = 480


def _two_tet_surface(second_apex_z: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.25, 0.25, second_apex_z),
        ),
        dtype=np.float64,
    )
    source_faces = np.asarray(
        ((0, 1, 3), (0, 3, 2), (1, 2, 3), (0, 2, 4), (0, 4, 1), (2, 1, 4)),
        dtype=np.int64,
    )
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)
    return points, source_faces, tets


def test_l0_source_preserving_pre_cvt_candidate_is_not_a_candidate_policy() -> None:
    source_points, source_faces, tets = _two_tet_surface(-1.0)
    unsafe_points, _unused_faces, _unused_tets = _two_tet_surface(0.5)
    record = capture_cvt_rollback_feasibility_l1(
        fixture="two_tet",
        repeat=0,
        cvt_call_index=0,
        source_points=source_points,
        source_faces=source_faces,
        pre_points=source_points,
        pre_tets=tets,
        candidate_points=unsafe_points,
        candidate_tets=tets,
    )
    assert record.pre_same_side_internal_faces == 0
    assert record.candidate_same_side_internal_faces == 1
    assert record.pre_source_faces_preserved is True
    assert record.candidate_source_faces_preserved is False
    assert record.pre_strict_writer_eligible is True
    assert record.candidate_strict_writer_eligible is False
    assert record.source_preserving_pre_cvt_candidate_exists is True


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
    from core.generator.native_tet.cvt_rollback_feasibility_l1 import (
        capture_cvt_rollback_feasibility_l1,
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
        pre_points = points.copy(order="C")
        pre_tets = tets.copy(order="C")
        candidate_points, cvt_result = original_cvt(points, tets, *args, **kwargs)
        records.append(
            capture_cvt_rollback_feasibility_l1(
                fixture=fixture_name,
                repeat=repeat,
                cvt_call_index=len(records),
                source_points=source_points,
                source_faces=source_faces,
                pre_points=pre_points,
                pre_tets=pre_tets,
                candidate_points=np.ascontiguousarray(candidate_points),
                candidate_tets=np.ascontiguousarray(tets),
            ).as_json()
        )
        return candidate_points, cvt_result

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
        "cvt_records": records,
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
            f"CVT rollback feasibility worker timed out after {_L1_TIMEOUT_SECONDS}s "
            f"for {fixture_name} repeat {repeat}; evidence is UNVERIFIED: {error}"
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture_name", ("cube", "sphere"))
def test_l1_cvt_pre_post_feasibility_is_deterministic_and_refuses_output(
    fixture_name: str, tmp_path: Path
) -> None:
    payloads = tuple(_run_worker(tmp_path, fixture_name, repeat) for repeat in range(3))
    for payload in payloads:
        result = payload["result"]
        records = payload["cvt_records"]
        assert isinstance(result, dict) and isinstance(records, list)
        assert result["success"] is False
        assert result["writer_artifact_exists"] is False
        assert records
        assert all(
            isinstance(record, dict)
            and record["candidate_strict_writer_eligible"] is False
            for record in records
        )
        assert all(
            isinstance(record, dict)
            and record["source_preserving_pre_cvt_candidate_exists"] is False
            for record in records
        )
    deterministic_payloads = tuple(
        (
            payload["fixture"],
            payload["result"],
            tuple(
                tuple(
                    sorted(
                        (key, value)
                        for key, value in record.items()
                        if key != "repeat"
                    )
                )
                for record in payload["cvt_records"]
                if isinstance(record, dict)
            ),
        )
        for payload in payloads
    )
    assert deterministic_payloads == (
        deterministic_payloads[0],
        deterministic_payloads[0],
        deterministic_payloads[0],
    )


def _main() -> None:
    if len(sys.argv) != 6 or sys.argv[1] != "--worker":
        raise SystemExit(
            "usage: test_native_tet_cvt_rollback_feasibility_l1.py "
            "--worker fixture repeat case evidence"
        )
    fixture_name, repeat_text, case_text, evidence_text = sys.argv[2:]
    payload = _worker_payload(fixture_name, int(repeat_text), Path(case_text))
    Path(evidence_text).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    _main()
