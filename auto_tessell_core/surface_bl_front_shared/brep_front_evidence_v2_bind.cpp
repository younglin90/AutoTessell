// C++23 validator for actual CAD/B-Rep edge provenance (default-off).

#include <pybind11/pybind11.h>

#include "brep_evidence_sha256.hpp"
#include "brep_contact_geometry.hpp"
#include "brep_occt_sdk_manifest_impl.hpp"

#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

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
    if (!evidence.contains("schema") ||
        py::cast<std::string>(evidence["schema"]) != "BRepFrontEvidence/v2") {
        return refusal("schema_mismatch");
    }
    if (!evidence.contains("source_digest") ||
        py::cast<std::string>(evidence["source_digest"]).size() != 64U) {
        return refusal("source_digest_missing");
    }
    for (const char* key : {"canonical_positions", "canonical_positions_digest",
                            "face_ordinal_digest", "orientation_digest", "seam_digest",
                            "authority", "triangles", "edges",
                            "non_manifold_edge_count", "missing_edge_polygon_count"}) {
        if (!evidence.contains(key)) return refusal("v2_record_incomplete");
    }
    if (evidence["canonical_positions_digest"].cast<std::string>().size() != 64U ||
        evidence["face_ordinal_digest"].cast<std::string>().size() != 64U ||
        evidence["orientation_digest"].cast<std::string>().size() != 64U ||
        evidence["seam_digest"].cast<std::string>().size() != 64U) {
        return refusal("v2_digest_invalid");
    }
    if (evidence["non_manifold_edge_count"].cast<std::int64_t>() != 0 ||
        evidence["missing_edge_polygon_count"].cast<std::int64_t>() != 0) {
        return refusal("authority_gap_present");
    }
    const auto authority = evidence["authority"].cast<py::dict>();
    for (const char* key : {"face_ordinals", "orientation", "seam_connectivity"}) {
        if (!authority.contains(key) || !authority[key].cast<bool>()) {
            return refusal("authority_incomplete");
        }
    }
    const auto positions = evidence["canonical_positions"].cast<py::sequence>();
    for (const py::handle item : positions) {
        if (item.cast<py::sequence>().size() != 3U) return refusal("canonical_position_invalid");
    }

    const auto triangles = evidence["triangles"].cast<py::list>();
    const auto edges = evidence["edges"].cast<py::list>();
    std::set<std::int64_t> triangle_ids;
    std::set<std::int64_t> edge_ids;
    std::set<std::int64_t> referenced_edges;
    std::set<std::pair<std::int64_t, std::int64_t>> referenced_segments;
    std::set<std::pair<std::int64_t, std::int64_t>> declared_segments;
    std::set<std::int64_t> canonical_vertices;
    std::unordered_map<std::int64_t, std::int64_t> triangle_faces;
    std::unordered_map<std::int64_t, std::uint8_t> triangle_orientation;
    std::unordered_map<std::int64_t, std::array<std::int64_t, 3>> triangle_canonical;
    for (const py::handle item : triangles) {
        const auto triangle = item.cast<py::dict>();
        for (const char* key : {"triangle_id", "brep_face_id", "canonical_vertices",
                                "raw_vertices", "orientation_reversed", "brep_edge_ids",
                                "brep_edge_segment_ids", "brep_edge_segment_parameters"}) {
            if (!triangle.contains(key)) return refusal("v2_triangle_record_incomplete");
        }
        const auto triangle_id = triangle["triangle_id"].cast<std::int64_t>();
        const auto face_id = triangle["brep_face_id"].cast<std::int64_t>();
        const auto canonical = triangle["canonical_vertices"].cast<py::sequence>();
        const auto raw = triangle["raw_vertices"].cast<py::sequence>();
        const auto mapped_edges = triangle["brep_edge_ids"].cast<py::sequence>();
        const auto mapped_segment_ids = triangle["brep_edge_segment_ids"].cast<py::sequence>();
        const auto mapped_parameters = triangle["brep_edge_segment_parameters"].cast<py::sequence>();
        if (triangle_id < 0 || face_id < 0 || canonical.size() != 3U || raw.size() != 3U ||
            mapped_edges.size() != 3U || mapped_segment_ids.size() != 3U || mapped_parameters.size() != 3U) {
            return refusal("v2_triangle_record_invalid");
        }
        if (!triangle_ids.insert(triangle_id).second) return refusal("duplicate_triangle_id");
        triangle_faces.emplace(triangle_id, face_id);
        triangle_orientation.emplace(triangle_id, triangle["orientation_reversed"].cast<bool>() ? 1U : 0U);
        std::set<std::int64_t> local_vertices;
        for (const py::handle value : canonical) {
            const auto vertex = value.cast<std::int64_t>();
            if (vertex < 0 || static_cast<std::size_t>(vertex) >= positions.size() ||
                !local_vertices.insert(vertex).second) {
                return refusal("canonical_triangle_degenerate_or_unknown");
            }
            canonical_vertices.insert(vertex);
        }
        triangle_canonical.emplace(
            triangle_id,
            std::array<std::int64_t, 3>{canonical[0].cast<std::int64_t>(),
                                        canonical[1].cast<std::int64_t>(),
                                        canonical[2].cast<std::int64_t>()});
        for (std::size_t slot = 0; slot < 3U; ++slot) {
            const auto edge_id = mapped_edges[slot].cast<std::int64_t>();
            const auto segment_id = mapped_segment_ids[slot].cast<std::int64_t>();
            const auto parameters = mapped_parameters[slot].cast<py::sequence>();
            if (parameters.size() != 2U) return refusal("triangle_edge_parameter_invalid");
            const double t0 = parameters[0].cast<double>();
            const double t1 = parameters[1].cast<double>();
            if (edge_id < -1) return refusal("triangle_edge_id_invalid");
            if (edge_id < 0) {
                if (segment_id != -1 || !std::isnan(t0) || !std::isnan(t1)) return refusal("diagonal_segment_invalid");
            } else {
                if (segment_id < 0 || !std::isfinite(t0) || !std::isfinite(t1) || t0 < 0.0 || t0 > 1.0 || t1 < 0.0 || t1 > 1.0 || t0 == t1) return refusal("triangle_edge_parameter_invalid");
                referenced_edges.insert(edge_id);
                referenced_segments.emplace(edge_id, segment_id);
            }
        }
    }

    if (triangle_ids.size() != triangles.size()) return refusal("triangle_count_mismatch");
    std::vector<std::uint8_t> position_bytes;
    for (const py::handle item : positions) {
        const auto point = item.cast<py::sequence>();
        for (const py::handle value : point) {
            const double coordinate = value.cast<double>();
            if (!std::isfinite(coordinate)) return refusal("canonical_position_nonfinite");
            brep_evidence::append_little_endian(position_bytes, coordinate);
        }
    }
    if (brep_evidence::sha256_hex(position_bytes) !=
        evidence["canonical_positions_digest"].cast<std::string>()) {
        return refusal("canonical_positions_digest_mismatch");
    }
    std::vector<std::uint8_t> face_ordinal_bytes;
    std::vector<std::uint8_t> orientation_bytes;
    std::vector<std::uint8_t> seam_bytes;
    for (std::int64_t triangle_id = 0; triangle_id < static_cast<std::int64_t>(triangles.size()); ++triangle_id) {
        if (!triangle_faces.contains(triangle_id) || !triangle_orientation.contains(triangle_id) ||
            !triangle_canonical.contains(triangle_id)) {
            return refusal("triangle_ids_not_contiguous");
        }
        brep_evidence::append_little_endian(face_ordinal_bytes, triangle_faces.at(triangle_id));
        orientation_bytes.push_back(triangle_orientation.at(triangle_id));
        for (const auto vertex : triangle_canonical.at(triangle_id)) {
            brep_evidence::append_little_endian(seam_bytes, vertex);
        }
    }
    if (brep_evidence::sha256_hex(face_ordinal_bytes) !=
            evidence["face_ordinal_digest"].cast<std::string>() ||
        brep_evidence::sha256_hex(orientation_bytes) !=
            evidence["orientation_digest"].cast<std::string>() ||
        brep_evidence::sha256_hex(seam_bytes) != evidence["seam_digest"].cast<std::string>()) {
        return refusal("provenance_digest_mismatch");
    }

    for (const py::handle item : edges) {
        const auto edge = item.cast<py::dict>();
        for (const char* key : {"brep_edge_id", "is_actual_brep_edge", "owner_face_id",
                                "canonical_endpoints", "incident_faces", "incident_triangles",
                                "incident_triangles_by_face", "segments"}) {
            if (!edge.contains(key)) return refusal("v2_edge_record_incomplete");
        }
        const auto edge_id = edge["brep_edge_id"].cast<std::int64_t>();
        const auto owner = edge["owner_face_id"].cast<std::int64_t>();
        const auto endpoints = edge["canonical_endpoints"].cast<py::sequence>();
        const auto incident_faces = edge["incident_faces"].cast<py::sequence>();
        const auto incident_triangles = edge["incident_triangles"].cast<py::sequence>();
        const auto by_face = edge["incident_triangles_by_face"].cast<py::sequence>();
        const auto segments = edge["segments"].cast<py::sequence>();
        if (edge_id < 0 || !edge["is_actual_brep_edge"].cast<bool>() || owner < 0 ||
            endpoints.size() != 2U || incident_faces.size() == 0U ||
            incident_triangles.size() == 0U || by_face.size() == 0U || segments.size() == 0U ||
            endpoints[0].cast<std::int64_t>() == endpoints[1].cast<std::int64_t>()) {
            return refusal("v2_edge_record_invalid");
        }
        if (!edge_ids.insert(edge_id).second) return refusal("duplicate_brep_edge_id");
        bool owner_present = false;
        std::set<std::int64_t> faces;
        for (const py::handle value : incident_faces) {
            const auto face = value.cast<std::int64_t>();
            faces.insert(face);
            owner_present = owner_present || face == owner;
        }
        if (!owner_present) return refusal("owner_face_not_incident");
        for (const py::handle value : endpoints) {
            if (!canonical_vertices.contains(value.cast<std::int64_t>())) {
                return refusal("edge_vertex_not_in_triangle_contract");
            }
        }
        for (const py::handle segment_item : segments) {
            const auto segment = segment_item.cast<py::dict>();
            if (!segment.contains("segment_id") || !segment.contains("t0") || !segment.contains("t1")) {
                return refusal("edge_segment_record_incomplete");
            }
            const auto segment_id = segment["segment_id"].cast<std::int64_t>();
            const double t0 = segment["t0"].cast<double>();
            const double t1 = segment["t1"].cast<double>();
            if (segment_id < 0 || !std::isfinite(t0) || !std::isfinite(t1) || t0 < 0.0 || t0 > 1.0 || t1 < 0.0 || t1 > 1.0 || t0 == t1) {
                return refusal("edge_segment_record_invalid");
            }
            if (!declared_segments.emplace(edge_id, segment_id).second) {
                return refusal("duplicate_edge_segment_id");
            }
        }
        std::set<std::int64_t> listed_triangles;
        for (const py::handle value : incident_triangles) {
            const auto triangle = value.cast<std::int64_t>();
            if (!triangle_ids.contains(triangle)) return refusal("incident_triangle_unknown");
            listed_triangles.insert(triangle);
        }
        std::set<std::int64_t> grouped_triangles;
        for (const py::handle group_item : by_face) {
            const auto group = group_item.cast<py::dict>();
            if (!group.contains("face_id") || !group.contains("triangle_ids")) {
                return refusal("incident_triangle_group_incomplete");
            }
            const auto face = group["face_id"].cast<std::int64_t>();
            if (!faces.contains(face)) return refusal("incident_group_face_unknown");
            for (const py::handle value : group["triangle_ids"].cast<py::sequence>()) {
                const auto triangle = value.cast<std::int64_t>();
                if (!listed_triangles.contains(triangle) || triangle_faces[triangle] != face) {
                    return refusal("incident_group_triangle_mismatch");
                }
                grouped_triangles.insert(triangle);
            }
        }
        if (grouped_triangles != listed_triangles) return refusal("incident_group_incomplete");
    }
    for (const auto edge_id : referenced_edges) {
    for (const auto& segment : referenced_segments) {
        if (!declared_segments.contains(segment)) return refusal("triangle_edge_segment_unknown");
    }
        if (!edge_ids.contains(edge_id)) return refusal("triangle_edge_unknown");
    }

    py::dict result;
    result["accepted"] = true;
    result["status"] = "brep_evidence_v2_ready";
    result["schema"] = "BRepFrontEvidence/v2";
    result["source_digest"] = evidence["source_digest"];
    result["triangle_count"] = static_cast<std::int64_t>(triangle_ids.size());
    result["edge_count"] = static_cast<std::int64_t>(edge_ids.size());
    result["actual_edge_count"] = static_cast<std::int64_t>(edge_ids.size());
    result["canonical_vertex_count"] = static_cast<std::int64_t>(canonical_vertices.size());
    result["contact_policy"] = "explicit_owner_and_incident_face_witness_required";
    result["uncertain_is_refusal"] = true;
    return result;
}

#include "brep_contact_witness_impl.hpp"
#include "brep_contact_transaction_impl.hpp"
#include "brep_layer_input_impl.hpp"
#include "brep_direction_contract_impl.hpp"
py::dict classify(const py::dict& evidence, std::int64_t edge_id,
                  std::int64_t triangle_id, const std::string& geometric_class) {
    const py::dict validation = validate(evidence);
    if (!validation["accepted"].cast<bool>()) return validation;
    py::dict edge_record;
    py::dict triangle_record;
    bool edge_found = false;
    bool triangle_found = false;
    for (const py::handle item : evidence["edges"].cast<py::list>()) {
        if (item.cast<py::dict>()["brep_edge_id"].cast<std::int64_t>() == edge_id) {
            edge_record = item.cast<py::dict>();
            edge_found = true;
        }
    }
    for (const py::handle item : evidence["triangles"].cast<py::list>()) {
        if (item.cast<py::dict>()["triangle_id"].cast<std::int64_t>() == triangle_id) {
            triangle_record = item.cast<py::dict>();
            triangle_found = true;
        }
    }
    if (!edge_found || !triangle_found) return refusal("contact_record_unknown");
    const auto owner = edge_record["owner_face_id"].cast<std::int64_t>();
    const auto face = triangle_record["brep_face_id"].cast<std::int64_t>();
    bool incident = false;
    bool triangle_incident = false;
    bool owner_triangle = false;
    for (const py::handle value : edge_record["incident_faces"].cast<py::sequence>()) {
        incident = incident || value.cast<std::int64_t>() == face;
    }
    for (const py::handle group_item : edge_record["incident_triangles_by_face"].cast<py::sequence>()) {
        const auto group = group_item.cast<py::dict>();
        const auto group_face = group["face_id"].cast<std::int64_t>();
        for (const py::handle value : group["triangle_ids"].cast<py::sequence>()) {
            if (value.cast<std::int64_t>() == triangle_id) {
                triangle_incident = true;
                owner_triangle = owner_triangle || group_face == owner;
            }
        }
    }
    const bool same_owner = owner == face;
    const bool permitted = geometric_class == "none" ||
        (geometric_class == "base_touch" && same_owner && owner_triangle) ||
        (geometric_class == "seam_touch" && incident && triangle_incident && !same_owner);
    py::dict result;
    result["accepted"] = true;
    result["geometric_class"] = geometric_class;
    result["same_owner_face"] = same_owner;
    result["incident_face"] = incident;
    result["triangle_incident"] = triangle_incident;
    result["permitted"] = permitted;
    result["decision"] = permitted ? "permitted_contact" : "forbidden_or_uncertain_refusal";
    result["contact_policy"] = "explicit_owner_and_incident_face_witness_required";
    return result;
}

py::dict occt_native_pcurve_preflight_v2() {
#if __has_include(<BRep_Tool.hxx>) && __has_include(<BRepAdaptor_Curve2d.hxx>)
    constexpr bool headers_available = true;
#else
    constexpr bool headers_available = false;
#endif
#if defined(AUTOTESSSELL_OCCT_NATIVE_ENABLED)
    constexpr bool occt_linked = true;
#else
    constexpr bool occt_linked = false;
#endif
    py::dict result;
    result["available"] = false;
    result["status"] = "occt_native_ingress_unavailable";
    result["occt_headers_available"] = headers_available;
    result["occt_linked"] = occt_linked;
    result["sdk_manifest_ready"] = headers_available && occt_linked;
    result["indexed_curve_on_surface"] = false;
    result["is_stored_authoritative"] = false;
    result["reason"] = !headers_available
        ? "occt_headers_unavailable"
        : (!occt_linked ? "occt_linkage_not_configured" : "indexed_shim_not_built");
    return result;
}

}  // namespace

PYBIND11_MODULE(native_brep_front_evidence_v2, module) {
    module.doc() = "Default-off C++23 actual B-Rep edge evidence validator";
    module.def("validate_brep_front_evidence_v2", &validate, py::arg("evidence"));
    module.def("classify_brep_contact_v2", &classify, py::arg("evidence"),
               py::arg("edge_id"), py::arg("triangle_id"), py::arg("geometric_class"));
    module.def("witness_brep_contact_v2", &witness, py::arg("evidence"),
               py::arg("edge_id"), py::arg("candidate_face_id"),
               py::arg("candidate_vertices"));
    module.def("prepare_brep_layer_input_v2", &prepare_brep_layer_input_v2,
               py::arg("evidence"), py::arg("requested_layers"));
    module.def("validate_brep_direction_contract_v2",
               &validate_brep_direction_contract_v2, py::arg("ledger"), py::arg("records"));
    module.def("plan_brep_shared_surface_wall_edge_front",
               &plan_brep_shared_surface_wall_edge_front, py::arg("evidence"),
               py::arg("requested_layers"), py::arg("candidates"));
    module.def("occt_native_pcurve_preflight_v2", &occt_native_pcurve_preflight_v2);
    module.def("audit_occt_sdk_manifest_v2", &autotessell_occt::audit_sdk_manifest,
               py::arg("sdk_root"), py::arg("runtime_root"),
               py::arg("expected_occt_version"),
               py::arg("expected_runtime_package"));
}
