"""FSL4 probe: capture final in-memory mesh at the FSL3 hook, characterize the
61 core-unflippable 2-boundary-face wedges, and empirically weigh approach (a)
surface-edge split vs (b) known-limit."""
import os, tempfile
os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
import numpy as np
from pathlib import Path
from core.analyzer.file_reader import load_mesh
import core.generator.native_tet.validate as V

_CAP = {}
_orig = V.apply_flat_sliver_23_flips
def _spy(pts, tets, n_surf, **kw):
    _CAP["pts"] = np.asarray(pts, float).copy()
    _CAP["tets"] = np.asarray(tets, np.int64).copy()
    _CAP["n_surf"] = int(n_surf)
    return _orig(pts, tets, n_surf, **kw)
V.apply_flat_sliver_23_flips = _spy

from core.generator.native_tet.mesher import generate_native_tet
m = load_mesh(Path("tests/benchmarks/high_genus_dual_torus.stl"))
r = generate_native_tet(np.asarray(m.vertices, float), np.asarray(m.faces, np.int64),
                        Path(tempfile.mkdtemp()) / "c", target_cells=600)
print("grade", r.quality_grade, "ncells", r.n_cells)

pts = _CAP["pts"]; tets = _CAP["tets"]; ns = _CAP["n_surf"]
print("captured: pts", pts.shape, "tets", tets.shape, "n_surf", ns)
np.savez(Path("harness/_fsl4_mesh.npz"), pts=pts, tets=tets, ns=ns)

# ---- rebuild detector internals to enumerate the 61 wedges ----
v = pts[tets]
all_surface = (tets < ns).all(1)
e = [np.linalg.norm(v[:, i] - v[:, j], axis=1)
     for i, j in ((0,1),(0,2),(0,3),(1,2),(1,3),(2,3))]
edge_max = np.maximum.reduce(e)
vol = np.abs(np.einsum("ij,ij->i", v[:,1]-v[:,0], np.cross(v[:,2]-v[:,0], v[:,3]-v[:,0])))/6.0
q = np.zeros_like(edge_max); safe = edge_max > 1e-30
q[safe] = 8.48*vol[safe]/(edge_max[safe]**3)
cand = np.where(all_surface & (q < 0.01))[0]

local = np.array([[1,2,3],[0,2,3],[0,1,3],[0,1,2]])
sf = np.sort(tets[:, local].reshape(-1,3), axis=1)
order = np.lexsort((sf[:,2], sf[:,1], sf[:,0])); sk = sf[order]
match = np.all(sk[1:]==sk[:-1], axis=1)
partner = np.full(order.size, -1, np.int64)
pi = np.where(match)[0]
partner[order[pi]] = order[pi+1]; partner[order[pi+1]] = order[pi]

def sv(a,b,c,d): return float(np.dot(b-a, np.cross(c-a, d-a)))

wedges = []  # 2-boundary unflippable
for ti in cand.tolist():
    n_boundary = 0; flip_ok = False; bfaces = []
    for lf in range(4):
        nbf = partner[4*ti+lf]
        s0,s1,s2 = tets[ti, local[lf]]
        if nbf < 0:
            n_boundary += 1
            fc = (pts[s0]+pts[s1]+pts[s2])/3.0
            nrm = np.cross(pts[s1]-pts[s0], pts[s2]-pts[s0]); nm = np.linalg.norm(nrm)
            if nm < 1e-30: continue
            nrm/=nm; cc = v[ti].mean(0); tf = fc-cc
            nd = float(np.dot(tf, nrm)); tang = tf-nd*nrm
            bskew = float(np.linalg.norm(tang))/max(abs(nd),1e-30)
            bfaces.append((lf, (int(s0),int(s1),int(s2)), bskew, abs(nd)))
        else:
            tj, nlf = divmod(int(nbf), 4)
            a1,a2 = tets[ti,lf], tets[tj,nlf]
            vs = [sv(pts[s0],pts[s1],pts[a1],pts[a2]), sv(pts[s1],pts[s2],pts[a1],pts[a2]),
                  sv(pts[s2],pts[s0],pts[a1],pts[a2])]
            if all(abs(x)>1e-18 for x in vs) and (all(x>0 for x in vs) or all(x<0 for x in vs)):
                flip_ok = True
    if (not flip_ok) and n_boundary >= 2:
        wedges.append((ti, n_boundary, bfaces))

print("n_cand", cand.size, "n_wedges(unflippable,>=2bnd)", len(wedges))
allbsk = sorted((max(bs for _,_,bs,_ in bf), ti, nb) for ti,nb,bf in wedges if bf)[::-1]
print("top-8 wedge bskew:", [(round(b,3 if b<1e3 else 0), t) for b,t,_ in allbsk[:8]])
nb_dist = {}
for ti,nb,bf in wedges: nb_dist[nb] = nb_dist.get(nb,0)+1
print("n_boundary_faces distribution among wedges:", nb_dist)
big = [w for w in allbsk if w[0] > 1e4]
print("n wedges with bskew>1e4:", len(big), " >1e6:", sum(1 for w in allbsk if w[0]>1e6))

# ---- characterize the WORST wedge geometry (approach-a feasibility) ----
worst_ti = allbsk[0][1]
wi = [w for w in wedges if w[0]==worst_ti][0]
ti, nb, bf = wi
verts = tets[ti]
print("\n=== WORST wedge tet", ti, "verts", verts.tolist(), "(all<ns=%d surface)"%ns)
print("edge lengths:", [round(float(x[ti]),5) for x in e])
print("vol", float(vol[ti]), "q", float(q[ti]))
# boundary faces of the wedge
for lf,(s0,s1,s2),bskew,nd in bf:
    print(" bnd-face verts", (s0,s1,s2), "bskew", round(bskew,1), "normal_dist", nd)
# The two boundary faces share an edge (the wedge spine). Find shared edge.
if len(bf) >= 2:
    f0 = set(bf[0][1]); f1 = set(bf[1][1])
    spine = f0 & f1
    apex_each = (f0 - spine, f1 - spine)
    print(" shared spine edge verts:", spine, " apex of each bnd face:", apex_each)
    # midpoint of the two apex vertices -> candidate split point
    sp = list(spine)
    if len(apex_each[0])==1 and len(apex_each[1])==1:
        a0 = list(apex_each[0])[0]; a1 = list(apex_each[1])[0]
        mid = (pts[a0]+pts[a1])/2.0
        print(" apex verts", a0, a1, " midpoint", mid.round(5).tolist())
        # distance from midpoint to each boundary-face plane (envelope proxy)
        for lf,(s0,s1,s2),bskew,nd in bf:
            nrm = np.cross(pts[s1]-pts[s0], pts[s2]-pts[s0]); nrm/=np.linalg.norm(nrm)
            d = abs(float(np.dot(mid-pts[s0], nrm)))
            print("  mid dist to bnd-plane", (s0,s1,s2), "=", round(d,6))
