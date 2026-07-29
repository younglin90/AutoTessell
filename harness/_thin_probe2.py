"""THINSLIVER2 probe: naca0012 boundary-skew driver root-cause + apex-relax
simulation, with a per-vertex backtracking line-search (zero-inversion) safe
variant. Measurement only."""
import os, sys, tempfile
os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
import numpy as np
from pathlib import Path
from core.pipeline.orchestrator import PipelineOrchestrator
from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels, parse_foam_points


def _load(stl):
    tmp = Path(tempfile.mkdtemp()); case = tmp / "case"
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
    return pts, faces, owner, nb


def _topology(pts, faces, owner, nb):
    n_int = len(nb); n_faces = len(faces)
    n_cells = 1 + int(max(owner.max(), nb.max()))
    cellset = [set() for _ in range(n_cells)]
    for f in range(n_faces):
        cellset[owner[f]].update(faces[f])
    for f in range(n_int):
        cellset[nb[f]].update(faces[f])
    cellverts = [sorted(cellset[c]) for c in range(n_cells)]
    bverts = set(); bfcount = np.zeros(n_cells, np.int64); bfaces = []
    for f in range(n_int, n_faces):
        bverts.update(faces[f]); bfcount[owner[f]] += 1; bfaces.append((f, int(owner[f])))
    return n_int, n_faces, n_cells, cellverts, bverts, bfcount, bfaces


def _global_skew(pts, faces, owner, nb, n_int, n_faces, n_cells, cellverts):
    cc = np.array([pts[cellverts[c]].mean(0) for c in range(n_cells)])
    fc = np.array([pts[f].mean(0) for f in faces])
    imax = 0.0
    for f in range(n_int):
        o = owner[f]; nbc = nb[f]; d = cc[nbc]-cc[o]; dm = np.linalg.norm(d)
        if dm < 1e-30: continue
        t = np.dot(fc[f]-cc[o], d)/dm**2; proj = cc[o]+t*d
        imax = max(imax, np.linalg.norm(fc[f]-proj)/dm)
    bmax = 0.0
    for f in range(n_int, n_faces):
        o = owner[f]; p = pts[faces[f]]; n = np.zeros(3)
        for k in range(len(p)):
            n += np.cross(p[k], p[(k+1) % len(p)])
        nm = np.linalg.norm(n)
        if nm < 1e-30: continue
        nu = n/nm; nd = np.dot(fc[f]-cc[o], nu); proj = cc[o]+nd*nu
        bmax = max(bmax, np.linalg.norm(fc[f]-proj)/max(abs(nd), 1e-30))
    return imax, bmax


def _sv6(pts, cellverts):
    v = np.zeros(len(cellverts))
    for c, vs in enumerate(cellverts):
        if len(vs) != 4: continue
        p = pts[vs]; v[c] = np.dot(p[1]-p[0], np.cross(p[2]-p[0], p[3]-p[0]))
    return v


def analyze(stl):
    pts, faces, owner, nb = _load(stl)
    n_int, n_faces, n_cells, cellverts, bverts, bfcount, bfaces = _topology(pts, faces, owner, nb)
    imax0, bmax0 = _global_skew(pts, faces, owner, nb, n_int, n_faces, n_cells, cellverts)
    print(f"\n===== {Path(stl).name}: cells={n_cells} bnd_faces={n_faces-n_int} surf_v={len(bverts)} =====")
    print(f" GLOBAL max skew: internal={imax0:.3f} boundary={bmax0:.3f} -> report={max(imax0, bmax0):.3f}")

    fc = np.array([pts[f].mean(0) for f in faces])
    cc = np.array([pts[cellverts[c]].mean(0) for c in range(n_cells)])
    rows = []
    for f, o in bfaces:
        p = pts[faces[f]]; n = np.zeros(3)
        for k in range(len(p)):
            n += np.cross(p[k], p[(k+1) % len(p)])
        nm = np.linalg.norm(n)
        if nm < 1e-30: continue
        nu = n/nm; nd = np.dot(fc[f]-cc[o], nu); proj = cc[o]+nd*nu
        sk = np.linalg.norm(fc[f]-proj)/max(abs(nd), 1e-30)
        vs = cellverts[o]; nsv = sum(v in bverts for v in vs)
        free = [v for v in vs if v not in bverts]
        rows.append((sk, f, o, abs(nd), nsv, len(free)))
    rows.sort(reverse=True)
    print(" WORST boundary-skew cells:")
    for sk, f, o, nd, nsv, nfree in rows[:6]:
        print(f"   bskew={sk:.3f} cell={o} nd={nd:.2e} n_surf_v={nsv}/4 free={nfree} bnd_f={bfcount[o]}")
    n1 = sum(1 for r in rows[:30] if r[5] == 1)
    print(f"   of worst 30 bskew cells: {n1}/30 have exactly 1 free interior vert")

    areas = []
    for f, o in bfaces:
        p = pts[faces[f]]; c = p.mean(0); a = 0.0
        for i in range(len(p)):
            a += np.linalg.norm(np.cross(p[i]-c, p[(i+1) % len(p)]-c))/2
        areas.append(a)
    h = float(np.sqrt(np.median(areas)))

    v2t = {}
    for c, vs in enumerate(cellverts):
        if len(vs) != 4: continue
        for v in vs:
            v2t.setdefault(v, []).append(c)

    def _tvol(pt, c):
        p = pt[cellverts[c]]
        return np.dot(p[1]-p[0], np.cross(p[2]-p[0], p[3]-p[0]))

    def _safe_step(cur, v, disp):
        tets = v2t.get(v, [])
        if not tets: return 1.0
        sv0 = np.array([_tvol(cur, c) for c in tets])
        for lam in (1.0, 0.5, 0.25, 0.125, 0.0625):
            tp = cur.copy(); tp[v] = cur[v]+lam*disp
            sv1 = np.array([_tvol(tp, c) for c in tets])
            if np.all((np.sign(sv1) == np.sign(sv0)) & (np.abs(sv1) > 1e-14)):
                return lam
        return 0.0

    # NAIVE (no line search) — shows inversion damage
    for tau, alpha, iters, safe in [(1.0, 0.7, 3, False), (1.0, 0.7, 3, True),
                                     (3.0, 1.0, 5, True), (5.0, 1.0, 6, True)]:
        cur = pts.copy(); target, thresh = 0.5*h, tau*h
        for _ in range(iters):
            acc = {}; wt = {}
            ccx = np.array([cur[cellverts[c]].mean(0) for c in range(n_cells)])
            fcx = np.array([cur[f].mean(0) for f in faces])
            for f, o in bfaces:
                p = cur[faces[f]]; n = np.zeros(3)
                for k in range(len(p)):
                    n += np.cross(p[k], p[(k+1) % len(p)])
                nm = np.linalg.norm(n)
                if nm < 1e-30: continue
                nu = n/nm; nd = np.dot(fcx[f]-ccx[o], nu)
                if abs(nd) >= thresh: continue
                free = [v for v in cellverts[o] if v not in bverts]
                if not free: continue
                step = alpha*max(target-abs(nd), 0.0)
                disp = -step*nu if nd >= 0 else step*nu
                for v in free:
                    acc[v] = acc.get(v, np.zeros(3))+disp; wt[v] = wt.get(v, 0)+1
            if not acc: break
            for v, a in acc.items():
                d = a/wt[v]
                lam = _safe_step(cur, v, d) if safe else 1.0
                if lam > 0: cur[v] = cur[v]+lam*d
        surf_ids = np.array(sorted(bverts))
        surf_moved = float(np.abs(cur[surf_ids]-pts[surf_ids]).max())
        sv_pre = _sv6(pts, cellverts); sv_post = _sv6(cur, cellverts)
        tm = np.array([len(v) == 4 for v in cellverts])
        inv = int(np.sum((np.sign(sv_pre) != np.sign(sv_post)) & tm))
        im, bm = _global_skew(cur, faces, owner, nb, n_int, n_faces, n_cells, cellverts)
        tag = "SAFE" if safe else "NAIVE"
        print(f"   [{tag} tau={tau} a={alpha} it={iters}] surf_moved={surf_moved:.2e} inv={inv} "
              f"-> int={im:.3f} bnd={bm:.3f} report={max(im, bm):.3f} (was {max(imax0, bmax0):.3f})")


for s in sys.argv[1:]:
    analyze(s)
