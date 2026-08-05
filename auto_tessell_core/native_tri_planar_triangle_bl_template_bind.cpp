#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "native_tri_planar_triangle_bl_template.hpp"
#include "native_tri_wall_edge_bl_preflight.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace py = pybind11;
namespace auth = autotessell_native_tri_authority;
namespace edge = autotessell_native_tri_wall_edge;
namespace tpl = autotessell_native_tri_planar_template;

namespace {

struct Label {
    std::string feature, patch, group, component, provenance;
};
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
struct TemplateSpec {
    std::string schema, template_id, source_sha, edge_sha, preflight_digest;
    std::string issuer, key_id;
    std::int64_t face = -1;
    std::vector<std::string> wall_edge_ids;
    std::vector<std::int64_t> active_sector_faces;
    Label label;
};

py::dict refuse(const std::string& reason) {
    py::dict r;
    r["accepted"] = false;
    r["status"] = "native_tri_planar_triangle_bl_template_refused";
    r["reason"] = reason;
    r["requested_layers"] = 0;
    r["actual_layers"] = 0;
    r["writer_invoked"] = false;
    r["preflight_only"] = false;
    r["artifact_emitted"] = false;
    r["publication_eligible"] = false;
    r["release_eligible"] = false;
    r["candidate_discarded"] = true;
    r["atomic_rollback"] = true;
    r["runtime_route"] = "private_default_off";
    r["route_calls"] = 0;
    r["generated_vertices"] = py::list();
    r["generated_faces"] = py::list();
    r["output_vertices"] = py::list();
    r["output_faces"] = py::list();
    r["provenance"] = py::list();
    r["generated_provenance"] = py::list();
    r["quality_witness"] = py::list();
    r["wall_edge_ids"] = py::list();
    r["layer_heights"] = py::list();
    return r;
}
bool strv(const py::dict& d, const char* k, std::string& out) {
    if (!d.contains(k) || !py::isinstance<py::str>(d[k])) return false;
    out = d[k].cast<std::string>();
    return !out.empty();
}
bool i64v(const py::dict& d, const char* k, std::int64_t& out) {
    if (!d.contains(k) || py::isinstance<py::bool_>(d[k])) return false;
    try { out = d[k].cast<std::int64_t>(); return true; } catch (...) { return false; }
}
bool bv(const py::dict& d, const char* k, bool& out) {
    if (!d.contains(k) || !py::isinstance<py::bool_>(d[k])) return false;
    out = d[k].cast<bool>(); return true;
}
bool hex64(const std::string& s) {
    return s.size() == 64U && std::all_of(s.begin(), s.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    });
}
template<class T>
bool seq(const py::handle& h, std::vector<T>& out) {
    try { out = h.cast<std::vector<T>>(); return true; } catch (...) { return false; }
}
void field(std::ostringstream& s, const std::string& v) {
    s << v.size() << ':' << v << '|';
}
py::dict label_dict(const Label& l) {
    py::dict d;
    d["feature"] = l.feature;
    d["patch"] = l.patch;
    d["physical_group"] = l.group;
    d["component"] = l.component;
    d["provenance"] = l.provenance;
    return d;
}
std::string semantic_stream(const Source& s) {
    std::ostringstream out;
    out << "rows=" << s.faces.size() << '|';
    for (std::size_t i = 0; i < s.faces.size(); ++i) {
        const auto& f = s.faces[i];
        out << i << ':' << f[0] << ',' << f[1] << ',' << f[2] << '|';
        field(out, s.labels[i].feature);
        field(out, s.labels[i].patch);
        field(out, s.labels[i].group);
        field(out, s.labels[i].component);
        field(out, s.labels[i].provenance);
    }
    return out.str();
}
bool parse_source(const py::dict& input, Source& s, std::string& why) {
    py::dict c = input;
    if (input.contains("certificate")) {
        if (!py::isinstance<py::dict>(input["certificate"])) {
            why = "tri_planar_source_certificate_payload_invalid"; return false;
        }
        c = input["certificate"].cast<py::dict>();
    }
    std::string schema;
    if (!strv(c, "schema", schema) || schema != "NativeTriAuthorityCertificate/v2" ||
        !strv(c, "source_sha256", s.source_sha) || !hex64(s.source_sha) ||
        !strv(c, "semantic_ledger_sha256", s.semantic_sha) || !hex64(s.semantic_sha) ||
        !strv(c, "canonical_geometry_sha256", s.geometry_sha) || !hex64(s.geometry_sha) ||
        !strv(c, "certificate_sha256", s.certificate_sha) || !hex64(s.certificate_sha) ||
        !strv(c, "source_kind", s.source_kind) ||
        !strv(c, "issuer", s.issuer) || !strv(c, "key_id", s.key_id) ||
        !i64v(c, "source_byte_count", s.byte_count) || s.byte_count <= 0) {
        why = "tri_planar_source_certificate_fields_invalid"; return false;
    }
    try {
        s.points = c["canonical_points"].cast<std::vector<auth::Point>>();
        s.faces = c["canonical_triangles"].cast<std::vector<auth::Triangle>>();
    } catch (...) {
        why = "tri_planar_source_certificate_arrays_invalid"; return false;
    }
    if (s.points.empty() || s.faces.empty() || !c.contains("face_ledger")) {
        why = "tri_planar_source_certificate_arrays_empty"; return false;
    }
    try {
        const py::sequence records = c["face_ledger"].cast<py::sequence>();
        if (records.size() != s.faces.size()) {
            why = "tri_planar_source_face_ledger_coverage_incomplete"; return false;
        }
        s.labels.assign(s.faces.size(), {});
        std::vector<bool> seen(s.faces.size(), false);
        for (const py::handle& item : records) {
            const py::dict row = item.cast<py::dict>();
            std::int64_t id = -1, source_id = -2;
            std::vector<std::int64_t> vertices;
            Label l;
            if (!i64v(row, "face_id", id) || !i64v(row, "source_facet_id", source_id) ||
                id != source_id || id < 0 || static_cast<std::size_t>(id) >= s.faces.size() ||
                !row.contains("vertices") || !seq(row["vertices"], vertices) ||
                vertices.size() != 3U ||
                auth::Triangle{vertices[0], vertices[1], vertices[2]} !=
                    s.faces[static_cast<std::size_t>(id)] || seen[static_cast<std::size_t>(id)] ||
                !strv(row, "feature", l.feature) || !strv(row, "patch", l.patch) ||
                !strv(row, "physical_group", l.group) ||
                !strv(row, "component", l.component) ||
                !strv(row, "provenance", l.provenance)) {
                why = "tri_planar_source_face_binding_invalid"; return false;
            }
            s.labels[static_cast<std::size_t>(id)] = l;
            seen[static_cast<std::size_t>(id)] = true;
        }
        if (std::any_of(seen.begin(), seen.end(), [](bool v) { return !v; })) {
            why = "tri_planar_source_face_binding_incomplete"; return false;
        }
    } catch (...) {
        why = "tri_planar_source_face_ledger_invalid"; return false;
    }
    const auth::CanonicalSource canonical{s.points, s.faces, {}, {}, s.source_kind};
    if (auth::sha256_text(semantic_stream(s)) != s.semantic_sha) {
        why = "tri_planar_source_semantic_digest_mismatch"; return false;
    }
    if (auth::sha256_text(auth::canonical_geometry_stream(canonical)) != s.geometry_sha) {
        why = "tri_planar_source_geometry_digest_mismatch"; return false;
    }
    std::ostringstream cert;
    cert << "NativeTriAuthorityCertificate/v2|" << s.source_kind << '|' << s.source_sha
         << '|' << s.geometry_sha << '|' << s.semantic_sha << '|' << s.issuer << '|'
         << s.key_id;
    if (auth::sha256_text(cert.str()) != s.certificate_sha) {
        why = "tri_planar_source_certificate_digest_mismatch"; return false;
    }
    if (!c.contains("topology") || !py::isinstance<py::dict>(c["topology"])) {
        why = "tri_planar_source_topology_not_strict"; return false;
    }
    const py::dict topology = c["topology"].cast<py::dict>();
    bool strict = false, checked = false;
    if (!bv(topology, "strict_zero", strict) || !strict ||
        !bv(topology, "self_intersection_checked", checked) || !checked) {
        why = "tri_planar_source_topology_not_strict"; return false;
    }
    for (const char* key : {"duplicate", "non_manifold", "open_edges", "degenerate",
                            "inverted", "self_intersection"}) {
        std::int64_t count = -1;
        if (!i64v(topology, key, count) || count != 0) {
            why = "tri_planar_source_topology_not_strict"; return false;
        }
    }
    bool authoritative = false, inferred_groups = true, inferred_features = true;
    std::string canonicalization;
    if (!bv(c, "source_provenance_authoritative", authoritative) || !authoritative ||
        !bv(c, "physical_groups_inferred", inferred_groups) || inferred_groups ||
        !bv(c, "feature_ids_inferred", inferred_features) || inferred_features ||
        !strv(c, "canonicalization", canonicalization) ||
        canonicalization != "exact_coordinate_identity_only") {
        why = "tri_planar_source_authority_fields_invalid"; return false;
    }
    return true;
}
bool parse_edges(const py::list& records, std::vector<edge::EdgeRow>& rows,
                 std::string& why) {
    try {
        for (const py::handle& item : records) {
            const py::dict d = item.cast<py::dict>();
            edge::EdgeRow r;
            std::vector<std::int64_t> endpoints;
            if (!strv(d, "edge_id", r.edge_id) || !d.contains("endpoint_vertex_ids") ||
                !seq(d["endpoint_vertex_ids"], endpoints) || endpoints.size() != 2U ||
                !d.contains("incident_face_ids") || !seq(d["incident_face_ids"], r.incident_faces) ||
                !d.contains("directed_sector_face_ids") ||
                !seq(d["directed_sector_face_ids"], r.directed_sector_faces) ||
                !d.contains("directed_sector_ids") ||
                !seq(d["directed_sector_ids"], r.directed_sector_ids) ||
                !strv(d, "wall_role", r.wall_role) ||
                !strv(d, "patch_boundary_role", r.patch_boundary_role) ||
                !strv(d, "feature", r.feature) || !strv(d, "patch", r.patch) ||
                !strv(d, "physical_group", r.physical_group) ||
                !strv(d, "component", r.component) ||
                !strv(d, "provenance", r.provenance)) {
                why = "tri_planar_wall_edge_record_invalid"; return false;
            }
            r.endpoints = {endpoints[0], endpoints[1]};
            rows.push_back(r);
        }
        return true;
    } catch (...) {
        why = "tri_planar_wall_edge_record_invalid"; return false;
    }
}
bool parse_anchor(const py::dict& d, Anchor& a) {
    return strv(d, "source_sha256", a.source_sha) && hex64(a.source_sha) &&
           strv(d, "semantic_ledger_sha256", a.semantic_sha) && hex64(a.semantic_sha) &&
           strv(d, "certificate_sha256", a.certificate_sha) && hex64(a.certificate_sha) &&
           strv(d, "edge_ledger_sha256", a.edge_sha) && hex64(a.edge_sha) &&
           strv(d, "issuer", a.issuer) && strv(d, "key_id", a.key_id) &&
           strv(d, "loop_policy", a.loop_policy) &&
           i64v(d, "source_byte_count", a.byte_count) &&
           (!d.contains("loop_endpoint_vertex_ids") ||
            seq(d["loop_endpoint_vertex_ids"], a.endpoints));
}
bool parse_template(const py::dict& d, TemplateSpec& s) {
    std::vector<std::int64_t> active;
    return strv(d, "schema", s.schema) && s.schema == "NativeTriPlanarTriangleTemplate/v1" &&
           strv(d, "template_id", s.template_id) &&
           strv(d, "source_certificate_sha256", s.source_sha) && hex64(s.source_sha) &&
           strv(d, "edge_ledger_sha256", s.edge_sha) && hex64(s.edge_sha) &&
           strv(d, "preflight_digest", s.preflight_digest) && hex64(s.preflight_digest) &&
           strv(d, "issuer", s.issuer) && strv(d, "key_id", s.key_id) &&
           i64v(d, "cavity_source_face_id", s.face) &&
           d.contains("wall_edge_ids") && seq(d["wall_edge_ids"], s.wall_edge_ids) &&
           d.contains("active_sector_face_ids") &&
           seq(d["active_sector_face_ids"], active) && active.size() == 3U &&
           strv(d, "feature", s.label.feature) && strv(d, "patch", s.label.patch) &&
           strv(d, "physical_group", s.label.group) &&
           strv(d, "component", s.label.component) &&
           strv(d, "provenance", s.label.provenance) &&
           (s.active_sector_faces = std::move(active), true);
}
bool validate_binding(const Source& s, const std::vector<edge::EdgeRow>& rows,
                      const Anchor& a, const TemplateSpec& t,
                      std::vector<const edge::EdgeRow*>& selected, std::string& why) {
    if (a.byte_count != s.byte_count || a.source_sha != s.source_sha ||
        a.semantic_sha != s.semantic_sha || a.certificate_sha != s.certificate_sha ||
        a.loop_policy != "closed_nonbranching" || !a.endpoints.empty() ||
        rows.size() != 3U || t.wall_edge_ids.size() != 3U ||
        t.active_sector_faces.size() != 3U ||
        t.source_sha != s.certificate_sha || t.edge_sha != a.edge_sha ||
        t.issuer != a.issuer || t.key_id != a.key_id) {
        why = "tri_planar_authority_or_template_anchor_mismatch"; return false;
    }
    if (t.face < 0 || static_cast<std::size_t>(t.face) >= s.faces.size()) {
        why = "tri_planar_cavity_face_invalid"; return false;
    }
    const Label& label = s.labels[static_cast<std::size_t>(t.face)];
    if (t.label.feature != label.feature || t.label.patch != label.patch ||
        t.label.group != label.group || t.label.component != label.component ||
        t.label.provenance != label.provenance) {
        why = "tri_planar_cavity_label_mismatch"; return false;
    }
    std::vector<std::string> ids = t.wall_edge_ids;
    std::sort(ids.begin(), ids.end());
    if (ids.size() != 3U || std::adjacent_find(ids.begin(), ids.end()) != ids.end()) {
        why = "tri_planar_wall_edge_ids_duplicate"; return false;
    }
    std::vector<std::pair<std::string, const edge::EdgeRow*>> ordered;
    for (const auto& row : rows) {
        if (row.wall_role != "wall" ||
            std::find(ids.begin(), ids.end(), row.edge_id) == ids.end() ||
            std::find(row.incident_faces.begin(), row.incident_faces.end(), t.face) ==
                row.incident_faces.end() ||
            std::find(row.directed_sector_faces.begin(), row.directed_sector_faces.end(), t.face) ==
                row.directed_sector_faces.end() ||
            row.feature != label.feature || row.patch != label.patch ||
            row.physical_group != label.group || row.component != label.component ||
            row.provenance != label.provenance) {
            why = "tri_planar_active_sector_or_label_binding_invalid"; return false;
        }
        ordered.emplace_back(row.edge_id, &row);
    }
    std::sort(ordered.begin(), ordered.end(),
              [](const auto& l, const auto& r) { return l.first < r.first; });
    for (std::size_t i = 0; i < ids.size(); ++i)
        if (ordered[i].first != ids[i] || t.active_sector_faces[i] != t.face) {
            why = "tri_planar_edge_registration_mismatch"; return false;
        }
    const auto& f = s.faces[static_cast<std::size_t>(t.face)];
    std::set<std::pair<std::int64_t, std::int64_t>> expected, actual;
    for (int i = 0; i < 3; ++i)
        expected.insert(edge::undirected_edge(f[i], f[(i + 1) % 3]));
    selected.clear();
    for (const auto& item : ordered) {
        actual.insert(edge::undirected_edge(item.second->endpoints[0], item.second->endpoints[1]));
        selected.push_back(item.second);
    }
    if (actual != expected) {
        why = "tri_planar_face_edge_set_mismatch"; return false;
    }
    return true;
}
std::vector<double> heights_for(const std::int64_t n, const double first,
                                const double growth, std::string& why) {
    std::vector<double> h;
    if (n < 0 || n > 1024) { why = "tri_planar_layer_count_out_of_bounds"; return h; }
    if (n == 0) return h;
    if (!std::isfinite(first) || !std::isfinite(growth) || !(first > 0.0) ||
        !(growth >= 1.0)) { why = "tri_planar_layer_schedule_invalid"; return h; }
    h.reserve(static_cast<std::size_t>(n));
    double value = first;
    for (std::int64_t i = 0; i < n; ++i) {
        if (!std::isfinite(value) || !(value > 0.0)) {
            why = "tri_planar_layer_schedule_overflow"; h.clear(); return h;
        }
        h.push_back(value); value *= growth;
    }
    return h;
}
std::string preflight_stream(const Source& s, const std::string& edge_sha,
                             const std::string& policy, std::int64_t n,
                             double first, double growth,
                             const std::vector<double>& heights) {
    std::ostringstream out;
    out << "NativeTriWallEdgeBLPreflight/v1|" << s.certificate_sha << '|' << s.source_sha
        << '|' << s.semantic_sha << '|' << edge_sha << '|' << policy << '|' << n << '|'
        << first << '|' << growth;
    for (double h : heights) out << '|' << h;
    return out.str();
}
py::dict point_receipt(std::int64_t id, const tpl::Point& p, std::int64_t layer,
                       std::int64_t face, const std::vector<std::string>& edges,
                       const Label& label) {
    py::dict r;
    r["vertex_id"] = id; r["x"] = p[0]; r["y"] = p[1]; r["z"] = p[2];
    r["layer"] = layer; r["source_face_id"] = face;
    py::list e; for (const auto& v : edges) e.append(v); r["source_wall_edge_ids"] = e;
    r["feature"] = label.feature; r["patch"] = label.patch;
    r["physical_group"] = label.group; r["component"] = label.component;
    r["provenance"] = label.provenance;
    return r;
}
py::dict quality_receipt(const tpl::Quality& q, std::int64_t id, std::int64_t layer,
                         const std::string& role, const std::string& edge_id, int diagonal) {
    py::dict r;
    r["output_face_id"] = id; r["layer"] = layer; r["role"] = role;
    r["source_wall_edge"] = edge_id; r["diagonal"] = diagonal;
    r["skewness"] = q.skewness; r["aspect_ratio"] = q.aspect;
    r["wall_front_non_orthogonality_degrees"] = q.wall_nonorthogonality;
    r["triangle_angle_non_orthogonality_degrees"] = q.angle_nonorthogonality;
    r["signed_area"] = q.signed_area; r["physical_aspect_ratio"] = q.physical_aspect; r["accepted"] = true;
    return r;
}
py::dict audit_receipt(const autotessell_surface_bl_independent_audit::Summary& a) {
    py::dict r;
    r["accepted"] = a.finite && a.invalid == 0 && a.inverted == 0 &&
                    a.duplicate == 0 && a.non_manifold == 0 && a.self_intersection == 0;
    r["invalid"] = a.invalid; r["inverted"] = a.inverted;
    r["duplicate"] = a.duplicate; r["non_manifold"] = a.non_manifold;
    r["self_intersection"] = a.self_intersection;
    r["max_skewness"] = static_cast<double>(a.max_skewness);
    r["max_aspect_ratio"] = static_cast<double>(a.max_aspect);
    r["max_non_orthogonality_degrees"] =
        static_cast<double>(a.max_non_orthogonality_degrees);
    r["p95_skewness"] = static_cast<double>(a.p95_skewness);
    r["p99_skewness"] = static_cast<double>(a.p99_skewness);
    r["p95_aspect_ratio"] = static_cast<double>(a.p95_aspect);
    r["p99_aspect_ratio"] = static_cast<double>(a.p99_aspect);
    r["p95_non_orthogonality_degrees"] = static_cast<double>(a.p95_non_orthogonality_degrees);
    r["p99_non_orthogonality_degrees"] = static_cast<double>(a.p99_non_orthogonality_degrees);
    r["source_plane_deviation"] = static_cast<double>(a.source_plane_deviation);
    r["metric_kernel"] = "independent_long_double_no_strip_triangle_quality";
    return r;
}
py::dict validate_impl(const py::dict& source_input, const py::list& edge_records,
                       const py::dict& edge_anchor, const py::dict& template_anchor,
                       std::int64_t requested, double first, double growth) {
    if (requested < 0) return refuse("tri_planar_requested_layers_invalid");
    Source source; std::string why;
    if (!parse_source(source_input, source, why)) return refuse(why);
    Anchor anchor;
    if (!parse_anchor(edge_anchor, anchor)) return refuse("tri_planar_external_edge_anchor_invalid");
    std::vector<edge::EdgeRow> rows;
    if (!parse_edges(edge_records, rows, why)) return refuse(why);
    const std::string edge_sha = auth::sha256_text(
        edge::canonical_edge_stream(rows, anchor.loop_policy, anchor.endpoints));
    if (edge_sha != anchor.edge_sha) return refuse("tri_planar_external_edge_ledger_mismatch");
    std::size_t count = 0U;
    if (!edge::validate_edge_ledger_geometry(source.points, source.faces, rows,
                                             anchor.loop_policy, anchor.endpoints, why, count))
        return refuse(why);
    if (count != 3U) return refuse("tri_planar_template_requires_three_edges");
    TemplateSpec spec;
    if (!parse_template(template_anchor, spec)) return refuse("tri_planar_template_anchor_invalid");
    std::vector<const edge::EdgeRow*> selected;
    if (!validate_binding(source, rows, anchor, spec, selected, why)) return refuse(why);
    std::vector<double> heights = heights_for(requested, first, growth, why);
    if (requested > 0 && heights.empty()) return refuse(why);
    const std::string expected_preflight = auth::sha256_text(
        preflight_stream(source, edge_sha, anchor.loop_policy, requested,
                         first, growth, heights));
    if (expected_preflight != spec.preflight_digest)
        return refuse("tri_planar_preflight_digest_mismatch");

    const auto& sf = source.faces[static_cast<std::size_t>(spec.face)];
    const std::array<tpl::Point, 3> cavity{
        source.points[static_cast<std::size_t>(sf[0])],
        source.points[static_cast<std::size_t>(sf[1])],
        source.points[static_cast<std::size_t>(sf[2])]};
    const tpl::Point face_normal = tpl::unit(auth::cross(
        tpl::sub(cavity[1], cavity[0]), tpl::sub(cavity[2], cavity[0])));
    const double scale = [&]() {
        double v = 1.0;
        for (const auto& p : source.points) v = std::max(v, auth::norm(p));
        return v;
    }();
    const double coord_tol = 1.0e-12 * scale;
    const double area_tol = 1.0e-14 * scale * scale;
    const double area = tpl::signed_area(cavity[0], cavity[1], cavity[2], face_normal);
    const double perimeter = auth::norm(tpl::sub(cavity[1], cavity[0])) +
                             auth::norm(tpl::sub(cavity[2], cavity[1])) +
                             auth::norm(tpl::sub(cavity[0], cavity[2]));
    const double inradius = 2.0 * area / perimeter;
    if (!(area > area_tol) || !(inradius > coord_tol))
        return refuse("tri_planar_cavity_geometry_invalid");

    if (requested == 0) {
        py::dict r;
        r["accepted"] = true; r["status"] = "native_tri_planar_triangle_bl_identity";
        r["reason"] = "authority_bound_source_identity";
        r["requested_layers"] = 0; r["actual_layers"] = 0;
        r["source_certificate_sha256"] = source.certificate_sha;
        r["source_sha256"] = source.source_sha; r["source_byte_count"] = source.byte_count;
        r["semantic_ledger_sha256"] = source.semantic_sha;
        r["canonical_geometry_sha256"] = source.geometry_sha;
        r["edge_ledger_sha256"] = edge_sha; r["preflight_digest"] = spec.preflight_digest;
        r["template_id"] = spec.template_id; r["cavity_source_face_id"] = spec.face;
        r["wall_edge_ids"] = spec.wall_edge_ids;
        r["active_sector_face_ids"] = spec.active_sector_faces;
        r["bl0_identity"] = true; r["writer_invoked"] = false;
        r["preflight_only"] = false; r["artifact_emitted"] = false;
        r["publication_eligible"] = false; r["release_eligible"] = false;
        r["candidate_discarded"] = false; r["atomic_rollback"] = false;
        r["runtime_route"] = "private_default_off"; r["route_calls"] = 0;
        py::list points, faces;
        for (const auto& p : source.points) {
            py::list row; for (double v : p) row.append(v); points.append(row);
        }
        for (const auto& f : source.faces) {
            py::list row; for (auto v : f) row.append(v); faces.append(row);
        }
        r["output_vertices"] = points; r["output_faces"] = faces;
        r["generated_vertices"] = py::list(); r["generated_faces"] = py::list();
        r["provenance"] = py::list(); r["generated_provenance"] = py::list();
        r["source_face_coverage_complete"] = true; r["identity_digest"] = source.certificate_sha;
        r["layer_heights"] = py::list();
        return r;
    }

    std::vector<tpl::Point> points = source.points;
    std::vector<tpl::Triangle> output, generated;
    std::vector<bool> generated_mask;
    std::vector<tpl::Quality> qualities;
    py::list output_prov, generated_prov, generated_vertices, quality_witness;
    const auto provenance_for = [&](std::int64_t output_id, std::int64_t face_id,
                                    const std::string& role) {
        py::dict d = label_dict(source.labels[static_cast<std::size_t>(face_id)]);
        d["output_face_id"] = output_id; d["source_face_id"] = face_id;
        py::list coverage; coverage.append(face_id); d["source_face_ids"] = coverage;
        d["replacement_role"] = role;
        return d;
    };
    for (std::size_t id = 0; id < source.faces.size(); ++id) {
        if (static_cast<std::int64_t>(id) == spec.face) continue;
        output.push_back(source.faces[id]); generated_mask.push_back(false);
        output_prov.append(provenance_for(static_cast<std::int64_t>(output.size()-1U),
                                           static_cast<std::int64_t>(id), "source_retained"));
    }

    std::vector<std::array<std::int64_t, 3>> fronts;
    double cumulative = 0.0, max_skew = 0.0, max_aspect = 0.0, max_wall = 0.0, max_physical_aspect = 0.0;
    for (std::int64_t layer = 0; layer < requested; ++layer) {
        cumulative += heights[static_cast<std::size_t>(layer)];
        if (!(cumulative < inradius - coord_tol))
            return refuse("tri_planar_cumulative_height_reaches_inradius");
        std::array<tpl::Point, 3> inner{};
        if (!tpl::make_inner_front(cavity, face_normal, cumulative, inner, coord_tol, why))
            return refuse(why);
        std::array<std::int64_t, 3> ids{};
        for (int i = 0; i < 3; ++i) {
            ids[static_cast<std::size_t>(i)] = static_cast<std::int64_t>(points.size());
            points.push_back(inner[static_cast<std::size_t>(i)]);
            const int prev = (i + 2) % 3;
            generated_vertices.append(point_receipt(
                ids[static_cast<std::size_t>(i)], inner[static_cast<std::size_t>(i)],
                layer + 1, spec.face,
                {spec.wall_edge_ids[static_cast<std::size_t>(prev)],
                 spec.wall_edge_ids[static_cast<std::size_t>(i)]}, spec.label));
        }
        fronts.push_back(ids);
        const std::array<std::int64_t, 3> lower = layer == 0
            ? std::array<std::int64_t, 3>{sf[0], sf[1], sf[2]}
            : fronts[static_cast<std::size_t>(layer - 1)];
        const std::array<std::int64_t, 3> upper = ids;
        for (int i = 0; i < 3; ++i) {
            const int j = (i + 1) % 3;
            const tpl::Triangle z0{lower[i], lower[j], upper[j]};
            const tpl::Triangle z1{lower[i], upper[j], upper[i]};
            const tpl::Triangle o0{lower[i], lower[j], upper[i]};
            const tpl::Triangle o1{lower[j], upper[j], upper[i]};
            auto zero = tpl::evaluate_pair(z0, z1, points, lower, upper, i,
                                            face_normal, area_tol);
            auto one = tpl::evaluate_pair(o0, o1, points, lower, upper, i,
                                           face_normal, area_tol);
            zero.diagonal = 0; one.diagonal = 1;
            const bool choose_zero = tpl::pair_rank(zero) <= tpl::pair_rank(one);
            const auto& chosen = choose_zero ? zero : one;
            const std::array<tpl::Triangle, 2> tris = choose_zero
                ? std::array<tpl::Triangle, 2>{z0, z1}
                : std::array<tpl::Triangle, 2>{o0, o1};
            if (!chosen.valid) {
                py::dict rejected = refuse("tri_planar_no_quality_admissible_diagonal");
                py::dict z;
                z["valid"] = zero.valid; z["skewness"] = zero.max_skewness;
                z["aspect"] = zero.max_aspect;
                z["wall_nonorthogonality"] = zero.max_wall_nonorthogonality;
                z["angle_nonorthogonality"] = zero.max_angle_nonorthogonality;
                z["min_signed_area"] = zero.min_signed_area;
                py::dict o;
                o["valid"] = one.valid; o["skewness"] = one.max_skewness;
                o["aspect"] = one.max_aspect;
                o["wall_nonorthogonality"] = one.max_wall_nonorthogonality;
                o["angle_nonorthogonality"] = one.max_angle_nonorthogonality;
                o["min_signed_area"] = one.min_signed_area;
                rejected["quality_candidate_zero"] = z;
                rejected["quality_candidate_one"] = o;
                return rejected;
            }
            max_skew = std::max(max_skew, chosen.max_skewness);
            max_aspect = std::max(max_aspect, chosen.max_aspect);
            max_physical_aspect = std::max(max_physical_aspect, std::max(chosen.first.physical_aspect, chosen.second.physical_aspect));
            max_wall = std::max(max_wall, chosen.max_wall_nonorthogonality);
            for (int part = 0; part < 2; ++part) {
                const auto& tri = tris[static_cast<std::size_t>(part)];
                output.push_back(tri); generated.push_back(tri); generated_mask.push_back(true);
                const auto id = static_cast<std::int64_t>(output.size() - 1U);
                py::dict p = provenance_for(id, spec.face, "boundary_layer_ring");
                p["layer"] = layer + 1;
                p["source_wall_edge"] = spec.wall_edge_ids[static_cast<std::size_t>(i)];
                p["source_wall_edge_ids"] = py::make_tuple(
                    spec.wall_edge_ids[static_cast<std::size_t>(i)]);
                p["diagonal"] = chosen.diagonal;
                output_prov.append(p); generated_prov.append(p);
                const tpl::Quality q = part == 0 ? chosen.first : chosen.second;
                qualities.push_back(q);
                quality_witness.append(quality_receipt(
                    q, id, layer + 1, "boundary_layer_ring",
                    spec.wall_edge_ids[static_cast<std::size_t>(i)], chosen.diagonal));
            }
        }
    }
    const auto& last = fronts.back();
    const tpl::Triangle core{last[0], last[1], last[2]};
    const tpl::Quality core_q = tpl::triangle_quality(
        points[static_cast<std::size_t>(core[0])],
        points[static_cast<std::size_t>(core[1])],
        points[static_cast<std::size_t>(core[2])], face_normal);
    if (!(core_q.signed_area > area_tol) || core_q.skewness > 0.50 + 1.0e-12 ||
        core_q.aspect > 10.0 + 1.0e-12 ||
        core_q.angle_nonorthogonality > 30.0 + 1.0e-12)
        return refuse("tri_planar_core_quality_failure");
    output.push_back(core); generated.push_back(core); generated_mask.push_back(true);
    const auto core_id = static_cast<std::int64_t>(output.size() - 1U);
    py::dict core_p = provenance_for(core_id, spec.face, "boundary_layer_core");
    core_p["layer"] = requested; core_p["source_wall_edge_ids"] = spec.wall_edge_ids;
    output_prov.append(core_p); generated_prov.append(core_p);
    qualities.push_back(core_q);
    quality_witness.append(quality_receipt(
        core_q, core_id, requested, "boundary_layer_core", "triangle_core", 0));
    max_skew = std::max(max_skew, core_q.skewness);
    max_aspect = std::max(max_aspect, core_q.aspect);
    max_physical_aspect = std::max(max_physical_aspect, core_q.physical_aspect);

    const auto topology = tpl::audit_output(
        points, output, generated_mask, face_normal, area_tol);
    if (topology.invalid || topology.degenerate || topology.inverted ||
        topology.duplicate || topology.open_edges || topology.non_manifold ||
        topology.self_intersection)
        return refuse("tri_planar_output_topology_failed");
    std::vector<tpl::Triangle> retained;
    for (std::size_t i = 0; i < source.faces.size(); ++i)
        if (static_cast<std::int64_t>(i) != spec.face) retained.push_back(source.faces[i]);
    const auto collision = tpl::audit_collisions(points, generated, retained, area_tol);
    if (collision.rejected_contacts)
        return refuse("tri_planar_candidate_collision");
    const auto independent = autotessell_surface_bl_independent_audit::audit_faces(
        points, generated, cavity[0], face_normal,
        static_cast<long double>(area_tol), static_cast<long double>(coord_tol));
    if (!independent.finite || independent.invalid || independent.inverted ||
        independent.duplicate || independent.non_manifold ||
        independent.self_intersection ||
        independent.source_plane_deviation > static_cast<long double>(coord_tol))
        return refuse("tri_planar_long_double_quality_audit_failed");

    std::ostringstream digest_stream;
    digest_stream << "NativeTriPlanarTriangleBL/v1|" << source.certificate_sha << '|'
                  << edge_sha << '|' << spec.preflight_digest << '|' << spec.template_id
                  << '|' << requested << '|' << std::setprecision(17) << first << '|' << growth;
    for (const auto& p : points) digest_stream << '|' << p[0] << ',' << p[1] << ',' << p[2];
    for (const auto& f : output) digest_stream << '|' << f[0] << ',' << f[1] << ',' << f[2];
    const std::string digest = auth::sha256_text(digest_stream.str());

    py::list output_points, output_faces, generated_faces;
    for (const auto& p : points) { py::list r; for (double v : p) r.append(v); output_points.append(r); }
    for (const auto& f : output) { py::list r; for (auto v : f) r.append(v); output_faces.append(r); }
    for (const auto& f : generated) { py::list r; for (auto v : f) r.append(v); generated_faces.append(r); }
    py::dict topo;
    topo["invalid"] = topology.invalid; topo["degenerate"] = topology.degenerate;
    topo["inverted"] = topology.inverted; topo["duplicate"] = topology.duplicate;
    topo["open_edges"] = topology.open_edges; topo["non_manifold"] = topology.non_manifold;
    topo["self_intersection"] = topology.self_intersection;
    py::dict coll;
    coll["checked"] = true; coll["broad_phase_pairs"] = collision.broad_phase_pairs;
    coll["narrow_phase_hits"] = collision.narrow_phase_hits;
    coll["allowed_shared_contacts"] = collision.allowed_shared_contacts;
    coll["rejected_contacts"] = collision.rejected_contacts;
    py::dict q;
    q["max_skewness"] = max_skew; q["max_aspect_ratio"] = max_aspect; q["max_physical_aspect_ratio"] = max_physical_aspect;
    q["max_wall_front_non_orthogonality_degrees"] = max_wall;
    q["max_triangle_angle_non_orthogonality_degrees"] =
        static_cast<double>(independent.max_non_orthogonality_degrees);
    q["skewness_limit"] = 0.50; q["aspect_ratio_limit"] = 10.0;
    q["wall_front_non_orthogonality_limit_degrees"] = 30.0;
    q["raw_triangle_angle_non_orthogonality_report_only"] = true;
    q["raw_physical_aspect_report_only"] = true;
    q["metric_quality_gate_pass"] = true;
    q["metric_mode"] = "constant_identity_planar";
    q["count_is_report_only"] = true;
    q["independent_long_double_audit"] = audit_receipt(independent);

    py::dict r;
    r["accepted"] = true; r["status"] = "native_tri_planar_triangle_bl_artifact_sealed";
    r["reason"] = "authority_bound_planar_triangle_bl_quality_passed";
    r["requested_layers"] = requested; r["actual_layers"] = requested;
    r["layer_heights"] = heights; r["cumulative_height"] = cumulative; r["inradius"] = inradius;
    r["source_certificate_sha256"] = source.certificate_sha;
    r["source_sha256"] = source.source_sha; r["source_byte_count"] = source.byte_count;
    r["semantic_ledger_sha256"] = source.semantic_sha;
    r["canonical_geometry_sha256"] = source.geometry_sha;
    r["edge_ledger_sha256"] = edge_sha; r["preflight_digest"] = spec.preflight_digest;
    r["template_id"] = spec.template_id; r["template_digest"] = digest;
    r["deterministic_digest"] = digest; r["cavity_source_face_id"] = spec.face;
    r["wall_edge_ids"] = spec.wall_edge_ids;
    r["active_sector_face_ids"] = spec.active_sector_faces;
    r["source_faces_removed"] = py::make_tuple(spec.face);
    py::list kept; for (std::size_t i=0;i<source.faces.size();++i)
        if (static_cast<std::int64_t>(i) != spec.face) kept.append(i);
    r["source_faces_retained"] = kept; r["source_face_coverage_complete"] = true;
    r["generated_vertices"] = generated_vertices; r["generated_faces"] = generated_faces;
    r["output_vertices"] = output_points; r["output_faces"] = output_faces;
    r["provenance"] = output_prov; r["generated_provenance"] = generated_prov;
    r["quality_witness"] = quality_witness; r["quality"] = q;
    r["independent_long_double_audit"] = audit_receipt(independent);
    r["topology"] = topo; r["topology_invalid"] = topology.invalid;
    r["topology_degenerate"] = topology.degenerate; r["topology_inverted"] = topology.inverted;
    r["topology_duplicate"] = topology.duplicate; r["topology_open_edges"] = topology.open_edges;
    r["topology_non_manifold"] = topology.non_manifold;
    r["topology_self_intersection"] = topology.self_intersection; r["collision"] = coll;
    r["writer_invoked"] = true; r["preflight_only"] = false; r["artifact_emitted"] = true;
    r["publication_eligible"] = false; r["release_eligible"] = false;
    r["candidate_discarded"] = false; r["atomic_rollback"] = false;
    r["bl0_identity"] = false; r["runtime_route"] = "private_default_off"; r["route_calls"] = 0;
    return r;
}
py::dict guarded(const py::dict& source, const py::list& edges, const py::dict& anchor,
                 const py::dict& templ, std::int64_t n, double h, double g) {
    try { return validate_impl(source, edges, anchor, templ, n, h, g); }
    catch (...) { return refuse("tri_planar_template_malformed"); }
}

}  // namespace

PYBIND11_MODULE(native_tri_planar_triangle_bl_template, module) {
    module.doc() = "Private C++23 authority-bound planar Native Tri BL template";
    module.def("write_native_tri_planar_triangle_bl", &guarded,
               py::arg("source_certificate"), py::arg("edge_ledger"),
               py::arg("edge_anchor"), py::arg("template_anchor"),
               py::arg("requested_layers"), py::arg("first_height"),
               py::arg("growth_ratio"));
}
