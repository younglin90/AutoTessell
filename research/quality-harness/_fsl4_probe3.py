"""FSL4 probe3: calibrate the PASS-gate invariants (volume tiling + watertight
boundary) and the xfail skew target for the dual_torus gate."""
import os
os.environ["AUTO_TESSELL_P4C_PYTETWILD"]="0"
import numpy as np
from pathlib import Path
from core.analyzer.file_reader import load_mesh

d = np.load("research/quality-harness/_fsl4_mesh.npz")
pts=d["pts"]; tets=d["tets"]
# input surface volume (divergence) + area
m = load_mesh(Path("tests/benchmarks/high_genus_dual_torus.stl"))
V=np.asarray(m.vertices,float); F=np.asarray(m.faces,np.int64)
tri=V[F]
inp_vol=abs(float(np.einsum("ij,ij->i", tri[:,0], np.cross(tri[:,1],tri[:,2])).sum()/6.0))
inp_area=float(np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1).sum()/2.0)
# mesh sum|tet vol|
v=pts[tets]
cellvol=np.abs(np.einsum("ij,ij->i", v[:,1]-v[:,0], np.cross(v[:,2]-v[:,0],v[:,3]-v[:,0])))/6.0
print("input surface volume:", round(inp_vol,4), " area:", round(inp_area,4))
print("mesh sum|cell vol|:", round(float(cellvol.sum()),4), " ratio:", round(float(cellvol.sum())/inp_vol,4))
print("n cells:", tets.shape[0], " n near-zero vol (<1e-9):", int((cellvol<1e-9).sum()))
# watertight boundary check: boundary faces (partner<0) signed area sum ~0
local=np.array([[1,2,3],[0,2,3],[0,1,3],[0,1,2]])
sf=np.sort(tets[:,local].reshape(-1,3),axis=1)
order=np.lexsort((sf[:,2],sf[:,1],sf[:,0])); sk=sf[order]
match=np.all(sk[1:]==sk[:-1],axis=1)
partner=np.full(order.size,-1,np.int64); pi=np.where(match)[0]
partner[order[pi]]=order[pi+1]; partner[order[pi+1]]=order[pi]
bf_local=np.where(partner<0)[0]
faces_all=tets[:,local].reshape(-1,3)[bf_local]
fa=faces_all
avec=np.cross(pts[fa[:,1]]-pts[fa[:,0]], pts[fa[:,2]]-pts[fa[:,0]])/2.0
print("n boundary faces:", bf_local.size, " Σ|area-vec| (unsigned):", round(float(np.linalg.norm(avec,axis=1).sum()),4))
print("Σ area-vec (signed, watertight => ~0):", np.abs(avec.sum(0)).round(4).tolist(), " |Σ|:", round(float(np.linalg.norm(avec.sum(0))),4))
# skew target reference
print("current max_boundary_skew ~ 2.94e7; cylinder known-limit class skew ~44.9")
