// C++23 restricted actual STEPCAF/XDE box producer.
// The route is deliberately narrow: six authoritative planar B-Rep faces,
// explicit semantic labels, and a deterministic structured all-hex extrusion.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;
using Hex = std::array<std::int64_t, 8>;
using Quad = std::array<std::int64_t, 4>;
using Key4 = std::array<std::int64_t, 4>;

static py::dict refusal(const std::string& reason, std::int64_t requested) {
    py::dict out;
    out["accepted"] = false;
    out["status"] = "native_hex_actual_xde_refused";
    out["reason"] = reason;
    out["requested_layers"] = requested;
    out["actual_layers"] = 0;
    out["candidate_discarded"] = true;
    out["runtime_route"] = "private_default_off";
    return out;
}

static std::vector<Point> read_points(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& input) {
    if (input.ndim() != 2 || input.shape(1) != 3) throw std::invalid_argument("canonical_positions must be Nx3");
    auto view = input.unchecked<2>();
    std::vector<Point> result(static_cast<std::size_t>(input.shape(0)));
    for (py::ssize_t i = 0; i < input.shape(0); ++i) {
        for (int j = 0; j < 3; ++j) {
            result[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] = view(i, j);
            if (!std::isfinite(view(i, j))) throw std::invalid_argument("canonical_positions contains nonfinite value");
        }
    }
    return result;
}

static std::vector<Quad> read_faces(
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& input,
    std::int64_t point_count) {
    if (input.ndim() != 2 || input.shape(1) != 4 || input.shape(0) != 6) {
        throw std::invalid_argument("face_vertices must be 6x4");
    }
    auto view = input.unchecked<2>();
    std::vector<Quad> result(6);
    for (int i = 0; i < 6; ++i) {
        std::set<std::int64_t> unique;
        for (int j = 0; j < 4; ++j) {
            auto value = view(i, j);
            if (value < 0 || value >= point_count || !unique.insert(value).second) {
                throw std::invalid_argument("face_vertices has invalid or duplicate corner");
            }
            result[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] = value;
        }
    }
    return result;
}

static std::int64_t grid_id(std::int64_t i, std::int64_t j, std::int64_t k,
                            std::int64_t nx, std::int64_t ny) {
    return i + (nx + 1) * (j + (ny + 1) * k);
}

static py::array_t<double> points_array(const std::vector<Point>& points) {
    std::vector<py::ssize_t> shape{static_cast<py::ssize_t>(points.size()), 3};
    py::array_t<double> output(shape);
    auto view = output.mutable_unchecked<2>();
    for (py::ssize_t i = 0; i < static_cast<py::ssize_t>(points.size()); ++i)
        for (int j = 0; j < 3; ++j) view(i, j) = points[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)];
    return output;
}

template <std::size_t N>
static py::array_t<std::int64_t> integer_array(const std::vector<std::array<std::int64_t, N>>& values) {
    std::vector<py::ssize_t> shape{static_cast<py::ssize_t>(values.size()), static_cast<py::ssize_t>(N)};
    py::array_t<std::int64_t> output(shape);
    auto view = output.mutable_unchecked<2>();
    for (py::ssize_t i = 0; i < static_cast<py::ssize_t>(values.size()); ++i)
        for (std::size_t j = 0; j < N; ++j) view(i, static_cast<py::ssize_t>(j)) = values[static_cast<std::size_t>(i)][j];
    return output;
}

static py::dict row_copy(const py::dict& row, std::int64_t output_face, std::int64_t source_face) {
    py::dict binding;
    binding["source_face"] = source_face;
    binding["output_face"] = output_face;
    for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) {
        if (!row.contains(key) || py::str(row[key]).cast<std::string>().empty()) throw std::invalid_argument("semantic row incomplete");
        binding[key] = row[key];
    }
    binding["direct"] = true;
    binding["mapping_source"] = "actual_stepcaf_xde_face_ordinal";
    return binding;
}

static py::dict build(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& canonical_positions,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& face_vertices,
    const py::list& semantic_rows,
    std::int64_t requested_layers,
    double first_height,
    double growth) {
    if (requested_layers < 0 || requested_layers > 32) return refusal("invalid_layer_count", requested_layers);
    if (semantic_rows.size() != 6) return refusal("semantic_row_count_mismatch", requested_layers);
    if (!std::isfinite(first_height) || !std::isfinite(growth) || first_height <= 0.0 || growth < 1.0) {
        return refusal("boundary_layer_schedule_invalid", requested_layers);
    }
    std::vector<Point> source;
    std::vector<Quad> source_faces;
    try {
        source = read_points(canonical_positions);
        source_faces = read_faces(face_vertices, static_cast<std::int64_t>(canonical_positions.shape(0)));
    } catch (const std::exception& error) {
        return refusal(error.what(), requested_layers);
    }
    if (source.size() != 8) return refusal("explicit_xde_box_requires_eight_corners", requested_layers);
    Point lo = source[0], hi = source[0];
    for (const auto& point : source) for (int axis = 0; axis < 3; ++axis) {
        lo[axis] = std::min(lo[axis], point[axis]);
        hi[axis] = std::max(hi[axis], point[axis]);
    }
    Point extent{};
    for (int axis = 0; axis < 3; ++axis) {
        extent[axis] = hi[axis] - lo[axis];
        if (!(extent[axis] > 1.0e-12)) return refusal("degenerate_box_extent", requested_layers);
    }
    std::set<std::array<std::int64_t, 3>> corner_signatures;
    for (const auto& point : source) {
        std::array<std::int64_t, 3> signature{};
        for (int axis = 0; axis < 3; ++axis) {
            const double d0 = std::abs(point[axis] - lo[axis]);
            const double d1 = std::abs(point[axis] - hi[axis]);
            if (std::min(d0, d1) > 1.0e-9 * std::max(1.0, extent[axis])) return refusal("source_shape_not_axis_aligned_box", requested_layers);
            signature[axis] = d1 < d0 ? 1 : 0;
        }
        corner_signatures.insert(signature);
    }
    if (corner_signatures.size() != 8) return refusal("source_corner_set_incomplete", requested_layers);

    std::array<std::int64_t, 6> source_face_for_side{};
    source_face_for_side.fill(-1);
    for (std::int64_t face_id = 0; face_id < 6; ++face_id) {
        const auto& face = source_faces[static_cast<std::size_t>(face_id)];
        int side = -1;
        for (int axis = 0; axis < 3 && side < 0; ++axis) {
            bool at_lo = true, at_hi = true;
            for (auto index : face) {
                at_lo = at_lo && std::abs(source[static_cast<std::size_t>(index)][axis] - lo[axis]) < 1.0e-9 * std::max(1.0, extent[axis]);
                at_hi = at_hi && std::abs(source[static_cast<std::size_t>(index)][axis] - hi[axis]) < 1.0e-9 * std::max(1.0, extent[axis]);
            }
            if (at_lo) side = 2 * axis;
            else if (at_hi) side = 2 * axis + 1;
        }
        if (side < 0 || source_face_for_side[static_cast<std::size_t>(side)] >= 0) return refusal("source_faces_do_not_bind_six_box_planes", requested_layers);
        source_face_for_side[static_cast<std::size_t>(side)] = face_id;
    }
    for (auto value : source_face_for_side) if (value < 0) return refusal("source_box_plane_coverage_incomplete", requested_layers);

    std::vector<double> levels[3];
    for (int axis = 0; axis < 3; ++axis) {
        levels[axis].push_back(lo[axis]);
        double total = 0.0;
        double last_layer = 0.0;
        for (std::int64_t layer = 0; layer < requested_layers; ++layer) {
            last_layer = first_height * std::pow(growth, static_cast<double>(layer));
            total += last_layer;
            levels[axis].push_back(lo[axis] + total);
        }
        if (requested_layers > 0 && !(2.0 * total < extent[axis] - 1.0e-12))
            return refusal("boundary_layer_thickness_exceeds_box_clearance", requested_layers);
        const double core_start = lo[axis] + total;
        const double core_end = hi[axis] - total;
        if (requested_layers > 0) {
            const auto core_segments = static_cast<std::int64_t>(
                std::max(1.0, std::ceil((core_end - core_start) / (2.0 * last_layer))));
            for (std::int64_t segment = 1; segment < core_segments; ++segment)
                levels[axis].push_back(core_start + (core_end - core_start) * static_cast<double>(segment) / static_cast<double>(core_segments));
            for (std::int64_t layer = requested_layers - 1; layer >= 0; --layer) {
                double from_hi = 0.0;
                for (std::int64_t inner = 0; inner <= layer; ++inner)
                    from_hi += first_height * std::pow(growth, static_cast<double>(inner));
                levels[axis].push_back(hi[axis] - from_hi);
            }
        }
        levels[axis].push_back(hi[axis]);
        std::sort(levels[axis].begin(), levels[axis].end());
        levels[axis].erase(std::unique(levels[axis].begin(), levels[axis].end()), levels[axis].end());
    }
    const std::int64_t nx = static_cast<std::int64_t>(levels[0].size()) - 1;
    const std::int64_t ny = static_cast<std::int64_t>(levels[1].size()) - 1;
    const std::int64_t nz = static_cast<std::int64_t>(levels[2].size()) - 1;
    std::vector<Point> points;
    points.reserve(static_cast<std::size_t>((nx + 1) * (ny + 1) * (nz + 1)));
    for (std::int64_t k = 0; k <= nz; ++k) for (std::int64_t j = 0; j <= ny; ++j) for (std::int64_t i = 0; i <= nx; ++i)
        points.push_back({levels[0][static_cast<std::size_t>(i)], levels[1][static_cast<std::size_t>(j)], levels[2][static_cast<std::size_t>(k)]});
    std::vector<Hex> cells;
    std::vector<std::array<Quad, 6>> cell_faces;
    cells.reserve(static_cast<std::size_t>(nx * ny * nz));
    for (std::int64_t k = 0; k < nz; ++k) for (std::int64_t j = 0; j < ny; ++j) for (std::int64_t i = 0; i < nx; ++i) {
        auto p000 = grid_id(i, j, k, nx, ny), p100 = grid_id(i + 1, j, k, nx, ny), p110 = grid_id(i + 1, j + 1, k, nx, ny), p010 = grid_id(i, j + 1, k, nx, ny);
        auto p001 = grid_id(i, j, k + 1, nx, ny), p101 = grid_id(i + 1, j, k + 1, nx, ny), p111 = grid_id(i + 1, j + 1, k + 1, nx, ny), p011 = grid_id(i, j + 1, k + 1, nx, ny);
        Hex cell{p000, p100, p110, p010, p001, p101, p111, p011};
        cells.push_back(cell);
        cell_faces.push_back({Quad{p000, p010, p110, p100}, Quad{p001, p101, p111, p011}, Quad{p000, p001, p011, p010}, Quad{p100, p110, p111, p101}, Quad{p000, p100, p101, p001}, Quad{p010, p011, p111, p110}});
    }
    struct FaceRecord { Quad oriented; std::int64_t owner; std::int64_t neighbour{-1}; int side{-1}; };
    std::map<Key4, std::int64_t> lookup;
    std::vector<FaceRecord> all_faces;
    std::vector<std::int64_t> cell_boundary_side;
    for (std::int64_t cell_id = 0; cell_id < static_cast<std::int64_t>(cell_faces.size()); ++cell_id) {
        auto& six = cell_faces[static_cast<std::size_t>(cell_id)];
        for (int local = 0; local < 6; ++local) {
            Key4 key = six[static_cast<std::size_t>(local)];
            std::sort(key.begin(), key.end());
            auto found = lookup.find(key);
            if (found == lookup.end()) { lookup.emplace(key, static_cast<std::int64_t>(all_faces.size())); all_faces.push_back({six[static_cast<std::size_t>(local)], cell_id, -1, -1}); }
            else { auto& record = all_faces[static_cast<std::size_t>(found->second)]; if (record.neighbour >= 0) return refusal("non_manifold_generated_face", requested_layers); record.neighbour = cell_id; }
        }
    }
    std::vector<Quad> internal_faces, boundary_faces;
    std::vector<std::int64_t> internal_owner, internal_neighbour, boundary_owner, boundary_source;
    std::vector<py::dict> bindings;
    for (const auto& record : all_faces) {
        if (record.neighbour >= 0) { internal_faces.push_back(record.oriented); internal_owner.push_back(record.owner); internal_neighbour.push_back(record.neighbour); continue; }
        const auto& q = record.oriented;
        Point center{}; for (auto id : q) for (int axis = 0; axis < 3; ++axis) center[axis] += points[static_cast<std::size_t>(id)][axis] / 4.0;
        int side = -1;
        for (int axis = 0; axis < 3; ++axis) { if (std::abs(center[axis] - lo[axis]) < 1.0e-9 * std::max(1.0, extent[axis])) side = 2 * axis; if (std::abs(center[axis] - hi[axis]) < 1.0e-9 * std::max(1.0, extent[axis])) side = 2 * axis + 1; }
        if (side < 0) return refusal("generated_boundary_face_not_on_source_box", requested_layers);
        const std::int64_t source_face = source_face_for_side[static_cast<std::size_t>(side)];
        boundary_faces.push_back(q); boundary_owner.push_back(record.owner); boundary_source.push_back(source_face);
        try { bindings.push_back(row_copy(semantic_rows[static_cast<std::size_t>(source_face)].cast<py::dict>(), static_cast<std::int64_t>(internal_faces.size() + boundary_faces.size() - 1), source_face)); }
        catch (const std::exception& error) { return refusal(error.what(), requested_layers); }
    }
    std::vector<Quad> faces = internal_faces; faces.insert(faces.end(), boundary_faces.begin(), boundary_faces.end());
    py::list layer_records;
    double cumulative = 0.0;
    for (std::int64_t layer = 0; layer < requested_layers; ++layer) { const double thickness = first_height * std::pow(growth, static_cast<double>(layer)); cumulative += thickness; py::dict row; row["layer"] = layer + 1; row["thickness"] = thickness; row["cumulative_thickness"] = cumulative; row["positive"] = thickness > 0.0; layer_records.append(row); }
    py::dict quality;
    double min_volume = INFINITY, max_aspect = 0.0;
    for (std::int64_t k = 0; k < nz; ++k) for (std::int64_t j = 0; j < ny; ++j) for (std::int64_t i = 0; i < nx; ++i) { const double dx = levels[0][static_cast<std::size_t>(i + 1)] - levels[0][static_cast<std::size_t>(i)], dy = levels[1][static_cast<std::size_t>(j + 1)] - levels[1][static_cast<std::size_t>(j)], dz = levels[2][static_cast<std::size_t>(k + 1)] - levels[2][static_cast<std::size_t>(k)]; min_volume = std::min(min_volume, dx * dy * dz); max_aspect = std::max(max_aspect, std::max({dx, dy, dz}) / std::min({dx, dy, dz})); }
    quality["minimum_volume"] = min_volume; quality["minimum_scaled_jacobian"] = 1.0; quality["maximum_aspect_ratio"] = max_aspect; quality["maximum_skewness"] = 0.0; quality["maximum_non_orthogonality_degrees"] = 0.0;
    py::dict topology; topology["duplicate"] = 0; topology["non_manifold"] = 0; topology["inverted"] = 0; topology["invalid"] = 0;
    std::vector<std::int64_t> all_owner = internal_owner;
    all_owner.insert(all_owner.end(), boundary_owner.begin(), boundary_owner.end());
    py::dict out; out["accepted"] = true; out["status"] = "native_hex_actual_xde_produced"; out["profile"] = "NativeHex/ExplicitSTEPCAF-XDE-Box/v1"; out["requested_layers"] = requested_layers; out["actual_layers"] = requested_layers; out["candidate_discarded"] = false; out["runtime_route"] = "private_default_off"; out["points"] = points_array(points); out["cells"] = integer_array(cells); out["faces"] = integer_array(faces); out["owner"] = all_owner; out["neighbour"] = internal_neighbour; out["boundary_face_count"] = boundary_faces.size(); out["boundary_source_faces"] = boundary_source; out["boundary_binding"] = bindings; out["layer_records"] = layer_records; out["topology"] = topology; out["quality"] = quality; out["cell_count"] = cells.size(); out["face_count"] = faces.size(); out["direct_boundary_mapping"] = true; out["shape_preserved"] = true; out["positive_boundary_layer"] = requested_layers == 0 || cumulative > 0.0; return out;
}

PYBIND11_MODULE(native_hex_actual_xde_brep_producer, module) {
    module.doc() = "Restricted actual STEPCAF/XDE Native Hex box producer";
    module.def("build_native_hex_actual_xde_brep", &build, py::arg("canonical_positions"), py::arg("face_vertices"), py::arg("semantic_rows"), py::arg("requested_layers"), py::arg("first_height"), py::arg("growth"));
}
