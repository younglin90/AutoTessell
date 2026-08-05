"""THINSLIVER1 probe: root-cause the worst-skew / degen cells on very_thin_disk
and needle. Runs orchestrator, writes polyMesh, recomputes internal+boundary
skew EXACTLY as native_checker does, prints the worst face's cell topology."""
import os, sys, tempfile
os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
import numpy as np
from pathlib import Path
from core.pipeline.orchestrator import PipelineOrchestrator
from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels, parse_foam_points


def analyze(stl):
    tmp = Path(tempfile.mkdtemp())
    case = tmp / "case"
    PipelineOrchestrator().run(
        Path(stl), case, quality_level="draft", mesh_type="tet",
        tier_hint="native_tet", max_iterations=1, auto_retry="off",
        write_of_case=True, max_cells=2000,
        tier_specific_params={"max_cells": 2000, "target_cells": 2000})
    poly = case / "constant" / "polyMesh"
    pts = np.asarray(parse_foam_points(poly / "points"), float)
    faces = [list(int(v) for v in f) for f in parse_foam_faces(poly / "faces")]
    owner = np.asarray(parse_foam_labels(poly / "owner"), np.int64)
    nb = np.asarray(parse_foam_labels(poly / "neighbour"), np.int64)
    n_int = len(nb); n_faces = len(faces)
    n_cells = 1 + int(max(owner.max(), nb.max()))

    cellset = [set() for _ in range(n_cells)]
    for f in range(n_faces):
        cellset[owner[f]].update(faces[f])
    for f in range(n_int):
        cellset[nb[f]].update(faces[f])
    cc = np.zeros((n_cells, 3))
    cellverts = []
    for c in range(n_cells):
        vs = sorted(cellset[c]); cellverts.append(vs)
        cc[c] = pts[vs].mean(0)

    fc = np.array([pts[f].mean(0) for f in faces])
    fn = np.zeros((n_faces, 3))
    for i, f in enumerate(faces):
        p = pts[f]; a = np.zeros(3)
        for k in range(len(p)):
            a += np.cross(p[k], p[(k + 1) % len(p)])
        fn[i] = 0.5 * a

    bverts = set()
    bfcount = np.zeros(n_cells, np.int64)
    for f in range(n_int, n_faces):
        bverts.update(faces[f]); bfcount[owner[f]] += 1

    print(f"\n===== {Path(stl).name}: cells={n_cells} bnd={n_faces-n_int} n_surf_verts={len(bverts)} =====")

    # boundary skew top
    bsk_list = []
    for f in range(n_int, n_faces):
        o = owner[f]; n = fn[f]; nm = np.linalg.norm(n)
        if nm < 1e-30: continue
        nu = n / nm
        tf = fc[f] - cc[o]; ndist = float(np.dot(tf, nu))
        proj = cc[o] + ndist * nu
        sk = np.linalg.norm(fc[f] - proj) / max(abs(ndist), 1e-30)
        bsk_list.append((sk, f, o, abs(ndist)))
    bsk_list.sort(reverse=True)
    print(f" BOUNDARY max skew {bsk_list[0][0]:.3e}")
    for sk, f, o, nd in bsk_list[:4]:
        vs = cellverts[o]
        surf = [v in bverts for v in vs]
        print(f"   bskew {sk:.3e} owner {o} nd={nd:.2e} n_surf_v={sum(surf)}/4 bnd_faces={bfcount[o]}")

    # degen cells: classify removability
    degen = []
    for c in range(n_cells):
        vs = cellverts[c]
        if len(vs) == 4:
            p = pts[vs]
            vol = abs(np.dot(p[1]-p[0], np.cross(p[2]-p[0], p[3]-p[0]))) / 6.0
            if vol < 1e-9:
                degen.append((c, vol))
    print(f" DEGEN cells (<1e-9): {len(degen)}")
    n_fullint = collapse_ok = 0
    for c, vol in degen:
        vs = cellverts[c]
        n_surf_v = sum(v in bverts for v in vs)
        best = (1e30, None, None)
        for i in range(4):
            for j in range(i+1, 4):
                L = float(np.linalg.norm(pts[vs[i]]-pts[vs[j]]))
                if L < best[0]:
                    best = (L, vs[i], vs[j])
        L, a, b = best
        a_int = a not in bverts; b_int = b not in bverts
        if bfcount[c] == 0:
            n_fullint += 1
        if a_int or b_int:
            collapse_ok += 1
        if c in [d[0] for d in degen[:6]]:
            print(f"   cell {c} vol={vol:.2e} n_surf_v={n_surf_v}/4 bnd_faces={bfcount[c]} "
                  f"short_edge L={L:.2e} endpts=({'I' if a_int else 'S'},{'I' if b_int else 'S'})")
    print(f"   SUMMARY: {n_fullint}/{len(degen)} fully-interior(0 bnd-face), "
          f"{collapse_ok}/{len(degen)} have >=1 interior endpoint on shortest edge (collapse-safe)")


for s in sys.argv[1:]:
    analyze(s)
