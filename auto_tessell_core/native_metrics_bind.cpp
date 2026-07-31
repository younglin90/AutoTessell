// Fast geometry kernels for AutoTessell's NativeMeshChecker.
//
// These bindings intentionally cover small, stable data-parallel kernels first:
// face centres/normals/areas and cell centres from unique vertices.  The Python
// checker keeps orchestration and fallback behaviour; this module removes the
// hottest Python list/set loops when the extension is available.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "native_weighted_matching.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <limits>
#include <numeric>
#include <optional>
#include <numbers>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace py = pybind11;

namespace {

using Point3 = std::array<double, 3>;
constexpr std::size_t kMaximumPairingFaceCount = 256;

py::array_t<long long> copy_index_vector(const std::vector<long long>& values);

void skip_foam_trivia(std::string_view text, size_t& pos)
{
    while (pos < text.size()) {
        const char ch = text[pos];
        if (std::isspace(static_cast<unsigned char>(ch))) {
            ++pos;
            continue;
        }
        if (ch == '/' && pos + 1 < text.size()) {
            const char next = text[pos + 1];
            if (next == '/') {
                pos += 2;
                while (pos < text.size() && text[pos] != '\n') {
                    ++pos;
                }
                continue;
            }
            if (next == '*') {
                const size_t end = text.find("*/", pos + 2);
                if (end == std::string_view::npos) {
                    throw std::invalid_argument(
                        "unterminated block comment in OpenFOAM file");
                }
                pos = end + 2;
                continue;
            }
        }
        if (ch == '\'' || ch == '"') {
            const char quote = ch;
            ++pos;
            bool closed = false;
            while (pos < text.size()) {
                const char quoted_ch = text[pos++];
                if (quoted_ch == '\\' && pos < text.size()) {
                    ++pos;
                } else if (quoted_ch == quote) {
                    closed = true;
                    break;
                }
            }
            if (!closed) {
                throw std::invalid_argument(
                    "unterminated quoted string in OpenFOAM file");
            }
            continue;
        }
        return;
    }
}

bool is_integer_boundary(char ch)
{
    const auto uch = static_cast<unsigned char>(ch);
    return !std::isalnum(uch) && ch != '_' && ch != '.';
}

long long parse_signed_integer(std::string_view text, size_t& pos)
{
    const size_t start = pos;
    bool negative = false;
    if (pos < text.size() && (text[pos] == '+' || text[pos] == '-')) {
        negative = text[pos] == '-';
        ++pos;
    }
    if (pos >= text.size()
        || !std::isdigit(static_cast<unsigned char>(text[pos]))) {
        pos = start;
        throw std::invalid_argument("expected signed integer in OpenFOAM file");
    }

    constexpr unsigned long long positive_limit =
        static_cast<unsigned long long>(std::numeric_limits<long long>::max());
    constexpr unsigned long long negative_limit = positive_limit + 1ULL;
    const unsigned long long limit = negative ? negative_limit : positive_limit;
    unsigned long long value = 0;
    while (pos < text.size()
           && std::isdigit(static_cast<unsigned char>(text[pos]))) {
        const auto digit = static_cast<unsigned long long>(text[pos] - '0');
        if (value > (limit - digit) / 10ULL) {
            throw std::invalid_argument("integer out of range in OpenFOAM file");
        }
        value = value * 10ULL + digit;
        ++pos;
    }

    if (negative) {
        if (value == negative_limit) {
            return std::numeric_limits<long long>::min();
        }
        return -static_cast<long long>(value);
    }
    return static_cast<long long>(value);
}

std::pair<long long, size_t> find_foam_list(
    std::string_view text,
    std::string_view list_name)
{
    for (size_t pos = 0; pos < text.size();) {
        skip_foam_trivia(text, pos);
        if (pos >= text.size()) {
            break;
        }
        const char ch = text[pos];
        const bool has_sign = ch == '+' || ch == '-';
        if (!std::isdigit(static_cast<unsigned char>(ch))
            && !(has_sign && pos + 1 < text.size()
                 && std::isdigit(static_cast<unsigned char>(text[pos + 1])))) {
            ++pos;
            continue;
        }
        if (pos > 0 && !is_integer_boundary(text[pos - 1])) {
            ++pos;
            continue;
        }

        size_t end = pos + (has_sign ? 1U : 0U);
        while (end < text.size()
               && std::isdigit(static_cast<unsigned char>(text[end]))) {
            ++end;
        }
        if (end < text.size() && !is_integer_boundary(text[end])) {
            pos = end;
            continue;
        }
        size_t opening = end;
        skip_foam_trivia(text, opening);
        if (opening >= text.size() || text[opening] != '(') {
            pos = opening;
            continue;
        }

        size_t parse_pos = pos;
        const long long count = parse_signed_integer(text, parse_pos);
        if (count < 0) {
            throw std::invalid_argument(
                std::string(list_name) + " count must be non-negative");
        }
        return {count, opening + 1};
    }
    throw std::invalid_argument(
        "missing " + std::string(list_name) + " in OpenFOAM file");
}

void finish_foam_list(
    std::string_view text,
    size_t& pos,
    std::string_view list_name)
{
    skip_foam_trivia(text, pos);
    if (pos >= text.size() || text[pos] != ')') {
        throw std::invalid_argument(
            std::string(list_name) + " count does not match list");
    }
    ++pos;
    skip_foam_trivia(text, pos);
    if (pos < text.size() && text[pos] == ';') {
        ++pos;
        skip_foam_trivia(text, pos);
    }
    if (pos != text.size()) {
        throw std::invalid_argument(
            "unexpected trailing data after " + std::string(list_name));
    }
}

std::string read_foam_file(
    const std::string& filename,
    std::string_view file_kind)
{
    std::ifstream input(filename, std::ios::binary);
    if (!input) {
        throw std::runtime_error(
            "unable to open " + std::string(file_kind) + " file: " + filename);
    }
    input.seekg(0, std::ios::end);
    const std::streampos end = input.tellg();
    if (end < 0
        || static_cast<unsigned long long>(end)
               > static_cast<unsigned long long>(
                   std::numeric_limits<std::streamsize>::max())) {
        throw std::runtime_error(
            "unable to read " + std::string(file_kind) + " file: " + filename);
    }
    std::string text(static_cast<size_t>(end), '\0');
    input.seekg(0, std::ios::beg);
    if (!text.empty()) {
        input.read(text.data(), static_cast<std::streamsize>(text.size()));
    }
    if (!input) {
        throw std::runtime_error(
            "unable to read " + std::string(file_kind) + " file: " + filename);
    }
    return text;
}

struct NativeFaceTopology {
    std::vector<long long> indices;
    std::vector<long long> offsets{0};
    bool all_triangles = true;

    [[nodiscard]] py::ssize_t face_count() const
    {
        return static_cast<py::ssize_t>(offsets.size() - 1);
    }

    [[nodiscard]] py::list to_lists() const
    {
        py::list faces;
        for (size_t face_i = 0; face_i + 1 < offsets.size(); ++face_i) {
            py::list face;
            const auto begin = static_cast<size_t>(offsets[face_i]);
            const auto end = static_cast<size_t>(offsets[face_i + 1]);
            for (size_t i = begin; i < end; ++i) {
                face.append(indices[i]);
            }
            faces.append(std::move(face));
        }
        return faces;
    }
};

NativeFaceTopology parse_foam_face_topology_text(std::string_view text)
{
    const auto [face_count, list_start] = find_foam_list(text, "face-list");
    if (static_cast<unsigned long long>(face_count) > text.size()) {
        throw std::invalid_argument("face-list count exceeds file size");
    }

    NativeFaceTopology topology;
    topology.offsets.reserve(static_cast<size_t>(face_count) + 1);
    const auto face_count_size = static_cast<size_t>(face_count);
    if (face_count_size <= std::numeric_limits<size_t>::max() / 4) {
        topology.indices.reserve(face_count_size * 4);
    }
    size_t pos = list_start;
    for (long long face_i = 0; face_i < face_count; ++face_i) {
        skip_foam_trivia(text, pos);
        const long long vertex_count = parse_signed_integer(text, pos);
        if (vertex_count < 0) {
            throw std::invalid_argument("face vertex count must be non-negative");
        }
        if (static_cast<unsigned long long>(vertex_count) > text.size()) {
            throw std::invalid_argument("face vertex count exceeds file size");
        }
        skip_foam_trivia(text, pos);
        if (pos >= text.size() || text[pos] != '(') {
            throw std::invalid_argument("expected '(' after face vertex count");
        }
        ++pos;

        topology.all_triangles = topology.all_triangles && vertex_count == 3;
        for (long long vertex_i = 0; vertex_i < vertex_count; ++vertex_i) {
            skip_foam_trivia(text, pos);
            topology.indices.push_back(parse_signed_integer(text, pos));
        }
        skip_foam_trivia(text, pos);
        if (pos >= text.size() || text[pos] != ')') {
            throw std::invalid_argument("face vertex count does not match list");
        }
        ++pos;
        topology.offsets.push_back(
            static_cast<long long>(topology.indices.size()));
    }

    finish_foam_list(text, pos, "face-list");
    return topology;
}

std::vector<long long> parse_foam_labels_text(std::string_view text)
{
    const auto [label_count, list_start] = find_foam_list(text, "label-list");
    if (static_cast<unsigned long long>(label_count) > text.size()) {
        throw std::invalid_argument("label-list count exceeds file size");
    }

    std::vector<long long> labels;
    labels.reserve(static_cast<size_t>(label_count));
    size_t pos = list_start;
    for (long long label_i = 0; label_i < label_count; ++label_i) {
        skip_foam_trivia(text, pos);
        if (pos >= text.size() || text[pos] == ')') {
            throw std::invalid_argument(
                "label-list count does not match list");
        }
        labels.push_back(parse_signed_integer(text, pos));
    }
    finish_foam_list(text, pos, "label-list");
    return labels;
}

NativeFaceTopology parse_foam_faces_topology_file(const py::object& path)
{
    const std::string filename =
        py::module_::import("os").attr("fspath")(path).cast<std::string>();
    NativeFaceTopology topology;
    {
        py::gil_scoped_release release;
        const std::string text = read_foam_file(filename, "faces");
        topology = parse_foam_face_topology_text(text);
    }
    return topology;
}

py::list parse_foam_faces_file(const py::object& path)
{
    return parse_foam_faces_topology_file(path).to_lists();
}

py::array_t<long long> parse_foam_labels_file(const py::object& path)
{
    const std::string filename =
        py::module_::import("os").attr("fspath")(path).cast<std::string>();
    std::vector<long long> labels;
    {
        py::gil_scoped_release release;
        const std::string text = read_foam_file(filename, "labels");
        labels = parse_foam_labels_text(text);
    }
    return copy_index_vector(labels);
}

long long as_vertex_index(const py::handle& value, long long n_points)
{
    const auto idx = value.cast<long long>();
    if (idx < 0 || idx >= n_points) {
        throw py::index_error("face vertex index out of bounds");
    }
    return idx;
}

Point3 point_at(
    const py::detail::unchecked_reference<double, 2>& pts,
    long long idx)
{
    return {pts(idx, 0), pts(idx, 1), pts(idx, 2)};
}

Point3 sub(const Point3& a, const Point3& b)
{
    return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}

Point3 cross(const Point3& a, const Point3& b)
{
    return {
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    };
}

double norm3(double x, double y, double z)
{
    return std::sqrt(x * x + y * y + z * z);
}

NativeFaceTopology topology_from_python_faces(
    py::sequence faces,
    long long n_points)
{
    NativeFaceTopology topology;
    const auto n_faces = static_cast<py::ssize_t>(faces.size());
    topology.offsets.reserve(static_cast<size_t>(n_faces) + 1);
    const auto n_faces_size = static_cast<size_t>(n_faces);
    if (n_faces_size <= std::numeric_limits<size_t>::max() / 4) {
        topology.indices.reserve(n_faces_size * 4);
    }
    for (py::ssize_t face_i = 0; face_i < n_faces; ++face_i) {
        py::sequence face = faces[face_i].cast<py::sequence>();
        const auto n_vertices = static_cast<py::ssize_t>(face.size());
        topology.all_triangles = topology.all_triangles && n_vertices == 3;
        for (py::ssize_t vertex_i = 0; vertex_i < n_vertices; ++vertex_i) {
            topology.indices.push_back(as_vertex_index(face[vertex_i], n_points));
        }
        topology.offsets.push_back(
            static_cast<long long>(topology.indices.size()));
    }
    return topology;
}

void validate_topology(const NativeFaceTopology& topology, long long n_points)
{
    if (topology.offsets.empty() || topology.offsets.front() != 0
        || topology.offsets.back()
            != static_cast<long long>(topology.indices.size())) {
        throw std::invalid_argument("invalid face topology offsets");
    }
    for (size_t i = 1; i < topology.offsets.size(); ++i) {
        if (topology.offsets[i] < topology.offsets[i - 1]) {
            throw std::invalid_argument("face topology offsets must be monotonic");
        }
    }
    for (const auto idx : topology.indices) {
        if (idx < 0 || idx >= n_points) {
            throw py::index_error("face vertex index out of bounds");
        }
    }
}

py::tuple compute_face_geometry_topology(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    const NativeFaceTopology& topology)
{
    const auto pts = points.unchecked<2>();
    if (pts.ndim() != 2 || pts.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }

    const auto n_points = static_cast<long long>(pts.shape(0));
    validate_topology(topology, n_points);
    const auto n_faces = topology.face_count();

    py::array_t<double> centres({n_faces, static_cast<py::ssize_t>(3)});
    py::array_t<double> normals({n_faces, static_cast<py::ssize_t>(3)});
    py::array_t<double> areas(py::array::ShapeContainer{n_faces});

    auto c = centres.mutable_unchecked<2>();
    auto n = normals.mutable_unchecked<2>();
    auto a = areas.mutable_unchecked<1>();

    {
        py::gil_scoped_release release;
        for (py::ssize_t face_i = 0; face_i < n_faces; ++face_i) {
            const auto begin = static_cast<size_t>(
                topology.offsets[static_cast<size_t>(face_i)]);
            const auto end = static_cast<size_t>(
                topology.offsets[static_cast<size_t>(face_i) + 1]);
            const auto k = end - begin;

            double cx = 0.0;
            double cy = 0.0;
            double cz = 0.0;

            for (size_t j = begin; j < end; ++j) {
                const auto idx = topology.indices[j];
                cx += pts(idx, 0);
                cy += pts(idx, 1);
                cz += pts(idx, 2);
            }

            if (k > 0) {
                c(face_i, 0) = cx / static_cast<double>(k);
                c(face_i, 1) = cy / static_cast<double>(k);
                c(face_i, 2) = cz / static_cast<double>(k);
            } else {
                c(face_i, 0) = 0.0;
                c(face_i, 1) = 0.0;
                c(face_i, 2) = 0.0;
            }

            n(face_i, 0) = 0.0;
            n(face_i, 1) = 0.0;
            n(face_i, 2) = 0.0;
            a(face_i) = 0.0;

            if (k < 3) {
                continue;
            }

            const Point3 p0 = point_at(pts, topology.indices[begin]);
            Point3 area_vec{0.0, 0.0, 0.0};

            for (size_t j = begin + 1; j + 1 < end; ++j) {
                const Point3 p1 = point_at(pts, topology.indices[j]);
                const Point3 p2 = point_at(pts, topology.indices[j + 1]);
                const Point3 cr = cross(sub(p1, p0), sub(p2, p0));
                area_vec[0] += cr[0];
                area_vec[1] += cr[1];
                area_vec[2] += cr[2];
            }

            const double mag = std::sqrt(
                area_vec[0] * area_vec[0]
                + area_vec[1] * area_vec[1]
                + area_vec[2] * area_vec[2]);
            a(face_i) = 0.5 * mag;
            if (mag > 0.0) {
                n(face_i, 0) = area_vec[0] / mag;
                n(face_i, 1) = area_vec[1] / mag;
                n(face_i, 2) = area_vec[2] / mag;
            }
        }
    }

    return py::make_tuple(centres, normals, areas);
}

py::tuple compute_face_geometry(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    py::sequence faces)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    auto topology = topology_from_python_faces(
        std::move(faces), static_cast<long long>(points.shape(0)));
    return compute_face_geometry_topology(std::move(points), topology);
}

py::array_t<double> compute_cell_centres_from_vertices(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    py::sequence faces,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    py::object neighbour_obj,
    long long n_cells)
{
    const auto pts = points.unchecked<2>();
    const auto own = owner.unchecked<1>();
    if (pts.ndim() != 2 || pts.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (n_cells < 0) {
        throw std::invalid_argument("n_cells must be non-negative");
    }

    const auto n_faces = static_cast<py::ssize_t>(faces.size());
    const auto n_points = static_cast<long long>(pts.shape(0));

    std::vector<long long> neighbour_values;
    if (!neighbour_obj.is_none()) {
        py::array_t<long long, py::array::c_style | py::array::forcecast> neighbour =
            neighbour_obj.cast<
                py::array_t<long long, py::array::c_style | py::array::forcecast>>();
        const auto nbr = neighbour.unchecked<1>();
        neighbour_values.reserve(static_cast<size_t>(nbr.shape(0)));
        for (py::ssize_t i = 0; i < nbr.shape(0); ++i) {
            neighbour_values.push_back(nbr(i));
        }
    }
    const auto n_internal = static_cast<py::ssize_t>(neighbour_values.size());

    std::vector<std::unordered_set<long long>> cell_vertices(
        static_cast<size_t>(n_cells));

    for (py::ssize_t face_i = 0; face_i < n_faces; ++face_i) {
        py::sequence face = faces[face_i].cast<py::sequence>();
        const auto k = static_cast<py::ssize_t>(face.size());
        if (k == 0) {
            continue;
        }

        const auto own_cell = face_i < own.shape(0) ? own(face_i) : -1;
        const bool add_owner = own_cell >= 0 && own_cell < n_cells;

        long long nbr_cell = -1;
        bool add_neighbour = false;
        if (face_i < n_internal) {
            nbr_cell = neighbour_values[static_cast<size_t>(face_i)];
            add_neighbour = nbr_cell >= 0 && nbr_cell < n_cells;
        }

        if (!add_owner && !add_neighbour) {
            continue;
        }

        for (py::ssize_t j = 0; j < k; ++j) {
            const auto vidx = as_vertex_index(face[j], n_points);
            if (add_owner) {
                cell_vertices[static_cast<size_t>(own_cell)].insert(vidx);
            }
            if (add_neighbour) {
                cell_vertices[static_cast<size_t>(nbr_cell)].insert(vidx);
            }
        }
    }

    py::array_t<double> centres({static_cast<py::ssize_t>(n_cells),
                                 static_cast<py::ssize_t>(3)});
    auto c = centres.mutable_unchecked<2>();
    for (long long cell_i = 0; cell_i < n_cells; ++cell_i) {
        double sx = 0.0;
        double sy = 0.0;
        double sz = 0.0;
        const auto& verts = cell_vertices[static_cast<size_t>(cell_i)];
        for (const auto vidx : verts) {
            sx += pts(vidx, 0);
            sy += pts(vidx, 1);
            sz += pts(vidx, 2);
        }
        if (!verts.empty()) {
            const double inv = 1.0 / static_cast<double>(verts.size());
            c(cell_i, 0) = sx * inv;
            c(cell_i, 1) = sy * inv;
            c(cell_i, 2) = sz * inv;
        } else {
            c(cell_i, 0) = 0.0;
            c(cell_i, 1) = 0.0;
            c(cell_i, 2) = 0.0;
        }
    }

    return centres;
}

py::tuple compute_cell_centres_and_aspect_ratios_topology(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    const NativeFaceTopology& topology,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    py::object neighbour_obj,
    long long n_cells)
{
    const auto pts = points.unchecked<2>();
    const auto own = owner.unchecked<1>();
    if (pts.ndim() != 2 || pts.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (n_cells < 0) {
        throw std::invalid_argument("n_cells must be non-negative");
    }

    const auto n_faces = topology.face_count();
    if (own.shape(0) < n_faces) {
        throw std::invalid_argument("owner must contain one entry per face");
    }
    const auto n_points = static_cast<long long>(pts.shape(0));
    validate_topology(topology, n_points);

    std::vector<long long> neighbour_values;
    if (!neighbour_obj.is_none()) {
        py::array_t<long long, py::array::c_style | py::array::forcecast> neighbour =
            neighbour_obj.cast<
                py::array_t<long long, py::array::c_style | py::array::forcecast>>();
        const auto nbr = neighbour.unchecked<1>();
        neighbour_values.reserve(static_cast<size_t>(nbr.shape(0)));
        for (py::ssize_t i = 0; i < nbr.shape(0); ++i) {
            neighbour_values.push_back(nbr(i));
        }
    }
    const auto n_internal = static_cast<py::ssize_t>(neighbour_values.size());

    using TaggedVertex = std::uint64_t;
    constexpr TaggedVertex owner_vertex_flag = 1;
    constexpr TaggedVertex max_tagged_vertex =
        std::numeric_limits<TaggedVertex>::max() >> 1;
    if (n_points > 0
        && static_cast<unsigned long long>(n_points - 1) > max_tagged_vertex) {
        throw std::overflow_error("point index cannot be packed safely");
    }

    if (static_cast<unsigned long long>(n_cells)
        >= static_cast<unsigned long long>(
            std::numeric_limits<size_t>::max())) {
        throw std::overflow_error("cell count cannot be indexed safely");
    }
    const auto n_cells_size = static_cast<size_t>(n_cells);
    std::vector<size_t> cell_offsets;
    std::vector<TaggedVertex> cell_vertices;
    std::vector<Point3> centre_values(
        n_cells_size, Point3{0.0, 0.0, 0.0});
    std::vector<long long> out_cells;
    std::vector<double> out_ratios;

    {
        py::gil_scoped_release release;

        cell_offsets.assign(n_cells_size + 1, 0);
        for (py::ssize_t face_i = 0; face_i < n_faces; ++face_i) {
            const auto own_cell = own(face_i);
            const bool add_owner = own_cell >= 0 && own_cell < n_cells;

            long long nbr_cell = -1;
            bool add_neighbour = false;
            if (face_i < n_internal) {
                nbr_cell = neighbour_values[static_cast<size_t>(face_i)];
                add_neighbour = nbr_cell >= 0 && nbr_cell < n_cells;
            }
            if (!add_owner && !add_neighbour) {
                continue;
            }

            const auto begin = static_cast<size_t>(
                topology.offsets[static_cast<size_t>(face_i)]);
            const auto end = static_cast<size_t>(
                topology.offsets[static_cast<size_t>(face_i) + 1]);
            const auto face_vertex_count = end - begin;
            const auto add_contribution = [&](long long cell_i) {
                auto& count = cell_offsets[static_cast<size_t>(cell_i) + 1];
                if (face_vertex_count
                    > std::numeric_limits<size_t>::max() - count) {
                    throw std::overflow_error(
                        "cell vertex contribution count overflow");
                }
                count += face_vertex_count;
            };
            if (add_owner) {
                add_contribution(own_cell);
            }
            if (add_neighbour) {
                add_contribution(nbr_cell);
            }
        }

        for (size_t cell_i = 0; cell_i < n_cells_size; ++cell_i) {
            if (cell_offsets[cell_i + 1]
                > cell_vertices.max_size() - cell_offsets[cell_i]) {
                throw std::overflow_error(
                    "cell vertex contribution prefix sum overflow");
            }
            cell_offsets[cell_i + 1] += cell_offsets[cell_i];
        }
        cell_vertices.resize(cell_offsets.back());
        std::vector<size_t> write_positions(
            cell_offsets.begin(), cell_offsets.end() - 1);

        // Low bit records owner-face membership; remaining bits hold the
        // validated non-negative vertex index.
        for (py::ssize_t face_i = 0; face_i < n_faces; ++face_i) {
            const auto own_cell = own(face_i);
            const bool add_owner = own_cell >= 0 && own_cell < n_cells;

            long long nbr_cell = -1;
            bool add_neighbour = false;
            if (face_i < n_internal) {
                nbr_cell = neighbour_values[static_cast<size_t>(face_i)];
                add_neighbour = nbr_cell >= 0 && nbr_cell < n_cells;
            }
            if (!add_owner && !add_neighbour) {
                continue;
            }

            const auto begin = static_cast<size_t>(
                topology.offsets[static_cast<size_t>(face_i)]);
            const auto end = static_cast<size_t>(
                topology.offsets[static_cast<size_t>(face_i) + 1]);
            for (size_t j = begin; j < end; ++j) {
                const auto vertex_i = topology.indices[j];
                const auto packed_vertex =
                    static_cast<TaggedVertex>(vertex_i) << 1;
                if (add_owner) {
                    cell_vertices[write_positions[
                        static_cast<size_t>(own_cell)]++] =
                        packed_vertex | owner_vertex_flag;
                }
                if (add_neighbour) {
                    cell_vertices[write_positions[
                        static_cast<size_t>(nbr_cell)]++] = packed_vertex;
                }
            }
        }

        constexpr long long sample_cap = 25'000;
        const long long step = n_cells > sample_cap
            ? std::max(1LL, n_cells / sample_cap)
            : 1LL;
        const auto step_size = static_cast<size_t>(step);
        const auto sample_count = n_cells_size == 0
            ? 0
            : 1 + (n_cells_size - 1) / step_size;
        out_cells.reserve(sample_count);
        out_ratios.reserve(out_cells.capacity());

        for (long long cell_i = 0; cell_i < n_cells; ++cell_i) {
            const auto begin = cell_offsets[static_cast<size_t>(cell_i)];
            const auto end = cell_offsets[static_cast<size_t>(cell_i) + 1];
            std::sort(
                cell_vertices.begin() + static_cast<std::ptrdiff_t>(begin),
                cell_vertices.begin() + static_cast<std::ptrdiff_t>(end));
            if (begin == end) {
                continue;
            }

            size_t unique_end = begin;
            for (size_t read_i = begin; read_i < end;) {
                const auto vertex_i = cell_vertices[read_i] >> 1;
                TaggedVertex owner_flag = 0;
                do {
                    owner_flag |=
                        cell_vertices[read_i] & owner_vertex_flag;
                    ++read_i;
                } while (read_i < end
                         && (cell_vertices[read_i] >> 1) == vertex_i);
                cell_vertices[unique_end++] =
                    (vertex_i << 1) | owner_flag;
            }
            const auto unique_count = unique_end - begin;

            Point3 sum{0.0, 0.0, 0.0};
            for (size_t slot = begin; slot < unique_end; ++slot) {
                const auto packed_vertex = cell_vertices[slot];
                const auto vertex_i = static_cast<long long>(packed_vertex >> 1);
                sum[0] += pts(vertex_i, 0);
                sum[1] += pts(vertex_i, 1);
                sum[2] += pts(vertex_i, 2);
            }
            const double inv = 1.0 / static_cast<double>(unique_count);
            centre_values[static_cast<size_t>(cell_i)] = {
                sum[0] * inv, sum[1] * inv, sum[2] * inv};

            if (cell_i % step != 0 || unique_count < 2) {
                continue;
            }

            double min_d2 = std::numeric_limits<double>::infinity();
            double max_d2 = 0.0;
            for (size_t i = begin; i + 1 < unique_end; ++i) {
                if ((cell_vertices[i] & owner_vertex_flag) == 0) {
                    continue;
                }
                const auto vi =
                    static_cast<long long>(cell_vertices[i] >> 1);
                for (size_t j = i + 1; j < unique_end; ++j) {
                    if ((cell_vertices[j] & owner_vertex_flag) == 0) {
                        continue;
                    }
                    const auto vj =
                        static_cast<long long>(cell_vertices[j] >> 1);
                    const double dx = pts(vi, 0) - pts(vj, 0);
                    const double dy = pts(vi, 1) - pts(vj, 1);
                    const double dz = pts(vi, 2) - pts(vj, 2);
                    const double d2 = dx * dx + dy * dy + dz * dz;
                    if (d2 > 1e-30) {
                        min_d2 = std::min(min_d2, d2);
                        max_d2 = std::max(max_d2, d2);
                    }
                }
            }

            if (!std::isfinite(min_d2)) {
                continue;
            }
            out_cells.push_back(cell_i);
            out_ratios.push_back(std::sqrt(max_d2 / min_d2));
        }
    }

    py::array_t<double> centres({static_cast<py::ssize_t>(n_cells),
                                 static_cast<py::ssize_t>(3)});
    py::array_t<long long> cell_ids(
        py::array::ShapeContainer{static_cast<py::ssize_t>(out_cells.size())});
    py::array_t<double> ratios(
        py::array::ShapeContainer{static_cast<py::ssize_t>(out_ratios.size())});
    auto centres_out = centres.mutable_unchecked<2>();
    auto ids_out = cell_ids.mutable_unchecked<1>();
    auto ratios_out = ratios.mutable_unchecked<1>();
    for (long long cell_i = 0; cell_i < n_cells; ++cell_i) {
        const auto& centre = centre_values[static_cast<size_t>(cell_i)];
        centres_out(cell_i, 0) = centre[0];
        centres_out(cell_i, 1) = centre[1];
        centres_out(cell_i, 2) = centre[2];
    }
    for (size_t i = 0; i < out_cells.size(); ++i) {
        ids_out(static_cast<py::ssize_t>(i)) = out_cells[i];
        ratios_out(static_cast<py::ssize_t>(i)) = out_ratios[i];
    }
    return py::make_tuple(centres, cell_ids, ratios);
}

py::tuple compute_cell_centres_and_aspect_ratios(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    py::sequence faces,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    py::object neighbour_obj,
    long long n_cells)
{
    if (points.ndim() != 2 || points.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    auto topology = topology_from_python_faces(
        std::move(faces), static_cast<long long>(points.shape(0)));
    return compute_cell_centres_and_aspect_ratios_topology(
        std::move(points), topology, std::move(owner),
        std::move(neighbour_obj), n_cells);
}

struct MetricSummary {
    double min = 0.0;
    double mean = 0.0;
    double p95 = 0.0;
    double max = 0.0;
};

MetricSummary summarize_finite(std::vector<double>& values)
{
    values.erase(
        std::remove_if(values.begin(), values.end(), [](double value) {
            return !std::isfinite(value);
        }),
        values.end());
    if (values.empty()) {
        return {};
    }
    std::sort(values.begin(), values.end());
    const double mean = std::accumulate(values.begin(), values.end(), 0.0)
        / static_cast<double>(values.size());
    const double position = 0.95 * static_cast<double>(values.size() - 1);
    const auto lower = static_cast<size_t>(std::floor(position));
    const auto upper = static_cast<size_t>(std::ceil(position));
    const double fraction = position - static_cast<double>(lower);
    const double p95 = values[lower]
        + fraction * (values[upper] - values[lower]);
    return {values.front(), mean, p95, values.back()};
}

double norm3(const Point3& value)
{
    return std::sqrt(
        value[0] * value[0] + value[1] * value[1]
        + value[2] * value[2]);
}

struct BinarySaving final {
    std::uint64_t coefficient = 0;
    int exponent = 0;
};

BinarySaving decompose_binary_saving(double value)
{
    if (!(value > 0.0)) {
        return {};
    }
    const std::uint64_t bits = std::bit_cast<std::uint64_t>(value);
    const std::uint64_t fraction = bits & ((std::uint64_t{1} << 52) - 1);
    const unsigned exponent_field = static_cast<unsigned>((bits >> 52) & 0x7ffU);
    std::uint64_t coefficient = fraction;
    int exponent = -1074;
    if (exponent_field != 0) {
        coefficient |= std::uint64_t{1} << 52;
        exponent = static_cast<int>(exponent_field) - 1023 - 52;
    }
    const unsigned trailing_zeros = std::countr_zero(coefficient);
    coefficient >>= trailing_zeros;
    exponent += static_cast<int>(trailing_zeros);
    return {coefficient, exponent};
}

template <std::size_t WordCount>
std::vector<int> solve_exact_pair_matching(
    const std::vector<std::vector<double>>& savings,
    std::size_t graph_size,
    int minimum_exponent,
    std::size_t cardinality_shift)
{
    using Matching = autotessell::matching::MaximumWeightMatching<WordCount>;
    using Weight = typename Matching::Weight;
    Matching matching(static_cast<int>(graph_size));
    for (std::size_t first = 0; first < graph_size; ++first) {
        for (std::size_t second = first + 1; second < graph_size; ++second) {
            Weight edge_weight = Weight::shifted(1, cardinality_shift);
            const BinarySaving binary = decompose_binary_saving(savings[first][second]);
            if (binary.coefficient != 0) {
                const auto shift = static_cast<std::size_t>(
                    binary.exponent - minimum_exponent);
                edge_weight += Weight::shifted(binary.coefficient, shift);
            }
            matching.add_edge(
                static_cast<int>(first + 1),
                static_cast<int>(second + 1),
                edge_weight.doubled());
        }
    }
    return matching.solve();
}

std::vector<int> dispatch_exact_pair_matching(
    const std::vector<std::vector<double>>& savings,
    std::size_t graph_size,
    int minimum_exponent,
    std::size_t required_bits)
{
    // A dominant common bonus preserves maximum cardinality during every
    // primal-dual phase without discarding any lower exact saving bit.
    const std::size_t cardinality_shift = required_bits
        + static_cast<std::size_t>(std::bit_width(graph_size));
    // Reserve headroom for the dominant bonus, doubled edge weights, and duals.
    const std::size_t working_bits = cardinality_shift + 16;
    if (working_bits <= 128) {
        return solve_exact_pair_matching<2>(
            savings, graph_size, minimum_exponent, cardinality_shift);
    }
    if (working_bits <= 256) {
        return solve_exact_pair_matching<4>(
            savings, graph_size, minimum_exponent, cardinality_shift);
    }
    if (working_bits <= 512) {
        return solve_exact_pair_matching<8>(
            savings, graph_size, minimum_exponent, cardinality_shift);
    }
    if (working_bits <= 1024) {
        return solve_exact_pair_matching<16>(
            savings, graph_size, minimum_exponent, cardinality_shift);
    }
    if (working_bits <= 2176) {
        return solve_exact_pair_matching<34>(
            savings, graph_size, minimum_exponent, cardinality_shift);
    }
    throw std::overflow_error("binary64 matching weights exceed exact capacity");
}

double minimum_pairing_sum(const std::vector<Point3>& vectors)
{
    if (vectors.empty()) {
        return 0.0;
    }
    if (vectors.size() > kMaximumPairingFaceCount) {
        throw std::invalid_argument(
            "native Phase-0 pairing supports at most 256 faces per cell");
    }

    std::vector<double> norms;
    norms.reserve(vectors.size());
    for (const auto& vector : vectors) {
        const double magnitude = norm3(vector);
        if (!std::isfinite(magnitude)) {
            throw std::invalid_argument("pairing vectors must be finite");
        }
        norms.push_back(magnitude);
    }

    const size_t graph_size = vectors.size() + (vectors.size() & 1U);
    std::vector<std::vector<double>> savings(
        graph_size, std::vector<double>(graph_size, 0.0));
    std::optional<int> minimum_exponent;
    std::size_t required_bits = 1;
    for (size_t first = 0; first < vectors.size(); ++first) {
        for (size_t second = first + 1; second < vectors.size(); ++second) {
            const Point3 pair{
                vectors[first][0] + vectors[second][0],
                vectors[first][1] + vectors[second][1],
                vectors[first][2] + vectors[second][2]};
            const double raw_saving = norms[first] + norms[second] - norm3(pair);
            if (!std::isfinite(raw_saving)) {
                throw std::invalid_argument("pairing vector arithmetic must remain finite");
            }
            const double saving = std::max(0.0, raw_saving);
            savings[first][second] = saving;
            savings[second][first] = saving;
            const BinarySaving binary = decompose_binary_saving(saving);
            if (binary.coefficient != 0) {
                minimum_exponent = minimum_exponent.has_value()
                    ? std::min(*minimum_exponent, binary.exponent)
                    : binary.exponent;
            }
        }
    }

    const int exact_exponent = minimum_exponent.value_or(0);
    for (std::size_t first = 0; first < vectors.size(); ++first) {
        for (std::size_t second = first + 1; second < vectors.size(); ++second) {
            const BinarySaving binary = decompose_binary_saving(savings[first][second]);
            if (binary.coefficient != 0) {
                const auto coefficient_bits = static_cast<std::size_t>(
                    std::bit_width(binary.coefficient));
                required_bits = std::max(
                    required_bits,
                    coefficient_bits + static_cast<std::size_t>(
                        binary.exponent - exact_exponent));
            }
        }
    }

    const std::vector<int> mates = dispatch_exact_pair_matching(
        savings, graph_size, exact_exponent, required_bits);
    if (mates.size() != graph_size) {
        throw std::logic_error("weighted pairing returned an incomplete mate vector");
    }
    std::vector<bool> covered(graph_size, false);
    for (std::size_t first = 0; first < graph_size; ++first) {
        const int second_raw = mates[first];
        if (second_raw < 0 || static_cast<std::size_t>(second_raw) >= graph_size) {
            throw std::logic_error("weighted pairing mate is out of range");
        }
        const auto second = static_cast<std::size_t>(second_raw);
        if (second == first) {
            throw std::logic_error("weighted pairing returned a self match");
        }
        if (mates[second] != static_cast<int>(first)) {
            throw std::logic_error("weighted pairing mate relation is not involutive");
        }
        if (first < second) {
            if (covered[first] || covered[second]) {
                throw std::logic_error("weighted pairing reused a vertex");
            }
            covered[first] = true;
            covered[second] = true;
        }
    }
    if (std::find(covered.begin(), covered.end(), false) != covered.end()) {
        throw std::logic_error("weighted pairing did not cover every vertex");
    }
    std::vector<double> selected_costs;
    selected_costs.reserve((vectors.size() + 1) / 2);
    for (size_t first = 0; first < vectors.size(); ++first) {
        const int second_raw = mates[first];
        if (second_raw < 0) {
            throw std::logic_error("weighted pairing did not produce a full matching");
        }
        const auto second = static_cast<size_t>(second_raw);
        if (second >= vectors.size()) {
            selected_costs.push_back(norms[first]);
        } else if (first < second) {
            const Point3 pair{
                vectors[first][0] + vectors[second][0],
                vectors[first][1] + vectors[second][1],
                vectors[first][2] + vectors[second][2]};
            selected_costs.push_back(norm3(pair));
        }
    }
    std::sort(selected_costs.begin(), selected_costs.end());
    long double objective = 0.0L;
    for (const double cost : selected_costs) {
        objective += static_cast<long double>(cost);
    }
    const double result = static_cast<double>(objective);
    if (!std::isfinite(result)) {
        throw std::invalid_argument("pairing objective must remain finite");
    }
    return result;
}

double minimum_pairing_sum_array(py::array vectors)
{
    if (vectors.ndim() != 2 || vectors.shape(1) != 3) {
        throw std::invalid_argument("vectors must have shape (n, 3)");
    }
    if (vectors.shape(0) > static_cast<py::ssize_t>(kMaximumPairingFaceCount)) {
        throw std::invalid_argument(
            "native Phase-0 pairing supports at most 256 faces per cell");
    }
    py::array_t<double, py::array::c_style | py::array::forcecast> values_array(vectors);
    const auto values = values_array.unchecked<2>();
    std::vector<Point3> copied;
    copied.reserve(static_cast<size_t>(values_array.shape(0)));
    for (py::ssize_t row = 0; row < values_array.shape(0); ++row) {
        copied.push_back(Point3{values(row, 0), values(row, 1), values(row, 2)});
    }
    py::gil_scoped_release release;
    return minimum_pairing_sum(copied);
}

py::tuple compute_triangle_phase0_metrics_topology(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    const NativeFaceTopology& topology,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    py::array_t<long long, py::array::c_style | py::array::forcecast> neighbour,
    long long n_internal,
    py::array_t<double, py::array::c_style | py::array::forcecast> cell_centres,
    py::array_t<double, py::array::c_style | py::array::forcecast> face_centres,
    py::array_t<double, py::array::c_style | py::array::forcecast> face_normals,
    py::array_t<double, py::array::c_style | py::array::forcecast> face_areas,
    py::array_t<double, py::array::c_style | py::array::forcecast> cell_volumes)
{
    if (!topology.all_triangles) {
        throw std::invalid_argument("triangle Phase-0 kernel requires triangle faces");
    }
    if (points.ndim() != 2 || points.shape(1) != 3
        || cell_centres.ndim() != 2 || cell_centres.shape(1) != 3
        || face_centres.ndim() != 2 || face_centres.shape(1) != 3
        || face_normals.ndim() != 2 || face_normals.shape(1) != 3
        || owner.ndim() != 1 || neighbour.ndim() != 1
        || face_areas.ndim() != 1 || cell_volumes.ndim() != 1) {
        throw std::invalid_argument("invalid array shape for triangle Phase-0 metrics");
    }

    const auto n_faces = topology.face_count();
    const auto n_cells = cell_centres.shape(0);
    if (owner.shape(0) < n_faces || face_centres.shape(0) < n_faces
        || face_normals.shape(0) < n_faces || face_areas.shape(0) < n_faces) {
        throw std::invalid_argument("face arrays must contain every topology face");
    }
    validate_topology(topology, static_cast<long long>(points.shape(0)));

    const auto pts = points.unchecked<2>();
    const auto own = owner.unchecked<1>();
    const auto nbr = neighbour.unchecked<1>();
    const auto cc = cell_centres.unchecked<2>();
    const auto fc = face_centres.unchecked<2>();
    const auto fn = face_normals.unchecked<2>();
    const auto fa = face_areas.unchecked<1>();
    const auto volumes = cell_volumes.unchecked<1>();
    const auto internal_count = std::max<py::ssize_t>(
        0, std::min<py::ssize_t>(
               {static_cast<py::ssize_t>(n_internal), nbr.shape(0), n_faces}));

    std::vector<double> psi_values;
    std::vector<double> h_values;
    std::vector<double> circle_ratios;
    std::vector<double> sphericities;
    std::vector<double> diameters;
    std::vector<double> pairing_residuals;
    std::vector<size_t> cell_face_offsets(static_cast<size_t>(n_cells) + 1, 0);
    std::vector<long long> cell_faces;

    {
        py::gil_scoped_release release;

        psi_values.reserve(static_cast<size_t>(internal_count));
        for (py::ssize_t face_i = 0; face_i < internal_count; ++face_i) {
            const auto owner_i = own(face_i);
            const auto neighbour_i = nbr(face_i);
            if (owner_i < 0 || neighbour_i < 0
                || owner_i >= n_cells || neighbour_i >= n_cells) {
                continue;
            }
            const Point3 d{
                cc(neighbour_i, 0) - cc(owner_i, 0),
                cc(neighbour_i, 1) - cc(owner_i, 1),
                cc(neighbour_i, 2) - cc(owner_i, 2)};
            const double d2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
            if (d2 <= 1.0e-60) {
                continue;
            }
            const Point3 face_delta{
                fc(face_i, 0) - cc(owner_i, 0),
                fc(face_i, 1) - cc(owner_i, 1),
                fc(face_i, 2) - cc(owner_i, 2)};
            const double t = (face_delta[0] * d[0] + face_delta[1] * d[1]
                              + face_delta[2] * d[2])
                / d2;
            const Point3 residual{
                face_delta[0] - t * d[0],
                face_delta[1] - t * d[1],
                face_delta[2] - t * d[2]};
            psi_values.push_back(norm3(residual) / std::sqrt(d2));
        }

        for (py::ssize_t face_i = 0; face_i < n_faces; ++face_i) {
            const auto owner_i = own(face_i);
            if (owner_i >= 0 && owner_i < n_cells) {
                ++cell_face_offsets[static_cast<size_t>(owner_i) + 1];
            }
            if (face_i < internal_count) {
                const auto neighbour_i = nbr(face_i);
                if (neighbour_i >= 0 && neighbour_i < n_cells) {
                    ++cell_face_offsets[static_cast<size_t>(neighbour_i) + 1];
                }
            }
        }
        for (size_t cell_i = 0; cell_i < static_cast<size_t>(n_cells); ++cell_i) {
            cell_face_offsets[cell_i + 1] += cell_face_offsets[cell_i];
        }
        cell_faces.resize(cell_face_offsets.back());
        std::vector<size_t> write_positions(
            cell_face_offsets.begin(), cell_face_offsets.end() - 1);
        for (py::ssize_t face_i = 0; face_i < n_faces; ++face_i) {
            const auto owner_i = own(face_i);
            if (owner_i >= 0 && owner_i < n_cells) {
                cell_faces[write_positions[static_cast<size_t>(owner_i)]++] = face_i;
            }
            if (face_i < internal_count) {
                const auto neighbour_i = nbr(face_i);
                if (neighbour_i >= 0 && neighbour_i < n_cells) {
                    cell_faces[write_positions[static_cast<size_t>(neighbour_i)]++] = face_i;
                }
            }
        }

        h_values.reserve(static_cast<size_t>(n_cells));
        circle_ratios.reserve(static_cast<size_t>(n_cells));
        sphericities.reserve(static_cast<size_t>(n_cells));
        diameters.reserve(static_cast<size_t>(n_cells));
        pairing_residuals.reserve(static_cast<size_t>(n_cells));
        std::vector<long long> vertex_ids;
        std::vector<Point3> area_vectors;
        for (py::ssize_t cell_i = 0; cell_i < n_cells; ++cell_i) {
            const auto begin = cell_face_offsets[static_cast<size_t>(cell_i)];
            const auto end = cell_face_offsets[static_cast<size_t>(cell_i) + 1];
            if (begin == end) {
                continue;
            }
            vertex_ids.clear();
            vertex_ids.reserve(3 * (end - begin));
            area_vectors.clear();
            area_vectors.reserve(end - begin);
            double total_area = 0.0;
            double pairing_denominator = 0.0;
            for (size_t slot = begin; slot < end; ++slot) {
                const auto face_i = cell_faces[slot];
                const auto topology_begin = static_cast<size_t>(
                    topology.offsets[static_cast<size_t>(face_i)]);
                const auto topology_end = static_cast<size_t>(
                    topology.offsets[static_cast<size_t>(face_i) + 1]);
                vertex_ids.insert(
                    vertex_ids.end(),
                    topology.indices.begin() + static_cast<std::ptrdiff_t>(topology_begin),
                    topology.indices.begin() + static_cast<std::ptrdiff_t>(topology_end));
                total_area += fa(face_i);
                const double area = fa(face_i);
                const bool finite_normal = std::isfinite(fn(face_i, 0))
                    && std::isfinite(fn(face_i, 1))
                    && std::isfinite(fn(face_i, 2));
                const Point3 area_vector{
                    fn(face_i, 0) * area,
                    fn(face_i, 1) * area,
                    fn(face_i, 2) * area};
                const double magnitude = norm3(area_vector);
                if (finite_normal && std::isfinite(area) && area > 1.0e-30
                    && std::isfinite(magnitude)) {
                    area_vectors.push_back(area_vector);
                    pairing_denominator += magnitude;
                }
            }
            std::sort(vertex_ids.begin(), vertex_ids.end());
            vertex_ids.erase(
                std::unique(vertex_ids.begin(), vertex_ids.end()), vertex_ids.end());
            if (vertex_ids.size() < 4) {
                continue;
            }

            const double pairing = pairing_denominator > 1.0e-30
                ? std::clamp(
                      minimum_pairing_sum(area_vectors) / pairing_denominator,
                      0.0, 1.0)
                : 0.0;
            pairing_residuals.push_back(pairing);

            double diameter2 = 0.0;
            for (size_t i = 0; i + 1 < vertex_ids.size(); ++i) {
                for (size_t j = i + 1; j < vertex_ids.size(); ++j) {
                    const auto vi = vertex_ids[i];
                    const auto vj = vertex_ids[j];
                    const double dx = pts(vi, 0) - pts(vj, 0);
                    const double dy = pts(vi, 1) - pts(vj, 1);
                    const double dz = pts(vi, 2) - pts(vj, 2);
                    diameter2 = std::max(diameter2, dx * dx + dy * dy + dz * dz);
                }
            }
            const double diameter = std::sqrt(diameter2);
            diameters.push_back(diameter);

            const double volume = cell_i < volumes.shape(0)
                ? std::abs(volumes(cell_i))
                : 0.0;
            if (total_area > 1.0e-30) {
                h_values.push_back(6.0 * volume / total_area);
                const double sphericity = std::cbrt(
                    36.0 * std::numbers::pi * volume * volume) / total_area;
                sphericities.push_back(std::clamp(sphericity, 0.0, 1.0));
            } else {
                h_values.push_back(0.0);
                sphericities.push_back(0.0);
            }

            if (diameter <= 1.0e-30) {
                circle_ratios.push_back(0.0);
                continue;
            }
            double circumradius = 0.0;
            for (const auto vertex_i : vertex_ids) {
                const double dx = pts(vertex_i, 0) - cc(cell_i, 0);
                const double dy = pts(vertex_i, 1) - cc(cell_i, 1);
                const double dz = pts(vertex_i, 2) - cc(cell_i, 2);
                circumradius = std::max(
                    circumradius, std::sqrt(dx * dx + dy * dy + dz * dz));
            }
            double inradius = std::numeric_limits<double>::infinity();
            for (size_t slot = begin; slot < end; ++slot) {
                const auto face_i = cell_faces[slot];
                const Point3 normal{fn(face_i, 0), fn(face_i, 1), fn(face_i, 2)};
                const double normal_magnitude = norm3(normal);
                if (normal_magnitude <= 1.0e-30) {
                    continue;
                }
                const double distance = std::abs(
                    (fc(face_i, 0) - cc(cell_i, 0)) * normal[0]
                    + (fc(face_i, 1) - cc(cell_i, 1)) * normal[1]
                    + (fc(face_i, 2) - cc(cell_i, 2)) * normal[2])
                    / normal_magnitude;
                inradius = std::min(inradius, distance);
            }
            circle_ratios.push_back(
                std::isfinite(inradius) && circumradius > 1.0e-30
                    ? std::clamp(inradius / circumradius, 0.0, 1.0)
                    : 0.0);
        }
    }

    std::vector<double> uniformity;
    uniformity.reserve(diameters.size());
    if (!diameters.empty()) {
        const double max_diameter = *std::max_element(diameters.begin(), diameters.end());
        const double denominator = std::max(max_diameter, 1.0e-30);
        for (const double diameter : diameters) {
            uniformity.push_back(diameter / denominator);
        }
    }
    const auto psi = summarize_finite(psi_values);
    const auto h = summarize_finite(h_values);
    const auto circle = summarize_finite(circle_ratios);
    const auto sphericity = summarize_finite(sphericities);
    const auto uniform = summarize_finite(uniformity);
    const auto pairing = summarize_finite(pairing_residuals);
    const std::array<double, 29> values{
        0.0, 0.0, 0.0,
        0.0, 0.0, 0.0,
        psi.max, psi.mean, psi.p95,
        h.min, h.mean, h.p95, h.max,
        circle.min, circle.mean, circle.p95, circle.max,
        sphericity.min, sphericity.mean, sphericity.p95, sphericity.max,
        uniform.min, uniform.mean, uniform.p95, uniform.max,
        pairing.min, pairing.mean, pairing.p95, pairing.max};
    py::tuple result(values.size());
    for (size_t i = 0; i < values.size(); ++i) {
        result[static_cast<py::ssize_t>(i)] = values[i];
    }
    return result;
}

py::tuple compute_non_orthogonality(
    py::array_t<double, py::array::c_style | py::array::forcecast> face_centres,
    py::array_t<double, py::array::c_style | py::array::forcecast> face_normals,
    py::array_t<double, py::array::c_style | py::array::forcecast> cell_centres,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    py::array_t<long long, py::array::c_style | py::array::forcecast> neighbour,
    long long n_internal,
    double severe_threshold)
{
    if (n_internal <= 0) {
        return py::make_tuple(0.0, 0.0, 0);
    }
    (void)face_centres;
    const auto fn = face_normals.unchecked<2>();
    const auto cc = cell_centres.unchecked<2>();
    const auto own = owner.unchecked<1>();
    const auto nbr = neighbour.unchecked<1>();

    const auto max_i = std::min<long long>(
        n_internal,
        std::min<long long>(own.shape(0), nbr.shape(0)));
    double max_angle = 0.0;
    double sum_angle = 0.0;
    long long n_valid = 0;
    long long severe = 0;

    constexpr double pi = 3.141592653589793238462643383279502884;
    for (long long i = 0; i < max_i; ++i) {
        const auto oi = own(i);
        const auto ni = nbr(i);
        if (oi < 0 || ni < 0 || oi >= cc.shape(0) || ni >= cc.shape(0)) {
            continue;
        }
        const double dx = cc(ni, 0) - cc(oi, 0);
        const double dy = cc(ni, 1) - cc(oi, 1);
        const double dz = cc(ni, 2) - cc(oi, 2);
        const double dmag = norm3(dx, dy, dz);
        const double nmag = norm3(fn(i, 0), fn(i, 1), fn(i, 2));
        if (dmag <= 1e-30 || nmag <= 1e-30) {
            continue;
        }
        double cos_theta = std::abs(
            (dx * fn(i, 0) + dy * fn(i, 1) + dz * fn(i, 2)) / (dmag * nmag));
        if (cos_theta < 0.0) {
            cos_theta = 0.0;
        } else if (cos_theta > 1.0) {
            cos_theta = 1.0;
        }
        const double angle = std::acos(cos_theta) * 180.0 / pi;
        max_angle = std::max(max_angle, angle);
        sum_angle += angle;
        ++n_valid;
        if (angle > severe_threshold) {
            ++severe;
        }
    }

    if (n_valid == 0) {
        return py::make_tuple(0.0, 0.0, 0);
    }
    return py::make_tuple(max_angle, sum_angle / static_cast<double>(n_valid),
                          static_cast<int>(severe));
}

double compute_skewness(
    py::array_t<double, py::array::c_style | py::array::forcecast> face_centres,
    py::array_t<double, py::array::c_style | py::array::forcecast> cell_centres,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    py::array_t<long long, py::array::c_style | py::array::forcecast> neighbour,
    long long n_internal)
{
    if (n_internal <= 0) {
        return 0.0;
    }
    const auto fc = face_centres.unchecked<2>();
    const auto cc = cell_centres.unchecked<2>();
    const auto own = owner.unchecked<1>();
    const auto nbr = neighbour.unchecked<1>();
    const auto max_i = std::min<long long>(
        n_internal,
        std::min<long long>(own.shape(0), nbr.shape(0)));

    double max_skew = 0.0;
    for (long long i = 0; i < max_i; ++i) {
        const auto oi = own(i);
        const auto ni = nbr(i);
        if (oi < 0 || ni < 0 || oi >= cc.shape(0) || ni >= cc.shape(0)) {
            continue;
        }
        const double dx = cc(ni, 0) - cc(oi, 0);
        const double dy = cc(ni, 1) - cc(oi, 1);
        const double dz = cc(ni, 2) - cc(oi, 2);
        const double d2 = dx * dx + dy * dy + dz * dz;
        if (d2 <= 1e-60) {
            continue;
        }
        const double fx = fc(i, 0) - cc(oi, 0);
        const double fy = fc(i, 1) - cc(oi, 1);
        const double fz = fc(i, 2) - cc(oi, 2);
        const double t = (fx * dx + fy * dy + fz * dz) / d2;
        const double px = cc(oi, 0) + t * dx;
        const double py = cc(oi, 1) + t * dy;
        const double pz = cc(oi, 2) + t * dz;
        const double sx = fc(i, 0) - px;
        const double sy = fc(i, 1) - py;
        const double sz = fc(i, 2) - pz;
        const double skew = norm3(sx, sy, sz) / std::sqrt(d2);
        if (std::isfinite(skew)) {
            max_skew = std::max(max_skew, skew);
        }
    }
    return max_skew;
}

double compute_boundary_skewness(
    py::array_t<double, py::array::c_style | py::array::forcecast> face_centres,
    py::array_t<double, py::array::c_style | py::array::forcecast> face_normals,
    py::array_t<double, py::array::c_style | py::array::forcecast> cell_centres,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    long long n_internal)
{
    const auto fc = face_centres.unchecked<2>();
    const auto fn = face_normals.unchecked<2>();
    const auto cc = cell_centres.unchecked<2>();
    const auto own = owner.unchecked<1>();
    const auto n_faces = fc.shape(0);
    if (n_faces <= n_internal) {
        return 0.0;
    }

    double max_skew = 0.0;
    for (py::ssize_t i = static_cast<py::ssize_t>(n_internal); i < n_faces; ++i) {
        if (i >= own.shape(0)) {
            continue;
        }
        const auto oi = own(i);
        if (oi < 0 || oi >= cc.shape(0)) {
            continue;
        }
        const double nmag = norm3(fn(i, 0), fn(i, 1), fn(i, 2));
        if (nmag <= 1e-30) {
            continue;
        }
        const double nx = fn(i, 0) / nmag;
        const double ny = fn(i, 1) / nmag;
        const double nz = fn(i, 2) / nmag;
        const double tx = fc(i, 0) - cc(oi, 0);
        const double ty = fc(i, 1) - cc(oi, 1);
        const double tz = fc(i, 2) - cc(oi, 2);
        const double normal_dist = tx * nx + ty * ny + tz * nz;
        const double px = cc(oi, 0) + normal_dist * nx;
        const double py = cc(oi, 1) + normal_dist * ny;
        const double pz = cc(oi, 2) + normal_dist * nz;
        const double sx = fc(i, 0) - px;
        const double sy = fc(i, 1) - py;
        const double sz = fc(i, 2) - pz;
        const double denom = std::max(std::abs(normal_dist), 1e-30);
        const double skew = norm3(sx, sy, sz) / denom;
        if (std::isfinite(skew)) {
            max_skew = std::max(max_skew, skew);
        }
    }
    return max_skew;
}

py::tuple compute_face_weight_volume_ratio(
    py::array_t<double, py::array::c_style | py::array::forcecast> face_centres,
    py::array_t<double, py::array::c_style | py::array::forcecast> face_area_vectors,
    py::array_t<double, py::array::c_style | py::array::forcecast> cell_centres,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    py::array_t<long long, py::array::c_style | py::array::forcecast> neighbour,
    py::array_t<double, py::array::c_style | py::array::forcecast> cell_volumes,
    long long n_internal)
{
    if (n_internal <= 0 || cell_volumes.size() == 0) {
        return py::make_tuple(1.0, 1.0, 1.0, 1.0);
    }
    if (face_centres.ndim() != 2 || face_centres.shape(1) != 3
        || face_area_vectors.ndim() != 2 || face_area_vectors.shape(1) != 3
        || cell_centres.ndim() != 2 || cell_centres.shape(1) != 3
        || owner.ndim() != 1 || neighbour.ndim() != 1
        || cell_volumes.ndim() != 1) {
        throw std::invalid_argument(
            "face and cell centres/vectors must have shape (N, 3); "
            "owner, neighbour, and cell_volumes must be one-dimensional");
    }

    const auto own_count = std::min<long long>(n_internal, owner.shape(0));
    const auto nbr_count = std::min<long long>(n_internal, neighbour.shape(0));
    if (own_count != nbr_count) {
        throw std::invalid_argument(
            "owner and neighbour slices must have equal length");
    }
    if (face_centres.shape(0) < own_count
        || face_area_vectors.shape(0) < own_count) {
        throw std::invalid_argument(
            "face arrays must contain every internal owner/neighbour pair");
    }

    const auto fc = face_centres.unchecked<2>();
    const auto fa = face_area_vectors.unchecked<2>();
    const auto cc = cell_centres.unchecked<2>();
    const auto own = owner.unchecked<1>();
    const auto nbr = neighbour.unchecked<1>();
    const auto volumes = cell_volumes.unchecked<1>();

    bool has_valid_face = false;
    bool has_valid_weight = false;
    bool has_non_nan_weight = false;
    bool has_valid_volume = false;
    bool has_non_nan_ratio = false;
    double min_face_weight = std::numeric_limits<double>::infinity();
    double max_adjacent = -std::numeric_limits<double>::infinity();

    {
        py::gil_scoped_release release;
        for (long long i = 0; i < own_count; ++i) {
            const auto oi = own(i);
            const auto ni = nbr(i);
            if (oi < 0 || ni < 0 || oi >= cc.shape(0) || ni >= cc.shape(0)
                || oi >= volumes.shape(0) || ni >= volumes.shape(0)) {
                continue;
            }
            has_valid_face = true;

            const double own_dx = fc(i, 0) - cc(oi, 0);
            const double own_dy = fc(i, 1) - cc(oi, 1);
            const double own_dz = fc(i, 2) - cc(oi, 2);
            const double nbr_dx = cc(ni, 0) - fc(i, 0);
            const double nbr_dy = cc(ni, 1) - fc(i, 1);
            const double nbr_dz = cc(ni, 2) - fc(i, 2);
            const double d_own = std::abs(
                fa(i, 0) * own_dx + fa(i, 1) * own_dy + fa(i, 2) * own_dz);
            const double d_nei = std::abs(
                fa(i, 0) * nbr_dx + fa(i, 1) * nbr_dy + fa(i, 2) * nbr_dz);
            const double denom = d_own + d_nei;
            if (denom > 1e-300) {
                has_valid_weight = true;
                const double weight = std::min(d_own, d_nei) / denom;
                if (!std::isnan(weight)) {
                    has_non_nan_weight = true;
                    min_face_weight = std::min(min_face_weight, weight);
                }
            }

            const double vo = std::abs(volumes(oi));
            const double vn = std::abs(volumes(ni));
            if (vo > 1e-30 && vn > 1e-30) {
                has_valid_volume = true;
                const double ratio = std::max(vo, vn)
                    / std::max(std::min(vo, vn), 1e-30);
                if (!std::isnan(ratio)) {
                    has_non_nan_ratio = true;
                    max_adjacent = std::max(max_adjacent, ratio);
                }
            }
        }
    }

    if (!has_valid_face) {
        return py::make_tuple(1.0, 1.0, 1.0, 1.0);
    }
    if (!has_valid_weight) {
        min_face_weight = 1.0;
    } else if (!has_non_nan_weight) {
        min_face_weight = std::numeric_limits<double>::quiet_NaN();
    }
    if (!has_valid_volume) {
        const double infinity = std::numeric_limits<double>::infinity();
        return py::make_tuple(min_face_weight, 0.0, infinity, infinity);
    }
    if (!has_non_nan_ratio) {
        max_adjacent = std::numeric_limits<double>::quiet_NaN();
    }
    const double min_vol_ratio = std::isnan(max_adjacent)
        ? max_adjacent
        : 1.0 / std::max(max_adjacent, 1.0);
    const double max_growth = std::pow(max_adjacent, 1.0 / 3.0);
    return py::make_tuple(
        min_face_weight, min_vol_ratio, max_adjacent, max_growth);
}

py::tuple compute_cell_volumes(
    py::array_t<double, py::array::c_style | py::array::forcecast> face_centres,
    py::array_t<double, py::array::c_style | py::array::forcecast> face_normals,
    py::array_t<double, py::array::c_style | py::array::forcecast> face_areas,
    py::array_t<double, py::array::c_style | py::array::forcecast> cell_centres,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    py::array_t<long long, py::array::c_style | py::array::forcecast> neighbour,
    long long n_cells,
    long long n_internal)
{
    if (n_cells <= 0) {
        return py::make_tuple(
            py::array_t<double>(py::array::ShapeContainer{static_cast<py::ssize_t>(0)}),
            0);
    }

    const auto fc = face_centres.unchecked<2>();
    const auto fn = face_normals.unchecked<2>();
    const auto fa = face_areas.unchecked<1>();
    const auto cc = cell_centres.unchecked<2>();
    const auto own = owner.unchecked<1>();
    const auto nbr = neighbour.unchecked<1>();

    py::array_t<double> volumes(
        py::array::ShapeContainer{static_cast<py::ssize_t>(n_cells)});
    auto vol = volumes.mutable_unchecked<1>();
    for (long long i = 0; i < n_cells; ++i) {
        vol(i) = 0.0;
    }

    const auto n_faces = std::min<py::ssize_t>(fc.shape(0), own.shape(0));
    for (py::ssize_t i = 0; i < n_faces; ++i) {
        const auto oi = own(i);
        if (oi >= 0 && oi < n_cells && oi < cc.shape(0)) {
            const double avx = fn(i, 0) * fa(i);
            const double avy = fn(i, 1) * fa(i);
            const double avz = fn(i, 2) * fa(i);
            const double dx = fc(i, 0) - cc(oi, 0);
            const double dy = fc(i, 1) - cc(oi, 1);
            const double dz = fc(i, 2) - cc(oi, 2);
            vol(oi) += std::abs(avx * dx + avy * dy + avz * dz) / 3.0;
        }
    }

    const auto n_int_use = std::min<long long>(
        std::min<long long>(n_internal, n_faces),
        nbr.shape(0));
    for (long long i = 0; i < n_int_use; ++i) {
        const auto ni = nbr(i);
        if (ni >= 0 && ni < n_cells && ni < cc.shape(0)) {
            const double avx = fn(i, 0) * fa(i);
            const double avy = fn(i, 1) * fa(i);
            const double avz = fn(i, 2) * fa(i);
            const double dx = fc(i, 0) - cc(ni, 0);
            const double dy = fc(i, 1) - cc(ni, 1);
            const double dz = fc(i, 2) - cc(ni, 2);
            vol(ni) += std::abs(avx * dx + avy * dy + avz * dz) / 3.0;
        }
    }

    return py::make_tuple(volumes, 0);
}

py::tuple compute_oriented_cell_volume_audit(
    py::array_t<double, py::array::c_style | py::array::forcecast> face_centres,
    py::array_t<double, py::array::c_style | py::array::forcecast> face_normals,
    py::array_t<double, py::array::c_style | py::array::forcecast> face_areas,
    py::array_t<double, py::array::c_style | py::array::forcecast> cell_centres,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    py::array_t<long long, py::array::c_style | py::array::forcecast> neighbour,
    const long long n_cells,
    const long long n_internal)
{
    if (n_cells < 0 || n_internal < 0) {
        throw std::invalid_argument("cell and internal-face counts must be non-negative");
    }
    if (face_centres.ndim() != 2 || face_centres.shape(1) != 3
        || face_normals.ndim() != 2 || face_normals.shape(1) != 3
        || face_centres.shape(0) != face_normals.shape(0)
        || face_areas.ndim() != 1
        || face_areas.shape(0) != face_centres.shape(0)) {
        throw std::invalid_argument(
            "face centres/normals/areas must have shapes (F,3), (F,3), and (F,)");
    }
    if (cell_centres.ndim() != 2 || cell_centres.shape(1) != 3
        || cell_centres.shape(0) < n_cells) {
        throw std::invalid_argument("cell_centres must have shape (C,3) with C >= n_cells");
    }
    if (owner.ndim() != 1 || owner.shape(0) < face_centres.shape(0)) {
        throw std::invalid_argument("owner must contain one id per face");
    }
    if (neighbour.ndim() != 1 || neighbour.shape(0) < n_internal
        || n_internal > face_centres.shape(0)) {
        throw std::invalid_argument(
            "neighbour must contain at least n_internal ids");
    }

    const auto face_count = static_cast<size_t>(face_centres.shape(0));
    const double* const centre_data = face_centres.data();
    const double* const normal_data = face_normals.data();
    const double* const area_data = face_areas.data();
    const double* const cell_data = cell_centres.data();
    const long long* const owner_data = owner.data();
    const long long* const neighbour_data = neighbour.data();
    for (size_t face = 0U; face < face_count; ++face) {
        if (owner_data[face] < 0 || owner_data[face] >= n_cells) {
            throw std::invalid_argument("owner cell id is out of range");
        }
    }
    for (long long face = 0; face < n_internal; ++face) {
        if (neighbour_data[face] < 0 || neighbour_data[face] >= n_cells) {
            throw std::invalid_argument("neighbour cell id is out of range");
        }
    }

    py::array_t<double> signed_volumes(
        py::array::ShapeContainer{static_cast<py::ssize_t>(n_cells)});
    py::array_t<double> absolute_pyramid_sums(
        py::array::ShapeContainer{static_cast<py::ssize_t>(n_cells)});
    double* const signed_data = signed_volumes.mutable_data();
    double* const absolute_data = absolute_pyramid_sums.mutable_data();
    {
        py::gil_scoped_release release;
        std::fill_n(signed_data, static_cast<size_t>(n_cells), 0.0);
        std::fill_n(absolute_data, static_cast<size_t>(n_cells), 0.0);
        const auto contribution = [=](const size_t face, const long long cell) {
            const double* const face_centre = centre_data + face * 3U;
            const double* const normal = normal_data + face * 3U;
            const double* const cell_centre = cell_data
                + static_cast<size_t>(cell) * 3U;
            return area_data[face]
                * (normal[0] * (face_centre[0] - cell_centre[0])
                   + normal[1] * (face_centre[1] - cell_centre[1])
                   + normal[2] * (face_centre[2] - cell_centre[2]))
                / 3.0;
        };
        for (size_t face = 0U; face < face_count; ++face) {
            const long long cell = owner_data[face];
            const double value = contribution(face, cell);
            signed_data[cell] += value;
            absolute_data[cell] += std::abs(value);
        }
        for (long long face = 0; face < n_internal; ++face) {
            const long long cell = neighbour_data[face];
            const double value = -contribution(static_cast<size_t>(face), cell);
            signed_data[cell] += value;
            absolute_data[cell] += std::abs(value);
        }
    }
    return py::make_tuple(signed_volumes, absolute_pyramid_sums);
}

py::tuple compute_per_cell_aspect_ratios(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    py::sequence faces,
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    long long n_cells)
{
    const auto pts = points.unchecked<2>();
    const auto own = owner.unchecked<1>();
    if (pts.ndim() != 2 || pts.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }
    if (n_cells < 0) {
        throw std::invalid_argument("n_cells must be non-negative");
    }

    const auto n_faces = static_cast<py::ssize_t>(faces.size());
    if (own.shape(0) < n_faces) {
        throw std::invalid_argument("owner must contain one entry per face");
    }
    const auto n_points = static_cast<long long>(pts.shape(0));
    std::vector<std::vector<long long>> cell_vertices(
        static_cast<size_t>(n_cells));

    // Python objects are inspected once. Everything below this conversion can
    // operate on native storage without holding the GIL.
    for (py::ssize_t face_i = 0; face_i < n_faces; ++face_i) {
        const auto cell_i = own(face_i);
        if (cell_i < 0 || cell_i >= n_cells) {
            continue;
        }
        py::sequence face = faces[face_i].cast<py::sequence>();
        auto& vertices = cell_vertices[static_cast<size_t>(cell_i)];
        const auto n_vertices = static_cast<py::ssize_t>(face.size());
        for (py::ssize_t j = 0; j < n_vertices; ++j) {
            vertices.push_back(as_vertex_index(face[j], n_points));
        }
    }

    std::vector<long long> out_cells;
    std::vector<double> out_ratios;
    {
        py::gil_scoped_release release;

        for (auto& vertices : cell_vertices) {
            std::sort(vertices.begin(), vertices.end());
            vertices.erase(
                std::unique(vertices.begin(), vertices.end()), vertices.end());
        }

        constexpr long long sample_cap = 25'000;
        const long long step = n_cells > sample_cap
            ? std::max(1LL, n_cells / sample_cap)
            : 1LL;
        out_cells.reserve(static_cast<size_t>((n_cells + step - 1) / step));
        out_ratios.reserve(out_cells.capacity());

        for (long long cell_i = 0; cell_i < n_cells; cell_i += step) {
            const auto& vertices = cell_vertices[static_cast<size_t>(cell_i)];
            if (vertices.size() < 2) {
                continue;
            }

            double min_d2 = std::numeric_limits<double>::infinity();
            double max_d2 = 0.0;
            for (size_t i = 0; i + 1 < vertices.size(); ++i) {
                const auto vi = vertices[i];
                for (size_t j = i + 1; j < vertices.size(); ++j) {
                    const auto vj = vertices[j];
                    const double dx = pts(vi, 0) - pts(vj, 0);
                    const double dy = pts(vi, 1) - pts(vj, 1);
                    const double dz = pts(vi, 2) - pts(vj, 2);
                    const double d2 = dx * dx + dy * dy + dz * dz;
                    if (d2 > 1e-30) {
                        min_d2 = std::min(min_d2, d2);
                        max_d2 = std::max(max_d2, d2);
                    }
                }
            }

            if (!std::isfinite(min_d2)) {
                continue;
            }
            out_cells.push_back(cell_i);
            out_ratios.push_back(std::sqrt(max_d2 / min_d2));
        }
    }

    py::array_t<long long> cell_ids(
        py::array::ShapeContainer{static_cast<py::ssize_t>(out_cells.size())});
    py::array_t<double> ratios(
        py::array::ShapeContainer{static_cast<py::ssize_t>(out_ratios.size())});
    auto ids_out = cell_ids.mutable_unchecked<1>();
    auto ratios_out = ratios.mutable_unchecked<1>();
    for (size_t i = 0; i < out_cells.size(); ++i) {
        ids_out(static_cast<py::ssize_t>(i)) = out_cells[i];
        ratios_out(static_cast<py::ssize_t>(i)) = out_ratios[i];
    }
    return py::make_tuple(cell_ids, ratios);
}

long long count_faces_not_upper_triangular(
    py::array_t<long long, py::array::c_style | py::array::forcecast> owner,
    py::array_t<long long, py::array::c_style | py::array::forcecast> neighbour)
{
    if (owner.ndim() != 1 || neighbour.ndim() != 1) {
        throw std::invalid_argument("owner and neighbour must be one-dimensional");
    }

    const auto own = owner.unchecked<1>();
    const auto nbr = neighbour.unchecked<1>();
    const auto n = nbr.shape(0);
    if (n <= 1) {
        return 0;
    }
    if (own.shape(0) < n) {
        throw std::invalid_argument(
            "owner must contain at least len(neighbour) entries");
    }

    py::gil_scoped_release release;
    bool already_sorted = true;
    for (py::ssize_t i = 1; i < n; ++i) {
        if (own(i - 1) > own(i)
            || (own(i - 1) == own(i) && nbr(i - 1) > nbr(i))) {
            already_sorted = false;
            break;
        }
    }
    if (already_sorted) {
        return 0;
    }

    std::vector<py::ssize_t> order(static_cast<size_t>(n));
    std::iota(order.begin(), order.end(), py::ssize_t{0});
    std::stable_sort(
        order.begin(), order.end(),
        [&](py::ssize_t lhs, py::ssize_t rhs) {
            if (own(lhs) != own(rhs)) {
                return own(lhs) < own(rhs);
            }
            return nbr(lhs) < nbr(rhs);
        });

    long long displaced = 0;
    for (py::ssize_t i = 0; i < n; ++i) {
        displaced += order[static_cast<size_t>(i)] != i;
    }
    return displaced;
}

py::array_t<long long> copy_index_vector(const std::vector<long long>& values)
{
    py::array_t<long long> result(
        py::array::ShapeContainer{static_cast<py::ssize_t>(values.size())});
    auto out = result.mutable_unchecked<1>();
    for (size_t i = 0; i < values.size(); ++i) {
        out(static_cast<py::ssize_t>(i)) = values[i];
    }
    return result;
}

template <size_t Size>
struct FixedIndexHash {
    size_t operator()(const std::array<long long, Size>& values) const noexcept
    {
        size_t seed = Size;
        for (const long long value : values) {
            seed ^= std::hash<long long>{}(value) + 0x9e3779b97f4a7c15ULL
                + (seed << 6U) + (seed >> 2U);
        }
        return seed;
    }
};

struct TriangleEdgeIncidence {
    std::array<long long, 2> key;
    std::vector<long long> face_indices;
    std::vector<signed char> directions;
};

struct TriangleFlipEdgeRecord {
    long long first_face = -1;
    long long second_face = -1;
    long long count = 0;
};

struct CurvatureEdgeRecord {
    std::array<long long, 2> key;
    size_t face_index;
    size_t encounter_order;
};

struct CurvatureEdgeContribution {
    size_t encounter_order;
    long long first_vertex;
    long long second_vertex;
    double curvature;
};

[[nodiscard]] Point3 scale(const Point3& value, double factor) noexcept;
[[nodiscard]] double dot_product(
    const Point3& left, const Point3& right) noexcept;

py::array_t<double> triangle_quality_batch(const py::array& triangles_input)
{
    if (!triangles_input.dtype().is(py::dtype::of<double>())
        || (triangles_input.flags() & py::array::c_style) == 0
        || triangles_input.ndim() != 3 || triangles_input.shape(1) != 3
        || triangles_input.shape(2) != 3) {
        throw std::invalid_argument(
            "triangles must be a C-contiguous float64 array with shape (N, 3, 3)");
    }

    const auto triangles_array =
        py::reinterpret_borrow<py::array_t<double>>(triangles_input);
    const auto triangles = triangles_array.unchecked<3>();
    const auto triangle_count = triangles.shape(0);
    py::array_t<double> quality(py::array::ShapeContainer{triangle_count});
    auto output = quality.mutable_unchecked<1>();
    constexpr double normalization =
        2.0 * std::numbers::sqrt3_v<double>;

    for (py::ssize_t index = 0; index < triangle_count; ++index) {
        const double edge01_x = triangles(index, 1, 0) - triangles(index, 0, 0);
        const double edge01_y = triangles(index, 1, 1) - triangles(index, 0, 1);
        const double edge01_z = triangles(index, 1, 2) - triangles(index, 0, 2);
        const double edge12_x = triangles(index, 2, 0) - triangles(index, 1, 0);
        const double edge12_y = triangles(index, 2, 1) - triangles(index, 1, 1);
        const double edge12_z = triangles(index, 2, 2) - triangles(index, 1, 2);
        const double edge20_x = triangles(index, 0, 0) - triangles(index, 2, 0);
        const double edge20_y = triangles(index, 0, 1) - triangles(index, 2, 1);
        const double edge20_z = triangles(index, 0, 2) - triangles(index, 2, 2);
        const double denominator =
            edge01_x * edge01_x + edge01_y * edge01_y + edge01_z * edge01_z
            + edge12_x * edge12_x + edge12_y * edge12_y + edge12_z * edge12_z
            + edge20_x * edge20_x + edge20_y * edge20_y + edge20_z * edge20_z;
        const double cross_x = edge01_z * edge20_y - edge01_y * edge20_z;
        const double cross_y = edge01_x * edge20_z - edge01_z * edge20_x;
        const double cross_z = edge01_y * edge20_x - edge01_x * edge20_y;
        const double area_twice = std::sqrt(
            cross_x * cross_x + cross_y * cross_y + cross_z * cross_z);
        output(index) = denominator > 0.0 && std::isfinite(denominator)
                && std::isfinite(area_twice)
            ? normalization * area_twice / denominator
            : 0.0;
    }
    return quality;
}

[[nodiscard]] double triangle_mean_ratio(
    const py::detail::unchecked_reference<double, 2>& vertices,
    const std::array<long long, 3>& face) noexcept
{
    const long long i0 = face[0];
    const long long i1 = face[1];
    const long long i2 = face[2];
    const double edge01_x = vertices(i1, 0) - vertices(i0, 0);
    const double edge01_y = vertices(i1, 1) - vertices(i0, 1);
    const double edge01_z = vertices(i1, 2) - vertices(i0, 2);
    const double edge12_x = vertices(i2, 0) - vertices(i1, 0);
    const double edge12_y = vertices(i2, 1) - vertices(i1, 1);
    const double edge12_z = vertices(i2, 2) - vertices(i1, 2);
    const double edge20_x = vertices(i0, 0) - vertices(i2, 0);
    const double edge20_y = vertices(i0, 1) - vertices(i2, 1);
    const double edge20_z = vertices(i0, 2) - vertices(i2, 2);
    const double denominator =
        edge01_x * edge01_x + edge01_y * edge01_y + edge01_z * edge01_z
        + edge12_x * edge12_x + edge12_y * edge12_y + edge12_z * edge12_z
        + edge20_x * edge20_x + edge20_y * edge20_y + edge20_z * edge20_z;
    const double cross_x = edge01_z * edge20_y - edge01_y * edge20_z;
    const double cross_y = edge01_x * edge20_z - edge01_z * edge20_x;
    const double cross_z = edge01_y * edge20_x - edge01_x * edge20_y;
    const double area_twice = std::sqrt(
        cross_x * cross_x + cross_y * cross_y + cross_z * cross_z);
    constexpr double normalization = 2.0 * std::numbers::sqrt3_v<double>;
    return denominator > 0.0 && std::isfinite(denominator)
            && std::isfinite(area_twice)
        ? normalization * area_twice / denominator
        : 0.0;
}

py::array_t<bool> triangle_flip_candidate_mask(
    const py::array& vertices_input,
    const py::array& faces_input,
    const py::array& edges_input)
{
    if (!vertices_input.dtype().is(py::dtype::of<double>())
        || (vertices_input.flags() & py::array::c_style) == 0
        || vertices_input.ndim() != 2 || vertices_input.shape(1) != 3) {
        throw std::invalid_argument(
            "vertices must be a C-contiguous float64 array with shape (N, 3)");
    }
    if (!faces_input.dtype().is(py::dtype::of<long long>())
        || (faces_input.flags() & py::array::c_style) == 0
        || faces_input.ndim() != 2 || faces_input.shape(1) != 3) {
        throw std::invalid_argument(
            "faces must be a C-contiguous int64 array with shape (F, 3)");
    }
    if (!edges_input.dtype().is(py::dtype::of<long long>())
        || (edges_input.flags() & py::array::c_style) == 0
        || edges_input.ndim() != 2 || edges_input.shape(1) != 2) {
        throw std::invalid_argument(
            "edges must be a C-contiguous int64 array with shape (E, 2)");
    }

    const auto vertices_array =
        py::reinterpret_borrow<py::array_t<double>>(vertices_input);
    const auto faces_array =
        py::reinterpret_borrow<py::array_t<long long>>(faces_input);
    const auto edges_array =
        py::reinterpret_borrow<py::array_t<long long>>(edges_input);
    const auto vertices = vertices_array.unchecked<2>();
    const auto faces = faces_array.unchecked<2>();
    const auto edges = edges_array.unchecked<2>();
    const py::ssize_t vertex_count = vertices.shape(0);
    const py::ssize_t face_count = faces.shape(0);
    const py::ssize_t edge_count = edges.shape(0);

    py::array_t<bool> result(py::array::ShapeContainer{edge_count});
    auto accepted = result.mutable_unchecked<1>();
    std::fill_n(accepted.mutable_data(0), edge_count, false);

    using EdgeKey = std::array<long long, 2>;
    using FaceKey = std::array<long long, 3>;
    const auto edge_key = [](long long first, long long second) noexcept {
        return EdgeKey{std::min(first, second), std::max(first, second)};
    };
    const auto face_key = [](long long first, long long second, long long third) {
        FaceKey key{first, second, third};
        std::sort(key.begin(), key.end());
        return key;
    };

    py::gil_scoped_release release;

    for (py::ssize_t vertex = 0; vertex < vertex_count; ++vertex) {
        for (py::ssize_t axis = 0; axis < 3; ++axis) {
            if (!std::isfinite(vertices(vertex, axis))) {
                return result;
            }
        }
    }
    if (face_count == 0) {
        return result;
    }

    std::unordered_map<EdgeKey, TriangleFlipEdgeRecord, FixedIndexHash<2>> topology;
    topology.reserve(static_cast<size_t>(face_count) * 4U);
    std::unordered_set<FaceKey, FixedIndexHash<3>> unique_faces;
    unique_faces.reserve(static_cast<size_t>(face_count) * 2U);
    bool valid_state = true;
    for (py::ssize_t face_index = 0; face_index < face_count; ++face_index) {
        const long long a = faces(face_index, 0);
        const long long b = faces(face_index, 1);
        const long long c = faces(face_index, 2);
        if (a < 0 || b < 0 || c < 0 || a >= vertex_count || b >= vertex_count
            || c >= vertex_count || a == b || b == c || c == a
            || !unique_faces.insert(face_key(a, b, c)).second) {
            valid_state = false;
            break;
        }
        const std::array<EdgeKey, 3> local_edges{
            edge_key(a, b), edge_key(b, c), edge_key(c, a)};
        for (const EdgeKey& key : local_edges) {
            auto& record = topology[key];
            if (record.count == 0) {
                record.first_face = face_index;
            } else if (record.count == 1) {
                record.second_face = face_index;
            }
            ++record.count;
            if (record.count > 2) {
                valid_state = false;
                break;
            }
        }
        if (!valid_state) {
            break;
        }
    }
    if (!valid_state) {
        return result;
    }

    std::vector<long long> valence(static_cast<size_t>(vertex_count), 0);
    std::vector<long long> boundary_degree(static_cast<size_t>(vertex_count), 0);
    for (const auto& [key, record] : topology) {
        if (key[0] != key[1]) {
            ++valence[static_cast<size_t>(key[0])];
            ++valence[static_cast<size_t>(key[1])];
        }
        if (record.count == 1) {
            ++boundary_degree[static_cast<size_t>(key[0])];
            ++boundary_degree[static_cast<size_t>(key[1])];
        }
    }
    const auto deviation = [](long long vertex_valence, long long boundary_count) {
        if (vertex_valence == 0) {
            return 0LL;
        }
        const long long target = boundary_count > 0 ? 4LL : 6LL;
        return std::llabs(vertex_valence - target);
    };
    long long total_deviation = 0;
    for (py::ssize_t vertex = 0; vertex < vertex_count; ++vertex) {
        total_deviation += deviation(
            valence[static_cast<size_t>(vertex)],
            boundary_degree[static_cast<size_t>(vertex)]);
    }

    for (py::ssize_t candidate_index = 0; candidate_index < edge_count;
         ++candidate_index) {
        const long long a = edges(candidate_index, 0);
        const long long b = edges(candidate_index, 1);
        if (a < 0 || b < 0 || a >= vertex_count || b >= vertex_count || a == b) {
            continue;
        }
        const auto topology_it = topology.find(edge_key(a, b));
        if (topology_it == topology.end() || topology_it->second.count != 2) {
            continue;
        }
        const long long first_index = topology_it->second.first_face;
        const long long second_index = topology_it->second.second_face;

        long long x = -1;
        long long y = -1;
        long long c = -1;
        for (py::ssize_t offset = 0; offset < 3; ++offset) {
            const long long first = faces(first_index, offset);
            const long long second = faces(first_index, (offset + 1) % 3);
            if ((first == a && second == b) || (first == b && second == a)) {
                x = first;
                y = second;
                c = faces(first_index, (offset + 2) % 3);
                break;
            }
        }
        if (x < 0) {
            continue;
        }
        long long d = -1;
        for (py::ssize_t offset = 0; offset < 3; ++offset) {
            if (faces(second_index, offset) == y
                && faces(second_index, (offset + 1) % 3) == x) {
                d = faces(second_index, (offset + 2) % 3);
                break;
            }
        }
        if (d < 0 || c == d || c == x || c == y || d == x || d == y) {
            continue;
        }

        const std::array<long long, 3> first_face{
            faces(first_index, 0), faces(first_index, 1), faces(first_index, 2)};
        const std::array<long long, 3> second_face{
            faces(second_index, 0), faces(second_index, 1), faces(second_index, 2)};
        const std::array<long long, 3> new_first{c, x, d};
        const std::array<long long, 3> new_second{c, d, y};
        const double old_quality = std::min(
            triangle_mean_ratio(vertices, first_face),
            triangle_mean_ratio(vertices, second_face));
        const double new_quality = std::min(
            triangle_mean_ratio(vertices, new_first),
            triangle_mean_ratio(vertices, new_second));
        if (new_quality > old_quality + 1e-12) {
            accepted(candidate_index) = true;
            continue;
        }

        std::unordered_map<EdgeKey, long long, FixedIndexHash<2>> edge_deltas;
        edge_deltas.reserve(8);
        const auto add_face_delta = [&](const std::array<long long, 3>& face,
                                        const long long delta) {
            edge_deltas[edge_key(face[0], face[1])] += delta;
            edge_deltas[edge_key(face[1], face[2])] += delta;
            edge_deltas[edge_key(face[2], face[0])] += delta;
        };
        add_face_delta(first_face, -1);
        add_face_delta(second_face, -1);
        add_face_delta(new_first, 1);
        add_face_delta(new_second, 1);

        std::array<long long, 4> touched{x, y, c, d};
        std::array<long long, 4> new_valence{
            valence[static_cast<size_t>(x)], valence[static_cast<size_t>(y)],
            valence[static_cast<size_t>(c)], valence[static_cast<size_t>(d)]};
        std::array<long long, 4> new_boundary{
            boundary_degree[static_cast<size_t>(x)],
            boundary_degree[static_cast<size_t>(y)],
            boundary_degree[static_cast<size_t>(c)],
            boundary_degree[static_cast<size_t>(d)]};
        for (const auto& [key, delta] : edge_deltas) {
            const auto old_it = topology.find(key);
            const long long old_count =
                old_it == topology.end() ? 0LL : old_it->second.count;
            const long long new_count = old_count + delta;
            if (new_count < 0) {
                valid_state = false;
                break;
            }
            for (size_t local = 0; local < touched.size(); ++local) {
                if (touched[local] != key[0] && touched[local] != key[1]) {
                    continue;
                }
                if ((old_count > 0) != (new_count > 0)) {
                    new_valence[local] += new_count > 0 ? 1 : -1;
                }
                if (old_count == 1) {
                    --new_boundary[local];
                }
                if (new_count == 1) {
                    ++new_boundary[local];
                }
            }
        }
        if (!valid_state) {
            return result;
        }
        long long after_deviation = total_deviation;
        for (size_t local = 0; local < touched.size(); ++local) {
            after_deviation -= deviation(
                valence[static_cast<size_t>(touched[local])],
                boundary_degree[static_cast<size_t>(touched[local])]);
            after_deviation += deviation(new_valence[local], new_boundary[local]);
        }
        accepted(candidate_index) = after_deviation < total_deviation;
    }
    return result;
}

py::dict estimate_triangle_curvature_sizing(
    const py::array& vertices_input,
    const py::array& triangles_input,
    const double epsilon,
    const std::optional<double> minimum_length,
    const std::optional<double> maximum_length)
{
    if (!vertices_input.dtype().is(py::dtype::of<double>())
        || (vertices_input.flags() & py::array::c_style) == 0
        || vertices_input.ndim() != 2 || vertices_input.shape(1) != 3) {
        throw std::invalid_argument(
            "vertices must be a C-contiguous float64 array with shape (N, 3)");
    }
    if (!triangles_input.dtype().is(py::dtype::of<long long>())
        || (triangles_input.flags() & py::array::c_style) == 0
        || triangles_input.ndim() != 2 || triangles_input.shape(1) != 3) {
        throw std::invalid_argument(
            "faces must be a C-contiguous int64 array with shape (M, 3)");
    }
    if (!std::isfinite(epsilon) || epsilon <= 0.0) {
        throw std::invalid_argument("epsilon must be finite and positive");
    }

    const auto vertices_array =
        py::reinterpret_borrow<py::array_t<double>>(vertices_input);
    const auto triangles_array =
        py::reinterpret_borrow<py::array_t<long long>>(triangles_input);
    const auto vertices = vertices_array.unchecked<2>();
    const auto triangles = triangles_array.unchecked<2>();
    const size_t vertex_count = static_cast<size_t>(vertices.shape(0));
    const size_t face_count = static_cast<size_t>(triangles.shape(0));
    std::vector<double> lengths(vertex_count, 0.0);
    double reference = 0.0;
    double lower = 0.0;
    double upper = 0.0;

    {
        py::gil_scoped_release release;
        for (size_t vertex = 0; vertex < vertex_count; ++vertex) {
            for (size_t axis = 0; axis < 3; ++axis) {
                if (!std::isfinite(vertices(
                        static_cast<py::ssize_t>(vertex),
                        static_cast<py::ssize_t>(axis)))) {
                    throw std::invalid_argument(
                        "vertices must be a finite (n, 3) array");
                }
            }
        }
        for (size_t face = 0; face < face_count; ++face) {
            for (size_t local = 0; local < 3; ++local) {
                const long long vertex = triangles(
                    static_cast<py::ssize_t>(face),
                    static_cast<py::ssize_t>(local));
                if (vertex < 0 || vertex >= static_cast<long long>(vertex_count)) {
                    throw std::invalid_argument(
                        "faces contain an invalid vertex index");
                }
            }
        }

        std::vector<Point3> face_normals(face_count, Point3{0.0, 0.0, 0.0});
        std::vector<double> face_areas(face_count, 0.0);
        std::vector<CurvatureEdgeRecord> edge_records;
        edge_records.reserve(face_count * 3U);
        constexpr std::array<std::array<size_t, 2>, 3> local_edges{{
            {{0, 1}}, {{1, 2}}, {{2, 0}},
        }};
        for (size_t face = 0; face < face_count; ++face) {
            std::array<long long, 3> triangle{
                triangles(static_cast<py::ssize_t>(face), 0),
                triangles(static_cast<py::ssize_t>(face), 1),
                triangles(static_cast<py::ssize_t>(face), 2),
            };
            const auto point = [&](const size_t local) {
                const auto vertex = static_cast<py::ssize_t>(triangle[local]);
                return Point3{
                    vertices(vertex, 0), vertices(vertex, 1), vertices(vertex, 2)};
            };
            const Point3 first = point(0);
            const Point3 second = point(1);
            const Point3 third = point(2);
            const Point3 normal = cross(sub(second, first), sub(third, first));
            const double twice_area = norm3(normal);
            if (twice_area > std::numeric_limits<double>::min()
                && std::isfinite(twice_area)) {
                face_normals[face] = scale(normal, 1.0 / twice_area);
                face_areas[face] = 0.5 * twice_area;
            }
            for (size_t local = 0; local < local_edges.size(); ++local) {
                std::array<long long, 2> key{
                    triangle[local_edges[local][0]],
                    triangle[local_edges[local][1]],
                };
                if (key[1] < key[0]) {
                    std::swap(key[0], key[1]);
                }
                edge_records.push_back(CurvatureEdgeRecord{
                    key, face, face * 3U + local});
            }
        }

        std::sort(
            edge_records.begin(), edge_records.end(),
            [](const CurvatureEdgeRecord& left, const CurvatureEdgeRecord& right) {
                if (left.key != right.key) {
                    return left.key < right.key;
                }
                if (left.face_index != right.face_index) {
                    return left.face_index < right.face_index;
                }
                return left.encounter_order < right.encounter_order;
            });

        std::vector<double> positive_edge_lengths;
        positive_edge_lengths.reserve(edge_records.size() / 2U + 1U);
        std::vector<CurvatureEdgeContribution> contributions;
        contributions.reserve(edge_records.size() / 2U + 1U);
        for (size_t begin = 0; begin < edge_records.size();) {
            size_t end = begin + 1U;
            while (end < edge_records.size()
                   && edge_records[end].key == edge_records[begin].key) {
                ++end;
            }
            const long long first_vertex = edge_records[begin].key[0];
            const long long second_vertex = edge_records[begin].key[1];
            const Point3 edge_vector = sub(
                Point3{
                    vertices(static_cast<py::ssize_t>(second_vertex), 0),
                    vertices(static_cast<py::ssize_t>(second_vertex), 1),
                    vertices(static_cast<py::ssize_t>(second_vertex), 2)},
                Point3{
                    vertices(static_cast<py::ssize_t>(first_vertex), 0),
                    vertices(static_cast<py::ssize_t>(first_vertex), 1),
                    vertices(static_cast<py::ssize_t>(first_vertex), 2)});
            const double edge_length = norm3(edge_vector);
            if (std::isfinite(edge_length) && edge_length > 0.0) {
                positive_edge_lengths.push_back(edge_length);
                double turning = 0.0;
                if (end - begin >= 2U) {
                    for (size_t left = begin; left + 1U < end; ++left) {
                        for (size_t right = left + 1U; right < end; ++right) {
                            const double cosine = std::clamp(
                                dot_product(
                                    face_normals[edge_records[left].face_index],
                                    face_normals[edge_records[right].face_index]),
                                -1.0, 1.0);
                            turning = std::max(turning, std::acos(cosine));
                        }
                    }
                }
                contributions.push_back(CurvatureEdgeContribution{
                    edge_records[begin].encounter_order,
                    first_vertex,
                    second_vertex,
                    edge_length * turning});
            }
            begin = end;
        }
        if (positive_edge_lengths.empty()) {
            throw std::invalid_argument("mesh has no positive-length edge");
        }
        std::sort(positive_edge_lengths.begin(), positive_edge_lengths.end());
        const size_t middle = positive_edge_lengths.size() / 2U;
        reference = positive_edge_lengths[middle];
        if (positive_edge_lengths.size() % 2U == 0U) {
            reference = (
                positive_edge_lengths[middle - 1U]
                + positive_edge_lengths[middle]) / 2.0;
        }
        lower = minimum_length.value_or(reference * 0.25);
        upper = maximum_length.value_or(reference * 2.0);
        if (!std::isfinite(lower) || !std::isfinite(upper)
            || (lower > 0.0 && lower > upper)) {
            throw std::invalid_argument(
                "min_length/max_length must be finite and ordered");
        }
        if (lower <= 0.0 || upper <= 0.0) {
            throw std::invalid_argument(
                "min_length/max_length must be positive");
        }
        upper = std::max(lower, upper);

        std::sort(
            contributions.begin(), contributions.end(),
            [](const CurvatureEdgeContribution& left,
               const CurvatureEdgeContribution& right) {
                return left.encounter_order < right.encounter_order;
            });
        std::vector<double> curvature(vertex_count, 0.0);
        for (const auto& contribution : contributions) {
            curvature[static_cast<size_t>(contribution.first_vertex)]
                += contribution.curvature;
            curvature[static_cast<size_t>(contribution.second_vertex)]
                += contribution.curvature;
        }
        std::vector<double> vertex_area(vertex_count, 0.0);
        for (size_t face = 0; face < face_count; ++face) {
            const double share = face_areas[face] / 3.0;
            for (size_t local = 0; local < 3; ++local) {
                const auto vertex = static_cast<size_t>(triangles(
                    static_cast<py::ssize_t>(face),
                    static_cast<py::ssize_t>(local)));
                vertex_area[vertex] += share;
            }
        }
        for (size_t vertex = 0; vertex < vertex_count; ++vertex) {
            const bool valid_area =
                vertex_area[vertex] > std::numeric_limits<double>::min();
            if (valid_area) {
                curvature[vertex] /= 4.0 * vertex_area[vertex];
            }
            double target = upper;
            if (valid_area && std::isfinite(curvature[vertex])
                && curvature[vertex] > 1e-14) {
                const double radicand =
                    6.0 * epsilon / curvature[vertex]
                    - 3.0 * epsilon * epsilon;
                if (radicand > 0.0 && std::isfinite(radicand)) {
                    target = std::sqrt(radicand);
                }
            }
            lengths[vertex] = std::clamp(target, lower, upper);
        }
    }

    py::array_t<double> lengths_array(
        py::array::ShapeContainer{static_cast<py::ssize_t>(lengths.size())});
    auto lengths_out = lengths_array.mutable_unchecked<1>();
    for (size_t vertex = 0; vertex < lengths.size(); ++vertex) {
        lengths_out(static_cast<py::ssize_t>(vertex)) = lengths[vertex];
    }
    py::dict result;
    result["lengths"] = std::move(lengths_array);
    result["reference_length"] = reference;
    result["minimum_length"] = lower;
    result["maximum_length"] = upper;
    return result;
}

py::dict validate_triangle_surface_and_build_edge_faces(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& vertices_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& triangles_array)
{
    if (vertices_array.ndim() != 2 || vertices_array.shape(1) != 3) {
        throw std::invalid_argument("vertices must have shape (N, 3)");
    }
    if (triangles_array.ndim() != 2 || triangles_array.shape(1) != 3) {
        throw std::invalid_argument("triangles must have shape (M, 3)");
    }

    const auto vertices = vertices_array.unchecked<2>();
    const auto triangles = triangles_array.unchecked<2>();
    const size_t vertex_count = static_cast<size_t>(vertices.shape(0));
    const size_t face_count = static_cast<size_t>(triangles.shape(0));
    std::vector<TriangleEdgeIncidence> edge_buckets;
    edge_buckets.reserve(face_count * 3U / 2U + 1U);
    std::unordered_map<
        std::array<long long, 2>, size_t, FixedIndexHash<2>> edge_indices;
    edge_indices.reserve(face_count * 3U / 2U + 1U);
    std::unordered_set<std::array<long long, 3>, FixedIndexHash<3>> unique_faces;
    unique_faces.reserve(face_count);
    std::vector<std::vector<std::array<long long, 2>>> vertex_link_edges(vertex_count);
    constexpr std::array<std::array<size_t, 2>, 3> local_edges{{
        {{0, 1}}, {{1, 2}}, {{2, 0}},
    }};

    {
        py::gil_scoped_release release;

        for (size_t vertex = 0; vertex < vertex_count; ++vertex) {
            for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
                if (!std::isfinite(vertices(
                        static_cast<py::ssize_t>(vertex),
                        static_cast<py::ssize_t>(coordinate)))) {
                    throw std::invalid_argument("surface contains non-finite vertices");
                }
            }
        }
        for (size_t face = 0; face < face_count; ++face) {
            for (size_t local = 0; local < 3; ++local) {
                const long long vertex = triangles(
                    static_cast<py::ssize_t>(face),
                    static_cast<py::ssize_t>(local));
                if (vertex < 0 || vertex >= static_cast<long long>(vertex_count)) {
                    throw std::invalid_argument(
                        "triangle indices are outside the input vertex range");
                }
            }
        }

        for (size_t face_index = 0; face_index < face_count; ++face_index) {
            std::array<long long, 3> triangle{
                triangles(static_cast<py::ssize_t>(face_index), 0),
                triangles(static_cast<py::ssize_t>(face_index), 1),
                triangles(static_cast<py::ssize_t>(face_index), 2),
            };
            std::array<long long, 3> face_key = triangle;
            std::sort(face_key.begin(), face_key.end());
            if (std::adjacent_find(face_key.begin(), face_key.end())
                != face_key.end()) {
                throw std::invalid_argument("surface contains a degenerate triangle");
            }
            if (!unique_faces.insert(face_key).second) {
                throw std::invalid_argument("surface contains a duplicate triangle");
            }

            const auto coordinate = [&](const size_t local, const size_t axis) {
                return vertices(
                    static_cast<py::ssize_t>(triangle[local]),
                    static_cast<py::ssize_t>(axis));
            };
            const double ax = coordinate(1, 0) - coordinate(0, 0);
            const double ay = coordinate(1, 1) - coordinate(0, 1);
            const double az = coordinate(1, 2) - coordinate(0, 2);
            const double bx = coordinate(2, 0) - coordinate(0, 0);
            const double by = coordinate(2, 1) - coordinate(0, 1);
            const double bz = coordinate(2, 2) - coordinate(0, 2);
            const double cx = ay * bz - az * by;
            const double cy = az * bx - ax * bz;
            const double cz = ax * by - ay * bx;
            if (std::sqrt(cx * cx + cy * cy + cz * cz) <= 1e-30) {
                throw std::invalid_argument("surface contains a zero-area triangle");
            }

            for (const auto& local_edge : local_edges) {
                const long long start = triangle[local_edge[0]];
                const long long end = triangle[local_edge[1]];
                std::array<long long, 2> key{start, end};
                signed char direction = 1;
                if (key[1] < key[0]) {
                    std::swap(key[0], key[1]);
                    direction = -1;
                }
                const auto [position, inserted] = edge_indices.emplace(
                    key, edge_buckets.size());
                if (inserted) {
                    edge_buckets.push_back(TriangleEdgeIncidence{key, {}, {}});
                }
                auto& bucket = edge_buckets[position->second];
                bucket.face_indices.push_back(static_cast<long long>(face_index));
                bucket.directions.push_back(direction);
            }

            vertex_link_edges[static_cast<size_t>(triangle[0])].push_back(
                {triangle[1], triangle[2]});
            vertex_link_edges[static_cast<size_t>(triangle[1])].push_back(
                {triangle[2], triangle[0]});
            vertex_link_edges[static_cast<size_t>(triangle[2])].push_back(
                {triangle[0], triangle[1]});
        }

        for (const auto& bucket : edge_buckets) {
            if (bucket.directions.size() > 2) {
                throw std::invalid_argument(
                    "surface contains non-manifold edge ("
                    + std::to_string(bucket.key[0]) + ", "
                    + std::to_string(bucket.key[1]) + ")");
            }
            if (bucket.directions.size() == 2
                && bucket.directions[0] == bucket.directions[1]) {
                throw std::invalid_argument(
                    "surface contains inconsistent orientation at edge ("
                    + std::to_string(bucket.key[0]) + ", "
                    + std::to_string(bucket.key[1]) + ")");
            }
        }

        for (size_t vertex = 0; vertex < vertex_count; ++vertex) {
            const auto& link_edges = vertex_link_edges[vertex];
            if (link_edges.empty()) {
                continue;
            }
            std::unordered_map<long long, std::vector<long long>> adjacency;
            adjacency.reserve(link_edges.size() * 2U);
            for (const auto& edge : link_edges) {
                adjacency[edge[0]].push_back(edge[1]);
                adjacency[edge[1]].push_back(edge[0]);
            }
            std::vector<long long> pending{adjacency.begin()->first};
            std::unordered_set<long long> visited;
            visited.reserve(adjacency.size());
            while (!pending.empty()) {
                const long long neighbour = pending.back();
                pending.pop_back();
                if (!visited.insert(neighbour).second) {
                    continue;
                }
                const auto position = adjacency.find(neighbour);
                if (position != adjacency.end()) {
                    pending.insert(
                        pending.end(), position->second.begin(), position->second.end());
                }
            }
            if (visited.size() != adjacency.size()) {
                throw std::invalid_argument(
                    "surface contains non-manifold vertex "
                    + std::to_string(vertex));
            }
        }
    }

    py::dict result;
    for (auto& bucket : edge_buckets) {
        result[py::make_tuple(bucket.key[0], bucket.key[1])] =
            py::cast(std::move(bucket.face_indices));
    }
    return result;
}

struct TriangleTopologyAuditEdge {
    long long first;
    long long second;
    long long face;
    signed char direction;
};

[[nodiscard]] bool triangle_topology_audit_edge_less(
    const TriangleTopologyAuditEdge& left,
    const TriangleTopologyAuditEdge& right) noexcept
{
    if (left.first != right.first) {
        return left.first < right.first;
    }
    if (left.second != right.second) {
        return left.second < right.second;
    }
    return left.face < right.face;
}

[[nodiscard]] size_t triangle_topology_audit_find(
    std::vector<size_t>& parents,
    size_t index) noexcept
{
    size_t root = index;
    while (parents[root] != root) {
        root = parents[root];
    }
    while (parents[index] != index) {
        const size_t next = parents[index];
        parents[index] = root;
        index = next;
    }
    return root;
}

void triangle_topology_audit_union(
    std::vector<size_t>& parents,
    const size_t first,
    const size_t second) noexcept
{
    const size_t first_root = triangle_topology_audit_find(parents, first);
    const size_t second_root = triangle_topology_audit_find(parents, second);
    if (first_root != second_root) {
        parents[second_root] = first_root;
    }
}

py::dict triangle_surface_topology_audit(
    const py::array& vertices_input,
    const py::array& faces_input)
{
    if (!vertices_input.dtype().is(py::dtype::of<double>())
        || (vertices_input.flags() & py::array::c_style) == 0
        || vertices_input.ndim() != 2 || vertices_input.shape(1) != 3) {
        throw std::invalid_argument(
            "vertices must be a C-contiguous float64 array with shape (N, 3)");
    }
    if (!faces_input.dtype().is(py::dtype::of<long long>())
        || (faces_input.flags() & py::array::c_style) == 0
        || faces_input.ndim() != 2 || faces_input.shape(1) != 3) {
        throw std::invalid_argument(
            "faces must be a C-contiguous int64 array with shape (F, 3)");
    }

    const auto vertices_array =
        py::reinterpret_borrow<py::array_t<double>>(vertices_input);
    const auto faces_array =
        py::reinterpret_borrow<py::array_t<long long>>(faces_input);
    const auto vertices = vertices_array.unchecked<2>();
    const auto faces = faces_array.unchecked<2>();
    const size_t vertex_count = static_cast<size_t>(vertices.shape(0));
    const size_t face_count = static_cast<size_t>(faces.shape(0));

    const auto invalid = [] {
        py::dict result;
        result["valid"] = false;
        result["closed_oriented_manifold"] = false;
        result["edge_count"] = 0;
        result["component_count"] = 0;
        result["euler_characteristic"] = py::none();
        return result;
    };
    if (face_count == 0U) {
        return invalid();
    }

    std::vector<TriangleTopologyAuditEdge> edges;
    edges.reserve(face_count * 3U);
    std::vector<size_t> parents(face_count);
    std::iota(parents.begin(), parents.end(), 0U);
    bool valid = true;
    bool closed_oriented = false;
    size_t edge_count = 0U;
    size_t component_count = 0U;
    {
        py::gil_scoped_release release;
        for (size_t vertex = 0; vertex < vertex_count && valid; ++vertex) {
            for (size_t axis = 0; axis < 3U; ++axis) {
                if (!std::isfinite(vertices(
                        static_cast<py::ssize_t>(vertex),
                        static_cast<py::ssize_t>(axis)))) {
                    valid = false;
                    break;
                }
            }
        }
        for (size_t face = 0; face < face_count && valid; ++face) {
            const long long a = faces(static_cast<py::ssize_t>(face), 0);
            const long long b = faces(static_cast<py::ssize_t>(face), 1);
            const long long c = faces(static_cast<py::ssize_t>(face), 2);
            if (a < 0 || b < 0 || c < 0 || a >= static_cast<long long>(vertex_count)
                || b >= static_cast<long long>(vertex_count)
                || c >= static_cast<long long>(vertex_count)) {
                valid = false;
                break;
            }
            const auto coordinate = [&](const long long index, const size_t axis) {
                return vertices(index, static_cast<py::ssize_t>(axis));
            };
            const double ab_x = coordinate(b, 0U) - coordinate(a, 0U);
            const double ab_y = coordinate(b, 1U) - coordinate(a, 1U);
            const double ab_z = coordinate(b, 2U) - coordinate(a, 2U);
            const double ac_x = coordinate(c, 0U) - coordinate(a, 0U);
            const double ac_y = coordinate(c, 1U) - coordinate(a, 1U);
            const double ac_z = coordinate(c, 2U) - coordinate(a, 2U);
            const double cross_x = ab_y * ac_z - ab_z * ac_y;
            const double cross_y = ab_z * ac_x - ab_x * ac_z;
            const double cross_z = ab_x * ac_y - ab_y * ac_x;
            const double twice_area = std::sqrt(
                cross_x * cross_x + cross_y * cross_y + cross_z * cross_z);
            if (!std::isfinite(twice_area)
                || twice_area <= std::numeric_limits<double>::min()) {
                valid = false;
                break;
            }
            const std::array<std::array<long long, 2>, 3> local_edges{{
                {{a, b}}, {{b, c}}, {{c, a}},
            }};
            for (const auto& edge : local_edges) {
                const long long first = std::min(edge[0], edge[1]);
                const long long second = std::max(edge[0], edge[1]);
                edges.push_back(TriangleTopologyAuditEdge{
                    first,
                    second,
                    static_cast<long long>(face),
                    static_cast<signed char>((edge[0] == first && edge[1] == second) ? 1 : -1),
                });
            }
        }
        if (valid) {
            std::sort(edges.begin(), edges.end(), triangle_topology_audit_edge_less);
            closed_oriented = true;
            for (size_t first = 0U; first < edges.size();) {
                size_t last = first + 1U;
                while (last < edges.size() && edges[last].first == edges[first].first
                       && edges[last].second == edges[first].second) {
                    ++last;
                }
                ++edge_count;
                if (last - first != 2U
                    || edges[first].direction == edges[first + 1U].direction) {
                    closed_oriented = false;
                }
                if (last - first == 2U) {
                    triangle_topology_audit_union(
                        parents,
                        static_cast<size_t>(edges[first].face),
                        static_cast<size_t>(edges[first + 1U].face));
                }
                first = last;
            }
            for (size_t face = 0U; face < face_count; ++face) {
                if (triangle_topology_audit_find(parents, face) == face) {
                    ++component_count;
                }
            }
        }
    }
    if (!valid) {
        return invalid();
    }
    py::dict result;
    result["valid"] = true;
    result["closed_oriented_manifold"] = closed_oriented;
    result["edge_count"] = edge_count;
    result["component_count"] = component_count;
    result["euler_characteristic"] = static_cast<long long>(vertex_count)
        - static_cast<long long>(edge_count) + static_cast<long long>(face_count);
    return result;
}

struct QuadPreparationEdge {
    std::array<long long, 2> key;
    long long face;
    signed char direction;
    size_t encounter_order;
};

struct QuadPreparationLink {
    long long centre;
    std::array<long long, 2> edge;
};

struct QuadPreparationPair {
    std::array<long long, 2> faces;
    size_t encounter_order;
};

template <size_t Size>
[[nodiscard]] std::optional<std::array<Point3, Size>>
similarity_normalized_points(
    const std::array<Point3, Size>& points) noexcept
{
    double coordinate_magnitude = 0.0;
    for (const Point3& point : points) {
        for (const double coordinate : point) {
            coordinate_magnitude = std::max(
                coordinate_magnitude, std::abs(coordinate));
        }
    }
    if (!std::isfinite(coordinate_magnitude)
        || coordinate_magnitude == 0.0) {
        return std::nullopt;
    }
    int coordinate_exponent = 0;
    static_cast<void>(std::frexp(
        coordinate_magnitude, &coordinate_exponent));

    std::array<Point3, Size> relative{};
    Point3 origin{};
    for (size_t coordinate = 0; coordinate < origin.size(); ++coordinate) {
        origin[coordinate] = std::scalbn(
            points[0][coordinate], -coordinate_exponent);
    }
    double local_magnitude = 0.0;
    for (size_t point = 0; point < points.size(); ++point) {
        for (size_t coordinate = 0; coordinate < origin.size(); ++coordinate) {
            relative[point][coordinate] = std::scalbn(
                points[point][coordinate], -coordinate_exponent)
                - origin[coordinate];
            local_magnitude = std::max(
                local_magnitude, std::abs(relative[point][coordinate]));
        }
    }
    if (!std::isfinite(local_magnitude) || local_magnitude == 0.0) {
        return std::nullopt;
    }
    int local_exponent = 0;
    static_cast<void>(std::frexp(local_magnitude, &local_exponent));
    for (Point3& point : relative) {
        for (double& coordinate : point) {
            coordinate = std::scalbn(coordinate, -local_exponent);
        }
    }
    return relative;
}

[[nodiscard]] bool quad_preparation_edge_less(
    const QuadPreparationEdge& left,
    const QuadPreparationEdge& right) noexcept
{
    if (left.key != right.key) {
        return left.key < right.key;
    }
    return left.encounter_order < right.encounter_order;
}

[[nodiscard]] bool quad_preparation_link_less(
    const QuadPreparationLink& left,
    const QuadPreparationLink& right) noexcept
{
    if (left.centre != right.centre) {
        return left.centre < right.centre;
    }
    return left.edge < right.edge;
}

[[nodiscard]] bool canonical_face_less(
    const std::array<long long, 3>& left,
    const std::array<long long, 3>& right) noexcept
{
    return left < right;
}

[[nodiscard]] size_t disjoint_find(
    std::vector<size_t>& parent, size_t index) noexcept
{
    size_t root = index;
    while (parent[root] != root) {
        root = parent[root];
    }
    while (parent[index] != index) {
        const size_t next = parent[index];
        parent[index] = root;
        index = next;
    }
    return root;
}

void disjoint_union(
    std::vector<size_t>& parent, size_t first, size_t second) noexcept
{
    first = disjoint_find(parent, first);
    second = disjoint_find(parent, second);
    if (first != second) {
        parent[second] = first;
    }
}

py::tuple prepare_quad_pairs(
    const py::array_t<double, py::array::c_style>& vertices_array,
    const py::array_t<long long, py::array::c_style>& triangles_array,
    const py::array_t<long long, py::array::c_style>& wall_edges_array,
    const double feature_angle_deg)
{
    if (vertices_array.ndim() != 2 || vertices_array.shape(1) != 3) {
        throw std::invalid_argument(
            "vertices must be a C-contiguous float64 array with shape (N, 3)");
    }
    if (triangles_array.ndim() != 2 || triangles_array.shape(1) != 3) {
        throw std::invalid_argument(
            "triangles must be a C-contiguous int64 array with shape (M, 3)");
    }
    if (wall_edges_array.ndim() != 2 || wall_edges_array.shape(1) != 2) {
        throw std::invalid_argument(
            "wall_edges must be a C-contiguous int64 array with shape (K, 2)");
    }
    if (!std::isfinite(feature_angle_deg)
        || feature_angle_deg <= 0.0 || feature_angle_deg >= 180.0) {
        throw std::invalid_argument(
            "feature_angle_deg must be finite and in (0, 180)");
    }

    const auto vertices = vertices_array.unchecked<2>();
    const auto triangles = triangles_array.unchecked<2>();
    const auto wall_edges = wall_edges_array.unchecked<2>();
    const size_t vertex_count = static_cast<size_t>(vertices.shape(0));
    const size_t face_count = static_cast<size_t>(triangles.shape(0));
    const size_t wall_edge_count = static_cast<size_t>(wall_edges.shape(0));
    if (vertex_count > static_cast<size_t>(std::numeric_limits<long long>::max())
        || face_count > static_cast<size_t>(std::numeric_limits<long long>::max())
        || face_count > std::numeric_limits<size_t>::max() / 3U) {
        throw std::invalid_argument("surface is too large for signed int64 topology");
    }
    std::vector<QuadPreparationEdge> edges;
    edges.reserve(face_count * 3U);
    std::vector<QuadPreparationLink> links;
    links.reserve(face_count * 3U);
    std::vector<std::array<long long, 3>> canonical_faces;
    canonical_faces.reserve(face_count);
    std::vector<Point3> normals(face_count);
    std::vector<std::array<long long, 2>> canonical_walls;
    canonical_walls.reserve(wall_edge_count);
    std::vector<QuadPreparationPair> face_pairs;
    long long boundary_count = 0;
    long long feature_count = 0;
    long long candidate_count = 0;
    long long rejected_protected = 0;

    {
        py::gil_scoped_release release;
        for (size_t vertex = 0; vertex < vertex_count; ++vertex) {
            for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
                if (!std::isfinite(vertices(
                        static_cast<py::ssize_t>(vertex),
                        static_cast<py::ssize_t>(coordinate)))) {
                    throw std::invalid_argument("surface contains non-finite vertices");
                }
            }
        }

        constexpr std::array<std::array<size_t, 2>, 3> local_edges{{
            {{0, 1}}, {{1, 2}}, {{2, 0}},
        }};
        for (size_t face = 0; face < face_count; ++face) {
            std::array<long long, 3> triangle{};
            for (size_t local = 0; local < triangle.size(); ++local) {
                const long long vertex = triangles(
                    static_cast<py::ssize_t>(face),
                    static_cast<py::ssize_t>(local));
                if (vertex < 0 || vertex >= static_cast<long long>(vertex_count)) {
                    throw std::invalid_argument(
                        "triangle indices are outside the input vertex range");
                }
                triangle[local] = vertex;
            }
            std::array<long long, 3> face_key = triangle;
            std::sort(face_key.begin(), face_key.end());
            if (std::adjacent_find(face_key.begin(), face_key.end())
                != face_key.end()) {
                throw std::invalid_argument("surface contains a degenerate triangle");
            }
            canonical_faces.push_back(face_key);

            const auto point = [&](const size_t local) -> Point3 {
                const auto vertex = static_cast<py::ssize_t>(triangle[local]);
                return {vertices(vertex, 0), vertices(vertex, 1), vertices(vertex, 2)};
            };
            const std::array<Point3, 3> face_points{
                point(0), point(1), point(2)};
            const auto normalized = similarity_normalized_points(face_points);
            if (!normalized.has_value()) {
                throw std::invalid_argument("surface contains a zero-area triangle");
            }
            const Point3 normal = cross((*normalized)[1], (*normalized)[2]);
            const double normal_length = norm3(normal);
            if (normal_length <= 1e-30) {
                throw std::invalid_argument("surface contains a zero-area triangle");
            }
            normals[face] = {
                normal[0] / normal_length,
                normal[1] / normal_length,
                normal[2] / normal_length,
            };

            for (size_t local = 0; local < local_edges.size(); ++local) {
                long long start = triangle[local_edges[local][0]];
                long long end = triangle[local_edges[local][1]];
                signed char direction = 1;
                if (end < start) {
                    std::swap(start, end);
                    direction = -1;
                }
                edges.push_back(QuadPreparationEdge{
                    {start, end}, static_cast<long long>(face), direction,
                    face * 3U + local});
            }
            links.push_back(QuadPreparationLink{
                triangle[0], {triangle[1], triangle[2]}});
            links.push_back(QuadPreparationLink{
                triangle[1], {triangle[2], triangle[0]}});
            links.push_back(QuadPreparationLink{
                triangle[2], {triangle[0], triangle[1]}});
        }

        std::sort(canonical_faces.begin(), canonical_faces.end(), canonical_face_less);
        if (std::adjacent_find(canonical_faces.begin(), canonical_faces.end())
            != canonical_faces.end()) {
            throw std::invalid_argument("surface contains a duplicate triangle");
        }

        std::sort(links.begin(), links.end(), quad_preparation_link_less);
        std::vector<long long> link_vertices;
        std::vector<size_t> parent;
        for (size_t begin = 0; begin < links.size();) {
            size_t end = begin + 1U;
            while (end < links.size() && links[end].centre == links[begin].centre) {
                ++end;
            }
            link_vertices.clear();
            link_vertices.reserve((end - begin) * 2U);
            for (size_t index = begin; index < end; ++index) {
                link_vertices.push_back(links[index].edge[0]);
                link_vertices.push_back(links[index].edge[1]);
            }
            std::sort(link_vertices.begin(), link_vertices.end());
            link_vertices.erase(
                std::unique(link_vertices.begin(), link_vertices.end()),
                link_vertices.end());
            parent.resize(link_vertices.size());
            std::iota(parent.begin(), parent.end(), size_t{0});
            for (size_t index = begin; index < end; ++index) {
                const size_t first = static_cast<size_t>(std::lower_bound(
                    link_vertices.begin(), link_vertices.end(), links[index].edge[0])
                    - link_vertices.begin());
                const size_t second = static_cast<size_t>(std::lower_bound(
                    link_vertices.begin(), link_vertices.end(), links[index].edge[1])
                    - link_vertices.begin());
                disjoint_union(parent, first, second);
            }
            const size_t root = disjoint_find(parent, 0U);
            for (size_t index = 1; index < parent.size(); ++index) {
                if (disjoint_find(parent, index) != root) {
                    throw std::invalid_argument(
                        "surface contains non-manifold vertex "
                        + std::to_string(links[begin].centre));
                }
            }
            begin = end;
        }

        for (size_t index = 0; index < wall_edge_count; ++index) {
            long long first = wall_edges(static_cast<py::ssize_t>(index), 0);
            long long second = wall_edges(static_cast<py::ssize_t>(index), 1);
            if (first == second) {
                throw std::invalid_argument(
                    "protected wall edge must have distinct endpoints");
            }
            if (second < first) {
                std::swap(first, second);
            }
            canonical_walls.push_back({first, second});
        }
        std::sort(canonical_walls.begin(), canonical_walls.end());
        canonical_walls.erase(
            std::unique(canonical_walls.begin(), canonical_walls.end()),
            canonical_walls.end());

        std::sort(edges.begin(), edges.end(), quad_preparation_edge_less);
        const double cosine_limit = std::cos(
            feature_angle_deg * std::numbers::pi_v<double> / 180.0);
        size_t wall_cursor = 0;
        for (size_t begin = 0; begin < edges.size();) {
            size_t end = begin + 1U;
            while (end < edges.size() && edges[end].key == edges[begin].key) {
                ++end;
            }
            const size_t incidence = end - begin;
            if (incidence > 2U) {
                throw std::invalid_argument(
                    "surface contains non-manifold edge ("
                    + std::to_string(edges[begin].key[0]) + ", "
                    + std::to_string(edges[begin].key[1]) + ")");
            }
            if (incidence == 2U
                && edges[begin].direction == edges[begin + 1U].direction) {
                throw std::invalid_argument(
                    "surface contains inconsistent orientation at edge ("
                    + std::to_string(edges[begin].key[0]) + ", "
                    + std::to_string(edges[begin].key[1]) + ")");
            }

            while (wall_cursor < canonical_walls.size()
                   && canonical_walls[wall_cursor] < edges[begin].key) {
                throw std::invalid_argument(
                    "protected wall edge ("
                    + std::to_string(canonical_walls[wall_cursor][0]) + ", "
                    + std::to_string(canonical_walls[wall_cursor][1])
                    + ") is not an input surface edge");
            }
            const bool is_wall = wall_cursor < canonical_walls.size()
                && canonical_walls[wall_cursor] == edges[begin].key;
            if (is_wall) {
                ++wall_cursor;
            }
            if (incidence == 1U) {
                ++boundary_count;
            } else {
                ++candidate_count;
                const Point3& first_normal = normals[
                    static_cast<size_t>(edges[begin].face)];
                const Point3& second_normal = normals[
                    static_cast<size_t>(edges[begin + 1U].face)];
                const double normal_dot =
                    first_normal[0] * second_normal[0]
                    + first_normal[1] * second_normal[1]
                    + first_normal[2] * second_normal[2];
                const bool is_feature = normal_dot < cosine_limit;
                if (is_feature) {
                    ++feature_count;
                }
                if (is_feature || is_wall) {
                    ++rejected_protected;
                } else {
                    std::array<long long, 2> pair{
                        edges[begin].face, edges[begin + 1U].face};
                    if (pair[1] < pair[0]) {
                        std::swap(pair[0], pair[1]);
                    }
                    face_pairs.push_back(QuadPreparationPair{
                        pair,
                        std::min(
                            edges[begin].encounter_order,
                            edges[begin + 1U].encounter_order)});
                }
            }
            begin = end;
        }
        if (wall_cursor != canonical_walls.size()) {
            throw std::invalid_argument(
                "protected wall edge ("
                + std::to_string(canonical_walls[wall_cursor][0]) + ", "
                + std::to_string(canonical_walls[wall_cursor][1])
                + ") is not an input surface edge");
        }
        std::sort(
            face_pairs.begin(), face_pairs.end(),
            [](const QuadPreparationPair& left, const QuadPreparationPair& right) {
                return left.encounter_order < right.encounter_order;
            });
    }

    py::array_t<long long> pairs_array({
        static_cast<py::ssize_t>(face_pairs.size()), py::ssize_t{2}});
    auto pairs_out = pairs_array.mutable_unchecked<2>();
    for (py::ssize_t index = 0;
         index < static_cast<py::ssize_t>(face_pairs.size()); ++index) {
        pairs_out(index, 0) = face_pairs[static_cast<size_t>(index)].faces[0];
        pairs_out(index, 1) = face_pairs[static_cast<size_t>(index)].faces[1];
    }
    py::array_t<long long> diagnostics_array(py::array::ShapeContainer{py::ssize_t{5}});
    auto diagnostics = diagnostics_array.mutable_unchecked<1>();
    diagnostics(0) = boundary_count;
    diagnostics(1) = feature_count;
    diagnostics(2) = static_cast<long long>(canonical_walls.size());
    diagnostics(3) = candidate_count;
    diagnostics(4) = rejected_protected;
    return py::make_tuple(std::move(pairs_array), std::move(diagnostics_array));
}

struct QuadPairCandidate {
    double score;
    std::array<long long, 2> face_pair;
    std::array<long long, 4> quad;
    std::array<double, 3> quality;
};

[[nodiscard]] Point3 scale(const Point3& value, const double factor) noexcept
{
    return {value[0] * factor, value[1] * factor, value[2] * factor};
}

[[nodiscard]] Point3 add(const Point3& left, const Point3& right) noexcept
{
    return {left[0] + right[0], left[1] + right[1], left[2] + right[2]};
}

[[nodiscard]] double dot_product(
    const Point3& left, const Point3& right) noexcept
{
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

[[nodiscard]] std::optional<std::array<long long, 4>> oriented_quad(
    const std::array<long long, 3>& first,
    const std::array<long long, 3>& second) noexcept
{
    std::array<long long, 2> shared{};
    size_t shared_count = 0;
    for (const long long first_vertex : first) {
        if (std::find(second.begin(), second.end(), first_vertex) == second.end()) {
            continue;
        }
        if (shared_count == shared.size()) {
            return std::nullopt;
        }
        shared[shared_count++] = first_vertex;
    }
    if (shared_count != shared.size()) {
        return std::nullopt;
    }

    constexpr std::array<size_t, 3> next{{1, 2, 0}};
    constexpr std::array<size_t, 3> opposite{{2, 0, 1}};
    for (size_t local = 0; local < first.size(); ++local) {
        const long long edge_start = first[local];
        const long long edge_end = first[next[local]];
        const bool is_shared_edge =
            (edge_start == shared[0] && edge_end == shared[1])
            || (edge_start == shared[1] && edge_end == shared[0]);
        if (!is_shared_edge) {
            continue;
        }
        const auto second_opposite = std::find_if(
            second.begin(), second.end(), [&](const long long vertex) {
                return vertex != shared[0] && vertex != shared[1];
            });
        if (second_opposite == second.end()) {
            return std::nullopt;
        }
        return std::array<long long, 4>{
            first[opposite[local]], edge_start, *second_opposite, edge_end};
    }
    return std::nullopt;
}

[[nodiscard]] std::optional<std::array<double, 3>> quad_quality(
    const std::array<Point3, 4>& points) noexcept
{
    const auto normalized = similarity_normalized_points(points);
    if (!normalized.has_value()) {
        return std::nullopt;
    }
    const auto& local = *normalized;
    const Point3 first_edge = local[1];
    const Point3 first_diagonal = local[2];
    const Point3 second_diagonal = local[3];
    const Point3 normal = add(
        cross(first_edge, first_diagonal),
        cross(first_diagonal, second_diagonal));
    const double normal_length = norm3(normal);
    if (normal_length <= 1e-30) {
        return std::nullopt;
    }
    const Point3 unit_normal = scale(normal, 1.0 / normal_length);

    std::array<double, 4> lengths{};
    constexpr std::array<size_t, 4> next{{1, 2, 3, 0}};
    constexpr std::array<size_t, 4> previous{{3, 0, 1, 2}};
    for (size_t corner = 0; corner < local.size(); ++corner) {
        lengths[corner] = norm3(sub(local[next[corner]], local[corner]));
    }
    const auto [minimum_length, maximum_length] =
        std::minmax_element(lengths.begin(), lengths.end());
    if (*minimum_length <= 1e-30) {
        return std::nullopt;
    }

    std::array<double, 4> scaled_jacobians{};
    for (size_t corner = 0; corner < local.size(); ++corner) {
        const Point3 next_edge = sub(local[next[corner]], local[corner]);
        const Point3 previous_edge = sub(
            local[previous[corner]], local[corner]);
        const double denominator = norm3(next_edge) * norm3(previous_edge);
        const double value = dot_product(
            cross(next_edge, previous_edge), unit_normal)
            / denominator;
        if (value <= 1e-12) {
            return std::nullopt;
        }
        scaled_jacobians[corner] = value;
    }

    const Point3 plane_normal = cross(first_edge, first_diagonal);
    const double plane_length = norm3(plane_normal);
    if (plane_length <= 1e-30) {
        return std::nullopt;
    }
    const double warpage = std::abs(
        dot_product(second_diagonal, scale(plane_normal, 1.0 / plane_length)))
        / *maximum_length;
    return std::array<double, 3>{
        *std::min_element(scaled_jacobians.begin(), scaled_jacobians.end()),
        *maximum_length / *minimum_length,
        warpage,
    };
}

py::dict select_quad_pairs(
    const py::array_t<double, py::array::c_style>& vertices_array,
    const py::array_t<long long, py::array::c_style>& triangles_array,
    const py::array_t<long long, py::array::c_style>& face_pairs_array,
    const double minimum_scaled_jacobian,
    const double maximum_aspect_ratio,
    const double maximum_warpage)
{
    if (vertices_array.ndim() != 2 || vertices_array.shape(1) != 3) {
        throw std::invalid_argument(
            "vertices must be a C-contiguous float64 array with shape (N, 3)");
    }
    if (triangles_array.ndim() != 2 || triangles_array.shape(1) != 3) {
        throw std::invalid_argument(
            "triangles must be a C-contiguous int64 array with shape (M, 3)");
    }
    if (face_pairs_array.ndim() != 2 || face_pairs_array.shape(1) != 2) {
        throw std::invalid_argument(
            "face_pairs must be a C-contiguous int64 array with shape (K, 2)");
    }
    if (!std::isfinite(minimum_scaled_jacobian)
        || minimum_scaled_jacobian <= 0.0
        || minimum_scaled_jacobian > 1.0) {
        throw std::invalid_argument(
            "minimum_scaled_jacobian must be finite and in (0, 1]");
    }
    if (!std::isfinite(maximum_aspect_ratio)
        || maximum_aspect_ratio < 1.0) {
        throw std::invalid_argument(
            "maximum_aspect_ratio must be finite and at least 1");
    }
    if (!std::isfinite(maximum_warpage)
        || maximum_warpage < 0.0
        || maximum_warpage > 1.0) {
        throw std::invalid_argument(
            "maximum_warpage must be finite and in [0, 1]");
    }

    const auto vertices = vertices_array.unchecked<2>();
    const auto triangles = triangles_array.unchecked<2>();
    const auto face_pairs = face_pairs_array.unchecked<2>();
    const size_t vertex_count = static_cast<size_t>(vertices.shape(0));
    const size_t face_count = static_cast<size_t>(triangles.shape(0));
    const size_t pair_count = static_cast<size_t>(face_pairs.shape(0));
    std::vector<QuadPairCandidate> candidates;
    candidates.reserve(pair_count);
    std::vector<size_t> accepted_indices;
    accepted_indices.reserve(std::min(pair_count, face_count / 2U));
    long long rejected_quality = 0;

    {
        py::gil_scoped_release release;
        for (size_t vertex = 0; vertex < vertex_count; ++vertex) {
            for (size_t axis = 0; axis < 3; ++axis) {
                if (!std::isfinite(vertices(
                        static_cast<py::ssize_t>(vertex),
                        static_cast<py::ssize_t>(axis)))) {
                    throw std::invalid_argument("vertices must contain only finite values");
                }
            }
        }

        for (size_t face = 0; face < face_count; ++face) {
            std::array<long long, 3> triangle{};
            for (size_t local = 0; local < triangle.size(); ++local) {
                const long long vertex = triangles(
                    static_cast<py::ssize_t>(face),
                    static_cast<py::ssize_t>(local));
                if (vertex < 0 || vertex >= static_cast<long long>(vertex_count)) {
                    throw std::invalid_argument(
                        "triangles contain an invalid vertex index");
                }
                triangle[local] = vertex;
            }
            std::sort(triangle.begin(), triangle.end());
            if (std::adjacent_find(triangle.begin(), triangle.end())
                != triangle.end()) {
                throw std::invalid_argument(
                    "triangles must contain three distinct vertex indices");
            }
        }

        std::unordered_set<std::array<long long, 2>, FixedIndexHash<2>> unique_pairs;
        unique_pairs.reserve(pair_count);
        for (size_t pair_index = 0; pair_index < pair_count; ++pair_index) {
            std::array<long long, 2> pair{
                face_pairs(static_cast<py::ssize_t>(pair_index), 0),
                face_pairs(static_cast<py::ssize_t>(pair_index), 1),
            };
            if (pair[0] < 0 || pair[1] < 0
                || pair[0] >= static_cast<long long>(face_count)
                || pair[1] >= static_cast<long long>(face_count)) {
                throw std::invalid_argument(
                    "face_pairs contain an invalid triangle index");
            }
            if (pair[0] == pair[1]) {
                throw std::invalid_argument(
                    "face_pairs must contain two distinct triangle indices");
            }
            if (pair[1] < pair[0]) {
                std::swap(pair[0], pair[1]);
            }
            if (!unique_pairs.insert(pair).second) {
                throw std::invalid_argument("face_pairs contain a duplicate pair");
            }

            std::array<long long, 3> first{};
            std::array<long long, 3> second{};
            for (size_t local = 0; local < first.size(); ++local) {
                first[local] = triangles(
                    static_cast<py::ssize_t>(pair[0]),
                    static_cast<py::ssize_t>(local));
                second[local] = triangles(
                    static_cast<py::ssize_t>(pair[1]),
                    static_cast<py::ssize_t>(local));
            }
            const auto quad = oriented_quad(first, second);
            if (!quad.has_value()) {
                ++rejected_quality;
                continue;
            }
            std::array<Point3, 4> points{};
            for (size_t corner = 0; corner < quad->size(); ++corner) {
                const auto vertex = static_cast<py::ssize_t>((*quad)[corner]);
                points[corner] = {
                    vertices(vertex, 0),
                    vertices(vertex, 1),
                    vertices(vertex, 2),
                };
            }
            const auto quality = quad_quality(points);
            if (!quality.has_value()
                || !std::isfinite((*quality)[0])
                || !std::isfinite((*quality)[1])
                || !std::isfinite((*quality)[2])
                || (*quality)[0] < minimum_scaled_jacobian
                || (*quality)[1] > maximum_aspect_ratio
                || (*quality)[2] > maximum_warpage) {
                ++rejected_quality;
                continue;
            }
            const double score = (*quality)[0] - (*quality)[2];
            if (!std::isfinite(score)) {
                ++rejected_quality;
                continue;
            }
            candidates.push_back(QuadPairCandidate{
                score, pair, *quad, *quality});
        }

        std::stable_sort(
            candidates.begin(), candidates.end(),
            [](const QuadPairCandidate& left, const QuadPairCandidate& right) {
                if (left.score != right.score) {
                    return left.score > right.score;
                }
                if (left.face_pair[0] != right.face_pair[0]) {
                    return left.face_pair[0] < right.face_pair[0];
                }
                return left.face_pair[1] < right.face_pair[1];
            });
        std::vector<unsigned char> consumed(face_count, 0U);
        for (size_t candidate_index = 0;
             candidate_index < candidates.size(); ++candidate_index) {
            const auto& candidate = candidates[candidate_index];
            const size_t first = static_cast<size_t>(candidate.face_pair[0]);
            const size_t second = static_cast<size_t>(candidate.face_pair[1]);
            if (consumed[first] != 0U || consumed[second] != 0U) {
                continue;
            }
            consumed[first] = 1U;
            consumed[second] = 1U;
            accepted_indices.push_back(candidate_index);
        }
        std::sort(
            accepted_indices.begin(), accepted_indices.end(),
            [&](const size_t left_index, const size_t right_index) {
                const auto& left = candidates[left_index];
                const auto& right = candidates[right_index];
                if (left.face_pair[0] != right.face_pair[0]) {
                    return left.face_pair[0] < right.face_pair[0];
                }
                return left.face_pair[1] < right.face_pair[1];
            });
    }

    const auto accepted_count = static_cast<py::ssize_t>(accepted_indices.size());
    py::array_t<long long> accepted_pairs({accepted_count, py::ssize_t{2}});
    py::array_t<long long> quads({accepted_count, py::ssize_t{4}});
    py::array_t<double> quality({accepted_count, py::ssize_t{3}});
    auto accepted_pairs_out = accepted_pairs.mutable_unchecked<2>();
    auto quads_out = quads.mutable_unchecked<2>();
    auto quality_out = quality.mutable_unchecked<2>();
    for (py::ssize_t index = 0; index < accepted_count; ++index) {
        const auto& candidate = candidates[
            accepted_indices[static_cast<size_t>(index)]];
        for (py::ssize_t local = 0; local < 2; ++local) {
            accepted_pairs_out(index, local) =
                candidate.face_pair[static_cast<size_t>(local)];
        }
        for (py::ssize_t local = 0; local < 4; ++local) {
            quads_out(index, local) = candidate.quad[static_cast<size_t>(local)];
        }
        for (py::ssize_t metric = 0; metric < 3; ++metric) {
            quality_out(index, metric) =
                candidate.quality[static_cast<size_t>(metric)];
        }
    }
    py::dict result;
    result["accepted_face_pairs"] = std::move(accepted_pairs);
    result["quads"] = std::move(quads);
    result["quality"] = std::move(quality);
    result["rejected_quality"] = rejected_quality;
    return result;
}

py::dict quad_dominant_transaction(
    const py::array_t<double, py::array::c_style>& vertices_array,
    const py::array_t<long long, py::array::c_style>& triangles_array,
    const py::array_t<long long, py::array::c_style>& wall_edges_array,
    const double feature_angle_deg,
    const double minimum_scaled_jacobian,
    const double maximum_aspect_ratio,
    const double maximum_warpage)
{
    const py::tuple preparation = prepare_quad_pairs(
        vertices_array, triangles_array, wall_edges_array, feature_angle_deg);
    const auto candidate_pairs =
        py::cast<py::array_t<long long>>(preparation[0]);
    const auto preparation_diagnostics =
        py::cast<py::array_t<long long>>(preparation[1]);
    py::dict selection = select_quad_pairs(
        vertices_array,
        triangles_array,
        candidate_pairs,
        minimum_scaled_jacobian,
        maximum_aspect_ratio,
        maximum_warpage);
    const auto accepted_pairs = py::cast<py::array_t<long long>>(
        selection["accepted_face_pairs"]);
    const auto accepted = accepted_pairs.unchecked<2>();
    const auto triangles = triangles_array.unchecked<2>();
    const size_t face_count = static_cast<size_t>(triangles.shape(0));
    const size_t accepted_count = static_cast<size_t>(accepted.shape(0));
    if (accepted_count > face_count / 2U) {
        throw std::logic_error(
            "quad transaction accepted more face pairs than the surface contains");
    }
    std::vector<unsigned char> consumed(face_count, 0U);
    for (size_t pair = 0; pair < accepted_count; ++pair) {
        for (size_t local = 0; local < 2U; ++local) {
            const auto face = accepted(
                static_cast<py::ssize_t>(pair),
                static_cast<py::ssize_t>(local));
            if (face < 0 || face >= static_cast<long long>(face_count)) {
                throw std::logic_error(
                    "quad transaction produced an out-of-range accepted face");
            }
            auto& marker = consumed[static_cast<size_t>(face)];
            if (marker != 0U) {
                throw std::logic_error(
                    "quad transaction consumed one face more than once");
            }
            marker = 1U;
        }
    }

    const auto remaining_count = static_cast<py::ssize_t>(
        face_count - accepted_count * 2U);
    py::array_t<long long> remaining_triangles({
        remaining_count, py::ssize_t{3}});
    auto remaining = remaining_triangles.mutable_unchecked<2>();
    py::ssize_t output_index = 0;
    for (size_t face = 0; face < face_count; ++face) {
        if (consumed[face] != 0U) {
            continue;
        }
        for (py::ssize_t local = 0; local < 3; ++local) {
            remaining(output_index, local) = triangles(
                static_cast<py::ssize_t>(face), local);
        }
        ++output_index;
    }

    py::dict result;
    result["candidate_face_pairs"] = candidate_pairs;
    result["accepted_face_pairs"] = accepted_pairs;
    result["remaining_triangles"] = std::move(remaining_triangles);
    result["quads"] = selection["quads"];
    result["quality"] = selection["quality"];
    result["preparation_diagnostics"] = preparation_diagnostics;
    result["rejected_quality"] = selection["rejected_quality"];
    return result;
}

struct StrictQuadPairAuditEdge {
    long long first;
    long long second;
    size_t face;
    signed char direction;
};

struct StrictQuadPairTopology {
    bool manifold = false;
    size_t edge_count = 0U;
    size_t component_count = 0U;
    std::vector<std::array<long long, 3>> boundary_edges;
    std::vector<std::array<long long, 2>> edge_keys;
};

[[nodiscard]] bool strict_quad_pair_audit_edge_less(
    const StrictQuadPairAuditEdge& left,
    const StrictQuadPairAuditEdge& right) noexcept
{
    if (left.first != right.first) {
        return left.first < right.first;
    }
    if (left.second != right.second) {
        return left.second < right.second;
    }
    return left.face < right.face;
}

template <size_t Corners, typename FaceAt>
[[nodiscard]] StrictQuadPairTopology strict_quad_pair_audit_topology(
    const size_t face_count,
    FaceAt&& face_at)
{
    std::vector<StrictQuadPairAuditEdge> edges;
    edges.reserve(face_count * Corners);
    std::vector<size_t> parents(face_count);
    std::iota(parents.begin(), parents.end(), 0U);
    for (size_t face = 0U; face < face_count; ++face) {
        for (size_t local = 0U; local < Corners; ++local) {
            const long long start = face_at(face, local);
            const long long end = face_at(face, (local + 1U) % Corners);
            const long long first = std::min(start, end);
            const long long second = std::max(start, end);
            edges.push_back(StrictQuadPairAuditEdge{
                first,
                second,
                face,
                static_cast<signed char>(start == first ? 1 : -1),
            });
        }
    }
    std::sort(edges.begin(), edges.end(), strict_quad_pair_audit_edge_less);
    StrictQuadPairTopology result;
    result.manifold = true;
    for (size_t first = 0U; first < edges.size();) {
        size_t last = first + 1U;
        while (last < edges.size() && edges[last].first == edges[first].first
               && edges[last].second == edges[first].second) {
            ++last;
        }
        result.edge_keys.push_back({edges[first].first, edges[first].second});
        ++result.edge_count;
        if (last - first > 2U
            || (last - first == 2U
                && edges[first].direction == edges[first + 1U].direction)) {
            result.manifold = false;
        }
        if (last - first == 1U) {
            result.boundary_edges.push_back({
                edges[first].first,
                edges[first].second,
                static_cast<long long>(edges[first].direction),
            });
        } else if (last - first == 2U) {
            triangle_topology_audit_union(
                parents, edges[first].face, edges[first + 1U].face);
        }
        first = last;
    }
    for (size_t face = 0U; face < face_count; ++face) {
        if (triangle_topology_audit_find(parents, face) == face) {
            ++result.component_count;
        }
    }
    return result;
}

py::dict strict_quad_pair_preflight(
    const py::array& source_vertices_input,
    const py::array& candidate_vertices_input,
    const py::array& source_triangles_input,
    const py::array& candidate_triangles_input,
    const py::array& quads_input,
    const py::array& pair_provenance_input,
    const py::array& feature_edges_input)
{
    const auto require_points = [](const py::array& values, const char* name) {
        if (!values.dtype().is(py::dtype::of<double>())
            || (values.flags() & py::array::c_style) == 0
            || values.ndim() != 2 || values.shape(1) != 3) {
            throw std::invalid_argument(
                std::string(name)
                + " must be a C-contiguous float64 array with shape (N, 3)");
        }
    };
    const auto require_indices = [](const py::array& values,
                                    const py::ssize_t columns,
                                    const char* name) {
        if (!values.dtype().is(py::dtype::of<long long>())
            || (values.flags() & py::array::c_style) == 0
            || values.ndim() != 2 || values.shape(1) != columns) {
            throw std::invalid_argument(
                std::string(name)
                + " must be a C-contiguous int64 array with shape (N, "
                + std::to_string(columns) + ")");
        }
    };
    require_points(source_vertices_input, "source_vertices");
    require_points(candidate_vertices_input, "candidate_vertices");
    require_indices(source_triangles_input, 3, "source_triangles");
    require_indices(candidate_triangles_input, 3, "candidate_triangles");
    require_indices(quads_input, 4, "quads");
    require_indices(pair_provenance_input, 2, "pair_provenance");
    require_indices(feature_edges_input, 2, "feature_edges");

    const auto source_vertices =
        py::reinterpret_borrow<py::array_t<double>>(source_vertices_input)
            .unchecked<2>();
    const auto candidate_vertices =
        py::reinterpret_borrow<py::array_t<double>>(candidate_vertices_input)
            .unchecked<2>();
    const auto source_triangles =
        py::reinterpret_borrow<py::array_t<long long>>(source_triangles_input)
            .unchecked<2>();
    const auto candidate_triangles =
        py::reinterpret_borrow<py::array_t<long long>>(candidate_triangles_input)
            .unchecked<2>();
    const auto quads = py::reinterpret_borrow<py::array_t<long long>>(quads_input)
        .unchecked<2>();
    const auto pairs =
        py::reinterpret_borrow<py::array_t<long long>>(pair_provenance_input)
            .unchecked<2>();
    const auto feature_edges =
        py::reinterpret_borrow<py::array_t<long long>>(feature_edges_input)
            .unchecked<2>();
    const size_t source_vertex_count =
        static_cast<size_t>(source_vertices.shape(0));
    const size_t source_face_count =
        static_cast<size_t>(source_triangles.shape(0));
    const size_t quad_count = static_cast<size_t>(quads.shape(0));

    bool coordinates_finite = true;
    bool vertices_exact = source_vertices.shape(0) == candidate_vertices.shape(0);
    for (size_t vertex = 0U; vertex < source_vertex_count; ++vertex) {
        for (size_t axis = 0U; axis < 3U; ++axis) {
            const double source = source_vertices(
                static_cast<py::ssize_t>(vertex), static_cast<py::ssize_t>(axis));
            if (!std::isfinite(source)) {
                coordinates_finite = false;
            }
            if (vertices_exact && std::bit_cast<std::uint64_t>(source)
                != std::bit_cast<std::uint64_t>(candidate_vertices(
                    static_cast<py::ssize_t>(vertex),
                    static_cast<py::ssize_t>(axis)))) {
                vertices_exact = false;
            }
        }
    }
    for (py::ssize_t vertex = 0; vertex < candidate_vertices.shape(0); ++vertex) {
        for (py::ssize_t axis = 0; axis < 3; ++axis) {
            if (!std::isfinite(candidate_vertices(vertex, axis))) {
                coordinates_finite = false;
            }
        }
    }

    bool source_indices_valid = source_face_count > 0U;
    bool quad_indices_valid = quad_count > 0U;
    bool quads_degree_four = quad_count > 0U;
    bool source_triangles_non_degenerate = source_indices_valid;
    for (size_t face = 0U; face < source_face_count; ++face) {
        std::array<long long, 3> triangle{};
        for (size_t local = 0U; local < triangle.size(); ++local) {
            triangle[local] = source_triangles(
                static_cast<py::ssize_t>(face), static_cast<py::ssize_t>(local));
            if (triangle[local] < 0
                || triangle[local] >= static_cast<long long>(source_vertex_count)) {
                source_indices_valid = false;
            }
        }
        std::sort(triangle.begin(), triangle.end());
        if (std::adjacent_find(triangle.begin(), triangle.end()) != triangle.end()) {
            source_indices_valid = false;
        }
        if (source_indices_valid) {
            const Point3 first{
                source_vertices(source_triangles(static_cast<py::ssize_t>(face), 0), 0),
                source_vertices(source_triangles(static_cast<py::ssize_t>(face), 0), 1),
                source_vertices(source_triangles(static_cast<py::ssize_t>(face), 0), 2),
            };
            const Point3 second{
                source_vertices(source_triangles(static_cast<py::ssize_t>(face), 1), 0),
                source_vertices(source_triangles(static_cast<py::ssize_t>(face), 1), 1),
                source_vertices(source_triangles(static_cast<py::ssize_t>(face), 1), 2),
            };
            const Point3 third{
                source_vertices(source_triangles(static_cast<py::ssize_t>(face), 2), 0),
                source_vertices(source_triangles(static_cast<py::ssize_t>(face), 2), 1),
                source_vertices(source_triangles(static_cast<py::ssize_t>(face), 2), 2),
            };
            const Point3 ab{second[0] - first[0], second[1] - first[1], second[2] - first[2]};
            const Point3 ac{third[0] - first[0], third[1] - first[1], third[2] - first[2]};
            const Point3 cross{
                ab[1] * ac[2] - ab[2] * ac[1],
                ab[2] * ac[0] - ab[0] * ac[2],
                ab[0] * ac[1] - ab[1] * ac[0],
            };
            const double twice_area = std::sqrt(
                cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2]);
            if (!std::isfinite(twice_area)
                || twice_area <= std::numeric_limits<double>::min()) {
                source_triangles_non_degenerate = false;
            }
        }
    }
    for (size_t face = 0U; face < quad_count; ++face) {
        std::array<long long, 4> quad{};
        for (size_t local = 0U; local < quad.size(); ++local) {
            quad[local] = quads(
                static_cast<py::ssize_t>(face), static_cast<py::ssize_t>(local));
            if (quad[local] < 0
                || quad[local] >= static_cast<long long>(source_vertex_count)) {
                quad_indices_valid = false;
            }
        }
        std::sort(quad.begin(), quad.end());
        if (std::adjacent_find(quad.begin(), quad.end()) != quad.end()) {
            quads_degree_four = false;
        }
    }

    bool provenance_complete = pairs.shape(0) == quads.shape(0)
        && source_face_count == quad_count * 2U;
    std::vector<unsigned char> source_consumed(source_face_count, 0U);
    bool pair_ordered = true;
    for (size_t pair_index = 0U; pair_index < quad_count; ++pair_index) {
        const long long first = pairs(static_cast<py::ssize_t>(pair_index), 0);
        const long long second = pairs(static_cast<py::ssize_t>(pair_index), 1);
        if (first < 0 || second < 0 || first >= static_cast<long long>(source_face_count)
            || second >= static_cast<long long>(source_face_count) || first >= second) {
            provenance_complete = false;
            continue;
        }
        if (pair_index > 0U) {
            const long long previous_first = pairs(
                static_cast<py::ssize_t>(pair_index - 1U), 0);
            const long long previous_second = pairs(
                static_cast<py::ssize_t>(pair_index - 1U), 1);
            if (first < previous_first
                || (first == previous_first && second <= previous_second)) {
                pair_ordered = false;
            }
        }
        if (source_consumed[static_cast<size_t>(first)] != 0U
            || source_consumed[static_cast<size_t>(second)] != 0U) {
            provenance_complete = false;
        }
        source_consumed[static_cast<size_t>(first)] = 1U;
        source_consumed[static_cast<size_t>(second)] = 1U;
    }
    if (!std::all_of(source_consumed.begin(), source_consumed.end(),
                     [](const unsigned char value) { return value != 0U; })) {
        provenance_complete = false;
    }

    bool pair_quads_exact = true;
    bool pairs_coplanar = true;
    if (!source_indices_valid || !quad_indices_valid || !provenance_complete) {
        pair_quads_exact = false;
        pairs_coplanar = false;
    } else {
        for (size_t pair_index = 0U; pair_index < quad_count; ++pair_index) {
            std::array<long long, 3> first{};
            std::array<long long, 3> second{};
            for (size_t local = 0U; local < 3U; ++local) {
                first[local] = source_triangles(
                    pairs(static_cast<py::ssize_t>(pair_index), 0),
                    static_cast<py::ssize_t>(local));
                second[local] = source_triangles(
                    pairs(static_cast<py::ssize_t>(pair_index), 1),
                    static_cast<py::ssize_t>(local));
            }
            const auto expected = oriented_quad(first, second);
            if (!expected.has_value()) {
                pair_quads_exact = false;
                continue;
            }
            for (size_t local = 0U; local < 4U; ++local) {
                if ((*expected)[local] != quads(
                        static_cast<py::ssize_t>(pair_index),
                        static_cast<py::ssize_t>(local))) {
                    pair_quads_exact = false;
                }
            }
            const Point3 first_point{
                source_vertices((*expected)[0], 0), source_vertices((*expected)[0], 1), source_vertices((*expected)[0], 2)};
            const Point3 second_point{
                source_vertices((*expected)[1], 0), source_vertices((*expected)[1], 1), source_vertices((*expected)[1], 2)};
            const Point3 third_point{
                source_vertices((*expected)[2], 0), source_vertices((*expected)[2], 1), source_vertices((*expected)[2], 2)};
            const Point3 fourth_point{
                source_vertices((*expected)[3], 0), source_vertices((*expected)[3], 1), source_vertices((*expected)[3], 2)};
            const Point3 ab{second_point[0] - first_point[0], second_point[1] - first_point[1], second_point[2] - first_point[2]};
            const Point3 ac{third_point[0] - first_point[0], third_point[1] - first_point[1], third_point[2] - first_point[2]};
            const Point3 ad{fourth_point[0] - first_point[0], fourth_point[1] - first_point[1], fourth_point[2] - first_point[2]};
            const Point3 cross{
                ab[1] * ac[2] - ab[2] * ac[1],
                ab[2] * ac[0] - ab[0] * ac[2],
                ab[0] * ac[1] - ab[1] * ac[0],
            };
            if (cross[0] * ad[0] + cross[1] * ad[1] + cross[2] * ad[2] != 0.0) {
                pairs_coplanar = false;
            }
        }
    }

    StrictQuadPairTopology source_topology;
    StrictQuadPairTopology quad_topology;
    if (source_indices_valid && quad_indices_valid) {
        source_topology = strict_quad_pair_audit_topology<3>(
            source_face_count,
            [&](const size_t face, const size_t local) {
                return source_triangles(
                    static_cast<py::ssize_t>(face), static_cast<py::ssize_t>(local));
            });
        quad_topology = strict_quad_pair_audit_topology<4>(
            quad_count,
            [&](const size_t face, const size_t local) {
                return quads(
                    static_cast<py::ssize_t>(face), static_cast<py::ssize_t>(local));
            });
    }
    const bool boundary_equal = source_topology.boundary_edges
        == quad_topology.boundary_edges;
    const long long source_euler = static_cast<long long>(source_vertex_count)
        - static_cast<long long>(source_topology.edge_count)
        + static_cast<long long>(source_face_count);
    const long long quad_euler = static_cast<long long>(source_vertex_count)
        - static_cast<long long>(quad_topology.edge_count)
        + static_cast<long long>(quad_count);
    bool features_preserved = true;
    for (py::ssize_t feature = 0; feature < feature_edges.shape(0); ++feature) {
        long long first = feature_edges(feature, 0);
        long long second = feature_edges(feature, 1);
        if (first < 0 || second < 0 || first >= static_cast<long long>(source_vertex_count)
            || second >= static_cast<long long>(source_vertex_count) || first == second) {
            features_preserved = false;
            continue;
        }
        if (second < first) {
            std::swap(first, second);
        }
        const std::array<long long, 2> edge{first, second};
        if (!std::binary_search(
                source_topology.edge_keys.begin(), source_topology.edge_keys.end(), edge)
            || !std::binary_search(
                quad_topology.edge_keys.begin(), quad_topology.edge_keys.end(), edge)) {
            features_preserved = false;
        }
    }
    const bool candidate_triangles_empty = candidate_triangles.shape(0) == 0;
    const bool topology_preserved = source_topology.manifold
        && quad_topology.manifold && boundary_equal
        && source_topology.component_count == quad_topology.component_count
        && source_euler == quad_euler;
    const bool valid = coordinates_finite && vertices_exact && source_indices_valid
        && quad_indices_valid && quads_degree_four && quad_count > 0U
        && source_triangles_non_degenerate
        && candidate_triangles_empty && provenance_complete && pair_ordered
        && pair_quads_exact && pairs_coplanar && features_preserved && topology_preserved;
    py::dict result;
    result["valid"] = valid;
    result["coordinates_finite"] = coordinates_finite;
    result["vertices_exact"] = vertices_exact;
    result["source_triangles_non_degenerate"] = source_triangles_non_degenerate;
    result["candidate_triangles_empty"] = candidate_triangles_empty;
    result["quads_degree_four"] = quads_degree_four;
    result["provenance_complete"] = provenance_complete && pair_ordered;
    result["pair_quads_exact"] = pair_quads_exact;
    result["pairs_coplanar"] = pairs_coplanar;
    result["source_manifold"] = source_topology.manifold;
    result["quad_manifold"] = quad_topology.manifold;
    result["boundary_equal"] = boundary_equal;
    result["features_preserved"] = features_preserved;
    result["source_component_count"] = source_topology.component_count;
    result["quad_component_count"] = quad_topology.component_count;
    result["source_euler_characteristic"] = source_euler;
    result["quad_euler_characteristic"] = quad_euler;
    return result;
}

[[nodiscard]] double dot(const Point3& left, const Point3& right) noexcept
{
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

[[nodiscard]] double norm(const Point3& value) noexcept
{
    return std::sqrt(dot(value, value));
}

[[nodiscard]] bool all_greater(
    const std::array<double, 3>& values, const double threshold) noexcept
{
    return values[0] > threshold
        && values[1] > threshold
        && values[2] > threshold;
}

[[nodiscard]] bool all_less(
    const std::array<double, 3>& values, const double threshold) noexcept
{
    return values[0] < threshold
        && values[1] < threshold
        && values[2] < threshold;
}

[[nodiscard]] bool segment_hits_triangle(
    const Point3& point0,
    const Point3& point1,
    const std::array<Point3, 3>& triangle,
    const double epsilon) noexcept
{
    const Point3 direction = sub(point1, point0);
    const Point3 edge1 = sub(triangle[1], triangle[0]);
    const Point3 edge2 = sub(triangle[2], triangle[0]);
    const Point3 pvec = cross(direction, edge2);
    const double determinant = dot(edge1, pvec);
    if (std::abs(determinant) < epsilon) {
        return false;
    }
    const double inverse_determinant = 1.0 / determinant;
    const Point3 tvec = sub(point0, triangle[0]);
    const double u = dot(tvec, pvec) * inverse_determinant;
    if (u < -epsilon || u > 1.0 + epsilon) {
        return false;
    }
    const Point3 qvec = cross(tvec, edge1);
    const double v = dot(direction, qvec) * inverse_determinant;
    if (v < -epsilon || u + v > 1.0 + epsilon) {
        return false;
    }
    const double distance = dot(edge2, qvec) * inverse_determinant;
    return distance >= -epsilon && distance <= 1.0 + epsilon;
}

[[nodiscard]] bool segment_triangle_intersection(
    const std::array<Point3, 3>& first,
    const std::array<Point3, 3>& second,
    const double epsilon) noexcept
{
    const Point3 normal1 = cross(
        sub(first[1], first[0]), sub(first[2], first[0]));
    if (norm(normal1) < epsilon) {
        return false;
    }
    const double distance1 = dot(normal1, first[0]);
    const std::array<double, 3> second_distances{
        dot(normal1, second[0]) - distance1,
        dot(normal1, second[1]) - distance1,
        dot(normal1, second[2]) - distance1,
    };
    if (all_greater(second_distances, epsilon)
        || all_less(second_distances, -epsilon)) {
        return false;
    }
    if (std::abs(second_distances[0]) < epsilon
        && std::abs(second_distances[1]) < epsilon
        && std::abs(second_distances[2]) < epsilon) {
        return false;
    }

    const Point3 normal2 = cross(
        sub(second[1], second[0]), sub(second[2], second[0]));
    if (norm(normal2) < epsilon) {
        return false;
    }
    const double distance2 = dot(normal2, second[0]);
    const std::array<double, 3> first_distances{
        dot(normal2, first[0]) - distance2,
        dot(normal2, first[1]) - distance2,
        dot(normal2, first[2]) - distance2,
    };
    if (all_greater(first_distances, epsilon)
        || all_less(first_distances, -epsilon)) {
        return false;
    }

    constexpr std::array<std::array<size_t, 2>, 3> edges{{
        {{0U, 1U}}, {{1U, 2U}}, {{2U, 0U}},
    }};
    for (const auto& edge : edges) {
        if (segment_hits_triangle(
                first[edge[0]], first[edge[1]], second, epsilon)) {
            return true;
        }
    }
    for (const auto& edge : edges) {
        if (segment_hits_triangle(
                second[edge[0]], second[edge[1]], first, epsilon)) {
            return true;
        }
    }
    return false;
}

[[nodiscard]] std::pair<double, double> intersection_interval(
    const std::array<Point3, 3>& triangle,
    const std::array<double, 3>& signed_distances,
    const Point3& direction,
    const double epsilon) noexcept
{
    const std::array<double, 3> projection{
        dot(triangle[0], direction),
        dot(triangle[1], direction),
        dot(triangle[2], direction),
    };
    std::array<size_t, 3> same{};
    std::array<size_t, 3> different{};
    size_t same_count = 0U;
    size_t different_count = 0U;
    for (size_t index = 0U; index < 3U; ++index) {
        if (signed_distances[index] * signed_distances[0] > 0.0) {
            same[same_count++] = index;
        } else {
            different[different_count++] = index;
        }
    }

    size_t alone = 0U;
    std::array<size_t, 2> others{1U, 2U};
    if (same_count == 2U) {
        alone = 0U;
    } else if (different_count == 1U) {
        alone = different[0];
        others = alone == 0U
            ? std::array<size_t, 2>{1U, 2U}
            : alone == 1U
                ? std::array<size_t, 2>{0U, 2U}
                : std::array<size_t, 2>{0U, 1U};
    } else if (same_count == 1U) {
        alone = same[0];
        others = alone == 0U
            ? std::array<size_t, 2>{1U, 2U}
            : alone == 1U
                ? std::array<size_t, 2>{0U, 2U}
                : std::array<size_t, 2>{0U, 1U};
    }

    std::array<double, 2> values{};
    for (size_t index = 0U; index < 2U; ++index) {
        const size_t other = others[index];
        const double denominator =
            signed_distances[alone] - signed_distances[other];
        values[index] = std::abs(denominator) < epsilon
            ? projection[alone]
            : projection[other]
                + (projection[alone] - projection[other])
                    * signed_distances[other] / denominator;
    }
    return std::minmax(values[0], values[1]);
}

[[nodiscard]] bool interval_triangle_intersection(
    const std::array<Point3, 3>& first,
    const std::array<Point3, 3>& second,
    const double epsilon) noexcept
{
    const Point3 normal1 = cross(
        sub(first[1], first[0]), sub(first[2], first[0]));
    const double distance1 = dot(normal1, first[0]);
    const std::array<double, 3> second_distances{
        dot(second[0], normal1) - distance1,
        dot(second[1], normal1) - distance1,
        dot(second[2], normal1) - distance1,
    };
    if (all_greater(second_distances, epsilon)
        || all_less(second_distances, -epsilon)) {
        return false;
    }

    const Point3 normal2 = cross(
        sub(second[1], second[0]), sub(second[2], second[0]));
    const double distance2 = dot(normal2, second[0]);
    const std::array<double, 3> first_distances{
        dot(first[0], normal2) - distance2,
        dot(first[1], normal2) - distance2,
        dot(first[2], normal2) - distance2,
    };
    if (all_greater(first_distances, epsilon)
        || all_less(first_distances, -epsilon)) {
        return false;
    }

    Point3 direction = cross(normal1, normal2);
    const double direction_norm = norm(direction);
    if (direction_norm < epsilon) {
        return false;
    }
    direction[0] /= direction_norm;
    direction[1] /= direction_norm;
    direction[2] /= direction_norm;
    const auto first_interval = intersection_interval(
        first, first_distances, direction, epsilon);
    const auto second_interval = intersection_interval(
        second, second_distances, direction, epsilon);
    return first_interval.second >= second_interval.first - epsilon
        && second_interval.second >= first_interval.first - epsilon;
}

struct TriangleIntersectionResult {
    long long tested = 0;
    std::vector<std::pair<long long, long long>> pairs;
};

enum class TrianglePredicate : unsigned char {
    Segment,
    Interval,
};

TriangleIntersectionResult triangle_intersections_impl(
    const double* vertices,
    const long long* triangles,
    const long long* candidates,
    const size_t candidate_count,
    const size_t shared_vertex_threshold,
    const double epsilon,
    const TrianglePredicate predicate)
{
    TriangleIntersectionResult result;
    result.pairs.reserve(std::min(candidate_count, static_cast<size_t>(1024U)));
    for (size_t candidate_index = 0U;
         candidate_index < candidate_count;
         ++candidate_index) {
        const long long first_id = candidates[candidate_index * 2U];
        const long long second_id = candidates[candidate_index * 2U + 1U];
        const long long* const first_face = triangles
            + static_cast<size_t>(first_id) * 3U;
        const long long* const second_face = triangles
            + static_cast<size_t>(second_id) * 3U;
        std::array<long long, 3> shared_ids{};
        size_t shared_vertices = 0U;
        for (size_t first_local = 0U; first_local < 3U; ++first_local) {
            for (size_t second_local = 0U; second_local < 3U; ++second_local) {
                if (first_face[first_local] == second_face[second_local]) {
                    const long long shared = first_face[first_local];
                    if (std::find(
                            shared_ids.begin(),
                            shared_ids.begin() + shared_vertices,
                            shared)
                        == shared_ids.begin() + shared_vertices) {
                        shared_ids[shared_vertices++] = shared;
                    }
                }
            }
        }
        if (shared_vertices >= shared_vertex_threshold) {
            continue;
        }
        ++result.tested;

        std::array<Point3, 3> first{};
        std::array<Point3, 3> second{};
        for (size_t local = 0U; local < 3U; ++local) {
            const double* const first_point = vertices
                + static_cast<size_t>(first_face[local]) * 3U;
            const double* const second_point = vertices
                + static_cast<size_t>(second_face[local]) * 3U;
            first[local] = {first_point[0], first_point[1], first_point[2]};
            second[local] = {second_point[0], second_point[1], second_point[2]};
        }
        const bool intersects = predicate == TrianglePredicate::Segment
            ? segment_triangle_intersection(first, second, epsilon)
            : interval_triangle_intersection(first, second, epsilon);
        if (intersects) {
            result.pairs.emplace_back(first_id, second_id);
        }
    }
    return result;
}

void validate_triangle_intersection_inputs(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& vertices,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& triangles,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& candidates,
    const double epsilon)
{
    if (vertices.ndim() != 2 || vertices.shape(1) != 3) {
        throw std::invalid_argument("vertices must have shape (N, 3)");
    }
    if (triangles.ndim() != 2 || triangles.shape(1) != 3) {
        throw std::invalid_argument("triangles must have shape (F, 3)");
    }
    if (candidates.ndim() != 2 || candidates.shape(1) != 2) {
        throw std::invalid_argument("candidates must have shape (K, 2)");
    }
    if (!std::isfinite(epsilon) || epsilon < 0.0) {
        throw std::invalid_argument("epsilon must be finite and non-negative");
    }
    const long long vertex_count = static_cast<long long>(vertices.shape(0));
    const long long face_count = static_cast<long long>(triangles.shape(0));
    const long long* const face_data = triangles.data();
    for (py::ssize_t index = 0; index < triangles.size(); ++index) {
        if (face_data[index] < 0 || face_data[index] >= vertex_count) {
            throw std::invalid_argument("triangle vertex index is out of bounds");
        }
    }
    const long long* const candidate_data = candidates.data();
    for (py::ssize_t index = 0; index < candidates.shape(0); ++index) {
        const long long first = candidate_data[index * 2];
        const long long second = candidate_data[index * 2 + 1];
        if (first < 0 || second < 0 || first >= face_count || second >= face_count) {
            throw std::invalid_argument("candidate face index is out of bounds");
        }
        if (first >= second) {
            throw std::invalid_argument("candidate pairs must satisfy i < j");
        }
    }
}

py::array_t<long long> copy_triangle_pairs(
    const std::vector<std::pair<long long, long long>>& pairs)
{
    py::array_t<long long> result({
        static_cast<py::ssize_t>(pairs.size()), static_cast<py::ssize_t>(2)});
    long long* const output = result.mutable_data();
    for (size_t index = 0U; index < pairs.size(); ++index) {
        output[index * 2U] = pairs[index].first;
        output[index * 2U + 1U] = pairs[index].second;
    }
    return result;
}

py::tuple triangle_intersections_segment(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& vertices,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& triangles,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& candidates,
    const double epsilon)
{
    validate_triangle_intersection_inputs(vertices, triangles, candidates, epsilon);
    TriangleIntersectionResult result;
    {
        py::gil_scoped_release release;
        result = triangle_intersections_impl(
            vertices.data(), triangles.data(), candidates.data(),
            static_cast<size_t>(candidates.shape(0)), 1U, epsilon,
            TrianglePredicate::Segment);
    }
    return py::make_tuple(result.tested, copy_triangle_pairs(result.pairs));
}

py::array_t<long long> triangle_intersections_interval(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& vertices,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& triangles,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& candidates,
    const double epsilon)
{
    validate_triangle_intersection_inputs(vertices, triangles, candidates, epsilon);
    TriangleIntersectionResult result;
    {
        py::gil_scoped_release release;
        result = triangle_intersections_impl(
            vertices.data(), triangles.data(), candidates.data(),
            static_cast<size_t>(candidates.shape(0)), 2U, epsilon,
            TrianglePredicate::Interval);
    }
    return copy_triangle_pairs(result.pairs);
}

py::array_t<long long> aabb_overlap_pairs(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& aabb_min,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& aabb_max,
    const double epsilon)
{
    if (aabb_min.ndim() != 2 || aabb_min.shape(1) != 3
        || aabb_max.ndim() != 2 || aabb_max.shape(1) != 3) {
        throw std::invalid_argument("AABBs must have shape (N, 3)");
    }
    if (aabb_min.shape(0) != aabb_max.shape(0)) {
        throw std::invalid_argument("AABB arrays must have matching lengths");
    }
    if (!std::isfinite(epsilon) || epsilon < 0.0) {
        throw std::invalid_argument("epsilon must be finite and non-negative");
    }

    const size_t count = static_cast<size_t>(aabb_min.shape(0));
    const double* const minimum = aabb_min.data();
    const double* const maximum = aabb_max.data();
    for (size_t box = 0U; box < count; ++box) {
        for (size_t axis = 0U; axis < 3U; ++axis) {
            const size_t offset = box * 3U + axis;
            if (!std::isfinite(minimum[offset])
                || !std::isfinite(maximum[offset])) {
                throw std::invalid_argument("AABBs must contain finite values");
            }
            if (minimum[offset] > maximum[offset]) {
                throw std::invalid_argument("AABB minimum exceeds maximum");
            }
        }
    }

    std::vector<std::pair<long long, long long>> pairs;
    {
        py::gil_scoped_release release;

        size_t sweep_axis = 0U;
        if (count > 0U) {
            double global_minimum[3]{minimum[0], minimum[1], minimum[2]};
            double global_maximum[3]{maximum[0], maximum[1], maximum[2]};
            for (size_t box = 1U; box < count; ++box) {
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    const size_t offset = box * 3U + axis;
                    global_minimum[axis] = std::min(
                        global_minimum[axis], minimum[offset]);
                    global_maximum[axis] = std::max(
                        global_maximum[axis], maximum[offset]);
                }
            }
            double widest_extent = global_maximum[0] - global_minimum[0];
            for (size_t axis = 1U; axis < 3U; ++axis) {
                const double extent = global_maximum[axis] - global_minimum[axis];
                if (extent > widest_extent) {
                    widest_extent = extent;
                    sweep_axis = axis;
                }
            }
        }

        std::vector<size_t> order(count);
        std::iota(order.begin(), order.end(), 0U);
        std::stable_sort(
            order.begin(), order.end(),
            [&](const size_t left, const size_t right) {
                const double left_minimum = minimum[left * 3U + sweep_axis];
                const double right_minimum = minimum[right * 3U + sweep_axis];
                return left_minimum < right_minimum
                    || (left_minimum == right_minimum && left < right);
            });

        std::vector<size_t> active;
        active.reserve(count);
        for (const size_t current : order) {
            const double current_minimum =
                minimum[current * 3U + sweep_axis] - epsilon;
            size_t kept = 0U;
            for (const size_t candidate : active) {
                if (maximum[candidate * 3U + sweep_axis] >= current_minimum) {
                    active[kept++] = candidate;
                }
            }
            active.resize(kept);

            for (const size_t candidate : active) {
                bool overlaps = true;
                for (size_t axis = 0U; axis < 3U; ++axis) {
                    const size_t candidate_offset = candidate * 3U + axis;
                    const size_t current_offset = current * 3U + axis;
                    if (maximum[candidate_offset]
                            < minimum[current_offset] - epsilon
                        || maximum[current_offset]
                            < minimum[candidate_offset] - epsilon) {
                        overlaps = false;
                        break;
                    }
                }
                if (overlaps) {
                    const size_t first = std::min(candidate, current);
                    const size_t second = std::max(candidate, current);
                    pairs.emplace_back(
                        static_cast<long long>(first),
                        static_cast<long long>(second));
                }
            }
            active.push_back(current);
        }
        std::sort(pairs.begin(), pairs.end());
    }

    py::array_t<long long> result({
        static_cast<py::ssize_t>(pairs.size()), static_cast<py::ssize_t>(2)});
    long long* const output = result.mutable_data();
    for (size_t index = 0U; index < pairs.size(); ++index) {
        output[index * 2U] = pairs[index].first;
        output[index * 2U + 1U] = pairs[index].second;
    }
    return result;
}

}  // namespace

PYBIND11_MODULE(native_metrics, m)
{
    m.doc() = "C++ metric kernels for AutoTessell NativeMeshChecker";
    py::class_<NativeFaceTopology>(m, "NativeFaceTopology")
        .def_property_readonly(
            "face_count", &NativeFaceTopology::face_count)
        .def_readonly("all_triangles", &NativeFaceTopology::all_triangles)
        .def_property_readonly(
            "indices",
            [](const NativeFaceTopology& topology) {
                return copy_index_vector(topology.indices);
            })
        .def_property_readonly(
            "offsets",
            [](const NativeFaceTopology& topology) {
                return copy_index_vector(topology.offsets);
            })
        .def("to_lists", &NativeFaceTopology::to_lists);
    m.def("parse_foam_faces_topology_file",
          &parse_foam_faces_topology_file, py::arg("path"));
    m.def("parse_foam_faces_file", &parse_foam_faces_file, py::arg("path"));
    m.def("parse_foam_labels_file", &parse_foam_labels_file, py::arg("path"));
    m.def("compute_face_geometry_topology", &compute_face_geometry_topology,
          py::arg("points"), py::arg("topology"));
    m.def("compute_face_geometry", &compute_face_geometry,
          py::arg("points"), py::arg("faces"));
    m.def("compute_cell_centres_from_vertices",
          &compute_cell_centres_from_vertices,
          py::arg("points"), py::arg("faces"), py::arg("owner"),
          py::arg("neighbour"), py::arg("n_cells"));
    m.def("compute_cell_centres_and_aspect_ratios",
          &compute_cell_centres_and_aspect_ratios,
          py::arg("points"), py::arg("faces"), py::arg("owner"),
          py::arg("neighbour"), py::arg("n_cells"));
    m.def("compute_cell_centres_and_aspect_ratios_topology",
          &compute_cell_centres_and_aspect_ratios_topology,
          py::arg("points"), py::arg("topology"), py::arg("owner"),
          py::arg("neighbour"), py::arg("n_cells"));
    m.def("compute_triangle_phase0_metrics_topology",
          &compute_triangle_phase0_metrics_topology,
          py::arg("points"), py::arg("topology"), py::arg("owner"),
          py::arg("neighbour"), py::arg("n_internal"),
          py::arg("cell_centres"), py::arg("face_centres"),
          py::arg("face_normals"), py::arg("face_areas"),
          py::arg("cell_volumes"));
    m.def("minimum_pairing_sum", &minimum_pairing_sum_array,
          py::arg("vectors"));
    m.def("compute_non_orthogonality", &compute_non_orthogonality,
          py::arg("face_centres"), py::arg("face_normals"),
          py::arg("cell_centres"), py::arg("owner"), py::arg("neighbour"),
          py::arg("n_internal"), py::arg("severe_threshold"));
    m.def("compute_skewness", &compute_skewness,
          py::arg("face_centres"), py::arg("cell_centres"),
          py::arg("owner"), py::arg("neighbour"), py::arg("n_internal"));
    m.def("compute_boundary_skewness", &compute_boundary_skewness,
          py::arg("face_centres"), py::arg("face_normals"),
          py::arg("cell_centres"), py::arg("owner"), py::arg("n_internal"));
    m.def("compute_face_weight_volume_ratio",
          &compute_face_weight_volume_ratio,
          py::arg("face_centres"), py::arg("face_area_vectors"),
          py::arg("cell_centres"), py::arg("owner"), py::arg("neighbour"),
          py::arg("cell_volumes"), py::arg("n_internal"));
    m.def("compute_cell_volumes", &compute_cell_volumes,
          py::arg("face_centres"), py::arg("face_normals"), py::arg("face_areas"),
          py::arg("cell_centres"), py::arg("owner"), py::arg("neighbour"),
          py::arg("n_cells"), py::arg("n_internal"));
    m.def("compute_oriented_cell_volume_audit",
          &compute_oriented_cell_volume_audit,
          py::arg("face_centres"), py::arg("face_normals"), py::arg("face_areas"),
          py::arg("cell_centres"), py::arg("owner"), py::arg("neighbour"),
          py::arg("n_cells"), py::arg("n_internal"));
    m.def("compute_per_cell_aspect_ratios", &compute_per_cell_aspect_ratios,
          py::arg("points"), py::arg("faces"), py::arg("owner"),
          py::arg("n_cells"));
    m.def("count_faces_not_upper_triangular",
          &count_faces_not_upper_triangular,
          py::arg("owner"), py::arg("neighbour"));
    m.def("validate_triangle_surface_and_build_edge_faces",
          &validate_triangle_surface_and_build_edge_faces,
          py::arg("vertices"), py::arg("triangles"));
    m.def("triangle_surface_topology_audit", &triangle_surface_topology_audit,
          py::arg("vertices").noconvert(), py::arg("faces").noconvert());
    m.def("prepare_quad_pairs", &prepare_quad_pairs,
          py::arg("vertices").noconvert(),
          py::arg("triangles").noconvert(),
          py::arg("wall_edges").noconvert(),
          py::arg("feature_angle_deg"));
    m.def("quad_dominant_transaction", &quad_dominant_transaction,
          py::arg("vertices").noconvert(),
          py::arg("triangles").noconvert(),
          py::arg("wall_edges").noconvert(),
          py::arg("feature_angle_deg"),
          py::arg("minimum_scaled_jacobian"),
          py::arg("maximum_aspect_ratio"),
          py::arg("maximum_warpage"));
    m.def("strict_quad_pair_preflight", &strict_quad_pair_preflight,
          py::arg("source_vertices").noconvert(),
          py::arg("candidate_vertices").noconvert(),
          py::arg("source_triangles").noconvert(),
          py::arg("candidate_triangles").noconvert(),
          py::arg("quads").noconvert(),
          py::arg("pair_provenance").noconvert(),
          py::arg("feature_edges").noconvert());
    m.def("estimate_triangle_curvature_sizing",
          &estimate_triangle_curvature_sizing,
          py::arg("vertices"), py::arg("triangles"), py::arg("epsilon"),
          py::arg("minimum_length") = py::none(),
          py::arg("maximum_length") = py::none());
    m.def("triangle_quality_batch", &triangle_quality_batch,
          py::arg("triangles").noconvert());
    m.def("triangle_flip_candidate_mask", &triangle_flip_candidate_mask,
          py::arg("vertices").noconvert(),
          py::arg("faces").noconvert(),
          py::arg("edges").noconvert());
    m.def("select_quad_pairs", &select_quad_pairs,
          py::arg("vertices").noconvert(),
          py::arg("triangles").noconvert(),
          py::arg("face_pairs").noconvert(),
          py::arg("minimum_scaled_jacobian"),
          py::arg("maximum_aspect_ratio"), py::arg("maximum_warpage"));
    m.def("aabb_overlap_pairs", &aabb_overlap_pairs,
          py::arg("aabb_min"), py::arg("aabb_max"),
          py::arg("epsilon") = 1e-12);
    m.def("triangle_intersections_segment", &triangle_intersections_segment,
          py::arg("vertices"), py::arg("triangles"),
          py::arg("candidates"), py::arg("epsilon") = 1e-12);
    m.def("triangle_intersections_interval", &triangle_intersections_interval,
          py::arg("vertices"), py::arg("triangles"),
          py::arg("candidates"), py::arg("epsilon") = 1e-10);
}
