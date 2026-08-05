// Native boundary-layer search kernels.
//
// The uniform-grid hash keeps collision candidates local without allocating
// the dense N x N dot-product and distance matrices used by the NumPy oracle.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <numeric>
#include <ranges>
#include <span>
#include <stdexcept>
#include <tuple>
#include <unordered_map>
#include <vector>

namespace py = pybind11;

namespace {

struct GridKey {
    std::int64_t x;
    std::int64_t y;
    std::int64_t z;

    friend bool operator==(const GridKey&, const GridKey&) = default;
};

struct GridKeyHash {
    [[nodiscard]] size_t operator()(const GridKey& key) const noexcept
    {
        size_t seed = std::hash<std::int64_t>{}(key.x);
        const auto combine = [&seed](std::int64_t value) {
            const size_t hashed = std::hash<std::int64_t>{}(value);
            seed ^= hashed + 0x9e3779b97f4a7c15ULL + (seed << 6U) + (seed >> 2U);
        };
        combine(key.y);
        combine(key.z);
        return seed;
    }
};

using Point3 = std::array<double, 3>;

struct RayTriangle {
    Point3 vertex0;
    Point3 edge1;
    Point3 edge2;
};

struct IndexedRayTriangle {
    RayTriangle geometry;
    Point3 centroid;
    std::array<std::int64_t, 3> vertex_ids;
};

struct LayerFrontEdgeRef {
    std::int64_t low;
    std::int64_t high;
    std::int64_t face_id;
    size_t face_order;
    size_t local_edge;
};

struct LayerFrontVertexFaceRef {
    std::int64_t vertex;
    std::int64_t face_id;
    size_t face_order;
};

struct LayerFrontCompactSummary {
    size_t face_count{};
    size_t vertex_count{};
    size_t edge_count{};
    size_t boundary_edge_count{};
    size_t nonmanifold_edge_count{};
    size_t feature_vertex_count{};
    size_t blocked_vertex_count{};
    std::array<std::int64_t, 2> first_nonmanifold_edge{-1, -1};
    std::vector<std::int64_t> first_nonmanifold_faces;
    std::vector<std::int64_t> adjacent_face_ids;
};

[[nodiscard]] constexpr Point3 subtract(
    const Point3& left, const Point3& right) noexcept
{
    return {
        left[0] - right[0],
        left[1] - right[1],
        left[2] - right[2],
    };
}

[[nodiscard]] constexpr Point3 cross(
    const Point3& left, const Point3& right) noexcept
{
    return {
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    };
}

[[nodiscard]] constexpr double dot(
    const Point3& left, const Point3& right) noexcept
{
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

[[nodiscard]] LayerFrontCompactSummary compute_layer_front_summary(
    const std::span<const std::int64_t> face_ids,
    const std::span<const std::int64_t> triangles,
    const std::span<const double> points,
    const double feature_cos_threshold)
{
    const size_t face_count = face_ids.size();
    std::vector<LayerFrontEdgeRef> edges;
    std::vector<LayerFrontVertexFaceRef> vertex_faces;
    std::vector<Point3> face_normals(face_count);
    std::vector<std::uint8_t> face_has_normal(face_count, 0U);
    edges.reserve(face_count * 3U);
    vertex_faces.reserve(face_count * 3U);

    for (size_t face = 0U; face < face_count; ++face) {
        const std::int64_t face_id = face_ids[face];
        const std::array<std::int64_t, 3> vertices{
            triangles[face * 3U],
            triangles[face * 3U + 1U],
            triangles[face * 3U + 2U],
        };
        for (size_t local = 0U; local < 3U; ++local) {
            const std::int64_t first = vertices[local];
            const std::int64_t second = vertices[(local + 1U) % 3U];
            edges.push_back({
                std::min(first, second),
                std::max(first, second),
                face_id,
                face,
                local,
            });
            vertex_faces.push_back({first, face_id, face});
        }

        const auto point_at = [&](const std::int64_t vertex) noexcept {
            const size_t offset = static_cast<size_t>(vertex) * 3U;
            return Point3{points[offset], points[offset + 1U], points[offset + 2U]};
        };
        const Point3 p0 = point_at(vertices[0]);
        const Point3 p1 = point_at(vertices[1]);
        const Point3 p2 = point_at(vertices[2]);
        Point3 normal = cross(subtract(p1, p0), subtract(p2, p0));
        const double magnitude = std::sqrt(dot(normal, normal));
        if (magnitude >= 1.0e-30) {
            for (double& value : normal) {
                value /= magnitude;
            }
            face_normals[face] = normal;
            face_has_normal[face] = 1U;
        }
    }

    std::ranges::sort(edges, {}, [](const LayerFrontEdgeRef& edge) {
        return std::tuple{edge.low, edge.high, edge.face_order};
    });
    std::ranges::sort(vertex_faces, {}, [](const LayerFrontVertexFaceRef& ref) {
        return std::tuple{ref.vertex, ref.face_id, ref.face_order};
    });

    LayerFrontCompactSummary summary;
    summary.face_count = face_count;
    summary.adjacent_face_ids.assign(face_count * 3U, -1);
    std::vector<std::int64_t> vertices;
    vertices.reserve(vertex_faces.size());
    for (const auto& ref : vertex_faces) {
        if (vertices.empty() || vertices.back() != ref.vertex) {
            vertices.push_back(ref.vertex);
        }
    }
    summary.vertex_count = vertices.size();
    std::unordered_map<std::int64_t, size_t> vertex_index;
    vertex_index.max_load_factor(0.7F);
    vertex_index.reserve(vertices.size());
    for (size_t index = 0U; index < vertices.size(); ++index) {
        vertex_index.emplace(vertices[index], index);
    }
    std::vector<std::uint8_t> boundary_vertex(vertices.size(), 0U);
    std::vector<std::uint8_t> nonmanifold_vertex(vertices.size(), 0U);
    std::vector<std::uint8_t> feature_vertex(vertices.size(), 0U);

    for (size_t begin = 0U; begin < edges.size();) {
        size_t end = begin + 1U;
        while (end < edges.size()
               && edges[end].low == edges[begin].low
               && edges[end].high == edges[begin].high) {
            ++end;
        }
        const size_t owners = end - begin;
        ++summary.edge_count;
        const bool is_boundary = owners == 1U;
        const bool is_nonmanifold = owners > 2U;
        summary.boundary_edge_count += static_cast<size_t>(is_boundary);
        summary.nonmanifold_edge_count += static_cast<size_t>(is_nonmanifold);
        if (is_boundary || is_nonmanifold) {
            const size_t first_vertex = vertex_index.at(edges[begin].low);
            const size_t second_vertex = vertex_index.at(edges[begin].high);
            if (is_boundary) {
                boundary_vertex[first_vertex] = 1U;
                boundary_vertex[second_vertex] = 1U;
            }
            if (is_nonmanifold) {
                nonmanifold_vertex[first_vertex] = 1U;
                nonmanifold_vertex[second_vertex] = 1U;
            }
        }
        if (is_nonmanifold && summary.first_nonmanifold_faces.empty()) {
            summary.first_nonmanifold_edge = {edges[begin].low, edges[begin].high};
            summary.first_nonmanifold_faces.reserve(owners);
            for (size_t index = begin; index < end; ++index) {
                summary.first_nonmanifold_faces.push_back(edges[index].face_id);
            }
        }
        size_t first_different = end;
        for (size_t index = begin + 1U; index < end; ++index) {
            if (edges[index].face_id != edges[begin].face_id) {
                first_different = index;
                break;
            }
        }
        for (size_t index = begin; index < end; ++index) {
            const auto& reference = edges[index];
            const size_t other = (
                reference.face_id == edges[begin].face_id
                ? first_different
                : begin
            );
            if (other != end) {
                summary.adjacent_face_ids[
                    reference.face_order * 3U + reference.local_edge
                ] = edges[other].face_id;
            }
        }
        begin = end;
    }

    for (size_t begin = 0U; begin < vertex_faces.size();) {
        size_t end = begin + 1U;
        while (end < vertex_faces.size()
               && vertex_faces[end].vertex == vertex_faces[begin].vertex) {
            ++end;
        }
        std::vector<size_t> normal_faces;
        normal_faces.reserve(end - begin);
        std::int64_t previous_face_id = std::numeric_limits<std::int64_t>::min();
        for (size_t index = begin; index < end; ++index) {
            const auto& ref = vertex_faces[index];
            if (ref.face_id == previous_face_id) {
                continue;
            }
            previous_face_id = ref.face_id;
            if (face_has_normal[ref.face_order] != 0U) {
                normal_faces.push_back(ref.face_order);
            }
        }
        for (size_t first = 0U;
             first < normal_faces.size() && feature_vertex[vertex_index.at(
                 vertex_faces[begin].vertex)] == 0U;
             ++first) {
            for (size_t second = first + 1U; second < normal_faces.size(); ++second) {
                if (dot(face_normals[normal_faces[first]], face_normals[normal_faces[second]])
                    < feature_cos_threshold) {
                    feature_vertex[vertex_index.at(vertex_faces[begin].vertex)] = 1U;
                    break;
                }
            }
        }
        begin = end;
    }

    for (size_t vertex = 0U; vertex < vertices.size(); ++vertex) {
        const bool feature = feature_vertex[vertex] != 0U;
        const bool blocked = feature
            || boundary_vertex[vertex] != 0U
            || nonmanifold_vertex[vertex] != 0U;
        summary.feature_vertex_count += static_cast<size_t>(feature);
        summary.blocked_vertex_count += static_cast<size_t>(blocked);
    }
    return summary;
}

py::dict layer_front_summary(
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& face_ids,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& triangles,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const double feature_cos_threshold)
{
    if (face_ids.ndim() != 1 || triangles.ndim() != 2 || triangles.shape(1) != 3
        || triangles.shape(0) != face_ids.shape(0)) {
        throw std::invalid_argument(
            "face_ids must have shape (F,) and triangles shape (F, 3)");
    }
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (!std::isfinite(feature_cos_threshold)) {
        throw std::invalid_argument("feature_cos_threshold must be finite");
    }
    for (py::ssize_t index = 0; index < points.size(); ++index) {
        if (!std::isfinite(points.data()[index])) {
            throw std::invalid_argument("points must be finite");
        }
    }
    const size_t point_count = static_cast<size_t>(points.shape(0));
    for (py::ssize_t index = 0; index < triangles.size(); ++index) {
        const std::int64_t vertex = triangles.data()[index];
        if (vertex < 0 || static_cast<size_t>(vertex) >= point_count) {
            throw std::invalid_argument("triangle vertex index is out of range");
        }
    }
    for (py::ssize_t index = 0; index < face_ids.size(); ++index) {
        if (face_ids.data()[index] < 0) {
            throw std::invalid_argument("face ids must be non-negative");
        }
    }

    LayerFrontCompactSummary summary;
    {
        py::gil_scoped_release release;
        summary = compute_layer_front_summary(
            {face_ids.data(), static_cast<size_t>(face_ids.size())},
            {triangles.data(), static_cast<size_t>(triangles.size())},
            {points.data(), static_cast<size_t>(points.size())},
            feature_cos_threshold);
    }

    py::dict result;
    result["n_faces"] = py::int_(summary.face_count);
    result["n_ignored"] = py::int_(0);
    result["n_vertices"] = py::int_(summary.vertex_count);
    result["n_edges"] = py::int_(summary.edge_count);
    result["n_boundary_edges"] = py::int_(summary.boundary_edge_count);
    result["n_nonmanifold_edges"] = py::int_(summary.nonmanifold_edge_count);
    result["n_feature_vertices"] = py::int_(summary.feature_vertex_count);
    result["n_blocked_vertices"] = py::int_(summary.blocked_vertex_count);
    py::array_t<std::int64_t> adjacency({
        static_cast<py::ssize_t>(summary.face_count),
        static_cast<py::ssize_t>(3),
    });
    std::copy(
        summary.adjacent_face_ids.begin(),
        summary.adjacent_face_ids.end(),
        adjacency.mutable_data());
    result["adjacent_face_ids"] = std::move(adjacency);
    if (summary.first_nonmanifold_faces.empty()) {
        result["first_nonmanifold_edge"] = py::none();
        result["first_nonmanifold_faces"] = py::tuple();
    } else {
        result["first_nonmanifold_edge"] = py::make_tuple(
            summary.first_nonmanifold_edge[0], summary.first_nonmanifold_edge[1]);
        result["first_nonmanifold_faces"] = py::cast(summary.first_nonmanifold_faces);
    }
    return result;
}

[[nodiscard]] double ray_triangle_distance(
    const Point3& origin,
    const Point3& direction,
    const RayTriangle& triangle,
    const double epsilon) noexcept
{
    const Point3 pvec = cross(direction, triangle.edge2);
    const double determinant = dot(triangle.edge1, pvec);
    if (!(std::abs(determinant) > epsilon)) {
        return std::numeric_limits<double>::infinity();
    }
    const double inverse_determinant = 1.0 / determinant;
    const Point3 tvec = subtract(origin, triangle.vertex0);
    const double u = dot(tvec, pvec) * inverse_determinant;
    // Match the long-standing Python oracle exactly.  The u + v test below
    // supplies the upper barycentric bound.
    if (u < -epsilon) {
        return std::numeric_limits<double>::infinity();
    }
    const Point3 qvec = cross(tvec, triangle.edge1);
    const double v = dot(direction, qvec) * inverse_determinant;
    if (v < -epsilon || u + v > 1.0 + epsilon) {
        return std::numeric_limits<double>::infinity();
    }
    const double distance = dot(triangle.edge2, qvec) * inverse_determinant;
    if (distance > epsilon) {
        return distance;
    }
    return std::numeric_limits<double>::infinity();
}

std::int64_t grid_coordinate(double value, double inverse_cell_size)
{
    if (!std::isfinite(value)) {
        throw std::invalid_argument("front points must be finite");
    }
    const double coordinate = std::floor(value * inverse_cell_size);
    constexpr double lower = static_cast<double>(
        std::numeric_limits<std::int64_t>::min() + 1);
    constexpr double upper = static_cast<double>(
        std::numeric_limits<std::int64_t>::max() - 1);
    if (!std::isfinite(coordinate) || coordinate < lower || coordinate > upper) {
        throw std::overflow_error("front point exceeds spatial-hash coordinate range");
    }
    return static_cast<std::int64_t>(coordinate);
}

py::array_t<bool> nearby_opposite_front_mask(
    py::array_t<double, py::array::c_style | py::array::forcecast> front_normals,
    py::array_t<double, py::array::c_style | py::array::forcecast> front_points,
    double search_radius,
    double normal_dot_threshold)
{
    if (front_normals.ndim() != 2 || front_normals.shape(1) != 3
        || front_points.ndim() != 2 || front_points.shape(1) != 3
        || front_normals.shape(0) != front_points.shape(0)) {
        throw std::invalid_argument("front normals and points must have shape (N, 3)");
    }
    if (!std::isfinite(search_radius) || search_radius <= 0.0) {
        throw std::invalid_argument("search_radius must be finite and positive");
    }
    if (!std::isfinite(normal_dot_threshold)) {
        throw std::invalid_argument("normal_dot_threshold must be finite");
    }

    const auto normals = front_normals.unchecked<2>();
    const auto points = front_points.unchecked<2>();
    const auto count = points.shape(0);
    std::vector<GridKey> point_keys(static_cast<size_t>(count));
    std::vector<size_t> next(
        static_cast<size_t>(count), std::numeric_limits<size_t>::max());
    std::vector<std::uint8_t> collisions(static_cast<size_t>(count), 0);
    std::unordered_map<GridKey, size_t, GridKeyHash> cell_heads;

    {
        py::gil_scoped_release release;
        cell_heads.max_load_factor(0.7F);
        cell_heads.reserve(static_cast<size_t>(count));
        const double inverse_cell_size = 1.0 / search_radius;
        for (py::ssize_t point_i = 0; point_i < count; ++point_i) {
            const GridKey key{
                grid_coordinate(points(point_i, 0), inverse_cell_size),
                grid_coordinate(points(point_i, 1), inverse_cell_size),
                grid_coordinate(points(point_i, 2), inverse_cell_size)};
            point_keys[static_cast<size_t>(point_i)] = key;
            auto [cell, inserted] = cell_heads.try_emplace(
                key, std::numeric_limits<size_t>::max());
            (void)inserted;
            next[static_cast<size_t>(point_i)] = cell->second;
            cell->second = static_cast<size_t>(point_i);
        }

        const double radius_squared = search_radius * search_radius;
        for (py::ssize_t point_i = 0; point_i < count; ++point_i) {
            const auto& key = point_keys[static_cast<size_t>(point_i)];
            for (std::int64_t dx = -1; dx <= 1; ++dx) {
                for (std::int64_t dy = -1; dy <= 1; ++dy) {
                    for (std::int64_t dz = -1; dz <= 1; ++dz) {
                        const auto cell = cell_heads.find(
                            GridKey{key.x + dx, key.y + dy, key.z + dz});
                        if (cell == cell_heads.end()) {
                            continue;
                        }
                        for (size_t point_j = cell->second;
                             point_j != std::numeric_limits<size_t>::max();
                             point_j = next[point_j]) {
                            if (point_j <= static_cast<size_t>(point_i)) {
                                continue;
                            }
                            const double dot =
                                normals(point_i, 0) * normals(point_j, 0)
                                + normals(point_i, 1) * normals(point_j, 1)
                                + normals(point_i, 2) * normals(point_j, 2);
                            if (dot >= normal_dot_threshold) {
                                continue;
                            }
                            const double px = points(point_i, 0) - points(point_j, 0);
                            const double py = points(point_i, 1) - points(point_j, 1);
                            const double pz = points(point_i, 2) - points(point_j, 2);
                            const double distance_squared = px * px + py * py + pz * pz;
                            if (distance_squared <= radius_squared) {
                                collisions[static_cast<size_t>(point_i)] = 1;
                                collisions[point_j] = 1;
                            }
                        }
                    }
                }
            }
        }
    }

    py::array_t<bool> result(count);
    auto result_view = result.mutable_unchecked<1>();
    for (py::ssize_t point_i = 0; point_i < count; ++point_i) {
        result_view(point_i) = collisions[static_cast<size_t>(point_i)] != 0;
    }
    return result;
}

py::array_t<double> ray_triangle_min_distance(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& origins,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& directions,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& triangle_vertices,
    const py::object& exclude_mask,
    const double epsilon)
{
    if (origins.ndim() != 2 || origins.shape(1) != 3
        || directions.ndim() != 2 || directions.shape(1) != 3
        || origins.shape(0) != directions.shape(0)) {
        throw std::invalid_argument(
            "origins and directions must have shape (R, 3)");
    }
    if (triangle_vertices.ndim() != 3
        || triangle_vertices.shape(1) != 3
        || triangle_vertices.shape(2) != 3) {
        throw std::invalid_argument("triangle_vertices must have shape (T, 3, 3)");
    }
    if (!std::isfinite(epsilon) || epsilon < 0.0) {
        throw std::invalid_argument("epsilon must be finite and non-negative");
    }

    const size_t ray_count = static_cast<size_t>(origins.shape(0));
    const size_t triangle_count = static_cast<size_t>(triangle_vertices.shape(0));
    const double* const origin_data = origins.data();
    const double* const direction_data = directions.data();
    const double* const triangle_data = triangle_vertices.data();
    for (py::ssize_t index = 0; index < origins.size(); ++index) {
        if (!std::isfinite(origin_data[index])
            || !std::isfinite(direction_data[index])) {
            throw std::invalid_argument("ray origins and directions must be finite");
        }
    }
    for (py::ssize_t index = 0; index < triangle_vertices.size(); ++index) {
        if (!std::isfinite(triangle_data[index])) {
            throw std::invalid_argument("triangle vertices must be finite");
        }
    }

    py::array exclude_owner;
    const bool* exclude_data = nullptr;
    if (!exclude_mask.is_none()) {
        auto typed_exclude = py::array_t<
            bool, py::array::c_style | py::array::forcecast>::ensure(exclude_mask);
        if (!typed_exclude) {
            throw std::invalid_argument("exclude_mask must be a boolean array");
        }
        if (typed_exclude.ndim() != 2
            || static_cast<size_t>(typed_exclude.shape(0)) != ray_count
            || static_cast<size_t>(typed_exclude.shape(1)) != triangle_count) {
            throw std::invalid_argument("exclude_mask must have shape (R, T)");
        }
        exclude_owner = typed_exclude;
        exclude_data = typed_exclude.data();
    }

    py::array_t<double> result(
        py::array::ShapeContainer{static_cast<py::ssize_t>(ray_count)});
    double* const output = result.mutable_data();
    std::vector<RayTriangle> triangles(triangle_count);
    {
        py::gil_scoped_release release;
        for (size_t triangle = 0U; triangle < triangle_count; ++triangle) {
            const double* const values = triangle_data + triangle * 9U;
            const Point3 vertex0{values[0], values[1], values[2]};
            const Point3 vertex1{values[3], values[4], values[5]};
            const Point3 vertex2{values[6], values[7], values[8]};
            triangles[triangle] = {
                vertex0,
                subtract(vertex1, vertex0),
                subtract(vertex2, vertex0),
            };
        }

        for (size_t ray = 0U; ray < ray_count; ++ray) {
            const double* const origin_values = origin_data + ray * 3U;
            const double* const direction_values = direction_data + ray * 3U;
            const Point3 origin{
                origin_values[0], origin_values[1], origin_values[2]};
            const Point3 direction{
                direction_values[0], direction_values[1], direction_values[2]};
            double best = std::numeric_limits<double>::infinity();
            for (size_t triangle = 0U; triangle < triangle_count; ++triangle) {
                if (exclude_data != nullptr
                    && exclude_data[ray * triangle_count + triangle]) {
                    continue;
                }
                const RayTriangle& candidate = triangles[triangle];
                const double distance = ray_triangle_distance(
                    origin, direction, candidate, epsilon);
                if (distance < best) {
                    best = distance;
                }
            }
            output[ray] = best;
        }
    }
    return result;
}

py::array_t<double> indexed_wall_collision_distances(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>&
        ray_vertex_ids,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& directions,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>&
        triangle_vertex_ids,
    const double max_distance,
    const double epsilon)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (ray_vertex_ids.ndim() != 1
        || directions.ndim() != 2 || directions.shape(1) != 3
        || ray_vertex_ids.shape(0) != directions.shape(0)) {
        throw std::invalid_argument(
            "ray_vertex_ids and directions must have shapes (R,) and (R, 3)");
    }
    if (triangle_vertex_ids.ndim() != 2
        || triangle_vertex_ids.shape(1) != 3) {
        throw std::invalid_argument(
            "triangle_vertex_ids must have shape (T, 3)");
    }
    if (std::isnan(max_distance) || max_distance <= 0.0) {
        throw std::invalid_argument("max_distance must be positive or infinity");
    }
    if (!std::isfinite(epsilon) || epsilon < 0.0) {
        throw std::invalid_argument("epsilon must be finite and non-negative");
    }

    const size_t point_count = static_cast<size_t>(points.shape(0));
    const size_t ray_count = static_cast<size_t>(ray_vertex_ids.shape(0));
    const size_t triangle_count = static_cast<size_t>(triangle_vertex_ids.shape(0));
    const double* const point_data = points.data();
    const double* const direction_data = directions.data();
    const std::int64_t* const ray_id_data = ray_vertex_ids.data();
    const std::int64_t* const triangle_id_data = triangle_vertex_ids.data();

    for (py::ssize_t index = 0; index < points.size(); ++index) {
        if (!std::isfinite(point_data[index])) {
            throw std::invalid_argument("points must be finite");
        }
    }
    for (py::ssize_t index = 0; index < directions.size(); ++index) {
        if (!std::isfinite(direction_data[index])) {
            throw std::invalid_argument("directions must be finite");
        }
    }
    for (size_t ray = 0U; ray < ray_count; ++ray) {
        if (ray_id_data[ray] < 0
            || static_cast<size_t>(ray_id_data[ray]) >= point_count) {
            throw std::invalid_argument("ray vertex index is out of range");
        }
    }
    for (size_t index = 0U; index < triangle_count * 3U; ++index) {
        if (triangle_id_data[index] < 0
            || static_cast<size_t>(triangle_id_data[index]) >= point_count) {
            throw std::invalid_argument("triangle vertex index is out of range");
        }
    }

    py::array_t<double> result(
        py::array::ShapeContainer{static_cast<py::ssize_t>(ray_count)});
    double* const output = result.mutable_data();
    std::vector<IndexedRayTriangle> triangles(triangle_count);
    std::vector<size_t> next;
    std::unordered_map<GridKey, size_t, GridKeyHash> cell_heads;
    std::vector<size_t> candidates;

    {
        py::gil_scoped_release release;
        const auto read_point = [point_data](const std::int64_t point_id) {
            const double* const values = point_data
                + static_cast<size_t>(point_id) * 3U;
            return Point3{values[0], values[1], values[2]};
        };

        double maximum_triangle_radius = 0.0;
        for (size_t triangle = 0U; triangle < triangle_count; ++triangle) {
            const std::int64_t* const ids = triangle_id_data + triangle * 3U;
            const Point3 vertex0 = read_point(ids[0]);
            const Point3 vertex1 = read_point(ids[1]);
            const Point3 vertex2 = read_point(ids[2]);
            Point3 centroid{};
            for (size_t axis = 0U; axis < 3U; ++axis) {
                const double minimum = std::min(
                    vertex0[axis], std::min(vertex1[axis], vertex2[axis]));
                const double maximum = std::max(
                    vertex0[axis], std::max(vertex1[axis], vertex2[axis]));
                centroid[axis] = std::midpoint(minimum, maximum);
            }
            double radius = 0.0;
            const std::array<const Point3*, 3> vertices{
                &vertex0, &vertex1, &vertex2};
            for (const Point3* const vertex : vertices) {
                const Point3 delta = subtract(*vertex, centroid);
                radius = std::max(
                    radius, std::hypot(delta[0], delta[1], delta[2]));
            }
            maximum_triangle_radius = std::max(
                maximum_triangle_radius, radius);
            triangles[triangle] = {
                {vertex0, subtract(vertex1, vertex0), subtract(vertex2, vertex0)},
                centroid,
                {ids[0], ids[1], ids[2]},
            };
        }

        double maximum_direction_norm = 0.0;
        for (size_t ray = 0U; ray < ray_count; ++ray) {
            const double* const values = direction_data + ray * 3U;
            maximum_direction_norm = std::max(
                maximum_direction_norm,
                std::hypot(values[0], values[1], values[2]));
        }

        const bool distance_is_bounded = std::isfinite(max_distance);
        const double radius_inflation = 1.0 + 4.0 * epsilon;
        double cell_size = std::numeric_limits<double>::infinity();
        if (distance_is_bounded) {
            cell_size = max_distance * maximum_direction_norm
                + radius_inflation * maximum_triangle_radius;
            if (std::isfinite(cell_size) && cell_size > 0.0) {
                cell_size = std::nextafter(
                    cell_size, std::numeric_limits<double>::infinity());
            }
        }

        bool use_spatial_hash = distance_is_bounded
            && std::isfinite(cell_size) && cell_size > 0.0
            && ray_count > 0U && triangle_count > 0U;
        Point3 anchor{
            std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::infinity(),
        };
        if (use_spatial_hash) {
            for (const IndexedRayTriangle& triangle : triangles) {
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    anchor[axis] = std::min(anchor[axis], triangle.centroid[axis]);
                }
            }
            for (size_t ray = 0U; ray < ray_count; ++ray) {
                const Point3 origin = read_point(ray_id_data[ray]);
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    anchor[axis] = std::min(anchor[axis], origin[axis]);
                }
            }

            constexpr double maximum_exact_grid_coordinate =
                static_cast<double>(std::uint64_t{1} << 50U);
            const double inverse_cell_size = 1.0 / cell_size;
            const auto coordinate_is_safe = [=](const double value, const double base) {
                const double shifted = value - base;
                const double quotient = shifted * inverse_cell_size;
                return std::isfinite(shifted) && std::isfinite(quotient)
                    && quotient >= 0.0
                    && quotient <= maximum_exact_grid_coordinate;
            };
            for (const IndexedRayTriangle& triangle : triangles) {
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    use_spatial_hash = use_spatial_hash
                        && coordinate_is_safe(triangle.centroid[axis], anchor[axis]);
                }
            }
            for (size_t ray = 0U; ray < ray_count; ++ray) {
                const Point3 origin = read_point(ray_id_data[ray]);
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    use_spatial_hash = use_spatial_hash
                        && coordinate_is_safe(origin[axis], anchor[axis]);
                }
            }
        }

        double inverse_cell_size = 0.0;
        if (use_spatial_hash) {
            inverse_cell_size = 1.0 / cell_size;
            next.assign(triangle_count, std::numeric_limits<size_t>::max());
            cell_heads.max_load_factor(0.7F);
            cell_heads.reserve(triangle_count);
            for (size_t triangle = 0U; triangle < triangle_count; ++triangle) {
                const Point3& centroid = triangles[triangle].centroid;
                const GridKey key{
                    grid_coordinate(centroid[0] - anchor[0], inverse_cell_size),
                    grid_coordinate(centroid[1] - anchor[1], inverse_cell_size),
                    grid_coordinate(centroid[2] - anchor[2], inverse_cell_size),
                };
                auto [cell, inserted] = cell_heads.try_emplace(
                    key, std::numeric_limits<size_t>::max());
                (void)inserted;
                next[triangle] = cell->second;
                cell->second = triangle;
            }
            candidates.reserve(std::min<size_t>(triangle_count, 1024U));
        }

        for (size_t ray = 0U; ray < ray_count; ++ray) {
            const std::int64_t ray_vertex = ray_id_data[ray];
            const Point3 origin = read_point(ray_vertex);
            const double* const direction_values = direction_data + ray * 3U;
            const Point3 direction{
                direction_values[0], direction_values[1], direction_values[2]};
            double best = std::numeric_limits<double>::infinity();

            const auto test_triangle = [&](const size_t triangle) {
                const IndexedRayTriangle& candidate = triangles[triangle];
                if (candidate.vertex_ids[0] == ray_vertex
                    || candidate.vertex_ids[1] == ray_vertex
                    || candidate.vertex_ids[2] == ray_vertex) {
                    return;
                }
                const double distance = ray_triangle_distance(
                    origin, direction, candidate.geometry, epsilon);
                if (distance < best
                    && (!distance_is_bounded || distance <= max_distance)) {
                    best = distance;
                }
            };

            if (!use_spatial_hash) {
                for (size_t triangle = 0U; triangle < triangle_count; ++triangle) {
                    test_triangle(triangle);
                }
            } else {
                const GridKey origin_key{
                    grid_coordinate(origin[0] - anchor[0], inverse_cell_size),
                    grid_coordinate(origin[1] - anchor[1], inverse_cell_size),
                    grid_coordinate(origin[2] - anchor[2], inverse_cell_size),
                };
                candidates.clear();
                // Two-cell padding protects the conservative bound from a
                // quotient rounding at a hash-cell boundary.
                for (std::int64_t dx = -2; dx <= 2; ++dx) {
                    for (std::int64_t dy = -2; dy <= 2; ++dy) {
                        for (std::int64_t dz = -2; dz <= 2; ++dz) {
                            const auto cell = cell_heads.find(GridKey{
                                origin_key.x + dx,
                                origin_key.y + dy,
                                origin_key.z + dz,
                            });
                            if (cell == cell_heads.end()) {
                                continue;
                            }
                            for (size_t triangle = cell->second;
                                 triangle != std::numeric_limits<size_t>::max();
                                 triangle = next[triangle]) {
                                candidates.push_back(triangle);
                            }
                        }
                    }
                }
                std::sort(candidates.begin(), candidates.end());
                for (const size_t triangle : candidates) {
                    test_triangle(triangle);
                }
            }
            output[ray] = best;
        }
    }
    return result;
}


py::array_t<bool> centroid_overlap_mask(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& radii,
    const double epsilon)
{
    if (points.ndim() != 2 || points.shape(1) != 3
        || radii.ndim() != 1 || radii.shape(0) != points.shape(0)) {
        throw std::invalid_argument("points must be Nx3 and radii must be N");
    }
    if (!std::isfinite(epsilon) || epsilon < 0.0) {
        throw std::invalid_argument("epsilon must be finite and non-negative");
    }
    const auto point_view = points.unchecked<2>();
    const auto radius_view = radii.unchecked<1>();
    const size_t count = static_cast<size_t>(points.shape(0));
    py::array_t<bool> result(points.shape(0));
    auto result_view = result.mutable_unchecked<1>();
    if (count == 0U) return result;
    double max_radius = 0.0;
    for (size_t index = 0U; index < count; ++index) {
        for (int axis = 0; axis < 3; ++axis) {
            if (!std::isfinite(point_view(static_cast<py::ssize_t>(index), axis))) {
                throw std::invalid_argument("points must be finite");
            }
        }
        const double radius = radius_view(static_cast<py::ssize_t>(index));
        if (!std::isfinite(radius) || radius < 0.0) {
            throw std::invalid_argument("radii must be finite and non-negative");
        }
        max_radius = std::max(max_radius, radius);
        result_view(static_cast<py::ssize_t>(index)) = false;
    }
    if (!(max_radius > 0.0)) return result;
    std::unordered_map<GridKey, std::vector<size_t>, GridKeyHash> buckets;
    buckets.max_load_factor(0.7F);
    buckets.reserve(count);
    const double inverse_cell_size = 1.0 / max_radius;
    std::vector<GridKey> keys(count);
    {
        py::gil_scoped_release release;
        for (size_t index = 0U; index < count; ++index) {
            const auto row = static_cast<py::ssize_t>(index);
            keys[index] = GridKey{
                grid_coordinate(point_view(row, 0), inverse_cell_size),
                grid_coordinate(point_view(row, 1), inverse_cell_size),
                grid_coordinate(point_view(row, 2), inverse_cell_size)};
            buckets[keys[index]].push_back(index);
        }
        const double epsilon_squared = epsilon * epsilon;
        for (size_t index = 0U; index < count; ++index) {
            const double radius = radius_view(static_cast<py::ssize_t>(index));
            if (!(radius > 0.0)) continue;
            const auto& key = keys[index];
            bool blocked = false;
            for (std::int64_t dx = -1; dx <= 1 && !blocked; ++dx) {
                for (std::int64_t dy = -1; dy <= 1 && !blocked; ++dy) {
                    for (std::int64_t dz = -1; dz <= 1 && !blocked; ++dz) {
                        const auto bucket = buckets.find(
                            GridKey{key.x + dx, key.y + dy, key.z + dz});
                        if (bucket == buckets.end()) continue;
                        for (const size_t other : bucket->second) {
                            if (other == index) continue;
                            const auto row = static_cast<py::ssize_t>(index);
                            const auto other_row = static_cast<py::ssize_t>(other);
                            const double px = point_view(row, 0) - point_view(other_row, 0);
                            const double py_value = point_view(row, 1) - point_view(other_row, 1);
                            const double pz = point_view(row, 2) - point_view(other_row, 2);
                            const double distance_squared = px * px + py_value * py_value + pz * pz;
                            if (distance_squared > epsilon_squared
                                && distance_squared < radius * radius) {
                                blocked = true;
                                break;
                            }
                        }
                    }
                }
            }
            result_view(static_cast<py::ssize_t>(index)) = blocked;
        }
    }
    return result;
}


py::array_t<bool> centroid_query_overlap_mask(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& query_points,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& query_radii,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& source_points,
    const double epsilon)
{
    if (query_points.ndim() != 2 || query_points.shape(1) != 3
        || query_radii.ndim() != 1 || query_radii.shape(0) != query_points.shape(0)
        || source_points.ndim() != 2 || source_points.shape(1) != 3) {
        throw std::invalid_argument("query/source points and query radii have invalid shapes");
    }
    if (!std::isfinite(epsilon) || epsilon < 0.0) {
        throw std::invalid_argument("epsilon must be finite and non-negative");
    }
    const auto query = query_points.unchecked<2>();
    const auto radii = query_radii.unchecked<1>();
    const auto source = source_points.unchecked<2>();
    const size_t query_count = static_cast<size_t>(query_points.shape(0));
    const size_t source_count = static_cast<size_t>(source_points.shape(0));
    py::array_t<bool> result(query_points.shape(0));
    auto output = result.mutable_unchecked<1>();
    double max_radius = 0.0;
    for (size_t i = 0U; i < query_count; ++i) {
        for (int axis = 0; axis < 3; ++axis) {
            if (!std::isfinite(query(static_cast<py::ssize_t>(i), axis))) {
                throw std::invalid_argument("query points must be finite");
            }
        }
        const double radius = radii(static_cast<py::ssize_t>(i));
        if (!std::isfinite(radius) || radius < 0.0) {
            throw std::invalid_argument("query radii must be finite and non-negative");
        }
        max_radius = std::max(max_radius, radius);
        output(static_cast<py::ssize_t>(i)) = false;
    }
    if (source_count == 0U || !(max_radius > 0.0)) return result;
    std::unordered_map<GridKey, std::vector<size_t>, GridKeyHash> buckets;
    buckets.max_load_factor(0.7F);
    buckets.reserve(source_count);
    const double inverse_cell_size = 1.0 / max_radius;
    {
        py::gil_scoped_release release;
        for (size_t j = 0U; j < source_count; ++j) {
            for (int axis = 0; axis < 3; ++axis) {
                if (!std::isfinite(source(static_cast<py::ssize_t>(j), axis))) {
                    throw std::invalid_argument("source points must be finite");
                }
            }
            const auto row = static_cast<py::ssize_t>(j);
            const GridKey key{
                grid_coordinate(source(row, 0), inverse_cell_size),
                grid_coordinate(source(row, 1), inverse_cell_size),
                grid_coordinate(source(row, 2), inverse_cell_size)};
            buckets[key].push_back(j);
        }
        const double epsilon_squared = epsilon * epsilon;
        for (size_t i = 0U; i < query_count; ++i) {
            const double radius = radii(static_cast<py::ssize_t>(i));
            if (!(radius > 0.0)) continue;
            const auto row = static_cast<py::ssize_t>(i);
            const GridKey key{
                grid_coordinate(query(row, 0), inverse_cell_size),
                grid_coordinate(query(row, 1), inverse_cell_size),
                grid_coordinate(query(row, 2), inverse_cell_size)};
            bool blocked = false;
            for (std::int64_t dx = -1; dx <= 1 && !blocked; ++dx) {
                for (std::int64_t dy = -1; dy <= 1 && !blocked; ++dy) {
                    for (std::int64_t dz = -1; dz <= 1 && !blocked; ++dz) {
                        const auto bucket = buckets.find(
                            GridKey{key.x + dx, key.y + dy, key.z + dz});
                        if (bucket == buckets.end()) continue;
                        for (const size_t j : bucket->second) {
                            const auto other = static_cast<py::ssize_t>(j);
                            const double px = query(row, 0) - source(other, 0);
                            const double py_value = query(row, 1) - source(other, 1);
                            const double pz = query(row, 2) - source(other, 2);
                            const double distance_squared = px * px + py_value * py_value + pz * pz;
                            if (distance_squared > epsilon_squared
                                && distance_squared < radius * radius) {
                                blocked = true;
                                break;
                            }
                        }
                    }
                }
            }
            output(row) = blocked;
        }
    }
    return result;
}

}  // namespace

PYBIND11_MODULE(native_bl, module)
{
    module.doc() = "C++23 boundary-layer search kernels for AutoTessell";
    module.def(
        "nearby_opposite_front_mask",
        &nearby_opposite_front_mask,
        py::arg("front_normals"),
        py::arg("front_points"),
        py::arg("search_radius"),
        py::arg("normal_dot_threshold") = -0.5);
    module.def(
        "ray_triangle_min_distance",
        &ray_triangle_min_distance,
        py::arg("origins"),
        py::arg("directions"),
        py::arg("triangle_vertices"),
        py::arg("exclude_mask") = py::none(),
        py::arg("epsilon") = 1e-12);
    module.def(
        "indexed_wall_collision_distances",
        &indexed_wall_collision_distances,
        py::arg("points"),
        py::arg("ray_vertex_ids"),
        py::arg("directions"),
        py::arg("triangle_vertex_ids"),
        py::arg("max_distance") = std::numeric_limits<double>::infinity(),
        py::arg("epsilon") = 1e-12);
    module.def(
        "centroid_query_overlap_mask",
        &centroid_query_overlap_mask,
        py::arg("query_points"),
        py::arg("query_radii"),
        py::arg("source_points"),
        py::arg("epsilon") = 1e-12);
    module.def(
        "centroid_overlap_mask",
        &centroid_overlap_mask,
        py::arg("points"),
        py::arg("radii"),
        py::arg("epsilon") = 1e-12);
    module.def(
        "layer_front_summary",
        &layer_front_summary,
        py::arg("face_ids"),
        py::arg("triangles"),
        py::arg("points"),
        py::arg("feature_cos_threshold") = 0.9);
}
