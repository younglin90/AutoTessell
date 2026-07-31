// OpenFOAM-style quality primitives for fixed-topology hexahedra.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "native_hex_quality_local_front.hpp"

namespace py = pybind11;

namespace {

using Label = long long;
using Point3 = std::array<double, 3>;
using FaceKey = std::array<Label, 4>;
using Face = std::vector<Label>;
using Cell = std::vector<Face>;
using Cells = std::vector<Cell>;

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

struct GenericFaceReference {
    size_t cell;
    Face vertices;
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

py::dict local_front_backtrack_steps(
    py::array_t<double, py::array::c_style> outer_points,
    py::array_t<std::int64_t, py::array::c_style> outer_quads,
    py::array_t<double, py::array::c_style> unit_inward_normals,
    double initial_step,
    double geometry_tolerance,
    double determinant_tolerance,
    int maximum_iterations)
{
    if (outer_points.ndim() != 2 || outer_points.shape(1) != 3) {
        throw std::invalid_argument("outer_points must have shape (V, 3)");
    }
    if (outer_quads.ndim() != 2 || outer_quads.shape(1) != 4) {
        throw std::invalid_argument("outer_quads must have shape (H, 4)");
    }
    if (unit_inward_normals.ndim() != 2
        || unit_inward_normals.shape(0) != outer_points.shape(0)
        || unit_inward_normals.shape(1) != 3) {
        throw std::invalid_argument("unit_inward_normals must have shape (V, 3)");
    }
    if (outer_points.shape(0) <= 0 || outer_quads.shape(0) <= 0) {
        throw std::invalid_argument("local front requires non-empty vertices and quads");
    }
    constexpr std::size_t maximum_size = std::numeric_limits<std::size_t>::max();
    const auto vertex_count = static_cast<std::size_t>(outer_points.shape(0));
    const auto hex_count = static_cast<std::size_t>(outer_quads.shape(0));
    if (vertex_count > maximum_size / 3U || hex_count > maximum_size / 4U) {
        throw std::overflow_error("local front input shape exceeds addressable size");
    }
    if (!std::isfinite(geometry_tolerance) || geometry_tolerance <= 0.0) {
        throw std::invalid_argument("geometry_tolerance must be finite and positive");
    }
    if (!std::isfinite(initial_step) || initial_step <= geometry_tolerance) {
        throw std::invalid_argument(
            "initial_step must be finite and greater than geometry_tolerance");
    }
    if (!std::isfinite(determinant_tolerance) || determinant_tolerance < 0.0) {
        throw std::invalid_argument(
            "determinant_tolerance must be finite and non-negative");
    }
    if (maximum_iterations <= 0 || maximum_iterations > 64) {
        throw std::invalid_argument("maximum_iterations must be in [1, 64]");
    }

    const double* outer_data = outer_points.data();
    const double* normal_data = unit_inward_normals.data();
    const std::int64_t* quad_data = outer_quads.data();
    constexpr double unit_tolerance =
        256.0 * std::numeric_limits<double>::epsilon();
    for (std::size_t vertex = 0; vertex < vertex_count; ++vertex) {
        double squared_norm = 0.0;
        for (std::size_t axis = 0; axis < 3U; ++axis) {
            const std::size_t offset = 3U * vertex + axis;
            const double coordinate = outer_data[offset];
            const double normal = normal_data[offset];
            if (!std::isfinite(coordinate) || !std::isfinite(normal)) {
                throw std::invalid_argument("outer points and normals must be finite");
            }
            if (!std::isfinite(coordinate - initial_step * normal)) {
                throw std::overflow_error("initial inner-front coordinate is not finite");
            }
            squared_norm += normal * normal;
        }
        const double normal_length = std::sqrt(squared_norm);
        if (!std::isfinite(normal_length)
            || std::abs(normal_length - 1.0) > unit_tolerance) {
            throw std::invalid_argument(
                "unit_inward_normals rows must have unit length within 256*epsilon");
        }
    }
    for (std::size_t hex = 0; hex < hex_count; ++hex) {
        std::array<std::int64_t, 4> quad{};
        for (std::size_t slot = 0; slot < quad.size(); ++slot) {
            const std::int64_t vertex = quad_data[4U * hex + slot];
            if (vertex < 0
                || static_cast<std::uint64_t>(vertex)
                    >= static_cast<std::uint64_t>(vertex_count)) {
                throw py::index_error("outer_quads contains a vertex out of range");
            }
            quad[slot] = vertex;
        }
        std::sort(quad.begin(), quad.end());
        if (std::adjacent_find(quad.begin(), quad.end()) != quad.end()) {
            throw std::invalid_argument("outer_quads rows must contain four unique vertices");
        }
    }

    py::array_t<double> local_steps({static_cast<py::ssize_t>(vertex_count)});
    autotessell::native_hex::LocalFrontResult result;
    {
        py::gil_scoped_release release;
        result = autotessell::native_hex::backtrack_local_front(
            std::span<const double>(outer_data, 3U * vertex_count),
            std::span<const std::int64_t>(quad_data, 4U * hex_count),
            std::span<const double>(normal_data, 3U * vertex_count),
            std::span<double>(local_steps.mutable_data(), vertex_count),
            initial_step,
            geometry_tolerance,
            determinant_tolerance,
            static_cast<std::size_t>(maximum_iterations));
    }

    const auto steps = local_steps.unchecked<1>();
    double minimum_step = std::numeric_limits<double>::infinity();
    double maximum_step = 0.0;
    for (py::ssize_t vertex = 0; vertex < steps.shape(0); ++vertex) {
        minimum_step = std::min(minimum_step, steps(vertex));
        maximum_step = std::max(maximum_step, steps(vertex));
    }
    py::dict report;
    report["local_steps"] = std::move(local_steps);
    report["iterations"] = result.iterations;
    report["reduced_vertices"] = result.reduced_vertices;
    report["collapsed_vertices"] = result.collapsed_vertices;
    report["raw_negative_hexes"] = result.raw_negative_hexes;
    report["nonpositive_corner_hexes"] = result.nonpositive_corner_hexes;
    report["minimum_corner_determinant"] = result.minimum_corner_determinant;
    report["minimum_step"] = minimum_step;
    report["maximum_step"] = maximum_step;
    report["converged"] = result.converged;
    report["unit_normal_tolerance"] = unit_tolerance;
    return report;
}

py::dict local_front_numeric_admission(
    py::array_t<std::int64_t, py::array::c_style> source_face_ids,
    long long source_face_count,
    double requested_step,
    double minimum_clearance)
{
    if (source_face_count <= 0) {
        throw std::invalid_argument("source_face_count must be positive");
    }
    if (source_face_ids.ndim() != 1) {
        throw std::invalid_argument("source_face_ids must have shape (Q,)");
    }
    const auto result = autotessell::native_hex::audit_local_front_numeric_admission(
        std::span<const autotessell::native_hex::Label>(
            source_face_ids.data(), static_cast<std::size_t>(source_face_ids.shape(0))),
        static_cast<std::size_t>(source_face_count), requested_step, minimum_clearance);
    py::dict output;
    output["source_rows_complete"] = result.source_rows_complete;
    output["clearance_sufficient"] = result.clearance_sufficient;
    output["source_face_count"] = result.source_face_count;
    output["quad_count"] = result.quad_count;
    return output;
}

py::dict certify_oriented_box(
    py::array_t<double, py::array::c_style | py::array::forcecast> points_array,
    const std::vector<Face>& faces)
{
    constexpr double tolerance_factor = 8.0;
    const double normalized_tolerance =
        tolerance_factor * std::sqrt(std::numeric_limits<double>::epsilon());
    const py::buffer_info point_info = points_array.request();
    if (point_info.ndim != 2 || point_info.shape[0] != 8 || point_info.shape[1] != 3) {
        throw std::invalid_argument("requires_exactly_8_finite_points");
    }
    if (faces.size() != 6U) {
        throw std::invalid_argument("requires_exactly_6_quad_faces");
    }

    const auto points = points_array.unchecked<2>();
    std::array<Point3, 8> vertices{};
    Point3 minima{};
    Point3 maxima{};
    for (size_t vertex = 0; vertex < vertices.size(); ++vertex) {
        Point3 point{};
        for (size_t axis = 0; axis < 3U; ++axis) {
            point[axis] = points(
                static_cast<py::ssize_t>(vertex), static_cast<py::ssize_t>(axis));
            if (!std::isfinite(point[axis])) {
                throw std::invalid_argument("requires_exactly_8_finite_points");
            }
        }
        vertices[vertex] = point;
        if (vertex == 0U) {
            minima = point;
            maxima = point;
        } else {
            for (size_t axis = 0; axis < 3U; ++axis) {
                minima[axis] = std::min(minima[axis], point[axis]);
                maxima[axis] = std::max(maxima[axis], point[axis]);
            }
        }
    }
    const double bounding_diagonal = norm(subtract(maxima, minima));
    const double coordinate_tolerance =
        normalized_tolerance * std::max(1.0, bounding_diagonal);

    std::map<std::pair<Label, Label>, int> edge_incidence;
    std::set<Label> used_vertices;
    for (const Face& face : faces) {
        if (face.size() != 4U) {
            throw std::invalid_argument("requires_exactly_6_quad_faces");
        }
        std::set<Label> face_vertices;
        for (size_t slot = 0; slot < face.size(); ++slot) {
            const Label vertex = face[slot];
            const Label adjacent = face[(slot + 1U) % face.size()];
            if (vertex < 0 || vertex >= 8 || adjacent < 0 || adjacent >= 8) {
                throw std::invalid_argument("face_point_id_out_of_range");
            }
            face_vertices.insert(vertex);
            used_vertices.insert(vertex);
            const auto edge = std::minmax(vertex, adjacent);
            ++edge_incidence[{edge.first, edge.second}];
        }
        if (face_vertices.size() != 4U) {
            throw std::invalid_argument("quad_has_repeated_vertex");
        }
    }
    if (used_vertices.size() != 8U) {
        throw std::invalid_argument("requires_exactly_8_used_vertices");
    }
    if (edge_incidence.size() != 12U
        || std::any_of(edge_incidence.begin(), edge_incidence.end(),
            [](const auto& entry) { return entry.second != 2; })) {
        throw std::invalid_argument("requires_12_edges_with_incidence_2");
    }

    std::array<std::vector<Label>, 8> adjacency{};
    for (const auto& [edge, incidence] : edge_incidence) {
        (void)incidence;
        adjacency[static_cast<size_t>(edge.first)].push_back(edge.second);
        adjacency[static_cast<size_t>(edge.second)].push_back(edge.first);
    }
    for (auto& neighbors : adjacency) {
        std::sort(neighbors.begin(), neighbors.end());
        if (neighbors.size() != 3U) {
            throw std::invalid_argument("box_graph_requires_vertex_degree_3");
        }
    }

    constexpr Label anchor = 0;
    std::array<Label, 3> basis_neighbors{
        adjacency[anchor][0], adjacency[anchor][1], adjacency[anchor][2]};
    std::array<Point3, 3> basis{};
    std::array<double, 3> side_lengths{};
    for (size_t axis = 0; axis < 3U; ++axis) {
        basis[axis] = subtract(
            vertices[static_cast<size_t>(basis_neighbors[axis])], vertices[anchor]);
        side_lengths[axis] = norm(basis[axis]);
        if (!std::isfinite(side_lengths[axis])
            || side_lengths[axis] <= 4.0 * coordinate_tolerance) {
            throw std::invalid_argument("box_side_length_not_positive");
        }
    }
    for (size_t first = 0; first < 3U; ++first) {
        for (size_t second = first + 1U; second < 3U; ++second) {
            const double normalized_dot = std::abs(dot(basis[first], basis[second]))
                / (side_lengths[first] * side_lengths[second]);
            if (!std::isfinite(normalized_dot)
                || normalized_dot > normalized_tolerance) {
                throw std::invalid_argument("basis_edges_are_not_orthogonal");
            }
        }
    }
    double determinant = dot(cross(basis[0], basis[1]), basis[2]);
    if (determinant < 0.0) {
        std::swap(basis[1], basis[2]);
        std::swap(side_lengths[1], side_lengths[2]);
        std::swap(basis_neighbors[1], basis_neighbors[2]);
        determinant = -determinant;
    }
    const double normalized_determinant =
        determinant / (side_lengths[0] * side_lengths[1] * side_lengths[2]);
    if (!std::isfinite(normalized_determinant)
        || normalized_determinant < 1.0 - 4.0 * normalized_tolerance) {
        throw std::invalid_argument("basis_is_not_right_handed_orthogonal");
    }

    std::array<int, 8> vertex_roles{};
    vertex_roles.fill(-1);
    std::array<Label, 8> role_vertices{};
    role_vertices.fill(-1);
    for (size_t vertex = 0; vertex < vertices.size(); ++vertex) {
        int matched_role = -1;
        for (int role = 0; role < 8; ++role) {
            Point3 expected = vertices[anchor];
            for (size_t axis = 0; axis < 3U; ++axis) {
                if ((role & (1 << axis)) != 0) {
                    expected = add(expected, basis[axis]);
                }
            }
            if (norm(subtract(vertices[vertex], expected)) <= coordinate_tolerance) {
                if (matched_role != -1) {
                    throw std::invalid_argument("corner_role_is_not_unique");
                }
                matched_role = role;
            }
        }
        if (matched_role == -1 || role_vertices[static_cast<size_t>(matched_role)] != -1) {
            throw std::invalid_argument("points_are_not_8_oriented_box_corners");
        }
        vertex_roles[vertex] = matched_role;
        role_vertices[static_cast<size_t>(matched_role)] = static_cast<Label>(vertex);
    }

    std::set<std::pair<int, int>> edge_roles;
    for (const auto& [edge, incidence] : edge_incidence) {
        (void)incidence;
        const int first_role = vertex_roles[static_cast<size_t>(edge.first)];
        const int second_role = vertex_roles[static_cast<size_t>(edge.second)];
        const int difference = first_role ^ second_role;
        if (difference != 1 && difference != 2 && difference != 4) {
            throw std::invalid_argument("edge_does_not_match_oriented_box_role");
        }
        edge_roles.emplace(std::min(first_role, second_role), std::max(first_role, second_role));
    }
    if (edge_roles.size() != 12U) {
        throw std::invalid_argument("edge_roles_are_not_bijective");
    }

    std::vector<std::array<int, 2>> face_roles;
    face_roles.reserve(faces.size());
    std::set<std::array<int, 2>> unique_face_roles;
    for (const Face& face : faces) {
        int constant_axis = -1;
        int constant_side = -1;
        for (int axis = 0; axis < 3; ++axis) {
            const int side = (vertex_roles[static_cast<size_t>(face[0])] >> axis) & 1;
            const bool constant = std::all_of(face.begin(), face.end(), [&](Label vertex) {
                return ((vertex_roles[static_cast<size_t>(vertex)] >> axis) & 1) == side;
            });
            if (constant) {
                if (constant_axis != -1) {
                    throw std::invalid_argument("face_role_is_not_unique");
                }
                constant_axis = axis;
                constant_side = side;
            }
        }
        if (constant_axis == -1) {
            throw std::invalid_argument("face_does_not_match_oriented_box_plane");
        }
        const std::array<int, 2> role{constant_axis, constant_side};
        if (!unique_face_roles.insert(role).second) {
            throw std::invalid_argument("face_roles_are_not_bijective");
        }
        face_roles.push_back(role);
    }
    if (unique_face_roles.size() != 6U) {
        throw std::invalid_argument("face_roles_are_not_bijective");
    }

    py::dict report;
    report["side_lengths"] = side_lengths;
    report["vertex_roles"] = vertex_roles;
    report["face_roles"] = face_roles;
    report["basis_neighbors"] = basis_neighbors;
    report["normalized_tolerance"] = normalized_tolerance;
    report["coordinate_tolerance"] = coordinate_tolerance;
    return report;
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

py::array_t<double> generic_cell_signed_volumes(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    const Cells& cell_faces)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    py::array_t<double> volumes(
        {static_cast<py::ssize_t>(cell_faces.size())});
    auto output = volumes.mutable_unchecked<1>();
    const auto point_view = points.unchecked<2>();
    const py::ssize_t point_count = points.shape(0);

    {
        py::gil_scoped_release release;
        for (size_t cell_index = 0; cell_index < cell_faces.size(); ++cell_index) {
            const Cell& cell = cell_faces[cell_index];
            std::vector<Label> vertices;
            for (const Face& face : cell) {
                vertices.insert(vertices.end(), face.begin(), face.end());
            }
            std::sort(vertices.begin(), vertices.end());
            vertices.erase(std::unique(vertices.begin(), vertices.end()), vertices.end());
            if (vertices.empty()) {
                throw std::invalid_argument("cell must contain at least one vertex");
            }

            Point3 sum{0.0, 0.0, 0.0};
            for (const Label vertex : vertices) {
                sum = add(sum, load_point(point_view, vertex, point_count));
            }
            const Point3 centroid = scale(
                sum, 1.0 / static_cast<double>(vertices.size()));

            double volume = 0.0;
            for (const Face& face : cell) {
                if (face.empty()) {
                    throw std::invalid_argument("face must contain at least one vertex");
                }
                const Point3 first = load_point(
                    point_view, face.front(), point_count);
                for (size_t slot = 1; slot + 1 < face.size(); ++slot) {
                    const Point3 second = load_point(
                        point_view, face[slot], point_count);
                    const Point3 third = load_point(
                        point_view, face[slot + 1], point_count);
                    volume += dot(
                        subtract(first, centroid),
                        cross(
                            subtract(second, centroid),
                            subtract(third, centroid)))
                        / 6.0;
                }
            }
            output(static_cast<py::ssize_t>(cell_index)) = volume;
        }
    }
    return volumes;
}

py::array_t<double> boundary_vertex_local_scales(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    const Cells& cell_faces,
    py::array_t<Label, py::array::c_style | py::array::forcecast> boundary_vertices)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (boundary_vertices.ndim() != 1) {
        throw std::invalid_argument("boundary_vertices must have shape (B,)");
    }

    const py::ssize_t point_count = points.shape(0);
    const py::ssize_t boundary_count = boundary_vertices.shape(0);
    py::array_t<double> local_scales({boundary_count});
    const auto point_view = points.unchecked<2>();
    const auto boundary_view = boundary_vertices.unchecked<1>();
    auto output = local_scales.mutable_unchecked<1>();

    {
        py::gil_scoped_release release;
        std::vector<py::ssize_t> boundary_slots(
            static_cast<size_t>(point_count), py::ssize_t{-1});
        for (py::ssize_t slot = 0; slot < boundary_count; ++slot) {
            const Label vertex = normalize_index(
                boundary_view(slot), point_count);
            auto& mapped_slot = boundary_slots[static_cast<size_t>(vertex)];
            if (mapped_slot != py::ssize_t{-1}) {
                throw std::invalid_argument("boundary_vertices must be unique");
            }
            mapped_slot = slot;
            output(slot) = 0.0;
        }

        for (const Cell& cell : cell_faces) {
            double cell_scale = 0.0;
            for (const Face& face : cell) {
                const size_t face_size = face.size();
                for (size_t edge = 0; edge < face_size; ++edge) {
                    const Point3 first = load_point(
                        point_view, face[edge], point_count);
                    const Point3 second = load_point(
                        point_view, face[(edge + 1) % face_size], point_count);
                    cell_scale = std::max(
                        cell_scale, norm(subtract(first, second)));
                }
            }
            for (const Face& face : cell) {
                for (const Label raw_vertex : face) {
                    const Label vertex = normalize_index(raw_vertex, point_count);
                    const py::ssize_t slot =
                        boundary_slots[static_cast<size_t>(vertex)];
                    if (slot != py::ssize_t{-1}) {
                        output(slot) = std::max(output(slot), cell_scale);
                    }
                }
            }
        }
    }
    return local_scales;
}

py::tuple generic_cell_face_signs(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    const Cell& cell_faces)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    py::array_t<double> signs(
        {static_cast<py::ssize_t>(cell_faces.size())});
    auto output = signs.mutable_unchecked<1>();
    const auto point_view = points.unchecked<2>();
    const py::ssize_t point_count = points.shape(0);
    double magnitude = 0.0;

    {
        py::gil_scoped_release release;
        std::vector<Label> vertices;
        for (const Face& face : cell_faces) {
            vertices.insert(vertices.end(), face.begin(), face.end());
        }
        std::sort(vertices.begin(), vertices.end());
        vertices.erase(std::unique(vertices.begin(), vertices.end()), vertices.end());
        if (vertices.empty()) {
            throw std::invalid_argument("cell must contain at least one vertex");
        }

        Point3 sum{0.0, 0.0, 0.0};
        for (const Label vertex : vertices) {
            sum = add(sum, load_point(point_view, vertex, point_count));
        }
        const Point3 centroid = scale(
            sum, 1.0 / static_cast<double>(vertices.size()));

        for (size_t face_index = 0; face_index < cell_faces.size(); ++face_index) {
            const Face& face = cell_faces[face_index];
            if (face.empty()) {
                throw std::invalid_argument("face must contain at least one vertex");
            }
            const Point3 first = subtract(
                load_point(point_view, face.front(), point_count), centroid);
            double sign = 0.0;
            for (size_t slot = 1; slot + 1 < face.size(); ++slot) {
                const Point3 second = subtract(
                    load_point(point_view, face[slot], point_count), centroid);
                const Point3 third = subtract(
                    load_point(point_view, face[slot + 1], point_count), centroid);
                sign += dot(first, cross(second, third));
            }
            output(static_cast<py::ssize_t>(face_index)) = sign;
            magnitude += std::abs(sign);
        }
    }
    return py::make_tuple(signs, magnitude);
}

py::tuple generic_side_metrics(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    const Cells& cell_faces)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    const auto point_view = points.unchecked<2>();
    const py::ssize_t point_count = points.shape(0);
    double maximum_skewness = 0.0;
    double maximum_non_orthogonality = 0.0;
    long long negative_volumes = 0;

    {
        py::gil_scoped_release release;
        std::vector<Point3> centroids(cell_faces.size());
        std::map<Face, std::vector<GenericFaceReference>> owners;
        for (size_t cell_index = 0; cell_index < cell_faces.size(); ++cell_index) {
            const Cell& cell = cell_faces[cell_index];
            std::vector<Label> vertices;
            for (const Face& face : cell) {
                vertices.insert(vertices.end(), face.begin(), face.end());
            }
            std::sort(vertices.begin(), vertices.end());
            vertices.erase(std::unique(vertices.begin(), vertices.end()), vertices.end());
            if (vertices.empty()) {
                throw std::invalid_argument("cell must contain at least one vertex");
            }
            Point3 sum{0.0, 0.0, 0.0};
            for (const Label vertex : vertices) {
                sum = add(sum, load_point(point_view, vertex, point_count));
            }
            centroids[cell_index] = scale(
                sum, 1.0 / static_cast<double>(vertices.size()));
            for (const Face& face : cell) {
                Face key = face;
                std::sort(key.begin(), key.end());
                owners[std::move(key)].push_back(
                    GenericFaceReference{cell_index, face});
            }
        }

        for (const auto& [key, references] : owners) {
            static_cast<void>(key);
            if (references.size() != 2) {
                continue;
            }
            const GenericFaceReference& first_reference = references[0];
            const GenericFaceReference& second_reference = references[1];
            const Point3 first_centroid = centroids[first_reference.cell];
            const Point3 second_centroid = centroids[second_reference.cell];
            const Point3 delta = subtract(second_centroid, first_centroid);
            const double delta_magnitude = norm(delta);
            if (delta_magnitude < 1e-30) {
                continue;
            }

            const Face& face = first_reference.vertices;
            if (face.empty()) {
                throw std::invalid_argument("face must contain at least one vertex");
            }
            Point3 face_centroid_sum{0.0, 0.0, 0.0};
            Point3 newell{0.0, 0.0, 0.0};
            for (size_t slot = 0; slot < face.size(); ++slot) {
                const Point3 first = load_point(
                    point_view, face[slot], point_count);
                const Point3 second = load_point(
                    point_view, face[(slot + 1) % face.size()], point_count);
                face_centroid_sum = add(face_centroid_sum, first);
                newell[0] += (first[1] - second[1]) * (first[2] + second[2]);
                newell[1] += (first[2] - second[2]) * (first[0] + second[0]);
                newell[2] += (first[0] - second[0]) * (first[1] + second[1]);
            }
            const Point3 face_centroid = scale(
                face_centroid_sum, 1.0 / static_cast<double>(face.size()));
            const double normal_magnitude = norm(newell);
            const Point3 unit_normal = normal_magnitude > 1e-30
                ? scale(newell, 1.0 / normal_magnitude)
                : newell;

            const double parameter =
                dot(subtract(face_centroid, first_centroid), delta)
                / (delta_magnitude * delta_magnitude);
            const Point3 projected = add(first_centroid, scale(delta, parameter));
            maximum_skewness = std::max(
                maximum_skewness,
                norm(subtract(face_centroid, projected)) / delta_magnitude);

            if (unit_normal[0] != 0.0 || unit_normal[1] != 0.0
                || unit_normal[2] != 0.0) {
                double cosine = std::abs(dot(unit_normal, delta)) / delta_magnitude;
                if (std::isnan(cosine)) {
                    cosine = 0.0;
                } else if (cosine < 0.0) {
                    cosine = 0.0;
                } else if (cosine > 1.0) {
                    cosine = 1.0;
                }
                maximum_non_orthogonality = std::max(
                    maximum_non_orthogonality,
                    std::acos(cosine) * (180.0 / std::acos(-1.0)));
            }
        }

        for (size_t cell_index = 0; cell_index < cell_faces.size(); ++cell_index) {
            double volume = 0.0;
            const Point3 centroid = centroids[cell_index];
            for (const Face& face : cell_faces[cell_index]) {
                if (face.empty()) {
                    throw std::invalid_argument("face must contain at least one vertex");
                }
                const Point3 first = load_point(
                    point_view, face.front(), point_count);
                for (size_t slot = 1; slot + 1 < face.size(); ++slot) {
                    const Point3 second = load_point(
                        point_view, face[slot], point_count);
                    const Point3 third = load_point(
                        point_view, face[slot + 1], point_count);
                    volume += dot(
                        subtract(first, centroid),
                        cross(
                            subtract(second, centroid),
                            subtract(third, centroid)))
                        / 6.0;
                }
            }
            if (volume <= 0.0) {
                ++negative_volumes;
            }
        }
    }
    return py::make_tuple(
        maximum_skewness,
        maximum_non_orthogonality,
        static_cast<double>(negative_volumes));
}

py::array_t<double> hex_face_nonorthogonality(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    py::array_t<Label, py::array::c_style | py::array::forcecast> hexes,
    py::array_t<Label, py::array::c_style | py::array::forcecast> faces,
    py::array_t<Label, py::array::c_style | py::array::forcecast> owners)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (hexes.ndim() != 2 || hexes.shape(1) != 8) {
        throw std::invalid_argument("hexes must have shape (C, 8)");
    }
    if (faces.ndim() != 2 || faces.shape(1) != 4) {
        throw std::invalid_argument("faces must have shape (F, 4)");
    }
    if (owners.ndim() != 2 || owners.shape(1) != 2
        || owners.shape(0) != faces.shape(0)) {
        throw std::invalid_argument("owners must have shape (F, 2)");
    }

    const auto point_view = points.unchecked<2>();
    const auto hex_view = hexes.unchecked<2>();
    const auto face_view = faces.unchecked<2>();
    const auto owner_view = owners.unchecked<2>();
    const py::ssize_t point_count = points.shape(0);
    const py::ssize_t cell_count = hexes.shape(0);
    const py::ssize_t face_count = faces.shape(0);
    py::array_t<double> angles({face_count});
    auto output = angles.mutable_unchecked<1>();

    {
        py::gil_scoped_release release;
        std::vector<Point3> centroids(static_cast<size_t>(cell_count));
        for (py::ssize_t cell = 0; cell < cell_count; ++cell) {
            Point3 sum{0.0, 0.0, 0.0};
            for (int local = 0; local < 8; ++local) {
                sum = add(
                    sum,
                    load_hex_point(point_view, hex_view, cell, local, point_count));
            }
            centroids[static_cast<size_t>(cell)] = scale(sum, 0.125);
        }

        for (py::ssize_t face = 0; face < face_count; ++face) {
            const Label first_owner = owner_view(face, 0);
            const Label second_owner = owner_view(face, 1);
            if (first_owner < 0 || second_owner < 0
                || first_owner >= cell_count || second_owner >= cell_count) {
                output(face) = 0.0;
                continue;
            }
            const Point3 delta = subtract(
                centroids[static_cast<size_t>(second_owner)],
                centroids[static_cast<size_t>(first_owner)]);
            const double delta_length = norm(delta);
            if (delta_length < 1e-30) {
                output(face) = 0.0;
                continue;
            }
            std::array<Point3, 4> vertices{};
            for (int slot = 0; slot < 4; ++slot) {
                vertices[static_cast<size_t>(slot)] = load_point(
                    point_view, face_view(face, slot), point_count);
            }
            const Point3 normal = cross(
                subtract(vertices[2], vertices[0]),
                subtract(vertices[3], vertices[1]));
            const double normal_length = norm(normal);
            if (normal_length < 1e-30) {
                output(face) = 0.0;
                continue;
            }
            double cosine = std::abs(dot(normal, delta))
                / (normal_length * delta_length);
            if (std::isnan(cosine)) {
                cosine = 1.0;
            } else if (cosine > 1.0) {
                cosine = 1.0;
            }
            output(face) = std::acos(cosine) * (180.0 / std::acos(-1.0));
        }
    }
    return angles;
}

}  // namespace

PYBIND11_MODULE(native_hex_quality, module)
{
    module.doc() = "C++ OpenFOAM-style quality primitives for hexahedral meshes";
    module.def(
        "local_front_backtrack_steps",
        &local_front_backtrack_steps,
        py::arg("outer_points").noconvert(),
        py::arg("outer_quads").noconvert(),
        py::arg("unit_inward_normals").noconvert(),
        py::arg("initial_step"),
        py::arg("geometry_tolerance"),
        py::arg("determinant_tolerance"),
        py::arg("maximum_iterations") = 32);
    module.def(
        "local_front_numeric_admission",
        &local_front_numeric_admission,
        py::arg("source_face_ids").noconvert(),
        py::arg("source_face_count"),
        py::arg("requested_step"),
        py::arg("minimum_clearance"));
    module.def(
        "certify_oriented_box",
        &certify_oriented_box,
        py::arg("points"),
        py::arg("faces"));
    module.def(
        "boundary_vertex_local_scales",
        &boundary_vertex_local_scales,
        py::arg("points"),
        py::arg("cell_faces"),
        py::arg("boundary_vertices"));
    module.def(
        "hex_quality_primitives",
        &hex_quality_primitives,
        py::arg("points"),
        py::arg("hexes"));
    module.def(
        "generic_cell_signed_volumes",
        &generic_cell_signed_volumes,
        py::arg("points"),
        py::arg("cell_faces"));
    module.def(
        "generic_cell_face_signs",
        &generic_cell_face_signs,
        py::arg("points"),
        py::arg("cell_faces"));
    module.def(
        "generic_side_metrics",
        &generic_side_metrics,
        py::arg("points"),
        py::arg("cell_faces"));
    module.def(
        "hex_face_nonorthogonality",
        &hex_face_nonorthogonality,
        py::arg("points"),
        py::arg("hexes"),
        py::arg("faces"),
        py::arg("owners"));
}
