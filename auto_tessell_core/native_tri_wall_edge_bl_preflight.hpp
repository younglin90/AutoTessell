#pragma once

#include "native_tri_authority_source_certificate.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <map>
#include <set>
#include <sstream>
#include <stack>
#include <string>
#include <utility>
#include <vector>

namespace autotessell_native_tri_wall_edge {

using Point = autotessell_native_tri_authority::Point;
using Triangle = autotessell_native_tri_authority::Triangle;

struct EdgeRow {
    std::string edge_id;
    std::array<std::int64_t, 2> endpoints{};
    std::vector<std::int64_t> incident_faces;
    std::vector<std::int64_t> directed_sector_faces;
    std::vector<std::string> directed_sector_ids;
    std::string wall_role;
    std::string patch_boundary_role;
    std::string feature;
    std::string patch;
    std::string physical_group;
    std::string component;
    std::string provenance;
};

inline bool nonempty(const std::string& value) noexcept {
    return !value.empty();
}

inline std::pair<std::int64_t, std::int64_t> undirected_edge(
    const std::int64_t first, const std::int64_t second) noexcept {
    return first < second ? std::make_pair(first, second)
                          : std::make_pair(second, first);
}

inline void append_field(std::ostringstream& stream, const std::string& value) {
    stream << value.size() << ':' << value << '|';
}

inline std::string canonical_edge_stream(
    const std::vector<EdgeRow>& rows,
    const std::string& loop_policy,
    const std::vector<std::int64_t>& loop_endpoints) {
    std::vector<const EdgeRow*> ordered;
    ordered.reserve(rows.size());
    for (const EdgeRow& row : rows) ordered.push_back(&row);
    std::sort(ordered.begin(), ordered.end(),
              [](const EdgeRow* left, const EdgeRow* right) {
                  return left->edge_id < right->edge_id;
              });
    std::ostringstream stream;
    stream << "loop_policy=";
    append_field(stream, loop_policy);
    stream << "loop_endpoints=" << loop_endpoints.size() << '|';
    for (const std::int64_t endpoint : loop_endpoints) stream << endpoint << ',';
    stream << '|';
    stream << "rows=" << ordered.size() << '|';
    for (const EdgeRow* row : ordered) {
        append_field(stream, row->edge_id);
        stream << row->endpoints[0] << ',' << row->endpoints[1] << '|';
        stream << row->incident_faces.size() << '|';
        for (const std::int64_t face : row->incident_faces) stream << face << ',';
        stream << '|';
        stream << row->directed_sector_faces.size() << '|';
        for (const std::int64_t face : row->directed_sector_faces) stream << face << ',';
        stream << '|';
        stream << row->directed_sector_ids.size() << '|';
        for (const std::string& sector : row->directed_sector_ids)
            append_field(stream, sector);
        append_field(stream, row->wall_role);
        append_field(stream, row->patch_boundary_role);
        append_field(stream, row->feature);
        append_field(stream, row->patch);
        append_field(stream, row->physical_group);
        append_field(stream, row->component);
        append_field(stream, row->provenance);
    }
    return stream.str();
}

struct HalfEdgeOccurrence {
    std::int64_t face = -1;
    std::int64_t from = -1;
    std::int64_t to = -1;
};

inline bool validate_edge_ledger_geometry(
    const std::vector<Point>& points,
    const std::vector<Triangle>& faces,
    const std::vector<EdgeRow>& rows,
    const std::string& loop_policy,
    const std::vector<std::int64_t>& loop_endpoints,
    std::string& reason,
    std::size_t& edge_count) {
    if (rows.empty()) {
        reason = "tri_wall_edge_ledger_empty";
        return false;
    }
    std::map<std::pair<std::int64_t, std::int64_t>,
             std::vector<HalfEdgeOccurrence>> source_edges;
    for (std::size_t face_id = 0; face_id < faces.size(); ++face_id) {
        const Triangle& face = faces[face_id];
        for (const std::int64_t vertex : face) {
            if (vertex < 0 || static_cast<std::size_t>(vertex) >= points.size()) {
                reason = "tri_wall_edge_source_vertex_invalid";
                return false;
            }
        }
        for (int local = 0; local < 3; ++local) {
            const std::int64_t from = face[static_cast<std::size_t>(local)];
            const std::int64_t to = face[static_cast<std::size_t>((local + 1) % 3)];
            if (from == to) {
                reason = "tri_wall_edge_source_degenerate_edge";
                return false;
            }
            source_edges[undirected_edge(from, to)].push_back(
                {static_cast<std::int64_t>(face_id), from, to});
        }
    }

    std::set<std::string> edge_ids;
    std::set<std::pair<std::int64_t, std::int64_t>> selected;
    std::map<std::int64_t, std::set<std::int64_t>> adjacency;
    for (const EdgeRow& row : rows) {
        if (!nonempty(row.edge_id) || !edge_ids.insert(row.edge_id).second) {
            reason = "tri_wall_edge_id_duplicate_or_empty";
            return false;
        }
        const std::int64_t first = row.endpoints[0];
        const std::int64_t second = row.endpoints[1];
        if (first == second || first < 0 || second < 0 ||
            static_cast<std::size_t>(first) >= points.size() ||
            static_cast<std::size_t>(second) >= points.size()) {
            reason = "tri_wall_edge_endpoint_invalid";
            return false;
        }
        if (row.incident_faces.size() != 2U ||
            row.incident_faces[0] < 0 ||
            row.incident_faces[1] <= row.incident_faces[0] ||
            static_cast<std::size_t>(row.incident_faces[1]) >= faces.size()) {
            reason = "tri_wall_edge_incident_face_binding_invalid";
            return false;
        }
        if (row.directed_sector_faces != row.incident_faces ||
            row.directed_sector_ids.size() != row.incident_faces.size() ||
            std::any_of(row.directed_sector_ids.begin(), row.directed_sector_ids.end(),
                        [](const std::string& value) { return value.empty(); })) {
            reason = "tri_wall_edge_sector_binding_invalid";
            return false;
        }
        if (row.wall_role != "wall" || row.patch_boundary_role.empty() ||
            row.feature.empty() || row.patch.empty() || row.physical_group.empty() ||
            row.component.empty() || row.provenance.empty()) {
            reason = "tri_wall_edge_authority_field_missing";
            return false;
        }
        const auto key = undirected_edge(first, second);
        if (!selected.insert(key).second) {
            reason = "tri_wall_edge_duplicate_geometry";
            return false;
        }
        const auto source = source_edges.find(key);
        if (source == source_edges.end() || source->second.size() != 2U) {
            reason = "tri_wall_edge_source_edge_binding_invalid";
            return false;
        }
        std::set<std::int64_t> incident(row.incident_faces.begin(),
                                         row.incident_faces.end());
        if (incident.size() != 2U ||
            incident.count(source->second[0].face) == 0U ||
            incident.count(source->second[1].face) == 0U) {
            reason = "tri_wall_edge_incident_face_binding_invalid";
            return false;
        }
        bool forward = false;
        bool reverse = false;
        for (const HalfEdgeOccurrence& occurrence : source->second) {
            forward = forward || (occurrence.from == first && occurrence.to == second);
            reverse = reverse || (occurrence.from == second && occurrence.to == first);
        }
        if (!forward || !reverse) {
            reason = "tri_wall_edge_direction_binding_invalid";
            return false;
        }
        const Point& a = points[static_cast<std::size_t>(first)];
        const Point& b = points[static_cast<std::size_t>(second)];
        const Point tangent = autotessell_native_tri_authority::sub(b, a);
        const double tangent_norm = autotessell_native_tri_authority::norm(tangent);
        if (!(tangent_norm > 1.0e-14)) {
            reason = "tri_wall_edge_zero_length";
            return false;
        }
        for (const std::int64_t face_id : row.incident_faces) {
            const Triangle& face = faces[static_cast<std::size_t>(face_id)];
            const Point& p0 = points[static_cast<std::size_t>(face[0])];
            const Point& p1 = points[static_cast<std::size_t>(face[1])];
            const Point& p2 = points[static_cast<std::size_t>(face[2])];
            const Point normal = autotessell_native_tri_authority::cross(
                autotessell_native_tri_authority::sub(p1, p0),
                autotessell_native_tri_authority::sub(p2, p0));
            if (!(autotessell_native_tri_authority::norm(normal) > 1.0e-14) ||
                !(autotessell_native_tri_authority::norm(
                      autotessell_native_tri_authority::cross(normal, tangent)) >
                  1.0e-14)) {
                reason = "tri_wall_edge_incident_frame_degenerate";
                return false;
            }
        }
        adjacency[first].insert(second);
        adjacency[second].insert(first);
    }

    if (loop_policy != "closed_nonbranching" &&
        loop_policy != "open_nonbranching") {
        reason = "tri_wall_edge_loop_policy_missing_or_unsupported";
        return false;
    }
    if (loop_policy == "closed_nonbranching" && rows.size() < 3U) {
        reason = "tri_wall_edge_closed_loop_too_short";
        return false;
    }
    if (loop_policy == "open_nonbranching" && rows.size() < 2U) {
        reason = "tri_wall_edge_open_loop_too_short";
        return false;
    }
    std::set<std::int64_t> visited;
    std::stack<std::int64_t> pending;
    pending.push(rows.front().endpoints[0]);
    while (!pending.empty()) {
        const std::int64_t vertex = pending.top();
        pending.pop();
        if (!visited.insert(vertex).second) continue;
        for (const std::int64_t neighbor : adjacency[vertex]) pending.push(neighbor);
    }
    if (visited.size() != adjacency.size()) {
        reason = "tri_wall_edge_loop_disconnected";
        return false;
    }
    if (loop_policy == "closed_nonbranching") {
        if (!loop_endpoints.empty()) {
            reason = "tri_wall_edge_closed_loop_endpoints_unexpected";
            return false;
        }
        for (const auto& [vertex, neighbors] : adjacency) {
            if (neighbors.size() != 2U) {
                reason = "tri_wall_edge_loop_branch_or_open";
                return false;
            }
        }
    } else {
        if (loop_endpoints.size() != 2U || loop_endpoints[0] == loop_endpoints[1] ||
            adjacency.count(loop_endpoints[0]) == 0U ||
            adjacency.count(loop_endpoints[1]) == 0U) {
            reason = "tri_wall_edge_open_loop_endpoints_invalid";
            return false;
        }
        for (const auto& [vertex, neighbors] : adjacency) {
            const bool declared_endpoint =
                vertex == loop_endpoints[0] || vertex == loop_endpoints[1];
            const std::size_t expected_degree = declared_endpoint ? 1U : 2U;
            if (neighbors.size() != expected_degree) {
                reason = "tri_wall_edge_open_loop_branch_or_endpoint_invalid";
                return false;
            }
        }
    }
    edge_count = rows.size();
    return true;
}

inline std::string sha256_text(const std::string& value) {
    return autotessell_native_tri_authority::sha256_text(value);
}

}  // namespace autotessell_native_tri_wall_edge
