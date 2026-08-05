#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "native_tri_planar_face_pair_bl_template.hpp"
#include "native_tri_wall_edge_bl_preflight.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;
namespace auth = autotessell_native_tri_authority;
namespace edge = autotessell_native_tri_wall_edge;
namespace pair = autotessell_native_tri_planar_pair;
namespace base = autotessell_native_tri_planar_template;

namespace {
struct Label { std::string feature, patch, group, component, provenance; };
struct Source {
    std::vector<auth::Point> points;
    std::vector<auth::Triangle> faces;
    std::vector<Label> labels;
    std::string source_sha, semantic_sha, geometry_sha, certificate_sha;
    std::string source_kind, issuer, key_id;
    std::int64_t byte_count = -1;
};
struct Anchor {
    std::string source_sha, semantic_sha, certificate_sha, edge_sha;
    std::string issuer, key_id, loop_policy;
    std::int64_t byte_count = -1;
    std::vector<std::int64_t> endpoints;
};
struct Spec {
    std::string schema, template_id, source_sha, edge_sha, preflight_digest;
    std::string issuer, key_id;
    std::vector<std::int64_t> faces, active;
    std::vector<std::string> edges;
    Label label;
};
py::dict refuse(const std::string& why, std::int64_t requested) {
    py::dict r;
    r["accepted"]=false; r["status"]="native_tri_planar_face_pair_bl_template_refused";
    r["reason"]=why; r["requested_layers"]=requested; r["actual_layers"]=0;
    r["writer_invoked"]=false; r["preflight_only"]=false; r["artifact_emitted"]=false;
    r["publication_eligible"]=false; r["release_eligible"]=false;
    r["candidate_discarded"]=true; r["atomic_rollback"]=true;
    r["runtime_route"]="private_default_off"; r["route_calls"]=0;
    r["generated_vertices"]=py::list(); r["generated_faces"]=py::list();
    r["output_vertices"]=py::list(); r["output_faces"]=py::list();
    r["provenance"]=py::list(); r["generated_provenance"]=py::list();
    r["quality_witness"]=py::list(); r["wall_edge_ids"]=py::list();
    r["active_sector_face_ids"]=py::list(); r["layer_heights"]=py::list();
    return r;
}
bool sv(const py::dict& d,const char* k,std::string& v) {
    if(!d.contains(k)||!py::isinstance<py::str>(d[k])) return false;
    v=d[k].cast<std::string>(); return !v.empty();
}
bool iv(const py::dict& d,const char* k,std::int64_t& v) {
    if(!d.contains(k)||py::isinstance<py::bool_>(d[k])) return false;
    try { v=d[k].cast<std::int64_t>(); return true; } catch(...) { return false; }
}
bool bv(const py::dict& d,const char* k,bool& v) {
    if(!d.contains(k)||!py::isinstance<py::bool_>(d[k])) return false;
    v=d[k].cast<bool>(); return true;
}
bool h64(const std::string& v) {
    return v.size()==64U && std::all_of(v.begin(),v.end(),[](char c){
        return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
}
template<class T> bool seq(const py::handle& h,std::vector<T>& v) {
    try { v=h.cast<std::vector<T>>(); return true; } catch(...) { return false; }
}
void field(std::ostringstream& s,const std::string& v) { s<<v.size()<<':'<<v<<'|'; }
std::string semantic_stream(const Source& s) {
    std::ostringstream o; o<<"rows="<<s.faces.size()<<'|';
    for(std::size_t i=0;i<s.faces.size();++i) {
        const auto& f=s.faces[i];
        o<<i<<':'<<f[0]<<','<<f[1]<<','<<f[2]<<'|';
        field(o,s.labels[i].feature); field(o,s.labels[i].patch);
        field(o,s.labels[i].group); field(o,s.labels[i].component);
        field(o,s.labels[i].provenance);
    }
    return o.str();
}
bool parse_source(const py::dict& input,Source& s,std::string& why) {
    py::dict c=input;
    if(input.contains("certificate")) {
        if(!py::isinstance<py::dict>(input["certificate"])) { why="source_certificate_payload_invalid"; return false; }
        c=input["certificate"].cast<py::dict>();
    }
    std::string schema;
    if(!sv(c,"schema",schema)||schema!="NativeTriAuthorityCertificate/v2"||
       !sv(c,"source_sha256",s.source_sha)||!h64(s.source_sha)||
       !sv(c,"semantic_ledger_sha256",s.semantic_sha)||!h64(s.semantic_sha)||
       !sv(c,"canonical_geometry_sha256",s.geometry_sha)||!h64(s.geometry_sha)||
       !sv(c,"certificate_sha256",s.certificate_sha)||!h64(s.certificate_sha)||
       !sv(c,"source_kind",s.source_kind)||!sv(c,"issuer",s.issuer)||
       !sv(c,"key_id",s.key_id)||!iv(c,"source_byte_count",s.byte_count)||
       s.byte_count<=0) { why="source_certificate_fields_invalid"; return false; }
    try {
        s.points=c["canonical_points"].cast<std::vector<auth::Point>>();
        s.faces=c["canonical_triangles"].cast<std::vector<auth::Triangle>>();
    } catch(...) { why="source_certificate_arrays_invalid"; return false; }
    if(s.points.empty()||s.faces.empty()||!c.contains("face_ledger")) { why="source_certificate_arrays_empty"; return false; }
    try {
        const py::sequence rows=c["face_ledger"].cast<py::sequence>();
        if(rows.size()!=s.faces.size()) { why="source_face_ledger_coverage_incomplete"; return false; }
        s.labels.assign(s.faces.size(),{}); std::vector<bool> seen(s.faces.size(),false);
        for(const py::handle& item:rows) {
            const py::dict row=item.cast<py::dict>(); std::int64_t id=-1,sid=-2;
            std::vector<std::int64_t> vertices; Label l;
            if(!iv(row,"face_id",id)||!iv(row,"source_facet_id",sid)||id!=sid||id<0||
               static_cast<std::size_t>(id)>=s.faces.size()||!row.contains("vertices")||
               !seq(row["vertices"],vertices)||vertices.size()!=3U||
               auth::Triangle{vertices[0],vertices[1],vertices[2]}!=s.faces[static_cast<std::size_t>(id)]||
               seen[static_cast<std::size_t>(id)]||!sv(row,"feature",l.feature)||
               !sv(row,"patch",l.patch)||!sv(row,"physical_group",l.group)||
               !sv(row,"component",l.component)||!sv(row,"provenance",l.provenance)) {
                why="source_face_binding_invalid"; return false;
            }
            s.labels[static_cast<std::size_t>(id)]=l; seen[static_cast<std::size_t>(id)]=true;
        }
        if(std::any_of(seen.begin(),seen.end(),[](bool x){return !x;})) { why="source_face_binding_incomplete"; return false; }
    } catch(...) { why="source_face_ledger_invalid"; return false; }
    const auth::CanonicalSource canonical{s.points,s.faces,{},{},s.source_kind};
    if(auth::sha256_text(semantic_stream(s))!=s.semantic_sha) { why="source_semantic_digest_mismatch"; return false; }
    if(auth::sha256_text(auth::canonical_geometry_stream(canonical))!=s.geometry_sha) { why="source_geometry_digest_mismatch"; return false; }
    std::ostringstream cert;
    cert<<"NativeTriAuthorityCertificate/v2|"<<s.source_kind<<'|'<<s.source_sha<<'|'<<s.geometry_sha<<'|'<<s.semantic_sha<<'|'<<s.issuer<<'|'<<s.key_id;
    if(auth::sha256_text(cert.str())!=s.certificate_sha) { why="source_certificate_digest_mismatch"; return false; }
    if(!c.contains("topology")||!py::isinstance<py::dict>(c["topology"])) { why="source_topology_not_strict"; return false; }
    const py::dict top=c["topology"].cast<py::dict>(); bool strict=false,checked=false;
    if(!bv(top,"strict_zero",strict)||!strict||!bv(top,"self_intersection_checked",checked)||!checked) { why="source_topology_not_strict"; return false; }
    for(const char* k:{"duplicate","non_manifold","open_edges","degenerate","inverted","self_intersection"}) {
        std::int64_t n=-1; if(!iv(top,k,n)||n!=0) { why="source_topology_not_strict"; return false; }
    }
    bool authoritative=false,groups=true,features=true; std::string canonicalization;
    if(!bv(c,"source_provenance_authoritative",authoritative)||!authoritative||
       !bv(c,"physical_groups_inferred",groups)||groups||!bv(c,"feature_ids_inferred",features)||features||
       !sv(c,"canonicalization",canonicalization)||canonicalization!="exact_coordinate_identity_only") {
        why="source_authority_fields_invalid"; return false;
    }
    return true;
}
bool parse_edges(const py::list& records,std::vector<edge::EdgeRow>& rows,std::string& why) {
    try {
        for(const py::handle& item:records) {
            const py::dict d=item.cast<py::dict>(); edge::EdgeRow r; std::vector<std::int64_t> e;
            if(!sv(d,"edge_id",r.edge_id)||!d.contains("endpoint_vertex_ids")||!seq(d["endpoint_vertex_ids"],e)||e.size()!=2U||
               !d.contains("incident_face_ids")||!seq(d["incident_face_ids"],r.incident_faces)||
               !d.contains("directed_sector_face_ids")||!seq(d["directed_sector_face_ids"],r.directed_sector_faces)||
               !d.contains("directed_sector_ids")||!seq(d["directed_sector_ids"],r.directed_sector_ids)||
               !sv(d,"wall_role",r.wall_role)||!sv(d,"patch_boundary_role",r.patch_boundary_role)||
               !sv(d,"feature",r.feature)||!sv(d,"patch",r.patch)||!sv(d,"physical_group",r.physical_group)||
               !sv(d,"component",r.component)||!sv(d,"provenance",r.provenance)) {
                why="wall_edge_record_invalid"; return false;
            }
            r.endpoints={e[0],e[1]}; rows.push_back(r);
        }
        return true;
    } catch(...) { why="wall_edge_record_invalid"; return false; }
}
bool parse_anchor(const py::dict& d,Anchor& a) {
    return sv(d,"source_sha256",a.source_sha)&&h64(a.source_sha)&&
           sv(d,"semantic_ledger_sha256",a.semantic_sha)&&h64(a.semantic_sha)&&
           sv(d,"certificate_sha256",a.certificate_sha)&&h64(a.certificate_sha)&&
           sv(d,"edge_ledger_sha256",a.edge_sha)&&h64(a.edge_sha)&&
           sv(d,"issuer",a.issuer)&&sv(d,"key_id",a.key_id)&&
           sv(d,"loop_policy",a.loop_policy)&&iv(d,"source_byte_count",a.byte_count)&&
           (!d.contains("loop_endpoint_vertex_ids")||seq(d["loop_endpoint_vertex_ids"],a.endpoints));
}
bool parse_spec(const py::dict& d,Spec& s) {
    return sv(d,"schema",s.schema)&&s.schema=="NativeTriPlanarFacePairTemplate/v1"&&
           sv(d,"template_id",s.template_id)&&sv(d,"source_certificate_sha256",s.source_sha)&&h64(s.source_sha)&&
           sv(d,"edge_ledger_sha256",s.edge_sha)&&h64(s.edge_sha)&&sv(d,"preflight_digest",s.preflight_digest)&&h64(s.preflight_digest)&&
           sv(d,"issuer",s.issuer)&&sv(d,"key_id",s.key_id)&&d.contains("source_face_ids")&&seq(d["source_face_ids"],s.faces)&&s.faces.size()==2U&&
           d.contains("wall_edge_ids")&&seq(d["wall_edge_ids"],s.edges)&&s.edges.size()==4U&&
           d.contains("active_sector_face_ids")&&seq(d["active_sector_face_ids"],s.active)&&s.active.size()==4U&&
           sv(d,"feature",s.label.feature)&&sv(d,"patch",s.label.patch)&&sv(d,"physical_group",s.label.group)&&sv(d,"component",s.label.component)&&sv(d,"provenance",s.label.provenance);
}
bool bind_pair(const Source& s,const std::vector<edge::EdgeRow>& rows,const Anchor& a,const Spec& t,
               std::array<std::int64_t,4>& outer_ids,pair::Point& normal,std::string& why) {
    if(a.byte_count!=s.byte_count||a.source_sha!=s.source_sha||a.semantic_sha!=s.semantic_sha||
       a.certificate_sha!=s.certificate_sha||a.loop_policy!="closed_nonbranching"||!a.endpoints.empty()||
       rows.size()!=4U||t.faces.size()!=2U||t.source_sha!=s.certificate_sha||t.edge_sha!=a.edge_sha||
       t.issuer!=a.issuer||t.key_id!=a.key_id||t.faces[0]<0||t.faces[1]<0||t.faces[0]>=static_cast<std::int64_t>(s.faces.size())||
       t.faces[1]>=static_cast<std::int64_t>(s.faces.size())||t.faces[0]>=t.faces[1]) {
        why="pair_authority_or_template_anchor_mismatch"; return false;
    }
    const Label& l0=s.labels[static_cast<std::size_t>(t.faces[0])]; const Label& l1=s.labels[static_cast<std::size_t>(t.faces[1])];
    if(l0.feature!=l1.feature||l0.patch!=l1.patch||l0.group!=l1.group||l0.component!=l1.component||l0.provenance!=l1.provenance||
       t.label.feature!=l0.feature||t.label.patch!=l0.patch||t.label.group!=l0.group||t.label.component!=l0.component||t.label.provenance!=l0.provenance) {
        why="pair_label_binding_invalid"; return false;
    }
    std::set<std::pair<std::int64_t,std::int64_t>> toggled;
    for(const auto id:t.faces) {
        const auto& f=s.faces[static_cast<std::size_t>(id)];
        for(int i=0;i<3;++i) { const auto k=edge::undirected_edge(f[i],f[(i+1)%3]); if(!toggled.insert(k).second)toggled.erase(k); }
    }
    if(toggled.size()!=4U) { why="pair_faces_not_adjacent"; return false; }
    std::set<std::pair<std::int64_t,std::int64_t>> actual;
    for(std::size_t i=0;i<rows.size();++i) {
        const auto& r=rows[i]; const auto k=edge::undirected_edge(r.endpoints[0],r.endpoints[1]);
        if(!actual.insert(k).second||t.edges[i]!=r.edge_id||toggled.count(k)==0U||r.wall_role!="wall"||
           r.feature!=l0.feature||r.patch!=l0.patch||r.physical_group!=l0.group||r.component!=l0.component||r.provenance!=l0.provenance||
           std::find(r.incident_faces.begin(),r.incident_faces.end(),t.active[i])==r.incident_faces.end()||
           std::find(t.faces.begin(),t.faces.end(),t.active[i])==t.faces.end()) {
            why="pair_wall_edge_binding_invalid"; return false;
        }
        int selected=0; std::int64_t selected_id=-1;
        for(const auto id:r.incident_faces) if(std::find(t.faces.begin(),t.faces.end(),id)!=t.faces.end()){++selected;selected_id=id;}
        if(selected!=1||selected_id!=t.active[i]) { why="pair_active_sector_binding_invalid"; return false; }
        outer_ids[i]=r.endpoints[0];
        if(i+1<rows.size()&&r.endpoints[1]!=rows[i+1].endpoints[0]) { why="pair_outer_loop_order_invalid"; return false; }
    }
    if(rows.back().endpoints[1]!=rows.front().endpoints[0]||actual!=toggled) { why="pair_outer_boundary_set_invalid"; return false; }
    std::set<std::int64_t> vertices; for(const auto& r:rows){vertices.insert(r.endpoints[0]);vertices.insert(r.endpoints[1]);}
    if(vertices.size()!=4U) { why="pair_outer_vertex_count_invalid"; return false; }
    const auto& f0=s.faces[static_cast<std::size_t>(t.faces[0])]; const auto& f1=s.faces[static_cast<std::size_t>(t.faces[1])];
    normal=base::unit(auth::cross(auth::sub(s.points[f0[1]],s.points[f0[0]]),auth::sub(s.points[f0[2]],s.points[f0[0]])));
    const auto n1=base::unit(auth::cross(auth::sub(s.points[f1[1]],s.points[f1[0]]),auth::sub(s.points[f1[2]],s.points[f1[0]])));
    if(auth::dot(normal,n1)<1.0-1.0e-10){why="pair_face_normals_not_coherent";return false;}
    for(const auto id:f1) if(std::abs(auth::dot(auth::sub(s.points[id],s.points[f0[0]]),normal))>1.0e-12){why="pair_faces_not_coplanar";return false;}
    std::array<pair::Point,4> outer{}; for(int i=0;i<4;++i) outer[static_cast<std::size_t>(i)]=s.points[static_cast<std::size_t>(outer_ids[i])];
    if(!pair::square_like_quad(outer,normal,1.0e-12,why)) return false;
    return true;
}
std::vector<double> heights(std::int64_t n,double first,double growth,std::string& why) {
    std::vector<double> out; if(n<0||n>1024){why="pair_layer_count_invalid";return out;} if(n==0)return out;
    if(!std::isfinite(first)||!std::isfinite(growth)||first<=0.0||growth<1.0){why="pair_schedule_invalid";return out;}
    double x=first; out.reserve(static_cast<std::size_t>(n));
    for(std::int64_t i=0;i<n;++i){if(!std::isfinite(x)||x<=0.0){why="pair_schedule_overflow";out.clear();return out;}out.push_back(x);x*=growth;}
    return out;
}
std::string preflight(const Source& s,const std::string& edge_sha,const std::string& policy,std::int64_t n,double first,double growth,const std::vector<double>& h) {
    std::ostringstream o; o<<"NativeTriWallEdgeBLPreflight/v1|"<<s.certificate_sha<<'|'<<s.source_sha<<'|'<<s.semantic_sha<<'|'<<edge_sha<<'|'<<policy<<'|'<<n<<'|'<<first<<'|'<<growth;
    for(double x:h) o<<'|'<<x;
    return o.str();
}
py::list to_points(const std::vector<pair::Point>& v){py::list o;for(const auto& p:v){py::list r;for(double x:p)r.append(x);o.append(r);}return o;}
py::list to_faces(const std::vector<pair::Triangle>& v){py::list o;for(const auto& f:v){py::list r;for(auto x:f)r.append(x);o.append(r);}return o;}
py::dict label_py(const Label& l){py::dict d;d["feature"]=l.feature;d["patch"]=l.patch;d["physical_group"]=l.group;d["component"]=l.component;d["provenance"]=l.provenance;return d;}
py::dict point_receipt(std::int64_t id,const pair::Point& p,std::int64_t layer,const Spec& t,const Label& l,const std::vector<std::string>& edges) {
    py::dict d;d["vertex_id"]=id;d["x"]=p[0];d["y"]=p[1];d["z"]=p[2];d["layer"]=layer;
    d["source_face_ids"]=t.faces;d["source_wall_edge_ids"]=edges;d["active_sector_face_ids"]=t.active;
    const py::dict labels=label_py(l); for(const auto& item:labels) d[item.first]=item.second; return d;
}
py::dict q_receipt(std::int64_t id,std::int64_t layer,const std::string& role,const std::string& eid,int diag,const pair::Raw& r,const pair::Metric& m,double wall) {
    py::dict d;d["output_face_id"]=id;d["layer"]=layer;d["role"]=role;d["source_wall_edge"]=eid;d["diagonal"]=diag;
    d["raw_physical_aspect_ratio"]=r.aspect;d["raw_skewness"]=r.skewness;d["raw_mean_ratio"]=r.mean_ratio;
    d["raw_angle_nonorthogonality_degrees"]=r.angle_nonorthogonality;d["metric_aspect_ratio"]=m.aspect;d["metric_skewness"]=m.skewness;
    d["metric_angle_nonorthogonality_degrees"]=m.angle_nonorthogonality;d["wall_front_non_orthogonality_degrees"]=wall;
    d["signed_area"]=r.signed_area;d["accepted"]=true;return d;
}
double pct(std::vector<double> v,double p){if(v.empty())return std::numeric_limits<double>::infinity();std::sort(v.begin(),v.end());std::size_t i=p<=1.0?0U:static_cast<std::size_t>(std::ceil(p*v.size()))-1U;return v[std::min(i,v.size()-1U)];}
pair::TriangleEvaluation core_eval(const pair::Triangle& f,const std::vector<pair::Point>& points,const pair::Point& n) {
    const auto& a=points[static_cast<std::size_t>(f[0])];const auto& b=points[static_cast<std::size_t>(f[1])];const auto& c=points[static_cast<std::size_t>(f[2])];
    const base::Quality q=base::triangle_quality(a,b,c,n);pair::TriangleEvaluation e;
    e.raw={q.physical_aspect,q.skewness,pair::mean_ratio(a,b,c),q.angle_nonorthogonality,q.signed_area};
    e.metric={q.skewness,q.aspect,q.angle_nonorthogonality};e.wall_nonorthogonality=0.0;return e;
}
bool core_valid(const pair::PairEvaluation& e) {
    return e.min_signed_area>1.0e-14&&e.max_metric_skewness<=0.35+1e-12&&e.max_metric_aspect<=1.60+1e-12&&
           e.max_raw_aspect<=5.50+1e-12&&e.min_raw_mean_ratio>=0.30-1e-12&&e.max_raw_angle_nonorthogonality<=55.0+1e-12;
}
py::dict run(const py::dict& source_input,const py::list& edge_rows,const py::dict& edge_anchor,const py::dict& template_anchor,
            std::int64_t requested,double first,double growth) {
    if(requested<0)return refuse("pair_requested_layers_invalid",requested);
    Source s;std::string why;if(!parse_source(source_input,s,why))return refuse(why,requested);
    Anchor a;if(!parse_anchor(edge_anchor,a))return refuse("pair_edge_anchor_invalid",requested);
    std::vector<edge::EdgeRow> rows;if(!parse_edges(edge_rows,rows,why))return refuse(why,requested);
    const std::string edge_sha=auth::sha256_text(edge::canonical_edge_stream(rows,a.loop_policy,a.endpoints));
    if(edge_sha!=a.edge_sha)return refuse("pair_edge_ledger_digest_mismatch",requested);
    std::size_t count=0;if(!edge::validate_edge_ledger_geometry(s.points,s.faces,rows,a.loop_policy,a.endpoints,why,count))return refuse(why,requested);
    if(count!=4U)return refuse("pair_requires_four_outer_edges",requested);
    Spec t;if(!parse_spec(template_anchor,t))return refuse("pair_template_invalid",requested);
    std::array<std::int64_t,4> outer_ids{};pair::Point normal{};
    if(!bind_pair(s,rows,a,t,outer_ids,normal,why))return refuse(why,requested);
    const auto h=heights(requested,first,growth,why);if(requested>0&&h.empty())return refuse(why,requested);
    if(auth::sha256_text(preflight(s,edge_sha,a.loop_policy,requested,first,growth,h))!=t.preflight_digest)return refuse("pair_preflight_digest_mismatch",requested);
    if(requested==0){
        py::dict r;r["accepted"]=true;r["status"]="native_tri_planar_face_pair_bl_identity";r["reason"]="authority_bound_source_identity";
        r["requested_layers"]=0;r["actual_layers"]=0;r["source_certificate_sha256"]=s.certificate_sha;r["source_sha256"]=s.source_sha;r["source_byte_count"]=s.byte_count;
        r["semantic_ledger_sha256"]=s.semantic_sha;r["canonical_geometry_sha256"]=s.geometry_sha;r["edge_ledger_sha256"]=edge_sha;r["preflight_digest"]=t.preflight_digest;
        r["template_id"]=t.template_id;r["source_face_ids"]=t.faces;r["wall_edge_ids"]=t.edges;r["active_sector_face_ids"]=t.active;
        r["bl0_identity"]=true;r["writer_invoked"]=false;r["preflight_only"]=false;r["artifact_emitted"]=false;r["publication_eligible"]=false;r["release_eligible"]=false;
        r["candidate_discarded"]=false;r["atomic_rollback"]=false;r["runtime_route"]="private_default_off";r["route_calls"]=0;
        r["output_vertices"]=to_points(s.points);r["output_faces"]=to_faces(s.faces);r["generated_vertices"]=py::list();r["generated_faces"]=py::list();
        r["provenance"]=py::list();r["generated_provenance"]=py::list();r["quality_witness"]=py::list();r["source_face_coverage_complete"]=true;r["identity_digest"]=s.certificate_sha;r["layer_heights"]=py::list();return r;
    }
    double scale=1.0;for(const auto& p:s.points)scale=std::max(scale,auth::norm(p));const double tol=1.0e-12*scale;const double area_tol=1.0e-14*scale*scale;
    std::array<pair::Point,4> outer{};for(int i=0;i<4;++i)outer[static_cast<std::size_t>(i)]=s.points[static_cast<std::size_t>(outer_ids[i])];
    const double side_min=std::min({auth::norm(auth::sub(outer[1],outer[0])),auth::norm(auth::sub(outer[2],outer[1])),auth::norm(auth::sub(outer[3],outer[2])),auth::norm(auth::sub(outer[0],outer[3]))});
    std::vector<pair::Point> points=s.points;std::vector<pair::Triangle> output,generated;std::vector<bool> mask;
    py::list outprov,genprov,genverts,witness;std::vector<pair::Raw> raws;std::vector<pair::Metric> metrics;std::vector<double>walls;std::vector<int> masks;
    auto pairprov=[&](std::int64_t id,const std::string& role,std::int64_t layer,const std::string& eid,int diag){
        py::dict p=label_py(s.labels[static_cast<std::size_t>(t.faces[0])]);p["output_face_id"]=id;p["source_face_ids"]=t.faces;p["active_sector_face_ids"]=t.active;p["replacement_role"]=role;p["layer"]=layer;
        p["source_wall_edge_ids"]=eid.empty()?t.edges:std::vector<std::string>{eid};p["diagonal"]=diag;return p;
    };
    for(std::size_t i=0;i<s.faces.size();++i){const auto id=static_cast<std::int64_t>(i);if(id==t.faces[0]||id==t.faces[1])continue;output.push_back(s.faces[i]);mask.push_back(false);py::dict p=label_py(s.labels[i]);p["output_face_id"]=static_cast<std::int64_t>(output.size()-1);p["source_face_id"]=id;p["source_face_ids"]=std::vector<std::int64_t>{id};p["active_sector_face_ids"]=std::vector<std::int64_t>{};p["source_wall_edge_ids"]=std::vector<std::string>{};p["replacement_role"]="source_retained";outprov.append(p);}
    auto append=[&](const pair::Triangle& f,const pair::TriangleEvaluation& e,std::int64_t layer,const std::string& role,const std::string& eid,int diag){
        output.push_back(f);generated.push_back(f);mask.push_back(true);const auto id=static_cast<std::int64_t>(output.size()-1);auto p=pairprov(id,role,layer,eid,diag);outprov.append(p);genprov.append(p);
        raws.push_back(e.raw);metrics.push_back(e.metric);walls.push_back(e.wall_nonorthogonality);witness.append(q_receipt(id,layer,role,eid.empty()?"core":eid,diag,e.raw,e.metric,e.wall_nonorthogonality));
    };
    std::vector<std::array<std::int64_t,4>> fronts;double cumulative=0.0;
    for(std::int64_t layer=0;layer<requested;++layer){
        cumulative+=h[static_cast<std::size_t>(layer)];
        if(!std::isfinite(cumulative)||cumulative>=0.5*side_min-tol)return refuse("pair_cumulative_height_reaches_half_width",requested);
        std::array<std::int64_t,4> lower=layer==0?outer_ids:fronts[static_cast<std::size_t>(layer-1)];
        std::array<pair::Point,4> inner{};
        if(!pair::offset_quad(outer,normal,cumulative,inner,tol,why))return refuse(why,requested);
        std::array<std::int64_t,4> upper{};
        for(int i=0;i<4;++i){upper[static_cast<std::size_t>(i)]=static_cast<std::int64_t>(points.size());points.push_back(inner[static_cast<std::size_t>(i)]);const int prev=(i+3)%4;
            genverts.append(point_receipt(upper[static_cast<std::size_t>(i)],inner[static_cast<std::size_t>(i)],layer+1,t,s.labels[static_cast<std::size_t>(t.faces[0])],
                {t.edges[static_cast<std::size_t>(prev)],t.edges[static_cast<std::size_t>(i)]}));}
        fronts.push_back(upper);
        std::array<std::array<std::array<pair::Triangle,2>,2>,4> options{};
        for(int i=0;i<4;++i){const int j=(i+1)%4;const auto li=lower[static_cast<std::size_t>(i)],lj=lower[static_cast<std::size_t>(j)],ui=upper[static_cast<std::size_t>(i)],uj=upper[static_cast<std::size_t>(j)];
            options[static_cast<std::size_t>(i)][0]={pair::Triangle{li,lj,uj},pair::Triangle{li,uj,ui}};options[static_cast<std::size_t>(i)][1]={pair::Triangle{li,lj,ui},pair::Triangle{lj,uj,ui}};}
        const auto choice=pair::choose_ring(options,points,lower,upper,normal,area_tol);
        if(!choice.valid) {
            py::dict rejected=refuse("pair_no_quality_admissible_ring",requested);
            py::list witnesses;
            for(int wi=0;wi<4;++wi) {
                const auto& ev=choice.evaluation[static_cast<std::size_t>(wi)];
                py::dict w; w["edge_index"]=wi; w["diagonal"]=ev.diagonal; w["valid"]=ev.valid;
                w["metric_skewness"]=ev.max_metric_skewness; w["metric_aspect_ratio"]=ev.max_metric_aspect;
                w["raw_aspect_ratio"]=ev.max_raw_aspect; w["raw_mean_ratio"]=ev.min_raw_mean_ratio;
                w["raw_angle_nonorthogonality_degrees"]=ev.max_raw_angle_nonorthogonality;
                w["wall_front_non_orthogonality_degrees"]=ev.max_wall_nonorthogonality;
                witnesses.append(w);
            }
            rejected["quality_witness"]=witnesses;
            rejected["best_ring_mask"]=choice.mask;
            return rejected;
        }
        masks.push_back(choice.mask);
        for(int i=0;i<4;++i){const int d=(choice.mask>>i)&1;const auto& e=choice.evaluation[static_cast<std::size_t>(i)];append(choice.triangles[static_cast<std::size_t>(i)][0],e.first,layer+1,"boundary_layer_ring",t.edges[static_cast<std::size_t>(i)],d);append(choice.triangles[static_cast<std::size_t>(i)][1],e.second,layer+1,"boundary_layer_ring",t.edges[static_cast<std::size_t>(i)],d);}
    }
    if(fronts.empty()) return refuse("pair_no_front",requested);
    const auto last=fronts.back();
    const std::array<std::array<pair::Triangle,2>,2> cores={{
        {pair::Triangle{last[0],last[1],last[2]}, pair::Triangle{last[0],last[2],last[3]}},
        {pair::Triangle{last[0],last[1],last[3]}, pair::Triangle{last[1],last[2],last[3]}}}};
    pair::PairEvaluation ce[2]{};for(int d=0;d<2;++d){ce[d].diagonal=d;ce[d].first=core_eval(cores[static_cast<std::size_t>(d)][0],points,normal);ce[d].second=core_eval(cores[static_cast<std::size_t>(d)][1],points,normal);
        ce[d].max_metric_skewness=std::max(ce[d].first.metric.skewness,ce[d].second.metric.skewness);ce[d].max_metric_aspect=std::max(ce[d].first.metric.aspect,ce[d].second.metric.aspect);
        ce[d].max_raw_aspect=std::max(ce[d].first.raw.aspect,ce[d].second.raw.aspect);ce[d].min_raw_mean_ratio=std::min(ce[d].first.raw.mean_ratio,ce[d].second.raw.mean_ratio);
        ce[d].max_raw_angle_nonorthogonality=std::max(ce[d].first.raw.angle_nonorthogonality,ce[d].second.raw.angle_nonorthogonality);ce[d].min_signed_area=std::min(ce[d].first.raw.signed_area,ce[d].second.raw.signed_area);ce[d].max_wall_nonorthogonality=0.0;ce[d].valid=core_valid(ce[d]);}
    const int cd=pair::pair_rank(ce[0])<=pair::pair_rank(ce[1])?0:1;if(!ce[cd].valid)return refuse("pair_core_quality_failure",requested);
    append(cores[static_cast<std::size_t>(cd)][0],ce[cd].first,requested,"boundary_layer_core","",cd);append(cores[static_cast<std::size_t>(cd)][1],ce[cd].second,requested,"boundary_layer_core","",cd);
    const auto topo=base::audit_output(points,output,mask,normal,area_tol);if(topo.invalid||topo.degenerate||topo.inverted||topo.duplicate||topo.open_edges||topo.non_manifold||topo.self_intersection)return refuse("pair_output_topology_failed",requested);
    std::vector<pair::Triangle> retained;for(std::size_t i=0;i<s.faces.size();++i){const auto id=static_cast<std::int64_t>(i);if(id!=t.faces[0]&&id!=t.faces[1])retained.push_back(s.faces[i]);}
    const auto collision=base::audit_collisions(points,generated,retained,area_tol);if(collision.rejected_contacts)return refuse("pair_candidate_collision",requested);
    const auto independent=autotessell_surface_bl_independent_audit::audit_faces(points,generated,outer[0],normal,static_cast<long double>(area_tol),static_cast<long double>(tol));
    if(!independent.finite||independent.invalid||independent.inverted||independent.duplicate||independent.non_manifold||independent.self_intersection||independent.source_plane_deviation>static_cast<long double>(tol))return refuse("pair_long_double_audit_failed",requested);
    std::vector<double>ra,rs,rm,rr,ma,ms,mm,mw;for(const auto& x:raws){ra.push_back(x.aspect);rs.push_back(x.skewness);rm.push_back(x.mean_ratio);rr.push_back(x.angle_nonorthogonality);}for(const auto& x:metrics){ma.push_back(x.aspect);ms.push_back(x.skewness);mm.push_back(x.angle_nonorthogonality);}mw=walls;
    auto mx=[](const std::vector<double>&v){return *std::max_element(v.begin(),v.end());};auto mn=[](const std::vector<double>&v){return *std::min_element(v.begin(),v.end());};
    const double p95ra=pct(ra,.95),p05rm=pct(rm,.05),p95ms=pct(ms,.95),p99ma=pct(ma,.99),p95mw=pct(mw,.95);const double maxra=mx(ra),minrm=mn(rm),maxrr=mx(rr),maxms=mx(ms),maxma=mx(ma),maxmw=mx(mw);
    if(!(p95ra<=4.5+1e-12&&maxra<=5.5+1e-12&&p05rm>=.35-1e-12&&minrm>=.30-1e-12&&maxrr<=55.0+1e-12&&p95ms<=.32+1e-12&&maxms<=.35+1e-12&&p99ma<=1.50+1e-12&&maxma<=1.60+1e-12&&p95mw<=.50+1e-12&&maxmw<=1.0+1e-12))return refuse("pair_quality_distribution_gate_failed",requested);
    std::ostringstream ds;ds<<"NativeTriPlanarFacePairBL/v1|"<<s.certificate_sha<<'|'<<edge_sha<<'|'<<t.preflight_digest<<'|'<<t.template_id<<'|'<<requested<<'|'<<std::setprecision(17)<<first<<'|'<<growth;for(int x:masks)ds<<"|mask="<<x;ds<<"|core="<<cd;for(const auto&p:points)ds<<'|'<<p[0]<<','<<p[1]<<','<<p[2];for(const auto&f:output)ds<<'|'<<f[0]<<','<<f[1]<<','<<f[2];const std::string digest=auth::sha256_text(ds.str());
    py::dict top;top["invalid"]=topo.invalid;top["degenerate"]=topo.degenerate;top["inverted"]=topo.inverted;top["duplicate"]=topo.duplicate;top["open_edges"]=topo.open_edges;top["non_manifold"]=topo.non_manifold;top["self_intersection"]=topo.self_intersection;
    py::dict col;col["checked"]=true;col["broad_phase_pairs"]=collision.broad_phase_pairs;col["narrow_phase_hits"]=collision.narrow_phase_hits;col["allowed_shared_contacts"]=collision.allowed_shared_contacts;col["rejected_contacts"]=collision.rejected_contacts;
    py::dict q;q["raw_physical_aspect_p95"]=p95ra;q["raw_physical_aspect_max"]=maxra;q["raw_skewness_max"]=mx(rs);q["raw_mean_ratio_p05"]=p05rm;q["raw_mean_ratio_min"]=minrm;q["raw_angle_nonorthogonality_max_degrees"]=maxrr;
    q["metric_skewness_p95"]=p95ms;q["metric_skewness_max"]=maxms;q["metric_aspect_ratio_p99"]=p99ma;q["metric_aspect_ratio_max"]=maxma;q["metric_angle_nonorthogonality_max_degrees"]=mx(mm);
    q["wall_front_non_orthogonality_p95_degrees"]=p95mw;q["wall_front_non_orthogonality_max_degrees"]=maxmw;
    q["raw_quality_gate_pass"]=true;q["metric_quality_gate_pass"]=true;q["count_is_report_only"]=true;
    py::dict indep;indep["accepted"]=independent.finite&&independent.invalid==0&&independent.inverted==0&&independent.duplicate==0&&independent.non_manifold==0&&independent.self_intersection==0;indep["source_plane_deviation"]=static_cast<double>(independent.source_plane_deviation);q["independent_long_double_audit"]=indep;
    py::dict r;r["accepted"]=true;r["status"]="native_tri_planar_face_pair_bl_artifact_sealed";r["reason"]="authority_bound_planar_face_pair_quality_passed";r["requested_layers"]=requested;r["actual_layers"]=requested;r["layer_heights"]=h;r["cumulative_height"]=cumulative;
    r["source_certificate_sha256"]=s.certificate_sha;r["source_sha256"]=s.source_sha;r["source_byte_count"]=s.byte_count;r["semantic_ledger_sha256"]=s.semantic_sha;r["canonical_geometry_sha256"]=s.geometry_sha;r["edge_ledger_sha256"]=edge_sha;r["preflight_digest"]=t.preflight_digest;r["template_id"]=t.template_id;r["deterministic_digest"]=digest;r["template_digest"]=digest;
    r["source_face_ids"]=t.faces;r["source_faces_removed"]=t.faces;r["source_faces_retained"]=py::make_tuple();r["source_face_coverage_complete"]=true;r["wall_edge_ids"]=t.edges;r["active_sector_face_ids"]=t.active;
    py::list kept;for(std::size_t i=0;i<s.faces.size();++i){const auto id=static_cast<std::int64_t>(i);if(id!=t.faces[0]&&id!=t.faces[1])kept.append(id);}r["source_faces_retained"]=kept;
    r["generated_vertices"]=genverts;r["generated_faces"]=to_faces(generated);r["output_vertices"]=to_points(points);r["output_faces"]=to_faces(output);r["provenance"]=outprov;r["generated_provenance"]=genprov;r["quality_witness"]=witness;r["quality"]=q;r["topology"]=top;r["collision"]=col;
    r["writer_invoked"]=true;r["preflight_only"]=false;r["artifact_emitted"]=true;r["publication_eligible"]=false;r["release_eligible"]=false;r["candidate_discarded"]=false;r["atomic_rollback"]=false;r["bl0_identity"]=false;r["runtime_route"]="private_default_off";r["route_calls"]=0;return r;
}
py::dict guarded(const py::dict& s,const py::list& e,const py::dict& a,const py::dict& t,std::int64_t n,double h,double g){try{return run(s,e,a,t,n,h,g);}catch(...){return refuse("pair_malformed",n);}}
} // namespace
PYBIND11_MODULE(native_tri_planar_face_pair_bl_template,module){
    module.doc()="Private C++23 authority-bound Native Tri planar face-pair BL template";
    module.def("write_native_tri_planar_face_pair_bl",&guarded,py::arg("source_certificate"),py::arg("edge_ledger"),py::arg("edge_anchor"),py::arg("template_anchor"),py::arg("requested_layers"),py::arg("first_height"),py::arg("growth_ratio"));
}
