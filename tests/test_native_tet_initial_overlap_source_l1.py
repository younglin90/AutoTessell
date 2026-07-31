"""L0/L1 report-only root-cause evidence for first native-tet strict overlap."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.generator.native_tet.initial_overlap_source_l1 import (
    array_sha256,
    capture_initial_strict_overlap_source_l1,
    first_strict_overlap_source,
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
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)
    source_faces = np.asarray(
        ((0, 1, 3), (0, 3, 2), (1, 2, 3), (0, 2, 4), (0, 4, 1), (2, 1, 4)),
        dtype=np.int64,
    )
    return points, source_faces, tets


def test_l0_same_side_overlap_is_classified_without_source_or_candidate_mutation() -> None:
    points, source_faces, tets = _two_tet_surface(1.0)
    before = tuple(array_sha256(values) for values in (points, source_faces, tets))
    record = capture_initial_strict_overlap_source_l1(
        fixture="two_tet_same_side",
        repeat=0,
        audit_call_index=0,
        source_points=points,
        source_faces=source_faces,
        candidate_points=points,
        candidate_tets=tets,
    )

    assert record.n_same_side_internal_faces == 1
    assert record.n_ambiguous_internal_faces == 0
    assert record.source_faces_preserved
    assert record.overlap_source_class == "same_side_overlap_source_provenance_preserved"
    assert first_strict_overlap_source((record,)) == record
    assert tuple(array_sha256(values) for values in (points, source_faces, tets)) == before


def test_l0_opposite_side_has_no_strict_overlap_source() -> None:
    points, source_faces, tets = _two_tet_surface(-1.0)
    record = capture_initial_strict_overlap_source_l1(
        fixture="two_tet_opposite_side",
        repeat=0,
        audit_call_index=0,
        source_points=points,
        source_faces=source_faces,
        candidate_points=points,
        candidate_tets=tets,
    )

    assert record.n_same_side_internal_faces == 0
    assert record.overlap_source_class == "no_strict_overlap"
    assert first_strict_overlap_source((record,)) is None


def _worker_payload(fixture_name: str, repeat: int, case_dir: Path) -> dict[str, object]:
    """Run one unchanged generator call while observing strict-audit inputs."""
    if fixture_name == "cube":
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

    import core.generator.native_tet.rescue_gate as rescue_gate
    from core.analyzer.readers import read_stl
    from core.generator.native_tet.initial_overlap_source_l1 import (
        capture_initial_strict_overlap_source_l1,
        first_strict_overlap_source,
    )
    from core.generator.native_tet.mesher import generate_native_tet

    fixture = {"cube": _CUBE, "sphere": _SPHERE}[fixture_name]
    mesh = read_stl(fixture)
    source_points = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    source_faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    records: list[Any] = []
    original = rescue_gate.audit_internal_face_sidedness
    call_index = 0
    first_seen = False

    def traced(
        points: np.ndarray,
        tets: np.ndarray,
        *args: object,
        **kwargs: object,
    ) -> object:
        nonlocal call_index, first_seen
        observed = original(points, tets, *args, **kwargs)
        if not first_seen:
            record = capture_initial_strict_overlap_source_l1(
                fixture=fixture_name,
                repeat=repeat,
                audit_call_index=call_index,
                source_points=source_points,
                source_faces=source_faces,
                candidate_points=points,
                candidate_tets=tets,
                sidedness=observed,
            )
            records.append(record)
            first_seen = record.n_same_side_internal_faces > 0
        call_index += 1
        return observed

    rescue_gate.audit_internal_face_sidedness = traced
    try:
        kwargs: dict[str, object] = {
            "target_cells": 10000 if fixture_name == "cube" else 2000,
        }
        if fixture_name == "sphere":
            kwargs.update(
                enable_bsp_insertion=False,
                enable_edge_recovery=False,
                enable_phase_b=False,
                enable_phase_c=False,
            )
        result = generate_native_tet(source_points, source_faces, case_dir, **kwargs)
    finally:
        rescue_gate.audit_internal_face_sidedness = original

    first = first_strict_overlap_source(tuple(records))
    writer_exists = (case_dir / "constant" / "polyMesh").exists()
    return {
        "fixture": fixture_name,
        "repeat": repeat,
        "result": {
            "success": result.success,
            "message": result.message,
            "n_cells": result.n_cells,
            "writer_artifact_exists": writer_exists,
            "points_sha256": array_sha256(result.tet_points),
            "tets_sha256": array_sha256(result.tets),
        },
        "records": [record.as_json() for record in records],
        "first_strict_overlap": first.as_json() if first is not None else None,
        "strict_audit_call_count": call_index,
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
    previous_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        str(_ROOT) if not previous_pythonpath else f"{_ROOT}:{previous_pythonpath}"
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
            f"L1 initial-overlap worker timed out after {_L1_TIMEOUT_SECONDS}s "
            f"for {fixture_name} repeat {repeat}; evidence is UNVERIFIED: {error}"
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture_name", ("cube", "sphere"))
def test_l1_first_strict_overlap_source_is_deterministic_and_report_only(
    fixture_name: str, tmp_path: Path
) -> None:
    runs = tuple(_run_worker(tmp_path, fixture_name, repeat) for repeat in range(3))
    first = runs[0]
    assert first["records"]
    for run in runs:
        result = run["result"]
        assert isinstance(result, dict)
        assert result["success"] is False
        assert result["writer_artifact_exists"] is False
        assert isinstance(run["strict_audit_call_count"], int)
        assert run["strict_audit_call_count"] >= len(run["records"])

    def signature(run: dict[str, object]) -> tuple[object, ...]:
        records = run["records"]
        assert isinstance(records, list)

        def without_repeat(record: object) -> tuple[tuple[str, object], ...]:
            assert isinstance(record, dict)
            return tuple(sorted((key, value) for key, value in record.items() if key != "repeat"))

        return (
            run["result"],
            (
                without_repeat(run["first_strict_overlap"])
                if run["first_strict_overlap"] is not None
                else None
            ),
            run["strict_audit_call_count"],
            tuple(without_repeat(record) for record in records),
        )

    assert all(signature(run) == signature(first) for run in runs[1:])
    if fixture_name == "cube":
        result = first["result"]
        assert isinstance(result, dict)
        assert result["message"] == "native_tet CVT candidate increases strict internal-face debt"
        assert result["n_cells"] == 5913


def _main() -> None:
    if len(sys.argv) != 6 or sys.argv[1] != "--worker":
        raise SystemExit(
            "usage: test_native_tet_initial_overlap_source_l1.py "
            "--worker fixture repeat case evidence"
        )
    fixture_name, repeat_text, case_text, evidence_text = sys.argv[2:]
    payload = _worker_payload(fixture_name, int(repeat_text), Path(case_text))
    Path(evidence_text).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    _main()
