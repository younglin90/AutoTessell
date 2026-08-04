// Default-off C++23 canonical face/cell quality witness.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include "native_quality_witness_v3.hpp"
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;
py::dict build_surface_witness(const py::array_t<double, py::array::c_style | py::array::forcecast>&, const py::list&, const py::list&, const py::object&, const py::object&);
py::dict build_volume_witness(const py::array_t<double, py::array::c_style | py::array::forcecast>&, const py::list&, const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>&, const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>&, const py::object&, const py::object&);
py::dict build_full_volume_witness(const py::array_t<double, py::array::c_style | py::array::forcecast>&, const py::list&, const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>&, const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>&, const py::object&, const py::object&);
py::dict build_authority_bound_volume_witness(const py::array_t<double, py::array::c_style | py::array::forcecast>&, const py::list&, const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>&, const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>&, const py::object&, const py::object&);

Point sub(const Point& a, const Point& b) noexcept { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point add(const Point& a, const Point& b) noexcept { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
Point mul(const Point& a, double s) noexcept { return {a[0] * s, a[1] * s, a[2] * s}; }
Point cross(const Point& a, const Point& b) noexcept { return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]}; }
double dot(const Point& a, const Point& b) noexcept { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double norm(const Point& a) noexcept { return std::sqrt(dot(a, a)); }

double percentile(std::vector<double> values, double fraction) {
    if (values.empty()) return 0.0;
    std::ranges::sort(values);
    const double position = fraction * static_cast<double>(values.size() - 1U);
    const auto lo = static_cast<size_t>(std::floor(position));
    const auto hi = static_cast<size_t>(std::ceil(position));
    if (lo == hi) return values[lo];
    return values[lo] + (values[hi] - values[lo]) * (position - static_cast<double>(lo));
}

py::dict distribution(const std::vector<double>& values, const char* definition) {
    py::dict out;
    out["status"] = values.empty() ? "not_applicable" : "measured";
    out["count"] = static_cast<std::int64_t>(values.size());
    out["min"] = values.empty() ? py::none() : py::cast(*std::min_element(values.begin(), values.end()));
    out["p95"] = values.empty() ? py::none() : py::cast(percentile(values, 0.95));
    out["p99"] = values.empty() ? py::none() : py::cast(percentile(values, 0.99));
    out["max"] = values.empty() ? py::none() : py::cast(*std::max_element(values.begin(), values.end()));
    out["definition"] = definition;
    return out;
}

py::dict refusal(const char* reason) {
    py::dict out;
    out["accepted"] = false;
    out["status"] = "unverified";
    out["reason"] = reason;
    return out;
}

py::dict build_witness(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::list& faces,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& owner,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& neighbour)
{
    if (points.ndim() != 2 || points.shape(1) != 3 || owner.ndim() != 1 || neighbour.ndim() != 1) {
        throw std::invalid_argument("points Nx3 and owner/neighbour vectors are required");
    }
    const auto n_faces = static_cast<size_t>(faces.size());
    if (static_cast<size_t>(owner.size()) != n_faces || static_cast<size_t>(neighbour.size()) > n_faces) {
        throw std::invalid_argument("owner must match faces and neighbour cannot exceed faces");
    }
    const auto* point_data = points.data();
    const auto* owner_data = owner.data();
    const auto* neighbour_data = neighbour.data();
    std::vector<Point> xyz;
    xyz.reserve(static_cast<size_t>(points.shape(0)));
    for (py::ssize_t i = 0; i < points.shape(0); ++i) {
        Point p{point_data[3U * static_cast<size_t>(i)], point_data[3U * static_cast<size_t>(i) + 1U], point_data[3U * static_cast<size_t>(i) + 2U]};
        if (!std::ranges::all_of(p, [](double v) { return std::isfinite(v); })) return refusal("nonfinite_point");
        xyz.push_back(p);
    }
    std::vector<std::vector<std::int64_t>> topology;
    topology.reserve(n_faces);
    for (const auto& item : faces) {
        if (!py::isinstance<py::sequence>(item)) return refusal("invalid_face_record");
        std::vector<std::int64_t> face = item.cast<std::vector<std::int64_t>>();
        if (face.size() < 3U) return refusal("face_has_fewer_than_three_vertices");
        for (const auto id : face) if (id < 0 || id >= points.shape(0)) return refusal("face_vertex_out_of_range");
        topology.push_back(std::move(face));
    }
    std::int64_t max_cell = -1;
    for (py::ssize_t i = 0; i < owner.size(); ++i) max_cell = std::max(max_cell, owner_data[i]);
    for (py::ssize_t i = 0; i < neighbour.size(); ++i) max_cell = std::max(max_cell, neighbour_data[i]);
    const size_t n_cells = max_cell < 0 ? 0U : static_cast<size_t>(max_cell + 1);
    if (n_cells == 0U) return refusal("empty_cell_incidence");

    std::vector<Point> face_centres(n_faces, Point{0.0, 0.0, 0.0});
    std::vector<Point> area_vectors(n_faces, Point{0.0, 0.0, 0.0});
    std::vector<std::set<std::int64_t>> cell_vertices(n_cells);
    for (size_t fi = 0; fi < n_faces; ++fi) {
        const auto& face = topology[fi];
        for (const auto id : face) {
            face_centres[fi] = add(face_centres[fi], xyz[static_cast<size_t>(id)]);
            cell_vertices[static_cast<size_t>(owner_data[fi])].insert(id);
        }
        face_centres[fi] = mul(face_centres[fi], 1.0 / static_cast<double>(face.size()));
        const Point anchor = xyz[static_cast<size_t>(face[0])];
        for (size_t j = 1; j + 1U < face.size(); ++j) {
            area_vectors[fi] = add(area_vectors[fi], cross(sub(xyz[static_cast<size_t>(face[j])], anchor), sub(xyz[static_cast<size_t>(face[j + 1U])], anchor)));
        }
        if (fi < static_cast<size_t>(neighbour.size())) {
            const auto id = neighbour_data[fi];
            if (id < 0 || id >= static_cast<std::int64_t>(n_cells)) return refusal("neighbour_cell_out_of_range");
            for (const auto vertex : face) cell_vertices[static_cast<size_t>(id)].insert(vertex);
        }
    }
    std::vector<Point> cell_centres(n_cells, Point{0.0, 0.0, 0.0});
    for (size_t ci = 0; ci < n_cells; ++ci) {
        if (cell_vertices[ci].empty()) return refusal("cell_without_vertices");
        for (const auto id : cell_vertices[ci]) cell_centres[ci] = add(cell_centres[ci], xyz[static_cast<size_t>(id)]);
        cell_centres[ci] = mul(cell_centres[ci], 1.0 / static_cast<double>(cell_vertices[ci].size()));
    }

    std::vector<double> internal_non_ortho, internal_skew, boundary_skew, all_skew;
    py::list records;
    for (size_t fi = 0; fi < n_faces; ++fi) {
        const auto owner_id = owner_data[fi];
        if (owner_id < 0 || owner_id >= static_cast<std::int64_t>(n_cells)) return refusal("owner_cell_out_of_range");
        const Point normal_vector = area_vectors[fi];
        const double normal_length = norm(normal_vector);
        if (!(normal_length > 1e-30)) return refusal("zero_face_area");
        const Point owner_delta = sub(face_centres[fi], cell_centres[static_cast<size_t>(owner_id)]);
        py::dict record;
        record["face_index"] = static_cast<std::int64_t>(fi);
        record["owner_cell"] = owner_id;
        if (fi < static_cast<size_t>(neighbour.size())) {
            const auto neighbour_id = neighbour_data[fi];
            if (neighbour_id < 0 || neighbour_id >= static_cast<std::int64_t>(n_cells)) return refusal("neighbour_cell_out_of_range");
            const Point d = sub(cell_centres[static_cast<size_t>(neighbour_id)], cell_centres[static_cast<size_t>(owner_id)]);
            const double d_length = norm(d);
            if (!(d_length > 1e-30)) return refusal("zero_cell_distance");
            const double cosine = std::clamp(std::abs(dot(d, normal_vector)) / (d_length * normal_length), 0.0, 1.0);
            const double eta = std::acos(cosine) * 180.0 / 3.14159265358979323846;
            const double projection = dot(owner_delta, d) / (d_length * d_length);
            const double skew = norm(sub(owner_delta, mul(d, projection))) / d_length;
            internal_non_ortho.push_back(eta); internal_skew.push_back(skew); all_skew.push_back(skew);
            record["face_class"] = "internal"; record["neighbour_cell"] = neighbour_id; record["non_orthogonality"] = eta; record["skewness"] = skew;
        } else {
            const Point n = mul(normal_vector, 1.0 / normal_length);
            const double h = dot(n, owner_delta);
            if (!(std::abs(h) > 1e-30)) return refusal("zero_boundary_normal_distance");
            const Point tangential = sub(owner_delta, mul(n, h));
            const double skew = norm(tangential) / std::abs(h);
            boundary_skew.push_back(skew); all_skew.push_back(skew);
            record["face_class"] = "boundary"; record["neighbour_cell"] = py::none(); record["non_orthogonality"] = py::none(); record["skewness"] = skew;
        }
        records.append(record);
    }

    py::dict quality;
    quality["internal_non_orthogonality"] = distribution(internal_non_ortho, "internal/coupled face-centre axis angle in degrees");
    quality["internal_skewness"] = distribution(internal_skew, "internal face-centre distance from owner-neighbour line");
    quality["boundary_skewness"] = distribution(boundary_skew, "boundary face-centre normal projection miss");
    quality["release_skew"] = distribution(all_skew, "tagged union of internal and boundary skewness");
    py::dict out;
    out["accepted"] = true; out["status"] = "measured"; out["reason"] = "canonical_quality_witness_measured";
    out["n_points"] = static_cast<std::int64_t>(points.shape(0)); out["n_faces"] = static_cast<std::int64_t>(n_faces); out["n_cells"] = static_cast<std::int64_t>(n_cells);
    out["boundary_non_orthogonality"] = "not_applicable"; out["quality"] = quality; out["faces"] = records;
    return out;
}

PYBIND11_MODULE(native_quality_witness, m) {
    m.doc() = "Default-off C++23 canonical face/cell quality witness";
    m.def("build_quality_witness", &build_witness, py::arg("points"), py::arg("faces"), py::arg("owner"), py::arg("neighbour"));
    m.def("build_volume_quality_witness", &build_volume_witness, py::arg("points"), py::arg("faces"), py::arg("owner"), py::arg("neighbour"), py::arg("partitions") = py::none(), py::arg("cell_uids") = py::none());
    m.def("build_full_volume_quality_witness", &build_full_volume_witness, py::arg("points"), py::arg("faces"), py::arg("owner"), py::arg("neighbour"), py::arg("partitions"), py::arg("cell_uids"));
    m.def("build_authority_bound_volume_quality_witness", &build_authority_bound_volume_witness, py::arg("points"), py::arg("faces"), py::arg("owner"), py::arg("neighbour"), py::arg("partitions"), py::arg("cell_uids"));
    m.def("build_surface_quality_witness", &build_surface_witness, py::arg("vertices"), py::arg("triangles"), py::arg("quads"), py::arg("triangle_reference_normals") = py::none(), py::arg("quad_reference_normals") = py::none());
    m.def("seal_policy_v3", &native_quality_witness_v3::seal_policy_v3, py::arg("policy"));
    m.def("evaluate_v3", &native_quality_witness_v3::evaluate_v3, py::arg("snapshot"), py::arg("authority"), py::arg("sealed_policy"), py::arg("stage"));
    m.def("compare_candidate_reread_v3", &native_quality_witness_v3::compare_candidate_reread_v3, py::arg("candidate"), py::arg("reread"));
}

py::dict build_volume_witness(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::list& faces,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& owner,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& neighbour,
    const py::object& partitions,
    const py::object& cell_uids)
{
    py::dict base = build_witness(points, faces, owner, neighbour);
    if (!base["accepted"].cast<bool>()) return base;
    const auto* owner_data = owner.data();
    const auto* neighbour_data = neighbour.data();
    std::int64_t max_cell = -1;
    for (py::ssize_t i = 0; i < owner.size(); ++i) max_cell = std::max(max_cell, owner_data[i]);
    for (py::ssize_t i = 0; i < neighbour.size(); ++i) max_cell = std::max(max_cell, neighbour_data[i]);
    const size_t n_cells = max_cell < 0 ? 0U : static_cast<size_t>(max_cell + 1);
    if (n_cells == 0U) return refusal("empty_cell_incidence");
    if (!partitions.is_none() && (!py::isinstance<py::sequence>(partitions) ||
        static_cast<size_t>(py::len(partitions)) != n_cells)) return refusal("cell_partition_length");
    if (!cell_uids.is_none() && (!py::isinstance<py::sequence>(cell_uids) ||
        static_cast<size_t>(py::len(cell_uids)) != n_cells)) return refusal("cell_uid_length");

    const auto* point_data = points.data();
    std::vector<std::vector<std::int64_t>> topology;
    topology.reserve(static_cast<size_t>(faces.size()));
    std::vector<std::set<std::int64_t>> vertices(n_cells);
    for (const auto& item : faces) {
        auto face = item.cast<std::vector<std::int64_t>>();
        topology.push_back(face);
        const size_t fi = topology.size() - 1U;
        for (const auto id : face) {
            vertices[static_cast<size_t>(owner_data[fi])].insert(id);
            if (fi < static_cast<size_t>(neighbour.size()))
                vertices[static_cast<size_t>(neighbour_data[fi])].insert(id);
        }
    }

    std::vector<double> aspect_values;
    std::map<std::string, std::vector<double>> by_partition;
    py::list cells;
    for (size_t ci = 0; ci < n_cells; ++ci) {
        const auto& ids = vertices[ci];
        if (ids.size() < 2U) return refusal("cell_without_two_vertices");
        Point lo{std::numeric_limits<double>::infinity(), std::numeric_limits<double>::infinity(), std::numeric_limits<double>::infinity()};
        Point hi{-std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()};
        double min_distance = std::numeric_limits<double>::infinity();
        for (const auto id : ids) {
            const Point p{point_data[3U * static_cast<size_t>(id)], point_data[3U * static_cast<size_t>(id) + 1U], point_data[3U * static_cast<size_t>(id) + 2U]};
            for (size_t axis = 0; axis < 3U; ++axis) {
                lo[axis] = std::min(lo[axis], p[axis]);
                hi[axis] = std::max(hi[axis], p[axis]);
            }
        }
        std::vector<std::int64_t> id_list(ids.begin(), ids.end());
        for (size_t i = 0; i < id_list.size(); ++i) for (size_t j = i + 1U; j < id_list.size(); ++j) {
            const Point a{point_data[3U * static_cast<size_t>(id_list[i])], point_data[3U * static_cast<size_t>(id_list[i]) + 1U], point_data[3U * static_cast<size_t>(id_list[i]) + 2U]};
            const Point b{point_data[3U * static_cast<size_t>(id_list[j])], point_data[3U * static_cast<size_t>(id_list[j]) + 1U], point_data[3U * static_cast<size_t>(id_list[j]) + 2U]};
            min_distance = std::min(min_distance, norm(sub(a, b)));
        }
        const double max_extent = std::max({hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]});
        if (!(max_extent > 1e-30) || !(min_distance > 1e-30) || !std::isfinite(max_extent / min_distance))
            return refusal("nonpositive_cell_aspect_geometry");
        const double aspect = max_extent / min_distance;
        std::string partition = "core";
        if (!partitions.is_none()) partition = partitions[py::int_(ci)].cast<std::string>();
        if (partition != "core" && partition != "boundary_layer" && partition != "transition")
            return refusal("unknown_cell_partition");
        std::string uid = "cell:" + std::to_string(ci);
        if (!cell_uids.is_none()) uid = cell_uids[py::int_(ci)].cast<std::string>();
        py::dict row;
        row["cell_index"] = static_cast<std::int64_t>(ci);
        row["cell_uid"] = uid;
        row["partition"] = partition;
        row["aspect_ratio"] = aspect;
        row["positive_geometry"] = true;
        cells.append(row);
        aspect_values.push_back(aspect);
        by_partition[partition].push_back(aspect);
    }
    py::dict quality = base["quality"].cast<py::dict>();
    quality["aspect_ratio"] = distribution(aspect_values, "cell bbox max extent divided by minimum vertex separation");
    py::dict partition_quality;
    for (const auto& [partition, values] : by_partition)
        partition_quality[py::str(partition)] = distribution(values, "cell aspect ratio by declared partition");
    py::dict volume;
    volume["schema"] = "native-volume-quality-witness/v1";
    volume["cells"] = cells;
    volume["partitions"] = partition_quality;
    volume["positive_geometry"] = true;
    volume["full_population"] = true;
    base["quality"] = quality;
    base["volume_quality"] = volume;
    return base;
}

py::dict build_surface_witness(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& vertices,
    const py::list& triangles,
    const py::list& quads,
    const py::object& triangle_reference_normals,
    const py::object& quad_reference_normals)
{
    if (vertices.ndim() != 2 || vertices.shape(1) != 3) return refusal("vertices_Nx3_required");
    const auto* data = vertices.data();
    const size_t n_vertices = static_cast<size_t>(vertices.shape(0));
    std::vector<Point> xyz;
    xyz.reserve(n_vertices);
    for (size_t i = 0; i < n_vertices; ++i) {
        Point p{data[3U * i], data[3U * i + 1U], data[3U * i + 2U]};
        if (!std::ranges::all_of(p, [](double v) { return std::isfinite(v); })) return refusal("nonfinite_vertex");
        xyz.push_back(p);
    }
    auto read_faces = [&](const py::list& source, size_t width, std::vector<std::vector<std::int64_t>>& out) -> bool {
        for (const auto& item : source) {
            if (!py::isinstance<py::sequence>(item)) return false;
            auto ids = item.cast<std::vector<std::int64_t>>();
            if (ids.size() != width) return false;
            for (const auto id : ids) if (id < 0 || static_cast<size_t>(id) >= n_vertices) return false;
            out.push_back(std::move(ids));
        }
        return true;
    };
    std::vector<std::vector<std::int64_t>> tris, quads_vec;
    if (!read_faces(triangles, 3U, tris) || !read_faces(quads, 4U, quads_vec))
        return refusal("surface_face_record_invalid");
    auto normal_for = [&](const std::vector<std::int64_t>& ids, size_t offset) {
        const Point a = xyz[static_cast<size_t>(ids[offset])];
        const Point b = xyz[static_cast<size_t>(ids[(offset + 1U) % ids.size()])];
        const Point c = xyz[static_cast<size_t>(ids[(offset + 2U) % ids.size()])];
        return cross(sub(b, a), sub(c, a));
    };
    auto reference_angle = [&](const py::object& refs, size_t index, const Point& normal) -> std::optional<double> {
        if (refs.is_none()) return std::nullopt;
        if (!py::isinstance<py::sequence>(refs) || static_cast<size_t>(py::len(refs)) <= index) return std::nullopt;
        auto values = refs[py::int_(index)].cast<std::vector<double>>();
        if (values.size() != 3U) return std::nullopt;
        const Point ref{values[0], values[1], values[2]};
        const double nr = norm(ref), nn = norm(normal);
        if (!(nr > 1e-30) || !(nn > 1e-30)) return std::nullopt;
        return std::acos(std::clamp(dot(ref, normal) / (nr * nn), -1.0, 1.0)) * 180.0 / 3.14159265358979323846;
    };

    std::vector<double> tri_ratios, tri_min_angles, tri_max_angles;
    std::vector<double> quad_jacobians, quad_aspects, quad_warpage, quad_min_angles, quad_max_angles, normal_angles;
    py::list tri_records, quad_records;
    std::map<std::pair<std::int64_t, std::int64_t>, int> edges;
    std::set<std::vector<std::int64_t>> unique_faces;
    auto add_edges = [&](const std::vector<std::int64_t>& ids) {
        std::vector<std::int64_t> key = ids;
        std::ranges::sort(key);
        unique_faces.insert(key);
        for (size_t i = 0; i < ids.size(); ++i) {
            const auto a = ids[i], b = ids[(i + 1U) % ids.size()];
            edges[{std::min(a, b), std::max(a, b)}] += 1;
        }
    };
    for (size_t i = 0; i < tris.size(); ++i) {
        add_edges(tris[i]);
        const Point n = normal_for(tris[i], 0U);
        const double area2 = norm(n);
        double edge_sum = 0.0;
        for (size_t j = 0; j < 3U; ++j) {
            const Point d = sub(xyz[static_cast<size_t>(tris[i][(j + 1U) % 3U])], xyz[static_cast<size_t>(tris[i][j])]);
            edge_sum += dot(d, d);
        }
        if (!(area2 > 1e-30) || !(edge_sum > 1e-30)) return refusal("nonpositive_triangle_area");
        const double ratio = 2.0 * std::sqrt(3.0) * area2 / edge_sum;
        if (!(ratio > 0.0) || ratio > 1.0 + 1e-9 || !std::isfinite(ratio)) return refusal("triangle_mean_ratio_invalid");
        auto corner_angle = [](const Point& u, const Point& v) {
            const double denominator = norm(u) * norm(v);
            if (!(denominator > 1e-30)) return std::numeric_limits<double>::quiet_NaN();
            return std::acos(std::clamp(dot(u, v) / denominator, -1.0, 1.0)) *
                   180.0 / 3.14159265358979323846;
        };
        const double angle_a = corner_angle(
            sub(xyz[static_cast<size_t>(tris[i][1])], xyz[static_cast<size_t>(tris[i][0])]),
            sub(xyz[static_cast<size_t>(tris[i][2])], xyz[static_cast<size_t>(tris[i][0])]));
        const double angle_b = corner_angle(
            sub(xyz[static_cast<size_t>(tris[i][0])], xyz[static_cast<size_t>(tris[i][1])]),
            sub(xyz[static_cast<size_t>(tris[i][2])], xyz[static_cast<size_t>(tris[i][1])]));
        const double angle_c = corner_angle(
            sub(xyz[static_cast<size_t>(tris[i][0])], xyz[static_cast<size_t>(tris[i][2])]),
            sub(xyz[static_cast<size_t>(tris[i][1])], xyz[static_cast<size_t>(tris[i][2])]));
        const double min_angle = std::min({angle_a, angle_b, angle_c});
        const double max_angle = std::max({angle_a, angle_b, angle_c});
        if (!std::isfinite(min_angle) || !std::isfinite(max_angle)) return refusal("triangle_angle_invalid");
        tri_ratios.push_back(ratio);
        tri_min_angles.push_back(min_angle);
        tri_max_angles.push_back(max_angle);
        py::dict row; row["face_index"] = static_cast<std::int64_t>(i); row["mean_ratio"] = ratio;
        row["min_angle"] = min_angle; row["max_angle"] = max_angle;
        auto angle = reference_angle(triangle_reference_normals, i, n);
        if (angle.has_value()) { row["surface_angle_deviation"] = *angle; normal_angles.push_back(*angle); }
        else row["surface_angle_deviation"] = py::none();
        tri_records.append(row);
    }
    for (size_t i = 0; i < quads_vec.size(); ++i) {
        add_edges(quads_vec[i]);
        const Point n0 = normal_for(quads_vec[i], 0U);
        const Point n1 = normal_for(quads_vec[i], 2U);
        const Point normal = add(n0, n1);
        const double nn = norm(normal);
        if (!(nn > 1e-30)) return refusal("nonpositive_quad_area");
        double min_j = std::numeric_limits<double>::infinity();
        double min_edge = std::numeric_limits<double>::infinity();
        double max_edge = 0.0;
        for (size_t j = 0; j < 4U; ++j) {
            const Point at = xyz[static_cast<size_t>(quads_vec[i][j])];
            const Point next = xyz[static_cast<size_t>(quads_vec[i][(j + 1U) % 4U])];
            const Point prev = xyz[static_cast<size_t>(quads_vec[i][(j + 3U) % 4U])];
            const double en = norm(sub(next, at));
            const double ep = norm(sub(prev, at));
            if (!(en > 1e-30) || !(ep > 1e-30)) return refusal("zero_quad_edge");
            const double length = en;
            min_edge = std::min(min_edge, length); max_edge = std::max(max_edge, length);
            min_j = std::min(min_j, dot(cross(sub(next, at), sub(prev, at)), mul(normal, 1.0 / nn)) / (en * ep));
        }
        if (!(min_j > 1e-12) || !(min_edge > 1e-30)) return refusal("quad_nonconvex_or_inverted");
        const double aspect = max_edge / min_edge;
        const double n0n = norm(n0), n1n = norm(n1);
        const double warpage = 1.0 - std::clamp(dot(n0, n1) / (n0n * n1n), -1.0, 1.0);
        double min_angle = std::numeric_limits<double>::infinity();
        double max_angle = 0.0;
        for (size_t j = 0; j < 4U; ++j) {
            const Point at = xyz[static_cast<size_t>(quads_vec[i][j])];
            const Point next = xyz[static_cast<size_t>(quads_vec[i][(j + 1U) % 4U])];
            const Point prev = xyz[static_cast<size_t>(quads_vec[i][(j + 3U) % 4U])];
            const double denominator = norm(sub(next, at)) * norm(sub(prev, at));
            if (!(denominator > 1e-30)) return refusal("quad_angle_invalid");
            const double angle = std::acos(std::clamp(
                dot(sub(next, at), sub(prev, at)) / denominator, -1.0, 1.0)) *
                180.0 / 3.14159265358979323846;
            min_angle = std::min(min_angle, angle);
            max_angle = std::max(max_angle, angle);
        }
        if (!std::isfinite(aspect) || !std::isfinite(warpage) ||
            !std::isfinite(min_angle) || !std::isfinite(max_angle))
            return refusal("quad_metric_nonfinite");
        quad_jacobians.push_back(min_j); quad_aspects.push_back(aspect);
        quad_warpage.push_back(warpage); quad_min_angles.push_back(min_angle);
        quad_max_angles.push_back(max_angle);
        py::dict row; row["face_index"] = static_cast<std::int64_t>(i);
        row["scaled_jacobian"] = min_j; row["aspect_ratio"] = aspect; row["warpage"] = warpage;
        row["min_angle"] = min_angle; row["max_angle"] = max_angle;
        auto angle = reference_angle(quad_reference_normals, i, normal);
        if (angle.has_value()) { row["surface_angle_deviation"] = *angle; normal_angles.push_back(*angle); }
        else row["surface_angle_deviation"] = py::none();
        quad_records.append(row);
    }
    int boundary_edges = 0, nonmanifold_edges = 0;
    for (const auto& [edge, count] : edges) {
        if (count == 1) ++boundary_edges;
        if (count > 2) ++nonmanifold_edges;
    }
    const int total_faces = static_cast<int>(tris.size() + quads_vec.size());
    const int duplicate_faces = total_faces - static_cast<int>(unique_faces.size());
    py::dict topology;
    topology["boundary_edges"] = boundary_edges; topology["nonmanifold_edges"] = nonmanifold_edges;
    topology["duplicate_faces"] = duplicate_faces;
    topology["closed_manifold"] = boundary_edges == 0 && nonmanifold_edges == 0 && duplicate_faces == 0;
    py::dict quality;
    quality["tri_mean_ratio"] = distribution(tri_ratios, "4*sqrt(3)*triangle_area divided by sum squared edge lengths");
    quality["tri_min_angle"] = distribution(tri_min_angles, "minimum triangle corner angle in degrees");
    quality["tri_max_angle"] = distribution(tri_max_angles, "maximum triangle corner angle in degrees");
    quality["quad_scaled_jacobian"] = distribution(quad_jacobians, "minimum corner scaled Jacobian");
    quality["quad_aspect_ratio"] = distribution(quad_aspects, "maximum quad edge divided by minimum quad edge");
    quality["quad_min_angle"] = distribution(quad_min_angles, "minimum quad corner angle in degrees");
    quality["quad_max_angle"] = distribution(quad_max_angles, "maximum quad corner angle in degrees");
    quality["quad_warpage"] = distribution(quad_warpage, "one minus split-triangle normal cosine");
    quality["surface_angle_deviation"] = distribution(normal_angles, "angle between output and supplied source normal in degrees");
    py::dict out;
    out["accepted"] = true; out["status"] = "measured"; out["quality"] = quality;
    out["topology"] = topology; out["triangles"] = tri_records; out["quads"] = quad_records;
    out["n_vertices"] = static_cast<std::int64_t>(n_vertices);
    out["n_triangles"] = static_cast<std::int64_t>(tris.size());
    out["n_quads"] = static_cast<std::int64_t>(quads_vec.size());
    return out;
}


py::dict build_full_volume_witness(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::list& faces,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& owner,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& neighbour,
    const py::object& partitions,
    const py::object& cell_uids)
{
    if (partitions.is_none() || cell_uids.is_none())
        return refusal("full_readback_partition_or_uid_missing");
    if (!py::isinstance<py::sequence>(partitions) ||
        !py::isinstance<py::sequence>(cell_uids))
        return refusal("full_readback_partition_or_uid_sequence");
    const size_t n_faces = static_cast<size_t>(faces.size());
    if (static_cast<size_t>(owner.size()) != n_faces ||
        static_cast<size_t>(neighbour.size()) > n_faces)
        return refusal("full_readback_incidence_length");
    std::int64_t max_cell = -1;
    const auto* owner_data = owner.data();
    const auto* neighbour_data = neighbour.data();
    for (py::ssize_t i = 0; i < owner.size(); ++i) max_cell = std::max(max_cell, owner_data[i]);
    for (py::ssize_t i = 0; i < neighbour.size(); ++i) max_cell = std::max(max_cell, neighbour_data[i]);
    const size_t n_cells = max_cell < 0 ? 0U : static_cast<size_t>(max_cell + 1);
    if (n_cells == 0U || static_cast<size_t>(py::len(partitions)) != n_cells ||
        static_cast<size_t>(py::len(cell_uids)) != n_cells)
        return refusal("full_readback_population_length");

    std::vector<std::string> uids;
    std::set<std::string> unique_uids;
    uids.reserve(n_cells);
    for (size_t ci = 0; ci < n_cells; ++ci) {
        if (!py::isinstance<py::str>(cell_uids[py::int_(ci)]))
            return refusal("cell_uid_not_string");
        const auto uid = cell_uids[py::int_(ci)].cast<std::string>();
        if (uid.empty() || !unique_uids.insert(uid).second)
            return refusal("cell_uid_not_unique");
        uids.push_back(uid);
    }

    if (points.ndim() != 2 || points.shape(1) != 3)
        return refusal("full_readback_points_shape");
    const auto* point_data = points.data();
    std::vector<Point> xyz;
    xyz.reserve(static_cast<size_t>(points.shape(0)));
    for (py::ssize_t i = 0; i < points.shape(0); ++i) {
        Point p{point_data[3U * static_cast<size_t>(i)],
                point_data[3U * static_cast<size_t>(i) + 1U],
                point_data[3U * static_cast<size_t>(i) + 2U]};
        if (!std::ranges::all_of(p, [](double v) { return std::isfinite(v); }))
            return refusal("nonfinite_point");
        xyz.push_back(p);
    }

    std::vector<std::vector<std::int64_t>> topology;
    topology.reserve(n_faces);
    std::vector<std::set<std::int64_t>> vertices(n_cells);
    for (size_t fi = 0; fi < n_faces; ++fi) {
        if (!py::isinstance<py::sequence>(faces[py::int_(fi)]))
            return refusal("full_readback_face_record");
        auto face = faces[py::int_(fi)].cast<std::vector<std::int64_t>>();
        if (face.size() < 3U) return refusal("face_has_fewer_than_three_vertices");
        if (owner_data[fi] < 0 || owner_data[fi] >= static_cast<std::int64_t>(n_cells))
            return refusal("owner_cell_out_of_range");
        for (const auto id : face) {
            if (id < 0 || id >= points.shape(0))
                return refusal("face_vertex_out_of_range");
            vertices[static_cast<size_t>(owner_data[fi])].insert(id);
        }
        if (fi < static_cast<size_t>(neighbour.size())) {
            const auto id = neighbour_data[fi];
            if (id < 0 || id >= static_cast<std::int64_t>(n_cells))
                return refusal("neighbour_cell_out_of_range");
            for (const auto vertex : face) vertices[static_cast<size_t>(id)].insert(vertex);
        }
        topology.push_back(std::move(face));
    }

    std::vector<Point> centres(n_cells, Point{0.0, 0.0, 0.0});
    for (size_t ci = 0; ci < n_cells; ++ci) {
        if (vertices[ci].empty()) return refusal("cell_without_vertices");
        for (const auto id : vertices[ci]) centres[ci] = add(centres[ci], xyz[static_cast<size_t>(id)]);
        centres[ci] = mul(centres[ci], 1.0 / static_cast<double>(vertices[ci].size()));
    }

    // The strict path refuses a reversed internal winding instead of masking it with abs().
    for (size_t fi = 0; fi < static_cast<size_t>(neighbour.size()); ++fi) {
        const auto& face = topology[fi];
        Point centre{0.0, 0.0, 0.0};
        for (const auto id : face) centre = add(centre, xyz[static_cast<size_t>(id)]);
        centre = mul(centre, 1.0 / static_cast<double>(face.size()));
        Point area{0.0, 0.0, 0.0};
        const Point anchor = xyz[static_cast<size_t>(face[0])];
        for (size_t j = 1; j + 1U < face.size(); ++j)
            area = add(area, cross(sub(xyz[static_cast<size_t>(face[j])], anchor),
                                   sub(xyz[static_cast<size_t>(face[j + 1U])], anchor)));
        const Point d = sub(centres[static_cast<size_t>(neighbour_data[fi])],
                            centres[static_cast<size_t>(owner_data[fi])]);
        const double area_norm = norm(area);
        const double d_norm = norm(d);
        const double oriented = dot(d, area);
        if (!(area_norm > 1e-30) || !(d_norm > 1e-30) ||
            !(oriented > 1e-12 * area_norm * d_norm))
            return refusal("reversed_internal_winding");
    }

    std::vector<double> signed_volumes(n_cells, 0.0);
    for (size_t fi = 0; fi < static_cast<size_t>(faces.size()); ++fi) {
        const auto& face = topology[fi];
        const std::int64_t owner_id = owner_data[fi];
        Point area{0.0, 0.0, 0.0};
        Point face_centre{0.0, 0.0, 0.0};
        const Point anchor = xyz[static_cast<size_t>(face[0])];
        for (size_t j = 1; j + 1U < face.size(); ++j)
            area = add(area, cross(sub(xyz[static_cast<size_t>(face[j])], anchor),
                                   sub(xyz[static_cast<size_t>(face[j + 1U])], anchor)));
        for (const auto id : face) face_centre = add(face_centre, xyz[static_cast<size_t>(id)]);
        face_centre = mul(face_centre, 1.0 / static_cast<double>(face.size()));
        signed_volumes[static_cast<size_t>(owner_id)] += dot(area, sub(face_centre, centres[static_cast<size_t>(owner_id)])) / 6.0;
        if (fi < static_cast<size_t>(neighbour.size())) {
            const std::int64_t neighbour_id = neighbour_data[fi];
            signed_volumes[static_cast<size_t>(neighbour_id)] += dot(mul(area, -1.0), sub(face_centre, centres[static_cast<size_t>(neighbour_id)])) / 6.0;
        }
    }
    for (const double volume : signed_volumes) {
        if (!std::isfinite(volume)) return refusal("nonfinite_signed_cell_volume");
    }
    py::dict result = build_volume_witness(
        points, faces, owner, neighbour, partitions, cell_uids);
    bool positive_geometry = true;
    for (const double volume : signed_volumes) positive_geometry = positive_geometry && volume > 1e-30;
    result["volume_quality"].cast<py::dict>()["positive_geometry"] = positive_geometry;
    if (!result["accepted"].cast<bool>()) return result;
    result["schema"] = "autotessell/native-volume-quality-witness/v2";
    result["orientation_checked"] = true;
    result["full_population"] = true;
    result["cell_uid_count"] = static_cast<std::int64_t>(n_cells);
    result["partition_count"] = static_cast<std::int64_t>(py::len(partitions));

    py::dict quality = result["quality"].cast<py::dict>();
    quality["orientation_definition"] = "owner-to-neighbour oriented area vector";
    auto worst_face_uid = [&](const char* metric, bool internal_only) -> py::object {
        py::list records = result["faces"].cast<py::list>();
        double best = -std::numeric_limits<double>::infinity();
        std::int64_t best_owner = 0;
        bool found = false;
        for (const auto& handle : records) {
            py::dict record = handle.cast<py::dict>();
            if (internal_only && record["face_class"].cast<std::string>() != "internal") continue;
            if (!record.contains(metric) || record[metric].is_none()) continue;
            const double value = record[metric].cast<double>();
            if (std::isfinite(value) && value > best) {
                best = value;
                best_owner = record["owner_cell"].cast<std::int64_t>();
                found = true;
            }
        }
        return found ? py::cast(uids[static_cast<size_t>(best_owner)]) : py::none();
    };
    quality["internal_non_orthogonality"].cast<py::dict>()["worst_uid"] =
        worst_face_uid("non_orthogonality", true);
    quality["internal_skewness"].cast<py::dict>()["worst_uid"] =
        worst_face_uid("skewness", true);
    quality["release_skew"].cast<py::dict>()["worst_uid"] = worst_face_uid("skewness", false);
    quality["release_skew"].cast<py::dict>() =
        quality["release_skew"].cast<py::dict>();
    py::list cell_records = result["volume_quality"].cast<py::dict>()["cells"].cast<py::list>();
    for (const auto& handle : cell_records) {
        py::dict record = handle.cast<py::dict>();
        const auto cell_index = record["cell_index"].cast<std::int64_t>();
        record["signed_volume"] = signed_volumes[static_cast<size_t>(cell_index)];
        record["volume"] = signed_volumes[static_cast<size_t>(cell_index)];
    }
    double best_aspect = -std::numeric_limits<double>::infinity();
    py::object best_aspect_uid = py::none();
    for (const auto& handle : cell_records) {
        py::dict record = handle.cast<py::dict>();
        const double value = record["aspect_ratio"].cast<double>();
        if (std::isfinite(value) && value > best_aspect) {
            best_aspect = value;
            best_aspect_uid = record["cell_uid"];
        }
    }
    quality["aspect_ratio"].cast<py::dict>()["worst_uid"] = best_aspect_uid;
    return result;
}


py::dict build_authority_bound_volume_witness(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::list& faces,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& owner,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& neighbour,
    const py::object& partitions,
    const py::object& cell_uids)
{
    py::dict base = build_full_volume_witness(points, faces, owner, neighbour, partitions, cell_uids);
    if (!base["accepted"].cast<bool>()) return base;
    const auto* pd = points.data(); const auto* od = owner.data(); const auto* nd = neighbour.data();
    const size_t nf = static_cast<size_t>(faces.size());
    std::vector<Point> xyz; xyz.reserve(static_cast<size_t>(points.shape(0)));
    for (py::ssize_t i=0;i<points.shape(0);++i) xyz.push_back({pd[3U*static_cast<size_t>(i)],pd[3U*static_cast<size_t>(i)+1U],pd[3U*static_cast<size_t>(i)+2U]});
    std::vector<std::vector<std::int64_t>> topo; topo.reserve(nf);
    std::int64_t max_cell=-1;
    for (py::ssize_t i=0;i<owner.size();++i) max_cell=std::max(max_cell,od[i]);
    for (py::ssize_t i=0;i<neighbour.size();++i) max_cell=std::max(max_cell,nd[i]);
    if (max_cell<0) return refusal("empty_cell_incidence");
    const size_t nc=static_cast<size_t>(max_cell+1);
    struct Inc { size_t face; int sign; };
    std::vector<std::vector<Inc>> cell_faces(nc); std::vector<std::set<std::int64_t>> verts(nc);
    std::set<std::vector<std::int64_t>> unique_faces; std::map<std::pair<std::int64_t,std::int64_t>,int> edge_counts;
    for(size_t fi=0;fi<nf;++fi){
        auto f=faces[py::int_(fi)].cast<std::vector<std::int64_t>>(); if(f.size()<3U) return refusal("face_has_fewer_than_three_vertices");
        for(auto id:f){if(id<0||id>=points.shape(0))return refusal("face_vertex_out_of_range");verts[static_cast<size_t>(od[fi])].insert(id);}
        if(!unique_faces.insert(f).second)return refusal("duplicate_face");
        cell_faces[static_cast<size_t>(od[fi])].push_back({fi,1});
        for(size_t j=0;j<f.size();++j){auto a=f[j],b=f[(j+1U)%f.size()];if(a>b)std::swap(a,b);++edge_counts[{a,b}];}
        if(fi<static_cast<size_t>(neighbour.size())){auto id=nd[fi];if(id<0||id>=static_cast<std::int64_t>(nc))return refusal("neighbour_cell_out_of_range");for(auto v:f)verts[static_cast<size_t>(id)].insert(v);cell_faces[static_cast<size_t>(id)].push_back({fi,-1});}
        topo.push_back(std::move(f));
    }
    std::vector<Point> centres(nc); std::vector<double> volumes(nc,0.0), aspects; std::map<std::string,std::vector<double>> exact_partitions; std::vector<double> internal_no, internal_skew, boundary_skew, release_skew;
    py::list cell_records;
    for(size_t ci=0;ci<nc;++ci){
        if(cell_faces[ci].empty()||verts[ci].size()<4U)return refusal("cell_without_closed_geometry");
        Point rough{};for(auto id:verts[ci])rough=add(rough,xyz[static_cast<size_t>(id)]);rough=mul(rough,1.0/static_cast<double>(verts[ci].size()));
        Point first_moment{}; double volume=0.0; int winding=0;
        for(const auto inc:cell_faces[ci]){const auto&f=topo[inc.face];const Point a=xyz[static_cast<size_t>(f[0])];Point area{};for(size_t j=1;j+1U<f.size();++j){Point b=xyz[static_cast<size_t>(f[j])],c=xyz[static_cast<size_t>(f[j+1U])];area=add(area,cross(sub(b,a),sub(c,a)));double v=inc.sign*dot(a,cross(b,c))/6.0;volume+=v;first_moment=add(first_moment,mul(add(add(a,b),c),v/4.0));}double side=inc.sign*dot(area,sub(rough,a));if(std::abs(side)<=1e-12)return refusal("coplanar_cell_face_orientation");int sign=side>0?1:-1;if(winding==0)winding=sign;else if(sign!=winding)return refusal("inconsistent_cell_face_orientation");}
        if(!(std::abs(volume)>1e-12)||!std::isfinite(volume))return refusal("nonpositive_oriented_cell_volume");
        if(volume<0.){volume=-volume;first_moment=mul(first_moment,-1.0);}
        volumes[ci]=volume; centres[ci]=mul(first_moment,1.0/volume);
        double diameter=0.0,min_height=std::numeric_limits<double>::infinity(); std::vector<std::int64_t> ids(verts[ci].begin(),verts[ci].end());
        for(size_t i=0;i<ids.size();++i)for(size_t j=i+1U;j<ids.size();++j)diameter=std::max(diameter,norm(sub(xyz[static_cast<size_t>(ids[i])],xyz[static_cast<size_t>(ids[j])])));
        for(const auto inc:cell_faces[ci]){const auto&f=topo[inc.face];Point area{};const Point a=xyz[static_cast<size_t>(f[0])];for(size_t j=1;j+1U<f.size();++j)area=add(area,cross(sub(xyz[static_cast<size_t>(f[j])],a),sub(xyz[static_cast<size_t>(f[j+1U])],a)));double an=norm(area);if(!(an>1e-30))return refusal("zero_face_area");min_height=std::min(min_height,std::abs(dot(mul(area,1.0/an),sub(centres[ci],a))));}
        if(!(min_height>1e-30)||!std::isfinite(diameter/min_height))return refusal("unmeasurable_face_pyramid_aspect");
        double aspect=diameter/min_height;aspects.push_back(aspect);std::string partition="core";if(!partitions.is_none())partition=partitions[py::int_(ci)].cast<std::string>();exact_partitions[partition].push_back(aspect);py::dict row;row["cell_index"]=static_cast<std::int64_t>(ci);row["volume"]=volume;row["centroid"]=std::vector<double>{centres[ci][0],centres[ci][1],centres[ci][2]};row["aspect_ratio"]=aspect;row["positive_geometry"]=true;cell_records.append(row);
    }
    for(size_t fi=0;fi<static_cast<size_t>(neighbour.size());++fi){const auto&f=topo[fi];Point area{};const Point a=xyz[static_cast<size_t>(f[0])];Point fc{};for(auto id:f)fc=add(fc,xyz[static_cast<size_t>(id)]);fc=mul(fc,1.0/static_cast<double>(f.size()));for(size_t j=1;j+1U<f.size();++j)area=add(area,cross(sub(xyz[static_cast<size_t>(f[j])],a),sub(xyz[static_cast<size_t>(f[j+1U])],a)));Point d=sub(centres[static_cast<size_t>(nd[fi])],centres[static_cast<size_t>(od[fi])]);double an=norm(area),dn=norm(d);if(!(an>1e-30)||!(dn>1e-30))return refusal("zero_internal_geometry");double no=std::acos(std::clamp(std::abs(dot(area,d))/(an*dn),0.0,1.0))*180.0/3.14159265358979323846;double proj=dot(sub(fc,centres[static_cast<size_t>(od[fi])]),d)/dot(d,d);double sk=norm(sub(sub(fc,centres[static_cast<size_t>(od[fi])]),mul(d,proj)))/dn;internal_no.push_back(no);internal_skew.push_back(sk);release_skew.push_back(sk);}
    for(size_t fi=static_cast<size_t>(neighbour.size());fi<nf;++fi){const auto&f=topo[fi];Point area{};const Point a=xyz[static_cast<size_t>(f[0])];Point fc{};for(auto id:f)fc=add(fc,xyz[static_cast<size_t>(id)]);fc=mul(fc,1.0/static_cast<double>(f.size()));for(size_t j=1;j+1U<f.size();++j)area=add(area,cross(sub(xyz[static_cast<size_t>(f[j])],a),sub(xyz[static_cast<size_t>(f[j+1U])],a)));double an=norm(area);Point delta=sub(fc,centres[static_cast<size_t>(od[fi])]);double h=std::abs(dot(mul(area,1.0/an),delta));if(!(h>1e-30))return refusal("zero_boundary_normal_distance");double sk=norm(sub(delta,mul(mul(area,1.0/an),dot(mul(area,1.0/an),delta))))/h;boundary_skew.push_back(sk);release_skew.push_back(sk);}
    py::dict quality=base["quality"].cast<py::dict>();quality["internal_non_orthogonality"]=distribution(internal_no,"owner-neighbour cell-centre to face-normal angle in degrees");quality["internal_skewness"]=distribution(internal_skew,"normalized internal face-centre residual from owner-neighbour line");quality["boundary_skewness"]=distribution(boundary_skew,"normalized boundary face-centre residual from owner-normal line");quality["release_skew"]=distribution(release_skew,"typed internal and boundary face-centre residual");quality["aspect_ratio"]=distribution(aspects,"cell diameter divided by minimum face-normal centroid height");quality["centres_definition"]="oriented face-pyramid centroid";quality["aspect_definition"]="face-pyramid height, not bbox/min-edge";
    py::dict volume=base["volume_quality"].cast<py::dict>();volume["cells"]=cell_records;py::dict exact_partition_quality;for(const auto&[name,values]:exact_partitions)exact_partition_quality[py::str(name)]=distribution(values,"exact cell diameter divided by minimum face-normal centroid height by declared partition");volume["partitions"]=exact_partition_quality;volume["aspect_definition"]="cell diameter divided by minimum face-normal centroid height";volume["oriented_volume_sum"]=volumes;volume["positive_geometry"]=true;base["quality"]=quality;base["volume_quality"]=volume;base["schema"]="autotessell/native-authority-bound-quality-witness/v1";base["geometry_readback"]=true;base["authority_bound_metrics"]=true;return base;
}
