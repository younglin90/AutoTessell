// Face cleaning and topology assembly for write_generic_polymesh.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <span>
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

    py::array_t<bool> result({static_cast<py::ssize_t>(ragged.size())});
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

    py::array_t<bool> on_plane({static_cast<py::ssize_t>(ragged.size())});
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
}
