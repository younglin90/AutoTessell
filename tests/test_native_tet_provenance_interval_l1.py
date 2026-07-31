"""L1 localization of sphere source-provenance loss with report-only checkpoints."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_SPHERE = _ROOT / "tests" / "benchmarks" / "sphere.stl"
_STAGES = (
    "post_filter_compaction",
    "post_bsp_orient_fix",
    "post_phase_a_smoothing",
    "post_phase_a_fix_inverted",
    "post_smooth_then_drop_slivers",
    "post_drop_extreme_slivers",
    "post_degenerate_removal",
    "post_prewrite_locked_smooth",
    "post_fsl3_flip",
    "post_best_of",
    "post_nn1_collapse",
    "pre_rr1_flip",
    "post_rr1_flip",
    "pre_ddd1_bsp",
    "post_eee_quality",
    "post_nnn1_dry_run",
    "post_nnn2_insert",
    "post_nnn3_insert",
    "post_nnn4_amips",
    "post_rrr2_targeted_amips",
    "post_sss_revival",
    "pre_cvt3d",
)


def _passes(record: dict[str, object]) -> bool:
    return bool(
        record["component_bijective"]
        and record["source_faces_preserved"]
        and record["n_unowned_candidate_faces"] == 0
    )


def _worker(repeat: int, case_dir: Path) -> dict[str, object]:
    from core.analyzer.readers import read_stl
    from core.generator.native_tet.initial_overlap_source_l1 import (
        capture_initial_strict_overlap_source_l1,
    )
    from core.generator.native_tet.mesher import generate_native_tet

    mesh = read_stl(_SPHERE)
    points = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    records: list[dict[str, object]] = []
    immutable = True

    def observe(checkpoint: Any) -> None:
        nonlocal immutable
        arrays = (
            checkpoint.source_points,
            checkpoint.source_faces,
            checkpoint.candidate_points,
            checkpoint.candidate_tets,
        )
        immutable &= all(
            values.flags.c_contiguous and not values.flags.writeable for values in arrays
        )
        for values in arrays:
            try:
                values.setflags(write=True)
            except ValueError:
                continue
            immutable = False
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
    first_failed = next((item["stage"] for item in records if not _passes(item["record"])), None)
    return {
        "records": records,
        "immutable": immutable,
        "first_failed": first_failed,
        "result": {
            "success": result.success,
            "n_cells": result.n_cells,
            "writer": (case_dir / "constant" / "polyMesh").exists(),
        },
    }


def _run(tmp_path: Path, repeat: int) -> dict[str, object]:
    evidence = tmp_path / f"sphere_{repeat}.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        str(repeat),
        str(tmp_path / f"sphere_{repeat}"),
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


def test_sphere_provenance_interval_l1(tmp_path: Path) -> None:
    payloads = tuple(_run(tmp_path, repeat) for repeat in range(3))
    for payload in payloads:
        records = payload["records"]
        assert payload["immutable"] is True
        assert payload["result"]["success"] is False
        assert payload["result"]["writer"] is False
        assert tuple(item["stage"] for item in records) == _STAGES
        assert payload["first_failed"] == "post_sss_revival"
        for item in records[:-2]:
            assert _passes(item["record"]) is True
        failed = records[-2]["record"]
        assert _passes(failed) is False
        assert failed["n_missing_source_vertices"] == 636
        assert failed["n_missing_source_faces"] == 1280
    signatures = tuple(
        (
            payload["first_failed"],
            payload["immutable"],
            payload["result"],
            tuple(
                (
                    item["stage"],
                    tuple(
                        sorted(
                            (key, value) for key, value in item["record"].items() if key != "repeat"
                        )
                    ),
                )
                for item in payload["records"]
            ),
        )
        for payload in payloads
    )
    assert signatures == (signatures[0], signatures[0], signatures[0])


if __name__ == "__main__":
    _, repeat, case, evidence = sys.argv[1:]
    Path(evidence).write_text(
        json.dumps(_worker(int(repeat), Path(case)), sort_keys=True), encoding="utf-8"
    )
