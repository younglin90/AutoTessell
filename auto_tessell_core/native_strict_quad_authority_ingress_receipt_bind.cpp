#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <utility>

namespace py = pybind11;

py::dict refuse(const char* reason) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "strict_quad_authority_ingress_refused";
    result["reason"] = reason;
    result["eligible_for_strict_quad_bl"] = false;
    result["actual_layers"] = 0;
    result["publication_eligible"] = false;
    result["candidate_discarded"] = true;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    return result;
}

bool text(const py::dict& d, const char* k) {
    return d.contains(k) && !d[k].is_none() && !py::str(d[k]).cast<std::string>().empty();
}
bool hex64(const std::string& s) {
    if (s.size() != 64) return false;
    return std::all_of(s.begin(), s.end(), [](char c) { return std::isdigit(c) || (c >= 'a' && c <= 'f'); });
}

py::dict validate(const std::string& raw_sha, std::int64_t bytes,
                  const py::sequence& points, const py::sequence& triangles,
                  const py::dict& receipt) {
    if (!hex64(raw_sha) || bytes <= 0) return refuse("strict_quad_raw_digest_invalid");
    if (!text(receipt, "schema") || py::str(receipt["schema"]).cast<std::string>() != "StrictQuadAuthorityReceipt/v1") return refuse("strict_quad_schema_unsupported");
    for (const char* k : {"source_sha256", "reader_id", "issuer", "provenance", "point_digest", "triangle_digest", "fixed_pair_digest"}) {
        if (!text(receipt, k)) return refuse("strict_quad_receipt_header_incomplete");
    }
    if (py::str(receipt["source_sha256"]).cast<std::string>() != raw_sha ||
        !receipt.contains("source_byte_count") || receipt["source_byte_count"].cast<std::int64_t>() != bytes) return refuse("strict_quad_source_digest_mismatch");
    if (!receipt.contains("trust_policy") || !py::isinstance<py::dict>(receipt["trust_policy"]) || receipt["trust_policy"].cast<py::dict>().empty()) return refuse("strict_quad_trust_policy_missing");
    if (points.empty() || triangles.empty() || triangles.size() % 2 != 0) return refuse("strict_quad_tri_pair_input_invalid");
    if (!receipt.contains("faces") || !py::isinstance<py::list>(receipt["faces"])) return refuse("strict_quad_face_ledger_missing");
    py::list faces = receipt["faces"].cast<py::list>();
    if (faces.size() != triangles.size()) return refuse("strict_quad_face_coverage_incomplete");
    std::set<std::int64_t> face_ids;
    for (const py::handle& h : faces) {
        if (!py::isinstance<py::dict>(h)) return refuse("strict_quad_face_record_invalid");
        py::dict row = h.cast<py::dict>();
        for (const char* k : {"face_id", "feature", "patch", "physical_group", "component", "provenance"}) if (!text(row, k)) return refuse("strict_quad_semantic_label_incomplete");
        auto id = row["face_id"].cast<std::int64_t>();
        if (id < 0 || id >= static_cast<std::int64_t>(faces.size()) || !face_ids.insert(id).second) return refuse("strict_quad_face_id_invalid");
    }
    if (!receipt.contains("fixed_pairs") || !py::isinstance<py::list>(receipt["fixed_pairs"])) return refuse("strict_quad_fixed_pair_plan_missing");
    py::list pairs = receipt["fixed_pairs"].cast<py::list>();
    if (pairs.size() * 2 != triangles.size()) return refuse("strict_quad_fixed_pair_coverage_incomplete");
    std::set<std::int64_t> paired;
    for (const py::handle& h : pairs) {
        if (!py::isinstance<py::dict>(h)) return refuse("strict_quad_fixed_pair_invalid");
        py::dict row = h.cast<py::dict>();
        for (const char* k : {"pair_id", "triangle_ids", "quad_vertices", "feature", "patch", "physical_group", "component", "provenance"}) if (!text(row, k) && std::string(k) != "triangle_ids" && std::string(k) != "quad_vertices") return refuse("strict_quad_fixed_pair_label_incomplete");
        if (!row.contains("triangle_ids") || !py::isinstance<py::sequence>(row["triangle_ids"]) || !row.contains("quad_vertices") || !py::isinstance<py::sequence>(row["quad_vertices"])) return refuse("strict_quad_fixed_pair_geometry_missing");
        py::sequence ids = row["triangle_ids"].cast<py::sequence>(), verts = row["quad_vertices"].cast<py::sequence>();
        if (ids.size() != 2 || verts.size() != 4) return refuse("strict_quad_fixed_pair_geometry_invalid");
        for (const py::handle& idh : ids) { auto id = idh.cast<std::int64_t>(); if (id < 0 || id >= static_cast<std::int64_t>(triangles.size()) || !paired.insert(id).second) return refuse("strict_quad_fixed_pair_triangle_reuse"); }
        std::set<std::int64_t> unique_vertices;
        for (const py::handle& vh : verts) unique_vertices.insert(vh.cast<std::int64_t>());
        if (unique_vertices.size() != 4) return refuse("strict_quad_quad_vertices_invalid");
    }
    bool wall = false;
    if (receipt.contains("wall_loop") && py::isinstance<py::list>(receipt["wall_loop"])) {
        py::list loop = receipt["wall_loop"].cast<py::list>();
        std::set<std::string> edges;
        for (const py::handle& h : loop) {
            if (!py::isinstance<py::dict>(h)) return refuse("strict_quad_wall_loop_invalid");
            py::dict row = h.cast<py::dict>();
            for (const char* k : {"edge_id", "patch", "feature", "physical_group", "component", "provenance"}) if (!text(row, k)) return refuse("strict_quad_wall_loop_label_incomplete");
            if (!row.contains("endpoints") || !py::isinstance<py::sequence>(row["endpoints"]) || !row.contains("directed") || !row["directed"].cast<bool>()) return refuse("strict_quad_wall_loop_direction_missing");
            py::sequence ep = row["endpoints"].cast<py::sequence>(); if (ep.size() != 2 || ep[0].cast<std::int64_t>() == ep[1].cast<std::int64_t>()) return refuse("strict_quad_wall_loop_edge_invalid");
            std::string id = py::str(row["edge_id"]).cast<std::string>(); if (!edges.insert(id).second) return refuse("strict_quad_wall_loop_duplicate");
            wall = true;
        }
    }
    py::dict result;
    result["accepted"] = true;
    result["status"] = "strict_quad_authority_ingress_sealed";
    result["reason"] = wall ? "strict_quad_source_pair_and_wall_authority_verified" : "strict_quad_source_verified_wall_boundary_absent";
    result["eligible_for_strict_quad_bl"] = wall;
    result["wall_boundary_available"] = wall;
    result["actual_layers"] = 0;
    result["publication_eligible"] = false;
    result["candidate_discarded"] = false;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["triangle_count"] = triangles.size();
    result["fixed_pair_count"] = pairs.size();
    result["authority_schema"] = "StrictQuadAuthorityReceipt/v1";
    return result;
}

PYBIND11_MODULE(native_strict_quad_authority_ingress_receipt, m) {
    m.doc() = "Private C++23 Strict Quad fixed-pair authority ingress";
    m.def("validate_strict_quad_authority_ingress", &validate,
          py::arg("raw_sha"), py::arg("byte_count"), py::arg("points"),
          py::arg("triangles"), py::arg("receipt"));
}
