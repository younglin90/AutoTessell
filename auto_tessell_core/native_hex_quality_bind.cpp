// OpenFOAM-style quality primitives for fixed-topology hexahedra.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

namespace {

using Label = long long;
using Point3 = std::array<double, 3>;
using FaceKey = std::array<Label, 4>;

constexpr std::array<std::array<int, 4>, 6> hex_faces{{
    {{0, 3, 2, 1}},
    {{4, 5, 6, 7}},
    {{0, 1, 5, 4}},
    {{3, 7, 6, 2}},
    {{0, 4, 7, 3}},
    {{1, 2, 6, 5}},
}};

constexpr std::array<int, 12> edge_first{{0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3}};
constexpr std::array<int, 12> edge_second{{1, 2, 3, 0, 5, 6, 7, 4, 4, 5, 6, 7}};

struct FaceEntry {
    FaceKey key;
    py::ssize_t cell;
    int local;
};

struct QualityValues {
    long long face_count = 0;
    double min_face_area = 0.0;
    std::vector<double> non_orthogonality;
    std::vector<double> skewness;
    std::vector<double> aspect;
};

Point3 subtract(const Point3& lhs, const Point3& rhs)
{
    return {lhs[0] - rhs[0], lhs[1] - rhs[1], lhs[2] - rhs[2]};
}

Point3 add(const Point3& lhs, const Point3& rhs)
{
    return {lhs[0] + rhs[0], lhs[1] + rhs[1], lhs[2] + rhs[2]};
}

Point3 scale(const Point3& value, double factor)
{
    return {value[0] * factor, value[1] * factor, value[2] * factor};
}

double dot(const Point3& lhs, const Point3& rhs)
{
    return lhs[0] * rhs[0] + lhs[1] * rhs[1] + lhs[2] * rhs[2];
}

Point3 cross(const Point3& lhs, const Point3& rhs)
{
    return {
        lhs[1] * rhs[2] - lhs[2] * rhs[1],
        lhs[2] * rhs[0] - lhs[0] * rhs[2],
        lhs[0] * rhs[1] - lhs[1] * rhs[0],
    };
}

double norm(const Point3& value)
{
    return std::sqrt(dot(value, value));
}

Label normalize_index(Label index, py::ssize_t point_count)
{
    if (index < 0) {
        if (index < -point_count) {
            throw py::index_error("point index is out of bounds");
        }
        index += point_count;
    }
    if (index < 0 || index >= point_count) {
        throw py::index_error("point index is out of bounds");
    }
    return index;
}

template <typename PointView>
Point3 load_point(const PointView& points, Label index, py::ssize_t point_count)
{
    const Label normalized = normalize_index(index, point_count);
    return {
        points(normalized, 0),
        points(normalized, 1),
        points(normalized, 2),
    };
}

template <typename PointView, typename HexView>
Point3 load_hex_point(
    const PointView& points,
    const HexView& hexes,
    py::ssize_t cell,
    int local,
    py::ssize_t point_count)
{
    return load_point(points, hexes(cell, local), point_count);
}

template <typename PointView, typename HexView>
QualityValues compute_quality(
    const PointView& points,
    const HexView& hexes,
    py::ssize_t point_count,
    py::ssize_t cell_count)
{
    QualityValues result;
    std::vector<Point3> cell_centroids(static_cast<size_t>(cell_count));
    std::vector<FaceEntry> entries;
    entries.reserve(static_cast<size_t>(cell_count) * hex_faces.size());

    for (py::ssize_t cell = 0; cell < cell_count; ++cell) {
        Point3 sum{0.0, 0.0, 0.0};
        for (int local = 0; local < 8; ++local) {
            sum = add(sum, load_hex_point(points, hexes, cell, local, point_count));
        }
        cell_centroids[static_cast<size_t>(cell)] = scale(sum, 0.125);

        for (int local_face = 0; local_face < 6; ++local_face) {
            FaceKey key{};
            for (int slot = 0; slot < 4; ++slot) {
                key[static_cast<size_t>(slot)] =
                    hexes(cell, hex_faces[static_cast<size_t>(local_face)][slot]);
            }
            std::sort(key.begin(), key.end());
            entries.push_back(FaceEntry{key, cell, local_face});
        }
    }

    std::stable_sort(
        entries.begin(), entries.end(), [](const FaceEntry& lhs, const FaceEntry& rhs) {
            return lhs.key < rhs.key;
        });

    double min_face_area = std::numeric_limits<double>::infinity();
    for (size_t begin = 0; begin < entries.size();) {
        size_t end = begin + 1;
        while (end < entries.size() && entries[end].key == entries[begin].key) {
            ++end;
        }
        ++result.face_count;
        if (end - begin == 2) {
            const FaceEntry& first_entry = entries[begin];
            const FaceEntry& second_entry = entries[begin + 1];
            std::array<Point3, 4> vertices{};
            for (int slot = 0; slot < 4; ++slot) {
                vertices[static_cast<size_t>(slot)] = load_hex_point(
                    points,
                    hexes,
                    first_entry.cell,
                    hex_faces[static_cast<size_t>(first_entry.local)][slot],
                    point_count);
            }

            const Point3 first_cross = cross(
                subtract(vertices[1], vertices[0]),
                subtract(vertices[2], vertices[0]));
            const Point3 second_cross = cross(
                subtract(vertices[2], vertices[0]),
                subtract(vertices[3], vertices[0]));
            const Point3 normal_sum = add(first_cross, second_cross);
            const double normal_length = norm(normal_sum);
            Point3 unit_normal{0.0, 0.0, 0.0};
            if (normal_length > 1e-30) {
                unit_normal = scale(normal_sum, 1.0 / normal_length);
            }
            const Point3 face_centroid = scale(
                add(add(vertices[0], vertices[1]), add(vertices[2], vertices[3])),
                0.25);
            const double area = 0.5 * (norm(first_cross) + norm(second_cross));
            if (area < min_face_area) {
                min_face_area = area;
            }

            const Point3 cell_delta = subtract(
                cell_centroids[static_cast<size_t>(second_entry.cell)],
                cell_centroids[static_cast<size_t>(first_entry.cell)]);
            const double delta_length = norm(cell_delta);
            if (!(delta_length < 1e-30)) {
                const Point3 delta_unit = scale(cell_delta, 1.0 / delta_length);
                double cosine = std::abs(dot(delta_unit, unit_normal));
                if (cosine < 0.0) {
                    cosine = 0.0;
                } else if (cosine > 1.0) {
                    cosine = 1.0;
                }
                result.non_orthogonality.push_back(
                    std::acos(cosine) * (180.0 / std::acos(-1.0)));

                const double denominator = dot(delta_unit, unit_normal);
                if (!(std::abs(denominator) < 1e-30)) {
                    const Point3 owner_centroid =
                        cell_centroids[static_cast<size_t>(first_entry.cell)];
                    const double parameter =
                        dot(subtract(face_centroid, owner_centroid), unit_normal)
                        / denominator;
                    const Point3 intersection =
                        add(owner_centroid, scale(delta_unit, parameter));
                    const double skew_distance =
                        norm(subtract(intersection, face_centroid));
                    if (area > 0.0) {
                        result.skewness.push_back(skew_distance / std::sqrt(area));
                    }
                }
            }
        }
        begin = end;
    }

    if (result.non_orthogonality.empty()) {
        result.non_orthogonality.push_back(0.0);
    }
    if (result.skewness.empty()) {
        result.skewness.push_back(0.0);
    }
    result.min_face_area = std::isinf(min_face_area) ? 0.0 : min_face_area;

    result.aspect.reserve(static_cast<size_t>(cell_count));
    for (py::ssize_t cell = 0; cell < cell_count; ++cell) {
        double maximum = 0.0;
        double minimum = std::numeric_limits<double>::infinity();
        bool maximum_is_nan = false;
        for (size_t edge = 0; edge < edge_first.size(); ++edge) {
            const Point3 first = load_hex_point(
                points, hexes, cell, edge_first[edge], point_count);
            const Point3 second = load_hex_point(
                points, hexes, cell, edge_second[edge], point_count);
            const double length = norm(subtract(second, first));
            if (std::isnan(length)) {
                maximum_is_nan = true;
            } else {
                maximum = std::max(maximum, length);
            }
            if (length > 1e-30) {
                minimum = std::min(minimum, length);
            }
        }
        if (maximum_is_nan) {
            maximum = std::numeric_limits<double>::quiet_NaN();
        }
        minimum = std::max(minimum, 1e-30);
        result.aspect.push_back(maximum / minimum);
    }
    return result;
}

py::array_t<double> copy_values(const std::vector<double>& values)
{
    py::array_t<double> output({static_cast<py::ssize_t>(values.size())});
    auto view = output.mutable_unchecked<1>();
    for (size_t index = 0; index < values.size(); ++index) {
        view(static_cast<py::ssize_t>(index)) = values[index];
    }
    return output;
}

py::tuple hex_quality_primitives(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    py::array_t<Label, py::array::c_style | py::array::forcecast> hexes)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (hexes.ndim() != 2 || hexes.shape(1) != 8) {
        throw std::invalid_argument("hexes must have shape (C, 8)");
    }

    QualityValues values;
    const auto point_view = points.unchecked<2>();
    const auto hex_view = hexes.unchecked<2>();
    {
        py::gil_scoped_release release;
        values = compute_quality(
            point_view, hex_view, points.shape(0), hexes.shape(0));
    }
    return py::make_tuple(
        values.face_count,
        copy_values(values.non_orthogonality),
        copy_values(values.skewness),
        copy_values(values.aspect),
        values.min_face_area);
}

}  // namespace

PYBIND11_MODULE(native_hex_quality, module)
{
    module.doc() = "C++ OpenFOAM-style quality primitives for hexahedral meshes";
    module.def(
        "hex_quality_primitives",
        &hex_quality_primitives,
        py::arg("points"),
        py::arg("hexes"));
}
