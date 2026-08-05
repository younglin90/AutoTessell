#pragma once

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace autotessell_native_tri_authority {

using Point = std::array<double, 3>;
using Triangle = std::array<std::int64_t, 3>;

struct RawFacet {
    std::array<Point, 3> vertices{};
    Point normal{};
    bool normal_present = false;
};

struct CanonicalSource {
    std::vector<Point> points;
    std::vector<Triangle> faces;
    std::vector<Point> normals;
    std::vector<bool> normal_present;
    std::string source_kind;
};

struct TopologySummary {
    std::int64_t duplicate = 0;
    std::int64_t non_manifold = 0;
    std::int64_t open_edges = 0;
    std::int64_t degenerate = 0;
    std::int64_t inverted = 0;
    std::int64_t self_intersection = 0;
    bool self_intersection_checked = false;
};

inline Point sub(const Point& a, const Point& b) noexcept {
    return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}

inline Point add(const Point& a, const Point& b) noexcept {
    return {a[0] + b[0], a[1] + b[1], a[2] + b[2]};
}

inline Point scale(const Point& a, const double value) noexcept {
    return {a[0] * value, a[1] * value, a[2] * value};
}

inline Point cross(const Point& a, const Point& b) noexcept {
    return {a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]};
}

inline double dot(const Point& a, const Point& b) noexcept {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

inline double norm(const Point& value) noexcept {
    return std::sqrt(dot(value, value));
}

inline bool finite(const Point& value) noexcept {
    return std::all_of(value.begin(), value.end(), [](const double item) {
        return std::isfinite(item);
    });
}

inline std::uint64_t canonical_bits(double value) noexcept {
    if (value == 0.0) value = 0.0;
    return std::bit_cast<std::uint64_t>(value);
}

struct CoordinateKey {
    std::array<std::uint64_t, 3> bits{};
    auto operator<=>(const CoordinateKey&) const = default;
};

inline bool read_binary_float(const std::vector<std::uint8_t>& bytes,
                              const std::size_t offset, double& output) noexcept {
    if (offset + sizeof(float) > bytes.size()) return false;
    float value = 0.0F;
    std::memcpy(&value, bytes.data() + offset, sizeof(value));
    output = static_cast<double>(value);
    return std::isfinite(output);
}

inline std::uint32_t read_u32_le(const std::vector<std::uint8_t>& bytes,
                                 const std::size_t offset) noexcept {
    return static_cast<std::uint32_t>(bytes[offset]) |
           (static_cast<std::uint32_t>(bytes[offset + 1U]) << 8U) |
           (static_cast<std::uint32_t>(bytes[offset + 2U]) << 16U) |
           (static_cast<std::uint32_t>(bytes[offset + 3U]) << 24U);
}

inline bool parse_binary_stl(const std::vector<std::uint8_t>& bytes,
                             std::vector<RawFacet>& facets) {
    if (bytes.size() < 84U) return false;
    const std::uint64_t count = read_u32_le(bytes, 80U);
    if (count == 0U || count > (std::numeric_limits<std::size_t>::max() - 84U) / 50U)
        return false;
    if (84U + static_cast<std::size_t>(count) * 50U != bytes.size()) return false;
    facets.clear();
    facets.reserve(static_cast<std::size_t>(count));
    for (std::size_t facet = 0; facet < static_cast<std::size_t>(count); ++facet) {
        const std::size_t base = 84U + facet * 50U;
        RawFacet current;
        current.normal_present = true;
        for (int axis = 0; axis < 3; ++axis) {
            if (!read_binary_float(bytes, base + static_cast<std::size_t>(axis) * 4U,
                                   current.normal[static_cast<std::size_t>(axis)]))
                return false;
        }
        for (int vertex = 0; vertex < 3; ++vertex) {
            for (int axis = 0; axis < 3; ++axis) {
                const std::size_t offset = base + 12U +
                                           static_cast<std::size_t>(vertex) * 12U +
                                           static_cast<std::size_t>(axis) * 4U;
                if (!read_binary_float(bytes, offset,
                                       current.vertices[static_cast<std::size_t>(vertex)]
                                           [static_cast<std::size_t>(axis)]))
                    return false;
            }
        }
        facets.push_back(current);
    }
    return !facets.empty();
}

inline bool parse_ascii_stl(const std::vector<std::uint8_t>& bytes,
                            std::vector<RawFacet>& facets) {
    std::string text(bytes.begin(), bytes.end());
    std::istringstream input(text);
    std::string line;
    RawFacet current;
    std::vector<Point> vertices;
    bool in_facet = false;
    bool any_facet = false;
    while (std::getline(input, line)) {
        std::istringstream row(line);
        std::string token;
        if (!(row >> token)) continue;
        if (token == "facet") {
            std::string normal_token;
            if (!(row >> normal_token) || normal_token != "normal" ||
                !(row >> current.normal[0] >> current.normal[1] >> current.normal[2])) {
                return false;
            }
            current.normal_present = true;
            vertices.clear();
            in_facet = true;
            any_facet = true;
        } else if (token == "vertex") {
            if (!in_facet || vertices.size() >= 3U) return false;
            Point point{};
            if (!(row >> point[0] >> point[1] >> point[2]) || !finite(point)) return false;
            vertices.push_back(point);
            if (vertices.size() == 3U) {
                current.vertices = {vertices[0], vertices[1], vertices[2]};
                facets.push_back(current);
                vertices.clear();
                in_facet = false;
            }
        }
    }
    return any_facet && !facets.empty() && vertices.empty();
}

inline bool parse_stl(const std::vector<std::uint8_t>& bytes,
                      CanonicalSource& output, std::string& reason) {
    std::vector<RawFacet> facets;
    if (parse_binary_stl(bytes, facets)) {
        output.source_kind = "stl_binary";
    } else {
        facets.clear();
        if (!parse_ascii_stl(bytes, facets)) {
            reason = "stl_binary_or_ascii_parse_failed";
            return false;
        }
        output.source_kind = "stl_ascii";
    }
    std::map<CoordinateKey, std::int64_t> vertex_ids;
    output.points.clear();
    output.faces.clear();
    output.normals.clear();
    output.normal_present.clear();
    output.faces.reserve(facets.size());
    output.normals.reserve(facets.size());
    output.normal_present.reserve(facets.size());
    for (const RawFacet& facet : facets) {
        Triangle triangle{};
        for (int vertex = 0; vertex < 3; ++vertex) {
            const Point point = facet.vertices[static_cast<std::size_t>(vertex)];
            if (!finite(point)) {
                reason = "stl_nonfinite_vertex";
                return false;
            }
            CoordinateKey key{{canonical_bits(point[0]), canonical_bits(point[1]),
                               canonical_bits(point[2])}};
            auto [it, inserted] = vertex_ids.emplace(key,
                                                     static_cast<std::int64_t>(output.points.size()));
            if (inserted) output.points.push_back(point);
            triangle[static_cast<std::size_t>(vertex)] = it->second;
        }
        output.faces.push_back(triangle);
        output.normals.push_back(facet.normal);
        output.normal_present.push_back(facet.normal_present);
    }
    if (output.faces.empty() || output.normals.size() != output.faces.size()) {
        reason = "stl_empty_canonical_stream";
        return false;
    }
    return true;
}

struct Aabb {
    Point low{std::numeric_limits<double>::infinity(),
              std::numeric_limits<double>::infinity(),
              std::numeric_limits<double>::infinity()};
    Point high{-std::numeric_limits<double>::infinity(),
               -std::numeric_limits<double>::infinity(),
               -std::numeric_limits<double>::infinity()};
};

inline Aabb triangle_aabb(const Point& a, const Point& b, const Point& c) noexcept {
    Aabb box;
    for (int axis = 0; axis < 3; ++axis) {
        box.low[static_cast<std::size_t>(axis)] =
            std::min({a[static_cast<std::size_t>(axis)], b[static_cast<std::size_t>(axis)],
                      c[static_cast<std::size_t>(axis)]});
        box.high[static_cast<std::size_t>(axis)] =
            std::max({a[static_cast<std::size_t>(axis)], b[static_cast<std::size_t>(axis)],
                      c[static_cast<std::size_t>(axis)]});
    }
    return box;
}

inline bool aabb_overlap(const Aabb& left, const Aabb& right,
                         const double tolerance) noexcept {
    for (int axis = 0; axis < 3; ++axis) {
        if (left.high[static_cast<std::size_t>(axis)] <
                right.low[static_cast<std::size_t>(axis)] - tolerance ||
            right.high[static_cast<std::size_t>(axis)] <
                left.low[static_cast<std::size_t>(axis)] - tolerance)
            return false;
    }
    return true;
}

inline int dominant_axis(const Point& normal) noexcept {
    const Point absolute{std::abs(normal[0]), std::abs(normal[1]), std::abs(normal[2])};
    return absolute[0] >= absolute[1] && absolute[0] >= absolute[2]
               ? 0
               : (absolute[1] >= absolute[2] ? 1 : 2);
}

inline std::pair<double, double> project(const Point& point, const int dropped_axis) noexcept {
    const int first = (dropped_axis + 1) % 3;
    const int second = (dropped_axis + 2) % 3;
    return {point[static_cast<std::size_t>(first)],
            point[static_cast<std::size_t>(second)]};
}

inline double orient2(const std::pair<double, double>& a,
                      const std::pair<double, double>& b,
                      const std::pair<double, double>& c) noexcept {
    return (b.first - a.first) * (c.second - a.second) -
           (b.second - a.second) * (c.first - a.first);
}

inline bool segment_2d_intersects(const std::pair<double, double>& a,
                                  const std::pair<double, double>& b,
                                  const std::pair<double, double>& c,
                                  const std::pair<double, double>& d,
                                  const double tolerance) noexcept {
    const double ab_c = orient2(a, b, c);
    const double ab_d = orient2(a, b, d);
    const double cd_a = orient2(c, d, a);
    const double cd_b = orient2(c, d, b);
    const auto on = [tolerance](const std::pair<double, double>& p,
                                const std::pair<double, double>& q,
                                const std::pair<double, double>& x) noexcept {
        return x.first >= std::min(p.first, q.first) - tolerance &&
               x.first <= std::max(p.first, q.first) + tolerance &&
               x.second >= std::min(p.second, q.second) - tolerance &&
               x.second <= std::max(p.second, q.second) + tolerance;
    };
    const auto sign = [tolerance](const double value) noexcept {
        return value > tolerance ? 1 : (value < -tolerance ? -1 : 0);
    };
    const int s0 = sign(ab_c), s1 = sign(ab_d), s2 = sign(cd_a), s3 = sign(cd_b);
    return (s0 * s1 < 0 && s2 * s3 < 0) ||
           (s0 == 0 && on(a, b, c)) || (s1 == 0 && on(a, b, d)) ||
           (s2 == 0 && on(c, d, a)) || (s3 == 0 && on(c, d, b));
}

inline bool point_in_projected_triangle(const std::pair<double, double>& p,
                                        const std::array<std::pair<double, double>, 3>& tri,
                                        const double tolerance) noexcept {
    const double a = orient2(tri[0], tri[1], p);
    const double b = orient2(tri[1], tri[2], p);
    const double c = orient2(tri[2], tri[0], p);
    return (a >= -tolerance && b >= -tolerance && c >= -tolerance) ||
           (a <= tolerance && b <= tolerance && c <= tolerance);
}

inline bool coplanar_triangles_intersect(const std::array<Point, 3>& left,
                                         const std::array<Point, 3>& right,
                                         const Point& normal,
                                         const double tolerance) noexcept {
    const int axis = dominant_axis(normal);
    std::array<std::pair<double, double>, 3> a{};
    std::array<std::pair<double, double>, 3> b{};
    for (int i = 0; i < 3; ++i) {
        a[static_cast<std::size_t>(i)] = project(left[static_cast<std::size_t>(i)], axis);
        b[static_cast<std::size_t>(i)] = project(right[static_cast<std::size_t>(i)], axis);
    }
    for (int i = 0; i < 3; ++i) {
        const auto& a0 = a[static_cast<std::size_t>(i)];
        const auto& a1 = a[static_cast<std::size_t>((i + 1) % 3)];
        for (int j = 0; j < 3; ++j) {
            if (segment_2d_intersects(a0, a1, b[static_cast<std::size_t>(j)],
                                      b[static_cast<std::size_t>((j + 1) % 3)],
                                      tolerance))
                return true;
        }
    }
    return point_in_projected_triangle(a[0], b, tolerance) ||
           point_in_projected_triangle(b[0], a, tolerance);
}

inline bool point_in_triangle_3d(const Point& point, const std::array<Point, 3>& triangle,
                                 const Point& normal, const double tolerance) noexcept {
    const Point c0 = cross(sub(triangle[1], triangle[0]), sub(point, triangle[0]));
    const Point c1 = cross(sub(triangle[2], triangle[1]), sub(point, triangle[1]));
    const Point c2 = cross(sub(triangle[0], triangle[2]), sub(point, triangle[2]));
    const double first = dot(c0, normal);
    const double second = dot(c1, normal);
    const double third = dot(c2, normal);
    return (first >= -tolerance && second >= -tolerance && third >= -tolerance) ||
           (first <= tolerance && second <= tolerance && third <= tolerance);
}

inline bool segment_plane_triangle_hit(const Point& first, const Point& second,
                                       const std::array<Point, 3>& triangle,
                                       const Point& normal, const double tolerance) noexcept {
    const double d0 = dot(normal, sub(first, triangle[0]));
    const double d1 = dot(normal, sub(second, triangle[0]));
    if ((d0 > tolerance && d1 > tolerance) || (d0 < -tolerance && d1 < -tolerance))
        return false;
    const double denominator = d0 - d1;
    if (std::abs(denominator) <= tolerance)
        return std::abs(d0) <= tolerance && point_in_triangle_3d(first, triangle, normal, tolerance);
    const double parameter = std::clamp(d0 / denominator, 0.0, 1.0);
    const Point point = add(first, scale(sub(second, first), parameter));
    return point_in_triangle_3d(point, triangle, normal, tolerance);
}

inline bool triangles_intersect(const std::array<Point, 3>& left,
                                const std::array<Point, 3>& right,
                                const double tolerance) noexcept {
    const Point left_normal = cross(sub(left[1], left[0]), sub(left[2], left[0]));
    const Point right_normal = cross(sub(right[1], right[0]), sub(right[2], right[0]));
    const double left_size = norm(left_normal);
    const double right_size = norm(right_normal);
    if (!(left_size > tolerance && right_size > tolerance)) return false;
    const Point left_unit = scale(left_normal, 1.0 / left_size);
    const Point right_unit = scale(right_normal, 1.0 / right_size);
    const std::array<double, 3> left_distances{
        dot(right_unit, sub(left[0], right[0])), dot(right_unit, sub(left[1], right[0])),
        dot(right_unit, sub(left[2], right[0]))};
    const std::array<double, 3> right_distances{
        dot(left_unit, sub(right[0], left[0])), dot(left_unit, sub(right[1], left[0])),
        dot(left_unit, sub(right[2], left[0]))};
    const auto one_side = [tolerance](const auto& values) noexcept {
        return (values[0] > tolerance && values[1] > tolerance && values[2] > tolerance) ||
               (values[0] < -tolerance && values[1] < -tolerance && values[2] < -tolerance);
    };
    if (one_side(left_distances) || one_side(right_distances)) return false;
    const bool coplanar = std::all_of(left_distances.begin(), left_distances.end(),
                                      [tolerance](const double value) {
                                          return std::abs(value) <= tolerance;
                                      }) &&
                          std::all_of(right_distances.begin(), right_distances.end(),
                                      [tolerance](const double value) {
                                          return std::abs(value) <= tolerance;
                                      });
    if (coplanar) return coplanar_triangles_intersect(left, right, left_normal, tolerance);
    for (int edge = 0; edge < 3; ++edge) {
        if (segment_plane_triangle_hit(left[static_cast<std::size_t>(edge)],
                                       left[static_cast<std::size_t>((edge + 1) % 3)], right,
                                       right_unit, tolerance) ||
            segment_plane_triangle_hit(right[static_cast<std::size_t>(edge)],
                                       right[static_cast<std::size_t>((edge + 1) % 3)], left,
                                       left_unit, tolerance))
            return true;
    }
    return false;
}

inline TopologySummary audit_topology(const CanonicalSource& source) {
    TopologySummary result;
    std::set<std::array<std::int64_t, 3>> faces;
    std::map<std::pair<std::int64_t, std::int64_t>, std::int64_t> edges;
    const double scale_value = [&]() {
        if (source.points.empty()) return 1.0;
        Point low = source.points.front();
        Point high = source.points.front();
        for (const Point& point : source.points) {
            for (int axis = 0; axis < 3; ++axis) {
                low[static_cast<std::size_t>(axis)] =
                    std::min(low[static_cast<std::size_t>(axis)], point[static_cast<std::size_t>(axis)]);
                high[static_cast<std::size_t>(axis)] =
                    std::max(high[static_cast<std::size_t>(axis)], point[static_cast<std::size_t>(axis)]);
            }
        }
        return std::max(1.0, norm(sub(high, low)));
    }();
    const double tolerance = 1.0e-12 * scale_value;
    std::vector<std::array<Point, 3>> triangles;
    std::vector<Aabb> boxes;
    triangles.reserve(source.faces.size());
    boxes.reserve(source.faces.size());
    for (std::size_t index = 0; index < source.faces.size(); ++index) {
        const Triangle& face = source.faces[index];
        auto key = face;
        std::sort(key.begin(), key.end());
        if (!faces.insert(key).second) ++result.duplicate;
        const Point& a = source.points[static_cast<std::size_t>(face[0])];
        const Point& b = source.points[static_cast<std::size_t>(face[1])];
        const Point& c = source.points[static_cast<std::size_t>(face[2])];
        const Point geometric_normal = cross(sub(b, a), sub(c, a));
        if (!(norm(geometric_normal) > tolerance)) ++result.degenerate;
        if (index >= source.normals.size() || index >= source.normal_present.size() ||
            !source.normal_present[index]) {
            ++result.inverted;
        } else {
            const double supplied_norm = norm(source.normals[index]);
            if (!(supplied_norm > tolerance) || dot(geometric_normal, source.normals[index]) <= 0.0)
                ++result.inverted;
        }
        for (int edge = 0; edge < 3; ++edge) {
            auto first = face[static_cast<std::size_t>(edge)];
            auto second = face[static_cast<std::size_t>((edge + 1) % 3)];
            if (first > second) std::swap(first, second);
            ++edges[{first, second}];
        }
        triangles.push_back({a, b, c});
        boxes.push_back(triangle_aabb(a, b, c));
    }
    for (const auto& [edge, count] : edges) {
        (void)edge;
        if (count > 2) ++result.non_manifold;
        if (count == 1) ++result.open_edges;
    }
    for (std::size_t left = 0; left < triangles.size(); ++left) {
        for (std::size_t right = left + 1U; right < triangles.size(); ++right) {
            const Triangle& left_face = source.faces[left];
            const Triangle& right_face = source.faces[right];
            bool shared_vertex = false;
            for (const auto first : left_face)
                for (const auto second : right_face)
                    shared_vertex = shared_vertex || first == second;
            if (shared_vertex || !aabb_overlap(boxes[left], boxes[right], tolerance)) continue;
            if (triangles_intersect(triangles[left], triangles[right], tolerance)) ++result.self_intersection;
        }
    }
    result.self_intersection_checked = true;
    return result;
}

inline std::string canonical_geometry_stream(const CanonicalSource& source) {
    std::ostringstream stream;
    stream << "points=" << source.points.size() << ";faces=" << source.faces.size() << ";";
    stream << std::hex << std::setfill('0');
    for (const Point& point : source.points) {
        stream << std::setw(16) << canonical_bits(point[0]) << ','
               << std::setw(16) << canonical_bits(point[1]) << ','
               << std::setw(16) << canonical_bits(point[2]) << ';';
    }
    stream << std::dec;
    for (const Triangle& face : source.faces)
        stream << face[0] << ',' << face[1] << ',' << face[2] << ';';
    return stream.str();
}

inline std::string sha256_text(const std::string& value) {
    return brep_evidence::sha256_hex(
        std::vector<std::uint8_t>(value.begin(), value.end()));
}

}  // namespace autotessell_native_tri_authority
