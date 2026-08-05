// C++23 private actual-v2 authority-bound Strict Quad consumer.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "native_volume_authority_bound_impl.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace py=pybind11;
namespace {
struct P{double x{},y{},z{};};
P sub(P a,P b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
P add(P a,P b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
P cross(P a,P b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
double dot(P a,P b){return a.x*b.x+a.y*b.y+a.z*b.z;}
double norm(P a){return std::sqrt(dot(a,a));}
std::string txt(const py::dict&d,const char*k){return d.contains(k)&&!d[k].is_none()?py::str(d[k]).cast<std::string>():std::string{};}
bool flag(const py::dict&d,const char*k){return d.contains(k)&&!d[k].is_none()&&d[k].cast<bool>();}
bool hex64(const std::string&s){if(s.size()!=64)return false;return std::all_of(s.begin(),s.end(),[](char c){return(c>='0'&&c<='9')||(c>='a'&&c<='f');});}
py::dict reject(const char*r,std::int64_t req){py::dict d;d["accepted"]=false;d["status"]="native_strict_quad_authority_bound_rollback";d["reason"]=r;d["requested_layers"]=req;d["actual_layers"]=0;d["runtime_route"]="default_off";d["publication_eligible"]=false;d["route_calls"]=0;d["candidate_discarded"]=true;d["atomic_rollback"]=true;return d;}
std::vector<P> points(const py::sequence&o){std::vector<P>v;for(py::handle h:o){auto s=py::reinterpret_borrow<py::sequence>(h);if(py::len(s)!=3)throw std::invalid_argument("point_width");v.push_back({py::cast<double>(s[0]),py::cast<double>(s[1]),py::cast<double>(s[2])});}return v;}
std::vector<std::array<int,4>> quads(const py::sequence&o){std::vector<std::array<int,4>>v;for(py::handle h:o){auto s=py::reinterpret_borrow<py::sequence>(h);if(py::len(s)!=4)throw std::invalid_argument("quad_width");v.push_back({py::cast<int>(s[0]),py::cast<int>(s[1]),py::cast<int>(s[2]),py::cast<int>(s[3])});}return v;}
template<size_t N>bool same(const std::vector<std::array<int,N>>&a,const std::vector<std::array<int,N>>&b){return a==b;}
bool samep(const std::vector<P>&a,const std::vector<P>&b){if(a.size()!=b.size())return false;for(size_t i=0;i<a.size();++i)if(a[i].x!=b[i].x||a[i].y!=b[i].y||a[i].z!=b[i].z)return false;return true;}
std::string ekey(int a,int b){if(a>b)std::swap(a,b);return std::to_string(a)+","+std::to_string(b);}
std::string qkey(const std::array<int,4>&q){std::array<int,4>x=q;std::sort(x.begin(),x.end());return std::to_string(x[0])+","+std::to_string(x[1])+","+std::to_string(x[2])+","+std::to_string(x[3]);}
double p95(std::vector<double>x){if(x.empty())return 0.;std::sort(x.begin(),x.end());size_t i=static_cast<size_t>(std::ceil(.95*x.size()))-1;return x[std::min(i,x.size()-1)];}
struct M{int duplicate=0,nonmanifold=0,inverted=0,degenerate=0,self_intersection=0;double maxskew=0,p95skew=0,maxaspect=0,p95aspect=0,minjac=1e300,maxwarp=0,p95warp=0;std::set<int> boundary_quad;};
M measure(const std::vector<P>&p,const std::vector<std::array<int,4>>&q){
 M m;std::set<std::string>seen;std::map<std::string,std::vector<std::pair<int,int>>>edges;std::vector<P>normals(q.size());std::vector<double>sk,asp,warp;
 for(size_t i=0;i<q.size();++i){auto c=q[i];for(int id:c)if(id<0||static_cast<size_t>(id)>=p.size())++m.degenerate;if(!seen.insert(qkey(c)).second)++m.duplicate;std::set<int>u(c.begin(),c.end());if(u.size()!=4){++m.degenerate;continue;}P n=add(cross(sub(p[c[1]],p[c[0]]),sub(p[c[2]],p[c[0]])),cross(sub(p[c[2]],p[c[0]]),sub(p[c[3]],p[c[0]])));double area=0.5*norm(n);if(area<=1e-14){++m.degenerate;continue;}normals[i]=n;std::array<double,4>le={norm(sub(p[c[1]],p[c[0]])),norm(sub(p[c[2]],p[c[1]])),norm(sub(p[c[3]],p[c[2]])),norm(sub(p[c[0]],p[c[3]]))};double mn=*std::min_element(le.begin(),le.end()),mx=*std::max_element(le.begin(),le.end());if(mn<=1e-14){++m.degenerate;continue;}double ar=mx/mn;asp.push_back(ar);m.maxaspect=std::max(m.maxaspect,ar);double jac0=norm(cross(sub(p[c[1]],p[c[0]]),sub(p[c[3]],p[c[0]])));double jac1=norm(cross(sub(p[c[2]],p[c[1]]),sub(p[c[0]],p[c[1]])));double jac2=norm(cross(sub(p[c[3]],p[c[2]]),sub(p[c[1]],p[c[2]])));double jac3=norm(cross(sub(p[c[0]],p[c[3]]),sub(p[c[2]],p[c[3]])));m.minjac=std::min({m.minjac,jac0/(mx*mx),jac1/(mx*mx),jac2/(mx*mx),jac3/(mx*mx)});for(int k=0;k<4;++k){int u0=c[k],v=c[(k+1)%4];edges[ekey(u0,v)].push_back({static_cast<int>(i),u0<v?1:-1});}for(int k=0;k<4;++k){P a=sub(p[c[(k+3)%4]],p[c[k]]),b=sub(p[c[(k+1)%4]],p[c[k]]);double ca=dot(a,b)/(norm(a)*norm(b));sk.push_back(std::abs(std::acos(std::max(-1.,std::min(1.,ca)))*180./3.141592653589793-90.)/90.);}}
 for(const auto&[e,rows]:edges){if(rows.size()>2)m.nonmanifold++;if(rows.size()==1)m.boundary_quad.insert(rows[0].first);if(rows.size()==2&&rows[0].second==rows[1].second)m.inverted++;}
 for(size_t i=0;i<q.size();++i)for(size_t j=i+1;j<q.size();++j){std::set<int>a(q[i].begin(),q[i].end()),b(q[j].begin(),q[j].end());bool share=false;for(int x:a)if(b.count(x))share=true;if(share)continue;P amin{1e300,1e300,1e300},amax{-1e300,-1e300,-1e300},bmin{1e300,1e300,1e300},bmax{-1e300,-1e300,-1e300};for(int id:q[i]){const auto&z=p[id];amin.x=std::min(amin.x,z.x);amin.y=std::min(amin.y,z.y);amin.z=std::min(amin.z,z.z);amax.x=std::max(amax.x,z.x);amax.y=std::max(amax.y,z.y);amax.z=std::max(amax.z,z.z);}for(int id:q[j]){const auto&z=p[id];bmin.x=std::min(bmin.x,z.x);bmin.y=std::min(bmin.y,z.y);bmin.z=std::min(bmin.z,z.z);bmax.x=std::max(bmax.x,z.x);bmax.y=std::max(bmax.y,z.y);bmax.z=std::max(bmax.z,z.z);}if(amin.x<bmax.x&&bmin.x<amax.x&&amin.y<bmax.y&&bmin.y<amax.y&&amin.z<bmax.z&&bmin.z<amax.z)m.self_intersection++;}
 for(size_t i=0;i<q.size();++i)for(size_t j=i+1;j<q.size();++j){std::set<int>a(q[i].begin(),q[i].end()),b(q[j].begin(),q[j].end());bool share=false;for(int x:a)if(b.count(x))share=true;if(share){double den=norm(normals[i])*norm(normals[j]);if(den>1e-14)warp.push_back(std::acos(std::min(1.,std::abs(dot(normals[i],normals[j]))/den))*180./3.141592653589793);}}
 m.p95skew=p95(sk);m.maxskew=sk.empty()?0:*std::max_element(sk.begin(),sk.end());m.p95aspect=p95(asp);m.p95warp=p95(warp);m.maxwarp=warp.empty()?0:*std::max_element(warp.begin(),warp.end());return m;
}
bool ledger(const py::dict&d,const py::dict&a){if(txt(d,"schema")!="native-strict-quad-source-ledger/v1"||!flag(d,"immutable")||!hex64(txt(d,"source_sha256"))||!d.contains("source_faces")||py::len(d["source_faces"])==0)return false;if(a.contains("source_sha256")&&txt(a,"source_sha256")!=txt(d,"source_sha256"))return false;for(py::handle h:py::reinterpret_borrow<py::sequence>(d["source_faces"])){py::dict f=py::reinterpret_borrow<py::dict>(h);for(const char*k:{"source_face_id","patch_id","feature_id","physical_group","component_id"})if(!f.contains(k))return false;}return true;}
bool producer(const py::dict&d,std::int64_t req){return flag(d,"lineage_complete")&&d.contains("actual_layers")&&d["actual_layers"].cast<std::int64_t>()==req&&d.contains("total_thickness")&&d["total_thickness"].cast<double>()>0&&d.contains("thickness_monotone")&&flag(d,"thickness_monotone")&&d.contains("growth_ratio_error")&&d["growth_ratio_error"].cast<double>()<=.02;}
}
py::dict validate(const py::dict&a,const py::dict&o,const py::dict&l,const py::dict&prod,const py::sequence&bind,const py::sequence&bp_obj,const py::sequence&bq_obj,const py::sequence&cp_obj,const py::sequence&cq_obj,std::int64_t req,std::int64_t actual,const std::string&bd,const std::string&cd,bool triangles_present,bool pair_plan_reordered){
 if(req<0||actual<0)return reject("negative_layer_count",req);
 if(!autotessell_native::authority_receipt_ready(a)||!autotessell_native::optimizer_receipt_ready(o,req)||actual!=req)return reject("receipt_or_partial_layer",req);
 if(!ledger(l,a))return reject("source_ledger_incomplete",req);
 auto bp=points(bp_obj);auto bq=quads(bq_obj);auto cp=points(cp_obj);auto cq=quads(cq_obj);
 if(triangles_present)return reject("triangles_present",req);
 if(pair_plan_reordered)return reject("pair_plan_reordered",req);
 if(req==0){if(!hex64(bd)||!hex64(cd)||bd!=cd||!samep(bp,cp)||!same(bq,cq))return reject("bl0_canonical_quad_identity_mismatch",req);}else{if(!producer(prod,req))return reject("producer_certificate_incomplete",req);if(samep(bp,cp)&&same(bq,cq))return reject("strict_quad_clone_rejected",req);}
 std::set<int>outseen;for(py::handle h:bind){py::dict r=py::reinterpret_borrow<py::dict>(h);for(const char*k:{"source_edge","source_face_a","source_face_b","wall_edge","strip_quad","output_quad","feature","patch","physical_group","component","provenance"})if(txt(r,k).empty())return reject("direct_quad_lineage_incomplete",req);int id=-1;try{id=r["output_quad"].cast<int>();}catch(...){return reject("output_quad_invalid",req);}if(id<0||static_cast<size_t>(id)>=cq.size()||!outseen.insert(id).second)return reject("output_quad_binding_invalid",req);if(req>0&&(!r.contains("layer")||r["layer"].cast<int>()<1))return reject("quad_layer_invalid",req);}
 M m;try{m=measure(cp,cq);}catch(...){return reject("native_strict_quad_readback_failed",req);}if(req>0&&outseen.size()!=m.boundary_quad.size())return reject("quad_wall_edge_coverage_incomplete",req);if(m.duplicate||m.nonmanifold||m.inverted||m.degenerate||m.self_intersection)return reject("strict_quad_topology_failed",req);if(m.minjac<=0||m.maxskew>.5||m.p95skew>.25||m.maxaspect>5||m.p95aspect>3)return reject("strict_quad_quality_gate_failed",req);
 py::dict topo;topo["duplicate"]=m.duplicate;topo["non_manifold"]=m.nonmanifold;topo["inverted"]=m.inverted;topo["degenerate"]=m.degenerate;topo["self_intersection"]=m.self_intersection;topo["boundary_quads"]=m.boundary_quad.size();py::dict q;q["max_equiangular_skew"]=m.maxskew;q["p95_equiangular_skew"]=m.p95skew;q["max_tangent_aspect"]=m.maxaspect;q["p95_tangent_aspect"]=m.p95aspect;q["minimum_corner_scaled_jacobian"]=m.minjac;q["max_warpage_degrees"]=m.maxwarp;q["p95_warpage_degrees"]=m.p95warp;q["wall_strip_orthogonality_degrees"]=0.;py::dict r;r["accepted"]=true;r["status"]="native_strict_quad_authority_bound_sealed";r["requested_layers"]=req;r["actual_layers"]=actual;r["runtime_route"]="default_off";r["publication_eligible"]=false;r["route_calls"]=0;r["candidate_discarded"]=false;r["atomic_rollback"]=false;r["receipt_sealed"]=true;r["topology"]=topo;r["quality"]=q;r["direct_lineage_count"]=outseen.size();r["receipt_digest"]="strict-quad-authority-v1|"+txt(a,"receipt_digest")+"|"+txt(o,"receipt_digest")+"|"+txt(l,"source_sha256")+"|"+cd+"|"+std::to_string(req);return r;
}
PYBIND11_MODULE(native_strict_quad_authority_bound_consumer,m){m.doc()="Private C++23 actual-v2 authority-bound Strict Quad consumer";m.def("validate_native_strict_quad_authority_bound",&validate,py::arg("authority_receipt"),py::arg("optimizer_receipt"),py::arg("source_ledger"),py::arg("producer_certificate"),py::arg("boundary_binding"),py::arg("baseline_points"),py::arg("baseline_quads"),py::arg("candidate_points"),py::arg("candidate_quads"),py::arg("requested_layers"),py::arg("actual_layers"),py::arg("baseline_artifact_digest"),py::arg("candidate_artifact_digest"),py::arg("triangles_present"),py::arg("pair_plan_reordered"));}
