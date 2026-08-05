#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <set>
#include <vector>

namespace autotessell_surface_bl_independent_audit {

using Point = std::array<double, 3>;
using Triangle = std::array<std::int64_t, 3>;
using LongPoint = std::array<long double, 3>;
using EdgeKey = std::pair<std::int64_t, std::int64_t>;

struct Summary {
    bool finite = true;
    std::int64_t invalid = 0;
    std::int64_t inverted = 0;
    std::int64_t duplicate = 0;
    std::int64_t non_manifold = 0;
    std::int64_t self_intersection = 0;
    long double max_skewness = 0.0L;
    long double max_aspect = 0.0L;
    long double max_non_orthogonality_degrees = 0.0L;
    long double p95_skewness = 0.0L;
    long double p99_skewness = 0.0L;
    long double p95_aspect = 0.0L;
    long double p99_aspect = 0.0L;
    long double p95_non_orthogonality_degrees = 0.0L;
    long double p99_non_orthogonality_degrees = 0.0L;
    long double source_plane_deviation = 0.0L;
};

inline LongPoint as_long(const Point& value) noexcept {
    return {static_cast<long double>(value[0]),
            static_cast<long double>(value[1]),
            static_cast<long double>(value[2])};
}

inline LongPoint sub(const LongPoint& a, const LongPoint& b) noexcept {
    return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}

inline LongPoint cross(const LongPoint& a, const LongPoint& b) noexcept {
    return {a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]};
}

inline long double dot(const LongPoint& a, const LongPoint& b) noexcept {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

inline long double length(const LongPoint& value) noexcept {
    return std::sqrt(dot(value, value));
}

inline long double angle_degrees(const LongPoint& a, const LongPoint& b) noexcept {
    const long double denominator = length(a) * length(b);
    if (!(denominator > 0.0L) || !std::isfinite(denominator))
        return std::numeric_limits<long double>::infinity();
    const long double cosine = std::clamp(dot(a, b) / denominator, -1.0L, 1.0L);
    return std::acos(cosine) * 180.0L / std::acos(-1.0L);
}

inline long double percentile(std::vector<long double> values, long double fraction) {
    if (values.empty()) return 0.0L;
    std::sort(values.begin(), values.end());
    const auto raw = static_cast<std::size_t>(
        std::ceil(fraction * static_cast<long double>(values.size())));
    const auto index = std::min(values.size() - 1U, raw == 0U ? 0U : raw - 1U);
    return values[index];
}

struct ProjectedSegment {
    std::int64_t first = -1;
    std::int64_t second = -1;
    std::int64_t face = -1;
    long double ax = 0.0L;
    long double ay = 0.0L;
    long double bx = 0.0L;
    long double by = 0.0L;
};

inline long double orient2(const long double ax, const long double ay,
                           const long double bx, const long double by,
                           const long double cx, const long double cy) noexcept {
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
}

inline bool projected_segment_intersects(
    const ProjectedSegment& left,
    const ProjectedSegment& right,
    const long double coordinate_tolerance,
    const long double orientation_tolerance) noexcept {
    const long double min_left_x = std::min(left.ax, left.bx) - coordinate_tolerance;
    const long double max_left_x = std::max(left.ax, left.bx) + coordinate_tolerance;
    const long double min_left_y = std::min(left.ay, left.by) - coordinate_tolerance;
    const long double max_left_y = std::max(left.ay, left.by) + coordinate_tolerance;
    const long double min_right_x = std::min(right.ax, right.bx) - coordinate_tolerance;
    const long double max_right_x = std::max(right.ax, right.bx) + coordinate_tolerance;
    const long double min_right_y = std::min(right.ay, right.by) - coordinate_tolerance;
    const long double max_right_y = std::max(right.ay, right.by) + coordinate_tolerance;
    if (max_left_x < min_right_x || max_right_x < min_left_x ||
        max_left_y < min_right_y || max_right_y < min_left_y) {
        return false;
    }
    const long double first = orient2(left.ax, left.ay, left.bx, left.by,
                                      right.ax, right.ay);
    const long double second = orient2(left.ax, left.ay, left.bx, left.by,
                                       right.bx, right.by);
    const long double third = orient2(right.ax, right.ay, right.bx, right.by,
                                      left.ax, left.ay);
    const long double fourth = orient2(right.ax, right.ay, right.bx, right.by,
                                       left.bx, left.by);
    const auto sign = [orientation_tolerance](const long double value) noexcept {
        if (value > orientation_tolerance) return 1;
        if (value < -orientation_tolerance) return -1;
        return 0;
    };
    const int first_sign = sign(first);
    const int second_sign = sign(second);
    const int third_sign = sign(third);
    const int fourth_sign = sign(fourth);
    if (first_sign * second_sign < 0 && third_sign * fourth_sign < 0) return true;
    const auto on_segment = [coordinate_tolerance](const long double ax,
                                                    const long double ay,
                                                    const long double bx,
                                                    const long double by,
                                                    const long double px,
                                                    const long double py) noexcept {
        return px >= std::min(ax, bx) - coordinate_tolerance &&
               px <= std::max(ax, bx) + coordinate_tolerance &&
               py >= std::min(ay, by) - coordinate_tolerance &&
               py <= std::max(ay, by) + coordinate_tolerance;
    };
    return (first_sign == 0 && on_segment(left.ax, left.ay, left.bx, left.by,
                                           right.ax, right.ay)) ||
           (second_sign == 0 && on_segment(left.ax, left.ay, left.bx, left.by,
                                            right.bx, right.by)) ||
           (third_sign == 0 && on_segment(right.ax, right.ay, right.bx, right.by,
                                           left.ax, left.ay)) ||
           (fourth_sign == 0 && on_segment(right.ax, right.ay, right.bx, right.by,
                                            left.bx, left.by));
}

inline std::int64_t count_projected_self_intersections(
    const std::vector<ProjectedSegment>& segments,
    const long double coordinate_tolerance,
    const long double orientation_tolerance) noexcept {
    std::int64_t intersections = 0;
    for (std::size_t left_index = 0; left_index < segments.size(); ++left_index) {
        for (std::size_t right_index = left_index + 1; right_index < segments.size();
             ++right_index) {
            const auto& left = segments[left_index];
            const auto& right = segments[right_index];
            if (left.face == right.face || left.first == right.first ||
                left.first == right.second || left.second == right.first ||
                left.second == right.second) {
                continue;
            }
            if (projected_segment_intersects(left, right, coordinate_tolerance,
                                             orientation_tolerance)) {
                ++intersections;
            }
        }
    }
    return intersections;
}

inline Summary audit_faces(
    const std::vector<Point>& points,
    const std::vector<Triangle>& faces,
    const Point& reference_point,
    const Point& reference_normal,
    long double area_tolerance = 1.0e-18L,
    long double plane_tolerance = 1.0e-12L) {
    Summary result;
    const LongPoint origin = as_long(reference_point);
    const LongPoint normal = as_long(reference_normal);
    const long double normal_length = length(normal);
    if (!(normal_length > 0.0L) || !std::isfinite(normal_length)) {
        result.finite = false;
        ++result.invalid;
        return result;
    }
    const LongPoint unit_normal{
        normal[0] / normal_length, normal[1] / normal_length, normal[2] / normal_length};
    std::set<std::array<std::int64_t, 3>> face_keys;
    std::map<EdgeKey, std::int64_t> edge_counts;
    std::vector<long double> skewness;
    std::vector<long double> aspects;
    std::vector<long double> non_orthogonality;
    std::vector<ProjectedSegment> projected_segments;
    projected_segments.reserve(faces.size() * 3U);
    const int projection_axis =
        std::abs(unit_normal[0]) >= std::abs(unit_normal[1]) &&
                std::abs(unit_normal[0]) >= std::abs(unit_normal[2])
            ? 0
            : (std::abs(unit_normal[1]) >= std::abs(unit_normal[2]) ? 1 : 2);
    long double coordinate_scale = 1.0L;
    for (const auto& point : points) {
        const LongPoint value = as_long(point);
        coordinate_scale = std::max(
            coordinate_scale,
            std::max({std::abs(value[0]), std::abs(value[1]), std::abs(value[2])}));
    }
    const long double coordinate_tolerance = 1.0e-15L * coordinate_scale;
    const long double orientation_tolerance =
        1.0e-18L * coordinate_scale * coordinate_scale;
    skewness.reserve(faces.size());
    aspects.reserve(faces.size());
    non_orthogonality.reserve(faces.size());

    for (const auto& triangle : faces) {
        if (triangle[0] < 0 || triangle[1] < 0 || triangle[2] < 0 ||
            triangle[0] >= static_cast<std::int64_t>(points.size()) ||
            triangle[1] >= static_cast<std::int64_t>(points.size()) ||
            triangle[2] >= static_cast<std::int64_t>(points.size()) ||
            triangle[0] == triangle[1] || triangle[1] == triangle[2] ||
            triangle[2] == triangle[0]) {
            ++result.invalid;
            continue;
        }
        auto key = triangle;
        std::sort(key.begin(), key.end());
        if (!face_keys.insert(key).second) ++result.duplicate;
        const LongPoint a = as_long(points[static_cast<std::size_t>(triangle[0])]);
        const LongPoint b = as_long(points[static_cast<std::size_t>(triangle[1])]);
        const LongPoint c = as_long(points[static_cast<std::size_t>(triangle[2])]);
        const long double signed_area = 0.5L * dot(cross(sub(b, a), sub(c, a)), unit_normal);
        const long double deviation = std::abs(dot(sub(a, origin), unit_normal));
        result.source_plane_deviation = std::max(result.source_plane_deviation, deviation);
        if (!std::isfinite(deviation) || deviation > plane_tolerance) ++result.invalid;
        if (!std::isfinite(signed_area) || signed_area <= area_tolerance)
            ++result.inverted;
        const long double ab = length(sub(b, a));
        const long double bc = length(sub(c, b));
        const long double ca = length(sub(a, c));
        const long double shortest = std::min({ab, bc, ca});
        const long double longest = std::max({ab, bc, ca});
        const long double minimum = std::max(shortest, 1.0e-30L);
        if (!(std::isfinite(longest) && std::isfinite(shortest) && shortest > 0.0L)) {
            ++result.invalid;
            continue;
        }
        const long double aspect = longest / minimum;
        const long double skew = (aspect - 1.0L) / aspect;
        const long double angle_error = std::max({
            std::abs(angle_degrees(sub(b, a), sub(c, a)) - 60.0L),
            std::abs(angle_degrees(sub(a, b), sub(c, b)) - 60.0L),
            std::abs(angle_degrees(sub(a, c), sub(b, c)) - 60.0L)});
        if (!std::isfinite(aspect) || !std::isfinite(skew) ||
            !std::isfinite(angle_error)) {
            result.finite = false;
            ++result.invalid;
            continue;
        }
        result.max_aspect = std::max(result.max_aspect, aspect);
        result.max_skewness = std::max(result.max_skewness, skew);
        result.max_non_orthogonality_degrees =
            std::max(result.max_non_orthogonality_degrees, angle_error);
        skewness.push_back(skew);
        aspects.push_back(aspect);
        non_orthogonality.push_back(angle_error);
        for (int i = 0; i < 3; ++i) {
            const auto first = triangle[static_cast<std::size_t>(i)];
            const auto second = triangle[static_cast<std::size_t>((i + 1) % 3)];
            edge_counts[{std::min(first, second), std::max(first, second)}] += 1;
            const LongPoint first_point =
                as_long(points[static_cast<std::size_t>(first)]);
            const LongPoint second_point =
                as_long(points[static_cast<std::size_t>(second)]);
            const int first_axis = (projection_axis + 1) % 3;
            const int second_axis = (projection_axis + 2) % 3;
            projected_segments.push_back(ProjectedSegment{
                first,
                second,
                static_cast<std::int64_t>(&triangle - faces.data()),
                first_point[first_axis],
                first_point[second_axis],
                second_point[first_axis],
                second_point[second_axis]});
        }
    }
    result.self_intersection = count_projected_self_intersections(
        projected_segments, coordinate_tolerance, orientation_tolerance);
    for (const auto& [edge, count] : edge_counts)
        if (count > 2) ++result.non_manifold;
    result.p95_skewness = percentile(skewness, 0.95L);
    result.p99_skewness = percentile(skewness, 0.99L);
    result.p95_aspect = percentile(aspects, 0.95L);
    result.p99_aspect = percentile(aspects, 0.99L);
    result.p95_non_orthogonality_degrees =
        percentile(non_orthogonality, 0.95L);
    result.p99_non_orthogonality_degrees =
        percentile(non_orthogonality, 0.99L);
    return result;
}

inline bool strict_maxima_pass(const Summary& value) noexcept {
    return value.finite && value.invalid == 0 && value.inverted == 0 &&
           value.duplicate == 0 && value.non_manifold == 0 &&
           value.self_intersection == 0 &&
           value.max_skewness <= 0.30L + 1.0e-12L &&
           value.max_aspect <= (10.0L / 7.0L) + 1.0e-12L &&
           value.max_non_orthogonality_degrees <= 30.0L + 1.0e-12L;
}

}  // namespace autotessell_surface_bl_independent_audit
