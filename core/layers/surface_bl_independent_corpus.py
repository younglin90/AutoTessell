"""Explicit corpus inventory for the independent surface-BL verifier."""

from __future__ import annotations

from pathlib import Path
from typing import Any


SOURCE_CASES = {
    "cube-stl": "tests/benchmarks/cube.stl",
    "sphere-stl": "tests/benchmarks/sphere_watertight.stl",
    "naca0012-stl": "tests/benchmarks/naca0012.stl",
    "ridge-cad": "tests/benchmarks/ridge.step",
    "narrow-gap-cad": "tests/benchmarks/narrow_gap.step",
    "t-junction-cad": "tests/benchmarks/t_junction.step",
    "complex-duct-stl": "tests/benchmarks/complex_duct.stl",
    "complex-xde-step": "tests/benchmarks/complex_duct.xde.step",
}
CONFIGURATIONS = (
    [{"layers": 0, "growth": 1.0, "h0_lref": None}]
    + [
        {"layers": layers, "growth": growth, "h0_lref": h0_lref}
        for layers in (1, 3, 8)
        for growth in (1.0, 1.2, 1.5)
        for h0_lref in (0.0025, 0.01)
    ]
)


def build_corpus_matrix(root: str | Path) -> dict[str, Any]:
    """Return the full 8x19 inventory without pretending missing rows passed."""
    root_path = Path(root)
    rows: list[dict[str, Any]] = []
    for source_case, relative in SOURCE_CASES.items():
        source_path = root_path / relative
        for config in CONFIGURATIONS:
            rows.append({
                "source_case": source_case,
                "source_path": str(relative),
                "source_present": source_path.exists(),
                "authoritative_mapping_present": False,
                "configuration": dict(config),
                "fresh_process_replays": 3,
                "verdict": "UNVERIFIED",
                "reason": "missing_authoritative_source_mapping",
            })
    return {
        "schema": "NativeSurfaceBLIndependentCorpus",
        "source_count": len(SOURCE_CASES),
        "configuration_count": len(CONFIGURATIONS),
        "row_count": len(rows),
        "planned_verifier_invocations": sum(row["fresh_process_replays"] for row in rows),
        "rows": rows,
        "route": "default_off",
    }


def classify_verifier_row(*, authoritative_source: bool, artifact_present: bool, replay_identical: bool, gate_passed: bool) -> str:
    """Return the only allowed release-review states for one row."""
    if not authoritative_source or not artifact_present:
        return "UNVERIFIED"
    if not replay_identical or not gate_passed:
        return "REFUSED"
    return "PASS_FOR_REVIEW"
