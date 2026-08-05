#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace py = pybind11;
using T = std::array<std::int64_t, 3>;

py::dict refuse(const char* reason) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "native_tri_authority_ingress_refused";
    result["reason"] = reason;
    result["eligible_for_tri_bl"] = false;
    result["actual_layers"] = 0;
    result["publication_eligible"] = false;
    result["candidate_discarded"] = true;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    return result;
}

bool text(const py::dict& value, const char* key) {
    return value.contains(key) && !value[key].is_none() &&
           !py::str(value[key]).cast<std::string>().empty();
}

bool hex64(const std::string& value) {
    if (value.size() != 64) return false;
    return std::all_of(value.begin(), value.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    });
}

py::dict validate(
    const std::string& raw_sha256,
    std::int64_t byte_count,
    const py::sequence& points,
    const py::sequence& triangles,
    const py::sequence& orientation,
    const py::dict& receipt) {
    if (!hex64(raw_sha256) || byte_count <= 0) return refuse("raw_source_digest_or_size_invalid");
    if (!text(receipt, "schema") || py::str(receipt["schema"]).cast<std::string>() != "NativeTriAuthorityReceipt/v1") {
        return refuse("tri_receipt_schema_unsupported");
    }
    for (const char* key : {"source_kind", "source_sha256", "reader_id", "issuer",
                            "provenance", "point_digest", "triangle_digest",
                            "orientation_digest"}) {
        if (!text(receipt, key)) return refuse("tri_receipt_header_incomplete");
    }
    std::string source_kind = py::str(receipt["source_kind"]).cast<std::string>();
    if (source_kind != "stl" && source_kind != "step") return refuse("tri_source_kind_unsupported");
    if (py::str(receipt["source_sha256"]).cast<std::string>() != raw_sha256 ||
        !receipt.contains("source_byte_count") ||
        receipt["source_byte_count"].cast<std::int64_t>() != byte_count) {
        return refuse("tri_source_digest_or_size_mismatch");
    }
    if (!receipt.contains("trust_policy") || !py::isinstance<py::dict>(receipt["trust_policy"]) ||
        receipt["trust_policy"].cast<py::dict>().empty()) {
        return refuse("tri_trust_policy_missing");
    }
    if (points.empty() || triangles.empty() || orientation.size() != triangles.size()) {
        return refuse("tri_canonical_arrays_incomplete");
    }
    std::vector<std::array<double, 3>> xyz;
    xyz.reserve(points.size());
    for (const py::handle& item : points) {
        if (!py::isinstance<py::sequence>(item)) return refuse("tri_point_record_invalid");
        py::sequence row = item.cast<py::sequence>();
        if (row.size() != 3) return refuse("tri_point_record_invalid");
        std::array<double, 3> p{row[0].cast<double>(), row[1].cast<double>(), row[2].cast<double>()};
        if (!std::isfinite(p[0]) || !std::isfinite(p[1]) || !std::isfinite(p[2])) return refuse("tri_point_not_finite");
        xyz.push_back(p);
    }
    std::vector<T> faces;
    std::set<T> face_set;
    std::map<std::pair<std::int64_t, std::int64_t>, std::vector<std::int64_t>> edge_faces;
    for (size_t i = 0; i < triangles.size(); ++i) {
        if (!py::isinstance<py::sequence>(triangles[i])) return refuse("tri_face_record_invalid");
        py::sequence row = triangles[i].cast<py::sequence>();
        if (row.size() != 3) return refuse("tri_face_record_invalid");
        T face{row[0].cast<std::int64_t>(), row[1].cast<std::int64_t>(), row[2].cast<std::int64_t>()};
        if (face[0] < 0 || face[1] < 0 || face[2] < 0 ||
            face[0] >= static_cast<std::int64_t>(xyz.size()) ||
            face[1] >= static_cast<std::int64_t>(xyz.size()) ||
            face[2] >= static_cast<std::int64_t>(xyz.size()) ||
            face[0] == face[1] || face[0] == face[2] || face[1] == face[2]) {
            return refuse("tri_face_index_or_degeneracy_invalid");
        }
        T sorted = face;
        std::sort(sorted.begin(), sorted.end());
        if (!face_set.insert(sorted).second) return refuse("tri_duplicate_source_face");
        faces.push_back(face);
        for (int e = 0; e < 3; ++e) {
            auto a = face[e], b = face[(e + 1) % 3];
            if (a > b) std::swap(a, b);
            edge_faces[{a, b}].push_back(static_cast<std::int64_t>(i));
        }
    }
    if (!receipt.contains("faces") || !py::isinstance<py::list>(receipt["faces"])) return refuse("tri_face_authority_missing");
    py::list records = receipt["faces"].cast<py::list>();
    if (records.size() != faces.size()) return refuse("tri_face_coverage_incomplete");
    for (size_t i = 0; i < records.size(); ++i) {
        if (!py::isinstance<py::dict>(records[i])) return refuse("tri_face_authority_record_invalid");
        py::dict record = records[i].cast<py::dict>();
        for (const char* key : {"face_id", "feature", "patch", "physical_group", "component", "provenance"}) {
            if (!text(record, key)) return refuse("tri_face_semantic_label_incomplete");
        }
        if (record["face_id"].cast<std::int64_t>() != static_cast<std::int64_t>(i) ||
            !record.contains("vertices") || !py::isinstance<py::sequence>(record["vertices"])) {
            return refuse("tri_face_id_or_vertex_binding_mismatch");
        }
        py::sequence vertices = record["vertices"].cast<py::sequence>();
        if (vertices.size() != 3 ||
            vertices[0].cast<std::int64_t>() != faces[i][0] ||
            vertices[1].cast<std::int64_t>() != faces[i][1] ||
            vertices[2].cast<std::int64_t>() != faces[i][2]) {
            return refuse("tri_face_id_or_vertex_binding_mismatch");
        }
    }
    bool wall_available = false;
    std::set<std::pair<std::int64_t, std::int64_t>> declared_edges;
    std::set<std::pair<std::string, std::int64_t>> curve_order;
    if (receipt.contains("wall_edges") && py::isinstance<py::list>(receipt["wall_edges"])) {
        py::list walls = receipt["wall_edges"].cast<py::list>();
        for (const py::handle& item : walls) {
            if (!py::isinstance<py::dict>(item)) return refuse("tri_wall_edge_record_invalid");
            py::dict wall = item.cast<py::dict>();
            for (const char* key : {"edge_id", "curve_id", "owner_face", "feature", "patch", "physical_group", "component", "provenance"}) {
                if (!text(wall, key)) return refuse("tri_wall_edge_label_incomplete");
            }
            if (!wall.contains("endpoints") || !py::isinstance<py::sequence>(wall["endpoints"]) ||
                !wall.contains("directed") || !wall["directed"].cast<bool>() ||
                !wall.contains("order_index")) return refuse("tri_wall_edge_direction_missing");
            py::sequence endpoints = wall["endpoints"].cast<py::sequence>();
            if (endpoints.size() != 2) return refuse("tri_wall_edge_record_invalid");
            std::int64_t a = endpoints[0].cast<std::int64_t>(), b = endpoints[1].cast<std::int64_t>();
            if (a == b || a < 0 || b < 0 || a >= static_cast<std::int64_t>(xyz.size()) || b >= static_cast<std::int64_t>(xyz.size())) {
                return refuse("tri_wall_edge_endpoint_invalid");
            }
            auto key = std::minmax(a, b);
            if (!declared_edges.insert(key).second || edge_faces[key].size() != 1 ||
                edge_faces[key][0] != wall["owner_face"].cast<std::int64_t>()) {
                return refuse("tri_wall_edge_not_source_boundary");
            }
            std::string curve = py::str(wall["curve_id"]).cast<std::string>();
            std::int64_t order = wall["order_index"].cast<std::int64_t>();
            if (!curve_order.insert({curve, order}).second) return refuse("tri_wall_curve_order_duplicate");
            wall_available = true;
        }
    }
    if (source_kind == "step" && (!receipt.contains("brep_face_map") || !py::isinstance<py::dict>(receipt["brep_face_map"]) ||
                                   receipt["brep_face_map"].cast<py::dict>().empty())) {
        return refuse("tri_cad_brep_map_missing");
    }
    py::dict result;
    result["accepted"] = true;
    result["status"] = "native_tri_authority_ingress_sealed";
    result["reason"] = wall_available ? "tri_source_and_wall_authority_verified" : "tri_source_verified_wall_boundary_absent";
    result["eligible_for_tri_bl"] = wall_available;
    result["wall_boundary_available"] = wall_available;
    result["actual_layers"] = 0;
    result["publication_eligible"] = false;
    result["candidate_discarded"] = false;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["source_kind"] = source_kind;
    result["source_sha256"] = raw_sha256;
    result["source_byte_count"] = byte_count;
    result["face_count"] = faces.size();
    result["boundary_edge_count"] = declared_edges.size();
    result["authority_schema"] = "NativeTriAuthorityReceipt/v1";
    return result;
}

PYBIND11_MODULE(native_tri_authority_ingress_receipt, module) {
    module.doc() = "Private C++23 Native Tri source authority ingress receipt";
    module.def("validate_native_tri_authority_ingress", &validate,
               py::arg("raw_sha256"), py::arg("byte_count"), py::arg("points"),
               py::arg("triangles"), py::arg("orientation"), py::arg("receipt"));
}
