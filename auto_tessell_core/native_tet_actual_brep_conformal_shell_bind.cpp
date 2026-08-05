// C++23 restricted actual BRep regular-tetrahedral pure-Tet BL producer.
// Private/default-off evidence only. No generic CAD reconnection is attempted.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;
using Tri = std::array<std::int64_t, 3>;
using Tet = std::array<std::int64_t, 4>;
using FaceKey = std::array<std::int64_t, 3>;

Point sub(Point a, Point b) noexcept { return {a[0]-b[0], a[1]-b[1], a[2]-b[2]}; }
Point add(Point a, Point b) noexcept { return {a[0]+b[0], a[1]+b[1], a[2]+b[2]}; }
Point mul(Point a, double s) noexcept { return {a[0]*s, a[1]*s, a[2]*s}; }
Point cross(Point a, Point b) noexcept { return {a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]}; }
double dot(Point a, Point b) noexcept { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
double norm(Point a) noexcept { return std::sqrt(dot(a,a)); }

double volume6(const std::vector<Point>& p, const Tet& t) {
    return dot(sub(p[t[1]],p[t[0]]), cross(sub(p[t[2]],p[t[0]]), sub(p[t[3]],p[t[0]])));
}
FaceKey sorted_face(Tri f) { std::sort(f.begin(), f.end()); return f; }
int orientation_sign(Tri f) {
    int inv=0; for(int i=0;i<3;++i) for(int j=i+1;j<3;++j) if(f[i]>f[j]) ++inv;
    return (inv&1)?-1:1;
}
std::string text(const py::dict& row, const char* key) {
    return row.contains(key) ? py::str(row[key]).cast<std::string>() : std::string{};
}
py::dict refuse(const std::string& reason, std::int64_t requested) {
    py::dict out; out["accepted"]=false; out["status"]="actual_brep_tet_shell_refused";
    out["reason"]=reason; out["requested_layers"]=requested; out["actual_layers"]=0;
    out["runtime_route"]="default_off"; out["publication_eligible"]=false;
    out["candidate_discarded"]=true; out["atomic_rollback"]=true; return out;
}
std::vector<Point> load_points(const py::array_t<double,py::array::c_style|py::array::forcecast>& a) {
    if(a.ndim()!=2||a.shape(1)!=3) throw std::invalid_argument("canonical_positions_must_be_Nx3");
    auto r=a.unchecked<2>(); std::vector<Point> out; out.reserve(static_cast<size_t>(r.shape(0)));
    for(py::ssize_t i=0;i<r.shape(0);++i){Point p{};for(int j=0;j<3;++j){p[j]=r(i,j);if(!std::isfinite(p[j]))throw std::invalid_argument("canonical_position_nonfinite");}out.push_back(p);}
    return out;
}
py::list points_py(const std::vector<Point>& p){py::list o;for(const auto&x:p)o.append(py::make_tuple(x[0],x[1],x[2]));return o;}
py::list tets_py(const std::vector<Tet>& c){py::list o;for(const auto&t:c)o.append(py::make_tuple(t[0],t[1],t[2],t[3]));return o;}
py::list tris_py(const std::vector<Tri>& f){py::list o;for(const auto&x:f)o.append(py::make_tuple(x[0],x[1],x[2]));return o;}

struct SourceFace{std::int64_t id;Tri vertices;};
struct Plane{std::int64_t id;Point p;Point n;};
struct FaceRecord{Tri face;std::int64_t owner=-1;std::int64_t neighbour=-1;std::vector<int> signs;};
struct Candidate{
    std::vector<Point> points;std::vector<Tet> cells;std::vector<FaceRecord> internal_faces,boundary_faces;
    double min_volume=0.,min_jacobian=0.,max_aspect=0.,p95_aspect=0.,max_skew=0.,p95_skew=0.;
    int duplicate=0,non_manifold=0,inverted=0,degenerate=0,self_intersection=0;bool valid=false;std::string error;
};
std::pair<double,double> tet_metrics(const std::vector<Point>&p,const Tet&t){
    double lo=std::numeric_limits<double>::infinity(),hi=0.;
    for(int i=0;i<4;++i)for(int j=i+1;j<4;++j){double d=norm(sub(p[t[j]],p[t[i]]));lo=std::min(lo,d);hi=std::max(hi,d);}
    return (lo>1e-14&&hi>1e-14)?std::pair<double,double>{hi/lo,(hi-lo)/hi}:std::pair<double,double>{std::numeric_limits<double>::infinity(),std::numeric_limits<double>::infinity()};
}
double percentile(std::vector<double>v,double q){if(v.empty())return 0.;std::sort(v.begin(),v.end());return v[std::min(v.size()-1,static_cast<size_t>(std::ceil(q*v.size())-1))];}
std::array<Tri,4> cell_faces(const Tet&t){return {Tri{t[0],t[2],t[1]},Tri{t[0],t[1],t[3]},Tri{t[0],t[3],t[2]},Tri{t[1],t[2],t[3]}};}

Candidate build_candidate(const std::vector<Point>&base,const Tri&wall,const std::vector<std::array<std::int64_t,3>>&rings,std::int64_t apex,int tid,double base_volume){
    Candidate c;c.points=base;
    std::vector<double>aspects,skews;double total=0.;c.min_volume=std::numeric_limits<double>::infinity();c.min_jacobian=std::numeric_limits<double>::infinity();
    for(size_t layer=0;layer<rings.size();++layer){
        const auto prev=layer==0?wall:rings[layer-1];const auto next=rings[layer];
        int i0=tid%3,i1=(tid+1)%3,i2=(tid+2)%3;
        std::array<Tet,3> prism={Tet{prev[i0],prev[i1],prev[i2],next[i0]},Tet{prev[i1],prev[i2],next[i0],next[i1]},Tet{prev[i2],next[i0],next[i1],next[i2]}};
        for(auto t:prism){if(volume6(c.points,t)<0.)std::swap(t[2],t[3]);c.cells.push_back(t);}
    }
    Tet inner;
    if(rings.empty())inner=Tet{wall[0],wall[1],wall[2],apex};else{auto r=rings.back();inner=Tet{r[0],r[1],r[2],apex};}
    if(volume6(c.points,inner)<0.)std::swap(inner[2],inner[3]);c.cells.push_back(inner);
    std::map<FaceKey,FaceRecord> fmap;std::map<FaceKey,int> counts;std::set<std::array<std::int64_t,4>> seen;
    for(size_t ci=0;ci<c.cells.size();++ci){
        const auto&t=c.cells[ci];double v=volume6(c.points,t)/6.;total+=v;c.min_volume=std::min(c.min_volume,v);if(!(v>1e-14))++c.degenerate;
        auto [ar,sk]=tet_metrics(c.points,t);aspects.push_back(ar);skews.push_back(sk);c.max_aspect=std::max(c.max_aspect,ar);c.max_skew=std::max(c.max_skew,sk);
        double hi=0.;for(int i=0;i<4;++i)for(int j=i+1;j<4;++j)hi=std::max(hi,norm(sub(c.points[t[j]],c.points[t[i]])));
        if(hi>1e-14)c.min_jacobian=std::min(c.min_jacobian,v/(hi*hi*hi));
        auto s=t;std::sort(s.begin(),s.end());if(!seen.insert(s).second)++c.duplicate;
        for(const auto&f:cell_faces(t)){auto k=sorted_face(f);auto it=fmap.find(k);if(it==fmap.end()){FaceRecord r;r.face=f;r.owner=static_cast<std::int64_t>(ci);r.signs.push_back(orientation_sign(f));fmap.emplace(k,r);}else{it->second.neighbour=static_cast<std::int64_t>(ci);it->second.signs.push_back(orientation_sign(f));}++counts[k];}
    }
    if(std::abs(total-base_volume)>std::max(1e-12,1e-8*base_volume))c.error="tet_shell_volume_not_conservative";
    for(const auto&[k,n]:counts){const auto&r=fmap.at(k);if(n>2)++c.non_manifold;if(n==2&&r.signs.size()==2&&r.signs[0]==r.signs[1])++c.inverted;}
    c.p95_aspect=percentile(aspects,.95);c.p95_skew=percentile(skews,.95);
    for(const auto&[k,r]:fmap){if(r.neighbour>=0)c.internal_faces.push_back(r);else c.boundary_faces.push_back(r);}
    c.valid=c.error.empty()&&c.duplicate==0&&c.non_manifold==0&&c.inverted==0&&c.degenerate==0&&c.min_volume>1e-14&&c.min_jacobian>1e-14&&c.max_aspect<5.&&c.p95_aspect<5.&&c.max_skew<.8&&c.p95_skew<.8;
    if(!c.valid&&c.error.empty())c.error="tet_shell_topology_or_quality_gate_failed";return c;
}

py::dict produce(const py::array_t<double,py::array::c_style|py::array::forcecast>&positions_array,const py::dict&evidence,const py::list&explicit_mapping,std::int64_t requested,double first_height,double growth){
    if(requested<0||requested>64)return refuse("invalid_requested_layers",requested);auto base=load_points(positions_array);if(base.size()!=4)return refuse("regular_tetra_fixture_requires_four_vertices",requested);
    if(!std::isfinite(first_height)||!std::isfinite(growth)||first_height<=0.||growth<=0.)return refuse("invalid_layer_geometry_parameters",requested);
    if(!evidence.contains("triangles")||!evidence.contains("edges"))return refuse("brep_evidence_missing",requested);
    auto triangles=evidence["triangles"].cast<py::list>();auto edges=evidence["edges"].cast<py::list>();if(triangles.size()!=4||edges.size()!=6)return refuse("regular_tetra_brep_cardinality_failed",requested);
    std::vector<SourceFace>source_faces;std::set<std::int64_t>face_ids;
    for(py::handle h:triangles){auto row=h.cast<py::dict>();if(!row.contains("brep_face_id")||!row.contains("canonical_vertices"))return refuse("brep_face_record_incomplete",requested);auto id=row["brep_face_id"].cast<std::int64_t>();auto v=row["canonical_vertices"].cast<py::sequence>();if(v.size()!=3||!face_ids.insert(id).second)return refuse("brep_face_stream_invalid",requested);Tri f{v[0].cast<std::int64_t>(),v[1].cast<std::int64_t>(),v[2].cast<std::int64_t>()};for(auto x:f)if(x<0||x>=4)return refuse("brep_face_vertex_invalid",requested);source_faces.push_back({id,f});}
    std::sort(source_faces.begin(),source_faces.end(),[](const SourceFace&a,const SourceFace&b){return a.id<b.id;});
    std::set<FaceKey>edge_keys;for(py::handle h:edges){auto row=h.cast<py::dict>();if(!row.contains("is_actual_brep_edge")||!row["is_actual_brep_edge"].cast<bool>()||!row.contains("canonical_endpoints"))return refuse("actual_brep_edge_witness_missing",requested);auto ep=row["canonical_endpoints"].cast<py::sequence>();if(ep.size()!=2)return refuse("actual_brep_edge_endpoint_invalid",requested);FaceKey k{ep[0].cast<std::int64_t>(),ep[1].cast<std::int64_t>(),0};if(k[0]>k[1])std::swap(k[0],k[1]);if(k[0]<0||k[1]>=4||!edge_keys.insert(k).second)return refuse("actual_brep_edge_stream_invalid",requested);}
    double shortest=std::numeric_limits<double>::infinity(),longest=0.;for(int i=0;i<4;++i)for(int j=i+1;j<4;++j){double d=norm(sub(base[i],base[j]));shortest=std::min(shortest,d);longest=std::max(longest,d);}if(!(shortest>1e-12)||longest/shortest>1.000001)return refuse("regular_tetra_shape_required",requested);
    std::vector<py::dict>mappings;for(py::handle h:explicit_mapping){auto row=h.cast<py::dict>();for(const char*k:{"source_edge","source_face","wall_edge","output_face","patch","feature","physical_group","component","provenance"})if(!row.contains(k)||text(row,k).empty())return refuse("explicit_semantic_mapping_incomplete",requested);if(!row.contains("direct")||!row["direct"].cast<bool>())return refuse("explicit_semantic_mapping_not_direct",requested);mappings.push_back(row);}
    int selected=-1;py::dict selected_row;for(const auto&row:mappings)if(row.contains("selected_for_bl")&&row["selected_for_bl"].cast<bool>()){if(selected>=0)return refuse("multiple_selected_wall_edges",requested);selected=static_cast<int>(row["source_edge"].cast<std::int64_t>());selected_row=row;}if(selected<0)return refuse("selected_wall_edge_missing",requested);
    auto wall_id=selected_row["source_face"].cast<std::int64_t>();auto wit=std::find_if(source_faces.begin(),source_faces.end(),[&](const SourceFace&f){return f.id==wall_id;});if(wit==source_faces.end())return refuse("selected_wall_face_missing",requested);Tri wall=wit->vertices;int apex=-1;for(int i=0;i<4;++i)if(i!=wall[0]&&i!=wall[1]&&i!=wall[2])apex=i;if(apex<0)return refuse("tetra_apex_missing",requested);
    Point n=cross(sub(base[wall[1]],base[wall[0]]),sub(base[wall[2]],base[wall[0]]));double nn=norm(n);if(!(nn>1e-12))return refuse("wall_face_degenerate",requested);n=mul(n,1./nn);Point centroid=mul(add(add(base[wall[0]],base[wall[1]]),base[wall[2]]),1./3.);double signed_h=dot(sub(base[apex],centroid),n);if(std::abs(signed_h)<1e-12)return refuse("tetra_apex_height_invalid",requested);if(norm(sub(sub(base[apex],mul(n,signed_h)),centroid))>1e-6*longest)return refuse("apex_projection_not_wall_centroid",requested);double height=std::abs(signed_h);
    if(requested>0){double total=0.;for(std::int64_t i=0;i<requested;++i)total+=first_height*std::pow(growth,static_cast<double>(i));if(!(total<height*(1.-1e-12)))return refuse("layer_stack_exceeds_apex_altitude",requested);}
    std::vector<Point>common=base;std::vector<std::array<std::int64_t,3>>rings;double cumulative=0.;for(std::int64_t layer=0;layer<requested;++layer){cumulative+=first_height*std::pow(growth,static_cast<double>(layer));double s=cumulative/height;std::array<std::int64_t,3>r{};for(int j=0;j<3;++j){r[j]=static_cast<std::int64_t>(common.size());common.push_back(add(mul(base[wall[j]],1.-s),mul(base[apex],s)));}rings.push_back(r);}
    double base_volume=std::abs(volume6(base,Tet{0,1,2,3}))/6.;std::vector<Candidate>candidates;for(int tid=0;tid<3;++tid)candidates.push_back(build_candidate(common,wall,rings,apex,tid,base_volume));
    auto best_it=std::min_element(candidates.begin(),candidates.end(),[](const Candidate&a,const Candidate&b){auto ka=std::tuple<int,int,int,double,double,double>{!a.valid,a.duplicate+a.non_manifold+a.inverted+a.degenerate,-a.min_jacobian,a.max_aspect,a.max_skew,0.};auto kb=std::tuple<int,int,int,double,double,double>{!b.valid,b.duplicate+b.non_manifold+b.inverted+b.degenerate,-b.min_jacobian,b.max_aspect,b.max_skew,0.};return ka<kb;});if(best_it==candidates.end()||!best_it->valid)return refuse("all_prism_templates_rejected",requested);Candidate best=*best_it;
    std::vector<Plane>planes;for(const auto&sf:source_faces){Point pn=cross(sub(best.points[sf.vertices[1]],best.points[sf.vertices[0]]),sub(best.points[sf.vertices[2]],best.points[sf.vertices[0]]));pn=mul(pn,1./norm(pn));planes.push_back({sf.id,best.points[sf.vertices[0]],pn});}
    std::map<std::int64_t,std::vector<FaceRecord>>by_source;for(const auto&rec:best.boundary_faces){std::set<std::int64_t>matches;for(const auto&pl:planes){bool on=true;for(auto id:rec.face)if(std::abs(dot(sub(best.points[id],pl.p),pl.n))>1e-7*longest)on=false;if(on)matches.insert(pl.id);}if(matches.size()!=1)return refuse("boundary_face_source_binding_ambiguous",requested);by_source[*matches.begin()].push_back(rec);}
    std::vector<Tri>all_faces;std::vector<std::int64_t>owners,neighbours;std::map<FaceKey,std::int64_t>final_ids;for(const auto&rec:best.internal_faces){final_ids[sorted_face(rec.face)]=static_cast<std::int64_t>(all_faces.size());all_faces.push_back(rec.face);owners.push_back(rec.owner);neighbours.push_back(rec.neighbour);}
    std::vector<std::array<std::int64_t,2>>ranges;std::vector<std::vector<std::int64_t>>boundary_ids(source_faces.size());for(size_t si=0;si<source_faces.size();++si){auto sid=source_faces[si].id;const auto&rows=by_source[sid];if(rows.empty())return refuse("source_face_boundary_coverage_missing",requested);auto start=static_cast<std::int64_t>(all_faces.size());for(const auto&rec:rows){final_ids[sorted_face(rec.face)]=static_cast<std::int64_t>(all_faces.size());boundary_ids[si].push_back(static_cast<std::int64_t>(all_faces.size()));all_faces.push_back(rec.face);owners.push_back(rec.owner);}ranges.push_back({start,static_cast<std::int64_t>(rows.size())});}
    auto find_edge=[&](std::int64_t a,std::int64_t b){auto lo=std::min(a,b),hi=std::max(a,b);for(py::handle h:edges){auto row=h.cast<py::dict>();auto ep=row["canonical_endpoints"].cast<py::sequence>();auto x=ep[0].cast<std::int64_t>(),y=ep[1].cast<std::int64_t>();if(std::min(x,y)==lo&&std::max(x,y)==hi)return row["brep_edge_id"].cast<std::int64_t>();}return static_cast<std::int64_t>(-1);};
    py::list layer_rows;for(size_t layer=0;layer<rings.size();++layer){py::dict row;row["source_wall_edge"]=selected;row["source_face"]="face-"+std::to_string(wall_id);row["layer"]=static_cast<std::int64_t>(layer);std::vector<std::int64_t>cell_ids;for(int j=0;j<3;++j)cell_ids.push_back(static_cast<std::int64_t>(layer*3+j));row["cell_ids"]=cell_ids;auto k=sorted_face(Tri{rings[layer][0],rings[layer][1],rings[layer][2]});row["front_face_ids"]=final_ids.count(k)?py::make_tuple(final_ids[k]):py::tuple();row["feature"]=text(selected_row,"feature");row["patch"]=text(selected_row,"patch");row["physical_group"]=text(selected_row,"physical_group");row["component"]=text(selected_row,"component");row["orientation"]="forward";row["provenance"]=text(selected_row,"provenance");layer_rows.append(row);}
    py::list bindings;for(size_t si=0;si<source_faces.size();++si){auto sid=source_faces[si].id;py::dict sem;for(const auto&m:mappings)if(m["source_face"].cast<std::int64_t>()==sid){sem=m;break;}if(sem.empty())sem=selected_row;auto fv=source_faces[si].vertices;std::int64_t w0=fv[0],w1=fv[1],f0=w0,f1=w1,eid=find_edge(w0,w1);for(int i=0;i<3;++i)for(int j=i+1;j<3;++j){bool a=false,b=false;for(auto x:wall){a|=x==fv[i];b|=b||x==fv[j];}if(a&&b){w0=fv[i];w1=fv[j];eid=find_edge(w0,w1);}}if(!rings.empty())for(int j=0;j<3;++j){if(wall[j]==w0)f0=rings[0][j];if(wall[j]==w1)f1=rings[0][j];}std::vector<std::int64_t>ids=boundary_ids[si],cell_ids;for(const auto&rec:by_source[sid])cell_ids.push_back(rec.owner);py::dict row;row["source_face"]="face-"+std::to_string(sid);row["source_face_a"]="";row["source_face_b"]="";row["source_edge"]="edge-"+std::to_string(eid);row["wall_edge"]="wall-"+std::to_string(eid);row["bl_strip"]="tet-shell-face-"+std::to_string(sid);row["output_boundary_face"]="out-face-"+std::to_string(sid);row["volume_boundary_face"]="vol-face-"+std::to_string(sid);row["feature"]=text(sem,"feature");row["patch"]=text(sem,"patch");row["physical_group"]=text(sem,"physical_group");row["component"]=text(sem,"component");row["provenance"]=text(sem,"provenance");row["wall0"]=w0;row["wall1"]=w1;row["front0"]=f0;row["front1"]=f1;row["tangent_face"]="face-"+std::to_string(sid);row["first_strip_face"]=ids.front();row["orientation"]="forward";row["final_cell_ids"]=cell_ids;row["final_front_face_ids"]=ids;row["final_wall_face_ids"]=ids;bindings.append(row);}
    py::dict topology;topology["duplicate"]=best.duplicate;topology["non_manifold"]=best.non_manifold;topology["inverted"]=best.inverted;topology["degenerate"]=best.degenerate;topology["self_intersection"]=best.self_intersection;
    py::dict quality;quality["minimum_volume"]=best.min_volume;quality["minimum_scaled_jacobian"]=best.min_jacobian;quality["max_aspect_ratio"]=best.max_aspect;quality["p95_aspect_ratio"]=best.p95_aspect;quality["max_skewness"]=best.max_skew;quality["p95_skewness"]=best.p95_skew;quality["template_key"]=static_cast<int>(best_it-candidates.begin());quality["base_volume"]=base_volume;quality["total_cells"]=static_cast<std::int64_t>(best.cells.size());
    py::list receipts;for(size_t i=0;i<candidates.size();++i){py::dict q;q["template_key"]=static_cast<int>(i);q["accepted"]=candidates[i].valid;q["min_volume"]=candidates[i].min_volume;q["min_scaled_jacobian"]=candidates[i].min_jacobian;q["max_aspect_ratio"]=candidates[i].max_aspect;q["max_skewness"]=candidates[i].max_skew;q["reason"]=candidates[i].error;receipts.append(q);}
    py::list face_rows;for(size_t i=0;i<all_faces.size();++i){py::dict r;r["face_id"]=static_cast<std::int64_t>(i);r["vertices"]=all_faces[i];r["source_face"]=static_cast<std::int64_t>(-1);face_rows.append(r);}for(size_t si=0;si<source_faces.size();++si)for(auto id:boundary_ids[si])face_rows[id].cast<py::dict>()["source_face"]=source_faces[si].id;
    py::list range_rows;for(size_t si=0;si<ranges.size();++si)range_rows.append(py::make_tuple(source_faces[si].id,ranges[si][0],ranges[si][1]));
    py::dict out;out["accepted"]=true;out["status"]=requested?"actual_brep_conformal_tet_shell_produced":"disabled_identity";out["reason"]="regular_tetra_conformal_shell_passed";out["points"]=points_py(best.points);out["cells"]=tets_py(best.cells);out["faces"]=tris_py(all_faces);py::list own;for(auto x:owners)own.append(x);out["owner"]=own;py::list nei;for(auto x:neighbours)nei.append(x);out["neighbour"]=nei;py::list br;for(const auto&r:ranges)br.append(py::make_tuple(r[0],r[1]));out["boundary_ranges"]=br;out["boundary_faces"]=face_rows;out["boundary_ranges_by_source"]=range_rows;out["layer_records"]=layer_rows;out["boundary_binding"]=bindings;out["topology"]=topology;out["quality"]=quality;out["template_candidates"]=receipts;out["actual_layers"]=requested;out["requested_layers"]=requested;out["runtime_route"]="default_off";out["publication_eligible"]=false;out["candidate_discarded"]=false;out["direct_lineage"]=true;out["authority_level"]="L0_actual_brep_fixture";return out;
}
PYBIND11_MODULE(native_tet_actual_brep_conformal_shell,m){m.doc()="Private C++23 regular tetrahedron actual BRep conformal pure-Tet BL producer";m.def("produce_actual_brep_conformal_tet_shell",&produce,py::arg("canonical_positions"),py::arg("evidence"),py::arg("explicit_mapping"),py::arg("requested_layers"),py::arg("first_height"),py::arg("growth_ratio"));}