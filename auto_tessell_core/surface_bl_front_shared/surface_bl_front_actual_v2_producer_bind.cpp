// C++23 actual BRepFrontEvidence/v2 surface wall-edge producer.
// It consumes canonical IDs and the feature-aware optimizer receipt directly.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;
using Tri = std::array<std::int64_t, 3>;

namespace {
Point sub(Point a, Point b) { return {a[0]-b[0],a[1]-b[1],a[2]-b[2]}; }
Point cross(Point a, Point b) { return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]}; }
double dot(Point a, Point b) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
std::string text(const py::dict& row, const char* key) {
    return row.contains(key) && !row[key].is_none() ? py::str(row[key]).cast<std::string>() : std::string{};
}
bool truth(const py::dict& row, const char* key) {
    return row.contains(key) && !row[key].is_none() && row[key].cast<bool>();
}
py::dict refuse(const std::string& reason, std::int64_t requested) {
    py::dict r; r["accepted"]=false; r["status"]="actual_brep_surface_producer_rolled_back";
    r["reason"]=reason; r["requested_layers"]=requested; r["actual_layers"]=0;
    r["runtime_route"]="default_off"; r["publication_eligible"]=false;
    r["candidate_discarded"]=true; r["atomic_rollback"]=true; return r;
}
py::list as_points(const std::vector<Point>& points) {
    py::list out; for (const auto& p:points) out.append(py::make_tuple(p[0],p[1],p[2])); return out;
}
py::list as_triangles(const std::vector<Tri>& faces) {
    py::list out; for (const auto& f:faces) out.append(py::make_tuple(f[0],f[1],f[2])); return out;
}
}

py::dict produce(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& positions,
    const py::dict& evidence, const py::list& mapping,
    const py::dict& optimizer, std::int64_t requested) {
    if (requested < 0) return refuse("negative_layer_count", requested);
    if (positions.ndim()!=2 || positions.shape(1)!=3) return refuse("canonical_positions_invalid", requested);
    if (evidence.contains("schema") && py::str(evidence["schema"]).cast<std::string>() != "BRepFrontEvidence/v2")
        return refuse("brep_evidence_v2_schema_mismatch", requested);
    if (!optimizer.contains("accepted") || !optimizer["accepted"].cast<bool>())
        return refuse("optimizer_receipt_not_accepted", requested);
    py::dict selected; bool found=false;
    for (py::handle h:mapping) {
        auto row=h.cast<py::dict>();
        if (truth(row,"selected_for_bl")) { if(found) return refuse("multiple_selected_wall_edges",requested); selected=row; found=true; }
    }
    if (!found && !mapping.empty()) { selected=mapping[0].cast<py::dict>(); found=true; }
    if (!found) return refuse("selected_wall_edge_missing", requested);
    for (const char* key:{"source_edge","source_face","wall_edge","output_face","patch","feature","physical_group","component","provenance"})
        if (!selected.contains(key) || text(selected,key).empty()) return refuse("mapping_lineage_incomplete",requested);
    const auto edge_id=selected["source_edge"].cast<std::int64_t>();
    const auto face_id=selected["source_face"].cast<std::int64_t>();
    py::dict edge; bool edge_found=false;
    if (evidence.contains("edges")) for (py::handle h:evidence["edges"].cast<py::list>()) {
        auto row=h.cast<py::dict>();
        if (row.contains("brep_edge_id") && row["brep_edge_id"].cast<std::int64_t>()==edge_id) { edge=row; edge_found=true; break; }
    }
    if (!edge_found || !edge.contains("canonical_endpoints")) return refuse("selected_edge_not_authoritative",requested);
    auto endpoints=edge["canonical_endpoints"].cast<py::sequence>();
    if (endpoints.size()!=2) return refuse("selected_edge_endpoints_invalid",requested);
    const auto wall0=endpoints[0].cast<std::int64_t>(), wall1=endpoints[1].cast<std::int64_t>();
    if (wall0<0||wall1<0||wall0>=positions.shape(0)||wall1>=positions.shape(0)||wall0==wall1)
        return refuse("selected_edge_endpoint_out_of_range",requested);
    Tri source_face{}; bool face_found=false;
    if (evidence.contains("triangles")) for (py::handle h:evidence["triangles"].cast<py::list>()) {
        auto row=h.cast<py::dict>();
        if (row.contains("brep_face_id") && row["brep_face_id"].cast<std::int64_t>()==face_id) {
            auto v=row["canonical_vertices"].cast<py::sequence>();
            if (v.size()!=3) return refuse("source_triangle_invalid",requested);
            source_face={v[0].cast<std::int64_t>(),v[1].cast<std::int64_t>(),v[2].cast<std::int64_t>()};
            face_found=true; break;
        }
    }
    if (!face_found) return refuse("source_face_triangle_missing",requested);
    Point normal{0.,0.,0.}; bool normal_found=false;
    if (evidence.contains("direction_records")) for (py::handle h:evidence["direction_records"].cast<py::list>()) {
        auto row=h.cast<py::dict>();
        if (row.contains("face_id") && row["face_id"].cast<std::int64_t>()==face_id && row.contains("face_normal")) {
            auto v=row["face_normal"].cast<py::sequence>(); if(v.size()!=3) return refuse("source_normal_invalid",requested);
            normal={v[0].cast<double>(),v[1].cast<double>(),v[2].cast<double>()}; normal_found=true; break;
        }
    }
    if (!normal_found) return refuse("source_normal_missing",requested);
    std::vector<Point> points; points.reserve(static_cast<size_t>(positions.shape(0)));
    const auto* pd=positions.data(); for(py::ssize_t i=0;i<positions.shape(0);++i) points.push_back({pd[3*i],pd[3*i+1],pd[3*i+2]});
    std::vector<Tri> faces{source_face};
    const auto source_area=dot(cross(sub(points[source_face[1]],points[source_face[0]]),sub(points[source_face[2]],points[source_face[0]])),normal);
    if(std::abs(source_area)<=1e-14) return refuse("source_triangle_orientation_degenerate",requested);
    const int strip_sign=source_area>0. ? -1 : 1;
    py::list layer_rows; std::vector<std::int64_t> previous{wall0,wall1};
    std::map<std::int64_t,std::int64_t> generated_to_point;
    if (requested>0) {
        if (!optimizer.contains("generated_vertices") || !optimizer.contains("provenance")) return refuse("optimizer_geometry_missing",requested);
        for (py::handle h:optimizer["generated_vertices"].cast<py::list>()) {
            auto row=h.cast<py::dict>(); for(const char* k:{"id","layer","x","y","z"}) if(!row.contains(k)) return refuse("optimizer_vertex_record_incomplete",requested);
            auto id=row["id"].cast<std::int64_t>(); if(generated_to_point.contains(id)) return refuse("optimizer_vertex_id_duplicate",requested);
            generated_to_point[id]=static_cast<std::int64_t>(points.size());
            points.push_back({row["x"].cast<double>(),row["y"].cast<double>(),row["z"].cast<double>()});
        }
        if (static_cast<std::int64_t>(generated_to_point.size()) < requested*2) return refuse("optimizer_layer_vertex_count_incomplete",requested);
        std::vector<py::dict> rows;
        for(py::handle h:optimizer["provenance"].cast<py::list>()) {
            auto row=h.cast<py::dict>(); if(row.contains("source_wall_edge") && row["source_wall_edge"].cast<std::int64_t>()==edge_id) rows.push_back(row);
        }
        std::sort(rows.begin(),rows.end(),[](const py::dict&a,const py::dict&b){return a["layer"].cast<std::int64_t>()<b["layer"].cast<std::int64_t>();});
        if (static_cast<std::int64_t>(rows.size())!=requested) return refuse("optimizer_layer_provenance_incomplete",requested);
        for (const auto& row:rows) {
            const auto layer=row["layer"].cast<std::int64_t>(); auto gv=row["generated_vertices"].cast<py::sequence>();
            if(gv.size()!=2 || layer<1 || layer>requested) return refuse("optimizer_layer_record_invalid",requested);
            auto ga=generated_to_point.at(gv[0].cast<std::int64_t>()), gb=generated_to_point.at(gv[1].cast<std::int64_t>());
            Tri t0{previous[0],previous[1],gb}, t1{previous[0],gb,ga};
            auto area=dot(cross(sub(points[t0[1]],points[t0[0]]),sub(points[t0[2]],points[t0[0]])),normal);
            if(std::abs(area)<=1e-14) return refuse("generated_strip_orientation_degenerate",requested);
            if((area>0. ? 1 : -1)!=strip_sign) { std::swap(t0[0],t0[1]); std::swap(t1[0],t1[1]); }
            const auto final0=static_cast<std::int64_t>(faces.size()); faces.push_back(t0);
            const auto final1=static_cast<std::int64_t>(faces.size()); faces.push_back(t1);
            py::dict direct; direct["source_wall_edge"]=edge_id; direct["source_face"]="face-"+std::to_string(face_id); direct["side"]="wall"; direct["layer"]=layer;
            direct["wall0"]=wall0; direct["wall1"]=wall1; direct["front0"]=ga; direct["front1"]=gb;
            direct["final_face_ids"]=py::make_tuple(final0,final1);
            for(const char* k:{"patch","feature","physical_group","component","provenance"}) direct[k]=selected[k];
            direct["orientation"]="forward";
            layer_rows.append(direct); previous={ga,gb};
        }
    }
    py::dict source; source["source_wall_edge"]=edge_id; source["source_face"]=face_id; source["side"]="source"; source["layer"]=0;
    source["patch"]=selected["patch"]; source["feature"]=selected["feature"]; source["physical_group"]=selected["physical_group"]; source["component"]=selected["component"]; source["provenance"]=selected["provenance"];
    py::list source_rows; source_rows.append(source);
    py::dict ledger; ledger["source_face_id"]="face-"+std::to_string(face_id); ledger["source_edge"]="edge-"+std::to_string(edge_id);
    ledger["feature_id"]=selected["feature"]; ledger["patch_id"]=selected["patch"]; ledger["physical_group"]=selected["physical_group"]; ledger["component_id"]=selected["component"]; ledger["orientation"]="forward"; ledger["source_vertex_ids"]=py::make_tuple(source_face[0],source_face[1],source_face[2]); ledger["provenance"]=selected["provenance"];
    py::list ledgers; ledgers.append(ledger);
    py::dict binding; binding["source_face"]="face-"+std::to_string(face_id); binding["source_face_a"]=""; binding["source_face_b"]=""; binding["source_edge"]="edge-"+std::to_string(edge_id); binding["wall_edge"]="wall-"+std::to_string(edge_id); binding["bl_strip"]="brep-strip-"+std::to_string(edge_id); binding["output_boundary_face"]=text(selected,"output_face"); binding["volume_boundary_face"]="none"; binding["feature"]=selected["feature"]; binding["patch"]=selected["patch"]; binding["physical_group"]=selected["physical_group"]; binding["component"]=selected["component"]; binding["provenance"]=selected["provenance"]; binding["wall0"]=std::to_string(wall0); binding["wall1"]=std::to_string(wall1); binding["front0"]=std::to_string(requested?previous[0]:wall0); binding["front1"]=std::to_string(requested?previous[1]:wall1); binding["tangent_face"]="face-"+std::to_string(face_id); binding["first_strip_face"]=requested?"1":"0"; binding["orientation"]="forward"; py::list bindings; bindings.append(binding);
    py::dict result; result["accepted"]=true; result["status"]=requested?"actual_brep_surface_produced":"disabled_identity"; result["reason"]="canonical_brep_direct_surface_producer_passed"; result["points"]=as_points(points); result["triangles"]=as_triangles(faces); result["source_triangles"]=as_triangles(std::vector<Tri>{source_face}); result["source_provenance"]=source_rows; result["ledger"]=ledgers; result["boundary_binding"]=bindings; result["layer_records"]=layer_rows; result["source_edge"]=edge_id; result["source_face"]=face_id; result["wall_edge"]=py::make_tuple(wall0,wall1); result["face_normal"]=py::make_tuple(normal[0],normal[1],normal[2]); result["actual_layers"]=requested; result["runtime_route"]="default_off"; result["publication_eligible"]=false; result["candidate_discarded"]=false; result["direct_lineage"]=true; return result;
}

PYBIND11_MODULE(native_surface_bl_front_actual_v2_producer,m) {
    m.doc()="Private C++23 actual BRepFrontEvidence/v2 surface wall-edge producer";
    m.def("produce_actual_brep_wall_strip_v1",&produce,py::arg("canonical_positions"),py::arg("evidence"),py::arg("explicit_mapping"),py::arg("optimizer_receipt"),py::arg("requested_layers"));
}
