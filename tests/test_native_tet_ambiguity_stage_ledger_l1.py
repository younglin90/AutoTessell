"""L1 report-only ambiguity records at existing native-tet stage hooks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.generator.native_tet.ambiguity_stage_ledger_l1 import (
    array_sha256,
    capture_after_stage,
)

_ROOT = Path(__file__).resolve().parents[1]
_CUBE = _ROOT / "tests" / "benchmarks" / "cube.stl"
_SPHERE = _ROOT / "tests" / "benchmarks" / "sphere.stl"
_L1_TIMEOUT_SECONDS = 480


def _shared_face_points(second_apex_z: float) -> np.ndarray:
    return np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.25, 0.25, second_apex_z),
        ),
        dtype=np.float64,
    )


def _synthetic_record(second_apex_z: float) -> dict[str, object]:
    points = _shared_face_points(second_apex_z)
    before = array_sha256(points)
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)
    record = capture_after_stage(
        fixture="synthetic",
        repeat=0,
        stage_index=0,
        stage="synthetic",
        points=points,
        tets=tets,
    )
    assert array_sha256(points) == before
    assert record.partition_conserved
    return record.as_json()


@pytest.mark.parametrize(
    ("apex_z", "expected_distribution"),
    (
        (-1.0, (0, 0, 0)),
        (-1.0e-15, (0, 0, 1)),
        (1.0e-15, (0, 1, 0)),
        (0.0, (1, 0, 0)),
    ),
)
def test_l0_ambiguity_stage_record_preserves_existing_classes(
    apex_z: float, expected_distribution: tuple[int, int, int]
) -> None:
    record = _synthetic_record(apex_z)
    distribution = (
        record["n_predicate_zero_internal_faces"],
        record["n_floor_only_same_side_internal_faces"],
        record["n_floor_only_opposite_side_internal_faces"],
    )
    assert distribution == expected_distribution
    assert record["n_ambiguous_internal_faces"] == sum(distribution)
    if sum(expected_distribution):
        assert record["audit_valid"] is False


def _worker_payload(fixture_name: str, repeat: int, case_dir: Path) -> dict[str, object]:
    """Run exactly one generation in an isolated interpreter process."""
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
    import core.generator.native_tet.boundary_invariant as boundary_invariant
    from core.analyzer.readers import read_stl
    from core.generator.native_tet.ambiguity_stage_ledger_l1 import (
        capture_after_stage,
        with_result_context,
    )
    from core.generator.native_tet.mesher import generate_native_tet

    fixture = {"cube": _CUBE, "sphere": _SPHERE}[fixture_name]
    records: list[Any] = []
    original = boundary_invariant.check_boundary_invariant

    def traced(
        before_points: np.ndarray,
        before_tets: np.ndarray,
        after_points: np.ndarray,
        after_tets: np.ndarray,
        stage: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        records.append(
            capture_after_stage(
                fixture=fixture_name,
                repeat=repeat,
                stage_index=len(records),
                stage=str(stage),
                points=after_points,
                tets=after_tets,
            )
        )
        return original(
            before_points, before_tets, after_points, after_tets, stage, *args, **kwargs
        )

    # The observation is test-only.  The original hook executes with exactly
    # the original arguments after capture; no production function is edited.
    boundary_invariant.check_boundary_invariant = traced
    try:
        mesh = read_stl(fixture)
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
        result = generate_native_tet(
            np.asarray(mesh.vertices, dtype=np.float64),
            np.asarray(mesh.faces, dtype=np.int64),
            case_dir,
            **kwargs,
        )
    finally:
        boundary_invariant.check_boundary_invariant = original
    source_certificate = {
        "strict_source_component_bijection": result.debug_info.get(
            "strict_source_component_bijection", {}
        ),
        "strict_source_topology": result.debug_info.get("strict_source_topology", {}),
    }
    writer_exists = (case_dir / "constant" / "polyMesh").exists()
    enriched = [
        with_result_context(
            record,
            result_success=result.success,
            result_message=result.message,
            writer_artifact_exists=writer_exists,
            source_certificate=source_certificate,
        ).as_json()
        for record in records
    ]
    return {
        "fixture": fixture_name,
        "repeat": repeat,
        "result": {
            "success": result.success,
            "message": result.message,
            "n_points": result.n_points,
            "n_cells": result.n_cells,
            "points_sha256": array_sha256(result.tet_points),
            "tets_sha256": array_sha256(result.tets),
            "writer_artifact_exists": writer_exists,
            "source_certificate": source_certificate,
        },
        "records": enriched,
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
            f"L1 ambiguity-stage worker timed out after {_L1_TIMEOUT_SECONDS}s "
            f"for {fixture_name} repeat {repeat}; evidence is UNVERIFIED: {error}"
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture_name", ("cube", "sphere"))
def test_l1_stage_distribution_is_repeatable_and_report_only(
    fixture_name: str, tmp_path: Path
) -> None:
    """Primary metric: the stage-wise three-category ambiguity distribution."""
    runs = tuple(_run_worker(tmp_path, fixture_name, repeat) for repeat in range(3))
    first = runs[0]
    assert first["records"]
    for run in runs:
        result = run["result"]
        assert isinstance(result, dict)
        assert result["success"] is False
        assert result["writer_artifact_exists"] is False
        for record in run["records"]:
            assert record["partition_conserved"] is True
            assert record["writer_artifact_exists"] is False

    def signature(run: dict[str, object]) -> tuple[object, ...]:
        result = run["result"]
        assert isinstance(result, dict)
        records = run["records"]
        assert isinstance(records, list)
        return (
            result,
            tuple(
                (
                    record["stage_index"],
                    record["stage"],
                    record["points_sha256"],
                    record["tets_sha256"],
                    record["n_predicate_zero_internal_faces"],
                    record["n_floor_only_same_side_internal_faces"],
                    record["n_floor_only_opposite_side_internal_faces"],
                )
                for record in records
            ),
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
            "usage: test_native_tet_ambiguity_stage_ledger_l1.py "
            "--worker fixture repeat case evidence"
        )
    fixture_name, repeat_text, case_text, evidence_text = sys.argv[2:]
    payload = _worker_payload(fixture_name, int(repeat_text), Path(case_text))
    Path(evidence_text).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    _main()
