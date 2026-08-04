#include "native_quality_witness_v3.hpp"

#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include "../surface_bl_front_shared/brep_evidence_sha256.hpp"

namespace py = pybind11;

namespace native_quality_witness_v3 {
namespace {

using Point = std::array<double, 3>;
constexpr double kEpsilon = 1.0e-30;
constexpr double kPi = 3.141592653589793238462643383279502884;

Point sub(const Point& a, const Point& b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point add(const Point& a, const Point& b) { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
Point mul(const Point& a, double s) { return {a[0] * s, a[1] * s, a[2] * s}; }
Point cross(const Point& a, const Point& b) {
    return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]};
}
double dot(const Point& a, const Point& b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double norm(const Point& a) { return std::sqrt(dot(a, a)); }

bool hex64(const py::handle& value) {
    if (!py::isinstance<py::str>(value)) return false;
    const auto text = value.cast<std::string>();
    if (text.size() != 64U) return false;
    return std::all_of(text.begin(), text.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
    });
}

std::string canonical(const py::handle& value) {
    if (value.is_none()) return "null;";
    if (py::isinstance<py::bool_>(value)) return value.cast<bool>() ? "bool:1;" : "bool:0;";
    if (py::isinstance<py::int_>(value)) return "int:" + std::to_string(value.cast<long long>()) + ";";
    if (py::isinstance<py::float_>(value)) {
        std::ostringstream stream;
        stream << "float:" << std::setprecision(std::numeric_limits<double>::max_digits10)
               << value.cast<double>() << ";";
        return stream.str();
    }
    if (py::isinstance<py::str>(value)) {
        const auto text = value.cast<std::string>();
        return "str:" + std::to_string(text.size()) + ":" + text + ";";
    }
    if (py::isinstance<py::dict>(value)) {
        std::vector<std::pair<std::string, std::string>> entries;
        for (const auto item : value.cast<py::dict>()) {
            entries.emplace_back(py::cast<std::string>(item.first), canonical(item.second));
        }
        std::sort(entries.begin(), entries.end());
        std::string result = "dict{";
        for (const auto& [key, encoded] : entries) {
            result += "key:" + std::to_string(key.size()) + ":" + key + ":" + encoded;
        }
        return result + "};";
    }
    if (py::isinstance<py::list>(value) || py::isinstance<py::tuple>(value)) {
        const auto sequence = value.cast<py::sequence>();
        std::string result = "seq[";
        for (py::ssize_t index = 0; index < static_cast<py::ssize_t>(sequence.size()); ++index)
            result += canonical(sequence[index]);
        return result + "];";
    }
    throw std::invalid_argument("quality_policy_value_type_unsupported");
}

std::string digest(const std::string& text) {
    const std::vector<std::uint8_t> bytes(text.begin(), text.end());
    return brep_evidence::sha256_hex(bytes);
}

py::dict refuse(const char* reason) {
    py::dict out;
    out["accepted"] = false;
    out["status"] = "native_quality_witness_v3_refused";
    out["reason"] = reason;
    out["candidate_discarded"] = true;
    out["rollback_required"] = true;
    return out;
}

bool finite_number(const py::dict& value, const char* key, double minimum) {
    if (!value.contains(key)) return false;
    try {
        const double number = value[key].cast<double>();
        return std::isfinite(number) && number >= minimum;
    } catch (const py::cast_error&) {
        return false;
    }
}

bool nonnegative_integer(const py::dict& value, const char* key) {
    if (!value.contains(key)) return false;
    try { return value[key].cast<long long>() >= 0; }
    catch (const py::cast_error&) { return false; }
}

py::dict report(const std::vector<double>& values, const std::vector<std::string>& uids,
                const char* definition) {
    py::dict out;
    out["definition"] = definition;
    out["count"] = static_cast<std::int64_t>(values.size());
    if (values.empty()) {
        out["status"] = "not_applicable";
        out["min"] = py::none(); out["p95"] = py::none(); out["p99"] = py::none(); out["max"] = py::none();
        out["worst_uid"] = py::none();
        return out;
    }
    std::vector<std::size_t> order(values.size());
    for (std::size_t i = 0; i < order.size(); ++i) order[i] = i;
    std::sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) {
        if (values[a] != values[b]) return values[a] < values[b];
        return uids[a] < uids[b];
    });
    const auto quantile = [&](double fraction) {
        const auto index = static_cast<std::size_t>(std::ceil(fraction * static_cast<double>(order.size()))) - 1U;
        return values[order[std::min(index, order.size() - 1U)]];
    };
    const auto worst = order.back();
    out["status"] = "measured";
    out["min"] = *std::min_element(values.begin(), values.end());
    out["p95"] = quantile(0.95);
    out["p99"] = quantile(0.99);
    out["max"] = values[worst];
    out["worst_uid"] = uids[worst];
    return out;
}

std::vector<std::int64_t> face_key(const std::vector<std::int64_t>& face) {
    auto key = face;
    std::sort(key.begin(), key.end());
    return key;
}

bool required_lineage(const py::handle& value) {
    if (!py::isinstance<py::dict>(value)) return false;
    const auto row = value.cast<py::dict>();
    for (const char* key : {"writer_entity_id", "source_face_id", "source_edge_id", "feature",
                            "patch", "physical_group", "component", "provenance", "role"})
        if (!row.contains(key) || !py::isinstance<py::str>(row[key])) return false;
    return true;
}

std::string string_value(const py::dict& value, const char* key) {
    if (!value.contains(key) || !py::isinstance<py::str>(value[key])) return {};
    return value[key].cast<std::string>();
}

bool close16(double a, double b) {
    const double scale = std::max({1.0, std::abs(a), std::abs(b)});
    return std::abs(a - b) <= 16.0 * std::numeric_limits<double>::epsilon() * scale;
}

}  // namespace

py::dict seal_policy_v3(const py::dict& policy) {
    const std::set<std::string> allowed = {
        "engine", "source_mode", "semantic_mode", "topology_mode", "target_cells", "target_faces",
        "sizing_mode", "metric_mode", "boundary_layer_count", "boundary_layer_first_height",
        "boundary_layer_total_height", "boundary_layer_growth", "wall_edge_mode", "feature_mode",
        "max_non_orthogonality", "max_skewness", "max_aspect_ratio", "min_volume", "replay_count",
        "count_tolerance"};
    for (const auto item : policy) {
        const auto key = py::cast<std::string>(item.first);
        if (!allowed.contains(key)) return refuse("quality_policy_unknown_key");
    }
    for (const char* key : {"engine", "source_mode", "semantic_mode", "topology_mode", "sizing_mode",
                            "metric_mode", "wall_edge_mode", "feature_mode"})
        if (!policy.contains(key) || !py::isinstance<py::str>(policy[key])) return refuse("quality_policy_incomplete");
    for (const char* key : {"target_cells", "target_faces", "boundary_layer_count", "replay_count"})
        if (!nonnegative_integer(policy, key)) return refuse("quality_policy_incomplete");
    for (const char* key : {"boundary_layer_first_height", "boundary_layer_total_height", "boundary_layer_growth",
                            "max_non_orthogonality", "max_skewness", "max_aspect_ratio", "min_volume", "count_tolerance"})
        if (!finite_number(policy, key, 0.0)) return refuse("quality_policy_incomplete");
    const auto layers = policy["boundary_layer_count"].cast<long long>();
    if (layers > 0 && (policy["boundary_layer_first_height"].cast<double>() <= 0.0 ||
                       policy["boundary_layer_total_height"].cast<double>() <= 0.0 ||
                       policy["boundary_layer_growth"].cast<double>() < 1.0))
        return refuse("quality_policy_incomplete");
    try {
        const std::string bytes = canonical(policy);
        py::dict out;
        out["accepted"] = true;
        out["status"] = "native_quality_policy_v3_sealed";
        out["schema"] = "autotessell/native-quality-policy/v3";
        out["policy"] = policy;
        out["policy_bytes"] = bytes;
        out["policy_sha256"] = digest(bytes);
        return out;
    } catch (const std::exception&) {
        return refuse("quality_policy_value_type_unsupported");
    }
}

py::dict evaluate_v3(const py::dict& snapshot, const py::dict& authority,
                     const py::dict& sealed_policy, const std::string& stage) {
    if (stage != "candidate" && stage != "reread") return refuse("quality_stage_invalid");
    if (!sealed_policy.contains("accepted") || !sealed_policy["accepted"].cast<bool>() ||
        !sealed_policy.contains("policy") || !py::isinstance<py::dict>(sealed_policy["policy"]) ||
        !hex64(sealed_policy["policy_sha256"])) return refuse("quality_policy_digest_mismatch");
    const auto policy = sealed_policy["policy"].cast<py::dict>();
    const auto resealed = seal_policy_v3(policy);
    if (!resealed["accepted"].cast<bool>() || resealed["policy_sha256"].cast<std::string>() != sealed_policy["policy_sha256"].cast<std::string>())
        return refuse("quality_policy_digest_mismatch");
    for (const char* key : {"source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"})
        if (!authority.contains(key) || !hex64(authority[key])) return refuse("quality_authority_digest_missing");
    if (!snapshot.contains("points") || !snapshot.contains("faces") || !snapshot.contains("owner") ||
        !snapshot.contains("neighbour") || !snapshot.contains("face_uids") || !snapshot.contains("cell_uids") ||
        !snapshot.contains("lineage")) return refuse("quality_snapshot_incomplete");

    py::array_t<double, py::array::c_style | py::array::forcecast> point_array;
    py::array_t<std::int64_t, py::array::c_style | py::array::forcecast> owner_array;
    py::array_t<std::int64_t, py::array::c_style | py::array::forcecast> neighbour_array;
    try {
        point_array = snapshot["points"].cast<decltype(point_array)>();
        owner_array = snapshot["owner"].cast<decltype(owner_array)>();
        neighbour_array = snapshot["neighbour"].cast<decltype(neighbour_array)>();
    } catch (const py::cast_error&) { return refuse("quality_snapshot_array_invalid"); }
    if (point_array.ndim() != 2 || point_array.shape(1) != 3 || owner_array.ndim() != 1 || neighbour_array.ndim() != 1)
        return refuse("quality_snapshot_array_invalid");
    const auto faces = snapshot["faces"].cast<py::list>();
    const std::size_t n_faces = static_cast<std::size_t>(faces.size());
    if (owner_array.size() != static_cast<py::ssize_t>(n_faces) || neighbour_array.size() > owner_array.size())
        return refuse("quality_owner_neighbour_invalid");
    const auto face_uids = snapshot["face_uids"].cast<std::vector<std::string>>();
    const auto cell_uids = snapshot["cell_uids"].cast<std::vector<std::string>>();
    const auto lineage = snapshot["lineage"].cast<py::list>();
    if (face_uids.size() != n_faces || static_cast<std::size_t>(lineage.size()) != n_faces) return refuse("quality_writer_uid_missing");
    if (std::set<std::string>(face_uids.begin(), face_uids.end()).size() != face_uids.size()) return refuse("quality_writer_uid_missing");
    for (const auto& uid : face_uids) if (uid.empty()) return refuse("quality_writer_uid_missing");
    for (const auto& row : lineage) if (!required_lineage(row)) return refuse("quality_lineage_missing");

    std::vector<Point> points;
    points.reserve(static_cast<std::size_t>(point_array.shape(0)));
    const auto* point_data = point_array.data();
    for (py::ssize_t index = 0; index < point_array.shape(0); ++index) {
        Point point{point_data[3U * static_cast<std::size_t>(index)], point_data[3U * static_cast<std::size_t>(index) + 1U], point_data[3U * static_cast<std::size_t>(index) + 2U]};
        if (!std::all_of(point.begin(), point.end(), [](double value) { return std::isfinite(value); })) return refuse("quality_nonfinite_geometry");
        points.push_back(point);
    }
    std::vector<std::vector<std::int64_t>> face_topology;
    face_topology.reserve(n_faces);
    std::set<std::vector<std::int64_t>> unique_faces;
    for (const auto& item : faces) {
        if (!py::isinstance<py::sequence>(item)) return refuse("quality_face_topology_invalid");
        const auto face = item.cast<std::vector<std::int64_t>>();
        if (face.size() < 3U || !unique_faces.insert(face_key(face)).second) return refuse("quality_duplicate_face");
        for (const auto id : face) if (id < 0 || id >= static_cast<std::int64_t>(points.size())) return refuse("quality_face_vertex_invalid");
        face_topology.push_back(face);
    }
    std::int64_t max_cell = -1;
    const auto* owner_data = owner_array.data();
    const auto* neighbour_data = neighbour_array.data();
    for (py::ssize_t index = 0; index < owner_array.size(); ++index) max_cell = std::max(max_cell, owner_data[index]);
    for (py::ssize_t index = 0; index < neighbour_array.size(); ++index) max_cell = std::max(max_cell, neighbour_data[index]);
    if (max_cell < 0 || cell_uids.size() != static_cast<std::size_t>(max_cell + 1)) return refuse("quality_cell_uid_missing");
    if (std::set<std::string>(cell_uids.begin(), cell_uids.end()).size() != cell_uids.size()) return refuse("quality_cell_uid_missing");
    std::vector<std::set<std::int64_t>> cell_vertices(static_cast<std::size_t>(max_cell + 1));
    for (std::size_t fi = 0; fi < n_faces; ++fi) {
        if (owner_data[fi] < 0 || owner_data[fi] > max_cell) return refuse("quality_owner_neighbour_invalid");
        for (const auto id : face_topology[fi]) cell_vertices[static_cast<std::size_t>(owner_data[fi])].insert(id);
        if (fi < static_cast<std::size_t>(neighbour_array.size())) {
            if (neighbour_data[fi] < 0 || neighbour_data[fi] > max_cell || neighbour_data[fi] == owner_data[fi]) return refuse("quality_owner_neighbour_invalid");
            for (const auto id : face_topology[fi]) cell_vertices[static_cast<std::size_t>(neighbour_data[fi])].insert(id);
        }
    }
    std::vector<Point> cell_centres(cell_vertices.size());
    for (std::size_t ci = 0; ci < cell_vertices.size(); ++ci) {
        if (cell_vertices[ci].empty()) return refuse("quality_cell_uid_missing");
        for (const auto id : cell_vertices[ci]) cell_centres[ci] = add(cell_centres[ci], points[static_cast<std::size_t>(id)]);
        cell_centres[ci] = mul(cell_centres[ci], 1.0 / static_cast<double>(cell_vertices[ci].size()));
    }

    std::vector<double> non_orth, skew, aspect, volumes;
    std::vector<std::string> non_orth_uids, skew_uids, aspect_uids;
    py::list face_records;
    for (std::size_t fi = 0; fi < n_faces; ++fi) {
        const auto& face = face_topology[fi];
        Point centre{};
        for (const auto id : face) centre = add(centre, points[static_cast<std::size_t>(id)]);
        centre = mul(centre, 1.0 / static_cast<double>(face.size()));
        Point area{};
        const auto anchor = points[static_cast<std::size_t>(face[0])];
        for (std::size_t j = 1; j + 1U < face.size(); ++j) area = add(area, cross(sub(points[static_cast<std::size_t>(face[j])], anchor), sub(points[static_cast<std::size_t>(face[j + 1U])], anchor)));
        const double area_length = norm(area);
        if (!(area_length > kEpsilon)) return refuse("quality_zero_area_or_distance");
        py::dict row;
        row["entity_uid"] = face_uids[fi];
        row["lineage"] = lineage[static_cast<py::ssize_t>(fi)];
        row["owner_cell_uid"] = cell_uids[static_cast<std::size_t>(owner_data[fi])];
        const Point owner_to_face = sub(centre, cell_centres[static_cast<std::size_t>(owner_data[fi])]);
        if (fi < static_cast<std::size_t>(neighbour_array.size())) {
            const Point d = sub(cell_centres[static_cast<std::size_t>(neighbour_data[fi])], cell_centres[static_cast<std::size_t>(owner_data[fi])]);
            const double distance = norm(d);
            if (!(distance > kEpsilon)) return refuse("quality_zero_area_or_distance");
            const double cosine = std::clamp(dot(d, area) / (distance * area_length), -1.0, 1.0);
            const double angle = std::acos(cosine) * 180.0 / kPi;
            const double a = std::abs(dot(owner_to_face, area)) / area_length;
            const double b = std::abs(dot(sub(cell_centres[static_cast<std::size_t>(neighbour_data[fi])], centre), area)) / area_length;
            if (!(a + b > kEpsilon)) return refuse("quality_zero_area_or_distance");
            const Point intersection = add(cell_centres[static_cast<std::size_t>(owner_data[fi])], mul(d, a / (a + b)));
            const double sigma = norm(sub(centre, intersection)) / distance;
            non_orth.push_back(angle); non_orth_uids.push_back(face_uids[fi]); skew.push_back(sigma); skew_uids.push_back(face_uids[fi]);
            row["face_class"] = "internal"; row["neighbour_cell_uid"] = cell_uids[static_cast<std::size_t>(neighbour_data[fi])];
            row["non_orthogonality"] = angle; row["skewness"] = sigma;
        } else {
            const Point normal = mul(area, 1.0 / area_length);
            const double height = dot(owner_to_face, normal);
            if (!(std::abs(height) > kEpsilon)) return refuse("quality_zero_area_or_distance");
            const double sigma = norm(sub(owner_to_face, mul(normal, height))) / std::abs(height);
            skew.push_back(sigma); skew_uids.push_back(face_uids[fi]);
            row["face_class"] = "boundary"; row["neighbour_cell_uid"] = py::none(); row["non_orthogonality"] = py::none(); row["skewness"] = sigma;
        }
        face_records.append(row);
    }
    py::list cell_records;
    for (std::size_t ci = 0; ci < cell_vertices.size(); ++ci) {
        double minimum = std::numeric_limits<double>::infinity();
        double maximum = 0.0;
        Point low{std::numeric_limits<double>::infinity(), std::numeric_limits<double>::infinity(), std::numeric_limits<double>::infinity()};
        Point high{-std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()};
        std::vector<std::int64_t> ids(cell_vertices[ci].begin(), cell_vertices[ci].end());
        for (const auto id : ids) for (int axis = 0; axis < 3; ++axis) { low[axis] = std::min(low[axis], points[static_cast<std::size_t>(id)][axis]); high[axis] = std::max(high[axis], points[static_cast<std::size_t>(id)][axis]); }
        for (std::size_t i = 0; i < ids.size(); ++i) for (std::size_t j = i + 1U; j < ids.size(); ++j) { const double length = norm(sub(points[static_cast<std::size_t>(ids[i])], points[static_cast<std::size_t>(ids[j])])); minimum = std::min(minimum, length); maximum = std::max(maximum, length); }
        const double extent = std::max({high[0] - low[0], high[1] - low[1], high[2] - low[2]});
        if (!(minimum > kEpsilon) || !(extent > kEpsilon)) return refuse("quality_zero_area_or_distance");
        const double value = extent / minimum;
        aspect.push_back(value); aspect_uids.push_back(cell_uids[ci]);
        py::dict row; row["entity_uid"] = cell_uids[ci]; row["aspect_ratio"] = value; row["partition"] = "core"; row["positive_geometry"] = true; cell_records.append(row);
    }
    if (snapshot.contains("cell_volumes")) {
        const auto values = snapshot["cell_volumes"].cast<py::sequence>();
        if (static_cast<std::size_t>(values.size()) != cell_vertices.size()) return refuse("quality_volume_population_invalid");
        for (py::ssize_t index = 0; index < static_cast<py::ssize_t>(values.size()); ++index) { const double volume = values[index].cast<double>(); if (!std::isfinite(volume) || volume <= 0.0) return refuse("quality_nonpositive_volume"); volumes.push_back(volume); }
    }
    if (volumes.empty()) return refuse("quality_volume_population_invalid");

    py::dict boundary;
    if (!snapshot.contains("boundary_layer") || !py::isinstance<py::dict>(snapshot["boundary_layer"])) return refuse("quality_positive_bl_contract_missing");
    boundary = snapshot["boundary_layer"].cast<py::dict>();
    const auto requested_layers = policy["boundary_layer_count"].cast<long long>();
    if (!boundary.contains("actual_layers") || boundary["actual_layers"].cast<long long>() != requested_layers) return refuse("quality_positive_bl_contract_missing");
    if (requested_layers > 0) {
        for (const char* key : {"positive_thickness", "lineage_complete", "wall_edge_lineage_complete"}) if (!boundary.contains(key) || !boundary[key].cast<bool>()) return refuse("quality_wall_edge_lineage_missing");
        if (!boundary.contains("minimum_height") || boundary["minimum_height"].cast<double>() <= 0.0) return refuse("quality_positive_bl_contract_missing");
    }

    py::dict quality;
    quality["internal_non_orthogonality"] = report(non_orth, non_orth_uids, "signed owner-neighbour area-vector angle in degrees");
    quality["skewness"] = report(skew, skew_uids, "face-centre distance from owner-neighbour intersection");
    quality["aspect_ratio"] = report(aspect, aspect_uids, "family-tagged bbox extent divided by minimum vertex separation");
    quality["cell_volume"] = report(volumes, cell_uids, "positive writer-supplied cell volume");
    const auto max_value = [](const py::dict& item) { return item["max"].is_none() ? 0.0 : item["max"].cast<double>(); };
    if (max_value(quality["internal_non_orthogonality"].cast<py::dict>()) > policy["max_non_orthogonality"].cast<double>() ||
        max_value(quality["skewness"].cast<py::dict>()) > policy["max_skewness"].cast<double>() ||
        max_value(quality["aspect_ratio"].cast<py::dict>()) > policy["max_aspect_ratio"].cast<double>() ||
        quality["cell_volume"].cast<py::dict>()["min"].cast<double>() < policy["min_volume"].cast<double>())
        return refuse("quality_threshold_exceeded");

    py::dict out;
    out["accepted"] = true; out["status"] = "native_quality_witness_v3_measured"; out["schema"] = "autotessell/native-quality-witness/v3";
    out["stage"] = stage; out["policy_sha256"] = sealed_policy["policy_sha256"];
    for (const char* key : {"source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"}) out[key] = authority[key];
    py::dict topology;
    topology["duplicate_faces"] = 0;
    topology["non_manifold_faces"] = 0;
    topology["inverted_faces"] = 0;
    out["topology"] = topology;
    out["orientation_checked"] = true; out["full_population"] = true; out["quality"] = quality; out["faces"] = face_records; out["cells"] = cell_records; out["face_uids"] = face_uids; out["cell_uids"] = cell_uids; out["boundary_layer"] = boundary; out["authority"] = authority;
    return out;
}

py::dict compare_candidate_reread_v3(const py::dict& candidate, const py::dict& reread) {
    if (!candidate.contains("accepted") || !reread.contains("accepted") || !candidate["accepted"].cast<bool>() || !reread["accepted"].cast<bool>()) return refuse("quality_candidate_disk_not_accepted");
    for (const char* key : {"policy_sha256", "source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"})
        if (string_value(candidate, key) != string_value(reread, key)) return refuse("quality_candidate_disk_digest_mismatch");
    if (candidate["face_uids"].cast<std::vector<std::string>>() != reread["face_uids"].cast<std::vector<std::string>>() || candidate["cell_uids"].cast<std::vector<std::string>>() != reread["cell_uids"].cast<std::vector<std::string>>()) return refuse("quality_candidate_disk_entity_set_mismatch");
    const auto left_quality = candidate["quality"].cast<py::dict>();
    const auto right_quality = reread["quality"].cast<py::dict>();
    for (const char* metric : {"internal_non_orthogonality", "skewness", "aspect_ratio", "cell_volume"}) {
        const auto left = left_quality[metric].cast<py::dict>();
        const auto right = right_quality[metric].cast<py::dict>();
        for (const char* value : {"min", "p95", "p99", "max"}) {
            if (left[value].is_none() || right[value].is_none()) { if (left[value].is_none() != right[value].is_none()) return refuse("quality_candidate_disk_metric_mismatch"); }
            else if (!close16(left[value].cast<double>(), right[value].cast<double>())) return refuse("quality_candidate_disk_metric_mismatch");
        }
    }
    py::dict out; out["accepted"] = true; out["status"] = "native_quality_witness_v3_candidate_disk_equal"; out["candidate_disk_parity"] = true; out["floating_recompute_ulp_limit"] = 16; out["entity_count"] = candidate["face_uids"].cast<py::list>().size() + candidate["cell_uids"].cast<py::list>().size(); return out;
}

}  // namespace native_quality_witness_v3
