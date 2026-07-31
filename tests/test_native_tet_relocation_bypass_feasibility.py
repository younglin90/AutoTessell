"""Diagnostic-only comparison of current SSS pass-0 relocation and bypass."""

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


def _source_passes(record: dict[str, object]) -> bool:
    return bool(
        record["component_bijective"]
        and record["source_faces_preserved"]
        and record["n_unowned_candidate_faces"] == 0
    )


def _worker(repeat: int, mode: str, case_dir: Path) -> dict[str, object]:
    from core.analyzer.readers import read_stl
    from core.generator.native_tet import envelope_relocate
    from core.generator.native_tet.initial_overlap_source_l1 import (
        capture_initial_strict_overlap_source_l1,
    )
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_tet.quality import snapshot as quality_snapshot
    from core.generator.native_tet.quality import snapshot_to_dict
    from core.generator.native_tet.rescue_gate import audit_tet_boundary

    mesh = read_stl(_SPHERE)
    points = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    pass0: dict[str, object] | None = None
    pass0_tets: np.ndarray | None = None
    relocation_calls = 0

    def observe(checkpoint: Any) -> None:
        nonlocal pass0_tets
        if checkpoint.stage == "post_rrr2_targeted_amips":
            pass0_tets = checkpoint.candidate_tets.copy()

    original = envelope_relocate._envelope_bounded_relocate

    def _pass0_summary(
        before: np.ndarray,
        after: np.ndarray,
        tets: np.ndarray,
    ) -> dict[str, object]:
        displacement = np.linalg.norm(after - before, axis=1)
        before_source = capture_initial_strict_overlap_source_l1(
            fixture="sphere",
            repeat=repeat,
            audit_call_index=0,
            source_points=points,
            source_faces=faces,
            candidate_points=before,
            candidate_tets=tets,
        ).as_json()
        after_source = capture_initial_strict_overlap_source_l1(
            fixture="sphere",
            repeat=repeat,
            audit_call_index=1,
            source_points=points,
            source_faces=faces,
            candidate_points=after,
            candidate_tets=tets,
        ).as_json()
        before_validity = audit_tet_boundary(before, tets)
        after_validity = audit_tet_boundary(after, tets)
        return {
            "delta": {
                "moved_vertices": int((displacement > 0.0).sum()),
                "max_displacement": float(displacement.max()),
            },
            "source_before": {
                "passes": _source_passes(before_source),
                "n_missing_source_vertices": before_source["n_missing_source_vertices"],
                "n_missing_source_faces": before_source["n_missing_source_faces"],
                "n_unowned_candidate_faces": before_source["n_unowned_candidate_faces"],
            },
            "source_after": {
                "passes": _source_passes(after_source),
                "n_missing_source_vertices": after_source["n_missing_source_vertices"],
                "n_missing_source_faces": after_source["n_missing_source_faces"],
                "n_unowned_candidate_faces": after_source["n_unowned_candidate_faces"],
            },
            "validity_before": {
                "valid": bool(before_validity.valid),
                "n_inverted_tets": int(before_validity.n_inverted_tets),
                "n_degenerate_tets": int(before_validity.n_degenerate_tets),
                "n_same_side_internal_faces": int(before_validity.n_same_side_internal_faces),
            },
            "validity_after": {
                "valid": bool(after_validity.valid),
                "n_inverted_tets": int(after_validity.n_inverted_tets),
                "n_degenerate_tets": int(after_validity.n_degenerate_tets),
                "n_same_side_internal_faces": int(after_validity.n_same_side_internal_faces),
            },
            "quality_before": snapshot_to_dict(quality_snapshot(before, tets)),
            "quality_after": snapshot_to_dict(quality_snapshot(after, tets)),
        }

    def instrument_pass0(
        candidate_points: np.ndarray,
        surface_idx: np.ndarray,
        target_points: np.ndarray,
        normals: np.ndarray,
        envelope: Any,
    ) -> np.ndarray:
        nonlocal pass0, relocation_calls
        relocation_calls += 1
        if relocation_calls == 1:
            assert pass0_tets is not None
            relocated = (
                candidate_points.copy()
                if mode == "bypass"
                else original(
                    candidate_points,
                    surface_idx,
                    target_points,
                    normals,
                    envelope,
                )
            )
            pass0 = _pass0_summary(candidate_points, relocated, pass0_tets)
            return relocated
        return original(
            candidate_points,
            surface_idx,
            target_points,
            normals,
            envelope,
        )

    if mode not in ("bypass", "current"):
        raise ValueError(f"unknown mode: {mode}")
    envelope_relocate._envelope_bounded_relocate = instrument_pass0
    try:
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
    finally:
        envelope_relocate._envelope_bounded_relocate = original

    assert pass0 is not None
    validity = audit_tet_boundary(result.tet_points, result.tets)
    return {
        "mode": mode,
        "pass0": pass0,
        "relocation_calls": relocation_calls,
        "validity": {
            "valid": bool(validity.valid),
            "n_inverted_tets": int(validity.n_inverted_tets),
            "n_degenerate_tets": int(validity.n_degenerate_tets),
            "n_same_side_internal_faces": int(validity.n_same_side_internal_faces),
        },
        "quality": snapshot_to_dict(quality_snapshot(result.tet_points, result.tets)),
        "result": {
            "success": result.success,
            "n_cells": result.n_cells,
            "n_points": result.n_points,
            "writer": (case_dir / "constant" / "polyMesh").exists(),
            "points_hash": hashlib.sha256(np.ascontiguousarray(result.tet_points)).hexdigest(),
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
    stable = {key: value for key, value in payload.items() if key != "mode"}
    return json.dumps(stable, sort_keys=True)


def test_sphere_pass0_relocation_bypass_feasibility(tmp_path: Path) -> None:
    current = tuple(_run(tmp_path, "current", repeat) for repeat in range(3))
    bypass = tuple(_run(tmp_path, "bypass", repeat) for repeat in range(3))

    assert _signature(current[0]) == _signature(current[1]) == _signature(current[2])
    assert _signature(bypass[0]) == _signature(bypass[1]) == _signature(bypass[2])
    assert current[0]["pass0"]["delta"]["moved_vertices"] > 0
    assert current[0]["pass0"]["delta"]["max_displacement"] > 0.0
    assert bypass[0]["pass0"]["delta"] == {
        "moved_vertices": 0,
        "max_displacement": 0.0,
    }
    assert bypass[0]["relocation_calls"] == 1
    assert current[0]["pass0"]["source_before"]["passes"] is True
    assert current[0]["pass0"]["source_after"] == {
        "passes": False,
        "n_missing_source_vertices": 636,
        "n_missing_source_faces": 1280,
        "n_unowned_candidate_faces": 1280,
    }
    assert bypass[0]["pass0"]["source_before"]["passes"] is True
    assert bypass[0]["pass0"]["source_after"] == {
        "passes": True,
        "n_missing_source_vertices": 0,
        "n_missing_source_faces": 0,
        "n_unowned_candidate_faces": 0,
    }
    assert current[0]["result"]["success"] is False
    assert bypass[0]["result"]["success"] is False
    assert current[0]["result"]["writer"] is False
    assert bypass[0]["result"]["writer"] is False


if __name__ == "__main__":
    _, mode, repeat, case, evidence = sys.argv[1:]
    Path(evidence).write_text(
        json.dumps(_worker(int(repeat), mode, Path(case)), sort_keys=True),
        encoding="utf-8",
    )
