// C++23 private actual-v2 authority-bound Native Tri consumer.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "native_volume_authority_bound_impl.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace py=pybind11;
namespace {
struct P{double x{},y{},z{};};
P sub(P a,P b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
P cross(P a,P b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
double dot(P a,P b){return a.x*b.x+a.y*b.y+a.z*b.z;}
double norm(P a){return std::sqrt(dot(a,a));}
std::string txt(const py::dict& d,const char* k){return d.contains(k)&&!d[k].is_none()?py::str(d[k]).cast<std::string>():std::string{};}
bool flag(const py::dict& d,const char* k){return d.contains(k)&&!d[k].is_none()&&d[k].cast<bool>();}
bool hex64(const std::string&s){if(s.size()!=64)return false;return std::all_of(s.begin(),s.end(),[](char c){return(c>='0'&&c<='9')||(c>='a'&&c<='f');});}
py::dict reject(const char*r,std::int64_t req){py::dict d;d["accepted"]=false;d["status"]="native_tri_authority_bound_rollback";d["reason"]=r;d["requested_layers"]=req;d["actual_layers"]=0;d["runtime_route"]="default_off";d["publication_eligible"]=false;d["route_calls"]=0;d["candidate_discarded"]=true;d["atomic_rollback"]=true;return d;}
std::vector<P> points(const py::sequence&o){std::vector<P>v;for(py::handle h:o){auto s=py::reinterpret_borrow<py::sequence>(h);if(py::len(s)!=3)throw std::invalid_argument("point_width");v.push_back({py::cast<double>(s[0]),py::cast<double>(s[1]),py::cast<double>(s[2])});}return v;}
std::vector<std::array<int,3>> tris(const py::sequence&o){std::vector<std::array<int,3>>v;for(py::handle h:o){auto s=py::reinterpret_borrow<py::sequence>(h);if(py::len(s)!=3)throw std::invalid_argument("triangle_width");v.push_back({py::cast<int>(s[0]),py::cast<int>(s[1]),py::cast<int>(s[2])});}return v;}
template<size_t N>bool same(const std::vector<std::array<int,N>>&a,const std::vector<std::array<int,N>>&b){return a==b;}
bool samep(const std::vector<P>&a,const std::vector<P>&b){if(a.size()!=b.size())return false;for(size_t i=0;i<a.size();++i)if(a[i].x!=b[i].x||a[i].y!=b[i].y||a[i].z!=b[i].z)return false;return true;}
std::string ekey(int a,int b){if(a>b)std::swap(a,b);return std::to_string(a)+","+std::to_string(b);}
std::string tkey(const std::array<int,3>&t){std::array<int,3>x=t;std::sort(x.begin(),x.end());return std::to_string(x[0])+","+std::to_string(x[1])+","+std::to_string(x[2]);}
double p95(std::vector<double>x){if(x.empty())return 0.;std::sort(x.begin(),x.end());size_t i=static_cast<size_t>(std::ceil(.95*x.size()))-1;return x[std::min(i,x.size()-1)];}
struct M{int duplicate=0,nonmanifold=0,inverted=0,degenerate=0,self_intersection=0;double maxno=0,p95no=0,maxskew=0,p95skew=0,maxaspect=0,p95aspect=0,minjac=1e300,minangle=180.;std::set<int> boundary_tri;};
M measure(const std::vector<P>&p,const std::vector<std::array<int,3>>&t){
 M m;std::set<std::string> seen;std::map<std::string,std::vector<std::pair<int,int>>> edges;std::vector<P> normals(t.size());std::vector<double> sk,asp,no,angles;
 for(size_t i=0;i<t.size();++i){auto c=t[i];if(c[0]<0||c[1]<0||c[2]<0||static_cast<size_t>(c[0])>=p.size()||static_cast<size_t>(c[1])>=p.size()||static_cast<size_t>(c[2])>=p.size()){++m.degenerate;continue;}if(!seen.insert(tkey(c)).second)++m.duplicate;P n=cross(sub(p[c[1]],p[c[0]]),sub(p[c[2]],p[c[0]]));double a=0.5*norm(n);normals[i]=n;if(a<=1e-14){++m.degenerate;continue;}std::array<double,3> le={norm(sub(p[c[1]],p[c[0]])),norm(sub(p[c[2]],p[c[1]])),norm(sub(p[c[0]],p[c[2]]))};double mn=*std::min_element(le.begin(),le.end()),mx=*std::max_element(le.begin(),le.end());if(mn<=1e-14){++m.degenerate;continue;}double ar=mx/mn;asp.push_back(ar);m.maxaspect=std::max(m.maxaspect,ar);sk.push_back(.5*(1.-mn/mx));m.minjac=std::min(m.minjac,a/(mx*mx));for(int q=0;q<3;++q){int u=c[q],v=c[(q+1)%3];edges[ekey(u,v)].push_back({static_cast<int>(i),u<v?1:-1});}double cos0=dot(sub(p[c[1]],p[c[0]]),sub(p[c[2]],p[c[0]]))/(le[0]*le[2]);double cos1=dot(sub(p[c[0]],p[c[1]]),sub(p[c[2]],p[c[1]]))/(le[0]*le[1]);double cos2=dot(sub(p[c[0]],p[c[2]]),sub(p[c[1]],p[c[2]]))/(le[2]*le[1]);for(double z:{cos0,cos1,cos2})angles.push_back(std::acos(std::max(-1.,std::min(1.,z)))*180./3.141592653589793);}
 for(const auto&[e,rows]:edges){if(rows.size()>2)m.nonmanifold++;if(rows.size()==1)m.boundary_tri.insert(rows[0].first);if(rows.size()==2&&rows[0].second==rows[1].second)m.inverted++;}
 for(size_t i=0;i<t.size();++i)for(size_t j=i+1;j<t.size();++j){std::set<int>a(t[i].begin(),t[i].end()),b(t[j].begin(),t[j].end());bool share=false;for(int x:a)if(b.count(x))share=true;if(share)continue;P amin{1e300,1e300,1e300},amax{-1e300,-1e300,-1e300},bmin{1e300,1e300,1e300},bmax{-1e300,-1e300,-1e300};for(int id:t[i]){const auto&q=p[id];amin.x=std::min(amin.x,q.x);amin.y=std::min(amin.y,q.y);amin.z=std::min(amin.z,q.z);amax.x=std::max(amax.x,q.x);amax.y=std::max(amax.y,q.y);amax.z=std::max(amax.z,q.z);}for(int id:t[j]){const auto&q=p[id];bmin.x=std::min(bmin.x,q.x);bmin.y=std::min(bmin.y,q.y);bmin.z=std::min(bmin.z,q.z);bmax.x=std::max(bmax.x,q.x);bmax.y=std::max(bmax.y,q.y);bmax.z=std::max(bmax.z,q.z);}if(amin.x<bmax.x&&bmin.x<amax.x&&amin.y<bmax.y&&bmin.y<amax.y&&amin.z<bmax.z&&bmin.z<amax.z)m.self_intersection++;}
 for(const auto&[e,rows]:edges)if(rows.size()==2){P a=normals[rows[0].first],b=normals[rows[1].first];double den=norm(a)*norm(b);no.push_back(den>1e-14?std::acos(std::min(1.,std::abs(dot(a,b))/den))*180./3.141592653589793:90.);}
 m.p95no=p95(no);m.maxno=no.empty()?0:*std::max_element(no.begin(),no.end());m.p95skew=p95(sk);m.maxskew=sk.empty()?0:*std::max_element(sk.begin(),sk.end());m.p95aspect=p95(asp);m.minangle=angles.empty()?0:*std::min_element(angles.begin(),angles.end());return m;
}
bool ledger(const py::dict&d,const py::dict&a){if(txt(d,"schema")!="native-tri-source-ledger/v1"||!flag(d,"immutable")||!hex64(txt(d,"source_sha256"))||!d.contains("source_faces")||py::len(d["source_faces"])==0)return false;if(a.contains("source_sha256")&&txt(a,"source_sha256")!=txt(d,"source_sha256"))return false;for(py::handle h:py::reinterpret_borrow<py::sequence>(d["source_faces"])){py::dict f=py::reinterpret_borrow<py::dict>(h);for(const char*k:{"source_face_id","patch_id","feature_id","physical_group","component_id"})if(!f.contains(k))return false;}return true;}
bool producer(const py::dict&d,std::int64_t req){return flag(d,"lineage_complete")&&d.contains("actual_layers")&&d["actual_layers"].cast<std::int64_t>()==req&&d.contains("total_thickness")&&d["total_thickness"].cast<double>()>0&&d.contains("thickness_monotone")&&flag(d,"thickness_monotone")&&d.contains("growth_ratio_error")&&d["growth_ratio_error"].cast<double>()<=.02;}
}
py::dict validate(const py::dict&a,const py::dict&o,const py::dict&l,const py::dict&prod,const py::sequence&bind,const py::sequence&bp_obj,const py::sequence&bt_obj,const py::sequence&cp_obj,const py::sequence&ct_obj,std::int64_t req,std::int64_t actual,const std::string&bd,const std::string&cd,bool quad_relabel){
 if(req<0||actual<0) return reject("negative_layer_count",req);
 if(!autotessell_native::authority_receipt_ready(a)||!autotessell_native::optimizer_receipt_ready(o,req)||actual!=req) return reject("receipt_or_partial_layer",req);
 if(!ledger(l,a)) return reject("source_ledger_incomplete",req);
 auto bp=points(bp_obj); auto bt=tris(bt_obj); auto cp=points(cp_obj); auto ct=tris(ct_obj);
 if(req==0){if(!hex64(bd)||!hex64(cd)||bd!=cd||!samep(bp,cp)||!same(bt,ct))return reject("bl0_identity_mismatch",req);}
 else {if(!producer(prod,req))return reject("producer_certificate_incomplete",req);if(samep(bp,cp)&&same(bt,ct))return reject("tri_clone_rejected",req);if(quad_relabel||flag(prod,"quad_relabel"))return reject("quad_relabel_rejected",req);}
 std::set<int>outseen;for(py::handle h:bind){py::dict r=py::reinterpret_borrow<py::dict>(h);for(const char*k:{"source_edge","source_face","wall_edge","strip_face","output_face","feature","patch","physical_group","component","provenance"})if(txt(r,k).empty())return reject("direct_lineage_incomplete",req);int id=-1;try{id=r["output_face"].cast<int>();}catch(...){return reject("output_face_invalid",req);}if(id<0||static_cast<size_t>(id)>=ct.size()||!outseen.insert(id).second)return reject("output_face_binding_invalid",req);if(req>0&&(!r.contains("layer")||r["layer"].cast<int>()<1))return reject("wall_edge_layer_invalid",req);}
 M m;try{m=measure(cp,ct);}catch(...){return reject("native_tri_readback_failed",req);}if(req>0&&outseen.size()!=m.boundary_tri.size())return reject("wall_edge_output_coverage_incomplete",req);if(m.duplicate||m.nonmanifold||m.inverted||m.degenerate||m.self_intersection)return reject("strict_surface_topology_failed",req);if(m.maxno>50||m.p95no>35||m.maxskew>.5||m.p95skew>.25||m.p95aspect>3||m.maxaspect>5||m.minjac<=0||m.minangle<10)return reject("surface_quality_gate_failed",req);
 py::dict topo;topo["duplicate"]=m.duplicate;topo["non_manifold"]=m.nonmanifold;topo["inverted"]=m.inverted;topo["degenerate"]=m.degenerate;topo["self_intersection"]=m.self_intersection;py::dict q;q["max_non_orthogonality"]=m.maxno;q["p95_non_orthogonality"]=m.p95no;q["max_skewness"]=m.maxskew;q["p95_skewness"]=m.p95skew;q["p95_aspect"]=m.p95aspect;q["max_aspect"]=m.maxaspect;q["minimum_scaled_jacobian"]=m.minjac;q["minimum_angle"]=m.minangle;py::dict r;r["accepted"]=true;r["status"]="native_tri_authority_bound_sealed";r["requested_layers"]=req;r["actual_layers"]=actual;r["runtime_route"]="default_off";r["publication_eligible"]=false;r["route_calls"]=0;r["candidate_discarded"]=false;r["atomic_rollback"]=false;r["receipt_sealed"]=true;r["topology"]=topo;r["quality"]=q;r["direct_lineage_count"]=outseen.size();r["receipt_digest"]="tri-authority-v1|"+txt(a,"receipt_digest")+"|"+txt(o,"receipt_digest")+"|"+txt(l,"source_sha256")+"|"+cd+"|"+std::to_string(req);return r;
}
PYBIND11_MODULE(native_tri_authority_bound_consumer,m){m.doc()="Private C++23 Native Tri actual-v2 authority-bound consumer";m.def("validate_native_tri_authority_bound",&validate,py::arg("authority_receipt"),py::arg("optimizer_receipt"),py::arg("source_ledger"),py::arg("producer_certificate"),py::arg("boundary_binding"),py::arg("baseline_points"),py::arg("baseline_triangles"),py::arg("candidate_points"),py::arg("candidate_triangles"),py::arg("requested_layers"),py::arg("actual_layers"),py::arg("baseline_artifact_digest"),py::arg("candidate_artifact_digest"),py::arg("quad_relabel"));}
