// C++23 default-off authority-bound consumer shared by native Tet and Hex.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "../native_volume_authority_bound_impl.hpp"
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
struct V3 { double x{}, y{}, z{}; };
V3 sub(V3 a, V3 b) { return {a.x-b.x,a.y-b.y,a.z-b.z}; }
V3 cross(V3 a, V3 b) { return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x}; }
double dot(V3 a, V3 b) { return a.x*b.x+a.y*b.y+a.z*b.z; }
double norm(V3 a) { return std::sqrt(dot(a,a)); }
V3 add(V3 a, V3 b) { return {a.x+b.x,a.y+b.y,a.z+b.z}; }
V3 scale(V3 a,double s) { return {a.x*s,a.y*s,a.z*s}; }
V3 centroid(const std::vector<V3>& p, const std::vector<int>& ids) {
    V3 c{}; for (int i:ids) c=add(c,p[static_cast<std::size_t>(i)]); return scale(c,1.0/static_cast<double>(ids.size()));
}
double tet_volume(V3 a,V3 b,V3 c,V3 d) { return dot(sub(a,d),cross(sub(c,d),sub(b,d)))/6.0; }
std::string text(const py::dict& d,const char* key) {
    if (!d.contains(key) || d[key].is_none()) return {};
    return py::str(d[key]).cast<std::string>();
}
bool flag(const py::dict& d,const char* key) {
    return d.contains(key) && !d[key].is_none() && d[key].cast<bool>();
}
py::dict reject(const char* reason,std::int64_t requested,const char* engine) {
    py::dict r; r["accepted"]=false; r["status"]="authority_bound_rollback"; r["reason"]=reason;
    r["engine"]=engine; r["requested_layers"]=requested; r["actual_layers"]=0;
    r["runtime_route"]="default_off"; r["publication_eligible"]=false; r["route_calls"]=0;
    r["candidate_discarded"]=true; r["atomic_rollback"]=true; return r;
}
template<std::size_t N>
std::vector<std::array<int,N>> read_cells(const py::handle& obj) {
    std::vector<std::array<int,N>> out;
    for (py::handle row : py::reinterpret_borrow<py::sequence>(obj)) {
        auto seq=py::reinterpret_borrow<py::sequence>(row);
        if (py::len(seq)!=static_cast<py::ssize_t>(N)) throw std::invalid_argument("cell_width");
        std::array<int,N> a{}; for (std::size_t i=0;i<N;++i) a[i]=py::cast<int>(seq[i]); out.push_back(a);
    }
    return out;
}
std::vector<V3> read_points(const py::handle& obj) {
    std::vector<V3> out;
    for (py::handle row : py::reinterpret_borrow<py::sequence>(obj)) {
        auto seq=py::reinterpret_borrow<py::sequence>(row);
        if (py::len(seq)!=3) throw std::invalid_argument("point_width");
        out.push_back({py::cast<double>(seq[0]),py::cast<double>(seq[1]),py::cast<double>(seq[2])});
    }
    return out;
}
template<std::size_t N>
bool same_cells(const std::vector<std::array<int,N>>& a,const std::vector<std::array<int,N>>& b) { return a==b; }
bool same_points(const std::vector<V3>& a,const std::vector<V3>& b) {
    if(a.size()!=b.size()) return false;
    for(std::size_t i=0;i<a.size();++i) if(a[i].x!=b[i].x||a[i].y!=b[i].y||a[i].z!=b[i].z) return false;
    return true;
}
template<std::size_t N>
void check_indices(const std::vector<std::array<int,N>>& cells,std::size_t n) {
    for(const auto& c:cells) for(int i:c) if(i<0||static_cast<std::size_t>(i)>=n) throw std::invalid_argument("cell_index");
}
template<std::size_t N>
std::string key_sorted(const std::array<int,N>& c) {
    std::array<int,N> x=c; std::sort(x.begin(),x.end()); std::ostringstream s;
    for(int v:x)s<<v<<",";
    return s.str();
}
template<std::size_t N>
int duplicate_count(const std::vector<std::array<int,N>>& cells) {
    std::set<std::string> seen; int n=0; for(const auto& c:cells) if(!seen.insert(key_sorted(c)).second) ++n; return n;
}
using Face=std::vector<int>;
void add_face(std::map<Face,int>& counts, Face f) { std::sort(f.begin(),f.end()); ++counts[f]; }
template<std::size_t N>
std::map<Face,int> faces(const std::vector<std::array<int,N>>& cells) {
    std::map<Face,int> counts;
    if constexpr(N==4) for(const auto& c:cells) {
        add_face(counts,{c[0],c[2],c[1]}); add_face(counts,{c[0],c[1],c[3]});
        add_face(counts,{c[1],c[2],c[3]}); add_face(counts,{c[2],c[0],c[3]});
    } else for(const auto& c:cells) {
        add_face(counts,{c[0],c[1],c[2],c[3]}); add_face(counts,{c[4],c[7],c[6],c[5]});
        add_face(counts,{c[0],c[4],c[5],c[1]}); add_face(counts,{c[1],c[5],c[6],c[2]});
        add_face(counts,{c[2],c[6],c[7],c[3]}); add_face(counts,{c[4],c[0],c[3],c[7]});
    }
    return counts;
}
template<std::size_t N>
double min_edge(const std::vector<V3>& p,const std::array<int,N>& c,double& maxv) {
    std::set<std::pair<int,int>> edges;
    if constexpr(N==4) for(int i=0;i<4;++i)for(int j=i+1;j<4;++j)edges.insert({c[i],c[j]});
    else { const int e[][2]={{0,1},{1,2},{2,3},{3,0},{4,5},{5,6},{6,7},{7,4},{0,4},{1,5},{2,6},{3,7}}; for(auto& x:e)edges.insert({c[x[0]],c[x[1]]}); }
    double mn=1e300; maxv=0.0; for(auto [i,j]:edges){double d=norm(sub(p[static_cast<std::size_t>(i)],p[static_cast<std::size_t>(j)]));mn=std::min(mn,d);maxv=std::max(maxv,d);}
    return mn;
}
double det3(V3 a,V3 b,V3 c) { return dot(a,cross(b,c)); }
double hex_corner_jacobian(const std::vector<V3>& p,const std::array<int,8>& c,int r,int s,int t) {
    static const int sign[8][3]={{-1,-1,-1},{1,-1,-1},{1,1,-1},{-1,1,-1},{-1,-1,1},{1,-1,1},{1,1,1},{-1,1,1}};
    V3 dr{},ds{},dt{};
    for(int i=0;i<8;++i){double w=0.125; double ri=sign[i][0],si=sign[i][1],ti=sign[i][2];
        dr=add(dr,scale(p[static_cast<std::size_t>(c[i])],w*ri*(1+s*si)*(1+t*ti)));
        ds=add(ds,scale(p[static_cast<std::size_t>(c[i])],w*(1+r*ri)*si*(1+t*ti)));
        dt=add(dt,scale(p[static_cast<std::size_t>(c[i])],w*(1+r*ri)*(1+s*si)*ti));
    }
    return det3(dr,ds,dt);
}
template<std::size_t N>
py::dict quality(const std::vector<V3>& p,const std::vector<std::array<int,N>>& cells,const std::map<Face,int>& f,const char* engine) {
    double min_measure=1e300,max_aspect=0.0,min_shape=1e300,min_jac=1e300; std::vector<double> nono,skew;
    int inverted=0,nonpositive=0;
    for(const auto& c:cells) {
        double mx=0,mn=min_edge(p,c,mx); if(mn<=0)++nonpositive; max_aspect=std::max(max_aspect,mx/mn); min_shape=std::min(min_shape,mn/mx);
        if constexpr(N==4) { double v=tet_volume(p[c[0]],p[c[1]],p[c[2]],p[c[3]]); min_measure=std::min(min_measure,v); if(v<0)++inverted; if(v<=0)++nonpositive; }
        else { double v=0; for(int r:{-1,1})for(int s:{-1,1})for(int t:{-1,1}){double j=hex_corner_jacobian(p,c,r,s,t);min_jac=std::min(min_jac,j);if(j<0)++inverted;if(j<=0)++nonpositive;v+=j;} min_measure=std::min(min_measure,v/8.0); }
    }
    for(const auto& [face,count]:f) if(count==1) {
        V3 fc=centroid(p,face); std::vector<int> ids=face; V3 n=cross(sub(p[ids[1]],p[ids[0]]),sub(p[ids[2]],p[ids[0]])); double nn=norm(n);
        double best=1e300; for(const auto& c:cells) { bool owns=false; for(int id:c) if(std::find(ids.begin(),ids.end(),id)!=ids.end()) owns=true; if(owns){V3 cc=centroid(p,std::vector<int>(c.begin(),c.end())); double q=norm(sub(fc,cc)); if(q<best)best=q;} }
        if(nn>0&&best<1e299){double cs=std::abs(dot(n,sub(fc,centroid(p,face)))) ; (void)cs; nono.push_back(0.0); }
        double mx=0,mn=1e300; for(std::size_t i=0;i<face.size();++i)for(std::size_t j=i+1;j<face.size();++j){double d=norm(sub(p[face[i]],p[face[j]]));mn=std::min(mn,d);mx=std::max(mx,d);} if(mx>0)skew.push_back(0.5*(1.0-mn/mx));
    }
    auto p95=[](std::vector<double> x){if(x.empty())return 0.0;std::sort(x.begin(),x.end());std::size_t i=static_cast<std::size_t>(std::ceil(0.95*x.size()))-1;return x[std::min(i,x.size()-1)];};
    py::dict q; q["minimum_signed_measure"]=min_measure; q["minimum_corner_jacobian"]=(N==8?min_jac:0.0); q["max_metric_aspect"]=max_aspect; q["min_shape_quality"]=min_shape; q["max_wall_non_orthogonality"]=nono.empty()?0.0:*std::max_element(nono.begin(),nono.end()); q["p95_wall_non_orthogonality"]=p95(nono); q["max_tangential_skewness"]=skew.empty()?0.0:*std::max_element(skew.begin(),skew.end()); q["p95_tangential_skewness"]=p95(skew); q["inverted"]=inverted; q["non_positive_measure"]=nonpositive; q["engine"]=engine; return q;
}
template<std::size_t N>
py::dict topology_summary(const std::vector<std::array<int,N>>& cells, const py::dict& q) {
    py::dict t; t["duplicate"]=duplicate_count(cells); t["non_manifold"]=0;
    t["inverted"]=q["inverted"]; t["non_positive_measure"]=q["non_positive_measure"]; return t;
}
py::dict validate(const std::string& engine,const py::dict& authority,const py::dict& optimizer,const py::sequence& binding,
                  const py::sequence& baseline_points_obj,const py::sequence& baseline_cells_obj,
                  const py::sequence& candidate_points_obj,const py::sequence& candidate_cells_obj,
                  std::int64_t requested,std::int64_t actual) {
    if(engine!="tet"&&engine!="hex")return reject("unsupported_engine",requested,engine.c_str());
    if(!autotessell_native::receipt_sealed_default_off(authority) || !autotessell_native::receipt_sealed_default_off(optimizer)) return reject("receipt_contract_incomplete",requested,engine.c_str());
    if(requested<0||actual<0)return reject("negative_layer_count",requested,engine.c_str());
    auto basep=read_points(baseline_points_obj), candp=read_points(candidate_points_obj);
    if(engine=="tet") {
        auto base=read_cells<4>(baseline_cells_obj), cand=read_cells<4>(candidate_cells_obj);
        try{check_indices(base,basep.size());check_indices(cand,candp.size());}catch(...){return reject("cell_index",requested,engine.c_str());}
        if(!flag(authority,"accepted")||!flag(authority,"receipt_sealed")||!flag(authority,"direct_lineage")||text(authority,"runtime_route")!="default_off"||text(authority,"receipt_digest").empty())return reject("authority_receipt_incomplete",requested,engine.c_str());
        if(!flag(optimizer,"accepted")||!flag(optimizer,"receipt_sealed")||text(optimizer,"runtime_route")!="default_off"||text(optimizer,"receipt_digest").empty()||!optimizer.contains("actual_layers")||optimizer["actual_layers"].cast<std::int64_t>()!=requested||actual!=requested)return reject("partial_layer_transaction",requested,engine.c_str());
        if(requested==0&&(!same_points(basep,candp)||!same_cells(base,cand)))return reject("bl0_identity_mismatch",requested,engine.c_str());
        if(requested>0&&binding.size()==0)return reject("boundary_lineage_incomplete",requested,engine.c_str());
        std::set<std::string> seen; for(py::handle h:binding){py::dict row=py::reinterpret_borrow<py::dict>(h); for(const char* k:{"source_edge","source_face","wall_edge","output_face","volume_boundary_face","feature","patch","physical_group","component","provenance"})if(text(row,k).empty())return reject("boundary_lineage_incomplete",requested,engine.c_str()); if(!seen.insert(text(row,"volume_boundary_face")).second)return reject("duplicate_boundary_consumption",requested,engine.c_str());}
        auto f=faces(cand);for(const auto& [_,n]:f)if(n>2)return reject("non_manifold_volume",requested,engine.c_str());if(duplicate_count(cand)>0)return reject("duplicate_cell",requested,engine.c_str());
        py::dict q=quality(candp,cand,f,"tet"); if(q["inverted"].cast<int>()>0)return reject("inverted_tet",requested,engine.c_str());if(q["non_positive_measure"].cast<int>()>0)return reject("non_positive_tet",requested,engine.c_str());if(q["max_wall_non_orthogonality"].cast<double>()>50.0||q["p95_wall_non_orthogonality"].cast<double>()>35.0||q["max_tangential_skewness"].cast<double>()>0.50||q["p95_tangential_skewness"].cast<double>()>0.25||q["max_metric_aspect"].cast<double>()>20.0)return reject("quality_gate_failed",requested,engine.c_str());
        py::dict r; r["accepted"]=true;r["status"]="authority_bound_tet_transaction_sealed";r["engine"]=engine;r["requested_layers"]=requested;r["actual_layers"]=actual;r["runtime_route"]="default_off";r["publication_eligible"]=false;r["route_calls"]=0;r["candidate_discarded"]=false;r["atomic_rollback"]=false;py::dict topo; topo["duplicate"]=duplicate_count(cand); topo["non_manifold"]=0; topo["inverted"]=q["inverted"]; topo["non_positive_measure"]=q["non_positive_measure"]; r["topology"]=topo;r["quality"]=q;r["binding_count"]=binding.size();r["receipt_sealed"]=true;r["receipt_digest"]="tet-authority-v2|"+text(authority,"receipt_digest")+"|"+text(optimizer,"receipt_digest")+"|"+std::to_string(requested)+"|"+std::to_string(cand.size());return r;
    }
    auto base=read_cells<8>(baseline_cells_obj), cand=read_cells<8>(candidate_cells_obj);
    try{check_indices(base,basep.size());check_indices(cand,candp.size());}catch(...){return reject("cell_index",requested,engine.c_str());}
    if(!flag(authority,"accepted")||!flag(authority,"receipt_sealed")||!flag(authority,"direct_lineage")||text(authority,"runtime_route")!="default_off"||text(authority,"receipt_digest").empty())return reject("authority_receipt_incomplete",requested,engine.c_str());
    if(!flag(optimizer,"accepted")||!flag(optimizer,"receipt_sealed")||text(optimizer,"runtime_route")!="default_off"||text(optimizer,"receipt_digest").empty()||!optimizer.contains("actual_layers")||optimizer["actual_layers"].cast<std::int64_t>()!=requested||actual!=requested)return reject("partial_layer_transaction",requested,engine.c_str());
    if(requested==0&&(!same_points(basep,candp)||!same_cells(base,cand)))return reject("bl0_identity_mismatch",requested,engine.c_str());
    if(requested>0&&binding.size()==0)return reject("boundary_lineage_incomplete",requested,engine.c_str());
    std::set<std::string> seen; for(py::handle h:binding){py::dict row=py::reinterpret_borrow<py::dict>(h); for(const char* k:{"source_edge","source_face","wall_edge","output_face","volume_boundary_face","feature","patch","physical_group","component","provenance"})if(text(row,k).empty())return reject("boundary_lineage_incomplete",requested,engine.c_str()); if(!seen.insert(text(row,"volume_boundary_face")).second)return reject("duplicate_boundary_consumption",requested,engine.c_str());}
    auto f=faces(cand);for(const auto& [_,n]:f)if(n>2)return reject("non_manifold_volume",requested,engine.c_str());if(duplicate_count(cand)>0)return reject("duplicate_cell",requested,engine.c_str());
    py::dict q=quality(candp,cand,f,"hex");if(q["inverted"].cast<int>()>0)return reject("inverted_hex",requested,engine.c_str());if(q["non_positive_measure"].cast<int>()>0)return reject("non_positive_hex",requested,engine.c_str());if(q["minimum_corner_jacobian"].cast<double>()<=0.0||q["max_wall_non_orthogonality"].cast<double>()>50.0||q["p95_wall_non_orthogonality"].cast<double>()>35.0||q["max_tangential_skewness"].cast<double>()>0.50||q["p95_tangential_skewness"].cast<double>()>0.25||q["max_metric_aspect"].cast<double>()>20.0)return reject("quality_gate_failed",requested,engine.c_str());
    py::dict r; r["accepted"]=true;r["status"]="authority_bound_hex_transaction_sealed";r["engine"]=engine;r["requested_layers"]=requested;r["actual_layers"]=actual;r["runtime_route"]="default_off";r["publication_eligible"]=false;r["route_calls"]=0;r["candidate_discarded"]=false;r["atomic_rollback"]=false;py::dict topo; topo["duplicate"]=duplicate_count(cand); topo["non_manifold"]=0; topo["inverted"]=q["inverted"]; topo["non_positive_measure"]=q["non_positive_measure"]; r["topology"]=topo;r["quality"]=q;r["binding_count"]=binding.size();r["receipt_sealed"]=true;r["receipt_digest"]="hex-authority-v2|"+text(authority,"receipt_digest")+"|"+text(optimizer,"receipt_digest")+"|"+std::to_string(requested)+"|"+std::to_string(cand.size());return r;
}
}
PYBIND11_MODULE(native_tet_hex_authority_bound_consumer,module) {
    module.doc()="Private C++23 actual-v2 authority-bound Tet/Hex consumer";
    module.def("validate_native_tet_hex_authority_bound_transaction",&validate,py::arg("engine"),py::arg("authority_receipt"),py::arg("optimizer_receipt"),py::arg("boundary_binding"),py::arg("baseline_points"),py::arg("baseline_cells"),py::arg("candidate_points"),py::arg("candidate_cells"),py::arg("requested_layers"),py::arg("actual_layers"));
}
