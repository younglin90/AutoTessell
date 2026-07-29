"""Validate one native mesh case against CFD and topology gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.evaluator.native_checker import NativeMeshChecker
from core.utils.polymesh_reader import parse_foam_faces

DEFAULT_GATE = {
    "max_non_orthogonality": 70.0,
    "max_skewness": 4.0,
    "max_aspect_ratio": 200.0,
    "negative_volumes": 0,
    "severe_non_orthogonal_faces": 0,
    "non_manifold_faces": 0,
}


def _canonical_face(face: list[int]) -> tuple[int, ...]:
    """Return orientation-independent cyclic face key."""
    if not face:
        return ()
    rotations = [tuple(face[index:] + face[:index]) for index in range(len(face))]
    reverse = list(reversed(face))
    rotations.extend(tuple(reverse[index:] + reverse[:index]) for index in range(len(reverse)))
    return min(rotations)


def _non_manifold_face_count(case_dir: Path) -> int:
    """Count duplicate geometric faces emitted by a polyMesh writer."""
    faces = parse_foam_faces(case_dir / "constant" / "polyMesh" / "faces")
    seen: set[tuple[int, ...]] = set()
    duplicates = 0
    for raw_face in faces:
        face = [int(vertex) for vertex in raw_face]
        if len(set(face)) < 3:
            duplicates += 1
            continue
        key = _canonical_face(face)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


def validate_case(case_dir: Path, gate: dict[str, float | int]) -> dict[str, Any]:
    """Measure a case and return deterministic pass/fail evidence."""
    result = NativeMeshChecker().run(case_dir)
    metrics = {
        "cells": int(result.cells),
        "points": int(result.points),
        "mesh_ok": bool(result.mesh_ok),
        "negative_volumes": int(result.negative_volumes),
        "max_non_orthogonality": float(result.max_non_orthogonality),
        "max_skewness": float(result.max_skewness),
        "max_aspect_ratio": float(result.max_aspect_ratio),
        "severe_non_orthogonal_faces": int(result.severely_non_orthogonal_faces),
        "non_manifold_faces": _non_manifold_face_count(case_dir),
    }
    checks = {
        "mesh_ok": metrics["mesh_ok"],
        "negative_volumes": metrics["negative_volumes"] <= gate["negative_volumes"],
        "max_non_orthogonality": metrics["max_non_orthogonality"] <= gate["max_non_orthogonality"],
        "max_skewness": metrics["max_skewness"] <= gate["max_skewness"],
        "max_aspect_ratio": metrics["max_aspect_ratio"] <= gate["max_aspect_ratio"],
        "severe_non_orthogonal_faces": (
            metrics["severe_non_orthogonal_faces"]
            <= gate["severe_non_orthogonal_faces"]
        ),
        "non_manifold_faces": metrics["non_manifold_faces"] <= gate["non_manifold_faces"],
    }
    return {"case": str(case_dir), "gate": gate, "metrics": metrics, "checks": checks,
            "passed": all(checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--gate", type=Path, help="JSON object overriding default gate")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    gate: dict[str, float | int] = dict(DEFAULT_GATE)
    if args.gate:
        loaded_gate = json.loads(args.gate.read_text(encoding="utf-8"))
        if "quality_gate" in loaded_gate:
            loaded_gate = loaded_gate["quality_gate"]
        gate.update(loaded_gate)
    report = validate_case(args.case_dir, gate)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
