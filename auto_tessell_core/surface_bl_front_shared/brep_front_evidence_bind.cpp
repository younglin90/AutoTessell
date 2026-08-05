// C++23 default-off B-Rep front evidence contract and contact policy.

#include <pybind11/pybind11.h>

#include <cstdint>
#include <set>
#include <string>

namespace py = pybind11;

namespace {

py::dict refusal(const std::string& reason) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "refused_brep_evidence";
    result["reason"] = reason;
    result["contact_policy"] = "fail_closed";
    return result;
}

py::dict validate(const py::dict& evidence) {
    if (!evidence.contains("schema") || py::cast<std::string>(evidence["schema"]) != "BRepFrontEvidence/v1") return refusal("schema_mismatch");
    if (!evidence.contains("source_digest") || py::cast<std::string>(evidence["source_digest"]).size() != 64U) return refusal("source_digest_missing");
    if (!evidence.contains("triangles") || !evidence.contains("edges")) return refusal("topology_records_missing");
    const auto triangles = evidence["triangles"].cast<py::list>();
    const auto edges = evidence["edges"].cast<py::list>();
    std::set<std::int64_t> triangle_ids;
    std::set<std::int64_t> edge_ids;
    std::set<std::int64_t> canonical_vertices;
    for (const py::handle item : triangles) {
        const auto triangle = item.cast<py::dict>();
        if (!triangle.contains("triangle_id") || !triangle.contains("brep_face_id") || !triangle.contains("canonical_vertices") || !triangle.contains("raw_vertices") || !triangle.contains("orientation_reversed")) return refusal("triangle_record_incomplete");
        const auto triangle_id = triangle["triangle_id"].cast<std::int64_t>();
        const auto face_id = triangle["brep_face_id"].cast<std::int64_t>();
        const auto canonical = triangle["canonical_vertices"].cast<py::sequence>();
        const auto raw = triangle["raw_vertices"].cast<py::sequence>();
        if (triangle_id < 0 || face_id < 0 || canonical.size() != 3 || raw.size() != 3) return refusal("triangle_record_invalid");
        if (!triangle_ids.insert(triangle_id).second) return refusal("duplicate_triangle_id");
        std::set<std::int64_t> local_vertices;
        for (const py::handle value : canonical) {
            const auto vertex = value.cast<std::int64_t>();
            if (vertex < 0 || !local_vertices.insert(vertex).second) return refusal("canonical_triangle_degenerate");
            canonical_vertices.insert(vertex);
        }
    }
    for (const py::handle item : edges) {
        const auto edge = item.cast<py::dict>();
        if (!edge.contains("brep_edge_id") || !edge.contains("owner_face_id") || !edge.contains("canonical_endpoints") || !edge.contains("incident_faces") || !edge.contains("incident_triangles")) return refusal("edge_record_incomplete");
        const auto edge_id = edge["brep_edge_id"].cast<std::int64_t>();
        const auto owner = edge["owner_face_id"].cast<std::int64_t>();
        const auto endpoints = edge["canonical_endpoints"].cast<py::sequence>();
        const auto incident_faces = edge["incident_faces"].cast<py::sequence>();
        const auto incident_triangles = edge["incident_triangles"].cast<py::sequence>();
        if (edge_id < 0 || owner < 0 || endpoints.size() != 2 || incident_faces.size() == 0 || incident_triangles.size() == 0) return refusal("edge_record_invalid");
        if (!edge_ids.insert(edge_id).second) return refusal("duplicate_brep_edge_id");
        if (endpoints[0].cast<std::int64_t>() == endpoints[1].cast<std::int64_t>()) return refusal("canonical_edge_degenerate");
        bool owner_present = false;
        for (const py::handle face : incident_faces) owner_present = owner_present || face.cast<std::int64_t>() == owner;
        if (!owner_present) return refusal("owner_face_not_incident");
        for (const py::handle vertex : endpoints) if (!canonical_vertices.contains(vertex.cast<std::int64_t>())) return refusal("edge_vertex_not_in_triangle_contract");
        for (const py::handle triangle : incident_triangles) if (!triangle_ids.contains(triangle.cast<std::int64_t>())) return refusal("incident_triangle_unknown");
    }
    py::dict result;
    result["accepted"] = true;
    result["status"] = "brep_evidence_ready";
    result["schema"] = "BRepFrontEvidence/v1";
    result["source_digest"] = evidence["source_digest"];
    result["triangle_count"] = static_cast<std::int64_t>(triangle_ids.size());
    result["edge_count"] = static_cast<std::int64_t>(edge_ids.size());
    result["canonical_vertex_count"] = static_cast<std::int64_t>(canonical_vertices.size());
    result["contact_policy"] = "owner_face_or_verified_seam_only";
    result["uncertain_is_refusal"] = true;
    return result;
}

py::dict classify(const py::dict& evidence, std::int64_t edge_id, std::int64_t triangle_id, const std::string& geometric_class) {
    const py::dict validation = validate(evidence);
    if (!validation["accepted"].cast<bool>()) return validation;
    py::dict edge_record;
    py::dict triangle_record;
    bool edge_found = false;
    bool triangle_found = false;
    for (const py::handle item : evidence["edges"].cast<py::list>()) if (item.cast<py::dict>()["brep_edge_id"].cast<std::int64_t>() == edge_id) { edge_record = item.cast<py::dict>(); edge_found = true; }
    for (const py::handle item : evidence["triangles"].cast<py::list>()) if (item.cast<py::dict>()["triangle_id"].cast<std::int64_t>() == triangle_id) { triangle_record = item.cast<py::dict>(); triangle_found = true; }
    if (!edge_found || !triangle_found) return refusal("contact_record_unknown");
    const auto owner = edge_record["owner_face_id"].cast<std::int64_t>();
    const auto face = triangle_record["brep_face_id"].cast<std::int64_t>();
    bool incident = false;
    for (const py::handle value : edge_record["incident_faces"].cast<py::sequence>()) incident = incident || value.cast<std::int64_t>() == face;
    const bool same_owner = owner == face;
    const bool permitted = geometric_class == "none" || (geometric_class == "base_touch" && same_owner) || (geometric_class == "seam_touch" && incident);
    py::dict result;
    result["accepted"] = true;
    result["geometric_class"] = geometric_class;
    result["same_owner_face"] = same_owner;
    result["incident_face"] = incident;
    result["permitted"] = permitted;
    result["decision"] = permitted ? "permitted_contact" : "forbidden_or_uncertain_refusal";
    result["contact_policy"] = "owner_face_or_verified_seam_only";
    return result;
}

}  // namespace

PYBIND11_MODULE(native_brep_front_evidence, module)
{
    module.doc() = "Default-off C++23 B-Rep front evidence validator";
    module.def("validate_brep_front_evidence", &validate, py::arg("evidence"));
    module.def("classify_brep_contact", &classify, py::arg("evidence"), py::arg("edge_id"), py::arg("triangle_id"), py::arg("geometric_class"));
}
