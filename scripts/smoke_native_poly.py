"""Canonical solid smoke for native_poly — the ONE measurement protocol.

Ports the native_tet/native_hex methodology (scripts/smoke_native_tet.py,
scripts/smoke_native_hex.py) to the polyhedral-dual engine
(core/generator/native_poly/harness.py). This script makes the current
native_poly state MEASURABLE, it does not fix quality.

Protocol: cube.stl / draft / mesh_type poly / tier_hint native_poly /
strict_tier (no cross-family fallback) / N cells (default 500, argv[1]).
With bl_layers=0 (the default here), tier_native_poly routes to
run_native_poly_harness (tet -> poly dual), NOT the scipy Voronoi fallback
(tier_native_poly.py:35-55). max_cells/target_cells are accepted for CLI
interface parity with the tet/hex smokes but are NOT forwarded to the harness
path (tier_native_poly.py:57-61) — N is inert here, unlike tet/hex.

Solid invariants measured (see tests/test_native_poly_solid_volume.py for the
locked gate values):

  1. surface coverage — boundary area lying ON the cube's 6 planes must == 6.000.
  2. no interior voids — boundary area lying OFF those planes must be ~0.
  3. volume — Σ|cell vol| must == 1.000 (cells tile the cube, no gaps/overlap).
  4. no degenerate cells — no cell with (near) zero volume.

Poly cells are arbitrary convex polyhedra (tet->dual cells), so tet's |det|/6
does not apply. Cell volume is computed the same orientation-free way as the
hex smoke: decompose into centroid-apex pyramids over each face, fan-
triangulate each face, sum |tet vol|.

MEASURED (beta2822, CARD POLY-S1): surface 6.000 (1.00x) OK, void 7.588 BAD
(dual open-wall boundary cells), volume 1.177 (1.18x) BAD (cube-exceeding
bulge), degen 0 OK. Only (1) and (4) are exit-code-gated here — void/volume
are recorded, printed, but treated as OPEN quality targets (like the tet
smoke treats skew), matching the xfail(strict) gates in
tests/test_native_poly_solid_volume.py. A future card (POLY-S2/S3) promotes
them to permanent gates once the dual open-boundary/bulge defects are fixed.

Prints one line + exits non-zero if the solid SUBSET (surface, degen)
regresses. If native_poly writes no polyMesh (or crashes), prints
"NO POLYMESH" + the error and exits non-zero — an honest result, not a masked
one.

Usage:
    python scripts/smoke_native_poly.py            # N=500
    python scripts/smoke_native_poly.py 2000       # interface parity only, inert
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)

import numpy as np  # noqa: E402

from core.utils.logging import configure_logging  # noqa: E402

configure_logging(verbose=False, json=False)

from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402
from core.utils.polymesh_reader import (  # noqa: E402
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

_CUBE = Path(REPO) / "tests" / "benchmarks" / "cube.stl"
_TRUE_AREA = 6.0
_TRUE_VOLUME = 1.0
_PLANES = 0.5  # |x| = |y| = |z| = 0.5


def _face_area(pts: np.ndarray, face: list[int]) -> float:
    """Fan-triangulate a polygon face (arbitrary n-gon for poly) and return |area|."""
    p = pts[np.asarray(face, dtype=int)]
    acc = np.zeros(3)
    for i in range(1, len(face) - 1):
        acc = acc + np.cross(p[i] - p[0], p[i + 1] - p[0]) / 2.0
    return float(np.linalg.norm(acc))


def _cell_volume_orientation_free(pts: np.ndarray, cell_faces: list[list[int]]) -> float:
    """|volume| of a convex cell, independent of face orientation.

    Decompose the cell into pyramids from its centroid over each face, then
    fan-triangulate each face into tets (centroid, v0, vi, vi+1) and sum the
    magnitude |det|/6 of every tet. For a convex cell with an interior apex the
    pyramids tile the cell without overlap, so summing per-tet magnitudes gives
    the exact volume regardless of the polyMesh owner/neighbour sign convention.
    """
    verts = sorted({int(v) for f in cell_faces for v in f})
    if len(verts) < 4:
        return 0.0
    c = pts[np.asarray(verts, dtype=int)].mean(axis=0)
    total = 0.0
    for face in cell_faces:
        p = pts[np.asarray(face, dtype=int)]
        for i in range(1, len(face) - 1):
            total += abs(float(np.dot(p[0] - c, np.cross(p[i] - c, p[i + 1] - c)))) / 6.0
    return total


def _measure(poly: Path) -> dict[str, float]:
    pts = np.asarray(parse_foam_points(poly / "points"), dtype=float)
    faces = [list(f) for f in parse_foam_faces(poly / "faces")]
    owner = np.asarray(parse_foam_labels(poly / "owner"), dtype=np.int64)
    nb = np.asarray(parse_foam_labels(poly / "neighbour"), dtype=np.int64)
    n_int = len(nb)
    n_cells = int(max(owner.max(), nb.max() if nb.size else 0)) + 1

    # cell -> list of its faces (vertex lists), from owner/neighbour.
    cell_faces: list[list[list[int]]] = [[] for _ in range(n_cells)]
    for fi, f in enumerate(faces):
        o = int(owner[fi])
        if 0 <= o < n_cells:
            cell_faces[o].append(f)
        if fi < n_int:
            nn = int(nb[fi])
            if 0 <= nn < n_cells:
                cell_faces[nn].append(f)

    vol_sum = 0.0
    n_degen = 0
    for cf in cell_faces:
        v = _cell_volume_orientation_free(pts, cf)
        vol_sum += v
        if v < 1e-12:
            n_degen += 1

    on = off = 0.0
    for f in faces[n_int:]:
        p = pts[np.asarray(f, dtype=int)]
        area = _face_area(pts, f)
        on_plane = any(
            np.all(np.abs(p[:, ax] - s) < 1e-6) for ax in range(3) for s in (-_PLANES, _PLANES)
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
            _CUBE,
            case,
            quality_level="draft",
            mesh_type="poly",
            tier_hint="native_poly",
            max_iterations=1,
            auto_retry="off",
            strict_tier=True,
            write_of_case=True,
            max_cells=n,
            tier_specific_params={"max_cells": n, "target_cells": n},
        )
        dt = time.monotonic() - t0
        poly = case / "constant" / "polyMesh"
        if not (poly / "points").exists():
            print(f"POLY N={n}: NO POLYMESH (pipeline failed) error={res.error}")
            return 1

        m = _measure(poly)
        cm = res.quality_report.evaluation_summary.checkmesh if res.quality_report else None
        skew = cm.max_skewness if cm else float("nan")
        verdict = (
            str(res.quality_report.evaluation_summary.verdict.value) if res.quality_report else "?"
        )

        on_ok = abs(m["on"] / _TRUE_AREA - 1.0) <= 0.05
        off_ok = m["off"] <= 0.05 * _TRUE_AREA
        vol_ok = abs(m["vol"] / _TRUE_VOLUME - 1.0) <= 0.05
        degen_ok = m["degen"] == 0
        # Only the solid SUBSET currently passing gates the exit code — void and
        # volume are open quality targets (see module docstring), not regressions.
        solid = on_ok and degen_ok

        print(
            f"POLY N={n} cells={int(m['cells'])} time={dt:.1f}s  "
            f"[surface {m['on']:.3f}{'ok' if on_ok else 'BAD'}  "
            f"void {m['off']:.3f}{'ok' if off_ok else 'BAD'}  "
            f"vol {m['vol']:.3f}{'ok' if vol_ok else 'BAD'}  "
            f"degen {int(m['degen'])}{'ok' if degen_ok else 'BAD'}]  "
            f"skew={skew:.3g} verdict={verdict}"
        )
        if not solid:
            print("SMOKE FAIL: a solid invariant regressed")
            return 1
        print("SMOKE OK (solid subset); void/volume are the open targets")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
