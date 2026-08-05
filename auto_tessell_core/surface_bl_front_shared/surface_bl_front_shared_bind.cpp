// C++23 shared-vertex physical-space surface BL candidate transaction.
// Standalone and default-off: it never mutates or routes production state.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <ranges>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;

namespace {

Point add(const Point& a, const Point& b) noexcept { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
Point sub(const Point& a, const Point& b) noexcept { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point mul(const Point& a, double s) noexcept { return {a[0] * s, a[1] * s, a[2] * s}; }
double dot(const Point& a, const Point& b) noexcept { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
Point cross(const Point& a, const Point& b) noexcept {
    return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]};
}
double norm(const Point& a) noexcept { return std::sqrt(dot(a, a)); }
bool finite_point(const Point& a) noexcept { return std::ranges::all_of(a, [](double v) { return std::isfinite(v); }); }

Point unit(const Point& a, const char* name) {
    const double length = norm(a);
    if (!(length > 1.0e-14) || !std::isfinite(length)) throw std::invalid_argument(std::string(name) + " must be nonzero and finite");
    return mul(a, 1.0 / length);
}

bool contains_vertex(const std::array<std::int64_t, 3>& tri, std::int64_t id) noexcept { return tri[0] == id || tri[1] == id || tri[2] == id; }

bool segment_hits_triangle(const Point& origin, const Point& endpoint, const Point& a, const Point& b, const Point& c) noexcept {
    constexpr double eps = 1.0e-12;
    const Point direction = sub(endpoint, origin);
    const Point edge1 = sub(b, a);
    const Point edge2 = sub(c, a);
    const Point pvec = cross(direction, edge2);
    const double determinant = dot(edge1, pvec);
    if (std::abs(determinant) <= eps) return false;
    const double inverse = 1.0 / determinant;
    const Point tvec = sub(origin, a);
    const double u = dot(tvec, pvec) * inverse;
    if (u < -eps || u > 1.0 + eps) return false;
    const Point qvec = cross(tvec, edge1);
    const double v = dot(direction, qvec) * inverse;
    if (v < -eps || u + v > 1.0 + eps) return false;
    const double distance = dot(edge2, qvec) * inverse;
    return distance >= -eps && distance <= 1.0 + eps;
}

struct EdgeSpec { std::int64_t id; std::int64_t first; std::int64_t second; std::int64_t face; };
struct VertexRecord { std::int64_t id; std::int64_t source_vertex; std::int64_t layer; Point position; };
struct FaceRecord { std::int64_t source_edge; std::int64_t layer; std::int64_t source_a; std::int64_t source_b; std::int64_t generated_a; std::int64_t generated_b; };
struct LineageRecord {
    std::int64_t source_wall_edge;
    std::int64_t source_face;
    std::int64_t layer;
    std::int64_t generated_a;
    std::int64_t generated_b;
    std::string patch;
    std::string feature;
    std::string physical_group;
    double requested_step;
    double used_step;
};
struct StackAttempt {
    std::int64_t attempt_index = 0;
    double scale = 1.0;
    std::vector<VertexRecord> vertices;
    std::vector<FaceRecord> faces;
    std::vector<LineageRecord> lineage;
    std::vector<double> aspects;
    double minimum_area = std::numeric_limits<double>::infinity();
    double minimum_step = std::numeric_limits<double>::infinity();
    double maximum_skewness = 0.0;
    double maximum_non_orthogonality = 0.0;
    double maximum_metric_aspect_ratio = 0.0;
    double maximum_metric_distortion = 0.0;
    double metric_aspect_p99 = 0.0;
};

py::dict refusal(const std::string& reason, std::int64_t requested) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "refused_rollback";
    result["reason"] = reason;
    result["requested_layers"] = requested;
    result["actual_layers"] = 0;
    result["generated_vertices"] = py::list();
    result["generated_faces"] = py::list();
    result["provenance"] = py::list();
    return result;
}

double p99(std::vector<double> values) {
    if (values.empty()) return 0.0;
    std::ranges::sort(values);
    const size_t index = std::min(values.size() - 1U, static_cast<size_t>(std::ceil(0.99 * static_cast<double>(values.size()))) - 1U);
    return values[index];
}

bool better_attempt(const StackAttempt& candidate, const StackAttempt& current) noexcept {
    if (candidate.maximum_metric_aspect_ratio != current.maximum_metric_aspect_ratio) return candidate.maximum_metric_aspect_ratio < current.maximum_metric_aspect_ratio;
    if (candidate.metric_aspect_p99 != current.metric_aspect_p99) return candidate.metric_aspect_p99 < current.metric_aspect_p99;
    if (candidate.minimum_area != current.minimum_area) return candidate.minimum_area > current.minimum_area;
    if (candidate.scale != current.scale) return candidate.scale > current.scale;
    return candidate.attempt_index < current.attempt_index;
}

py::dict plan_shared_front(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edges,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& face_normals,
    const py::list& patch_names, const py::list& feature_names, const py::list& physical_groups,
    std::int64_t requested_layers, double first_height, double growth_ratio,
    const py::object& source_triangles = py::none(), std::int64_t max_step_halvings = 8,
    double min_signed_area = 1.0e-14, double minimum_allowed_step = 1.0e-8,
    double max_metric_aspect_ratio = std::numeric_limits<double>::infinity(), const py::object& directed_loops = py::none(), const py::object& cavity_faces = py::none())
{
    if (points.ndim() != 2 || points.shape(1) != 3 || edges.ndim() != 2 || edges.shape(1) != 4 || face_normals.ndim() != 2 || face_normals.shape(1) != 3) throw std::invalid_argument("points Nx3, edges Ex4, and face_normals Fx3 are required");
    if (requested_layers < 0) return refusal("negative_layer_count", requested_layers);
    if (requested_layers == 0) {
        py::dict result = refusal("disabled_identity", 0);
        result["accepted"] = true;
        result["status"] = "disabled_identity";
        result["reason"] = "disabled_identity";
        return result;
    }
    if (!std::isfinite(first_height) || first_height <= 0.0) return refusal("invalid_first_height", requested_layers);
    if (!std::isfinite(growth_ratio) || growth_ratio < 1.0) return refusal("invalid_growth_ratio", requested_layers);
    if (max_step_halvings < 0 || !std::isfinite(min_signed_area) || min_signed_area <= 0.0 || !std::isfinite(minimum_allowed_step) || minimum_allowed_step <= 0.0 || (!(std::isfinite(max_metric_aspect_ratio)) && !std::isinf(max_metric_aspect_ratio)) || max_metric_aspect_ratio <= 0.0) return refusal("invalid_transaction_options", requested_layers);
    if (edges.shape(0) == 0) return refusal("empty_wall_edge_selection", requested_layers);
    if (patch_names.size() != static_cast<size_t>(face_normals.shape(0)) || feature_names.size() != static_cast<size_t>(face_normals.shape(0)) || physical_groups.size() != static_cast<size_t>(face_normals.shape(0))) throw std::invalid_argument("labels must match face_normals");

    const auto* point_data = points.data();
    const auto* edge_data = edges.data();
    const auto* normal_data = face_normals.data();
    const auto point_at = [&](std::int64_t id) -> Point {
        if (id < 0 || id >= points.shape(0)) throw std::invalid_argument("edge vertex index is out of range");
        const auto offset = static_cast<size_t>(id) * 3U;
        Point point{point_data[offset], point_data[offset + 1U], point_data[offset + 2U]};
        if (!finite_point(point)) throw std::invalid_argument("points must be finite");
        return point;
    };
    std::vector<EdgeSpec> specs;
    specs.reserve(static_cast<size_t>(edges.shape(0)));
    for (py::ssize_t row = 0; row < edges.shape(0); ++row) {
        const auto offset = static_cast<size_t>(row) * 4U;
        specs.push_back({edge_data[offset], edge_data[offset + 1U], edge_data[offset + 2U], edge_data[offset + 3U]});
    }
    std::ranges::sort(specs, {}, [](const EdgeSpec& edge) { return std::tuple{edge.id, edge.face, edge.first, edge.second}; });
    for (size_t i = 1; i < specs.size(); ++i) if (specs[i - 1].id == specs[i].id && specs[i - 1].face == specs[i].face) return refusal("duplicate_source_edge_sector", requested_layers);

    py::array_t<std::int64_t, py::array::c_style | py::array::forcecast> triangles;
    const bool has_triangles = !source_triangles.is_none();
    if (has_triangles) {
        triangles = source_triangles.cast<py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>>();
        if (triangles.ndim() != 2 || triangles.shape(1) != 3) throw std::invalid_argument("source_triangles must be Tx3");
    }
    const auto* triangle_data = has_triangles ? triangles.data() : nullptr;

    const auto triangle_at = [&](py::ssize_t row) { const auto offset = static_cast<size_t>(row) * 3U; return std::array<std::int64_t, 3>{triangle_data[offset], triangle_data[offset + 1U], triangle_data[offset + 2U]}; };
    std::set<std::int64_t> replaceable_cavity;
    if (!cavity_faces.is_none()) {
        if (!py::isinstance<py::list>(cavity_faces)) return refusal("replaceable_cavity_invalid", requested_layers);
        if (!has_triangles) return refusal("replaceable_cavity_requires_source_triangles", requested_layers);
        for (const py::handle& value : cavity_faces.cast<py::list>()) {
            try {
                const auto face = value.cast<std::int64_t>();
                if (face < 0 || face >= triangles.shape(0)) return refusal("replaceable_cavity_face_out_of_range", requested_layers);
                if (!replaceable_cavity.insert(face).second) return refusal("replaceable_cavity_duplicate_face", requested_layers);
            } catch (...) { return refusal("replaceable_cavity_face_invalid", requested_layers); }
        }
        if (replaceable_cavity.empty()) return refusal("replaceable_cavity_empty", requested_layers);
        for (const EdgeSpec& edge : specs) if (!replaceable_cavity.contains(edge.face)) return refusal("replaceable_cavity_wall_face_missing", requested_layers);
    }

    std::map<std::int64_t, Point> base_positions;
    std::map<std::int64_t, Point> direction_sum;
    std::map<std::int64_t, Point> edge_normals;
    std::map<std::int64_t, Point> normal_sum;
    std::set<std::pair<std::int64_t, std::int64_t>> wall_edges;
    std::set<std::pair<std::int64_t, std::int64_t>> directed_edges;
    for (const EdgeSpec& edge : specs) {
        if (edge.face < 0 || edge.face >= face_normals.shape(0)) return refusal("source_face_out_of_range", requested_layers);
        const Point first = point_at(edge.first);
        const Point second = point_at(edge.second);
        const Point tangent = unit(sub(second, first), "edge tangent");
        const auto no = static_cast<size_t>(edge.face) * 3U;
        const Point normal = unit(Point{normal_data[no], normal_data[no + 1U], normal_data[no + 2U]}, "face normal");
        const Point co_normal = unit(cross(normal, tangent), "surface co-normal");
        base_positions.emplace(edge.first, first);
        base_positions.emplace(edge.second, second);
        direction_sum[edge.first] = add(direction_sum[edge.first], co_normal);
        direction_sum[edge.second] = add(direction_sum[edge.second], co_normal);
        edge_normals[edge.id] = normal;
        wall_edges.emplace(edge.first < edge.second ? std::pair{edge.first, edge.second} : std::pair{edge.second, edge.first});
        normal_sum[edge.first] = add(normal_sum[edge.first], normal);
        normal_sum[edge.second] = add(normal_sum[edge.second], normal);
    }
    if (!directed_loops.is_none()) {
        if (!py::isinstance<py::list>(directed_loops)) return refusal("directed_wall_loop_invalid", requested_layers);
        const py::list loops = directed_loops.cast<py::list>();
        if (loops.empty()) return refusal("directed_wall_loop_missing", requested_layers);
        std::map<std::int64_t, Point> loop_sum;
        for (const py::handle& item : loops) {
            if (!py::isinstance<py::list>(item)) return refusal("directed_wall_loop_invalid", requested_layers);
            const py::list loop = item.cast<py::list>();
            if (loop.size() < 3U) return refusal("directed_wall_loop_too_short", requested_layers);
            std::vector<std::int64_t> vertices;
            for (const py::handle& value : loop) {
                try { vertices.push_back(value.cast<std::int64_t>()); } catch (...) { return refusal("directed_wall_loop_vertex_invalid", requested_layers); }
            }
            for (std::size_t index = 0; index < vertices.size(); ++index) {
                const auto vertex = vertices[index];
                const auto previous_vertex = vertices[(index + vertices.size() - 1U) % vertices.size()];
                const auto next_vertex = vertices[(index + 1U) % vertices.size()];
                if (!base_positions.contains(vertex) || !base_positions.contains(previous_vertex) || !base_positions.contains(next_vertex)) return refusal("directed_wall_loop_vertex_unknown", requested_layers);
                const auto wall_edge = vertex < next_vertex ? std::pair{vertex, next_vertex} : std::pair{next_vertex, vertex};
                if (!wall_edges.contains(wall_edge)) return refusal("directed_wall_loop_edge_binding_mismatch", requested_layers);
                if (!directed_edges.emplace(vertex, next_vertex).second) return refusal("directed_wall_loop_duplicate_edge", requested_layers);
                const EdgeSpec* bound = nullptr;
                for (const EdgeSpec& candidate : specs) {
                    const auto candidate_edge = candidate.first < candidate.second ? std::pair{candidate.first, candidate.second} : std::pair{candidate.second, candidate.first};
                    if (candidate_edge == wall_edge) {
                        if (bound != nullptr) return refusal("directed_wall_loop_winding_ambiguous", requested_layers);
                        bound = &candidate;
                    }
                }
                if (bound == nullptr) return refusal("directed_wall_loop_source_binding_missing", requested_layers);
                bool follows_source_winding = false;
                if (has_triangles) {
                    const auto source_face = triangle_at(bound->face);
                    for (std::size_t edge_index = 0; edge_index < 3U; ++edge_index)
                        follows_source_winding = follows_source_winding || (source_face[edge_index] == vertex && source_face[(edge_index + 1U) % 3U] == next_vertex);
                } else {
                    follows_source_winding = bound->first == vertex && bound->second == next_vertex;
                }
                if (!follows_source_winding) return refusal("directed_wall_loop_winding_mismatch", requested_layers);
                const Point tangent = unit(sub(base_positions.at(next_vertex), base_positions.at(previous_vertex)), "directed loop tangent");
                const auto no = static_cast<size_t>(bound->face) * 3U;
                const Point normal = unit(Point{normal_data[no], normal_data[no + 1U], normal_data[no + 2U]}, "directed source-face normal");
                loop_sum[vertex] = add(loop_sum[vertex], unit(cross(normal, tangent), "directed loop co-normal"));
            }
        }
        if (loop_sum.size() != base_positions.size()) return refusal("directed_wall_loop_coverage_incomplete", requested_layers);
        direction_sum = std::move(loop_sum);
    }
    std::map<std::int64_t, Point> directions;
    for (const auto& [vertex, sum] : direction_sum) {
        try { directions.emplace(vertex, unit(sum, "shared vertex co-normal")); } catch (const std::invalid_argument&) { return refusal("shared_vertex_direction_failure", requested_layers); }
    }

    std::vector<StackAttempt> valid_attempts;
    std::string last_failure_reason = "unknown";
    for (std::int64_t attempt_index = 0; attempt_index <= max_step_halvings; ++attempt_index) {
        StackAttempt candidate;
        candidate.attempt_index = attempt_index;
        candidate.scale = std::ldexp(1.0, -static_cast<int>(attempt_index));
        std::map<std::int64_t, Point> previous = base_positions;
        std::int64_t layer_vertex_id = 0;
        bool failed = false;
        for (std::int64_t layer = 1; layer <= requested_layers && !failed; ++layer) {
            const double requested_step = first_height * std::pow(growth_ratio, static_cast<double>(layer - 1));
            const double used_step = requested_step * candidate.scale;
            if (!std::isfinite(used_step) || used_step < minimum_allowed_step) { last_failure_reason = "minimum_step"; failed = true; break; }
            std::map<std::int64_t, Point> next;
            for (const auto& [vertex, previous_point] : previous) next.emplace(vertex, add(previous_point, mul(directions.at(vertex), used_step)));
            bool collision = false;
            double layer_min_area = std::numeric_limits<double>::infinity();
            for (const EdgeSpec& edge : specs) {
                const Point a = base_positions.at(edge.first);
                const Point b = base_positions.at(edge.second);
                const Point na = next.at(edge.first);
                const Point nb = next.at(edge.second);
                const double source_length = norm(sub(b, a));
                const double generated_length = norm(sub(nb, na));
                if (!(source_length > 1.0e-14) || !(generated_length > 1.0e-14) || !std::isfinite(generated_length)) { last_failure_reason = "edge_length"; collision = true; break; }
                const double log_aspect = std::abs(std::log(source_length) - std::log(used_step));
                const double metric_aspect_ratio = log_aspect >= std::log(std::numeric_limits<double>::max()) ? std::numeric_limits<double>::infinity() : std::exp(log_aspect);
                const double skewness = std::abs(generated_length - source_length) / std::max(generated_length, source_length);
                const double cosine = std::clamp(dot(sub(b, a), sub(nb, na)) / (source_length * generated_length), -1.0, 1.0);
                const double non_orthogonality = std::acos(cosine) * 180.0 / std::acos(-1.0);
                const double metric_distortion = std::max(generated_length / source_length, source_length / generated_length);
                candidate.aspects.push_back(metric_aspect_ratio);
                candidate.maximum_skewness = std::max(candidate.maximum_skewness, skewness);
                candidate.maximum_non_orthogonality = std::max(candidate.maximum_non_orthogonality, non_orthogonality);
                candidate.maximum_metric_aspect_ratio = std::max(candidate.maximum_metric_aspect_ratio, metric_aspect_ratio);
                candidate.maximum_metric_distortion = std::max(candidate.maximum_metric_distortion, metric_distortion);
                if (!std::isfinite(metric_aspect_ratio) || skewness > 0.50 || non_orthogonality > 50.0 || metric_aspect_ratio > max_metric_aspect_ratio) { last_failure_reason = "edge_quality"; collision = true; break; }
                Point area_origin = a;
                Point area_edge = sub(b, a);
                Point area_offset = na;
                if (!directed_edges.empty()) {
                    const std::pair<std::int64_t, std::int64_t> forward{edge.first, edge.second};
                    const std::pair<std::int64_t, std::int64_t> reverse{edge.second, edge.first};
                    if (directed_edges.contains(reverse)) { area_origin = b; area_edge = sub(a, b); area_offset = nb; }
                    else if (!directed_edges.contains(forward)) { last_failure_reason = "directed_edge_missing"; collision = true; break; }
                }
                if (has_triangles) {
                    for (py::ssize_t triangle = 0; triangle < triangles.shape(0) && !collision; ++triangle) {
                        const auto ids = triangle_at(triangle);
                        if (replaceable_cavity.contains(static_cast<std::int64_t>(triangle))) continue;
                        if (contains_vertex(ids, edge.first) || contains_vertex(ids, edge.second)) continue;
                        const bool intersects = segment_hits_triangle(previous.at(edge.first), na, point_at(ids[0]), point_at(ids[1]), point_at(ids[2])) || segment_hits_triangle(previous.at(edge.second), nb, point_at(ids[0]), point_at(ids[1]), point_at(ids[2])) || segment_hits_triangle(na, nb, point_at(ids[0]), point_at(ids[1]), point_at(ids[2]));
                        if (intersects) last_failure_reason = "non_cavity_intersection";
                        collision = intersects;
                    }
                }
            }
            if (collision) { failed = true; break; }
            candidate.minimum_area = std::min(candidate.minimum_area, layer_min_area);
            candidate.minimum_step = std::min(candidate.minimum_step, used_step);
            std::map<std::int64_t, std::int64_t> ids;
            for (const auto& [vertex, position] : next) {
                const std::int64_t id = layer_vertex_id++;
                ids[vertex] = id;
                candidate.vertices.push_back({id, vertex, layer, position});
            }
            for (const EdgeSpec& edge : specs) {
                candidate.faces.push_back({edge.id, layer, edge.first, edge.second, ids.at(edge.first), ids.at(edge.second)});
                candidate.lineage.push_back({edge.id, edge.face, layer, ids.at(edge.first), ids.at(edge.second), py::cast<std::string>(patch_names[edge.face]), py::cast<std::string>(feature_names[edge.face]), py::cast<std::string>(physical_groups[edge.face]), requested_step, used_step});
            }
            previous = std::move(next);
        }
        if (!failed && static_cast<std::int64_t>(candidate.lineage.size()) == requested_layers * static_cast<std::int64_t>(specs.size())) {
            candidate.metric_aspect_p99 = p99(candidate.aspects);
            valid_attempts.push_back(std::move(candidate));
        }
    }
    if (valid_attempts.empty()) {
        py::dict result = refusal("collision_or_quality_failure", requested_layers);
        result["last_failure_reason"] = last_failure_reason;
        return result;
    }
    const auto selected = std::ranges::min_element(valid_attempts, [](const StackAttempt& a, const StackAttempt& b) { return better_attempt(a, b); });
    const StackAttempt& best = *selected;

    py::list staged_vertices;
    py::list staged_faces;
    py::list staged_lineage;
    for (const auto& vertex : best.vertices) {
        py::dict item; item["id"] = vertex.id; item["source_vertex"] = vertex.source_vertex; item["layer"] = vertex.layer; item["x"] = vertex.position[0]; item["y"] = vertex.position[1]; item["z"] = vertex.position[2]; staged_vertices.append(item);
    }
    for (const auto& face : best.faces) {
        py::dict item; item["source_edge"] = face.source_edge; item["layer"] = face.layer; item["source_a"] = face.source_a; item["source_b"] = face.source_b; item["generated_a"] = face.generated_a; item["generated_b"] = face.generated_b; staged_faces.append(item);
    }
    for (const auto& item : best.lineage) {
        py::dict lineage; lineage["source_wall_edge"] = item.source_wall_edge; lineage["source_face"] = item.source_face; lineage["layer"] = item.layer; lineage["generated_vertices"] = py::make_tuple(item.generated_a, item.generated_b); lineage["patch"] = item.patch; lineage["feature"] = item.feature; lineage["physical_group"] = item.physical_group; lineage["sector"] = "smooth"; lineage["requested_step"] = item.requested_step; lineage["used_step"] = item.used_step; staged_lineage.append(lineage);
    }
    py::dict quality;
    quality["min_signed_area"] = best.minimum_area;
    quality["min_step"] = best.minimum_step;
    quality["shared_vertex_count"] = static_cast<std::int64_t>(base_positions.size());
    quality["layer_count"] = requested_layers;
    quality["max_skewness"] = best.maximum_skewness;
    quality["max_non_orthogonality"] = best.maximum_non_orthogonality;
    quality["metric_aspect_ratio"] = best.maximum_metric_aspect_ratio;
    quality["metric_aspect_p99"] = best.metric_aspect_p99;
    quality["metric_distortion"] = best.maximum_metric_distortion;
    quality["selected_scale"] = best.scale;
    quality["valid_candidate_count"] = static_cast<std::int64_t>(valid_attempts.size());
    quality["direction_mode"] = directed_loops.is_none() ? "averaged_co_normal_legacy" : "directed_loop_tangent_frame";
    quality["directed_wall_loop_count"] = directed_loops.is_none() ? 0 : directed_loops.cast<py::list>().size();
    quality["cavity_mode"] = replaceable_cavity.empty() ? "none" : "replaceable_source_faces";
    quality["cavity_source_face_count"] = static_cast<std::int64_t>(replaceable_cavity.size());
    py::dict result;
    result["accepted"] = true; result["status"] = "candidate_plan_ready"; result["reason"] = "shared_vertex_quality_first_plan";
    result["requested_layers"] = requested_layers; result["actual_layers"] = requested_layers; result["generated_vertices"] = staged_vertices; result["generated_faces"] = staged_faces; result["provenance"] = staged_lineage; result["quality"] = quality; result["source_immutable"] = true; result["count_is_report_only"] = true; result["lineage_is_shared"] = true; result["runtime_route"] = "default_off";
    result["replaceable_cavity_verified"] = !replaceable_cavity.empty();
    return result;
}

}  // namespace

PYBIND11_MODULE(native_surface_bl_front_shared, module)
{
    module.doc() = "Default-off C++23 shared-vertex surface wall-edge BL candidate planner";
    module.def("plan_shared_surface_wall_edge_front", &plan_shared_front,
        py::arg("points"), py::arg("edges"), py::arg("face_normals"), py::arg("patch_names"),
        py::arg("feature_names"), py::arg("physical_groups"), py::arg("requested_layers"),
        py::arg("first_height"), py::arg("growth_ratio"), py::arg("source_triangles") = py::none(),
        py::arg("max_step_halvings") = 8, py::arg("min_signed_area") = 1.0e-14,
        py::arg("minimum_allowed_step") = 1.0e-8, py::arg("max_metric_aspect_ratio") = std::numeric_limits<double>::infinity(), py::arg("directed_loops") = py::none(), py::arg("cavity_faces") = py::none());
}
