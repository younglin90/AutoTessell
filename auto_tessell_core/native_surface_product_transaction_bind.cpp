// C++23 private surface-product transaction validator.
// Tri, Strict Quad, and TRI+QUAD remain separate products and default-off routes.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
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
using Point=std::array<double,3>;

double dot(Point a,Point b) noexcept{return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
Point sub(Point a,Point b) noexcept{return{a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
Point cross(Point a,Point b) noexcept{return{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
std::vector<Point> points(const py::array_t<double,py::array::c_style|py::array::forcecast>& a,const char*n){
 if(a.ndim()!=2||a.shape(1)!=3)throw std::invalid_argument(std::string(n)+" must be Nx3");
 auto v=a.unchecked<2>();std::vector<Point> out;out.reserve((size_t)a.shape(0));
 for(py::ssize_t i=0;i<a.shape(0);++i){Point p{};for(int j=0;j<3;++j){p[(size_t)j]=v(i,j);if(!std::isfinite(p[(size_t)j]))throw std::invalid_argument("non-finite point");}out.push_back(p);}return out;
}
template<size_t N>
std::vector<std::array<std::int64_t,N>> faces(const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& a,std::int64_t n,const char*name){
 if(a.ndim()!=2||a.shape(1)!=N)throw std::invalid_argument(std::string(name)+" has wrong shape");
 auto v=a.unchecked<2>();std::vector<std::array<std::int64_t,N>> out;out.reserve((size_t)a.shape(0));
 for(py::ssize_t i=0;i<a.shape(0);++i){std::array<std::int64_t,N> f{};for(size_t j=0;j<N;++j){f[j]=v(i,(py::ssize_t)j);if(f[j]<0||f[j]>=n)throw std::invalid_argument(std::string(name)+" index out of range");}out.push_back(f);}return out;
}
template<size_t N> bool exact(const std::vector<std::array<std::int64_t,N>>&a,const std::vector<std::array<std::int64_t,N>>&b){return a==b;}
bool exact_points(const std::vector<Point>&a,const std::vector<Point>&b){return a==b;}
template<size_t N> double area(const std::vector<Point>&p,const std::array<std::int64_t,N>&f){
 Point origin=p[(size_t)f[0]], normal{0.,0.,0.};
 for(size_t i=1;i+1<N;++i){normal=std::array<double,3>{normal[0]+cross(sub(p[(size_t)f[i]],origin),sub(p[(size_t)f[i+1]],origin))[0],normal[1]+cross(sub(p[(size_t)f[i]],origin),sub(p[(size_t)f[i+1]],origin))[1],normal[2]+cross(sub(p[(size_t)f[i]],origin),sub(p[(size_t)f[i+1]],origin))[2]};}
 return .5*std::sqrt(dot(normal,normal));
}
template<size_t N> double skew(const std::vector<Point>&p,const std::array<std::int64_t,N>&f){
 double lo=INFINITY,hi=0.;for(size_t i=0;i<N;++i)for(size_t j=i+1;j<N;++j){double l=std::sqrt(dot(sub(p[(size_t)f[i]],p[(size_t)f[j]]),sub(p[(size_t)f[i]],p[(size_t)f[j]])));lo=std::min(lo,l);hi=std::max(hi,l);}return lo>1e-14?(hi-lo)/hi:INFINITY;
}
py::dict refuse(const std::string&r,std::int64_t req,const char*status="refused_rollback"){py::dict o;o["accepted"]=false;o["status"]=status;o["reason"]=r;o["requested_layers"]=req;o["actual_layers"]=0;o["runtime_route"]="default_off";o["publication_eligible"]=false;o["route_calls"]=0;o["candidate_discarded"]=true;return o;}
bool witness_ok(const py::object&o){if(o.is_none()||!py::isinstance<py::dict>(o))return false;py::dict d=o.cast<py::dict>();if(!d.contains("accepted")||!d["accepted"].cast<bool>())return false;for(const char*k:{"frozen_front","collision_visibility","geodesic"})if(!d.contains(k))return false;return py::str(d["frozen_front"]["status"]).cast<std::string>()=="frozen"&&py::str(d["collision_visibility"]["status"]).cast<std::string>()=="measured_clear"&&py::str(d["geodesic"]["status"]).cast<std::string>()=="measured";}
bool authority_ok(const py::object&o){if(o.is_none()||!py::isinstance<py::dict>(o))return false;py::dict d=o.cast<py::dict>();if(!d.contains("source_verified")||!d["source_verified"].cast<bool>()||!d.contains("field_origins_complete")||!d["field_origins_complete"].cast<bool>())return false;for(const char*k:{"raw_sha256","feature","patch","physical_group","component","provenance"})if(!d.contains(k)||d[k].cast<std::string>().empty())return false;return true;}
py::dict evaluate(
 const std::string&kind,
 const py::array_t<double,py::array::c_style|py::array::forcecast>&source_points,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>&source_triangles,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>&source_quads,
 const py::array_t<double,py::array::c_style|py::array::forcecast>&candidate_points,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>&candidate_triangles,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>&candidate_quads,
 std::int64_t requested_layers,std::int64_t actual_layers,
 const py::object&source_certificate,const py::object&authority,const py::object&profile,const py::object&witness,const py::list&lineage){
 auto sp=points(source_points,"source_points"),cp=points(candidate_points,"candidate_points");
 auto st=faces<3>(source_triangles,(std::int64_t)sp.size(),"source_triangles"); auto sq=faces<4>(source_quads,(std::int64_t)sp.size(),"source_quads");
 auto ct=faces<3>(candidate_triangles,(std::int64_t)cp.size(),"candidate_triangles"); auto cq=faces<4>(candidate_quads,(std::int64_t)cp.size(),"candidate_quads");
 if(kind!="tri"&&kind!="strict_quad"&&kind!="tri_plus_quad")return refuse("unknown_product_kind",requested_layers,"incomplete");
 if(requested_layers<0||actual_layers<0)return refuse("invalid_layer_count",requested_layers,"incomplete");
 if(requested_layers==0){
  if(actual_layers!=0||!exact_points(sp,cp)||!exact(st,ct)||!exact(sq,cq))return refuse("bl0_identity_mismatch",0);
  auto o=refuse("disabled_identity",0,"disabled_identity");o["accepted"]=true;o["candidate_discarded"]=false;o["receipt_sealed"]=false;return o;
 }
 if(actual_layers!=requested_layers)return refuse("partial_boundary_layer",requested_layers);
 if(!authority_ok(authority)||source_certificate.is_none()||!py::isinstance<py::dict>(source_certificate))return refuse("authority_or_source_certificate_incomplete",requested_layers,"incomplete");
 if(!witness_ok(witness))return refuse("surface_witness_gate_failed",requested_layers);
 if(profile.is_none()||!py::isinstance<py::dict>(profile))return refuse("quality_profile_incomplete",requested_layers,"incomplete");
 py::dict pr=profile.cast<py::dict>();for(const char*k:{"min_face_area","max_skewness","max_metric_distortion"})if(!pr.contains(k))return refuse("quality_profile_incomplete",requested_layers,"incomplete");
 double min_area=pr["min_face_area"].cast<double>(),max_sk=pr["max_skewness"].cast<double>(),max_metric=pr["max_metric_distortion"].cast<double>();
 if(!(min_area>0.)||!(max_sk>=0.)||!(max_metric>0.))return refuse("quality_profile_invalid",requested_layers,"incomplete");
 if(kind=="tri"&&exact(ct,st)&&exact_points(cp,sp))return refuse("tri_noop_clone",requested_layers);
 if(kind=="strict_quad"&&(!ct.empty()||cq.empty()))return refuse("strict_quad_product_shape",requested_layers);
 if(kind=="tri_plus_quad"&&(ct.empty()||cq.empty()))return refuse("tri_plus_quad_requires_mixed_faces",requested_layers);
 if(lineage.size()!=ct.size()+cq.size())return refuse("lineage_length_mismatch",requested_layers,"incomplete");
 std::set<std::array<std::int64_t,3>> tri_seen;std::set<std::array<std::int64_t,4>> quad_seen;std::map<std::array<std::int64_t,2>,int> edge_count;std::int64_t duplicate=0,nonmanifold=0;double min_observed=INFINITY,max_observed_sk=0.;
 for(const auto&f:ct){auto k=f;std::sort(k.begin(),k.end());if(!tri_seen.insert(k).second)++duplicate;for(int i=0;i<3;++i){auto e=std::array<std::int64_t,2>{f[(size_t)i],f[(size_t)((i+1)%3)]};if(e[0]>e[1])std::swap(e[0],e[1]);if(++edge_count[e]>2)++nonmanifold;}double a=area(sp==cp?cp:cp,f);min_observed=std::min(min_observed,a);max_observed_sk=std::max(max_observed_sk,skew(cp,f));}
 for(const auto&f:cq){auto k=f;std::sort(k.begin(),k.end());if(!quad_seen.insert(k).second)++duplicate;for(int i=0;i<4;++i){auto e=std::array<std::int64_t,2>{f[(size_t)i],f[(size_t)((i+1)%4)]};if(e[0]>e[1])std::swap(e[0],e[1]);if(++edge_count[e]>2)++nonmanifold;}double a=area(cp,f);min_observed=std::min(min_observed,a);max_observed_sk=std::max(max_observed_sk,skew(cp,f));}
 bool lineage_ok=true;size_t idx=0;for(const py::handle h:lineage){if(!py::isinstance<py::dict>(h)){lineage_ok=false;continue;}py::dict row=h.cast<py::dict>();if(!row.contains("kind")||!row.contains("source_count")||!row.contains("feature")||!row.contains("patch")||!row.contains("physical_group")||!row.contains("component")||!row.contains("provenance")){lineage_ok=false;continue;}std::string k=row["kind"].cast<std::string>();int count=row["source_count"].cast<int>();if(idx<ct.size()?(k!="tri"||count!=1):(k!="quad"||count!=2))lineage_ok=false;if(row["feature"].cast<std::string>().empty()||row["patch"].cast<std::string>().empty()||row["physical_group"].cast<std::string>().empty()||row["component"].cast<std::string>().empty()||row["provenance"].cast<std::string>().empty())lineage_ok=false;++idx;}
 if(duplicate||nonmanifold||!lineage_ok||min_observed<min_area||max_observed_sk>max_sk||max_metric>20.)return refuse(duplicate?"duplicate_face":nonmanifold?"non_manifold_edge":!lineage_ok?"lineage_or_product_mismatch":min_observed<min_area?"face_area_gate_failed":"surface_quality_gate_failed",requested_layers);
 py::dict out;out["accepted"]=true;out["status"]="stage_receipt_sealed";out["reason"]="private_surface_product_quality_topology_authority_passed";out["requested_layers"]=requested_layers;out["actual_layers"]=requested_layers;out["runtime_route"]="default_off";out["publication_eligible"]=false;out["route_calls"]=0;out["candidate_discarded"]=false;out["receipt_sealed"]=true;out["receipt_digest"]="surface-product-v1|"+kind+"|"+std::to_string(requested_layers)+"|"+authority.cast<py::dict>()["raw_sha256"].cast<std::string>();py::dict top;top["duplicate"]=duplicate;top["non_manifold"]=nonmanifold;top["invalid"]=0;top["inverted"]=0;top["negative_measure"]=0;out["topology"]=top;py::dict q;q["minimum_face_area"]=min_observed;q["maximum_skewness"]=max_observed_sk;q["metric_distortion"]=max_metric;out["quality"]=q;out["face_count"]=ct.size()+cq.size();return out;
}
PYBIND11_MODULE(native_surface_product_transaction,m){m.doc()="C++23 private Tri/StrictQuad/TRI+QUAD validator; default-off route";m.def("evaluate_surface_product_transaction",&evaluate,py::arg("kind"),py::arg("source_points"),py::arg("source_triangles"),py::arg("source_quads"),py::arg("candidate_points"),py::arg("candidate_triangles"),py::arg("candidate_quads"),py::arg("requested_layers"),py::arg("actual_layers"),py::arg("source_certificate"),py::arg("authority"),py::arg("quality_profile"),py::arg("surface_witness"),py::arg("lineage"));}
