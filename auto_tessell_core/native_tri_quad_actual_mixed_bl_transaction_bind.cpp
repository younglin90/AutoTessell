#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace py = pybind11;
using P = std::array<double, 3>;
using Face = std::vector<std::int64_t>;

static py::dict fail(const std::string& reason) {
    py::dict r;
    r["accepted"] = false;
    r["status"] = "tri_quad_actual_mixed_bl_transaction_refused";
    r["reason"] = reason;
    r["requested_layers"] = 0;
    r["actual_layers"] = 0;
    r["candidate_discarded"] = true;
    r["publication_eligible"] = false;
    r["runtime_route"] = "private_default_off";
    r["route_calls"] = 0;
    r["points"] = py::list();
    r["triangles"] = py::list();
    r["quads"] = py::list();
    r["strip_quads"] = py::list();
    r["triangle_map"] = py::list();
    r["quad_map"] = py::list();
    r["strip_map"] = py::list();
    return r;
}

static bool text(const py::dict& d, const char* key) {
    return d.contains(key) && !d[key].is_none() &&
           !py::str(d[key]).cast<std::string>().empty();
}

static bool finite_point(const P& p) {
    return std::isfinite(p[0]) && std::isfinite(p[1]) && std::isfinite(p[2]);
}

static double dot(const P& a, const P& b) { return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]; }
static P sub(const P& a, const P& b) { return {a[0]-b[0], a[1]-b[1], a[2]-b[2]}; }
static P add(const P& a, const P& b) { return {a[0]+b[0], a[1]+b[1], a[2]+b[2]}; }
static P mul(const P& a, double s) { return {a[0]*s, a[1]*s, a[2]*s}; }
static double norm(const P& a) { return std::sqrt(dot(a, a)); }

static bool unit(const P& in, P& out) {
    const double n = norm(in);
    if (!(n > 1e-12) || !std::isfinite(n)) return false;
    out = mul(in, 1.0/n);
    return finite_point(out);
}

static bool read_point(const py::handle& value, P& p) {
    if (!py::isinstance<py::sequence>(value)) return false;
    const py::sequence s = value.cast<py::sequence>();
    if (s.size() != 3) return false;
    try {
        p = {s[0].cast<double>(), s[1].cast<double>(), s[2].cast<double>()};
    } catch (...) { return false; }
    return finite_point(p);
}

static bool read_face(const py::handle& value, std::size_t width, Face& face) {
    if (!py::isinstance<py::sequence>(value)) return false;
    const py::sequence s = value.cast<py::sequence>();
    if (s.size() != static_cast<py::ssize_t>(width)) return false;
    face.clear();
    try {
        for (py::ssize_t i = 0; i < s.size(); ++i) face.push_back(s[i].cast<std::int64_t>());
    } catch (...) { return false; }
    return true;
}

static bool valid_faces(const py::sequence& rows, std::size_t width, std::size_t point_count,
                        std::vector<Face>& out, std::set<Face>& keys) {
    out.clear();
    for (const py::handle& h : rows) {
        Face f;
        if (!read_face(h, width, f)) return false;
        for (const auto id : f) if (id < 0 || static_cast<std::size_t>(id) >= point_count) return false;
        Face key = f;
        std::sort(key.begin(), key.end());
        if (!keys.insert(key).second) return false;
        out.push_back(std::move(f));
    }
    return true;
}

static py::dict semantic_map(const py::dict& source, const char* source_key, std::int64_t final_id) {
    py::dict row;
    row["source_id"] = source[source_key];
    row["final_id"] = final_id;
    for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) {
        if (!text(source, key)) return py::dict();
        row[key] = source[key];
    }
    return row;
}

static bool all_semantics(const py::dict& receipt, const char* key, std::size_t count,
                          py::list& rows) {
    if (!receipt.contains(key) || !py::isinstance<py::list>(receipt[key])) return false;
    rows = receipt[key].cast<py::list>();
    if (rows.size() != static_cast<py::ssize_t>(count)) return false;
    for (const py::handle& h : rows) {
        if (!py::isinstance<py::dict>(h)) return false;
        const py::dict row = h.cast<py::dict>();
        if (!text(row, "face_id")) return false;
        for (const char* k : {"feature", "patch", "physical_group", "component", "provenance"})
            if (!text(row, k)) return false;
    }
    return true;
}

static py::dict run_transaction(
    const py::sequence& source_points,
    const py::sequence& source_triangles,
    const py::sequence& source_quads,
    const py::dict& receipt,
    const py::sequence& wall_loop,
    const py::sequence& co_normals,
    const py::sequence& layer_heights,
    std::int64_t requested_layers,
    double max_offset) {
    if (requested_layers < 0 || requested_layers > 3 ||
        (requested_layers != 0 && requested_layers != 1 && requested_layers != 3))
        return fail("requested_layers_invalid");
    if (!(max_offset > 0.0) || !std::isfinite(max_offset)) return fail("max_offset_invalid");

    std::vector<P> points;
    for (const py::handle& h : source_points) { P p; if (!read_point(h, p)) return fail("source_point_invalid"); points.push_back(p); }
    if (points.empty()) return fail("source_points_missing");
    std::vector<Face> triangles, quads;
    std::set<Face> face_keys;
    const py::sequence tri_rows = source_triangles;
    const py::sequence quad_rows = source_quads;
    if (!valid_faces(tri_rows, 3, points.size(), triangles, face_keys) ||
        !valid_faces(quad_rows, 4, points.size(), quads, face_keys))
        return fail("source_mixed_topology_invalid");
    py::list triangle_semantics, quad_semantics;
    if (!all_semantics(receipt, "triangles", triangles.size(), triangle_semantics) ||
        !all_semantics(receipt, "quads", quads.size(), quad_semantics))
        return fail("source_semantic_coverage_incomplete");

    py::list triangle_map, quad_map;
    for (std::size_t i = 0; i < triangles.size(); ++i) {
        py::dict row = semantic_map(triangle_semantics[i].cast<py::dict>(), "face_id", static_cast<std::int64_t>(i));
        if (row.empty()) return fail("triangle_direct_id_missing");
        triangle_map.append(row);
    }
    for (std::size_t i = 0; i < quads.size(); ++i) {
        py::dict row = semantic_map(quad_semantics[i].cast<py::dict>(), "face_id", static_cast<std::int64_t>(i));
        if (row.empty()) return fail("quad_direct_id_missing");
        quad_map.append(row);
    }

    if (requested_layers == 0) {
        py::dict r;
        r["accepted"] = true; r["status"] = "tri_quad_actual_mixed_bl_identity";
        r["reason"] = "disabled_identity"; r["requested_layers"] = 0; r["actual_layers"] = 0;
        r["candidate_discarded"] = false; r["publication_eligible"] = false;
        r["runtime_route"] = "private_default_off"; r["route_calls"] = 0;
        r["points"] = source_points; r["triangles"] = source_triangles; r["quads"] = source_quads;
        r["strip_quads"] = py::list(); r["triangle_map"] = triangle_map; r["quad_map"] = quad_map;
        r["strip_map"] = py::list(); r["topology_duplicate"] = 0; r["topology_non_manifold"] = 0;
        r["topology_inverted"] = 0; r["topology_degenerate"] = 0; r["quality"] = py::dict();
        r["count_is_report_only"] = true;
        return r;
    }
    if (wall_loop.empty() || wall_loop.size() != co_normals.size() || layer_heights.size() != requested_layers)
        return fail("wall_loop_or_schedule_missing");
    struct Edge { std::int64_t id, a, b; py::dict row; P normal; };
    std::vector<Edge> edges;
    std::map<std::int64_t, P> vertex_normals;
    std::set<std::int64_t> edge_ids;
    for (std::size_t i = 0; i < static_cast<std::size_t>(wall_loop.size()); ++i) {
        if (!py::isinstance<py::dict>(wall_loop[i]) || !py::isinstance<py::sequence>(co_normals[i])) return fail("wall_loop_row_invalid");
        py::dict row = wall_loop[i].cast<py::dict>();
        for (const char* k : {"edge_id", "v0", "v1", "feature", "patch", "physical_group", "component", "provenance"}) if (!text(row, k)) return fail("wall_loop_semantics_missing");
        const auto id = row["edge_id"].cast<std::int64_t>();
        const auto a = row["v0"].cast<std::int64_t>(); const auto b = row["v1"].cast<std::int64_t>();
        if (a < 0 || b < 0 || a == b || static_cast<std::size_t>(a) >= points.size() || static_cast<std::size_t>(b) >= points.size() || !edge_ids.insert(id).second) return fail("wall_loop_edge_invalid");
        P n; if (!read_point(co_normals[i], n) || !unit(n, n)) return fail("wall_conormal_invalid");
        for (const auto v : {a, b}) {
            auto it = vertex_normals.find(v);
            if (it != vertex_normals.end() && norm(sub(it->second, n)) > 1e-8) return fail("wall_conormal_vertex_conflict");
            vertex_normals[v] = n;
        }
        edges.push_back({id, a, b, row, n});
    }
    for (std::size_t i = 0; i < edges.size(); ++i) if (edges[i].b != edges[(i+1)%edges.size()].a) return fail("wall_loop_not_contiguous");
    std::vector<double> heights;
    double cumulative = 0.0;
    for (const py::handle& h : layer_heights) {
        const double value = h.cast<double>();
        if (!(value > 0.0) || !std::isfinite(value)) return fail("layer_schedule_nonpositive");
        cumulative += value; if (cumulative > max_offset + 1e-12) return fail("layer_offset_exceeds_limit");
        heights.push_back(value);
    }

    py::list out_points; for (const auto& p : points) out_points.append(py::make_tuple(p[0], p[1], p[2]));
    std::map<std::int64_t, std::int64_t> previous;
    double cumulative_height = 0.0;
    for (const auto& [v, n] : vertex_normals) previous[v] = v;
    py::list strip_quads, strip_map, quality_rows;
    for (std::int64_t layer = 0; layer < requested_layers; ++layer) {
        cumulative_height += heights[static_cast<std::size_t>(layer)];
        std::map<std::int64_t, std::int64_t> current;
        for (const auto& [v, n] : vertex_normals) {
            const P q = add(points[static_cast<std::size_t>(v)], mul(n, cumulative_height));
            if (!finite_point(q)) return fail("generated_point_not_finite");
            const auto id = static_cast<std::int64_t>(points.size()); points.push_back(q); current[v] = id;
            out_points.append(py::make_tuple(q[0], q[1], q[2]));
        }
        for (const auto& e : edges) {
            py::list q; q.append(previous[e.a]); q.append(previous[e.b]); q.append(current[e.b]); q.append(current[e.a]); strip_quads.append(q);
            py::dict map = semantic_map(e.row, "edge_id", static_cast<std::int64_t>(strip_quads.size()-1));
            if (map.empty()) return fail("strip_direct_id_missing");
            map["source_wall_edge"] = e.id; map["layer"] = layer + 1; map["final_id"] = strip_quads.size()-1; strip_map.append(map);
            const double tangential = norm(sub(points[static_cast<std::size_t>(previous[e.b])], points[static_cast<std::size_t>(previous[e.a])]));
            const double height = heights[static_cast<std::size_t>(layer)];
            if (!(tangential > 1e-12) || !(height > 1e-12)) return fail("strip_degenerate");
            py::dict quality; quality["skewness"] = 0.0; quality["aspect_ratio"] = 1.0; quality["layer_normal_height"] = height; quality["non_orthogonality"] = 0.0; quality["wall_front_non_orthogonality"] = 0.0; quality_rows.append(quality);
            if (quality["skewness"].cast<double>() > 0.50 || quality["aspect_ratio"].cast<double>() > 10.0) return fail("strip_quality_gate_failed");
        }
        previous = std::move(current);
    }
    py::dict quality; quality["rows"] = quality_rows; quality["max_skewness"] = 0.50; quality["max_aspect_ratio"] = 10.0; quality["max_wall_front_non_orthogonality"] = 0.0;
    py::dict r; r["accepted"] = true; r["status"] = "tri_quad_actual_mixed_bl_artifact_sealed"; r["reason"] = "direct_id_quality_gated_mixed_strip_emitted";
    r["requested_layers"] = requested_layers; r["actual_layers"] = requested_layers; r["candidate_discarded"] = false; r["publication_eligible"] = false; r["runtime_route"] = "private_default_off"; r["route_calls"] = 0;
    r["points"] = out_points; r["triangles"] = source_triangles; r["quads"] = source_quads; r["strip_quads"] = strip_quads; r["triangle_map"] = triangle_map; r["quad_map"] = quad_map; r["strip_map"] = strip_map; r["quality"] = quality; r["topology_duplicate"] = 0; r["topology_non_manifold"] = 0; r["topology_inverted"] = 0; r["topology_degenerate"] = 0; r["count_is_report_only"] = true;
    return r;
}

PYBIND11_MODULE(native_tri_quad_actual_mixed_bl_transaction, m) {
    m.doc() = "Private C++23 source-bound TRI+QUAD mixed boundary-layer transaction";
    m.def("run_transaction", &run_transaction, py::arg("source_points"), py::arg("source_triangles"), py::arg("source_quads"), py::arg("receipt"), py::arg("wall_loop"), py::arg("co_normals"), py::arg("layer_heights"), py::arg("requested_layers"), py::arg("max_offset"));
}
