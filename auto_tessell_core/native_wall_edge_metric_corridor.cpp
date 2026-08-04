#include "native_wall_edge_metric_corridor.hpp"

#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <numeric>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

namespace py = pybind11;

namespace native_wall_edge_metric_corridor {
namespace {

using Point = std::array<double, 3>;
constexpr double kEpsilon = 1.0e-14;
constexpr double kPi = 3.141592653589793238462643383279502884;

struct Metadata {
    std::string edge_id;
    std::string sector_id;
    std::string feature;
    std::string patch;
    std::string physical_group;
    std::string component;
    std::string provenance;
};

struct EdgeGeometry : Metadata {
    Point p0{};
    Point p1{};
    Point normal{};
    bool visible = false;
};

struct BoxObstacle {
    std::string obstacle_id;
    Point lo{};
    Point hi{};
    bool blocks_visibility = false;
};

Point sub(const Point& a, const Point& b) noexcept { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point add(const Point& a, const Point& b) noexcept { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
Point mul(const Point& a, double scale) noexcept { return {a[0] * scale, a[1] * scale, a[2] * scale}; }
Point cross(const Point& a, const Point& b) noexcept {
    return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]};
}
double dot(const Point& a, const Point& b) noexcept { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double norm(const Point& value) noexcept { return std::sqrt(dot(value, value)); }

bool finite_point(const Point& value) noexcept {
    return std::all_of(value.begin(), value.end(), [](double item) { return std::isfinite(item); });
}

bool unit(const Point& value, Point& result) noexcept {
    const double length = norm(value);
    if (!(length > kEpsilon) || !std::isfinite(length)) return false;
    result = mul(value, 1.0 / length);
    return finite_point(result);
}

bool hex64(const py::handle& value) {
    if (!py::isinstance<py::str>(value)) return false;
    const auto text = value.cast<std::string>();
    return text.size() == 64U && std::all_of(text.begin(), text.end(), [](char item) {
        return (item >= '0' && item <= '9') || (item >= 'a' && item <= 'f') || (item >= 'A' && item <= 'F');
    });
}

std::string canonical(const py::handle& value) {
    if (value.is_none()) return "null;";
    if (py::isinstance<py::bool_>(value)) return value.cast<bool>() ? "bool:1;" : "bool:0;";
    if (py::isinstance<py::int_>(value)) return "int:" + std::to_string(value.cast<long long>()) + ";";
    if (py::isinstance<py::float_>(value)) {
        std::ostringstream stream;
        stream << "float:" << std::setprecision(std::numeric_limits<double>::max_digits10) << value.cast<double>() << ";";
        return stream.str();
    }
    if (py::isinstance<py::str>(value)) {
        const auto text = value.cast<std::string>();
        return "str:" + std::to_string(text.size()) + ":" + text + ";";
    }
    if (py::isinstance<py::dict>(value)) {
        std::vector<std::pair<std::string, std::string>> entries;
        for (const auto item : value.cast<py::dict>()) entries.emplace_back(py::cast<std::string>(item.first), canonical(item.second));
        std::sort(entries.begin(), entries.end());
        std::string result = "dict{";
        for (const auto& [key, encoded] : entries) result += "key:" + std::to_string(key.size()) + ":" + key + ":" + encoded;
        return result + "};";
    }
    if (py::isinstance<py::list>(value) || py::isinstance<py::tuple>(value)) {
        const auto sequence = value.cast<py::sequence>();
        std::string result = "seq[";
        for (py::ssize_t index = 0; index < static_cast<py::ssize_t>(sequence.size()); ++index) result += canonical(sequence[index]);
        return result + "];";
    }
    throw std::invalid_argument("corridor_policy_value_type_unsupported");
}

std::string digest(const std::string& text) {
    return brep_evidence::sha256_hex(std::vector<std::uint8_t>(text.begin(), text.end()));
}

py::dict refuse(const char* reason) {
    py::dict out;
    out["accepted"] = false;
    out["schema"] = "autotessell/native-wall-edge-metric-corridor/v1";
    out["status"] = "native_wall_edge_metric_corridor_refused";
    out["reason"] = reason;
    out["actual_layers"] = 0;
    out["generated_entities"] = 0;
    out["source_immutable"] = true;
    out["candidate_discarded"] = true;
    out["rollback_required"] = true;
    out["runtime_route"] = "default_off_preflight_only";
    return out;
}

bool string_value(const py::dict& value, const char* key, std::string& result) {
    if (!value.contains(key) || !py::isinstance<py::str>(value[key])) return false;
    result = value[key].cast<std::string>();
    return !result.empty();
}

bool finite_value(const py::dict& value, const char* key, double minimum) {
    if (!value.contains(key) || py::isinstance<py::bool_>(value[key])) return false;
    try {
        const double number = value[key].cast<double>();
        return std::isfinite(number) && number >= minimum;
    } catch (const py::cast_error&) { return false; }
}

bool integer_value(const py::dict& value, const char* key) {
    if (!value.contains(key) || py::isinstance<py::bool_>(value[key])) return false;
    try { return value[key].cast<long long>() >= 0; }
    catch (const py::cast_error&) { return false; }
}

bool read_point(const py::dict& value, const char* key, Point& result) {
    if (!value.contains(key)) return false;
    try {
        const auto sequence = value[key].cast<std::vector<double>>();
        if (sequence.size() != 3U) return false;
        result = {sequence[0], sequence[1], sequence[2]};
        return finite_point(result);
    } catch (const py::cast_error&) { return false; }
}

bool read_metadata(const py::dict& value, Metadata& result) {
    return string_value(value, "edge_id", result.edge_id) && string_value(value, "sector_id", result.sector_id) &&
           string_value(value, "feature", result.feature) && string_value(value, "patch", result.patch) &&
           string_value(value, "physical_group", result.physical_group) && string_value(value, "component", result.component) &&
           string_value(value, "provenance", result.provenance);
}

bool same_metadata(const Metadata& left, const Metadata& right) {
    return left.edge_id == right.edge_id && left.sector_id == right.sector_id && left.feature == right.feature &&
           left.patch == right.patch && left.physical_group == right.physical_group && left.component == right.component &&
           left.provenance == right.provenance;
}

bool read_bool(const py::dict& value, const char* key, bool& result) {
    if (!value.contains(key) || !py::isinstance<py::bool_>(value[key])) return false;
    result = value[key].cast<bool>();
    return true;
}

bool validate_authority(const py::dict& ledger, std::map<std::string, Metadata>& rows, std::string& reason) {
    bool accepted = false;
    if (!read_bool(ledger, "accepted", accepted) || !accepted) { reason = "wall_edge_authority_missing"; return false; }
    for (const char* key : {"source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"}) {
        if (!ledger.contains(key) || !hex64(ledger[key])) { reason = "wall_edge_authority_missing"; return false; }
    }
    if (!ledger.contains("topology") || !py::isinstance<py::dict>(ledger["topology"])) { reason = "topology_not_strict"; return false; }
    const auto topology = ledger["topology"].cast<py::dict>();
    for (const char* key : {"duplicate", "non_manifold", "inverted"}) {
        if (!integer_value(topology, key) || topology[key].cast<long long>() != 0) { reason = "topology_not_strict"; return false; }
    }
    if (!ledger.contains("edges") || !py::isinstance<py::list>(ledger["edges"])) { reason = "wall_edge_authority_missing"; return false; }
    for (const auto item : ledger["edges"].cast<py::list>()) {
        if (!py::isinstance<py::dict>(item)) { reason = "wall_edge_authority_missing"; return false; }
        Metadata row;
        if (!read_metadata(item.cast<py::dict>(), row) || !rows.emplace(row.edge_id, row).second) { reason = "wall_edge_authority_missing"; return false; }
    }
    if (rows.empty()) { reason = "directed_sector_missing"; return false; }
    return true;
}

bool parse_geometry(const py::dict& geometry, std::map<std::string, EdgeGeometry>& edges, std::string& reason) {
    if (!geometry.contains("edges") || !py::isinstance<py::list>(geometry["edges"])) { reason = "directed_sector_missing"; return false; }
    for (const auto item : geometry["edges"].cast<py::list>()) {
        if (!py::isinstance<py::dict>(item)) { reason = "directed_sector_missing"; return false; }
        const auto row = item.cast<py::dict>();
        EdgeGeometry edge;
        if (!read_metadata(row, edge) || !read_point(row, "p0", edge.p0) || !read_point(row, "p1", edge.p1) ||
            !read_point(row, "normal", edge.normal) || !read_bool(row, "visible", edge.visible) ||
            !edges.emplace(edge.edge_id, edge).second) { reason = "directed_sector_missing"; return false; }
    }
    if (edges.empty()) { reason = "directed_sector_missing"; return false; }
    return true;
}

bool parse_obstacles(const py::dict& input, std::vector<BoxObstacle>& obstacles, std::string& reason) {
    if (!input.contains("boxes") || !py::isinstance<py::list>(input["boxes"])) { reason = "collision_clearance_failed"; return false; }
    for (const auto item : input["boxes"].cast<py::list>()) {
        if (!py::isinstance<py::dict>(item)) { reason = "collision_clearance_failed"; return false; }
        const auto row = item.cast<py::dict>();
        BoxObstacle obstacle;
        if (!string_value(row, "obstacle_id", obstacle.obstacle_id) || !read_point(row, "lo", obstacle.lo) ||
            !read_point(row, "hi", obstacle.hi) || !read_bool(row, "blocks_visibility", obstacle.blocks_visibility) ||
            obstacle.lo[0] > obstacle.hi[0] || obstacle.lo[1] > obstacle.hi[1] || obstacle.lo[2] > obstacle.hi[2]) {
            reason = "collision_clearance_failed";
            return false;
        }
        obstacles.push_back(obstacle);
    }
    return true;
}

double point_box_distance(const Point& point, const BoxObstacle& box) noexcept {
    double sum = 0.0;
    for (int axis = 0; axis < 3; ++axis) {
        const double delta = point[axis] < box.lo[axis] ? box.lo[axis] - point[axis] : point[axis] > box.hi[axis] ? point[axis] - box.hi[axis] : 0.0;
        sum += delta * delta;
    }
    return std::sqrt(sum);
}

bool valid_sealed_policy(const py::dict& sealed, py::dict& policy, std::string& reason) {
    bool accepted = false;
    if (!read_bool(sealed, "accepted", accepted) || !accepted || !sealed.contains("policy") ||
        !py::isinstance<py::dict>(sealed["policy"]) || !hex64(sealed["policy_sha256"])) {
        reason = "policy_digest_mismatch";
        return false;
    }
    policy = sealed["policy"].cast<py::dict>();
    const auto resealed = seal_corridor_policy_v1(policy);
    if (!resealed["accepted"].cast<bool>() || resealed["policy_sha256"].cast<std::string>() != sealed["policy_sha256"].cast<std::string>()) {
        reason = "policy_digest_mismatch";
        return false;
    }
    return true;
}

double tolerance_equal(double left, double right, double tolerance) noexcept {
    return std::abs(left - right) <= tolerance * std::max({1.0, std::abs(left), std::abs(right)});
}

}  // namespace

py::dict seal_corridor_policy_v1(const py::dict& policy) {
    const std::set<std::string> allowed = {
        "engine", "source_mode", "semantic_mode", "topology_mode", "target_cells", "target_faces", "count_tolerance",
        "wall_edge_mode", "wall_selection", "feature_mode", "ridge_mode", "corner_mode", "metric_mode",
        "boundary_layer_count", "boundary_layer_first_height", "boundary_layer_final_height", "boundary_layer_total_height",
        "boundary_layer_growth", "metric_tangential_height", "metric_co_normal_height", "metric_normal_height", "anisotropy",
        "diffusion", "attenuation", "collision_tolerance", "visibility_tolerance", "height_tolerance",
        "max_metric_skewness", "max_signed_non_orthogonality", "max_metric_aspect_ratio", "min_positive_measure",
        "seed", "replay_count"};
    try {
        for (const auto item : policy) if (!allowed.contains(py::cast<std::string>(item.first))) return refuse("policy_unknown_key");
        for (const char* key : {"engine", "source_mode", "semantic_mode", "topology_mode", "wall_edge_mode", "wall_selection",
                                "feature_mode", "ridge_mode", "corner_mode", "metric_mode"}) {
            std::string ignored;
            if (!string_value(policy, key, ignored)) return refuse("policy_incomplete");
        }
        for (const char* key : {"target_cells", "target_faces", "boundary_layer_count", "seed", "replay_count"})
            if (!integer_value(policy, key)) return refuse("policy_incomplete");
        for (const char* key : {"boundary_layer_first_height", "boundary_layer_final_height", "boundary_layer_total_height",
                                "boundary_layer_growth", "metric_tangential_height", "metric_co_normal_height", "metric_normal_height",
                                "anisotropy", "diffusion", "attenuation", "collision_tolerance", "visibility_tolerance", "height_tolerance",
                                "max_metric_skewness", "max_signed_non_orthogonality", "max_metric_aspect_ratio", "min_positive_measure", "count_tolerance"})
            if (!finite_value(policy, key, 0.0)) return refuse("policy_incomplete");
        const auto layers = policy["boundary_layer_count"].cast<long long>();
        if (!(policy["metric_tangential_height"].cast<double>() > 0.0) || !(policy["metric_co_normal_height"].cast<double>() > 0.0) ||
            !(policy["metric_normal_height"].cast<double>() > 0.0) || !(policy["anisotropy"].cast<double>() > 0.0) ||
            !(policy["height_tolerance"].cast<double>() > 0.0) || !(policy["max_metric_aspect_ratio"].cast<double>() > 0.0) ||
            !(policy["min_positive_measure"].cast<double>() >= 0.0)) return refuse("policy_incomplete");
        if (layers > 0 && (!(policy["boundary_layer_first_height"].cast<double>() > 0.0) ||
                           !(policy["boundary_layer_final_height"].cast<double>() > 0.0) ||
                           !(policy["boundary_layer_total_height"].cast<double>() > 0.0) ||
                           !(policy["boundary_layer_growth"].cast<double>() >= 1.0))) return refuse("policy_incomplete");
        if (layers == 0 && (policy["boundary_layer_first_height"].cast<double>() != 0.0 ||
                            policy["boundary_layer_final_height"].cast<double>() != 0.0 ||
                            policy["boundary_layer_total_height"].cast<double>() != 0.0)) return refuse("policy_incomplete");
        const auto bytes = canonical(policy);
        py::dict out;
        out["accepted"] = true;
        out["status"] = "native_wall_edge_metric_policy_v1_sealed";
        out["schema"] = "autotessell/native-wall-edge-metric-policy/v1";
        out["policy"] = policy;
        out["policy_bytes"] = bytes;
        out["policy_sha256"] = digest(bytes);
        return out;
    } catch (const std::exception&) { return refuse("policy_value_type_unsupported"); }
}

py::dict certify_wall_edge_metric_corridor(const py::dict& authority_ledger, const py::dict& sealed_policy,
                                           const py::dict& geometry, const py::dict& obstacles) {
    try {
        py::dict policy;
        std::string reason;
        if (!valid_sealed_policy(sealed_policy, policy, reason)) return refuse(reason.c_str());
        std::map<std::string, Metadata> authority_rows;
        if (!validate_authority(authority_ledger, authority_rows, reason)) return refuse(reason.c_str());
        const auto layers = policy["boundary_layer_count"].cast<long long>();
        py::dict out;
        out["accepted"] = true;
        out["schema"] = "autotessell/native-wall-edge-metric-corridor/v1";
        out["status"] = layers == 0 ? "disabled_identity" : "wall_edge_metric_corridor_certified";
        out["policy_sha256"] = sealed_policy["policy_sha256"];
        for (const char* key : {"source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"}) out[key] = authority_ledger[key];
        out["requested_layers"] = layers;
        out["actual_layers"] = layers;
        out["source_immutable"] = true;
        out["runtime_route"] = "default_off_preflight_only";
        out["count_gate"] = "secondary_after_quality_topology_authority";
        py::dict work;
        work["layer_work"] = layers == 0 ? 0 : layers * static_cast<long long>(authority_rows.size());
        work["collision_queries"] = 0;
        work["writer_calls"] = 0;
        out["work_counters"] = work;
        if (layers == 0) {
            out["layer_heights"] = py::list();
            out["edges"] = py::list();
            py::dict identity_quality;
            identity_quality["status"] = "zero_work_identity";
            out["quality"] = identity_quality;
            out["receipt_sha256"] = digest(canonical(out));
            out["rollback_required"] = false;
            return out;
        }

        std::map<std::string, EdgeGeometry> edges;
        if (!parse_geometry(geometry, edges, reason)) return refuse(reason.c_str());
        if (edges.size() != authority_rows.size()) return refuse("source_binding_lost");
        for (const auto& [edge_id, authority] : authority_rows) {
            const auto found = edges.find(edge_id);
            if (found == edges.end() || !same_metadata(authority, found->second)) return refuse("source_binding_lost");
        }
        std::vector<BoxObstacle> boxes;
        if (!parse_obstacles(obstacles, boxes, reason)) return refuse(reason.c_str());

        const double first = policy["boundary_layer_first_height"].cast<double>();
        const double final_height = policy["boundary_layer_final_height"].cast<double>();
        const double total_height = policy["boundary_layer_total_height"].cast<double>();
        const double growth = policy["boundary_layer_growth"].cast<double>();
        const double height_tolerance = policy["height_tolerance"].cast<double>();
        std::vector<double> heights;
        heights.reserve(static_cast<std::size_t>(layers));
        double sum = 0.0;
        for (long long layer = 0; layer < layers; ++layer) {
            const double value = first * std::pow(growth, static_cast<double>(layer));
            if (!std::isfinite(value) || !(value > 0.0)) return refuse("layer_schedule_inconsistent");
            heights.push_back(value);
            sum += value;
        }
        if (!tolerance_equal(heights.back(), final_height, height_tolerance) || !tolerance_equal(sum, total_height, height_tolerance))
            return refuse("layer_schedule_inconsistent");

        const auto collision_tolerance = policy["collision_tolerance"].cast<double>();
        const auto max_skew = policy["max_metric_skewness"].cast<double>();
        const auto max_non_orth = policy["max_signed_non_orthogonality"].cast<double>();
        const auto max_aspect = policy["max_metric_aspect_ratio"].cast<double>();
        const auto min_measure = policy["min_positive_measure"].cast<double>();
        const double h_t = policy["metric_tangential_height"].cast<double>() * (1.0 + policy["diffusion"].cast<double>());
        const double h_c = policy["metric_co_normal_height"].cast<double>() * (1.0 + policy["attenuation"].cast<double>());
        const double h_n = policy["metric_normal_height"].cast<double>() / policy["anisotropy"].cast<double>();
        if (!(h_t > 0.0) || !(h_c > 0.0) || !(h_n > 0.0) || !std::isfinite(h_t) || !std::isfinite(h_c) || !std::isfinite(h_n)) return refuse("metric_not_spd");
        const std::array<double, 3> eigenvalues{1.0 / (h_t * h_t), 1.0 / (h_c * h_c), 1.0 / (h_n * h_n)};
        const double metric_aspect = std::max({h_t, h_c, h_n}) / std::min({h_t, h_c, h_n});
        if (!std::isfinite(metric_aspect) || metric_aspect > max_aspect) return refuse("metric_quality_failed");

        py::list edge_receipts;
        double worst_skew = 0.0, worst_non_orth = 0.0, minimum_measure = std::numeric_limits<double>::infinity();
        std::string worst_skew_id, worst_non_orth_id, worst_measure_id;
        long long collision_queries = 0;
        for (const auto& [edge_id, edge] : edges) {
            if (!edge.visible) return refuse("visibility_failed");
            const Point direction = sub(edge.p1, edge.p0);
            Point t, n, c;
            if (!unit(direction, t) || !unit(edge.normal, n)) return refuse("feature_frame_ambiguous");
            if (!unit(cross(n, t), c)) return refuse("feature_frame_ambiguous");
            const double skew = std::max({std::abs(dot(t, c)), std::abs(dot(t, n)), std::abs(dot(c, n))});
            const double signed_non_orth = std::acos(std::clamp(dot(t, t), -1.0, 1.0)) * 180.0 / kPi;
            const double length = norm(direction);
            const double measure = length * h_c * h_n;
            if (!std::isfinite(skew) || !std::isfinite(signed_non_orth) || !std::isfinite(measure) || !(measure > 0.0) ||
                skew > max_skew || signed_non_orth > max_non_orth || measure < min_measure) return refuse("metric_quality_failed");
            if (skew > worst_skew) { worst_skew = skew; worst_skew_id = edge_id; }
            if (signed_non_orth > worst_non_orth) { worst_non_orth = signed_non_orth; worst_non_orth_id = edge_id; }
            if (measure < minimum_measure) { minimum_measure = measure; worst_measure_id = edge_id; }

            double minimum_clearance = std::numeric_limits<double>::infinity();
            for (long long layer = 0; layer < layers; ++layer) {
                const double offset = std::accumulate(heights.begin(), heights.begin() + layer + 1, 0.0);
                for (const Point& base : {edge.p0, edge.p1, mul(add(edge.p0, edge.p1), 0.5)}) {
                    const Point sample = add(base, mul(n, offset));
                    for (const auto& box : boxes) {
                        ++collision_queries;
                        const double clearance = point_box_distance(sample, box);
                        minimum_clearance = std::min(minimum_clearance, clearance);
                        if (clearance <= collision_tolerance) return refuse("collision_clearance_failed");
                    }
                }
            }
            py::dict row;
            row["edge_id"] = edge.edge_id; row["sector_id"] = edge.sector_id; row["feature"] = edge.feature;
            row["patch"] = edge.patch; row["physical_group"] = edge.physical_group; row["component"] = edge.component;
            row["provenance"] = edge.provenance; row["t"] = std::vector<double>{t[0], t[1], t[2]};
            row["c"] = std::vector<double>{c[0], c[1], c[2]}; row["n"] = std::vector<double>{n[0], n[1], n[2]};
            row["metric_eigenvalues"] = std::vector<double>{eigenvalues[0], eigenvalues[1], eigenvalues[2]};
            row["metric_skewness"] = skew; row["signed_non_orthogonality"] = signed_non_orth; row["positive_measure"] = measure;
            if (std::isfinite(minimum_clearance)) row["minimum_clearance"] = minimum_clearance;
            else row["minimum_clearance"] = py::none();
            edge_receipts.append(row);
        }
        py::dict quality;
        quality["metric_skewness_max"] = worst_skew; quality["metric_skewness_worst_uid"] = worst_skew_id;
        quality["signed_non_orthogonality_max"] = worst_non_orth; quality["signed_non_orthogonality_worst_uid"] = worst_non_orth_id;
        quality["metric_aspect_ratio"] = metric_aspect; quality["positive_measure_min"] = minimum_measure;
        quality["positive_measure_worst_uid"] = worst_measure_id; quality["tuple_order"] = "topology_authority_quality_count";
        out["layer_heights"] = heights; out["total_height"] = sum; out["edges"] = edge_receipts; out["quality"] = quality;
        out["metric_spd"] = true; out["collision_queries"] = collision_queries;
        work["collision_queries"] = collision_queries; out["work_counters"] = work;
        out["receipt_sha256"] = digest(canonical(out)); out["rollback_required"] = false;
        return out;
    } catch (const std::exception&) { return refuse("corridor_input_type_invalid"); }
}

py::dict compare_corridor_receipts(const py::dict& candidate, const py::dict& reread) {
    if (!candidate.contains("accepted") || !reread.contains("accepted") || !candidate["accepted"].cast<bool>() || !reread["accepted"].cast<bool>()) return refuse("candidate_disk_receipt_mismatch");
    for (const char* key : {"receipt_sha256", "policy_sha256", "source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"})
        if (!candidate.contains(key) || !reread.contains(key) || candidate[key].cast<std::string>() != reread[key].cast<std::string>()) return refuse("candidate_disk_receipt_mismatch");
    py::dict out; out["accepted"] = true; out["status"] = "native_wall_edge_metric_corridor_candidate_disk_equal";
    out["candidate_disk_parity"] = true; out["floating_recompute_ulp_limit"] = 16; return out;
}

}  // namespace native_wall_edge_metric_corridor

PYBIND11_MODULE(native_wall_edge_metric_corridor, module) {
    module.def("seal_corridor_policy_v1", &native_wall_edge_metric_corridor::seal_corridor_policy_v1);
    module.def("certify_wall_edge_metric_corridor", &native_wall_edge_metric_corridor::certify_wall_edge_metric_corridor);
    module.def("compare_corridor_receipts", &native_wall_edge_metric_corridor::compare_corridor_receipts);
}
