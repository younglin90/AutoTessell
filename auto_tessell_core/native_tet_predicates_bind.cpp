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
#include <compare>
#include <cstdint>
#include <cstddef>
#include <functional>
#include <iterator>
#include <limits>
#include <mutex>
#include <numbers>
#include <ranges>
#include <span>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace py = pybind11;

extern "C" {
void exactinit();
double orient3d(double* pa, double* pb, double* pc, double* pd);
double insphere(double* pa, double* pb, double* pc, double* pd, double* pe);
}

namespace {

using CdtEdge = std::array<int64_t, 2>;
using CdtFace = std::array<int64_t, 3>;

struct CdtAuditResult {
    std::vector<CdtEdge> missing_edges;
    size_t n_surface_edges{};
    size_t n_present_edges{};
    size_t n_surface_faces{};
    size_t n_present_faces{};
};

template <typename Entity>
void sort_unique(std::vector<Entity>& entities)
{
    std::sort(entities.begin(), entities.end());
    entities.erase(std::unique(entities.begin(), entities.end()), entities.end());
}

size_t checked_entity_count(
    const size_t rows,
    const size_t entities_per_row,
    const char* const name)
{
    if (rows > std::numeric_limits<size_t>::max() / entities_per_row) {
        throw std::overflow_error(std::string(name) + " is too large");
    }
    return rows * entities_per_row;
}

void validate_cdt_array(
    const py::array& array,
    const py::ssize_t columns,
    const char* const name)
{
    if (!array.dtype().is(py::dtype::of<int64_t>())) {
        throw py::type_error(std::string(name) + " must have dtype int64");
    }
    if (array.ndim() != 2 || array.shape(1) != columns) {
        throw py::value_error(
            std::string(name) + " must have shape (N, "
            + std::to_string(columns) + ")");
    }
    if ((array.flags() & py::array::c_style) == 0) {
        throw py::value_error(std::string(name) + " must be C-contiguous");
    }
}

void validate_point_array(const py::array& array, const char* const name)
{
    if (!array.dtype().is(py::dtype::of<double>())) {
        throw py::type_error(std::string(name) + " must have dtype float64");
    }
    if (array.ndim() != 2 || array.shape(1) != 3) {
        throw py::value_error(std::string(name) + " must have shape (N, 3)");
    }
    if ((array.flags() & py::array::c_style) == 0) {
        throw py::value_error(std::string(name) + " must be C-contiguous");
    }
}

CdtAuditResult audit_cdt_constraints_impl(
    const std::span<const int64_t> surface_faces,
    const std::span<const int64_t> tets)
{
    const size_t n_surface_faces = surface_faces.size() / 3U;
    const size_t n_tets = tets.size() / 4U;

    std::vector<CdtEdge> surface_edges;
    std::vector<CdtFace> canonical_surface_faces;
    std::vector<CdtEdge> tet_edges;
    std::vector<CdtFace> tet_faces;
    surface_edges.reserve(checked_entity_count(n_surface_faces, 3U, "surface_faces"));
    canonical_surface_faces.reserve(n_surface_faces);
    tet_edges.reserve(checked_entity_count(n_tets, 6U, "tets"));
    tet_faces.reserve(checked_entity_count(n_tets, 4U, "tets"));

    const auto edge = [](const int64_t a, const int64_t b) {
        return a <= b ? CdtEdge{a, b} : CdtEdge{b, a};
    };
    const auto face = [](const int64_t a, const int64_t b, const int64_t c) {
        CdtFace result{a, b, c};
        std::sort(result.begin(), result.end());
        return result;
    };

    for (size_t row = 0; row < n_surface_faces; ++row) {
        const int64_t a = surface_faces[3U * row];
        const int64_t b = surface_faces[3U * row + 1U];
        const int64_t c = surface_faces[3U * row + 2U];
        if (a < 0 || b < 0 || c < 0) {
            throw std::invalid_argument("surface_faces contains a negative index");
        }
        surface_edges.push_back(edge(a, b));
        surface_edges.push_back(edge(b, c));
        surface_edges.push_back(edge(c, a));
        canonical_surface_faces.push_back(face(a, b, c));
    }
    for (size_t row = 0; row < n_tets; ++row) {
        const int64_t a = tets[4U * row];
        const int64_t b = tets[4U * row + 1U];
        const int64_t c = tets[4U * row + 2U];
        const int64_t d = tets[4U * row + 3U];
        if (a < 0 || b < 0 || c < 0 || d < 0) {
            throw std::invalid_argument("tets contains a negative index");
        }
        tet_edges.push_back(edge(a, b));
        tet_edges.push_back(edge(a, c));
        tet_edges.push_back(edge(a, d));
        tet_edges.push_back(edge(b, c));
        tet_edges.push_back(edge(b, d));
        tet_edges.push_back(edge(c, d));
        tet_faces.push_back(face(a, b, c));
        tet_faces.push_back(face(a, b, d));
        tet_faces.push_back(face(a, c, d));
        tet_faces.push_back(face(b, c, d));
    }

    sort_unique(surface_edges);
    sort_unique(canonical_surface_faces);
    sort_unique(tet_edges);
    sort_unique(tet_faces);

    CdtAuditResult result;
    result.n_surface_edges = surface_edges.size();
    result.n_surface_faces = canonical_surface_faces.size();
    result.missing_edges.reserve(surface_edges.size());
    std::set_difference(
        surface_edges.begin(), surface_edges.end(),
        tet_edges.begin(), tet_edges.end(),
        std::back_inserter(result.missing_edges));
    result.n_present_edges = surface_edges.size() - result.missing_edges.size();

    size_t surface_index = 0;
    size_t tet_index = 0;
    while (surface_index < canonical_surface_faces.size() && tet_index < tet_faces.size()) {
        if (canonical_surface_faces[surface_index] < tet_faces[tet_index]) {
            ++surface_index;
        } else if (tet_faces[tet_index] < canonical_surface_faces[surface_index]) {
            ++tet_index;
        } else {
            ++result.n_present_faces;
            ++surface_index;
            ++tet_index;
        }
    }
    return result;
}

py::dict audit_cdt_constraints(const py::array& surface_faces, const py::array& tets)
{
    validate_cdt_array(surface_faces, 3, "surface_faces");
    validate_cdt_array(tets, 4, "tets");
    const auto surface_info = surface_faces.request();
    const auto tet_info = tets.request();
    const auto surface_count = static_cast<size_t>(surface_info.size);
    const auto tet_count = static_cast<size_t>(tet_info.size);
    const auto surface_view = std::span{
        static_cast<const int64_t*>(surface_info.ptr), surface_count};
    const auto tet_view = std::span{
        static_cast<const int64_t*>(tet_info.ptr), tet_count};

    CdtAuditResult audit;
    {
        py::gil_scoped_release release;
        audit = audit_cdt_constraints_impl(surface_view, tet_view);
    }

    if (audit.missing_edges.size()
        > static_cast<size_t>(std::numeric_limits<py::ssize_t>::max())) {
        throw std::overflow_error("missing edge output exceeds Python array limits");
    }
    py::array_t<int64_t> missing_edges({
        static_cast<py::ssize_t>(audit.missing_edges.size()), py::ssize_t{2}});
    auto output = missing_edges.mutable_unchecked<2>();
    for (size_t row = 0; row < audit.missing_edges.size(); ++row) {
        output(static_cast<py::ssize_t>(row), 0) = audit.missing_edges[row][0];
        output(static_cast<py::ssize_t>(row), 1) = audit.missing_edges[row][1];
    }

    py::dict result;
    result["n_surface_edges"] = audit.n_surface_edges;
    result["n_present_as_tet_edges"] = audit.n_present_edges;
    result["n_missing"] = audit.missing_edges.size();
    result["missing_edges"] = std::move(missing_edges);
    result["n_surface_faces"] = audit.n_surface_faces;
    result["n_present_as_tet_faces"] = audit.n_present_faces;
    result["n_missing_faces"] = audit.n_surface_faces - audit.n_present_faces;
    return result;
}

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

struct TetHash {
    size_t operator()(const Tet& tet) const
    {
        size_t hash = 0;
        for (const long long vertex : tet) {
            hash ^= std::hash<long long>{}(vertex) + 0x9e3779b9U + (hash << 6U)
                + (hash >> 2U);
        }
        return hash;
    }
};

class DisjointSet {
public:
    explicit DisjointSet(const size_t count) : parent_(count), rank_(count, 0)
    {
        for (size_t index = 0; index < count; ++index) {
            parent_[index] = index;
        }
    }

    size_t find(size_t item)
    {
        while (parent_[item] != item) {
            parent_[item] = parent_[parent_[item]];
            item = parent_[item];
        }
        return item;
    }

    void unite(const size_t left, const size_t right)
    {
        size_t left_root = find(left);
        size_t right_root = find(right);
        if (left_root == right_root) {
            return;
        }
        if (rank_[left_root] < rank_[right_root]) {
            std::swap(left_root, right_root);
        }
        parent_[right_root] = left_root;
        if (rank_[left_root] == rank_[right_root]) {
            ++rank_[left_root];
        }
    }

private:
    std::vector<size_t> parent_;
    std::vector<unsigned char> rank_;
};

struct BoundaryEdgeInfo {
    size_t first_face = 0;
    size_t count = 0;
};

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

long double signed_volume6_long_double(
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
    return determinant;
}

long double absolute_volume6(
    const py::detail::unchecked_reference<double, 2>& points,
    const Tet& tet)
{
    return std::abs(signed_volume6_long_double(points, tet));
}

py::tuple audit_tet_boundary_native(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array,
    const double relative_volume_tolerance)
{
    if (points_array.ndim() != 2 || points_array.shape(1) != 3) {
        throw std::invalid_argument("audit_tet_boundary expects points shaped (N, 3)");
    }
    if (tets_array.ndim() != 2 || tets_array.shape(1) != 4) {
        throw std::invalid_argument("audit_tet_boundary expects tets shaped (M, 4)");
    }
    if (!std::isfinite(relative_volume_tolerance)) {
        throw std::invalid_argument("relative_volume_tolerance must be finite");
    }

    const auto points = points_array.unchecked<2>();
    const auto tets = tets_array.unchecked<2>();
    const size_t point_count = static_cast<size_t>(points.shape(0));
    const size_t tet_count = static_cast<size_t>(tets.shape(0));
    if (tet_count == 0) {
        return py::make_tuple(0, 0, 0, 0, 0, 0, 0, 0, 0);
    }

    std::array<long long, 9> stats{};
    {
        py::gil_scoped_release release;

        std::array<double, 3> bbox_min{
            std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::infinity()};
        std::array<double, 3> bbox_max{
            -std::numeric_limits<double>::infinity(),
            -std::numeric_limits<double>::infinity(),
            -std::numeric_limits<double>::infinity()};
        for (size_t point_index = 0; point_index < point_count; ++point_index) {
            for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
                const double value = points(
                    static_cast<py::ssize_t>(point_index),
                    static_cast<py::ssize_t>(coordinate));
                if (!std::isfinite(value)) {
                    throw std::invalid_argument(
                        "audit_tet_boundary requires finite point coordinates");
                }
                bbox_min[coordinate] = std::min(bbox_min[coordinate], value);
                bbox_max[coordinate] = std::max(bbox_max[coordinate], value);
            }
        }
        const double dx = bbox_max[0] - bbox_min[0];
        const double dy = bbox_max[1] - bbox_min[1];
        const double dz = bbox_max[2] - bbox_min[2];
        const double diagonal = std::max(
            std::sqrt(dx * dx + dy * dy + dz * dz),
            std::numeric_limits<double>::min());
        const long double volume_floor = static_cast<long double>(
            std::max(0.0, relative_volume_tolerance))
            * static_cast<long double>(diagonal)
            * static_cast<long double>(diagonal)
            * static_cast<long double>(diagonal);

        std::unordered_set<Tet, TetHash> unique_tets;
        unique_tets.reserve(tet_count);
        std::unordered_map<FaceKey, size_t, FaceKeyHash> face_counts;
        face_counts.reserve(tet_count * 4U);
        size_t duplicate_tets = 0;
        size_t degenerate_tets = 0;
        size_t inverted_tets = 0;

        for (size_t row = 0; row < tet_count; ++row) {
            Tet tet{};
            for (size_t local = 0; local < 4; ++local) {
                tet[local] = tets(
                    static_cast<py::ssize_t>(row),
                    static_cast<py::ssize_t>(local));
                if (tet[local] < 0
                    || tet[local] >= static_cast<long long>(point_count)) {
                    throw std::invalid_argument("tet vertex index out of range");
                }
            }
            Tet canonical_tet = tet;
            std::sort(canonical_tet.begin(), canonical_tet.end());
            if (!unique_tets.insert(canonical_tet).second) {
                ++duplicate_tets;
            }
            const long double volume6 = signed_volume6_long_double(points, tet);
            const bool degenerate = std::abs(volume6) <= volume_floor;
            if (degenerate) {
                ++degenerate_tets;
            }
            // The existing scale-relative degeneracy threshold is also a
            // conservative exact-predicate filter.  Outside it, extended
            // precision has a stable sign; inside it, use Shewchuk exactly.
            const int orientation_sign = degenerate
                ? -orient3d_shewchuk_sign(points, tet)
                : (volume6 > 0.0L ? 1 : -1);
            if (orientation_sign < 0) {
                ++inverted_tets;
            }
            for (size_t excluded = 0; excluded < 4; ++excluded) {
                ++face_counts[make_face_key(tet, excluded)];
            }
        }

        std::vector<FaceKey> boundary_faces;
        boundary_faces.reserve(face_counts.size());
        size_t nonmanifold_faces = 0;
        for (const auto& [face, count] : face_counts) {
            if (count == 1) {
                boundary_faces.push_back(face);
            } else if (count > 2) {
                ++nonmanifold_faces;
            }
        }

        stats[0] = static_cast<long long>(tet_count);
        stats[1] = static_cast<long long>(boundary_faces.size());
        stats[4] = static_cast<long long>(nonmanifold_faces);
        stats[6] = static_cast<long long>(duplicate_tets);
        stats[7] = static_cast<long long>(degenerate_tets);
        stats[8] = static_cast<long long>(inverted_tets);
        if (!boundary_faces.empty()) {
            DisjointSet components(boundary_faces.size());
            std::unordered_map<EdgeKey, BoundaryEdgeInfo, EdgeKeyHash> edge_info;
            edge_info.reserve(boundary_faces.size() * 3U);
            for (size_t face_index = 0; face_index < boundary_faces.size(); ++face_index) {
                const auto& vertices = boundary_faces[face_index].vertices;
                const std::array<EdgeKey, 3> edges{{
                    EdgeKey{{vertices[0], vertices[1]}},
                    EdgeKey{{vertices[1], vertices[2]}},
                    EdgeKey{{vertices[0], vertices[2]}},
                }};
                for (const EdgeKey& edge : edges) {
                    auto [position, inserted] = edge_info.try_emplace(
                        edge, BoundaryEdgeInfo{face_index, 0});
                    BoundaryEdgeInfo& info = position->second;
                    if (!inserted) {
                        components.unite(info.first_face, face_index);
                    }
                    ++info.count;
                }
            }

            size_t open_edges = 0;
            size_t nonmanifold_edges = 0;
            for (const auto& [edge, info] : edge_info) {
                static_cast<void>(edge);
                open_edges += info.count == 1;
                nonmanifold_edges += info.count > 2;
            }
            std::unordered_set<size_t> roots;
            roots.reserve(boundary_faces.size());
            for (size_t face_index = 0; face_index < boundary_faces.size(); ++face_index) {
                roots.insert(components.find(face_index));
            }
            stats[2] = static_cast<long long>(open_edges);
            stats[3] = static_cast<long long>(nonmanifold_edges);
            stats[5] = static_cast<long long>(roots.size());
        }
    }

    return py::make_tuple(
        stats[0], stats[1], stats[2], stats[3],
        stats[4], stats[5], stats[6], stats[7], stats[8]);
}

struct SourceComponentAuditResult {
    size_t n_source_components{};
    size_t n_candidate_boundary_components{};
    size_t n_source_surface_vertices{};
    size_t n_source_vertices_on_boundary{};
    size_t n_missing_source_vertices{};
    size_t n_matched_source_components{};
    size_t n_mixed_candidate_components{};
    size_t n_split_source_components{};
    size_t n_unanchored_candidate_components{};
    size_t n_unknown_source_vertex_anchors{};
    size_t n_source_faces{};
    size_t n_source_faces_on_boundary{};
    size_t n_missing_source_faces{};
    size_t n_candidate_boundary_faces{};
    size_t n_owned_candidate_faces{};
    size_t n_unowned_candidate_faces{};
    size_t n_source_planar_patches{};
    size_t n_uncovered_source_patches{};
    size_t n_area_mismatch_patches{};
    size_t n_feature_boundary_mismatches{};
    size_t n_overlap_pairs{};
    bool source_faces_preserved{};
    bool bijective{};
};

using EdgeFaceRecord = std::pair<CdtEdge, size_t>;
using ComponentPair = std::array<size_t, 2>;

struct CdtFaceHash {
    size_t operator()(const CdtFace& face) const noexcept
    {
        size_t hash = 0U;
        for (const int64_t vertex : face) {
            hash ^= std::hash<int64_t>{}(vertex) + 0x9e3779b9U + (hash << 6U)
                + (hash >> 2U);
        }
        return hash;
    }
};

struct CdtEdgeHash {
    size_t operator()(const CdtEdge& edge) const noexcept
    {
        return std::hash<int64_t>{}(edge[0])
            ^ (std::hash<int64_t>{}(edge[1]) << 1U);
    }
};

struct PointRecord {
    std::array<double, 3> coordinates;
    size_t index;

    auto operator<=>(const PointRecord&) const = default;
};

using ProvenancePoint2 = std::array<long double, 2>;
using ProvenancePoint3 = std::array<long double, 3>;
using ProvenanceTriangle2 = std::array<ProvenancePoint2, 3>;

constexpr long double provenance_epsilon =
    static_cast<long double>(std::numeric_limits<double>::epsilon());
constexpr long double provenance_distance_tolerance = 256.0L * provenance_epsilon;
constexpr long double provenance_normal_tolerance = 1024.0L * provenance_epsilon;
constexpr long double provenance_area_tolerance_factor = 8192.0L * provenance_epsilon;

struct ProvenancePlane {
    ProvenancePoint3 normal{};
    long double offset{};
    size_t axis{};
};

struct ProvenancePatch {
    std::vector<size_t> source_face_indices;
    ProvenancePlane plane;
    std::vector<ProvenanceTriangle2> triangles;
    std::vector<CdtEdge> boundary_edges;
};

struct PlanarProvenanceResult {
    size_t n_source_faces{};
    size_t n_source_faces_on_boundary{};
    size_t n_missing_source_faces{};
    size_t n_candidate_boundary_faces{};
    size_t n_owned_candidate_faces{};
    size_t n_unowned_candidate_faces{};
    size_t n_source_planar_patches{};
    size_t n_uncovered_source_patches{};
    size_t n_area_mismatch_patches{};
    size_t n_feature_boundary_mismatches{};
    size_t n_overlap_pairs{};
    bool preserved{};
};

std::pair<std::vector<ProvenancePoint3>, std::vector<ProvenancePoint3>>
normalized_provenance_points(
    const std::span<const double> source_flat,
    const std::span<const double> candidate_flat)
{
    long double maximum = 0.0L;
    for (const double value : source_flat) {
        maximum = std::max(maximum, std::abs(static_cast<long double>(value)));
    }
    if (!(maximum > 0.0L)) {
        throw std::invalid_argument("source surface has zero coordinate scale");
    }
    ProvenancePoint3 origin{
        std::numeric_limits<long double>::infinity(),
        std::numeric_limits<long double>::infinity(),
        std::numeric_limits<long double>::infinity()};
    ProvenancePoint3 upper{
        -std::numeric_limits<long double>::infinity(),
        -std::numeric_limits<long double>::infinity(),
        -std::numeric_limits<long double>::infinity()};
    for (size_t index = 0; index < source_flat.size() / 3U; ++index) {
        for (size_t coordinate = 0; coordinate < 3U; ++coordinate) {
            const long double value =
                static_cast<long double>(source_flat[3U * index + coordinate]) / maximum;
            origin[coordinate] = std::min(origin[coordinate], value);
            upper[coordinate] = std::max(upper[coordinate], value);
        }
    }
    long double diagonal_squared = 0.0L;
    for (size_t coordinate = 0; coordinate < 3U; ++coordinate) {
        const long double extent = upper[coordinate] - origin[coordinate];
        diagonal_squared += extent * extent;
    }
    const long double diagonal = std::sqrt(diagonal_squared);
    if (!(diagonal > 0.0L) || !std::isfinite(diagonal)) {
        throw std::invalid_argument("source surface has zero bounding-box diagonal");
    }
    const auto normalize = [&](const std::span<const double> flat) {
        std::vector<ProvenancePoint3> points(flat.size() / 3U);
        for (size_t index = 0; index < points.size(); ++index) {
            for (size_t coordinate = 0; coordinate < 3U; ++coordinate) {
                points[index][coordinate] =
                    (static_cast<long double>(flat[3U * index + coordinate]) / maximum
                     - origin[coordinate])
                    / diagonal;
            }
        }
        return points;
    };
    return {normalize(source_flat), normalize(candidate_flat)};
}

ProvenancePlane provenance_plane(const std::array<ProvenancePoint3, 3>& triangle)
{
    ProvenancePoint3 first{};
    ProvenancePoint3 second{};
    for (size_t coordinate = 0; coordinate < 3U; ++coordinate) {
        first[coordinate] = triangle[1][coordinate] - triangle[0][coordinate];
        second[coordinate] = triangle[2][coordinate] - triangle[0][coordinate];
    }
    ProvenancePoint3 normal{
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0]};
    const long double length = std::sqrt(
        normal[0] * normal[0] + normal[1] * normal[1] + normal[2] * normal[2]);
    if (!(length > provenance_area_tolerance_factor) || !std::isfinite(length)) {
        throw std::invalid_argument(
            "source or candidate boundary contains a degenerate face");
    }
    size_t axis = 0U;
    for (size_t coordinate = 1U; coordinate < 3U; ++coordinate) {
        if (std::abs(normal[coordinate]) > std::abs(normal[axis])) {
            axis = coordinate;
        }
    }
    for (long double& value : normal) {
        value /= length;
    }
    if (normal[axis] < 0.0L) {
        for (long double& value : normal) {
            value = -value;
        }
    }
    long double offset = 0.0L;
    for (size_t coordinate = 0; coordinate < 3U; ++coordinate) {
        offset += normal[coordinate] * triangle[0][coordinate];
    }
    return ProvenancePlane{normal, offset, axis};
}

bool same_provenance_plane(const ProvenancePlane& left, const ProvenancePlane& right)
{
    long double dot = 0.0L;
    for (size_t coordinate = 0; coordinate < 3U; ++coordinate) {
        dot += left.normal[coordinate] * right.normal[coordinate];
    }
    return 1.0L - dot <= provenance_normal_tolerance
        && std::abs(left.offset - right.offset) <= provenance_distance_tolerance;
}

ProvenancePoint2 project_provenance_point(
    const ProvenancePoint3& point,
    const size_t axis)
{
    ProvenancePoint2 projected{};
    size_t output = 0U;
    for (size_t coordinate = 0; coordinate < 3U; ++coordinate) {
        if (coordinate != axis) {
            projected[output++] = point[coordinate];
        }
    }
    return projected;
}

long double provenance_orient2d(
    const ProvenancePoint2& first,
    const ProvenancePoint2& second,
    const ProvenancePoint2& third)
{
    return (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0]);
}

bool provenance_point_in_triangle(
    const ProvenancePoint2& point,
    const ProvenanceTriangle2& triangle,
    const bool strict)
{
    const std::array<long double, 3> signs{
        provenance_orient2d(triangle[0], triangle[1], point),
        provenance_orient2d(triangle[1], triangle[2], point),
        provenance_orient2d(triangle[2], triangle[0], point)};
    if (strict) {
        return std::ranges::all_of(signs, [](const long double value) {
                   return value > provenance_area_tolerance_factor;
               })
            || std::ranges::all_of(signs, [](const long double value) {
                   return value < -provenance_area_tolerance_factor;
               });
    }
    return std::ranges::all_of(signs, [](const long double value) {
               return value >= -provenance_area_tolerance_factor;
           })
        || std::ranges::all_of(signs, [](const long double value) {
               return value <= provenance_area_tolerance_factor;
           });
}

using ProvenanceSegment2 = std::array<ProvenancePoint2, 2>;

bool proper_provenance_segment_intersection(
    const ProvenanceSegment2& left,
    const ProvenanceSegment2& right)
{
    const long double ab_c = provenance_orient2d(left[0], left[1], right[0]);
    const long double ab_d = provenance_orient2d(left[0], left[1], right[1]);
    const long double cd_a = provenance_orient2d(right[0], right[1], left[0]);
    const long double cd_b = provenance_orient2d(right[0], right[1], left[1]);
    const auto opposite = [](const long double first, const long double second) {
        return (first > provenance_area_tolerance_factor
                && second < -provenance_area_tolerance_factor)
            || (first < -provenance_area_tolerance_factor
                && second > provenance_area_tolerance_factor);
    };
    return opposite(ab_c, ab_d) && opposite(cd_a, cd_b);
}

long double provenance_triangle_area(const ProvenanceTriangle2& triangle)
{
    return 0.5L
        * std::abs(provenance_orient2d(triangle[0], triangle[1], triangle[2]));
}

long double provenance_cross2d(
    const ProvenancePoint2& left,
    const ProvenancePoint2& right)
{
    return left[0] * right[1] - left[1] * right[0];
}

bool provenance_segment_inside_patch(
    const ProvenanceSegment2& segment,
    const std::vector<ProvenanceSegment2>& boundary_segments,
    const std::vector<ProvenanceTriangle2>& patch_triangles)
{
    const ProvenancePoint2 direction{
        segment[1][0] - segment[0][0], segment[1][1] - segment[0][1]};
    const long double squared_length =
        direction[0] * direction[0] + direction[1] * direction[1];
    if (!(squared_length > provenance_distance_tolerance
            * provenance_distance_tolerance)) {
        return false;
    }
    const long double length = std::sqrt(squared_length);
    const long double parameter_tolerance = provenance_distance_tolerance / length;
    std::vector<long double> parameters{0.0L, 1.0L};
    parameters.reserve(2U + 2U * boundary_segments.size());
    for (const ProvenanceSegment2& boundary : boundary_segments) {
        const ProvenancePoint2 boundary_direction{
            boundary[1][0] - boundary[0][0],
            boundary[1][1] - boundary[0][1]};
        const ProvenancePoint2 relative{
            boundary[0][0] - segment[0][0],
            boundary[0][1] - segment[0][1]};
        const long double denominator =
            provenance_cross2d(direction, boundary_direction);
        if (std::abs(denominator) > provenance_area_tolerance_factor) {
            const long double parameter =
                provenance_cross2d(relative, boundary_direction) / denominator;
            const long double boundary_parameter =
                provenance_cross2d(relative, direction) / denominator;
            if (parameter >= -parameter_tolerance
                && parameter <= 1.0L + parameter_tolerance
                && boundary_parameter >= -parameter_tolerance
                && boundary_parameter <= 1.0L + parameter_tolerance) {
                parameters.push_back(std::clamp(parameter, 0.0L, 1.0L));
            }
            continue;
        }
        const long double first_distance = std::abs(provenance_orient2d(
            segment[0], segment[1], boundary[0])) / length;
        const long double second_distance = std::abs(provenance_orient2d(
            segment[0], segment[1], boundary[1])) / length;
        if (std::max(first_distance, second_distance)
            > provenance_distance_tolerance) {
            continue;
        }
        for (const ProvenancePoint2& point : boundary) {
            const long double parameter =
                ((point[0] - segment[0][0]) * direction[0]
                 + (point[1] - segment[0][1]) * direction[1])
                / squared_length;
            if (parameter >= -parameter_tolerance
                && parameter <= 1.0L + parameter_tolerance) {
                parameters.push_back(std::clamp(parameter, 0.0L, 1.0L));
            }
        }
    }
    std::sort(parameters.begin(), parameters.end());
    std::vector<long double> unique_parameters;
    unique_parameters.reserve(parameters.size());
    for (const long double parameter : parameters) {
        if (unique_parameters.empty()
            || parameter > unique_parameters.back() + parameter_tolerance) {
            unique_parameters.push_back(parameter);
        } else {
            unique_parameters.back() = std::max(unique_parameters.back(), parameter);
        }
    }
    for (size_t index = 1U; index < unique_parameters.size(); ++index) {
        const long double low = unique_parameters[index - 1U];
        const long double high = unique_parameters[index];
        if (high <= low + parameter_tolerance) {
            continue;
        }
        const long double midpoint_parameter = 0.5L * (low + high);
        const ProvenancePoint2 midpoint{
            segment[0][0] + midpoint_parameter * direction[0],
            segment[0][1] + midpoint_parameter * direction[1]};
        if (std::ranges::none_of(
                patch_triangles,
                [&](const ProvenanceTriangle2& source_triangle) {
                    return provenance_point_in_triangle(
                        midpoint, source_triangle, false);
                })) {
            return false;
        }
    }
    return true;
}

std::vector<ProvenancePatch> build_provenance_patches(
    const std::vector<ProvenancePoint3>& source,
    const std::vector<CdtFace>& source_faces)
{
    std::vector<ProvenancePlane> planes;
    planes.reserve(source_faces.size());
    for (const CdtFace& face : source_faces) {
        planes.push_back(provenance_plane(std::array{
            source[static_cast<size_t>(face[0])],
            source[static_cast<size_t>(face[1])],
            source[static_cast<size_t>(face[2])] }));
    }
    std::unordered_map<CdtEdge, std::vector<size_t>, CdtEdgeHash> edge_faces;
    edge_faces.reserve(checked_entity_count(source_faces.size(), 3U, "source_faces"));
    for (size_t face_index = 0; face_index < source_faces.size(); ++face_index) {
        const CdtFace& face = source_faces[face_index];
        const std::array<CdtEdge, 3> edges{{
            CdtEdge{face[0], face[1]},
            CdtEdge{face[1], face[2]},
            CdtEdge{face[0], face[2]}}};
        for (const CdtEdge& edge : edges) {
            edge_faces[edge].push_back(face_index);
        }
    }
    DisjointSet components(source_faces.size());
    for (const auto& [edge, owners] : edge_faces) {
        static_cast<void>(edge);
        for (size_t index = 1U; index < owners.size(); ++index) {
            if (same_provenance_plane(planes[owners[0]], planes[owners[index]])) {
                components.unite(owners[0], owners[index]);
            }
        }
    }
    std::unordered_map<size_t, size_t> patch_for_root;
    std::vector<ProvenancePatch> patches;
    for (size_t face_index = 0; face_index < source_faces.size(); ++face_index) {
        const size_t root = components.find(face_index);
        auto [position, inserted] = patch_for_root.try_emplace(root, patches.size());
        if (inserted) {
            patches.push_back(ProvenancePatch{});
            patches.back().plane = planes[face_index];
        }
        patches[position->second].source_face_indices.push_back(face_index);
    }
    for (ProvenancePatch& patch : patches) {
        std::unordered_map<CdtEdge, size_t, CdtEdgeHash> edge_counts;
        edge_counts.reserve(checked_entity_count(
            patch.source_face_indices.size(), 3U, "patch_faces"));
        for (const size_t face_index : patch.source_face_indices) {
            const CdtFace& face = source_faces[face_index];
            ProvenanceTriangle2 projected{};
            for (size_t local = 0; local < 3U; ++local) {
                projected[local] = project_provenance_point(
                    source[static_cast<size_t>(face[local])], patch.plane.axis);
            }
            patch.triangles.push_back(projected);
            ++edge_counts[CdtEdge{face[0], face[1]}];
            ++edge_counts[CdtEdge{face[1], face[2]}];
            ++edge_counts[CdtEdge{face[0], face[2]}];
        }
        for (const auto& [edge, count] : edge_counts) {
            if (count == 1U) {
                patch.boundary_edges.push_back(edge);
            }
        }
    }
    return patches;
}

bool triangle_fully_inside_provenance_patch(
    const std::array<ProvenancePoint3, 3>& triangle3,
    const ProvenancePatch& patch,
    const std::vector<ProvenancePoint3>& source)
{
    ProvenanceTriangle2 triangle{};
    for (size_t local = 0; local < 3U; ++local) {
        triangle[local] = project_provenance_point(triangle3[local], patch.plane.axis);
    }
    if (provenance_triangle_area(triangle) <= provenance_area_tolerance_factor) {
        return false;
    }
    ProvenancePoint2 centroid{};
    for (const ProvenancePoint2& point : triangle) {
        centroid[0] += point[0] / 3.0L;
        centroid[1] += point[1] / 3.0L;
    }
    std::array<ProvenancePoint2, 4> probes{
        triangle[0], triangle[1], triangle[2], centroid};
    for (const ProvenancePoint2& probe : probes) {
        if (std::ranges::none_of(patch.triangles, [&](const ProvenanceTriangle2& source_triangle) {
                return provenance_point_in_triangle(probe, source_triangle, false);
            })) {
            return false;
        }
    }
    const std::array<ProvenanceSegment2, 3> candidate_edges{{
        ProvenanceSegment2{triangle[0], triangle[1]},
        ProvenanceSegment2{triangle[1], triangle[2]},
        ProvenanceSegment2{triangle[0], triangle[2]}}};
    std::vector<ProvenanceSegment2> boundary_segments;
    boundary_segments.reserve(patch.boundary_edges.size());
    for (const CdtEdge& boundary_edge : patch.boundary_edges) {
        boundary_segments.push_back(ProvenanceSegment2{
            project_provenance_point(
                source[static_cast<size_t>(boundary_edge[0])], patch.plane.axis),
            project_provenance_point(
                source[static_cast<size_t>(boundary_edge[1])], patch.plane.axis)});
    }
    if (std::ranges::any_of(candidate_edges, [&](const ProvenanceSegment2& edge) {
            return !provenance_segment_inside_patch(
                edge, boundary_segments, patch.triangles);
        })) {
        return false;
    }
    std::unordered_set<int64_t> boundary_vertices;
    boundary_vertices.reserve(patch.boundary_edges.size() * 2U);
    for (const CdtEdge& edge : patch.boundary_edges) {
        boundary_vertices.insert(edge[0]);
        boundary_vertices.insert(edge[1]);
    }
    return std::ranges::none_of(boundary_vertices, [&](const int64_t vertex) {
        return provenance_point_in_triangle(
            project_provenance_point(
                source[static_cast<size_t>(vertex)], patch.plane.axis),
            triangle,
            true);
    });
}

bool provenance_triangles_overlap(
    const ProvenanceTriangle2& left,
    const ProvenanceTriangle2& right)
{
    for (size_t coordinate = 0; coordinate < 2U; ++coordinate) {
        long double left_min = left[0][coordinate];
        long double left_max = left[0][coordinate];
        long double right_min = right[0][coordinate];
        long double right_max = right[0][coordinate];
        for (size_t local = 1U; local < 3U; ++local) {
            left_min = std::min(left_min, left[local][coordinate]);
            left_max = std::max(left_max, left[local][coordinate]);
            right_min = std::min(right_min, right[local][coordinate]);
            right_max = std::max(right_max, right[local][coordinate]);
        }
        if (left_max < right_min - provenance_distance_tolerance
            || right_max < left_min - provenance_distance_tolerance) {
            return false;
        }
    }
    const std::array<ProvenanceSegment2, 3> left_edges{{
        ProvenanceSegment2{left[0], left[1]}, ProvenanceSegment2{left[1], left[2]},
        ProvenanceSegment2{left[0], left[2]}}};
    const std::array<ProvenanceSegment2, 3> right_edges{{
        ProvenanceSegment2{right[0], right[1]}, ProvenanceSegment2{right[1], right[2]},
        ProvenanceSegment2{right[0], right[2]}}};
    for (const ProvenanceSegment2& left_edge : left_edges) {
        for (const ProvenanceSegment2& right_edge : right_edges) {
            if (proper_provenance_segment_intersection(left_edge, right_edge)) {
                return true;
            }
        }
    }
    if (std::ranges::any_of(left, [&](const ProvenancePoint2& point) {
            return provenance_point_in_triangle(point, right, true);
        })
        || std::ranges::any_of(right, [&](const ProvenancePoint2& point) {
               return provenance_point_in_triangle(point, left, true);
           })) {
        return true;
    }
    ProvenancePoint2 left_centroid{};
    ProvenancePoint2 right_centroid{};
    for (size_t local = 0; local < 3U; ++local) {
        for (size_t coordinate = 0; coordinate < 2U; ++coordinate) {
            left_centroid[coordinate] += left[local][coordinate] / 3.0L;
            right_centroid[coordinate] += right[local][coordinate] / 3.0L;
        }
    }
    return provenance_point_in_triangle(left_centroid, right, true)
        || provenance_point_in_triangle(right_centroid, left, true);
}

bool provenance_segment_covered(
    const ProvenanceSegment2& target,
    const std::vector<ProvenanceSegment2>& covers)
{
    const ProvenancePoint2 direction{
        target[1][0] - target[0][0], target[1][1] - target[0][1]};
    const long double squared_length =
        direction[0] * direction[0] + direction[1] * direction[1];
    if (!(squared_length > provenance_distance_tolerance * provenance_distance_tolerance)) {
        return false;
    }
    const long double length = std::sqrt(squared_length);
    const long double parameter_tolerance = provenance_distance_tolerance / length;
    std::vector<std::array<long double, 2>> intervals;
    for (const ProvenanceSegment2& cover : covers) {
        const long double first_distance =
            std::abs(provenance_orient2d(target[0], target[1], cover[0])) / length;
        const long double second_distance =
            std::abs(provenance_orient2d(target[0], target[1], cover[1])) / length;
        if (std::max(first_distance, second_distance) > provenance_distance_tolerance) {
            continue;
        }
        const auto parameter = [&](const ProvenancePoint2& point) {
            return ((point[0] - target[0][0]) * direction[0]
                    + (point[1] - target[0][1]) * direction[1])
                / squared_length;
        };
        long double low = parameter(cover[0]);
        long double high = parameter(cover[1]);
        if (low > high) {
            std::swap(low, high);
        }
        low = std::max(0.0L, low);
        high = std::min(1.0L, high);
        if (high >= low - parameter_tolerance) {
            intervals.push_back({low, high});
        }
    }
    if (intervals.empty()) {
        return false;
    }
    std::sort(intervals.begin(), intervals.end());
    long double covered_end = 0.0L;
    for (const auto& interval : intervals) {
        if (interval[0] > covered_end + parameter_tolerance) {
            return false;
        }
        covered_end = std::max(covered_end, interval[1]);
    }
    return covered_end >= 1.0L - parameter_tolerance;
}

bool provenance_patch_boundary_preserved(
    const ProvenancePatch& patch,
    const std::vector<ProvenancePoint3>& source,
    const std::vector<ProvenancePoint3>& candidate,
    const std::vector<CdtFace>& candidate_faces)
{
    std::unordered_map<CdtEdge, size_t, CdtEdgeHash> candidate_edge_counts;
    candidate_edge_counts.reserve(
        checked_entity_count(candidate_faces.size(), 3U, "candidate_patch_faces"));
    for (const CdtFace& face : candidate_faces) {
        ++candidate_edge_counts[CdtEdge{face[0], face[1]}];
        ++candidate_edge_counts[CdtEdge{face[1], face[2]}];
        ++candidate_edge_counts[CdtEdge{face[0], face[2]}];
    }
    std::vector<ProvenanceSegment2> source_segments;
    source_segments.reserve(patch.boundary_edges.size());
    for (const CdtEdge& edge : patch.boundary_edges) {
        source_segments.push_back(ProvenanceSegment2{
            project_provenance_point(
                source[static_cast<size_t>(edge[0])], patch.plane.axis),
            project_provenance_point(
                source[static_cast<size_t>(edge[1])], patch.plane.axis)});
    }
    std::vector<ProvenanceSegment2> candidate_segments;
    for (const auto& [edge, count] : candidate_edge_counts) {
        if (count == 1U) {
            candidate_segments.push_back(ProvenanceSegment2{
                project_provenance_point(
                    candidate[static_cast<size_t>(edge[0])], patch.plane.axis),
                project_provenance_point(
                    candidate[static_cast<size_t>(edge[1])], patch.plane.axis)});
        }
    }
    return std::ranges::all_of(source_segments, [&](const ProvenanceSegment2& segment) {
               return provenance_segment_covered(segment, candidate_segments);
           })
        && std::ranges::all_of(candidate_segments, [&](const ProvenanceSegment2& segment) {
               return provenance_segment_covered(segment, source_segments);
           });
}

PlanarProvenanceResult audit_planar_facet_provenance(
    const std::span<const double> source_points_flat,
    const std::vector<CdtFace>& source_faces,
    const std::span<const double> candidate_points_flat,
    const std::vector<CdtFace>& candidate_boundary_faces,
    const size_t exact_source_faces)
{
    PlanarProvenanceResult result;
    result.n_source_faces = source_faces.size();
    result.n_source_faces_on_boundary = exact_source_faces;
    result.n_missing_source_faces = result.n_source_faces - exact_source_faces;
    result.n_candidate_boundary_faces = candidate_boundary_faces.size();
    if (exact_source_faces == source_faces.size()
        && candidate_boundary_faces.size() == source_faces.size()) {
        result.n_owned_candidate_faces = candidate_boundary_faces.size();
        result.preserved = true;
        return result;
    }

    auto [source, candidate] = normalized_provenance_points(
        source_points_flat, candidate_points_flat);
    const std::vector<ProvenancePatch> patches =
        build_provenance_patches(source, source_faces);
    result.n_source_planar_patches = patches.size();
    std::vector<size_t> owners(
        candidate_boundary_faces.size(), std::numeric_limits<size_t>::max());
    for (size_t face_index = 0; face_index < candidate_boundary_faces.size(); ++face_index) {
        const CdtFace& face = candidate_boundary_faces[face_index];
        const std::array<ProvenancePoint3, 3> triangle{
            candidate[static_cast<size_t>(face[0])],
            candidate[static_cast<size_t>(face[1])],
            candidate[static_cast<size_t>(face[2])]};
        ProvenancePlane plane{};
        try {
            plane = provenance_plane(triangle);
        } catch (const std::invalid_argument&) {
            ++result.n_unowned_candidate_faces;
            continue;
        }
        size_t matches = 0U;
        size_t owner = std::numeric_limits<size_t>::max();
        for (size_t patch_index = 0; patch_index < patches.size(); ++patch_index) {
            if (same_provenance_plane(plane, patches[patch_index].plane)
                && triangle_fully_inside_provenance_patch(
                    triangle, patches[patch_index], source)) {
                owner = patch_index;
                ++matches;
            }
        }
        if (matches == 1U) {
            owners[face_index] = owner;
            ++result.n_owned_candidate_faces;
        } else {
            ++result.n_unowned_candidate_faces;
        }
    }

    const long double area_tolerance = provenance_area_tolerance_factor
        * static_cast<long double>(std::max<size_t>(
            1U, source_faces.size() + candidate_boundary_faces.size()));
    for (size_t patch_index = 0; patch_index < patches.size(); ++patch_index) {
        const ProvenancePatch& patch = patches[patch_index];
        std::vector<CdtFace> owned_faces;
        std::vector<ProvenanceTriangle2> owned_triangles;
        for (size_t face_index = 0; face_index < owners.size(); ++face_index) {
            if (owners[face_index] != patch_index) {
                continue;
            }
            const CdtFace& face = candidate_boundary_faces[face_index];
            owned_faces.push_back(face);
            ProvenanceTriangle2 projected{};
            for (size_t local = 0; local < 3U; ++local) {
                projected[local] = project_provenance_point(
                    candidate[static_cast<size_t>(face[local])], patch.plane.axis);
            }
            owned_triangles.push_back(projected);
        }
        if (owned_faces.empty()) {
            ++result.n_uncovered_source_patches;
            continue;
        }
        long double source_area = 0.0L;
        for (const ProvenanceTriangle2& triangle : patch.triangles) {
            source_area += provenance_triangle_area(triangle);
        }
        long double candidate_area = 0.0L;
        for (const ProvenanceTriangle2& triangle : owned_triangles) {
            candidate_area += provenance_triangle_area(triangle);
        }
        result.n_area_mismatch_patches +=
            std::abs(source_area - candidate_area) > area_tolerance;
        for (size_t left = 0; left < owned_triangles.size(); ++left) {
            for (size_t right = left + 1U; right < owned_triangles.size(); ++right) {
                result.n_overlap_pairs += provenance_triangles_overlap(
                    owned_triangles[left], owned_triangles[right]);
            }
        }
        result.n_feature_boundary_mismatches +=
            !provenance_patch_boundary_preserved(
                patch, source, candidate, owned_faces);
    }
    result.preserved = result.n_source_faces > 0U
        && result.n_candidate_boundary_faces > 0U
        && result.n_unowned_candidate_faces == 0U
        && result.n_uncovered_source_patches == 0U
        && result.n_area_mismatch_patches == 0U
        && result.n_feature_boundary_mismatches == 0U
        && result.n_overlap_pairs == 0U;
    return result;
}

std::vector<size_t> face_component_roots(const std::vector<CdtFace>& faces)
{
    if (faces.empty()) {
        return {};
    }
    std::vector<EdgeFaceRecord> edge_faces;
    edge_faces.reserve(checked_entity_count(faces.size(), 3U, "faces"));
    const auto edge = [](const int64_t first, const int64_t second) {
        return first <= second ? CdtEdge{first, second} : CdtEdge{second, first};
    };
    for (size_t face_index = 0; face_index < faces.size(); ++face_index) {
        const CdtFace& face = faces[face_index];
        edge_faces.emplace_back(edge(face[0], face[1]), face_index);
        edge_faces.emplace_back(edge(face[1], face[2]), face_index);
        edge_faces.emplace_back(edge(face[0], face[2]), face_index);
    }
    std::sort(edge_faces.begin(), edge_faces.end());

    DisjointSet components(faces.size());
    size_t start = 0;
    while (start < edge_faces.size()) {
        size_t end = start + 1U;
        while (end < edge_faces.size()
               && edge_faces[end].first == edge_faces[start].first) {
            ++end;
        }
        const size_t first_face = edge_faces[start].second;
        for (size_t index = start + 1U; index < end; ++index) {
            components.unite(first_face, edge_faces[index].second);
        }
        start = end;
    }

    std::vector<size_t> roots(faces.size());
    for (size_t face_index = 0; face_index < faces.size(); ++face_index) {
        roots[face_index] = components.find(face_index);
    }
    return roots;
}

SourceComponentAuditResult audit_source_component_bijection_impl(
    const std::span<const double> source_points_flat,
    const std::span<const int64_t> source_faces_flat,
    const std::span<const double> candidate_points_flat,
    const std::span<const int64_t> tets_flat)
{
    const size_t source_vertex_count = source_points_flat.size() / 3U;
    const size_t candidate_vertex_count = candidate_points_flat.size() / 3U;
    const size_t source_face_count = source_faces_flat.size() / 3U;
    const size_t tet_count = tets_flat.size() / 4U;
    if (source_vertex_count == 0U) {
        throw std::invalid_argument("source_points must not be empty");
    }
    if (candidate_vertex_count == 0U) {
        throw std::invalid_argument("candidate_points must not be empty");
    }
    if (source_face_count == 0U) {
        throw std::invalid_argument("source_faces must not be empty");
    }
    if (tet_count == 0U) {
        throw std::invalid_argument("tets must not be empty");
    }

    const auto point_records = [](const std::span<const double> flat) {
        std::vector<PointRecord> records;
        records.reserve(flat.size() / 3U);
        for (size_t index = 0; index < flat.size() / 3U; ++index) {
            const std::array<double, 3> coordinates{
                flat[3U * index], flat[3U * index + 1U], flat[3U * index + 2U]};
            if (!std::ranges::all_of(coordinates, [](const double value) {
                    return std::isfinite(value);
                })) {
                throw std::invalid_argument("point coordinates must be finite");
            }
            records.push_back(PointRecord{coordinates, index});
        }
        std::sort(records.begin(), records.end());
        return records;
    };
    const std::vector<PointRecord> source_points = point_records(source_points_flat);
    const std::vector<PointRecord> candidate_points = point_records(candidate_points_flat);
    const auto same_coordinates = [](const PointRecord& left, const PointRecord& right) {
        return left.coordinates == right.coordinates;
    };
    if (std::adjacent_find(
            source_points.begin(), source_points.end(), same_coordinates)
        != source_points.end()) {
        throw std::invalid_argument(
            "source_points contains ambiguous duplicate coordinates");
    }
    if (source_vertex_count > static_cast<size_t>(std::numeric_limits<int64_t>::max())
        || candidate_vertex_count
            > static_cast<size_t>(std::numeric_limits<int64_t>::max())
                - source_vertex_count) {
        throw std::overflow_error("point provenance index range is too large");
    }

    // Candidate ordering is not a provenance contract: external P4C paths may
    // reorder vertices.  Recover immutable source identity by exact finite
    // coordinates, and assign collision-free synthetic IDs to new vertices.
    std::vector<int64_t> candidate_provenance(candidate_vertex_count);
    for (size_t start = 0; start < candidate_points.size();) {
        size_t end = start + 1U;
        while (end < candidate_points.size()
               && same_coordinates(candidate_points[start], candidate_points[end])) {
            ++end;
        }
        const auto source_match = std::lower_bound(
            source_points.begin(), source_points.end(), candidate_points[start],
            [](const PointRecord& left, const PointRecord& right) {
                return left.coordinates < right.coordinates;
            });
        const bool matches_source = source_match != source_points.end()
            && source_match->coordinates == candidate_points[start].coordinates;
        if (matches_source && end != start + 1U) {
            throw std::invalid_argument(
                "candidate_points duplicates a source coordinate");
        }
        for (size_t index = start; index < end; ++index) {
            const size_t candidate_index = candidate_points[index].index;
            candidate_provenance[candidate_index] = matches_source
                ? static_cast<int64_t>(source_match->index)
                : static_cast<int64_t>(source_vertex_count + candidate_index);
        }
        start = end;
    }

    const auto face = [](const int64_t a, const int64_t b, const int64_t c) {
        CdtFace result{a, b, c};
        std::sort(result.begin(), result.end());
        return result;
    };

    std::vector<CdtFace> source_faces;
    source_faces.reserve(source_face_count);
    for (size_t row = 0; row < source_face_count; ++row) {
        const int64_t a = source_faces_flat[3U * row];
        const int64_t b = source_faces_flat[3U * row + 1U];
        const int64_t c = source_faces_flat[3U * row + 2U];
        if (a < 0 || b < 0 || c < 0
            || static_cast<size_t>(a) >= source_vertex_count
            || static_cast<size_t>(b) >= source_vertex_count
            || static_cast<size_t>(c) >= source_vertex_count) {
            throw std::invalid_argument("source_faces vertex index out of range");
        }
        if (a == b || a == c || b == c) {
            throw std::invalid_argument("source_faces contains a repeated vertex");
        }
        source_faces.push_back(face(a, b, c));
    }
    {
        std::vector<CdtFace> sorted_source = source_faces;
        std::sort(sorted_source.begin(), sorted_source.end());
        if (std::adjacent_find(sorted_source.begin(), sorted_source.end())
            != sorted_source.end()) {
            throw std::invalid_argument("source_faces contains a duplicate face");
        }
    }

    std::unordered_map<CdtFace, size_t, CdtFaceHash> tet_face_counts;
    tet_face_counts.reserve(checked_entity_count(tet_count, 4U, "tets"));
    for (size_t row = 0; row < tet_count; ++row) {
        const int64_t raw_a = tets_flat[4U * row];
        const int64_t raw_b = tets_flat[4U * row + 1U];
        const int64_t raw_c = tets_flat[4U * row + 2U];
        const int64_t raw_d = tets_flat[4U * row + 3U];
        if (raw_a < 0 || raw_b < 0 || raw_c < 0 || raw_d < 0
            || static_cast<size_t>(raw_a) >= candidate_vertex_count
            || static_cast<size_t>(raw_b) >= candidate_vertex_count
            || static_cast<size_t>(raw_c) >= candidate_vertex_count
            || static_cast<size_t>(raw_d) >= candidate_vertex_count) {
            throw std::invalid_argument("tets vertex index out of range");
        }
        if (raw_a == raw_b || raw_a == raw_c || raw_a == raw_d
            || raw_b == raw_c || raw_b == raw_d || raw_c == raw_d) {
            throw std::invalid_argument("tets contains a repeated vertex");
        }
        const int64_t a = candidate_provenance[static_cast<size_t>(raw_a)];
        const int64_t b = candidate_provenance[static_cast<size_t>(raw_b)];
        const int64_t c = candidate_provenance[static_cast<size_t>(raw_c)];
        const int64_t d = candidate_provenance[static_cast<size_t>(raw_d)];
        ++tet_face_counts[face(a, b, c)];
        ++tet_face_counts[face(a, b, d)];
        ++tet_face_counts[face(a, c, d)];
        ++tet_face_counts[face(b, c, d)];
    }
    std::vector<CdtFace> boundary_faces;
    boundary_faces.reserve(tet_face_counts.size());
    for (const auto& [face_key, count] : tet_face_counts) {
        if (count == 1U) {
            boundary_faces.push_back(face_key);
        }
    }
    SourceComponentAuditResult result;
    result.n_source_faces = source_face_count;
    for (const CdtFace& source_face : source_faces) {
        const auto position = tet_face_counts.find(source_face);
        result.n_source_faces_on_boundary += position != tet_face_counts.end()
            && position->second == 1U;
    }
    result.n_missing_source_faces =
        result.n_source_faces - result.n_source_faces_on_boundary;
    result.n_candidate_boundary_faces = boundary_faces.size();
    if (result.n_source_faces_on_boundary == source_face_count
        && boundary_faces.size() == source_face_count) {
        result.n_owned_candidate_faces = boundary_faces.size();
        result.source_faces_preserved = true;
    } else if (!boundary_faces.empty()) {
        std::vector<CdtFace> raw_boundary_faces;
        raw_boundary_faces.reserve(boundary_faces.size());
        const auto append_raw_boundary_face = [&](
                                                  const int64_t first,
                                                  const int64_t second,
                                                  const int64_t third) {
            const CdtFace provenance_face = face(
                candidate_provenance[static_cast<size_t>(first)],
                candidate_provenance[static_cast<size_t>(second)],
                candidate_provenance[static_cast<size_t>(third)]);
            const auto position = tet_face_counts.find(provenance_face);
            if (position == tet_face_counts.end() || position->second != 1U) {
                return;
            }
            raw_boundary_faces.push_back(face(first, second, third));
        };
        for (size_t row = 0; row < tet_count; ++row) {
            const int64_t a = tets_flat[4U * row];
            const int64_t b = tets_flat[4U * row + 1U];
            const int64_t c = tets_flat[4U * row + 2U];
            const int64_t d = tets_flat[4U * row + 3U];
            append_raw_boundary_face(a, b, c);
            append_raw_boundary_face(a, b, d);
            append_raw_boundary_face(a, c, d);
            append_raw_boundary_face(b, c, d);
        }
        const PlanarProvenanceResult provenance = audit_planar_facet_provenance(
            source_points_flat,
            source_faces,
            candidate_points_flat,
            raw_boundary_faces,
            result.n_source_faces_on_boundary);
        result.n_candidate_boundary_faces = provenance.n_candidate_boundary_faces;
        result.n_owned_candidate_faces = provenance.n_owned_candidate_faces;
        result.n_unowned_candidate_faces = provenance.n_unowned_candidate_faces;
        result.n_source_planar_patches = provenance.n_source_planar_patches;
        result.n_uncovered_source_patches = provenance.n_uncovered_source_patches;
        result.n_area_mismatch_patches = provenance.n_area_mismatch_patches;
        result.n_feature_boundary_mismatches =
            provenance.n_feature_boundary_mismatches;
        result.n_overlap_pairs = provenance.n_overlap_pairs;
        result.source_faces_preserved = provenance.preserved;
    }
    if (boundary_faces.empty()) {
        return result;
    }

    const std::vector<size_t> source_roots = face_component_roots(source_faces);
    const std::vector<size_t> candidate_roots = face_component_roots(boundary_faces);
    std::vector<size_t> unique_source_roots = source_roots;
    std::vector<size_t> unique_candidate_roots = candidate_roots;
    sort_unique(unique_source_roots);
    sort_unique(unique_candidate_roots);

    constexpr size_t absent = std::numeric_limits<size_t>::max();
    std::vector<size_t> source_component_for_vertex(source_vertex_count, absent);
    std::vector<unsigned char> source_surface_vertex(source_vertex_count, 0U);
    for (size_t face_index = 0; face_index < source_faces.size(); ++face_index) {
        const size_t root = source_roots[face_index];
        for (const int64_t vertex : source_faces[face_index]) {
            const size_t index = static_cast<size_t>(vertex);
            source_surface_vertex[index] = 1U;
            if (source_component_for_vertex[index] == absent) {
                source_component_for_vertex[index] = root;
            } else if (source_component_for_vertex[index] != root) {
                throw std::invalid_argument(
                    "source vertex belongs to multiple edge-connected components");
            }
        }
    }

    std::vector<unsigned char> source_vertex_on_boundary(source_vertex_count, 0U);
    std::vector<ComponentPair> component_pairs;
    component_pairs.reserve(checked_entity_count(
        boundary_faces.size(), 3U, "boundary_faces"));
    std::vector<size_t> anchored_candidate_roots;
    anchored_candidate_roots.reserve(boundary_faces.size());
    size_t unknown_source_vertex_anchors = 0U;
    std::vector<unsigned char> unknown_seen(source_vertex_count, 0U);
    for (size_t face_index = 0; face_index < boundary_faces.size(); ++face_index) {
        const size_t candidate_root = candidate_roots[face_index];
        bool anchored = false;
        for (const int64_t vertex : boundary_faces[face_index]) {
            const size_t index = static_cast<size_t>(vertex);
            if (index >= source_vertex_count) {
                continue;
            }
            const size_t source_root = source_component_for_vertex[index];
            if (source_root == absent) {
                if (unknown_seen[index] == 0U) {
                    unknown_seen[index] = 1U;
                    ++unknown_source_vertex_anchors;
                }
                continue;
            }
            source_vertex_on_boundary[index] = 1U;
            component_pairs.push_back(ComponentPair{source_root, candidate_root});
            anchored = true;
        }
        if (anchored) {
            anchored_candidate_roots.push_back(candidate_root);
        }
    }
    sort_unique(component_pairs);
    sort_unique(anchored_candidate_roots);

    size_t source_surface_vertices = 0U;
    size_t source_vertices_on_boundary = 0U;
    for (size_t vertex = 0; vertex < source_vertex_count; ++vertex) {
        source_surface_vertices += source_surface_vertex[vertex] != 0U;
        source_vertices_on_boundary += source_vertex_on_boundary[vertex] != 0U;
    }

    size_t matched_source_components = 0U;
    size_t split_source_components = 0U;
    for (size_t index = 0; index < component_pairs.size();) {
        const size_t source_root = component_pairs[index][0];
        size_t end = index + 1U;
        size_t candidate_count = 1U;
        while (end < component_pairs.size()
               && component_pairs[end][0] == source_root) {
            if (component_pairs[end][1] != component_pairs[end - 1U][1]) {
                ++candidate_count;
            }
            ++end;
        }
        ++matched_source_components;
        split_source_components += candidate_count > 1U;
        index = end;
    }

    std::vector<ComponentPair> candidate_source_pairs;
    candidate_source_pairs.reserve(component_pairs.size());
    for (const ComponentPair& pair : component_pairs) {
        candidate_source_pairs.push_back(ComponentPair{pair[1], pair[0]});
    }
    sort_unique(candidate_source_pairs);
    size_t mixed_candidate_components = 0U;
    for (size_t index = 0; index < candidate_source_pairs.size();) {
        const size_t candidate_root = candidate_source_pairs[index][0];
        size_t end = index + 1U;
        size_t source_count = 1U;
        while (end < candidate_source_pairs.size()
               && candidate_source_pairs[end][0] == candidate_root) {
            if (candidate_source_pairs[end][1]
                != candidate_source_pairs[end - 1U][1]) {
                ++source_count;
            }
            ++end;
        }
        mixed_candidate_components += source_count > 1U;
        index = end;
    }

    result.n_source_components = unique_source_roots.size();
    result.n_candidate_boundary_components = unique_candidate_roots.size();
    result.n_source_surface_vertices = source_surface_vertices;
    result.n_source_vertices_on_boundary = source_vertices_on_boundary;
    result.n_missing_source_vertices =
        source_surface_vertices - source_vertices_on_boundary;
    result.n_matched_source_components = matched_source_components;
    result.n_mixed_candidate_components = mixed_candidate_components;
    result.n_split_source_components = split_source_components;
    result.n_unanchored_candidate_components =
        unique_candidate_roots.size() - anchored_candidate_roots.size();
    result.n_unknown_source_vertex_anchors = unknown_source_vertex_anchors;
    result.bijective = result.n_source_components > 0U
        && result.n_source_components == result.n_candidate_boundary_components
        && result.n_source_components == result.n_matched_source_components
        && result.n_missing_source_vertices == 0U
        && result.n_mixed_candidate_components == 0U
        && result.n_split_source_components == 0U
        && result.n_unanchored_candidate_components == 0U
        && result.n_unknown_source_vertex_anchors == 0U;
    return result;
}

py::dict audit_source_component_bijection(
    const py::array& source_points,
    const py::array& source_faces,
    const py::array& candidate_points,
    const py::array& tets)
{
    validate_point_array(source_points, "source_points");
    validate_cdt_array(source_faces, 3, "source_faces");
    validate_point_array(candidate_points, "candidate_points");
    validate_cdt_array(tets, 4, "tets");
    const auto source_point_info = source_points.request();
    const auto source_info = source_faces.request();
    const auto candidate_point_info = candidate_points.request();
    const auto tet_info = tets.request();
    const auto source_point_view = std::span{
        static_cast<const double*>(source_point_info.ptr),
        static_cast<size_t>(source_point_info.size)};
    const auto source_view = std::span{
        static_cast<const int64_t*>(source_info.ptr),
        static_cast<size_t>(source_info.size)};
    const auto candidate_point_view = std::span{
        static_cast<const double*>(candidate_point_info.ptr),
        static_cast<size_t>(candidate_point_info.size)};
    const auto tet_view = std::span{
        static_cast<const int64_t*>(tet_info.ptr),
        static_cast<size_t>(tet_info.size)};

    SourceComponentAuditResult audit;
    {
        py::gil_scoped_release release;
        audit = audit_source_component_bijection_impl(
            source_point_view,
            source_view,
            candidate_point_view,
            tet_view);
    }

    py::dict result;
    result["n_source_components"] = audit.n_source_components;
    result["n_candidate_boundary_components"] =
        audit.n_candidate_boundary_components;
    result["n_source_surface_vertices"] = audit.n_source_surface_vertices;
    result["n_source_vertices_on_boundary"] =
        audit.n_source_vertices_on_boundary;
    result["n_missing_source_vertices"] = audit.n_missing_source_vertices;
    result["n_matched_source_components"] = audit.n_matched_source_components;
    result["n_mixed_candidate_components"] =
        audit.n_mixed_candidate_components;
    result["n_split_source_components"] = audit.n_split_source_components;
    result["n_unanchored_candidate_components"] =
        audit.n_unanchored_candidate_components;
    result["n_unknown_source_vertex_anchors"] =
        audit.n_unknown_source_vertex_anchors;
    result["n_source_faces"] = audit.n_source_faces;
    result["n_source_faces_on_boundary"] = audit.n_source_faces_on_boundary;
    result["n_missing_source_faces"] = audit.n_missing_source_faces;
    result["n_candidate_boundary_faces"] = audit.n_candidate_boundary_faces;
    result["n_owned_candidate_faces"] = audit.n_owned_candidate_faces;
    result["n_unowned_candidate_faces"] = audit.n_unowned_candidate_faces;
    result["n_source_planar_patches"] = audit.n_source_planar_patches;
    result["n_uncovered_source_patches"] = audit.n_uncovered_source_patches;
    result["n_area_mismatch_patches"] = audit.n_area_mismatch_patches;
    result["n_feature_boundary_mismatches"] =
        audit.n_feature_boundary_mismatches;
    result["n_overlap_pairs"] = audit.n_overlap_pairs;
    result["source_faces_preserved"] = audit.source_faces_preserved;
    result["bijective"] = audit.bijective;
    return result;
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
    m.def("audit_tet_boundary", &audit_tet_boundary_native,
          py::arg("points"), py::arg("tets"),
          py::arg("relative_volume_tolerance") = 1e-12);
    m.def("audit_cdt_constraints", &audit_cdt_constraints,
          py::arg("surface_faces").noconvert(), py::arg("tets").noconvert(),
          "Audit exact CDT edge/face membership without copying input arrays.\n\n"
          "Inputs must be immutable for the duration of this call because the GIL "
          "is released while their C-contiguous int64 storage is read.");
    m.def("audit_source_component_bijection", &audit_source_component_bijection,
          py::arg("source_points").noconvert(),
          py::arg("source_faces").noconvert(),
          py::arg("candidate_points").noconvert(),
          py::arg("tets").noconvert(),
          "Audit exact source-to-boundary component provenance without geometry "
          "mutation. Inputs must be immutable while the GIL is released.");
    m.def("recover_targeted_edges_23", &recover_targeted_edges_23,
          py::arg("points"), py::arg("tets"), py::arg("edges"),
          py::arg("max_attempts") = 200);
}
