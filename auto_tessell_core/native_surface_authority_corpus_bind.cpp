#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <cstdint>
#include <set>
#include <string>
#include <utility>

namespace py = pybind11;

py::dict refuse(const char* reason) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "surface_authority_corpus_refused";
    result["reason"] = reason;
    result["eligible_for_surface_bl"] = false;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["candidate_discarded"] = true;
    return result;
}

bool text(const py::dict& value, const char* key) {
    return value.contains(key) && !value[key].is_none() &&
           !py::str(value[key]).cast<std::string>().empty();
}

bool map_nonempty(const py::dict& value, const char* key) {
    return value.contains(key) && py::isinstance<py::dict>(value[key]) &&
           !value[key].cast<py::dict>().empty();
}

py::dict validate(
    const std::string& source_kind,
    const std::string& raw_sha256,
    const py::dict& sidecar,
    const std::string& sidecar_sha256,
    std::int64_t source_entity_count) {
    if (source_kind != "stl" && source_kind != "step") return refuse("unsupported_source_kind");
    if (raw_sha256.empty() || sidecar_sha256.empty()) return refuse("source_or_sidecar_digest_missing");
    for (const char* key : {"schema", "source_kind", "source_sha256", "provenance"}) {
        if (!text(sidecar, key)) return refuse("sidecar_header_incomplete");
    }
    if (py::str(sidecar["schema"]).cast<std::string>() != "NativeSurfaceAuthoritySidecar/v1") {
        return refuse("sidecar_schema_unsupported");
    }
    if (py::str(sidecar["source_kind"]).cast<std::string>() != source_kind ||
        py::str(sidecar["source_sha256"]).cast<std::string>() != raw_sha256) {
        return refuse("source_digest_or_kind_mismatch");
    }
    if (source_entity_count <= 0 || !sidecar.contains("entity_count") ||
        sidecar["entity_count"].cast<std::int64_t>() != source_entity_count) {
        return refuse("source_entity_coverage_mismatch");
    }
    if (!sidecar.contains("entities") || !py::isinstance<py::list>(sidecar["entities"])) {
        return refuse("entity_authority_missing");
    }
    py::list entities = sidecar["entities"].cast<py::list>();
    if (entities.size() != static_cast<size_t>(source_entity_count)) return refuse("entity_authority_incomplete");
    std::set<std::int64_t> entity_ids;
    for (const py::handle& item : entities) {
        if (!py::isinstance<py::dict>(item)) return refuse("entity_authority_incomplete");
        py::dict entity = item.cast<py::dict>();
        for (const char* key : {"entity_id", "patch", "feature", "physical_group", "component"}) {
            if (!text(entity, key)) return refuse("entity_label_incomplete");
        }
        std::int64_t id = entity["entity_id"].cast<std::int64_t>();
        if (id < 0 || id >= source_entity_count || !entity_ids.insert(id).second) {
            return refuse("entity_id_duplicate_or_out_of_range");
        }
    }
    if (entity_ids.size() != static_cast<size_t>(source_entity_count)) return refuse("entity_authority_incomplete");
    if (!sidecar.contains("directed_wall_curves") || !py::isinstance<py::list>(sidecar["directed_wall_curves"])) {
        return refuse("directed_wall_curve_missing");
    }
    py::list curves = sidecar["directed_wall_curves"].cast<py::list>();
    if (curves.empty()) return refuse("directed_wall_curve_missing");
    std::set<std::string> curve_ids;
    std::set<std::pair<std::int64_t, std::int64_t>> directed_edges;
    for (const py::handle& item : curves) {
        if (!py::isinstance<py::dict>(item)) return refuse("wall_curve_record_invalid");
        py::dict curve = item.cast<py::dict>();
        for (const char* key : {"curve_id", "patch", "feature", "physical_group", "component"}) {
            if (!text(curve, key)) return refuse("wall_curve_label_incomplete");
        }
        std::string curve_id = py::str(curve["curve_id"]).cast<std::string>();
        if (!curve_ids.insert(curve_id).second) return refuse("wall_curve_id_duplicate");
        if (!curve.contains("owner_face") || !curve.contains("directed_edges") ||
            !py::isinstance<py::list>(curve["directed_edges"])) return refuse("wall_curve_direction_missing");
        std::int64_t owner_face = curve["owner_face"].cast<std::int64_t>();
        if (owner_face < 0 || owner_face >= source_entity_count) return refuse("wall_curve_owner_out_of_range");
        py::list edges = curve["directed_edges"].cast<py::list>();
        if (edges.empty()) return refuse("wall_curve_direction_missing");
        for (const py::handle& edge_item : edges) {
            if (!py::isinstance<py::sequence>(edge_item)) return refuse("wall_curve_edge_invalid");
            py::sequence edge = edge_item.cast<py::sequence>();
            if (edge.size() != 3) return refuse("wall_curve_edge_invalid");
            std::int64_t a = edge[0].cast<std::int64_t>();
            std::int64_t b = edge[1].cast<std::int64_t>();
            std::int64_t face = edge[2].cast<std::int64_t>();
            if (a == b || face != owner_face || face < 0 || face >= source_entity_count) {
                return refuse("wall_curve_face_binding_mismatch");
            }
            if (!directed_edges.insert({a, b}).second || directed_edges.contains({b, a})) {
                return refuse("wall_curve_duplicate_or_reversed_edge");
            }
        }
    }
    if (!map_nonempty(sidecar, "physical_group_map")) return refuse("physical_group_map_missing");
    if (source_kind == "step" && !map_nonempty(sidecar, "cad_entity_map")) {
        return refuse("cad_entity_map_missing");
    }
    py::dict result;
    result["accepted"] = true;
    result["status"] = "surface_authority_corpus_sealed";
    result["reason"] = "source_digest_entity_curve_and_group_authority_verified";
    result["eligible_for_surface_bl"] = true;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["candidate_discarded"] = false;
    result["source_kind"] = source_kind;
    result["source_sha256"] = raw_sha256;
    result["sidecar_sha256"] = sidecar_sha256;
    result["entity_count"] = source_entity_count;
    result["wall_curve_count"] = curves.size();
    result["authority_schema"] = "NativeSurfaceAuthorityReceipt/v1";
    return result;
}

PYBIND11_MODULE(native_surface_authority_corpus, module) {
    module.doc() = "Private C++23 source-authority sidecar validator for surface BL corpus";
    module.def("validate_surface_authority_corpus", &validate,
               py::arg("source_kind"), py::arg("raw_sha256"), py::arg("sidecar"),
               py::arg("sidecar_sha256"), py::arg("source_entity_count"));
}
