// C++23 private deterministic classified dual-hull canonical receipt.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;
namespace {
struct P { double x{},y{},z{}; };
double dot(P a,P b){return a.x*b.x+a.y*b.y+a.z*b.z;}
double norm(P a){return std::sqrt(dot(a,a));}
bool hex64(const std::string& s){if(s.size()!=64)return false;return std::all_of(s.begin(),s.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});}
py::dict reject(const char* reason,const std::string& mode){py::dict r;r["accepted"]=false;r["status"]="native_poly_dual_receipt_rollback";r["reason"]=reason;r["hull_mode"]=mode;r["runtime_route"]="default_off";r["publication_eligible"]=false;r["candidate_discarded"]=true;r["actual_layers"]=0;return r;}
std::vector<P> read_points(const py::sequence& obj){std::vector<P> out;for(py::handle h:obj){auto row=py::reinterpret_borrow<py::sequence>(h);if(py::len(row)!=3)throw std::invalid_argument("point_width");out.push_back({py::cast<double>(row[0]),py::cast<double>(row[1]),py::cast<double>(row[2])});}return out;}
std::vector<int> read_ids(const py::sequence& obj){std::vector<int> out;for(py::handle h:obj)out.push_back(py::cast<int>(h));return out;}
long long q(double x){return static_cast<long long>(std::llround(x*1.0e9));}
std::tuple<long long,long long,long long,int> key(const P& p,int id){return {q(p.x),q(p.y),q(p.z),id};}
P newell(const std::vector<P>& p,const std::vector<int>& ids){P n{};for(std::size_t i=0;i<ids.size();++i){const P&a=p[ids[i]],&b=p[ids[(i+1)%ids.size()]];n.x+=(a.y-b.y)*(a.z+b.z);n.y+=(a.z-b.z)*(a.x+b.x);n.z+=(a.x-b.x)*(a.y+b.y);}return n;}
std::vector<int> min_rotation(const std::vector<int>& ids,const std::vector<P>& p){std::vector<int> best;for(std::size_t start=0;start<ids.size();++start){std::vector<int> c;for(std::size_t k=0;k<ids.size();++k)c.push_back(ids[(start+k)%ids.size()]);if(best.empty()||std::lexicographical_compare(c.begin(),c.end(),best.begin(),best.end(),[&](int a,int b){return key(p[a],a)<key(p[b],b);}))best=std::move(c);}return best;}
std::string join(const std::vector<int>& ids){std::ostringstream s;for(int id:ids)s<<id<<",";return s.str();}
}
py::dict validate(const std::string& mode,const std::string& input_point_digest,const std::string& input_label_digest,const std::string& plane_group_digest,const py::sequence& points_obj,const py::sequence& polygon_obj,const py::sequence& plane_obj,const std::string& source_label){
    if(mode!="exact")return reject(mode=="joggle"?"joggle_not_source_authoritative":"hull_mode_refused",mode);
    if(!hex64(input_point_digest)||!hex64(input_label_digest)||!hex64(plane_group_digest))return reject("input_digest_incomplete",mode);
    if(source_label.empty())return reject("source_label_missing",mode);
    auto p=read_points(points_obj); auto ids=read_ids(polygon_obj);if(py::len(plane_obj)!=3)return reject("plane_normal_shape",mode);if(ids.size()<3)return reject("polygon_too_small",mode);
    std::vector<double> pv;for(py::handle h:plane_obj)pv.push_back(py::cast<double>(h));P n{pv[0],pv[1],pv[2]};if(norm(n)<=1e-14)return reject("plane_normal_zero",mode);
    std::vector<bool> seen(p.size(),false);for(int id:ids){if(id<0||static_cast<std::size_t>(id)>=p.size()||seen[static_cast<std::size_t>(id)])return reject("polygon_vertex_duplicate_or_invalid",mode);seen[static_cast<std::size_t>(id)]=true;}
    P poly=newell(p,ids);double area=norm(poly);if(area<=1e-14)return reject("polygon_zero_area",mode);double alignment=dot(poly,n)/(area*norm(n));if(std::abs(alignment)<=1e-12)return reject("polygon_ambiguous_orientation",mode);if(alignment<0){std::reverse(ids.begin(),ids.end());poly=newell(p,ids);}
    auto canonical=min_rotation(ids,p);P checked=newell(p,canonical);if(dot(checked,n)<=0)return reject("polygon_orientation_failed",mode);
    py::list out;for(int id:canonical)out.append(id);py::dict r;r["accepted"]=true;r["status"]="native_poly_dual_receipt_sealed";r["hull_mode"]="exact";r["runtime_route"]="default_off";r["publication_eligible"]=false;r["candidate_discarded"]=false;r["actual_layers"]=0;r["source_label"]=source_label;r["canonical_vertices"]=out;r["polygon_area_norm"]=norm(checked);r["input_point_digest"]=input_point_digest;r["input_label_digest"]=input_label_digest;r["plane_group_digest"]=plane_group_digest;r["source_label_coverage_digest"]="source-label|"+source_label+"|"+join(canonical);r["polygon_digest"]="poly-dual-polygon-v1|"+join(canonical);r["receipt_digest"]="poly-dual-receipt-v1|"+mode+"|"+input_point_digest+"|"+input_label_digest+"|"+plane_group_digest+"|"+source_label+"|"+join(canonical);return r;
}
PYBIND11_MODULE(native_poly_dual_deterministic_receipt,module){module.doc()="Private C++23 deterministic classified dual-hull receipt";module.def("validate_canonical_dual_hull_receipt",&validate,py::arg("hull_mode"),py::arg("input_point_digest"),py::arg("input_label_digest"),py::arg("plane_group_digest"),py::arg("points"),py::arg("polygon_vertices"),py::arg("plane_normal"),py::arg("source_label"));}
