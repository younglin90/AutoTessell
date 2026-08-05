#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <cstdint>
#include <set>
#include <string>

namespace py = pybind11;

py::dict refuse(const char* reason) {
    py::dict r;
    r["accepted"] = false;
    r["status"] = "tri_quad_authority_ingress_refused";
    r["reason"] = reason;
    r["eligible_for_tri_quad_bl"] = false;
    r["actual_layers"] = 0;
    r["publication_eligible"] = false;
    r["candidate_discarded"] = true;
    r["runtime_route"] = "private_default_off";
    r["route_calls"] = 0;
    return r;
}
bool text(const py::dict& d, const char* k) {
    return d.contains(k) && !d[k].is_none() && !py::str(d[k]).cast<std::string>().empty();
}
bool hex64(const std::string& s) {
    if (s.size() != 64) return false;
    return std::all_of(s.begin(), s.end(), [](char c) { return std::isdigit(c) || (c >= 'a' && c <= 'f'); });
}
bool face_records(const py::object& value, const char* kind, std::set<std::string>& ids) {
    if (!py::isinstance<py::list>(value)) return false;
    for (const py::handle& h : value.cast<py::list>()) {
        if (!py::isinstance<py::dict>(h)) return false;
        py::dict row = h.cast<py::dict>();
        for (const char* k : {"face_id", "feature", "patch", "physical_group", "component", "provenance"}) if (!text(row, k)) return false;
        std::string id = std::string(kind) + ":" + py::str(row["face_id"]).cast<std::string>();
        if (!ids.insert(id).second) return false;
    }
    return true;
}
py::dict validate(const std::string& raw_sha, std::int64_t bytes,
                  const py::sequence& points, const py::sequence& triangles,
                  const py::sequence& quads, const py::dict& receipt) {
    if (!hex64(raw_sha) || bytes <= 0) return refuse("tri_quad_raw_digest_invalid");
    if (!text(receipt, "schema") || py::str(receipt["schema"]).cast<std::string>() != "TriQuadAuthorityReceipt/v1") return refuse("tri_quad_schema_unsupported");
    for (const char* k : {"source_sha256", "reader_id", "issuer", "provenance", "point_digest", "triangle_digest", "quad_digest", "product_identity"}) if (!text(receipt, k)) return refuse("tri_quad_receipt_header_incomplete");
    if (py::str(receipt["source_sha256"]).cast<std::string>() != raw_sha || !receipt.contains("source_byte_count") || receipt["source_byte_count"].cast<std::int64_t>() != bytes) return refuse("tri_quad_source_digest_mismatch");
    if (py::str(receipt["product_identity"]).cast<std::string>() != "tri_plus_quad" || (receipt.contains("tri_clone") && receipt["tri_clone"].cast<bool>()) || (receipt.contains("quad_relabel") && receipt["quad_relabel"].cast<bool>())) return refuse("tri_quad_product_identity_invalid");
    if (!receipt.contains("trust_policy") || !py::isinstance<py::dict>(receipt["trust_policy"]) || receipt["trust_policy"].cast<py::dict>().empty()) return refuse("tri_quad_trust_policy_missing");
    if (points.empty() || triangles.empty() || quads.empty()) return refuse("tri_quad_mixed_faces_missing");
    std::set<std::string> ids;
    if (!face_records(receipt["triangles"], "tri", ids) || !face_records(receipt["quads"], "quad", ids)) return refuse("tri_quad_semantic_coverage_incomplete");
    if (receipt["triangles"].cast<py::list>().size() != triangles.size() || receipt["quads"].cast<py::list>().size() != quads.size()) return refuse("tri_quad_face_count_mismatch");
    if (!receipt.contains("mixed_lineage") || !py::isinstance<py::list>(receipt["mixed_lineage"]) || receipt["mixed_lineage"].cast<py::list>().empty()) return refuse("tri_quad_direct_lineage_missing");
    for (const py::handle& h : receipt["mixed_lineage"].cast<py::list>()) {
        if (!py::isinstance<py::dict>(h)) return refuse("tri_quad_direct_lineage_invalid");
        py::dict row = h.cast<py::dict>();
        for (const char* k : {"kind", "source_id", "output_ids", "feature", "patch", "physical_group", "component", "provenance"}) if (!text(row, k) && std::string(k) != "output_ids") return refuse("tri_quad_direct_lineage_incomplete");
        if (!row.contains("output_ids") || !py::isinstance<py::sequence>(row["output_ids"]) || row["output_ids"].cast<py::sequence>().empty()) return refuse("tri_quad_direct_lineage_incomplete");
        std::string kind = py::str(row["kind"]).cast<std::string>();
        if (kind != "tri" && kind != "quad" && kind != "bl_strip_quad") return refuse("tri_quad_direct_lineage_kind_invalid");
    }
    bool wall = receipt.contains("wall_loop") && py::isinstance<py::list>(receipt["wall_loop"]) && !receipt["wall_loop"].cast<py::list>().empty();
    if (wall) {
        for (const py::handle& h : receipt["wall_loop"].cast<py::list>()) {
            if (!py::isinstance<py::dict>(h)) return refuse("tri_quad_wall_loop_invalid");
            py::dict row = h.cast<py::dict>();
            for (const char* k : {"edge_id", "feature", "patch", "physical_group", "component", "provenance"}) if (!text(row, k)) return refuse("tri_quad_wall_loop_incomplete");
        }
    }
    py::dict result;
    result["accepted"] = true;
    result["status"] = "tri_quad_authority_ingress_sealed";
    result["reason"] = wall ? "tri_quad_mixed_authority_and_wall_verified" : "tri_quad_mixed_source_verified_wall_boundary_absent";
    result["eligible_for_tri_quad_bl"] = wall;
    result["wall_boundary_available"] = wall;
    result["actual_layers"] = 0;
    result["publication_eligible"] = false;
    result["candidate_discarded"] = false;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["triangle_count"] = triangles.size();
    result["quad_count"] = quads.size();
    result["lineage_count"] = receipt["mixed_lineage"].cast<py::list>().size();
    result["authority_schema"] = "TriQuadAuthorityReceipt/v1";
    return result;
}
PYBIND11_MODULE(native_tri_quad_authority_ingress_receipt, m) {
    m.doc() = "Private C++23 TRI+QUAD mixed authority ingress";
    m.def("validate_tri_quad_authority_ingress", &validate, py::arg("raw_sha"), py::arg("byte_count"), py::arg("points"), py::arg("triangles"), py::arg("quads"), py::arg("receipt"));
}
