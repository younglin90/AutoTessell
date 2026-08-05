#pragma once

#include "native_tri_planar_triangle_bl_template.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace autotessell_native_tri_planar_pair {

namespace base = autotessell_native_tri_planar_template;
using Point = base::Point;
using Triangle = base::Triangle;

struct Metric {
    double skewness = std::numeric_limits<double>::infinity();
    double aspect = std::numeric_limits<double>::infinity();
    double angle_nonorthogonality = std::numeric_limits<double>::infinity();
};

struct Raw {
    double aspect = std::numeric_limits<double>::infinity();
    double skewness = std::numeric_limits<double>::infinity();
    double mean_ratio = 0.0;
    double angle_nonorthogonality = std::numeric_limits<double>::infinity();
    double signed_area = -std::numeric_limits<double>::infinity();
};

struct TriangleEvaluation {
    Raw raw{};
    Metric metric{};
    double wall_nonorthogonality = std::numeric_limits<double>::infinity();
};

struct PairEvaluation {
    bool valid = false;
    TriangleEvaluation first{};
    TriangleEvaluation second{};
    double max_metric_skewness = std::numeric_limits<double>::infinity();
    double max_metric_aspect = std::numeric_limits<double>::infinity();
    double max_wall_nonorthogonality = std::numeric_limits<double>::infinity();
    double max_raw_aspect = std::numeric_limits<double>::infinity();
    double min_raw_mean_ratio = 0.0;
    double max_raw_angle_nonorthogonality = std::numeric_limits<double>::infinity();
    double min_signed_area = -std::numeric_limits<double>::infinity();
    int diagonal = 0;
};

struct RingChoice {
    bool valid = false;
    int mask = 0;
    std::array<PairEvaluation, 4> evaluation{};
    std::array<std::array<Triangle, 2>, 4> triangles{};
    double max_metric_skewness = std::numeric_limits<double>::infinity();
    double max_metric_aspect = std::numeric_limits<double>::infinity();
    double max_wall_nonorthogonality = std::numeric_limits<double>::infinity();
    double max_raw_aspect = std::numeric_limits<double>::infinity();
    double min_raw_mean_ratio = 0.0;
    double max_raw_angle_nonorthogonality = std::numeric_limits<double>::infinity();
    double min_signed_area = -std::numeric_limits<double>::infinity();
};

inline double mean_ratio(const Point& a, const Point& b, const Point& c) noexcept {
    const Point ab = base::sub(b, a);
    const Point bc = base::sub(c, b);
    const Point ca = base::sub(a, c);
    const double area = base::signed_area(a, b, c, base::unit(
        autotessell_native_tri_authority::cross(ab, base::sub(c, a))));
    const double denominator =
        autotessell_native_tri_authority::dot(ab, ab) +
        autotessell_native_tri_authority::dot(bc, bc) +
        autotessell_native_tri_authority::dot(ca, ca);
    if (!(area > 0.0) || !(denominator > 0.0) || !std::isfinite(area) ||
        !std::isfinite(denominator))
        return 0.0;
    return 4.0 * std::sqrt(3.0) * area / denominator;
}

inline Metric metric_triangle_quality(
    const Point& a, const Point& b, const Point& c,
    const Point& tangent, const Point& co_normal, const double normal_scale) {
    const auto transformed_length = [&](const Point& value) {
        const double t = autotessell_native_tri_authority::dot(value, tangent);
        const double n = autotessell_native_tri_authority::dot(value, co_normal);
        return std::sqrt(t * t + n * n * normal_scale * normal_scale);
    };
    const auto metric_dot = [&](const Point& left, const Point& right) {
        return autotessell_native_tri_authority::dot(left, tangent) *
                   autotessell_native_tri_authority::dot(right, tangent) +
               autotessell_native_tri_authority::dot(left, co_normal) *
                   autotessell_native_tri_authority::dot(right, co_normal) *
                   normal_scale * normal_scale;
    };
    const auto metric_angle = [&](const Point& left, const Point& right) {
        const double denominator = transformed_length(left) * transformed_length(right);
        if (!(denominator > 0.0) || !std::isfinite(denominator))
            return std::numeric_limits<double>::infinity();
        return std::acos(std::clamp(metric_dot(left, right) / denominator, -1.0, 1.0)) *
               180.0 / std::acos(-1.0);
    };
    const Point ab = base::sub(b, a);
    const Point bc = base::sub(c, b);
    const Point ca = base::sub(a, c);
    const double lengths[3] = {
        transformed_length(ab), transformed_length(bc), transformed_length(ca)};
    const double shortest = std::min({lengths[0], lengths[1], lengths[2]});
    const double longest = std::max({lengths[0], lengths[1], lengths[2]});
    if (!(shortest > 1.0e-14) || !std::isfinite(longest))
        return {};
    return {
        (longest / shortest - 1.0) / (longest / shortest),
        longest / shortest,
        std::max({
            std::abs(metric_angle(ab, base::sub(c, a)) - 60.0),
            std::abs(metric_angle(base::sub(a, b), bc) - 60.0),
            std::abs(metric_angle(base::sub(a, c), base::sub(b, c)) - 60.0)})};
}

inline PairEvaluation evaluate_pair(
    const Triangle& first, const Triangle& second,
    const std::vector<Point>& points,
    const std::array<std::int64_t, 4>& lower,
    const std::array<std::int64_t, 4>& upper,
    const int edge_index,
    const Point& normal,
    const double epsilon,
    const int diagonal) {
    PairEvaluation result;
    result.diagonal = diagonal;
    const auto point = [&](const std::int64_t id) -> const Point& {
        return points.at(static_cast<std::size_t>(id));
    };
    const Point tangent = base::unit(base::sub(
        point(lower[static_cast<std::size_t>((edge_index + 1) % 4)]),
        point(lower[static_cast<std::size_t>(edge_index)])));
    const Point co_normal = base::unit(
        autotessell_native_tri_authority::cross(normal, tangent));
    const Point displacement = base::sub(
        base::mul(base::add(
            point(upper[static_cast<std::size_t>(edge_index)]),
            point(upper[static_cast<std::size_t>((edge_index + 1) % 4)])), 0.5),
        base::mul(base::add(
            point(lower[static_cast<std::size_t>(edge_index)]),
            point(lower[static_cast<std::size_t>((edge_index + 1) % 4)])), 0.5));
    const double thickness =
        autotessell_native_tri_authority::dot(displacement, co_normal);
    if (!(thickness > epsilon) || !std::isfinite(thickness))
        return result;
    const double normal_scale = autotessell_native_tri_authority::norm(base::sub(
        point(lower[static_cast<std::size_t>((edge_index + 1) % 4)]),
        point(lower[static_cast<std::size_t>(edge_index)]))) / thickness;
    const auto eval = [&](const Triangle& f) {
        const base::Quality raw_q = base::triangle_quality(
            point(f[0]), point(f[1]), point(f[2]), normal);
        const Metric metric_q = metric_triangle_quality(
            point(f[0]), point(f[1]), point(f[2]),
            tangent, co_normal, normal_scale);
        TriangleEvaluation value;
        value.raw.aspect = raw_q.physical_aspect;
        value.raw.skewness = raw_q.skewness;
        value.raw.angle_nonorthogonality = raw_q.angle_nonorthogonality;
        value.raw.signed_area = raw_q.signed_area;
        value.raw.mean_ratio = mean_ratio(
            point(f[0]), point(f[1]), point(f[2]));
        value.metric = metric_q;
        value.wall_nonorthogonality = base::wall_nonorthogonality(
            point(lower[static_cast<std::size_t>(edge_index)]),
            point(lower[static_cast<std::size_t>((edge_index + 1) % 4)]),
            point(upper[static_cast<std::size_t>(edge_index)]),
            point(upper[static_cast<std::size_t>((edge_index + 1) % 4)]),
            normal);
        return value;
    };
    result.first = eval(first);
    result.second = eval(second);
    result.max_metric_skewness = std::max(
        result.first.metric.skewness, result.second.metric.skewness);
    result.max_metric_aspect = std::max(
        result.first.metric.aspect, result.second.metric.aspect);
    result.max_wall_nonorthogonality = std::max(
        result.first.wall_nonorthogonality, result.second.wall_nonorthogonality);
    result.max_raw_aspect = std::max(
        result.first.raw.aspect, result.second.raw.aspect);
    result.min_raw_mean_ratio = std::min(
        result.first.raw.mean_ratio, result.second.raw.mean_ratio);
    result.max_raw_angle_nonorthogonality = std::max(
        result.first.raw.angle_nonorthogonality,
        result.second.raw.angle_nonorthogonality);
    result.min_signed_area = std::min(
        result.first.raw.signed_area, result.second.raw.signed_area);
    result.valid =
        std::isfinite(result.max_metric_skewness) &&
        std::isfinite(result.max_metric_aspect) &&
        std::isfinite(result.max_wall_nonorthogonality) &&
        std::isfinite(result.max_raw_aspect) &&
        std::isfinite(result.min_raw_mean_ratio) &&
        std::isfinite(result.max_raw_angle_nonorthogonality) &&
        result.min_signed_area > epsilon &&
        result.max_metric_skewness <= 0.35 + 1.0e-12 &&
        result.max_metric_aspect <= 1.60 + 1.0e-12 &&
        result.max_wall_nonorthogonality <= 1.0 + 1.0e-12 &&
        result.max_raw_aspect <= 5.50 + 1.0e-12 &&
        result.min_raw_mean_ratio >= 0.30 - 1.0e-12 &&
        result.max_raw_angle_nonorthogonality <= 55.0 + 1.0e-12;
    return result;
}

inline auto pair_rank(const PairEvaluation& value) {
    return std::tuple{
        value.valid ? 0 : 1,
        value.max_metric_skewness,
        value.max_metric_aspect,
        value.max_raw_aspect,
        -value.min_raw_mean_ratio,
        value.max_raw_angle_nonorthogonality,
        value.diagonal};
}

inline RingChoice choose_ring(
    const std::array<std::array<std::array<Triangle, 2>, 2>, 4>& options,
    const std::vector<Point>& points,
    const std::array<std::int64_t, 4>& lower,
    const std::array<std::int64_t, 4>& upper,
    const Point& normal,
    const double epsilon) {
    RingChoice best;
    for (int mask = 0; mask < 16; ++mask) {
        RingChoice candidate;
        candidate.mask = mask;
        candidate.valid = true;
        candidate.max_metric_skewness = 0.0;
        candidate.max_metric_aspect = 0.0;
        candidate.max_wall_nonorthogonality = 0.0;
        candidate.max_raw_aspect = 0.0;
        candidate.min_raw_mean_ratio = std::numeric_limits<double>::infinity();
        candidate.max_raw_angle_nonorthogonality = 0.0;
        candidate.min_signed_area = std::numeric_limits<double>::infinity();
        for (int edge = 0; edge < 4; ++edge) {
            const int diagonal = (mask >> edge) & 1;
            candidate.triangles[static_cast<std::size_t>(edge)] =
                options[static_cast<std::size_t>(edge)][static_cast<std::size_t>(diagonal)];
            const PairEvaluation value = evaluate_pair(
                options[static_cast<std::size_t>(edge)][static_cast<std::size_t>(diagonal)][0],
                options[static_cast<std::size_t>(edge)][static_cast<std::size_t>(diagonal)][1],
                points, lower, upper, edge, normal, epsilon, diagonal);
            candidate.evaluation[static_cast<std::size_t>(edge)] = value;
            candidate.valid = candidate.valid && value.valid;
            candidate.max_metric_skewness = std::max(
                candidate.max_metric_skewness, value.max_metric_skewness);
            candidate.max_metric_aspect = std::max(
                candidate.max_metric_aspect, value.max_metric_aspect);
            candidate.max_wall_nonorthogonality = std::max(
                candidate.max_wall_nonorthogonality, value.max_wall_nonorthogonality);
            candidate.max_raw_aspect = std::max(
                candidate.max_raw_aspect, value.max_raw_aspect);
            candidate.min_raw_mean_ratio = edge == 0
                ? value.min_raw_mean_ratio
                : std::min(candidate.min_raw_mean_ratio, value.min_raw_mean_ratio);
            candidate.max_raw_angle_nonorthogonality = std::max(
                candidate.max_raw_angle_nonorthogonality,
                value.max_raw_angle_nonorthogonality);
            candidate.min_signed_area = edge == 0
                ? value.min_signed_area
                : std::min(candidate.min_signed_area, value.min_signed_area);
        }
        if (!best.valid || pair_rank(PairEvaluation{
                candidate.valid,
                {}, {},
                candidate.max_metric_skewness,
                candidate.max_metric_aspect,
                candidate.max_wall_nonorthogonality,
                candidate.max_raw_aspect,
                candidate.min_raw_mean_ratio,
                candidate.max_raw_angle_nonorthogonality,
                candidate.min_signed_area,
                candidate.mask}) <
            pair_rank(PairEvaluation{
                best.valid,
                {}, {},
                best.max_metric_skewness,
                best.max_metric_aspect,
                best.max_wall_nonorthogonality,
                best.max_raw_aspect,
                best.min_raw_mean_ratio,
                best.max_raw_angle_nonorthogonality,
                best.min_signed_area,
                best.mask})) {
            best = candidate;
        }
    }
    return best;
}

inline bool offset_quad(
    const std::array<Point, 4>& outer, const Point& normal,
    const double offset, std::array<Point, 4>& inner,
    const double tolerance, std::string& reason) {
    std::array<Point, 4> inward{};
    for (int i = 0; i < 4; ++i) {
        const int next = (i + 1) % 4;
        try {
            inward[static_cast<std::size_t>(i)] = base::unit(
                autotessell_native_tri_authority::cross(
                    normal, base::sub(outer[static_cast<std::size_t>(next)],
                                      outer[static_cast<std::size_t>(i)])));
        } catch (...) {
            reason = "tri_planar_pair_outer_frame_invalid";
            return false;
        }
    }
    const Point origin = outer[0];
    const Point u = base::unit(base::sub(outer[1], outer[0]));
    const Point v = base::unit(autotessell_native_tri_authority::cross(normal, u));
    const auto xy = [&](const Point& p) {
        const Point delta = base::sub(p, origin);
        return std::array<double, 2>{
            autotessell_native_tri_authority::dot(delta, u),
            autotessell_native_tri_authority::dot(delta, v)};
    };
    const auto xy_vec = [&](const Point& p) {
        return std::array<double, 2>{
            autotessell_native_tri_authority::dot(p, u),
            autotessell_native_tri_authority::dot(p, v)};
    };
    const auto cross2 = [](const std::array<double, 2>& a,
                           const std::array<double, 2>& b) {
        return a[0] * b[1] - a[1] * b[0];
    };
    const auto add2 = [](const std::array<double, 2>& a,
                         const std::array<double, 2>& b) {
        return std::array<double, 2>{a[0] + b[0], a[1] + b[1]};
    };
    const auto sub2 = [](const std::array<double, 2>& a,
                         const std::array<double, 2>& b) {
        return std::array<double, 2>{a[0] - b[0], a[1] - b[1]};
    };
    const auto mul2 = [](const std::array<double, 2>& a, const double s) {
        return std::array<double, 2>{a[0] * s, a[1] * s};
    };
    const auto make_point = [&](const std::array<double, 2>& p) {
        return base::add(origin, base::add(base::mul(u, p[0]), base::mul(v, p[1])));
    };
    for (int i = 0; i < 4; ++i) {
        const int prev = (i + 3) % 4;
        const int next = (i + 1) % 4;
        const auto d0 = sub2(xy(outer[i]), xy(outer[prev]));
        const auto d1 = sub2(xy(outer[next]), xy(outer[i]));
        const auto s0 = add2(xy(outer[prev]), mul2(xy_vec(inward[prev]), offset));
        const auto s1 = add2(xy(outer[i]), mul2(xy_vec(inward[i]), offset));
        const double denominator = cross2(d0, d1);
        if (!(denominator > tolerance) || !std::isfinite(denominator)) {
            reason = "tri_planar_pair_offset_lines_parallel";
            return false;
        }
        const double t = cross2(sub2(s1, s0), d1) / denominator;
        const auto result_xy = add2(s0, mul2(d0, t));
        inner[static_cast<std::size_t>(i)] = make_point(result_xy);
        if (!autotessell_native_tri_authority::finite(inner[static_cast<std::size_t>(i)])) {
            reason = "tri_planar_pair_inner_front_nonfinite";
            return false;
        }
    }
    for (int edge = 0; edge < 4; ++edge) {
        const int next = (edge + 1) % 4;
        const Point edge_vector = base::sub(
            outer[static_cast<std::size_t>(next)],
            outer[static_cast<std::size_t>(edge)]);
        for (const Point& p : inner) {
            const double side = autotessell_native_tri_authority::dot(
                autotessell_native_tri_authority::cross(
                    edge_vector, base::sub(p, outer[static_cast<std::size_t>(edge)])),
                normal);
            if (!(side >= -tolerance)) {
                reason = "tri_planar_pair_inner_front_outside_source";
                return false;
            }
        }
        const Point displacement = base::sub(
            base::mul(base::add(
                inner[static_cast<std::size_t>(edge)],
                inner[static_cast<std::size_t>(next)]), 0.5),
            base::mul(base::add(
                outer[static_cast<std::size_t>(edge)],
                outer[static_cast<std::size_t>(next)]), 0.5));
        const Point expected = inward[static_cast<std::size_t>(edge)];
        if (!(autotessell_native_tri_authority::dot(displacement, expected) >
              offset - tolerance)) {
            reason = "tri_planar_pair_inner_front_inset_invalid";
            return false;
        }
    }
    const double area = base::signed_area(
        inner[0], inner[1], inner[2], normal) +
        base::signed_area(inner[0], inner[2], inner[3], normal);
    if (!(area > tolerance) || !std::isfinite(area)) {
        reason = "tri_planar_pair_inner_front_nonpositive";
        return false;
    }
    return true;
}

inline bool square_like_quad(
    const std::array<Point, 4>& outer, const Point& normal,
    const double tolerance, std::string& reason) {
    std::array<double, 4> lengths{};
    for (int i = 0; i < 4; ++i) {
        lengths[static_cast<std::size_t>(i)] = autotessell_native_tri_authority::norm(base::sub(
            outer[static_cast<std::size_t>((i + 1) % 4)],
            outer[static_cast<std::size_t>(i)]));
        if (!(lengths[static_cast<std::size_t>(i)] > tolerance) ||
            !std::isfinite(lengths[static_cast<std::size_t>(i)]))
            { reason = "tri_planar_pair_outer_edge_zero_length"; return false; }
    }
    const double shortest = *std::min_element(lengths.begin(), lengths.end());
    const double longest = *std::max_element(lengths.begin(), lengths.end());
    if (longest / shortest > 1.25 + 1.0e-12) {
        reason = "tri_planar_pair_not_square_like";
        return false;
    }
    for (int i = 0; i < 4; ++i) {
        const Point e0 = base::sub(outer[static_cast<std::size_t>((i + 1) % 4)],
                                   outer[static_cast<std::size_t>(i)]);
        const Point e1 = base::sub(outer[static_cast<std::size_t>((i + 2) % 4)],
                                   outer[static_cast<std::size_t>((i + 1) % 4)]);
        const double turn = autotessell_native_tri_authority::dot(
            autotessell_native_tri_authority::cross(e0, e1), normal);
        if (!(turn > tolerance)) {
            reason = "tri_planar_pair_outer_not_convex";
            return false;
        }
        const double orth = std::abs(autotessell_native_tri_authority::dot(e0, e1)) /
                            (lengths[static_cast<std::size_t>(i)] *
                             lengths[static_cast<std::size_t>((i + 1) % 4)]);
        if (orth > 0.20) {
            reason = "tri_planar_pair_outer_not_orthogonal";
            return false;
        }
    }
    const double diagonal0 = autotessell_native_tri_authority::norm(base::sub(outer[2], outer[0]));
    const double diagonal1 = autotessell_native_tri_authority::norm(base::sub(outer[3], outer[1]));
    if (!(diagonal0 > tolerance) || !(diagonal1 > tolerance) ||
        std::max(diagonal0, diagonal1) / std::min(diagonal0, diagonal1) > 1.25) {
        reason = "tri_planar_pair_diagonals_not_square_like";
        return false;
    }
    return true;
}

}  // namespace autotessell_native_tri_planar_pair
