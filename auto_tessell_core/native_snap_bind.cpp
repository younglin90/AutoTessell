// Closest-point candidate reduction for native_hex surface snapping.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <numbers>
#include <stdexcept>
#include <utility>
#include <vector>

namespace py = pybind11;

namespace {

using Point3 = std::array<double, 3>;

struct EdgeRecord {
    std::int64_t first;
    std::int64_t second;
    py::ssize_t face;
    py::ssize_t ordinal;
};

struct FeatureEdge {
    std::int64_t first;
    std::int64_t second;
    double weight;
};

constexpr std::array<std::array<py::ssize_t, 2>, 3> triangle_edges {{
    {{0, 1}},
    {{1, 2}},
    {{2, 0}},
}};

Point3 subtract(const Point3& lhs, const Point3& rhs)
{
    return {lhs[0] - rhs[0], lhs[1] - rhs[1], lhs[2] - rhs[2]};
}

Point3 add_scaled(const Point3& base, const Point3& direction, double scale)
{
    return {
        base[0] + direction[0] * scale,
        base[1] + direction[1] * scale,
        base[2] + direction[2] * scale,
    };
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

Point3 closest_point_on_triangle(
    const Point3& point,
    const Point3& first,
    const Point3& second,
    const Point3& third)
{
    const Point3 ab = subtract(second, first);
    const Point3 ac = subtract(third, first);
    const Point3 ap = subtract(point, first);
    const double d1 = dot(ab, ap);
    const double d2 = dot(ac, ap);
    if (d1 <= 0.0 && d2 <= 0.0) {
        return first;
    }

    const Point3 bp = subtract(point, second);
    const double d3 = dot(ab, bp);
    const double d4 = dot(ac, bp);
    if (d3 >= 0.0 && d4 <= d3) {
        return second;
    }

    const double vc = d1 * d4 - d3 * d2;
    if (vc <= 0.0 && d1 >= 0.0 && d3 <= 0.0) {
        return add_scaled(first, ab, d1 / (d1 - d3));
    }

    const Point3 cp = subtract(point, third);
    const double d5 = dot(ab, cp);
    const double d6 = dot(ac, cp);
    if (d6 >= 0.0 && d5 <= d6) {
        return third;
    }

    const double vb = d5 * d2 - d1 * d6;
    if (vb <= 0.0 && d2 >= 0.0 && d6 <= 0.0) {
        return add_scaled(first, ac, d2 / (d2 - d6));
    }

    const double va = d3 * d6 - d5 * d4;
    if (va <= 0.0 && (d4 - d3) >= 0.0 && (d5 - d6) >= 0.0) {
        const Point3 bc = subtract(third, second);
        const double weight = (d4 - d3) / ((d4 - d3) + (d5 - d6));
        return add_scaled(second, bc, weight);
    }

    const double denominator = 1.0 / (va + vb + vc);
    const double v = vb * denominator;
    const double w = vc * denominator;
    return {
        first[0] + ab[0] * v + ac[0] * w,
        first[1] + ab[1] * v + ac[1] * w,
        first[2] + ab[2] * v + ac[2] * w,
    };
}

template <typename View>
Point3 load_point(const View& view, py::ssize_t row)
{
    return {view(row, 0), view(row, 1), view(row, 2)};
}

py::tuple closest_triangle_candidates(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    py::array_t<double, py::array::c_style | py::array::forcecast> triangle_a,
    py::array_t<double, py::array::c_style | py::array::forcecast> triangle_b,
    py::array_t<double, py::array::c_style | py::array::forcecast> triangle_c,
    py::array_t<long long, py::array::c_style | py::array::forcecast> candidates)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (triangle_a.ndim() != 2 || triangle_a.shape(1) != 3
        || triangle_b.ndim() != 2 || triangle_b.shape(1) != 3
        || triangle_c.ndim() != 2 || triangle_c.shape(1) != 3) {
        throw std::invalid_argument("triangle arrays must have shape (M, 3)");
    }
    if (triangle_a.shape(0) != triangle_b.shape(0)
        || triangle_a.shape(0) != triangle_c.shape(0)) {
        throw std::invalid_argument("triangle arrays must have matching lengths");
    }
    if (candidates.ndim() != 2 || candidates.shape(0) != points.shape(0)) {
        throw std::invalid_argument("candidates must have shape (N, K)");
    }

    const py::ssize_t point_count = points.shape(0);
    const py::ssize_t triangle_count = triangle_a.shape(0);
    const py::ssize_t candidate_count = candidates.shape(1);
    py::array_t<double> best_points({point_count, py::ssize_t{3}});
    py::array_t<double> best_squared_distances(py::array::ShapeContainer{point_count});
    py::array_t<bool> valid(py::array::ShapeContainer{point_count});

    const auto point_view = points.unchecked<2>();
    const auto first_view = triangle_a.unchecked<2>();
    const auto second_view = triangle_b.unchecked<2>();
    const auto third_view = triangle_c.unchecked<2>();
    const auto candidate_view = candidates.unchecked<2>();
    auto output_points = best_points.mutable_unchecked<2>();
    auto output_distances = best_squared_distances.mutable_unchecked<1>();
    auto output_valid = valid.mutable_unchecked<1>();

    {
        py::gil_scoped_release release;
        for (py::ssize_t point_index = 0; point_index < point_count; ++point_index) {
            const Point3 point = load_point(point_view, point_index);
            Point3 best_point = point;
            double best_distance = std::numeric_limits<double>::infinity();
            bool found = false;
            for (py::ssize_t slot = 0; slot < candidate_count; ++slot) {
                long long triangle_index = candidate_view(point_index, slot);
                if (triangle_index >= triangle_count) {
                    continue;
                }
                if (triangle_index < 0) {
                    if (triangle_index < -triangle_count) {
                        throw py::index_error("triangle index is out of bounds");
                    }
                    triangle_index += triangle_count;
                }
                const auto row = static_cast<py::ssize_t>(triangle_index);
                const Point3 candidate_point = closest_point_on_triangle(
                    point,
                    load_point(first_view, row),
                    load_point(second_view, row),
                    load_point(third_view, row));
                const double dx = candidate_point[0] - point[0];
                const double dy = candidate_point[1] - point[1];
                const double dz = candidate_point[2] - point[2];
                const double squared_distance = dx * dx + dy * dy + dz * dz;
                if (squared_distance < best_distance) {
                    best_distance = squared_distance;
                    best_point = candidate_point;
                    found = true;
                }
            }
            output_points(point_index, 0) = best_point[0];
            output_points(point_index, 1) = best_point[1];
            output_points(point_index, 2) = best_point[2];
            output_distances(point_index) = best_distance;
            output_valid(point_index) = found;
        }
    }

    return py::make_tuple(best_points, best_squared_distances, valid);
}

std::pair<Point3, double> closest_point_on_segment(
    const Point3& point, const Point3& first, const Point3& second)
{
    const Point3 direction = subtract(second, first);
    const double length_squared = dot(direction, direction);
    if (length_squared < 1e-30) {
        const Point3 delta = subtract(point, first);
        return {first, std::sqrt(dot(delta, delta))};
    }
    const Point3 offset = subtract(point, first);
    double parameter = dot(offset, direction) / length_squared;
    if (parameter < 0.0) {
        parameter = 0.0;
    } else if (parameter > 1.0) {
        parameter = 1.0;
    }
    const Point3 candidate = add_scaled(first, direction, parameter);
    const Point3 delta = subtract(point, candidate);
    return {candidate, std::sqrt(dot(delta, delta))};
}

py::tuple closest_segment_candidates(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    py::array_t<double, py::array::c_style | py::array::forcecast> segment_a,
    py::array_t<double, py::array::c_style | py::array::forcecast> segment_b,
    py::array_t<long long, py::array::c_style | py::array::forcecast> candidates)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (segment_a.ndim() != 2 || segment_a.shape(1) != 3
        || segment_b.ndim() != 2 || segment_b.shape(1) != 3) {
        throw std::invalid_argument("segment arrays must have shape (M, 3)");
    }
    if (segment_a.shape(0) != segment_b.shape(0)) {
        throw std::invalid_argument("segment arrays must have matching lengths");
    }
    if (candidates.ndim() != 2 || candidates.shape(0) != points.shape(0)) {
        throw std::invalid_argument("candidates must have shape (N, K)");
    }

    const py::ssize_t point_count = points.shape(0);
    const py::ssize_t segment_count = segment_a.shape(0);
    const py::ssize_t candidate_count = candidates.shape(1);
    py::array_t<double> best_points({point_count, py::ssize_t{3}});
    py::array_t<double> best_distances(py::array::ShapeContainer{point_count});
    py::array_t<long long> best_segments(py::array::ShapeContainer{point_count});
    py::array_t<bool> valid(py::array::ShapeContainer{point_count});

    const auto point_view = points.unchecked<2>();
    const auto first_view = segment_a.unchecked<2>();
    const auto second_view = segment_b.unchecked<2>();
    const auto candidate_view = candidates.unchecked<2>();
    auto output_points = best_points.mutable_unchecked<2>();
    auto output_distances = best_distances.mutable_unchecked<1>();
    auto output_segments = best_segments.mutable_unchecked<1>();
    auto output_valid = valid.mutable_unchecked<1>();

    {
        py::gil_scoped_release release;
        for (py::ssize_t point_index = 0; point_index < point_count; ++point_index) {
            const Point3 point = load_point(point_view, point_index);
            Point3 best_point = point;
            double best_distance = std::numeric_limits<double>::infinity();
            long long best_segment = -1;
            for (py::ssize_t slot = 0; slot < candidate_count; ++slot) {
                long long segment_index = candidate_view(point_index, slot);
                if (segment_index >= segment_count) {
                    continue;
                }
                if (segment_index < 0) {
                    if (segment_index < -segment_count) {
                        throw py::index_error("segment index is out of bounds");
                    }
                    segment_index += segment_count;
                }
                const auto row = static_cast<py::ssize_t>(segment_index);
                const auto [candidate_point, distance] = closest_point_on_segment(
                    point, load_point(first_view, row), load_point(second_view, row));
                if (distance < best_distance) {
                    best_distance = distance;
                    best_point = candidate_point;
                    best_segment = segment_index;
                }
            }
            output_points(point_index, 0) = best_point[0];
            output_points(point_index, 1) = best_point[1];
            output_points(point_index, 2) = best_point[2];
            output_distances(point_index) = best_distance;
            output_segments(point_index) = best_segment;
            output_valid(point_index) = best_segment >= 0;
        }
    }

    return py::make_tuple(best_points, best_distances, best_segments, valid);
}

py::tuple extract_feature_edges(
    const py::array& vertices,
    const py::array& faces,
    double feature_angle_deg)
{
    if (!vertices.dtype().is(py::dtype::of<double>())
        || (vertices.flags() & py::array::c_style) == 0) {
        throw py::type_error("vertices must have exact float64 dtype and C-contiguous layout");
    }
    if (!faces.dtype().is(py::dtype::of<long long>())
        || (faces.flags() & py::array::c_style) == 0) {
        throw py::type_error("faces must have exact int64 dtype and C-contiguous layout");
    }
    if (vertices.ndim() != 2 || vertices.shape(1) != 3) {
        throw std::invalid_argument("vertices must be a C-contiguous float64 array of shape (V, 3)");
    }
    if (faces.ndim() != 2 || faces.shape(1) != 3) {
        throw std::invalid_argument("faces must be a C-contiguous int64 array of shape (F, 3)");
    }
    if (!std::isfinite(feature_angle_deg)) {
        throw std::invalid_argument("feature_angle_deg must be finite");
    }

    const py::ssize_t vertex_count = vertices.shape(0);
    const py::ssize_t face_count = faces.shape(0);
    constexpr py::ssize_t edges_per_face = 3;
    if (face_count > std::numeric_limits<py::ssize_t>::max() / edges_per_face) {
        throw std::overflow_error("face count exceeds the feature-edge index range");
    }

    const auto vertex_view = vertices.unchecked<double, 2>();
    const auto face_view = faces.unchecked<long long, 2>();
    for (py::ssize_t vertex = 0; vertex < vertex_count; ++vertex) {
        for (py::ssize_t axis = 0; axis < 3; ++axis) {
            if (!std::isfinite(vertex_view(vertex, axis))) {
                throw std::invalid_argument("vertices must contain only finite coordinates");
            }
        }
    }
    for (py::ssize_t face = 0; face < face_count; ++face) {
        for (py::ssize_t corner = 0; corner < 3; ++corner) {
            const long long vertex = face_view(face, corner);
            if (vertex < 0 || vertex >= vertex_count) {
                throw py::index_error("face vertex index is out of bounds");
            }
        }
    }

    const auto edge_count = static_cast<std::size_t>(face_count * edges_per_face);
    std::vector<EdgeRecord> edge_records;
    std::vector<Point3> normals(static_cast<std::size_t>(face_count));
    std::vector<FeatureEdge> feature_edges;
    if (edge_count > edge_records.max_size()) {
        throw std::overflow_error("feature-edge working set exceeds addressable memory");
    }
    edge_records.reserve(edge_count);

    {
        py::gil_scoped_release release;

        for (py::ssize_t face = 0; face < face_count; ++face) {
            const auto first_index = static_cast<py::ssize_t>(face_view(face, 0));
            const auto second_index = static_cast<py::ssize_t>(face_view(face, 1));
            const auto third_index = static_cast<py::ssize_t>(face_view(face, 2));
            const Point3 first = load_point(vertex_view, first_index);
            const Point3 second = load_point(vertex_view, second_index);
            const Point3 third = load_point(vertex_view, third_index);
            Point3 normal = cross(subtract(second, first), subtract(third, first));
            const double normal_length = std::sqrt(dot(normal, normal));
            if (normal_length > 1e-30) {
                normal[0] /= normal_length;
                normal[1] /= normal_length;
                normal[2] /= normal_length;
            } else {
                normal = {0.0, 0.0, 0.0};
            }
            normals[static_cast<std::size_t>(face)] = normal;

            for (py::ssize_t local_edge = 0; local_edge < edges_per_face; ++local_edge) {
                const auto& edge = triangle_edges[static_cast<std::size_t>(local_edge)];
                auto edge_first = static_cast<std::int64_t>(face_view(face, edge[0]));
                auto edge_second = static_cast<std::int64_t>(face_view(face, edge[1]));
                if (edge_second < edge_first) {
                    std::swap(edge_first, edge_second);
                }
                edge_records.push_back(
                    {edge_first, edge_second, face, face * edges_per_face + local_edge});
            }
        }

        std::sort(
            edge_records.begin(),
            edge_records.end(),
            [](const EdgeRecord& lhs, const EdgeRecord& rhs) {
                if (lhs.first != rhs.first) {
                    return lhs.first < rhs.first;
                }
                if (lhs.second != rhs.second) {
                    return lhs.second < rhs.second;
                }
                return lhs.ordinal < rhs.ordinal;
            });

        const double radians = feature_angle_deg * std::numbers::pi_v<double> / 180.0;
        const double cosine_threshold = std::cos(radians);
        const auto feature_weight = [&](std::size_t run_start, std::size_t owner_count) {
            if (owner_count == 1) {
                return 1.5;
            }
            if (owner_count != 2) {
                return 0.0;
            }
            const Point3& first_normal =
                normals[static_cast<std::size_t>(edge_records[run_start].face)];
            const Point3& second_normal =
                normals[static_cast<std::size_t>(edge_records[run_start + 1].face)];
            const double cosine = std::clamp(dot(first_normal, second_normal), -1.0, 1.0);
            return cosine < cosine_threshold ? 1.0 + (1.0 - cosine) : 0.0;
        };

        std::size_t feature_count = 0;
        std::size_t run_start = 0;
        while (run_start < edge_records.size()) {
            std::size_t run_end = run_start + 1;
            while (run_end < edge_records.size()
                   && edge_records[run_end].first == edge_records[run_start].first
                   && edge_records[run_end].second == edge_records[run_start].second) {
                ++run_end;
            }
            feature_count += feature_weight(run_start, run_end - run_start) > 0.0 ? 1 : 0;
            run_start = run_end;
        }

        feature_edges.reserve(feature_count);
        run_start = 0;
        while (run_start < edge_records.size()) {
            std::size_t run_end = run_start + 1;
            while (run_end < edge_records.size()
                   && edge_records[run_end].first == edge_records[run_start].first
                   && edge_records[run_end].second == edge_records[run_start].second) {
                ++run_end;
            }
            const std::size_t owner_count = run_end - run_start;
            const double weight = feature_weight(run_start, owner_count);
            if (weight > 0.0) {
                feature_edges.push_back(
                    {edge_records[run_start].first, edge_records[run_start].second, weight});
            }
            run_start = run_end;
        }
    }

    if (feature_edges.size()
        > static_cast<std::size_t>(std::numeric_limits<py::ssize_t>::max())) {
        throw std::overflow_error("feature-edge output exceeds the NumPy index range");
    }
    const auto segment_count = static_cast<py::ssize_t>(feature_edges.size());
    py::array_t<double> segments({segment_count, py::ssize_t {2}, py::ssize_t {3}});
    py::array_t<double> weights(py::array::ShapeContainer{segment_count});
    auto segment_output = segments.mutable_unchecked<3>();
    auto weight_output = weights.mutable_unchecked<1>();
    for (py::ssize_t segment = 0; segment < segment_count; ++segment) {
        const FeatureEdge& source = feature_edges[static_cast<std::size_t>(segment)];
        const Point3 first = load_point(vertex_view, static_cast<py::ssize_t>(source.first));
        const Point3 second = load_point(vertex_view, static_cast<py::ssize_t>(source.second));
        for (py::ssize_t axis = 0; axis < 3; ++axis) {
            segment_output(segment, 0, axis) = first[static_cast<std::size_t>(axis)];
            segment_output(segment, 1, axis) = second[static_cast<std::size_t>(axis)];
        }
        weight_output(segment) = source.weight;
    }
    return py::make_tuple(segments, weights);
}

}  // namespace

PYBIND11_MODULE(native_snap, module)
{
    module.doc() = "C++ closest-point candidate kernels for AutoTessell snapping";
    module.def(
        "closest_triangle_candidates",
        &closest_triangle_candidates,
        py::arg("points"),
        py::arg("triangle_a"),
        py::arg("triangle_b"),
        py::arg("triangle_c"),
        py::arg("candidates"));
    module.def(
        "closest_segment_candidates",
        &closest_segment_candidates,
        py::arg("points"),
        py::arg("segment_a"),
        py::arg("segment_b"),
        py::arg("candidates"));
    module.def(
        "extract_feature_edges",
        &extract_feature_edges,
        py::arg("vertices"),
        py::arg("faces"),
        py::arg("feature_angle_deg"));
}
