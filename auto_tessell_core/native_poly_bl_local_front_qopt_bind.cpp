// Native Poly local boundary-layer front feasibility kernel.
//
// The kernel proposes deterministic per-wall-vertex layer scales.  It never
// edits topology or source points.  Python remains the authority boundary and
// must re-run strict topology, provenance, and canonical quality gates before
// publishing the candidate.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
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

Point cross(const Point& left, const Point& right)
{
    return Point{
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0]};
}

double dot(const Point& left, const Point& right)
{
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
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

std::vector<Point> load_points(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& input,
    const char* name)
{
    if (input.ndim() != 2 || input.shape(1) != 3) {
        throw std::invalid_argument(std::string(name) + " expects shape (N, 3)");
    }
    const auto view = input.unchecked<2>();
    std::vector<Point> points;
    points.reserve(static_cast<std::size_t>(view.shape(0)));
    for (py::ssize_t row = 0; row < view.shape(0); ++row) {
        Point point{};
        for (std::size_t coordinate = 0U; coordinate < 3U; ++coordinate) {
            point[coordinate] = view(row, static_cast<py::ssize_t>(coordinate));
            if (!std::isfinite(point[coordinate])) {
                throw std::invalid_argument(std::string(name) + " must be finite");
            }
        }
        points.push_back(point);
    }
    if (points.empty()) {
        throw std::invalid_argument(std::string(name) + " must not be empty");
    }
    return points;
}

std::vector<long long> load_vector(
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& input,
    const char* name)
{
    if (input.ndim() != 1) {
        throw std::invalid_argument(std::string(name) + " expects one dimension");
    }
    const auto view = input.unchecked<1>();
    std::vector<long long> values;
    values.reserve(static_cast<std::size_t>(view.shape(0)));
    for (py::ssize_t index = 0; index < view.shape(0); ++index) {
        values.push_back(view(index));
    }
    return values;
}

struct Mapping {
    long long base_vertex = -1;
    long long layer_point = -1;
    Point delta{0.0, 0.0, 0.0};
    double alpha = 1.0;
};

struct Mesh {
    std::vector<Face> faces;
    std::vector<long long> owner;
    std::vector<long long> neighbour;
    std::vector<std::vector<long long>> cell_vertices;
    std::vector<std::vector<long long>> owner_faces;
    std::vector<Mapping> mappings;
    int base_cell_count = 0;
};

Mesh load_mesh(
    const std::vector<Point>& original,
    const std::vector<Point>& candidate,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& flat_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& offsets_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& owner_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& neighbour_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& base_vertices,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& layer_points,
    const int base_cell_count)
{
    Mesh mesh;
    const std::vector<long long> flat = load_vector(flat_array, "face_vertices");
    const std::vector<long long> offsets = load_vector(offsets_array, "face_offsets");
    mesh.owner = load_vector(owner_array, "owner");
    mesh.neighbour = load_vector(neighbour_array, "neighbour");
    const std::vector<long long> base_ids = load_vector(base_vertices, "base_vertices");
    const std::vector<long long> layer_ids = load_vector(layer_points, "layer_points");
    if (offsets.size() != mesh.owner.size() + 1U || offsets.empty()
        || offsets.front() != 0 || offsets.back() != static_cast<long long>(flat.size())) {
        throw std::invalid_argument("face offsets and owner lengths disagree");
    }
    if (mesh.neighbour.size() > mesh.owner.size()) {
        throw std::invalid_argument("neighbour cannot contain more entries than owner");
    }
    if (base_cell_count < 0) {
        throw std::invalid_argument("base_cell_count must be non-negative");
    }
    if (base_ids.size() != layer_ids.size()) {
        throw std::invalid_argument("base_vertices and layer_points lengths disagree");
    }
    mesh.base_cell_count = base_cell_count;
    mesh.faces.reserve(mesh.owner.size());
    for (std::size_t face_id = 0; face_id < mesh.owner.size(); ++face_id) {
        const long long begin = offsets[face_id];
        const long long end = offsets[face_id + 1U];
        if (begin < 0 || end < begin || end > static_cast<long long>(flat.size())
            || end - begin < 3) {
            throw std::invalid_argument("invalid face offset");
        }
        Face face;
        for (long long cursor = begin; cursor < end; ++cursor) {
            const long long vertex = flat[static_cast<std::size_t>(cursor)];
            if (vertex < 0 || vertex >= static_cast<long long>(candidate.size())) {
                throw std::invalid_argument("face vertex is out of candidate range");
            }
            if (std::find(face.begin(), face.end(), vertex) != face.end()) {
                throw std::invalid_argument("face contains duplicate vertex");
            }
            face.push_back(vertex);
        }
        mesh.faces.push_back(std::move(face));
    }
    std::vector<long long> all_cells = mesh.owner;
    all_cells.insert(all_cells.end(), mesh.neighbour.begin(), mesh.neighbour.end());
    const long long max_cell = all_cells.empty()
        ? -1
        : *std::max_element(all_cells.begin(), all_cells.end());
    if (max_cell < 0 || base_cell_count > max_cell + 1) {
        throw std::invalid_argument("base_cell_count is outside mesh cells");
    }
    mesh.cell_vertices.resize(static_cast<std::size_t>(max_cell + 1));
    mesh.owner_faces.resize(static_cast<std::size_t>(max_cell + 1));
    for (std::size_t face_id = 0; face_id < mesh.faces.size(); ++face_id) {
        const long long owner = mesh.owner[face_id];
        if (owner < 0 || owner > max_cell) {
            throw std::invalid_argument("owner cell is out of range");
        }
        auto& owner_vertices = mesh.cell_vertices[static_cast<std::size_t>(owner)];
        owner_vertices.insert(owner_vertices.end(), mesh.faces[face_id].begin(), mesh.faces[face_id].end());
        mesh.owner_faces[static_cast<std::size_t>(owner)].push_back(static_cast<long long>(face_id));
        if (face_id < mesh.neighbour.size()) {
            const long long neighbour = mesh.neighbour[face_id];
            if (neighbour < 0 || neighbour > max_cell || neighbour == owner) {
                throw std::invalid_argument("neighbour cell is invalid");
            }
            auto& neighbour_vertices = mesh.cell_vertices[static_cast<std::size_t>(neighbour)];
            neighbour_vertices.insert(neighbour_vertices.end(), mesh.faces[face_id].begin(), mesh.faces[face_id].end());
        }
    }
    for (auto& vertices : mesh.cell_vertices) {
        std::sort(vertices.begin(), vertices.end());
        vertices.erase(std::unique(vertices.begin(), vertices.end()), vertices.end());
    }
    std::unordered_set<long long> seen_layer_points;
    mesh.mappings.reserve(base_ids.size());
    for (std::size_t index = 0; index < base_ids.size(); ++index) {
        const long long base = base_ids[index];
        const long long layer = layer_ids[index];
        if (base < 0 || base >= static_cast<long long>(original.size())
            || layer < 0 || layer >= static_cast<long long>(candidate.size())) {
            throw std::invalid_argument("layer mapping index is out of range");
        }
        if (!seen_layer_points.insert(layer).second) {
            throw std::invalid_argument("layer mapping is not injective");
        }
        Mapping mapping;
        mapping.base_vertex = base;
        mapping.layer_point = layer;
        mapping.delta = subtract(candidate[static_cast<std::size_t>(layer)], original[static_cast<std::size_t>(base)]);
        mesh.mappings.push_back(mapping);
    }
    return mesh;
}

Point face_centre(const std::vector<Point>& points, const Face& face)
{
    Point centre{0.0, 0.0, 0.0};
    for (const long long vertex : face) {
        centre = add(centre, points[static_cast<std::size_t>(vertex)]);
    }
    return scale(centre, 1.0 / static_cast<double>(face.size()));
}

Point face_normal(const std::vector<Point>& points, const Face& face, const Point& centre)
{
    Point normal{0.0, 0.0, 0.0};
    for (std::size_t index = 0; index < face.size(); ++index) {
        const Point left = subtract(points[static_cast<std::size_t>(face[index])], centre);
        const Point right = subtract(points[static_cast<std::size_t>(face[(index + 1U) % face.size()])], centre);
        normal = add(normal, cross(left, right));
    }
    return normal;
}

struct FrontState {
    std::vector<long long> inverted_cells;
    bool finite = true;
};

FrontState inspect_front(const Mesh& mesh, const std::vector<Point>& points)
{
    FrontState result;
    std::size_t total_owner_faces = 0U;
    std::vector<Point> cell_centres(mesh.cell_vertices.size());
    for (std::size_t cell = 0; cell < mesh.cell_vertices.size(); ++cell) {
        if (mesh.cell_vertices[cell].empty()) {
            continue;
        }
        cell_centres[cell] = mean_points(points, mesh.cell_vertices[cell]);
    }
    std::vector<bool> flipped(mesh.faces.size(), false);
    for (std::size_t cell = 0; cell < mesh.owner_faces.size(); ++cell) {
        for (const long long face_id : mesh.owner_faces[cell]) {
            const Face& face = mesh.faces[static_cast<std::size_t>(face_id)];
            const Point centre = face_centre(points, face);
            const Point normal = face_normal(points, face, centre);
            const double normal_norm = norm(normal);
            if (!std::isfinite(normal_norm) || normal_norm <= 1e-30) {
                result.finite = false;
                continue;
            }
            const double orientation = dot(normal, subtract(centre, cell_centres[cell]));
            if (!std::isfinite(orientation)) {
                result.finite = false;
                continue;
            }
            ++total_owner_faces;
            if (orientation < -1e-14) {
                flipped[static_cast<std::size_t>(face_id)] = true;
            }
        }
    }
    if (!result.finite || total_owner_faces == 0U) {
        return result;
    }
    std::vector<int> bad_cells;
    for (int cell = 0; cell < mesh.base_cell_count; ++cell) {
        const auto& faces = mesh.owner_faces[static_cast<std::size_t>(cell)];
        if (!faces.empty() && std::all_of(faces.begin(), faces.end(), [&flipped](const long long face_id) {
                return flipped[static_cast<std::size_t>(face_id)];
            })) {
            bad_cells.push_back(cell);
        }
    }
    for (std::size_t face_id = 0; face_id < mesh.neighbour.size(); ++face_id) {
        const Face& face = mesh.faces[face_id];
        const Point anchor = points[static_cast<std::size_t>(face.front())];
        Point area{0.0, 0.0, 0.0};
        for (std::size_t index = 1U; index + 1U < face.size(); ++index) {
            area = add(
                area,
                cross(
                    subtract(points[static_cast<std::size_t>(face[index])], anchor),
                    subtract(points[static_cast<std::size_t>(face[index + 1U])], anchor)));
        }
        const long long owner = mesh.owner[face_id];
        const long long neighbour = mesh.neighbour[face_id];
        const Point centre_delta = subtract(
            cell_centres[static_cast<std::size_t>(neighbour)],
            cell_centres[static_cast<std::size_t>(owner)]);
        const double area_norm = norm(area);
        const double delta_norm = norm(centre_delta);
        const double oriented = dot(centre_delta, area);
        if (!(area_norm > 1e-30) || !(delta_norm > 1e-30)
            || !std::isfinite(oriented)
            || !(oriented > 1e-12 * area_norm * delta_norm)) {
            bad_cells.push_back(static_cast<int>(owner));
            bad_cells.push_back(static_cast<int>(neighbour));
        }
    }
    std::sort(bad_cells.begin(), bad_cells.end());
    bad_cells.erase(std::unique(bad_cells.begin(), bad_cells.end()), bad_cells.end());
    result.inverted_cells.assign(bad_cells.begin(), bad_cells.end());
    return result;
}

bool cell_contains_point(const Mesh& mesh, const int cell, const long long point)
{
    const auto& vertices = mesh.cell_vertices[static_cast<std::size_t>(cell)];
    return std::binary_search(vertices.begin(), vertices.end(), point);
}

std::vector<Point> build_candidate(
    const std::vector<Point>& original,
    const std::vector<Point>& input,
    const std::vector<Mapping>& mappings)
{
    std::vector<Point> result = input;
    for (const Mapping& mapping : mappings) {
        result[static_cast<std::size_t>(mapping.layer_point)] = add(
            original[static_cast<std::size_t>(mapping.base_vertex)],
            scale(mapping.delta, mapping.alpha));
    }
    return result;
}

py::array_t<double> points_array(const std::vector<Point>& points)
{
    py::array_t<double> result(py::array::ShapeContainer{
        static_cast<py::ssize_t>(points.size()), py::ssize_t{3}});
    auto view = result.mutable_unchecked<2>();
    for (std::size_t row = 0; row < points.size(); ++row) {
        for (std::size_t coordinate = 0; coordinate < 3U; ++coordinate) {
            view(static_cast<py::ssize_t>(row), static_cast<py::ssize_t>(coordinate)) = points[row][coordinate];
        }
    }
    return result;
}

py::array_t<double> alpha_array(const std::vector<Mapping>& mappings)
{
    py::array_t<double> result(static_cast<py::ssize_t>(mappings.size()));
    auto view = result.mutable_unchecked<1>();
    for (std::size_t index = 0; index < mappings.size(); ++index) {
        view(static_cast<py::ssize_t>(index)) = mappings[index].alpha;
    }
    return result;
}

py::dict optimize_local_front(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& original_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& candidate_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& face_vertices,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& face_offsets,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& owner,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& neighbour,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& base_vertices,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& layer_points,
    const int base_cell_count,
    const int max_rounds,
    const double alpha_min)
{
    if (max_rounds < 0 || max_rounds > 64) {
        throw std::invalid_argument("max_rounds must be in [0, 64]");
    }
    if (!std::isfinite(alpha_min) || alpha_min <= 0.0 || alpha_min > 1.0) {
        throw std::invalid_argument("alpha_min must be in (0, 1]");
    }
    const std::vector<Point> original = load_points(original_array, "original_points");
    const std::vector<Point> input = load_points(candidate_array, "candidate_points");
    Mesh mesh = load_mesh(
        original, input, face_vertices, face_offsets, owner, neighbour,
        base_vertices, layer_points, base_cell_count);
    const FrontState before = inspect_front(mesh, input);
    std::vector<Point> candidate = input;
    std::size_t affected_cells = 0U;
    std::size_t scaled_points = 0U;
    int iterations = 0;
    if (before.finite && !before.inverted_cells.empty() && !mesh.mappings.empty()) {
        for (int round = 0; round < max_rounds; ++round) {
            const FrontState current = inspect_front(mesh, candidate);
            if (!current.finite || current.inverted_cells.empty()) {
                break;
            }
            ++iterations;
            affected_cells += current.inverted_cells.size();
            bool changed = false;
            for (const long long cell : current.inverted_cells) {
                for (std::size_t index = 0; index < mesh.mappings.size(); ++index) {
                    Mapping& mapping = mesh.mappings[index];
                    if (!cell_contains_point(mesh, static_cast<int>(cell), mapping.layer_point)) {
                        continue;
                    }
                    if (norm(mapping.delta) <= 1e-15) {
                        continue;
                    }
                    const double next = std::max(alpha_min, mapping.alpha * 0.5);
                    if (next + 1e-15 < mapping.alpha) {
                        mapping.alpha = next;
                        changed = true;
                    }
                }
            }
            if (!changed) {
                break;
            }
            candidate = build_candidate(original, input, mesh.mappings);
        }
        candidate = build_candidate(original, input, mesh.mappings);
    }
    const FrontState after = inspect_front(mesh, candidate);
    for (const Mapping& mapping : mesh.mappings) {
        if (mapping.alpha < 1.0 - 1e-15) {
            ++scaled_points;
        }
    }
    py::dict result;
    result["accepted"] = before.finite && after.finite && after.inverted_cells.empty();
    result["reason"] = !before.finite
        ? py::str("input_front_nonfinite_or_degenerate")
        : (!after.finite
            ? py::str("local_front_nonfinite_or_degenerate")
            : (after.inverted_cells.empty() ? py::str("local_front_feasible")
                                             : py::str("local_front_inverted_cells_remain")));
    result["candidate_points"] = points_array(candidate);
    result["alpha"] = alpha_array(mesh.mappings);
    result["n_input_inverted_cells"] = static_cast<long long>(before.inverted_cells.size());
    result["n_remaining_inverted_cells"] = static_cast<long long>(after.inverted_cells.size());
    result["n_affected_cells"] = static_cast<long long>(affected_cells);
    result["n_scaled_points"] = static_cast<long long>(scaled_points);
    result["iterations"] = iterations;
    result["alpha_min"] = alpha_min;
    result["topology_untouched"] = true;
    result["source_points_untouched"] = true;
    result["deterministic"] = true;
    return result;
}

}  // namespace

PYBIND11_MODULE(native_poly_bl_local_front_qopt, module)
{
    module.doc() = "Fail-closed C++23 Native Poly local boundary-layer front optimizer";
    module.def(
        "optimize_local_front",
        &optimize_local_front,
        py::arg("original_points"), py::arg("candidate_points"),
        py::arg("face_vertices"), py::arg("face_offsets"), py::arg("owner"),
        py::arg("neighbour"), py::arg("base_vertices"), py::arg("layer_points"),
        py::arg("base_cell_count"), py::arg("max_rounds") = 8,
        py::arg("alpha_min") = 0.03125);
}
