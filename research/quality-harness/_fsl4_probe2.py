"""FSL4 probe2: classify the 61 wedges — coplanar flat-on-surface vs gap-spanning
— and empirically test both removal approaches on the worst wedges."""
import numpy as np
d = np.load("research/quality-harness/_fsl4_mesh.npz")
pts = d["pts"]; tets = d["tets"]; ns = int(d["ns"])

v = pts[tets]
all_surface = (tets < ns).all(1)
e = [np.linalg.norm(v[:,i]-v[:,j], axis=1) for i,j in ((0,1),(0,2),(0,3),(1,2),(1,3),(2,3))]
edge_max = np.maximum.reduce(e)
vol = np.abs(np.einsum("ij,ij->i", v[:,1]-v[:,0], np.cross(v[:,2]-v[:,0], v[:,3]-v[:,0])))/6.0
q = np.zeros_like(edge_max); safe = edge_max>1e-30
q[safe] = 8.48*vol[safe]/(edge_max[safe]**3)
cand = np.where(all_surface & (q<0.01))[0]

local = np.array([[1,2,3],[0,2,3],[0,1,3],[0,1,2]])
sf = np.sort(tets[:,local].reshape(-1,3), axis=1)
order = np.lexsort((sf[:,2],sf[:,1],sf[:,0])); sk = sf[order]
match = np.all(sk[1:]==sk[:-1],axis=1)
partner = np.full(order.size,-1,np.int64); pi=np.where(match)[0]
partner[order[pi]]=order[pi+1]; partner[order[pi+1]]=order[pi]

def sv(a,b,c,d_): return float(np.dot(b-a, np.cross(c-a, d_-a)))

wedges=[]
for ti in cand.tolist():
    nb=0; flip_ok=False; bf=[]
    for lf in range(4):
        nbf=partner[4*ti+lf]; s0,s1,s2=tets[ti,local[lf]]
        if nbf<0:
            nb+=1
            nrm=np.cross(pts[s1]-pts[s0],pts[s2]-pts[s0]); nm=np.linalg.norm(nrm)
            fc=(pts[s0]+pts[s1]+pts[s2])/3.0; cc=v[ti].mean(0)
            nd=float(np.dot(fc-cc, nrm/nm)) if nm>1e-30 else 0.0
            tang=(fc-cc)-nd*(nrm/nm) if nm>1e-30 else fc-cc
            bskew=float(np.linalg.norm(tang))/max(abs(nd),1e-30)
            bf.append((lf,(int(s0),int(s1),int(s2)),bskew,abs(nd),nrm/nm if nm>1e-30 else nrm))
        else:
            tj,nlf=divmod(int(nbf),4); a1,a2=tets[ti,lf],tets[tj,nlf]
            vs=[sv(pts[s0],pts[s1],pts[a1],pts[a2]),sv(pts[s1],pts[s2],pts[a1],pts[a2]),sv(pts[s2],pts[s0],pts[a1],pts[a2])]
            if all(abs(x)>1e-18 for x in vs) and (all(x>0 for x in vs) or all(x<0 for x in vs)): flip_ok=True
    if (not flip_ok) and nb>=2: wedges.append((ti,bf))

# classify: coplanar (2 bnd faces same plane, flat-on-surface) vs opposing (gap span)
copl=0; oppo=0; angles=[]
for ti,bf in wedges:
    if len(bf)<2: continue
    n0=bf[0][4]; n1=bf[1][4]
    cosang=abs(float(np.dot(n0,n1)))
    ang=np.degrees(np.arccos(min(1,cosang)))
    angles.append(ang)
    # coplanar test: apex of face1 distance to face0 plane
    f0=set(bf[0][1]); f1=set(bf[1][1]); spine=f0&f1
    if len(spine)==2:
        apex1=list(f1-spine)[0]; s=list(f0)[0]
        dd=abs(float(np.dot(pts[apex1]-pts[s], n0)))
        if dd < 1e-6: copl+=1
        else: oppo+=1
print("wedge count", len(wedges))
print("coplanar(flat-on-surface, 2 bnd faces SAME plane):", copl, " non-coplanar:", oppo)
print("dihedral angle between 2 bnd faces: min %.3f max %.3f mean %.3f deg"%(min(angles),max(angles),np.mean(angles)))

# span-thickness: for each wedge, the normal extent of its 4 verts along bnd-face normal
spans=[]
for ti,bf in wedges:
    n0=bf[0][4]; proj=pts[tets[ti]]@n0; spans.append(float(proj.max()-proj.min()))
spans=np.array(spans)
edg=np.array([float(edge_max[ti]) for ti,_ in wedges])
print("normal-span/edge_max ratio: min %.2e max %.2e mean %.2e"%((spans/edg).min(),(spans/edg).max(),(spans/edg).mean()))
print("(ratio ~0 => flat sliver in-plane, not gap-spanning)")

# washer thickness reference: z-range of surface verts
zs=pts[:ns,2]; print("surface z-range:", round(zs.min(),4), round(zs.max(),4), "=> washer half-thickness", round((zs.max()-zs.min())/2,4))

# ---- APPROACH (a) EMPIRICAL: surface-edge split on worst wedge ----
# insert new vertex at spine-edge midpoint; would it de-coplanarize? (all pts coplanar => no)
print("\n=== APPROACH (a) test: does any surface point insertion de-coplanarize?")
ti0=wedges[np.argmax([max(b[2] for b in bf) for ti,bf in wedges])][0]
P=pts[tets[ti0]]
# plane fit of the 4 verts
c=P.mean(0); u,sg,vt=np.linalg.svd(P-c)
print("worst wedge tet",ti0,"4-vert planarity (smallest singular val):",f"{sg[-1]:.2e}","(0 => perfectly coplanar)")
print("=> ANY new vertex on the surface (envelope) is ALSO on this plane; split keeps tets coplanar. (a) cannot de-coplanarize a flat-on-surface sliver.")

# ---- APPROACH near-wall interior insert EMPIRICAL: offset point below plane ----
print("\n=== Interior-offset (Garimella) test on worst wedge: split bnd faces to an interior apex")
# take the 2 bnd faces, insert interior point at centroid offset inward by delta along -normal
bf0=[b for ti,bf in wedges if ti==ti0 for b in bf]
n0=bf0[0][4]
# inward = toward washer interior (z=0). worst wedge near z=0.5 top => inward -z-ish; use -n0 sign toward centroid of all surface
inward = -n0 if np.dot(n0, np.array([0,0,0])-P.mean(0))<0 else n0
delta = 0.5*edge_max[ti0]
newp = P.mean(0) + inward*delta
# new tets: each bnd face + newp
oldbsk=[]; newbsk=[]
newvols=[]
for lf,(s0,s1,s2),bskew,nd,nrm in bf0:
    oldbsk.append(bskew)
    tp=np.array([pts[s0],pts[s1],pts[s2],newp])
    newvols.append(sv(tp[0],tp[1],tp[2],tp[3]))
    fc=tp[:3].mean(0); cc=tp.mean(0)
    ndn=float(np.dot(fc-cc,nrm)); tang=(fc-cc)-ndn*nrm
    newbsk.append(float(np.linalg.norm(tang))/max(abs(ndn),1e-30))
print("interior offset point:", newp.round(4).tolist(), "delta", round(float(delta),4))
print("old bnd-face bskew:", [round(x,1) for x in oldbsk])
print("new bnd-face bskew (with interior apex):", [round(x,3) for x in newbsk])
print("new tet signed vols (must be same sign, nonzero):", [f"{x:.2e}" for x in newvols])
print("=> interior offset apex DECIMATES bskew (flat cap -> proper tet). But new vertex is INTERIOR, requires cavity re-tetrahedralization + neg-vol/void guards across the wedge fan. Multi-card, not a surface split.")
