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
#include <cctype>
#include <cmath>
#include <fstream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_set>
#include <utility>
#include <vector>

namespace py = pybind11;

namespace {

using Point3 = std::array<double, 3>;

std::string strip_foam_comments_and_strings(std::string_view text)
{
    enum class State { normal, line_comment, block_comment, quoted };

    std::string clean;
    clean.reserve(text.size());
    State state = State::normal;
    char quote = '\0';
    bool escaped = false;

    for (size_t i = 0; i < text.size(); ++i) {
        const char ch = text[i];
        const char next = i + 1 < text.size() ? text[i + 1] : '\0';

        if (state == State::line_comment) {
            if (ch == '\n') {
                clean.push_back('\n');
                state = State::normal;
            } else {
                clean.push_back(' ');
            }
            continue;
        }
        if (state == State::block_comment) {
            clean.push_back(ch == '\n' ? '\n' : ' ');
            if (ch == '*' && next == '/') {
                clean.push_back(' ');
                ++i;
                state = State::normal;
            }
            continue;
        }
        if (state == State::quoted) {
            clean.push_back(ch == '\n' ? '\n' : ' ');
            if (escaped) {
                escaped = false;
            } else if (ch == '\\') {
                escaped = true;
            } else if (ch == quote) {
                state = State::normal;
            }
            continue;
        }

        if (ch == '/' && next == '/') {
            clean.append("  ");
            ++i;
            state = State::line_comment;
        } else if (ch == '/' && next == '*') {
            clean.append("  ");
            ++i;
            state = State::block_comment;
        } else if (ch == '\'' || ch == '"') {
            clean.push_back(' ');
            quote = ch;
            escaped = false;
            state = State::quoted;
        } else {
            clean.push_back(ch);
        }
    }

    if (state == State::block_comment) {
        throw std::invalid_argument("unterminated block comment in faces file");
    }
    if (state == State::quoted) {
        throw std::invalid_argument("unterminated quoted string in faces file");
    }
    return clean;
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
        throw std::invalid_argument("expected signed integer in faces file");
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
            throw std::invalid_argument("integer out of range in faces file");
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

void skip_whitespace(std::string_view text, size_t& pos)
{
    while (pos < text.size()
           && std::isspace(static_cast<unsigned char>(text[pos]))) {
        ++pos;
    }
}

std::pair<long long, size_t> find_face_list(std::string_view text)
{
    for (size_t pos = 0; pos < text.size(); ++pos) {
        const char ch = text[pos];
        const bool has_sign = ch == '+' || ch == '-';
        if (!std::isdigit(static_cast<unsigned char>(ch))
            && !(has_sign && pos + 1 < text.size()
                 && std::isdigit(static_cast<unsigned char>(text[pos + 1])))) {
            continue;
        }
        if (pos > 0 && !is_integer_boundary(text[pos - 1])) {
            continue;
        }

        size_t end = pos + (has_sign ? 1U : 0U);
        while (end < text.size()
               && std::isdigit(static_cast<unsigned char>(text[end]))) {
            ++end;
        }
        if (end < text.size() && !is_integer_boundary(text[end])) {
            continue;
        }
        size_t opening = end;
        skip_whitespace(text, opening);
        if (opening >= text.size() || text[opening] != '(') {
            pos = end - 1;
            continue;
        }

        size_t parse_pos = pos;
        const long long count = parse_signed_integer(text, parse_pos);
        if (count < 0) {
            throw std::invalid_argument("face-list count must be non-negative");
        }
        return {count, opening + 1};
    }
    throw std::invalid_argument("missing face list in faces file");
}

std::vector<std::vector<long long>> parse_foam_faces_text(std::string_view text)
{
    const std::string clean = strip_foam_comments_and_strings(text);
    const auto [face_count, list_start] = find_face_list(clean);
    if (static_cast<unsigned long long>(face_count) > clean.size()) {
        throw std::invalid_argument("face-list count exceeds file size");
    }

    std::vector<std::vector<long long>> faces;
    faces.reserve(static_cast<size_t>(face_count));
    size_t pos = list_start;
    for (long long face_i = 0; face_i < face_count; ++face_i) {
        skip_whitespace(clean, pos);
        const long long vertex_count = parse_signed_integer(clean, pos);
        if (vertex_count < 0) {
            throw std::invalid_argument("face vertex count must be non-negative");
        }
        if (static_cast<unsigned long long>(vertex_count) > clean.size()) {
            throw std::invalid_argument("face vertex count exceeds file size");
        }
        skip_whitespace(clean, pos);
        if (pos >= clean.size() || clean[pos] != '(') {
            throw std::invalid_argument("expected '(' after face vertex count");
        }
        ++pos;

        std::vector<long long> vertices;
        vertices.reserve(static_cast<size_t>(vertex_count));
        for (long long vertex_i = 0; vertex_i < vertex_count; ++vertex_i) {
            skip_whitespace(clean, pos);
            vertices.push_back(parse_signed_integer(clean, pos));
        }
        skip_whitespace(clean, pos);
        if (pos >= clean.size() || clean[pos] != ')') {
            throw std::invalid_argument("face vertex count does not match list");
        }
        ++pos;
        faces.push_back(std::move(vertices));
    }

    skip_whitespace(clean, pos);
    if (pos >= clean.size() || clean[pos] != ')') {
        throw std::invalid_argument("face-list count does not match list");
    }
    ++pos;
    skip_whitespace(clean, pos);
    if (pos < clean.size() && clean[pos] == ';') {
        ++pos;
        skip_whitespace(clean, pos);
    }
    if (pos != clean.size()) {
        throw std::invalid_argument("unexpected trailing data after face list");
    }
    return faces;
}

std::vector<std::vector<long long>> parse_foam_faces_file(const py::object& path)
{
    const std::string filename =
        py::module_::import("os").attr("fspath")(path).cast<std::string>();
    std::vector<std::vector<long long>> faces;
    {
        py::gil_scoped_release release;
        std::ifstream input(filename, std::ios::binary);
        if (!input) {
            throw std::runtime_error("unable to open faces file: " + filename);
        }
        const std::string text{
            std::istreambuf_iterator<char>(input),
            std::istreambuf_iterator<char>()};
        if (input.bad()) {
            throw std::runtime_error("unable to read faces file: " + filename);
        }
        faces = parse_foam_faces_text(text);
    }
    return faces;
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

double dot_arr(
    const py::detail::unchecked_reference<double, 2>& arr_a,
    py::ssize_t ia,
    const py::detail::unchecked_reference<double, 2>& arr_b,
    py::ssize_t ib)
{
    return (
        arr_a(ia, 0) * arr_b(ib, 0)
        + arr_a(ia, 1) * arr_b(ib, 1)
        + arr_a(ia, 2) * arr_b(ib, 2));
}

double norm3(double x, double y, double z)
{
    return std::sqrt(x * x + y * y + z * z);
}

py::tuple compute_face_geometry(
    py::array_t<double, py::array::c_style | py::array::forcecast> points,
    py::sequence faces)
{
    const auto pts = points.unchecked<2>();
    if (pts.ndim() != 2 || pts.shape(1) != 3) {
        throw std::invalid_argument("points must have shape (N, 3)");
    }

    const auto n_points = static_cast<long long>(pts.shape(0));
    const auto n_faces = static_cast<py::ssize_t>(faces.size());

    py::array_t<double> centres({n_faces, static_cast<py::ssize_t>(3)});
    py::array_t<double> normals({n_faces, static_cast<py::ssize_t>(3)});
    py::array_t<double> areas({n_faces});

    auto c = centres.mutable_unchecked<2>();
    auto n = normals.mutable_unchecked<2>();
    auto a = areas.mutable_unchecked<1>();

    for (py::ssize_t face_i = 0; face_i < n_faces; ++face_i) {
        py::sequence face = faces[face_i].cast<py::sequence>();
        const auto k = static_cast<py::ssize_t>(face.size());

        double cx = 0.0;
        double cy = 0.0;
        double cz = 0.0;
        std::vector<long long> idxs;
        idxs.reserve(static_cast<size_t>(k));

        for (py::ssize_t j = 0; j < k; ++j) {
            const auto idx = as_vertex_index(face[j], n_points);
            idxs.push_back(idx);
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

        const Point3 p0 = point_at(pts, idxs[0]);
        Point3 area_vec{0.0, 0.0, 0.0};

        for (py::ssize_t j = 1; j + 1 < k; ++j) {
            const Point3 p1 = point_at(pts, idxs[static_cast<size_t>(j)]);
            const Point3 p2 = point_at(pts, idxs[static_cast<size_t>(j + 1)]);
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

    return py::make_tuple(centres, normals, areas);
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
    const auto fc = face_centres.unchecked<2>();
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

}  // namespace

PYBIND11_MODULE(native_metrics, m)
{
    m.doc() = "C++ metric kernels for AutoTessell NativeMeshChecker";
    m.def("parse_foam_faces_file", &parse_foam_faces_file, py::arg("path"));
    m.def("compute_face_geometry", &compute_face_geometry,
          py::arg("points"), py::arg("faces"));
    m.def("compute_cell_centres_from_vertices",
          &compute_cell_centres_from_vertices,
          py::arg("points"), py::arg("faces"), py::arg("owner"),
          py::arg("neighbour"), py::arg("n_cells"));
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
    m.def("compute_cell_volumes", &compute_cell_volumes,
          py::arg("face_centres"), py::arg("face_normals"), py::arg("face_areas"),
          py::arg("cell_centres"), py::arg("owner"), py::arg("neighbour"),
          py::arg("n_cells"), py::arg("n_internal"));
    m.def("compute_per_cell_aspect_ratios", &compute_per_cell_aspect_ratios,
          py::arg("points"), py::arg("faces"), py::arg("owner"),
          py::arg("n_cells"));
}
