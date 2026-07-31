"""Test-only whole post-processing bypass comparison for native tet sphere."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_SPHERE = _ROOT / "tests" / "benchmarks" / "sphere.stl"
_MESHER = _ROOT / "core" / "generator" / "native_tet" / "mesher.py"


def _source_passes(record: dict[str, object]) -> bool:
    return bool(
        record["component_bijective"]
        and record["source_faces_preserved"]
        and record["n_unowned_candidate_faces"] == 0
    )


def _worker(repeat: int, mode: str, case_dir: Path) -> dict[str, object]:
    from core.analyzer.readers import read_stl
    from core.generator.native_tet.initial_overlap_source_l1 import (
        capture_initial_strict_overlap_source_l1,
    )
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_tet.quality import snapshot, snapshot_to_dict
    from core.generator.native_tet.rescue_gate import audit_tet_boundary

    mesh = read_stl(_SPHERE)
    points = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    records: list[dict[str, object]] = []

    def observe(checkpoint: Any) -> None:
        record = capture_initial_strict_overlap_source_l1(
            fixture="sphere",
            repeat=repeat,
            audit_call_index=len(records),
            source_points=checkpoint.source_points,
            source_faces=checkpoint.source_faces,
            candidate_points=checkpoint.candidate_points,
            candidate_tets=checkpoint.candidate_tets,
        ).as_json()
        records.append(
            {
                "stage": checkpoint.stage,
                "source_passes": _source_passes(record),
                "n_missing_source_vertices": record["n_missing_source_vertices"],
                "n_missing_source_faces": record["n_missing_source_faces"],
                "n_unowned_candidate_faces": record["n_unowned_candidate_faces"],
            }
        )

    if mode == "p3_skipped":
        # Existing fail-closed seam: Phase-A quality forces the documented
        # Phase-B/C plus NNN/RRR/SSS/VVV post-processing skip before P4-C.
        os.environ["AUTO_TESSELL_PHASE_BC_SKIP"] = "1"
        os.environ["AUTO_TESSELL_PHASE_BC_SKIP_MQ"] = "1.0"
        os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "1"
    elif mode == "current":
        os.environ["AUTO_TESSELL_PHASE_BC_SKIP"] = "0"
        os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "1"
    else:
        raise ValueError(f"unknown mode: {mode}")

    result = generate_native_tet(
        points,
        faces,
        case_dir,
        target_cells=2000,
        enable_bsp_insertion=False,
        enable_edge_recovery=False,
        enable_phase_b=False,
        enable_phase_c=False,
        _phase_a_observer=observe,
    )
    validity = audit_tet_boundary(result.tet_points, result.tets)
    return {
        "mode": mode,
        "stages": records,
        "first_source_failure": next(
            (item["stage"] for item in records if not item["source_passes"]), None
        ),
        "validity": {
            "valid": bool(validity.valid),
            "n_inverted_tets": int(validity.n_inverted_tets),
            "n_degenerate_tets": int(validity.n_degenerate_tets),
            "n_same_side_internal_faces": int(validity.n_same_side_internal_faces),
        },
        "quality": snapshot_to_dict(snapshot(result.tet_points, result.tets)),
        "result": {
            "success": result.success,
            "n_cells": result.n_cells,
            "n_points": result.n_points,
            "writer": (case_dir / "constant" / "polyMesh").exists(),
            "points_hash": hashlib.sha256(
                np.ascontiguousarray(result.tet_points)
            ).hexdigest(),
            "tets_hash": hashlib.sha256(np.ascontiguousarray(result.tets)).hexdigest(),
        },
    }


def _run(tmp_path: Path, mode: str, repeat: int) -> dict[str, object]:
    evidence = tmp_path / f"{mode}_{repeat}.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        mode,
        str(repeat),
        str(tmp_path / f"{mode}_{repeat}"),
        str(evidence),
    ]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(_ROOT) + (
        ":" + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    completed = subprocess.run(
        command,
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=480,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


def _signature(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True)


def _diagnostic_sphere_whole_p3_bypass_feasibility(tmp_path: Path) -> None:
    """Run only where P4-C fallback has enough wall-time budget."""
    current = tuple(_run(tmp_path, "current", repeat) for repeat in range(3))
    skipped = tuple(_run(tmp_path, "p3_skipped", repeat) for repeat in range(3))

    assert _signature(current[0]) == _signature(current[1]) == _signature(current[2])
    assert _signature(skipped[0]) == _signature(skipped[1]) == _signature(skipped[2])
    assert current[0]["result"]["success"] is False
    assert skipped[0]["result"]["success"] is False
    assert current[0]["result"]["writer"] is False
    assert skipped[0]["result"]["writer"] is False


def test_whole_p3_bypass_uses_existing_phase_bc_skip_seam() -> None:
    source = _MESHER.read_text(encoding="utf-8")

    assert 'os.environ.get("AUTO_TESSELL_PHASE_BC_SKIP", "1") != "0"' in source
    assert 'os.environ.get("AUTO_TESSELL_PHASE_BC_SKIP_MQ", "0.18")' in source
    assert "Phase B/C 와 함께 후속 heavy 패스" in source


if __name__ == "__main__":
    _, mode, repeat, case, evidence = sys.argv[1:]
    Path(evidence).write_text(
        json.dumps(_worker(int(repeat), mode, Path(case)), sort_keys=True),
        encoding="utf-8",
    )
