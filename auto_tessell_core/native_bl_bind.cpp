// Native boundary-layer search kernels.
//
// The uniform-grid hash keeps collision candidates local without allocating
// the dense N x N dot-product and distance matrices used by the NumPy oracle.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <numeric>
#include <stdexcept>
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

    py::array_t<double> result({static_cast<py::ssize_t>(ray_count)});
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

    py::array_t<double> result({static_cast<py::ssize_t>(ray_count)});
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
}
