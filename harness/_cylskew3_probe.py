"""CYLSKEW3 probe — sphere.stl offset-ring OFF/ON solid-invariant comparison.

Usage: python harness/_cylskew3_probe.py <N>
Env AUTO_TESSELL_TET_OFFSET_RING toggles the ring; P4C forced OFF.
"""
from __future__ import annotations
import os, sys, tempfile, time
from pathlib import Path

os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)
import numpy as np
from core.utils.logging import configure_logging
configure_logging(verbose=False, json=True)
from core.pipeline.orchestrator import PipelineOrchestrator
from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels, parse_foam_points

N = int(sys.argv[1]) if len(sys.argv) > 1 else 800
SPH = Path(REPO) / "tests" / "benchmarks" / "sphere.stl"
R = 1.0
STL_AREA = 12.506492595767828
STL_VOL = 4.1527407490072425
ring = os.environ.get("AUTO_TESSELL_TET_OFFSET_RING", "0")

with tempfile.TemporaryDirectory() as t:
    case = Path(t) / "case"
    t0 = time.monotonic()
    res = PipelineOrchestrator().run(
        SPH, case, quality_level="draft", mesh_type="tet",
        tier_hint="native_tet", max_iterations=1, auto_retry="off",
        write_of_case=True, max_cells=N,
        tier_specific_params={"max_cells": N, "target_cells": N},
    )
    dt = time.monotonic() - t0
    poly = case / "constant" / "polyMesh"
    if not (poly / "points").exists():
        print(f"SPH ring={ring} N={N}: NO POLYMESH err={res.error}")
        raise SystemExit(1)
    pts = np.asarray(parse_foam_points(poly / "points"), float)
    faces = [list(int(v) for v in f) for f in parse_foam_faces(poly / "faces")]
    owner = np.asarray(parse_foam_labels(poly / "owner"), np.int64)
    nb = np.asarray(parse_foam_labels(poly / "neighbour"), np.int64)
    n_int = len(nb); n_faces = len(faces)

    def area_vec(vs):
        p = pts[vs]; a = np.zeros(3)
        for i in range(len(p)):
            a += np.cross(p[i], p[(i + 1) % len(p)])
        return 0.5 * a

    bnd_area = 0.0
    bnd_verts = set()
    for f in range(n_int, n_faces):
        bnd_area += float(np.linalg.norm(area_vec(faces[f])))
        bnd_verts.update(faces[f])
    area_ratio = bnd_area / STL_AREA

    n_cells = 1 + int(max(owner.max() if len(owner) else -1, nb.max() if len(nb) else -1))
    cell_pts = [set() for _ in range(n_cells)]
    for f in range(n_faces):
        cell_pts[owner[f]].update(faces[f])
    for f in range(n_int):
        cell_pts[nb[f]].update(faces[f])
    sum_abs_vol = 0.0; degen = 0; non_tet = 0
    for c in range(n_cells):
        vs = sorted(cell_pts[c])
        if len(vs) == 4:
            p = pts[vs]
            vol = abs(np.dot(p[1]-p[0], np.cross(p[2]-p[0], p[3]-p[0]))) / 6.0
            sum_abs_vol += vol
            if vol < 1e-9:
                degen += 1
        else:
            non_tet += 1
    vol_ratio = sum_abs_vol / STL_VOL

    # wall_dev = |radius - 1.0| over boundary points
    bp = pts[np.asarray(sorted(bnd_verts), int)]
    rad = np.linalg.norm(bp, axis=1)
    wall_dev = np.abs(rad - R)

    cm = res.quality_report.evaluation_summary.checkmesh if res.quality_report else None
    v = str(res.quality_report.evaluation_summary.verdict.value) if res.quality_report else "?"
    print(f"SPH ring={ring} N={N}: cells={cm.cells if cm else n_cells} "
          f"skew={cm.max_skewness if cm else 0:.4g} "
          f"nonOrt={cm.max_non_orthogonality if cm else 0:.1f} "
          f"neg_vol={cm.negative_volumes if cm else -1} "
          f"wall_dev_max={wall_dev.max():.4f} wall_dev_mean={wall_dev.mean():.4f} "
          f"area_ratio={area_ratio:.4f} vol_ratio={vol_ratio:.4f} "
          f"degen={degen} non_tet={non_tet} verdict={v} time={dt:.1f}s")
