"""HEX-TRANSITION-PROVENANCE-DIAG1 builder-to-writer audit.

The opt-in diagnostic collects deterministic builder-side grid-origin/level
labels and reports the exact boundary where ``write_generic_polymesh`` receives
only final connectivity.  It does not edit the generated mesh or enable any
repair path.

Usage:
    AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG=1 \
        python scripts/diag_hex_transition_provenance1.py --max-cells 8000
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
}


def _run_one(name: str, stl_path: Path, max_cells: int) -> int:
    if not stl_path.exists():
        print(f"{name}: SKIP fixture_missing={stl_path}")
        return 0
    previous = os.environ.get("AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG")
    os.environ["AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG"] = "1"
    captured = io.StringIO()
    try:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            # The project logger owns its stream handler at configuration time;
            # configure it inside the capture scope so only the two provenance
            # records are printed by this diagnostic.
            configure_logging(verbose=False, json=False)
            result = PipelineOrchestrator().run(
                stl_path,
                Path(tmp) / "case",
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
        if previous is None:
            os.environ.pop("AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG", None)
        else:
            os.environ["AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG"] = previous

    lines = [
        line
        for line in captured.getvalue().splitlines()
        if "native_hex_transition_provenance_" in line
    ]
    print(f"\n===== {name} =====")
    if not lines:
        print(f"status=NO_DIAGNOSTIC_LOG pipeline_success={result.success} error={result.error}")
        return 1
    for line in lines:
        print(line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cells", type=int, default=8000)
    parser.add_argument("--shapes", default="cylinder,sphere,gear")
    args = parser.parse_args()
    return sum(
        _run_one(name, _SHAPES[name], args.max_cells)
        for name in args.shapes.split(",")
        if name in _SHAPES
    )


if __name__ == "__main__":
    raise SystemExit(main())
