#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <vector>

namespace autotessell::native_hex {

using Label = std::int64_t;
using Point3 = std::array<double, 3>;

struct LocalFrontResult {
    std::size_t iterations = 0;
    std::size_t reduced_vertices = 0;
    std::size_t collapsed_vertices = 0;
    std::size_t raw_negative_hexes = 0;
    std::size_t nonpositive_corner_hexes = 0;
    double minimum_corner_determinant = std::numeric_limits<double>::infinity();
    bool converged = false;
};

struct LocalFrontAdmissionNumericResult {
    bool source_rows_complete = false;
    bool clearance_sufficient = false;
    std::size_t source_face_count = 0;
    std::size_t quad_count = 0;
};

[[nodiscard]] inline LocalFrontAdmissionNumericResult
audit_local_front_numeric_admission(
    std::span<const Label> source_face_ids,
    std::size_t source_face_count,
    double requested_step,
    double minimum_clearance)
{
    LocalFrontAdmissionNumericResult result;
    result.source_face_count = source_face_count;
    result.quad_count = source_face_ids.size();
    if (source_face_count == 0U
        || source_face_count > std::numeric_limits<std::size_t>::max() / 3U
        || source_face_ids.size() != 3U * source_face_count
        || !std::isfinite(requested_step) || requested_step <= 0.0
        || !std::isfinite(minimum_clearance) || minimum_clearance <= 0.0) {
        return result;
    }
    std::vector<std::uint8_t> counts(source_face_count, std::uint8_t{0});
    for (const Label source_face : source_face_ids) {
        if (source_face < 0
            || static_cast<std::size_t>(source_face) >= source_face_count) {
            return result;
        }
        auto& count = counts[static_cast<std::size_t>(source_face)];
        if (count == 3U) {
            return result;
        }
        ++count;
    }
    result.source_rows_complete = std::all_of(
        counts.begin(), counts.end(),
        [](std::uint8_t count) { return count == 3U; });
    result.clearance_sufficient = minimum_clearance >= requested_step;
    return result;
}

inline constexpr std::array<std::array<int, 4>, 5> five_tet_fan{{
    {{0, 1, 3, 4}},
    {{1, 2, 3, 6}},
    {{3, 4, 6, 7}},
    {{1, 4, 5, 6}},
    {{1, 3, 4, 6}},
}};

inline constexpr std::array<std::array<int, 3>, 8> corner_neighbors{{
    {{1, 3, 4}},
    {{2, 0, 5}},
    {{3, 1, 6}},
    {{0, 2, 7}},
    {{7, 5, 0}},
    {{4, 6, 1}},
    {{5, 7, 2}},
    {{6, 4, 3}},
}};

[[nodiscard]] inline Point3 subtract(const Point3& lhs, const Point3& rhs) noexcept
{
    return {lhs[0] - rhs[0], lhs[1] - rhs[1], lhs[2] - rhs[2]};
}

[[nodiscard]] inline Point3 cross(const Point3& lhs, const Point3& rhs) noexcept
{
    return {
        lhs[1] * rhs[2] - lhs[2] * rhs[1],
        lhs[2] * rhs[0] - lhs[0] * rhs[2],
        lhs[0] * rhs[1] - lhs[1] * rhs[0],
    };
}

[[nodiscard]] inline double dot(const Point3& lhs, const Point3& rhs) noexcept
{
    return lhs[0] * rhs[0] + lhs[1] * rhs[1] + lhs[2] * rhs[2];
}

[[nodiscard]] inline Point3 load_point(
    std::span<const double> points, std::size_t vertex) noexcept
{
    const std::size_t offset = 3U * vertex;
    return {points[offset], points[offset + 1U], points[offset + 2U]};
}

[[nodiscard]] inline Point3 load_cell_point(
    std::span<const double> outer,
    std::span<const double> inner,
    std::span<const Label> quads,
    std::size_t hex,
    int local) noexcept
{
    const std::size_t quad_slot = static_cast<std::size_t>(3 - (local % 4));
    const std::size_t vertex = static_cast<std::size_t>(quads[4U * hex + quad_slot]);
    return load_point(local < 4 ? outer : inner, vertex);
}

[[nodiscard]] inline double determinant(
    const Point3& origin,
    const Point3& first,
    const Point3& second,
    const Point3& third) noexcept
{
    return dot(
        subtract(first, origin),
        cross(subtract(second, origin), subtract(third, origin)));
}

inline void construct_inner_front(
    std::span<const double> outer,
    std::span<const double> normals,
    std::span<const double> steps,
    std::span<double> inner) noexcept
{
    for (std::size_t vertex = 0; vertex < steps.size(); ++vertex) {
        const std::size_t offset = 3U * vertex;
        const double step = steps[vertex];
        inner[offset] = outer[offset] - step * normals[offset];
        inner[offset + 1U] = outer[offset + 1U] - step * normals[offset + 1U];
        inner[offset + 2U] = outer[offset + 2U] - step * normals[offset + 2U];
    }
}

struct HexAudit {
    bool raw_negative = false;
    bool nonpositive_corner = false;
    double minimum_corner_determinant = std::numeric_limits<double>::infinity();
};

[[nodiscard]] inline HexAudit audit_hex(
    std::span<const double> outer,
    std::span<const double> inner,
    std::span<const Label> quads,
    std::size_t hex,
    double determinant_tolerance) noexcept
{
    std::array<Point3, 8> vertices{};
    for (int local = 0; local < 8; ++local) {
        vertices[static_cast<std::size_t>(local)] =
            load_cell_point(outer, inner, quads, hex, local);
    }

    double raw_volume = 0.0;
    for (const auto& tet : five_tet_fan) {
        raw_volume += determinant(
            vertices[static_cast<std::size_t>(tet[0])],
            vertices[static_cast<std::size_t>(tet[1])],
            vertices[static_cast<std::size_t>(tet[2])],
            vertices[static_cast<std::size_t>(tet[3])]);
    }

    HexAudit result;
    result.raw_negative = !std::isfinite(raw_volume) || raw_volume < -1.0e-20;
    for (std::size_t corner = 0; corner < corner_neighbors.size(); ++corner) {
        const auto& neighbors = corner_neighbors[corner];
        const double value = determinant(
            vertices[corner],
            vertices[static_cast<std::size_t>(neighbors[0])],
            vertices[static_cast<std::size_t>(neighbors[1])],
            vertices[static_cast<std::size_t>(neighbors[2])]);
        if (!std::isfinite(value)) {
            result.nonpositive_corner = true;
            result.minimum_corner_determinant = -std::numeric_limits<double>::infinity();
        } else {
            result.minimum_corner_determinant =
                std::min(result.minimum_corner_determinant, value);
            result.nonpositive_corner =
                result.nonpositive_corner || value <= determinant_tolerance;
        }
    }
    return result;
}

[[nodiscard]] inline LocalFrontResult backtrack_local_front(
    std::span<const double> outer,
    std::span<const Label> quads,
    std::span<const double> normals,
    std::span<double> steps,
    double initial_step,
    double geometry_tolerance,
    double determinant_tolerance,
    std::size_t maximum_iterations)
{
    const std::size_t vertex_count = steps.size();
    const std::size_t hex_count = quads.size() / 4U;
    std::fill(steps.begin(), steps.end(), initial_step);

    std::vector<double> inner(3U * vertex_count);
    std::vector<std::uint8_t> failing(hex_count, std::uint8_t{0});
    std::vector<std::uint8_t> affected(vertex_count, std::uint8_t{0});
    LocalFrontResult result;

    for (std::size_t iteration = 0; iteration <= maximum_iterations; ++iteration) {
        construct_inner_front(outer, normals, steps, inner);
        std::fill(failing.begin(), failing.end(), std::uint8_t{0});
        result.raw_negative_hexes = 0;
        result.nonpositive_corner_hexes = 0;
        result.minimum_corner_determinant = std::numeric_limits<double>::infinity();

        for (std::size_t hex = 0; hex < hex_count; ++hex) {
            const HexAudit audit =
                audit_hex(outer, inner, quads, hex, determinant_tolerance);
            result.raw_negative_hexes += static_cast<std::size_t>(audit.raw_negative);
            result.nonpositive_corner_hexes +=
                static_cast<std::size_t>(audit.nonpositive_corner);
            result.minimum_corner_determinant =
                std::min(result.minimum_corner_determinant, audit.minimum_corner_determinant);
            failing[hex] = static_cast<std::uint8_t>(
                audit.raw_negative || audit.nonpositive_corner);
        }

        result.iterations = iteration;
        const bool any_failure = std::any_of(
            failing.begin(), failing.end(), [](std::uint8_t value) { return value != 0U; });
        if (!any_failure) {
            result.converged = true;
            break;
        }
        if (iteration == maximum_iterations) {
            break;
        }

        std::fill(affected.begin(), affected.end(), std::uint8_t{0});
        for (std::size_t hex = 0; hex < hex_count; ++hex) {
            if (failing[hex] == 0U) {
                continue;
            }
            for (std::size_t slot = 0; slot < 4U; ++slot) {
                const std::size_t vertex =
                    static_cast<std::size_t>(quads[4U * hex + slot]);
                affected[vertex] = std::uint8_t{1};
            }
        }

        result.collapsed_vertices = 0;
        for (std::size_t vertex = 0; vertex < vertex_count; ++vertex) {
            if (affected[vertex] != 0U && steps[vertex] * 0.5 <= geometry_tolerance) {
                ++result.collapsed_vertices;
            }
        }
        if (result.collapsed_vertices != 0U) {
            break;
        }
        for (std::size_t vertex = 0; vertex < vertex_count; ++vertex) {
            if (affected[vertex] != 0U) {
                steps[vertex] *= 0.5;
            }
        }
    }

    result.reduced_vertices = static_cast<std::size_t>(std::count_if(
        steps.begin(), steps.end(),
        [initial_step](double value) { return value < initial_step; }));
    return result;
}

}  // namespace autotessell::native_hex
