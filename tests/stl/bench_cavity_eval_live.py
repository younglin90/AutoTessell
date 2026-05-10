#!/usr/bin/env python3
"""Live partial-results reader for bench_cavity_eval.py.

Scans the bench RUN_ROOT for completed cases and runs
``NativeMeshChecker`` directly on each polyMesh to report the
max-non-orthogonality and other quality metrics, plus PASS/FAIL
against the ``agents/specs/evaluator.md`` thresholds for the
chosen quality level.  Useful for monitoring an in-flight bench
without waiting for the parent script to finish writing the
summary TSV.

Usage::

    python3 tests/stl/bench_cavity_eval_live.py
    AUTO_TESSELL_BENCH_CAVITY_QUALITY=draft \\
        python3 tests/stl/bench_cavity_eval_live.py
    AUTO_TESSELL_BENCH_CAVITY_RUN_ROOT=/tmp/foo \\
        python3 tests/stl/bench_cavity_eval_live.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evaluator.native_checker import NativeMeshChecker
from core.evaluator.report import get_thresholds


RUN_ROOT = Path(
    os.environ.get(
        "AUTO_TESSELL_BENCH_CAVITY_RUN_ROOT",
        "/tmp/autotessell_bench_cavity_eval",
    )
)
QUALITY = os.environ.get("AUTO_TESSELL_BENCH_CAVITY_QUALITY", "fine")


def main() -> int:
    if not RUN_ROOT.exists():
        print(f"run root not found: {RUN_ROOT}", file=sys.stderr)
        return 1
    thresholds = get_thresholds(QUALITY)
    hard_no = float(thresholds.get("hard_non_ortho", 65.0))
    hard_skew = float(thresholds.get("hard_skewness", 4.0))
    cases = sorted(p for p in RUN_ROOT.iterdir() if p.is_dir())
    cols = ("case", "n_cells", "max_no", "max_skew", "min_det", "verdict")
    print(f"quality={QUALITY}  hard_no={hard_no}  hard_skew={hard_skew}")
    print("\t".join(cols))
    n_pass = n_fail = n_skipped = 0
    for case in cases:
        poly = case / "constant" / "polyMesh"
        if not (poly / "owner").exists():
            print(f"{case.name}\t-\t-\t-\t-\tSKIP_NO_POLYMESH")
            n_skipped += 1
            continue
        try:
            r = NativeMeshChecker().run(case)
        except Exception as exc:  # noqa: BLE001
            print(f"{case.name}\t-\t-\t-\t-\tSKIP_{type(exc).__name__}")
            n_skipped += 1
            continue
        max_no = float(r.max_non_orthogonality)
        max_skew = float(r.max_skewness)
        min_det = float(r.min_determinant)
        n_cells = int(getattr(r, "cells", 0))
        hard_fail = (
            max_no > hard_no
            or max_skew > hard_skew
            or min_det <= 0.0
            or int(getattr(r, "negative_volumes", 0)) > 0
        )
        verdict = "FAIL" if hard_fail else "PASS"
        if hard_fail:
            n_fail += 1
        else:
            n_pass += 1
        print(
            f"{case.name}\t{n_cells}\t{round(max_no, 2)}\t"
            f"{round(max_skew, 3)}\t{round(min_det, 5)}\t{verdict}"
        )
    print(
        f"--- pass={n_pass} fail={n_fail} skipped={n_skipped} "
        f"total={len(cases)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
