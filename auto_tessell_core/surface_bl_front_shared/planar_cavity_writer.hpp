#pragma once

#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <tuple>
#include <functional>
#include <vector>

namespace autotessell_surface_bl_cavity_detail {

struct Eval {
    bool valid = false;
    double surface_deviation = 0.0;
    double non_orthogonality = 0.0;
    double skewness = 0.0;
    double aspect = 0.0;
};

inline std::array<double, 2> project(const P& value, int dropped_axis) {
    if (dropped_axis == 0) return {value[1], value[2]};
    if (dropped_axis == 1) return {value[0], value[2]};
    return {value[0], value[1]};
}

inline double orient2(const std::array<double, 2>& a,
                      const std::array<double, 2>& b,
                      const std::array<double, 2>& c) {
    return (b[0] - a[0]) * (c[1] - a[1]) -
           (b[1] - a[1]) * (c[0] - a[0]);
}

inline bool on_segment(const std::array<double, 2>& a,
                       const std::array<double, 2>& b,
                       const std::array<double, 2>& p,
                       double tolerance) {
    return std::abs(orient2(a, b, p)) <= tolerance &&
           p[0] >= std::min(a[0], b[0]) - tolerance &&
           p[0] <= std::max(a[0], b[0]) + tolerance &&
           p[1] >= std::min(a[1], b[1]) - tolerance &&
           p[1] <= std::max(a[1], b[1]) + tolerance;
}

inline bool segments_intersect(const std::array<double, 2>& a,
                               const std::array<double, 2>& b,
                               const std::array<double, 2>& c,
                               const std::array<double, 2>& d,
                               double tolerance) {
    const double o1 = orient2(a, b, c);
    const double o2 = orient2(a, b, d);
    const double o3 = orient2(c, d, a);
    const double o4 = orient2(c, d, b);
    const bool cross_ab = ((o1 > tolerance && o2 < -tolerance) ||
                           (o1 < -tolerance && o2 > tolerance));
    const bool cross_cd = ((o3 > tolerance && o4 < -tolerance) ||
                           (o3 < -tolerance && o4 > tolerance));
    if (cross_ab && cross_cd) return true;
    return on_segment(a, b, c, tolerance) || on_segment(a, b, d, tolerance) ||
           on_segment(c, d, a, tolerance) || on_segment(c, d, b, tolerance);
}

inline bool point_inside_polygon(const std::array<double, 2>& point,
                                 const std::vector<std::array<double, 2>>& polygon,
                                 double tolerance) {
    bool inside = false;
    for (std::size_t i = 0, j = polygon.size() - 1; i < polygon.size(); j = i++) {
        const auto& a = polygon[j];
        const auto& b = polygon[i];
        if (on_segment(a, b, point, tolerance)) return false;
        const bool crosses = ((a[1] > point[1]) != (b[1] > point[1])) &&
                             (point[0] < (b[0] - a[0]) * (point[1] - a[1]) /
                                                (b[1] - a[1]) + a[0]);
        if (crosses) inside = !inside;
    }
    return inside;
}

}  // namespace autotessell_surface_bl_cavity_detail

py::dict write_planar_cavity(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& source_triangles,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edges,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& layer_ids,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals,
    const py::dict& authority,
    const py::list& provenance,
    std::int64_t requested_layers,
    double epsilon = 1.0e-12,
    bool strict_quality = false) {
    using namespace autotessell_surface_bl_cavity_detail;
    const auto refuse = [&](const char* reason) {
        auto result = fail(reason);
        result["status"] = "surface_bl_planar_cavity_writer_refused";
        result["replacement_mode"] = "planar_cavity";
        result["source_faces_removed"] = py::list();
        result["source_faces_retained"] = py::list();
        result["source_face_coverage_complete"] = false;
        result["topology_invalid"] = 0;
        result["topology_inverted"] = 0;
        result["topology_duplicate"] = 0;
        result["topology_non_manifold"] = 0;
        result["topology_self_intersection"] = 0;
        result["strict_quality"] = strict_quality;
        result["quality_witness"] = py::list();
        result["point_updates"] = py::list();
        result["generated_vertex_lineage"] = py::list();
        result["interval_ledger"] = py::list();
        result["optimized_front_scale"] = 1.0;
        result["subdivision_factor"] = 1;
        result["independent_long_double_audit"] = py::dict();
        result["count_ledger"] = py::list();
        return result;
    };
    if (requested_layers == 0) {
        py::dict result;
        result["accepted"] = true;
        result["status"] = "surface_bl_planar_cavity_bl0_identity";
        result["reason"] = "disabled_identity";
        result["requested_layers"] = 0;
        result["actual_layers"] = 0;
        result["replacement_mode"] = "planar_cavity";
        result["generated_faces"] = py::list();
        result["provenance"] = py::list();
        result["source_faces_removed"] = py::list();
        result["source_faces_retained"] = py::list();
        result["source_face_coverage_complete"] = true;
        result["candidate_discarded"] = false;
        result["publication_eligible"] = false;
        result["count_is_report_only"] = true;
        result["strict_quality"] = strict_quality;
        result["quality_witness"] = py::list();
        result["point_updates"] = py::list();
        result["generated_vertex_lineage"] = py::list();
        result["interval_ledger"] = py::list();
        result["optimized_front_scale"] = 1.0;
        result["subdivision_factor"] = 1;
        result["independent_long_double_audit"] = py::dict();
        result["count_ledger"] = py::list();
        return result;
    }
    if (requested_layers < 0 || requested_layers > 3)
        return refuse("planar_cavity_layer_count_out_of_bounds");
    if (points.ndim() != 2 || points.shape(1) != 3 ||
        source_triangles.ndim() != 2 || source_triangles.shape(1) != 3 ||
        edges.ndim() != 2 || edges.shape(1) != 4 ||
        normals.ndim() != 2 || normals.shape(1) != 3 ||
        normals.shape(0) != source_triangles.shape(0) ||
        layer_ids.ndim() != 3 ||
        layer_ids.shape(0) != requested_layers ||
        layer_ids.shape(1) != edges.shape(0) || layer_ids.shape(2) != 2 ||
        provenance.size() != static_cast<std::size_t>(requested_layers) *
            static_cast<std::size_t>(edges.shape(0)))
        return refuse("planar_cavity_shape_or_lineage_invalid");
    if (edges.shape(0) < 3)
        return refuse("planar_cavity_source_disk_cardinality");
    if (!text(authority, "source_kind") || !text(authority, "source_sha256") ||
        !text(authority, "boundary_mapping_sha256") ||
        !text(authority, "physical_group_sha256") || !text(authority, "provenance"))
        return refuse("authority_unsealed");

    const auto* point_data = points.data();
    const auto* triangle_data = source_triangles.data();
    const auto* edge_data = edges.data();
    const auto* layer_data = layer_ids.data();
    const auto* normal_data = normals.data();
    std::vector<P> working_points(static_cast<std::size_t>(points.shape(0)));
    for (py::ssize_t index = 0; index < points.shape(0); ++index) {
        const auto offset = static_cast<std::size_t>(index) * 3U;
        working_points[static_cast<std::size_t>(index)] =
            P{point_data[offset], point_data[offset + 1U], point_data[offset + 2U]};
        if (!finite(working_points[static_cast<std::size_t>(index)]))
            return refuse("planar_cavity_point_nonfinite");
    }
    const std::vector<P> baseline_points = working_points;
    const auto point = [&](std::int64_t id) {
        return working_points.at(static_cast<std::size_t>(id));
    };
    const auto normal = [&](std::int64_t id) {
        const auto offset = static_cast<std::size_t>(id) * 3U;
        return unit(P{normal_data[offset], normal_data[offset + 1U], normal_data[offset + 2U]});
    };
    const auto scale_point = point(0);
    P reference_normal{};
    try {
        reference_normal = normal(0);
    } catch (...) {
        return refuse("planar_cavity_reference_normal_invalid");
    }
    const double scale = [&]() {
        double value = 1.0;
        for (py::ssize_t i = 0; i < points.shape(0); ++i) {
            const P current = point(i);
            value = std::max(value, autotessell_surface_bl_quality::length(sub(current, scale_point)));
        }
        return value;
    }();
    const double tolerance = std::max(epsilon, 1.0e-10 * scale);
    const auto signed_area = [&](const P& a, const P& b, const P& c) {
        return 0.5 * dot(cross(sub(b, a), sub(c, a)), reference_normal);
    };
    for (py::ssize_t face = 0; face < source_triangles.shape(0); ++face) {
        const auto offset = static_cast<std::size_t>(face) * 3U;
        const auto a = triangle_data[offset];
        const auto b = triangle_data[offset + 1U];
        const auto c = triangle_data[offset + 2U];
        if (a < 0 || b < 0 || c < 0 || a >= points.shape(0) || b >= points.shape(0) ||
            c >= points.shape(0) || a == b || b == c || c == a)
            return refuse("planar_cavity_source_triangle_invalid");
        const P face_normal = normal(face);
        if (!(dot(face_normal, reference_normal) > 1.0 - 1.0e-8) ||
            !(signed_area(point(a), point(b), point(c)) > tolerance) ||
            std::abs(dot(sub(point(a), scale_point), reference_normal)) > tolerance ||
            std::abs(dot(sub(point(b), scale_point), reference_normal)) > tolerance ||
            std::abs(dot(sub(point(c), scale_point), reference_normal)) > tolerance)
            return refuse("planar_cavity_source_not_planar_or_positive");
    }

    using EdgeKey = std::pair<std::int64_t, std::int64_t>;
    const auto edge_key = [](std::int64_t a, std::int64_t b) {
        return EdgeKey{std::min(a, b), std::max(a, b)};
    };
    std::map<EdgeKey, std::vector<std::int64_t>> source_incidence;
    for (py::ssize_t face = 0; face < source_triangles.shape(0); ++face) {
        const auto offset = static_cast<std::size_t>(face) * 3U;
        const std::array<std::int64_t, 3> tri{
            triangle_data[offset], triangle_data[offset + 1U], triangle_data[offset + 2U]};
        for (int i = 0; i < 3; ++i)
            source_incidence[edge_key(tri[i], tri[(i + 1) % 3])].push_back(face);
    }
    std::set<EdgeKey> source_boundary;
    for (const auto& [key, faces] : source_incidence) {
        if (faces.size() == 1U) source_boundary.insert(key);
        else if (faces.size() != 2U) return refuse("planar_cavity_source_edge_incidence_invalid");
    }
    if (source_boundary.size() != static_cast<std::size_t>(edges.shape(0)))
        return refuse("planar_cavity_boundary_edge_set_mismatch");
    std::set<std::int64_t> source_vertices;
    for (py::ssize_t face = 0; face < source_triangles.shape(0); ++face) {
        const auto offset = static_cast<std::size_t>(face) * 3U;
        source_vertices.insert(triangle_data[offset]);
        source_vertices.insert(triangle_data[offset + 1U]);
        source_vertices.insert(triangle_data[offset + 2U]);
    }
    std::set<std::int64_t> source_boundary_vertices;
    for (const auto& key : source_boundary) {
        source_boundary_vertices.insert(key.first);
        source_boundary_vertices.insert(key.second);
    }
    if (source_vertices.size() < source_boundary_vertices.size())
        return refuse("planar_cavity_source_vertex_set_invalid");
    const auto interior_vertex_count = source_vertices.size() - source_boundary_vertices.size();
    const auto expected_face_count = source_boundary.size() + 2U * interior_vertex_count - 2U;
    if (static_cast<std::size_t>(source_triangles.shape(0)) != expected_face_count)
        return refuse("planar_cavity_source_disk_cardinality");

    std::vector<std::int64_t> oriented_a(edges.shape(0)), oriented_b(edges.shape(0));
    std::map<std::int64_t, std::size_t> outgoing, incoming;
    std::set<EdgeKey> selected_boundary;
    std::set<std::int64_t> edge_ids;
    std::map<std::int64_t, py::dict> face_templates;
    for (py::ssize_t i = 0; i < edges.shape(0); ++i) {
        const auto offset = static_cast<std::size_t>(i) * 4U;
        const auto id = edge_data[offset];
        const auto a = edge_data[offset + 1U];
        const auto b = edge_data[offset + 2U];
        const auto face = edge_data[offset + 3U];
        if (a < 0 || b < 0 || a >= points.shape(0) || b >= points.shape(0) || a == b ||
            face < 0 || face >= source_triangles.shape(0) || !edge_ids.insert(id).second)
            return refuse("planar_cavity_boundary_edge_invalid");
        const auto key = edge_key(a, b);
        const auto incidence = source_incidence.find(key);
        if (incidence == source_incidence.end() || incidence->second.size() != 1U ||
            incidence->second.front() != face || !selected_boundary.insert(key).second)
            return refuse("planar_cavity_boundary_ownership_mismatch");
        bool found = false;
        const auto tri_offset = static_cast<std::size_t>(face) * 3U;
        for (int j = 0; j < 3; ++j) {
            const auto ta = triangle_data[tri_offset + static_cast<std::size_t>(j)];
            const auto tb = triangle_data[tri_offset + static_cast<std::size_t>((j + 1) % 3)];
            if ((ta == a && tb == b) || (ta == b && tb == a)) {
                oriented_a[i] = ta;
                oriented_b[i] = tb;
                found = true;
                break;
            }
        }
        if (!found || !outgoing.emplace(oriented_a[i], static_cast<std::size_t>(i)).second ||
            !incoming.emplace(oriented_b[i], static_cast<std::size_t>(i)).second)
            return refuse("planar_cavity_boundary_cycle_invalid");
        if (!outgoing.contains(oriented_a[i]) || !incoming.contains(oriented_b[i]))
            return refuse("planar_cavity_boundary_cycle_invalid");
    }
    const auto edge_count = static_cast<std::size_t>(edges.shape(0));
    const auto layer_count = static_cast<std::size_t>(requested_layers);
    for (std::size_t layer = 0; layer < layer_count; ++layer) {
        for (std::size_t index = 0; index < edge_count; ++index) {
            const auto provenance_index = layer * edge_count + index;
            if (!py::isinstance<py::dict>(provenance[static_cast<py::ssize_t>(provenance_index)]))
                return refuse("planar_cavity_lineage_row_invalid");
            const py::dict row =
                provenance[static_cast<py::ssize_t>(provenance_index)].cast<py::dict>();
            if (!text(row, "source_face_id") || !text(row, "source_wall_edge") ||
                !text(row, "feature") || !text(row, "patch") ||
                !text(row, "physical_group") || !text(row, "component") ||
                !text(row, "provenance"))
                return refuse("planar_cavity_lineage_row_incomplete");
            const auto source_face = row["source_face_id"].cast<std::int64_t>();
            const auto edge_face = edge_data[index * 4U + 3U];
            if (source_face != edge_face)
                return refuse("planar_cavity_lineage_face_mismatch");
            if (layer == 0U) face_templates.emplace(source_face, row);
        }
    }
    if (selected_boundary != source_boundary || face_templates.empty())
        return refuse("planar_cavity_source_coverage_incomplete");

    std::size_t seed = 0U;
    for (std::size_t i = 1; i < static_cast<std::size_t>(edges.shape(0)); ++i) {
        const auto lhs = std::tuple{edge_data[i * 4U], edge_data[i * 4U + 3U], oriented_a[i], oriented_b[i], i};
        const auto rhs = std::tuple{edge_data[seed * 4U], edge_data[seed * 4U + 3U], oriented_a[seed], oriented_b[seed], seed};
        if (lhs < rhs) seed = i;
    }
    std::vector<std::size_t> cycle;
    std::set<std::size_t> used_edges;
    const auto start = oriented_a[seed];
    auto current = start;
    for (std::size_t count = 0; count < static_cast<std::size_t>(edges.shape(0)); ++count) {
        const auto iterator = outgoing.find(current);
        if (iterator == outgoing.end() || !used_edges.insert(iterator->second).second)
            return refuse("planar_cavity_boundary_cycle_repeated");
        cycle.push_back(iterator->second);
        current = oriented_b[iterator->second];
    }
    if (current != start || cycle.size() != static_cast<std::size_t>(edges.shape(0)))
        return refuse("planar_cavity_boundary_cycle_not_closed");
    std::vector<std::int64_t> boundary_vertices;
    for (const auto index : cycle) boundary_vertices.push_back(oriented_a[index]);
    if (std::set<std::int64_t>(boundary_vertices.begin(), boundary_vertices.end()).size() != boundary_vertices.size())
        return refuse("planar_cavity_boundary_vertex_repeated");
    double boundary_area = 0.0;
    for (std::size_t i = 0; i < boundary_vertices.size(); ++i)
        boundary_area += signed_area(point(boundary_vertices[i]), point(boundary_vertices[(i + 1) % boundary_vertices.size()]), scale_point);
    if (!(boundary_area > tolerance)) return refuse("planar_cavity_boundary_orientation_invalid");

    int dropped_axis = 0;
    if (std::abs(reference_normal[1]) > std::abs(reference_normal[dropped_axis])) dropped_axis = 1;
    if (std::abs(reference_normal[2]) > std::abs(reference_normal[dropped_axis])) dropped_axis = 2;
    std::vector<std::array<double, 2>> boundary_projection;
    for (const auto vertex : boundary_vertices) boundary_projection.push_back(project(point(vertex), dropped_axis));
    for (std::size_t i = 0; i < boundary_projection.size(); ++i) {
        const std::size_t next_i = (i + 1) % boundary_projection.size();
        for (std::size_t j = i + 1; j < boundary_projection.size(); ++j) {
            const std::size_t next_j = (j + 1) % boundary_projection.size();
            if (i == j || next_i == j || next_j == i) continue;
            if (segments_intersect(boundary_projection[i], boundary_projection[next_i],
                                   boundary_projection[j], boundary_projection[next_j], tolerance))
                return refuse("planar_cavity_boundary_self_intersection");
        }
    }

    std::vector<std::map<std::int64_t, std::int64_t>> front_by_vertex(layer_count);
    std::vector<std::vector<std::int64_t>> front_vertices(layer_count);
    std::vector<std::vector<std::array<double, 2>>> front_projection(layer_count);
    std::set<std::int64_t> generated_ids;
    for (std::size_t layer = 0; layer < layer_count; ++layer) {
        const auto& lower_projection =
            layer == 0U ? boundary_projection : front_projection[layer - 1U];
        auto& current_map = front_by_vertex[layer];
        for (const auto index : cycle) {
            const auto offset = (layer * edge_count + index) * 2U;
            const auto a = oriented_a[index];
            const auto b = oriented_b[index];
            const auto raw_a = layer_data[offset];
            const auto raw_b = layer_data[offset + 1U];
            const auto assign = [&](std::int64_t vertex, std::int64_t child) {
                if (child < 0 || child >= points.shape(0) || child == vertex)
                    return false;
                const auto [iterator, inserted] = current_map.emplace(vertex, child);
                return inserted || iterator->second == child;
            };
            if (!assign(a, raw_a) || !assign(b, raw_b))
                return refuse("planar_cavity_shared_child_mismatch");
        }
        if (current_map.size() != boundary_vertices.size())
            return refuse("planar_cavity_child_front_incomplete");
        std::vector<std::int64_t> current_vertices;
        std::vector<std::array<double, 2>> current_projection;
        current_vertices.reserve(boundary_vertices.size());
        current_projection.reserve(boundary_vertices.size());
        for (const auto vertex : boundary_vertices) {
            const auto child = current_map.at(vertex);
            if (!generated_ids.insert(child).second)
                return refuse("planar_cavity_child_vertex_duplicate");
            current_vertices.push_back(child);
            current_projection.push_back(project(point(child), dropped_axis));
            if (!point_inside_polygon(current_projection.back(), lower_projection, tolerance))
                return refuse("planar_cavity_front_not_inside_predecessor");
        }
        for (std::size_t i = 0; i < current_projection.size(); ++i) {
            const std::size_t next_i = (i + 1U) % current_projection.size();
            for (std::size_t j = i + 1U; j < current_projection.size(); ++j) {
                const std::size_t next_j = (j + 1U) % current_projection.size();
                if (i == j || next_i == j || next_j == i) continue;
                if (segments_intersect(current_projection[i], current_projection[next_i],
                                       current_projection[j], current_projection[next_j],
                                       tolerance))
                    return refuse("planar_cavity_front_self_intersection");
            }
            for (std::size_t j = 0; j < lower_projection.size(); ++j) {
                if (segments_intersect(
                        current_projection[i], current_projection[next_i],
                        lower_projection[j], lower_projection[(j + 1U) % lower_projection.size()],
                        tolerance))
                    return refuse("planar_cavity_front_crosses_predecessor");
            }
        }
        double current_area = 0.0;
        for (std::size_t i = 0; i < current_vertices.size(); ++i)
            current_area += signed_area(
                point(current_vertices[i]),
                point(current_vertices[(i + 1U) % current_vertices.size()]),
                scale_point);
        if (!(current_area > tolerance))
            return refuse("planar_cavity_front_orientation_invalid");
        front_vertices[layer] = std::move(current_vertices);
        front_projection[layer] = std::move(current_projection);
    }
    std::vector<std::int64_t> child_vertices = front_vertices.back();
    std::vector<std::int64_t> source_interior_vertices;
    for (const auto vertex : source_vertices)
        if (!source_boundary_vertices.contains(vertex)) source_interior_vertices.push_back(vertex);

    const auto clone = [](const py::dict& input) {
        py::dict output;
        for (const auto item : input) output[item.first] = item.second;
        return output;
    };
    std::vector<Tri> faces;
    py::list output_provenance;
    py::list quality_witness;
    std::set<std::array<std::int64_t, 3>> face_keys;
    double max_skew = 0.0;
    double max_aspect = 0.0;
    double max_nonorth = 0.0;
    constexpr double quality_tolerance = 1.0e-12;
    const double max_skew_gate = strict_quality ? 0.30 : 0.50;
    const double max_aspect_gate = 10.0;
    const double max_nonorth_gate = strict_quality ? 30.0 : 75.0;
    const auto evaluate = [&](const std::vector<Tri>& candidates) {
        Eval result;
        result.valid = true;
        for (const auto& tri : candidates) {
            const P a = point(tri[0]);
            const P b = point(tri[1]);
            const P c = point(tri[2]);
            const auto score = autotessell_surface_bl_quality::score(a, b, c);
            const double area = signed_area(a, b, c);
            const double deviation = std::max({
                std::abs(dot(sub(a, scale_point), reference_normal)),
                std::abs(dot(sub(b, scale_point), reference_normal)),
                std::abs(dot(sub(c, scale_point), reference_normal))});
            result.surface_deviation = std::max(result.surface_deviation, deviation);
            result.non_orthogonality = std::max(result.non_orthogonality, score.non_orthogonality);
            result.skewness = std::max(result.skewness, score.skewness);
            result.aspect = std::max(result.aspect, score.aspect_ratio);
            if (!(std::isfinite(area) && area > epsilon && std::isfinite(score.skewness) &&
                  std::isfinite(score.aspect_ratio) && std::isfinite(score.non_orthogonality) &&
                  score.skewness <= max_skew_gate + quality_tolerance &&
                  score.aspect_ratio <= max_aspect_gate + quality_tolerance &&
                  score.non_orthogonality <= max_nonorth_gate + quality_tolerance &&
                  deviation <= tolerance))
                result.valid = false;
        }
        return result;
    };
    const auto append_face = [&](const Tri& tri, const py::dict& source_row,
                                 const std::vector<std::int64_t>& covered_faces,
                                 const char* role) {
        auto key = tri;
        std::sort(key.begin(), key.end());
        if (!face_keys.insert(key).second) return false;
        auto row = clone(source_row);
        py::list coverage;
        for (const auto face : covered_faces) coverage.append(face);
        row["source_face_ids"] = coverage;
        row["replacement_role"] = role;
        row["output_face_id"] = static_cast<std::int64_t>(faces.size());
        faces.push_back(tri);
        output_provenance.append(row);
        return true;
    };
    const auto record_quality = [&](const Tri& tri, std::int64_t layer,
                                   const char* role) {
        const auto score = autotessell_surface_bl_quality::score(
            point(tri[0]), point(tri[1]), point(tri[2]));
        py::dict witness;
        witness["output_face_id"] =
            static_cast<std::int64_t>(faces.size() - 1U);
        witness["layer"] = layer;
        witness["role"] = role;
        witness["vertex_ids"] = py::make_tuple(tri[0], tri[1], tri[2]);
        witness["skewness"] = score.skewness;
        witness["aspect_ratio"] = score.aspect_ratio;
        witness["non_orthogonality_degrees"] = score.non_orthogonality;
        witness["accepted"] = true;
        quality_witness.append(witness);
    };

    double optimized_front_scale = 1.0;
    double selected_phase_offset = 0.0;
    const bool regular_hex_topology =
        strict_quality && layer_count == 1U &&
        boundary_vertices.size() == 6U &&
        source_interior_vertices.size() == 1U &&
        source_triangles.shape(0) == 6;
    bool regular_hex_zipper = false;
    if (strict_quality && !regular_hex_topology) {
        const auto validate_current_front = [&]() {
            for (std::size_t layer = 0; layer < layer_count; ++layer) {
                const auto& lower_projection =
                    layer == 0U ? boundary_projection : front_projection[layer - 1U];
                auto& current_projection = front_projection[layer];
                current_projection.clear();
                current_projection.reserve(front_vertices[layer].size());
                for (const auto vertex : front_vertices[layer]) {
                    current_projection.push_back(project(point(vertex), dropped_axis));
                    if (!point_inside_polygon(
                            current_projection.back(), lower_projection, tolerance))
                        return false;
                }
                for (std::size_t i = 0; i < current_projection.size(); ++i) {
                    const std::size_t next_i = (i + 1U) % current_projection.size();
                    for (std::size_t j = i + 1U; j < current_projection.size(); ++j) {
                        const std::size_t next_j = (j + 1U) % current_projection.size();
                        if (i == j || next_i == j || next_j == i) continue;
                        if (segments_intersect(
                                current_projection[i], current_projection[next_i],
                                current_projection[j], current_projection[next_j],
                                tolerance))
                            return false;
                    }
                    for (std::size_t j = 0; j < lower_projection.size(); ++j) {
                        if (segments_intersect(
                                current_projection[i], current_projection[next_i],
                                lower_projection[j],
                                lower_projection[(j + 1U) % lower_projection.size()],
                                tolerance))
                            return false;
                    }
                }
                double area = 0.0;
                for (std::size_t i = 0; i < front_vertices[layer].size(); ++i)
                    area += signed_area(
                        point(front_vertices[layer][i]),
                        point(front_vertices[layer][(i + 1U) % front_vertices[layer].size()]),
                        scale_point);
                if (!(std::isfinite(area) && area > tolerance)) return false;
            }
            return true;
        };

        P center{};
        for (const auto vertex : boundary_vertices) {
            const P source = point(vertex);
            center[0] += source[0];
            center[1] += source[1];
            center[2] += source[2];
        }
        const double inverse_boundary_count =
            1.0 / static_cast<double>(boundary_vertices.size());
        center[0] *= inverse_boundary_count;
        center[1] *= inverse_boundary_count;
        center[2] *= inverse_boundary_count;

        const std::array<double, 11> scales{
            0.10, 0.15, 0.20, 0.25, 0.30, 0.40,
            0.50, 0.60, 0.75, 0.90, 1.00};
        bool found = false;
        double best_scale = 1.0;
        std::vector<P> best_points;
        std::tuple<double, double, double, double> best_rank{
            1.0e300, 1.0e300, 1.0e300, 1.0e300};

        for (const double candidate_scale : scales) {
            working_points = baseline_points;
            for (const auto id : generated_ids) {
                const auto& original = baseline_points.at(static_cast<std::size_t>(id));
                working_points[static_cast<std::size_t>(id)] = P{
                    center[0] + candidate_scale * (original[0] - center[0]),
                    center[1] + candidate_scale * (original[1] - center[1]),
                    center[2] + candidate_scale * (original[2] - center[2])};
            }
            if (!validate_current_front()) continue;
            if (!source_interior_vertices.empty()) {
                bool interior_inside = true;
                for (const auto vertex : source_interior_vertices) {
                    if (!point_inside_polygon(
                            project(point(vertex), dropped_axis),
                            front_projection.back(), tolerance)) {
                        interior_inside = false;
                        break;
                    }
                }
                if (!interior_inside) continue;
            }

            Eval aggregate;
            aggregate.valid = true;
            for (std::size_t layer = 0; layer < layer_count && aggregate.valid; ++layer) {
                for (const auto index : cycle) {
                    const auto lower_a =
                        layer == 0U ? oriented_a[index] : front_by_vertex[layer - 1U].at(oriented_a[index]);
                    const auto lower_b =
                        layer == 0U ? oriented_b[index] : front_by_vertex[layer - 1U].at(oriented_b[index]);
                    const auto upper_a = front_by_vertex[layer].at(oriented_a[index]);
                    const auto upper_b = front_by_vertex[layer].at(oriented_b[index]);
                    const Tri choice0{lower_a, lower_b, upper_b};
                    const Tri choice0_second{lower_a, upper_b, upper_a};
                    const Tri choice1{lower_a, lower_b, upper_a};
                    const Tri choice1_second{lower_b, upper_b, upper_a};
                    const auto score0 = evaluate({choice0, choice0_second});
                    const auto score1 = evaluate({choice1, choice1_second});
                    const auto rank = [](const Eval& score, int diagonal) {
                        return std::tuple{score.valid ? 0 : 1, score.surface_deviation,
                                           score.non_orthogonality, score.skewness,
                                           score.aspect, diagonal};
                    };
                    if (!score0.valid && !score1.valid) {
                        aggregate.valid = false;
                        break;
                    }
                    const Eval& selected = rank(score0, 0) <= rank(score1, 1)
                        ? score0 : score1;
                    aggregate.surface_deviation =
                        std::max(aggregate.surface_deviation, selected.surface_deviation);
                    aggregate.non_orthogonality =
                        std::max(aggregate.non_orthogonality, selected.non_orthogonality);
                    aggregate.skewness =
                        std::max(aggregate.skewness, selected.skewness);
                    aggregate.aspect =
                        std::max(aggregate.aspect, selected.aspect);
                }
            }
            if (!aggregate.valid) continue;
            const auto rank = std::tuple{
                aggregate.non_orthogonality, aggregate.skewness,
                aggregate.aspect, -candidate_scale};
            if (!found || rank < best_rank) {
                found = true;
                best_scale = candidate_scale;
                best_rank = rank;
                best_points = working_points;
            }
        }
        if (!found) {
            // The one-to-one front is only the first bounded template. Keep
            // the source/front coordinates unchanged and let the strict
            // subdivided-strip template attempt the next candidate.
            working_points = baseline_points;
            validate_current_front();
            optimized_front_scale = 1.0;
        } else {
            working_points = std::move(best_points);
            optimized_front_scale = best_scale;
            if (!validate_current_front())
                return refuse("planar_cavity_strict_front_validation_failed");
        }
    }

    if (strict_quality) {
        if (regular_hex_topology) {
            const P center = point(source_interior_vertices.front());
            P centroid{};
            for (const auto vertex : boundary_vertices) {
                const P source = point(vertex);
                centroid = add(centroid, source);
            }
            centroid = mul(
                centroid,
                1.0 / static_cast<double>(boundary_vertices.size()));
            const double geometry_tolerance = std::max(tolerance, 1.0e-8 * scale);
            const double center_deviation =
                autotessell_surface_bl_quality::length(sub(centroid, center));
            bool compatible = center_deviation <= geometry_tolerance;
            const double reference_radius =
                autotessell_surface_bl_quality::length(
                    sub(point(boundary_vertices.front()), center));
            const double reference_edge = autotessell_surface_bl_quality::length(
                sub(point(boundary_vertices.front()),
                    point(boundary_vertices[1])));
            for (std::size_t i = 0; i < boundary_vertices.size() && compatible;
                 ++i) {
                const auto current = boundary_vertices[i];
                const auto next =
                    boundary_vertices[(i + 1U) % boundary_vertices.size()];
                const P source = point(current);
                const P front =
                    point(front_by_vertex[0].at(current));
                const P expected_front{
                    center[0] + 0.5 * (source[0] - center[0]),
                    center[1] + 0.5 * (source[1] - center[1]),
                    center[2] + 0.5 * (source[2] - center[2])};
                const double front_deviation =
                    autotessell_surface_bl_quality::length(
                        sub(front, expected_front));
                const double radius =
                    autotessell_surface_bl_quality::length(
                        sub(source, center));
                const double edge_length =
                    autotessell_surface_bl_quality::length(
                        sub(point(next), source));
                if (front_deviation > geometry_tolerance ||
                    std::abs(radius - reference_radius) > geometry_tolerance ||
                    std::abs(edge_length - reference_edge) >
                        geometry_tolerance)
                    compatible = false;
            }
            if (compatible) {
                regular_hex_zipper = true;
                selected_phase_offset = 0.0;
            }
        } else {
        const auto validate_phase_front = [&]() {
            for (std::size_t layer = 0; layer < layer_count; ++layer) {
                const auto& lower_projection =
                    layer == 0U ? boundary_projection :
                    front_projection[layer - 1U];
                auto& current_projection = front_projection[layer];
                current_projection.clear();
                current_projection.reserve(front_vertices[layer].size());
                for (const auto vertex : front_vertices[layer]) {
                    current_projection.push_back(
                        project(point(vertex), dropped_axis));
                    if (!point_inside_polygon(
                            current_projection.back(), lower_projection,
                            tolerance))
                        return false;
                }
                for (std::size_t i = 0; i < current_projection.size(); ++i) {
                    const std::size_t next_i = (i + 1U) % current_projection.size();
                    for (std::size_t j = i + 1U;
                         j < current_projection.size(); ++j) {
                        const std::size_t next_j = (j + 1U) % current_projection.size();
                        if (i == j || next_i == j || next_j == i) continue;
                        if (segments_intersect(
                                current_projection[i],
                                current_projection[next_i],
                                current_projection[j],
                                current_projection[next_j],
                                tolerance))
                            return false;
                    }
                    for (std::size_t j = 0; j < lower_projection.size(); ++j) {
                        if (segments_intersect(
                                current_projection[i],
                                current_projection[next_i],
                                lower_projection[j],
                                lower_projection[(j + 1U) %
                                                 lower_projection.size()],
                                tolerance))
                            return false;
                    }
                }
                double area = 0.0;
                for (std::size_t i = 0; i < front_vertices[layer].size(); ++i)
                    area += signed_area(
                        point(front_vertices[layer][i]),
                        point(front_vertices[layer][(i + 1U) %
                                                     front_vertices[layer].size()]),
                        scale_point);
                if (!(std::isfinite(area) && area > tolerance)) return false;
            }
            return true;
        };

        const auto front_score = [&]() {
            Eval aggregate;
            aggregate.valid = true;
            for (std::size_t layer = 0; layer < layer_count && aggregate.valid;
                 ++layer) {
                for (const auto index : cycle) {
                    const auto lower_a =
                        layer == 0U ? oriented_a[index] :
                        front_by_vertex[layer - 1U].at(oriented_a[index]);
                    const auto lower_b =
                        layer == 0U ? oriented_b[index] :
                        front_by_vertex[layer - 1U].at(oriented_b[index]);
                    const auto upper_a =
                        front_by_vertex[layer].at(oriented_a[index]);
                    const auto upper_b =
                        front_by_vertex[layer].at(oriented_b[index]);
                    const Tri choice0{lower_a, lower_b, upper_b};
                    const Tri choice0_second{lower_a, upper_b, upper_a};
                    const Tri choice1{lower_a, lower_b, upper_a};
                    const Tri choice1_second{lower_b, upper_b, upper_a};
                    const auto score0 = evaluate({choice0, choice0_second});
                    const auto score1 = evaluate({choice1, choice1_second});
                    const auto rank = [](const Eval& score, int diagonal) {
                        return std::tuple{score.valid ? 0 : 1,
                                           score.surface_deviation,
                                           score.non_orthogonality,
                                           score.skewness,
                                           score.aspect, diagonal};
                    };
                    if (!score0.valid && !score1.valid) {
                        aggregate.valid = false;
                        break;
                    }
                    const Eval& selected = rank(score0, 0) <= rank(score1, 1)
                        ? score0 : score1;
                    aggregate.surface_deviation =
                        std::max(aggregate.surface_deviation,
                                 selected.surface_deviation);
                    aggregate.non_orthogonality =
                        std::max(aggregate.non_orthogonality,
                                 selected.non_orthogonality);
                    aggregate.skewness =
                        std::max(aggregate.skewness, selected.skewness);
                    aggregate.aspect =
                        std::max(aggregate.aspect, selected.aspect);
                }
            }
            return aggregate;
        };

        const std::vector<P> phase_base = working_points;
        std::map<std::int64_t, P> phase_directions;
        std::map<std::int64_t, double> phase_scales;
        for (std::size_t i = 0; i < boundary_vertices.size(); ++i) {
            const auto vertex = boundary_vertices[i];
            const auto previous =
                boundary_vertices[(i + boundary_vertices.size() - 1U) %
                                  boundary_vertices.size()];
            const auto next =
                boundary_vertices[(i + 1U) % boundary_vertices.size()];
            const P incoming = unit(sub(point(vertex), point(previous)));
            const P outgoing = unit(sub(point(next), point(vertex)));
            const P turn = sub(outgoing, incoming);
            const double turn_length =
                autotessell_surface_bl_quality::length(turn);
            if (turn_length > 1.0e-12) {
                phase_directions[vertex] = unit(turn);
            } else {
                phase_directions[vertex] = P{0.0, 0.0, 0.0};
            }
            const double local_length = 0.5 * (
                autotessell_surface_bl_quality::length(
                    sub(point(vertex), point(previous))) +
                autotessell_surface_bl_quality::length(
                    sub(point(next), point(vertex))));
            phase_scales[vertex] = 0.25 * local_length;
        }

        const std::array<double, 5> phase_candidates{
            -0.5, -1.0 / 3.0, 0.0, 1.0 / 3.0, 0.5};
        bool phase_found = false;
        double best_phase = 0.0;
        std::vector<P> best_phase_points;
        std::tuple<double, double, double, double, double> best_phase_rank{
            1.0e300, 1.0e300, 1.0e300, 1.0e300, 1.0e300};
        for (const double phase : phase_candidates) {
            working_points = phase_base;
            for (std::size_t layer = 0; layer < layer_count; ++layer) {
                for (const auto vertex : boundary_vertices) {
                    const auto id = front_by_vertex[layer].at(vertex);
                    const P displacement = mul(
                        phase_directions.at(vertex),
                        phase * phase_scales.at(vertex));
                    working_points[static_cast<std::size_t>(id)] =
                        add(phase_base[static_cast<std::size_t>(id)],
                            displacement);
                }
            }
            if (!validate_phase_front()) continue;
            if (!source_interior_vertices.empty()) {
                bool interior_inside = true;
                for (const auto vertex : source_interior_vertices) {
                    if (!point_inside_polygon(
                            project(point(vertex), dropped_axis),
                            front_projection.back(), tolerance)) {
                        interior_inside = false;
                        break;
                    }
                }
                if (!interior_inside) continue;
            }
            const Eval aggregate = front_score();
            if (!aggregate.valid) continue;
            const auto rank = std::tuple{
                aggregate.non_orthogonality, aggregate.skewness,
                aggregate.aspect, std::abs(phase), phase};
            if (!phase_found || rank < best_phase_rank) {
                phase_found = true;
                best_phase = phase;
                best_phase_rank = rank;
                best_phase_points = working_points;
            }
        }
        if (phase_found) {
            working_points = std::move(best_phase_points);
            selected_phase_offset = best_phase;
            if (!validate_phase_front())
                return refuse("planar_cavity_phase_front_validation_failed");
        } else {
            working_points = phase_base;
            validate_phase_front();
            selected_phase_offset = 0.0;
        }

        }
    }

    std::size_t subdivision_factor = regular_hex_zipper ? 2U : 1U;
    if (strict_quality && !regular_hex_zipper) {
        long double target_count_sum = 0.0L;
        std::size_t target_count_samples = 0U;
        const long double sqrt_three = std::sqrt(3.0L);
        for (const auto index : cycle) {
            const P source_a = point(oriented_a[index]);
            const P source_b = point(oriented_b[index]);
            const P front_a = point(front_by_vertex.back().at(oriented_a[index]));
            const P front_b = point(front_by_vertex.back().at(oriented_b[index]));
            const long double source_length = static_cast<long double>(
                autotessell_surface_bl_quality::length(sub(source_b, source_a)));
            const long double height_a = static_cast<long double>(
                autotessell_surface_bl_quality::length(sub(front_a, source_a)));
            const long double height_b = static_cast<long double>(
                autotessell_surface_bl_quality::length(sub(front_b, source_b)));
            const long double height = 0.5L * (height_a + height_b);
            const long double target_length = 2.0L * height / sqrt_three;
            if (std::isfinite(source_length) && std::isfinite(target_length) &&
                source_length > 0.0L && target_length > 0.0L) {
                target_count_sum += source_length / target_length;
                ++target_count_samples;
            }
        }
        if (target_count_samples != 0U) {
            const long double average_count =
                target_count_sum / static_cast<long double>(target_count_samples);
            const auto rounded = static_cast<long long>(std::llround(average_count));
            subdivision_factor = static_cast<std::size_t>(
                std::clamp(rounded, 1LL, 16LL));
        }
    }

    std::vector<std::vector<std::vector<std::int64_t>>> front_subdivision_ids(
        layer_count + 1U,
        std::vector<std::vector<std::int64_t>>(
            edge_count,
            std::vector<std::int64_t>(
                subdivision_factor > 1U ? subdivision_factor - 1U : 0U)));
    std::set<std::int64_t> output_generated_ids = generated_ids;
    py::list generated_vertex_lineage;
    py::list interval_ledger;
    py::list count_ledger;
    for (std::size_t level = 0; level <= layer_count; ++level) {
        for (const auto index : cycle) {
            const std::size_t count =
                regular_hex_zipper ? (level == 0U ? 2U : 1U) :
                subdivision_factor;
            py::dict ledger;
            ledger["source_edge_id"] = edge_data[index * 4U];
            ledger["source_wall_edge"] =
                std::to_string(edge_data[index * 4U]);
            ledger["layer"] = static_cast<std::int64_t>(level);
            ledger["count"] = static_cast<std::int64_t>(count);
            count_ledger.append(ledger);
        }
    }
    if (regular_hex_zipper) {
        for (const auto index : cycle) {
            const auto endpoint_a = oriented_a[index];
            const auto endpoint_b = oriented_b[index];
            const P a = point(endpoint_a);
            const P b = point(endpoint_b);
            const P midpoint{
                0.5 * (a[0] + b[0]),
                0.5 * (a[1] + b[1]),
                0.5 * (a[2] + b[2])};
            if (!finite(midpoint))
                return refuse("planar_cavity_subdivision_midpoint_nonfinite");
            const auto id = static_cast<std::int64_t>(working_points.size());
            working_points.push_back(midpoint);
            front_subdivision_ids[0][index][0] = id;
            output_generated_ids.insert(id);

            py::dict lineage;
            lineage["id"] = id;
            lineage["source_edge_id"] = edge_data[index * 4U];
            lineage["source_wall_edge"] =
                std::to_string(edge_data[index * 4U]);
            lineage["source_face_id"] = edge_data[index * 4U + 3U];
            lineage["layer"] = 0;
            lineage["parameter"] = 0.5;
            lineage["parameter_numerator"] = 1;
            lineage["parameter_denominator"] = 2;
            lineage["parent_vertex_ids"] =
                py::make_tuple(endpoint_a, endpoint_b);
            lineage["lineage_role"] = "subdivided_front_vertex";
            lineage["target_receipt_digest"] =
                "source-boundary-midpoint";
            generated_vertex_lineage.append(lineage);

            for (std::size_t segment = 0U; segment < 2U; ++segment) {
                py::dict interval;
                interval["source_edge_id"] = edge_data[index * 4U];
                interval["source_wall_edge"] =
                    std::to_string(edge_data[index * 4U]);
                interval["layer"] = 0;
                interval["subdivision_factor"] = 2;
                interval["interval_index"] =
                    static_cast<std::int64_t>(segment);
                interval["t0"] = 0.5 * static_cast<double>(segment);
                interval["t1"] =
                    0.5 * static_cast<double>(segment + 1U);
                interval["t0_numerator"] =
                    static_cast<std::int64_t>(segment);
                interval["t1_numerator"] =
                    static_cast<std::int64_t>(segment + 1U);
                interval["parameter_denominator"] = 2;
                interval_ledger.append(interval);
            }
        }
        child_vertices = front_vertices.back();
    } else if (subdivision_factor > 1U) {
        for (std::size_t level = 0; level <= layer_count; ++level) {
            for (const auto index : cycle) {
                const auto endpoint_a =
                    level == 0U ? oriented_a[index] :
                    front_by_vertex[level - 1U].at(oriented_a[index]);
                const auto endpoint_b =
                    level == 0U ? oriented_b[index] :
                    front_by_vertex[level - 1U].at(oriented_b[index]);
                const P a = point(endpoint_a);
                const P b = point(endpoint_b);
                for (std::size_t segment = 1U;
                     segment < subdivision_factor; ++segment) {
                    const double parameter =
                        static_cast<double>(segment) /
                        static_cast<double>(subdivision_factor);
                    const P interpolated{
                        a[0] + parameter * (b[0] - a[0]),
                        a[1] + parameter * (b[1] - a[1]),
                        a[2] + parameter * (b[2] - a[2])};
                    if (!finite(interpolated))
                        return refuse("planar_cavity_subdivision_midpoint_nonfinite");
                    const auto id = static_cast<std::int64_t>(
                        working_points.size());
                    working_points.push_back(interpolated);
                    front_subdivision_ids[level][index][segment - 1U] = id;
                    output_generated_ids.insert(id);

                    py::dict lineage;
                    lineage["id"] = id;
                    lineage["source_edge_id"] = edge_data[index * 4U];
                    lineage["source_wall_edge"] =
                        std::to_string(edge_data[index * 4U]);
                    lineage["source_face_id"] = edge_data[index * 4U + 3U];
                    lineage["layer"] = static_cast<std::int64_t>(level);
                    lineage["parameter"] = parameter;
                    lineage["parameter_numerator"] =
                        static_cast<std::int64_t>(segment);
                    lineage["parameter_denominator"] =
                        static_cast<std::int64_t>(subdivision_factor);
                    lineage["parent_vertex_ids"] =
                        py::make_tuple(endpoint_a, endpoint_b);
                    lineage["lineage_role"] = "subdivided_front_vertex";
                    if (level > 0U) {
                        const auto provenance_index =
                            (level - 1U) * edge_count + index;
                        const py::dict target_row =
                            provenance[py::ssize_t(provenance_index)]
                                .cast<py::dict>();
                        if (target_row.contains("target_receipt_digest"))
                            lineage["target_receipt_digest"] =
                                target_row["target_receipt_digest"];
                    } else {
                        lineage["target_receipt_digest"] =
                            "source-boundary-midpoint";
                    }
                    generated_vertex_lineage.append(lineage);
                }

                for (std::size_t segment = 0U;
                     segment < subdivision_factor; ++segment) {
                    py::dict interval;
                    interval["source_edge_id"] = edge_data[index * 4U];
                    interval["source_wall_edge"] =
                        std::to_string(edge_data[index * 4U]);
                    interval["layer"] =
                        static_cast<std::int64_t>(level);
                    interval["subdivision_factor"] =
                        static_cast<std::int64_t>(subdivision_factor);
                    interval["interval_index"] =
                        static_cast<std::int64_t>(segment);
                    interval["t0"] =
                        static_cast<double>(segment) /
                        static_cast<double>(subdivision_factor);
                    interval["t1"] =
                        static_cast<double>(segment + 1U) /
                        static_cast<double>(subdivision_factor);
                    interval["t0_numerator"] =
                        static_cast<std::int64_t>(segment);
                    interval["t1_numerator"] =
                        static_cast<std::int64_t>(segment + 1U);
                    interval["parameter_denominator"] =
                        static_cast<std::int64_t>(subdivision_factor);
                    interval_ledger.append(interval);
                }
            }
        }
        child_vertices.clear();
        child_vertices.reserve(
            boundary_vertices.size() * subdivision_factor);
        for (const auto index : cycle) {
            child_vertices.push_back(
                front_by_vertex.back().at(oriented_a[index]));
            for (const auto id : front_subdivision_ids[layer_count][index])
                child_vertices.push_back(id);
        }
    }

    const auto emit_strip_quad = [&](std::int64_t lower_a,
                                     std::int64_t lower_b,
                                     std::int64_t upper_a,
                                     std::int64_t upper_b,
                                     std::int64_t face,
                                     std::size_t layer,
                                     std::size_t index) {
        const Tri choice0{lower_a, lower_b, upper_b};
        const Tri choice0_second{lower_a, upper_b, upper_a};
        const Tri choice1{lower_a, lower_b, upper_a};
        const Tri choice1_second{lower_b, upper_b, upper_a};
        const auto score0 = evaluate({choice0, choice0_second});
        const auto score1 = evaluate({choice1, choice1_second});
        const auto rank = [](const Eval& score, int diagonal) {
            return std::tuple{score.valid ? 0 : 1, score.surface_deviation,
                               score.non_orthogonality, score.skewness,
                               score.aspect, diagonal};
        };
        if (!score0.valid && !score1.valid) return false;
        const bool use_first = rank(score0, 0) <= rank(score1, 1);
        const auto& selected = use_first ? score0 : score1;
        const std::array<Tri, 2> selected_faces = use_first
            ? std::array<Tri, 2>{choice0, choice0_second}
            : std::array<Tri, 2>{choice1, choice1_second};
        const auto provenance_index = layer * edge_count + index;
        const py::dict& layer_template =
            provenance[static_cast<py::ssize_t>(provenance_index)].cast<py::dict>();
        for (const auto& tri : selected_faces) {
            if (!append_face(
                    tri, layer_template, {face}, "boundary_layer_strip"))
                return false;
            record_quality(
                tri, static_cast<std::int64_t>(layer + 1U),
                "boundary_layer_strip");
        }
        max_skew = std::max(max_skew, selected.skewness);
        max_aspect = std::max(max_aspect, selected.aspect);
        max_nonorth = std::max(max_nonorth, selected.non_orthogonality);
        return true;
    };

    for (std::size_t layer = 0; layer < layer_count; ++layer) {
        for (const auto index : cycle) {
            const auto face = edge_data[index * 4U + 3U];
            const auto a = oriented_a[index];
            const auto b = oriented_b[index];
            const auto lower_a =
                layer == 0U ? a : front_by_vertex[layer - 1U].at(a);
            const auto lower_b =
                layer == 0U ? b : front_by_vertex[layer - 1U].at(b);
            const auto upper_a = front_by_vertex[layer].at(a);
            const auto upper_b = front_by_vertex[layer].at(b);
            if (regular_hex_zipper) {
                const auto midpoint = front_subdivision_ids[0][index][0];
                const std::array<Tri, 3> zipper_faces{
                    Tri{a, midpoint, upper_a},
                    Tri{midpoint, upper_b, upper_a},
                    Tri{midpoint, b, upper_b}};
                const auto provenance_index = layer * edge_count + index;
                const py::dict& layer_template =
                    provenance[py::ssize_t(provenance_index)].cast<py::dict>();
                for (const auto& tri : zipper_faces) {
                    const auto score = evaluate({tri});
                    if (!score.valid ||
                        !append_face(
                            tri, layer_template, {face},
                            "boundary_layer_zipper"))
                        return refuse(
                            "planar_cavity_regular_hex_zipper_quality_failure");
                    record_quality(
                        tri, static_cast<std::int64_t>(layer + 1U),
                        "boundary_layer_zipper");
                    max_skew = std::max(max_skew, score.skewness);
                    max_aspect = std::max(max_aspect, score.aspect);
                    max_nonorth = std::max(
                        max_nonorth, score.non_orthogonality);
                }
                continue;
            }
            for (std::size_t segment = 0U;
                 segment < subdivision_factor; ++segment) {
                const auto lower_start =
                    segment == 0U
                        ? lower_a
                        : front_subdivision_ids[layer][index][segment - 1U];
                const auto lower_end =
                    segment + 1U == subdivision_factor
                        ? lower_b
                        : front_subdivision_ids[layer][index][segment];
                const auto upper_start =
                    segment == 0U
                        ? upper_a
                        : front_subdivision_ids[layer + 1U][index][segment - 1U];
                const auto upper_end =
                    segment + 1U == subdivision_factor
                        ? upper_b
                        : front_subdivision_ids[layer + 1U][index][segment];
                if (!emit_strip_quad(
                        lower_start, lower_end, upper_start, upper_end,
                        face, layer, index))
                    return refuse(
                        subdivision_factor > 1U
                            ? "planar_cavity_subdivided_strip_quality_failure"
                            : "planar_cavity_strip_quality_failure");
            }
        }
    }
    std::vector<std::int64_t> all_faces;
    for (py::ssize_t face = 0; face < source_triangles.shape(0); ++face) all_faces.push_back(face);
    const auto& core_template = face_templates.begin()->second;
    struct CoreChoice {
        bool valid = false;
        Eval score;
        std::vector<Tri> faces;
    };
    std::map<std::pair<int, int>, CoreChoice> core_memo;
    const auto core_rank = [](const CoreChoice& choice) {
        return std::tuple{choice.valid ? 0 : 1, choice.score.surface_deviation,
                           choice.score.non_orthogonality, choice.score.skewness,
                           choice.score.aspect};
    };
    std::function<CoreChoice(int, int)> solve_core = [&](int left, int right) {
        const auto key = std::make_pair(left, right);
        const auto cached = core_memo.find(key);
        if (cached != core_memo.end()) return cached->second;
        CoreChoice best;
        if (right - left <= 1) {
            best.valid = true;
            best.score.valid = true;
            core_memo.emplace(key, best);
            return best;
        }
        for (int split = left + 1; split < right; ++split) {
            const CoreChoice left_choice = solve_core(left, split);
            const CoreChoice right_choice = solve_core(split, right);
            if (!left_choice.valid || !right_choice.valid) continue;
            const Tri triangle{child_vertices[static_cast<std::size_t>(left)],
                               child_vertices[static_cast<std::size_t>(split)],
                               child_vertices[static_cast<std::size_t>(right)]};
            const Eval triangle_score = evaluate({triangle});
            if (!triangle_score.valid) continue;
            CoreChoice candidate;
            candidate.valid = true;
            candidate.score.valid = true;
            candidate.score.surface_deviation = std::max(
                {left_choice.score.surface_deviation, right_choice.score.surface_deviation,
                 triangle_score.surface_deviation});
            candidate.score.non_orthogonality = std::max(
                {left_choice.score.non_orthogonality, right_choice.score.non_orthogonality,
                 triangle_score.non_orthogonality});
            candidate.score.skewness = std::max(
                {left_choice.score.skewness, right_choice.score.skewness,
                 triangle_score.skewness});
            candidate.score.aspect = std::max(
                {left_choice.score.aspect, right_choice.score.aspect, triangle_score.aspect});
            candidate.faces = left_choice.faces;
            candidate.faces.insert(candidate.faces.end(), right_choice.faces.begin(), right_choice.faces.end());
            candidate.faces.push_back(triangle);
            if (!best.valid || core_rank(candidate) < core_rank(best)) best = std::move(candidate);
        }
        core_memo.emplace(key, best);
        return best;
    };
    CoreChoice core;
    if (!source_interior_vertices.empty()) {
        std::map<std::int64_t, std::int64_t> core_vertex_ids;
        for (const auto vertex : boundary_vertices)
            core_vertex_ids[vertex] = front_by_vertex.back().at(vertex);
        for (const auto vertex : source_interior_vertices) {
            const auto projection = project(point(vertex), dropped_axis);
            if (!point_inside_polygon(
                    projection, front_projection.back(), tolerance))
                return refuse("planar_cavity_core_point_outside_front");
            core_vertex_ids[vertex] = vertex;
        }
        core.valid = true;
        core.score.valid = true;
        if (subdivision_factor > 1U) {
            if (source_interior_vertices.size() != 1U)
                return refuse("planar_cavity_subdivision_core_requires_one_interior_vertex");
            const auto center = source_interior_vertices.front();
            for (std::size_t i = 0; i < child_vertices.size(); ++i) {
                const Tri triangle{
                    center,
                    child_vertices[i],
                    child_vertices[(i + 1U) % child_vertices.size()]};
                const Eval triangle_score = evaluate({triangle});
                if (!triangle_score.valid) {
                    core.valid = false;
                    break;
                }
                core.score.surface_deviation = std::max(
                    core.score.surface_deviation, triangle_score.surface_deviation);
                core.score.non_orthogonality = std::max(
                    core.score.non_orthogonality, triangle_score.non_orthogonality);
                core.score.skewness = std::max(
                    core.score.skewness, triangle_score.skewness);
                core.score.aspect = std::max(
                    core.score.aspect, triangle_score.aspect);
                core.faces.push_back(triangle);
            }
        } else {
            for (py::ssize_t face = 0;
                 face < source_triangles.shape(0); ++face) {
                const auto offset = static_cast<std::size_t>(face) * 3U;
                const Tri triangle{
                    core_vertex_ids.at(triangle_data[offset]),
                    core_vertex_ids.at(triangle_data[offset + 1U]),
                    core_vertex_ids.at(triangle_data[offset + 2U])};
                const Eval triangle_score = evaluate({triangle});
                if (!triangle_score.valid) {
                    core.valid = false;
                    break;
                }
                core.score.surface_deviation = std::max(
                    core.score.surface_deviation, triangle_score.surface_deviation);
                core.score.non_orthogonality = std::max(
                    core.score.non_orthogonality, triangle_score.non_orthogonality);
                core.score.skewness = std::max(
                    core.score.skewness, triangle_score.skewness);
                core.score.aspect = std::max(
                    core.score.aspect, triangle_score.aspect);
                core.faces.push_back(triangle);
            }
        }
    } else {
        core = solve_core(0, static_cast<int>(child_vertices.size()) - 1);
    }
    if (!core.valid) return refuse("planar_cavity_core_quality_failure");
    for (const auto& triangle : core.faces) {
        if (!append_face(triangle, core_template, all_faces, "child_front_core"))
            return refuse("planar_cavity_core_face_duplicate");
        const auto score = evaluate({triangle});
        record_quality(
            triangle, static_cast<std::int64_t>(requested_layers),
            "child_front_core");
        max_skew = std::max(max_skew, score.skewness);
        max_aspect = std::max(max_aspect, score.aspect);
        max_nonorth = std::max(max_nonorth, score.non_orthogonality);
    }

    std::map<EdgeKey, int> edge_counts;
    std::int64_t invalid = 0;
    std::int64_t inverted = 0;
    std::int64_t duplicate = 0;
    for (const auto& tri : faces) {
        auto key = tri;
        std::sort(key.begin(), key.end());
        if (!face_keys.count(key)) ++duplicate;
        for (int i = 0; i < 3; ++i) ++edge_counts[edge_key(tri[i], tri[(i + 1) % 3])];
        if (!(signed_area(point(tri[0]), point(tri[1]), point(tri[2])) > epsilon)) ++inverted;
    }
    std::int64_t nonmanifold = 0;
    for (const auto& [edge, count] : edge_counts) if (count > 2) ++nonmanifold;
    if (invalid || inverted || duplicate || nonmanifold)
        return refuse("planar_cavity_final_topology_failed");

    const auto independent_audit =
        autotessell_surface_bl_independent_audit::audit_faces(
            working_points, faces, scale_point, reference_normal,
            static_cast<long double>(epsilon),
            static_cast<long double>(tolerance));
    if (!independent_audit.finite || independent_audit.invalid != 0 ||
        independent_audit.inverted != 0 ||
        independent_audit.duplicate != 0 ||
        independent_audit.non_manifold != 0 ||
        independent_audit.self_intersection != 0 ||
        independent_audit.source_plane_deviation >
            static_cast<long double>(tolerance))
        return refuse("planar_cavity_long_double_audit_failure");
    if (strict_quality &&
        !autotessell_surface_bl_independent_audit::strict_maxima_pass(
            independent_audit))
        return refuse("planar_cavity_long_double_strict_quality_failure");

    py::dict independent_audit_dict;
    independent_audit_dict["accepted"] = true;
    independent_audit_dict["invalid"] = independent_audit.invalid;
    independent_audit_dict["inverted"] = independent_audit.inverted;
    independent_audit_dict["duplicate"] = independent_audit.duplicate;
    independent_audit_dict["non_manifold"] = independent_audit.non_manifold;
    independent_audit_dict["self_intersection"] =
        independent_audit.self_intersection;
    independent_audit_dict["max_skewness"] =
        static_cast<double>(independent_audit.max_skewness);
    independent_audit_dict["max_aspect_ratio"] =
        static_cast<double>(independent_audit.max_aspect);
    independent_audit_dict["max_non_orthogonality_degrees"] =
        static_cast<double>(independent_audit.max_non_orthogonality_degrees);
    independent_audit_dict["p95_skewness"] =
        static_cast<double>(independent_audit.p95_skewness);
    independent_audit_dict["p99_skewness"] =
        static_cast<double>(independent_audit.p99_skewness);
    independent_audit_dict["p95_aspect_ratio"] =
        static_cast<double>(independent_audit.p95_aspect);
    independent_audit_dict["p99_aspect_ratio"] =
        static_cast<double>(independent_audit.p99_aspect);
    independent_audit_dict["p95_non_orthogonality_degrees"] =
        static_cast<double>(independent_audit.p95_non_orthogonality_degrees);
    independent_audit_dict["p99_non_orthogonality_degrees"] =
        static_cast<double>(independent_audit.p99_non_orthogonality_degrees);
    independent_audit_dict["source_plane_deviation"] =
        static_cast<double>(independent_audit.source_plane_deviation);
    independent_audit_dict["metric_kernel"] =
        "independent_long_double_no_strip_triangle_quality";

    py::list output_faces;
    for (const auto& tri : faces) {
        py::list row;
        row.append(tri[0]);
        row.append(tri[1]);
        row.append(tri[2]);
        output_faces.append(row);
    }
    py::list removed;
    for (const auto face : all_faces) removed.append(face);
    py::dict quality;
    quality["max_skewness"] = max_skew;
    quality["max_triangle_aspect_ratio"] = max_aspect;
    quality["max_non_orthogonality_degrees"] = max_nonorth;
    quality["skewness_limit"] = max_skew_gate;
    quality["triangle_aspect_limit"] = max_aspect_gate;
    quality["non_orthogonality_limit_degrees"] = max_nonorth_gate;
    quality["source_surface_deviation"] = 0.0;
    quality["actual_layers"] = static_cast<std::int64_t>(requested_layers);
    quality["subdivision_factor"] =
        static_cast<std::int64_t>(subdivision_factor);
    quality["independent_long_double_audit"] = independent_audit_dict;
    quality["phase_offset"] = selected_phase_offset;
    quality["count_ledger"] = count_ledger;
    py::list point_updates;
    for (const auto id : output_generated_ids) {
        const auto& current = working_points.at(static_cast<std::size_t>(id));
        bool changed = id >= static_cast<std::int64_t>(baseline_points.size());
        if (!changed) {
            const auto& original = baseline_points.at(static_cast<std::size_t>(id));
            changed =
                std::abs(original[0] - current[0]) > 1.0e-15 ||
                std::abs(original[1] - current[1]) > 1.0e-15 ||
                std::abs(original[2] - current[2]) > 1.0e-15;
        }
        if (!changed) continue;
        py::dict update;
        update["id"] = id;
        update["x"] = current[0];
        update["y"] = current[1];
        update["z"] = current[2];
        point_updates.append(update);
    }
    py::dict result;
    result["accepted"] = true;
    result["status"] = "surface_bl_planar_cavity_artifact_sealed";
    result["reason"] = "planar_cavity_replacement_quality_passed";
    result["replacement_mode"] = "planar_cavity";
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = requested_layers;
    result["generated_faces"] = output_faces;
    result["provenance"] = output_provenance;
    result["quality"] = quality;
    result["quality_witness"] = quality_witness;
    result["strict_quality"] = strict_quality;
    result["point_updates"] = point_updates;
    result["optimized_front_scale"] = optimized_front_scale;
    result["generated_vertex_lineage"] = generated_vertex_lineage;
    result["interval_ledger"] = interval_ledger;
    result["independent_long_double_audit"] = independent_audit_dict;
    result["phase_offset"] = selected_phase_offset;
    result["count_ledger"] = count_ledger;
    result["subdivision_factor"] =
        static_cast<std::int64_t>(subdivision_factor);
    result["source_faces_removed"] = removed;
    result["source_faces_retained"] = py::list();
    result["source_face_coverage_complete"] = true;
    result["topology_invalid"] = invalid;
    result["topology_inverted"] = inverted;
    result["topology_duplicate"] = duplicate;
    result["topology_non_manifold"] = nonmanifold;
    result["topology_self_intersection"] = 0;
    result["candidate_discarded"] = false;
    result["publication_eligible"] = false;
    result["count_is_report_only"] = true;
    return result;
}
