// C++23 surface partition transaction contract.
// It checks immutable source binding and rejects the unsafe original-face
// prefix plus appended-strip pattern before any publication route.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <limits>
#include <set>
#include <string>

namespace py = pybind11;
using Tri = std::array<std::int64_t, 3>;
using Point = std::array<double, 3>;

namespace {

Point sub(const Point& a, const Point& b) noexcept { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point cross(const Point& a, const Point& b) noexcept { return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]}; }
double norm(const Point& p) noexcept { return std::sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2]); }

py::dict refuse(const std::string& reason, std::int64_t requested) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "surface_partition_refused_rollback";
    result["reason"] = reason;
    result["requested_layers"] = requested;
    result["actual_layers"] = 0;
    result["source_immutable"] = true;
    result["candidate_discarded"] = true;
    result["publication_eligible"] = false;
    return result;
}

Tri triangle_at(const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& triangles, py::ssize_t row) {
    const auto* data = triangles.data() + static_cast<std::size_t>(row) * 3U;
    return {data[0], data[1], data[2]};
}

double area(const py::array_t<double, py::array::c_style | py::array::forcecast>& points, const Tri& triangle) {
    const auto* data = points.data();
    auto point = [&](std::int64_t id) {
        const auto offset = static_cast<std::size_t>(id) * 3U;
        return Point{data[offset], data[offset + 1U], data[offset + 2U]};
    };
    return 0.5 * norm(cross(sub(point(triangle[1]), point(triangle[0])), sub(point(triangle[2]), point(triangle[0]))));
}

py::dict validate_partition(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& source_triangles,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& output_triangles,
    const py::list& lineage,
    std::int64_t requested_layers,
    bool authoritative_source,
    const py::list& retained_source_faces,
    double minimum_area = 1.0e-14) {
    if (requested_layers < 0) return refuse("negative_layer_count", requested_layers);
    if (!authoritative_source) return refuse("source_authority_missing", requested_layers);
    if (points.ndim() != 2 || points.shape(1) != 3 || source_triangles.ndim() != 2 || source_triangles.shape(1) != 3 || output_triangles.ndim() != 2 || output_triangles.shape(1) != 3) throw std::invalid_argument("points Nx3 and triangles Tx3 are required");
    if (!std::isfinite(minimum_area) || minimum_area <= 0.0) return refuse("minimum_area_invalid", requested_layers);
    if (lineage.size() != static_cast<size_t>(output_triangles.shape(0))) return refuse("lineage_output_coverage_incomplete", requested_layers);
    if (!retained_source_faces.empty()) return refuse("original_surface_prefix_forbidden", requested_layers);
    std::set<Tri> output_seen;
    std::map<std::pair<std::int64_t, std::int64_t>, std::int64_t> edge_incidence;
    std::set<std::int64_t> source_coverage;
    double minimum_output_area = std::numeric_limits<double>::infinity();
    std::set<std::string> roles;
    for (py::ssize_t row = 0; row < output_triangles.shape(0); ++row) {
        const Tri triangle = triangle_at(output_triangles, row);
        for (const auto id : triangle) if (id < 0 || id >= points.shape(0)) return refuse("output_vertex_out_of_range", requested_layers);
        if (triangle[0] == triangle[1] || triangle[0] == triangle[2] || triangle[1] == triangle[2]) return refuse("output_degenerate_triangle", requested_layers);
        if (!output_seen.insert(Tri{std::min({triangle[0], triangle[1], triangle[2]}), std::max(std::min(triangle[0], triangle[1]), std::min(triangle[1], triangle[2])), std::max({triangle[0], triangle[1], triangle[2]})}).second) return refuse("output_duplicate_triangle", requested_layers);
        const double measure = area(points, triangle);
        if (!std::isfinite(measure) || measure <= minimum_area) return refuse("output_nonpositive_area", requested_layers);
        minimum_output_area = std::min(minimum_output_area, measure);
        for (std::size_t edge = 0; edge < 3U; ++edge) {
            const auto a = triangle[edge];
            const auto b = triangle[(edge + 1U) % 3U];
            edge_incidence[a < b ? std::pair{a, b} : std::pair{b, a}] += 1;
        }
        if (!py::isinstance<py::dict>(lineage[row])) return refuse("lineage_record_invalid", requested_layers);
        const py::dict record = lineage[row].cast<py::dict>();
        for (const char* key : {"output_id", "source_face", "operation", "role", "feature", "patch", "physical_group", "component", "provenance"}) if (!record.contains(key) || record[key].is_none()) return refuse("lineage_record_incomplete", requested_layers);
        try {
            if (record["output_id"].cast<std::int64_t>() != row || record["source_face"].cast<std::int64_t>() < 0 || record["source_face"].cast<std::int64_t>() >= source_triangles.shape(0)) return refuse("lineage_owner_mismatch", requested_layers);
            source_coverage.insert(record["source_face"].cast<std::int64_t>());
        } catch (...) { return refuse("lineage_id_invalid", requested_layers); }
        roles.insert(record["role"].cast<std::string>());
        for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) if (record[key].cast<std::string>().empty()) return refuse("lineage_semantic_empty", requested_layers);
        if (requested_layers == 0 && (record["operation"].cast<std::string>() != "identity" || record["role"].cast<std::string>() != "wall")) return refuse("bl0_identity_contract_failed", requested_layers);
        if (requested_layers > 0 && record["operation"].cast<std::string>() == "identity") return refuse("bl_positive_identity_face_forbidden", requested_layers);
    }
    for (const auto& [edge, count] : edge_incidence) if (count > 2) return refuse("output_nonmanifold_edge", requested_layers);
    if (source_coverage.size() != static_cast<size_t>(source_triangles.shape(0))) return refuse("source_face_coverage_incomplete", requested_layers);
    if (requested_layers > 0 && !(roles.contains("wall") && roles.contains("inner") && roles.contains("outer"))) return refuse("bl_role_partition_incomplete", requested_layers);
    if (requested_layers == 0) {
        if (output_triangles.shape(0) != source_triangles.shape(0)) return refuse("bl0_topology_identity_failed", requested_layers);
        for (py::ssize_t row = 0; row < source_triangles.shape(0); ++row) if (triangle_at(source_triangles, row) != triangle_at(output_triangles, row)) return refuse("bl0_index_identity_failed", requested_layers);
    }
    py::dict quality;
    quality["minimum_output_area"] = minimum_output_area;
    quality["duplicate"] = 0;
    quality["non_manifold"] = 0;
    quality["source_face_coverage"] = source_coverage.size();
    py::dict result;
    result["accepted"] = true;
    result["status"] = requested_layers == 0 ? "surface_partition_identity_passed" : "surface_partition_replacement_passed";
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = requested_layers;
    result["source_immutable"] = true;
    result["original_surface_prefix_retained"] = false;
    result["strict_topology_readback"] = true;
    result["quality"] = quality;
    result["candidate_discarded"] = false;
    result["publication_eligible"] = false;
    return result;
}

}  // namespace

PYBIND11_MODULE(native_surface_bl_partition_transaction, module) {
    module.doc() = "C++23 source-replacing surface partition transaction contract";
    module.def("validate_surface_partition", &validate_partition,
               py::arg("points"), py::arg("source_triangles"), py::arg("output_triangles"),
               py::arg("lineage"), py::arg("requested_layers"), py::arg("authoritative_source"),
               py::arg("retained_source_faces") = py::list(), py::arg("minimum_area") = 1.0e-14);
}
