// Default-off C++23 candidate planner for surface wall-edge BL fronts.
// It never mutates a source mesh or performs runtime routing.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;

namespace {

[[nodiscard]] Point sub(const Point& a, const Point& b) noexcept
{
    return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}

[[nodiscard]] Point add(const Point& a, const Point& b) noexcept
{
    return {a[0] + b[0], a[1] + b[1], a[2] + b[2]};
}

[[nodiscard]] Point mul(const Point& a, const double s) noexcept
{
    return {a[0] * s, a[1] * s, a[2] * s};
}

[[nodiscard]] Point cross(const Point& a, const Point& b) noexcept
{
    return {
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    };
}

[[nodiscard]] double dot(const Point& a, const Point& b) noexcept
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

[[nodiscard]] double norm(const Point& a) noexcept
{
    return std::sqrt(dot(a, a));
}

[[nodiscard]] Point unit(const Point& value, const char* name)
{
    const double length = norm(value);
    if (!(length > 1.0e-14) || !std::isfinite(length)) {
        throw std::invalid_argument(std::string(name) + " must be nonzero and finite");
    }
    return mul(value, 1.0 / length);
}

[[nodiscard]] bool finite_point(const Point& point) noexcept
{
    return std::all_of(point.begin(), point.end(), [](const double value) {
        return std::isfinite(value);
    });
}

[[nodiscard]] bool contains_edge(
    const std::array<std::int64_t, 3>& triangle,
    const std::int64_t first,
    const std::int64_t second) noexcept
{
    bool has_first = false;
    bool has_second = false;
    for (const auto vertex : triangle) {
        has_first = has_first || vertex == first;
        has_second = has_second || vertex == second;
    }
    return has_first && has_second;
}

[[nodiscard]] bool segment_hits_triangle(
    const Point& origin,
    const Point& endpoint,
    const Point& a,
    const Point& b,
    const Point& c) noexcept
{
    constexpr double epsilon = 1.0e-12;
    const Point direction = sub(endpoint, origin);
    const Point edge1 = sub(b, a);
    const Point edge2 = sub(c, a);
    const Point pvec = cross(direction, edge2);
    const double determinant = dot(edge1, pvec);
    if (std::abs(determinant) <= epsilon) {
        return false;
    }
    const double inverse = 1.0 / determinant;
    const Point tvec = sub(origin, a);
    const double u = dot(tvec, pvec) * inverse;
    if (u < -epsilon || u > 1.0 + epsilon) {
        return false;
    }
    const Point qvec = cross(tvec, edge1);
    const double v = dot(direction, qvec) * inverse;
    if (v < -epsilon || u + v > 1.0 + epsilon) {
        return false;
    }
    const double distance = dot(edge2, qvec) * inverse;
    return distance >= -epsilon && distance <= 1.0 + epsilon;
}

struct EdgeSpec {
    std::int64_t edge_id;
    std::int64_t first;
    std::int64_t second;
    std::int64_t face_id;
};

[[nodiscard]] py::dict refusal(
    const std::string& reason,
    const std::int64_t requested_layers,
    const std::int64_t actual_layers = 0)
{
    py::dict result;
    result["accepted"] = false;
    result["status"] = "refused_rollback";
    result["reason"] = reason;
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = actual_layers;
    result["generated_vertices"] = py::list();
    result["generated_faces"] = py::list();
    result["provenance"] = py::list();
    return result;
}

[[nodiscard]] py::dict plan_surface_wall_edge_front(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edges,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& face_normals,
    const py::list& patch_names,
    const py::list& feature_names,
    const py::list& physical_groups,
    const std::int64_t requested_layers,
    const double first_height,
    const double growth_ratio,
    const py::object& source_triangles = py::none(),
    const std::int64_t max_step_halvings = 8)
{
    if (points.ndim() != 2 || points.shape(1) != 3
        || edges.ndim() != 2 || edges.shape(1) != 4
        || face_normals.ndim() != 2 || face_normals.shape(1) != 3) {
        throw std::invalid_argument("points Nx3, edges Ex4, and face_normals Fx3 are required");
    }
    if (requested_layers < 0) {
        return refusal("negative_layer_count", requested_layers);
    }
    if (requested_layers == 0) {
        py::dict result = refusal("disabled_identity", 0, 0);
        result["accepted"] = true;
        result["status"] = "disabled_identity";
        result["reason"] = "disabled_identity";
        return result;
    }
    if (!std::isfinite(first_height) || first_height <= 0.0) {
        return refusal("invalid_first_height", requested_layers);
    }
    if (!std::isfinite(growth_ratio) || growth_ratio < 1.0) {
        return refusal("invalid_growth_ratio", requested_layers);
    }
    if (edges.shape(0) == 0) {
        return refusal("empty_wall_edge_selection", requested_layers);
    }
    if (patch_names.size() != static_cast<size_t>(face_normals.shape(0))
        || feature_names.size() != static_cast<size_t>(face_normals.shape(0))
        || physical_groups.size() != static_cast<size_t>(face_normals.shape(0))) {
        throw std::invalid_argument("patch, feature, and physical-group names must match face_normals");
    }

    const auto* point_data = points.data();
    const auto* edge_data = edges.data();
    const auto* normal_data = face_normals.data();
    const auto point_at = [&](const std::int64_t id) -> Point {
        if (id < 0 || id >= points.shape(0)) {
            throw std::invalid_argument("edge vertex index is out of range");
        }
        const auto offset = static_cast<size_t>(id) * 3U;
        const Point point{point_data[offset], point_data[offset + 1U], point_data[offset + 2U]};
        if (!finite_point(point)) {
            throw std::invalid_argument("points must be finite");
        }
        return point;
    };

    std::vector<EdgeSpec> specs;
    specs.reserve(static_cast<size_t>(edges.shape(0)));
    for (py::ssize_t row = 0; row < edges.shape(0); ++row) {
        const auto offset = static_cast<size_t>(row) * 4U;
        specs.push_back({edge_data[offset], edge_data[offset + 1U], edge_data[offset + 2U], edge_data[offset + 3U]});
    }
    std::ranges::sort(specs, {}, [](const EdgeSpec& edge) {
        return std::tuple{edge.edge_id, edge.face_id, edge.first, edge.second};
    });
    for (size_t index = 1U; index < specs.size(); ++index) {
        if (specs[index - 1U].edge_id == specs[index].edge_id
            && specs[index - 1U].face_id == specs[index].face_id) {
            return refusal("duplicate_source_edge_sector", requested_layers);
        }
    }

    py::array_t<std::int64_t, py::array::c_style | py::array::forcecast> triangles;
    const bool has_triangles = !source_triangles.is_none();
    if (has_triangles) {
        triangles = source_triangles.cast<py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>>();
        if (triangles.ndim() != 2 || triangles.shape(1) != 3) {
            throw std::invalid_argument("source_triangles must have shape Tx3");
        }
    }
    const auto* triangle_data = has_triangles ? triangles.data() : nullptr;
    const auto triangle_at = [&](const py::ssize_t row) {
        const auto offset = static_cast<size_t>(row) * 3U;
        return std::array<std::int64_t, 3>{triangle_data[offset], triangle_data[offset + 1U], triangle_data[offset + 2U]};
    };

    py::list generated_vertices;
    py::list generated_faces;
    py::list provenance;
    std::int64_t generated_id = 0;
    for (const EdgeSpec& edge : specs) {
        if (edge.face_id < 0 || edge.face_id >= face_normals.shape(0)) {
            return refusal("source_face_out_of_range", requested_layers);
        }
        const Point first = point_at(edge.first);
        const Point second = point_at(edge.second);
        const Point tangent = unit(sub(second, first), "edge tangent");
        const auto normal_offset = static_cast<size_t>(edge.face_id) * 3U;
        const Point normal = unit(
            Point{normal_data[normal_offset], normal_data[normal_offset + 1U], normal_data[normal_offset + 2U]},
            "face normal");
        const Point co_normal = unit(cross(normal, tangent), "surface co-normal");
        const double edge_length = norm(sub(second, first));
        const std::string patch = py::cast<std::string>(patch_names[edge.face_id]);
        const std::string feature = py::cast<std::string>(feature_names[edge.face_id]);
        const std::string physical_group = py::cast<std::string>(physical_groups[edge.face_id]);

        for (std::int64_t layer = 1; layer <= requested_layers; ++layer) {
            const double requested_step = first_height * std::pow(growth_ratio, static_cast<double>(layer - 1));
            bool accepted = false;
            Point offset_first{};
            Point offset_second{};
            double used_step = requested_step;
            for (std::int64_t attempt = 0; attempt <= max_step_halvings; ++attempt) {
                offset_first = add(first, mul(co_normal, used_step));
                offset_second = add(second, mul(co_normal, used_step));
                const Point area0 = cross(sub(second, first), sub(offset_second, first));
                const Point area1 = cross(sub(offset_second, first), sub(offset_first, first));
                if (dot(area0, normal) <= 1.0e-14 || dot(area1, normal) <= 1.0e-14) {
                    used_step *= 0.5;
                    continue;
                }
                bool collision = false;
                if (has_triangles) {
                    for (py::ssize_t triangle = 0; triangle < triangles.shape(0) && !collision; ++triangle) {
                        const auto ids = triangle_at(triangle);
                        if (contains_edge(ids, edge.first, edge.second)) {
                            continue;
                        }
                        const Point ta = point_at(ids[0]);
                        const Point tb = point_at(ids[1]);
                        const Point tc = point_at(ids[2]);
                        collision = segment_hits_triangle(first, offset_first, ta, tb, tc)
                            || segment_hits_triangle(second, offset_second, ta, tb, tc)
                            || segment_hits_triangle(offset_first, offset_second, ta, tb, tc);
                    }
                }
                if (!collision) {
                    accepted = true;
                    break;
                }
                used_step *= 0.5;
            }
            if (!accepted) {
                return refusal("collision_or_visibility_failure", requested_layers);
            }

            const std::int64_t first_generated = generated_id++;
            const std::int64_t second_generated = generated_id++;
            py::dict vertex_a;
            vertex_a["id"] = first_generated;
            vertex_a["x"] = offset_first[0];
            vertex_a["y"] = offset_first[1];
            vertex_a["z"] = offset_first[2];
            py::dict vertex_b = vertex_a;
            vertex_b["id"] = second_generated;
            vertex_b["x"] = offset_second[0];
            vertex_b["y"] = offset_second[1];
            vertex_b["z"] = offset_second[2];
            generated_vertices.append(vertex_a);
            generated_vertices.append(vertex_b);

            py::dict face_a;
            face_a["source_a"] = edge.first;
            face_a["source_b"] = edge.second;
            face_a["generated_b"] = second_generated;
            face_a["generated_a"] = first_generated;
            face_a["layer"] = layer;
            py::dict face_b = face_a;
            face_b["source_a"] = edge.first;
            face_b["source_b"] = second_generated;
            face_b["generated_b"] = first_generated;
            generated_faces.append(face_a);
            generated_faces.append(face_b);

            py::dict lineage;
            lineage["source_wall_edge"] = edge.edge_id;
            lineage["source_face"] = edge.face_id;
            lineage["patch"] = patch;
            lineage["feature"] = feature;
            lineage["physical_group"] = physical_group;
            lineage["sector"] = "smooth";
            lineage["layer"] = layer;
            lineage["requested_step"] = requested_step;
            lineage["used_step"] = used_step;
            lineage["metric_tangential_length"] = edge_length;
            lineage["metric_normal_length"] = used_step;
            lineage["candidate_ordinal"] = static_cast<std::int64_t>(provenance.size());
            provenance.append(lineage);
        }
    }

    py::dict result;
    result["accepted"] = true;
    result["status"] = "candidate_plan_ready";
    result["reason"] = "accepted_quality_first_plan";
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = requested_layers;
    result["generated_vertices"] = generated_vertices;
    result["generated_faces"] = generated_faces;
    result["provenance"] = provenance;
    result["source_immutable"] = true;
    result["count_is_report_only"] = true;
    return result;
}

}  // namespace

PYBIND11_MODULE(native_surface_bl_front, module)
{
    module.doc() = "Default-off C++23 surface wall-edge BL candidate planner";
    module.def(
        "plan_surface_wall_edge_front",
        &plan_surface_wall_edge_front,
        py::arg("points"),
        py::arg("edges"),
        py::arg("face_normals"),
        py::arg("patch_names"),
        py::arg("feature_names"),
        py::arg("physical_groups"),
        py::arg("requested_layers"),
        py::arg("first_height"),
        py::arg("growth_ratio"),
        py::arg("source_triangles") = py::none(),
        py::arg("max_step_halvings") = 8);
}
