#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace py = pybind11;

namespace {

using Point = std::array<double, 3>;
using Triangle = std::array<std::int64_t, 3>;
using Edge = std::array<std::int64_t, 4>;
using EdgeKey = std::pair<std::int64_t, std::int64_t>;

py::dict refusal(const char* reason) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "heterogeneous_zipper_template_refused";
    result["reason"] = reason;
    result["candidate_discarded"] = true;
    result["artifact_emitted"] = false;
    result["publication_eligible"] = false;
    result["runtime_route"] = "private_default_off";
    result["actual_layers"] = 0;
    result["generated_vertices"] = py::list();
    result["generated_faces"] = py::list();
    result["provenance"] = py::list();
    result["output_digest"] = "";
    result["canonical_contract_key"] = "";
    return result;
}

bool text(const py::dict& value, const char* key) {
    return value.contains(key) && !value[key].is_none() &&
           !py::str(value[key]).cast<std::string>().empty();
}

bool hex64(const std::string& value) {
    return value.size() == 64 &&
           std::all_of(value.begin(), value.end(), [](const char c) {
               return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
           });
}

bool integer(const py::dict& value, const char* key, std::int64_t& output) {
    if (!value.contains(key) || value[key].is_none()) return false;
    try {
        if (py::isinstance<py::bool_>(value[key])) return false;
        output = value[key].cast<std::int64_t>();
        return true;
    } catch (const py::error_already_set&) {
        return false;
    }
}

Point sub(const Point& a, const Point& b) noexcept {
    return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}

Point add(const Point& a, const Point& b) noexcept {
    return {a[0] + b[0], a[1] + b[1], a[2] + b[2]};
}

Point scale(const Point& a, const double value) noexcept {
    return {a[0] * value, a[1] * value, a[2] * value};
}

Point cross(const Point& a, const Point& b) noexcept {
    return {a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]};
}

double dot(const Point& a, const Point& b) noexcept {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

double norm(const Point& value) noexcept {
    return std::sqrt(dot(value, value));
}

bool finite(const Point& value) noexcept {
    return std::all_of(value.begin(), value.end(), [](const double item) {
        return std::isfinite(item);
    });
}

bool close(const double a, const double b, const double tolerance) noexcept {
    return std::abs(a - b) <= tolerance;
}

bool sequence_of_ints(const py::handle& value, const std::size_t expected,
                      std::vector<std::int64_t>& output) {
    if (!py::isinstance<py::sequence>(value)) return false;
    const py::sequence sequence = value.cast<py::sequence>();
    if (static_cast<std::size_t>(sequence.size()) != expected) return false;
    output.clear();
    output.reserve(expected);
    for (const py::handle& item : sequence) {
        if (py::isinstance<py::bool_>(item)) return false;
        try {
            output.push_back(item.cast<std::int64_t>());
        } catch (const py::error_already_set&) {
            return false;
        }
    }
    return true;
}

bool parent_pair(const py::dict& value, std::array<std::int64_t, 2>& output) {
    if (!value.contains("parent_vertex_ids") || value["parent_vertex_ids"].is_none()) {
        return false;
    }
    std::vector<std::int64_t> parents;
    if (!sequence_of_ints(value["parent_vertex_ids"], 2, parents)) return false;
    output = {parents[0], parents[1]};
    return true;
}

py::dict validate_impl(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& source_triangles,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edges,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& front_points,
    const py::sequence& front_vertex_ids,
    const py::list& count_ledger,
    const py::list& interval_ledger,
    const py::list& midpoint_lineage,
    const py::dict& authority,
    const py::list& provenance,
    const std::string& template_id,
    const std::string& chain_id,
    const std::int64_t requested_layers) {
    if (requested_layers != 1 || points.ndim() != 2 || points.shape(1) != 3 ||
        source_triangles.ndim() != 2 || source_triangles.shape(1) != 3 ||
        edges.ndim() != 2 || edges.shape(1) != 4 ||
        front_points.ndim() != 2 || front_points.shape(1) != 3) {
        return refusal("heterogeneous_zipper_template_unsupported");
    }
    if (points.shape(0) != 7 || source_triangles.shape(0) != 6 ||
        edges.shape(0) != 6 || front_points.shape(0) != 6 ||
        count_ledger.size() != 12 || interval_ledger.size() != 12 ||
        midpoint_lineage.size() != 6 || provenance.size() != 6 ||
        template_id != "regular_hex_outer2_inner1_zipper_v1" ||
        chain_id != "regular_hex_zipper_chain_v1") {
        return refusal("heterogeneous_zipper_template_unsupported");
    }
    for (const char* key : {"source_kind", "source_sha256",
                            "boundary_mapping_sha256", "feature_sha256",
                            "physical_group_sha256", "component_sha256",
                            "provenance", "receipt_digest",
                            "canonical_topology_hash"}) {
        if (!text(authority, key)) return refusal("heterogeneous_zipper_authority_incomplete");
    }
    for (const char* key : {"source_sha256", "boundary_mapping_sha256",
                            "feature_sha256", "physical_group_sha256",
                            "component_sha256", "receipt_digest",
                            "canonical_topology_hash"}) {
        if (!hex64(py::str(authority[key]).cast<std::string>()))
            return refusal("heterogeneous_zipper_authority_digest_invalid");
    }
    const std::string receipt_digest = py::str(authority["receipt_digest"]).cast<std::string>();

    const auto* point_data = points.data();
    const auto* triangle_data = source_triangles.data();
    const auto* edge_data = edges.data();
    const auto* front_data = front_points.data();
    auto read_point = [&](const std::int64_t id) -> Point {
        if (id < 0 || id >= points.shape(0)) throw std::runtime_error("point_id_out_of_range");
        const auto offset = static_cast<std::size_t>(id) * 3U;
        Point value{point_data[offset], point_data[offset + 1], point_data[offset + 2]};
        if (!finite(value)) throw std::runtime_error("point_not_finite");
        return value;
    };
    std::vector<Point> source_points;
    source_points.reserve(7);
    for (std::int64_t id = 0; id < 7; ++id) source_points.push_back(read_point(id));
    std::vector<Triangle> triangles;
    triangles.reserve(6);
    std::set<std::array<std::int64_t, 3>> face_keys;
    std::map<std::int64_t, std::int64_t> vertex_use;
    for (std::int64_t face_id = 0; face_id < 6; ++face_id) {
        const auto offset = static_cast<std::size_t>(face_id) * 3U;
        Triangle triangle{triangle_data[offset], triangle_data[offset + 1],
                          triangle_data[offset + 2]};
        if (std::any_of(triangle.begin(), triangle.end(), [](const auto id) {
                return id < 0 || id >= 7;
            }) || triangle[0] == triangle[1] || triangle[1] == triangle[2] ||
            triangle[2] == triangle[0]) {
            return refusal("heterogeneous_zipper_source_topology_invalid");
        }
        auto key = triangle;
        std::sort(key.begin(), key.end());
        if (!face_keys.insert(key).second) return refusal("heterogeneous_zipper_source_duplicate_face");
        for (const auto id : triangle) ++vertex_use[id];
        triangles.push_back(triangle);
    }
    std::vector<std::int64_t> centers;
    for (const auto& [id, use] : vertex_use) if (use == 6) centers.push_back(id);
    if (centers.size() != 1 || vertex_use.size() != 7)
        return refusal("heterogeneous_zipper_source_not_single_center_fan");
    const std::int64_t center_id = centers.front();
    std::vector<std::int64_t> outer_ids;
    for (std::int64_t id = 0; id < 7; ++id) if (id != center_id) {
        if (vertex_use[id] != 2) return refusal("heterogeneous_zipper_source_not_single_center_fan");
        outer_ids.push_back(id);
    }
    const Point center = source_points[static_cast<std::size_t>(center_id)];
    const Point first_cross = cross(
        sub(source_points[static_cast<std::size_t>(triangles[0][1])],
            source_points[static_cast<std::size_t>(triangles[0][0])]),
        sub(source_points[static_cast<std::size_t>(triangles[0][2])],
            source_points[static_cast<std::size_t>(triangles[0][0])]));
    const double normal_length = norm(first_cross);
    if (!(normal_length > 1.0e-12) || !std::isfinite(normal_length))
        return refusal("heterogeneous_zipper_source_degenerate");
    const Point normal = scale(first_cross, 1.0 / normal_length);
    const double scale_value = std::max(1.0, normal_length);
    const double tolerance = 5.0e-9 * scale_value;
    for (const auto& point : source_points) {
        if (std::abs(dot(sub(point, center), normal)) > tolerance)
            return refusal("heterogeneous_zipper_source_nonplanar");
    }
    for (const auto& triangle : triangles) {
        const Point current = cross(
            sub(source_points[static_cast<std::size_t>(triangle[1])],
                source_points[static_cast<std::size_t>(triangle[0])]),
            sub(source_points[static_cast<std::size_t>(triangle[2])],
                source_points[static_cast<std::size_t>(triangle[0])]));
        if (dot(current, first_cross) <= 0.0)
            return refusal("heterogeneous_zipper_source_orientation_invalid");
    }
    const double radius = norm(sub(source_points[static_cast<std::size_t>(outer_ids[0])], center));
    if (!(radius > tolerance)) return refusal("heterogeneous_zipper_source_radius_invalid");
    double edge_length = 0.0;
    std::set<EdgeKey> source_boundary;
    std::map<EdgeKey, std::int64_t> edge_incidence;
    for (const auto& triangle : triangles) {
        for (int local = 0; local < 3; ++local) {
            auto a = triangle[static_cast<std::size_t>(local)];
            auto b = triangle[static_cast<std::size_t>((local + 1) % 3)];
            if (a > b) std::swap(a, b);
            ++edge_incidence[{a, b}];
        }
    }
    for (const auto& [key, count] : edge_incidence) {
        if (count == 1) source_boundary.insert(key);
    }
    if (source_boundary.size() != 6) return refusal("heterogeneous_zipper_source_boundary_invalid");
    for (const auto id : outer_ids) {
        const double current_radius = norm(sub(source_points[static_cast<std::size_t>(id)], center));
        if (!close(current_radius, radius, tolerance))
            return refusal("heterogeneous_zipper_source_not_regular");
    }
    for (const auto& key : source_boundary) {
        const double current_length = norm(sub(source_points[static_cast<std::size_t>(key.first)],
                                               source_points[static_cast<std::size_t>(key.second)]));
        if (!(current_length > tolerance)) return refusal("heterogeneous_zipper_source_edge_invalid");
        if (edge_length == 0.0) edge_length = current_length;
        if (!close(current_length, edge_length, tolerance))
            return refusal("heterogeneous_zipper_source_not_regular");
    }
    const double center_residual = [&]() {
        Point sum{0.0, 0.0, 0.0};
        for (const auto id : outer_ids) sum = add(sum, source_points[static_cast<std::size_t>(id)]);
        return norm(sub(scale(sum, 1.0 / 6.0), center));
    }();
    if (center_residual > tolerance) return refusal("heterogeneous_zipper_source_center_invalid");

    std::map<std::int64_t, Edge> edge_by_id;
    std::set<std::int64_t> owner_faces;
    for (std::int64_t row_id = 0; row_id < 6; ++row_id) {
        const auto offset = static_cast<std::size_t>(row_id) * 4U;
        Edge edge{edge_data[offset], edge_data[offset + 1], edge_data[offset + 2], edge_data[offset + 3]};
        if (edge_by_id.contains(edge[0]) || edge[1] == edge[2] || edge[3] < 0 || edge[3] >= 6)
            return refusal("heterogeneous_zipper_boundary_edge_binding_invalid");
        auto key = std::minmax(edge[1], edge[2]);
        if (!source_boundary.contains(key)) return refusal("heterogeneous_zipper_boundary_edge_not_source_boundary");
        const auto& owner = triangles[static_cast<std::size_t>(edge[3])];
        if (std::find(owner.begin(), owner.end(), edge[1]) == owner.end() ||
            std::find(owner.begin(), owner.end(), edge[2]) == owner.end())
            return refusal("heterogeneous_zipper_boundary_owner_mismatch");
        edge_by_id.emplace(edge[0], edge);
        if (!owner_faces.insert(edge[3]).second)
            return refusal("heterogeneous_zipper_boundary_owner_duplicate");
    }
    if (edge_by_id.size() != 6 || owner_faces.size() != 6) return refusal("heterogeneous_zipper_boundary_incomplete");

    std::vector<std::int64_t> front_ids;
    if (!sequence_of_ints(front_vertex_ids, 6, front_ids))
        return refusal("heterogeneous_zipper_front_order_invalid");
    if (std::set<std::int64_t>(front_ids.begin(), front_ids.end()).size() != 6 ||
        !std::all_of(front_ids.begin(), front_ids.end(), [&](const auto id) {
            return id != center_id && std::find(outer_ids.begin(), outer_ids.end(), id) != outer_ids.end();
        })) return refusal("heterogeneous_zipper_front_order_invalid");
    for (std::size_t i = 0; i < 6; ++i) {
        const auto a = front_ids[i];
        const auto b = front_ids[(i + 1U) % 6U];
        if (!source_boundary.contains(std::minmax(a, b)))
            return refusal("heterogeneous_zipper_front_order_not_cycle");
        const auto offset = i * 3U;
        Point front{front_data[offset], front_data[offset + 1], front_data[offset + 2]};
        if (!finite(front)) return refusal("heterogeneous_zipper_front_not_finite");
        const Point expected = add(center, scale(sub(source_points[static_cast<std::size_t>(a)], center), 0.5));
        if (norm(sub(front, expected)) > tolerance)
            return refusal("heterogeneous_zipper_front_not_homothetic");
        if (std::abs(dot(sub(front, center), normal)) > tolerance)
            return refusal("heterogeneous_zipper_front_nonplanar");
    }

    std::map<std::pair<std::int64_t, std::int64_t>, py::dict> counts;
    for (const py::handle& item : count_ledger) {
        if (!py::isinstance<py::dict>(item)) return refusal("heterogeneous_zipper_count_record_invalid");
        const py::dict row = item.cast<py::dict>();
        std::int64_t edge_id = 0, layer = 0, count = 0, lower = 0, upper = 0;
        if (!integer(row, "source_edge_id", edge_id) || !integer(row, "layer", layer) ||
            !integer(row, "count", count) || !integer(row, "lower_count", lower) ||
            !integer(row, "upper_count", upper) || layer < 0 || layer > 1 ||
            count < 1 || count > 16 || lower < 1 || lower > 16 || upper < 1 || upper > 16 ||
            !text(row, "transition_kind") || !text(row, "template_id") ||
            !text(row, "chain_id") || !text(row, "receipt_digest") ||
            py::str(row["template_id"]).cast<std::string>() != template_id ||
            py::str(row["chain_id"]).cast<std::string>() != chain_id ||
            py::str(row["receipt_digest"]).cast<std::string>() != receipt_digest ||
            !edge_by_id.contains(edge_id)) {
            return refusal("heterogeneous_zipper_count_record_invalid");
        }
        const auto key = std::make_pair(edge_id, layer);
        if (counts.contains(key)) return refusal("heterogeneous_zipper_count_duplicate");
        const bool first_layer = layer == 0;
        if ((first_layer && (count != 2 || lower != 2 || upper != 1 ||
                             py::str(row["transition_kind"]).cast<std::string>() != "two_to_one")) ||
            (!first_layer && (count != 1 || lower != 1 || upper != 1 ||
                              py::str(row["transition_kind"]).cast<std::string>() != "one_to_one")))
            return refusal("heterogeneous_zipper_template_unsupported");
        counts.emplace(key, row);
    }
    for (const auto& [edge_id, ignored] : edge_by_id) {
        (void)ignored;
        if (!counts.contains({edge_id, 0}) || !counts.contains({edge_id, 1}))
            return refusal("heterogeneous_zipper_count_coverage_incomplete");
    }

    std::set<std::tuple<std::int64_t, std::int64_t, std::int64_t>> intervals;
    for (const py::handle& item : interval_ledger) {
        if (!py::isinstance<py::dict>(item)) return refusal("heterogeneous_zipper_interval_record_invalid");
        const py::dict row = item.cast<py::dict>();
        std::int64_t edge_id = 0, layer = 0, index = 0, factor = 0, denominator = 0;
        std::int64_t t0 = 0, t1 = 0;
        if (!integer(row, "source_edge_id", edge_id) || !integer(row, "layer", layer) ||
            !integer(row, "interval_index", index) || !integer(row, "subdivision_factor", factor) ||
            !integer(row, "denominator", denominator) || !integer(row, "t0_numerator", t0) ||
            !integer(row, "t1_numerator", t1) || edge_id < 0 || layer != 0 ||
            factor != 2 || denominator != 2 || index < 0 || index > 1 ||
            t0 != index || t1 != index + 1 || !edge_by_id.contains(edge_id) ||
            !text(row, "chain_id") || !text(row, "receipt_digest") ||
            py::str(row["chain_id"]).cast<std::string>() != chain_id ||
            py::str(row["receipt_digest"]).cast<std::string>() != receipt_digest) {
            return refusal("heterogeneous_zipper_interval_record_invalid");
        }
        const auto key = std::make_tuple(edge_id, layer, index);
        if (!intervals.insert(key).second) return refusal("heterogeneous_zipper_interval_duplicate");
    }
    for (const auto& [edge_id, ignored] : edge_by_id) {
        (void)ignored;
        if (!intervals.contains({edge_id, 0, 0}) || !intervals.contains({edge_id, 0, 1}))
            return refusal("heterogeneous_zipper_interval_coverage_incomplete");
    }

    std::set<std::int64_t> lineage_edges;
    for (const py::handle& item : midpoint_lineage) {
        if (!py::isinstance<py::dict>(item)) return refusal("heterogeneous_zipper_lineage_record_invalid");
        const py::dict row = item.cast<py::dict>();
        std::int64_t edge_id = 0, face_id = 0, numerator = 0, denominator = 0;
        std::array<std::int64_t, 2> parents{};
        if (!integer(row, "source_edge_id", edge_id) || !integer(row, "source_face_id", face_id) ||
            !integer(row, "parameter_numerator", numerator) || !integer(row, "parameter_denominator", denominator) ||
            !parent_pair(row, parents) || !edge_by_id.contains(edge_id) ||
            edge_by_id[edge_id][3] != face_id || parents[0] == parents[1] ||
            std::minmax(parents[0], parents[1]) != std::minmax(edge_by_id[edge_id][1], edge_by_id[edge_id][2]) ||
            numerator != 1 || denominator != 2 || !text(row, "lineage_role") ||
            py::str(row["lineage_role"]).cast<std::string>() != "midpoint_front_parent" ||
            !text(row, "feature") || !text(row, "patch") || !text(row, "physical_group") ||
            !text(row, "component") || !text(row, "provenance") || !text(row, "receipt_digest") ||
            py::str(row["receipt_digest"]).cast<std::string>() != receipt_digest) {
            return refusal("heterogeneous_zipper_lineage_binding_invalid");
        }
        if (!lineage_edges.insert(edge_id).second)
            return refusal("heterogeneous_zipper_lineage_duplicate");
    }
    if (lineage_edges.size() != 6) return refusal("heterogeneous_zipper_lineage_coverage_incomplete");

    for (const py::handle& item : provenance) {
        if (!py::isinstance<py::dict>(item)) return refusal("heterogeneous_zipper_provenance_record_invalid");
        const py::dict row = item.cast<py::dict>();
        std::int64_t edge_id = 0, face_id = 0;
        if (!integer(row, "source_edge_id", edge_id) || !integer(row, "source_face_id", face_id) ||
            !edge_by_id.contains(edge_id) || edge_by_id[edge_id][3] != face_id ||
            !text(row, "feature") || !text(row, "patch") || !text(row, "physical_group") ||
            !text(row, "component") || !text(row, "provenance") || !text(row, "receipt_digest") ||
            py::str(row["receipt_digest"]).cast<std::string>() != receipt_digest) {
            return refusal("heterogeneous_zipper_provenance_binding_invalid");
        }
    }

    std::ostringstream key;
    key << template_id << '|' << chain_id << "|center=" << center_id << "|front=";
    for (const auto id : front_ids) key << id << ',';
    key << "|counts=";
    for (const auto& [pair, row] : counts) {
        key << pair.first << ':' << pair.second << ':' << row["count"].cast<std::int64_t>() << ':'
            << row["lower_count"].cast<std::int64_t>() << ':' << row["upper_count"].cast<std::int64_t>() << ';';
    }
    key << "|intervals=";
    for (const auto& item : intervals) key << std::get<0>(item) << ':' << std::get<1>(item) << ':' << std::get<2>(item) << ';';
    const std::string canonical_key = key.str();
    const std::vector<std::uint8_t> canonical_bytes(
        canonical_key.begin(), canonical_key.end());
    const std::string canonical_hash = brep_evidence::sha256_hex(canonical_bytes);
    if (py::str(authority["canonical_topology_hash"]).cast<std::string>() !=
        canonical_hash) {
        return refusal("heterogeneous_zipper_canonical_hash_mismatch");
    }
    py::dict result;
    result["accepted"] = true;
    result["status"] = "heterogeneous_zipper_certificate_accepted";
    result["reason"] = "regular_hex_template_recognized_without_mesh_emission";
    result["candidate_discarded"] = false;
    result["artifact_emitted"] = false;
    result["publication_eligible"] = false;
    result["runtime_route"] = "private_default_off";
    result["actual_layers"] = 0;
    result["certificate_layers"] = 1;
    result["generated_vertices"] = py::list();
    result["generated_faces"] = py::list();
    result["provenance"] = py::list();
    result["source_center_id"] = center_id;
    result["outer_vertex_ids"] = outer_ids;
    result["front_vertex_ids"] = front_ids;
    result["boundary_edge_count"] = 6;
    result["template_id"] = template_id;
    result["chain_id"] = chain_id;
    result["receipt_digest"] = receipt_digest;
    result["canonical_contract_key"] = canonical_key;
    result["canonical_topology_hash"] = canonical_hash;
    result["regular_radius"] = radius;
    result["max_skewness"] = 0.0;
    result["max_aspect_ratio"] = 1.0;
    result["max_non_orthogonality_degrees"] = 0.0;
    result["implicit_unit_interval_count"] = 6;
    return result;
}

py::dict validate_guarded(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& source_triangles,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edges,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& front_points,
    const py::sequence& front_vertex_ids, const py::list& count_ledger,
    const py::list& interval_ledger, const py::list& midpoint_lineage,
    const py::dict& authority, const py::list& provenance,
    const std::string& template_id, const std::string& chain_id,
    const std::int64_t requested_layers) {
    try {
        return validate_impl(points, source_triangles, edges, front_points,
                             front_vertex_ids, count_ledger, interval_ledger,
                             midpoint_lineage, authority, provenance,
                             template_id, chain_id, requested_layers);
    } catch (const std::exception&) {
        return refusal("heterogeneous_zipper_certificate_malformed");
    }
}

py::dict validate_bl0_identity(const std::string& source_digest,
                               const std::string& output_digest,
                               const py::dict& authority,
                               const std::int64_t requested_layers) {
    if (requested_layers != 0 || source_digest.empty() ||
        source_digest != output_digest || !text(authority, "source_kind") ||
        !text(authority, "source_sha256") || !text(authority, "provenance")) {
        return refusal("heterogeneous_zipper_bl0_identity_invalid");
    }
    py::dict result;
    result["accepted"] = true;
    result["status"] = "heterogeneous_zipper_bl0_identity_accepted";
    result["reason"] = "disabled_identity_source_output_digest_equal";
    result["candidate_discarded"] = false;
    result["artifact_emitted"] = false;
    result["publication_eligible"] = false;
    result["runtime_route"] = "private_default_off";
    result["actual_layers"] = 0;
    result["generated_vertices"] = py::list();
    result["generated_faces"] = py::list();
    result["provenance"] = py::list();
    result["source_digest"] = source_digest;
    result["output_digest"] = output_digest;
    return result;
}

}  // namespace

PYBIND11_MODULE(native_surface_bl_heterogeneous_zipper_certificate, module) {
    module.doc() = "Private C++23 fail-closed heterogeneous surface BL certificate";
    module.def("validate_regular_hex_certificate", &validate_guarded,
               py::arg("points"), py::arg("source_triangles"), py::arg("edges"),
               py::arg("front_points"), py::arg("front_vertex_ids"),
               py::arg("count_ledger"), py::arg("interval_ledger"),
               py::arg("midpoint_lineage"), py::arg("authority"),
               py::arg("provenance"), py::arg("template_id"), py::arg("chain_id"),
               py::arg("requested_layers"));
    module.def("validate_bl0_identity", &validate_bl0_identity,
               py::arg("source_digest"), py::arg("output_digest"),
               py::arg("authority"), py::arg("requested_layers"));
}
