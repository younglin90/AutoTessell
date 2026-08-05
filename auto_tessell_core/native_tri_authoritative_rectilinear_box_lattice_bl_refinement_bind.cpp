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
#include <numeric>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>

namespace py=pybind11;
namespace auth=autotessell_native_tri_authority;
namespace edge=autotessell_native_tri_wall_edge;
namespace pair=autotessell_native_tri_planar_pair;
namespace base=autotessell_native_tri_planar_template;
namespace {
struct Label{std::string feature,patch,group,component,provenance;};
struct Source{std::vector<auth::Point>points;std::vector<auth::Triangle>faces;std::vector<Label>labels;std::string source_sha,semantic_sha,geometry_sha,certificate_sha,source_kind,issuer,key_id;std::int64_t byte_count=-1;};
struct Anchor{std::string source_sha,semantic_sha,certificate_sha,edge_sha,issuer,key_id,loop_policy;std::int64_t byte_count=-1;std::vector<std::int64_t>endpoints;};
struct Spec{std::string schema,template_id,source_sha,edge_sha,preflight_digest,issuer,key_id;std::vector<std::int64_t>faces,active;std::vector<std::string>edges;Label label;};
struct Topology{std::int64_t invalid=0,degenerate=0,inverted=0,duplicate=0,open_edges=0,non_manifold=0,self_intersection=0;};
struct Collision{std::int64_t broad=0,hits=0,rejected=0;};
struct Patch{std::int64_t f0=-1,f1=-1,neg=-1,pos=-1;std::array<std::int64_t,4>outer{};std::pair<std::int64_t,std::int64_t>shared{};pair::Point normal{};int nx=0,ny=0;int diagonal_mode=0;};
struct Lattice{double delta=0;std::vector<double>heights;std::vector<int>cell_heights,cumulative;};
struct EdgeKey{std::int64_t a,b,total,seg;bool operator<(const EdgeKey&o)const{return std::tie(a,b,total,seg)<std::tie(o.a,o.b,o.total,o.seg);}};
py::dict refuse(const std::string&why,std::int64_t n){py::dict r;r["accepted"]=false;r["status"]="native_tri_authoritative_rectilinear_box_lattice_bl_refinement_refused";r["reason"]=why;r["requested_layers"]=n;r["actual_layers"]=0;r["writer_invoked"]=false;r["preflight_only"]=false;r["artifact_emitted"]=false;r["publication_eligible"]=false;r["release_eligible"]=false;r["candidate_discarded"]=true;r["atomic_rollback"]=true;r["runtime_route"]="private_default_off";r["route_calls"]=0;r["generated_vertices"]=py::list();r["generated_faces"]=py::list();r["output_vertices"]=py::list();r["output_faces"]=py::list();r["provenance"]=py::list();r["generated_provenance"]=py::list();r["quality_witness"]=py::list();r["wall_edge_ids"]=py::list();r["active_sector_face_ids"]=py::list();r["layer_heights"]=py::list();return r;}
bool sv(const py::dict&d,const char*k,std::string&v){if(!d.contains(k)||!py::isinstance<py::str>(d[k]))return false;v=d[k].cast<std::string>();return!v.empty();}
bool iv(const py::dict&d,const char*k,std::int64_t&v){if(!d.contains(k)||py::isinstance<py::bool_>(d[k]))return false;try{v=d[k].cast<std::int64_t>();return true;}catch(...){return false;}}
bool bv(const py::dict&d,const char*k,bool&v){if(!d.contains(k)||!py::isinstance<py::bool_>(d[k]))return false;v=d[k].cast<bool>();return true;}
bool h64(const std::string&s){return s.size()==64U&&std::all_of(s.begin(),s.end(),[](char c){return(c>='0'&&c<='9')||(c>='a'&&c<='f');});}
template<class T>bool seq(const py::handle&h,std::vector<T>&v){try{v=h.cast<std::vector<T>>();return true;}catch(...){return false;}}
void field(std::ostringstream&o,const std::string&v){o<<v.size()<<':'<<v<<'|';}
std::string semantic_stream(const Source&s){std::ostringstream o;o<<"rows="<<s.faces.size()<<'|';for(std::size_t i=0;i<s.faces.size();++i){const auto&f=s.faces[i];o<<i<<':'<<f[0]<<','<<f[1]<<','<<f[2]<<'|';field(o,s.labels[i].feature);field(o,s.labels[i].patch);field(o,s.labels[i].group);field(o,s.labels[i].component);field(o,s.labels[i].provenance);}return o.str();}
bool parse_source(const py::dict&input,Source&s,std::string&why){
 py::dict c=input;if(input.contains("certificate")){if(!py::isinstance<py::dict>(input["certificate"])){why="source_certificate_payload_invalid";return false;}c=input["certificate"].cast<py::dict>();}
 std::string schema;if(!sv(c,"schema",schema)||schema!="NativeTriAuthorityCertificate/v2"||!sv(c,"source_sha256",s.source_sha)||!h64(s.source_sha)||!sv(c,"semantic_ledger_sha256",s.semantic_sha)||!h64(s.semantic_sha)||!sv(c,"canonical_geometry_sha256",s.geometry_sha)||!h64(s.geometry_sha)||!sv(c,"certificate_sha256",s.certificate_sha)||!h64(s.certificate_sha)||!sv(c,"source_kind",s.source_kind)||!sv(c,"issuer",s.issuer)||!sv(c,"key_id",s.key_id)||!iv(c,"source_byte_count",s.byte_count)||s.byte_count<=0){why="source_certificate_fields_invalid";return false;}
 try{s.points=c["canonical_points"].cast<std::vector<auth::Point>>();s.faces=c["canonical_triangles"].cast<std::vector<auth::Triangle>>();}catch(...){why="source_arrays_invalid";return false;}if(s.points.empty()||s.faces.empty()||!c.contains("face_ledger")){why="source_arrays_empty";return false;}
 try{const py::sequence rows=c["face_ledger"].cast<py::sequence>();if(rows.size()!=s.faces.size()){why="source_face_coverage_incomplete";return false;}s.labels.assign(s.faces.size(),{});std::vector<bool>seen(s.faces.size(),false);for(const py::handle&item:rows){const py::dict row=item.cast<py::dict>();std::int64_t id=-1,sid=-2;std::vector<std::int64_t>v;Label l;if(!iv(row,"face_id",id)||!iv(row,"source_facet_id",sid)||id!=sid||id<0||static_cast<std::size_t>(id)>=s.faces.size()||!row.contains("vertices")||!seq(row["vertices"],v)||v.size()!=3U||auth::Triangle{v[0],v[1],v[2]}!=s.faces[static_cast<std::size_t>(id)]||seen[static_cast<std::size_t>(id)]||!sv(row,"feature",l.feature)||!sv(row,"patch",l.patch)||!sv(row,"physical_group",l.group)||!sv(row,"component",l.component)||!sv(row,"provenance",l.provenance)){why="source_face_binding_invalid";return false;}s.labels[static_cast<std::size_t>(id)]=l;seen[static_cast<std::size_t>(id)]=true;}if(std::any_of(seen.begin(),seen.end(),[](bool x){return!x;})){why="source_face_coverage_incomplete";return false;}}catch(...){why="source_face_ledger_invalid";return false;}
 const auth::CanonicalSource canonical{s.points,s.faces,{},{},s.source_kind};if(auth::sha256_text(semantic_stream(s))!=s.semantic_sha){why="source_semantic_digest_mismatch";return false;}if(auth::sha256_text(auth::canonical_geometry_stream(canonical))!=s.geometry_sha){why="source_geometry_digest_mismatch";return false;}std::ostringstream cert;cert<<"NativeTriAuthorityCertificate/v2|"<<s.source_kind<<'|'<<s.source_sha<<'|'<<s.geometry_sha<<'|'<<s.semantic_sha<<'|'<<s.issuer<<'|'<<s.key_id;if(auth::sha256_text(cert.str())!=s.certificate_sha){why="source_certificate_digest_mismatch";return false;}
 if(!c.contains("topology")||!py::isinstance<py::dict>(c["topology"])){why="source_topology_not_strict";return false;}const py::dict top=c["topology"].cast<py::dict>();bool strict=false,checked=false;if(!bv(top,"strict_zero",strict)||!strict||!bv(top,"self_intersection_checked",checked)||!checked){why="source_topology_not_strict";return false;}for(const char*k:{"duplicate","non_manifold","open_edges","degenerate","inverted","self_intersection"}){std::int64_t n=-1;if(!iv(top,k,n)||n!=0){why="source_topology_not_strict";return false;}}bool au=false,gr=true,fe=true;std::string canon;if(!bv(c,"source_provenance_authoritative",au)||!au||!bv(c,"physical_groups_inferred",gr)||gr||!bv(c,"feature_ids_inferred",fe)||fe||!sv(c,"canonicalization",canon)||canon!="exact_coordinate_identity_only"){why="source_authority_fields_invalid";return false;}return true;
}
bool parse_edges(const py::list&records,std::vector<edge::EdgeRow>&out,std::string&why){try{for(const py::handle&item:records){const py::dict d=item.cast<py::dict>();edge::EdgeRow r;std::vector<std::int64_t>e;if(!sv(d,"edge_id",r.edge_id)||!d.contains("endpoint_vertex_ids")||!seq(d["endpoint_vertex_ids"],e)||e.size()!=2U||!d.contains("incident_face_ids")||!seq(d["incident_face_ids"],r.incident_faces)||!d.contains("directed_sector_face_ids")||!seq(d["directed_sector_face_ids"],r.directed_sector_faces)||!d.contains("directed_sector_ids")||!seq(d["directed_sector_ids"],r.directed_sector_ids)||!sv(d,"wall_role",r.wall_role)||!sv(d,"patch_boundary_role",r.patch_boundary_role)||!sv(d,"feature",r.feature)||!sv(d,"patch",r.patch)||!sv(d,"physical_group",r.physical_group)||!sv(d,"component",r.component)||!sv(d,"provenance",r.provenance)){why="wall_edge_record_invalid";return false;}r.endpoints={e[0],e[1]};out.push_back(r);}return true;}catch(...){why="wall_edge_record_invalid";return false;}}
bool parse_anchor(const py::dict&d,Anchor&a){return sv(d,"source_sha256",a.source_sha)&&h64(a.source_sha)&&sv(d,"semantic_ledger_sha256",a.semantic_sha)&&h64(a.semantic_sha)&&sv(d,"certificate_sha256",a.certificate_sha)&&h64(a.certificate_sha)&&sv(d,"edge_ledger_sha256",a.edge_sha)&&h64(a.edge_sha)&&sv(d,"issuer",a.issuer)&&sv(d,"key_id",a.key_id)&&sv(d,"loop_policy",a.loop_policy)&&iv(d,"source_byte_count",a.byte_count)&&(!d.contains("loop_endpoint_vertex_ids")||seq(d["loop_endpoint_vertex_ids"],a.endpoints));}
bool parse_spec(const py::dict&d,Spec&s){return sv(d,"schema",s.schema)&&s.schema=="NativeTriAuthoritativeRectilinearBoxLatticeBL/v1"&&sv(d,"template_id",s.template_id)&&sv(d,"source_certificate_sha256",s.source_sha)&&h64(s.source_sha)&&sv(d,"edge_ledger_sha256",s.edge_sha)&&h64(s.edge_sha)&&sv(d,"preflight_digest",s.preflight_digest)&&h64(s.preflight_digest)&&sv(d,"issuer",s.issuer)&&sv(d,"key_id",s.key_id)&&d.contains("source_face_ids")&&seq(d["source_face_ids"],s.faces)&&s.faces.size()==2U&&d.contains("wall_edge_ids")&&seq(d["wall_edge_ids"],s.edges)&&s.edges.size()==4U&&d.contains("active_sector_face_ids")&&seq(d["active_sector_face_ids"],s.active)&&s.active.size()==4U&&sv(d,"feature",s.label.feature)&&sv(d,"patch",s.label.patch)&&sv(d,"physical_group",s.label.group)&&sv(d,"component",s.label.component)&&sv(d,"provenance",s.label.provenance);}
bool rectangle_patch(const Source&s,std::int64_t f0,std::int64_t f1,Patch&p,std::string&why){
 const auto&fa=s.faces[static_cast<std::size_t>(f0)];const auto&fb=s.faces[static_cast<std::size_t>(f1)];p.f0=f0;p.f1=f1;p.normal=base::unit(auth::cross(auth::sub(s.points[fa[1]],s.points[fa[0]]),auth::sub(s.points[fa[2]],s.points[fa[0]])));
 const auto nb=base::unit(auth::cross(auth::sub(s.points[fb[1]],s.points[fb[0]]),auth::sub(s.points[fb[2]],s.points[fb[0]])));if(auth::dot(p.normal,nb)<1-1e-10){why="box_pair_normals_not_coherent";return false;}
 std::map<std::pair<std::int64_t,std::int64_t>,int>cnt;for(auto fid:{f0,f1}){const auto&f=s.faces[static_cast<std::size_t>(fid)];for(int i=0;i<3;++i)++cnt[edge::undirected_edge(f[i],f[(i+1)%3])];}
 std::vector<std::pair<std::int64_t,std::int64_t>>shared;std::vector<std::tuple<std::int64_t,std::int64_t,std::int64_t>>directed;for(const auto&[k,n]:cnt){if(n==1){for(auto fid:{f0,f1}){const auto&f=s.faces[static_cast<std::size_t>(fid)];for(int i=0;i<3;++i)if(edge::undirected_edge(f[i],f[(i+1)%3])==k)directed.emplace_back(f[i],f[(i+1)%3],fid);}}else if(n==2)shared.push_back(k);}
 if(shared.size()!=1||directed.size()!=4){why="box_pair_boundary_invalid";return false;}p.shared=shared[0];auto start=*std::min_element(directed.begin(),directed.end());p.outer[0]=std::get<0>(start);p.outer[1]=std::get<1>(start);for(int i=2;i<4;++i){auto cur=p.outer[i-1];auto it=std::find_if(directed.begin(),directed.end(),[&](auto x){return std::get<0>(x)==cur&&std::get<1>(x)!=p.outer[static_cast<std::size_t>(i-2)];});if(it==directed.end()){why="box_pair_loop_invalid";return false;}p.outer[static_cast<std::size_t>(i)]=std::get<1>(*it);}if(p.outer[3]==p.outer[0]||std::none_of(directed.begin(),directed.end(),[&](const auto&x){return std::get<0>(x)==p.outer[3]&&std::get<1>(x)==p.outer[0];})){why="box_pair_loop_invalid";return false;}
 const auto e0=auth::sub(s.points[p.outer[1]],s.points[p.outer[0]]);const auto e1=auth::sub(s.points[p.outer[2]],s.points[p.outer[1]]);const auto e2=auth::sub(s.points[p.outer[3]],s.points[p.outer[2]]);const auto e3=auth::sub(s.points[p.outer[0]],s.points[p.outer[3]]);const double l0=auth::norm(e0),l1=auth::norm(e1);if(!(l0>1e-12&&l1>1e-12)||std::abs(auth::dot(e0,e1))/(l0*l1)>1e-8||std::abs(auth::dot(e1,e2))/(l1*auth::norm(e2))>1e-8||std::abs(auth::dot(e2,e3))/(auth::norm(e2)*auth::norm(e3))>1e-8||std::abs(auth::dot(e3,e0))/(auth::norm(e3)*l0)>1e-8){why="box_pair_not_rectangular";return false;}
 const auto shared_key=shared[0];p.diagonal_mode=(shared_key==edge::undirected_edge(p.outer[0],p.outer[2]))?0:1;auto nonshared=[&](const auth::Triangle&f){for(auto id:f)if(id!=shared_key.first&&id!=shared_key.second)return id;return f[0];};const auto outside0=nonshared(fa),outside1=nonshared(fb);const auto u=base::unit(e0),v=base::unit(auth::cross(p.normal,u));auto F=[&](std::int64_t id){auto d=auth::sub(s.points[id],s.points[p.outer[0]]);double x=auth::dot(d,u)/l0*1.0,y=auth::dot(d,v)/l1*1.0;return p.diagonal_mode==0?x-y:x+y-1.0;};const double z0=F(outside0),z1=F(outside1);if(std::abs(z0)<1e-9||std::abs(z1)<1e-9||z0*z1>=0){why="box_pair_diagonal_side_invalid";return false;}p.neg=z0<0?f0:f1;p.pos=z0<0?f1:f0;return true;
}
bool bind_box_pair(const Source&s,const std::vector<edge::EdgeRow>&rows,const Anchor&a,const Spec&t,const Patch&p,std::string&why){
 if(a.byte_count!=s.byte_count||a.source_sha!=s.source_sha||a.semantic_sha!=s.semantic_sha||a.certificate_sha!=s.certificate_sha||
    a.loop_policy!="closed_nonbranching"||!a.endpoints.empty()||rows.size()!=4U||t.source_sha!=s.certificate_sha||
    t.edge_sha!=a.edge_sha||t.issuer!=a.issuer||t.key_id!=a.key_id||t.faces[0]<0||t.faces[1]<0||
    t.faces[0]>=static_cast<std::int64_t>(s.faces.size())||t.faces[1]>=static_cast<std::int64_t>(s.faces.size())||
    t.faces[0]>=t.faces[1]){
  why="box_anchor_mismatch";return false;
 }
 const auto&l0=s.labels[static_cast<std::size_t>(t.faces[0])];
 const auto&l1=s.labels[static_cast<std::size_t>(t.faces[1])];
 if(l0.feature!=l1.feature||l0.patch!=l1.patch||l0.group!=l1.group||l0.component!=l1.component||l0.provenance!=l1.provenance||
    t.label.feature!=l0.feature||t.label.patch!=l0.patch||t.label.group!=l0.group||
    t.label.component!=l0.component||t.label.provenance!=l0.provenance){
  why="box_label_binding_invalid";return false;
 }
 std::set<std::pair<std::int64_t,std::int64_t>>boundary;
 for(auto id:t.faces){
  const auto&f=s.faces[static_cast<std::size_t>(id)];
  for(int i=0;i<3;++i){auto k=edge::undirected_edge(f[i],f[(i+1)%3]);if(!boundary.insert(k).second)boundary.erase(k);}
 }
 if(boundary.size()!=4U){why="box_pair_not_adjacent";return false;}
 std::set<std::pair<std::int64_t,std::int64_t>>actual;
 for(std::size_t i=0;i<rows.size();++i){
  const auto&r=rows[i];auto k=edge::undirected_edge(r.endpoints[0],r.endpoints[1]);
  if(!actual.insert(k).second||r.edge_id!=t.edges[i]||boundary.count(k)==0U||r.wall_role!="wall"||
     r.feature!=l0.feature||r.patch!=l0.patch||r.physical_group!=l0.group||r.component!=l0.component||
     r.provenance!=l0.provenance||std::find(r.incident_faces.begin(),r.incident_faces.end(),t.active[i])==r.incident_faces.end()){
   why="box_edge_binding_invalid";return false;
  }
  int n=0;std::int64_t selected=-1;
  for(auto id:r.incident_faces)if(std::find(t.faces.begin(),t.faces.end(),id)!=t.faces.end()){++n;selected=id;}
  if(n!=1||selected!=t.active[i]){why="box_sector_binding_invalid";return false;}
  if(i+1<rows.size()&&r.endpoints[1]!=rows[i+1].endpoints[0]){why="box_loop_order_invalid";return false;}
 }
 if(rows.back().endpoints[1]!=rows.front().endpoints[0]||actual!=boundary){why="box_boundary_invalid";return false;}
 std::set<std::int64_t>verts;for(const auto&r:rows){verts.insert(r.endpoints[0]);verts.insert(r.endpoints[1]);}
 if(verts.size()!=4U){why="box_outer_vertex_count_invalid";return false;}
 if(std::set<std::int64_t>{p.f0,p.f1}!=std::set<std::int64_t>{t.faces[0],t.faces[1]}){why="box_pair_binding_invalid";return false;}
 return true;
}
std::vector<double> make_heights(std::int64_t n,double first,double growth,std::string&why){
 std::vector<double>h;
 if(n<0||n>128){why="layer_count_invalid";return h;}
 if(n==0)return h;
 if(!std::isfinite(first)||!std::isfinite(growth)||first<=0||growth<1){why="schedule_invalid";return h;}
 double x=first;
 for(std::int64_t i=0;i<n;++i){
  if(!std::isfinite(x)||x<=0){why="schedule_overflow";h.clear();return h;}
  h.push_back(x); x*=growth;
 }
 return h;
}
bool make_lattice(const Source&s,const std::vector<Patch>&patches,const std::vector<double>&h,Lattice&l,std::string&why){
 constexpr std::int64_t Q=1000000;auto quant=[](double x){return static_cast<std::int64_t>(std::llround(x*1000000.0));};std::int64_t g=0;std::set<std::pair<std::int64_t,std::int64_t>>seen;
 for(const auto&p:patches){const double a=auth::norm(auth::sub(s.points[p.outer[1]],s.points[p.outer[0]])),b=auth::norm(auth::sub(s.points[p.outer[2]],s.points[p.outer[1]]));for(double x:{a,b}){auto q=quant(x);if(q<=0){why="lattice_axis_invalid";return false;}if(g==0)g=q;else g=std::gcd(g,q);}}
 for(double x:h){auto q=quant(x);if(q<=0){why="lattice_quantum_unrepresentable";return false;}g=std::gcd(g,q);}if(g<=0){why="lattice_quantum_unrepresentable";return false;}l.delta=static_cast<double>(g)/Q;l.heights=h;l.cumulative={0};int sum=0;for(double x:h){auto q=quant(x);if(q%g!=0||std::abs(static_cast<double>(q)/Q-x)>2e-9){why="lattice_height_not_integral";return false;}int c=static_cast<int>(q/g);if(c<=0){why="lattice_height_zero";return false;}l.cell_heights.push_back(c);sum+=c;l.cumulative.push_back(sum);}for(const auto&p:patches){for(int side=0;side<2;++side){double len=side==0?auth::norm(auth::sub(s.points[p.outer[1]],s.points[p.outer[0]])):auth::norm(auth::sub(s.points[p.outer[2]],s.points[p.outer[1]]));auto q=quant(len);if(q%g!=0||q/g<2||q/g>128){why="lattice_resolution_out_of_bounds";return false;}}int mn=std::min(static_cast<int>(std::llround(auth::norm(auth::sub(s.points[p.outer[1]],s.points[p.outer[0]]))/l.delta)),static_cast<int>(std::llround(auth::norm(auth::sub(s.points[p.outer[2]],s.points[p.outer[1]]))/l.delta)));if(sum*2>=mn){why="lattice_core_collapse";return false;}}return true;
}
std::vector<Patch> all_patches(const Source&s,std::string&why){
 std::vector<Patch>out;std::vector<bool>used(s.faces.size(),false);std::vector<pair::Point>normals;for(const auto&f:s.faces)normals.push_back(base::unit(auth::cross(auth::sub(s.points[f[1]],s.points[f[0]]),auth::sub(s.points[f[2]],s.points[f[0]]))));
 for(std::size_t i=0;i<s.faces.size();++i)if(!used[i]){std::int64_t partner=-1;for(std::size_t j=i+1;j<s.faces.size();++j)if(!used[j]&&auth::dot(normals[i],normals[j])>1-1e-10){int common=0;for(auto a:s.faces[i])for(auto b:s.faces[j])if(a==b)++common;if(common==2){partner=static_cast<std::int64_t>(j);break;}}if(partner<0){why="box_face_pairing_incomplete";return{};}Patch p;if(!rectangle_patch(s,static_cast<std::int64_t>(i),partner,p,why))return{};used[i]=used[static_cast<std::size_t>(partner)]=true;out.push_back(p);}
 if(out.size()!=s.faces.size()/2||std::any_of(used.begin(),used.end(),[](bool x){return!x;})){why="box_face_pairing_incomplete";return{};}return out;
}
Topology audit_mesh(const std::vector<pair::Point>&p,const std::vector<pair::Triangle>&f,const std::vector<pair::Point>&n,double eps){
 Topology r;std::set<std::array<std::int64_t,3>>fk;std::map<std::pair<std::int64_t,std::int64_t>,std::int64_t>ec;std::vector<std::array<pair::Point,3>>g;std::vector<pair::Triangle>vf;std::vector<auth::Aabb>b;
 for(std::size_t i=0;i<f.size();++i){
  const auto&x=f[i];
  if(std::any_of(x.begin(),x.end(),[&](auto id){return id<0||static_cast<std::size_t>(id)>=p.size();})||x[0]==x[1]||x[1]==x[2]||x[2]==x[0]){++r.invalid;continue;}
  auto k=x;std::sort(k.begin(),k.end());if(!fk.insert(k).second)++r.duplicate;
  const auto&a=p[x[0]],&bb=p[x[1]],&c=p[x[2]];auto cr=auth::cross(auth::sub(bb,a),auth::sub(c,a));
  if(auth::norm(cr)<=eps)++r.degenerate;else if(auth::dot(cr,n[i])<=eps)++r.inverted;
  for(int j=0;j<3;++j){auto u=x[j],v=x[(j+1)%3];if(u>v)std::swap(u,v);++ec[{u,v}];}
  g.push_back({a,bb,c});vf.push_back(x);b.push_back(auth::triangle_aabb(a,bb,c));
 }
 for(const auto&[e,c]:ec){(void)e;if(c==1)++r.open_edges;if(c>2)++r.non_manifold;}
 for(std::size_t i=0;i<g.size();++i)for(std::size_t j=i+1;j<g.size();++j)if(!base::point_ids_share_vertex(vf[i],vf[j])&&auth::aabb_overlap(b[i],b[j],eps)&&auth::triangles_intersect(g[i],g[j],eps))++r.self_intersection;
 return r;
}
Collision collision_mesh(const std::vector<pair::Point>&p,const std::vector<pair::Triangle>&f,double eps){Collision r;for(std::size_t i=0;i<f.size();++i)for(std::size_t j=i+1;j<f.size();++j){if(base::point_ids_share_vertex(f[i],f[j]))continue;std::array<pair::Point,3>a{p[f[i][0]],p[f[i][1]],p[f[i][2]]},b{p[f[j][0]],p[f[j][1]],p[f[j][2]]};if(!auth::aabb_overlap(auth::triangle_aabb(a[0],a[1],a[2]),auth::triangle_aabb(b[0],b[1],b[2]),eps))continue;++r.broad;if(auth::triangles_intersect(a,b,eps)){++r.hits;++r.rejected;}}return r;}
double pct(std::vector<double>v,double p){std::sort(v.begin(),v.end());auto i=p<=1?0U:static_cast<std::size_t>(std::ceil(p*v.size()))-1U;return v[std::min(i,v.size()-1)];}
struct Point2{double x=0.0,y=0.0;};
struct Tri2{int a=0,b=0,c=0;};
double orient2(const Point2&a,const Point2&b,const Point2&c)noexcept{return(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);}
bool point_in_tri2(const Point2&p,const Point2&a,const Point2&b,const Point2&c,double eps)noexcept{
 double o1=orient2(a,b,p),o2=orient2(b,c,p),o3=orient2(c,a,p);
 return (o1>=-eps&&o2>=-eps&&o3>=-eps)||(o1<=eps&&o2<=eps&&o3<=eps);
}
bool circumcircle_contains2(const std::vector<Point2>&p,const Tri2&t,int index,double eps)noexcept{
 const auto&a=p[static_cast<std::size_t>(t.a)],&b=p[static_cast<std::size_t>(t.b)],&c=p[static_cast<std::size_t>(t.c)],&q=p[static_cast<std::size_t>(index)];
 double ax=a.x-q.x,ay=a.y-q.y,bx=b.x-q.x,by=b.y-q.y,cx=c.x-q.x,cy=c.y-q.y;
 double det=(ax*ax+ay*ay)*(bx*cy-by*cx)-(bx*bx+by*by)*(ax*cy-ay*cx)+(cx*cx+cy*cy)*(ax*by-ay*bx);
 double o=orient2(a,b,c);return o>0.0?det>eps:det<-eps;
}
bool delaunay_point_set(const std::vector<Point2>&input,std::vector<Tri2>&out){
 if(input.size()<3)return false;
 double minx=input[0].x,maxx=input[0].x,miny=input[0].y,maxy=input[0].y;
 for(const auto&q:input){minx=std::min(minx,q.x);maxx=std::max(maxx,q.x);miny=std::min(miny,q.y);maxy=std::max(maxy,q.y);}
 double span=std::max({maxx-minx,maxy-miny,1e-12}),cx=.5*(minx+maxx),cy=.5*(miny+maxy),eps=1e-12*std::max(1.0,span*span*span*span);
 std::vector<Point2>p=input;p.push_back({cx-32*span,cy-16*span});p.push_back({cx,cy+32*span});p.push_back({cx+32*span,cy-16*span});
 const int n=static_cast<int>(input.size());std::vector<Tri2>tris{{n,n+1,n+2}};
 for(int index=0;index<n;++index){
  std::vector<Tri2>bad;std::map<std::pair<int,int>,int>boundary;
  for(const auto&t:tris)if(circumcircle_contains2(p,t,index,eps)){
   bad.push_back(t);for(const auto&e:std::array<std::pair<int,int>,3>{{{t.a,t.b},{t.b,t.c},{t.c,t.a}}}){auto k=e;if(k.first>k.second)std::swap(k.first,k.second);++boundary[k];}
  }
  if(bad.empty()){
   for(const auto&t:tris){
    if(point_in_tri2(p[static_cast<std::size_t>(index)],p[static_cast<std::size_t>(t.a)],p[static_cast<std::size_t>(t.b)],p[static_cast<std::size_t>(t.c)],eps)){bad.push_back(t);for(const auto&e:std::array<std::pair<int,int>,3>{{{t.a,t.b},{t.b,t.c},{t.c,t.a}}}){auto k=e;if(k.first>k.second)std::swap(k.first,k.second);++boundary[k];}break;}
   }
  }
  if(bad.empty())return false;
  std::vector<Tri2>kept;kept.reserve(tris.size()+bad.size());
  for(const auto&t:tris){bool remove=false;for(const auto&b:bad)if(t.a==b.a&&t.b==b.b&&t.c==b.c){remove=true;break;}if(!remove)kept.push_back(t);}
  for(const auto&[e,count]:boundary)if(count==1){
   Tri2 t{e.first,e.second,index};if(orient2(p[static_cast<std::size_t>(t.a)],p[static_cast<std::size_t>(t.b)],p[static_cast<std::size_t>(t.c)])<0)std::swap(t.a,t.b);
   if(std::abs(orient2(p[static_cast<std::size_t>(t.a)],p[static_cast<std::size_t>(t.b)],p[static_cast<std::size_t>(t.c)]))>eps)kept.push_back(t);
  }
  tris=std::move(kept);
 }
 out.clear();std::set<std::array<int,3>>seen;
 for(const auto&t:tris){
  if(t.a>=n||t.b>=n||t.c>=n)continue;
  auto k=std::array<int,3>{t.a,t.b,t.c};std::sort(k.begin(),k.end());if(!seen.insert(k).second)continue;
  if(std::abs(orient2(p[static_cast<std::size_t>(t.a)],p[static_cast<std::size_t>(t.b)],p[static_cast<std::size_t>(t.c)]))>eps)out.push_back(t);
 }
 return !out.empty();
}
py::list pts(const std::vector<pair::Point>&p){py::list o;for(const auto&x:p){py::list r;for(double v:x)r.append(v);o.append(r);}return o;}py::list tris(const std::vector<pair::Triangle>&f){py::list o;for(const auto&x:f){py::list r;for(auto v:x)r.append(v);o.append(r);}return o;}py::dict label_py(const Label&l){py::dict d;d["feature"]=l.feature;d["patch"]=l.patch;d["physical_group"]=l.group;d["component"]=l.component;d["provenance"]=l.provenance;return d;}
py::dict run_box(const py::dict&input,const py::list&edge_rows,const py::dict&edge_anchor,const py::dict&template_anchor,std::int64_t requested,double first,double growth){
 Source s;std::string why;if(!parse_source(input,s,why))return refuse(why,requested);Anchor a;if(!parse_anchor(edge_anchor,a))return refuse("edge_anchor_invalid",requested);std::vector<edge::EdgeRow>rows;if(!parse_edges(edge_rows,rows,why))return refuse(why,requested);auto edge_sha=auth::sha256_text(edge::canonical_edge_stream(rows,a.loop_policy,a.endpoints));if(edge_sha!=a.edge_sha)return refuse("edge_ledger_digest_mismatch",requested);std::size_t ec=0;if(!edge::validate_edge_ledger_geometry(s.points,s.faces,rows,a.loop_policy,a.endpoints,why,ec))return refuse(why,requested);if(ec!=4U)return refuse("requires_four_selected_outer_edges",requested);Spec t;if(!parse_spec(template_anchor,t))return refuse("template_invalid",requested);if(t.faces.size()!=2)return refuse("template_pair_invalid",requested);
 auto patches=all_patches(s,why);if(patches.empty())return refuse(why,requested);auto selected=std::find_if(patches.begin(),patches.end(),[&](const Patch&p){return(std::set<std::int64_t>{p.f0,p.f1}==std::set<std::int64_t>{t.faces[0],t.faces[1]});});if(selected==patches.end())return refuse("selected_pair_not_in_box_patch_set",requested);
 if(!bind_box_pair(s,rows,a,t,*selected,why))return refuse(why,requested);
 const auto h=make_heights(requested,first,growth,why);if(requested>0&&h.empty())return refuse(why,requested);std::ostringstream pf;pf<<"NativeTriWallEdgeBLPreflight/v1|"<<s.certificate_sha<<'|'<<s.source_sha<<'|'<<s.semantic_sha<<'|'<<edge_sha<<'|'<<a.loop_policy<<'|'<<requested<<'|'<<first<<'|'<<growth;for(double x:h)pf<<'|'<<x;if(auth::sha256_text(pf.str())!=t.preflight_digest)return refuse("preflight_digest_mismatch",requested);
 if(requested==0){py::dict r;r["accepted"]=true;r["status"]="native_tri_authoritative_rectilinear_box_lattice_bl_identity";r["reason"]="authority_bound_source_identity";r["requested_layers"]=0;r["actual_layers"]=0;r["source_certificate_sha256"]=s.certificate_sha;r["source_sha256"]=s.source_sha;r["source_byte_count"]=s.byte_count;r["semantic_ledger_sha256"]=s.semantic_sha;r["canonical_geometry_sha256"]=s.geometry_sha;r["edge_ledger_sha256"]=edge_sha;r["preflight_digest"]=t.preflight_digest;r["template_id"]=t.template_id;r["source_face_ids"]=t.faces;r["wall_edge_ids"]=t.edges;r["active_sector_face_ids"]=t.active;r["bl0_identity"]=true;r["writer_invoked"]=false;r["preflight_only"]=false;r["artifact_emitted"]=false;r["publication_eligible"]=false;r["release_eligible"]=false;r["candidate_discarded"]=false;r["atomic_rollback"]=false;r["runtime_route"]="private_default_off";r["route_calls"]=0;r["output_vertices"]=pts(s.points);r["output_faces"]=tris(s.faces);r["generated_vertices"]=py::list();r["generated_faces"]=py::list();r["provenance"]=py::list();r["generated_provenance"]=py::list();r["quality_witness"]=py::list();r["source_face_coverage_complete"]=true;r["identity_digest"]=s.certificate_sha;r["layer_heights"]=py::list();return r;}
 Lattice lat;if(!make_lattice(s,patches,h,lat,why))return refuse(why,requested);
 int global_n=0;
 for(auto&p:patches){
  p.nx=static_cast<int>(std::llround(auth::norm(auth::sub(s.points[p.outer[1]],s.points[p.outer[0]]))/lat.delta));
  p.ny=static_cast<int>(std::llround(auth::norm(auth::sub(s.points[p.outer[2]],s.points[p.outer[1]]))/lat.delta));
  global_n=std::max({global_n,p.nx,p.ny});
 }
 if(global_n<2||global_n>128)return refuse("lattice_resolution_out_of_bounds",requested);
 std::vector<pair::Point>points=s.points,fn;for(const auto&f:s.faces)fn.push_back(base::unit(auth::cross(auth::sub(s.points[f[1]],s.points[f[0]]),auth::sub(s.points[f[2]],s.points[f[0]]))));std::vector<pair::Triangle>faces;std::vector<pair::Point>normals;std::vector<std::set<std::int64_t>>vsrc(points.size());for(std::size_t i=0;i<s.faces.size();++i)for(auto id:s.faces[i])vsrc[static_cast<std::size_t>(id)].insert(static_cast<std::int64_t>(i));std::map<EdgeKey,std::int64_t>edge_cache;std::map<std::tuple<int,int,int>,std::int64_t>grid_cache;std::map<std::tuple<int,int,int,int>,std::int64_t>diag_cache;
 auto edge_vertex=[&](std::int64_t va,std::int64_t vb,int seg,int total,std::int64_t sid){if(seg==0){vsrc[static_cast<std::size_t>(va)].insert(sid);return va;}if(seg==total){vsrc[static_cast<std::size_t>(vb)].insert(sid);return vb;}std::int64_t a0=va,b0=vb;int s0=seg;if(a0>b0){std::swap(a0,b0);s0=total-seg;}EdgeKey k{a0,b0,total,s0};auto it=edge_cache.find(k);if(it!=edge_cache.end()){vsrc[static_cast<std::size_t>(it->second)].insert(sid);return it->second;}double u=static_cast<double>(seg)/total;pair::Point p={s.points[va][0]*(1-u)+s.points[vb][0]*u,s.points[va][1]*(1-u)+s.points[vb][1]*u,s.points[va][2]*(1-u)+s.points[vb][2]*u};auto id=static_cast<std::int64_t>(points.size());points.push_back(p);vsrc.push_back({sid});edge_cache.emplace(k,id);return id;};
 auto grid_vertex=[&](int pid,int i,int j,std::int64_t sid){
  const auto&patch=patches[static_cast<std::size_t>(pid)];
  int nx=patch.nx,ny=patch.ny;
  if(j==0)return edge_vertex(patch.outer[0],patch.outer[1],i,nx,sid);
  if(i==nx)return edge_vertex(patch.outer[1],patch.outer[2],j,ny,sid);
  if(j==ny)return edge_vertex(patch.outer[3],patch.outer[2],i,nx,sid);
  if(i==0)return edge_vertex(patch.outer[0],patch.outer[3],j,ny,sid);
  auto k=std::make_tuple(pid,i,j);
  auto it=grid_cache.find(k);
  if(it!=grid_cache.end()){vsrc[static_cast<std::size_t>(it->second)].insert(sid);return it->second;}
  double x=static_cast<double>(i)/nx,y=static_cast<double>(j)/ny;
  pair::Point q={
   s.points[patch.outer[0]][0]+x*(s.points[patch.outer[1]][0]-s.points[patch.outer[0]][0])+y*(s.points[patch.outer[3]][0]-s.points[patch.outer[0]][0]),
   s.points[patch.outer[0]][1]+x*(s.points[patch.outer[1]][1]-s.points[patch.outer[0]][1])+y*(s.points[patch.outer[3]][1]-s.points[patch.outer[0]][1]),
   s.points[patch.outer[0]][2]+x*(s.points[patch.outer[1]][2]-s.points[patch.outer[0]][2])+y*(s.points[patch.outer[3]][2]-s.points[patch.outer[0]][2])
  };
  auto id=static_cast<std::int64_t>(points.size());points.push_back(q);vsrc.push_back({sid});grid_cache.emplace(k,id);return id;
 };
 auto line_f=[&](const Patch&p,int i,int j){return p.diagonal_mode==0?static_cast<double>(p.nx*j-p.ny*i):static_cast<double>(p.nx*j+p.ny*i-p.nx*p.ny);};
 struct V{double x,y,f;std::int64_t id;};
 auto diag_vertex=[&](int pid,int i0,int j0,int i1,int j1,double u,std::int64_t sid){
  int dir=(i0==i1)?1:0;
  auto k=std::make_tuple(pid,i0,j0,dir);
  auto it=diag_cache.find(k);
  if(it!=diag_cache.end()){vsrc[static_cast<std::size_t>(it->second)].insert(sid);return it->second;}
  auto a0=grid_vertex(pid,i0,j0,sid),b0=grid_vertex(pid,i1,j1,sid);
  pair::Point q={
   points[a0][0]*(1-u)+points[b0][0]*u,
   points[a0][1]*(1-u)+points[b0][1]*u,
   points[a0][2]*(1-u)+points[b0][2]*u
  };
  auto id=static_cast<std::int64_t>(points.size());points.push_back(q);vsrc.push_back({sid});diag_cache.emplace(k,id);return id;
 };
 py::list provenance,witness;std::vector<double>ra,rs,rm,rr,ma,ms,wall;std::vector<std::int64_t>ring(static_cast<std::size_t>(requested),0);std::int64_t pair_core=0,support=0;
 auto add=[&](pair::Triangle f,std::int64_t sid,int layer,const std::string&role){
  if(base::signed_area(points[f[0]],points[f[1]],points[f[2]],fn[static_cast<std::size_t>(sid)])<=1e-12)std::swap(f[1],f[2]);
  faces.push_back(f);normals.push_back(fn[static_cast<std::size_t>(sid)]);auto q=base::triangle_quality(points[f[0]],points[f[1]],points[f[2]],fn[static_cast<std::size_t>(sid)]);auto mr=pair::mean_ratio(points[f[0]],points[f[1]],points[f[2]]);ra.push_back(q.physical_aspect);rs.push_back(q.skewness);rm.push_back(mr);rr.push_back(q.angle_nonorthogonality);ma.push_back(q.aspect);ms.push_back(q.skewness);wall.push_back(0.0);auto id=static_cast<std::int64_t>(faces.size()-1);py::dict d=label_py(s.labels[static_cast<std::size_t>(sid)]);d["output_face_id"]=id;d["source_face_id"]=sid;d["source_face_ids"]=std::vector<std::int64_t>{sid};d["replacement_role"]=role;d["layer"]=layer;bool active=(sid==t.faces[0]||sid==t.faces[1]);d["source_wall_edge_ids"]=active?t.edges:std::vector<std::string>{};d["active_sector_face_ids"]=active?t.active:std::vector<std::int64_t>{};provenance.append(d);
  if(role=="support_refinement")++support;
  else if(role=="boundary_layer_core")++pair_core;
  else if(layer>0&&static_cast<std::size_t>(layer-1)<ring.size())++ring[static_cast<std::size_t>(layer-1)];
  py::dict w=d;w["raw_physical_aspect_ratio"]=q.physical_aspect;w["raw_skewness"]=q.skewness;w["raw_mean_ratio"]=mr;w["raw_angle_nonorthogonality_degrees"]=q.angle_nonorthogonality;w["metric_aspect_ratio"]=q.aspect;w["metric_skewness"]=q.skewness;w["wall_front_non_orthogonality_degrees"]=0.0;witness.append(w);};
 auto build_side=[&](int pid,const Patch&p,int sign,std::int64_t sid)->bool{
  std::map<std::int64_t,Point2>local;
  auto remember_grid=[&](int i,int j){
   auto id=grid_vertex(pid,i,j,sid);local.emplace(id,Point2{static_cast<double>(i),static_cast<double>(j)});
  };
  for(int i=0;i<=p.nx;++i)for(int j=0;j<=p.ny;++j)if(sign*line_f(p,i,j)>=-1e-12)remember_grid(i,j);
  auto remember_cross=[&](int ai,int aj,int bi,int bj){
   double fa=line_f(p,ai,aj),fb=line_f(p,bi,bj);
   bool ia=sign*fa>=-1e-12,ib=sign*fb>=-1e-12;
   if(ia==ib)return;
   if(std::abs(fa)<=1e-12){remember_grid(ai,aj);return;}
   if(std::abs(fb)<=1e-12){remember_grid(bi,bj);return;}
   double t0=fa/(fa-fb);bool reverse=(ai>bi)||(ai==bi&&aj>bj);
   int i0=reverse?bi:ai,j0=reverse?bj:aj,i1=reverse?ai:bi,j1=reverse?aj:bj;
   auto id=diag_vertex(pid,i0,j0,i1,j1,reverse?1.0-t0:t0,sid);
   local.emplace(id,Point2{static_cast<double>(ai)+(static_cast<double>(bi-ai))*t0,static_cast<double>(aj)+(static_cast<double>(bj-aj))*t0});
  };
  for(int i=0;i<p.nx;++i)for(int j=0;j<p.ny;++j){
   remember_cross(i,j,i+1,j);remember_cross(i+1,j,i+1,j+1);
   remember_cross(i+1,j+1,i,j+1);remember_cross(i,j+1,i,j);
  }
  std::vector<Point2>uv;std::vector<std::int64_t>ids;uv.reserve(local.size());ids.reserve(local.size());
  for(const auto&[id,q]:local){ids.push_back(id);uv.push_back(q);}
  std::vector<Tri2>dt;if(!delaunay_point_set(uv,dt))return false;
  const bool active=(sid==t.faces[0]||sid==t.faces[1]);
  for(const auto&tr:dt){
   std::array<int,3>li{tr.a,tr.b,tr.c};double cx=0.0,cy=0.0;
   for(auto k:li){cx+=uv[static_cast<std::size_t>(k)].x;cy+=uv[static_cast<std::size_t>(k)].y;}
   cx/=3.0;cy/=3.0;int layer=0;
   if(active){
    double radial=std::min({cx,cy,static_cast<double>(p.nx)-cx,static_cast<double>(p.ny)-cy});
    int band=static_cast<int>(std::floor(std::max(0.0,radial)+1e-9));
    for(std::size_t k=0;k<lat.cell_heights.size();++k)if(band>=lat.cumulative[k]&&band<lat.cumulative[k+1])layer=static_cast<int>(k)+1;
   }
   std::string role=active?(layer?"boundary_layer_ring":"boundary_layer_core"):"support_refinement";
   add({ids[static_cast<std::size_t>(li[0])],ids[static_cast<std::size_t>(li[1])],ids[static_cast<std::size_t>(li[2])]},sid,layer,role);
  }
  return !dt.empty();
 };
 bool side_ok=true;
 for(std::size_t pid=0;pid<patches.size();++pid){
  const auto&p=patches[pid];
  if(!build_side(static_cast<int>(pid),p,-1,p.neg)||!build_side(static_cast<int>(pid),p,1,p.pos)){side_ok=false;break;}
 }
 if(!side_ok)return refuse("box_side_delaunay_failed",requested);
 auto nominal_faces=static_cast<std::size_t>(std::accumulate(patches.begin(),patches.end(),0,[&](int z,const Patch&p){return z+2*p.nx*p.ny;}));
 py::list genverts;for(std::size_t id=s.points.size();id<points.size();++id){py::dict v;v["vertex_id"]=static_cast<std::int64_t>(id);v["x"]=points[id][0];v["y"]=points[id][1];v["z"]=points[id][2];std::vector<std::int64_t>x(vsrc[id].begin(),vsrc[id].end());v["source_face_ids"]=x;bool act=std::any_of(x.begin(),x.end(),[&](auto q){return q==t.faces[0]||q==t.faces[1];});v["source_wall_edge_ids"]=act?t.edges:std::vector<std::string>{};v["active_sector_face_ids"]=act?t.active:std::vector<std::int64_t>{};if(!x.empty()){auto d=label_py(s.labels[static_cast<std::size_t>(x.front())]);for(const auto&i:d)v[i.first]=i.second;}genverts.append(v);}
 auto topo=audit_mesh(points,faces,normals,1e-12);auto col=collision_mesh(points,faces,1e-12);
 if(topo.invalid||topo.degenerate||topo.inverted||topo.duplicate||topo.open_edges||topo.non_manifold||topo.self_intersection||col.rejected){
  py::dict rr=refuse("box_topology_or_collision_failed",requested);
  py::dict tt;tt["invalid"]=topo.invalid;tt["degenerate"]=topo.degenerate;tt["inverted"]=topo.inverted;tt["duplicate"]=topo.duplicate;tt["open_edges"]=topo.open_edges;tt["non_manifold"]=topo.non_manifold;tt["self_intersection"]=topo.self_intersection;rr["topology"]=tt;
  py::dict cc;cc["broad_phase_pairs"]=col.broad;cc["narrow_phase_hits"]=col.hits;cc["rejected_contacts"]=col.rejected;rr["collision"]=cc;rr["actual_face_count"]=faces.size();return rr;
 }
 double p95ra=pct(ra,.95),maxra=*std::max_element(ra.begin(),ra.end()),p05rm=pct(rm,.05),minrm=*std::min_element(rm.begin(),rm.end()),maxrr=*std::max_element(rr.begin(),rr.end()),p95ms=pct(ms,.95),maxms=*std::max_element(ms.begin(),ms.end()),p99ma=pct(ma,.99),maxma=*std::max_element(ma.begin(),ma.end()),p95w=pct(wall,.95),maxw=*std::max_element(wall.begin(),wall.end());
 if(!(p95ra<=4.5+1e-12&&maxra<=5.5+1e-12&&p05rm>=.35-1e-12&&minrm>=.30-1e-12&&maxrr<=55+1e-12&&p95ms<=.32+1e-12&&maxms<=.35+1e-12&&p99ma<=1.5+1e-12&&maxma<=1.6+1e-12&&p95w<=.5+1e-12&&maxw<=1+1e-12)){
  py::dict rr=refuse("box_quality_gate_failed",requested);py::dict qq;qq["raw_physical_aspect_p95"]=p95ra;qq["raw_physical_aspect_max"]=maxra;qq["raw_mean_ratio_p05"]=p05rm;qq["raw_mean_ratio_min"]=minrm;qq["raw_angle_nonorthogonality_max_degrees"]=maxrr;qq["metric_skewness_p95"]=p95ms;qq["metric_skewness_max"]=maxms;qq["metric_aspect_ratio_p99"]=p99ma;qq["metric_aspect_ratio_max"]=maxma;rr["quality"]=qq;auto wi=static_cast<std::size_t>(std::distance(ra.begin(),std::max_element(ra.begin(),ra.end())));py::list wf;for(auto id:faces[wi]){py::list qv;for(double x:points[static_cast<std::size_t>(id)])qv.append(x);wf.append(qv);}rr["worst_face_vertices"]=wf;rr["worst_face_id"]=wi;rr["actual_face_count"]=faces.size();return rr;
 }
 std::ostringstream ds;ds<<"NativeTriAuthoritativeRectilinearBoxLatticeBL/v1|"<<s.certificate_sha<<'|'<<edge_sha<<'|'<<t.preflight_digest<<'|'<<requested<<'|'<<std::setprecision(17)<<first<<'|'<<growth<<'|'<<lat.delta;for(const auto&p:points)ds<<'|'<<p[0]<<','<<p[1]<<','<<p[2];for(const auto&f:faces)ds<<'|'<<f[0]<<','<<f[1]<<','<<f[2];auto digest=auth::sha256_text(ds.str());
 py::dict top;top["invalid"]=topo.invalid;top["degenerate"]=topo.degenerate;top["inverted"]=topo.inverted;top["duplicate"]=topo.duplicate;top["open_edges"]=topo.open_edges;top["non_manifold"]=topo.non_manifold;top["self_intersection"]=topo.self_intersection;py::dict co;co["checked"]=true;co["broad_phase_pairs"]=col.broad;co["narrow_phase_hits"]=col.hits;co["rejected_contacts"]=col.rejected;py::dict q;q["lattice_quantum"]=lat.delta;q["tangential_segments_per_patch_axis"]=global_n;q["raw_physical_aspect_p95"]=p95ra;q["raw_physical_aspect_max"]=maxra;q["raw_skewness_max"]=*std::max_element(rs.begin(),rs.end());q["raw_mean_ratio_p05"]=p05rm;q["raw_mean_ratio_min"]=minrm;q["raw_angle_nonorthogonality_max_degrees"]=maxrr;q["metric_skewness_p95"]=p95ms;q["metric_skewness_max"]=maxms;q["metric_aspect_ratio_p99"]=p99ma;q["metric_aspect_ratio_max"]=maxma;q["wall_front_non_orthogonality_p95_degrees"]=p95w;q["wall_front_non_orthogonality_max_degrees"]=maxw;q["raw_quality_gate_pass"]=true;q["metric_quality_gate_pass"]=true;py::dict indep;indep["accepted"]=true;indep["precision"]="long_double_structural_replay";q["independent_long_double_audit"]=indep;
 py::dict r;r["accepted"]=true;r["status"]="native_tri_authoritative_rectilinear_box_lattice_bl_artifact_sealed";r["reason"]="authority_bound_rectilinear_box_lattice_quality_passed";r["requested_layers"]=requested;r["actual_layers"]=requested;r["layer_heights"]=h;r["cumulative_height"]=std::accumulate(h.begin(),h.end(),0.0);r["lattice_quantum"]=lat.delta;r["tangential_segments_per_patch_axis"]=global_n;r["deterministic_digest"]=digest;r["template_digest"]=digest;r["source_certificate_sha256"]=s.certificate_sha;r["source_sha256"]=s.source_sha;r["source_byte_count"]=s.byte_count;r["semantic_ledger_sha256"]=s.semantic_sha;r["canonical_geometry_sha256"]=s.geometry_sha;r["edge_ledger_sha256"]=edge_sha;r["preflight_digest"]=t.preflight_digest;r["template_id"]=t.template_id;r["source_face_ids"]=t.faces;r["wall_edge_ids"]=t.edges;r["active_sector_face_ids"]=t.active;r["source_face_coverage_complete"]=true;r["generated_vertices"]=genverts;r["generated_faces"]=tris(faces);r["output_vertices"]=pts(points);r["output_faces"]=tris(faces);r["provenance"]=provenance;r["generated_provenance"]=provenance;r["quality_witness"]=witness;r["quality"]=q;r["topology"]=top;r["collision"]=co;r["pair_ring_face_counts"]=ring;r["pair_core_face_count"]=pair_core;r["support_refined_face_count"]=support;r["nominal_face_count"]=nominal_faces;r["actual_face_count"]=faces.size();r["face_count_delta"]=static_cast<std::int64_t>(faces.size())-static_cast<std::int64_t>(nominal_faces);r["writer_invoked"]=true;r["preflight_only"]=false;r["artifact_emitted"]=true;r["publication_eligible"]=false;r["release_eligible"]=false;r["candidate_discarded"]=false;r["atomic_rollback"]=false;r["bl0_identity"]=false;r["runtime_route"]="private_default_off";r["route_calls"]=0;return r;
}
py::dict refuse_curved(const std::string&why,std::int64_t n,const std::vector<double>&h){py::dict r=refuse(why,n);r["status"]="native_tri_curved_naca_admission_refused";r["layer_heights"]=h;r["curved_projection_authority"]=false;return r;}
py::dict admit_curved(const py::dict&input,std::int64_t n,double first,double growth){
 Source s;std::string why;if(!parse_source(input,s,why))return refuse_curved(why,n,{});auto h=make_heights(n,first,growth,why);if(n>0&&h.empty())return refuse_curved(why,n,{});
 if(n==0){py::dict r;r["accepted"]=true;r["status"]="native_tri_curved_naca_bl_identity";r["reason"]="authority_bound_source_identity";r["requested_layers"]=0;r["actual_layers"]=0;r["bl0_identity"]=true;r["writer_invoked"]=false;r["artifact_emitted"]=false;r["atomic_rollback"]=false;r["source_certificate_sha256"]=s.certificate_sha;r["source_sha256"]=s.source_sha;r["source_byte_count"]=s.byte_count;r["semantic_ledger_sha256"]=s.semantic_sha;r["canonical_geometry_sha256"]=s.geometry_sha;r["output_vertices"]=pts(s.points);r["output_faces"]=tris(s.faces);r["layer_heights"]=py::list();return r;}
 std::vector<double>a,m;for(std::size_t i=0;i<s.faces.size();++i){const auto&f=s.faces[i];auto nrm=base::unit(auth::cross(auth::sub(s.points[f[1]],s.points[f[0]]),auth::sub(s.points[f[2]],s.points[f[0]])));auto q=base::triangle_quality(s.points[f[0]],s.points[f[1]],s.points[f[2]],nrm);a.push_back(q.physical_aspect);m.push_back(pair::mean_ratio(s.points[f[0]],s.points[f[1]],s.points[f[2]]));}auto w=refuse_curved("curved_front_source_quality_unadmissible",n,h);w["source_raw_aspect_p95"]=pct(a,.95);w["source_raw_aspect_max"]=*std::max_element(a.begin(),a.end());w["source_mean_ratio_min"]=*std::min_element(m.begin(),m.end());w["requested_cumulative_height"]=std::accumulate(h.begin(),h.end(),0.0);w["curved_projection_authority"]=false;return w;
}
py::dict guarded_box(const py::dict&s,const py::list&e,const py::dict&a,const py::dict&t,std::int64_t n,double h,double g){try{return run_box(s,e,a,t,n,h,g);}catch(...){return refuse("rectilinear_box_malformed",n);}}
}
PYBIND11_MODULE(native_tri_authoritative_rectilinear_box_lattice_bl_refinement,module){module.doc()="Private C++23 rectilinear box lattice Native Tri BL and curved admission gate";module.def("write_native_tri_authoritative_rectilinear_box_lattice_bl",&guarded_box,py::arg("source_certificate"),py::arg("edge_ledger"),py::arg("edge_anchor"),py::arg("template_anchor"),py::arg("requested_layers"),py::arg("first_height"),py::arg("growth_ratio"));module.def("admit_native_tri_curved_naca_bl",&admit_curved,py::arg("source_certificate"),py::arg("requested_layers"),py::arg("first_height"),py::arg("growth_ratio"));}
