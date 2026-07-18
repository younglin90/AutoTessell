"""Canonical cylinder smoke for native_tet — curved-surface standalone check.

THE one measurement protocol for the cylinder. Cycle-6 (BETA2827) was blocked
partly because two agents baselined "boundary skew" with different ad-hoc
scripts and reported 4159 vs 280 on identical code — a protocol mismatch, not
nondeterminism (verified: 5 runs across PYTHONHASHSEED 0/1/2/42 all report
skew 4.16e3 with this script). Numbers from different rulers are not
comparable; all future cards MUST baseline and verify the cylinder with this
script, exactly as cube work uses scripts/smoke_native_tet.py.

Protocol: cylinder.stl / draft / tier native_tet / N=2000 / P4C disabled
(self-implemented engine isolated). Reports the evaluator's max_skewness,
non-orthogonality, side-wall radius fidelity vs the true r=0.5, and verdict.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)

import numpy as np

from core.utils.logging import configure_logging
configure_logging(verbose=False, json=True)

from core.pipeline.orchestrator import PipelineOrchestrator
from core.utils.polymesh_reader import (
    parse_foam_faces, parse_foam_labels, parse_foam_points,
)

CYL = Path(REPO) / "tests" / "benchmarks" / "cylinder.stl"

with tempfile.TemporaryDirectory() as t:
    case = Path(t) / "case"
    t0 = time.monotonic()
    res = PipelineOrchestrator().run(
        CYL, case, quality_level="draft", mesh_type="tet",
        tier_hint="native_tet", max_iterations=1, auto_retry="off",
        write_of_case=True, max_cells=2000,
        tier_specific_params={"max_cells": 2000, "target_cells": 2000},
    )
    dt = time.monotonic() - t0
    poly = case / "constant" / "polyMesh"
    if not (poly / "points").exists():
        print(f"CYL P4C=0: NO POLYMESH (pipeline failed) error={res.error}")
        raise SystemExit(1)
    pts = np.asarray(parse_foam_points(poly / "points"), float)
    faces = [list(x) for x in parse_foam_faces(poly / "faces")]
    nb = np.asarray(parse_foam_labels(poly / "neighbour"), np.int64)
    n_int = len(nb)
    bnd: set[int] = set()
    for f in faces[n_int:]:
        bnd.update(int(v) for v in f)
    bp = pts[np.asarray(sorted(bnd), int)]
    side = np.abs(bp[:, 2]) < 0.49
    dev = np.abs(np.hypot(bp[side, 0], bp[side, 1]) - 0.5)
    cm = res.quality_report.evaluation_summary.checkmesh if res.quality_report else None
    v = (str(res.quality_report.evaluation_summary.verdict.value)
         if res.quality_report else "?")
    print(f"CYL P4C=0: cells={cm.cells if cm else 0} "
          f"skew={cm.max_skewness if cm else 0:.3g} "
          f"nonOrt={cm.max_non_orthogonality if cm else 0:.1f} "
          f"wall_dev_max={dev.max():.3f} verdict={v} time={dt:.1f}s")
