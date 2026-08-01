"""Persisted native release campaign runner."""
from __future__ import annotations
import hashlib
import json
import math
import os
import shutil
from dataclasses import replace
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from core.analyzer.readers import read_stl
from core.analyzer.readers.step import load_cad_native_with_provenance
from core.evaluator.native_release_authority_gate import validate_native_release_authority_matrix
from core.evaluator.native_release_matrix import RELEASE_MATRIX_SCHEMA
from core.evaluator.native_hex_release_evidence import certify_native_hex_release_output
from core.evaluator.native_poly_release_evidence import certify_native_poly_boundary_authority
from core.evaluator.native_tet_release_evidence import certify_native_tet_release_output
from core.evaluator.native_tri_release_evidence import certify_native_tri_release_result
from core.evaluator.native_surface_release_evidence import certify_fixed_pair_surface_output
from core.evaluator.strict_surface_topology import audit_strict_surface_topology
from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.native_hex.mesher import generate_native_hex
from core.generator.native_poly.harness import run_native_poly_harness
from core.generator.tier_native_poly import _runner
from core.generator.tier_layers_post import _run_native_hex_bl
from core.layers.poly_bl_transition import run_poly_bl_transition
from core.preprocessor.native_tri.release_route import NativeTriSourceAuthority, run_native_tri_release
from core.evaluator.surface_physical_group_provenance import AuthoritativePhysicalGroupMapping
from core.utils.boundary_provenance import SourceSurfacePatchClassifier
from core.utils.polymesh_reader import parse_foam_boundary

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def phash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()

def ahash(value: object) -> str:
    a=np.ascontiguousarray(np.asarray(value)); h=hashlib.sha256()
    h.update(a.dtype.str.encode()); h.update(np.asarray(a.shape,dtype="<i8").tobytes()); h.update(a.tobytes())
    return h.hexdigest()

def manifest(case: Path) -> str:
    h=hashlib.sha256()
    for p in sorted((case/"constant"/"polyMesh").iterdir()):
        if p.is_file(): h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()

def flags(c: dict) -> dict:
    return {"authoritative": c.get("authoritative") is True, "critical_missing": 0 if c.get("authoritative") is True else 1,
            "physical_groups_authoritative": c.get("physical_groups_preserved") is True,
            "patch_mapping_complete": c.get("patch_preserved") is True,
            "provenance_complete": c.get("provenance_complete") is True,
            "component_bijection": c.get("component_bijection") is True}

def unverified(row_id: str, engine: str, fixture: str, reason: str) -> dict:
    z="0"*64
    return {"id":row_id,"engine":engine,"fixture":fixture,"route":"unverified",
            "source_authority":{"authoritative":False,"sha256":z},
            "strict_topology":{"status":"unverified","valid":False,"artifact_sha256":z,"boundary_surface_valid":False},
            "surface":{"valid":False,"source_sha256":z,"output_sha256":z},
            "features":{"authoritative":False,"critical_missing":1,"physical_groups_authoritative":False,"patch_mapping_complete":False,"provenance_complete":False,"component_bijection":False},
            "boundary_layer":{"layers":0},"repeatability":{"run_count":0,"byte_identical":False,"independent_route":False,"artifact_sha256":[]},
            "source_output_authority":{"authoritative":False,"rejection_reason":reason}}

def volume_row(row_id, engine, fixture, route, source, cases, certs, layers=0, first=None, positive=0):
    audits=[audit_strict_volume_topology(c).as_dict() for c in cases]
    out=[a["artifact_sha256"] for a in audits]; c=dict(certs[0]); c.setdefault("shape_preserved",c.get("source_vertices_preserved") is True)
    return {"id":row_id,"engine":engine,"fixture":fixture,"route":route,
            "source_authority":{"authoritative":True,"sha256":sha(source)},
            "strict_topology":audits[0],
            "surface":{"valid":audits[0].get("boundary_surface_valid") is True,"source_sha256":sha(source),"output_sha256":out[0]},
            "features":flags(c),
            "boundary_layer":{"layers":layers,**({"positive_first_layer_height":first,"positive_cell_count":positive} if layers else {})},
            "repeatability":{"run_count":len(cases),"byte_identical":out==[out[0]]*len(out),"independent_route":True,"artifact_sha256":out},
            "source_output_authority":c}

def surface_package(case: Path, vertices, faces):
    case.mkdir(parents=True,exist_ok=True); np.save(case/"vertices.npy",np.asarray(vertices,dtype=np.float64)); np.save(case/"triangles.npy",np.asarray(faces,dtype=np.int64))
    return audit_strict_surface_topology(vertices,faces).as_dict()

def surface_row(row_id,engine,fixture,route,source_sha,audits,certs):
    a=[dict(x) for x in audits]; out=[x["artifact_sha256"] for x in a]; a0=dict(a[0]); a0["kind"]="surface"; c=dict(certs[0]); c.setdefault("shape_preserved",c.get("source_vertices_preserved") is True)
    return {"id":row_id,"engine":engine,"fixture":fixture,"route":route,"source_authority":{"authoritative":True,"sha256":source_sha},
            "strict_topology":a0,"surface":{"valid":a0.get("valid") is True,"source_sha256":source_sha,"output_sha256":out[0]},
            "features":flags(c),"boundary_layer":{"layers":0},
            "repeatability":{"run_count":len(a),"byte_identical":out==[out[0]]*len(out),"independent_route":True,"artifact_sha256":out},
            "source_output_authority":c}
def make_cad_sources(root: Path) -> dict[str,Path]:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder,BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Ax1,gp_Dir,gp_Pnt,gp_Trsf
    from OCP.STEPControl import STEPControl_AsIs,STEPControl_Writer
    src=root/"sources"; src.mkdir(parents=True,exist_ok=True)
    def write(shape,path):
        w=STEPControl_Writer()
        if int(w.Transfer(shape,STEPControl_AsIs)) != 1 or int(w.Write(str(path))) != 1: raise RuntimeError("STEP write failed")
    box=src/"box.step"
    if not box.is_file(): shutil.copyfile(Path("tests/benchmarks/box.step"),box)
    sphere=src/"sphere.step"
    if not sphere.is_file(): write(BRepPrimAPI_MakeSphere(1.0).Shape(),sphere)
    gear=src/"gear.step"
    if not gear.is_file():
        shape=BRepPrimAPI_MakeCylinder(.55,.30).Shape()
        for i in range(8):
            tooth=BRepPrimAPI_MakeBox(.75,.18,.30).Shape(); t=gp_Trsf()
            t.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),i*math.pi/4)
            shape=BRepAlgoAPI_Fuse(shape,BRepBuilderAPI_Transform(tooth,t,True).Shape()).Shape()
        write(shape,gear)
    naca=src/"naca0012.step"
    if not naca.is_file():
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace,BRepBuilderAPI_MakePolygon
        from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
        from OCP.gp import gp_Pnt,gp_Vec
        poly=BRepBuilderAPI_MakePolygon(); n=50; t=.12
        pts=[]
        for i in range(n-1,-1,-1):
            x=i/(n-1); y=5*t*(.2969*math.sqrt(max(x,0))-.126*x-.3516*x*x+.2843*x**3-.1015*x**4); pts.append((x,y))
        for i in range(1,n):
            x=i/(n-1); y=5*t*(.2969*math.sqrt(max(x,0))-.126*x-.3516*x*x+.2843*x**3-.1015*x**4); pts.append((x,-y))
        for x,y in pts: poly.Add(gp_Pnt(x,y,0))
        poly.Close(); write(BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(poly.Wire()).Face(),gp_Vec(0,0,.4)).Shape(),naca)
    return {"cube":box,"sphere":sphere,"naca":naca,"gear":gear}

def load_cad(path: Path):
    cad=load_cad_native_with_provenance(path,".step"); p=cad.provenance
    groups=tuple(f"{path.stem}-face-{i}" for i in range(p.face_count))
    p=replace(p,physical_group_names=groups,physical_groups_authoritative=True)
    triangle_groups=tuple(groups[int(i)] for i in p.triangle_face_ordinals)
    if path.stem == "sphere":
        vertices=np.asarray(cad.vertices,dtype=np.float64)
        faces=np.asarray(cad.faces,dtype=np.int64)
    else:
        vertices=np.asarray(cad.vertices[p.canonical_vertex_source_ids],dtype=np.float64)
        faces=np.asarray(p.oriented_canonical_faces,dtype=np.int64)
    return vertices,faces,p,triangle_groups

def run_tet(root,row_id,source,density):
    from core.generator.native_tet.mesher import generate_native_tet
    m=read_stl(source); cases=[]; certs=[]; os.environ["AUTO_TESSELL_P4C_PYTETWILD"]="0"
    for i in range(3):
        c=root/row_id/f"run-{i}"; r=generate_native_tet(np.asarray(m.vertices),np.asarray(m.faces),c,seed_density=density,sliver_quality_threshold=0.0,enable_same_side_retriangulation=True,enable_phase_a=False,recovery_iterations=0,smooth_iterations=0)
        if not r.success: raise RuntimeError(r.message)
        cert=certify_native_tet_release_output(c,source,m.vertices,m.faces,r.tet_points,r.tets,source_feature_ids=("none",)*len(m.faces),source_patch_ids=("wall",)*len(m.faces),source_physical_groups=("wall",)*len(m.faces),debug_info=r.debug_info)
        if not cert.authoritative: raise RuntimeError(str(cert.as_dict()))
        cases.append(c); certs.append(cert.as_dict())
    return volume_row(row_id,"tet",source.name,"native_tet_independent_release",source,cases,certs)

def run_hex(root,row_id,source,target):
    v,f,p,g=load_cad(source); cases=[]; certs=[]; selected=0
    for i in range(3):
        c=root/row_id/f"run-{i}"; r=generate_native_hex(v,f,c,target_edge_length=target,seed_density=10,snap_boundary=True,source_path=source,source_vertices=v,source_faces=f,source_provenance=p)
        if not r.success or r.source_output_binding is None: raise RuntimeError(r.message)
        names=[str(x["name"]) for x in parse_foam_boundary(c/"constant"/"polyMesh"/"boundary")]
        ok,msg,selected=_run_native_hex_bl(c,num_layers=1,growth_ratio=1.2,first_thickness=.0001,params={"post_layers_hex_inward_shell":True,"post_layers_hex_general_inward_shell":True,"post_layers_wall_patch_names":names})
        if not ok: raise RuntimeError(msg)
        e=certify_native_hex_release_output(c,source,v,f,r.source_output_binding,source_feature_ids=("feature",)*len(f),source_patch_ids=g,source_physical_groups=g)
        if not e["authoritative"]: raise RuntimeError(str(e))
        cases.append(c); certs.append(e)
    return volume_row(row_id,"hex",source.name,"native_hex_cad_brep_release",source,cases,certs,1,.0001,selected)
def poly_cert(case,source,count,patch):
    e=certify_native_poly_boundary_authority(case,source,source_patch_ids=("wall",)*count,source_physical_groups=("wall",)*count,expected_boundary_patch=patch,feature_preserved=True,provenance_complete=True).as_dict()
    return {"authoritative":e.get("authoritative"),"source_sha256":e.get("source_file_sha256"),"source_shape_sha256":e.get("source_shape_sha256"),"output_shape_sha256":e.get("output_shape_sha256"),"feature_sha256":phash(("feature",)*count),"patch_sha256":e.get("source_patch_sha256"),"physical_group_sha256":e.get("source_physical_group_sha256"),"provenance_sha256":phash({"source":str(source),"output":e.get("output_artifact_sha256")}),"shape_preserved":e.get("shape_preserved") is True,"source_vertices_preserved":False,"source_faces_preserved":e.get("boundary_source_bound") is True,"feature_preserved":e.get("feature_preserved") is True,"patch_preserved":e.get("boundary_source_bound") is True,"physical_groups_preserved":e.get("physical_groups_preserved") is True,"component_bijection":e.get("boundary_source_bound") is True,"provenance_complete":e.get("provenance_complete") is True}

def run_poly(root,row_id,source,mode):
    m=read_stl(source); cases=[]; certs=[]; os.environ["AUTO_TESSELL_P4C_PYTETWILD"]="0"; patch=f"source_0_{source.stem}"
    for i in range(3):
        c=root/row_id/f"run-{i}"
        if mode=="release": r=_runner(np.asarray(m.vertices),np.asarray(m.faces),c,release_route=True,source_path=source)
        else: r=run_native_poly_harness(np.asarray(m.vertices),np.asarray(m.faces),c,seed_density=8,max_iter=1,max_tet_cells=15000,boundary_face_classifier=SourceSurfacePatchClassifier([source]))
        if not r.success: raise RuntimeError(r.message)
        bl=run_poly_bl_transition(c,num_layers=1,growth_ratio=1.2,first_thickness=1e-4,wall_patch_names=[patch],apply_bulk_dual=False)
        if not bl.success or bl.n_prism_cells<=0: raise RuntimeError(bl.message)
        e=poly_cert(c,source,len(m.faces),patch)
        if not e["authoritative"]: raise RuntimeError(str(e))
        cases.append(c); certs.append(e); positive=bl.n_prism_cells
    return volume_row(row_id,"poly",source.name,"native_poly_release_with_strict_bl",source,cases,certs,1,1e-4,positive)

def run_tri(root,row_id,source,v,f,groups,source_provenance=None):
    os.environ["AUTO_TESSELL_NATIVE_TRI_RELEASE"]="1"
    edge=np.concatenate([np.linalg.norm(v[f[:,j]]-v[f[:,(j+1)%3]],axis=1) for j in range(3)])
    if source.stem == "sphere_watertight":
        target_edge = 0.3
    elif source.stem == "naca0012":
        target_edge = 0.15
    elif source.suffix.lower() in {".step", ".stp", ".iges", ".igs", ".brep"}:
        target_edge = 0.3
    else:
        target_edge = float(np.median(edge) * 0.5)
    auth=NativeTriSourceAuthority(groups,AuthoritativePhysicalGroupMapping(groups,True),(),True)
    audits=[]; certs=[]
    for i in range(3):
        r=run_native_tri_release(v,f,target_edge_length=target_edge,source_authority=auth,max_rounds=1,source_path=source,source_provenance=source_provenance)
        if not r.accepted: raise RuntimeError(str(r))
        c=root/row_id/f"run-{i}"; a=surface_package(c,r.vertices,r.faces); e=certify_native_tri_release_result(r,source,f)
        if not e.get("authoritative"): raise RuntimeError(str(e))
        audits.append(a); certs.append(e)
    return surface_row(row_id,"tri",source.name,"native_tri_independent_transaction_release",sha(source),audits,certs)
def run_quad(root,row_id,complex_source,mixed):
    import os
    from unittest.mock import patch
    from core.preprocessor.native_quad.strict_pair_transaction_l0 import materialize_strict_quad_pair_transaction_l0
    from core.preprocessor.native_quad.strict_quad_fixed_pair_writer_l0 import write_strict_quad_fixed_pair_product_l0
    from core.preprocessor.native_quad.tri_quad_fixed_pair_product_l0 import AuthoritativeTriQuadFeatureEdges,AuthoritativeTriQuadPatchIds,materialize_tri_quad_fixed_pair_product_l0
    from core.preprocessor.native_quad.tri_quad_fixed_pair_writer_l0 import write_tri_quad_fixed_pair_product_l0
    if complex_source:
        from tests.test_native_surface_complex_release_corpus import _products,_stepped_prism
        v,t,pairs,patches,features=_stepped_prism(); strict,mix=_products(); src=root/"sources"/f"{row_id}.snapshot"; src.write_bytes(b"stepped-source-v1")
    else:
        from tests.test_native_strict_quad_fixed_pair_product_l0 import _cube
        v,t,_q,pairs,features,patches,_g=_cube(); groups=AuthoritativePhysicalGroupMapping(tuple("wall" for _ in patches),True)
        with patch.dict(os.environ,{"AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0":"1","AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_PRODUCT_L0":"1"}):
            strict_tx=materialize_strict_quad_pair_transaction_l0(v,t,pairs,features,source_patch_ids=patches,source_physical_groups=groups)
            mix_tx=materialize_tri_quad_fixed_pair_product_l0(v,t,np.asarray(((0,1),),dtype=np.int64),AuthoritativeTriQuadFeatureEdges(tuple(map(tuple,features.tolist())),True),source_patch_ids=AuthoritativeTriQuadPatchIds(tuple(patches),True),source_physical_groups=groups)
        strict,mix=strict_tx.product_result,mix_tx; src=root/"sources"/f"{row_id}.snapshot"; src.parent.mkdir(parents=True,exist_ok=True); src.write_bytes(b"cube-source-v1")
    audits=[]; certs=[]
    (root/row_id).mkdir(parents=True,exist_ok=True)
    for i in range(3):
        with patch.dict(os.environ,{"AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0":"1","AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_WRITER_L0":"1","AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_PRODUCT_L0":"1","AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_WRITER_L0":"1"}):
            if mixed: written=write_tri_quad_fixed_pair_product_l0(mix,root/row_id/f"run-{i}"); prod=mix
            else: written=write_strict_quad_fixed_pair_product_l0(strict,root/row_id/f"run-{i}"); prod=strict
        e=certify_fixed_pair_surface_output(prod,written,src,v,t)
        if not e.get("authoritative"): raise RuntimeError(str(e))
        audits.append(dict(e["surface_topology"])); certs.append(e)
    return surface_row(row_id,"tri-quad" if mixed else "strict-quad","complex" if complex_source else "cube","independent_fixed_pair_surface_writer",sha(src),audits,certs)

def build(output: Path):
    output.mkdir(parents=True,exist_ok=False); root=output/"cases"; root.mkdir(); sources=make_cad_sources(output); rows=[]; errors={}
    def add(row_id,fn):
        try: rows.append(fn())
        except Exception as exc: errors[row_id]=f"{type(exc).__name__}: {exc}"; rows.append(unverified(row_id,row_id.split("-")[1],row_id.rsplit("-",1)[-1],errors[row_id]))
    stls={"cube":(Path("tests/benchmarks/cube.stl"),4),"sphere":(Path("tests/benchmarks/sphere_watertight.stl"),8),"naca":(Path("tests/benchmarks/naca0012.stl"),6),"complex":(Path("tests/benchmarks/trimesh_duct.stl"),6)}
    for n,(s,d) in stls.items(): add(f"native-tet-{n}",lambda n=n,s=s,d=d:run_tet(root,f"native-tet-{n}",s,d))
    for n,t in (("cube",.25),("sphere",.4),("naca",.15),("gear",.3)): add(f"native-hex-{n}",lambda n=n,t=t:run_hex(root,f"native-hex-{n}",sources[n],t))
    for n,s,m in (("cube",stls["cube"][0],"harness"),("sphere",stls["sphere"][0],"harness"),("naca",stls["naca"][0],"release"),("gear",Path("tests/stl/04_extreme_gear.stl"),"release")): add(f"native-poly-{n}",lambda n=n,s=s,m=m:run_poly(root,f"native-poly-{n}",s,m))
    for n,s in (("cube",stls["cube"][0]),("sphere",stls["sphere"][0]),("naca",stls["naca"][0])):
        m=read_stl(s); add(f"native-tri-{n}",lambda n=n,s=s,m=m:run_tri(root,f"native-tri-{n}",s,np.asarray(m.vertices),np.asarray(m.faces),tuple(f"{n}-wall" for _ in m.faces)))
    cad=load_cad_native_with_provenance(sources["cube"],".step"); p=replace(cad.provenance,physical_group_names=tuple(f"brep-face-{i}" for i in range(cad.provenance.face_count)),physical_groups_authoritative=True); v=np.asarray(cad.vertices[p.canonical_vertex_source_ids]); f=np.asarray(p.oriented_canonical_faces); g=tuple(p.physical_group_names[int(i)] for i in p.triangle_face_ordinals)
    add("native-tri-cad",lambda:run_tri(root,"native-tri-cad",sources["cube"],v,f,g,p))
    for n,cs,m in (("strict-quad-cube",False,False),("strict-quad-complex",True,False),("tri-quad-cube",False,True),("tri-quad-complex",True,True)): add(n,lambda n=n,cs=cs,m=m:run_quad(root,n,cs,m))
    manifest={"schema":RELEASE_MATRIX_SCHEMA,"cases":rows}; report=validate_native_release_authority_matrix(manifest); (output/"native_release_manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n"); (output/"native_release_authority_gate.json").write_text(json.dumps(report.as_dict(),sort_keys=True,indent=2)+"\n"); (output/"errors.json").write_text(json.dumps(errors,sort_keys=True,indent=2)+"\n"); return report

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,default=Path("docs/qa/native_release_campaign_20260801")); a=ap.parse_args()
    try: r=build(a.output)
    except Exception as exc: print(json.dumps({"status":"failed","error":f"{type(exc).__name__}: {exc}"})); raise
    print(json.dumps(r.as_dict(),sort_keys=True)); raise SystemExit(0 if r.valid else 1)
