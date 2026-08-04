#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "native_tet_polymesh_persisted_reader.hpp"
#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

namespace py = pybind11;
using Point = std::array<double, 3>;

namespace {

Point sub(Point a, Point b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point add(Point a, Point b) { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
Point scale(Point a, double value) { return {a[0] * value, a[1] * value, a[2] * value}; }
Point cross(Point a, Point b) {
    return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]};
}
double dot(Point a, Point b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double norm(Point a) { return std::sqrt(dot(a, a)); }

py::dict refuse(const std::string& reason) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "native-tet-persisted-volume-refused";
    result["reason"] = reason;
    result["candidate_discarded"] = true;
    result["publication_eligible"] = false;
    result["rollback_required"] = true;
    return result;
}

bool string_field(const py::dict& row, const char* key, std::string& value) {
    if (!row.contains(key) || !py::isinstance<py::str>(row[key])) return false;
    value = row[key].cast<std::string>();
    return !value.empty();
}

bool same_cycle(const std::vector<int>& expected, const std::vector<int>& actual) {
    if (expected.size() != 3 || actual.size() != 3) return false;
    for (int rotation = 0; rotation < 3; ++rotation) {
        if (expected[0] == actual[static_cast<std::size_t>(rotation)] &&
            expected[1] == actual[static_cast<std::size_t>((rotation + 1) % 3)] &&
            expected[2] == actual[static_cast<std::size_t>((rotation + 2) % 3)]) return true;
    }
    return false;
}

std::vector<int> vertex_ids(const py::handle& value) {
    return value.cast<std::vector<int>>();
}


py::dict read_authoritative_volume_artifact(const std::string& root_arg, const py::dict& authority) {
    autotessell_tet_polymesh::Artifact artifact;
    if (!autotessell_tet_polymesh::read_artifact(std::filesystem::path(root_arg), artifact)) {
        return refuse(artifact.error.empty() ? "persisted_reader_failed" : artifact.error);
    }
    if (!authority.contains("source_faces") || !py::isinstance<py::list>(authority["source_faces"])) {
        return refuse("source_authority_faces_missing");
    }
    const py::list source_faces = authority["source_faces"].cast<py::list>();
    if (source_faces.empty()) return refuse("source_authority_faces_empty");
    std::map<std::string, py::dict> source_by_id;
    std::set<std::string> matched_source_ids;
    for (const auto item : source_faces) {
        if (!py::isinstance<py::dict>(item)) return refuse("source_authority_face_invalid");
        const py::dict source = item.cast<py::dict>();
        std::string id;
        if (!string_field(source, "source_face_id", id) || source_by_id.contains(id) ||
            !source.contains("source_vertex_ids")) return refuse("source_authority_face_identity_invalid");
        for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) {
            std::string ignored;
            if (!string_field(source, key, ignored)) return refuse("source_authority_semantics_missing");
        }
        const auto vertices = vertex_ids(source["source_vertex_ids"]);
        if (vertices.size() != 3 || std::set<int>(vertices.begin(), vertices.end()).size() != 3) {
            return refuse("source_authority_face_vertices_invalid");
        }
        source_by_id.emplace(id, source);
    }

    const std::size_t internal_faces = artifact.neighbour.size();
    std::map<std::array<int, 3>, int> face_counts;
    for (const auto& face : artifact.faces) {
        std::array<int, 3> key{face[0], face[1], face[2]};
        std::sort(key.begin(), key.end());
        ++face_counts[key];
    }
    const int duplicate_faces = static_cast<int>(std::count_if(
        face_counts.begin(), face_counts.end(), [](const auto& item) { return item.second > 1; }));
    const int non_manifold_faces = static_cast<int>(std::count_if(
        face_counts.begin(), face_counts.end(), [](const auto& item) { return item.second > 2; }));
    if (duplicate_faces != 0 || non_manifold_faces != 0) return refuse("persisted_topology_duplicate_or_nonmanifold");

    const int cell_count = artifact.owner.empty() ? 0 : *std::max_element(artifact.owner.begin(), artifact.owner.end()) + 1;
    if (cell_count <= 0) return refuse("persisted_volume_cells_missing");
    std::vector<std::set<int>> cell_vertices(static_cast<std::size_t>(cell_count));
    std::vector<std::vector<std::size_t>> cell_faces(static_cast<std::size_t>(cell_count));
    for (std::size_t face_id = 0; face_id < artifact.faces.size(); ++face_id) {
        const int owner = artifact.owner[face_id];
        cell_faces[static_cast<std::size_t>(owner)].push_back(face_id);
        cell_vertices[static_cast<std::size_t>(owner)].insert(artifact.faces[face_id].begin(), artifact.faces[face_id].end());
        if (face_id < internal_faces) {
            const int neighbour = artifact.neighbour[face_id];
            cell_faces[static_cast<std::size_t>(neighbour)].push_back(face_id);
            cell_vertices[static_cast<std::size_t>(neighbour)].insert(artifact.faces[face_id].begin(), artifact.faces[face_id].end());
        }
    }
    for (const auto& vertices : cell_vertices) {
        if (vertices.size() != 4) return refuse("persisted_volume_cell_not_tet");
    }

    std::vector<Point> centers(static_cast<std::size_t>(cell_count));
    std::vector<double> volumes(static_cast<std::size_t>(cell_count), 0.0);
    double min_volume = std::numeric_limits<double>::infinity();
    double max_aspect = 0.0;
    for (int cell = 0; cell < cell_count; ++cell) {
        const auto& vertices = cell_vertices[static_cast<std::size_t>(cell)];
        Point center{};
        for (const int vertex : vertices) center = add(center, artifact.points[static_cast<std::size_t>(vertex)]);
        centers[static_cast<std::size_t>(cell)] = scale(center, 0.25);
        double signed_volume = 0.0;
        std::vector<int> unique(vertices.begin(), vertices.end());
        double min_edge = std::numeric_limits<double>::infinity();
        double max_edge = 0.0;
        for (int first = 0; first < 4; ++first) for (int second = first + 1; second < 4; ++second) {
            const double edge = norm(sub(artifact.points[static_cast<std::size_t>(unique[first])], artifact.points[static_cast<std::size_t>(unique[second])]));
            min_edge = std::min(min_edge, edge);
            max_edge = std::max(max_edge, edge);
        }
        max_aspect = std::max(max_aspect, max_edge / std::max(min_edge, 1.0e-14));
        for (const std::size_t face_id : cell_faces[static_cast<std::size_t>(cell)]) {
            const auto& face = artifact.faces[face_id];
            const Point& a = artifact.points[static_cast<std::size_t>(face[0])];
            const Point& b = artifact.points[static_cast<std::size_t>(face[1])];
            const Point& c = artifact.points[static_cast<std::size_t>(face[2])];
            const double contribution = dot(a, cross(b, c)) / 6.0;
            signed_volume += face_id < internal_faces && artifact.neighbour[face_id] == cell ? -contribution : contribution;
        }
        volumes[static_cast<std::size_t>(cell)] = signed_volume;
        if (!(std::isfinite(signed_volume) && signed_volume > 1.0e-14)) return refuse("persisted_tet_nonpositive_volume");
        min_volume = std::min(min_volume, signed_volume);
    }

    for (std::size_t face_id = internal_faces; face_id < artifact.faces.size(); ++face_id) {
        const auto& disk_face = artifact.faces[face_id];
        std::string matched_id;
        for (const auto& [id, source] : source_by_id) {
            if (same_cycle(vertex_ids(source["source_vertex_ids"]), disk_face)) {
                if (!matched_id.empty()) return refuse("source_boundary_face_ambiguous");
                matched_id = id;
            }
        }
        if (matched_id.empty() || !matched_source_ids.insert(matched_id).second) return refuse("source_boundary_coverage_mismatch");
    }
    if (matched_source_ids.size() != source_by_id.size()) return refuse("source_boundary_coverage_incomplete");

    if (!authority.contains("cell_lineage") || !py::isinstance<py::list>(authority["cell_lineage"])) {
        return refuse("cell_lineage_missing");
    }
    const py::list input_lineage = authority["cell_lineage"].cast<py::list>();
    if (input_lineage.size() != static_cast<py::size_t>(cell_count)) return refuse("cell_lineage_count_mismatch");
    py::list entity_uids;
    py::list lineage_rows;
    for (int cell = 0; cell < cell_count; ++cell) {
        if (!py::isinstance<py::dict>(input_lineage[static_cast<py::ssize_t>(cell)])) return refuse("cell_lineage_row_invalid");
        const py::dict input = input_lineage[static_cast<py::ssize_t>(cell)].cast<py::dict>();
        const std::string expected_uid = "cell-" + std::to_string(cell);
        std::string uid;
        std::string source_id;
        if (!string_field(input, "entity_uid", uid) || uid != expected_uid || !string_field(input, "source_face_id", source_id) || !source_by_id.contains(source_id)) {
            return refuse("cell_lineage_identity_mismatch");
        }
        for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) {
            std::string value;
            if (!string_field(input, key, value)) return refuse("cell_lineage_semantics_missing");
            if (value != source_by_id[source_id][key].cast<std::string>()) return refuse("cell_lineage_semantics_mismatch");
        }
        entity_uids.append(uid);
        py::dict row = input;
        lineage_rows.append(row);
    }

    double max_nonorth = 0.0;
    double max_skew = 0.0;
    for (std::size_t face_id = 0; face_id < artifact.faces.size(); ++face_id) {
        const auto& face = artifact.faces[face_id];
        const Point& a = artifact.points[static_cast<std::size_t>(face[0])];
        const Point& b = artifact.points[static_cast<std::size_t>(face[1])];
        const Point& c = artifact.points[static_cast<std::size_t>(face[2])];
        const Point area_vector = cross(sub(b, a), sub(c, a));
        const double area_twice = norm(area_vector);
        if (!(area_twice > 1.0e-14)) return refuse("persisted_face_zero_area");
        const Point normal = scale(area_vector, 1.0 / area_twice);
        const int owner = artifact.owner[face_id];
        const Point line = face_id < internal_faces
            ? sub(centers[static_cast<std::size_t>(artifact.neighbour[face_id])], centers[static_cast<std::size_t>(owner)])
            : sub(scale(add(add(a, b), c), 1.0 / 3.0), centers[static_cast<std::size_t>(owner)]);
        const double line_length = norm(line);
        if (!(line_length > 1.0e-14)) return refuse("persisted_face_centerline_zero");
        const double alignment = std::abs(dot(normal, scale(line, 1.0 / line_length)));
        max_nonorth = std::max(max_nonorth, std::acos(std::clamp(alignment, 0.0, 1.0)) * 180.0 / 3.14159265358979323846);
        const Point face_center = scale(add(add(a, b), c), 1.0 / 3.0);
        const double projection_distance = dot(sub(face_center, centers[static_cast<std::size_t>(owner)]), line) / std::max(dot(line, line), 1.0e-14);
        const Point projection = add(centers[static_cast<std::size_t>(owner)], scale(line, projection_distance));
        max_skew = std::max(max_skew, norm(sub(face_center, projection)) / std::max(std::sqrt(area_twice), 1.0e-14));
    }

    std::ostringstream contract;
    contract << "native-tet-persisted-volume-artifact/v1\n" << artifact.canonical_sha256 << '\n'
             << cell_count << '\n' << min_volume << '\n' << max_nonorth << '\n' << max_skew << '\n' << max_aspect << '\n';
    const std::string artifact_bytes = contract.str();
    const std::vector<std::uint8_t> artifact_input(artifact_bytes.begin(), artifact_bytes.end());
    const std::string writer_hash = brep_evidence::sha256_hex(artifact_input);
    py::dict topology;
    topology["duplicate"] = duplicate_faces;
    topology["non_manifold"] = non_manifold_faces;
    topology["inverted"] = 0;
    py::dict quality;
    quality["accepted"] = true;
    quality["aspect_family"] = "tet_dihedral";
    quality["signed_non_orthogonality_max"] = max_nonorth;
    quality["skewness_max"] = max_skew;
    quality["aspect_ratio_max"] = max_aspect;
    quality["positive_measure_min"] = min_volume;
    py::dict boundary;
    boundary["actual_layers"] = 0;
    boundary["layer_work"] = 0;
    boundary["positive_measure"] = true;
    boundary["rows"] = py::list();
    py::dict result;
    result["accepted"] = true;
    result["status"] = "native-tet-persisted-volume-artifact-sealed";
    result["runtime_route"] = "default_off";
    result["publication_eligible"] = false;
    result["candidate_discarded"] = false;
    result["artifact_schema"] = "native-tet-persisted-volume-artifact/v1";
    result["artifact_bytes"] = artifact_bytes;
    result["artifact_byte_size"] = artifact_bytes.size();
    result["writer_artifact_sha256"] = writer_hash;
    result["artifact_serialization_sha256"] = artifact.canonical_sha256;
    result["quality"] = quality;
    result["topology"] = topology;
    result["boundary_layer"] = boundary;
    result["entity_uids"] = entity_uids;
    result["lineage_rows"] = lineage_rows;
    result["strict_topology_checked"] = true;
    result["quality_checked"] = true;
    result["source_authority_status"] = "SOURCE_VERIFIED_FROM_PERSISTED_POLYMESH";
    result["source_boundary_coverage"] = true;
    result["persisted_reader"] = "native_tet_polymesh_persisted_reader_v1";
    return result;
}

}  // namespace

PYBIND11_MODULE(native_tet_persisted_volume_artifact, module) {
    module.doc() = "C++23 independent persisted Native Tet volume artifact reader.";
    module.def("read_authoritative_volume_artifact", &read_authoritative_volume_artifact,
        py::arg("poly_mesh_root"), py::arg("authority"));
}
