"""Fast smoke check for native_tet — dev/A-B iteration in ~1-2s, not ~30s.

The full solid gates in tests/test_native_tet_solid_volume.py run cube.stl at
N=2000 (~3.5s each, ~24s for the suite). For iterating on a change — and for
scoped-stash A/B where the pipeline runs many times — that is too slow.

This script runs cube.stl at a smaller N (default 500, ~1.1s) that is fully
representative: every N holds the same four solid invariants (surface 6.000,
off-plane void 0.000, volume ~1.0, degenerate 0) and shows the same skew defect
(>8.0). It prints the four invariants + skew and exits non-zero if any solid
invariant regresses, so it doubles as a fast guard.

Reserve the N=2000 pytest gates for FINAL verification; use this for the inner
loop. Measured on cube.stl / draft / P4C off:

    N       cells   skew    time
    200     212     15.5    1.2s
    500     417     25.6    1.1s     <- default
    1000    866     10.8    1.0s
    2000    2346    10.1    3.5s     <- pytest gate

Usage:
    python scripts/smoke_native_tet.py            # N=500
    python scripts/smoke_native_tet.py 2000       # match the pytest gate
    AUTO_TESSELL_P4C_PYTETWILD=0 already forced here (isolate the self-impl).
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"  # measure the self-impl alone

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

import numpy as np  # noqa: E402

from core.utils.logging import configure_logging  # noqa: E402

configure_logging(verbose=False, json=False)

from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402
from core.utils.polymesh_reader import (  # noqa: E402
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

_CUBE = _REPO / "tests" / "benchmarks" / "cube.stl"
_TRUE_AREA = 6.0
_TRUE_VOLUME = 1.0


def _measure(poly: Path) -> dict[str, float]:
    pts = np.asarray(parse_foam_points(poly / "points"), float)
    faces = [list(x) for x in parse_foam_faces(poly / "faces")]
    owner = np.asarray(parse_foam_labels(poly / "owner"), np.int64)
    nb = np.asarray(parse_foam_labels(poly / "neighbour"), np.int64)
    n_int = len(nb)
    n_cells = int(max(owner.max(), nb.max() if nb.size else 0)) + 1

    verts: list[set[int]] = [set() for _ in range(n_cells)]
    for fi, f in enumerate(faces):
        o = int(owner[fi])
        if 0 <= o < n_cells:
            verts[o].update(int(v) for v in f)
        if fi < n_int:
            nn = int(nb[fi])
            if 0 <= nn < n_cells:
                verts[nn].update(int(v) for v in f)

    n_degen = 0
    vol_sum = 0.0
    for s in verts:
        if len(s) != 4:
            continue
        q = pts[np.asarray(sorted(s), int)]
        vol = abs(float(np.dot(q[1] - q[0], np.cross(q[2] - q[0], q[3] - q[0])))) / 6.0
        vol_sum += vol
        if vol < 1e-9:
            n_degen += 1

    on = off = 0.0
    for f in faces[n_int:]:
        p = pts[np.asarray(f, int)]
        a = np.zeros(3)
        for i in range(1, len(f) - 1):
            a = a + np.cross(p[i] - p[0], p[i + 1] - p[0]) / 2.0
        area = float(np.linalg.norm(a))
        on_plane = any(
            np.all(np.abs(p[:, ax] - s) < 1e-6)
            for ax in range(3)
            for s in (-0.5, 0.5)
        )
        if on_plane:
            on += area
        else:
            off += area

    return {
        "cells": float(n_cells),
        "degen": float(n_degen),
        "on": on,
        "off": off,
        "vol": vol_sum,
    }


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    with tempfile.TemporaryDirectory() as tmp:
        case = Path(tmp) / "case"
        t0 = time.monotonic()
        res = PipelineOrchestrator().run(
            _CUBE, case, quality_level="draft", mesh_type="tet",
            tier_hint="native_tet", max_iterations=1, auto_retry="off",
            write_of_case=True, max_cells=n,
            tier_specific_params={"max_cells": n, "target_cells": n},
        )
        dt = time.monotonic() - t0
        poly = case / "constant" / "polyMesh"
        if not (poly / "points").exists():
            print(f"SMOKE FAIL: no polyMesh written (N={n})")
            return 1
        m = _measure(poly)
        cm = res.quality_report.evaluation_summary.checkmesh if res.quality_report else None
        skew = cm.max_skewness if cm else float("nan")

        # Solid invariants — N-independent, so failing any is a real regression.
        on_ok = abs(m["on"] / _TRUE_AREA - 1.0) <= 0.05
        off_ok = m["off"] <= 0.05 * _TRUE_AREA
        vol_ok = abs(m["vol"] / _TRUE_VOLUME - 1.0) <= 0.05
        degen_ok = m["degen"] == 0
        solid = on_ok and off_ok and vol_ok and degen_ok

        print(
            f"N={n} cells={int(m['cells'])} time={dt:.1f}s  "
            f"[surface {m['on']:.3f}{'ok' if on_ok else 'BAD'}  "
            f"void {m['off']:.3f}{'ok' if off_ok else 'BAD'}  "
            f"vol {m['vol']:.3f}{'ok' if vol_ok else 'BAD'}  "
            f"degen {int(m['degen'])}{'ok' if degen_ok else 'BAD'}]  "
            f"skew={skew:.3g}"
        )
        if not solid:
            print("SMOKE FAIL: a solid invariant regressed")
            return 1
        print("SMOKE OK (solid); skew is the open quality target (<=8.0)")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
