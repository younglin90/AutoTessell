// Fast geometry kernels for AutoTessell's NativeMeshChecker.
//
// These bindings intentionally cover small, stable data-parallel kernels first:
// face centres/normals/areas and cell centres from unique vertices.  The Python
// checker keeps orchestration and fallback behaviour; this module removes the
// hottest Python list/set loops when the extension is available.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <bit>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <limits>
#include <numeric>
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
    py::array_t<double> areas({n_faces});

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
        {static_cast<py::ssize_t>(out_cells.size())});
    py::array_t<double> ratios(
        {static_cast<py::ssize_t>(out_ratios.size())});
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

double minimum_pairing_sum(const std::vector<Point3>& vectors)
{
    if (vectors.empty()) {
        return 0.0;
    }
    if (vectors.size() >= 64) {
        throw std::invalid_argument(
            "native triangle Phase-0 pairing supports fewer than 64 faces per cell");
    }
    std::vector<double> norms;
    norms.reserve(vectors.size());
    for (const auto& vector : vectors) {
        norms.push_back(norm3(vector));
    }
    std::unordered_map<std::uint64_t, double> memo;
    const auto solve = [&](auto&& self, std::uint64_t mask) -> double {
        if (mask == 0) {
            return 0.0;
        }
        if (const auto found = memo.find(mask); found != memo.end()) {
            return found->second;
        }
        const auto first = static_cast<size_t>(std::countr_zero(mask));
        const std::uint64_t first_bit = std::uint64_t{1} << first;
        const std::uint64_t rest = mask ^ first_bit;
        double best = norms[first] + self(self, rest);
        for (std::uint64_t remaining = rest; remaining != 0;) {
            const auto second = static_cast<size_t>(std::countr_zero(remaining));
            const std::uint64_t second_bit = std::uint64_t{1} << second;
            const Point3 pair{
                vectors[first][0] + vectors[second][0],
                vectors[first][1] + vectors[second][1],
                vectors[first][2] + vectors[second][2]};
            best = std::min(
                best, norm3(pair) + self(self, rest ^ second_bit));
            remaining ^= second_bit;
        }
        memo.emplace(mask, best);
        return best;
    };
    return solve(solve, (std::uint64_t{1} << vectors.size()) - 1);
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
        return py::make_tuple(py::array_t<double>({static_cast<py::ssize_t>(0)}), 0);
    }

    const auto fc = face_centres.unchecked<2>();
    const auto fn = face_normals.unchecked<2>();
    const auto fa = face_areas.unchecked<1>();
    const auto cc = cell_centres.unchecked<2>();
    const auto own = owner.unchecked<1>();
    const auto nbr = neighbour.unchecked<1>();

    py::array_t<double> volumes({static_cast<py::ssize_t>(n_cells)});
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
        {static_cast<py::ssize_t>(out_cells.size())});
    py::array_t<double> ratios(
        {static_cast<py::ssize_t>(out_ratios.size())});
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
        {static_cast<py::ssize_t>(values.size())});
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
    m.def("compute_per_cell_aspect_ratios", &compute_per_cell_aspect_ratios,
          py::arg("points"), py::arg("faces"), py::arg("owner"),
          py::arg("n_cells"));
    m.def("count_faces_not_upper_triangular",
          &count_faces_not_upper_triangular,
          py::arg("owner"), py::arg("neighbour"));
    m.def("validate_triangle_surface_and_build_edge_faces",
          &validate_triangle_surface_and_build_edge_faces,
          py::arg("vertices"), py::arg("triangles"));
    m.def("aabb_overlap_pairs", &aabb_overlap_pairs,
          py::arg("aabb_min"), py::arg("aabb_max"),
          py::arg("epsilon") = 1e-12);
}
