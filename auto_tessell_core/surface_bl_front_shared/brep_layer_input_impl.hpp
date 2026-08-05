#pragma once

#include <cstdint>

// Build the authoritative deterministic wall-edge sector ledger after the
// complete v2 evidence validator accepts the source contract. This is a
// preparation step: it does not invent normals or generate layers.
inline py::dict prepare_brep_layer_input_v2(const py::dict& evidence,
                                            std::int64_t requested_layers) {
    const py::dict validation = validate(evidence);
    if (!validation["accepted"].cast<bool>()) return validation;
    if (requested_layers < 0) return refusal("negative_layer_count");

    py::list sectors;
    std::int64_t non_manifold_sector_count = 0;
    for (const py::handle edge_item : evidence["edges"].cast<py::sequence>()) {
        const py::dict edge = edge_item.cast<py::dict>();
        const std::int64_t edge_id = edge["brep_edge_id"].cast<std::int64_t>();
        const std::int64_t owner_face = edge["owner_face_id"].cast<std::int64_t>();
        const py::sequence endpoints = edge["canonical_endpoints"].cast<py::sequence>();
        const py::sequence groups = edge["incident_triangles_by_face"].cast<py::sequence>();
        const py::sequence segments = edge["segments"].cast<py::sequence>();
        if (groups.size() > 2U) {
            ++non_manifold_sector_count;
            continue;
        }
        for (const py::handle group_item : groups) {
            const py::dict group = group_item.cast<py::dict>();
            const std::int64_t face_id = group["face_id"].cast<std::int64_t>();
            for (const py::handle segment_item : segments) {
                const py::dict segment = segment_item.cast<py::dict>();
                py::dict sector;
                sector["sector_id"] = static_cast<std::int64_t>(sectors.size());
                sector["brep_edge_id"] = edge_id;
                sector["owner_face_id"] = owner_face;
                sector["incident_face_id"] = face_id;
                sector["segment_id"] = segment["segment_id"];
                sector["t0"] = segment["t0"];
                sector["t1"] = segment["t1"];
                sector["canonical_endpoints"] = endpoints;
                sector["triangle_ids"] = group["triangle_ids"];
                sector["source_digest"] = evidence["source_digest"];
                sectors.append(sector);
            }
        }
    }
    if (non_manifold_sector_count != 0) {
        return refusal("non_manifold_brep_edge_incidence");
    }
    if (sectors.size() == 0U && requested_layers > 0) {
        return refusal("missing_brep_layer_sectors");
    }

    py::dict result;
    result["accepted"] = true;
    result["status"] = "brep_layer_input_ready";
    result["schema"] = "BRepLayerInput/v1";
    result["source_digest"] = evidence["source_digest"];
    result["requested_layers"] = requested_layers;
    result["sector_count"] = static_cast<std::int64_t>(sectors.size());
    result["sectors"] = sectors;
    result["authority"] = evidence["authority"];
    result["source_metadata"] = evidence.contains("source_metadata")
        ? evidence["source_metadata"] : py::dict();
    result["runtime_route"] = "default_off_brep_diagnostic";
    result["candidate_generation"] = "cxx_authoritative_brep_layer_input";
    result["count_is_report_only"] = true;
    return result;
}
