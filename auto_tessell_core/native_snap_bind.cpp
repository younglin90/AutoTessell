// Closest-point candidate reduction for native_hex surface snapping.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace py = pybind11;

namespace {

using Point3 = std::array<double, 3>;

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
    py::array_t<double> best_squared_distances({point_count});
    py::array_t<bool> valid({point_count});

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
}
