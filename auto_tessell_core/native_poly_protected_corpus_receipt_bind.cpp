#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <cstdint>
#include <set>
#include <string>

namespace py = pybind11;

py::dict refuse(const char* reason, std::int64_t requested) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "native_poly_protected_corpus_refused";
    result["reason"] = reason;
    result["actual_layers"] = 0;
    result["publication_eligible"] = false;
    result["candidate_discarded"] = true;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["requested_layers"] = requested;
    return result;
}

bool text(const py::dict& value, const char* key) {
    return value.contains(key) && !value[key].is_none() &&
           !py::str(value[key]).cast<std::string>().empty();
}

bool equal_text(const py::dict& value, const char* key, const std::string& expected) {
    return text(value, key) && py::str(value[key]).cast<std::string>() == expected;
}

bool nonempty_dict(const py::dict& value, const char* key) {
    return value.contains(key) && py::isinstance<py::dict>(value[key]) &&
           !value[key].cast<py::dict>().empty();
}

bool nonempty_list(const py::dict& value, const char* key) {
    return value.contains(key) && py::isinstance<py::list>(value[key]) &&
           !value[key].cast<py::list>().empty();
}

py::dict validate(
    const std::string& protected_ref,
    const std::string& protected_commit,
    const std::string& protected_tree,
    const std::string& raw_source_sha256,
    const py::dict& package,
    const std::string& package_sha256,
    std::int64_t requested_layers) {
    if (requested_layers < 0) return refuse("requested_layers_invalid", requested_layers);
    if (protected_ref != "codex/native-poly-cycle41-solid-volume-timeout-1" ||
        protected_commit != "70ce4b9b") {
        return refuse("protected_ref_or_commit_mismatch", requested_layers);
    }
    if (protected_tree.empty() || raw_source_sha256.empty() || package_sha256.empty()) {
        return refuse("protected_or_source_digest_missing", requested_layers);
    }
    if (!equal_text(package, "schema", "NativePolyProtectedCorpusPackage/v1") ||
        !equal_text(package, "protected_ref", protected_ref) ||
        !equal_text(package, "protected_commit", protected_commit) ||
        !equal_text(package, "protected_tree", protected_tree) ||
        !equal_text(package, "raw_source_sha256", raw_source_sha256) ||
        !text(package, "issuer") || !text(package, "tool") ||
        !text(package, "reader_options") || !text(package, "provenance")) {
        return refuse("source_authority_package_header_incomplete", requested_layers);
    }
    if (!nonempty_dict(package, "trust") || !nonempty_dict(package, "source_reader") ||
        !nonempty_dict(package, "source_output_map")) {
        return refuse("source_authority_package_evidence_missing", requested_layers);
    }
    py::dict source_output_map = package["source_output_map"].cast<py::dict>();
    if (!nonempty_list(source_output_map, "source_face_to_output_faces") ||
        !nonempty_list(source_output_map, "wall_edges")) {
        return refuse("direct_source_output_map_incomplete", requested_layers);
    }
    if (!nonempty_list(package, "faces") || !nonempty_list(package, "physical_groups") ||
        !nonempty_list(package, "components")) {
        return refuse("feature_patch_group_component_coverage_missing", requested_layers);
    }
    if (requested_layers == 0) {
        if (!package.contains("bl0") || !py::isinstance<py::dict>(package["bl0"])) {
            return refuse("bl0_identity_receipt_missing", 0);
        }
        py::dict bl0 = package["bl0"].cast<py::dict>();
        if (!bl0.contains("exact_identity") || !bl0["exact_identity"].cast<bool>() ||
            !equal_text(bl0, "source_digest", raw_source_sha256) ||
            !text(bl0, "output_digest") || bl0["output_digest"].cast<std::string>() != raw_source_sha256) {
            return refuse("bl0_identity_mismatch", 0);
        }
    } else {
        if (!package.contains("positive_bl") || !py::isinstance<py::dict>(package["positive_bl"])) {
            return refuse("positive_bl_receipt_missing", requested_layers);
        }
        py::dict bl = package["positive_bl"].cast<py::dict>();
        if (!bl.contains("requested_layers") || !bl.contains("actual_layers") ||
            bl["requested_layers"].cast<std::int64_t>() != requested_layers ||
            bl["actual_layers"].cast<std::int64_t>() != requested_layers) {
            return refuse("partial_positive_layer", requested_layers);
        }
        if (!nonempty_list(bl, "direct_layer_final_ids") ||
            !nonempty_dict(bl, "topology") || !nonempty_dict(bl, "quality")) {
            return refuse("positive_bl_direct_or_quality_evidence_missing", requested_layers);
        }
        py::dict topology = bl["topology"].cast<py::dict>();
        py::dict quality = bl["quality"].cast<py::dict>();
        if (!topology.contains("accepted") || !topology["accepted"].cast<bool>() ||
            !quality.contains("accepted") || !quality["accepted"].cast<bool>()) {
            return refuse("positive_bl_topology_or_quality_refused", requested_layers);
        }
        if (!nonempty_list(bl, "fresh_process_digests")) return refuse("repeatability_evidence_missing", requested_layers);
        py::list digests = bl["fresh_process_digests"].cast<py::list>();
        if (digests.size() != 3 || py::str(digests[0]).cast<std::string>() != py::str(digests[1]).cast<std::string>() ||
            py::str(digests[1]).cast<std::string>() != py::str(digests[2]).cast<std::string>()) {
            return refuse("repeatability_digest_mismatch", requested_layers);
        }
    }
    py::dict result;
    result["accepted"] = true;
    result["status"] = "native_poly_protected_corpus_receipt_sealed";
    result["reason"] = requested_layers == 0 ? "protected_bl0_identity_authority_verified" : "protected_bl_authority_topology_quality_repeatability_verified";
    result["actual_layers"] = requested_layers;
    result["requested_layers"] = requested_layers;
    result["publication_eligible"] = false;
    result["candidate_discarded"] = false;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["protected_ref"] = protected_ref;
    result["protected_commit"] = protected_commit;
    result["protected_tree"] = protected_tree;
    result["raw_source_sha256"] = raw_source_sha256;
    result["package_sha256"] = package_sha256;
    result["authority_schema"] = "NativePolyProtectedCorpusReceipt/v1";
    return result;
}

PYBIND11_MODULE(native_poly_protected_corpus_receipt, module) {
    module.doc() = "Private C++23 audit-only protected Native Poly corpus receipt";
    module.def("validate_native_poly_protected_corpus", &validate,
               py::arg("protected_ref"), py::arg("protected_commit"),
               py::arg("protected_tree"), py::arg("raw_source_sha256"),
               py::arg("package"), py::arg("package_sha256"),
               py::arg("requested_layers"));
}
