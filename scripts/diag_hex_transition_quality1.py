"""HEX-OCT-TRANSITION-QUALITY-1 real-shape report-only measurement.

The mixed-level realization and this quality census are both opt-in.  The
script captures the builder and generic-writer quality records without
changing the production default or applying any repair.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402
from core.utils.logging import configure_logging  # noqa: E402

_SHAPES = {
    "cylinder": REPO / "tests" / "benchmarks" / "cylinder.stl",
    "sphere": REPO / "tests" / "benchmarks" / "sphere.stl",
    "gear": REPO / "tests" / "stl" / "04_extreme_gear.stl",
    "bracket": REPO / "tests" / "stl" / "03_hard_bracket.stl",
}


def _run_one(name: str, stl_path: Path, max_cells: int, *, compact: bool) -> int:
    if not stl_path.exists():
        print(f"{name}: SKIP fixture_missing={stl_path}")
        return 0
    previous_quality = os.environ.get("AUTO_TESSELL_HEX_TRANSITION_QUALITY_DIAG")
    previous_mixed = os.environ.get("AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION")
    previous_candidate = os.environ.get("AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG")
    os.environ["AUTO_TESSELL_HEX_TRANSITION_QUALITY_DIAG"] = "1"
    os.environ["AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION"] = "1"
    # Report-only candidate snapshots are enabled here so the local wall-fit
    # deltas and the final checker gate come from the same mesh run.
    os.environ["AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG"] = "1"
    captured = io.StringIO()
    result = None
    try:
        with (
            tempfile.TemporaryDirectory() as tmp,
            contextlib.redirect_stdout(captured),
            contextlib.redirect_stderr(captured),
        ):
            configure_logging(verbose=False, json=False)
            case_dir = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                stl_path,
                case_dir,
                quality_level="fine",
                mesh_type="hex_dominant",
                tier_hint="native_hex",
                max_iterations=1,
                auto_retry="off",
                strict_tier=True,
                write_of_case=True,
                max_cells=max_cells,
                tier_specific_params={
                    "max_cells": max_cells,
                    "target_cells": max_cells,
                    "bl_layers": 0,
                },
            )
    finally:
        if previous_quality is None:
            os.environ.pop("AUTO_TESSELL_HEX_TRANSITION_QUALITY_DIAG", None)
        else:
            os.environ["AUTO_TESSELL_HEX_TRANSITION_QUALITY_DIAG"] = previous_quality
        if previous_mixed is None:
            os.environ.pop("AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION", None)
        else:
            os.environ["AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION"] = previous_mixed
        if previous_candidate is None:
            os.environ.pop("AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG", None)
        else:
            os.environ["AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG"] = previous_candidate

    lines = [
        line
        for line in captured.getvalue().splitlines()
        if "native_hex_transition_quality_" in line or "native_hex_wall_fit" in line
    ]
    print(f"\n===== {name} =====")
    print(f"pipeline_success={result.success} error={result.error}")
    report = getattr(result, "quality_report", None)
    summary = getattr(report, "evaluation_summary", None)
    checkmesh = getattr(summary, "checkmesh", None)
    fidelity = getattr(summary, "geometry_fidelity", None)
    if summary is None or checkmesh is None:
        print("final_gate_summary=UNAVAILABLE")
    else:
        print(
            "final_gate_summary="
            f"verdict:{summary.verdict} "
            f"cells:{checkmesh.cells} "
            f"max_skew:{checkmesh.max_skewness:.9g} "
            f"max_boundary_skew:{checkmesh.max_boundary_skewness!r} "
            f"negative_volumes:{checkmesh.negative_volumes} "
            f"min_volume:{checkmesh.min_cell_volume:.9g} "
            f"max_warpage:{checkmesh.max_face_warpage!r}"
        )
        if fidelity is None:
            print("final_surface_fidelity=UNAVAILABLE")
        else:
            print(
                "final_surface_fidelity="
                f"hausdorff:{fidelity.hausdorff_distance:.9g} "
                f"distance_rms:{fidelity.distance_rms!r} "
                f"distance_p95:{fidelity.distance_p95!r} "
                f"area_dev_percent:{fidelity.surface_area_deviation_percent:.9g}"
            )
    if compact:
        # Stock pipeline input carries no validated source-feature sidecar.
        # Candidate records therefore keep explicit UNAVAILABLE status rather
        # than inventing a default patch or feature label.
        print(
            "candidate_provenance=UNAVAILABLE "
            "(stock run has no validated authoritative source-feature sidecar)"
        )
        lines = [line for line in lines if "native_hex_wall_fit_candidate_quality_summary" in line]
    if not lines:
        print("status=NO_QUALITY_LOG")
        return 1
    for line in lines:
        print(line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cells", type=int, default=2000)
    parser.add_argument("--shapes", default="cylinder,sphere,gear,bracket")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print only the candidate Pareto summary and explicit provenance refusal.",
    )
    args = parser.parse_args()
    return sum(
        _run_one(name, _SHAPES[name], args.max_cells, compact=args.compact)
        for name in args.shapes.split(",")
        if name in _SHAPES
    )


if __name__ == "__main__":
    raise SystemExit(main())
