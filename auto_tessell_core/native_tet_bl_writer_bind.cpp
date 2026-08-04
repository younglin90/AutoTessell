// Bounded C++23 Native Tet BL candidate writer.
// This kernel is intentionally not a release route: it emits in-memory mesh
// connectivity and writer-owned candidate lineage for independent admission.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <iomanip>
#include <sstream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;
using Triangle = std::array<std::int64_t, 3>;
using Tet = std::array<std::int64_t, 4>;

namespace {

Point sub(Point a, Point b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point cross(Point a, Point b) { return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]}; }
double dot(Point a, Point b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

double volume6(const std::vector<Point>& points, const Tet& tet) {
    return dot(
        sub(points[static_cast<size_t>(tet[1])], points[static_cast<size_t>(tet[0])]),
        cross(
            sub(points[static_cast<size_t>(tet[2])], points[static_cast<size_t>(tet[0])]),
            sub(points[static_cast<size_t>(tet[3])], points[static_cast<size_t>(tet[0])])))
        ;
}

std::vector<Point> load_points(const py::array_t<double, py::array::c_style | py::array::forcecast>& array) {
    if (array.ndim() != 2 || array.shape(1) != 3) throw std::invalid_argument("points_must_be_Nx3");
    const auto input = array.unchecked<2>();
    std::vector<Point> result;
    result.reserve(static_cast<size_t>(input.shape(0)));
    for (py::ssize_t i = 0; i < input.shape(0); ++i) {
        Point point{};
        for (int axis = 0; axis < 3; ++axis) {
            point[static_cast<size_t>(axis)] = input(i, axis);
            if (!std::isfinite(point[static_cast<size_t>(axis)])) throw std::invalid_argument("point_nonfinite");
        }
        result.push_back(point);
    }
    return result;
}

std::vector<Triangle> load_triangles(const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& array, std::int64_t point_count) {
    if (array.ndim() != 2 || array.shape(1) != 3) throw std::invalid_argument("triangles_must_be_Mx3");
    const auto input = array.unchecked<2>();
    std::vector<Triangle> result;
    result.reserve(static_cast<size_t>(input.shape(0)));
    for (py::ssize_t i = 0; i < input.shape(0); ++i) {
        Triangle triangle{};
        for (int vertex = 0; vertex < 3; ++vertex) {
            triangle[static_cast<size_t>(vertex)] = input(i, vertex);
            if (triangle[static_cast<size_t>(vertex)] < 0 || triangle[static_cast<size_t>(vertex)] >= point_count) {
                throw std::invalid_argument("triangle_vertex_out_of_range");
            }
        }
        if (std::set<std::int64_t>(triangle.begin(), triangle.end()).size() != 3) {
            throw std::invalid_argument("triangle_degenerate");
        }
        result.push_back(triangle);
    }
    return result;
}

std::vector<Point> load_normals(const py::array_t<double, py::array::c_style | py::array::forcecast>& array, std::int64_t point_count) {
    if (array.ndim() != 2 || array.shape(0) != point_count || array.shape(1) != 3) {
        throw std::invalid_argument("normals_must_match_points");
    }
    const auto input = array.unchecked<2>();
    std::vector<Point> result;
    result.reserve(static_cast<size_t>(point_count));
    for (py::ssize_t i = 0; i < input.shape(0); ++i) {
        Point normal{};
        double squared = 0.0;
        for (int axis = 0; axis < 3; ++axis) {
            normal[static_cast<size_t>(axis)] = input(i, axis);
            squared += normal[static_cast<size_t>(axis)] * normal[static_cast<size_t>(axis)];
        }
        if (!(squared > 1.0e-28) || !std::isfinite(squared)) throw std::invalid_argument("normal_degenerate");
        const double inverse = 1.0 / std::sqrt(squared);
        for (double& value : normal) value *= inverse;
        result.push_back(normal);
    }
    return result;
}

Tet positive_tet(const std::vector<Point>& points, Tet tet, double epsilon) {
    const double signed_volume6 = volume6(points, tet);
    if (!std::isfinite(signed_volume6) || std::abs(signed_volume6) <= 6.0 * epsilon) {
        throw std::runtime_error("tet_signed_volume_below_minimum");
    }
    if (signed_volume6 < 0.0) std::swap(tet[2], tet[3]);
    return tet;
}

py::array_t<double> points_array(const std::vector<Point>& points) {
    py::array_t<double> output({static_cast<py::ssize_t>(points.size()), static_cast<py::ssize_t>(3)});
    auto view = output.mutable_unchecked<2>();
    for (py::ssize_t i = 0; i < static_cast<py::ssize_t>(points.size()); ++i) {
        for (int axis = 0; axis < 3; ++axis) view(i, axis) = points[static_cast<size_t>(i)][static_cast<size_t>(axis)];
    }
    return output;
}

py::array_t<std::int64_t> tets_array(const std::vector<Tet>& tets) {
    py::array_t<std::int64_t> output({static_cast<py::ssize_t>(tets.size()), static_cast<py::ssize_t>(4)});
    auto view = output.mutable_unchecked<2>();
    for (py::ssize_t i = 0; i < static_cast<py::ssize_t>(tets.size()); ++i) {
        for (int vertex = 0; vertex < 4; ++vertex) view(i, vertex) = tets[static_cast<size_t>(i)][static_cast<size_t>(vertex)];
    }
    return output;
}

py::dict generate(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array_in,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& triangles_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals_array,
    std::int64_t requested_layers, double first_height, double growth_ratio,
    double minimum_volume = 1.0e-14) {
    const auto base_points = load_points(points_array_in);
    const auto triangles = load_triangles(triangles_array, static_cast<std::int64_t>(base_points.size()));
    const auto normals = load_normals(normals_array, static_cast<std::int64_t>(base_points.size()));
    if (requested_layers < 0 || !std::isfinite(first_height) || !std::isfinite(growth_ratio) ||
        !std::isfinite(minimum_volume) || first_height < 0.0 || growth_ratio <= 0.0 || minimum_volume <= 0.0) {
        throw std::invalid_argument("bl_policy_invalid");
    }
    py::dict result;
    result["runtime_route"] = "default_off";
    result["publication_eligible"] = false;
    result["candidate_discarded"] = false;
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = requested_layers;
    if (requested_layers == 0) {
        result["accepted"] = true;
        result["status"] = "bl0_identity";
        result["points"] = points_array_in;
        py::array_t<std::int64_t> empty_tets(py::array::ShapeContainer{
            static_cast<py::ssize_t>(0), static_cast<py::ssize_t>(4)});
        result["tets"] = empty_tets;
        result["writer_sidecar_emitted"] = false;
        return result;
    }

    std::vector<Point> output_points = base_points;
    const auto base_count = static_cast<std::int64_t>(base_points.size());
    double cumulative = 0.0;
    for (std::int64_t layer = 1; layer <= requested_layers; ++layer) {
        cumulative += first_height * std::pow(growth_ratio, static_cast<double>(layer - 1));
        for (const auto& point : base_points) {
            const auto index = static_cast<size_t>(&point - base_points.data());
            output_points.push_back({
                point[0] + normals[index][0] * cumulative,
                point[1] + normals[index][1] * cumulative,
                point[2] + normals[index][2] * cumulative,
            });
        }
    }

    std::vector<Tet> output_tets;
    py::list prism_records;
    py::list cell_records;
    std::ostringstream canonical;
    canonical << "native-tet-bl-writer-candidate/v1\n" << requested_layers << '\n'
              << std::setprecision(17) << first_height << '\n' << growth_ratio << '\n';
    for (std::int64_t face = 0; face < static_cast<std::int64_t>(triangles.size()); ++face) {
        const auto triangle = triangles[static_cast<size_t>(face)];
        for (std::int64_t layer = 0; layer < requested_layers; ++layer) {
            const auto lower_offset = layer * base_count;
            const auto upper_offset = (layer + 1) * base_count;
            const auto a = triangle[0] + lower_offset;
            const auto b = triangle[1] + lower_offset;
            const auto c = triangle[2] + lower_offset;
            const auto upper_a = triangle[0] + upper_offset;
            const auto upper_b = triangle[1] + upper_offset;
            const auto upper_c = triangle[2] + upper_offset;
            const std::array<std::array<std::int64_t, 4>, 3> pattern = {{
                {a, b, c, upper_a}, {b, c, upper_b, upper_a}, {c, upper_b, upper_c, upper_a}}};
            const auto prism_id = "prism-" + std::to_string(face) + "-" + std::to_string(layer + 1);
            py::dict prism;
            prism["prism_parent_id"] = prism_id;
            prism["source_face_id"] = "face-" + std::to_string(face);
            prism["layer"] = layer + 1;
            prism["vertex_ids"] = py::make_tuple(a, b, c, upper_a, upper_b, upper_c);
            py::list child_ids;
            for (const auto& raw : pattern) {
                const auto tet = positive_tet(output_points, raw, minimum_volume);
                const auto cell_id = "cell-" + std::to_string(output_tets.size());
                child_ids.append(cell_id);
                py::dict cell;
                cell["output_cell_id"] = cell_id;
                cell["prism_parent_id"] = prism_id;
                cell["source_face_id"] = "face-" + std::to_string(face);
                cell["layer"] = layer + 1;
                cell["local_tet_index"] = static_cast<std::int64_t>(child_ids.size() - 1);
                cell["vertex_ids"] = py::make_tuple(tet[0], tet[1], tet[2], tet[3]);
                cell["signed_volume"] = volume6(output_points, tet) / 6.0;
                cell_records.append(cell);
                output_tets.push_back(tet);
                for (const auto vertex : tet) canonical << vertex << ',';
                canonical << ';';
            }
            prism["child_tet_ids"] = child_ids;
            prism_records.append(prism);
        }
    }

    std::map<std::array<std::int64_t, 3>, int> face_counts;
    std::set<std::array<std::int64_t, 4>> unique_tets;
    for (const auto& tet : output_tets) {
        auto sorted_tet = tet;
        std::sort(sorted_tet.begin(), sorted_tet.end());
        if (!unique_tets.insert(sorted_tet).second) throw std::runtime_error("duplicate_tet_candidate");
        for (int omitted = 0; omitted < 4; ++omitted) {
            std::array<std::int64_t, 3> face{};
            int cursor = 0;
            for (int vertex = 0; vertex < 4; ++vertex) if (vertex != omitted) face[static_cast<size_t>(cursor++)] = tet[static_cast<size_t>(vertex)];
            std::sort(face.begin(), face.end());
            if (++face_counts[face] > 2) throw std::runtime_error("non_manifold_face_candidate");
        }
    }

    py::list source_records;
    for (std::int64_t face = 0; face < static_cast<std::int64_t>(triangles.size()); ++face) {
        py::dict source;
        source["source_face_id"] = "face-" + std::to_string(face);
        source["source_vertex_ids"] = py::make_tuple(
            triangles[static_cast<size_t>(face)][0], triangles[static_cast<size_t>(face)][1], triangles[static_cast<size_t>(face)][2]);
        source_records.append(source);
    }
    py::dict ledger;
    ledger["schema"] = "native-tet-bl-writer-candidate/v1";
    ledger["writer_owned"] = true;
    ledger["source_faces"] = source_records;
    ledger["prisms"] = prism_records;
    ledger["cells"] = cell_records;
    const std::string canonical_bytes = canonical.str();
    const std::vector<std::uint8_t> digest_input(canonical_bytes.begin(), canonical_bytes.end());
    ledger["graph_sha256"] = brep_evidence::sha256_hex(digest_input);
    py::dict quality;
    quality["min_signed_volume"] = minimum_volume;
    quality["cell_count"] = output_tets.size();
    quality["collision_checked"] = false;
    quality["publication_eligible"] = false;
    result["accepted"] = true;
    result["status"] = "candidate_writer_output";
    result["points"] = points_array(output_points);
    result["tets"] = tets_array(output_tets);
    result["ledger"] = ledger;
    result["quality"] = quality;
    result["writer_sidecar_emitted"] = false;
    return result;
}

}  // namespace
std::vector<Tet> load_output_tets(
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& array,
    std::int64_t point_count) {
    if (array.ndim() != 2 || array.shape(1) != 4) throw std::invalid_argument("tets_must_be_Kx4");
    const auto input = array.unchecked<2>();
    std::vector<Tet> tets;
    tets.reserve(static_cast<std::size_t>(input.shape(0)));
    for (py::ssize_t row = 0; row < input.shape(0); ++row) {
        Tet tet{};
        for (int vertex = 0; vertex < 4; ++vertex) {
            tet[static_cast<std::size_t>(vertex)] = input(row, vertex);
            if (tet[static_cast<std::size_t>(vertex)] < 0 ||
                tet[static_cast<std::size_t>(vertex)] >= point_count) {
                throw std::invalid_argument("tet_vertex_out_of_range");
            }
        }
        tets.push_back(tet);
    }
    return tets;
}

std::string required_authority_digest(const py::dict& authority, const char* key) {
    if (!authority.contains(key) || !py::isinstance<py::str>(authority[key])) {
        throw std::invalid_argument(std::string("authority_digest_missing:") + key);
    }
    const auto value = authority[key].cast<std::string>();
    if (value.size() != 64) throw std::invalid_argument(std::string("authority_digest_invalid:") + key);
    return value;
}

py::list integer_list(const std::vector<std::int64_t>& values) {
    py::list result;
    for (const auto value : values) result.append(value);
    return result;
}

void copy_semantics(const py::dict& source, py::dict& destination) {
    for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) {
        destination[key] = source.contains(key) ? source[key] : py::str("");
    }
}

py::dict generate_authoritative(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array_in,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& triangles_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals_array,
    std::int64_t requested_layers, double first_height, double growth_ratio,
    double minimum_volume, const py::dict& authority) {
    py::dict result = generate(
        points_array_in, triangles_array, normals_array, requested_layers,
        first_height, growth_ratio, minimum_volume);
    if (requested_layers == 0) return result;

    if (!authority.contains("source_faces") ||
        !py::isinstance<py::list>(authority["source_faces"])) {
        throw std::invalid_argument("authority_source_faces_required");
    }
    if (!authority.contains("source_edges") ||
        !py::isinstance<py::list>(authority["source_edges"])) {
        throw std::invalid_argument("authority_source_edges_required");
    }
    const auto base_points = load_points(points_array_in);
    const auto triangles = load_triangles(triangles_array, static_cast<std::int64_t>(base_points.size()));
    const auto source_faces = authority["source_faces"].cast<py::list>();
    const auto source_edges = authority["source_edges"].cast<py::list>();
    if (source_faces.size() != static_cast<py::ssize_t>(triangles.size())) {
        throw std::invalid_argument("authority_source_face_count_mismatch");
    }

    std::vector<std::string> source_face_ids;
    std::set<std::string> unique_source_faces;
    py::list source_records;
    for (py::ssize_t index = 0; index < source_faces.size(); ++index) {
        const py::dict input = source_faces[index].cast<py::dict>();
        if (!input.contains("source_face_id") || !input.contains("source_vertex_ids")) {
            throw std::invalid_argument("authority_source_face_row_invalid");
        }
        const auto face_id = input["source_face_id"].cast<std::string>();
        const auto vertices = input["source_vertex_ids"].cast<std::vector<std::int64_t>>();
        const auto triangle = triangles[static_cast<std::size_t>(index)];
        if (vertices.size() != 3 ||
            vertices[0] != triangle[0] || vertices[1] != triangle[1] || vertices[2] != triangle[2] ||
            !unique_source_faces.insert(face_id).second) {
            throw std::invalid_argument("authority_source_face_identity_mismatch");
        }
        py::dict record = input;
        record["source_vertex_ids"] = integer_list(vertices);
        copy_semantics(input, record);
        source_records.append(record);
        source_face_ids.push_back(face_id);
    }

    std::set<std::string> unique_source_edges;
    py::list edge_records;
    for (const auto item : source_edges) {
        const py::dict input = item.cast<py::dict>();
        if (!input.contains("source_edge_id") || !input.contains("vertex_ids")) {
            throw std::invalid_argument("authority_source_edge_row_invalid");
        }
        const auto edge_id = input["source_edge_id"].cast<std::string>();
        const auto vertices = input["vertex_ids"].cast<std::vector<std::int64_t>>();
        if (vertices.size() != 2 || !unique_source_edges.insert(edge_id).second) {
            throw std::invalid_argument("authority_source_edge_identity_invalid");
        }
        py::dict record = input;
        record["vertex_ids"] = integer_list(vertices);
        copy_semantics(input, record);
        edge_records.append(record);
    }

    const auto output_points_array =
        result["points"].cast<py::array_t<double, py::array::c_style | py::array::forcecast>>();
    const auto output_tets_array =
        result["tets"].cast<py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>>();
    const auto output_points = load_points(output_points_array);
    const auto output_tets = load_output_tets(output_tets_array, static_cast<std::int64_t>(output_points.size()));
    const auto base_count = static_cast<std::int64_t>(base_points.size());

    py::list boundary_records;
    py::list interface_records;
    py::list prism_records;
    py::list cell_records;
    py::list edge_child_records;
    py::dict boundary_inverse;
    py::dict tet_inverse;
    std::ostringstream canonical;
    canonical << "native-tet-bl-writer-ledger/v2\n" << requested_layers << '\n';

    for (std::size_t face = 0; face < triangles.size(); ++face) {
        const auto triangle = triangles[face];
        const auto& source_id = source_face_ids[face];
        const std::string wall_id = "wall-face-" + source_id;
        const std::string front_id = "front-face-" + source_id;
        py::dict boundary;
        boundary["source_face_id"] = source_id;
        py::list boundary_children;
        py::dict boundary_child;
        boundary_child["output_face_id"] = wall_id;
        boundary_child["disk_face_id"] = static_cast<std::int64_t>(2 * face);
        boundary_child["vertex_ids"] = integer_list({triangle[0], triangle[1], triangle[2]});
        copy_semantics(source_faces[static_cast<py::ssize_t>(face)].cast<py::dict>(), boundary_child);
        boundary_children.append(boundary_child);
        boundary["children"] = boundary_children;
        boundary_records.append(boundary);

        const auto top_offset = requested_layers * base_count;
        py::dict interface;
        interface["source_face_id"] = source_id;
        py::list interface_children;
        py::dict interface_child;
        interface_child["output_face_id"] = front_id;
        interface_child["disk_face_id"] = static_cast<std::int64_t>(2 * face + 1);
        interface_child["vertex_ids"] = integer_list({
            triangle[0] + top_offset, triangle[1] + top_offset, triangle[2] + top_offset});
        copy_semantics(source_faces[static_cast<py::ssize_t>(face)].cast<py::dict>(), interface_child);
        interface_children.append(interface_child);
        interface["children"] = interface_children;
        interface_records.append(interface);
        boundary_inverse[wall_id.c_str()] = source_id;

        for (std::int64_t layer = 0; layer < requested_layers; ++layer) {
            const auto lower_offset = layer * base_count;
            const auto upper_offset = (layer + 1) * base_count;
            const std::string prism_id = "prism-" + source_id + "-" + std::to_string(layer + 1);
            py::dict prism;
            prism["prism_parent_id"] = prism_id;
            prism["source_face_id"] = source_id;
            prism["layer"] = layer + 1;
            prism["vertex_ids"] = integer_list({
                triangle[0] + lower_offset, triangle[1] + lower_offset, triangle[2] + lower_offset,
                triangle[0] + upper_offset, triangle[1] + upper_offset, triangle[2] + upper_offset});
            py::list child_tet_ids;
            for (int local = 0; local < 3; ++local) {
                const auto global = static_cast<std::size_t>((face * static_cast<std::size_t>(requested_layers) +
                    static_cast<std::size_t>(layer)) * 3 + static_cast<std::size_t>(local));
                if (global >= output_tets.size()) throw std::runtime_error("authoritative_tet_order_mismatch");
                const std::string cell_id = "cell-" + std::to_string(global);
                child_tet_ids.append(cell_id);
                py::dict cell;
                cell["output_cell_id"] = cell_id;
                cell["disk_cell_id"] = static_cast<std::int64_t>(global);
                cell["prism_parent_id"] = prism_id;
                cell["source_face_id"] = source_id;
                cell["layer"] = layer + 1;
                cell["local_tet_index"] = local;
                cell["vertex_ids"] = integer_list({
                    output_tets[global][0], output_tets[global][1],
                    output_tets[global][2], output_tets[global][3]});
                cell["signed_volume"] = volume6(output_points, output_tets[global]) / 6.0;
                copy_semantics(source_faces[static_cast<py::ssize_t>(face)].cast<py::dict>(), cell);
                cell_records.append(cell);
                tet_inverse[cell_id.c_str()] = prism_id;
                canonical << cell_id << ':' << output_tets[global][0] << ',' << output_tets[global][1]
                          << ',' << output_tets[global][2] << ',' << output_tets[global][3] << ';';
            }
            prism["child_tet_ids"] = child_tet_ids;
            prism_records.append(prism);
        }
    }

    std::size_t edge_ordinal = 0;
    for (const auto item : source_edges) {
        const py::dict input = item.cast<py::dict>();
        const auto edge_id = input["source_edge_id"].cast<std::string>();
        py::dict edge;
        edge["source_edge_id"] = edge_id;
        py::list children;
        py::dict child;
        const std::string output_edge_id = "edge-" + edge_id + "-layer-" +
            std::to_string(requested_layers);
        child["output_edge_id"] = output_edge_id;
        child["disk_edge_id"] = static_cast<std::int64_t>(edge_ordinal++);
        child["source_edge_id"] = edge_id;
        child["vertex_ids"] = input["vertex_ids"];
        copy_semantics(input, child);
        children.append(child);
        edge["children"] = children;
        edge_child_records.append(edge);
        canonical << output_edge_id << ';';
    }

    py::dict ledger;
    ledger["schema"] = "native-tet-bl-writer-ledger/v2";
    ledger["writer_owned"] = true;
    ledger["actual_layers"] = requested_layers;
    ledger["source_sha256"] = required_authority_digest(authority, "source_sha256");
    ledger["semantic_ledger_sha256"] = required_authority_digest(authority, "semantic_ledger_sha256");
    ledger["bl_config_sha256"] = required_authority_digest(authority, "bl_config_sha256");
    ledger["quality_policy_sha256"] = required_authority_digest(authority, "quality_policy_sha256");
    ledger["artifact_tree_sha256"] = required_authority_digest(authority, "artifact_tree_sha256");
    ledger["source_faces"] = source_records;
    ledger["boundary_children"] = boundary_records;
    ledger["interface_children"] = interface_records;
    ledger["edge_children"] = edge_child_records;
    ledger["prisms"] = prism_records;
    ledger["cells"] = cell_records;
    py::dict inverse;
    inverse["boundary_face_to_source"] = boundary_inverse;
    inverse["tet_to_prism"] = tet_inverse;
    ledger["inverse"] = inverse;
    const std::string canonical_bytes = canonical.str();
    const std::vector<std::uint8_t> digest_input(canonical_bytes.begin(), canonical_bytes.end());
    ledger["graph_sha256"] = brep_evidence::sha256_hex(digest_input);
    ledger["graph_digest_pending_python_canonicalization"] = true;

    result["status"] = "authoritative_candidate_writer_output";
    result["authoritative_writer"] = true;
    result["ledger"] = ledger;
    result["publication_eligible"] = false;
    result["writer_sidecar_emitted"] = false;
    return result;
}
std::set<std::int64_t> vertex_set_from_handle(const py::handle& value) {
    const auto vertices = value.cast<std::vector<std::int64_t>>();
    return std::set<std::int64_t>(vertices.begin(), vertices.end());
}

py::dict generate_authoritative_artifact(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array_in,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& triangles_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals_array,
    std::int64_t requested_layers, double first_height, double growth_ratio,
    double minimum_volume, const py::dict& authority) {
    py::dict result = generate_authoritative(
        points_array_in, triangles_array, normals_array, requested_layers,
        first_height, growth_ratio, minimum_volume, authority);
    if (requested_layers == 0 || !result["accepted"].cast<bool>()) {
        result["status"] = "bl0_identity_artifact_bridge";
        result["artifact_bridge_work_performed"] = false;
        return result;
    }

    py::dict artifact;
    try {
        const py::module_ graph_module = py::module_::import("native_tet_bl_authoritative_graph");
        artifact = graph_module.attr("artifact")(result["points"], result["tets"]).cast<py::dict>();
    } catch (const py::error_already_set&) {
        result["accepted"] = false;
        result["status"] = "authoritative_artifact_bridge_refused";
        result["candidate_discarded"] = true;
        result["rollback_required"] = true;
        result["refusal_reason"] = "authoritative_graph_module_unavailable";
        return result;
    }
    if (!artifact.contains("accepted") || !artifact["accepted"].cast<bool>()) {
        result["accepted"] = false;
        result["status"] = "authoritative_artifact_bridge_refused";
        result["candidate_discarded"] = true;
        result["rollback_required"] = true;
        result["refusal_reason"] = "authoritative_graph_refused";
        result["artifact"] = artifact;
        return result;
    }

    py::dict ledger = result["ledger"].cast<py::dict>();
    if (ledger.contains("graph_digest_pending_python_canonicalization")) {
        ledger.attr("pop")("graph_digest_pending_python_canonicalization");
    }
    ledger["graph_sha256"] = artifact["graph_sha256"];
    ledger["artifact_tree_sha256"] = artifact["artifact_tree_sha256"];
    ledger["serialization_sha256"] = artifact["serialization_sha256"];
    ledger["graph_binding"] = "direct_writer_vertex_cycle";
    const py::list graph_faces = artifact["faces_table"].cast<py::list>();
    const py::dict disk_ids = artifact["disk_face_ids"].cast<py::dict>();

    for (const char* section_name : {"boundary_children", "interface_children"}) {
        const py::list sections = ledger[section_name].cast<py::list>();
        for (const auto section_item : sections) {
            py::dict section = section_item.cast<py::dict>();
            const py::list children = section["children"].cast<py::list>();
            for (const auto child_item : children) {
                py::dict child = child_item.cast<py::dict>();
                const auto target = vertex_set_from_handle(child["vertex_ids"]);
                bool found = false;
                for (const auto face_item : graph_faces) {
                    const py::dict face = face_item.cast<py::dict>();
                    if (vertex_set_from_handle(face["vertex_cycle"]) != target) continue;
                    const auto writer_face_id = face["writer_face_id"].cast<std::string>();
                    if (!disk_ids.contains(py::str(writer_face_id))) break;
                    child["disk_face_id"] = disk_ids[py::str(writer_face_id)];
                    child["graph_face_id"] = writer_face_id;
                    found = true;
                    break;
                }
                if (!found) {
                    result["accepted"] = false;
                    result["status"] = "authoritative_artifact_bridge_refused";
                    result["candidate_discarded"] = true;
                    result["rollback_required"] = true;
                    result["refusal_reason"] = "writer_face_cycle_not_in_graph";
                    result["artifact"] = artifact;
                    return result;
                }
            }
        }
    }

    result["ledger"] = ledger;
    result["artifact"] = artifact;
    const py::dict artifact_quality = artifact["quality"].cast<py::dict>();
    const py::list artifact_cells = ledger["cells"].cast<py::list>();
    double positive_measure_min = std::numeric_limits<double>::infinity();
    for (const auto item : artifact_cells) {
        const double volume = item.cast<py::dict>()["signed_volume"].cast<double>();
        if (std::isfinite(volume) && volume > 0.0) positive_measure_min = std::min(positive_measure_min, volume);
    }
    if (!std::isfinite(positive_measure_min)) {
        result["accepted"] = false;
        result["status"] = "authoritative_artifact_bridge_refused";
        result["candidate_discarded"] = true;
        result["rollback_required"] = true;
        result["refusal_reason"] = "writer_positive_measure_missing";
        result["artifact"] = artifact;
        return result;
    }
    py::dict writer_quality;
    writer_quality["accepted"] = true;
    writer_quality["aspect_family"] = "tet_dihedral";
    writer_quality["signed_non_orthogonality_max"] = artifact_quality["max_non_orthogonality"];
    writer_quality["skewness_max"] = artifact_quality["max_skewness"];
    writer_quality["aspect_ratio_max"] = artifact_quality["max_aspect_ratio"];
    writer_quality["positive_measure_min"] = positive_measure_min;
    writer_quality["p95_non_orthogonality"] = artifact_quality["p95_non_orthogonality"];
    writer_quality["p95_skewness"] = artifact_quality["p95_skewness"];
    py::dict topology;
    topology["duplicate"] = 0;
    topology["non_manifold"] = 0;
    topology["inverted"] = 0;
    py::list entity_uids;
    py::list lineage_rows;
    for (const auto item : artifact_cells) {
        const py::dict cell = item.cast<py::dict>();
        const auto uid = cell["output_cell_id"].cast<std::string>();
        entity_uids.append(uid);
        py::dict row;
        row["entity_uid"] = uid;
        copy_semantics(cell, row);
        lineage_rows.append(row);
    }
    py::dict boundary_layer;
    boundary_layer["actual_layers"] = requested_layers;
    boundary_layer["layer_work"] = static_cast<std::int64_t>(artifact_cells.size());
    boundary_layer["positive_measure"] = true;
    py::list boundary_roles;
    for (const char* role : {"wall", "front", "side"}) {
        py::dict row;
        row["role"] = role;
        boundary_roles.append(row);
    }
    boundary_layer["rows"] = boundary_roles;
    std::ostringstream artifact_contract;
    artifact_contract << "native-tet-bl-artifact/v2\n"
                      << artifact["artifact_tree_sha256"].cast<std::string>() << '\n'
                      << artifact["serialization_sha256"].cast<std::string>() << '\n';
    const std::string artifact_bytes = artifact_contract.str();
    const std::vector<std::uint8_t> artifact_input(artifact_bytes.begin(), artifact_bytes.end());
    const auto writer_artifact_sha256 = brep_evidence::sha256_hex(artifact_input);
    result["quality"] = writer_quality;
    result["topology"] = topology;
    result["entity_uids"] = entity_uids;
    result["lineage_rows"] = lineage_rows;
    result["boundary_layer"] = boundary_layer;
    result["strict_topology_checked"] = true;
    result["quality_checked"] = true;
    result["artifact_schema"] = "native-tet-bl-artifact/v2";
    result["artifact_bytes"] = artifact_bytes;
    result["artifact_byte_size"] = artifact_bytes.size();
    result["writer_artifact_sha256"] = writer_artifact_sha256;
    result["artifact_serialization_sha256"] = artifact["serialization_sha256"];
    result["status"] = "authoritative_candidate_artifact_bridge";
    result["authoritative_artifact_bridge"] = true;
    result["collision_surface_source"] = "writer_owned_graph_faces";
    result["publication_eligible"] = false;
    return result;
}

PYBIND11_MODULE(native_tet_bl_writer, module) {
    module.doc() = "C++23 bounded Native Tet BL candidate writer; release route disabled.";
    module.def("generate", &generate,
        py::arg("points"), py::arg("triangles"), py::arg("normals"),
        py::arg("requested_layers"), py::arg("first_height"), py::arg("growth_ratio"),
        py::arg("minimum_volume") = 1.0e-14);
    module.def("generate_authoritative", &generate_authoritative, py::arg("points"), py::arg("triangles"), py::arg("normals"), py::arg("requested_layers"), py::arg("first_height"), py::arg("growth_ratio"), py::arg("minimum_volume"), py::arg("authority"));
    module.def("generate_authoritative_artifact", &generate_authoritative_artifact, py::arg("points"), py::arg("triangles"), py::arg("normals"), py::arg("requested_layers"), py::arg("first_height"), py::arg("growth_ratio"), py::arg("minimum_volume"), py::arg("authority"));
}
py::list integer_list(std::initializer_list<std::int64_t> values) {
    return integer_list(std::vector<std::int64_t>(values));
}
