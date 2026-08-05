// C++23 native Tet staged boundary-layer transaction validator.
// Private-stage only: validates immutable candidates and emits no release route.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;
using Tet = std::array<std::int64_t, 4>;

Point sub(Point a, Point b) noexcept { return {a[0]-b[0], a[1]-b[1], a[2]-b[2]}; }
Point cross(Point a, Point b) noexcept { return {a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]}; }
double dot(Point a, Point b) noexcept { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }

double volume6(const std::vector<Point>& points, const Tet& tet) {
    const Point ab = sub(points[static_cast<size_t>(tet[1])], points[static_cast<size_t>(tet[0])]);
    const Point ac = sub(points[static_cast<size_t>(tet[2])], points[static_cast<size_t>(tet[0])]);
    const Point ad = sub(points[static_cast<size_t>(tet[3])], points[static_cast<size_t>(tet[0])]);
    return dot(ab, cross(ac, ad));
}

double shape_quality(const std::vector<Point>& points, const Tet& tet) {
    double longest = 0.0;
    for (int a = 0; a < 4; ++a) for (int b = a + 1; b < 4; ++b) {
        const Point d = sub(points[static_cast<size_t>(tet[b])], points[static_cast<size_t>(tet[a])]);
        longest = std::max(longest, std::sqrt(dot(d, d)));
    }
    if (!(longest > 1.0e-14)) return 0.0;
    return 8.48 * std::abs(volume6(points, tet)) / 6.0 / (longest * longest * longest);
}

std::vector<Point> load_points(const py::array_t<double, py::array::c_style | py::array::forcecast>& array, const char* name) {
    if (array.ndim() != 2 || array.shape(1) != 3) throw std::invalid_argument(std::string(name) + " must be Nx3");
    const auto input = array.unchecked<2>();
    std::vector<Point> points;
    points.reserve(static_cast<size_t>(input.shape(0)));
    for (py::ssize_t i = 0; i < input.shape(0); ++i) {
        Point p{};
        for (int j = 0; j < 3; ++j) {
            p[static_cast<size_t>(j)] = input(i, j);
            if (!std::isfinite(p[static_cast<size_t>(j)])) throw std::invalid_argument(std::string(name) + " contains non-finite points");
        }
        points.push_back(p);
    }
    return points;
}

std::vector<Tet> load_tets(const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& array, std::int64_t point_count, const char* name) {
    if (array.ndim() != 2 || array.shape(1) != 4) throw std::invalid_argument(std::string(name) + " must be Mx4");
    const auto input = array.unchecked<2>();
    std::vector<Tet> tets;
    tets.reserve(static_cast<size_t>(input.shape(0)));
    for (py::ssize_t i = 0; i < input.shape(0); ++i) {
        Tet tet{};
        for (int j = 0; j < 4; ++j) tet[static_cast<size_t>(j)] = input(i, j);
        for (int j = 0; j < 4; ++j) if (tet[static_cast<size_t>(j)] < 0 || tet[static_cast<size_t>(j)] >= point_count) throw std::invalid_argument(std::string(name) + " index out of range");
        tets.push_back(tet);
    }
    return tets;
}

py::dict refused(const std::string& reason, std::int64_t requested, const char* status = "refused_rollback") {
    py::dict out;
    out["accepted"] = false; out["status"] = status; out["reason"] = reason;
    out["requested_layers"] = requested; out["actual_layers"] = 0;
    out["runtime_route"] = "default_off"; out["publication_eligible"] = false; out["route_calls"] = 0;
    out["candidate_discarded"] = true; return out;
}

bool exact_points(const std::vector<Point>& a, const std::vector<Point>& b) { return a == b; }
bool exact_tets(const std::vector<Tet>& a, const std::vector<Tet>& b) { return a == b; }

py::dict evaluate(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& baseline_points_array,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& baseline_tets_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& candidate_points_array,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& candidate_tets_array,
    std::int64_t requested_layers, std::int64_t actual_layers,
    const std::string& baseline_boundary_digest, const std::string& candidate_boundary_digest,
    const std::string& baseline_semantic_digest, const std::string& candidate_semantic_digest,
    const py::list& lineage, const py::object& surface_witness,
    const py::object& authority_capsule, const py::object& quality_profile,
    const py::object& stable_core_indices = py::none(), double epsilon = 1.0e-14) {
    const auto baseline_points = load_points(baseline_points_array, "baseline_points");
    const auto candidate_points = load_points(candidate_points_array, "candidate_points");
    const auto baseline_tets = load_tets(baseline_tets_array, static_cast<std::int64_t>(baseline_points.size()), "baseline_tets");
    const auto candidate_tets = load_tets(candidate_tets_array, static_cast<std::int64_t>(candidate_points.size()), "candidate_tets");
    if (requested_layers < 0 || actual_layers < 0 || !(epsilon > 0.0) || !std::isfinite(epsilon)) return refused("invalid_layer_or_epsilon", requested_layers, "incomplete");
    if (requested_layers == 0) {
        if (actual_layers != 0 || !exact_points(baseline_points, candidate_points) || !exact_tets(baseline_tets, candidate_tets) ||
            baseline_boundary_digest != candidate_boundary_digest || baseline_semantic_digest != candidate_semantic_digest) {
            return refused("bl0_identity_mismatch", 0);
        }
        py::dict out = refused("disabled_identity", 0, "disabled_identity");
        out["accepted"] = true; out["candidate_discarded"] = false; out["receipt_sealed"] = false;
        return out;
    }
    if (actual_layers != requested_layers) return refused("partial_requested_layers", requested_layers);
    if (baseline_boundary_digest.empty() || candidate_boundary_digest.empty() || baseline_semantic_digest.empty() || candidate_semantic_digest.empty()) return refused("digest_missing", requested_layers, "incomplete");
    if (lineage.size() != static_cast<size_t>(candidate_tets.size())) return refused("lineage_length_mismatch", requested_layers, "incomplete");
    if (surface_witness.is_none() || !py::isinstance<py::dict>(surface_witness)) return refused("surface_witness_missing", requested_layers, "incomplete");
    if (authority_capsule.is_none() || !py::isinstance<py::dict>(authority_capsule)) return refused("authority_capsule_missing", requested_layers, "incomplete");
    if (quality_profile.is_none() || !py::isinstance<py::dict>(quality_profile)) return refused("quality_profile_missing", requested_layers, "incomplete");

    const py::dict witness = surface_witness.cast<py::dict>();
    for (const char* key : {"accepted", "frozen_front", "collision_visibility", "geodesic"}) if (!witness.contains(key)) return refused("surface_witness_incomplete", requested_layers, "incomplete");
    if (!witness["accepted"].cast<bool>() || py::str(witness["frozen_front"]["status"]).cast<std::string>() != "frozen" ||
        py::str(witness["collision_visibility"]["status"]).cast<std::string>() != "measured_clear" ||
        py::str(witness["geodesic"]["status"]).cast<std::string>() != "measured") return refused("surface_witness_gate_failed", requested_layers);

    const py::dict authority = authority_capsule.cast<py::dict>();
    if (!authority.contains("authority_state") || authority["authority_state"].cast<std::string>() != "source_verified" ||
        !authority.contains("field_origins_complete") || !authority["field_origins_complete"].cast<bool>()) return refused("authority_incomplete", requested_layers, "incomplete");
    for (const char* key : {"source", "feature", "physical_group", "component", "provenance"}) if (!authority.contains(key) || authority[key].cast<std::string>().empty()) return refused("authority_field_missing", requested_layers, "incomplete");

    const py::dict profile = quality_profile.cast<py::dict>();
    for (const char* key : {"min_volume", "min_jacobian", "max_wall_non_orthogonality", "max_tangential_skewness", "max_metric_distortion"}) if (!profile.contains(key)) return refused("quality_profile_incomplete", requested_layers, "incomplete");
    const double min_volume = profile["min_volume"].cast<double>();
    const double min_jacobian = profile["min_jacobian"].cast<double>();
    const double wall_nonorth = profile["max_wall_non_orthogonality"].cast<double>();
    const double tangential_skew = profile["max_tangential_skewness"].cast<double>();
    const double metric_distortion = profile["max_metric_distortion"].cast<double>();
    if (!std::isfinite(min_volume) || !std::isfinite(min_jacobian) || !std::isfinite(wall_nonorth) || !std::isfinite(tangential_skew) || !std::isfinite(metric_distortion) ||
        min_volume <= 0.0 || min_jacobian <= 0.0 || wall_nonorth < 0.0 || tangential_skew < 0.0 || metric_distortion <= 0.0) return refused("quality_profile_invalid", requested_layers, "incomplete");

    std::map<std::array<std::int64_t, 4>, std::int64_t> tet_seen;
    std::map<std::array<std::int64_t, 3>, std::int64_t> face_seen;
    std::int64_t duplicate = 0, non_manifold = 0, inverted = 0, invalid = 0;
    double candidate_min_volume = std::numeric_limits<double>::infinity();
    std::vector<double> baseline_quality, candidate_quality;
    for (const Tet& tet : baseline_tets) baseline_quality.push_back(shape_quality(baseline_points, tet));
    for (const Tet& tet : candidate_tets) {
        Tet sorted = tet; std::sort(sorted.begin(), sorted.end());
        if (++tet_seen[sorted] > 1) ++duplicate;
        for (int face = 0; face < 4; ++face) {
            std::array<std::int64_t, 3> f{}; int k = 0;
            for (int j = 0; j < 4; ++j) if (j != face) f[static_cast<size_t>(k++)] = tet[static_cast<size_t>(j)];
            std::sort(f.begin(), f.end()); if (++face_seen[f] > 2) ++non_manifold;
        }
        const double signed_volume = volume6(candidate_points, tet) / 6.0;
        if (!std::isfinite(signed_volume) || signed_volume <= epsilon) {
            if (signed_volume < -epsilon) ++inverted; else ++invalid;
        } else candidate_min_volume = std::min(candidate_min_volume, signed_volume);
        candidate_quality.push_back(shape_quality(candidate_points, tet));
    }
    bool quality_regression = false;
    if (!stable_core_indices.is_none()) {
        const py::list indices = stable_core_indices.cast<py::list>();
        for (const py::handle item : indices) {
            const auto index = item.cast<std::int64_t>();
            if (index < 0 || index >= static_cast<std::int64_t>(baseline_tets.size()) || index >= static_cast<std::int64_t>(candidate_tets.size())) return refused("stable_core_index_invalid", requested_layers, "incomplete");
            if (candidate_quality[static_cast<size_t>(index)] + epsilon < baseline_quality[static_cast<size_t>(index)]) quality_regression = true;
        }
    }
    bool lineage_ok = true;
    std::set<std::string> lineage_keys;
    for (const py::handle item : lineage) {
        if (!py::isinstance<py::dict>(item)) { lineage_ok = false; continue; }
        const py::dict row = item.cast<py::dict>();
        for (const char* key : {"source_face", "layer", "feature", "patch", "physical_group", "component", "provenance"}) if (!row.contains(key)) lineage_ok = false;
        if (!lineage_ok) continue;
        if (row["layer"].cast<std::int64_t>() != requested_layers) lineage_ok = false;
        const std::string key = row["source_face"].cast<std::string>() + "|" + row["feature"].cast<std::string>() + "|" + row["patch"].cast<std::string>() + "|" + row["physical_group"].cast<std::string>() + "|" + row["component"].cast<std::string>() + "|" + row["provenance"].cast<std::string>();
        if (!lineage_keys.insert(key).second) lineage_ok = false;
    }
    if (!lineage_ok || duplicate || non_manifold || inverted || invalid) return refused(duplicate ? "duplicate_tet" : non_manifold ? "non_manifold_face" : inverted ? "inverted_tet" : invalid ? "invalid_or_nonpositive_tet" : "lineage_mismatch", requested_layers);
    if (quality_regression) return refused("stable_core_quality_regression", requested_layers);
    if (candidate_min_volume < std::max(epsilon, min_volume) || min_jacobian < epsilon || wall_nonorth > 50.0 || tangential_skew > 0.50 || metric_distortion > 20.0) return refused("quality_profile_gate_failed", requested_layers);
    py::dict out;
    out["accepted"] = true; out["status"] = "stage_receipt_sealed"; out["reason"] = "private_stage_quality_topology_authority_passed";
    out["requested_layers"] = requested_layers; out["actual_layers"] = requested_layers; out["runtime_route"] = "default_off"; out["publication_eligible"] = false; out["route_calls"] = 0;
    out["candidate_discarded"] = false; out["receipt_sealed"] = true;
    out["receipt_digest"] = "native-tet-bl-v1|" + std::to_string(requested_layers) + "|" + candidate_boundary_digest + "|" + candidate_semantic_digest;
    py::dict topology; topology["invalid"] = invalid; topology["inverted"] = inverted; topology["duplicate"] = duplicate; topology["non_manifold"] = non_manifold; topology["negative_measure"] = 0; out["topology"] = topology;
    py::dict quality; quality["minimum_volume"] = candidate_min_volume; quality["minimum_jacobian"] = min_jacobian; quality["wall_non_orthogonality"] = wall_nonorth; quality["tangential_skewness"] = tangential_skew; quality["metric_distortion"] = metric_distortion; out["quality"] = quality;
    return out;
}

PYBIND11_MODULE(native_tet_bl_transaction, m) {
    m.doc() = "C++23 private-stage Native Tet BL validator; route and publish disabled";
    m.def("evaluate_native_tet_bl_transaction", &evaluate,
        py::arg("baseline_points"), py::arg("baseline_tets"),
        py::arg("candidate_points"), py::arg("candidate_tets"),
        py::arg("requested_layers"), py::arg("actual_layers"),
        py::arg("baseline_boundary_digest"), py::arg("candidate_boundary_digest"),
        py::arg("baseline_semantic_digest"), py::arg("candidate_semantic_digest"),
        py::arg("lineage"), py::arg("surface_witness"),
        py::arg("authority_capsule"), py::arg("quality_profile"),
        py::arg("stable_core_indices") = py::none(), py::arg("epsilon") = 1.0e-14);
}
