#pragma once

#include "native_tri_authority_source_certificate.hpp"
#include "surface_bl_front_shared/long_double_quality_audit.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace autotessell_native_tri_planar_template {

using Point = autotessell_native_tri_authority::Point;
using Triangle = autotessell_native_tri_authority::Triangle;

struct Quality {
    double skewness = 0.0;
    double aspect = 0.0;
    double wall_nonorthogonality = 0.0;
    double angle_nonorthogonality = 0.0;
    double signed_area = 0.0;
    double physical_aspect = 0.0;
};

struct PairQuality {
    bool valid = false;
    Quality first{};
    Quality second{};
    double max_skewness = 0.0;
    double max_aspect = 0.0;
    double max_wall_nonorthogonality = 0.0;
    double max_angle_nonorthogonality = 0.0;
    double min_signed_area = std::numeric_limits<double>::infinity();
    int diagonal = 0;
};

struct Topology {
    std::int64_t invalid = 0;
    std::int64_t degenerate = 0;
    std::int64_t inverted = 0;
    std::int64_t duplicate = 0;
    std::int64_t open_edges = 0;
    std::int64_t non_manifold = 0;
    std::int64_t self_intersection = 0;
};

struct Collision {
    std::int64_t broad_phase_pairs = 0;
    std::int64_t narrow_phase_hits = 0;
    std::int64_t allowed_shared_contacts = 0;
    std::int64_t rejected_contacts = 0;
};

inline Point add(const Point& a, const Point& b) noexcept {
    return {a[0] + b[0], a[1] + b[1], a[2] + b[2]};
}

inline Point sub(const Point& a, const Point& b) noexcept {
    return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}

inline Point mul(const Point& a, const double value) noexcept {
    return {a[0] * value, a[1] * value, a[2] * value};
}

inline Point unit(const Point& value, const double tolerance = 1.0e-14) {
    const double length = autotessell_native_tri_authority::norm(value);
    if (!(length > tolerance) || !std::isfinite(length))
        throw std::runtime_error("tri_planar_template_degenerate_vector");
    return mul(value, 1.0 / length);
}

inline double signed_area(const Point& a, const Point& b, const Point& c,
                          const Point& normal) noexcept {
    return 0.5 * autotessell_native_tri_authority::dot(
        autotessell_native_tri_authority::cross(sub(b, a), sub(c, a)), normal);
}

inline double angle_degrees(const Point& a, const Point& b) noexcept {
    const double denominator = autotessell_native_tri_authority::norm(a) *
                               autotessell_native_tri_authority::norm(b);
    if (!(denominator > 0.0) || !std::isfinite(denominator))
        return std::numeric_limits<double>::infinity();
    const double cosine = std::clamp(
        autotessell_native_tri_authority::dot(a, b) / denominator, -1.0, 1.0);
    return std::acos(cosine) * 180.0 / std::acos(-1.0);
}

inline Quality triangle_quality(const Point& a, const Point& b, const Point& c,
                                const Point& normal) {
    const Point ab = sub(b, a);
    const Point bc = sub(c, b);
    const Point ca = sub(a, c);
    const double lengths[3] = {
        autotessell_native_tri_authority::norm(ab),
        autotessell_native_tri_authority::norm(bc),
        autotessell_native_tri_authority::norm(ca)};
    const double shortest = std::min({lengths[0], lengths[1], lengths[2]});
    const double longest = std::max({lengths[0], lengths[1], lengths[2]});
    if (!(shortest > 1.0e-14) || !std::isfinite(longest))
        throw std::runtime_error("tri_planar_template_degenerate_triangle");
    const double aspect = longest / shortest;
    const double area = signed_area(a, b, c, normal);
    const double angle_error = std::max({
        std::abs(angle_degrees(ab, sub(c, a)) - 60.0),
        std::abs(angle_degrees(sub(a, b), sub(c, b)) - 60.0),
        std::abs(angle_degrees(sub(a, c), sub(b, c)) - 60.0)});
    Quality result{(aspect - 1.0) / aspect, aspect, 0.0, angle_error, area};
    result.physical_aspect = aspect;
    return result;
}

struct MetricQuality {
    double skewness = 0.0;
    double aspect = 0.0;
    double angle_nonorthogonality = 0.0;
};

inline MetricQuality metric_triangle_quality(
    const Point& a, const Point& b, const Point& c,
    const Point& tangent, const Point& co_normal, const double normal_scale) {
    const auto transform_length = [&](const Point& value) {
        const double tangent_component = autotessell_native_tri_authority::dot(value, tangent);
        const double normal_component = autotessell_native_tri_authority::dot(value, co_normal);
        return std::sqrt(tangent_component * tangent_component +
                         normal_component * normal_component * normal_scale * normal_scale);
    };
    const Point ab = sub(b, a), bc = sub(c, b), ca = sub(a, c);
    const double lengths[3] = {
        transform_length(ab), transform_length(bc), transform_length(ca)};
    const double shortest = std::min({lengths[0], lengths[1], lengths[2]});
    const double longest = std::max({lengths[0], lengths[1], lengths[2]});
    if (!(shortest > 1.0e-14) || !std::isfinite(longest))
        throw std::runtime_error("tri_planar_template_metric_degenerate");
    const auto metric_dot = [&](const Point& left, const Point& right) {
        return autotessell_native_tri_authority::dot(left, tangent) * autotessell_native_tri_authority::dot(right, tangent) +
               autotessell_native_tri_authority::dot(left, co_normal) * autotessell_native_tri_authority::dot(right, co_normal) *
                   normal_scale * normal_scale;
    };
    const auto metric_angle = [&](const Point& left, const Point& right) {
        const double denominator = transform_length(left) * transform_length(right);
        if (!(denominator > 0.0) || !std::isfinite(denominator))
            return std::numeric_limits<double>::infinity();
        return std::acos(std::clamp(metric_dot(left, right) / denominator, -1.0, 1.0)) *
               180.0 / std::acos(-1.0);
    };
    const double aspect = longest / shortest;
    return {(aspect - 1.0) / aspect, aspect,
            std::max({std::abs(metric_angle(ab, sub(c, a)) - 60.0),
                      std::abs(metric_angle(sub(a, b), bc) - 60.0),
                      std::abs(metric_angle(sub(a, c), sub(b, c)) - 60.0)})};
}

inline double wall_nonorthogonality(
    const Point& lower_a, const Point& lower_b,
    const Point& upper_a, const Point& upper_b,
    const Point& normal) {
    const Point lower_mid = mul(add(lower_a, lower_b), 0.5);
    const Point upper_mid = mul(add(upper_a, upper_b), 0.5);
    const Point direction = sub(upper_mid, lower_mid);
    const Point tangent = unit(sub(lower_b, lower_a));
    const Point expected = unit(autotessell_native_tri_authority::cross(normal, tangent));
    const double degrees = angle_degrees(direction, expected);
    return std::isfinite(degrees) ? degrees : std::numeric_limits<double>::infinity();
}

inline PairQuality evaluate_pair(
    const Triangle& first, const Triangle& second,
    const std::vector<Point>& points,
    const std::array<std::int64_t, 3>& lower,
    const std::array<std::int64_t, 3>& upper,
    const std::int64_t edge_index,
    const Point& normal,
    const double epsilon) {
    PairQuality result;
    result.diagonal = static_cast<int>(edge_index);
    const auto point = [&](const std::int64_t id) -> const Point& {
        return points.at(static_cast<std::size_t>(id));
    };
    result.first = triangle_quality(point(first[0]), point(first[1]), point(first[2]), normal);
    result.second = triangle_quality(point(second[0]), point(second[1]), point(second[2]), normal);
    const std::size_t i = static_cast<std::size_t>(edge_index);
    const std::size_t j = (i + 1U) % 3U;
    const double wall = wall_nonorthogonality(
        point(lower[i]), point(lower[j]), point(upper[i]), point(upper[j]), normal);
    const Point tangent = unit(sub(point(lower[j]), point(lower[i])));
    const Point co_normal = unit(autotessell_native_tri_authority::cross(normal, tangent));
    const Point displacement = sub(
        mul(add(point(upper[i]), point(upper[j])), 0.5),
        mul(add(point(lower[i]), point(lower[j])), 0.5));
    const double thickness = autotessell_native_tri_authority::dot(displacement, co_normal);
    if (!(thickness > epsilon) || !std::isfinite(thickness))
        throw std::runtime_error("tri_planar_template_metric_thickness_invalid");
    const double normal_scale = autotessell_native_tri_authority::norm(
        sub(point(lower[j]), point(lower[i]))) / thickness;
    const MetricQuality first_metric = metric_triangle_quality(
        point(first[0]), point(first[1]), point(first[2]),
        tangent, co_normal, normal_scale);
    const MetricQuality second_metric = metric_triangle_quality(
        point(second[0]), point(second[1]), point(second[2]),
        tangent, co_normal, normal_scale);
    result.first.skewness = first_metric.skewness;
    result.first.aspect = first_metric.aspect;
    result.first.angle_nonorthogonality = first_metric.angle_nonorthogonality;
    result.second.skewness = second_metric.skewness;
    result.second.aspect = second_metric.aspect;
    result.second.angle_nonorthogonality = second_metric.angle_nonorthogonality;
    result.first.wall_nonorthogonality = wall;
    result.second.wall_nonorthogonality = wall;
    result.max_skewness = std::max(result.first.skewness, result.second.skewness);
    result.max_aspect = std::max(result.first.aspect, result.second.aspect);
    result.max_wall_nonorthogonality = wall;
    result.max_angle_nonorthogonality = std::max(result.first.angle_nonorthogonality, result.second.angle_nonorthogonality);
    result.min_signed_area = std::min(result.first.signed_area, result.second.signed_area);
    constexpr double max_skewness = 0.50;
    constexpr double max_aspect = 10.0;
    constexpr double max_wall_nonorthogonality = 30.0;
    result.valid =
        std::isfinite(result.max_skewness) &&
        std::isfinite(result.max_aspect) &&
        std::isfinite(result.max_wall_nonorthogonality) &&
        result.min_signed_area > epsilon &&
        result.max_skewness <= max_skewness + 1.0e-12 &&
        result.max_aspect <= max_aspect + 1.0e-12 &&
        result.max_wall_nonorthogonality <= max_wall_nonorthogonality + 1.0e-12;
    return result;
}

inline auto pair_rank(const PairQuality& value) {
    return std::tuple{
        value.valid ? 0 : 1,
        value.max_wall_nonorthogonality,
        value.max_skewness,
        value.max_aspect,
        -value.min_signed_area,
        value.diagonal};
}

inline bool make_inner_front(
    const std::array<Point, 3>& source,
    const Point& normal,
    const double offset,
    std::array<Point, 3>& inner,
    const double tolerance,
    std::string& reason) {
    std::array<Point, 3> inward{};
    for (int i = 0; i < 3; ++i) {
        const int next = (i + 1) % 3;
        try {
            const Point tangent = unit(sub(
                source[static_cast<std::size_t>(next)],
                source[static_cast<std::size_t>(i)]));
            inward[static_cast<std::size_t>(i)] =
                unit(autotessell_native_tri_authority::cross(normal, tangent));
        } catch (...) {
            reason = "tri_planar_template_edge_frame_invalid";
            return false;
        }
    }
    std::array<Point, 3> midpoint_constraints{};
    for (int i = 0; i < 3; ++i) {
        const int next = (i + 1) % 3;
        midpoint_constraints[static_cast<std::size_t>(i)] = add(
            add(source[static_cast<std::size_t>(i)],
                source[static_cast<std::size_t>(next)]),
            mul(inward[static_cast<std::size_t>(i)], 2.0 * offset));
    }
    inner[0] = mul(add(sub(midpoint_constraints[0], midpoint_constraints[1]),
                       midpoint_constraints[2]), 0.5);
    inner[1] = mul(add(add(midpoint_constraints[0], midpoint_constraints[1]),
                       mul(midpoint_constraints[2], -1.0)), 0.5);
    inner[2] = mul(add(add(mul(midpoint_constraints[0], -1.0),
                           midpoint_constraints[1]),
                       midpoint_constraints[2]), 0.5);
    for (const Point& point : inner) {
        if (!autotessell_native_tri_authority::finite(point)) {
            reason = "tri_planar_template_inner_point_nonfinite";
            return false;
        }
        const double deviation = std::abs(
            autotessell_native_tri_authority::dot(sub(point, source[0]), normal));
        if (!(deviation <= tolerance)) {
            reason = "tri_planar_template_inner_front_nonplanar";
            return false;
        }
    }
    const double area = signed_area(inner[0], inner[1], inner[2], normal);
    if (!(area > tolerance) || !std::isfinite(area)) {
        reason = "tri_planar_template_inner_front_nonpositive";
        return false;
    }
    for (int i = 0; i < 3; ++i) {
        const int next = (i + 1) % 3;
        const Point edge_vector = sub(
            source[static_cast<std::size_t>(next)],
            source[static_cast<std::size_t>(i)]);
        for (const Point& point : inner) {
            const double side = autotessell_native_tri_authority::dot(
                autotessell_native_tri_authority::cross(
                    edge_vector, sub(point, source[static_cast<std::size_t>(i)])),
                normal);
            if (side < -tolerance) {
                reason = "tri_planar_template_inner_front_outside_source";
                return false;
            }
        }
        const Point displacement = sub(
            mul(add(inner[static_cast<std::size_t>(i)],
                    inner[static_cast<std::size_t>(next)]), 0.5),
            mul(add(source[static_cast<std::size_t>(i)],
                    source[static_cast<std::size_t>(next)]), 0.5));
        if (!(autotessell_native_tri_authority::dot(
                  displacement, inward[static_cast<std::size_t>(i)]) > tolerance)) {
            reason = "tri_planar_template_inner_front_not_inward";
            return false;
        }
    }
    return true;
}

inline bool point_ids_share_vertex(const Triangle& first, const Triangle& second) {
    for (const auto left : first)
        for (const auto right : second)
            if (left == right) return true;
    return false;
}

inline Topology audit_output(
    const std::vector<Point>& points,
    const std::vector<Triangle>& faces,
    const std::vector<bool>& generated,
    const Point& generated_normal,
    const double epsilon) {
    Topology result;
    std::set<std::array<std::int64_t, 3>> face_keys;
    std::map<std::pair<std::int64_t, std::int64_t>, std::int64_t> edge_counts;
    std::vector<std::array<Point, 3>> geometry;
    std::vector<Triangle> geometry_faces;
    std::vector<autotessell_native_tri_authority::Aabb> boxes;
    geometry.reserve(faces.size());
    boxes.reserve(faces.size());
    for (std::size_t index = 0; index < faces.size(); ++index) {
        const Triangle& face = faces[index];
        if (std::any_of(face.begin(), face.end(), [&](const std::int64_t id) {
                return id < 0 || static_cast<std::size_t>(id) >= points.size();
            }) ||
            face[0] == face[1] || face[1] == face[2] || face[2] == face[0]) {
            ++result.invalid;
            continue;
        }
        auto key = face;
        std::sort(key.begin(), key.end());
        if (!face_keys.insert(key).second) ++result.duplicate;
        const Point& a = points[static_cast<std::size_t>(face[0])];
        const Point& b = points[static_cast<std::size_t>(face[1])];
        const Point& c = points[static_cast<std::size_t>(face[2])];
        const double area = signed_area(a, b, c, generated[index] ? generated_normal : generated_normal);
        if (generated[index] && (!(area > epsilon) || !std::isfinite(area))) ++result.inverted;
        for (int local = 0; local < 3; ++local) {
            std::int64_t first = face[static_cast<std::size_t>(local)];
            std::int64_t second = face[static_cast<std::size_t>((local + 1) % 3)];
            if (first > second) std::swap(first, second);
            ++edge_counts[{first, second}];
        }
        geometry.push_back({a, b, c});
        geometry_faces.push_back(face);
        boxes.push_back(autotessell_native_tri_authority::triangle_aabb(a, b, c));
    }
    for (const auto& [edge, count] : edge_counts) {
        (void)edge;
        if (count == 1) ++result.open_edges;
        if (count > 2) ++result.non_manifold;
    }
    for (std::size_t left = 0; left < geometry.size(); ++left) {
        for (std::size_t right = left + 1U; right < geometry.size(); ++right) {
            if (point_ids_share_vertex(geometry_faces[left], geometry_faces[right]) ||
                !autotessell_native_tri_authority::aabb_overlap(
                    boxes[left], boxes[right], epsilon))
                continue;
            if (autotessell_native_tri_authority::triangles_intersect(
                    geometry[left], geometry[right], epsilon))
                ++result.self_intersection;
        }
    }
    return result;
}

inline Collision audit_collisions(
    const std::vector<Point>& points,
    const std::vector<Triangle>& candidate,
    const std::vector<Triangle>& retained_source,
    const double epsilon) {
    Collision result;
    const auto inspect = [&](const Triangle& left, const Triangle& right) {
        const std::array<Point, 3> left_geometry{
            points.at(static_cast<std::size_t>(left[0])),
            points.at(static_cast<std::size_t>(left[1])),
            points.at(static_cast<std::size_t>(left[2]))};
        const std::array<Point, 3> right_geometry{
            points.at(static_cast<std::size_t>(right[0])),
            points.at(static_cast<std::size_t>(right[1])),
            points.at(static_cast<std::size_t>(right[2]))};
        const auto left_box = autotessell_native_tri_authority::triangle_aabb(
            left_geometry[0], left_geometry[1], left_geometry[2]);
        const auto right_box = autotessell_native_tri_authority::triangle_aabb(
            right_geometry[0], right_geometry[1], right_geometry[2]);
        if (!autotessell_native_tri_authority::aabb_overlap(left_box, right_box, epsilon))
            return;
        ++result.broad_phase_pairs;
        if (!autotessell_native_tri_authority::triangles_intersect(
                left_geometry, right_geometry, epsilon))
            return;
        ++result.narrow_phase_hits;
        if (point_ids_share_vertex(left, right)) ++result.allowed_shared_contacts;
        else ++result.rejected_contacts;
    };
    for (const Triangle& left : candidate)
        for (const Triangle& right : retained_source) inspect(left, right);
    for (std::size_t left = 0; left < candidate.size(); ++left)
        for (std::size_t right = left + 1U; right < candidate.size(); ++right)
            inspect(candidate[left], candidate[right]);
    return result;
}

inline bool all_quality_pass(
    const std::vector<Triangle>& faces,
    const std::vector<Point>& points,
    const Point& normal,
    const double epsilon,
    double& max_skew,
    double& max_aspect,
    double& max_wall,
    std::vector<Quality>* witnesses = nullptr) {
    max_skew = 0.0;
    max_aspect = 0.0;
    max_wall = 0.0;
    for (const Triangle& face : faces) {
        const Quality value = triangle_quality(
            points.at(static_cast<std::size_t>(face[0])),
            points.at(static_cast<std::size_t>(face[1])),
            points.at(static_cast<std::size_t>(face[2])),
            normal);
        max_skew = std::max(max_skew, value.skewness);
        max_aspect = std::max(max_aspect, value.aspect);
        max_wall = std::max(max_wall, value.wall_nonorthogonality);
        if (!(value.signed_area > epsilon) ||
            value.skewness > 0.50 + 1.0e-12 ||
            value.aspect > 10.0 + 1.0e-12 ||
            !std::isfinite(value.angle_nonorthogonality))
            return false;
        if (witnesses) witnesses->push_back(value);
    }
    return true;
}

}  // namespace autotessell_native_tri_planar_template
