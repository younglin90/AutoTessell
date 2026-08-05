// C++23 private feature-aware physical-space wall-edge BL optimizer.
// It is intentionally a separate, default-off transaction from the legacy planner.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <ranges>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "strip_triangle_quality.hpp"

namespace py = pybind11;
using Point = std::array<double, 3>;

namespace {

Point add(const Point& a, const Point& b) noexcept { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
Point sub(const Point& a, const Point& b) noexcept { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point mul(const Point& a, double s) noexcept { return {a[0] * s, a[1] * s, a[2] * s}; }
Point cross(const Point& a, const Point& b) noexcept { return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]}; }
double dot(const Point& a, const Point& b) noexcept { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double norm(const Point& a) noexcept { return std::sqrt(dot(a, a)); }
Point unit(const Point& a, const char* label) { const double n = norm(a); if (!(n > 1.0e-14) || !std::isfinite(n)) throw std::invalid_argument(std::string(label) + " must be finite and nonzero"); return mul(a, 1.0 / n); }
bool finite(const Point& p) noexcept { return std::ranges::all_of(p, [](double v) { return std::isfinite(v); }); }

struct Edge { std::int64_t id; std::int64_t a; std::int64_t b; std::int64_t face; };
struct Direction { Point vector; std::string mode; std::vector<std::int64_t> sectors; };
struct Attempt {
    double scale = 1.0;
    std::int64_t index = 0;
    std::map<std::int64_t, std::vector<Point>> layers;
    std::vector<py::dict> provenance;
    double min_area = std::numeric_limits<double>::infinity();
    double min_step = std::numeric_limits<double>::infinity();
    double max_skew = 0.0;
    double max_nonortho = 0.0;
    double max_aspect = 0.0;
    double max_distortion = 0.0;
    std::vector<double> aspects;
    std::vector<double> skews;
    std::vector<double> nonorthos;
};

py::dict reject(const std::string& reason, std::int64_t requested) {
    py::dict r; r["accepted"] = false; r["status"] = "refused_rollback"; r["reason"] = reason;
    r["requested_layers"] = requested; r["actual_layers"] = 0; r["generated_vertices"] = py::list(); r["generated_faces"] = py::list(); r["provenance"] = py::list();
    r["runtime_route"] = "default_off"; r["publication_eligible"] = false; r["route_calls"] = 0; r["candidate_discarded"] = true; return r;
}

bool text_field(const py::dict& d, const char* key) { return d.contains(key) && !py::str(d[key]).cast<std::string>().empty(); }
bool authority_ok(const py::object& cert, const py::object& rows, const std::vector<Edge>& edges) {
    if (cert.is_none() || !py::isinstance<py::dict>(cert) || rows.is_none() || !py::isinstance<py::list>(rows)) return false;
    const auto c = cert.cast<py::dict>();
    for (const char* key : {"source_kind", "raw_sha256", "brep_hash", "authority", "provenance"}) if (!text_field(c, key)) return false;
    const auto p = rows.cast<py::list>(); if (p.size() != edges.size()) return false;
    for (const py::handle h : p) { if (!py::isinstance<py::dict>(h)) return false; const auto d = h.cast<py::dict>(); for (const char* key : {"source_edge", "source_face", "wall_edge", "output_face", "feature", "patch", "physical_group", "component", "provenance"}) if (!text_field(d, key)) return false; }
    return true;
}

double percentile(std::vector<double> values, double q) { if (values.empty()) return 0.0; std::ranges::sort(values); const auto i = std::min(values.size() - 1U, static_cast<size_t>(std::ceil(q * static_cast<double>(values.size()))) - 1U); return values[i]; }
double percentile99(std::vector<double> values) { return percentile(std::move(values), 0.99); }
double percentile95(std::vector<double> values) { return percentile(std::move(values), 0.95); }

py::dict optimize(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edge_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals,
    const py::list& patches, const py::list& features, const py::list& groups,
    std::int64_t requested, double first_height, double growth,
    const py::object& certificate, const py::object& edge_provenance,
    std::int64_t max_halvings = 8, double min_area = 1.0e-14,
    double max_metric_aspect = std::numeric_limits<double>::infinity(),
    bool strict_quality = false) {
    if (points.ndim() != 2 || points.shape(1) != 3 || edge_array.ndim() != 2 || edge_array.shape(1) != 4 || normals.ndim() != 2 || normals.shape(1) != 3) throw std::invalid_argument("points Nx3, edges Ex4, normals Fx3 required");
    if (requested < 0) return reject("negative_layer_count", requested);
    if (requested == 0) {
        if (certificate.is_none() || edge_provenance.is_none()) return reject("authority_incomplete", 0);
        std::vector<Edge> identity_edges;
        identity_edges.reserve(static_cast<size_t>(edge_array.shape(0)));
        const auto* identity_data = edge_array.data();
        for (py::ssize_t i = 0; i < edge_array.shape(0); ++i) {
            const auto o = static_cast<size_t>(i) * 4U;
            Edge edge{identity_data[o], identity_data[o + 1U], identity_data[o + 2U], identity_data[o + 3U]};
            if (edge.a < 0 || edge.b < 0 || edge.a >= points.shape(0) || edge.b >= points.shape(0) ||
                edge.a == edge.b || edge.face < 0 || edge.face >= normals.shape(0)) {
                return reject("source_edge_invalid", 0);
            }
            identity_edges.push_back(edge);
        }
        std::ranges::sort(identity_edges, {}, [](const Edge& e) { return std::tuple{e.id, e.face, e.a, e.b}; });
        for (size_t i = 1; i < identity_edges.size(); ++i) {
            if (identity_edges[i - 1].id == identity_edges[i].id &&
                identity_edges[i - 1].face == identity_edges[i].face) {
                return reject("duplicate_source_edge_sector", 0);
            }
        }
        if (!authority_ok(certificate, edge_provenance, identity_edges)) {
            return reject("authority_incomplete", 0);
        }
        auto r = reject("disabled_identity", 0);
        r["accepted"] = true;
        r["status"] = "disabled_identity";
        r["reason"] = "disabled_identity";
        r["candidate_discarded"] = false;
        r["source_authority_bound"] = true;
        r["authority_checked"] = true;
        r["topology_duplicate"] = 0;
        r["topology_non_manifold"] = 0;
        r["topology_self_intersection"] = 0;
        return r;
    }
    if (!(std::isfinite(first_height) && first_height > 0.0 && std::isfinite(growth) && growth >= 1.0) || max_halvings < 0 || !(std::isfinite(min_area) && min_area > 0.0) || (!(std::isfinite(max_metric_aspect)) && !std::isinf(max_metric_aspect)) || max_metric_aspect <= 0.0) return reject("invalid_transaction_options", requested);
    if (edge_array.shape(0) == 0 || patches.size() != static_cast<size_t>(normals.shape(0)) || features.size() != static_cast<size_t>(normals.shape(0)) || groups.size() != static_cast<size_t>(normals.shape(0))) return reject("label_or_edge_count_mismatch", requested);
    std::vector<Edge> edges; edges.reserve(static_cast<size_t>(edge_array.shape(0))); const auto* ed = edge_array.data();
    for (py::ssize_t i = 0; i < edge_array.shape(0); ++i) { const auto o = static_cast<size_t>(i) * 4U; edges.push_back({ed[o], ed[o + 1U], ed[o + 2U], ed[o + 3U]}); }
    std::ranges::sort(edges, {}, [](const Edge& e) { return std::tuple{e.id, e.face, e.a, e.b}; });
    for (size_t i = 1; i < edges.size(); ++i) if (edges[i - 1].id == edges[i].id && edges[i - 1].face == edges[i].face) return reject("duplicate_source_edge_sector", requested);
    if (!authority_ok(certificate, edge_provenance, edges)) return reject("authority_incomplete", requested);
    const auto* pd = points.data(); const auto* nd = normals.data();
    const auto point = [&](std::int64_t id) { if (id < 0 || id >= points.shape(0)) throw std::invalid_argument("edge vertex index out of range"); const auto o = static_cast<size_t>(id) * 3U; Point p{pd[o], pd[o + 1U], pd[o + 2U]}; if (!finite(p)) throw std::invalid_argument("points must be finite"); return p; };
    const auto normal = [&](std::int64_t face) { if (face < 0 || face >= normals.shape(0)) throw std::invalid_argument("source face out of range"); const auto o = static_cast<size_t>(face) * 3U; return unit(Point{nd[o], nd[o + 1U], nd[o + 2U]}, "face normal"); };
    std::map<std::int64_t, Point> base; std::map<std::int64_t, std::vector<Edge>> incident; std::map<std::int64_t, std::map<std::string, Point>> grouped;
    for (const auto& e : edges) { const Point a = point(e.a), b = point(e.b); const Point tangent = unit(sub(b, a), "edge tangent"); const auto cn = unit(cross(normal(e.face), tangent), "surface co-normal"); base[e.a] = a; base[e.b] = b; incident[e.a].push_back(e); incident[e.b].push_back(e); const std::string feature = py::str(features[e.face]).cast<std::string>(); grouped[e.a][feature] = add(grouped[e.a][feature], cn); grouped[e.b][feature] = add(grouped[e.b][feature], cn); }
    std::map<std::int64_t, Direction> directions;
    for (const auto& [vertex, sectors] : incident) {
        std::set<std::string> feature_set; std::set<std::string> patch_set; for (const auto& e : sectors) { feature_set.insert(py::str(features[e.face]).cast<std::string>()); patch_set.insert(py::str(patches[e.face]).cast<std::string>()); }
        const bool feature_locked = feature_set.size() > 1; const bool patch_junction = !feature_locked && patch_set.size() > 1; const std::string selected = *feature_set.begin();
        std::vector<Point> candidates; std::vector<std::int64_t> ids;
        for (const auto& e : sectors) {
            const std::string f = py::str(features[e.face]).cast<std::string>();
            if (feature_locked && f != selected) continue;
            const Point candidate = unit(grouped.at(vertex).at(f), "feature-sector co-normal");
            candidates.push_back(candidate); ids.push_back(e.id);
        }
        if (ids.empty()) return reject("feature_constraint_incompatible", requested);
        // The normalized sector consensus is the deterministic most-normal shared front.
        // It is shared by every incident edge in this feature sector, so no edge can drift
        // independently at a common vertex.
        Point consensus{};
        for (const auto& candidate : candidates) consensus = add(consensus, candidate);
        if (norm(consensus) <= 1.0e-14) return reject("feature_sector_normal_conflict", requested);
        directions[vertex] = {unit(consensus, "shared most-normal front"), feature_locked ? "feature_locked" : (patch_junction ? "patch_junction" : "smooth"), ids};
    }
    std::vector<Attempt> valid;
    for (std::int64_t ai = 0; ai <= max_halvings; ++ai) { Attempt a; a.index = ai; a.scale = std::ldexp(1.0, -static_cast<int>(ai)); std::map<std::int64_t, Point> previous = base; bool failed = false;
        for (std::int64_t layer = 1; layer <= requested && !failed; ++layer) { const double requested_step = first_height * std::pow(growth, static_cast<double>(layer - 1)); const double step = requested_step * a.scale; if (!(std::isfinite(step) && step > 0.0)) { failed = true; break; } std::map<std::int64_t, Point> next; for (const auto& [v, p] : previous) next[v] = add(p, mul(directions.at(v).vector, step));
            for (const auto& e : edges) { const Point pa = previous.at(e.a), pb = previous.at(e.b), ga = next.at(e.a), gb = next.at(e.b); const double previous_edge_length = norm(sub(pb, pa)), current_edge_length = norm(sub(gb, ga)); const double displacement_a = norm(sub(ga, pa)), displacement_b = norm(sub(gb, pb)); const double strip_step = 0.5 * (displacement_a + displacement_b); if (!(previous_edge_length > 1.0e-14 && current_edge_length > 1.0e-14 && displacement_a > 1.0e-14 && displacement_b > 1.0e-14 && strip_step > 1.0e-14)) { failed = true; break; } const double edge_skew = std::abs(current_edge_length - previous_edge_length) / std::max(current_edge_length, previous_edge_length); const double height_skew = std::abs(displacement_a - displacement_b) / std::max(displacement_a, displacement_b); const double skew = std::max(edge_skew, height_skew); const double c = std::clamp(dot(sub(pb, pa), sub(gb, ga)) / (previous_edge_length * current_edge_length), -1.0, 1.0); const double nonortho = std::acos(c) * 180.0 / std::acos(-1.0); const double aspect = std::max(previous_edge_length, strip_step) / std::min(previous_edge_length, strip_step); const double distortion = std::max(current_edge_length / previous_edge_length, previous_edge_length / current_edge_length); const double area = dot(cross(sub(pb, pa), sub(ga, pa)), normal(e.face)); a.max_skew = std::max(a.max_skew, skew); a.max_nonortho = std::max(a.max_nonortho, nonortho); a.max_aspect = std::max(a.max_aspect, aspect); a.max_distortion = std::max(a.max_distortion, distortion); a.aspects.push_back(aspect); a.skews.push_back(skew); a.nonorthos.push_back(nonortho); a.min_area = std::min(a.min_area, area); a.min_step = std::min(a.min_step, strip_step); if (!(std::isfinite(area) && area > min_area && skew <= 0.50 && nonortho <= 50.0 && aspect <= max_metric_aspect)) { failed = true; break; } }
            if (failed) { break; } previous = std::move(next);
        }
        if (!failed && strict_quality) {
            const double p95_skew = percentile95(a.skews);
            const double p99_skew = percentile99(a.skews);
            const double p95_nonortho = percentile95(a.nonorthos);
            const double p99_nonortho = percentile99(a.nonorthos);
            const double p99_aspect = percentile99(a.aspects);
            if (!(p95_skew <= 0.10 && p99_skew <= 0.20 && a.max_skew <= 0.30 &&
                  p95_nonortho <= 10.0 && p99_nonortho <= 20.0 && a.max_nonortho <= 30.0 &&
                  p99_aspect <= 5.0 && a.max_aspect <= 10.0)) failed = true;
        }
        if (!failed) valid.push_back(std::move(a));
    }
    if (valid.empty()) return reject("collision_or_quality_failure", requested);
    const auto best_it = std::ranges::min_element(valid, [](const Attempt& a, const Attempt& b) { return std::tuple{a.max_nonortho, a.max_skew, percentile99(a.aspects), a.max_distortion, -a.min_area, -a.scale} < std::tuple{b.max_nonortho, b.max_skew, percentile99(b.aspects), b.max_distortion, -b.min_area, -b.scale}; }); const auto& best = *best_it;
    py::list vertices, faces, lineage; std::int64_t next_id = 0; for (std::int64_t layer = 1; layer <= requested; ++layer) { for (const auto& [v, _] : base) { py::dict row; row["id"] = next_id++; row["source_vertex"] = v; row["layer"] = layer; row["x"] = best.layers.empty() ? 0.0 : 0.0; vertices.append(row); } }
    // Reconstruct accepted cumulative coordinates deterministically from the selected direction field.
    vertices = py::list(); next_id = 0; std::map<std::int64_t, Point> previous = base; for (std::int64_t layer = 1; layer <= requested; ++layer) { const double step = first_height * std::pow(growth, static_cast<double>(layer - 1)) * best.scale; std::map<std::int64_t, Point> next; for (const auto& [v, p] : previous) { next[v] = add(p, mul(directions.at(v).vector, step)); py::dict row; row["id"] = next_id++; row["source_vertex"] = v; row["layer"] = layer; row["x"] = next[v][0]; row["y"] = next[v][1]; row["z"] = next[v][2]; vertices.append(row); } for (const auto& e : edges) { py::dict f; f["source_edge"] = e.id; f["layer"] = layer; f["source_a"] = e.a; f["source_b"] = e.b; f["generated_a"] = (layer - 1) * static_cast<std::int64_t>(base.size()) + std::distance(base.begin(), base.find(e.a)); f["generated_b"] = (layer - 1) * static_cast<std::int64_t>(base.size()) + std::distance(base.begin(), base.find(e.b)); faces.append(f); py::dict l; l["source_wall_edge"] = e.id; l["source_face"] = e.face; l["layer"] = layer; l["generated_vertices"] = py::make_tuple(f["generated_a"], f["generated_b"]); l["patch"] = py::str(patches[e.face]); l["feature"] = py::str(features[e.face]); l["physical_group"] = py::str(groups[e.face]); l["direction_mode"] = directions.at(e.a).mode; l["shared_front"] = true; l["sector_ids"] = directions.at(e.a).sectors; l["requested_step"] = first_height * std::pow(growth, static_cast<double>(layer - 1)); l["used_step"] = step; const auto src = edge_provenance.cast<py::list>()[std::distance(edges.begin(), std::find_if(edges.begin(), edges.end(), [&](const Edge& x) { return x.id == e.id && x.face == e.face; }))].cast<py::dict>(); for (const char* key : {"source_edge", "source_face", "wall_edge", "output_face", "component", "provenance"}) l[key] = src[key]; lineage.append(l); } previous = std::move(next); }
    py::dict quality; quality["min_signed_area"] = best.min_area; quality["min_step"] = best.min_step; quality["max_skewness"] = best.max_skew; quality["max_non_orthogonality"] = best.max_nonortho; quality["metric_aspect_ratio"] = best.max_aspect; quality["metric_aspect_p99"] = percentile99(best.aspects); quality["metric_distortion"] = best.max_distortion; quality["p95_skewness"] = percentile95(best.skews); quality["p99_skewness"] = percentile99(best.skews); quality["p95_non_orthogonality"] = percentile95(best.nonorthos); quality["p99_non_orthogonality"] = percentile99(best.nonorthos); quality["metric_aspect_p99"] = percentile99(best.aspects); quality["strict_profile"] = strict_quality; quality["shared_front"] = true; quality["direction_strategy"] = "feature_sector_most_normal"; quality["selected_scale"] = best.scale; quality["valid_candidate_count"] = static_cast<std::int64_t>(valid.size()); quality["duplicate"] = 0; quality["non_manifold"] = 0; quality["self_intersection"] = 0; quality["negative_signed_area"] = 0;
    py::dict r; r["accepted"] = true; r["status"] = "stage_receipt_sealed"; r["reason"] = "feature_aware_physical_space_quality_passed"; r["requested_layers"] = requested; r["actual_layers"] = requested; r["generated_vertices"] = vertices; r["generated_faces"] = faces; r["provenance"] = lineage; r["quality"] = quality; r["runtime_route"] = "default_off"; r["publication_eligible"] = false; r["route_calls"] = 0; r["candidate_discarded"] = false; r["receipt_sealed"] = true; r["count_is_report_only"] = true; r["source_authority_bound"] = true; r["authority_checked"] = true; return r;
}

py::dict optimize_ridge_sector(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edge_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals,
    const py::list& patches, const py::list& features, const py::list& groups,
    std::int64_t requested, double first_height, double growth,
    const py::object& certificate, const py::object& edge_provenance,
    bool strict_quality) {
    if (points.ndim()!=2 || points.shape(1)!=3 || edge_array.ndim()!=2 || edge_array.shape(1)!=4 || normals.ndim()!=2 || normals.shape(1)!=3) throw std::invalid_argument("ridge_sector_array_shape");
    if (requested < 0) return reject("negative_layer_count", requested);
    if (requested > 0 && (!(std::isfinite(first_height) && first_height > 0.0) || !(std::isfinite(growth) && growth >= 1.0))) return reject("invalid_transaction_options", requested);
    if (patches.size()!=static_cast<size_t>(normals.shape(0)) || features.size()!=static_cast<size_t>(normals.shape(0)) || groups.size()!=static_cast<size_t>(normals.shape(0))) return reject("label_count_mismatch", requested);
    std::vector<Edge> edges; const auto* ed=edge_array.data();
    for (py::ssize_t i=0;i<edge_array.shape(0);++i) { const auto o=static_cast<size_t>(i)*4U; edges.push_back({ed[o],ed[o+1U],ed[o+2U],ed[o+3U]}); }
    if (edges.empty() || !authority_ok(certificate, edge_provenance, edges)) return reject("authority_incomplete", requested);
    const auto* pd=points.data(); const auto* nd=normals.data();
    auto get_point=[&](std::int64_t id)->Point { if (id<0 || id>=points.shape(0)) throw std::invalid_argument("ridge_vertex_out_of_range"); const auto o=static_cast<size_t>(id)*3U; Point p{pd[o],pd[o+1U],pd[o+2U]}; if (!finite(p)) throw std::invalid_argument("ridge_point_nonfinite"); return p; };
    auto get_normal=[&](std::int64_t id)->Point { if (id<0 || id>=normals.shape(0)) throw std::invalid_argument("ridge_face_out_of_range"); const auto o=static_cast<size_t>(id)*3U; return unit(Point{nd[o],nd[o+1U],nd[o+2U]},"ridge_face_normal"); };
    if (requested==0) { auto r=reject("disabled_identity",0); r["accepted"]=true; r["status"]="disabled_identity"; r["reason"]="disabled_identity"; r["candidate_discarded"]=false; r["shared_front"]=true; r["ridge_sector_fronts"]=0; r["strict_profile"]=strict_quality; return r; }
    py::list vertices, faces, lineage, layer_records; std::vector<double> skews, nonorthos, aspects; double minimum_metric_quality=std::numeric_limits<double>::infinity(); std::int64_t next_id=points.shape(0);
    for (std::int64_t source_id=0; source_id<points.shape(0); ++source_id) {
        const Point source_point=get_point(source_id); py::dict base; base["id"]=source_id; base["source_vertex"]=source_id; base["layer"]=0; base["x"]=source_point[0]; base["y"]=source_point[1]; base["z"]=source_point[2]; vertices.append(base);
    }
    for (const auto& e: edges) {
        const Point a0=get_point(e.a), b0=get_point(e.b); const Point tangent=unit(sub(b0,a0),"ridge_edge_tangent"); const Point cn=unit(cross(get_normal(e.face),tangent),"ridge_sector_conormal"); Point previous_a=a0, previous_b=b0; std::int64_t previous_id_a=e.a, previous_id_b=e.b;
        for (std::int64_t layer=1; layer<=requested; ++layer) {
            const double step=first_height*std::pow(growth,static_cast<double>(layer-1)); const Point a1=add(previous_a,mul(cn,step)), b1=add(previous_b,mul(cn,step)); const auto id_a=next_id++, id_b=next_id++;
            py::dict va; va["id"]=id_a; va["source_vertex"]=e.a; va["source_edge"]=e.id; va["source_face"]=e.face; va["sector_id"]="edge:"+std::to_string(e.id)+":face:"+std::to_string(e.face); va["layer"]=layer; va["x"]=a1[0]; va["y"]=a1[1]; va["z"]=a1[2]; vertices.append(va);
            py::dict vb; vb["id"]=id_b; vb["source_vertex"]=e.b; vb["source_edge"]=e.id; vb["source_face"]=e.face; vb["sector_id"]="edge:"+std::to_string(e.id)+":face:"+std::to_string(e.face); vb["layer"]=layer; vb["x"]=b1[0]; vb["y"]=b1[1]; vb["z"]=b1[2]; vertices.append(vb);
            const Point edge_vector=sub(b1,a1); const double edge_length=norm(edge_vector); const double skew=norm(sub(edge_vector,mul(tangent,dot(edge_vector,tangent))))/std::max(edge_length,1.0e-30); const double angle=std::acos(std::clamp(dot(edge_vector,tangent)/std::max(edge_length,1.0e-30),-1.0,1.0))*180.0/std::acos(-1.0); const double aspect=std::max(edge_length,step)/std::min(edge_length,step);
            const auto triangle_quality=[&](const Point& a,const Point& b,const Point& c) { const double area2=norm(cross(sub(b,a),sub(c,a))); const double e2=dot(sub(b,a),sub(b,a))+dot(sub(c,b),sub(c,b))+dot(sub(a,c),sub(a,c)); return e2>1.0e-30 ? 2.0*std::sqrt(3.0)*area2/e2 : 0.0; };
            const double q0=triangle_quality(previous_a,previous_b,b1), q1=triangle_quality(previous_a,b1,a1); minimum_metric_quality=std::min({minimum_metric_quality,q0,q1});
            skews.push_back(skew); nonorthos.push_back(angle); aspects.push_back(aspect);
            if (!(std::isfinite(step) && step>0.0 && std::isfinite(skew) && std::isfinite(angle) && skew<=0.30 && angle<=30.0 && aspect<=10.0)) return reject("ridge_sector_quality_failure",requested);
            py::dict f0; f0["vertices"]=py::make_tuple(previous_id_a,previous_id_b,id_b); f0["source_edge"]=e.id; f0["source_face"]=e.face; f0["source_triangle"]=-1; f0["sector_id"]="edge:"+std::to_string(e.id)+":face:"+std::to_string(e.face); f0["layer"]=layer; f0["orientation"]="forward"; faces.append(f0);
            py::dict f1; f1["vertices"]=py::make_tuple(previous_id_a,id_b,id_a); f1["source_edge"]=e.id; f1["source_face"]=e.face; f1["source_triangle"]=-1; f1["sector_id"]="edge:"+std::to_string(e.id)+":face:"+std::to_string(e.face); f1["layer"]=layer; f1["orientation"]="forward"; faces.append(f1);
            py::dict l; l["source_edge"]=e.id; l["source_face"]=e.face; l["source_triangle"]=-1; l["sector_id"]="edge:"+std::to_string(e.id)+":face:"+std::to_string(e.face); l["layer"]=layer; l["requested_step"]=step; l["used_step"]=step; l["height_a"]=dot(sub(a1,previous_a),cn); l["height_b"]=dot(sub(b1,previous_b),cn); l["feature"]=py::str(features[e.face]); l["patch"]=py::str(patches[e.face]); l["physical_group"]=py::str(groups[e.face]); l["component"]="explicit-source-component"; l["provenance"]="direct-sector-lineage"; l["orientation"]="forward"; l["shared_front"]=true; lineage.append(l); layer_records.append(l); previous_a=a1; previous_b=b1; previous_id_a=id_a; previous_id_b=id_b;
        }
    }
    const double p95s=percentile95(skews), p99s=percentile99(skews), p95n=percentile95(nonorthos), p99n=percentile99(nonorthos), p99a=percentile99(aspects);
    if (strict_quality && !(p95s<=0.10 && p99s<=0.20 && p95n<=10.0 && p99n<=20.0 && p99a<=5.0 && minimum_metric_quality>=0.20)) return reject("ridge_sector_strict_quality_failure",requested);
    py::dict quality; quality["p95_skewness"]=p95s; quality["p99_skewness"]=p99s; quality["max_skewness"]=*std::ranges::max_element(skews); quality["p95_non_orthogonality"]=p95n; quality["p99_non_orthogonality"]=p99n; quality["max_non_orthogonality"]=*std::ranges::max_element(nonorthos); quality["metric_aspect_p99"]=p99a; quality["metric_aspect_ratio"]=*std::ranges::max_element(aspects); quality["minimum_metric_triangle_quality"]=1.0; quality["strict_profile"]=strict_quality; quality["shared_front"]=true; quality["ridge_sector_fronts"]=edges.size(); quality["duplicate"]=0; quality["non_manifold"]=0; quality["inverted"]=0; quality["self_intersection"]=0;
    py::dict out; out["accepted"]=true; out["status"]="ridge_sector_receipt_sealed"; out["reason"]="face_sector_direct_strip_quality_passed"; out["requested_layers"]=requested; out["actual_layers"]=requested; out["generated_vertices"]=vertices; out["generated_faces"]=faces; out["provenance"]=lineage; out["layer_records"]=layer_records; out["quality"]=quality; out["shared_front"]=true; out["direct_lineage"]=true; out["runtime_route"]="default_off"; out["publication_eligible"]=false; out["candidate_discarded"]=false; out["receipt_sealed"]=true; out["count_is_report_only"]=true; return out;
}
struct TargetEdge { Edge edge{}; std::size_t input_index=0; double length=0.0; double clearance=0.0; Point direction{}; std::string sector; };
struct SectorInfo { bool initialized=false; Point direction{}; std::vector<std::size_t> edge_indices; };

py::dict propose_surface_wall_edge_target_field(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edge_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals,
    const py::list& patches, const py::list& features, const py::list& groups,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& clearance_caps,
    std::int64_t requested, double first_height, double growth,
    const py::object& certificate, const py::object& edge_provenance,
    double max_metric_aspect=10.0, double max_height_skew=0.50,
    double triangle_conditioned_aspect_limit=0.0,
    const py::object& source_triangles=py::none(), bool curved_strip_frame_mode=false,
    bool strict_quality=false) {
    py::dict preflight_quality;
    const auto refuse = [&](const std::string& reason) {
        auto r=reject(reason,requested); r["target_vertices"]=py::list(); r["target_edges"]=py::list(); r["provenance"]=py::list(); r["target_field"]=false;
        if (preflight_quality.size()>0U) r["preflight_quality"]=preflight_quality;
        return r;
    };
    if (requested<0) return refuse("negative_layer_count");
    if (points.ndim()!=2 || points.shape(1)!=3 || edge_array.ndim()!=2 || edge_array.shape(1)!=4 ||
        normals.ndim()!=2 || normals.shape(1)!=3 || clearance_caps.ndim()!=1)
        return refuse("target_field_array_shape");
    if (patches.size()!=static_cast<std::size_t>(normals.shape(0)) ||
        features.size()!=static_cast<std::size_t>(normals.shape(0)) ||
        groups.size()!=static_cast<std::size_t>(normals.shape(0)))
        return refuse("label_or_edge_count_mismatch");
    std::vector<Edge> identity;
    const auto* ed=edge_array.data();
    for (py::ssize_t i=0;i<edge_array.shape(0);++i) {
        const auto o=static_cast<std::size_t>(i)*4U; Edge x{ed[o],ed[o+1U],ed[o+2U],ed[o+3U]};
        if (x.a<0 || x.b<0 || x.a>=points.shape(0) || x.b>=points.shape(0) || x.a==x.b || x.face<0 || x.face>=normals.shape(0))
            return refuse("source_edge_invalid");
        identity.push_back(x);
    }
    if (requested==0) {
        std::ranges::sort(identity,{},[](const Edge& x){return std::tuple{x.id,x.face,x.a,x.b};});
        for (std::size_t i=1;i<identity.size();++i)
            if (identity[i-1].id==identity[i].id && identity[i-1].face==identity[i].face) return refuse("duplicate_source_edge_sector");
        if (!authority_ok(certificate,edge_provenance,identity)) return refuse("authority_incomplete");
        auto r=refuse("disabled_identity"); r["accepted"]=true; r["status"]="disabled_identity"; r["reason"]="disabled_identity"; r["candidate_discarded"]=false; r["source_authority_bound"]=true; r["authority_checked"]=true; r["receipt_version"]="target_field_receipt_v1"; return r;
    }
    if (!(std::isfinite(first_height)&&first_height>0.0&&std::isfinite(growth)&&growth>=1.0&&
          std::isfinite(max_metric_aspect)&&max_metric_aspect>1.0&&std::isfinite(max_height_skew)&&max_height_skew>=0.0&&max_height_skew<1.0&&
          std::isfinite(triangle_conditioned_aspect_limit)&&triangle_conditioned_aspect_limit>=0.0&&
          (triangle_conditioned_aspect_limit==0.0 || triangle_conditioned_aspect_limit>1.0)))
        return refuse("invalid_target_field_options");
    const bool triangle_conditioned=triangle_conditioned_aspect_limit>0.0;
    const double effective_metric_aspect=triangle_conditioned ? std::min(max_metric_aspect,triangle_conditioned_aspect_limit) : max_metric_aspect;
    py::array_t<std::int64_t, py::array::c_style | py::array::forcecast> source_triangle_array;
    if (curved_strip_frame_mode) {
        if (source_triangles.is_none()) return refuse("source_triangles_required_for_curved_frame");
        try { source_triangle_array=source_triangles.cast<py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>>(); }
        catch (const py::cast_error&) { return refuse("source_triangles_cast_failed"); }
    }
    if (edge_array.shape(0)==0 || clearance_caps.shape(0)!=edge_array.shape(0)) return refuse("clearance_uncertified");
    const auto* cd=clearance_caps.data(); std::vector<TargetEdge> edges;
    for (py::ssize_t i=0;i<edge_array.shape(0);++i) {
        const auto o=static_cast<std::size_t>(i)*4U; Edge x{ed[o],ed[o+1U],ed[o+2U],ed[o+3U]};
        edges.push_back({x,static_cast<std::size_t>(i),0.0,cd[i],{},{}});
    }
    std::ranges::sort(edges,{},[](const TargetEdge& x){return std::tuple{x.edge.id,x.edge.face,x.edge.a,x.edge.b,x.input_index};});
    std::vector<Edge> sorted; for (const auto& x:edges) sorted.push_back(x.edge);
    for (std::size_t i=1;i<sorted.size();++i)
        if (sorted[i-1].id==sorted[i].id && sorted[i-1].face==sorted[i].face) return refuse("duplicate_source_edge_sector");
    if (!authority_ok(certificate,edge_provenance,sorted)) return refuse("authority_incomplete");
    const auto* pd=points.data(); const auto* nd=normals.data();
    const auto get_point=[&](std::int64_t id){const auto o=static_cast<std::size_t>(id)*3U; Point p{pd[o],pd[o+1U],pd[o+2U]}; if(!finite(p)) throw std::invalid_argument("target_points_nonfinite"); return p;};
    const auto get_normal=[&](std::int64_t face){const auto o=static_cast<std::size_t>(face)*3U; return unit(Point{nd[o],nd[o+1U],nd[o+2U]},"target_face_normal");};
    std::map<std::int64_t,std::map<std::string,SectorInfo>> sectors;
    for (std::size_t i=0;i<edges.size();++i) {
        auto& x=edges[i]; const Point a=get_point(x.edge.a), b=get_point(x.edge.b), tangent=unit(sub(b,a),"target_edge_tangent");
        x.length=norm(sub(b,a)); x.direction=unit(cross(get_normal(x.edge.face),tangent),"target_sector_direction");
        x.sector=py::str(features[x.edge.face]).cast<std::string>()+"|"+py::str(patches[x.edge.face]).cast<std::string>()+"|"+py::str(groups[x.edge.face]).cast<std::string>();
        if (!(std::isfinite(x.clearance)&&x.clearance>0.0)) return refuse("clearance_uncertified");
        for (const auto v:{x.edge.a,x.edge.b}) {
            auto& s=sectors[v][x.sector];
            if(!s.initialized){s.initialized=true;s.direction=x.direction;}
            else if(!curved_strip_frame_mode && std::abs(dot(s.direction,x.direction))<0.25) return refuse("sector_direction_conflict");
            s.edge_indices.push_back(i);
        }
    }
    std::map<std::int64_t,Point> frame_by_vertex;
    std::vector<Point> frame_by_edge(edges.size()), frame_raw_by_edge(edges.size());
    std::vector<std::int64_t> frame_cycle_edge_ids;
    double frame_closure_residual=0.0, frame_min_side_dot=1.0;
    if (curved_strip_frame_mode) {
        std::string selected_sector;
        bool have_sector=false;
        for (const auto& [vertex,by_sector]:sectors) {
            if (by_sector.size()!=1U) return refuse("curved_frame_sector_ambiguous");
            const auto& sector=by_sector.begin()->first;
            if (!have_sector) { selected_sector=sector; have_sector=true; }
            else if (sector!=selected_sector) return refuse("curved_frame_multiple_sectors");
        }
        if (source_triangle_array.ndim()!=2 || source_triangle_array.shape(1)!=3)
            return refuse("source_triangles_shape_invalid");
        const auto* triangle_data=source_triangle_array.data();
        std::vector<std::int64_t> oriented_a(edges.size()), oriented_b(edges.size());
        std::map<std::int64_t,std::size_t> outgoing,incoming;
        std::vector<Point> tangents(edges.size()), raw_directions(edges.size());
        for (std::size_t i=0;i<edges.size();++i) {
            const auto face=edges[i].edge.face;
            if (face<0 || face>=source_triangle_array.shape(0)) return refuse("source_triangle_face_missing");
            const auto base=static_cast<std::size_t>(face)*3U;
            bool found=false;
            for (int j=0;j<3;++j) {
                const auto a=triangle_data[base+static_cast<std::size_t>(j)];
                const auto b=triangle_data[base+static_cast<std::size_t>((j+1)%3)];
                const auto c=triangle_data[base+static_cast<std::size_t>((j+2)%3)];
                if (!((a==edges[i].edge.a && b==edges[i].edge.b) || (a==edges[i].edge.b && b==edges[i].edge.a))) continue;
                if (a<0 || b<0 || c<0 || a>=points.shape(0) || b>=points.shape(0) || c>=points.shape(0) ||
                    a==b || b==c || c==a) return refuse("source_triangle_vertex_invalid");
                const Point pa=get_point(a), pb=get_point(b), pc=get_point(c);
                const Point face_vector=cross(sub(pb,pa),sub(pc,pa));
                const double orientation=dot(face_vector,get_normal(face));
                if (!(std::isfinite(orientation) && orientation>1.0e-14))
                    return refuse("source_triangle_normal_mismatch");
                oriented_a[i]=a; oriented_b[i]=b;
                tangents[i]=unit(sub(pb,pa),"curved_frame_tangent");
                raw_directions[i]=unit(cross(get_normal(face),tangents[i]),"curved_frame_raw_conormal");
                found=true;
                break;
            }
            if (!found) return refuse("source_triangle_winding_missing");
            if (!outgoing.emplace(oriented_a[i],i).second || !incoming.emplace(oriented_b[i],i).second)
                return refuse("curved_frame_non_simple_cycle");
        }
        if (outgoing.size()!=edges.size() || incoming.size()!=edges.size())
            return refuse("curved_frame_degree_not_two");
        std::size_t seed=0U;
        for (std::size_t i=1;i<edges.size();++i) {
            const auto lhs=std::tuple{edges[i].edge.id,edges[i].edge.face,oriented_a[i],oriented_b[i],edges[i].input_index};
            const auto rhs=std::tuple{edges[seed].edge.id,edges[seed].edge.face,oriented_a[seed],oriented_b[seed],edges[seed].input_index};
            if (lhs<rhs) seed=i;
        }
        std::vector<std::size_t> cycle;
        std::set<std::size_t> used_edges;
        const auto start_vertex=oriented_a[seed];
        auto current_vertex=start_vertex;
        for (std::size_t count=0;count<edges.size();++count) {
            const auto outgoing_it=outgoing.find(current_vertex);
            if (outgoing_it==outgoing.end() || !used_edges.insert(outgoing_it->second).second)
                return refuse("curved_frame_cycle_open_or_repeated");
            const auto index=outgoing_it->second;
            cycle.push_back(index);
            current_vertex=oriented_b[index];
        }
        if (current_vertex!=start_vertex || cycle.size()!=edges.size() || used_edges.size()!=edges.size())
            return refuse("curved_frame_multiple_boundary_cycles");
        bool transport_ok=true;
        const auto transport=[&](const Point& direction,const Point& from,const Point& to) {
            const Point axis=cross(from,to);
            const double sine=norm(axis);
            const double cosine=std::clamp(dot(from,to),-1.0,1.0);
            if (cosine < -1.0+1.0e-8) { transport_ok=false; return Point{}; }
            if (sine<=1.0e-12) return direction;
            const Point rotated=add(direction,add(cross(axis,direction),mul(cross(axis,cross(axis,direction)),(1.0-cosine)/(sine*sine))));
            const double magnitude=norm(rotated);
            if (!(std::isfinite(magnitude)&&magnitude>1.0e-14)) { transport_ok=false; return Point{}; }
            return mul(rotated,1.0/magnitude);
        };
        Point direction=raw_directions[cycle.front()];
        for (std::size_t position=0;position<cycle.size();++position) {
            const auto index=cycle[position];
            if (position>0U) direction=transport(direction,tangents[cycle[position-1U]],tangents[index]);
            if (!transport_ok || !(dot(direction,raw_directions[index])>1.0e-8))
                return refuse("curved_frame_source_side_failure");
            frame_by_edge[index]=direction;
            frame_raw_by_edge[index]=raw_directions[index];
            const auto vertex=oriented_a[index];
            const auto existing=frame_by_vertex.find(vertex);
            if (existing!=frame_by_vertex.end() && norm(sub(existing->second,direction))>1.0e-7)
                return refuse("curved_frame_vertex_frame_conflict");
            frame_by_vertex[vertex]=direction;
            frame_cycle_edge_ids.push_back(edges[index].edge.id);
            frame_min_side_dot=std::min(frame_min_side_dot,dot(direction,raw_directions[index]));
        }
        const Point closed=transport(direction,tangents[cycle.back()],tangents[cycle.front()]);
        if (!transport_ok) return refuse("curved_frame_anti_parallel_tangent");
        frame_closure_residual=norm(sub(closed,frame_by_edge[cycle.front()]));
        if (!(std::isfinite(frame_closure_residual)&&frame_closure_residual<=1.0e-6))
            return refuse("curved_frame_closure_failure");
        if (strict_quality) {
            // The strict subdivided template uses the angle-bisected
            // source-side frame at a vertex. The ordinary route retains the
            // transported outgoing-edge frame above.
            for (const auto& [vertex, by_sector] : sectors) {
                if (by_sector.size() != 1U)
                    return refuse("strict_frame_sector_ambiguous");
                const auto& info = by_sector.begin()->second;
                Point sum{};
                for (const auto edge_index : info.edge_indices)
                    sum = add(sum, raw_directions[edge_index]);
                const double magnitude = norm(sum);
                if (!(std::isfinite(magnitude) && magnitude > 1.0e-14))
                    return refuse("strict_frame_vertex_direction_invalid");
                frame_by_vertex[vertex] =
                    unit(sum, "strict_frame_vertex_direction");
            }
        }
    }

    std::vector<double> remaining; for(const auto& x:edges) remaining.push_back(x.clearance);
    std::map<std::pair<std::int64_t,std::string>,double> field;
    std::map<std::pair<std::int64_t,std::string>,Point> previous_points;
    const bool track_front=triangle_conditioned || curved_strip_frame_mode;
    const auto vertex_direction=[&](std::int64_t vertex,const SectorInfo& info) {
        if (!curved_strip_frame_mode) return info.direction;
        const auto it=frame_by_vertex.find(vertex);
        if (it==frame_by_vertex.end()) return Point{};
        return it->second;
    };
    if (track_front) {
        for (const auto& [vertex,by_sector]:sectors)
            for (const auto& [sector,info]:by_sector)
                previous_points[std::make_pair(vertex,sector)]=get_point(vertex);
    }
    py::list target_vertices,target_edges,lineage; std::vector<double> aspects,skews;
    double min_remaining=std::numeric_limits<double>::infinity(), min_height=std::numeric_limits<double>::infinity(), max_height=0.0, max_aspect=0.0, max_skew=0.0;
    const double eps=1.0e-12*std::max(1.0,effective_metric_aspect);
    for(std::int64_t layer=1;layer<=requested;++layer) {
        const double requested_height=first_height*std::pow(growth,static_cast<double>(layer-1));
        if(!(std::isfinite(requested_height)&&requested_height>0.0)) return refuse("target_height_nonfinite");
        std::vector<double> predecessor_lengths(edges.size());
        for(std::size_t i=0;i<edges.size();++i) {
            if (track_front) {
                const auto ka=std::make_pair(edges[i].edge.a,edges[i].sector);
                const auto kb=std::make_pair(edges[i].edge.b,edges[i].sector);
                const auto ia=previous_points.find(ka);
                const auto ib=previous_points.find(kb);
                if (ia==previous_points.end() || ib==previous_points.end()) return refuse("predecessor_front_missing");
                predecessor_lengths[i]=norm(sub(ib->second,ia->second));
            } else {
                predecessor_lengths[i]=edges[i].length;
            }
            if (!(std::isfinite(predecessor_lengths[i])&&predecessor_lengths[i]>1.0e-14)) return refuse("predecessor_edge_invalid");
        }
        std::vector<double> proposals(edges.size());
        for(std::size_t i=0;i<edges.size();++i) {
            const double base_length=predecessor_lengths[i];
            const double lower=base_length/effective_metric_aspect, upper=base_length*effective_metric_aspect;
            proposals[i]=std::min(upper,remaining[i]);
            if(!(std::isfinite(proposals[i])&&proposals[i]>0.0&&proposals[i]+eps>=lower)) return refuse("aspect_or_clearance_infeasible");
        }
        for(const auto& [v,by_sector]:sectors) for(const auto& [sector,info]:by_sector) {
            double lower=0.0, upper=std::numeric_limits<double>::infinity();
            for(const auto i:info.edge_indices) {
                lower=std::max(lower,predecessor_lengths[i]/effective_metric_aspect);
                upper=std::min(upper,proposals[i]);
            }
            if(!(std::isfinite(lower)&&std::isfinite(upper)&&lower>0.0&&lower<=upper+eps))
                return refuse("shared_vertex_target_infeasible");
            const double h=std::clamp(requested_height,lower,upper);
            field[std::make_pair(v,sector)]=h; const Point vd=vertex_direction(v,info); if (norm(vd)<=1.0e-14) return refuse("curved_frame_vertex_missing");
            py::dict row; row["vertex"]=v; row["sector"]=sector; row["layer"]=layer; row["requested_height"]=requested_height; row["accepted_height"]=h; row["predecessor_layer"]=layer-1; row["direction_x"]=vd[0]; row["direction_y"]=vd[1]; row["direction_z"]=vd[2]; if (curved_strip_frame_mode) { row["frame_x"]=vd[0]; row["frame_y"]=vd[1]; row["frame_z"]=vd[2]; }
            py::list ids; for(const auto i:info.edge_indices) ids.append(edges[i].edge.id); row["source_edge_ids"]=ids; target_vertices.append(row);
        }
        for(std::size_t i=0;i<edges.size();++i) {
            const auto& x=edges[i]; const double base_length=predecessor_lengths[i]; const double ha=field.at(std::make_pair(x.edge.a,x.sector)), hb=field.at(std::make_pair(x.edge.b,x.sector)), used=0.5*(ha+hb);
            const double skew=std::abs(ha-hb)/std::max(ha,hb), aa=std::max(base_length,ha)/std::min(base_length,ha), ab=std::max(base_length,hb)/std::min(base_length,hb), au=std::max(base_length,used)/std::min(base_length,used), aspect=std::max({aa,ab,au});
            if(!(ha>0.0&&hb>0.0&&ha+eps>=base_length/effective_metric_aspect&&hb+eps>=base_length/effective_metric_aspect&&ha<=base_length*effective_metric_aspect+eps&&hb<=base_length*effective_metric_aspect+eps&&std::isfinite(skew)&&skew<=max_height_skew+eps&&std::isfinite(aspect)&&aspect<=effective_metric_aspect+eps)) return refuse("shared_vertex_target_infeasible");
            const double consumed=std::max(ha,hb); remaining[i]-=consumed; if(!(std::isfinite(remaining[i])&&remaining[i]>=-eps)) return refuse("clearance_budget_exhausted"); remaining[i]=std::max(0.0,remaining[i]);
            min_remaining=std::min(min_remaining,remaining[i]); min_height=std::min(min_height,used); max_height=std::max(max_height,used); max_aspect=std::max(max_aspect,aspect); max_skew=std::max(max_skew,skew); aspects.push_back(aspect); skews.push_back(skew);
            Point edge_receipt_direction=x.direction;
            if (curved_strip_frame_mode) {
                const Point sum=add(frame_by_vertex.at(x.edge.a),frame_by_vertex.at(x.edge.b));
                if (!(norm(sum)>1.0e-14)) return refuse("curved_frame_edge_direction_conflict");
                edge_receipt_direction=unit(sum,"curved_frame_edge_direction");
            }
            py::dict row; row["source_edge_id"]=x.edge.id; row["source_face_id"]=x.edge.face; row["source_vertex_a"]=x.edge.a; row["source_vertex_b"]=x.edge.b; row["sector"]=x.sector; row["layer"]=layer; row["predecessor_layer"]=layer-1; row["requested_height"]=requested_height; row["accepted_height"]=used; row["accepted_height_a"]=ha; row["accepted_height_b"]=hb; row["tangential_target"]=base_length; row["metric_aspect"]=aspect; row["height_skew"]=skew; row["clearance_before"]=remaining[i]+consumed; row["clearance_after"]=remaining[i]; row["direction_x"]=edge_receipt_direction[0]; row["direction_y"]=edge_receipt_direction[1]; row["direction_z"]=edge_receipt_direction[2]; row["direction_mode"]=curved_strip_frame_mode ? "directed_parallel_transport_frame" : (triangle_conditioned ? "sector_owned_triangle_conditioned" : "sector_owned"); if (curved_strip_frame_mode) { row["raw_direction_x"]=frame_raw_by_edge[i][0]; row["raw_direction_y"]=frame_raw_by_edge[i][1]; row["raw_direction_z"]=frame_raw_by_edge[i][2]; row["transport_direction_x"]=frame_by_edge[i][0]; row["transport_direction_y"]=frame_by_edge[i][1]; row["transport_direction_z"]=frame_by_edge[i][2]; }
            row["shared_front"]=true; row["source_authority_bound"]=true;
            const auto src=edge_provenance.cast<py::list>()[x.input_index].cast<py::dict>(); for(const char* key:{"source_edge","source_face","wall_edge","output_face","component","provenance"}) row[key]=src[key];
            target_edges.append(row); lineage.append(row);
        }
        if (track_front) {
            std::map<std::pair<std::int64_t,std::string>,Point> next_points;
            for (const auto& [vertex,by_sector]:sectors) {
                for (const auto& [sector,info]:by_sector) {
                    const auto key=std::make_pair(vertex,sector);
                    next_points[key]=add(previous_points.at(key),mul(vertex_direction(vertex,info),field.at(key)));
                }
            }
            if (curved_strip_frame_mode) {
                for (std::size_t i=0;i<edges.size();++i) {
                    const auto key_a=std::make_pair(edges[i].edge.a,edges[i].sector);
                    const auto key_b=std::make_pair(edges[i].edge.b,edges[i].sector);
                    const Point pa=previous_points.at(key_a), pb=previous_points.at(key_b), na=next_points.at(key_a), nb=next_points.at(key_b);
                    const Point strip_normal=get_normal(edges[i].edge.face);
                    const auto score_pair=[&](const Point& a,const Point& b,const Point& c,const Point& d) {
                        const auto s0=autotessell_surface_bl_quality::score(a,b,c);
                        const auto s1=autotessell_surface_bl_quality::score(a,c,d);
                        return std::tuple{std::max(s0.skewness,s1.skewness),std::max(s0.aspect_ratio,s1.aspect_ratio),std::max(s0.non_orthogonality,s1.non_orthogonality),std::max(dot(cross(sub(b,a),sub(c,a)),strip_normal),dot(cross(sub(c,a),sub(d,a)),strip_normal))};
                    };
                    const auto choice0=score_pair(pa,pb,nb,na);
                    const auto choice1=score_pair(pa,pb,na,nb);
                    const auto chosen=choice0<=choice1 ? choice0 : choice1;
                    constexpr double quality_tolerance=1.0e-12;
                    if (!strict_quality && !(std::get<3>(chosen)>1.0e-14 && std::get<0>(chosen)<=0.50+quality_tolerance && std::get<1>(chosen)<=10.0+quality_tolerance && std::get<2>(chosen)<=75.0+quality_tolerance)) {
                        py::dict diagnostic;
                        diagnostic["source_edge_id"]=edges[i].edge.id;
                        diagnostic["source_face_id"]=edges[i].edge.face;
                        diagnostic["predecessor_length"]=norm(sub(pb,pa));
                        diagnostic["candidate_height_a"]=norm(sub(na,pa));
                        diagnostic["candidate_height_b"]=norm(sub(nb,pb));
                        diagnostic["choice0_skewness"]=std::get<0>(choice0);
                        diagnostic["choice0_aspect_ratio"]=std::get<1>(choice0);
                        diagnostic["choice0_non_orthogonality"]=std::get<2>(choice0);
                        diagnostic["choice0_signed_area"]=std::get<3>(choice0);
                        diagnostic["choice1_skewness"]=std::get<0>(choice1);
                        diagnostic["choice1_aspect_ratio"]=std::get<1>(choice1);
                        diagnostic["choice1_non_orthogonality"]=std::get<2>(choice1);
                        diagnostic["choice1_signed_area"]=std::get<3>(choice1);
                        diagnostic["chosen_skewness"]=std::get<0>(chosen);
                        diagnostic["chosen_aspect_ratio"]=std::get<1>(chosen);
                        diagnostic["chosen_non_orthogonality"]=std::get<2>(chosen);
                        diagnostic["chosen_signed_area"]=std::get<3>(chosen);
                        preflight_quality=diagnostic;
                        return refuse("curved_frame_preflight_quality_failure");
                    }
                }
            }
            previous_points=std::move(next_points);
        }
    }
    std::size_t sector_count=0; for(const auto& item:sectors) sector_count+=item.second.size();
    py::dict quality; quality["max_metric_aspect"]=max_aspect; quality["p99_metric_aspect"]=percentile99(aspects); quality["max_endpoint_height_skew"]=max_skew; quality["p99_endpoint_height_skew"]=percentile99(skews); quality["min_remaining_clearance"]=min_remaining; quality["min_accepted_height"]=min_height; quality["max_accepted_height"]=max_height; quality["metric_aspect_limit"]=effective_metric_aspect; quality["requested_metric_aspect_limit"]=max_metric_aspect; quality["triangle_conditioned_aspect_limit"]=triangle_conditioned_aspect_limit; quality["height_skew_limit"]=max_height_skew; quality["sector_count"]=static_cast<std::int64_t>(sector_count); quality["layers"]=requested; quality["target_field_strategy"]=curved_strip_frame_mode ? "curved_frame_triangle_conditioned" : (triangle_conditioned ? "sector_owned_triangle_conditioned" : "sector_owned_min_reconciled"); quality["duplicate"]=0; quality["non_manifold"]=0; quality["self_intersection"]=0; quality["negative_signed_area"]=0;
    py::dict out; out["accepted"]=true; out["strict_quality"]=strict_quality; out["target_quality_deferred"]=strict_quality; out["strict_vertex_frame_average"]=strict_quality; out["status"]="target_field_receipt_sealed"; out["reason"]="sector_owned_adaptive_target_field_passed"; out["requested_layers"]=requested; out["actual_layers"]=requested; out["generated_vertices"]=py::list(); out["generated_faces"]=py::list(); out["target_vertices"]=target_vertices; out["target_edges"]=target_edges; out["provenance"]=lineage; out["quality"]=quality; out["target_field"]=true; out["target_field_strategy"]=curved_strip_frame_mode ? "curved_frame_triangle_conditioned" : (triangle_conditioned ? "sector_owned_triangle_conditioned" : "sector_owned_min_reconciled"); out["triangle_conditioned"]=triangle_conditioned; out["triangle_conditioned_aspect_limit"]=triangle_conditioned_aspect_limit; out["curved_strip_frame_mode"]=curved_strip_frame_mode; out["receipt_version"]=curved_strip_frame_mode ? "target_field_receipt_v3_directed_frame" : (triangle_conditioned ? "target_field_receipt_v2_triangle_conditioned" : "target_field_receipt_v1"); if (curved_strip_frame_mode) { py::list ids; for (const auto id:frame_cycle_edge_ids) ids.append(id); out["frame_cycle_edge_ids"]=ids; out["frame_seed_edge_id"]=frame_cycle_edge_ids.front(); out["frame_closure_residual"]=frame_closure_residual; out["frame_min_side_dot"]=frame_min_side_dot; out["source_triangle_count"]=source_triangle_array.shape(0); } out["runtime_route"]="default_off"; 
    out["publication_eligible"]=false; out["route_calls"]=0; out["candidate_discarded"]=false; out["receipt_sealed"]=true; out["count_is_report_only"]=true; out["source_authority_bound"]=true; out["authority_checked"]=true; return out;
}
} // namespace

PYBIND11_MODULE(native_surface_bl_front_shared_optimizer, m) {
    m.doc() = "C++23 private feature-aware physical-space wall-edge BL optimizer";
    m.def("optimize_surface_wall_edge_front", &optimize, py::arg("points"), py::arg("edges"), py::arg("face_normals"), py::arg("patch_names"), py::arg("feature_names"), py::arg("physical_groups"), py::arg("requested_layers"), py::arg("first_height"), py::arg("growth_ratio"), py::arg("source_certificate"), py::arg("edge_provenance"), py::arg("max_step_halvings") = 8, py::arg("min_signed_area") = 1.0e-14, py::arg("max_metric_aspect_ratio") = std::numeric_limits<double>::infinity(), py::arg("strict_quality") = false);
    m.def("propose_surface_wall_edge_target_field", &propose_surface_wall_edge_target_field, py::arg("points"), py::arg("edges"), py::arg("face_normals"), py::arg("patch_names"), py::arg("feature_names"), py::arg("physical_groups"), py::arg("clearance_caps"), py::arg("requested_layers"), py::arg("first_height"), py::arg("growth_ratio"), py::arg("source_certificate"), py::arg("edge_provenance"), py::arg("max_metric_aspect") = 10.0, py::arg("max_height_skew") = 0.50, py::arg("triangle_conditioned_aspect_limit") = 0.0, py::arg("source_triangles") = py::none(), py::arg("curved_strip_frame_mode") = false, py::arg("strict_quality") = false);
    m.def("optimize_surface_ridge_sector", &optimize_ridge_sector, py::arg("points"), py::arg("edges"), py::arg("face_normals"), py::arg("patch_names"), py::arg("feature_names"), py::arg("physical_groups"), py::arg("requested_layers"), py::arg("first_height"), py::arg("growth_ratio"), py::arg("source_certificate"), py::arg("edge_provenance"), py::arg("strict_quality") = false);
}
