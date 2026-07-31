// Face cleaning and topology assembly for write_generic_polymesh.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <limits>
#include <numeric>
#include <span>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace py = pybind11;

namespace {

using Label = long long;
static_assert(
    sizeof(Label) == sizeof(std::int64_t)
        && std::numeric_limits<Label>::is_signed
        && std::numeric_limits<Label>::digits == 63,
    "native_polymesh requires a signed 64-bit Label");
using Face = std::vector<Label>;
using Cell = std::vector<Face>;
using Cells = std::vector<Cell>;

struct DualHullAssemblyInput {
    std::span<const double> seed_points;
    std::span<const double> cell_points;
    std::span<const Label> cell_point_offsets;
    std::span<const Label> hull_simplices;
    std::span<const Label> cell_hull_offsets;
    std::span<const double> hull_equations;
    std::span<const Label> n_tet_points;
    std::span<const Label> local_source_label_ids;
};

struct DualHullAssemblyResult {
    bool accepted = true;
    std::string reason = "ok";
    std::vector<double> points;
    std::vector<Label> face_offsets {0};
    std::vector<Label> face_indices;
    std::vector<Label> cell_face_offsets {0};
    std::vector<std::uint8_t> face_is_cap;
    std::vector<Label> face_label_ids;
    std::vector<std::uint8_t> face_order_ambiguous;
};

struct RaggedFaces {
    std::vector<size_t> offsets;
    std::vector<Label> indices;

    [[nodiscard]] size_t size() const noexcept
    {
        return offsets.empty() ? 0U : offsets.size() - 1U;
    }

    [[nodiscard]] std::span<const Label> face(const size_t index) const noexcept
    {
        const size_t begin = offsets[index];
        return {indices.data() + begin, offsets[index + 1U] - begin};
    }
};

enum class StarExampleKind : unsigned char {
    FewerThanFourVertices,
    NonPositiveSubtet,
};

struct StarExample {
    StarExampleKind kind;
    Label cell;
    Label face = -1;
    Label edge_a = -1;
    Label edge_b = -1;
    size_t edge_index = 0U;
    double signed_volume6 = 0.0;
    double normalized_signed_volume6 = 0.0;
};

struct StarSubtetGeometry {
    size_t face_index;
    size_t edge_index;
    Label edge_a;
    Label edge_b;
    const double* point_a;
    double edge_x;
    double edge_y;
    double edge_z;
    double face_x;
    double face_y;
    double face_z;
};

struct FaceHash {
    size_t operator()(const Face& face) const noexcept
    {
        size_t seed = face.size();
        for (const Label value : face) {
            const auto hash = std::hash<Label>{}(value);
            seed ^= hash + 0x9e3779b97f4a7c15ULL + (seed << 6U) + (seed >> 2U);
        }
        return seed;
    }
};

template <size_t Size>
struct ArrayHash {
    size_t operator()(const std::array<Label, Size>& values) const noexcept
    {
        size_t seed = Size;
        for (const Label value : values) {
            const auto hash = std::hash<Label>{}(value);
            seed ^= hash + 0x9e3779b97f4a7c15ULL + (seed << 6U) + (seed >> 2U);
        }
        return seed;
    }
};

[[nodiscard]] size_t checked_size_product(
    const size_t count,
    const size_t width,
    const char* const name)
{
    if (width != 0U && count > std::numeric_limits<size_t>::max() / width) {
        throw std::overflow_error(std::string(name) + " size multiplication overflow");
    }
    return count * width;
}

[[nodiscard]] Label checked_label_size(const size_t value, const char* const name)
{
    constexpr auto label_max = static_cast<size_t>(std::numeric_limits<Label>::max());
    if (value > label_max) {
        throw std::overflow_error(std::string(name) + " exceeds int64 range");
    }
    return static_cast<Label>(value);
}

[[nodiscard]] bool quantize_nearest_even(
    const double value,
    const double scale,
    Label& result) noexcept
{
    const double scaled = value * scale;
    if (!std::isfinite(scaled)) {
        return false;
    }
    const double rounded = std::nearbyint(scaled);
    constexpr double lower = static_cast<double>(std::numeric_limits<Label>::min());
    constexpr double upper_exclusive = -lower;
    if (!std::isfinite(rounded) || rounded < lower || rounded >= upper_exclusive) {
        return false;
    }
    result = static_cast<Label>(rounded);
    return true;
}

template <size_t Size>
[[nodiscard]] bool quantized_key(
    const double* const values,
    const double scale,
    std::array<Label, Size>& key) noexcept
{
    for (size_t index = 0U; index < Size; ++index) {
        if (!quantize_nearest_even(values[index], scale, key[index])) {
            return false;
        }
    }
    return true;
}

struct PlaneGroup {
    std::array<Label, 4> key;
    std::vector<size_t> simplex_rows;
};

[[nodiscard]] DualHullAssemblyResult refused_dual_hull_assembly(std::string reason)
{
    DualHullAssemblyResult result;
    result.accepted = false;
    result.reason = std::move(reason);
    return result;
}

[[nodiscard]] DualHullAssemblyResult assemble_dual_hull_faces_core(
    const DualHullAssemblyInput& input)
{
    constexpr double point_scale = 1.0e9;
    constexpr double equation_scale = 1.0e6;
    constexpr double vector_epsilon = 1.0e-30;
    constexpr double angle_epsilon_multiplier = 64.0;

    if (std::fegetround() != FE_TONEAREST) {
        return refused_dual_hull_assembly("non_nearest_even_rounding_mode");
    }
    if (input.seed_points.size() % 3U != 0U) {
        throw std::invalid_argument("seed_points flattened length must be divisible by 3");
    }
    if (input.cell_points.size() % 3U != 0U) {
        throw std::invalid_argument("cell_points flattened length must be divisible by 3");
    }
    if (input.hull_simplices.size() % 3U != 0U) {
        throw std::invalid_argument("hull_simplices flattened length must be divisible by 3");
    }
    if (input.hull_equations.size() % 4U != 0U) {
        throw std::invalid_argument("hull_equations flattened length must be divisible by 4");
    }
    if (input.cell_point_offsets.empty() || input.cell_hull_offsets.empty()) {
        throw std::invalid_argument("cell offsets must contain the zero sentinel");
    }
    const size_t num_cells = input.cell_point_offsets.size() - 1U;
    if (input.cell_hull_offsets.size() != num_cells + 1U
        || input.n_tet_points.size() != num_cells) {
        throw std::invalid_argument("cell metadata lengths disagree");
    }
    const size_t num_cell_points = input.cell_points.size() / 3U;
    const size_t num_hull_rows = input.hull_simplices.size() / 3U;
    if (input.hull_equations.size() / 4U != num_hull_rows) {
        throw std::invalid_argument("hull simplices and equations lengths disagree");
    }
    if (input.local_source_label_ids.size() != num_cell_points) {
        throw std::invalid_argument("local_source_label_ids length must match cell_points");
    }
    if (input.cell_point_offsets.front() != 0
        || input.cell_hull_offsets.front() != 0) {
        throw std::invalid_argument("cell offsets must begin at zero");
    }
    if (input.cell_point_offsets.back() != checked_label_size(num_cell_points, "cell points")
        || input.cell_hull_offsets.back() != checked_label_size(num_hull_rows, "hull rows")) {
        throw std::invalid_argument("cell offsets must end at flattened row counts");
    }

    for (size_t cell = 0U; cell < num_cells; ++cell) {
        const Label point_begin = input.cell_point_offsets[cell];
        const Label point_end = input.cell_point_offsets[cell + 1U];
        const Label hull_begin = input.cell_hull_offsets[cell];
        const Label hull_end = input.cell_hull_offsets[cell + 1U];
        if (point_begin < 0 || point_end < point_begin
            || hull_begin < 0 || hull_end < hull_begin) {
            throw std::invalid_argument("cell offsets must be nonnegative and monotonic");
        }
        const Label local_point_count = point_end - point_begin;
        if (input.n_tet_points[cell] < 0
            || input.n_tet_points[cell] > local_point_count) {
            throw std::invalid_argument("n_tet_points is outside its cell point range");
        }
        for (Label row = hull_begin; row < hull_end; ++row) {
            const size_t row_index = static_cast<size_t>(row);
            for (size_t corner = 0U; corner < 3U; ++corner) {
                const Label local_index = input.hull_simplices[row_index * 3U + corner];
                if (local_index < 0 || local_index >= local_point_count) {
                    throw std::out_of_range("hull simplex local point index is out of bounds");
                }
            }
        }
        for (Label row = point_begin; row < point_end; ++row) {
            if (input.local_source_label_ids[static_cast<size_t>(row)] < -1) {
                throw std::invalid_argument("local source label ids must be -1 or nonnegative");
            }
        }
    }

    DualHullAssemblyResult result;
    result.points.assign(input.seed_points.begin(), input.seed_points.end());
    result.cell_face_offsets.reserve(num_cells + 1U);
    result.cell_face_offsets.clear();
    result.cell_face_offsets.push_back(0);

    using PointKey = std::array<Label, 3>;
    std::unordered_map<PointKey, Label, ArrayHash<3>> point_ids;
    const size_t num_seed_points = input.seed_points.size() / 3U;
    if (num_seed_points > std::numeric_limits<size_t>::max() - num_cell_points) {
        throw std::overflow_error("dual point reserve size overflow");
    }
    const size_t reserve_points = num_seed_points + num_cell_points;
    point_ids.reserve(reserve_points);
    for (size_t point = 0U; point < num_seed_points; ++point) {
        PointKey key {};
        if (!quantized_key<3>(input.seed_points.data() + point * 3U, point_scale, key)) {
            return refused_dual_hull_assembly("seed_point_quantization_overflow");
        }
        const auto [position, inserted] = point_ids.emplace(
            key, checked_label_size(point, "seed point index"));
        static_cast<void>(position);
        if (!inserted) {
            throw std::invalid_argument("seed_points must be unique under point quantization");
        }
    }

    for (size_t cell = 0U; cell < num_cells; ++cell) {
        const size_t point_begin = static_cast<size_t>(input.cell_point_offsets[cell]);
        const size_t point_end = static_cast<size_t>(input.cell_point_offsets[cell + 1U]);
        const size_t hull_begin = static_cast<size_t>(input.cell_hull_offsets[cell]);
        const size_t hull_end = static_cast<size_t>(input.cell_hull_offsets[cell + 1U]);
        const size_t local_point_count = point_end - point_begin;
        const Label n_tet = input.n_tet_points[cell];

        std::vector<PlaneGroup> groups;
        groups.reserve(hull_end - hull_begin);
        std::unordered_map<std::array<Label, 4>, size_t, ArrayHash<4>> group_index;
        group_index.reserve(hull_end - hull_begin);
        for (size_t row = hull_begin; row < hull_end; ++row) {
            std::array<Label, 4> key {};
            if (!quantized_key<4>(
                    input.hull_equations.data() + row * 4U,
                    equation_scale,
                    key)) {
                return refused_dual_hull_assembly("hull_equation_quantization_overflow");
            }
            const auto position = group_index.find(key);
            if (position == group_index.end()) {
                const size_t index = groups.size();
                group_index.emplace(key, index);
                groups.push_back(PlaneGroup {key, {row}});
            } else {
                groups[position->second].simplex_rows.push_back(row);
            }
        }

        for (const PlaneGroup& group : groups) {
            std::vector<Label> vertices;
            vertices.reserve(checked_size_product(group.simplex_rows.size(), 3U, "face vertices"));
            for (const size_t row : group.simplex_rows) {
                for (size_t corner = 0U; corner < 3U; ++corner) {
                    vertices.push_back(input.hull_simplices[row * 3U + corner]);
                }
            }
            std::sort(vertices.begin(), vertices.end());
            vertices.erase(std::unique(vertices.begin(), vertices.end()), vertices.end());
            if (vertices.size() < 3U) {
                continue;
            }

            std::array<double, 3> centroid {0.0, 0.0, 0.0};
            for (const Label local_index : vertices) {
                const size_t global_point = point_begin + static_cast<size_t>(local_index);
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    centroid[axis] += input.cell_points[global_point * 3U + axis];
                }
            }
            for (double& value : centroid) {
                value /= static_cast<double>(vertices.size());
            }

            const size_t normal_row = group.simplex_rows.front();
            const std::array<double, 3> normal {
                input.hull_equations[normal_row * 4U],
                input.hull_equations[normal_row * 4U + 1U],
                input.hull_equations[normal_row * 4U + 2U],
            };
            std::array<double, 3> basis_one {};
            double basis_length = 0.0;
            for (const Label local_index : vertices) {
                const size_t global_point = point_begin + static_cast<size_t>(local_index);
                double projection = 0.0;
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    basis_one[axis] = input.cell_points[global_point * 3U + axis] - centroid[axis];
                    projection += basis_one[axis] * normal[axis];
                }
                basis_length = 0.0;
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    basis_one[axis] -= normal[axis] * projection;
                    basis_length += basis_one[axis] * basis_one[axis];
                }
                basis_length = std::sqrt(basis_length);
                if (basis_length >= vector_epsilon) {
                    break;
                }
            }
            if (!std::isfinite(basis_length)) {
                return refused_dual_hull_assembly("nonfinite_face_basis");
            }
            if (basis_length < vector_epsilon) {
                continue;
            }
            for (double& value : basis_one) {
                value /= basis_length;
            }
            const std::array<double, 3> basis_two {
                normal[1] * basis_one[2] - normal[2] * basis_one[1],
                normal[2] * basis_one[0] - normal[0] * basis_one[2],
                normal[0] * basis_one[1] - normal[1] * basis_one[0],
            };

            struct AngularVertex {
                double angle;
                Label local_index;
            };
            std::vector<AngularVertex> angular_vertices;
            angular_vertices.reserve(vertices.size());
            bool branch_cut_ambiguous = false;
            for (const Label local_index : vertices) {
                const size_t global_point = point_begin + static_cast<size_t>(local_index);
                volatile double x_accumulator = 0.0;
                volatile double y_accumulator = 0.0;
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    const double relative =
                        input.cell_points[global_point * 3U + axis] - centroid[axis];
                    x_accumulator = x_accumulator + relative * basis_one[axis];
                    y_accumulator = y_accumulator + relative * basis_two[axis];
                }
                const double x = x_accumulator;
                const double y = y_accumulator;
                const double angle = std::atan2(y, x);
                if (!std::isfinite(angle)) {
                    return refused_dual_hull_assembly("nonfinite_face_angle");
                }
                const double branch_scale = std::max(1.0, std::abs(x));
                if (x < 0.0
                    && std::abs(y)
                        <= angle_epsilon_multiplier
                            * std::numeric_limits<double>::epsilon() * branch_scale) {
                    branch_cut_ambiguous = true;
                }
                angular_vertices.push_back({angle, local_index});
            }
            std::sort(
                angular_vertices.begin(),
                angular_vertices.end(),
                [](const AngularVertex& left, const AngularVertex& right) {
                    return left.angle < right.angle;
                });
            for (size_t index = 1U; index < angular_vertices.size(); ++index) {
                const double left = angular_vertices[index - 1U].angle;
                const double right = angular_vertices[index].angle;
                const double scale = std::max({1.0, std::abs(left), std::abs(right)});
                if (right - left
                    <= angle_epsilon_multiplier * std::numeric_limits<double>::epsilon() * scale) {
                    return refused_dual_hull_assembly("ambiguous_face_angle_order");
                }
            }

            bool is_cap = false;
            Label selected_label = -1;
            bool multiple_labels = false;
            for (const AngularVertex& angular_vertex : angular_vertices) {
                const Label local_index = angular_vertex.local_index;
                const size_t global_point = point_begin + static_cast<size_t>(local_index);
                PointKey key {};
                if (!quantized_key<3>(
                        input.cell_points.data() + global_point * 3U,
                        point_scale,
                        key)) {
                    return refused_dual_hull_assembly("cell_point_quantization_overflow");
                }
                const auto position = point_ids.find(key);
                Label point_id = -1;
                if (position != point_ids.end()) {
                    point_id = position->second;
                } else {
                    const size_t next_point = result.points.size() / 3U;
                    point_id = checked_label_size(next_point, "dual point index");
                    point_ids.emplace(key, point_id);
                    for (size_t axis = 0U; axis < 3U; ++axis) {
                        result.points.push_back(input.cell_points[global_point * 3U + axis]);
                    }
                }
                result.face_indices.push_back(point_id);
                is_cap = is_cap || local_index >= n_tet;
                const Label label = input.local_source_label_ids[global_point];
                if (label >= 0) {
                    if (selected_label < 0) {
                        selected_label = label;
                    } else if (selected_label != label) {
                        multiple_labels = true;
                    }
                }
            }
            result.face_offsets.push_back(
                checked_label_size(result.face_indices.size(), "face index offset"));
            result.face_is_cap.push_back(is_cap ? 1U : 0U);
            result.face_label_ids.push_back(multiple_labels ? -1 : selected_label);
            result.face_order_ambiguous.push_back(branch_cut_ambiguous ? 1U : 0U);
        }
        result.cell_face_offsets.push_back(
            checked_label_size(result.face_is_cap.size(), "cell face offset"));
        static_cast<void>(local_point_count);
    }
    return result;
}

template <size_t Size>
struct IncidenceBucket {
    std::array<Label, Size> key;
    std::vector<Label> owners;
};

struct FaceRef {
    Label cell;
    Face vertices;
};

struct FaceBucket {
    Face key;
    std::vector<FaceRef> refs;
};

template <size_t Size>
struct CanonicalSimplexRecord {
    std::array<Label, Size> key;
    Label owner;
};

struct TopologyResult {
    std::vector<Face> internal_faces;
    std::vector<Label> internal_owner;
    std::vector<Label> internal_neighbour;
    std::vector<Face> boundary_faces;
    std::vector<Label> boundary_owner;
    Label num_cells = 0;
    Label num_cells_dropped = 0;
    Label num_faces_dropped = 0;
    std::vector<std::pair<Label, Label>> non_manifold;
};

enum class DualPointStatus : std::uint8_t {
    Circumcenter = 0,
    Clipped = 1,
    SingularCentroid = 2,
    NonFiniteSolveCentroid = 3,
};

enum class Solve3Status : unsigned char {
    Success,
    Singular,
    NonFinite,
};

[[nodiscard]] Solve3Status solve_3x3(
    std::array<double, 9> matrix,
    std::array<double, 3> rhs,
    std::array<double, 3>& solution) noexcept
{
    for (size_t column = 0U; column < 3U; ++column) {
        size_t pivot_row = column;
        double pivot_magnitude = std::abs(matrix[column * 3U + column]);
        for (size_t row = column + 1U; row < 3U; ++row) {
            const double candidate = std::abs(matrix[row * 3U + column]);
            if (candidate > pivot_magnitude) {
                pivot_magnitude = candidate;
                pivot_row = row;
            }
        }
        if (!std::isfinite(pivot_magnitude)) {
            return Solve3Status::NonFinite;
        }
        if (pivot_magnitude == 0.0) {
            return Solve3Status::Singular;
        }
        if (pivot_row != column) {
            for (size_t entry = column; entry < 3U; ++entry) {
                std::swap(
                    matrix[column * 3U + entry],
                    matrix[pivot_row * 3U + entry]);
            }
            std::swap(rhs[column], rhs[pivot_row]);
        }

        const double pivot = matrix[column * 3U + column];
        for (size_t row = column + 1U; row < 3U; ++row) {
            const double factor = matrix[row * 3U + column] / pivot;
            if (!std::isfinite(factor)) {
                return Solve3Status::NonFinite;
            }
            matrix[row * 3U + column] = 0.0;
            for (size_t entry = column + 1U; entry < 3U; ++entry) {
                matrix[row * 3U + entry] -= factor * matrix[column * 3U + entry];
            }
            rhs[row] -= factor * rhs[column];
        }
    }

    for (size_t reverse = 0U; reverse < 3U; ++reverse) {
        const size_t row = 2U - reverse;
        double value = rhs[row];
        for (size_t column = row + 1U; column < 3U; ++column) {
            value -= matrix[row * 3U + column] * solution[column];
        }
        const double pivot = matrix[row * 3U + row];
        if (pivot == 0.0) {
            return Solve3Status::Singular;
        }
        solution[row] = value / pivot;
        if (!std::isfinite(solution[row])) {
            return Solve3Status::NonFinite;
        }
    }
    return Solve3Status::Success;
}

[[nodiscard]] bool finite3(const std::array<double, 3>& point) noexcept
{
    return std::isfinite(point[0]) && std::isfinite(point[1])
        && std::isfinite(point[2]);
}

size_t point_offset(Label vertex, size_t num_points)
{
    Label normalized = vertex;
    if (normalized < 0) {
        const auto point_count = static_cast<Label>(num_points);
        if (normalized < -point_count) {
            throw py::index_error("vertex index is out of bounds");
        }
        normalized += point_count;
    }
    if (normalized < 0 || static_cast<unsigned long long>(normalized) >= num_points) {
        throw py::index_error("vertex index is out of bounds");
    }
    return static_cast<size_t>(normalized) * 3U;
}

RaggedFaces parse_ragged_faces(const py::sequence& faces, const size_t num_points)
{
    RaggedFaces result;
    const size_t face_count = static_cast<size_t>(py::len(faces));
    result.offsets.reserve(face_count + 1U);
    result.offsets.push_back(0U);

    size_t total_indices = 0U;
    for (const py::handle face_handle : faces) {
        const auto face = py::reinterpret_borrow<py::sequence>(face_handle);
        total_indices += static_cast<size_t>(py::len(face));
        result.offsets.push_back(total_indices);
    }
    result.indices.reserve(total_indices);

    for (const py::handle face_handle : faces) {
        const auto face = py::reinterpret_borrow<py::sequence>(face_handle);
        for (const py::handle vertex_handle : face) {
            Label vertex = py::cast<Label>(vertex_handle);
            if (vertex < 0) {
                vertex += static_cast<Label>(num_points);
            }
            if (vertex < 0 || static_cast<size_t>(vertex) >= num_points) {
                throw py::index_error("face vertex index is out of bounds");
            }
            result.indices.push_back(vertex);
        }
    }
    return result;
}

py::array_t<bool> face_flip_mask(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::sequence& faces,
    const py::array_t<Label, py::array::c_style | py::array::forcecast>& owners,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& cell_centroids)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (owners.ndim() != 1) {
        throw std::invalid_argument("owners must have shape (F,)");
    }
    if (cell_centroids.ndim() != 2 || cell_centroids.shape(1) != 3) {
        throw std::invalid_argument("cell_centroids must have shape (C, 3)");
    }

    const size_t point_count = static_cast<size_t>(points.shape(0));
    const RaggedFaces ragged = parse_ragged_faces(faces, point_count);
    if (static_cast<size_t>(owners.shape(0)) != ragged.size()) {
        throw std::invalid_argument("owners length must match faces");
    }
    const auto owner_values = owners.unchecked<1>();
    const Label centroid_count = static_cast<Label>(cell_centroids.shape(0));
    for (size_t face_index = 0; face_index < ragged.size(); ++face_index) {
        if (ragged.face(face_index).size() < 3U) {
            throw std::invalid_argument("faces must contain at least three vertices");
        }
        const Label owner = owner_values(static_cast<py::ssize_t>(face_index));
        if (owner < 0 || owner >= centroid_count) {
            throw py::index_error("face owner index is out of bounds");
        }
    }

    py::array_t<bool> result(
        py::array::ShapeContainer{static_cast<py::ssize_t>(ragged.size())});
    bool* const flips = result.mutable_data();
    const double* const point_data = points.data();
    const double* const centroid_data = cell_centroids.data();
    const Label* const owner_data = owners.data();

    {
        py::gil_scoped_release release;
        for (size_t face_index = 0; face_index < ragged.size(); ++face_index) {
            const std::span<const Label> face = ragged.face(face_index);
            double face_centroid[3]{0.0, 0.0, 0.0};
            for (const Label vertex : face) {
                const double* const point = point_data + static_cast<size_t>(vertex) * 3U;
                face_centroid[0] += point[0];
                face_centroid[1] += point[1];
                face_centroid[2] += point[2];
            }
            const double inverse_size = 1.0 / static_cast<double>(face.size());
            face_centroid[0] *= inverse_size;
            face_centroid[1] *= inverse_size;
            face_centroid[2] *= inverse_size;

            const double* const p0 = point_data + static_cast<size_t>(face[0]) * 3U;
            const double* const p1 = point_data + static_cast<size_t>(face[1]) * 3U;
            const double* const p2 = point_data + static_cast<size_t>(face[2]) * 3U;
            const double ax = p1[0] - p0[0];
            const double ay = p1[1] - p0[1];
            const double az = p1[2] - p0[2];
            const double bx = p2[0] - p0[0];
            const double by = p2[1] - p0[1];
            const double bz = p2[2] - p0[2];
            const double nx = ay * bz - az * by;
            const double ny = az * bx - ax * bz;
            const double nz = ax * by - ay * bx;
            const double* const cell_centroid = centroid_data
                + static_cast<size_t>(owner_data[face_index]) * 3U;
            const double direction = nx * (face_centroid[0] - cell_centroid[0])
                + ny * (face_centroid[1] - cell_centroid[1])
                + nz * (face_centroid[2] - cell_centroid[2]);
            flips[face_index] = direction < 0.0;
        }
    }
    return result;
}

py::tuple face_plane_geometry(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::sequence& faces,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& plane_normals,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& plane_offsets,
    const double tolerance)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (plane_normals.ndim() != 2 || plane_normals.shape(1) != 3) {
        throw std::invalid_argument("plane_normals must have shape (P, 3)");
    }
    if (plane_offsets.ndim() != 1
        || plane_offsets.shape(0) != plane_normals.shape(0)) {
        throw std::invalid_argument("plane_offsets must have shape (P,)");
    }

    const RaggedFaces ragged = parse_ragged_faces(
        faces, static_cast<size_t>(points.shape(0)));
    for (size_t face_index = 0; face_index < ragged.size(); ++face_index) {
        if (ragged.face(face_index).size() < 3U) {
            throw std::invalid_argument("faces must contain at least three vertices");
        }
    }

    py::array_t<bool> on_plane(
        py::array::ShapeContainer{static_cast<py::ssize_t>(ragged.size())});
    bool* const flags = on_plane.mutable_data();
    const double* const point_data = points.data();
    const double* const normal_data = plane_normals.data();
    const double* const offset_data = plane_offsets.data();
    const size_t plane_count = static_cast<size_t>(plane_normals.shape(0));
    double on_area = 0.0;
    double off_area = 0.0;

    {
        py::gil_scoped_release release;
        for (size_t face_index = 0; face_index < ragged.size(); ++face_index) {
            const std::span<const Label> face = ragged.face(face_index);
            const double* const base = point_data + static_cast<size_t>(face[0]) * 3U;
            double area_vector[3]{0.0, 0.0, 0.0};
            for (size_t local = 1U; local + 1U < face.size(); ++local) {
                const double* const first = point_data
                    + static_cast<size_t>(face[local]) * 3U;
                const double* const second = point_data
                    + static_cast<size_t>(face[local + 1U]) * 3U;
                const double ax = first[0] - base[0];
                const double ay = first[1] - base[1];
                const double az = first[2] - base[2];
                const double bx = second[0] - base[0];
                const double by = second[1] - base[1];
                const double bz = second[2] - base[2];
                area_vector[0] += (ay * bz - az * by) / 2.0;
                area_vector[1] += (az * bx - ax * bz) / 2.0;
                area_vector[2] += (ax * by - ay * bx) / 2.0;
            }
            const double area = std::sqrt(
                area_vector[0] * area_vector[0]
                + area_vector[1] * area_vector[1]
                + area_vector[2] * area_vector[2]);

            bool matches_plane = false;
            for (size_t plane = 0U; plane < plane_count && !matches_plane; ++plane) {
                const double* const normal = normal_data + plane * 3U;
                bool all_vertices_match = true;
                for (const Label vertex : face) {
                    const double* const point = point_data
                        + static_cast<size_t>(vertex) * 3U;
                    const double distance = point[0] * normal[0]
                        + point[1] * normal[1]
                        + point[2] * normal[2]
                        + offset_data[plane];
                    if (!(std::abs(distance) < tolerance)) {
                        all_vertices_match = false;
                        break;
                    }
                }
                matches_plane = all_vertices_match;
            }
            flags[face_index] = matches_plane;
            if (matches_plane) {
                on_area += area;
            } else {
                off_area += area;
            }
        }
    }
    return py::make_tuple(on_area, off_area, std::move(on_plane));
}

py::tuple star_validity(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::sequence& faces,
    const py::array_t<Label, py::array::c_style | py::array::forcecast>& owners,
    const py::array_t<Label, py::array::c_style | py::array::forcecast>& neighbours,
    const Label num_cells,
    const double tolerance,
    const Label max_examples)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (owners.ndim() != 1) {
        throw std::invalid_argument("owners must have shape (F,)");
    }
    if (neighbours.ndim() != 1) {
        throw std::invalid_argument("neighbours must have shape (I,)");
    }

    const size_t point_count = static_cast<size_t>(points.shape(0));
    const RaggedFaces ragged = parse_ragged_faces(faces, point_count);
    const size_t face_count = ragged.size();
    if (static_cast<size_t>(owners.shape(0)) < face_count) {
        throw std::invalid_argument("owners length must cover faces");
    }
    if (point_count == 0U || face_count == 0U || owners.shape(0) == 0
        || num_cells <= 0) {
        return py::make_tuple(0, 0, py::tuple());
    }

    const size_t cell_count = static_cast<size_t>(num_cells);
    const size_t internal_count = std::min(
        face_count, static_cast<size_t>(neighbours.shape(0)));
    const Label* const owner_data = owners.data();
    const Label* const neighbour_data = neighbours.data();
    const double* const point_data = points.data();
    const size_t example_limit = max_examples > 0
        ? static_cast<size_t>(max_examples)
        : 0U;

    std::vector<size_t> cell_face_offsets(cell_count + 1U, 0U);
    // ±(face_index + 1): sign stores orientation without padding a struct.
    std::vector<Label> cell_face_refs;
    std::vector<StarExample> examples;
    Label invalid_cells = 0;
    Label invalid_subtets = 0;

    {
        py::gil_scoped_release release;

        for (size_t face_index = 0U; face_index < face_count; ++face_index) {
            const Label owner = owner_data[face_index];
            if (owner >= 0 && owner < num_cells) {
                ++cell_face_offsets[static_cast<size_t>(owner) + 1U];
            }
            if (face_index < internal_count) {
                const Label neighbour = neighbour_data[face_index];
                if (neighbour >= 0 && neighbour < num_cells) {
                    ++cell_face_offsets[static_cast<size_t>(neighbour) + 1U];
                }
            }
        }
        std::partial_sum(
            cell_face_offsets.begin(), cell_face_offsets.end(),
            cell_face_offsets.begin());
        cell_face_refs.resize(cell_face_offsets.back());
        std::vector<size_t> write_offsets = cell_face_offsets;
        for (size_t face_index = 0U; face_index < face_count; ++face_index) {
            const Label owner = owner_data[face_index];
            if (owner >= 0 && owner < num_cells) {
                cell_face_refs[write_offsets[static_cast<size_t>(owner)]++] =
                    static_cast<Label>(face_index) + 1;
            }
            if (face_index < internal_count) {
                const Label neighbour = neighbour_data[face_index];
                if (neighbour >= 0 && neighbour < num_cells) {
                    cell_face_refs[write_offsets[static_cast<size_t>(neighbour)]++] =
                        -(static_cast<Label>(face_index) + 1);
                }
            }
        }

        double minimum[3]{point_data[0], point_data[1], point_data[2]};
        double maximum[3]{point_data[0], point_data[1], point_data[2]};
        for (size_t point_index = 1U; point_index < point_count; ++point_index) {
            const double* const point = point_data + point_index * 3U;
            for (size_t axis = 0U; axis < 3U; ++axis) {
                minimum[axis] = std::min(minimum[axis], point[axis]);
                maximum[axis] = std::max(maximum[axis], point[axis]);
            }
        }
        const double dx = maximum[0] - minimum[0];
        const double dy = maximum[1] - minimum[1];
        const double dz = maximum[2] - minimum[2];
        const double extent = std::sqrt(dx * dx + dy * dy + dz * dz);
        const double scale = std::max(extent * extent * extent, 1e-30);

        examples.reserve(std::min(example_limit, cell_face_refs.size()));
        std::vector<Label> cell_vertices;
        for (size_t cell_index = 0U; cell_index < cell_count; ++cell_index) {
            cell_vertices.clear();
            for (size_t reference_index = cell_face_offsets[cell_index];
                 reference_index < cell_face_offsets[cell_index + 1U];
                 ++reference_index) {
                const Label encoded_reference = cell_face_refs[reference_index];
                const size_t face_index = static_cast<size_t>(
                    std::abs(encoded_reference) - 1);
                const auto face = ragged.face(face_index);
                cell_vertices.insert(
                    cell_vertices.end(), face.begin(), face.end());
            }
            std::sort(cell_vertices.begin(), cell_vertices.end());
            cell_vertices.erase(
                std::unique(cell_vertices.begin(), cell_vertices.end()),
                cell_vertices.end());
            if (cell_vertices.size() < 4U) {
                ++invalid_cells;
                ++invalid_subtets;
                if (examples.size() < example_limit) {
                    examples.push_back({
                        StarExampleKind::FewerThanFourVertices,
                        static_cast<Label>(cell_index)});
                }
                continue;
            }

            double region_center[3]{0.0, 0.0, 0.0};
            for (const Label vertex : cell_vertices) {
                const double* const point = point_data
                    + static_cast<size_t>(vertex) * 3U;
                region_center[0] += point[0];
                region_center[1] += point[1];
                region_center[2] += point[2];
            }
            const double inverse_cell_vertices =
                1.0 / static_cast<double>(cell_vertices.size());
            region_center[0] *= inverse_cell_vertices;
            region_center[1] *= inverse_cell_vertices;
            region_center[2] *= inverse_cell_vertices;

            const auto visit_subtets = [&](auto&& visitor) {
                for (size_t reference_index = cell_face_offsets[cell_index];
                     reference_index < cell_face_offsets[cell_index + 1U];
                     ++reference_index) {
                    const Label encoded_reference = cell_face_refs[reference_index];
                    const bool reversed = encoded_reference < 0;
                    const size_t face_index = static_cast<size_t>(
                        std::abs(encoded_reference) - 1);
                    const auto face = ragged.face(face_index);
                    if (face.empty()) {
                        continue;
                    }
                    double face_center[3]{0.0, 0.0, 0.0};
                    for (size_t local = 0U; local < face.size(); ++local) {
                        const size_t oriented_local = reversed
                            ? face.size() - 1U - local
                            : local;
                        const Label vertex = face[oriented_local];
                        const double* const point = point_data
                            + static_cast<size_t>(vertex) * 3U;
                        face_center[0] += point[0];
                        face_center[1] += point[1];
                        face_center[2] += point[2];
                    }
                    const double inverse_face_vertices =
                        1.0 / static_cast<double>(face.size());
                    face_center[0] *= inverse_face_vertices;
                    face_center[1] *= inverse_face_vertices;
                    face_center[2] *= inverse_face_vertices;

                    for (size_t edge_index = 0U; edge_index < face.size(); ++edge_index) {
                        const size_t oriented_index = reversed
                            ? face.size() - 1U - edge_index
                            : edge_index;
                        const size_t oriented_next = reversed
                            ? (oriented_index == 0U
                                  ? face.size() - 1U
                                  : oriented_index - 1U)
                            : (oriented_index + 1U) % face.size();
                        const Label a = face[oriented_index];
                        const Label b = face[oriented_next];
                        const double* const point_a = point_data
                            + static_cast<size_t>(a) * 3U;
                        const double* const point_b = point_data
                            + static_cast<size_t>(b) * 3U;
                        visitor(StarSubtetGeometry{
                            face_index,
                            edge_index,
                            a,
                            b,
                            point_a,
                            point_b[0] - point_a[0],
                            point_b[1] - point_a[1],
                            point_b[2] - point_a[2],
                            face_center[0] - point_a[0],
                            face_center[1] - point_a[1],
                            face_center[2] - point_a[2]});
                    }
                }
            };

            const auto signed_volume_at_center = [&](const StarSubtetGeometry& subtet) {
                const double region_x = region_center[0] - subtet.point_a[0];
                const double region_y = region_center[1] - subtet.point_a[1];
                const double region_z = region_center[2] - subtet.point_a[2];
                const double cross_x = subtet.face_y * region_z
                    - subtet.face_z * region_y;
                const double cross_y = subtet.face_z * region_x
                    - subtet.face_x * region_z;
                const double cross_z = subtet.face_x * region_y
                    - subtet.face_y * region_x;
                return subtet.edge_x * cross_x + subtet.edge_y * cross_y
                    + subtet.edge_z * cross_z;
            };

            size_t arithmetic_violations = 0U;
            visit_subtets([&](const StarSubtetGeometry& subtet) {
                const double signed_volume6 = signed_volume_at_center(subtet);
                if (-signed_volume6 / scale <= tolerance) {
                    ++arithmetic_violations;
                }
            });
            if (arithmetic_violations == 0U) {
                continue;
            }

            // The arithmetic mean is only a witness candidate.  Project it
            // into the oriented half-spaces, then certify with the unchanged
            // signed-subtet predicate below.  This center is never output.
            constexpr size_t max_projection_sweeps = 8U;
            const double tolerance_scaled = tolerance * scale;
            const double inward_guard = 64.0 * std::numeric_limits<double>::epsilon()
                * std::max({
                    scale,
                    std::abs(tolerance_scaled),
                    std::numeric_limits<double>::min()});
            bool projection_valid = std::isfinite(scale)
                && std::isfinite(tolerance_scaled)
                && std::isfinite(inward_guard)
                && std::isfinite(region_center[0])
                && std::isfinite(region_center[1])
                && std::isfinite(region_center[2]);
            for (size_t sweep = 0U;
                 projection_valid && sweep < max_projection_sweeps;
                 ++sweep) {
                visit_subtets([&](const StarSubtetGeometry& subtet) {
                    const double normal_x = subtet.edge_y * subtet.face_z
                        - subtet.edge_z * subtet.face_y;
                    const double normal_y = subtet.edge_z * subtet.face_x
                        - subtet.edge_x * subtet.face_z;
                    const double normal_z = subtet.edge_x * subtet.face_y
                        - subtet.edge_y * subtet.face_x;
                    const double region_x = region_center[0] - subtet.point_a[0];
                    const double region_y = region_center[1] - subtet.point_a[1];
                    const double region_z = region_center[2] - subtet.point_a[2];
                    const double signed_volume6 = normal_x * region_x
                        + normal_y * region_y + normal_z * region_z;
                    const double normal_squared = normal_x * normal_x
                        + normal_y * normal_y + normal_z * normal_z;
                    if (!std::isfinite(signed_volume6)
                        || !std::isfinite(normal_squared)
                        || normal_squared <= std::numeric_limits<double>::min()) {
                        projection_valid = false;
                        return;
                    }
                    if (signed_volume6 >= -tolerance_scaled) {
                        const double step =
                            (signed_volume6 + tolerance_scaled + inward_guard)
                            / normal_squared;
                        region_center[0] -= step * normal_x;
                        region_center[1] -= step * normal_y;
                        region_center[2] -= step * normal_z;
                    }
                });
                if (!projection_valid) {
                    break;
                }
                bool projected_bad = false;
                visit_subtets([&](const StarSubtetGeometry& subtet) {
                    const double signed_volume6 = signed_volume_at_center(subtet);
                    if (-signed_volume6 / scale <= tolerance) {
                        projected_bad = true;
                    }
                });
                if (!projected_bad) {
                    break;
                }
            }

            bool cell_bad = false;
            visit_subtets([&](const StarSubtetGeometry& subtet) {
                const double signed_volume6 = signed_volume_at_center(subtet);
                const double normalized = -signed_volume6 / scale;
                if (normalized <= tolerance) {
                    cell_bad = true;
                    ++invalid_subtets;
                    if (examples.size() < example_limit) {
                        examples.push_back({
                            StarExampleKind::NonPositiveSubtet,
                            static_cast<Label>(cell_index),
                            static_cast<Label>(subtet.face_index),
                            subtet.edge_a,
                            subtet.edge_b,
                            subtet.edge_index,
                            signed_volume6,
                            normalized});
                    }
                }
            });
            if (cell_bad) {
                ++invalid_cells;
            }
        }
    }

    py::tuple python_examples(examples.size());
    for (size_t index = 0U; index < examples.size(); ++index) {
        const StarExample& example = examples[index];
        py::dict item;
        item["cell"] = example.cell;
        if (example.kind == StarExampleKind::FewerThanFourVertices) {
            item["face"] = py::none();
            item["edge"] = py::none();
            item["normalized_signed_volume6"] = 0.0;
            item["reason"] = "fewer_than_four_dual_vertices";
        } else {
            item["face"] = example.face;
            item["edge"] = py::make_tuple(example.edge_a, example.edge_b);
            item["edge_index"] = example.edge_index;
            item["signed_volume6"] = example.signed_volume6;
            item["normalized_signed_volume6"] = example.normalized_signed_volume6;
        }
        python_examples[index] = std::move(item);
    }
    return py::make_tuple(invalid_cells, invalid_subtets, std::move(python_examples));
}

bool clean_face(
    const Face& face,
    const double* points,
    size_t num_points,
    double area_eps,
    Face& cleaned)
{
    cleaned.clear();
    cleaned.reserve(face.size());
    std::unordered_set<Label> seen;
    seen.reserve(face.size());
    for (const Label vertex : face) {
        if (!cleaned.empty() && cleaned.back() == vertex) {
            continue;
        }
        if (!seen.insert(vertex).second) {
            continue;
        }
        cleaned.push_back(vertex);
    }
    if (cleaned.size() >= 2U && cleaned.back() == cleaned.front()) {
        cleaned.pop_back();
    }
    if (cleaned.size() < 3U) {
        return false;
    }

    const size_t base_offset = point_offset(cleaned.front(), num_points);
    const double* base = points + base_offset;
    double area = 0.0;
    for (size_t i = 1; i + 1 < cleaned.size(); ++i) {
        const double* first = points + point_offset(cleaned[i], num_points);
        const double* second = points + point_offset(cleaned[i + 1], num_points);
        const double ax = first[0] - base[0];
        const double ay = first[1] - base[1];
        const double az = first[2] - base[2];
        const double bx = second[0] - base[0];
        const double by = second[1] - base[1];
        const double bz = second[2] - base[2];
        const double cx = ay * bz - az * by;
        const double cy = az * bx - ax * bz;
        const double cz = ax * by - ay * bx;
        area += 0.5 * std::sqrt(cx * cx + cy * cy + cz * cz);
    }
    return !(area <= area_eps);
}

TopologyResult build_topology_kernel(
    const double* points,
    size_t num_points,
    const Cells& cells,
    double area_eps)
{
    TopologyResult result;
    std::vector<FaceBucket> buckets;
    std::unordered_map<Face, size_t, FaceHash> bucket_indices;

    for (const Cell& cell : cells) {
        Cell cleaned_faces;
        cleaned_faces.reserve(cell.size());
        bool drop_cell = false;
        for (const Face& face : cell) {
            Face cleaned;
            if (!clean_face(face, points, num_points, area_eps, cleaned)) {
                drop_cell = true;
                ++result.num_faces_dropped;
                break;
            }
            cleaned_faces.push_back(std::move(cleaned));
        }
        if (drop_cell || cleaned_faces.size() < 4U) {
            ++result.num_cells_dropped;
            continue;
        }

        const Label cell_id = result.num_cells++;
        for (Face& vertices : cleaned_faces) {
            Face key = vertices;
            std::sort(key.begin(), key.end());
            const auto [it, inserted] = bucket_indices.emplace(key, buckets.size());
            if (inserted) {
                buckets.push_back(FaceBucket{std::move(key), {}});
            }
            buckets[it->second].refs.push_back(
                FaceRef{cell_id, std::move(vertices)});
        }
    }

    for (FaceBucket& bucket : buckets) {
        const size_t num_refs = bucket.refs.size();
        if (num_refs == 1U) {
            result.boundary_owner.push_back(bucket.refs[0].cell);
            result.boundary_faces.push_back(std::move(bucket.refs[0].vertices));
            continue;
        }
        if (num_refs > 2U) {
            result.non_manifold.emplace_back(
                static_cast<Label>(num_refs),
                static_cast<Label>(bucket.key.size()));
        }

        FaceRef& first = bucket.refs[0];
        FaceRef& second = bucket.refs[1];
        const Label owner = std::min(first.cell, second.cell);
        const Label neighbour = std::max(first.cell, second.cell);
        result.internal_owner.push_back(owner);
        result.internal_neighbour.push_back(neighbour);
        result.internal_faces.push_back(
            first.cell == owner ? std::move(first.vertices)
                                : std::move(second.vertices));
    }
    return result;
}

py::array_t<Label> copy_labels(const std::vector<Label>& values)
{
    py::array_t<Label> result(
        py::array::ShapeContainer{static_cast<py::ssize_t>(values.size())});
    auto output = result.mutable_unchecked<1>();
    for (size_t i = 0; i < values.size(); ++i) {
        output(static_cast<py::ssize_t>(i)) = values[i];
    }
    return result;
}

py::tuple build_topology(
    py::array_t<double, py::array::c_style | py::array::forcecast> vertices,
    const Cells& cell_faces,
    double area_eps)
{
    if (vertices.ndim() != 2 || vertices.shape(1) != 3) {
        throw std::invalid_argument("vertices must have shape (N, 3)");
    }
    if (area_eps < 0.0) {
        throw std::invalid_argument("area_eps must be non-negative");
    }

    TopologyResult result;
    {
        py::gil_scoped_release release;
        result = build_topology_kernel(
            vertices.data(),
            static_cast<size_t>(vertices.shape(0)),
            cell_faces,
            area_eps);
    }

    return py::make_tuple(
        std::move(result.internal_faces),
        copy_labels(result.internal_owner),
        copy_labels(result.internal_neighbour),
        std::move(result.boundary_faces),
        copy_labels(result.boundary_owner),
        result.num_cells,
        result.num_cells_dropped,
        result.num_faces_dropped,
        std::move(result.non_manifold));
}

py::tuple compute_tet_dual_points(
    const py::array_t<double, py::array::c_style>& points,
    const py::array_t<Label, py::array::c_style>& tets)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (tets.ndim() != 2 || tets.shape(1) != 4) {
        throw std::invalid_argument("tets must have shape (M, 4)");
    }

    const size_t point_count = static_cast<size_t>(points.shape(0));
    const size_t tet_count = static_cast<size_t>(tets.shape(0));
    constexpr size_t max_size = std::numeric_limits<size_t>::max();
    if (point_count > max_size / 3U || tet_count > max_size / 4U
        || tet_count > max_size / 3U
        || tet_count
            > static_cast<size_t>(std::numeric_limits<py::ssize_t>::max())
        || point_count > static_cast<size_t>(std::numeric_limits<Label>::max())) {
        throw std::length_error("tet dual-point array is too large");
    }
    py::array_t<double> dual_points({
        static_cast<py::ssize_t>(tet_count), static_cast<py::ssize_t>(3)});
    py::array_t<std::uint8_t> statuses(
        py::array::ShapeContainer{static_cast<py::ssize_t>(tet_count)});
    const double* const point_data = points.data();
    const Label* const tet_data = tets.data();
    double* const dual_data = dual_points.mutable_data();
    std::uint8_t* const status_data = statuses.mutable_data();

    {
        py::gil_scoped_release release;
        for (size_t index = 0U; index < point_count * 3U; ++index) {
            if (!std::isfinite(point_data[index])) {
                throw std::invalid_argument("points must contain only finite coordinates");
            }
        }

        for (size_t tet_index = 0U; tet_index < tet_count; ++tet_index) {
            std::array<Label, 4> vertices{};
            for (size_t local = 0U; local < 4U; ++local) {
                const Label vertex = tet_data[tet_index * 4U + local];
                if (vertex < 0 || static_cast<size_t>(vertex) >= point_count) {
                    throw std::invalid_argument("tet vertex index out of range");
                }
                for (size_t previous = 0U; previous < local; ++previous) {
                    if (vertices[previous] == vertex) {
                        throw std::invalid_argument("tet repeats a vertex index");
                    }
                }
                vertices[local] = vertex;
            }

            std::array<double, 12> local_points{};
            for (size_t local = 0U; local < 4U; ++local) {
                const double* const source = point_data
                    + static_cast<size_t>(vertices[local]) * 3U;
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    local_points[local * 3U + axis] = source[axis];
                }
            }

            std::array<double, 3> centroid{};
            for (size_t axis = 0U; axis < 3U; ++axis) {
                centroid[axis] = (
                    local_points[axis] + local_points[3U + axis]
                    + local_points[6U + axis] + local_points[9U + axis])
                    * 0.25;
            }
            if (!finite3(centroid)) {
                throw std::invalid_argument("tet centroid is non-finite");
            }

            const auto write_centroid = [&](const DualPointStatus status) {
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    dual_data[tet_index * 3U + axis] = centroid[axis];
                }
                status_data[tet_index] = static_cast<std::uint8_t>(status);
            };

            std::array<double, 9> circumcenter_matrix{};
            std::array<double, 3> circumcenter_rhs{};
            double p0_squared = 0.0;
            for (size_t axis = 0U; axis < 3U; ++axis) {
                p0_squared += local_points[axis] * local_points[axis];
            }
            for (size_t row = 0U; row < 3U; ++row) {
                double point_squared = 0.0;
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    const double coordinate = local_points[(row + 1U) * 3U + axis];
                    circumcenter_matrix[row * 3U + axis] = 2.0
                        * (coordinate - local_points[axis]);
                    point_squared += coordinate * coordinate;
                }
                circumcenter_rhs[row] = point_squared - p0_squared;
            }

            std::array<double, 3> circumcenter{};
            const Solve3Status circumcenter_status = solve_3x3(
                circumcenter_matrix, circumcenter_rhs, circumcenter);
            if (circumcenter_status != Solve3Status::Success) {
                write_centroid(
                    circumcenter_status == Solve3Status::Singular
                        ? DualPointStatus::SingularCentroid
                        : DualPointStatus::NonFiniteSolveCentroid);
                continue;
            }

            std::array<double, 9> barycentric_matrix{};
            std::array<double, 3> barycentric_rhs{};
            for (size_t axis = 0U; axis < 3U; ++axis) {
                barycentric_rhs[axis] = circumcenter[axis] - local_points[axis];
                for (size_t column = 0U; column < 3U; ++column) {
                    barycentric_matrix[axis * 3U + column] =
                        local_points[(column + 1U) * 3U + axis]
                        - local_points[axis];
                }
            }
            std::array<double, 3> barycentric_tail{};
            const Solve3Status barycentric_status = solve_3x3(
                barycentric_matrix, barycentric_rhs, barycentric_tail);
            if (barycentric_status != Solve3Status::Success) {
                write_centroid(
                    barycentric_status == Solve3Status::Singular
                        ? DualPointStatus::SingularCentroid
                        : DualPointStatus::NonFiniteSolveCentroid);
                continue;
            }

            std::array<double, 4> barycentric{
                1.0 - barycentric_tail[0] - barycentric_tail[1]
                    - barycentric_tail[2],
                barycentric_tail[0],
                barycentric_tail[1],
                barycentric_tail[2],
            };
            if (!finite3(circumcenter)
                || !std::all_of(
                    barycentric.begin(),
                    barycentric.end(),
                    [](const double value) { return std::isfinite(value); })) {
                write_centroid(DualPointStatus::NonFiniteSolveCentroid);
                continue;
            }

            double alpha = 1.0;
            for (const double coordinate : barycentric) {
                if (coordinate < 0.0) {
                    alpha = std::min(alpha, 0.25 / (0.25 - coordinate));
                }
            }
            const bool clipped = alpha < 1.0;
            if (clipped) {
                alpha = std::max(0.0, alpha * (1.0 - 1e-12));
            }
            std::array<double, 3> result{};
            for (size_t axis = 0U; axis < 3U; ++axis) {
                result[axis] = centroid[axis]
                    + alpha * (circumcenter[axis] - centroid[axis]);
            }
            if (!finite3(result)) {
                write_centroid(DualPointStatus::NonFiniteSolveCentroid);
                continue;
            }
            for (size_t axis = 0U; axis < 3U; ++axis) {
                dual_data[tet_index * 3U + axis] = result[axis];
            }
            status_data[tet_index] = static_cast<std::uint8_t>(
                clipped ? DualPointStatus::Clipped : DualPointStatus::Circumcenter);
        }
    }
    return py::make_tuple(std::move(dual_points), std::move(statuses));
}

py::tuple audit_tet_primal_conformity(
    const py::array_t<double, py::array::c_style>& points,
    const py::array_t<Label, py::array::c_style>& tets)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (tets.ndim() != 2 || tets.shape(1) != 4) {
        throw std::invalid_argument("tets must have shape (M, 4)");
    }

    const size_t point_count = static_cast<size_t>(points.shape(0));
    const size_t tet_count = static_cast<size_t>(tets.shape(0));
    constexpr size_t max_size = std::numeric_limits<size_t>::max();
    if (point_count > max_size / 3U || tet_count > max_size / 4U
        || tet_count > static_cast<size_t>(std::numeric_limits<Label>::max())
        || point_count > static_cast<size_t>(std::numeric_limits<Label>::max())) {
        throw std::length_error("tet primal-conformity array is too large");
    }

    using TetRecord = CanonicalSimplexRecord<4>;
    using FaceRecord = CanonicalSimplexRecord<3>;
    std::vector<TetRecord> canonical_tets;
    canonical_tets.reserve(tet_count);
    std::vector<FaceRecord> canonical_faces;
    canonical_faces.reserve(tet_count * 4U);
    std::vector<Label> negative_orientation_rows;
    negative_orientation_rows.reserve(tet_count / 8U);
    std::vector<unsigned char> incident_vertices(point_count, 0U);

    constexpr std::array<std::array<size_t, 3>, 4> local_faces{{
        {{1, 2, 3}}, {{0, 3, 2}}, {{0, 1, 3}}, {{0, 2, 1}},
    }};
    const double* const point_data = points.data();
    const Label* const tet_data = tets.data();

    {
        py::gil_scoped_release release;
        for (size_t point_index = 0U; point_index < point_count * 3U; ++point_index) {
            if (!std::isfinite(point_data[point_index])) {
                throw std::invalid_argument("points must contain only finite coordinates");
            }
        }

        for (size_t tet_index = 0U; tet_index < tet_count; ++tet_index) {
            std::array<Label, 4> tet{};
            for (size_t local = 0U; local < 4U; ++local) {
                const Label vertex = tet_data[tet_index * 4U + local];
                if (vertex < 0 || static_cast<size_t>(vertex) >= point_count) {
                    throw std::invalid_argument("tet vertex index out of range");
                }
                for (size_t previous = 0U; previous < local; ++previous) {
                    if (tet[previous] == vertex) {
                        throw std::invalid_argument("tet repeats a vertex index");
                    }
                }
                tet[local] = vertex;
                incident_vertices[static_cast<size_t>(vertex)] = 1U;
            }

            std::array<Label, 4> canonical_tet = tet;
            std::sort(canonical_tet.begin(), canonical_tet.end());
            canonical_tets.push_back(
                {canonical_tet, static_cast<Label>(tet_index)});
            for (const auto& local_face : local_faces) {
                std::array<Label, 3> face{
                    tet[local_face[0]], tet[local_face[1]], tet[local_face[2]]};
                std::sort(face.begin(), face.end());
                canonical_faces.push_back({face, static_cast<Label>(tet_index)});
            }

            const double* const p0 = point_data + static_cast<size_t>(tet[0]) * 3U;
            const double* const p1 = point_data + static_cast<size_t>(tet[1]) * 3U;
            const double* const p2 = point_data + static_cast<size_t>(tet[2]) * 3U;
            const double* const p3 = point_data + static_cast<size_t>(tet[3]) * 3U;
            const double ax = p1[0] - p0[0];
            const double ay = p1[1] - p0[1];
            const double az = p1[2] - p0[2];
            const double bx = p2[0] - p0[0];
            const double by = p2[1] - p0[1];
            const double bz = p2[2] - p0[2];
            const double cx = p3[0] - p0[0];
            const double cy = p3[1] - p0[1];
            const double cz = p3[2] - p0[2];
            const double signed_volume6 = ax * (by * cz - bz * cy)
                - ay * (bx * cz - bz * cx)
                + az * (bx * cy - by * cx);
            if (!std::isfinite(signed_volume6)) {
                throw std::invalid_argument("tet signed volume is non-finite");
            }
            if (signed_volume6 == 0.0) {
                throw std::invalid_argument("tet signed volume is zero");
            }
            if (signed_volume6 < 0.0) {
                negative_orientation_rows.push_back(static_cast<Label>(tet_index));
            }
        }

        const auto record_less = [](const auto& first, const auto& second) {
            return first.key < second.key
                || (first.key == second.key && first.owner < second.owner);
        };
        std::sort(canonical_tets.begin(), canonical_tets.end(), record_less);
        std::sort(canonical_faces.begin(), canonical_faces.end(), record_less);
    }

    std::vector<std::pair<std::array<Label, 4>, std::vector<Label>>> duplicate_groups;
    for (size_t begin = 0U; begin < canonical_tets.size();) {
        size_t end = begin + 1U;
        while (end < canonical_tets.size()
               && canonical_tets[end].key == canonical_tets[begin].key) {
            ++end;
        }
        if (end - begin > 1U) {
            std::vector<Label> owners;
            owners.reserve(end - begin);
            for (size_t index = begin; index < end; ++index) {
                owners.push_back(canonical_tets[index].owner);
            }
            duplicate_groups.emplace_back(canonical_tets[begin].key, std::move(owners));
        }
        begin = end;
    }

    std::vector<std::pair<std::array<Label, 3>, std::vector<Label>>> nonmanifold_groups;
    for (size_t begin = 0U; begin < canonical_faces.size();) {
        size_t end = begin + 1U;
        while (end < canonical_faces.size()
               && canonical_faces[end].key == canonical_faces[begin].key) {
            ++end;
        }
        if (end - begin > 2U) {
            std::vector<Label> owners;
            owners.reserve(end - begin);
            for (size_t index = begin; index < end; ++index) {
                owners.push_back(canonical_faces[index].owner);
            }
            nonmanifold_groups.emplace_back(
                canonical_faces[begin].key, std::move(owners));
        }
        begin = end;
    }

    std::vector<Label> orphan_vertex_rows;
    orphan_vertex_rows.reserve(point_count);
    for (size_t point_index = 0U; point_index < point_count; ++point_index) {
        if (incident_vertices[point_index] == 0U) {
            orphan_vertex_rows.push_back(static_cast<Label>(point_index));
        }
    }

    py::tuple python_duplicates(duplicate_groups.size());
    for (size_t index = 0U; index < duplicate_groups.size(); ++index) {
        const auto& [key, owners] = duplicate_groups[index];
        python_duplicates[index] = py::make_tuple(
            py::make_tuple(key[0], key[1], key[2], key[3]),
            py::cast(owners));
    }
    py::tuple python_nonmanifold(nonmanifold_groups.size());
    for (size_t index = 0U; index < nonmanifold_groups.size(); ++index) {
        const auto& [key, owners] = nonmanifold_groups[index];
        python_nonmanifold[index] = py::make_tuple(
            py::make_tuple(key[0], key[1], key[2]),
            py::cast(owners));
    }
    py::array_t<Label> python_orphans(
        py::array::ShapeContainer{
            static_cast<py::ssize_t>(orphan_vertex_rows.size())});
    auto orphan_output = python_orphans.mutable_unchecked<1>();
    for (size_t index = 0U; index < orphan_vertex_rows.size(); ++index) {
        orphan_output(static_cast<py::ssize_t>(index)) = orphan_vertex_rows[index];
    }
    return py::make_tuple(
        std::move(python_duplicates),
        std::move(python_nonmanifold),
        py::cast(negative_orientation_rows),
        std::move(python_orphans));
}

py::tuple build_tet_incidence_maps(
    const py::array_t<Label, py::array::c_style | py::array::forcecast>& tets_array,
    const Label num_vertices)
{
    if (tets_array.ndim() != 2 || tets_array.shape(1) != 4) {
        throw std::invalid_argument("tets must have shape (N, 4)");
    }
    if (num_vertices < 0) {
        throw std::invalid_argument("num_vertices must be non-negative");
    }

    const auto tets = tets_array.unchecked<2>();
    const size_t tet_count = static_cast<size_t>(tets.shape(0));
    const size_t vertex_count = static_cast<size_t>(num_vertices);
    std::vector<std::vector<Label>> vertex_owners(vertex_count);
    std::vector<unsigned char> vertex_seen(vertex_count, 0);
    std::vector<Label> vertex_order;
    vertex_order.reserve(std::min(vertex_count, tet_count * 4U));
    std::vector<IncidenceBucket<2>> edge_buckets;
    edge_buckets.reserve(tet_count * 3U);
    std::unordered_map<std::array<Label, 2>, size_t, ArrayHash<2>> edge_indices;
    edge_indices.reserve(tet_count * 3U);
    std::vector<IncidenceBucket<3>> face_buckets;
    face_buckets.reserve(tet_count * 2U);
    std::unordered_map<std::array<Label, 3>, size_t, ArrayHash<3>> face_indices;
    face_indices.reserve(tet_count * 2U);

    constexpr std::array<std::array<size_t, 2>, 6> local_edges{{
        {{0, 1}}, {{0, 2}}, {{0, 3}}, {{1, 2}}, {{1, 3}}, {{2, 3}},
    }};
    constexpr std::array<std::array<size_t, 3>, 4> local_faces{{
        {{1, 2, 3}}, {{0, 3, 2}}, {{0, 1, 3}}, {{0, 2, 1}},
    }};

    {
        py::gil_scoped_release release;
        for (size_t tet_index = 0; tet_index < tet_count; ++tet_index) {
            std::array<Label, 4> tet{};
            for (size_t local = 0; local < 4; ++local) {
                const Label vertex = tets(
                    static_cast<py::ssize_t>(tet_index),
                    static_cast<py::ssize_t>(local));
                if (vertex < 0 || vertex >= num_vertices) {
                    throw std::invalid_argument("tet vertex index out of range");
                }
                tet[local] = vertex;
                const size_t vertex_index = static_cast<size_t>(vertex);
                if (vertex_seen[vertex_index] == 0) {
                    vertex_seen[vertex_index] = 1;
                    vertex_order.push_back(vertex);
                }
                vertex_owners[vertex_index].push_back(
                    static_cast<Label>(tet_index));
            }

            for (const auto& local_edge : local_edges) {
                std::array<Label, 2> key{
                    tet[local_edge[0]], tet[local_edge[1]]};
                if (key[1] < key[0]) {
                    std::swap(key[0], key[1]);
                }
                const auto [position, inserted] = edge_indices.emplace(
                    key, edge_buckets.size());
                if (inserted) {
                    edge_buckets.push_back(IncidenceBucket<2>{key, {}});
                }
                edge_buckets[position->second].owners.push_back(
                    static_cast<Label>(tet_index));
            }

            for (const auto& local_face : local_faces) {
                std::array<Label, 3> key{
                    tet[local_face[0]], tet[local_face[1]], tet[local_face[2]]};
                std::sort(key.begin(), key.end());
                const auto [position, inserted] = face_indices.emplace(
                    key, face_buckets.size());
                if (inserted) {
                    face_buckets.push_back(IncidenceBucket<3>{key, {}});
                }
                face_buckets[position->second].owners.push_back(
                    static_cast<Label>(tet_index));
            }
        }
    }

    py::dict vertex_map;
    for (const Label vertex : vertex_order) {
        vertex_map[py::int_(vertex)] = py::cast(
            std::move(vertex_owners[static_cast<size_t>(vertex)]));
    }
    py::dict edge_map;
    for (auto& bucket : edge_buckets) {
        edge_map[py::make_tuple(bucket.key[0], bucket.key[1])] =
            py::cast(std::move(bucket.owners));
    }
    py::dict face_map;
    for (auto& bucket : face_buckets) {
        face_map[py::make_tuple(bucket.key[0], bucket.key[1], bucket.key[2])] =
            py::cast(std::move(bucket.owners));
    }
    return py::make_tuple(
        std::move(vertex_map), std::move(edge_map), std::move(face_map));
}

[[nodiscard]] size_t checked_array_dimension(
    const py::ssize_t value,
    const char* const name)
{
    if (value < 0) {
        throw std::invalid_argument(std::string(name) + " has a negative dimension");
    }
    using UnsignedPySize = std::make_unsigned_t<py::ssize_t>;
    const auto unsigned_value = static_cast<UnsignedPySize>(value);
    if (unsigned_value > std::numeric_limits<size_t>::max()) {
        throw std::overflow_error(std::string(name) + " dimension exceeds size_t");
    }
    return static_cast<size_t>(unsigned_value);
}

[[nodiscard]] py::ssize_t checked_py_size(const size_t value, const char* const name)
{
    constexpr auto py_max = static_cast<size_t>(std::numeric_limits<py::ssize_t>::max());
    if (value > py_max) {
        throw std::overflow_error(std::string(name) + " exceeds Python ssize_t range");
    }
    return static_cast<py::ssize_t>(value);
}

template <typename Value>
[[nodiscard]] py::array_t<Value> owned_contiguous_array(
    std::vector<Value>&& values,
    std::vector<py::ssize_t> shape)
{
    size_t expected = 1U;
    for (const py::ssize_t dimension : shape) {
        expected = checked_size_product(
            expected,
            checked_array_dimension(dimension, "output"),
            "output");
    }
    if (expected != values.size()) {
        throw std::logic_error("owned array shape does not match storage size");
    }
    auto* storage = new std::vector<Value>(std::move(values));
    py::capsule owner(storage, [](void* pointer) {
        delete static_cast<std::vector<Value>*>(pointer);
    });
    return py::array_t<Value>(std::move(shape), storage->data(), std::move(owner));
}

py::tuple assemble_dual_hull_faces(
    const py::array_t<double, py::array::c_style>& seed_points,
    const py::array_t<double, py::array::c_style>& cell_points,
    const py::array_t<Label, py::array::c_style>& cell_point_offsets,
    const py::array_t<Label, py::array::c_style>& hull_simplices,
    const py::array_t<Label, py::array::c_style>& cell_hull_offsets,
    const py::array_t<double, py::array::c_style>& hull_equations,
    const py::array_t<Label, py::array::c_style>& n_tet_points,
    const py::array_t<Label, py::array::c_style>& local_source_label_ids)
{
    if (seed_points.ndim() != 2 || seed_points.shape(1) != 3) {
        throw std::invalid_argument("seed_points must have shape (N, 3)");
    }
    if (cell_points.ndim() != 2 || cell_points.shape(1) != 3) {
        throw std::invalid_argument("cell_points must have shape (N, 3)");
    }
    if (hull_simplices.ndim() != 2 || hull_simplices.shape(1) != 3) {
        throw std::invalid_argument("hull_simplices must have shape (N, 3)");
    }
    if (hull_equations.ndim() != 2 || hull_equations.shape(1) != 4) {
        throw std::invalid_argument("hull_equations must have shape (N, 4)");
    }
    if (cell_point_offsets.ndim() != 1 || cell_hull_offsets.ndim() != 1
        || n_tet_points.ndim() != 1 || local_source_label_ids.ndim() != 1) {
        throw std::invalid_argument("dual hull metadata arrays must be one-dimensional");
    }

    const size_t seed_rows = checked_array_dimension(seed_points.shape(0), "seed_points");
    const size_t point_rows = checked_array_dimension(cell_points.shape(0), "cell_points");
    const size_t point_offset_count = checked_array_dimension(
        cell_point_offsets.shape(0), "cell_point_offsets");
    const size_t hull_rows = checked_array_dimension(
        hull_simplices.shape(0), "hull_simplices");
    const size_t hull_offset_count = checked_array_dimension(
        cell_hull_offsets.shape(0), "cell_hull_offsets");
    const size_t equation_rows = checked_array_dimension(
        hull_equations.shape(0), "hull_equations");
    const size_t tet_count = checked_array_dimension(n_tet_points.shape(0), "n_tet_points");
    const size_t label_count = checked_array_dimension(
        local_source_label_ids.shape(0), "local_source_label_ids");

    const size_t seed_values = checked_size_product(seed_rows, 3U, "seed_points");
    const size_t point_values = checked_size_product(point_rows, 3U, "cell_points");
    const size_t simplex_values = checked_size_product(hull_rows, 3U, "hull_simplices");
    const size_t equation_values = checked_size_product(hull_rows, 4U, "hull_equations");
    if (equation_rows != hull_rows) {
        throw std::invalid_argument("hull_simplices and hull_equations row counts disagree");
    }
    if (point_offset_count == 0U || hull_offset_count == 0U) {
        throw std::invalid_argument("cell offsets must contain the zero sentinel");
    }
    const size_t num_cells = point_offset_count - 1U;
    if (hull_offset_count != point_offset_count || tet_count != num_cells
        || label_count != point_rows) {
        throw std::invalid_argument("dual hull metadata row counts disagree");
    }

    const DualHullAssemblyInput input {
        {seed_points.data(), seed_values},
        {cell_points.data(), point_values},
        {cell_point_offsets.data(), point_offset_count},
        {hull_simplices.data(), simplex_values},
        {cell_hull_offsets.data(), hull_offset_count},
        {hull_equations.data(), equation_values},
        {n_tet_points.data(), tet_count},
        {local_source_label_ids.data(), label_count},
    };

    DualHullAssemblyResult result;
    {
        py::gil_scoped_release release;
        result = assemble_dual_hull_faces_core(input);
    }
    const size_t output_point_rows = result.points.size() / 3U;
    const py::ssize_t output_point_count = checked_py_size(output_point_rows, "dual points");
    const py::ssize_t face_offset_count = checked_py_size(
        result.face_offsets.size(), "face offsets");
    const py::ssize_t face_index_count = checked_py_size(
        result.face_indices.size(), "face indices");
    const py::ssize_t cell_face_offset_count = checked_py_size(
        result.cell_face_offsets.size(), "cell face offsets");
    const py::ssize_t cap_count = checked_py_size(result.face_is_cap.size(), "cap flags");
    const py::ssize_t label_output_count = checked_py_size(
        result.face_label_ids.size(), "face label ids");
    const py::ssize_t ambiguous_count = checked_py_size(
        result.face_order_ambiguous.size(), "face ambiguity flags");
    return py::make_tuple(
        result.accepted,
        std::move(result.reason),
        owned_contiguous_array(
            std::move(result.points),
            {output_point_count, 3}),
        owned_contiguous_array(std::move(result.face_offsets), {face_offset_count}),
        owned_contiguous_array(std::move(result.face_indices), {face_index_count}),
        owned_contiguous_array(
            std::move(result.cell_face_offsets), {cell_face_offset_count}),
        owned_contiguous_array(std::move(result.face_is_cap), {cap_count}),
        owned_contiguous_array(std::move(result.face_label_ids), {label_output_count}),
        owned_contiguous_array(
            std::move(result.face_order_ambiguous), {ambiguous_count}));
}

}  // namespace

PYBIND11_MODULE(native_polymesh, module)
{
    module.doc() =
        "C++ face geometry, topology, and validity kernels for AutoTessell polyMesh";
    module.def(
        "build_topology",
        &build_topology,
        py::arg("vertices"),
        py::arg("cell_faces"),
        py::arg("area_eps"));
    module.def(
        "compute_tet_dual_points",
        &compute_tet_dual_points,
        py::arg("points").noconvert(),
        py::arg("tets").noconvert());
    module.def(
        "audit_tet_primal_conformity",
        &audit_tet_primal_conformity,
        py::arg("points").noconvert(),
        py::arg("tets").noconvert());
    module.def(
        "build_tet_incidence_maps",
        &build_tet_incidence_maps,
        py::arg("tets"),
        py::arg("num_vertices"));
    module.def(
        "assemble_dual_hull_faces",
        &assemble_dual_hull_faces,
        py::arg("seed_points").noconvert(),
        py::arg("cell_points").noconvert(),
        py::arg("cell_point_offsets").noconvert(),
        py::arg("hull_simplices").noconvert(),
        py::arg("cell_hull_offsets").noconvert(),
        py::arg("hull_equations").noconvert(),
        py::arg("n_tet_points").noconvert(),
        py::arg("local_source_label_ids").noconvert());
    module.def(
        "face_flip_mask",
        &face_flip_mask,
        py::arg("points"),
        py::arg("faces"),
        py::arg("owners"),
        py::arg("cell_centroids"));
    module.def(
        "face_plane_geometry",
        &face_plane_geometry,
        py::arg("points"),
        py::arg("faces"),
        py::arg("plane_normals"),
        py::arg("plane_offsets"),
        py::arg("tolerance") = 1e-6);
    module.def(
        "star_validity",
        &star_validity,
        py::arg("points"),
        py::arg("faces"),
        py::arg("owners"),
        py::arg("neighbours"),
        py::arg("num_cells"),
        py::arg("tolerance") = 1e-12,
        py::arg("max_examples") = 8);
}
