// C++23 candidate admission gate for Native Tet boundary-layer output.
//
// This module is deliberately candidate-only and default-off.  It owns the
// deterministic refusal order used before any transaction or release route:
// sealed policy/authority, collision, topology/volume, and quality.  It never
// repairs, publishes, or silently removes a layer.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <limits>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <map>
#include <set>
#include <stdexcept>
#include <iomanip>
#include <sstream>
#include <string>
#include "surface_bl_front_shared/brep_evidence_sha256.hpp"
#include <vector>
#include <utility>

namespace py = pybind11;
using Point = std::array<double, 3>;
using Triangle = std::array<std::int64_t, 3>;
using Tet = std::array<std::int64_t, 4>;

namespace {

constexpr double kEpsilon = 1.0e-12;
constexpr double kPi = 3.141592653589793238462643383279502884;

Point add(Point a, Point b) { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
Point sub(Point a, Point b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point scale(Point a, double value) { return {a[0] * value, a[1] * value, a[2] * value}; }
Point cross(Point a, Point b) {
    return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]};
}
double dot(Point a, Point b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double norm(Point a) { return std::sqrt(dot(a, a)); }
double distance(Point a, Point b) { return norm(sub(a, b)); }

double signed_volume6(const std::vector<Point>& points, const Tet& tet) {
    return dot(sub(points[static_cast<std::size_t>(tet[1])], points[static_cast<std::size_t>(tet[0])]),
               cross(sub(points[static_cast<std::size_t>(tet[2])], points[static_cast<std::size_t>(tet[0])]),
                     sub(points[static_cast<std::size_t>(tet[3])], points[static_cast<std::size_t>(tet[0])])));
}

std::vector<Point> load_points(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& array) {
    if (array.ndim() != 2 || array.shape(1) != 3) throw std::invalid_argument("points_must_be_Nx3");
    const auto input = array.unchecked<2>();
    std::vector<Point> points;
    points.reserve(static_cast<std::size_t>(input.shape(0)));
    for (py::ssize_t row = 0; row < input.shape(0); ++row) {
        Point point{};
        for (int axis = 0; axis < 3; ++axis) {
            point[static_cast<std::size_t>(axis)] = input(row, axis);
            if (!std::isfinite(point[static_cast<std::size_t>(axis)])) {
                throw std::invalid_argument("point_nonfinite");
            }
        }
        points.push_back(point);
    }
    return points;
}

std::vector<Tet> load_tets(
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& array,
    std::int64_t point_count) {
    if (array.ndim() != 2 || array.shape(1) != 4) throw std::invalid_argument("tets_must_be_Kx4");
    const auto input = array.unchecked<2>();
    std::vector<Tet> tets;
    tets.reserve(static_cast<std::size_t>(input.shape(0)));
    for (py::ssize_t row = 0; row < input.shape(0); ++row) {
        Tet tet{};
        for (int vertex = 0; vertex < 4; ++vertex) {
            tet[static_cast<std::size_t>(vertex)] = input(row, vertex);
            if (tet[static_cast<std::size_t>(vertex)] < 0 ||
                tet[static_cast<std::size_t>(vertex)] >= point_count) {
                throw std::invalid_argument("tet_vertex_out_of_range");
            }
        }
        if (std::set<std::int64_t>(tet.begin(), tet.end()).size() != 4) {
            throw std::invalid_argument("tet_degenerate");
        }
        tets.push_back(tet);
    }
    return tets;
}

std::vector<Triangle> load_triangles(
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& array,
    std::int64_t point_count) {
    if (array.ndim() != 2 || array.shape(1) != 3) throw std::invalid_argument("triangles_must_be_Mx3");
    const auto input = array.unchecked<2>();
    std::vector<Triangle> triangles;
    triangles.reserve(static_cast<std::size_t>(input.shape(0)));
    for (py::ssize_t row = 0; row < input.shape(0); ++row) {
        Triangle triangle{};
        for (int vertex = 0; vertex < 3; ++vertex) {
            triangle[static_cast<std::size_t>(vertex)] = input(row, vertex);
            if (triangle[static_cast<std::size_t>(vertex)] < 0 ||
                triangle[static_cast<std::size_t>(vertex)] >= point_count) {
                throw std::invalid_argument("collision_vertex_out_of_range");
            }
        }
        if (std::set<std::int64_t>(triangle.begin(), triangle.end()).size() != 3) {
            throw std::invalid_argument("collision_triangle_degenerate");
        }
        triangles.push_back(triangle);
    }
    return triangles;
}

bool is_hex64(const py::handle& value) {
    if (!py::isinstance<py::str>(value)) return false;
    const auto text = value.cast<std::string>();
    if (text.size() != 64) return false;
    for (const char character : text) {
        const bool digit = character >= '0' && character <= '9';
        const bool lower = character >= 'a' && character <= 'f';
        const bool upper = character >= 'A' && character <= 'F';
        if (!digit && !lower && !upper) return false;
    }
    return true;
}

struct Policy {
    double min_signed_volume = 0.0;
    double min_scaled_jacobian = 0.0;
    double max_skewness = 0.0;
    double max_non_orthogonality = 0.0;
    double max_aspect_ratio = 0.0;
    double p95_max_skewness = 0.0;
    double p95_max_non_orthogonality = 0.0;
    double p95_max_aspect_ratio = 0.0;
    bool has_p95 = false;
};

bool read_positive(const py::dict& dictionary, const char* key, double& destination) {
    if (!dictionary.contains(key)) return false;
    try {
        destination = dictionary[key].cast<double>();
    } catch (const py::cast_error&) {
        return false;
    }
    return std::isfinite(destination) && destination > 0.0;
}

bool read_nonnegative(const py::dict& dictionary, const char* key, double& destination) {
    if (!dictionary.contains(key)) return false;
    try {
        destination = dictionary[key].cast<double>();
    } catch (const py::cast_error&) {
        return false;
    }
    return std::isfinite(destination) && destination >= 0.0;
}

bool read_policy(const py::dict& dictionary, Policy& policy) {
    if (!read_positive(dictionary, "min_signed_volume", policy.min_signed_volume)) return false;
    if (!read_positive(dictionary, "min_scaled_jacobian", policy.min_scaled_jacobian)) return false;
    if (!read_nonnegative(dictionary, "max_skewness", policy.max_skewness)) return false;
    if (!read_nonnegative(dictionary, "max_non_orthogonality", policy.max_non_orthogonality)) return false;
    if (!read_positive(dictionary, "max_aspect_ratio", policy.max_aspect_ratio)) return false;
    if (!is_hex64(dictionary["policy_sha256"])) return false;

    const bool all_p95 = dictionary.contains("p95_max_skewness") &&
        dictionary.contains("p95_max_non_orthogonality") &&
        dictionary.contains("p95_max_aspect_ratio");
    if (all_p95) {
        if (!read_nonnegative(dictionary, "p95_max_skewness", policy.p95_max_skewness) ||
            !read_nonnegative(dictionary, "p95_max_non_orthogonality", policy.p95_max_non_orthogonality) ||
            !read_positive(dictionary, "p95_max_aspect_ratio", policy.p95_max_aspect_ratio)) {
            return false;
        }
        policy.has_p95 = true;
    }
    return true;
}

py::dict common_result() {
    py::dict result;
    result["runtime_route"] = "default_off";
    result["publication_eligible"] = false;
    result["candidate_discarded"] = true;
    result["rollback_required"] = true;
    return result;
}

py::dict refuse(const char* stage, const char* reason) {
    py::dict result = common_result();
    result["accepted"] = false;
    result["status"] = "candidate_refused";
    result["refusal_stage"] = stage;
    result["refusal_reason"] = reason;
    return result;
}

struct Aabb {
    Point low{};
    Point high{};
};

Aabb triangle_aabb(const std::vector<Point>& points, const Triangle& triangle) {
    Aabb box;
    box.low = points[static_cast<std::size_t>(triangle[0])];
    box.high = box.low;
    for (const auto index : triangle) {
        const Point point = points[static_cast<std::size_t>(index)];
        for (int axis = 0; axis < 3; ++axis) {
            box.low[static_cast<std::size_t>(axis)] =
                std::min(box.low[static_cast<std::size_t>(axis)], point[static_cast<std::size_t>(axis)]);
            box.high[static_cast<std::size_t>(axis)] =
                std::max(box.high[static_cast<std::size_t>(axis)], point[static_cast<std::size_t>(axis)]);
        }
    }
    return box;
}

bool aabb_overlap(const Aabb& first, const Aabb& second) {
    for (int axis = 0; axis < 3; ++axis) {
        if (first.high[static_cast<std::size_t>(axis)] + kEpsilon <
            second.low[static_cast<std::size_t>(axis)] ||
            second.high[static_cast<std::size_t>(axis)] + kEpsilon <
            first.low[static_cast<std::size_t>(axis)]) {
            return false;
        }
    }
    return true;
}

bool shares_vertex(const Triangle& first, const Triangle& second) {
    for (const auto left : first) for (const auto right : second) if (left == right) return true;
    return false;
}

int dominant_axis(Point normal) {
    const Point absolute = {std::abs(normal[0]), std::abs(normal[1]), std::abs(normal[2])};
    if (absolute[1] > absolute[0] && absolute[1] >= absolute[2]) return 1;
    if (absolute[2] > absolute[0] && absolute[2] > absolute[1]) return 2;
    return 0;
}

struct Point2 {
    double x = 0.0;
    double y = 0.0;
};

Point2 project(Point point, int dropped_axis) {
    if (dropped_axis == 0) return {point[1], point[2]};
    if (dropped_axis == 1) return {point[0], point[2]};
    return {point[0], point[1]};
}

double orient2(Point2 a, Point2 b, Point2 c) {
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

bool on_segment(Point2 a, Point2 b, Point2 point) {
    return std::abs(orient2(a, b, point)) <= kEpsilon &&
        point.x >= std::min(a.x, b.x) - kEpsilon && point.x <= std::max(a.x, b.x) + kEpsilon &&
        point.y >= std::min(a.y, b.y) - kEpsilon && point.y <= std::max(a.y, b.y) + kEpsilon;
}

bool segments_cross_2d(Point2 a, Point2 b, Point2 c, Point2 d) {
    const double first = orient2(a, b, c);
    const double second = orient2(a, b, d);
    const double third = orient2(c, d, a);
    const double fourth = orient2(c, d, b);
    if (((first > kEpsilon && second < -kEpsilon) || (first < -kEpsilon && second > kEpsilon)) &&
        ((third > kEpsilon && fourth < -kEpsilon) || (third < -kEpsilon && fourth > kEpsilon))) {
        return true;
    }
    return on_segment(a, b, c) || on_segment(a, b, d) || on_segment(c, d, a) || on_segment(c, d, b);
}

bool point_in_triangle_2d(Point2 point, const std::array<Point2, 3>& triangle) {
    const double first = orient2(triangle[0], triangle[1], point);
    const double second = orient2(triangle[1], triangle[2], point);
    const double third = orient2(triangle[2], triangle[0], point);
    const bool has_positive = first > kEpsilon || second > kEpsilon || third > kEpsilon;
    const bool has_negative = first < -kEpsilon || second < -kEpsilon || third < -kEpsilon;
    return !(has_positive && has_negative);
}

bool segment_triangle_intersection(Point start, Point end, Point a, Point b, Point c) {
    const Point direction = sub(end, start);
    const Point edge_one = sub(b, a);
    const Point edge_two = sub(c, a);
    const Point pvec = cross(direction, edge_two);
    const double determinant = dot(edge_one, pvec);
    if (std::abs(determinant) <= kEpsilon) return false;
    const double inverse = 1.0 / determinant;
    const Point tvec = sub(start, a);
    const double u = dot(tvec, pvec) * inverse;
    if (u < -kEpsilon || u > 1.0 + kEpsilon) return false;
    const Point qvec = cross(tvec, edge_one);
    const double v = dot(direction, qvec) * inverse;
    if (v < -kEpsilon || u + v > 1.0 + kEpsilon) return false;
    const double t = dot(edge_two, qvec) * inverse;
    return t >= -kEpsilon && t <= 1.0 + kEpsilon;
}

bool point_in_triangle_3d(Point point, Point a, Point b, Point c) {
    const Point normal = cross(sub(b, a), sub(c, a));
    const double normal_length = norm(normal);
    if (normal_length <= kEpsilon) return false;
    if (std::abs(dot(normal, sub(point, a))) > kEpsilon * normal_length) return false;
    const Point v0 = sub(b, a);
    const Point v1 = sub(c, a);
    const Point v2 = sub(point, a);
    const double dot00 = dot(v0, v0);
    const double dot01 = dot(v0, v1);
    const double dot02 = dot(v0, v2);
    const double dot11 = dot(v1, v1);
    const double dot12 = dot(v1, v2);
    const double denominator = dot00 * dot11 - dot01 * dot01;
    if (std::abs(denominator) <= kEpsilon) return false;
    const double inverse = 1.0 / denominator;
    const double u = (dot11 * dot02 - dot01 * dot12) * inverse;
    const double v = (dot00 * dot12 - dot01 * dot02) * inverse;
    return u >= -kEpsilon && v >= -kEpsilon && u + v <= 1.0 + kEpsilon;
}

bool coplanar_triangle_intersection(
    const std::vector<Point>& points, const Triangle& first, const Triangle& second) {
    const Point normal = cross(
        sub(points[static_cast<std::size_t>(first[1])], points[static_cast<std::size_t>(first[0])]),
        sub(points[static_cast<std::size_t>(first[2])], points[static_cast<std::size_t>(first[0])]));
    const int dropped = dominant_axis(normal);
    std::array<Point2, 3> left{};
    std::array<Point2, 3> right{};
    for (int vertex = 0; vertex < 3; ++vertex) {
        left[static_cast<std::size_t>(vertex)] =
            project(points[static_cast<std::size_t>(first[vertex])], dropped);
        right[static_cast<std::size_t>(vertex)] =
            project(points[static_cast<std::size_t>(second[vertex])], dropped);
    }
    for (int i = 0; i < 3; ++i) {
        const Point2 a = left[static_cast<std::size_t>(i)];
        const Point2 b = left[static_cast<std::size_t>((i + 1) % 3)];
        for (int j = 0; j < 3; ++j) {
            if (segments_cross_2d(a, b, right[static_cast<std::size_t>(j)],
                                   right[static_cast<std::size_t>((j + 1) % 3)])) return true;
        }
    }
    return point_in_triangle_2d(left[0], right) || point_in_triangle_2d(right[0], left);
}

bool triangles_intersect(
    const std::vector<Point>& points, const Triangle& first, const Triangle& second) {
    const Point first_normal = cross(
        sub(points[static_cast<std::size_t>(first[1])], points[static_cast<std::size_t>(first[0])]),
        sub(points[static_cast<std::size_t>(first[2])], points[static_cast<std::size_t>(first[0])]));
    const Point second_normal = cross(
        sub(points[static_cast<std::size_t>(second[1])], points[static_cast<std::size_t>(second[0])]),
        sub(points[static_cast<std::size_t>(second[2])], points[static_cast<std::size_t>(second[0])]));
    const Point normals_cross = cross(first_normal, second_normal);
    const bool coplanar = norm(normals_cross) <= kEpsilon * norm(first_normal) * norm(second_normal) &&
        std::abs(dot(first_normal,
            sub(points[static_cast<std::size_t>(second[0])],
                points[static_cast<std::size_t>(first[0])])) ) <=
            kEpsilon * norm(first_normal);
    if (coplanar) return coplanar_triangle_intersection(points, first, second);

    for (int edge = 0; edge < 3; ++edge) {
        const Point start = points[static_cast<std::size_t>(first[edge])];
        const Point end = points[static_cast<std::size_t>(first[(edge + 1) % 3])];
        if (segment_triangle_intersection(
                start, end,
                points[static_cast<std::size_t>(second[0])],
                points[static_cast<std::size_t>(second[1])],
                points[static_cast<std::size_t>(second[2])])) return true;
        const Point other_start = points[static_cast<std::size_t>(second[edge])];
        const Point other_end = points[static_cast<std::size_t>(second[(edge + 1) % 3])];
        if (segment_triangle_intersection(
                other_start, other_end,
                points[static_cast<std::size_t>(first[0])],
                points[static_cast<std::size_t>(first[1])],
                points[static_cast<std::size_t>(first[2])])) return true;
    }
    return point_in_triangle_3d(
        points[static_cast<std::size_t>(first[0])],
        points[static_cast<std::size_t>(second[0])],
        points[static_cast<std::size_t>(second[1])],
        points[static_cast<std::size_t>(second[2])]) ||
        point_in_triangle_3d(
        points[static_cast<std::size_t>(second[0])],
        points[static_cast<std::size_t>(first[0])],
        points[static_cast<std::size_t>(first[1])],
        points[static_cast<std::size_t>(first[2])]);
}

std::size_t percentile_index(std::size_t size) {
    if (size == 0) return 0;
    const auto index = static_cast<std::size_t>(std::ceil(0.95 * static_cast<double>(size))) - 1;
    return std::min(index, size - 1);
}

struct Quality {
    double max_skewness = 0.0;
    double p95_skewness = 0.0;
    double max_non_orthogonality = 0.0;
    double p95_non_orthogonality = 0.0;
    double max_aspect_ratio = 0.0;
    double p95_aspect_ratio = 0.0;
    double min_signed_volume = 0.0;
    double min_scaled_jacobian = 0.0;
};

Quality measure_quality(const std::vector<Point>& points, const std::vector<Tet>& tets) {
    Quality quality;
    std::vector<double> skewness;
    std::vector<double> non_orthogonality;
    std::vector<double> aspect_ratio;
    std::vector<double> scaled_jacobian;
    skewness.reserve(tets.size());
    non_orthogonality.reserve(tets.size());
    aspect_ratio.reserve(tets.size());
    scaled_jacobian.reserve(tets.size());
    quality.min_signed_volume = std::numeric_limits<double>::infinity();
    quality.min_scaled_jacobian = std::numeric_limits<double>::infinity();

    for (const auto& tet : tets) {
        const double volume = std::abs(signed_volume6(points, tet)) / 6.0;
        quality.min_signed_volume = std::min(quality.min_signed_volume, volume);
        std::array<double, 6> edges{};
        int cursor = 0;
        double minimum_edge = std::numeric_limits<double>::infinity();
        double maximum_edge = 0.0;
        for (int first = 0; first < 4; ++first) {
            for (int second = first + 1; second < 4; ++second) {
                const double edge = distance(
                    points[static_cast<std::size_t>(tet[first])],
                    points[static_cast<std::size_t>(tet[second])]);
                edges[static_cast<std::size_t>(cursor++)] = edge;
                minimum_edge = std::min(minimum_edge, edge);
                maximum_edge = std::max(maximum_edge, edge);
            }
        }
        const double aspect = maximum_edge / minimum_edge;
        const double skew = 1.0 - minimum_edge / maximum_edge;
        const double scaled = std::abs(signed_volume6(points, tet)) /
            std::pow(maximum_edge, 3.0);
        aspect_ratio.push_back(aspect);
        skewness.push_back(skew);
        scaled_jacobian.push_back(scaled);
        quality.min_scaled_jacobian = std::min(quality.min_scaled_jacobian, scaled);

        const Point center = scale(add(add(points[tet[0]], points[tet[1]]),
                                       add(points[tet[2]], points[tet[3]])), 0.25);
        double cell_max_angle = 0.0;
        for (int omitted = 0; omitted < 4; ++omitted) {
            std::array<int, 3> face{};
            int face_cursor = 0;
            for (int vertex = 0; vertex < 4; ++vertex) {
                if (vertex != omitted) face[static_cast<std::size_t>(face_cursor++)] = vertex;
            }
            const Point a = points[tet[face[0]]];
            const Point b = points[tet[face[1]]];
            const Point c = points[tet[face[2]]];
            const Point normal = cross(sub(b, a), sub(c, a));
            const Point face_center = scale(add(add(a, b), c), 1.0 / 3.0);
            const Point to_face = sub(face_center, center);
            const double alignment = std::abs(dot(normal, to_face)) / (norm(normal) * norm(to_face));
            cell_max_angle = std::max(cell_max_angle,
                std::acos(std::clamp(alignment, 0.0, 1.0)) * 180.0 / kPi);
        }
        non_orthogonality.push_back(cell_max_angle);
    }
    auto p95 = [](std::vector<double> values) {
        if (values.empty()) return 0.0;
        std::sort(values.begin(), values.end());
        return values[percentile_index(values.size())];
    };
    quality.max_skewness = *std::max_element(skewness.begin(), skewness.end());
    quality.p95_skewness = p95(skewness);
    quality.max_non_orthogonality = *std::max_element(non_orthogonality.begin(), non_orthogonality.end());
    quality.p95_non_orthogonality = p95(non_orthogonality);
    quality.max_aspect_ratio = *std::max_element(aspect_ratio.begin(), aspect_ratio.end());
    quality.p95_aspect_ratio = p95(aspect_ratio);
    return quality;
}

py::dict quality_dict(const Quality& quality) {
    py::dict result;
    result["max_skewness"] = quality.max_skewness;
    result["p95_skewness"] = quality.p95_skewness;
    result["max_non_orthogonality"] = quality.max_non_orthogonality;
    result["p95_non_orthogonality"] = quality.p95_non_orthogonality;
    result["max_aspect_ratio"] = quality.max_aspect_ratio;
    result["p95_aspect_ratio"] = quality.p95_aspect_ratio;
    result["min_signed_volume"] = quality.min_signed_volume;
    result["min_scaled_jacobian"] = quality.min_scaled_jacobian;
    return result;
}

py::dict admit(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tets_array,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& collision_triangles_array,
    const py::dict& policy,
    std::int64_t requested_layers,
    py::object base_points_object = py::none(),
    py::object ledger_object = py::none(),
    py::object authority_object = py::none()) {
    if (requested_layers < 0) throw std::invalid_argument("requested_layers_negative");
    if (requested_layers == 0) {
        if (base_points_object.is_none()) return refuse("identity", "base_points_required");
        const auto base_points = base_points_object.cast<py::array_t<double, py::array::c_style | py::array::forcecast>>();
        if (base_points.ndim() != points_array.ndim() ||
            base_points.ndim() != 2 || base_points.shape(1) != 3 ||
            base_points.shape(0) != points_array.shape(0) ||
            points_array.ndim() != 2 || points_array.shape(1) != 3) {
            return refuse("identity", "identity_shape_mismatch");
        }
        if (tets_array.ndim() != 2 || tets_array.shape(0) != 0 || collision_triangles_array.shape(0) != 0) {
            return refuse("identity", "bl0_must_have_no_tets_or_collision_scan");
        }
        if (std::memcmp(points_array.data(), base_points.data(), points_array.nbytes()) != 0) {
            return refuse("identity", "bl0_points_not_bitwise_identity");
        }
        py::dict result = common_result();
        result["accepted"] = true;
        result["status"] = "bl0_identity_admitted";
        result["candidate_discarded"] = false;
        result["rollback_required"] = false;
        result["writer_sidecar_emitted"] = false;
        result["collision_checked"] = false;
        result["full_ledger_required"] = false;
        result["quality"] = py::dict();
        return result;
    }

    Policy parsed_policy;
    if (!read_policy(policy, parsed_policy)) return refuse("policy", "sealed_quality_policy_invalid");
    if (authority_object.is_none() || !py::isinstance<py::dict>(authority_object)) {
        return refuse("authority", "authority_digests_required");
    }
    const py::dict authority = authority_object.cast<py::dict>();
    for (const char* key : {"source_sha256", "semantic_ledger_sha256"}) {
        if (!authority.contains(key) || !is_hex64(authority[key])) {
            return refuse("authority", "authority_digest_invalid");
        }
    }
    if (ledger_object.is_none() || !py::isinstance<py::dict>(ledger_object)) {
        return refuse("ledger", "full_ledger_v2_required");
    }
    const py::dict ledger = ledger_object.cast<py::dict>();
    if (!ledger.contains("schema") || ledger["schema"].cast<std::string>() !=
            "native-tet-bl-writer-ledger/v2") {
        return refuse("ledger", "full_ledger_v2_required");
    }
    if (!ledger.contains("writer_owned") || !ledger["writer_owned"].cast<bool>()) {
        return refuse("ledger", "full_ledger_inverse_required");
    }
    for (const char* key : {"source_sha256", "semantic_ledger_sha256", "bl_config_sha256",
                            "quality_policy_sha256", "graph_sha256", "artifact_tree_sha256"}) {
        if (!ledger.contains(key) || !is_hex64(ledger[key])) {
            return refuse("ledger", "full_ledger_digest_invalid");
        }
    }
    if (!ledger.contains("actual_layers") ||
        ledger["actual_layers"].cast<std::int64_t>() != requested_layers) {
        return refuse("ledger", "full_ledger_layer_count_mismatch");
    }
    if (ledger["source_sha256"].cast<std::string>() != authority["source_sha256"].cast<std::string>() ||
        ledger["semantic_ledger_sha256"].cast<std::string>() != authority["semantic_ledger_sha256"].cast<std::string>() ||
        ledger["quality_policy_sha256"].cast<std::string>() != policy["policy_sha256"].cast<std::string>()) {
        return refuse("ledger", "full_ledger_authority_digest_mismatch");
    }
    for (const char* key : {"source_faces", "boundary_children", "interface_children",
                            "edge_children", "prisms", "cells"}) {
        if (!ledger.contains(key) || !py::isinstance<py::list>(ledger[key])) {
            return refuse("ledger", "full_ledger_section_missing");
        }
    }
    if (!ledger.contains("inverse") || !py::isinstance<py::dict>(ledger["inverse"])) {
        return refuse("ledger", "full_ledger_inverse_required");
    }
    const py::dict inverse = ledger["inverse"].cast<py::dict>();
    for (const char* key : {"boundary_face_to_source", "tet_to_prism"}) {
        if (!inverse.contains(key) || !py::isinstance<py::dict>(inverse[key])) {
            return refuse("ledger", "full_ledger_inverse_required");
        }
    }

    const auto points = load_points(points_array);
    const auto tets = load_tets(tets_array, static_cast<std::int64_t>(points.size()));
    const auto collision_triangles = load_triangles(
        collision_triangles_array, static_cast<std::int64_t>(points.size()));
    if (tets.empty()) return refuse("topology", "positive_bl_candidate_has_no_cells");

    const auto boxes = [&]() {
        std::vector<Aabb> values;
        values.reserve(collision_triangles.size());
        for (const auto& triangle : collision_triangles) values.push_back(triangle_aabb(points, triangle));
        return values;
    }();
    for (std::size_t first = 0; first < collision_triangles.size(); ++first) {
        for (std::size_t second = first + 1; second < collision_triangles.size(); ++second) {
            if (shares_vertex(collision_triangles[first], collision_triangles[second])) continue;
            if (!aabb_overlap(boxes[first], boxes[second])) continue;
            if (triangles_intersect(points, collision_triangles[first], collision_triangles[second])) {
                return refuse("collision", "candidate_surface_self_intersection");
            }
        }
    }

    std::set<std::array<std::int64_t, 4>> unique_tets;
    std::map<std::array<std::int64_t, 3>, int> face_incidence;
    for (const auto& tet : tets) {
        const double signed_volume = signed_volume6(points, tet) / 6.0;
        if (!std::isfinite(signed_volume) || signed_volume <= 0.0) {
            return refuse("volume", "tet_signed_volume_nonpositive");
        }
        if (signed_volume < parsed_policy.min_signed_volume) {
            return refuse("volume", "tet_signed_volume_below_policy");
        }
        auto sorted_tet = tet;
        std::sort(sorted_tet.begin(), sorted_tet.end());
        if (!unique_tets.insert(sorted_tet).second) return refuse("topology", "duplicate_tet");
        for (int omitted = 0; omitted < 4; ++omitted) {
            std::array<std::int64_t, 3> face{};
            int cursor = 0;
            for (int vertex = 0; vertex < 4; ++vertex) {
                if (vertex != omitted) face[static_cast<std::size_t>(cursor++)] =
                    tet[static_cast<std::size_t>(vertex)];
            }
            std::sort(face.begin(), face.end());
            if (++face_incidence[face] > 2) return refuse("topology", "non_manifold_face");
        }
    }

    const Quality quality = measure_quality(points, tets);
    if (quality.min_scaled_jacobian < parsed_policy.min_scaled_jacobian ||
        quality.max_skewness > parsed_policy.max_skewness ||
        quality.max_non_orthogonality > parsed_policy.max_non_orthogonality ||
        quality.max_aspect_ratio > parsed_policy.max_aspect_ratio) {
        py::dict result = refuse("quality", "quality_policy_failed");
        result["quality"] = quality_dict(quality);
        return result;
    }
    if (parsed_policy.has_p95 &&
        (quality.p95_skewness > parsed_policy.p95_max_skewness ||
         quality.p95_non_orthogonality > parsed_policy.p95_max_non_orthogonality ||
         quality.p95_aspect_ratio > parsed_policy.p95_max_aspect_ratio)) {
        py::dict result = refuse("quality", "quality_p95_policy_failed");
        result["quality"] = quality_dict(quality);
        return result;
    }

    py::dict result;
    result["runtime_route"] = "default_off";
    result["publication_eligible"] = false;
    result["candidate_discarded"] = false;
    result["rollback_required"] = false;
    result["accepted"] = true;
    result["status"] = "candidate_admitted";
    result["collision_checked"] = true;
    result["full_ledger_admitted"] = true;
    result["cell_count"] = tets.size();
    result["quality"] = quality_dict(quality);
    return result;
}
#include "native_tet_writer_outer_admission.hpp"

}  // namespace

PYBIND11_MODULE(native_tet_bl_admission, module) {
    module.doc() = "C++23 Native Tet BL candidate admission; route and publication disabled.";
    module.def(
        "admit", &admit,
        py::arg("points"), py::arg("tets"), py::arg("collision_triangles"),
        py::arg("policy"), py::arg("requested_layers"),
        py::arg("base_points") = py::none(),
        py::arg("ledger") = py::none(),
        py::arg("authority") = py::none());
    module.def("canonical_input_parameters_sha256", &native_tet_writer_outer::input_parameters_sha256,
        py::arg("input_parameters"));
    module.def("admit_writer_owned_outer_surface", &native_tet_writer_outer::admit_writer_owned_outer_surface,
        py::arg("points"), py::arg("tets"), py::arg("policy"), py::arg("requested_layers"),
        py::arg("ledger"), py::arg("authority"));
}

