// Face cleaning and topology assembly for write_generic_polymesh.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace py = pybind11;

namespace {

using Label = long long;
using Face = std::vector<Label>;
using Cell = std::vector<Face>;
using Cells = std::vector<Cell>;

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
    py::array_t<Label> result({static_cast<py::ssize_t>(values.size())});
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

}  // namespace

PYBIND11_MODULE(native_polymesh, module)
{
    module.doc() = "C++ face cleaning and topology kernel for AutoTessell polyMesh";
    module.def(
        "build_topology",
        &build_topology,
        py::arg("vertices"),
        py::arg("cell_faces"),
        py::arg("area_eps"));
    module.def(
        "build_tet_incidence_maps",
        &build_tet_incidence_maps,
        py::arg("tets"),
        py::arg("num_vertices"));
}
