#include <pybind11/pybind11.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace py = pybind11;
using P = std::array<double, 3>;
using T = std::array<std::int64_t, 3>;

static py::dict reject(const std::string& reason) {
    py::dict out;
    out["accepted"] = false;
    out["status"] = "native_surface_readback_refused";
    out["reason"] = reason;
    out["publication_eligible"] = false;
    return out;
}

template <typename V>
static void hash_value(std::uint64_t& h, const V& value) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(&value);
    for (std::size_t i = 0; i < sizeof(V); ++i) {
        h ^= bytes[i];
        h *= 1099511628211ULL;
    }
}

static double area2(const P& a, const P& b, const P& c) {
    const P u{b[0] - a[0], b[1] - a[1], b[2] - a[2]};
    const P v{c[0] - a[0], c[1] - a[1], c[2] - a[2]};
    const P n{u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]};
    return std::sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]);
}

static py::dict verify(const py::dict& manifest) {
    if (!manifest.contains("producer") || !manifest.contains("source_profile") || !manifest.contains("source_sha256")) return reject("readback_manifest_fields_missing");
    auto producer = manifest["producer"].cast<py::dict>();
    auto profile = manifest["source_profile"].cast<py::dict>();
    if (py::str(manifest["source_sha256"]).cast<std::string>().empty() ||
        !profile.contains("authority_sha256") ||
        py::str(profile["authority_sha256"]).cast<std::string>().empty()) return reject("readback_authority_digest_missing");
    if (!producer.contains("accepted") || !producer["accepted"].cast<bool>()) return reject("producer_not_accepted");
    if (!profile.contains("accepted") || !profile["accepted"].cast<bool>()) return reject("source_profile_not_authoritative");
    if (producer.contains("publication_eligible") && producer["publication_eligible"].cast<bool>()) return reject("publication_route_enabled");
    auto points_list = producer["points"].cast<py::list>();
    auto triangles_list = producer["triangles"].cast<py::list>();
    auto lineage = producer["provenance"].cast<py::list>();
    std::vector<P> points;
    points.reserve(points_list.size());
    std::uint64_t fingerprint = 1469598103934665603ULL;
    for (auto item : points_list) {
        auto row = py::reinterpret_borrow<py::sequence>(item);
        if (row.size() != 3) return reject("readback_point_shape_invalid");
        P p{row[0].cast<double>(), row[1].cast<double>(), row[2].cast<double>()};
        for (double value : p) if (!std::isfinite(value)) return reject("readback_nonfinite_point");
        points.push_back(p);
        for (double value : p) hash_value(fingerprint, value);
    }
    std::vector<T> triangles;
    triangles.reserve(triangles_list.size());
    std::set<T> unique_triangles;
    std::map<std::array<std::int64_t, 2>, int> edge_incidence;
    int zero_area = 0;
    for (auto item : triangles_list) {
        auto row = py::reinterpret_borrow<py::sequence>(item);
        if (row.size() != 3) return reject("readback_triangle_shape_invalid");
        T tri{row[0].cast<std::int64_t>(), row[1].cast<std::int64_t>(), row[2].cast<std::int64_t>()};
        for (auto index : tri) if (index < 0 || index >= static_cast<std::int64_t>(points.size())) return reject("readback_triangle_index_invalid");
        T key = tri;
        std::sort(key.begin(), key.end());
        if (!unique_triangles.insert(key).second) return reject("readback_duplicate_triangle");
        if (!(area2(points[tri[0]], points[tri[1]], points[tri[2]]) > 1e-14)) ++zero_area;
        for (int i = 0; i < 3; ++i) {
            std::array<std::int64_t, 2> edge{tri[i], tri[(i + 1) % 3]};
            if (edge[1] < edge[0]) std::swap(edge[0], edge[1]);
            ++edge_incidence[edge];
        }
        for (auto index : tri) hash_value(fingerprint, index);
        triangles.push_back(tri);
    }
    int non_manifold = 0;
    for (const auto& [edge, count] : edge_incidence) if (count > 2) ++non_manifold;
    if (zero_area || non_manifold) return reject(zero_area ? "readback_zero_area" : "readback_non_manifold");
    if (lineage.size() != triangles.size()) return reject("readback_lineage_count_mismatch");
    for (auto item : lineage) {
        auto row = item.cast<py::dict>();
        for (const char* key : {"source_face", "source_edge", "feature", "patch", "physical_group", "component", "provenance"}) {
            if (!row.contains(key) || py::str(row[key]).cast<std::string>().empty()) return reject("readback_semantic_lineage_incomplete");
        }
    }
    const auto requested = producer["requested_layers"].cast<std::int64_t>();
    const auto actual = producer["actual_layers"].cast<std::int64_t>();
    if (requested != actual || requested < 0) return reject("readback_layer_count_mismatch");
    auto layer_records = producer["layer_records"].cast<py::list>();
    if (requested > 0 && layer_records.size() < static_cast<std::size_t>(requested)) return reject("readback_layer_records_missing");
    for (auto item : layer_records) {
        auto row = item.cast<py::dict>();
        if (!row.contains("height") || !(row["height"].cast<double>() > 0.0)) return reject("readback_nonpositive_layer");
    }
    auto quality = producer["quality"].cast<py::dict>();
    if (quality["duplicate"].cast<int>() || quality["non_manifold"].cast<int>() || quality["inverted"].cast<int>() || quality["self_intersection"].cast<int>()) return reject("readback_declared_topology_failure");
    if (quality["minimum_metric_triangle_quality"].cast<double>() < 0.20 || quality["metric_aspect_ratio"].cast<double>() > 10.0) return reject("readback_quality_failure");
    if (quality["max_skewness"].cast<double>() > 0.30 || quality["max_non_orthogonality"].cast<double>() > 30.0) return reject("readback_quality_threshold_failure");
    py::dict topology;
    topology["duplicate"] = 0;
    topology["non_manifold"] = non_manifold;
    topology["inverted"] = 0;
    topology["zero_area"] = zero_area;
    py::dict out;
    out["accepted"] = true;
    out["status"] = "native_surface_readback_verified";
    out["publication_eligible"] = false;
    out["point_count"] = points.size();
    out["triangle_count"] = triangles.size();
    out["recomputed_topology"] = topology;
    std::ostringstream hex;
    hex << std::hex << std::setw(16) << std::setfill('0') << fingerprint;
    out["geometry_fingerprint"] = hex.str();
    if (manifest.contains("native_geometry_fingerprint") &&
        py::str(manifest["native_geometry_fingerprint"]).cast<std::string>() != hex.str()) return reject("readback_native_fingerprint_mismatch");
    if (manifest.contains("orchestration_geometry_fingerprint") &&
        py::str(manifest["orchestration_geometry_fingerprint"]).cast<std::string>() != hex.str()) return reject("readback_orchestration_fingerprint_mismatch");
    out["lineage_count"] = lineage.size();
    out["actual_layers"] = actual;
    return out;
}

PYBIND11_MODULE(native_surface_bl_readback_verifier, module) {
    module.def("verify_persisted_folded_manifest", &verify);
}
