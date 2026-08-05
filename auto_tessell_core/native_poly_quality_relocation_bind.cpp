// Native Poly post-boundary-layer quality relocation.
//
// This kernel is deliberately conservative: it changes coordinates only, keeps
// every face/owner/neighbour entry untouched, locks all supplied boundary
// vertices, and returns the candidate to a Python transaction for the
// authoritative topology/provenance read-back. It is an opt-in operation; the
// default production path never calls it.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

namespace py = pybind11;

namespace {

using Point = std::array<double, 3>;
using Face = std::vector<long long>;

constexpr double kPi = 3.141592653589793238462643383279502884;

Point add(const Point& left, const Point& right)
{
    return Point{left[0] + right[0], left[1] + right[1], left[2] + right[2]};
}

Point subtract(const Point& left, const Point& right)
{
    return Point{left[0] - right[0], left[1] - right[1], left[2] - right[2]};
}

Point scale(const Point& value, const double factor)
{
    return Point{value[0] * factor, value[1] * factor, value[2] * factor};
}

double dot(const Point& left, const Point& right)
{
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

Point cross(const Point& left, const Point& right)
{
    return Point{
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0]};
}

double norm(const Point& value)
{
    return std::sqrt(dot(value, value));
}

Point mean_points(const std::vector<Point>& points, const std::vector<long long>& ids)
{
    Point result{0.0, 0.0, 0.0};
    if (ids.empty()) {
        return result;
    }
    for (const long long id : ids) {
        result = add(result, points[static_cast<std::size_t>(id)]);
    }
    return scale(result, 1.0 / static_cast<double>(ids.size()));
}

Point polygon_raw_normal(const std::vector<Point>& points, const Face& face)
{
    Point normal{0.0, 0.0, 0.0};
    const Point first = points[static_cast<std::size_t>(face.front())];
    for (std::size_t index = 1U; index + 1U < face.size(); ++index) {
        normal = add(normal, cross(
            subtract(points[static_cast<std::size_t>(face[index])], first),
            subtract(points[static_cast<std::size_t>(face[index + 1U])], first)));
    }
    return normal;
}

struct MeshInput {
    std::vector<Point> points;
    std::vector<Face> faces;
    std::vector<long long> owner;
    std::vector<long long> neighbour;
    std::vector<std::vector<long long>> cell_vertices;
    std::vector<std::vector<long long>> cell_faces;
    std::vector<std::vector<int>> cell_face_signs;
    std::vector<std::vector<long long>> vertex_cells;
    std::vector<std::vector<long long>> vertex_neighbours;
    std::vector<bool> locked;
    double scale = 1.0;
};

struct Metrics {
    double max_non_orthogonality = 0.0;
    double max_skewness = 0.0;
    double max_internal_skewness = 0.0;
    double max_boundary_skewness = 0.0;
    double max_aspect_ratio = 0.0;
    double min_pyramid_volume = 0.0;
    double min_signed_volume = 0.0;
    double min_signed_face_pyramid_volume = 0.0;
    double min_abs_pyramid_volume = 0.0;
    double min_abs_face_pyramid_volume = 0.0;
    long long min_signed_volume_cell = -1;
    long long min_signed_face_cell = -1;
    long long min_signed_face_id = -1;
    long long min_signed_face_fan = -1;
    long long max_non_orthogonality_face = -1;
    long long max_non_orthogonality_owner = -1;
    long long max_non_orthogonality_neighbour = -1;
    long long max_skewness_face = -1;
    bool max_skewness_is_boundary = false;
    long long max_internal_skewness_face = -1;
    long long max_boundary_skewness_face = -1;
    long long max_aspect_cell = -1;
};

py::dict metrics_dict(const Metrics& metrics)
{
    py::dict result;
    result["max_non_orthogonality_deg"] = metrics.max_non_orthogonality;
    result["max_skewness"] = metrics.max_skewness;
    result["max_internal_skewness"] = metrics.max_internal_skewness;
    result["max_boundary_skewness"] = metrics.max_boundary_skewness;
    result["max_aspect_ratio"] = metrics.max_aspect_ratio;
    result["min_pyramid_volume"] = metrics.min_pyramid_volume;
    result["min_signed_volume"] = metrics.min_signed_volume;
    result["min_signed_face_pyramid_volume"] = metrics.min_signed_face_pyramid_volume;
    result["min_abs_pyramid_volume"] = metrics.min_abs_pyramid_volume;
    result["min_abs_face_pyramid_volume"] = metrics.min_abs_face_pyramid_volume;
    result["min_signed_volume_cell"] = metrics.min_signed_volume_cell;
    result["min_signed_face_cell"] = metrics.min_signed_face_cell;
    result["min_signed_face_id"] = metrics.min_signed_face_id;
    result["min_signed_face_fan"] = metrics.min_signed_face_fan;
    result["max_non_orthogonality_face"] = metrics.max_non_orthogonality_face;
    result["max_non_orthogonality_owner"] = metrics.max_non_orthogonality_owner;
    result["max_non_orthogonality_neighbour"] = metrics.max_non_orthogonality_neighbour;
    result["max_skewness_face"] = metrics.max_skewness_face;
    result["max_skewness_is_boundary"] = metrics.max_skewness_is_boundary;
    result["max_internal_skewness_face"] = metrics.max_internal_skewness_face;
    result["max_boundary_skewness_face"] = metrics.max_boundary_skewness_face;
    result["max_aspect_cell"] = metrics.max_aspect_cell;
    return result;
}

std::vector<Point> load_points(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& input)
{
    if (input.ndim() != 2 || input.shape(1) != 3) {
        throw std::invalid_argument("points expects shape (N, 3)");
    }
    const auto view = input.unchecked<2>();
    std::vector<Point> points;
    points.reserve(static_cast<std::size_t>(view.shape(0)));
    for (py::ssize_t row = 0; row < view.shape(0); ++row) {
        Point point{};
        for (std::size_t coordinate = 0; coordinate < 3U; ++coordinate) {
            const double value = view(row, static_cast<py::ssize_t>(coordinate));
            if (!std::isfinite(value)) {
                throw std::invalid_argument("points must be finite");
            }
            point[coordinate] = value;
        }
        points.push_back(point);
    }
    return points;
}

std::vector<long long> load_vector(
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& input,
    const char* name)
{
    if (input.ndim() != 1) {
        throw std::invalid_argument(std::string(name) + " expects a one-dimensional array");
    }
    const auto view = input.unchecked<1>();
    std::vector<long long> values;
    values.reserve(static_cast<std::size_t>(view.shape(0)));
    for (py::ssize_t index = 0; index < view.shape(0); ++index) {
        values.push_back(view(index));
    }
    return values;
}

MeshInput load_mesh(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& flat_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& offsets_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& owner_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& neighbour_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& locked_array)
{
    MeshInput mesh;
    mesh.points = load_points(points_array);
    const std::vector<long long> flat = load_vector(flat_array, "face_vertices");
    const std::vector<long long> offsets = load_vector(offsets_array, "face_offsets");
    mesh.owner = load_vector(owner_array, "owner");
    mesh.neighbour = load_vector(neighbour_array, "neighbour");
    const std::vector<long long> locked_ids = load_vector(locked_array, "locked_vertices");

    if (offsets.empty() || offsets.front() != 0
        || offsets.back() != static_cast<long long>(flat.size())) {
        throw std::invalid_argument("face_offsets must start at zero and end at face_vertices length");
    }
    if (mesh.owner.size() + 1U != offsets.size()) {
        throw std::invalid_argument("owner and face_offsets lengths disagree");
    }
    if (mesh.neighbour.size() > mesh.owner.size()) {
        throw std::invalid_argument("neighbour cannot contain more entries than faces");
    }

    mesh.faces.reserve(mesh.owner.size());
    for (std::size_t face_index = 0; face_index < mesh.owner.size(); ++face_index) {
        const long long begin = offsets[face_index];
        const long long end = offsets[face_index + 1U];
        if (begin < 0 || end < begin || end > static_cast<long long>(flat.size())
            || end - begin < 3) {
            throw std::invalid_argument("face_offsets contains an invalid face");
        }
        Face face;
        face.reserve(static_cast<std::size_t>(end - begin));
        for (long long cursor = begin; cursor < end; ++cursor) {
            const long long vertex = flat[static_cast<std::size_t>(cursor)];
            if (vertex < 0 || vertex >= static_cast<long long>(mesh.points.size())) {
                throw std::invalid_argument("face vertex is out of range");
            }
            if (std::find(face.begin(), face.end(), vertex) != face.end()) {
                throw std::invalid_argument("face contains a duplicate vertex");
            }
            face.push_back(vertex);
        }
        mesh.faces.push_back(std::move(face));
    }

    std::vector<long long> cell_ids = mesh.owner;
    cell_ids.insert(cell_ids.end(), mesh.neighbour.begin(), mesh.neighbour.end());
    const long long max_cell = cell_ids.empty()
        ? -1
        : *std::max_element(cell_ids.begin(), cell_ids.end());
    if (max_cell < 0) {
        throw std::invalid_argument("mesh must contain at least one cell");
    }
    mesh.cell_vertices.resize(static_cast<std::size_t>(max_cell + 1));
    for (std::size_t face_index = 0; face_index < mesh.faces.size(); ++face_index) {
        const long long face_owner = mesh.owner[face_index];
        if (face_owner < 0 || face_owner > max_cell) {
            throw std::invalid_argument("owner cell is out of range");
        }
        auto& owner_vertices = mesh.cell_vertices[static_cast<std::size_t>(face_owner)];
        owner_vertices.insert(owner_vertices.end(), mesh.faces[face_index].begin(), mesh.faces[face_index].end());
        if (face_index < mesh.neighbour.size()) {
            const long long face_neighbour = mesh.neighbour[face_index];
            if (face_neighbour < 0 || face_neighbour > max_cell || face_neighbour == face_owner) {
                throw std::invalid_argument("neighbour cell is invalid");
            }
            auto& neighbour_vertices = mesh.cell_vertices[static_cast<std::size_t>(face_neighbour)];
            neighbour_vertices.insert(neighbour_vertices.end(), mesh.faces[face_index].begin(), mesh.faces[face_index].end());
        }
    }
    for (auto& vertices : mesh.cell_vertices) {
        std::sort(vertices.begin(), vertices.end());
        vertices.erase(std::unique(vertices.begin(), vertices.end()), vertices.end());
        if (vertices.size() < 4U) {
            throw std::invalid_argument("cell must contain at least four unique vertices");
        }
    }

    mesh.cell_faces.resize(mesh.cell_vertices.size());
    mesh.cell_face_signs.resize(mesh.cell_vertices.size());
    mesh.vertex_cells.resize(mesh.points.size());
    for (std::size_t face_index = 0; face_index < mesh.faces.size(); ++face_index) {
        const Face& face = mesh.faces[face_index];
        const long long face_owner = mesh.owner[face_index];
        mesh.cell_faces[static_cast<std::size_t>(face_owner)].push_back(
            static_cast<long long>(face_index));
        mesh.cell_face_signs[static_cast<std::size_t>(face_owner)].push_back(1);
        if (face_index < mesh.neighbour.size()) {
            mesh.cell_faces[static_cast<std::size_t>(mesh.neighbour[face_index])].push_back(
                static_cast<long long>(face_index));
            mesh.cell_face_signs[static_cast<std::size_t>(mesh.neighbour[face_index])].push_back(-1);
        }
        for (const long long vertex : face) {
            mesh.vertex_cells[static_cast<std::size_t>(vertex)].push_back(face_owner);
            if (face_index < mesh.neighbour.size()) {
                mesh.vertex_cells[static_cast<std::size_t>(vertex)].push_back(
                    mesh.neighbour[face_index]);
            }
        }
    }
    for (auto& faces : mesh.cell_faces) {
        std::sort(faces.begin(), faces.end());
        faces.erase(std::unique(faces.begin(), faces.end()), faces.end());
    }
    // Prefer a geometry-derived outward sign for each cell-face.  Some legacy
    // Poly corpora have valid topology but inconsistent raw face winding, so
    // owner/neighbour signs remain only the degenerate-face fallback.
    for (std::size_t cell = 0U; cell < mesh.cell_faces.size(); ++cell) {
        const Point cell_centre = mean_points(mesh.points, mesh.cell_vertices[cell]);
        auto& signs = mesh.cell_face_signs[cell];
        signs.resize(mesh.cell_faces[cell].size(), 1);
        for (std::size_t local_face = 0U; local_face < mesh.cell_faces[cell].size(); ++local_face) {
            const long long face_id = mesh.cell_faces[cell][local_face];
            const Face& face = mesh.faces[static_cast<std::size_t>(face_id)];
            const Point face_centre = mean_points(mesh.points, face);
            const Point raw_normal = polygon_raw_normal(mesh.points, face);
            const double alignment = dot(raw_normal, subtract(face_centre, cell_centre));
            if (std::abs(alignment) > mesh.scale * mesh.scale * 1e-24) {
                signs[local_face] = alignment >= 0.0 ? 1 : -1;
            } else if (face_id < static_cast<long long>(mesh.neighbour.size())
                       && mesh.neighbour[static_cast<std::size_t>(face_id)] == static_cast<long long>(cell)) {
                signs[local_face] = -1;
            } else {
                signs[local_face] = 1;
            }
        }
    }
    for (auto& cells : mesh.vertex_cells) {
        std::sort(cells.begin(), cells.end());
        cells.erase(std::unique(cells.begin(), cells.end()), cells.end());
    }

    mesh.vertex_neighbours.resize(mesh.points.size());
    for (const Face& face : mesh.faces) {
        for (const long long vertex : face) {
            auto& neighbours = mesh.vertex_neighbours[static_cast<std::size_t>(vertex)];
            neighbours.insert(neighbours.end(), face.begin(), face.end());
        }
    }
    for (std::size_t vertex = 0; vertex < mesh.vertex_neighbours.size(); ++vertex) {
        auto& neighbours = mesh.vertex_neighbours[vertex];
        neighbours.erase(std::remove(neighbours.begin(), neighbours.end(), static_cast<long long>(vertex)), neighbours.end());
        std::sort(neighbours.begin(), neighbours.end());
        neighbours.erase(std::unique(neighbours.begin(), neighbours.end()), neighbours.end());
    }

    mesh.locked.assign(mesh.points.size(), false);
    for (const long long vertex : locked_ids) {
        if (vertex < 0 || vertex >= static_cast<long long>(mesh.points.size())) {
            throw std::invalid_argument("locked vertex is out of range");
        }
        mesh.locked[static_cast<std::size_t>(vertex)] = true;
    }
    Point lower = mesh.points.front();
    Point upper = mesh.points.front();
    for (const Point& point : mesh.points) {
        for (std::size_t coordinate = 0; coordinate < 3U; ++coordinate) {
            lower[coordinate] = std::min(lower[coordinate], point[coordinate]);
            upper[coordinate] = std::max(upper[coordinate], point[coordinate]);
        }
    }
    mesh.scale = std::max(norm(subtract(upper, lower)), 1e-12);
    return mesh;
}

double face_area(const std::vector<Point>& points, const Face& face, const Point& centre, Point* normal)
{
    Point area_vector{0.0, 0.0, 0.0};
    double area = 0.0;
    const Point first = points[static_cast<std::size_t>(face.front())];
    for (std::size_t index = 1U; index + 1U < face.size(); ++index) {
        const Point left = subtract(points[static_cast<std::size_t>(face[index])], first);
        const Point right = subtract(points[static_cast<std::size_t>(face[index + 1U])], first);
        area += 0.5 * norm(cross(left, right));
    }
    for (std::size_t index = 0U; index < face.size(); ++index) {
        const Point left = subtract(points[static_cast<std::size_t>(face[index])], centre);
        const Point right = subtract(points[static_cast<std::size_t>(face[(index + 1U) % face.size()])], centre);
        area_vector = add(area_vector, cross(left, right));
    }
    if (normal != nullptr) {
        *normal = area_vector;
    }
    return area;
}

double cell_signed_pyramid_volume(
    const std::vector<Point>& points,
    const std::vector<Face>& faces,
    const std::vector<std::vector<long long>>& cell_faces,
    const std::vector<std::vector<int>>& cell_face_signs,
    const Point& centre,
    const std::size_t cell)
{
    double volume = 0.0;
    const auto& faces_for_cell = cell_faces[cell];
    const auto& signs_for_cell = cell_face_signs[cell];
    if (faces_for_cell.size() != signs_for_cell.size()) {
        return -std::numeric_limits<double>::infinity();
    }
    for (std::size_t local_face = 0U; local_face < faces_for_cell.size(); ++local_face) {
        const long long face_id = faces_for_cell[local_face];
        const Face& face = faces[static_cast<std::size_t>(face_id)];
        const Point first = points[static_cast<std::size_t>(face.front())];
        const double orientation = static_cast<double>(signs_for_cell[local_face]);
        for (std::size_t index = 1U; index + 1U < face.size(); ++index) {
            const Point left = subtract(first, centre);
            const Point middle = subtract(points[static_cast<std::size_t>(face[index])], centre);
            const Point right = subtract(points[static_cast<std::size_t>(face[index + 1U])], centre);
            volume += orientation * dot(left, cross(middle, right)) / 6.0;
        }
    }
    return volume;
}

struct FacePyramidWitness {
    double value = std::numeric_limits<double>::infinity();
    long long face_id = -1;
    long long fan_index = -1;
};

FacePyramidWitness cell_min_signed_face_pyramid_witness(
    const std::vector<Point>& points,
    const std::vector<Face>& faces,
    const std::vector<std::vector<long long>>& cell_faces,
    const std::vector<std::vector<int>>& cell_face_signs,
    const Point& centre,
    const std::size_t cell)
{
    FacePyramidWitness witness;
    const auto& faces_for_cell = cell_faces[cell];
    const auto& signs_for_cell = cell_face_signs[cell];
    if (faces_for_cell.size() != signs_for_cell.size()) {
        witness.value = -std::numeric_limits<double>::infinity();
        return witness;
    }
    for (std::size_t local_face = 0U; local_face < faces_for_cell.size(); ++local_face) {
        const long long face_id = faces_for_cell[local_face];
        const Face& face = faces[static_cast<std::size_t>(face_id)];
        const Point first = points[static_cast<std::size_t>(face.front())];
        const double orientation = static_cast<double>(signs_for_cell[local_face]);
        for (std::size_t index = 1U; index + 1U < face.size(); ++index) {
            const Point left = subtract(first, centre);
            const Point middle = subtract(points[static_cast<std::size_t>(face[index])], centre);
            const Point right = subtract(points[static_cast<std::size_t>(face[index + 1U])], centre);
            const double value = orientation * dot(left, cross(middle, right)) / 6.0;
            if (value < witness.value
                || (value == witness.value
                    && (face_id < witness.face_id || witness.face_id < 0))) {
                witness.value = value;
                witness.face_id = face_id;
                witness.fan_index = static_cast<long long>(index - 1U);
            }
        }
    }
    return witness;
}

double cell_abs_pyramid_volume(
    const std::vector<Point>& points,
    const std::vector<Face>& faces,
    const std::vector<std::vector<long long>>& cell_faces,
    const Point& centre,
    const std::size_t cell)
{
    double volume = 0.0;
    for (const long long face_id : cell_faces[cell]) {
        const Face& face = faces[static_cast<std::size_t>(face_id)];
        const Point first = points[static_cast<std::size_t>(face.front())];
        for (std::size_t index = 1U; index + 1U < face.size(); ++index) {
            const Point left = subtract(first, centre);
            const Point middle = subtract(points[static_cast<std::size_t>(face[index])], centre);
            const Point right = subtract(points[static_cast<std::size_t>(face[index + 1U])], centre);
            volume += std::abs(dot(left, cross(middle, right))) / 6.0;
        }
    }
    return volume;
}

double cell_min_abs_face_pyramid_volume(
    const std::vector<Point>& points,
    const std::vector<Face>& faces,
    const std::vector<std::vector<long long>>& cell_faces,
    const Point& centre,
    const std::size_t cell)
{
    double minimum = std::numeric_limits<double>::infinity();
    for (const long long face_id : cell_faces[cell]) {
        const Face& face = faces[static_cast<std::size_t>(face_id)];
        const Point first = points[static_cast<std::size_t>(face.front())];
        for (std::size_t index = 1U; index + 1U < face.size(); ++index) {
            const Point left = subtract(first, centre);
            const Point middle = subtract(points[static_cast<std::size_t>(face[index])], centre);
            const Point right = subtract(points[static_cast<std::size_t>(face[index + 1U])], centre);
            minimum = std::min(
                minimum, std::abs(dot(left, cross(middle, right))) / 6.0);
        }
    }
    return minimum;
}

bool local_candidate_positive(
    const MeshInput& mesh,
    const std::vector<Point>& points,
    const std::size_t vertex)
{
    const double minimum = mesh.scale * mesh.scale * mesh.scale * 1e-14;
    for (const long long cell_id : mesh.vertex_cells[vertex]) {
        const std::size_t cell = static_cast<std::size_t>(cell_id);
        const Point centre = mean_points(points, mesh.cell_vertices[cell]);
        const double absolute_cell = cell_abs_pyramid_volume(
            points, mesh.faces, mesh.cell_faces, centre, cell);
        const double absolute_face_min = cell_min_abs_face_pyramid_volume(
            points, mesh.faces, mesh.cell_faces, centre, cell);
        if (!(absolute_cell > minimum && absolute_face_min > minimum)) {
            return false;
        }
    }
    return true;
}

Metrics compute_metrics(const MeshInput& mesh, const std::vector<Point>& points)
{
    std::vector<Point> cell_centres(mesh.cell_vertices.size());
    for (std::size_t cell = 0; cell < mesh.cell_vertices.size(); ++cell) {
        cell_centres[cell] = mean_points(points, mesh.cell_vertices[cell]);
    }

    const auto& cell_faces = mesh.cell_faces;
    const auto& cell_face_signs = mesh.cell_face_signs;

    Metrics metrics;
    metrics.min_pyramid_volume = std::numeric_limits<double>::infinity();
    metrics.min_signed_volume = std::numeric_limits<double>::infinity();
    metrics.min_signed_face_pyramid_volume = std::numeric_limits<double>::infinity();
    metrics.min_abs_pyramid_volume = std::numeric_limits<double>::infinity();
    metrics.min_abs_face_pyramid_volume = std::numeric_limits<double>::infinity();
    for (std::size_t cell = 0; cell < mesh.cell_vertices.size(); ++cell) {
        // Match NativeMeshChecker's authority contract: aspect vertices are
        // collected from owner faces only; neighbour faces are not counted a
        // second time for the owner cell's aspect witness.
        std::vector<long long> aspect_vertices;
        for (const long long face_id : mesh.cell_faces[cell]) {
            if (mesh.owner[static_cast<std::size_t>(face_id)] != static_cast<long long>(cell)) {
                continue;
            }
            for (const long long vertex : mesh.faces[static_cast<std::size_t>(face_id)]) {
                if (std::find(aspect_vertices.begin(), aspect_vertices.end(), vertex) == aspect_vertices.end()) {
                    aspect_vertices.push_back(vertex);
                }
            }
        }
        const auto& vertices = aspect_vertices;
        double min_separation = std::numeric_limits<double>::infinity();
        double max_separation = 0.0;
        for (std::size_t first = 0U; first < vertices.size(); ++first) {
            for (std::size_t second = first + 1U; second < vertices.size(); ++second) {
                const double separation = norm(subtract(
                    points[static_cast<std::size_t>(vertices[first])],
                    points[static_cast<std::size_t>(vertices[second])]));
                if (separation > 1e-30) {
                    min_separation = std::min(min_separation, separation);
                    max_separation = std::max(max_separation, separation);
                }
            }
        }
        const double aspect = max_separation / std::max(min_separation, 1e-30);
        if (aspect > metrics.max_aspect_ratio) {
            metrics.max_aspect_ratio = aspect;
            metrics.max_aspect_cell = static_cast<long long>(cell);
        }
        const double signed_volume = cell_signed_pyramid_volume(
            points, mesh.faces, cell_faces, cell_face_signs, cell_centres[cell], cell);
        const FacePyramidWitness face_witness = cell_min_signed_face_pyramid_witness(
            points, mesh.faces, cell_faces, cell_face_signs, cell_centres[cell], cell);
        const double signed_face_min = face_witness.value;
        const double absolute_volume = cell_abs_pyramid_volume(
            points, mesh.faces, cell_faces, cell_centres[cell], cell);
        const double absolute_face_min = cell_min_abs_face_pyramid_volume(
            points, mesh.faces, cell_faces, cell_centres[cell], cell);
        metrics.min_abs_pyramid_volume = std::min(
            metrics.min_abs_pyramid_volume, absolute_volume);
        metrics.min_abs_face_pyramid_volume = std::min(
            metrics.min_abs_face_pyramid_volume, absolute_face_min);
        if (signed_volume < metrics.min_pyramid_volume) {
            metrics.min_pyramid_volume = signed_volume;
        }
        if (signed_face_min < metrics.min_signed_face_pyramid_volume
            || (signed_face_min == metrics.min_signed_face_pyramid_volume
                && (face_witness.face_id < metrics.min_signed_face_id
                    || metrics.min_signed_face_id < 0))) {
            metrics.min_signed_face_pyramid_volume = signed_face_min;
            metrics.min_signed_face_cell = static_cast<long long>(cell);
            metrics.min_signed_face_id = face_witness.face_id;
            metrics.min_signed_face_fan = face_witness.fan_index;
        }
        if (signed_volume < metrics.min_signed_volume
            || (signed_volume == metrics.min_signed_volume
                && static_cast<long long>(cell) < metrics.min_signed_volume_cell)) {
            metrics.min_signed_volume = signed_volume;
            metrics.min_signed_volume_cell = static_cast<long long>(cell);
        }
        if (signed_face_min < metrics.min_signed_volume) {
            metrics.min_signed_volume = signed_face_min;
            metrics.min_signed_face_cell = static_cast<long long>(cell);
            metrics.min_signed_face_id = face_witness.face_id;
            metrics.min_signed_face_fan = face_witness.fan_index;
        }
    }

    for (std::size_t face_index = 0; face_index < mesh.faces.size(); ++face_index) {
        const Face& face = mesh.faces[face_index];
        const Point face_centre = mean_points(points, face);
        Point normal{};
        const double area = face_area(points, face, face_centre, &normal);
        const double normal_length = norm(normal);
        const bool is_internal = face_index < mesh.neighbour.size();
        const long long face_owner = mesh.owner[face_index];
        const Point owner_to_face = subtract(face_centre, cell_centres[static_cast<std::size_t>(face_owner)]);
        if (area <= 1e-30 || normal_length <= 1e-30) {
            metrics.max_skewness = std::numeric_limits<double>::infinity();
            if (is_internal) {
                metrics.max_non_orthogonality = 180.0;
                metrics.max_internal_skewness = std::numeric_limits<double>::infinity();
                metrics.max_internal_skewness_face = static_cast<long long>(face_index);
            } else {
                metrics.max_boundary_skewness = std::numeric_limits<double>::infinity();
                metrics.max_boundary_skewness_face = static_cast<long long>(face_index);
            }
            continue;
        }
        if (!is_internal) {
            const Point unit_normal = scale(normal, 1.0 / normal_length);
            const double normal_distance = dot(owner_to_face, unit_normal);
            const Point projection = add(
                cell_centres[static_cast<std::size_t>(face_owner)],
                scale(unit_normal, normal_distance));
            const double boundary_skew = norm(subtract(face_centre, projection))
                / std::max(std::abs(normal_distance), 1e-30);
            if (boundary_skew > metrics.max_boundary_skewness) {
                metrics.max_boundary_skewness = boundary_skew;
                metrics.max_boundary_skewness_face = static_cast<long long>(face_index);
            }
            continue;
        }
        const long long face_neighbour = mesh.neighbour[face_index];
        const Point centre_axis = subtract(
            cell_centres[static_cast<std::size_t>(face_neighbour)],
            cell_centres[static_cast<std::size_t>(face_owner)]);
        const double axis_length = norm(centre_axis);
        if (axis_length <= 1e-30) {
            metrics.max_non_orthogonality = 180.0;
            metrics.max_internal_skewness = std::numeric_limits<double>::infinity();
            metrics.max_internal_skewness_face = static_cast<long long>(face_index);
            continue;
        }
        const double cosine = std::clamp(std::abs(dot(scale(centre_axis, 1.0 / axis_length),
            scale(normal, 1.0 / normal_length))), 0.0, 1.0);
        const double non_orthogonality = std::acos(cosine) * 180.0 / kPi;
        if (non_orthogonality > metrics.max_non_orthogonality) {
            metrics.max_non_orthogonality = non_orthogonality;
            metrics.max_non_orthogonality_face = static_cast<long long>(face_index);
            metrics.max_non_orthogonality_owner = face_owner;
            metrics.max_non_orthogonality_neighbour = face_neighbour;
        }
        const double axis_square = dot(centre_axis, centre_axis);
        const double parameter = dot(owner_to_face, centre_axis) / axis_square;
        const Point intersection = add(
            cell_centres[static_cast<std::size_t>(face_owner)],
            scale(centre_axis, parameter));
        const double internal_skew = norm(subtract(intersection, face_centre))
            / axis_length;
        if (internal_skew > metrics.max_internal_skewness) {
            metrics.max_internal_skewness = internal_skew;
            metrics.max_internal_skewness_face = static_cast<long long>(face_index);
        }
    }
    if (metrics.max_internal_skewness >= metrics.max_boundary_skewness) {
        metrics.max_skewness = metrics.max_internal_skewness;
        metrics.max_skewness_face = metrics.max_internal_skewness_face;
        metrics.max_skewness_is_boundary = false;
    } else {
        metrics.max_skewness = metrics.max_boundary_skewness;
        metrics.max_skewness_face = metrics.max_boundary_skewness_face;
        metrics.max_skewness_is_boundary = true;
    }
    if (!std::isfinite(metrics.min_pyramid_volume)) {
        metrics.min_pyramid_volume = 0.0;
    }
    if (!std::isfinite(metrics.min_signed_volume)) {
        metrics.min_signed_volume = 0.0;
    }
    if (!std::isfinite(metrics.min_signed_face_pyramid_volume)) {
        metrics.min_signed_face_pyramid_volume = 0.0;
    }
    if (!std::isfinite(metrics.min_abs_pyramid_volume)) {
        metrics.min_abs_pyramid_volume = 0.0;
    }
    if (!std::isfinite(metrics.min_abs_face_pyramid_volume)) {
        metrics.min_abs_face_pyramid_volume = 0.0;
    }
    return metrics;
}

py::dict owner_winding_witness(
    const MeshInput& mesh,
    const std::vector<Point>& points,
    const Metrics& oriented)
{
    const double minimum = mesh.scale * mesh.scale * mesh.scale * 1e-14;
    long long negative_face_pyramids = 0;
    long long negative_cells = 0;
    long long first_cell = -1;
    long long first_face = -1;
    long long first_fan = -1;
    for (std::size_t cell = 0U; cell < mesh.cell_faces.size(); ++cell) {
        const Point centre = mean_points(points, mesh.cell_vertices[cell]);
        double raw_cell = 0.0;
        bool cell_negative = false;
        for (const long long face_id : mesh.cell_faces[cell]) {
            const Face& face = mesh.faces[static_cast<std::size_t>(face_id)];
            const Point first = points[static_cast<std::size_t>(face.front())];
            const int sign = (
                face_id < static_cast<long long>(mesh.neighbour.size())
                && mesh.neighbour[static_cast<std::size_t>(face_id)]
                    == static_cast<long long>(cell)) ? -1 : 1;
            for (std::size_t index = 1U; index + 1U < face.size(); ++index) {
                const Point left = subtract(first, centre);
                const Point middle = subtract(points[static_cast<std::size_t>(face[index])], centre);
                const Point right = subtract(points[static_cast<std::size_t>(face[index + 1U])], centre);
                const double value = static_cast<double>(sign)
                    * dot(left, cross(middle, right)) / 6.0;
                raw_cell += value;
                if (value <= minimum) {
                    ++negative_face_pyramids;
                    cell_negative = true;
                    if (first_face < 0 || face_id < first_face) {
                        first_cell = static_cast<long long>(cell);
                        first_face = face_id;
                        first_fan = static_cast<long long>(index - 1U);
                    }
                }
            }
        }
        if (raw_cell <= minimum || cell_negative) {
            ++negative_cells;
        }
    }
    py::dict result;
    result["negative_face_pyramids"] = negative_face_pyramids;
    result["negative_cells"] = negative_cells;
    result["first_cell"] = first_cell;
    result["first_face"] = first_face;
    result["first_fan"] = first_fan;
    result["owner_winding_only"] = (
        negative_face_pyramids > 0
        && oriented.min_signed_volume > minimum
        && oriented.min_signed_face_pyramid_volume > minimum);
    return result;
}

double normalized_quality_score(const Metrics& metrics)
{
    constexpr double non_ortho_limit = 50.0;
    constexpr double skewness_limit = 0.50;
    constexpr double aspect_limit = 20.0;
    return std::max({
        metrics.max_non_orthogonality / non_ortho_limit,
        metrics.max_skewness / skewness_limit,
        metrics.max_aspect_ratio / aspect_limit});
}

bool filtered_quality_improvement(const Metrics& before, const Metrics& after)
{
    constexpr double epsilon = 1e-12;
    if (after.max_non_orthogonality > before.max_non_orthogonality + epsilon
        || after.max_skewness > before.max_skewness + epsilon
        || after.max_aspect_ratio > before.max_aspect_ratio + epsilon) {
        return false;
    }
    const double before_score = normalized_quality_score(before);
    const double after_score = normalized_quality_score(after);
    if (after_score + epsilon < before_score) {
        return true;
    }
    return after.max_non_orthogonality + epsilon < before.max_non_orthogonality
        || after.max_skewness + epsilon < before.max_skewness
        || after.max_aspect_ratio + epsilon < before.max_aspect_ratio;
}

bool quality_candidate_preferred(const Metrics& incumbent, const Metrics& challenger)
{
    constexpr double epsilon = 1e-12;
    if (challenger.max_non_orthogonality + epsilon < incumbent.max_non_orthogonality) {
        return true;
    }
    if (challenger.max_non_orthogonality > incumbent.max_non_orthogonality + epsilon) {
        return false;
    }
    if (challenger.max_skewness + epsilon < incumbent.max_skewness) {
        return true;
    }
    if (challenger.max_skewness > incumbent.max_skewness + epsilon) {
        return false;
    }
    if (challenger.max_aspect_ratio + epsilon < incumbent.max_aspect_ratio) {
        return true;
    }
    if (challenger.max_aspect_ratio > incumbent.max_aspect_ratio + epsilon) {
        return false;
    }
    return normalized_quality_score(challenger) + epsilon
        < normalized_quality_score(incumbent);
}

Point local_principal_direction(
    const MeshInput& mesh,
    const std::vector<Point>& points,
    const std::size_t vertex)
{
    const auto& neighbours = mesh.vertex_neighbours[vertex];
    double best_distance = 0.0;
    Point direction{0.0, 0.0, 0.0};
    for (std::size_t first = 0U; first < neighbours.size(); ++first) {
        for (std::size_t second = first + 1U; second < neighbours.size(); ++second) {
            const Point candidate = subtract(
                points[static_cast<std::size_t>(neighbours[second])],
                points[static_cast<std::size_t>(neighbours[first])]);
            const double distance = norm(candidate);
            if (distance > best_distance) {
                best_distance = distance;
                direction = scale(candidate, 1.0 / distance);
            }
        }
    }
    return direction;
}

struct BlockMove {
    long long vertex = -1;
    Point delta{0.0, 0.0, 0.0};
};

struct BlockMovePlan {
    std::vector<BlockMove> moves;
    long long face_id = -1;
    long long cell_id = -1;
    std::string objective;
};

std::vector<long long> unique_sorted_vertices(
    const std::vector<long long>& input)
{
    std::vector<long long> result = input;
    std::sort(result.begin(), result.end());
    result.erase(std::unique(result.begin(), result.end()), result.end());
    return result;
}

void add_exclusive_cell_group(
    const MeshInput& mesh,
    const std::vector<Point>& points,
    const std::size_t cell,
    const std::unordered_set<long long>& shared,
    const Point& centre_delta,
    std::unordered_set<long long>& selected,
    BlockMovePlan& plan)
{
    if (cell >= mesh.cell_vertices.size()) {
        (void)points;
        return;
    }
    const std::vector<long long> cell_vertices = unique_sorted_vertices(mesh.cell_vertices[cell]);
    std::vector<long long> free_vertices;
    for (const long long vertex : cell_vertices) {
        if (shared.find(vertex) == shared.end()
            && !mesh.locked[static_cast<std::size_t>(vertex)]) {
            free_vertices.push_back(vertex);
        }
    }
    constexpr std::size_t max_group_vertices = 8U;
    if (free_vertices.size() > max_group_vertices) {
        free_vertices.resize(max_group_vertices);
    }
    if (free_vertices.empty() || cell_vertices.empty()) {
        return;
    }
    const double centre_fraction = static_cast<double>(free_vertices.size())
        / static_cast<double>(cell_vertices.size());
    const Point per_vertex_delta = scale(
        centre_delta, 1.0 / std::max(centre_fraction, 1e-12));
    for (const long long vertex : free_vertices) {
        if (selected.insert(vertex).second) {
            plan.moves.push_back(BlockMove{vertex, per_vertex_delta});
        }
    }
}

BlockMovePlan make_quality_block_plan(
    const MeshInput& mesh,
    const std::vector<Point>& points,
    const Metrics& metrics,
    const bool focus_non_orthogonality)
{
    constexpr double non_ortho_limit = 50.0;
    constexpr double skewness_limit = 0.50;
    constexpr double aspect_limit = 20.0;
    const double non_ortho_score = metrics.max_non_orthogonality / non_ortho_limit;
    const double skew_score = metrics.max_skewness / skewness_limit;
    const double aspect_score = metrics.max_aspect_ratio / aspect_limit;
    BlockMovePlan plan;
    std::unordered_set<long long> selected;

    if (focus_non_orthogonality
        && metrics.max_non_orthogonality_face >= 0
        && metrics.max_non_orthogonality_face < static_cast<long long>(mesh.faces.size())
        && metrics.max_non_orthogonality_face < static_cast<long long>(mesh.neighbour.size())) {
        const long long face_id = metrics.max_non_orthogonality_face;
        const Face& face = mesh.faces[static_cast<std::size_t>(face_id)];
        const long long owner = mesh.owner[static_cast<std::size_t>(face_id)];
        const long long neighbour = mesh.neighbour[static_cast<std::size_t>(face_id)];
        Point normal{};
        const double area = face_area(points, face, mean_points(points, face), &normal);
        const Point owner_centre = mean_points(points, mesh.cell_vertices[static_cast<std::size_t>(owner)]);
        const Point neighbour_centre = mean_points(points, mesh.cell_vertices[static_cast<std::size_t>(neighbour)]);
        const Point axis = subtract(neighbour_centre, owner_centre);
        const double axis_length = norm(axis);
        if (area > 1e-30 && norm(normal) > 1e-30 && axis_length > 1e-30) {
            const Point unit_normal = scale(normal, 1.0 / norm(normal));
            const Point tangent = subtract(axis, scale(unit_normal, dot(axis, unit_normal)));
            const std::unordered_set<long long> shared(face.begin(), face.end());
            add_exclusive_cell_group(mesh, points, static_cast<std::size_t>(owner), shared,
                scale(tangent, 0.5), selected, plan);
            add_exclusive_cell_group(mesh, points, static_cast<std::size_t>(neighbour), shared,
                scale(tangent, -0.5), selected, plan);
            plan.objective = "focused_non_orthogonality_offender_block";
            plan.face_id = face_id;
            plan.cell_id = owner;
        }
        return plan;
    }

    if (skew_score >= non_ortho_score && skew_score >= aspect_score
        && metrics.max_skewness_face >= 0
        && metrics.max_skewness_face < static_cast<long long>(mesh.faces.size())) {
        const long long face_id = metrics.max_skewness_face;
        const Face& face = mesh.faces[static_cast<std::size_t>(face_id)];
        const long long owner = mesh.owner[static_cast<std::size_t>(face_id)];
        const Point face_centre = mean_points(points, face);
        Point normal{};
        const double area = face_area(points, face, face_centre, &normal);
        if (area > 1e-30 && norm(normal) > 1e-30) {
            const std::unordered_set<long long> shared(face.begin(), face.end());
            if (metrics.max_skewness_is_boundary) {
                const Point owner_centre = mean_points(points, mesh.cell_vertices[static_cast<std::size_t>(owner)]);
                const Point unit_normal = scale(normal, 1.0 / norm(normal));
                const double normal_distance = dot(subtract(face_centre, owner_centre), unit_normal);
                const Point projection = add(owner_centre, scale(unit_normal, normal_distance));
                const Point tangent_residual = subtract(face_centre, projection);
                add_exclusive_cell_group(mesh, points, static_cast<std::size_t>(owner), shared,
                    tangent_residual, selected, plan);
                plan.objective = "boundary_skew_offender_block";
                plan.face_id = face_id;
                plan.cell_id = owner;
            } else if (face_id < static_cast<long long>(mesh.neighbour.size())) {
                const long long neighbour = mesh.neighbour[static_cast<std::size_t>(face_id)];
                const Point owner_centre = mean_points(points, mesh.cell_vertices[static_cast<std::size_t>(owner)]);
                const Point neighbour_centre = mean_points(points, mesh.cell_vertices[static_cast<std::size_t>(neighbour)]);
                const Point axis = subtract(neighbour_centre, owner_centre);
                const double axis_square = dot(axis, axis);
                if (axis_square > 1e-30) {
                    const double parameter = dot(subtract(face_centre, owner_centre), axis) / axis_square;
                    const Point intersection = add(owner_centre, scale(axis, parameter));
                    const Point residual = subtract(face_centre, intersection);
                    add_exclusive_cell_group(mesh, points, static_cast<std::size_t>(owner), shared,
                        scale(residual, 0.5), selected, plan);
                    add_exclusive_cell_group(mesh, points, static_cast<std::size_t>(neighbour), shared,
                        scale(residual, 0.5), selected, plan);
                    plan.objective = "internal_skew_offender_block";
                    plan.face_id = face_id;
                    plan.cell_id = owner;
                }
            }
        }
    } else if (non_ortho_score >= aspect_score
               && metrics.max_non_orthogonality_face >= 0
               && metrics.max_non_orthogonality_face < static_cast<long long>(mesh.faces.size())
               && metrics.max_non_orthogonality_face < static_cast<long long>(mesh.neighbour.size())) {
        const long long face_id = metrics.max_non_orthogonality_face;
        const Face& face = mesh.faces[static_cast<std::size_t>(face_id)];
        const long long owner = mesh.owner[static_cast<std::size_t>(face_id)];
        const long long neighbour = mesh.neighbour[static_cast<std::size_t>(face_id)];
        Point normal{};
        const double area = face_area(points, face, mean_points(points, face), &normal);
        const Point owner_centre = mean_points(points, mesh.cell_vertices[static_cast<std::size_t>(owner)]);
        const Point neighbour_centre = mean_points(points, mesh.cell_vertices[static_cast<std::size_t>(neighbour)]);
        const Point axis = subtract(neighbour_centre, owner_centre);
        const double axis_length = norm(axis);
        if (area > 1e-30 && norm(normal) > 1e-30 && axis_length > 1e-30) {
            const Point unit_normal = scale(normal, 1.0 / norm(normal));
            const Point tangent = subtract(axis, scale(unit_normal, dot(axis, unit_normal)));
            const std::unordered_set<long long> shared(face.begin(), face.end());
            add_exclusive_cell_group(mesh, points, static_cast<std::size_t>(owner), shared,
                scale(tangent, 0.5), selected, plan);
            add_exclusive_cell_group(mesh, points, static_cast<std::size_t>(neighbour), shared,
                scale(tangent, -0.5), selected, plan);
            plan.objective = "non_orthogonality_offender_block";
            plan.face_id = face_id;
            plan.cell_id = owner;
        }
    } else if (metrics.max_aspect_cell >= 0
               && metrics.max_aspect_cell < static_cast<long long>(mesh.cell_vertices.size())) {
        const std::size_t cell = static_cast<std::size_t>(metrics.max_aspect_cell);
        const std::vector<long long> vertices = unique_sorted_vertices(mesh.cell_vertices[cell]);
        const Point centre = mean_points(points, vertices);
        for (const long long vertex : vertices) {
            if (!mesh.locked[static_cast<std::size_t>(vertex)]) {
                plan.moves.push_back(BlockMove{vertex,
                    scale(subtract(centre, points[static_cast<std::size_t>(vertex)]), 0.2)});
            }
        }
        plan.objective = "aspect_offender_block";
        plan.cell_id = static_cast<long long>(cell);
    }
    return plan;
}
py::array_t<double> make_points_array(const std::vector<Point>& points)
{
    py::array_t<double> result(py::array::ShapeContainer{
        static_cast<py::ssize_t>(points.size()), py::ssize_t{3}});
    auto view = result.mutable_unchecked<2>();
    for (std::size_t row = 0U; row < points.size(); ++row) {
        for (std::size_t coordinate = 0U; coordinate < 3U; ++coordinate) {
            view(static_cast<py::ssize_t>(row), static_cast<py::ssize_t>(coordinate)) = points[row][coordinate];
        }
    }
    return result;
}

py::dict relocate_poly_quality(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array_input,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& face_vertices,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& face_offsets,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& owner,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& neighbour,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& locked_vertices,
    const int iterations,
    const double relax,
    const double max_move,
    const bool focus_non_orthogonality)
{
    if (iterations < 0 || iterations > 64) {
        throw std::invalid_argument("iterations must be in [0, 64]");
    }
    if (!std::isfinite(relax) || relax < 0.0 || relax > 1.0) {
        throw std::invalid_argument("relax must be in [0, 1]");
    }
    if (!std::isfinite(max_move) || max_move < 0.0) {
        throw std::invalid_argument("max_move must be non-negative");
    }
    MeshInput mesh = load_mesh(
        points_array_input, face_vertices, face_offsets, owner, neighbour, locked_vertices);
    const Metrics before = compute_metrics(mesh, mesh.points);
    std::vector<Point> candidate = mesh.points;
    long long moved_vertices = 0;
    double maximum_displacement = 0.0;
    const std::array<double, 5> step_fractions{1.0, 0.5, 0.25, 0.125, 0.0625};
    long long local_step_rejections = 0;
    long long block_step_attempts = 0;
    long long block_step_rejections = 0;
    long long accepted_block_move_count = 0;
    std::string last_block_objective;
    long long last_block_face_id = -1;
    long long last_block_cell_id = -1;
    for (int iteration = 0; iteration < iterations; ++iteration) {
        Metrics current_metrics = compute_metrics(mesh, candidate);
        const BlockMovePlan block_plan = make_quality_block_plan(
            mesh, candidate, current_metrics, focus_non_orthogonality);
        if (!block_plan.moves.empty()) {
            last_block_objective = block_plan.objective;
            last_block_face_id = block_plan.face_id;
            last_block_cell_id = block_plan.cell_id;
            bool found_block_candidate = false;
            std::vector<Point> best_block_trial = candidate;
            Metrics best_block_metrics = current_metrics;
            const std::array<double, 4> block_step_fractions{1.0, 0.5, 0.25, 0.125};
            for (const double fraction : block_step_fractions) {
                ++block_step_attempts;
                std::vector<Point> trial = candidate;
                for (const BlockMove& move : block_plan.moves) {
                    Point delta = scale(move.delta, relax * fraction);
                    const double displacement = norm(delta);
                    if (max_move > 0.0 && displacement > max_move) {
                        delta = scale(delta, max_move / displacement);
                    }
                    trial[static_cast<std::size_t>(move.vertex)] = add(
                        candidate[static_cast<std::size_t>(move.vertex)], delta);
                }
                bool positive = true;
                for (const BlockMove& move : block_plan.moves) {
                    if (!local_candidate_positive(
                            mesh, trial, static_cast<std::size_t>(move.vertex))) {
                        positive = false;
                        break;
                    }
                }
                if (!positive) {
                    ++block_step_rejections;
                    continue;
                }
                const Metrics trial_metrics = compute_metrics(mesh, trial);
                if (!filtered_quality_improvement(current_metrics, trial_metrics)) {
                    ++block_step_rejections;
                    continue;
                }
                if (!found_block_candidate
                    || quality_candidate_preferred(best_block_metrics, trial_metrics)) {
                    best_block_trial = std::move(trial);
                    best_block_metrics = trial_metrics;
                    found_block_candidate = true;
                }
            }
            if (found_block_candidate) {
                candidate.swap(best_block_trial);
                current_metrics = best_block_metrics;
                accepted_block_move_count += static_cast<long long>(block_plan.moves.size());
            }
        }
        for (std::size_t vertex = 0U; vertex < candidate.size(); ++vertex) {
            if (mesh.locked[vertex] || mesh.vertex_neighbours[vertex].empty()
                || mesh.vertex_cells[vertex].empty()) {
                continue;
            }
            const Point target_delta = subtract(
                mean_points(candidate, mesh.vertex_neighbours[vertex]), candidate[vertex]);
            const double target_length = norm(target_delta);
            std::vector<Point> directions;
            if (target_length > 1e-30) {
                directions.push_back(scale(target_delta, 1.0 / target_length));
            }
            const Point principal = local_principal_direction(mesh, candidate, vertex);
            if (norm(principal) > 1e-30) {
                directions.push_back(principal);
                directions.push_back(scale(principal, -1.0));
            }
            bool found_candidate = false;
            std::vector<Point> best_trial = candidate;
            Metrics best_metrics = current_metrics;
            for (const Point& direction : directions) {
                const double base_length = std::max(target_length, mesh.scale * 1e-6);
                for (const double fraction : step_fractions) {
                    Point delta = scale(direction, relax * base_length * fraction);
                    const double displacement = norm(delta);
                    if (max_move > 0.0 && displacement > max_move) {
                        delta = scale(delta, max_move / displacement);
                    }
                    std::vector<Point> trial = candidate;
                    trial[vertex] = add(candidate[vertex], delta);
                    if (!local_candidate_positive(mesh, trial, vertex)) {
                        ++local_step_rejections;
                        continue;
                    }
                    const Metrics trial_metrics = compute_metrics(mesh, trial);
                    if (!filtered_quality_improvement(current_metrics, trial_metrics)) {
                        ++local_step_rejections;
                        continue;
                    }
                    if (!found_candidate || quality_candidate_preferred(best_metrics, trial_metrics)) {
                        best_trial = std::move(trial);
                        best_metrics = trial_metrics;
                        found_candidate = true;
                    }
                }
            }
            if (found_candidate) {
                candidate.swap(best_trial);
                current_metrics = best_metrics;
            }
        }
    }
    for (std::size_t vertex = 0U; vertex < candidate.size(); ++vertex) {
        const double displacement = norm(subtract(candidate[vertex], mesh.points[vertex]));
        maximum_displacement = std::max(maximum_displacement, displacement);
        if (displacement > 0.0) {
            ++moved_vertices;
        }
    }
    const Metrics after = compute_metrics(mesh, candidate);
    const double volume_floor = mesh.scale * mesh.scale * mesh.scale * 1e-14;
    const bool positive = after.min_signed_volume > volume_floor;
    const bool authority_aligned_valid = (
        after.min_abs_pyramid_volume > volume_floor
        && after.min_abs_face_pyramid_volume > volume_floor);
    const bool quality_improved = filtered_quality_improvement(before, after);
    const bool improved = quality_improved;

    py::dict result;
    result["accepted"] = improved;
    result["reason"] = improved
        ? py::str(positive ? "strict_quality_improvement"
                           : "quality_improvement_pending_signed_topology")
        : py::str(positive ? "no_strict_quality_improvement" : "nonpositive_signed_volume");
    result["points"] = make_points_array(candidate);
    result["metrics_before"] = metrics_dict(before);
    result["metrics_after"] = metrics_dict(after);
    py::dict worst_witness;
    worst_witness["before"] = metrics_dict(before);
    worst_witness["after"] = metrics_dict(after);
    worst_witness["owner_winding_before"] = owner_winding_witness(mesh, mesh.points, before);
    worst_witness["owner_winding_after"] = owner_winding_witness(mesh, candidate, after);
    py::dict authority_orientation;
    authority_orientation["min_abs_pyramid_before"] = before.min_abs_pyramid_volume;
    authority_orientation["min_abs_pyramid_after"] = after.min_abs_pyramid_volume;
    authority_orientation["min_abs_face_pyramid_before"] = before.min_abs_face_pyramid_volume;
    authority_orientation["min_abs_face_pyramid_after"] = after.min_abs_face_pyramid_volume;
    authority_orientation["owner_winding_before"] = owner_winding_witness(mesh, mesh.points, before);
    authority_orientation["owner_winding_after"] = owner_winding_witness(mesh, candidate, after);
    result["authority_orientation_witness"] = authority_orientation;
    py::dict mixed_fan_geometry;
    mixed_fan_geometry["min_signed_face_before"] = before.min_signed_face_pyramid_volume;
    mixed_fan_geometry["min_signed_face_after"] = after.min_signed_face_pyramid_volume;
    mixed_fan_geometry["min_signed_face_cell_after"] = after.min_signed_face_cell;
    mixed_fan_geometry["min_signed_face_id_after"] = after.min_signed_face_id;
    mixed_fan_geometry["min_signed_face_fan_after"] = after.min_signed_face_fan;
    result["mixed_fan_geometry_witness"] = mixed_fan_geometry;
    result["worst_witness"] = worst_witness;
    result["moved_vertex_count"] = moved_vertices;
    result["max_displacement"] = maximum_displacement;
    result["locked_vertex_count"] = static_cast<long long>(
        std::count(mesh.locked.begin(), mesh.locked.end(), true));
    result["topology_input_valid"] = true;
    result["boundary_vertices_locked"] = true;
    result["signed_volume_barrier"] = true;
    result["signed_topology_valid"] = positive;
    result["authority_aligned_valid"] = authority_aligned_valid;
    result["quality_improved"] = quality_improved;
    result["quality_score_before"] = normalized_quality_score(before);
    result["quality_score_after"] = normalized_quality_score(after);
    py::dict orientation_cache;
    orientation_cache["primary"] = "geometry_outward_face_centroid";
    orientation_cache["owner_fallback_sign"] = 1;
    orientation_cache["neighbour_fallback_sign"] = -1;
    result["orientation_cache"] = orientation_cache;
    py::dict adjacency;
    adjacency["cell_count"] = static_cast<long long>(mesh.cell_faces.size());
    adjacency["face_count"] = static_cast<long long>(mesh.faces.size());
    long long vertex_cell_links = 0;
    for (const auto& cells : mesh.vertex_cells) {
        vertex_cell_links += static_cast<long long>(cells.size());
    }
    adjacency["vertex_cell_links"] = vertex_cell_links;
    adjacency["cached"] = true;
    result["adjacency_cache"] = adjacency;
    result["local_step_rejections"] = local_step_rejections;
    result["block_step_attempts"] = block_step_attempts;
    result["block_step_rejections"] = block_step_rejections;
    result["accepted_block_move_count"] = accepted_block_move_count;
    result["last_block_objective"] = last_block_objective;
    result["last_block_face_id"] = last_block_face_id;
    result["last_block_cell_id"] = last_block_cell_id;
    result["focus_non_orthogonality"] = focus_non_orthogonality;
    result["focus_face_id_before"] = before.max_non_orthogonality_face;
    result["focus_face_id_after"] = after.max_non_orthogonality_face;
    result["focus_non_orthogonality_before"] = before.max_non_orthogonality;
    result["focus_non_orthogonality_after"] = after.max_non_orthogonality;
    py::list local_steps;
    for (const double step : step_fractions) {
        local_steps.append(step);
    }
    result["local_repair_step_fractions"] = local_steps;
    result["iterations"] = iterations;
    result["relax"] = relax;
    result["max_move"] = max_move;
    return result;
}

}  // namespace

PYBIND11_MODULE(native_poly_quality_relocation, module)
{
    module.doc() = "Fail-closed C++23 Native Poly quality relocation kernel";
    module.def(
        "relocate_poly_quality",
        &relocate_poly_quality,
        py::arg("points"), py::arg("face_vertices"), py::arg("face_offsets"),
        py::arg("owner"), py::arg("neighbour"), py::arg("locked_vertices"),
        py::arg("iterations") = 1, py::arg("relax") = 0.001,
        py::arg("max_move") = 0.0, py::arg("focus_non_orthogonality") = false);
}
