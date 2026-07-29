// Native one-layer padding for axis-aligned 3-D surface meshes.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace py = pybind11;
using namespace pybind11::literals;

namespace {

using Point = std::array<double, 3>;
using Face = std::vector<long long>;
using Cell = std::vector<Face>;

Point subtract(const Point& left, const Point& right)
{
    return {left[0] - right[0], left[1] - right[1], left[2] - right[2]};
}

double dot(const Point& left, const Point& right)
{
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

Point newell_normal(const std::vector<Point>& points)
{
    Point normal{0.0, 0.0, 0.0};
    for (size_t index = 0; index < points.size(); ++index) {
        const Point& point = points[index];
        const Point& next = points[(index + 1U) % points.size()];
        normal[0] += (point[1] - next[1]) * (point[2] + next[2]);
        normal[1] += (point[2] - next[2]) * (point[0] + next[0]);
        normal[2] += (point[0] - next[0]) * (point[1] + next[1]);
    }
    return normal;
}

double squared_norm(const Point& value)
{
    return dot(value, value);
}

std::vector<Point> face_points(const std::vector<Point>& vertices, const Face& face)
{
    std::vector<Point> result;
    result.reserve(face.size());
    for (const long long index : face) {
        result.push_back(vertices[static_cast<size_t>(index)]);
    }
    return result;
}

Cell orient_outward(const std::vector<Point>& vertices, Cell faces)
{
    Point center{0.0, 0.0, 0.0};
    std::vector<bool> used(vertices.size(), false);
    size_t n_used = 0;
    for (const Face& face : faces) {
        for (const long long index : face) {
            if (!used[static_cast<size_t>(index)]) {
                used[static_cast<size_t>(index)] = true;
                const Point& point = vertices[static_cast<size_t>(index)];
                center[0] += point[0];
                center[1] += point[1];
                center[2] += point[2];
                ++n_used;
            }
        }
    }
    center[0] /= static_cast<double>(n_used);
    center[1] /= static_cast<double>(n_used);
    center[2] /= static_cast<double>(n_used);

    for (Face& face : faces) {
        const std::vector<Point> points = face_points(vertices, face);
        const Point normal = newell_normal(points);
        if (squared_norm(normal) <= 1e-28) {
            throw std::invalid_argument("surface has a degenerate zero-area face");
        }
        Point face_center{0.0, 0.0, 0.0};
        for (const Point& point : points) {
            face_center[0] += point[0];
            face_center[1] += point[1];
            face_center[2] += point[2];
        }
        const double inverse_size = 1.0 / static_cast<double>(points.size());
        face_center[0] *= inverse_size;
        face_center[1] *= inverse_size;
        face_center[2] *= inverse_size;
        if (dot(normal, subtract(face_center, center)) < 0.0) {
            std::reverse(face.begin(), face.end());
        }
    }
    return faces;
}

py::dict pad_surface(
    py::array_t<double, py::array::c_style | py::array::forcecast> vertices_array,
    const std::vector<Face>& source_faces,
    int direction,
    double tolerance)
{
    const py::buffer_info info = vertices_array.request();
    if (info.ndim != 2 || info.shape[1] != 3 || info.shape[0] < 3) {
        throw std::invalid_argument("vertices must have shape (N, 3) with N >= 3");
    }
    if (direction != -1 && direction != 1) {
        throw std::invalid_argument("direction must be exactly +1 or -1");
    }
    if (!std::isfinite(tolerance) || tolerance <= 0.0) {
        throw std::invalid_argument("tolerance must be a finite positive value");
    }
    if (source_faces.empty()) {
        throw std::invalid_argument("faces must contain at least one triangle or quadrilateral");
    }

    const auto n_vertices = static_cast<size_t>(info.shape[0]);
    const double* raw = static_cast<const double*>(info.ptr);
    std::vector<Point> source_vertices(n_vertices);
    Point minima{raw[0], raw[1], raw[2]};
    Point maxima = minima;
    for (size_t index = 0; index < n_vertices; ++index) {
        Point point{raw[3U * index], raw[3U * index + 1U], raw[3U * index + 2U]};
        for (size_t axis = 0; axis < 3; ++axis) {
            if (!std::isfinite(point[axis])) {
                throw std::invalid_argument("vertices must contain only finite coordinates");
            }
            minima[axis] = std::min(minima[axis], point[axis]);
            maxima[axis] = std::max(maxima[axis], point[axis]);
        }
        source_vertices[index] = point;
    }

    int normal_axis = -1;
    int n_constant = 0;
    int n_varying = 0;
    for (int axis = 0; axis < 3; ++axis) {
        if (maxima[axis] - minima[axis] <= tolerance) {
            normal_axis = axis;
            ++n_constant;
        } else {
            ++n_varying;
        }
    }
    if (n_constant != 1 || n_varying != 2) {
        throw std::invalid_argument(
            "surface must lie on exactly one axis-aligned plane (xy, xz, or yz) within tolerance");
    }

    std::vector<std::pair<long long, long long>> edges;
    int n_triangles = 0;
    int n_quads = 0;
    for (size_t face_index = 0; face_index < source_faces.size(); ++face_index) {
        const Face& face = source_faces[face_index];
        if (face.size() != 3U && face.size() != 4U) {
            throw std::invalid_argument("each face must be a triangle or quadrilateral");
        }
        if (face.size() == 3U) {
            ++n_triangles;
        } else {
            ++n_quads;
        }
        Face sorted = face;
        std::sort(sorted.begin(), sorted.end());
        if (std::adjacent_find(sorted.begin(), sorted.end()) != sorted.end()) {
            throw std::invalid_argument("surface face has duplicate vertex indices");
        }
        for (const long long index : face) {
            if (index < 0 || static_cast<size_t>(index) >= n_vertices) {
                throw py::index_error("surface face has a vertex index outside vertices");
            }
        }
        const std::vector<Point> points = face_points(source_vertices, face);
        if (squared_norm(newell_normal(points)) <= 1e-28) {
            throw std::invalid_argument("surface has a degenerate zero-area face");
        }
        for (size_t index = 0; index < face.size(); ++index) {
            const long long begin = face[index];
            const long long end = face[(index + 1U) % face.size()];
            edges.emplace_back(std::min(begin, end), std::max(begin, end));
        }
    }
    std::sort(edges.begin(), edges.end());
    edges.erase(std::unique(edges.begin(), edges.end()), edges.end());
    double total_length = 0.0;
    for (const auto [begin, end] : edges) {
        const Point delta = subtract(
            source_vertices[static_cast<size_t>(end)], source_vertices[static_cast<size_t>(begin)]);
        const double length = std::sqrt(squared_norm(delta));
        if (!std::isfinite(length) || length <= 0.0) {
            throw std::invalid_argument("surface has a zero-length or invalid edge");
        }
        total_length += length;
    }
    const double thickness = total_length / static_cast<double>(edges.size());

    std::vector<Point> vertices = source_vertices;
    vertices.reserve(n_vertices * 2U);
    for (Point point : source_vertices) {
        point[static_cast<size_t>(normal_axis)] += static_cast<double>(direction) * thickness;
        vertices.push_back(point);
    }

    std::vector<Cell> cells;
    cells.reserve(source_faces.size());
    for (const Face& face : source_faces) {
        Face top;
        top.reserve(face.size());
        for (const long long index : face) {
            top.push_back(index + static_cast<long long>(n_vertices));
        }
        Cell cell{face, top};
        for (size_t index = 0; index < face.size(); ++index) {
            cell.push_back({
                face[index], face[(index + 1U) % face.size()],
                top[(index + 1U) % face.size()], top[index],
            });
        }
        cells.push_back(orient_outward(vertices, std::move(cell)));
    }

    py::array_t<double> output(py::array::ShapeContainer{
        static_cast<py::ssize_t>(vertices.size()), static_cast<py::ssize_t>(3),
    });
    auto output_view = output.mutable_unchecked<2>();
    for (size_t index = 0; index < vertices.size(); ++index) {
        for (size_t axis = 0; axis < 3; ++axis) {
            output_view(static_cast<py::ssize_t>(index), static_cast<py::ssize_t>(axis)) = vertices[index][axis];
        }
    }
    py::list py_cells;
    for (const Cell& cell : cells) {
        py::list py_cell;
        for (const Face& face : cell) {
            py_cell.append(face);
        }
        py_cells.append(py_cell);
    }
    const std::array<const char*, 3> axis_names{"x", "y", "z"};
    const std::array<const char*, 3> plane_names{"yz", "xz", "xy"};
    py::dict report;
    report["normal_axis"] = axis_names[static_cast<size_t>(normal_axis)];
    report["plane"] = plane_names[static_cast<size_t>(normal_axis)];
    report["direction"] = direction;
    report["padding_thickness"] = thickness;
    report["source_tri_faces"] = n_triangles;
    report["source_quad_faces"] = n_quads;
    report["prism_cells"] = n_triangles;
    report["hex_cells"] = n_quads;
    return py::dict("vertices"_a = output, "cell_faces"_a = py_cells, "report"_a = report);
}

}  // namespace

PYBIND11_MODULE(native_surface_padding, module)
{
    module.doc() = "Native axis-aligned planar surface padding kernel";
    module.def("pad_axis_aligned_surface_to_volume", &pad_surface,
        py::arg("vertices"), py::arg("faces"), py::arg("direction") = 1,
        py::arg("tolerance") = 1e-9);
}
