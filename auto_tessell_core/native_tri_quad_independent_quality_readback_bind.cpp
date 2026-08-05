#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <iomanip>
#include <sstream>
#include <limits>
#include <set>
#include <string>
#include <vector>

namespace py = pybind11;
using P = std::array<double, 3>;
using Face = std::vector<std::int64_t>;

static py::dict refuse(const std::string& reason) {
    py::dict r; r["accepted"] = false; r["status"] = "tri_quad_independent_quality_readback_refused";
    r["reason"] = reason; r["publication_eligible"] = false; r["candidate_discarded"] = true;
    r["auditor_route"] = "private_default_off"; return r;
}
static bool finite_p(const P& p) { return std::isfinite(p[0]) && std::isfinite(p[1]) && std::isfinite(p[2]); }
static double dot(const P& a,const P& b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
static P sub(const P& a,const P& b){return{a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
static P add(const P& a,const P& b){return{a[0]+b[0],a[1]+b[1],a[2]+b[2]};}
static P mul(const P& a,double s){return{a[0]*s,a[1]*s,a[2]*s};}
static P cross(const P& a,const P& b){return{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
static double len(const P& a){return std::sqrt(dot(a,a));}
static bool unit(const P& a,P& out){double n=len(a);if(!(n>1e-14)||!std::isfinite(n))return false;out=mul(a,1./n);return finite_p(out);}
static bool text(const py::dict& d,const char* k){return d.contains(k)&&!d[k].is_none()&&!py::str(d[k]).cast<std::string>().empty();}
static bool point(const py::handle& h,P& p){if(!py::isinstance<py::sequence>(h))return false;auto s=h.cast<py::sequence>();if(s.size()!=3)return false;try{p={s[0].cast<double>(),s[1].cast<double>(),s[2].cast<double>()};}catch(...){return false;}return finite_p(p);}
static bool face(const py::handle& h,std::size_t w,std::size_t n,Face& f){if(!py::isinstance<py::sequence>(h))return false;auto s=h.cast<py::sequence>();if(s.size()!=w)return false;try{f.clear();for(py::ssize_t i=0;i<s.size();++i){auto v=s[i].cast<std::int64_t>();if(v<0||static_cast<std::size_t>(v)>=n)return false;f.push_back(v);}}catch(...){return false;}return true;}
static Face key(Face f){std::sort(f.begin(),f.end());return f;}
static bool points_from(const py::handle& h,std::vector<P>& out){if(!py::isinstance<py::sequence>(h))return false;out.clear();for(const auto& x:h.cast<py::sequence>()){P p;if(!point(x,p))return false;out.push_back(p);}return !out.empty();}
static bool faces_from(const py::handle& h,std::size_t w,std::size_t n,std::vector<Face>& out){if(!py::isinstance<py::sequence>(h))return false;std::set<Face> seen;out.clear();for(const auto& x:h.cast<py::sequence>()){Face f;if(!face(x,w,n,f)||!seen.insert(key(f)).second)return false;out.push_back(f);}return true;}
static bool same_points(const std::vector<P>& a,const py::handle& h){if(!py::isinstance<py::sequence>(h))return false;auto s=h.cast<py::sequence>();if(s.size()!=static_cast<py::ssize_t>(a.size()))return false;for(std::size_t i=0;i<a.size();++i){P p;if(!point(s[i],p)||len(sub(a[i],p))>1e-12)return false;}return true;}
static bool same_faces(const std::vector<Face>& a,const py::handle& h){if(!py::isinstance<py::sequence>(h))return false;auto s=h.cast<py::sequence>();if(s.size()!=static_cast<py::ssize_t>(a.size()))return false;for(std::size_t i=0;i<a.size();++i){Face f;if(!face(s[i],a[i].size(),std::numeric_limits<std::size_t>::max(),f)||f!=a[i])return false;}return true;}
static double angle_deg(const P& a,const P& b){double d=dot(a,b)/(len(a)*len(b));return std::acos(std::clamp(d,-1.,1.))*180./std::acos(-1.);}
static double tri_aspect(const Face& f,const std::vector<P>& p){double a=len(sub(p[f[1]],p[f[0]])),b=len(sub(p[f[2]],p[f[1]])),c=len(sub(p[f[0]],p[f[2]]));return std::max({a,b,c})/std::max(1e-14,std::min({a,b,c}));}
static double tri_skew(const Face& f,const std::vector<P>& p){return (tri_aspect(f,p)-1.)/tri_aspect(f,p);}
static double tri_jac(const Face& f,const std::vector<P>& p,const P& n){return dot(cross(sub(p[f[1]],p[f[0]]),sub(p[f[2]],p[f[0]])),n);}
static double quad_jac(const Face& f,const std::vector<P>& p,const P& n,double u,double v){P du=add(mul(sub(p[f[1]],p[f[0]]),1.-v),mul(sub(p[f[2]],p[f[3]]),v));P dv=add(mul(sub(p[f[3]],p[f[0]]),1.-u),mul(sub(p[f[2]],p[f[1]]),u));return dot(cross(du,dv),n);}
static double quad_skew(const Face& f,const std::vector<P>& p){double worst=0.;for(int i=0;i<4;++i){const P a=sub(p[f[(i+3)%4]],p[f[i]]),b=sub(p[f[(i+1)%4]],p[f[i]]);worst=std::max(worst,std::abs(angle_deg(a,b)-90.)/90.);}return worst;}
static double quad_aspect(const Face& f,const std::vector<P>& p,bool strip){std::vector<double> e;for(int i=0;i<4;++i)e.push_back(len(sub(p[f[(i+1)%4]],p[f[i]])));if(strip)return std::max(e[0],e[2])/std::max(1e-14,std::min(e[0],e[2]));return *std::max_element(e.begin(),e.end())/std::max(1e-14,*std::min_element(e.begin(),e.end()));}
static py::dict metric_row(double skew,double aspect,double jac,double nonorth){py::dict r;r["skewness"]=skew;r["aspect_ratio"]=aspect;r["signed_jacobian"]=jac;r["non_orthogonality"]=nonorth;return r;}
struct MetricSample{double skew,aspect,jac;};
static std::string sample_digest(const std::vector<double>& values){std::ostringstream os;os<<std::setprecision(17)<<std::fixed;for(double v:values)os<<v<<";";std::uint64_t h=1469598103934665603ULL;for(unsigned char c:os.str()){h^=c;h*=1099511628211ULL;}std::ostringstream out;out<<std::hex<<std::setw(16)<<std::setfill('0')<<h;return out.str();}
static py::dict scalar_stats(std::vector<double> values){py::dict r;r["applicable"]=!values.empty();r["count"]=values.size();if(values.empty()){r["min"]=0.;r["p50"]=0.;r["p95"]=0.;r["p99"]=0.;r["max"]=0.;r["ordered_sample_digest"]=sample_digest(values);return r;}std::sort(values.begin(),values.end());auto q=[&](double x){std::size_t i=static_cast<std::size_t>(std::ceil(x*values.size()))-1;return values[std::min(i,values.size()-1)];};r["min"]=values.front();r["p50"]=q(.50);r["p95"]=q(.95);r["p99"]=q(.99);r["max"]=values.back();r["ordered_sample_digest"]=sample_digest(values);return r;}
static py::dict face_distribution(const std::vector<MetricSample>& samples){std::vector<double>a,b,c;for(const auto&s:samples){a.push_back(s.skew);b.push_back(s.aspect);c.push_back(s.jac);}py::dict r;r["applicable"]=!samples.empty();r["count"]=samples.size();r["skewness"]=scalar_stats(a);r["tangential_aspect_ratio"]=scalar_stats(b);r["signed_jacobian"]=scalar_stats(c);std::vector<double> all=a;all.insert(all.end(),b.begin(),b.end());all.insert(all.end(),c.begin(),c.end());r["ordered_sample_digest"]=sample_digest(all);return r;}
static py::dict dist(std::size_t n,double skew,double aspect,double jac){py::dict r;r["count"]=n;r["min"]=0.;r["p50"]=skew;r["p95"]=skew;r["p99"]=skew;r["max"]=skew;r["max_aspect_ratio"]=aspect;r["min_signed_jacobian"]=jac;return r;}
static py::dict statistics(std::vector<double> values,bool applicable){py::dict r=scalar_stats(std::move(values));r["applicable"]=applicable&&r["count"].cast<std::size_t>()>0;return r;}
static bool semantic_rows(const py::dict& receipt,const char* k,std::size_t n,py::list& out){if(!receipt.contains(k)||!py::isinstance<py::list>(receipt[k]))return false;out=receipt[k].cast<py::list>();if(out.size()!=static_cast<py::ssize_t>(n))return false;for(const auto& h:out){if(!py::isinstance<py::dict>(h))return false;auto d=h.cast<py::dict>();if(!text(d,"face_id"))return false;for(const char* x:{"feature","patch","physical_group","component","provenance"})if(!text(d,x))return false;}return true;}
static bool labels_match(const py::dict& a,const py::dict& b,const char* id){if(!a.contains("source_id")||py::str(a["source_id"]).cast<std::string>()!=py::str(b[id]).cast<std::string>())return false;for(const char* k:{"feature","patch","physical_group","component","provenance"})if(!a.contains(k)||py::str(a[k]).cast<std::string>()!=py::str(b[k]).cast<std::string>())return false;return true;}

static py::dict audit(const py::dict& data) {
    if(!data.contains("receipt")||!py::isinstance<py::dict>(data["receipt"]))return refuse("receipt_missing");
    auto receipt=data["receipt"].cast<py::dict>();
    std::vector<P> source, artifact; if(!points_from(data["source_points"],source)||!points_from(data["artifact_points"],artifact))return refuse("points_invalid");
    std::vector<Face> st, sq, at, aq, as;
    if(!faces_from(data["source_triangles"],3,source.size(),st)||!faces_from(data["source_quads"],4,source.size(),sq))return refuse("source_topology_invalid");
    if(!faces_from(data["artifact_triangles"],3,artifact.size(),at)||!faces_from(data["artifact_quads"],4,artifact.size(),aq)||!faces_from(data["artifact_strip_quads"],4,artifact.size(),as))return refuse("artifact_topology_invalid");
    if(!same_points(source,data["artifact_points"]) && artifact.size()==source.size())return refuse("bl0_point_identity_failed");
    if(st.size()!=at.size()||sq.size()!=aq.size())return refuse("core_cardinality_changed");
    for(std::size_t i=0;i<st.size();++i)if(st[i]!=at[i])return refuse("triangle_connectivity_changed");
    for(std::size_t i=0;i<sq.size();++i)if(sq[i]!=aq[i])return refuse("quad_connectivity_changed");
    py::list tri_sem,quad_sem;if(!semantic_rows(receipt,"triangles",st.size(),tri_sem)||!semantic_rows(receipt,"quads",sq.size(),quad_sem))return refuse("semantic_rows_missing");
    if(!py::isinstance<py::list>(data["triangle_map"])||!py::isinstance<py::list>(data["quad_map"]))return refuse("core_lineage_missing");
    auto tm=data["triangle_map"].cast<py::list>();auto qm=data["quad_map"].cast<py::list>();if(tm.size()!=st.size()||qm.size()!=sq.size())return refuse("core_lineage_cardinality");
    for(std::size_t i=0;i<st.size();++i)if(!py::isinstance<py::dict>(tm[i])||!labels_match(tm[i].cast<py::dict>(),tri_sem[i].cast<py::dict>(),"face_id"))return refuse("triangle_lineage_mismatch");
    for(std::size_t i=0;i<sq.size();++i)if(!py::isinstance<py::dict>(qm[i])||!labels_match(qm[i].cast<py::dict>(),quad_sem[i].cast<py::dict>(),"face_id"))return refuse("quad_lineage_mismatch");

    if(!data.contains("requested_layers")||!data.contains("actual_layers"))return refuse("layer_metadata_missing");
    const auto requested=data["requested_layers"].cast<std::int64_t>(), actual=data["actual_layers"].cast<std::int64_t>();if(requested!=actual||requested<0||requested>3||(requested!=0&&requested!=1&&requested!=3))return refuse("layer_count_mismatch");
    if(!py::isinstance<py::list>(data["wall_loop"])||!py::isinstance<py::list>(data["co_normals"])||!py::isinstance<py::list>(data["layer_heights"]))return refuse("wall_schedule_missing");
    auto loop=data["wall_loop"].cast<py::list>();auto normals=data["co_normals"].cast<py::list>();auto heights=data["layer_heights"].cast<py::list>();if(loop.size()!=normals.size()||heights.size()!=requested||loop.empty())return refuse("wall_schedule_cardinality");
    std::vector<std::int64_t> order;std::map<std::int64_t,P> vn,rn;std::set<std::int64_t> eids;
    for(std::size_t i=0;i<static_cast<std::size_t>(loop.size());++i){if(!py::isinstance<py::dict>(loop[i]))return refuse("wall_row_invalid");auto row=loop[i].cast<py::dict>();for(const char* k:{"edge_id","v0","v1","feature","patch","physical_group","component","provenance"})if(!text(row,k))return refuse("wall_semantics_missing");auto eid=row["edge_id"].cast<std::int64_t>();auto a=row["v0"].cast<std::int64_t>();auto b=row["v1"].cast<std::int64_t>();if(!eids.insert(eid).second||a<0||b<0||a==b||static_cast<std::size_t>(a)>=source.size()||static_cast<std::size_t>(b)>=source.size())return refuse("wall_edge_invalid");if(i&&order.back()!=a)return refuse("wall_loop_not_contiguous");order.push_back(b);P n;if(!point(normals[i],n)||!unit(n,n))return refuse("wall_normal_invalid");P ref=n;if(row.contains("reference_normal")&&(!point(row["reference_normal"],ref)||!unit(ref,ref)))return refuse("reference_normal_invalid");for(auto v:{a,b}){auto it=vn.find(v);if(it!=vn.end()&&len(sub(it->second,n))>1e-8)return refuse("wall_normal_conflict");auto ri=rn.find(v);if(ri!=rn.end()&&len(sub(ri->second,ref))>1e-8)return refuse("reference_normal_conflict");vn[v]=n;rn[v]=ref;}}
    if(order.back()!=loop[0].cast<py::dict>()["v0"].cast<std::int64_t>())return refuse("wall_loop_not_closed");
    if(requested==0){if(artifact.size()!=source.size()||!same_points(source,data["artifact_points"])||!as.empty())return refuse("bl0_identity_failed");}
    else if(as.size()!=static_cast<std::size_t>(requested)*loop.size())return refuse("strip_cardinality_mismatch");
    if(!py::isinstance<py::list>(data["strip_map"]))return refuse("strip_lineage_missing");auto sm=data["strip_map"].cast<py::list>();if(sm.size()!=as.size())return refuse("strip_lineage_cardinality");
    double max_residual=0., cumulative=0.;std::vector<double> wall_angles,wall_leaks;std::vector<std::int64_t> verts;for(const auto& [v,n]:vn)verts.push_back(v);
    std::map<std::int64_t,std::size_t> vrank;for(std::size_t i=0;i<verts.size();++i)vrank[verts[i]]=i;
    for(std::int64_t l=0;l<requested;++l){double h=heights[l].cast<double>();if(!(h>0.)||!std::isfinite(h))return refuse("height_invalid");cumulative+=h;for(auto v:verts){std::size_t id=source.size()+static_cast<std::size_t>(l)*verts.size()+vrank[v];if(id>=artifact.size())return refuse("layer_point_missing");std::size_t prev=(l==0)?static_cast<std::size_t>(v):source.size()+static_cast<std::size_t>(l-1)*verts.size()+vrank[v];P expected=add(source[v],mul(vn[v],cumulative));P d=sub(artifact[id],artifact[prev]);double dn=len(d);if(!(dn>1e-12)||!finite_p(d))return refuse("wall_displacement_invalid");double along=dot(d,rn[v]);if(!(along>0.))return refuse("wall_displacement_backward");double leak=len(sub(d,mul(rn[v],along)))/dn;wall_leaks.push_back(leak);wall_angles.push_back(angle_deg(d,rn[v]));max_residual=std::max(max_residual,len(sub(expected,artifact[id])));if(max_residual>1e-10||leak>0.025||wall_angles.back()>25.)return refuse("wall_front_metric_failed");}}
    for(std::size_t i=0;i<as.size();++i){auto row=sm[i].cast<py::dict>();if(!row.contains("source_wall_edge")||!row.contains("layer")||!row.contains("final_id"))return refuse("strip_lineage_fields_missing");if(row["final_id"].cast<std::int64_t>()!=static_cast<std::int64_t>(i)||row["layer"].cast<std::int64_t>()!=static_cast<std::int64_t>(i/loop.size()+1))return refuse("strip_lineage_id_mismatch");bool found=false;for(const auto& wh:loop){auto wr=wh.cast<py::dict>();if(wr["edge_id"].cast<std::int64_t>()==row["source_wall_edge"].cast<std::int64_t>()){found=true;for(const char* k:{"feature","patch","physical_group","component","provenance"})if(!row.contains(k)||py::str(row[k]).cast<std::string>()!=py::str(wr[k]).cast<std::string>())return refuse("strip_lineage_semantics_mismatch");}}if(!found)return refuse("strip_lineage_edge_unknown");}

    py::list metrics;std::vector<MetricSample> tri_samples,core_samples,strip_samples;double max_skew=0.,max_aspect=0.;double tri_sk=0.,tri_ar=0.,tri_j=1e300,core_sk=0.,core_ar=0.,core_j=1e300,strip_sk=0.,strip_ar=0.,strip_j=1e300;
    for(const auto& f:at){P n;if(!unit(cross(sub(artifact[f[1]],artifact[f[0]]),sub(artifact[f[2]],artifact[f[0]])),n))return refuse("triangle_degenerate");double j=tri_jac(f,artifact,n);if(!(j>1e-12))return refuse("triangle_signed_jacobian_failed");double sk=tri_skew(f,artifact),ar=tri_aspect(f,artifact);max_skew=std::max(max_skew,sk);max_aspect=std::max(max_aspect,ar);tri_sk=std::max(tri_sk,sk);tri_ar=std::max(tri_ar,ar);tri_j=std::min(tri_j,j);tri_samples.push_back({sk,ar,j});metrics.append(metric_row(sk,ar,j,0.));}
    for(const auto& f:aq){P n;if(!unit(cross(sub(artifact[f[1]],artifact[f[0]]),sub(artifact[f[3]],artifact[f[0]])),n))return refuse("quad_degenerate");double jmin=1e300;for(auto uv:std::array<std::pair<double,double>,5>{{{0,0},{1,0},{1,1},{0,1},{.5,.5}}})jmin=std::min(jmin,quad_jac(f,artifact,n,uv.first,uv.second));if(!(jmin>1e-12))return refuse("quad_signed_jacobian_failed");double sk=quad_skew(f,artifact),ar=quad_aspect(f,artifact,false);max_skew=std::max(max_skew,sk);max_aspect=std::max(max_aspect,ar);core_sk=std::max(core_sk,sk);core_ar=std::max(core_ar,ar);core_j=std::min(core_j,jmin);core_samples.push_back({sk,ar,jmin});metrics.append(metric_row(sk,ar,jmin,0.));}
    for(std::size_t i=0;i<as.size();++i){const auto& f=as[i];P n;if(!unit(cross(sub(artifact[f[1]],artifact[f[0]]),sub(artifact[f[3]],artifact[f[0]])),n))return refuse("strip_degenerate");double jmin=1e300;for(auto uv:std::array<std::pair<double,double>,5>{{{0,0},{1,0},{1,1},{0,1},{.5,.5}}})jmin=std::min(jmin,quad_jac(f,artifact,n,uv.first,uv.second));if(!(jmin>1e-12))return refuse("strip_signed_jacobian_failed");double sk=quad_skew(f,artifact),ar=quad_aspect(f,artifact,true);max_skew=std::max(max_skew,sk);max_aspect=std::max(max_aspect,ar);strip_sk=std::max(strip_sk,sk);strip_ar=std::max(strip_ar,ar);strip_j=std::min(strip_j,jmin);strip_samples.push_back({sk,ar,jmin});metrics.append(metric_row(sk,ar,jmin,0.));}
    std::map<std::pair<std::int64_t,std::int64_t>,std::vector<P>> incidence;
auto add_incidence=[&](const Face& f){P n;P raw=(f.size()==3)?cross(sub(artifact[f[1]],artifact[f[0]]),sub(artifact[f[2]],artifact[f[0]])):cross(sub(artifact[f[1]],artifact[f[0]]),sub(artifact[f[3]],artifact[f[0]]));if(!unit(raw,n))return false;for(std::size_t i=0;i<f.size();++i){auto a=f[i],b=f[(i+1)%f.size()];if(a>b)std::swap(a,b);incidence[{a,b}].push_back(n);}return true;};
for(const auto& f:at)if(!add_incidence(f))return refuse("adjacent_normal_face_degenerate");
for(const auto& f:aq)if(!add_incidence(f))return refuse("adjacent_normal_face_degenerate");
// Strip side faces are audited by their own Jacobian/quality and wall-front metrics;
// surface dihedral incidence is reserved for retained/paired core faces.

std::set<std::pair<std::int64_t,std::int64_t>> excluded;
if(requested==0){for(const auto& h:loop){auto d=h.cast<py::dict>();auto a=d["v0"].cast<std::int64_t>(),b=d["v1"].cast<std::int64_t>();if(a>b)std::swap(a,b);excluded.insert({a,b});}}
else{for(std::size_t i=static_cast<std::size_t>(requested-1)*as.size()/loop.size();i<as.size();++i){const auto& f=as[i];auto a=f[2],b=f[3];if(a>b)std::swap(a,b);excluded.insert({a,b});}}
std::vector<double> adjacent_samples;
for(const auto& [edge,normals_on_edge]:incidence){if(excluded.count(edge))continue;if(normals_on_edge.size()!=2){if(normals_on_edge.size()>2)return refuse("adjacent_normal_non_manifold");continue;}adjacent_samples.push_back(angle_deg(normals_on_edge[0],normals_on_edge[1]));}
if(adjacent_samples.empty()){}
if(max_skew>.50||max_aspect>10.)return refuse("quality_threshold_failed");
    py::dict quality;quality["rows"]=metrics;quality["max_skewness"]=max_skew;quality["max_tangential_aspect_ratio"]=max_aspect;quality["max_wall_front_non_orthogonality"]=0.;py::dict distributions;distributions["retained_triangle"]=face_distribution(tri_samples);distributions["paired_core_quad"]=face_distribution(core_samples);distributions["strip_quad"]=face_distribution(strip_samples);std::vector<MetricSample> aggregate_samples=tri_samples;aggregate_samples.insert(aggregate_samples.end(),core_samples.begin(),core_samples.end());aggregate_samples.insert(aggregate_samples.end(),strip_samples.begin(),strip_samples.end());distributions["aggregate"]=face_distribution(aggregate_samples);quality["distributions"]=distributions;quality["adjacent_face_normal_dihedral_degrees"]=statistics(adjacent_samples,!adjacent_samples.empty());quality["wall_front_non_orthogonality_degrees"]=statistics(wall_angles,requested>0);quality["wall_front_tangential_leakage"]=statistics(wall_leaks,requested>0);quality["wall_front_non_orthogonality"]=quality["wall_front_non_orthogonality_degrees"];quality["wall_front_leakage_max"]=wall_leaks.empty()?0.:*std::max_element(wall_leaks.begin(),wall_leaks.end());quality["coordinate_metrics"]=true;
    py::dict topo;topo["duplicate"]=0;topo["non_manifold"]=0;topo["inverted"]=0;topo["degenerate"]=0;
    py::dict r;r["accepted"]=true;r["status"]="tri_quad_independent_quality_certificate_sealed";r["reason"]="independent_readback_quality_topology_verified";r["publication_eligible"]=false;r["candidate_discarded"]=false;r["auditor_route"]="private_default_off";r["auditor_schema"]="TriQuadIndependentQualityCertificate/v4";r["requested_layers"]=requested;r["actual_layers"]=actual;r["topology"]=topo;r["quality"]=quality;r["max_offset_residual"]=max_residual;r["producer_quality_ignored"]=true;r["independent_geometry_source"]="artifact_coordinates";return r;
}

PYBIND11_MODULE(native_tri_quad_independent_quality_readback,m){m.doc()="Private C++23 independent TRI+QUAD quality/topology readback";m.def("audit_artifact",&audit,py::arg("data"));}
