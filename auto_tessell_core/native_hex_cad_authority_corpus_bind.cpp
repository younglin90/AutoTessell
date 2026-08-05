#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <cstdint>
#include <set>
#include <string>

namespace py = pybind11;

py::dict refuse(const char* reason) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "native_hex_cad_authority_refused";
    result["reason"] = reason;
    result["eligible_for_hex_bl"] = false;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["candidate_discarded"] = true;
    result["actual_layers"] = 0;
    return result;
}

bool text(const py::dict& value, const char* key) {
    return value.contains(key) && !value[key].is_none() &&
           !py::str(value[key]).cast<std::string>().empty();
}

bool nonempty_dict(const py::dict& value, const char* key) {
    return value.contains(key) && py::isinstance<py::dict>(value[key]) &&
           !value[key].cast<py::dict>().empty();
}

py::dict validate(
    const std::string& raw_sha256,
    const std::string& canonical_snapshot_sha256,
    const py::dict& sidecar,
    const std::string& sidecar_sha256,
    std::int64_t face_count) {
    if (raw_sha256.empty() || canonical_snapshot_sha256.empty() || sidecar_sha256.empty()) {
        return refuse("source_or_snapshot_digest_missing");
    }
    for (const char* key : {"schema", "source_sha256", "canonical_snapshot_sha256",
                            "reader_id", "author", "tool", "provenance"}) {
        if (!text(sidecar, key)) return refuse("cad_sidecar_header_incomplete");
    }
    if (py::str(sidecar["schema"]).cast<std::string>() != "NativeHexCadAuthoritySidecar/v1") {
        return refuse("cad_sidecar_schema_unsupported");
    }
    if (py::str(sidecar["source_sha256"]).cast<std::string>() != raw_sha256 ||
        py::str(sidecar["canonical_snapshot_sha256"]).cast<std::string>() != canonical_snapshot_sha256) {
        return refuse("source_or_snapshot_digest_mismatch");
    }
    if (face_count <= 0 || !sidecar.contains("face_count") ||
        sidecar["face_count"].cast<std::int64_t>() != face_count) {
        return refuse("cad_face_coverage_mismatch");
    }
    if (!text(sidecar, "orientation_digest") || !text(sidecar, "seam_digest")) {
        return refuse("canonical_orientation_or_seam_digest_missing");
    }
    if (!sidecar.contains("faces") || !py::isinstance<py::list>(sidecar["faces"])) {
        return refuse("cad_face_authority_missing");
    }
    py::list faces = sidecar["faces"].cast<py::list>();
    if (faces.size() != static_cast<size_t>(face_count)) return refuse("cad_face_authority_incomplete");
    std::set<std::int64_t> face_ids;
    for (const py::handle& item : faces) {
        if (!py::isinstance<py::dict>(item)) return refuse("cad_face_record_invalid");
        py::dict face = item.cast<py::dict>();
        for (const char* key : {"face_id", "feature", "patch", "physical_group", "component"}) {
            if (!text(face, key)) return refuse("cad_face_label_incomplete");
        }
        std::int64_t id = face["face_id"].cast<std::int64_t>();
        if (id < 0 || id >= face_count || !face_ids.insert(id).second) {
            return refuse("cad_face_id_duplicate_or_out_of_range");
        }
    }
    if (!sidecar.contains("wall_selection") || !py::isinstance<py::list>(sidecar["wall_selection"])) {
        return refuse("cad_wall_selection_missing");
    }
    py::list selection = sidecar["wall_selection"].cast<py::list>();
    if (selection.empty()) return refuse("cad_wall_selection_missing");
    std::set<std::string> curve_ids;
    std::set<std::int64_t> selected_faces;
    for (const py::handle& item : selection) {
        if (!py::isinstance<py::dict>(item)) return refuse("cad_wall_selection_invalid");
        py::dict row = item.cast<py::dict>();
        for (const char* key : {"face_id", "patch", "feature", "physical_group", "component"}) {
            if (!text(row, key)) return refuse("cad_wall_selection_label_incomplete");
        }
        std::int64_t face_id = row["face_id"].cast<std::int64_t>();
        if (!face_ids.contains(face_id) || !selected_faces.insert(face_id).second) {
            return refuse("cad_wall_face_ownership_ambiguous");
        }
        if (!row.contains("directed_curve_ids") || !py::isinstance<py::list>(row["directed_curve_ids"])) {
            return refuse("cad_directed_curve_selection_missing");
        }
        py::list curves = row["directed_curve_ids"].cast<py::list>();
        if (curves.empty()) return refuse("cad_directed_curve_selection_missing");
        for (const py::handle& curve : curves) {
            std::string id = py::str(curve).cast<std::string>();
            if (id.empty() || !curve_ids.insert(id).second) return refuse("cad_curve_id_duplicate_or_ambiguous");
        }
    }
    if (!nonempty_dict(sidecar, "physical_group_map")) return refuse("cad_physical_group_map_missing");
    if (!nonempty_dict(sidecar, "component_map")) return refuse("cad_component_map_missing");

    py::dict result;
    result["accepted"] = true;
    result["status"] = "native_hex_cad_authority_sealed";
    result["reason"] = "step_snapshot_face_curve_and_group_authority_verified";
    result["eligible_for_hex_bl"] = true;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["candidate_discarded"] = false;
    result["actual_layers"] = 0;
    result["source_sha256"] = raw_sha256;
    result["canonical_snapshot_sha256"] = canonical_snapshot_sha256;
    result["sidecar_sha256"] = sidecar_sha256;
    result["face_count"] = face_count;
    result["selected_wall_face_count"] = static_cast<std::int64_t>(selection.size());
    result["selected_curve_count"] = static_cast<std::int64_t>(curve_ids.size());
    result["authority_schema"] = "NativeHexCadAuthorityReceipt/v1";
    return result;
}

PYBIND11_MODULE(native_hex_cad_authority_corpus, module) {
    module.doc() = "Private C++23 Native Hex CAD authority sidecar validator";
    module.def("validate_native_hex_cad_authority", &validate,
               py::arg("raw_sha256"), py::arg("canonical_snapshot_sha256"),
               py::arg("sidecar"), py::arg("sidecar_sha256"), py::arg("face_count"));
}
