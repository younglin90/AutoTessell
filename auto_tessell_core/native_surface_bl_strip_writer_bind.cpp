#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <limits>
#include <sstream>
#include <tuple>
#include <vector>

#include "surface_bl_front_shared/strip_triangle_quality.hpp"
#include "surface_bl_front_shared/long_double_quality_audit.hpp"
#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

namespace py=pybind11;
using P=std::array<double,3>;
using Tri=std::array<std::int64_t,3>;
P sub(P a,P b){return{a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
P add(P a,P b){return{a[0]+b[0],a[1]+b[1],a[2]+b[2]};}
P mul(P a,double s){return{a[0]*s,a[1]*s,a[2]*s};}
P cross(P a,P b){return{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
double dot(P a,P b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
double len(P a){return std::sqrt(dot(a,a));}
P unit(P a){double n=len(a);if(!(n>1e-14)||!std::isfinite(n))throw std::invalid_argument("degenerate_vector");return mul(a,1./n);}
bool finite(P a){return std::isfinite(a[0])&&std::isfinite(a[1])&&std::isfinite(a[2]);}
py::dict fail(const char* reason){
 py::dict r;r["accepted"]=false;r["status"]="surface_bl_actual_strip_writer_refused";r["reason"]=reason;
 r["candidate_discarded"]=true;r["publication_eligible"]=false;r["generated_faces"]=py::list();r["provenance"]=py::list();return r;
}
bool text(const py::dict&d,const char*k){return d.contains(k)&&!d[k].is_none()&&!py::str(d[k]).cast<std::string>().empty();}
double tri_aspect(P a,P b,P c){return autotessell_surface_bl_quality::aspect(a,b,c);}
double tri_skew(P a,P b,P c){return autotessell_surface_bl_quality::skewness(a,b,c);}
double tri_nonorth(P a,P b,P c){return autotessell_surface_bl_quality::non_orthogonality(a,b,c);}
py::dict write_strip(
 const py::array_t<double,py::array::c_style|py::array::forcecast>& points,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& source_triangles,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& edges,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& layer_ids,
 const py::array_t<double,py::array::c_style|py::array::forcecast>& normals,
 const py::dict& authority,const py::list& provenance,
 std::int64_t requested_layers,double eps=1e-12){
 if(points.ndim()!=2||points.shape(1)!=3||source_triangles.ndim()!=2||source_triangles.shape(1)!=3||
    edges.ndim()!=2||edges.shape(1)!=4||normals.ndim()!=2||normals.shape(1)!=3)
  throw std::invalid_argument("points/triangles/edges/normals_shape");
 if(requested_layers<0)return fail("requested_layers_invalid");
 if(!text(authority,"source_kind")||!text(authority,"source_sha256")||!text(authority,"boundary_mapping_sha256")||
    !text(authority,"physical_group_sha256")||!text(authority,"provenance"))
  return fail("authority_unsealed");
 if(requested_layers==0){
  const auto* pd=points.data();const auto* sd=source_triangles.data();const auto* nd=normals.data();
  auto point0=[&](std::int64_t i){if(i<0||i>=points.shape(0))throw std::invalid_argument("point_id_out_of_range");size_t o=(size_t)i*3;P p{pd[o],pd[o+1],pd[o+2]};if(!finite(p))throw std::invalid_argument("point_not_finite");return p;};
  auto normal0=[&](std::int64_t i){if(i<0||i>=normals.shape(0))throw std::invalid_argument("normal_id_out_of_range");size_t o=(size_t)i*3;return unit(P{nd[o],nd[o+1],nd[o+2]});};
  std::set<std::array<std::int64_t,3>> seen0;std::map<std::pair<std::int64_t,std::int64_t>,int> edge_counts0;std::int64_t invalid0=0,inverted0=0,duplicate0=0,nonmanifold0=0;double min_area0=std::numeric_limits<double>::infinity(),max_skew0=0.0,max_aspect0=0.0,max_nonorth0=0.0;
  py::list lineage0;py::list uids0;
  for(py::ssize_t i=0;i<source_triangles.shape(0);++i){
   size_t o=(size_t)i*3;Tri t{sd[o],sd[o+1],sd[o+2]};Tri key=t;std::sort(key.begin(),key.end());if(!seen0.insert(key).second){++duplicate0;continue;}
   try{P a=point0(t[0]),b=point0(t[1]),c=point0(t[2]);P n=normal0(i);double area=.5*dot(cross(sub(b,a),sub(c,a)),n);if(!(area>eps)){++inverted0;}else{min_area0=std::min(min_area0,area);max_skew0=std::max(max_skew0,tri_skew(a,b,c));max_aspect0=std::max(max_aspect0,tri_aspect(a,b,c));max_nonorth0=std::max(max_nonorth0,tri_nonorth(a,b,c));}for(int j=0;j<3;++j){auto x=t[j],y=t[(j+1)%3];if(x>y)std::swap(x,y);++edge_counts0[{x,y}];}}catch(...){++invalid0;}
   if(static_cast<std::size_t>(i)>=provenance.size())return fail("direct_id_or_provenance_missing");
   py::dict source=provenance[(size_t)i];for(const char*k:{"source_wall_edge","source_face","patch","feature","physical_group","component","provenance"})if(!text(source,k))return fail("direct_id_or_provenance_missing");
   const std::string uid="face-"+std::to_string(i);uids0.append(uid);py::dict row;row["entity_uid"]=uid;for(const char*k:{"patch","feature","physical_group","component","provenance"})row[k]=source[k];lineage0.append(row);
  }
  for(const auto& item:edge_counts0)if(item.second>2)++nonmanifold0;
  if(invalid0||inverted0||duplicate0||nonmanifold0||!std::isfinite(min_area0))return fail("final_surface_topology_failed");
  py::dict quality0;quality0["accepted"]=true;quality0["aspect_family"]="tri_metric_angle";quality0["signed_non_orthogonality_max"]=max_nonorth0;quality0["skewness_max"]=max_skew0;quality0["aspect_ratio_max"]=max_aspect0;quality0["positive_measure_min"]=min_area0;
  py::dict topology0;topology0["invalid"]=invalid0;topology0["duplicate"]=duplicate0;topology0["non_manifold"]=nonmanifold0;topology0["inverted"]=inverted0;
  py::dict boundary0;boundary0["actual_layers"]=0;boundary0["layer_work"]=0;boundary0["positive_measure"]=min_area0>eps;boundary0["rows"]=py::list();
  std::ostringstream artifact0;artifact0<<"native-surface-bl-strip-artifact/v2|bl0|" << std::setprecision(17) << min_area0 << "|" << max_skew0 << "|" << max_aspect0 << "|" << max_nonorth0 << "|";for(py::ssize_t i=0;i<source_triangles.shape(0);++i){size_t o=(size_t)i*3;artifact0<<sd[o]<<","<<sd[o+1]<<","<<sd[o+2]<<";";}const std::string artifact_bytes0=artifact0.str();const std::vector<std::uint8_t> artifact_input0(artifact_bytes0.begin(),artifact_bytes0.end());
  py::dict r;r["accepted"]=true;r["status"]="surface_bl_actual_strip_bl0_identity";r["reason"]="disabled_identity";r["generated_faces"]=py::list();r["provenance"]=lineage0;r["candidate_discarded"]=false;r["publication_eligible"]=false;r["topology"]=topology0;r["quality"]=quality0;r["boundary_layer"]=boundary0;r["entity_uids"]=uids0;r["lineage_rows"]=lineage0;r["strict_topology_checked"]=true;r["quality_checked"]=true;r["artifact_schema"]="native-surface-bl-strip-artifact/v2";r["artifact_bytes"]=artifact_bytes0;r["artifact_byte_size"]=artifact_bytes0.size();r["writer_artifact_sha256"]=brep_evidence::sha256_hex(artifact_input0);r["count_is_report_only"]=true;return r;
 }
 if(layer_ids.ndim()!=3||layer_ids.shape(0)!=requested_layers||layer_ids.shape(1)!=edges.shape(0)||layer_ids.shape(2)!=2)
  return fail("layer_point_id_missing");
 if(provenance.size()!=static_cast<size_t>(requested_layers*edges.shape(0)))return fail("source_edge_lineage_missing");
 const auto*pd=points.data();const auto*sd=source_triangles.data();const auto*ed=edges.data();const auto*ld=layer_ids.data();const auto*nd=normals.data();
 auto point=[&](std::int64_t i){if(i<0||i>=points.shape(0))throw std::invalid_argument("point_id_out_of_range");size_t o=(size_t)i*3;P p{pd[o],pd[o+1],pd[o+2]};if(!finite(p))throw std::invalid_argument("point_not_finite");return p;};
 auto normal=[&](std::int64_t i){if(i<0||i>=normals.shape(0))throw std::invalid_argument("normal_id_out_of_range");size_t o=(size_t)i*3;return unit(P{nd[o],nd[o+1],nd[o+2]});};
 std::vector<Tri> faces;std::set<std::array<std::int64_t,3>> seen;py::list output_prov;std::int64_t invalid=0,inverted=0,duplicate=0,nonmanifold=0;double min_positive_area=std::numeric_limits<double>::infinity();double max_skew=0.0,max_aspect=0.0,max_nonorth=0.0;
 auto add_face=[&](Tri t,P n){Tri key=t;std::sort(key.begin(),key.end());if(!seen.insert(key).second){++duplicate;return;}try{P a=point(t[0]),b=point(t[1]),c=point(t[2]);double area=.5*dot(cross(sub(b,a),sub(c,a)),n);if(!(area>eps))++inverted;else min_positive_area=std::min(min_positive_area,area);}catch(...){++invalid;}faces.push_back(t);};
 for(py::ssize_t i=0;i<source_triangles.shape(0);++i){size_t o=(size_t)i*3;add_face({sd[o],sd[o+1],sd[o+2]},normal(i));}
 py::list decisions;
 for(std::int64_t layer=0;layer<requested_layers;++layer){
  for(py::ssize_t ei=0;ei<edges.shape(0);++ei){
   size_t eo=(size_t)ei*4;std::int64_t edge_id=ed[eo],a=ed[eo+1],b=ed[eo+2],fi=ed[eo+3];
   if(fi<0||fi>=normals.shape(0))return fail("selected_edge_not_boundary");
   std::int64_t ua=layer==0?a:ld[((size_t)(layer-1)*(size_t)edges.shape(0)+(size_t)ei)*2];
   std::int64_t ub=layer==0?b:ld[((size_t)(layer-1)*(size_t)edges.shape(0)+(size_t)ei)*2+1];
   std::int64_t va=ld[((size_t)layer*(size_t)edges.shape(0)+(size_t)ei)*2];
   std::int64_t vb=ld[((size_t)layer*(size_t)edges.shape(0)+(size_t)ei)*2+1];
   if(ua<0||ub<0||va<0||vb<0||ua>=points.shape(0)||ub>=points.shape(0)||va>=points.shape(0)||vb>=points.shape(0))
     return fail("layer_point_id_missing");

   Tri t0{ua,ub,vb},t1{ua,vb,va},u0{ua,ub,va},u1{ub,vb,va};
   auto score=[&](Tri x,Tri y){double sk=0,asp=0,no=0;for(Tri t:{x,y}){P p=point(t[0]),q=point(t[1]),r=point(t[2]);sk=std::max(sk,tri_skew(p,q,r));asp=std::max(asp,tri_aspect(p,q,r));no=std::max(no,tri_nonorth(p,q,r));}return std::tuple<double,double,double>{sk,asp,no};};
   auto s0=score(t0,t1),s1=score(u0,u1);bool first=s0<=s1;auto chosen=first?std::array<Tri,2>{t0,t1}:std::array<Tri,2>{u0,u1};auto sc=first?s0:s1;
   constexpr double quality_tolerance=1e-12; if(std::get<0>(sc)>.50+quality_tolerance||std::get<1>(sc)>10.+quality_tolerance||std::get<2>(sc)>75.+quality_tolerance)return fail("strip_diagonal_no_quality_admissible");
   P strip_n=unit(cross(sub(point(ub),point(ua)),normal(fi)));add_face(chosen[0],strip_n);add_face(chosen[1],strip_n);
   max_skew=std::max(max_skew,std::get<0>(sc));max_aspect=std::max(max_aspect,std::get<1>(sc));max_nonorth=std::max(max_nonorth,std::get<2>(sc));py::dict d;d["layer"]=layer;d["source_edge"]=edge_id;d["diagonal"]=first?0:1;d["skewness"]=std::get<0>(sc);d["metric_aspect_ratio"]=std::get<1>(sc);d["non_orthogonality"]=std::get<2>(sc);decisions.append(d);
   py::dict p=provenance[(size_t)layer*(size_t)edges.shape(0)+(size_t)ei];for(const char*k:{"source_wall_edge","source_face","patch","feature","physical_group","component","provenance"})if(!text(p,k))return fail("direct_id_or_provenance_missing");
   p["layer"]=layer+1;p["final_face_ids"]=py::make_tuple((std::int64_t)(faces.size()-2),(std::int64_t)(faces.size()-1));p["writer_face_uids"]=py::make_tuple("face-"+std::to_string(faces.size()-2),"face-"+std::to_string(faces.size()-1));output_prov.append(p);
  }
 }
 std::map<std::pair<std::int64_t,std::int64_t>,int> ec;for(const auto&t:faces)for(int i=0;i<3;++i){auto a=t[i],b=t[(i+1)%3];if(a>b)std::swap(a,b);++ec[{a,b}];}for(const auto&[e,n]:ec)if(n>2)++nonmanifold;
 if(invalid||inverted||duplicate||nonmanifold)return fail("final_surface_topology_failed");
 py::list outfaces;for(const auto&t:faces){py::list row;for(auto v:t)row.append(v);outfaces.append(row);}
 if(!std::isfinite(min_positive_area)||!std::isfinite(max_skew)||!std::isfinite(max_aspect)||!std::isfinite(max_nonorth))return fail("surface_quality_witness_missing");
 py::list entity_uids;py::list lineage_rows;const auto source_count=static_cast<std::size_t>(source_triangles.shape(0));if(output_prov.empty())return fail("direct_id_or_provenance_missing");
 for(std::size_t index=0;index<faces.size();++index){const std::string uid="face-"+std::to_string(index);entity_uids.append(uid);const auto lineage_index=std::min((index<source_count?std::size_t(0):(index-source_count)/2),static_cast<std::size_t>(output_prov.size()-1));const auto source=output_prov[static_cast<py::ssize_t>(lineage_index)].cast<py::dict>();py::dict row;row["entity_uid"]=uid;for(const char*k:{"patch","feature","physical_group","component","provenance"})row[k]=source[k];lineage_rows.append(row);}
 py::dict quality;quality["accepted"]=true;quality["aspect_family"]="tri_metric_angle";quality["signed_non_orthogonality_max"]=max_nonorth;quality["skewness_max"]=max_skew;quality["aspect_ratio_max"]=max_aspect;quality["positive_measure_min"]=min_positive_area;
 py::dict topology;topology["invalid"]=invalid;topology["duplicate"]=duplicate;topology["non_manifold"]=nonmanifold;topology["inverted"]=inverted;
 py::dict boundary;boundary["actual_layers"]=requested_layers;boundary["layer_work"]=static_cast<std::int64_t>(faces.size());boundary["positive_measure"]=min_positive_area>eps;py::list roles;py::dict wall;wall["role"]="wall";roles.append(wall);py::dict front;front["role"]="front";roles.append(front);py::dict side;side["role"]="side";roles.append(side);boundary["rows"]=roles;
 std::ostringstream artifact_stream;artifact_stream<<"native-surface-bl-strip-artifact/v2\n"<<requested_layers<<'\n'<<std::setprecision(17)<<max_nonorth<<'\n'<<max_skew<<'\n'<<max_aspect<<'\n';for(const auto&t:faces)artifact_stream<<t[0]<<','<<t[1]<<','<<t[2]<<';';const std::string artifact_bytes=artifact_stream.str();const std::vector<std::uint8_t> artifact_input(artifact_bytes.begin(),artifact_bytes.end());
 py::dict r;r["accepted"]=true;r["status"]="surface_bl_actual_strip_artifact_sealed";r["reason"]="direct_id_quality_gated_strip_emitted";r["generated_faces"]=outfaces;r["provenance"]=output_prov;r["diagonal_decisions"]=decisions;r["topology_invalid"]=invalid;r["topology_inverted"]=inverted;r["topology_duplicate"]=duplicate;r["topology_non_manifold"]=nonmanifold;r["topology"]=topology;r["quality"]=quality;r["boundary_layer"]=boundary;r["entity_uids"]=entity_uids;r["lineage_rows"]=lineage_rows;r["strict_topology_checked"]=true;r["quality_checked"]=true;r["artifact_schema"]="native-surface-bl-strip-artifact/v2";r["artifact_bytes"]=artifact_bytes;r["artifact_byte_size"]=artifact_bytes.size();r["writer_artifact_sha256"]=brep_evidence::sha256_hex(artifact_input);r["candidate_discarded"]=false;r["publication_eligible"]=false;r["count_is_report_only"]=true;return r;
}
#include "surface_bl_front_shared/planar_cavity_writer.hpp"
PYBIND11_MODULE(native_surface_bl_strip_writer,m){m.doc()="Private C++23 authoritative surface BL strip writer";m.def("write_authoritative_surface_bl_strip",&write_strip,py::arg("points"),py::arg("source_triangles"),py::arg("edges"),py::arg("layer_point_ids"),py::arg("normals"),py::arg("authority"),py::arg("provenance"),py::arg("requested_layers"),py::arg("epsilon")=1e-12);m.def("write_authoritative_surface_bl_planar_cavity",&write_planar_cavity,py::arg("points"),py::arg("source_triangles"),py::arg("edges"),py::arg("layer_point_ids"),py::arg("normals"),py::arg("authority"),py::arg("provenance"),py::arg("requested_layers"),py::arg("epsilon")=1e-12,py::arg("strict_quality")=false);}
