// Native boundary-layer search kernels.
//
// The uniform-grid hash keeps collision candidates local without allocating
// the dense N x N dot-product and distance matrices used by the NumPy oracle.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
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
}
