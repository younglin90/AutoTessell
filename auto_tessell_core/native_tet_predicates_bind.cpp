// Exact geometric predicates used by native tetrahedral refinement.
//
// The adaptive-expansion implementation is Shewchuk's public-domain
// predicates.c, vendored by fTetWild.  This binding deliberately exposes only
// unweighted predicates.  A Cheng-Dey exudation path must not use sampled
// weights until a true regular triangulation is available.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <boost/multiprecision/cpp_int.hpp>

#include <array>
#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstddef>
#include <functional>
#include <mutex>
#include <numbers>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace py = pybind11;

extern "C" {
void exactinit();
double orient3d(double* pa, double* pb, double* pc, double* pd);
double insphere(double* pa, double* pb, double* pc, double* pd, double* pe);
}

namespace {

void ensure_exact_predicates_initialized()
{
    static std::once_flag init_once;
    std::call_once(init_once, [] { exactinit(); });
}

int sign_of(const double value)
{
    return (value > 0.0) - (value < 0.0);
}

using ExactRational = boost::multiprecision::cpp_rational;

ExactRational exact_rational_from_double(const double value)
{
    if (!std::isfinite(value)) {
        throw std::invalid_argument("exact predicate requires finite values");
    }
    if (value == 0.0) {
        return ExactRational{0};
    }

    const uint64_t bits = std::bit_cast<uint64_t>(value);
    const bool negative = (bits >> 63U) != 0U;
    const uint64_t exponent_bits = (bits >> 52U) & 0x7ffU;
    uint64_t significand = bits & ((uint64_t{1} << 52U) - 1U);
    int exponent = 0;
    if (exponent_bits == 0U) {
        exponent = 1 - 1023 - 52;
    } else {
        significand |= uint64_t{1} << 52U;
        exponent = static_cast<int>(exponent_bits) - 1023 - 52;
    }

    ExactRational result{boost::multiprecision::cpp_int{significand}};
    if (exponent >= 0) {
        result *= boost::multiprecision::cpp_int{1} << exponent;
    } else {
        result /= boost::multiprecision::cpp_int{1} << (-exponent);
    }
    return negative ? -result : result;
}

ExactRational determinant_5x5(
    std::array<std::array<ExactRational, 5>, 5> matrix)
{
    ExactRational determinant{1};
    bool negate = false;
    for (size_t column = 0; column < 5; ++column) {
        size_t pivot = column;
        while (pivot < 5 && matrix[pivot][column] == 0) {
            ++pivot;
        }
        if (pivot == 5) {
            return ExactRational{0};
        }
        if (pivot != column) {
            std::swap(matrix[pivot], matrix[column]);
            negate = !negate;
        }

        const ExactRational pivot_value = matrix[column][column];
        determinant *= pivot_value;
        for (size_t row = column + 1; row < 5; ++row) {
            if (matrix[row][column] == 0) {
                continue;
            }
            const ExactRational factor = matrix[row][column] / pivot_value;
            for (size_t next_column = column + 1; next_column < 5; ++next_column) {
                matrix[row][next_column] -= factor * matrix[column][next_column];
            }
        }
    }
    return negate ? -determinant : determinant;
}

int power_insphere_sign_exact(
    const std::array<std::array<double, 3>, 5>& points,
    const std::array<double, 5>& weights)
{
    std::array<std::array<ExactRational, 5>, 5> matrix;
    for (size_t row = 0; row < 5; ++row) {
        const ExactRational x = exact_rational_from_double(points[row][0]);
        const ExactRational y = exact_rational_from_double(points[row][1]);
        const ExactRational z = exact_rational_from_double(points[row][2]);
        const ExactRational weight = exact_rational_from_double(weights[row]);
        matrix[row] = {x, y, z, x * x + y * y + z * z - weight, ExactRational{1}};
    }
    const ExactRational determinant = determinant_5x5(std::move(matrix));
    return determinant > 0 ? 1 : (determinant < 0 ? -1 : 0);
}

template <size_t PointCount, typename Predicate>
py::array_t<int> evaluate_signs(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    Predicate predicate,
    const char* name)
{
    if (points.ndim() != 3 || points.shape(1) != static_cast<py::ssize_t>(PointCount)
        || points.shape(2) != 3) {
        throw std::invalid_argument(
            std::string(name) + " expects an array shaped (N, "
            + std::to_string(PointCount) + ", 3)");
    }

    ensure_exact_predicates_initialized();
    const auto input = points.unchecked<3>();
    const auto count = input.shape(0);
    py::array_t<int> result({count});
    auto output = result.mutable_unchecked<1>();

    for (py::ssize_t index = 0; index < count; ++index) {
        double vertices[PointCount][3];
        for (size_t vertex = 0; vertex < PointCount; ++vertex) {
            for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
                const double value = input(index, static_cast<py::ssize_t>(vertex),
                                           static_cast<py::ssize_t>(coordinate));
                if (!std::isfinite(value)) {
                    throw std::invalid_argument(
                        std::string(name) + " requires finite coordinates");
                }
                vertices[vertex][coordinate] = value;
            }
        }
        output(index) = sign_of(predicate(vertices));
    }
    return result;
}

py::array_t<int> orient3d_signs(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points)
{
    return evaluate_signs<4>(
        points,
        [](double (&vertices)[4][3]) {
            return orient3d(vertices[0], vertices[1], vertices[2], vertices[3]);
        },
        "orient3d_signs");
}

py::array_t<int> insphere_signs(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points)
{
    return evaluate_signs<5>(
        points,
        [](double (&vertices)[5][3]) {
            return insphere(
                vertices[0], vertices[1], vertices[2], vertices[3], vertices[4]);
        },
        "insphere_signs");
}

py::array_t<int> power_insphere_signs_exact(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& weights)
{
    if (points.ndim() != 3 || points.shape(1) != 5 || points.shape(2) != 3) {
        throw std::invalid_argument(
            "power_insphere_signs_exact expects points shaped (N, 5, 3)");
    }
    if (weights.ndim() != 2 || weights.shape(0) != points.shape(0)
        || weights.shape(1) != 5) {
        throw std::invalid_argument(
            "power_insphere_signs_exact expects weights shaped (N, 5)");
    }

    const auto input_points = points.unchecked<3>();
    const auto input_weights = weights.unchecked<2>();
    const auto count = input_points.shape(0);
    py::array_t<int> result({count});
    auto output = result.mutable_unchecked<1>();

    for (py::ssize_t index = 0; index < count; ++index) {
        std::array<std::array<double, 3>, 5> row_points;
        std::array<double, 5> row_weights;
        for (size_t row = 0; row < 5; ++row) {
            for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
                row_points[row][coordinate] = input_points(
                    index, static_cast<py::ssize_t>(row),
                    static_cast<py::ssize_t>(coordinate));
            }
            row_weights[row] = input_weights(index, static_cast<py::ssize_t>(row));
        }
        output(index) = power_insphere_sign_exact(row_points, row_weights);
    }
    return result;
}

struct FaceKey {
    std::array<long long, 3> vertices;

    bool operator==(const FaceKey& other) const = default;
};

struct FaceKeyHash {
    size_t operator()(const FaceKey& face) const
    {
        size_t hash = 0;
        for (const long long vertex : face.vertices) {
            hash ^= std::hash<long long>{}(vertex) + 0x9e3779b9U + (hash << 6U)
                + (hash >> 2U);
        }
        return hash;
    }
};

struct EdgeKey {
    std::array<long long, 2> vertices;

    bool operator==(const EdgeKey& other) const = default;
};

struct EdgeKeyHash {
    size_t operator()(const EdgeKey& edge) const
    {
        return std::hash<long long>{}(edge.vertices[0])
            ^ (std::hash<long long>{}(edge.vertices[1]) << 1U);
    }
};

using Tet = std::array<long long, 4>;

FaceKey make_face_key(const Tet& tet, const size_t excluded)
{
    FaceKey key{};
    size_t output = 0;
    for (size_t local = 0; local < 4; ++local) {
        if (local != excluded) {
            key.vertices[output++] = tet[local];
        }
    }
    std::sort(key.vertices.begin(), key.vertices.end());
    return key;
}

bool has_distinct_valid_indices(const Tet& tet, const py::ssize_t point_count)
{
    Tet sorted = tet;
    std::sort(sorted.begin(), sorted.end());
    return sorted.front() >= 0 && sorted.back() < point_count
        && std::adjacent_find(sorted.begin(), sorted.end()) == sorted.end();
}

int orient3d_shewchuk_sign(
    const py::detail::unchecked_reference<double, 2>& points,
    const Tet& tet)
{
    double vertices[4][3];
    for (size_t local = 0; local < 4; ++local) {
        for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
            vertices[local][coordinate] = points(tet[local], coordinate);
        }
    }
    return sign_of(orient3d(vertices[0], vertices[1], vertices[2], vertices[3]));
}

long double absolute_volume6(
    const py::detail::unchecked_reference<double, 2>& points,
    const Tet& tet)
{
    const auto point = [&](const size_t local, const size_t coordinate) {
        return static_cast<long double>(points(tet[local], coordinate));
    };
    const long double abx = point(1, 0) - point(0, 0);
    const long double aby = point(1, 1) - point(0, 1);
    const long double abz = point(1, 2) - point(0, 2);
    const long double acx = point(2, 0) - point(0, 0);
    const long double acy = point(2, 1) - point(0, 1);
    const long double acz = point(2, 2) - point(0, 2);
    const long double adx = point(3, 0) - point(0, 0);
    const long double ady = point(3, 1) - point(0, 1);
    const long double adz = point(3, 2) - point(0, 2);
    const long double determinant = abx * (acy * adz - acz * ady)
        - aby * (acx * adz - acz * adx) + abz * (acx * ady - acy * adx);
    return std::abs(determinant);
}

double tet_mean_ratio_quality(
    const py::detail::unchecked_reference<double, 2>& points,
    const Tet& tet)
{
    long double edge_sq_sum = 0.0L;
    for (size_t first = 0; first < 4; ++first) {
        for (size_t second = first + 1; second < 4; ++second) {
            long double squared = 0.0L;
            for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
                const long double delta = static_cast<long double>(points(tet[first], coordinate))
                    - static_cast<long double>(points(tet[second], coordinate));
                squared += delta * delta;
            }
            edge_sq_sum += squared;
        }
    }
    if (edge_sq_sum <= 1e-30L) {
        return 0.0;
    }
    const long double volume = absolute_volume6(points, tet) / 6.0L;
    const long double quality = 12.0L * std::pow(3.0L * volume, 2.0L / 3.0L)
        / edge_sq_sum;
    return static_cast<double>(std::clamp(quality, 0.0L, 1.0L));
}

py::tuple tet_quality_metrics(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array)
{
    if (points_array.ndim() != 2 || points_array.shape(1) != 3) {
        throw std::invalid_argument("tet_quality_metrics expects points shaped (N, 3)");
    }
    if (tets_array.ndim() != 2 || tets_array.shape(1) != 4) {
        throw std::invalid_argument("tet_quality_metrics expects tets shaped (M, 4)");
    }

    const auto points = points_array.unchecked<2>();
    const auto tets = tets_array.unchecked<2>();
    const auto count = tets.shape(0);
    for (py::ssize_t row = 0; row < count; ++row) {
        Tet tet{};
        for (size_t local = 0; local < 4; ++local) {
            tet[local] = tets(row, static_cast<py::ssize_t>(local));
        }
        if (!has_distinct_valid_indices(tet, points.shape(0))) {
            throw std::invalid_argument("tet_quality_metrics received invalid tet indices");
        }
    }

    py::array_t<double> shape_quality({count});
    py::array_t<double> aspect_ratio({count});
    py::array_t<double> min_dihedral_deg({count});
    py::array_t<double> volume6({count});
    auto quality_out = shape_quality.mutable_unchecked<1>();
    auto aspect_out = aspect_ratio.mutable_unchecked<1>();
    auto dihedral_out = min_dihedral_deg.mutable_unchecked<1>();
    auto volume_out = volume6.mutable_unchecked<1>();

    const auto subtract = [](const std::array<double, 3>& left,
                             const std::array<double, 3>& right) {
        return std::array<double, 3>{
            left[0] - right[0], left[1] - right[1], left[2] - right[2]};
    };
    const auto dot = [](const std::array<double, 3>& left,
                        const std::array<double, 3>& right) {
        return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
    };
    const auto cross = [](const std::array<double, 3>& left,
                          const std::array<double, 3>& right) {
        return std::array<double, 3>{
            left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0]};
    };
    const auto norm = [&](const std::array<double, 3>& vector) {
        return std::sqrt(dot(vector, vector));
    };
    const auto face_area = [&](const std::array<double, 3>& first,
                               const std::array<double, 3>& second,
                               const std::array<double, 3>& third) {
        return 0.5 * norm(cross(subtract(second, first), subtract(third, first)));
    };
    const auto unit_normal = [&](const std::array<double, 3>& first,
                                 const std::array<double, 3>& second,
                                 const std::array<double, 3>& third) {
        auto normal = cross(subtract(second, first), subtract(third, first));
        const double normal_length = norm(normal);
        if (normal_length > 1e-30) {
            normal[0] /= normal_length;
            normal[1] /= normal_length;
            normal[2] /= normal_length;
        }
        return normal;
    };
    const auto dihedral = [&](const std::array<double, 3>& first,
                              const std::array<double, 3>& second) {
        const double cosine = std::clamp(dot(first, second), -1.0, 1.0);
        return 180.0 - std::acos(cosine) * 180.0 / std::numbers::pi_v<double>;
    };

    {
    py::gil_scoped_release release;
    for (py::ssize_t row = 0; row < count; ++row) {
        std::array<std::array<double, 3>, 4> vertex{};
        for (size_t local = 0; local < 4; ++local) {
            const auto index = tets(row, static_cast<py::ssize_t>(local));
            for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
                vertex[local][coordinate] = points(index, static_cast<py::ssize_t>(coordinate));
            }
        }

        const std::array<std::array<double, 3>, 6> edges = {{
            subtract(vertex[1], vertex[0]), subtract(vertex[2], vertex[0]),
            subtract(vertex[3], vertex[0]), subtract(vertex[2], vertex[1]),
            subtract(vertex[3], vertex[1]), subtract(vertex[3], vertex[2])}};
        double longest_edge = 0.0;
        for (const auto& edge : edges) {
            longest_edge = std::max(longest_edge, norm(edge));
        }
        const double signed_volume6 = dot(edges[0], cross(edges[1], edges[2]));
        const double absolute_volume6 = std::abs(signed_volume6);
        const double volume = absolute_volume6 / 6.0;
        volume_out(row) = absolute_volume6;
        quality_out(row) = longest_edge > 1e-30
            ? 8.48 * volume / (longest_edge * longest_edge * longest_edge)
            : 0.0;

        const double surface_area = face_area(vertex[0], vertex[1], vertex[2])
            + face_area(vertex[0], vertex[1], vertex[3])
            + face_area(vertex[0], vertex[2], vertex[3])
            + face_area(vertex[1], vertex[2], vertex[3]);
        const double inradius = surface_area > 1e-30 ? 3.0 * volume / surface_area : 0.0;
        aspect_out(row) = inradius > 1e-30 ? (longest_edge / 2.0) / inradius : 1e6;

        const auto n_abc = unit_normal(vertex[0], vertex[1], vertex[2]);
        const auto n_abd = unit_normal(vertex[0], vertex[1], vertex[3]);
        const auto n_acd = unit_normal(vertex[0], vertex[2], vertex[3]);
        const auto n_bcd = unit_normal(vertex[1], vertex[2], vertex[3]);
        dihedral_out(row) = std::min({
            dihedral(n_abc, n_abd), dihedral(n_abc, n_acd), dihedral(n_abd, n_acd),
            dihedral(n_abc, n_bcd), dihedral(n_abd, n_bcd), dihedral(n_acd, n_bcd)});
    }
    }
    return py::make_tuple(shape_quality, aspect_ratio, min_dihedral_deg, volume6);
}

void orient_positive(
    const py::detail::unchecked_reference<double, 2>& points,
    Tet& tet)
{
    // Native-tet's signed-volume convention is opposite Shewchuk orient3d.
    if (orient3d_shewchuk_sign(points, tet) > 0) {
        std::swap(tet[2], tet[3]);
    }
}

py::tuple regularize_weighted_23(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& weights_array,
    const int max_passes)
{
    if (points_array.ndim() != 2 || points_array.shape(1) != 3) {
        throw std::invalid_argument("regularize_weighted_23 expects points shaped (N, 3)");
    }
    if (tets_array.ndim() != 2 || tets_array.shape(1) != 4) {
        throw std::invalid_argument("regularize_weighted_23 expects tets shaped (M, 4)");
    }
    if (weights_array.ndim() != 1 || weights_array.shape(0) != points_array.shape(0)) {
        throw std::invalid_argument("regularize_weighted_23 expects weights shaped (N,)");
    }
    if (max_passes < 0) {
        throw std::invalid_argument("max_passes must be non-negative");
    }

    ensure_exact_predicates_initialized();
    const auto points = points_array.unchecked<2>();
    const auto input_tets = tets_array.unchecked<2>();
    const auto weights = weights_array.unchecked<1>();
    std::vector<Tet> tets;
    tets.reserve(static_cast<size_t>(input_tets.shape(0)));
    for (py::ssize_t row = 0; row < input_tets.shape(0); ++row) {
        Tet tet{};
        for (size_t local = 0; local < 4; ++local) {
            tet[local] = input_tets(row, static_cast<py::ssize_t>(local));
        }
        if (!has_distinct_valid_indices(tet, points.shape(0))) {
            throw std::invalid_argument("regularize_weighted_23 received invalid tet indices");
        }
        orient_positive(points, tet);
        if (orient3d_shewchuk_sign(points, tet) == 0) {
            throw std::invalid_argument("regularize_weighted_23 received degenerate tet");
        }
        tets.push_back(tet);
    }

    int applied = 0;
    int passes = 0;
    for (; passes < max_passes; ++passes) {
        std::unordered_map<FaceKey, std::vector<size_t>, FaceKeyHash> owners;
        owners.reserve(tets.size() * 4U);
        for (size_t tet_index = 0; tet_index < tets.size(); ++tet_index) {
            for (size_t excluded = 0; excluded < 4; ++excluded) {
                owners[make_face_key(tets[tet_index], excluded)].push_back(tet_index);
            }
        }

        bool changed = false;
        for (const auto& [face, face_owners] : owners) {
            if (face_owners.size() != 2) {
                continue;
            }
            const size_t first_index = face_owners[0];
            const size_t second_index = face_owners[1];
            const Tet first = tets[first_index];
            const Tet second = tets[second_index];
            long long first_apex = -1;
            long long second_apex = -1;
            for (const long long vertex : first) {
                if (!std::binary_search(face.vertices.begin(), face.vertices.end(), vertex)) {
                    first_apex = vertex;
                    break;
                }
            }
            for (const long long vertex : second) {
                if (!std::binary_search(face.vertices.begin(), face.vertices.end(), vertex)) {
                    second_apex = vertex;
                    break;
                }
            }
            if (first_apex < 0 || second_apex < 0 || first_apex == second_apex) {
                continue;
            }

            const Tet side_first = {
                face.vertices[0], face.vertices[1], face.vertices[2], first_apex};
            const Tet side_second = {
                face.vertices[0], face.vertices[1], face.vertices[2], second_apex};
            const int first_side = orient3d_shewchuk_sign(points, side_first);
            const int second_side = orient3d_shewchuk_sign(points, side_second);
            if (first_side == 0 || second_side == 0 || first_side == second_side) {
                continue;
            }

            std::array<std::array<double, 3>, 5> power_points{};
            std::array<double, 5> power_weights{};
            const std::array<long long, 5> indices = {
                face.vertices[0], face.vertices[1], face.vertices[2], first_apex, second_apex};
            for (size_t index = 0; index < 5; ++index) {
                for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
                    power_points[index][coordinate] = points(indices[index], coordinate);
                }
                power_weights[index] = weights(indices[index]);
            }
            const int power_sign = power_insphere_sign_exact(power_points, power_weights);
            if (power_sign == 0 || power_sign * first_side <= 0) {
                continue;
            }

            std::array<Tet, 3> replacements = {{
                {face.vertices[0], face.vertices[1], first_apex, second_apex},
                {face.vertices[1], face.vertices[2], first_apex, second_apex},
                {face.vertices[2], face.vertices[0], first_apex, second_apex},
            }};
            for (Tet& replacement : replacements) {
                orient_positive(points, replacement);
            }
            if (std::any_of(replacements.begin(), replacements.end(), [&](const Tet& tet) {
                    return orient3d_shewchuk_sign(points, tet) == 0;
                })) {
                continue;
            }

            const long double old_volume = absolute_volume6(points, first)
                + absolute_volume6(points, second);
            const long double new_volume = absolute_volume6(points, replacements[0])
                + absolute_volume6(points, replacements[1])
                + absolute_volume6(points, replacements[2]);
            if (std::abs(old_volume - new_volume) > 1e-12L * std::max(1.0L, old_volume)) {
                continue;
            }

            tets[first_index] = replacements[0];
            tets[second_index] = replacements[1];
            tets.push_back(replacements[2]);
            ++applied;
            changed = true;
            break;
        }
        if (!changed) {
            break;
        }
    }

    py::array_t<long long> output({static_cast<py::ssize_t>(tets.size()), py::ssize_t{4}});
    auto output_view = output.mutable_unchecked<2>();
    for (size_t row = 0; row < tets.size(); ++row) {
        for (size_t local = 0; local < 4; ++local) {
            output_view(static_cast<py::ssize_t>(row), static_cast<py::ssize_t>(local)) = tets[row][local];
        }
    }
    py::dict stats;
    stats["applied"] = applied;
    stats["passes"] = passes;
    return py::make_tuple(output, stats);
}

py::tuple regularize_weighted_32(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& weights_array,
    const int max_passes)
{
    if (points_array.ndim() != 2 || points_array.shape(1) != 3) {
        throw std::invalid_argument("regularize_weighted_32 expects points shaped (N, 3)");
    }
    if (tets_array.ndim() != 2 || tets_array.shape(1) != 4) {
        throw std::invalid_argument("regularize_weighted_32 expects tets shaped (M, 4)");
    }
    if (weights_array.ndim() != 1 || weights_array.shape(0) != points_array.shape(0)) {
        throw std::invalid_argument("regularize_weighted_32 expects weights shaped (N,)");
    }
    if (max_passes < 0) {
        throw std::invalid_argument("max_passes must be non-negative");
    }

    ensure_exact_predicates_initialized();
    const auto points = points_array.unchecked<2>();
    const auto input_tets = tets_array.unchecked<2>();
    const auto weights = weights_array.unchecked<1>();
    std::vector<Tet> tets;
    tets.reserve(static_cast<size_t>(input_tets.shape(0)));
    for (py::ssize_t row = 0; row < input_tets.shape(0); ++row) {
        Tet tet{};
        for (size_t local = 0; local < 4; ++local) {
            tet[local] = input_tets(row, static_cast<py::ssize_t>(local));
        }
        if (!has_distinct_valid_indices(tet, points.shape(0))) {
            throw std::invalid_argument("regularize_weighted_32 received invalid tet indices");
        }
        orient_positive(points, tet);
        if (orient3d_shewchuk_sign(points, tet) == 0) {
            throw std::invalid_argument("regularize_weighted_32 received degenerate tet");
        }
        tets.push_back(tet);
    }

    int applied = 0;
    int passes = 0;
    for (; passes < max_passes; ++passes) {
        std::unordered_map<EdgeKey, std::vector<size_t>, EdgeKeyHash> edge_owners;
        edge_owners.reserve(tets.size() * 6U);
        for (size_t tet_index = 0; tet_index < tets.size(); ++tet_index) {
            for (size_t first = 0; first < 4; ++first) {
                for (size_t second = first + 1; second < 4; ++second) {
                    auto edge = EdgeKey{{
                        tets[tet_index][first], tets[tet_index][second]}};
                    std::sort(edge.vertices.begin(), edge.vertices.end());
                    edge_owners[edge].push_back(tet_index);
                }
            }
        }

        bool changed = false;
        for (const auto& [edge, owners] : edge_owners) {
            if (owners.size() != 3) {
                continue;
            }
            std::array<long long, 3> outer{};
            size_t outer_count = 0;
            bool malformed = false;
            for (const size_t tet_index : owners) {
                for (const long long vertex : tets[tet_index]) {
                    if (vertex == edge.vertices[0] || vertex == edge.vertices[1]) {
                        continue;
                    }
                    if (std::find(outer.begin(), outer.begin() + outer_count, vertex)
                        == outer.begin() + outer_count) {
                        if (outer_count == outer.size()) {
                            malformed = true;
                            break;
                        }
                        outer[outer_count++] = vertex;
                    }
                }
                if (malformed) {
                    break;
                }
            }
            if (malformed || outer_count != outer.size()) {
                continue;
            }
            std::sort(outer.begin(), outer.end());

            // A boundary edge has a path-shaped link, not this three-vertex
            // cycle.  Requiring all three pair combinations prevents a 3-2
            // operation from touching a partial/non-manifold edge star.
            bool cycle = true;
            for (size_t first = 0; first < outer.size() && cycle; ++first) {
                for (size_t second = first + 1; second < outer.size(); ++second) {
                    bool found = false;
                    for (const size_t tet_index : owners) {
                        const Tet& tet = tets[tet_index];
                        const bool has_first = std::find(tet.begin(), tet.end(), outer[first])
                            != tet.end();
                        const bool has_second = std::find(tet.begin(), tet.end(), outer[second])
                            != tet.end();
                        if (has_first && has_second) {
                            found = true;
                            break;
                        }
                    }
                    cycle = found;
                }
            }
            if (!cycle) {
                continue;
            }

            const Tet side_first = {outer[0], outer[1], outer[2], edge.vertices[0]};
            const Tet side_second = {outer[0], outer[1], outer[2], edge.vertices[1]};
            const int first_side = orient3d_shewchuk_sign(points, side_first);
            const int second_side = orient3d_shewchuk_sign(points, side_second);
            if (first_side == 0 || second_side == 0 || first_side == second_side) {
                continue;
            }

            std::array<std::array<double, 3>, 5> power_points{};
            std::array<double, 5> power_weights{};
            const std::array<long long, 5> indices = {
                outer[0], outer[1], outer[2], edge.vertices[0], edge.vertices[1]};
            for (size_t index = 0; index < indices.size(); ++index) {
                for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
                    power_points[index][coordinate] = points(indices[index], coordinate);
                }
                power_weights[index] = weights(indices[index]);
            }
            const int power_sign = power_insphere_sign_exact(power_points, power_weights);
            // Exact inverse of 2-3: choose two base-face tetrahedra only when
            // their weighted circumsphere is locally regular.
            if (power_sign == 0 || power_sign * first_side >= 0) {
                continue;
            }

            std::array<Tet, 2> replacements = {{
                {outer[0], outer[1], outer[2], edge.vertices[0]},
                {outer[0], outer[2], outer[1], edge.vertices[1]},
            }};
            for (Tet& replacement : replacements) {
                orient_positive(points, replacement);
            }
            if (std::any_of(replacements.begin(), replacements.end(), [&](const Tet& tet) {
                    return orient3d_shewchuk_sign(points, tet) == 0;
                })) {
                continue;
            }

            long double old_volume = 0.0L;
            for (const size_t tet_index : owners) {
                old_volume += absolute_volume6(points, tets[tet_index]);
            }
            const long double new_volume = absolute_volume6(points, replacements[0])
                + absolute_volume6(points, replacements[1]);
            if (std::abs(old_volume - new_volume) > 1e-12L * std::max(1.0L, old_volume)) {
                continue;
            }

            tets[owners[0]] = replacements[0];
            tets[owners[1]] = replacements[1];
            tets[owners[2]] = tets.back();
            tets.pop_back();
            ++applied;
            changed = true;
            break;
        }
        if (!changed) {
            break;
        }
    }

    py::array_t<long long> output({static_cast<py::ssize_t>(tets.size()), py::ssize_t{4}});
    auto output_view = output.mutable_unchecked<2>();
    for (size_t row = 0; row < tets.size(); ++row) {
        for (size_t local = 0; local < 4; ++local) {
            output_view(static_cast<py::ssize_t>(row), static_cast<py::ssize_t>(local)) = tets[row][local];
        }
    }
    py::dict stats;
    stats["applied"] = applied;
    stats["passes"] = passes;
    return py::make_tuple(output, stats);
}

py::tuple recover_targeted_edges_23(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& edges_array,
    const int max_attempts)
{
    if (points_array.ndim() != 2 || points_array.shape(1) != 3) {
        throw std::invalid_argument("recover_targeted_edges_23 expects points shaped (N, 3)");
    }
    if (tets_array.ndim() != 2 || tets_array.shape(1) != 4) {
        throw std::invalid_argument("recover_targeted_edges_23 expects tets shaped (M, 4)");
    }
    if (edges_array.ndim() != 2 || edges_array.shape(1) != 2 || max_attempts < 0) {
        throw std::invalid_argument("recover_targeted_edges_23 received invalid edges or limits");
    }

    ensure_exact_predicates_initialized();
    const auto points = points_array.unchecked<2>();
    const auto input_tets = tets_array.unchecked<2>();
    const auto requested_edges = edges_array.unchecked<2>();
    std::vector<Tet> tets;
    tets.reserve(static_cast<size_t>(input_tets.shape(0)) + static_cast<size_t>(max_attempts));
    for (py::ssize_t row = 0; row < input_tets.shape(0); ++row) {
        Tet tet{};
        for (size_t local = 0; local < 4; ++local) {
            tet[local] = input_tets(row, static_cast<py::ssize_t>(local));
        }
        if (!has_distinct_valid_indices(tet, points.shape(0))) {
            throw std::invalid_argument("recover_targeted_edges_23 received invalid tet indices");
        }
        orient_positive(points, tet);
        if (orient3d_shewchuk_sign(points, tet) == 0) {
            throw std::invalid_argument("recover_targeted_edges_23 received degenerate tet");
        }
        tets.push_back(tet);
    }

    const auto contains = [](const Tet& tet, const long long vertex) {
        return std::find(tet.begin(), tet.end(), vertex) != tet.end();
    };
    int attempted = 0;
    int recovered = 0;
    const py::ssize_t request_count = std::min<py::ssize_t>(
        requested_edges.shape(0), static_cast<py::ssize_t>(max_attempts));
    for (py::ssize_t request = 0; request < request_count; ++request) {
        const long long u = requested_edges(request, 0);
        const long long v = requested_edges(request, 1);
        if (u < 0 || v < 0 || u >= points.shape(0) || v >= points.shape(0) || u == v) {
            throw std::invalid_argument("recover_targeted_edges_23 received invalid requested edge");
        }
        ++attempted;
        if (std::any_of(tets.begin(), tets.end(), [&](const Tet& tet) {
                return contains(tet, u) && contains(tet, v);
            })) {
            ++recovered;
            continue;
        }

        std::unordered_map<FaceKey, std::vector<size_t>, FaceKeyHash> owners;
        owners.reserve(tets.size() * 4U);
        for (size_t index = 0; index < tets.size(); ++index) {
            for (size_t excluded = 0; excluded < 4; ++excluded) {
                owners[make_face_key(tets[index], excluded)].push_back(index);
            }
        }
        bool changed = false;
        for (const auto& [face, face_owners] : owners) {
            if (face_owners.size() != 2) {
                continue;
            }
            const Tet first = tets[face_owners[0]];
            const Tet second = tets[face_owners[1]];
            long long first_apex = -1;
            long long second_apex = -1;
            for (const long long vertex : first) {
                if (!std::binary_search(face.vertices.begin(), face.vertices.end(), vertex)) {
                    first_apex = vertex;
                }
            }
            for (const long long vertex : second) {
                if (!std::binary_search(face.vertices.begin(), face.vertices.end(), vertex)) {
                    second_apex = vertex;
                }
            }
            if (!((first_apex == u && second_apex == v)
                  || (first_apex == v && second_apex == u))) {
                continue;
            }
            const Tet first_side_tet = {
                face.vertices[0], face.vertices[1], face.vertices[2], first_apex};
            const Tet second_side_tet = {
                face.vertices[0], face.vertices[1], face.vertices[2], second_apex};
            const int first_side = orient3d_shewchuk_sign(points, first_side_tet);
            const int second_side = orient3d_shewchuk_sign(points, second_side_tet);
            if (first_side == 0 || second_side == 0 || first_side == second_side) {
                continue;
            }
            std::array<Tet, 3> replacements = {{
                {face.vertices[0], face.vertices[1], first_apex, second_apex},
                {face.vertices[1], face.vertices[2], first_apex, second_apex},
                {face.vertices[2], face.vertices[0], first_apex, second_apex},
            }};
            for (Tet& replacement : replacements) {
                orient_positive(points, replacement);
            }
            if (std::any_of(replacements.begin(), replacements.end(), [&](const Tet& tet) {
                    return orient3d_shewchuk_sign(points, tet) == 0;
                })) {
                continue;
            }
            const long double old_volume = absolute_volume6(points, first)
                + absolute_volume6(points, second);
            const long double new_volume = absolute_volume6(points, replacements[0])
                + absolute_volume6(points, replacements[1])
                + absolute_volume6(points, replacements[2]);
            if (std::abs(old_volume - new_volume) > 1e-12L * std::max(1.0L, old_volume)) {
                continue;
            }
            tets[face_owners[0]] = replacements[0];
            tets[face_owners[1]] = replacements[1];
            tets.push_back(replacements[2]);
            ++recovered;
            changed = true;
            break;
        }
        (void)changed;
    }

    py::array_t<long long> output({static_cast<py::ssize_t>(tets.size()), py::ssize_t{4}});
    auto output_view = output.mutable_unchecked<2>();
    for (size_t row = 0; row < tets.size(); ++row) {
        for (size_t local = 0; local < 4; ++local) {
            output_view(static_cast<py::ssize_t>(row), static_cast<py::ssize_t>(local)) = tets[row][local];
        }
    }
    py::dict stats;
    stats["attempted"] = attempted;
    stats["recovered"] = recovered;
    return py::make_tuple(output, stats);
}

py::tuple flip_44_quality(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array,
    const int max_passes,
    const double min_quality_improvement)
{
    if (points_array.ndim() != 2 || points_array.shape(1) != 3) {
        throw std::invalid_argument("flip_44_quality expects points shaped (N, 3)");
    }
    if (tets_array.ndim() != 2 || tets_array.shape(1) != 4) {
        throw std::invalid_argument("flip_44_quality expects tets shaped (M, 4)");
    }
    if (max_passes < 0 || min_quality_improvement < 0.0) {
        throw std::invalid_argument("flip_44_quality received invalid limits");
    }

    ensure_exact_predicates_initialized();
    const auto points = points_array.unchecked<2>();
    const auto input_tets = tets_array.unchecked<2>();
    std::vector<Tet> tets;
    tets.reserve(static_cast<size_t>(input_tets.shape(0)));
    for (py::ssize_t row = 0; row < input_tets.shape(0); ++row) {
        Tet tet{};
        for (size_t local = 0; local < 4; ++local) {
            tet[local] = input_tets(row, static_cast<py::ssize_t>(local));
        }
        if (!has_distinct_valid_indices(tet, points.shape(0))) {
            throw std::invalid_argument("flip_44_quality received invalid tet indices");
        }
        orient_positive(points, tet);
        if (orient3d_shewchuk_sign(points, tet) == 0) {
            throw std::invalid_argument("flip_44_quality received degenerate tet");
        }
        tets.push_back(tet);
    }

    int applied = 0;
    int passes = 0;
    for (; passes < max_passes; ++passes) {
        std::unordered_map<EdgeKey, std::vector<size_t>, EdgeKeyHash> edge_owners;
        edge_owners.reserve(tets.size() * 6U);
        for (size_t tet_index = 0; tet_index < tets.size(); ++tet_index) {
            for (size_t first = 0; first < 4; ++first) {
                for (size_t second = first + 1; second < 4; ++second) {
                    EdgeKey edge{{tets[tet_index][first], tets[tet_index][second]}};
                    std::sort(edge.vertices.begin(), edge.vertices.end());
                    edge_owners[edge].push_back(tet_index);
                }
            }
        }

        bool changed = false;
        for (const auto& [edge, owners] : edge_owners) {
            if (owners.size() != 4) {
                continue;
            }
            std::unordered_map<long long, std::vector<long long>> adjacency;
            bool malformed = false;
            for (const size_t tet_index : owners) {
                std::array<long long, 2> opposite{};
                size_t opposite_count = 0;
                for (const long long vertex : tets[tet_index]) {
                    if (vertex != edge.vertices[0] && vertex != edge.vertices[1]) {
                        if (opposite_count == opposite.size()) {
                            malformed = true;
                            break;
                        }
                        opposite[opposite_count++] = vertex;
                    }
                }
                if (malformed || opposite_count != opposite.size() || opposite[0] == opposite[1]) {
                    malformed = true;
                    break;
                }
                adjacency[opposite[0]].push_back(opposite[1]);
                adjacency[opposite[1]].push_back(opposite[0]);
            }
            if (malformed || adjacency.size() != 4) {
                continue;
            }
            bool cycle = true;
            for (const auto& [vertex, neighbors] : adjacency) {
                (void)vertex;
                if (neighbors.size() != 2 || neighbors[0] == neighbors[1]) {
                    cycle = false;
                    break;
                }
            }
            if (!cycle) {
                continue;
            }

            std::vector<long long> ring;
            ring.reserve(4);
            long long start = adjacency.begin()->first;
            for (const auto& [vertex, neighbors] : adjacency) {
                (void)neighbors;
                start = std::min(start, vertex);
            }
            long long previous = start;
            long long current = std::min(adjacency.at(start)[0], adjacency.at(start)[1]);
            ring.push_back(start);
            for (size_t count = 1; count < 4; ++count) {
                if (std::find(ring.begin(), ring.end(), current) != ring.end()) {
                    cycle = false;
                    break;
                }
                ring.push_back(current);
                const auto& neighbors = adjacency.at(current);
                const long long next = neighbors[0] == previous ? neighbors[1] : neighbors[0];
                previous = current;
                current = next;
            }
            if (!cycle || current != start || ring.size() != 4) {
                continue;
            }

            double old_min_quality = 1.0;
            long double old_volume = 0.0L;
            for (const size_t tet_index : owners) {
                old_min_quality = std::min(old_min_quality,
                    tet_mean_ratio_quality(points, tets[tet_index]));
                old_volume += absolute_volume6(points, tets[tet_index]);
            }

            std::array<std::array<Tet, 4>, 2> candidates = {{
                {{{ring[0], ring[2], edge.vertices[0], ring[1]},
                  {ring[0], ring[2], ring[1], edge.vertices[1]},
                  {ring[0], ring[2], edge.vertices[1], ring[3]},
                  {ring[0], ring[2], ring[3], edge.vertices[0]}}},
                {{{ring[1], ring[3], edge.vertices[0], ring[2]},
                  {ring[1], ring[3], ring[2], edge.vertices[1]},
                  {ring[1], ring[3], edge.vertices[1], ring[0]},
                  {ring[1], ring[3], ring[0], edge.vertices[0]}}},
            }};
            std::array<Tet, 4> best{};
            double best_min_quality = old_min_quality;
            bool found = false;
            for (auto candidate : candidates) {
                bool valid = true;
                long double new_volume = 0.0L;
                double new_min_quality = 1.0;
                for (Tet& tet : candidate) {
                    orient_positive(points, tet);
                    if (orient3d_shewchuk_sign(points, tet) == 0) {
                        valid = false;
                        break;
                    }
                    new_volume += absolute_volume6(points, tet);
                    new_min_quality = std::min(new_min_quality,
                        tet_mean_ratio_quality(points, tet));
                }
                if (!valid
                    || std::abs(old_volume - new_volume)
                        > 1e-12L * std::max(1.0L, old_volume)
                    || new_min_quality < old_min_quality + min_quality_improvement) {
                    continue;
                }
                if (!found || new_min_quality > best_min_quality) {
                    best = candidate;
                    best_min_quality = new_min_quality;
                    found = true;
                }
            }
            if (!found) {
                continue;
            }

            for (size_t index = 0; index < owners.size(); ++index) {
                tets[owners[index]] = best[index];
            }
            ++applied;
            changed = true;
            break;
        }
        if (!changed) {
            break;
        }
    }

    py::array_t<long long> output({static_cast<py::ssize_t>(tets.size()), py::ssize_t{4}});
    auto output_view = output.mutable_unchecked<2>();
    for (size_t row = 0; row < tets.size(); ++row) {
        for (size_t local = 0; local < 4; ++local) {
            output_view(static_cast<py::ssize_t>(row), static_cast<py::ssize_t>(local)) = tets[row][local];
        }
    }
    py::dict stats;
    stats["applied"] = applied;
    stats["passes"] = passes;
    return py::make_tuple(output, stats);
}

}  // namespace

PYBIND11_MODULE(native_tet_predicates, m)
{
    m.doc() = "Exact adaptive predicates for AutoTessell native tetrahedral meshing.";
    m.def("orient3d_signs", &orient3d_signs, py::arg("points"));
    m.def("insphere_signs", &insphere_signs, py::arg("points"));
    m.def("power_insphere_signs_exact", &power_insphere_signs_exact,
          py::arg("points"), py::arg("weights"));
    m.def("regularize_weighted_23", &regularize_weighted_23,
          py::arg("points"), py::arg("tets"), py::arg("weights"),
          py::arg("max_passes") = 32);
    m.def("regularize_weighted_32", &regularize_weighted_32,
          py::arg("points"), py::arg("tets"), py::arg("weights"),
          py::arg("max_passes") = 32);
    m.def("flip_44_quality", &flip_44_quality,
          py::arg("points"), py::arg("tets"), py::arg("max_passes") = 32,
          py::arg("min_quality_improvement") = 1e-4);
    m.def("tet_quality_metrics", &tet_quality_metrics,
          py::arg("points"), py::arg("tets"));
    m.def("recover_targeted_edges_23", &recover_targeted_edges_23,
          py::arg("points"), py::arg("tets"), py::arg("edges"),
          py::arg("max_attempts") = 200);
}
