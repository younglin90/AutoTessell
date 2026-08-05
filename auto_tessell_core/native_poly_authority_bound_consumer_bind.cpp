// C++23 private Native Poly actual-v2 authority-bound readback consumer.
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

namespace py = pybind11;
namespace {
struct V { double x{}, y{}, z{}; };
V sub(V a,V b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
V add(V a,V b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
V scale(V a,double s){return {a.x*s,a.y*s,a.z*s};}
V cross(V a,V b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
double dot(V a,V b){return a.x*b.x+a.y*b.y+a.z*b.z;}
double norm(V a){return std::sqrt(dot(a,a));}
std::string txt(const py::dict& d,const char* k){return d.contains(k)&&!d[k].is_none()?py::str(d[k]).cast<std::string>():std::string{};}
bool flag(const py::dict& d,const char* k){return d.contains(k)&&!d[k].is_none()&&d[k].cast<bool>();}
bool digest(const std::string& s){if(s.size()!=64)return false;return std::all_of(s.begin(),s.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});}
py::dict reject(const char* reason,std::int64_t req){py::dict r;r["accepted"]=false;r["status"]="native_poly_authority_bound_rollback";r["reason"]=reason;r["requested_layers"]=req;r["actual_layers"]=0;r["runtime_route"]="default_off";r["publication_eligible"]=false;r["route_calls"]=0;r["candidate_discarded"]=true;r["atomic_rollback"]=true;return r;}
std::vector<V> points(const py::sequence& obj){std::vector<V> out;for(py::handle h:obj){auto row=py::reinterpret_borrow<py::sequence>(h);if(py::len(row)!=3)throw std::invalid_argument("point_width");out.push_back({py::cast<double>(row[0]),py::cast<double>(row[1]),py::cast<double>(row[2])});}return out;}
std::vector<std::vector<int>> faces(const py::sequence& obj){std::vector<std::vector<int>> out;for(py::handle h:obj){auto row=py::reinterpret_borrow<py::sequence>(h);std::vector<int> f;for(py::handle x:row)f.push_back(py::cast<int>(x));out.push_back(std::move(f));}return out;}
std::vector<int> ints(const py::sequence& obj){std::vector<int> out;for(py::handle h:obj)out.push_back(py::cast<int>(h));return out;}
std::string face_key(const std::vector<int>& f){std::vector<int>x=f;std::sort(x.begin(),x.end());std::ostringstream s;for(int v:x)s<<v<<",";return s.str();}
int as_int(const py::dict& d,const char* k){if(!d.contains(k))return -1;try{return d[k].cast<int>();}catch(...){try{return std::stoi(py::str(d[k]).cast<std::string>());}catch(...){return -1;}}}
V face_center(const std::vector<V>& p,const std::vector<int>& f){V c{};for(int id:f)c=add(c,p[static_cast<std::size_t>(id)]);return scale(c,1.0/static_cast<double>(f.size()));}
V cell_center(const std::vector<V>& p,const std::set<int>& ids){V c{};for(int id:ids)c=add(c,p[static_cast<std::size_t>(id)]);return scale(c,1.0/static_cast<double>(ids.size()));}
double p95(std::vector<double> v){if(v.empty())return 0.0;std::sort(v.begin(),v.end());auto i=static_cast<std::size_t>(std::ceil(0.95*v.size()))-1;return v[std::min(i,v.size()-1)];}
struct M { int duplicate=0,nonmanifold=0,open=0,inverted=0,nonpositive=0,self_intersection=0; double max_no=0,p95_no=0,max_skew=0,p95_skew=0,max_aspect=0,p95_aspect=0,min_scaled=0; };
M measure(const std::vector<V>& p,const std::vector<std::vector<int>>& fs,const std::vector<int>& own,const std::vector<int>& nei){
    M m;std::set<std::string> seen;std::map<int,std::set<int>> cell_ids;std::vector<double> nos,skews,aspects;double min_scaled=1e300;for(std::size_t i=0;i<fs.size();++i){if(i<own.size()&&own[i]>=0)cell_ids[own[i]].insert(fs[i].begin(),fs[i].end());if(i<nei.size()&&nei[i]>=0)cell_ids[nei[i]].insert(fs[i].begin(),fs[i].end());}
    for(std::size_t i=0;i<fs.size();++i){const auto& f=fs[i];if(f.size()<3){++m.nonpositive;continue;}for(int id:f)if(id<0||static_cast<std::size_t>(id)>=p.size())++m.nonpositive;std::set<int> uniq(f.begin(),f.end());if(uniq.size()!=f.size())++m.nonpositive;if(!seen.insert(face_key(f)).second)++m.duplicate;if(i>=own.size()||own[i]<0)++m.nonmanifold;else{cell_ids[own[i]].insert(f.begin(),f.end());if(i<nei.size()&&nei[i]>=0){cell_ids[nei[i]].insert(f.begin(),f.end());if(nei[i]==own[i])++m.nonmanifold;}}if(f.size()>=3&&uniq.size()==f.size()){V n=cross(sub(p[f[1]],p[f[0]]),sub(p[f[2]],p[f[0]]));double area2=norm(n);if(area2<=1e-14){++m.nonpositive;continue;}double mn=1e300,mx=0;for(std::size_t a=0;a<f.size();++a)for(std::size_t b=a+1;b<f.size();++b){double d=norm(sub(p[f[a]],p[f[b]]));mn=std::min(mn,d);mx=std::max(mx,d);}if(mn<=1e-14){++m.nonpositive;continue;}double ar=mx/mn;aspects.push_back(ar);m.max_aspect=std::max(m.max_aspect,ar);V fc=face_center(p,f),cc=cell_center(p,cell_ids[own[i]]);V dir=sub(fc,cc);if(i<nei.size()&&nei[i]>=0&&cell_ids.count(nei[i]))dir=sub(cell_center(p,cell_ids[nei[i]]),cc);double den=norm(n)*norm(dir);double angle=den>1e-14?std::acos(std::min(1.0,std::abs(dot(n,dir))/den))*180.0/3.141592653589793:90.0;nos.push_back(angle);double skew=0.0;if(i<nei.size()&&nei[i]>=0&&cell_ids.count(nei[i])){V mid=scale(add(cc,cell_center(p,cell_ids[nei[i]])),0.5);skew=norm(sub(fc,mid))/std::max(mx,1e-14);}skews.push_back(skew);min_scaled=std::min(min_scaled,area2*std::max(norm(dir),1e-14));}}
    m.p95_no=p95(nos);m.max_no=nos.empty()?0:*std::max_element(nos.begin(),nos.end());m.p95_skew=p95(skews);m.max_skew=skews.empty()?0:*std::max_element(skews.begin(),skews.end());m.p95_aspect=p95(aspects);m.min_scaled=min_scaled==1e300?0:min_scaled;return m;
}
bool common_receipts(const py::dict& auth,const py::dict& opt,std::int64_t req){return autotessell_native::authority_receipt_ready(auth)&&autotessell_native::optimizer_receipt_ready(opt,req);}
bool ledger_ready(const py::dict& ledger,const py::dict& auth){if(txt(ledger,"schema")!="native-poly-source-ledger/v1"||!flag(ledger,"immutable"))return false;if(!digest(txt(ledger,"source_sha256")))return false;if(ledger.contains("source_sha256")&&auth.contains("source_sha256")&&txt(ledger,"source_sha256")!=txt(auth,"source_sha256"))return false;if(!ledger.contains("source_faces")||py::len(ledger["source_faces"])==0)return false;for(py::handle h:py::reinterpret_borrow<py::sequence>(ledger["source_faces"])){py::dict f=py::reinterpret_borrow<py::dict>(h);for(const char* k:{"source_face_id","ordered_vertex_ids","canonical_vertex_ids","patch_id","feature_id","physical_group","component_id"})if(!f.contains(k))return false;}return true;}
bool producer_ready(const py::dict& prod,const py::dict& part,std::int64_t req){if(!flag(prod,"lineage_complete")||!digest(txt(prod,"source_sha256"))||!digest(txt(prod,"candidate_source_sha256"))||!digest(txt(prod,"producer_mapping_sha256"))||!digest(txt(prod,"wall_edge_layer_sha256"))||!digest(txt(prod,"source_face_preservation_sha256"))||!digest(txt(prod,"outer_front_sha256"))||!prod.contains("actual_layers")||prod["actual_layers"].cast<std::int64_t>()!=req||!prod.contains("total_thickness")||prod["total_thickness"].cast<double>()<=0)return false;if(!prod.contains("thickness_monotone")||!flag(prod,"thickness_monotone"))return false;if(!prod.contains("growth_ratio_error")||prod["growth_ratio_error"].cast<double>()>0.02)return false;if(!part.contains("cell_ids"))return false;py::dict ids=py::reinterpret_borrow<py::dict>(part["cell_ids"]);if(!ids.contains("core")||!ids.contains("boundary_layer")||!ids.contains("transition")||py::len(ids["boundary_layer"])==0)return false;return true;}
}
py::dict validate(const py::dict& auth,const py::dict& opt,const py::dict& ledger,const py::dict& prod,const py::dict& part,const py::sequence& binding,const py::sequence& pts_obj,const py::sequence& fs_obj,const py::sequence& own_obj,const py::sequence& nei_obj,std::int64_t req,std::int64_t actual,const std::string& base_digest,const std::string& cand_digest){
    if(req<0||actual<0) return reject("negative_layer_count",req);
    if(!common_receipts(auth,opt,req)||actual!=req) return reject("receipt_or_partial_layer",req);
    if(!ledger_ready(ledger,auth)) return reject("source_ledger_incomplete",req);
    if(req==0&&(!digest(base_digest)||!digest(cand_digest)||base_digest!=cand_digest)) return reject("bl0_artifact_identity_mismatch",req);
    if(req>0&&(!producer_ready(prod,part,req)||!digest(cand_digest))) return reject("producer_certificate_incomplete",req);
    if(req>0&&auth.contains("mapping_sha256")&&prod.contains("producer_mapping_sha256")&&txt(auth,"mapping_sha256")!=txt(prod,"producer_mapping_sha256")) return reject("mapping_digest_mismatch",req);
    if(req>0&&auth.contains("front_sha256")&&prod.contains("outer_front_sha256")&&txt(auth,"front_sha256")!=txt(prod,"outer_front_sha256")) return reject("front_digest_mismatch",req);
    auto p=points(pts_obj); auto fs=faces(fs_obj); auto own=ints(own_obj); auto nei=ints(nei_obj);if(fs.size()!=own.size()||fs.size()!=nei.size()||fs.empty())return reject("polymesh_array_length_mismatch",req);std::set<int> boundary;for(std::size_t i=0;i<fs.size();++i){if(nei[i]<0)boundary.insert(static_cast<int>(i));}
    std::set<int> bound_seen;for(py::handle h:binding){py::dict row=py::reinterpret_borrow<py::dict>(h);for(const char* k:{"source_edge","source_face","wall_edge","output_face","feature","patch","physical_group","component","provenance"})if(txt(row,k).empty())return reject("lineage_record_incomplete",req);int of=as_int(row,"output_face");if(!boundary.count(of)||!bound_seen.insert(of).second)return reject("boundary_output_binding_invalid",req);}
    if(req>0&&bound_seen.size()!=boundary.size())return reject("boundary_output_coverage_incomplete",req);
    M m;try{m=measure(p,fs,own,nei);}catch(...){return reject("native_poly_readback_failed",req);}if(m.duplicate||m.nonmanifold||m.nonpositive||m.inverted||m.self_intersection)return reject("strict_topology_failed",req);if(m.max_no>65||m.p95_no>40||m.max_skew>0.50||m.p95_skew>0.25||m.max_aspect>5||m.p95_aspect>3)return reject("core_quality_gate_failed",req);if(req>0&&m.min_scaled<=0)return reject("boundary_layer_scaled_jacobian_failed",req);
    py::dict topo;topo["duplicate"]=m.duplicate;topo["non_manifold"]=m.nonmanifold;topo["open"]=m.open;topo["boundary_faces"]=static_cast<int>(boundary.size());topo["inverted"]=m.inverted;topo["non_positive"]=m.nonpositive;topo["self_intersection"]=m.self_intersection;py::dict q;q["max_wall_non_orthogonality"]=m.max_no;q["p95_wall_non_orthogonality"]=m.p95_no;q["max_tangential_skewness"]=m.max_skew;q["p95_tangential_skewness"]=m.p95_skew;q["max_face_aspect"]=m.max_aspect;q["p95_face_aspect"]=m.p95_aspect;q["minimum_scaled_jacobian"]=m.min_scaled;py::dict r;r["accepted"]=true;r["status"]="native_poly_authority_bound_sealed";r["requested_layers"]=req;r["actual_layers"]=actual;r["runtime_route"]="default_off";r["publication_eligible"]=false;r["route_calls"]=0;r["candidate_discarded"]=false;r["atomic_rollback"]=false;r["receipt_sealed"]=true;r["topology"]=topo;r["quality"]=q;r["boundary_output_coverage"]=boundary.empty()?1.0:static_cast<double>(bound_seen.size())/boundary.size();r["source_sha256"]=txt(ledger,"source_sha256");r["candidate_artifact_digest"]=cand_digest;r["receipt_digest"]="poly-authority-v1|"+txt(auth,"receipt_digest")+"|"+txt(opt,"receipt_digest")+"|"+txt(ledger,"source_sha256")+"|"+cand_digest+"|"+std::to_string(req);return r;
}
PYBIND11_MODULE(native_poly_authority_bound_consumer,module){module.doc()="Private C++23 Native Poly actual-v2 authority-bound consumer";module.def("validate_native_poly_authority_bound",&validate,py::arg("authority_receipt"),py::arg("optimizer_receipt"),py::arg("source_ledger"),py::arg("producer_certificate"),py::arg("partition"),py::arg("boundary_binding"),py::arg("points"),py::arg("faces"),py::arg("owner"),py::arg("neighbour"),py::arg("requested_layers"),py::arg("actual_layers"),py::arg("baseline_artifact_digest"),py::arg("candidate_artifact_digest"));}
