// C++23 private bridge from authoritative B-Rep evidence to surface BL ingress.
// No OCCT linkage and no production route: this module only seals evidence.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <set>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;

namespace {

py::dict reject(const std::string& reason, std::int64_t requested) {
    py::dict r;
    r["accepted"] = false;
    r["status"] = "refused_rollback";
    r["reason"] = reason;
    r["requested_layers"] = requested;
    r["actual_layers"] = 0;
    r["runtime_route"] = "default_off";
    r["publication_eligible"] = false;
    r["route_calls"] = 0;
    r["candidate_discarded"] = true;
    return r;
}

bool text(const py::dict& d, const char* key) {
    return d.contains(key) && !py::str(d[key]).cast<std::string>().empty();
}

bool integer(const py::dict& d, const char* key) {
    return d.contains(key) && py::isinstance<py::int_>(d[key]);
}

bool finite_matrix(const py::array_t<double, py::array::c_style | py::array::forcecast>& a, int width) {
    if (a.ndim() != 2 || a.shape(1) != width) return false;
    const auto* data = a.data();
    for (py::ssize_t i = 0; i < a.size(); ++i) if (!std::isfinite(data[i])) return false;
    return true;
}

py::dict bridge(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edges,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals,
    std::int64_t requested_layers,
    const py::dict& evidence,
    const py::list& direction_records,
    const py::list& explicit_mapping,
    const py::dict& digests) {
    if (requested_layers < 0) return reject("negative_layer_count", requested_layers);
    if (!finite_matrix(points, 3) || !finite_matrix(normals, 3) || edges.ndim() != 2 || edges.shape(1) != 4) return reject("invalid_ingress_arrays", requested_layers);
    if (!evidence.contains("accepted") || !evidence["accepted"].cast<bool>() || !text(evidence, "version") || py::str(evidence["version"]).cast<std::string>() != "v2") return reject("brep_evidence_v2_incomplete", requested_layers);
    for (const char* key : {"source_kind", "raw_sha256", "brep_hash", "source_digest", "seam_digest", "orientation_digest", "face_ordinal_digest", "provenance_digest"}) if (!text(evidence, key)) return reject("brep_evidence_v2_incomplete", requested_layers);
    for (const char* key : {"source_digest", "seam_digest", "orientation_digest", "face_ordinal_digest", "mapping_digest"}) if (!text(digests, key)) return reject("authority_digest_incomplete", requested_layers);
    if (direction_records.size() != static_cast<size_t>(normals.shape(0)) || explicit_mapping.size() != static_cast<size_t>(edges.shape(0))) return reject("authority_mapping_coverage_incomplete", requested_layers);

    std::set<std::tuple<std::int64_t, std::int64_t>> sectors;
    const auto* edge_data = edges.data();
    py::list lineage;
    for (py::ssize_t i = 0; i < edges.shape(0); ++i) {
        const auto offset = static_cast<size_t>(i) * 4U;
        const std::int64_t edge_id = edge_data[offset];
        const std::int64_t a = edge_data[offset + 1U];
        const std::int64_t b = edge_data[offset + 2U];
        const std::int64_t face = edge_data[offset + 3U];
        if (edge_id < 0 || a < 0 || b < 0 || a >= points.shape(0) || b >= points.shape(0) || a == b || face < 0 || face >= normals.shape(0)) return reject("source_sector_invalid", requested_layers);
        if (!sectors.emplace(edge_id, face).second) return reject("source_sector_non_manifold", requested_layers);
        const auto mapping = explicit_mapping[i].cast<py::dict>();
        if (!integer(mapping, "source_edge") || !integer(mapping, "source_face") || mapping["source_edge"].cast<std::int64_t>() != edge_id || mapping["source_face"].cast<std::int64_t>() != face) return reject("mapping_owner_mismatch", requested_layers);
        if (!text(mapping, "mapping_source") || py::str(mapping["mapping_source"]).cast<std::string>() != "explicit_user") return reject("physical_group_mapping_not_explicit", requested_layers);
        if (!mapping.contains("direct") || !mapping["direct"].cast<bool>()) return reject("lineage_not_direct", requested_layers);
        for (const char* key : {"wall_edge", "output_face", "patch", "feature", "physical_group", "component", "provenance"}) if (!text(mapping, key)) return reject("mapping_lineage_incomplete", requested_layers);
        py::dict row;
        row["source_edge"] = std::to_string(edge_id);
        row["source_face"] = std::to_string(face);
        for (const char* key : {"wall_edge", "output_face", "patch", "feature", "physical_group", "component", "provenance"}) row[key] = mapping[key];
        lineage.append(row);
    }
    for (const py::handle handle : direction_records) {
        if (!py::isinstance<py::dict>(handle)) return reject("direction_contract_incomplete", requested_layers);
        const auto record = handle.cast<py::dict>();
        for (const char* key : {"face", "source_face", "orientation", "seam", "normal", "direction"}) if (!record.contains(key)) return reject("direction_contract_incomplete", requested_layers);
    }

    py::dict certificate;
    certificate["source_kind"] = evidence["source_kind"];
    certificate["raw_sha256"] = evidence["raw_sha256"];
    certificate["brep_hash"] = evidence["brep_hash"];
    certificate["authority"] = "brep-front-evidence-v2-explicit-mapping";
    certificate["provenance"] = evidence["provenance_digest"];
    py::dict ingress;
    ingress["points"] = points;
    ingress["edges"] = edges;
    ingress["face_normals"] = normals;
    ingress["source_certificate"] = certificate;
    ingress["edge_provenance"] = lineage;
    ingress["source_digest"] = digests["source_digest"];
    ingress["seam_digest"] = digests["seam_digest"];
    ingress["orientation_digest"] = digests["orientation_digest"];
    ingress["face_ordinal_digest"] = digests["face_ordinal_digest"];
    ingress["mapping_digest"] = digests["mapping_digest"];

    py::dict result;
    result["accepted"] = true;
    result["status"] = requested_layers == 0 ? "disabled_identity" : "authoritative_ingress_sealed";
    result["reason"] = "brep_v2_explicit_mapping_authority_passed";
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = requested_layers;
    result["optimizer_ingress"] = ingress;
    result["source_immutable"] = true;
    result["mapping_explicit"] = true;
    result["direct_lineage"] = true;
    result["runtime_route"] = "default_off";
    result["publication_eligible"] = false;
    result["route_calls"] = 0;
    result["receipt_sealed"] = true;
    result["receipt_digest"] = std::string("brep-bridge-v1|") + py::str(digests["source_digest"]).cast<std::string>() + "|" + py::str(digests["mapping_digest"]).cast<std::string>() + "|" + std::to_string(requested_layers);
    return result;
}

} // namespace

PYBIND11_MODULE(native_surface_bl_front_authority_bridge, module) {
    module.doc() = "C++23 private authoritative B-Rep wall-edge bridge; route disabled";
    module.def("bridge_authoritative_surface_wall_edge", &bridge,
        py::arg("points"), py::arg("edges"), py::arg("face_normals"), py::arg("requested_layers"),
        py::arg("evidence"), py::arg("direction_records"), py::arg("explicit_mapping"), py::arg("digests"));
}
