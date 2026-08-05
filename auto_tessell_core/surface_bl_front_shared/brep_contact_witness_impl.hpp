#pragma once

#include <algorithm>
#include <array>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>

inline py::dict witness(const py::dict& evidence, std::int64_t edge_id,
                        std::int64_t candidate_face_id, const py::sequence& candidate_vertices) {
    const py::dict validation = validate(evidence);
    if (!validation["accepted"].cast<bool>()) return validation;
    if (candidate_vertices.size() != 3U) return refusal("candidate_triangle_invalid");
    const auto positions = evidence["canonical_positions"].cast<py::sequence>();
    const auto to_vec = [](const py::handle item) {
        const auto point = item.cast<py::sequence>();
        return brep_contact::Vec3{point[0].cast<double>(), point[1].cast<double>(), point[2].cast<double>()};
    };
    std::array<brep_contact::Vec3, 3> candidate{};
    for (std::size_t i = 0; i < 3U; ++i) {
        candidate[i] = to_vec(candidate_vertices[i]);
        if (!brep_contact::finite(candidate[i])) return refusal("candidate_nonfinite");
    }
    py::dict edge_record;
    bool edge_found = false;
    for (const py::handle item : evidence["edges"].cast<py::list>()) {
        if (item.cast<py::dict>()["brep_edge_id"].cast<std::int64_t>() == edge_id) {
            edge_record = item.cast<py::dict>();
            edge_found = true;
        }
    }
    if (!edge_found) return refusal("contact_edge_unknown");
    const auto endpoints = edge_record["canonical_endpoints"].cast<py::sequence>();
    const auto p0 = to_vec(positions[endpoints[0].cast<std::int64_t>()]);
    const auto p1 = to_vec(positions[endpoints[1].cast<std::int64_t>()]);
    const double scale = std::max({1.0, brep_contact::norm(p0), brep_contact::norm(p1),
                                   brep_contact::norm(candidate[0]), brep_contact::norm(candidate[1]),
                                   brep_contact::norm(candidate[2])});
    const double tolerance = 1.0e-9 * scale;
    int endpoint0 = -1;
    int endpoint1 = -1;
    for (int i = 0; i < 3; ++i) {
        if (brep_contact::distance(candidate[static_cast<std::size_t>(i)], p0) <= tolerance) endpoint0 = i;
        if (brep_contact::distance(candidate[static_cast<std::size_t>(i)], p1) <= tolerance) endpoint1 = i;
    }
    py::dict result;
    result["accepted"] = true;
    result["candidate_face_id"] = candidate_face_id;
    result["edge_id"] = edge_id;
    result["uncertain_is_refusal"] = true;
    result["contact_policy"] = "computed_actual_edge_segment_witness";
    if (endpoint0 < 0 || endpoint1 < 0 || endpoint0 == endpoint1) {
        result["geometric_class"] = "uncertain_endpoint_mismatch";
        result["witness"] = false;
        result["permitted"] = false;
        result["decision"] = "forbidden_or_uncertain_refusal";
        return result;
    }
    bool incident_face = false;
    py::sequence source_triangle_ids = py::tuple(0);
    for (const py::handle group_item : edge_record["incident_triangles_by_face"].cast<py::sequence>()) {
        const auto group = group_item.cast<py::dict>();
        if (group["face_id"].cast<std::int64_t>() == candidate_face_id) {
            incident_face = true;
            source_triangle_ids = group["triangle_ids"].cast<py::sequence>();
        }
    }
    if (!incident_face) {
        result["geometric_class"] = "forbidden_non_adjacent_face";
        result["witness"] = false;
        result["permitted"] = false;
        result["decision"] = "forbidden_or_uncertain_refusal";
        return result;
    }
    py::dict source_triangle;
    bool source_found = false;
    for (const py::handle triangle_item : evidence["triangles"].cast<py::list>()) {
        const auto triangle = triangle_item.cast<py::dict>();
        const auto triangle_id = triangle["triangle_id"].cast<std::int64_t>();
        bool listed = false;
        for (const py::handle value : source_triangle_ids) listed = listed || value.cast<std::int64_t>() == triangle_id;
        if (!listed) continue;
        const auto mapped = triangle["brep_edge_ids"].cast<py::sequence>();
        const auto mapped_segments = triangle["brep_edge_segment_ids"].cast<py::sequence>();
        for (std::size_t slot = 0; slot < 3U; ++slot) {
            if (mapped[slot].cast<std::int64_t>() == edge_id && mapped_segments[slot].cast<std::int64_t>() >= 0) {
                source_triangle = triangle;
                source_found = true;
            }
        }
    }
    if (!source_found) return refusal("contact_edge_triangle_unknown");
    const auto source_vertices = source_triangle["canonical_vertices"].cast<py::sequence>();
    const auto a = to_vec(positions[source_vertices[0].cast<std::int64_t>()]);
    const auto b = to_vec(positions[source_vertices[1].cast<std::int64_t>()]);
    const auto c = to_vec(positions[source_vertices[2].cast<std::int64_t>()]);
    const auto normal = brep_contact::cross(brep_contact::subtract(b, a), brep_contact::subtract(c, a));
    const double normal_length = brep_contact::norm(normal);
    const double candidate_area_twice = brep_contact::norm(
        brep_contact::cross(brep_contact::subtract(candidate[1], candidate[0]),
                            brep_contact::subtract(candidate[2], candidate[0])));
    if (normal_length <= tolerance || candidate_area_twice <= tolerance) return refusal("degenerate_contact_triangle");
    const int third = 3 - endpoint0 - endpoint1;
    const double signed_distance = std::abs(
        brep_contact::dot(normal, brep_contact::subtract(candidate[static_cast<std::size_t>(third)], a))) / normal_length;
    if (signed_distance <= tolerance) {
        result["geometric_class"] = "coplanar_positive_area";
        result["witness"] = false;
        result["permitted"] = false;
        result["decision"] = "forbidden_or_uncertain_refusal";
        return result;
    }
    const auto owner = edge_record["owner_face_id"].cast<std::int64_t>();
    const bool base = candidate_face_id == owner;
    result["geometric_class"] = base ? "base_touch" : "seam_touch";
    result["witness"] = true;
    result["permitted"] = true;
    result["decision"] = "permitted_contact";
    return result;
}
