// C++23 private direct BRepFrontEvidence/v2 ingress transaction.

#include "brep_authoritative_ingress_impl.hpp"

#include <algorithm>
#include <cstdint>
#include <set>
#include <string>
#include <tuple>

namespace py = pybind11;
using namespace autotessell_brep_authority;

namespace {

py::dict validate_actual_v2(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& positions,
    const py::dict& evidence,
    const py::list& explicit_mapping,
    std::int64_t requested_layers,
    const std::string& source_digest,
    const std::string& mapping_digest) {
    if (requested_layers < 0) return reject("negative_layer_count", requested_layers);
    if (!finite_positions(positions)) return reject("canonical_positions_invalid", requested_layers);
    if (!evidence.contains("schema") || py::str(evidence["schema"]).cast<std::string>() != "BRepFrontEvidence/v2") return reject("brep_evidence_v2_schema_mismatch", requested_layers);
    for (const char* key : {"source_digest", "canonical_positions_digest", "face_ordinal_digest", "orientation_digest", "seam_digest"}) if (!text(evidence, key)) return reject("brep_evidence_v2_digest_incomplete", requested_layers);
    if (py::str(evidence["source_digest"]).cast<std::string>() != source_digest) return reject("source_digest_mismatch", requested_layers);
    if (!evidence.contains("triangles") || !py::isinstance<py::list>(evidence["triangles"]) || !evidence.contains("edges") || !py::isinstance<py::list>(evidence["edges"]) || !evidence.contains("direction_records") || !py::isinstance<py::list>(evidence["direction_records"])) return reject("brep_v2_payload_incomplete", requested_layers);
    const auto edges = evidence["edges"].cast<py::list>();
    const auto directions = evidence["direction_records"].cast<py::list>();
    if (edges.empty() || directions.empty() || explicit_mapping.size() != edges.size()) return reject("authority_mapping_coverage_incomplete", requested_layers);
    std::set<std::tuple<std::int64_t, std::int64_t>> sectors;
    py::list lineage;
    for (py::ssize_t i = 0; i < static_cast<py::ssize_t>(edges.size()); ++i) {
        if (!py::isinstance<py::dict>(edges[i])) return reject("brep_edge_record_incomplete", requested_layers);
        const auto edge = edges[i].cast<py::dict>();
        for (const char* key : {"brep_edge_id", "is_actual_brep_edge", "owner_face_id", "canonical_endpoints", "incident_faces", "segments"}) if (!edge.contains(key)) return reject("brep_edge_record_incomplete", requested_layers);
        if (!edge["is_actual_brep_edge"].cast<bool>() || !py::isinstance<py::list>(edge["canonical_endpoints"]) || edge["canonical_endpoints"].cast<py::list>().size() != 2 || edge["segments"].cast<py::list>().empty()) return reject("brep_edge_authority_incomplete", requested_layers);
        const auto edge_id = edge["brep_edge_id"].cast<std::int64_t>();
        const auto owner = edge["owner_face_id"].cast<std::int64_t>();
        if (!sectors.emplace(edge_id, owner).second) return reject("source_sector_non_manifold", requested_layers);
        const auto mapping = explicit_mapping[i].cast<py::dict>();
        if (!mapping.contains("source_edge") || !mapping.contains("source_face") || mapping["source_edge"].cast<std::int64_t>() != edge_id || mapping["source_face"].cast<std::int64_t>() != owner) return reject("mapping_owner_mismatch", requested_layers);
        if (!mapping.contains("mapping_source") || py::str(mapping["mapping_source"]).cast<std::string>() != "explicit_user") return reject("physical_group_mapping_not_explicit", requested_layers);
        if (!mapping.contains("direct") || !mapping["direct"].cast<bool>()) return reject("lineage_not_direct", requested_layers);
        for (const char* key : {"wall_edge", "output_face", "patch", "feature", "physical_group", "component", "provenance"}) if (!text(mapping, key)) return reject("mapping_lineage_incomplete", requested_layers);
        py::dict row; row["source_edge"] = std::to_string(edge_id); row["source_face"] = std::to_string(owner);
        for (const char* key : {"wall_edge", "output_face", "patch", "feature", "physical_group", "component", "provenance"}) row[key] = mapping[key];
        lineage.append(row);
    }
    for (const py::handle handle : directions) {
        if (!py::isinstance<py::dict>(handle)) return reject("direction_record_incomplete", requested_layers);
        const auto direction = handle.cast<py::dict>();
        for (const char* key : {"sector_id", "face_normal", "surface_du", "surface_dv", "domain_side_authority"}) if (!direction.contains(key)) return reject("direction_record_incomplete", requested_layers);
        if (!direction["domain_side_authority"].cast<bool>()) return reject("direction_authority_incomplete", requested_layers);
    }
    py::dict certificate; certificate["source_kind"] = "cad_brep_v2"; certificate["raw_sha256"] = source_digest; certificate["brep_hash"] = evidence["canonical_positions_digest"]; certificate["authority"] = "actual-brep-front-evidence-v2-explicit-mapping"; certificate["provenance"] = evidence["seam_digest"];
    py::dict ingress; ingress["canonical_positions"] = positions; ingress["source_certificate"] = certificate; ingress["edge_provenance"] = lineage; ingress["source_digest"] = source_digest; ingress["mapping_digest"] = mapping_digest; ingress["face_ordinal_digest"] = evidence["face_ordinal_digest"]; ingress["orientation_digest"] = evidence["orientation_digest"]; ingress["seam_digest"] = evidence["seam_digest"];
    py::dict result; result["accepted"] = true; result["status"] = requested_layers == 0 ? "disabled_identity" : "actual_brep_ingress_sealed"; result["reason"] = "actual_brep_v2_explicit_mapping_passed"; result["requested_layers"] = requested_layers; result["actual_layers"] = requested_layers; result["optimizer_ingress"] = ingress; result["source_immutable"] = true; result["direct_lineage"] = true; result["mapping_explicit"] = true; result["runtime_route"] = "default_off"; result["publication_eligible"] = false; result["route_calls"] = 0; result["receipt_sealed"] = true; result["receipt_digest"] = std::string("actual-brep-v2|") + source_digest + "|" + mapping_digest + "|" + std::to_string(requested_layers); return result;
}

} // namespace

PYBIND11_MODULE(native_surface_bl_front_actual_v2_ingress, module) {
    module.doc() = "Private C++23 actual BRepFrontEvidence/v2 ingress; route disabled";
    module.def("validate_actual_brep_v2_ingress", &validate_actual_v2, py::arg("canonical_positions"), py::arg("evidence"), py::arg("explicit_mapping"), py::arg("requested_layers"), py::arg("source_digest"), py::arg("mapping_digest"));
}
