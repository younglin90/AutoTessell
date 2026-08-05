#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "native_tri_wall_edge_bl_preflight.hpp"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace py = pybind11;
namespace auth = autotessell_native_tri_authority;
namespace edge = autotessell_native_tri_wall_edge;

namespace {
struct Label {
    std::string feature;
    std::string patch;
    std::string group;
    std::string component;
    std::string provenance;
};
struct Source {
    std::vector<auth::Point> points;
    std::vector<auth::Triangle> faces;
    std::vector<Label> labels;
    std::string source_sha;
    std::string semantic_sha;
    std::string geometry_sha;
    std::string certificate_sha;
    std::string source_kind;
    std::int64_t byte_count = -1;
};

py::dict refuse(const std::string& why) {
    py::dict r;
    r["accepted"] = false;
    r["preflight_accepted"] = false;
    r["status"] = "native_tri_wall_edge_bl_preflight_refused";
    r["reason"] = why;
    r["actual_layers"] = 0;
    r["writer_invoked"] = false;
    r["preflight_only"] = true;
    r["artifact_emitted"] = false;
    r["release_eligible"] = false;
    r["publication_eligible"] = false;
    r["candidate_discarded"] = true;
    r["runtime_route"] = "private_default_off";
    r["route_calls"] = 0;
    r["generated_vertices"] = py::list();
    r["generated_faces"] = py::list();
    r["provenance"] = py::list();
    r["wall_edges"] = py::list();
    r["layer_heights"] = py::list();
    return r;
}

bool str(const py::dict& d, const char* key, std::string& out) {
    if (!d.contains(key) || !py::isinstance<py::str>(d[key])) return false;
    out = d[key].cast<std::string>();
    return !out.empty();
}
bool i64(const py::dict& d, const char* key, std::int64_t& out) {
    if (!d.contains(key) || py::isinstance<py::bool_>(d[key])) return false;
    try { out = d[key].cast<std::int64_t>(); } catch (...) { return false; }
    return true;
}
bool bval(const py::dict& d, const char* key, bool& out) {
    if (!d.contains(key) || !py::isinstance<py::bool_>(d[key])) return false;
    out = d[key].cast<bool>();
    return true;
}
bool hex64(const std::string& x) {
    return x.size() == 64U && std::all_of(x.begin(), x.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    });
}
template <class T>
bool seq(const py::handle& value, std::vector<T>& out) {
    try { out = value.cast<std::vector<T>>(); return true; } catch (...) { return false; }
}

void append_field(std::ostringstream& stream, const std::string& value) {
    stream << value.size() << ':' << value << '|';
}

std::string semantic_stream(const Source& source) {
    std::ostringstream stream;
    stream << "rows=" << source.faces.size() << '|';
    for (std::size_t face = 0; face < source.faces.size(); ++face) {
        const auto& triangle = source.faces[face];
        const auto& label = source.labels[face];
        stream << face << ':' << triangle[0] << ',' << triangle[1] << ','
               << triangle[2] << '|';
        append_field(stream, label.feature);
        append_field(stream, label.patch);
        append_field(stream, label.group);
        append_field(stream, label.component);
        append_field(stream, label.provenance);
    }
    return stream.str();
}

bool parse_source(const py::dict& input, Source& s, std::string& why) {
    if (input.contains("certificate_accepted") &&
        (!py::isinstance<py::bool_>(input["certificate_accepted"]) ||
         !input["certificate_accepted"].cast<bool>())) {
        why = "tri_wall_edge_source_certificate_not_accepted";
        return false;
    }
    py::dict c = input;
    if (input.contains("certificate")) {
        if (!py::isinstance<py::dict>(input["certificate"])) {
            why = "tri_wall_edge_source_certificate_payload_invalid";
            return false;
        }
        c = input["certificate"].cast<py::dict>();
    }
    std::string schema, issuer, key_id;
    if (!str(c, "schema", schema) || schema != "NativeTriAuthorityCertificate/v2" ||
        !str(c, "source_sha256", s.source_sha) || !hex64(s.source_sha) ||
        !str(c, "semantic_ledger_sha256", s.semantic_sha) || !hex64(s.semantic_sha) ||
        !str(c, "canonical_geometry_sha256", s.geometry_sha) || !hex64(s.geometry_sha) ||
        !str(c, "certificate_sha256", s.certificate_sha) || !hex64(s.certificate_sha) ||
        !str(c, "source_kind", s.source_kind) ||
        !str(c, "issuer", issuer) || !str(c, "key_id", key_id) ||
        !i64(c, "source_byte_count", s.byte_count) || s.byte_count <= 0) {
        why = "tri_wall_edge_source_certificate_fields_invalid";
        return false;
    }
    try {
        s.points = c["canonical_points"].cast<std::vector<auth::Point>>();
        s.faces = c["canonical_triangles"].cast<std::vector<auth::Triangle>>();
    } catch (...) {
        why = "tri_wall_edge_source_certificate_arrays_invalid";
        return false;
    }
    if (s.points.empty() || s.faces.empty()) {
        why = "tri_wall_edge_source_certificate_arrays_empty";
        return false;
    }
    try {
        py::sequence records = c["face_ledger"].cast<py::sequence>();
        if (records.size() != s.faces.size()) {
            why = "tri_wall_edge_face_ledger_coverage_incomplete";
            return false;
        }
        s.labels.assign(s.faces.size(), {});
        std::vector<bool> seen(s.faces.size(), false);
        for (const py::handle& item : records) {
            py::dict row = item.cast<py::dict>();
            std::int64_t face = -1, source_face = -2;
            std::vector<std::int64_t> vertices;
            if (!i64(row, "face_id", face) || !i64(row, "source_facet_id", source_face) ||
                face != source_face || face < 0 ||
                static_cast<std::size_t>(face) >= s.faces.size() ||
                !seq(row["vertices"], vertices) || vertices.size() != 3U ||
                auth::Triangle{vertices[0], vertices[1], vertices[2]} !=
                    s.faces[static_cast<std::size_t>(face)] || seen[static_cast<std::size_t>(face)] ||
                !str(row, "feature", s.labels[static_cast<std::size_t>(face)].feature) ||
                !str(row, "patch", s.labels[static_cast<std::size_t>(face)].patch) ||
                !str(row, "physical_group", s.labels[static_cast<std::size_t>(face)].group) ||
                !str(row, "component", s.labels[static_cast<std::size_t>(face)].component) ||
                !str(row, "provenance", s.labels[static_cast<std::size_t>(face)].provenance)) {
                why = "tri_wall_edge_face_binding_invalid";
                return false;
            }
            seen[static_cast<std::size_t>(face)] = true;
        }
        if (std::any_of(seen.begin(), seen.end(), [](bool value) { return !value; })) {
            why = "tri_wall_edge_face_binding_incomplete";
            return false;
        }
    } catch (...) {
        why = "tri_wall_edge_face_ledger_invalid";
        return false;
    }
    auth::CanonicalSource canonical{s.points, s.faces, {}, {}, s.source_kind};
    if (auth::sha256_text(semantic_stream(s)) != s.semantic_sha) {
        why = "tri_wall_edge_source_semantic_digest_mismatch";
        return false;
    }
    if (auth::sha256_text(auth::canonical_geometry_stream(canonical)) != s.geometry_sha) {
        why = "tri_wall_edge_source_geometry_digest_mismatch";
        return false;
    }
    std::ostringstream cert;
    cert << "NativeTriAuthorityCertificate/v2|" << s.source_kind << '|' << s.source_sha
         << '|' << s.geometry_sha << '|' << s.semantic_sha << '|' << issuer << '|'
         << key_id;
    if (auth::sha256_text(cert.str()) != s.certificate_sha) {
        why = "tri_wall_edge_source_certificate_digest_mismatch";
        return false;
    }
    if (!c.contains("topology") || !py::isinstance<py::dict>(c["topology"])) {
        why = "tri_wall_edge_source_topology_not_strict";
        return false;
    }
    py::dict topology = c["topology"].cast<py::dict>();
    bool strict = false, checked = false;
    if (!bval(topology, "strict_zero", strict) || !strict ||
        !bval(topology, "self_intersection_checked", checked) || !checked) {
        why = "tri_wall_edge_source_topology_not_strict";
        return false;
    }
    for (const char* key : {"duplicate", "non_manifold", "open_edges", "degenerate",
                            "inverted", "self_intersection"}) {
        std::int64_t count = -1;
        if (!i64(topology, key, count) || count != 0) {
            why = "tri_wall_edge_source_topology_not_strict";
            return false;
        }
    }
    bool authoritative = false, inferred_groups = true, inferred_features = true;
    std::string canonicalization;
    if (!bval(c, "source_provenance_authoritative", authoritative) || !authoritative ||
        !bval(c, "physical_groups_inferred", inferred_groups) || inferred_groups ||
        !bval(c, "feature_ids_inferred", inferred_features) || inferred_features ||
        !str(c, "canonicalization", canonicalization) ||
        canonicalization != "exact_coordinate_identity_only") {
        why = "tri_wall_edge_source_authority_fields_invalid";
        return false;
    }
    return true;
}

bool parse_edges(const py::list& records, std::vector<edge::EdgeRow>& rows,
                 std::string& why) {
    rows.clear();
    for (const py::handle& item : records) {
        try {
            py::dict d = item.cast<py::dict>();
            edge::EdgeRow row;
            std::vector<std::int64_t> endpoints;
            if (!str(d, "edge_id", row.edge_id) ||
                !seq(d["endpoint_vertex_ids"], endpoints) || endpoints.size() != 2U ||
                !seq(d["incident_face_ids"], row.incident_faces) ||
                !seq(d["directed_sector_face_ids"], row.directed_sector_faces) ||
                !seq(d["directed_sector_ids"], row.directed_sector_ids) ||
                !str(d, "wall_role", row.wall_role) ||
                !str(d, "patch_boundary_role", row.patch_boundary_role) ||
                !str(d, "feature", row.feature) || !str(d, "patch", row.patch) ||
                !str(d, "physical_group", row.physical_group) ||
                !str(d, "component", row.component) ||
                !str(d, "provenance", row.provenance)) {
                why = "tri_wall_edge_ledger_record_invalid";
                return false;
            }
            row.endpoints = {endpoints[0], endpoints[1]};
            rows.push_back(row);
        } catch (...) {
            why = "tri_wall_edge_ledger_record_invalid";
            return false;
        }
    }
    return true;
}

py::dict validate_impl(const py::dict& certificate,
                       const py::list& edge_ledger,
                       const py::dict& anchor,
                       std::int64_t requested,
                       double first_height,
                       double growth) {
    if (requested < 0) return refuse("tri_wall_edge_requested_layers_invalid");
    Source source;
    std::string why;
    if (!parse_source(certificate, source, why)) return refuse(why);

    std::string source_sha, semantic_sha, cert_sha, edge_sha, issuer, key_id, policy;
    if (!str(anchor, "source_sha256", source_sha) || !hex64(source_sha) ||
        !str(anchor, "semantic_ledger_sha256", semantic_sha) || !hex64(semantic_sha) ||
        !str(anchor, "certificate_sha256", cert_sha) || !hex64(cert_sha) ||
        !str(anchor, "edge_ledger_sha256", edge_sha) || !hex64(edge_sha) ||
        !str(anchor, "issuer", issuer) || !str(anchor, "key_id", key_id) ||
        !str(anchor, "loop_policy", policy)) {
        return refuse("tri_wall_edge_external_trust_anchor_incomplete");
    }
    std::int64_t bytes = -1;
    if (!i64(anchor, "source_byte_count", bytes) || bytes != source.byte_count)
        return refuse("tri_wall_edge_external_source_byte_count_mismatch");
    if (source_sha != source.source_sha || semantic_sha != source.semantic_sha ||
        cert_sha != source.certificate_sha)
        return refuse("tri_wall_edge_external_source_certificate_mismatch");

    std::vector<std::int64_t> endpoints;
    if (anchor.contains("loop_endpoint_vertex_ids") &&
        !seq(anchor["loop_endpoint_vertex_ids"], endpoints))
        return refuse("tri_wall_edge_loop_endpoint_registration_invalid");

    std::vector<edge::EdgeRow> rows;
    if (!parse_edges(edge_ledger, rows, why)) return refuse(why);
    const std::string computed_edge_sha = auth::sha256_text(
        edge::canonical_edge_stream(rows, policy, endpoints));
    if (computed_edge_sha != edge_sha)
        return refuse("tri_wall_edge_external_ledger_mismatch");

    std::size_t edge_count = 0;
    if (!edge::validate_edge_ledger_geometry(source.points, source.faces, rows, policy,
                                             endpoints, why, edge_count))
        return refuse(why);
    for (const edge::EdgeRow& row : rows) {
        bool bound = false;
        for (std::int64_t face : row.incident_faces) {
            const Label& label = source.labels[static_cast<std::size_t>(face)];
            bound = bound ||
                    (row.feature == label.feature && row.patch == label.patch &&
                     row.physical_group == label.group &&
                     row.component == label.component &&
                     row.provenance == label.provenance);
        }
        if (!bound) return refuse("tri_wall_edge_semantic_label_not_source_bound");
    }

    std::vector<double> heights;
    if (requested > 0) {
        if (!std::isfinite(first_height) || !std::isfinite(growth) ||
            !(first_height > 0.0) || !(growth >= 1.0))
            return refuse("tri_wall_edge_layer_schedule_invalid");
        double height = first_height;
        for (std::int64_t layer = 0; layer < requested; ++layer) {
            if (!std::isfinite(height) || !(height > 0.0))
                return refuse("tri_wall_edge_layer_schedule_overflow");
            heights.push_back(height);
            height *= growth;
        }
    }
    std::ostringstream receipt;
    receipt << "NativeTriWallEdgeBLPreflight/v1|" << source.certificate_sha << '|'
            << source.source_sha << '|' << source.semantic_sha << '|' << computed_edge_sha
            << '|' << policy << '|' << requested << '|' << first_height << '|' << growth;
    for (double value : heights) receipt << '|' << value;
    py::dict result;
    result["accepted"] = true;
    result["preflight_accepted"] = true;
    result["status"] = requested == 0 ? "native_tri_wall_edge_bl_identity_sealed"
                                      : "native_tri_wall_edge_bl_preflight_sealed";
    result["reason"] = requested == 0 ? "source_and_edge_identity_verified"
                                      : "explicit_wall_edge_loop_and_schedule_verified";
    result["source_certificate_sha256"] = source.certificate_sha;
    result["source_sha256"] = source.source_sha;
    result["source_byte_count"] = source.byte_count;
    result["semantic_ledger_sha256"] = source.semantic_sha;
    result["edge_ledger_sha256"] = computed_edge_sha;
    result["issuer"] = issuer;
    result["key_id"] = key_id;
    result["loop_policy"] = policy;
    result["loop_endpoint_vertex_ids"] = endpoints;
    result["edge_count"] = edge_count;
    result["wall_edge_authority_verified"] = true;
    result["requested_layers"] = requested;
    result["layer_heights"] = heights;
    result["actual_layers"] = 0;
    result["writer_invoked"] = false;
    result["preflight_only"] = true;
    result["artifact_emitted"] = false;
    result["release_eligible"] = false;
    result["publication_eligible"] = false;
    result["eligible_for_tri_bl"] = false;
    result["candidate_discarded"] = false;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["bl0_identity"] = requested == 0;
    result["preflight_digest"] = auth::sha256_text(receipt.str());
    py::list edge_output;
    for (const edge::EdgeRow& row : rows) {
        py::dict item;
        item["edge_id"] = row.edge_id;
        item["endpoint_vertex_ids"] = row.endpoints;
        edge_output.append(item);
    }
    result["wall_edges"] = edge_output;
    result["generated_vertices"] = py::list();
    result["generated_faces"] = py::list();
    result["provenance"] = py::list();
    return result;
}

py::dict guarded(const py::dict& certificate, const py::list& edge_ledger,
                 const py::dict& anchor, std::int64_t requested,
                 double first_height, double growth) {
    try {
        return validate_impl(certificate, edge_ledger, anchor, requested,
                             first_height, growth);
    } catch (...) {
        return refuse("tri_wall_edge_preflight_malformed");
    }
}
}

PYBIND11_MODULE(native_tri_wall_edge_bl_preflight, module) {
    module.doc() = "Private C++23 Native Tri wall-edge BL preflight";
    module.def("validate_native_tri_wall_edge_bl_preflight", &guarded,
               py::arg("source_certificate"), py::arg("edge_ledger"),
               py::arg("trust_anchor"), py::arg("requested_layers"),
               py::arg("first_height"), py::arg("growth_ratio"));
}
