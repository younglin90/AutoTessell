#include <pybind11/pybind11.h>
#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <map>
#include <string>
#include <string_view>
#include <set>
#include <vector>

namespace py = pybind11;

namespace {
constexpr std::array<std::string_view, 10> digest_fields{
    "source_sha256", "route_sha256", "geometry_sha256", "topology_sha256",
    "boundary_sha256", "feature_sha256", "physical_group_sha256",
    "component_sha256", "provenance_sha256", "artifact_tree_sha256"};
constexpr std::array<std::string_view, 2> witness_fields{
    "quality_witness_digest", "authority_certificate_sha256"};
constexpr std::array<std::string_view, 4> semantic_fields{
    "schema", "engine", "product", "mode"};
constexpr std::array<std::string_view, 5> topology_fields{
    "invalid", "inverted", "duplicate", "non_manifold", "self_intersecting"};

bool valid_digest(const py::handle& value) {
    if (!py::isinstance<py::str>(value)) return false;
    const std::string text = value.cast<std::string>();
    if (text.size() != 64) return false;
    return std::all_of(text.begin(), text.end(), [](unsigned char c) {
        return std::isdigit(c) || (c >= 'a' && c <= 'f');
    });
}

bool non_empty_string(const py::handle& value) {
    return py::isinstance<py::str>(value) && !value.cast<std::string>().empty();
}

void require_field(const py::dict& record, std::string_view key,
                   std::vector<std::string>& reasons) {
    const std::string name(key);
    if (!record.contains(name.c_str()) || record[name.c_str()].is_none()) {
        reasons.push_back("record_missing:" + name);
    }
}

bool validate_record(const py::dict& record, std::vector<std::string>& reasons) {
    for (const auto key : semantic_fields) {
        require_field(record, key, reasons);
        if (record.contains(std::string(key).c_str()) &&
            !non_empty_string(record[std::string(key).c_str()])) {
            reasons.push_back("record_invalid:" + std::string(key));
        }
    }
    for (const auto key : digest_fields) {
        require_field(record, key, reasons);
        if (record.contains(std::string(key).c_str()) &&
            !valid_digest(record[std::string(key).c_str()])) {
            reasons.push_back("record_invalid_digest:" + std::string(key));
        }
    }
    for (const auto key : witness_fields) {
        require_field(record, key, reasons);
        if (record.contains(std::string(key).c_str()) &&
            !valid_digest(record[std::string(key).c_str()])) {
            reasons.push_back("record_invalid_digest:" + std::string(key));
        }
    }
    return reasons.empty();
}

bool exact_record_equal(const py::dict& left, const py::dict& right) {
    try {
        return left.attr("__eq__")(right).cast<bool>();
    } catch (const py::error_already_set&) {
        return false;
    }
}

bool same_value(const py::dict& left, const py::dict& right, const char* key) {
    if (!left.contains(key) || !right.contains(key)) return false;
    return left[key].equal(right[key]);
}

void validate_topology(const py::dict& topology, std::vector<std::string>& reasons) {
    for (const auto key : topology_fields) {
        const std::string name(key);
        if (!topology.contains(name.c_str())) {
            reasons.push_back("topology_missing:" + name);
            continue;
        }
        try {
            if (topology[name.c_str()].cast<std::int64_t>() != 0) {
                reasons.push_back("topology_nonzero:" + name);
            }
        } catch (const py::cast_error&) {
            reasons.push_back("topology_invalid:" + name);
        }
    }
}

void validate_quality(const py::dict& quality, const std::string& profile,
                      const py::dict& candidate,
                      std::vector<std::string>& reasons) {
    bool witness_accepted = false;
    try {
        witness_accepted = quality.contains("accepted") &&
                           quality["accepted"].cast<bool>();
    } catch (const py::cast_error&) {
        witness_accepted = false;
    }
    if (!witness_accepted) reasons.push_back("quality_witness_not_accepted");
    if (profile.empty()) reasons.push_back("quality_profile_missing");
    if (!candidate.contains("quality_profile_id") ||
        !non_empty_string(candidate["quality_profile_id"]) ||
        candidate["quality_profile_id"].cast<std::string>() != profile) {
        reasons.push_back("quality_profile_mismatch");
    }
    if (!quality.contains("profile_id") ||
        !non_empty_string(quality["profile_id"]) ||
        quality["profile_id"].cast<std::string>() != profile) {
        reasons.push_back("quality_witness_profile_mismatch");
    }
    if (!candidate.contains("quality_witness_digest") ||
        !valid_digest(candidate["quality_witness_digest"])) {
        reasons.push_back("quality_witness_digest_missing");
    }
}

py::dict evaluate_bl_identity_record(
    const py::dict& baseline, const py::dict& candidate,
    std::int64_t requested_layers, std::int64_t actual_layers,
    const py::dict& topology, const py::dict& quality,
    bool authority_complete, bool stage_publish_receipt,
    const std::string& quality_profile_id) {
    std::vector<std::string> reasons;
    validate_record(baseline, reasons);
    validate_record(candidate, reasons);
    validate_topology(topology, reasons);
    if (requested_layers < 0 || actual_layers < 0) reasons.push_back("layer_count_negative");

    const bool bl0 = requested_layers == 0;
    const bool exact_identity = exact_record_equal(baseline, candidate);
    if (bl0) {
        if (actual_layers != 0) reasons.push_back("bl0_actual_layer_nonzero");
        if (!candidate.contains("mode") ||
            !non_empty_string(candidate["mode"]) ||
            candidate["mode"].cast<std::string>() != "disabled_identity") {
            reasons.push_back("bl0_mode_not_identity");
        }
        if (!exact_identity) reasons.push_back("bl0_baseline_identity_mismatch");
    } else if (requested_layers > 0) {
        if (actual_layers != requested_layers) reasons.push_back("layer_count_mismatch");
        if (candidate.contains("mode") && non_empty_string(candidate["mode"]) &&
            candidate["mode"].cast<std::string>() == "disabled_identity") {
            reasons.push_back("positive_bl_disabled_identity");
        }
        for (const char* key : {"schema", "engine", "product", "source_sha256", "route_sha256"}) {
            if (!same_value(baseline, candidate, key)) {
                reasons.push_back(std::string("positive_bl_record_mismatch:") + key);
            }
        }
        validate_quality(quality, quality_profile_id, candidate, reasons);
        if (!authority_complete) reasons.push_back("authority_incomplete");
        if (!stage_publish_receipt) reasons.push_back("stage_publish_receipt_missing");
    } else {
        reasons.push_back("layer_count_invalid");
    }

    const bool accepted = reasons.empty();
    py::list reason_list;
    for (const std::string& reason : reasons) reason_list.append(reason);
    py::dict result;
    result["accepted"] = accepted;
    result["status"] = bl0 && accepted ? "identity_pass"
        : (!bl0 && accepted ? "publish_eligible" : "refused_rollback");
    result["reason"] = accepted ? (bl0 ? "baseline_identity_exact" : "positive_bl_publish_eligible")
                                : "identity_or_atomic_gate_failed";
    result["reasons"] = reason_list;
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = accepted ? actual_layers : 0;
    result["baseline_identity"] = bl0 && exact_identity;
    result["authority_complete"] = authority_complete;
    result["stage_publish_receipt"] = stage_publish_receipt;
    result["quality_profile_id"] = quality_profile_id;
    result["candidate_immutable"] = true;
    result["runtime_route"] = "default_off";
    return result;
}
}  // namespace


bool validate_capsule_origins(const py::dict& origins, std::vector<std::string>& reasons) {
    std::set<std::string> allowed;
    for (const auto key : semantic_fields) allowed.emplace(key);
    for (const auto key : digest_fields) allowed.emplace(key);
    for (const auto key : witness_fields) allowed.emplace(key);
    allowed.emplace("quality_profile_id");
    for (const auto item : origins) {
        if (!py::isinstance<py::str>(item.first)) {
            reasons.push_back("origin_key_invalid");
            continue;
        }
        const std::string key = item.first.cast<std::string>();
        if (!allowed.contains(key)) {
            reasons.push_back("origin_unknown:" + key);
            continue;
        }
        if (!non_empty_string(item.second) || item.second.cast<std::string>() != "direct") {
            reasons.push_back("origin_not_direct:" + key);
        }
    }
    for (const std::string& key : allowed) {
        if (!origins.contains(key.c_str())) reasons.push_back("origin_missing:" + key);
    }
    return reasons.empty();
}

void validate_capsule_topology(const py::dict& topology, std::vector<std::string>& reasons) {
    validate_topology(topology, reasons);
    if (!topology.contains("negative_measure")) {
        reasons.push_back("topology_missing:negative_measure");
        return;
    }
    try {
        if (topology["negative_measure"].cast<std::int64_t>() != 0) {
            reasons.push_back("topology_nonzero:negative_measure");
        }
    } catch (const py::cast_error&) {
        reasons.push_back("topology_invalid:negative_measure");
    }
}

py::dict normalize_bl0_identity_capsule_v1(
    const py::dict& baseline, const py::dict& candidate,
    std::int64_t requested_layers, std::int64_t actual_layers,
    const py::dict& topology, const py::dict& field_origins,
    const py::object& authority_state) {
    std::vector<std::string> record_reasons;
    validate_record(baseline, record_reasons);
    validate_record(candidate, record_reasons);
    std::vector<std::string> identity_reasons = record_reasons;
    validate_capsule_topology(topology, identity_reasons);
    if (requested_layers != 0 || actual_layers != 0) {
        identity_reasons.push_back("bl0_layer_state_mismatch");
    }
    if (!candidate.contains("mode") || !non_empty_string(candidate["mode"]) ||
        candidate["mode"].cast<std::string>() != "disabled_identity") {
        identity_reasons.push_back("bl0_mode_not_identity");
    }
    if (!exact_record_equal(baseline, candidate)) {
        identity_reasons.push_back("bl0_baseline_identity_mismatch");
    }
    const bool identity_exact = identity_reasons.empty();

    std::vector<std::string> authority_reasons;
    validate_capsule_origins(field_origins, authority_reasons);
    std::string state = "unverified";
    if (!py::isinstance<py::str>(authority_state)) {
        authority_reasons.push_back("authority_state_invalid");
    } else {
        state = authority_state.cast<std::string>();
        if (state != "source_verified") authority_reasons.push_back("authority_state_not_source_verified");
    }
    const bool authority_verified = authority_reasons.empty();
    std::vector<std::string> reasons = identity_reasons;
    reasons.insert(reasons.end(), authority_reasons.begin(), authority_reasons.end());
    const bool accepted = identity_exact && authority_verified;
    py::list reason_list;
    for (const std::string& reason : reasons) reason_list.append(reason);
    py::dict result;
    result["accepted"] = accepted;
    result["identity_exact"] = identity_exact;
    result["authority_state"] = state;
    result["publication_eligible"] = false;
    result["status"] = accepted ? "identity_capsule_ready"
        : (identity_exact ? "evidence_incomplete" : "identity_mismatch");
    result["reason"] = accepted ? "direct_source_verified_identity"
                                : "identity_or_authority_gate_failed";
    result["reasons"] = reason_list;
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = 0;
    result["candidate_immutable"] = true;
    result["runtime_route"] = "default_off";
    return result;
}


constexpr std::array<std::string_view, 7> matrix_products{
    "tet", "hex", "poly", "tri", "strict_quad", "tri_plus_quad", "surface"};

bool matrix_product_valid(const std::string& value) {
    return std::find(matrix_products.begin(), matrix_products.end(), value) != matrix_products.end();
}

bool matrix_get_string(const py::dict& row, const char* key, std::string& value) {
    if (!row.contains(key) || !non_empty_string(row[key])) return false;
    value = row[key].cast<std::string>();
    return true;
}

bool matrix_get_bool(const py::dict& row, const char* key, bool& value) {
    if (!row.contains(key)) return false;
    try {
        value = row[key].cast<bool>();
        return true;
    } catch (const py::cast_error&) {
        return false;
    }
}

bool matrix_get_layers(const py::dict& boundary_layer,
                       std::int64_t& requested, std::int64_t& actual,
                       std::string& mode) {
    if (!boundary_layer.contains("requested_layers") ||
        !boundary_layer.contains("actual_layers") ||
        !boundary_layer.contains("mode") ||
        !non_empty_string(boundary_layer["mode"])) return false;
    try {
        requested = boundary_layer["requested_layers"].cast<std::int64_t>();
        actual = boundary_layer["actual_layers"].cast<std::int64_t>();
        mode = boundary_layer["mode"].cast<std::string>();
        return true;
    } catch (const py::cast_error&) {
        return false;
    }
}

bool matrix_topology_zero(const py::dict& topology, std::vector<std::string>& reasons) {
    bool zero = true;
    for (const auto key : std::array<std::string_view, 6>{
             "invalid", "inverted", "duplicate", "non_manifold",
             "self_intersecting", "negative_measure"}) {
        const std::string name(key);
        if (!topology.contains(name.c_str())) {
            reasons.push_back("topology_missing:" + name);
            zero = false;
            continue;
        }
        try {
            if (topology[name.c_str()].cast<std::int64_t>() != 0) {
                reasons.push_back("topology_nonzero:" + name);
                zero = false;
            }
        } catch (const py::cast_error&) {
            reasons.push_back("topology_invalid:" + name);
            zero = false;
        }
    }
    return zero;
}

py::dict evaluate_route_evidence_matrix_v1(const py::list& rows) {
    py::list reports;
    std::map<std::string, std::int64_t> counts;
    for (py::ssize_t index = 0; index < static_cast<py::ssize_t>(rows.size()); ++index) {
        std::vector<std::string> reasons;
        std::string classification = "incomplete";
        std::string product;
        std::string engine;
        std::int64_t requested = 0;
        std::int64_t actual = 0;
        bool product_ok = matrix_get_string(
            py::isinstance<py::dict>(rows[index])
                ? py::reinterpret_borrow<py::dict>(rows[index]) : py::dict(), "product", product);
        py::dict row = py::isinstance<py::dict>(rows[index])
            ? py::reinterpret_borrow<py::dict>(rows[index]) : py::dict();
        if (!py::isinstance<py::dict>(rows[index])) {
            reasons.push_back("row_type_invalid");
            classification = "conflict";
        } else if (!product_ok || !matrix_product_valid(product)) {
            reasons.push_back("product_unknown_or_alias");
            classification = "conflict";
        } else if (!matrix_get_string(row, "engine", engine)) {
            reasons.push_back("engine_missing");
        }
        std::string evidence_status;
        if (classification != "conflict" && !matrix_get_string(row, "evidence_status", evidence_status)) {
            reasons.push_back("evidence_status_missing");
        }
        if (classification != "conflict" && evidence_status == "absent") {
            classification = "absent";
            reasons.push_back("evidence_absent");
        } else if (classification != "conflict" &&
                   evidence_status != "observed" && evidence_status != "present") {
            reasons.push_back("evidence_status_invalid");
            classification = "conflict";
        }

        py::dict boundary_layer;
        std::string mode;
        bool layers_ok = false;
        if (classification != "absent" && classification != "conflict") {
            if (!row.contains("boundary_layer") ||
                !py::isinstance<py::dict>(row["boundary_layer"])) {
                reasons.push_back("boundary_layer_missing");
            } else {
                boundary_layer = row["boundary_layer"].cast<py::dict>();
                layers_ok = matrix_get_layers(boundary_layer, requested, actual, mode);
                if (!layers_ok) reasons.push_back("boundary_layer_invalid");
            }
        }
        bool identity_exact = false;
        bool origins_complete = false;
        bool quality_accepted = false;
        bool stage_receipt = false;
        std::string authority_state;
        std::string profile;
        py::dict topology;
        bool topology_ok = false;
        if (classification != "absent" && classification != "conflict") {
            if (!matrix_get_bool(row, "identity_exact", identity_exact)) reasons.push_back("identity_exact_missing");
            if (!matrix_get_bool(row, "field_origins_complete", origins_complete)) reasons.push_back("field_origins_complete_missing");
            if (!matrix_get_bool(row, "quality_accepted", quality_accepted)) reasons.push_back("quality_accepted_missing");
            if (!matrix_get_bool(row, "stage_publish_receipt", stage_receipt)) reasons.push_back("stage_publish_receipt_missing");
            if (!matrix_get_string(row, "authority_state", authority_state)) reasons.push_back("authority_state_missing");
            if (!matrix_get_string(row, "quality_profile_id", profile)) reasons.push_back("quality_profile_missing");
            if (!row.contains("topology") || !py::isinstance<py::dict>(row["topology"])) {
                reasons.push_back("topology_missing");
            } else {
                topology = row["topology"].cast<py::dict>();
                topology_ok = matrix_topology_zero(topology, reasons);
            }
        }
        if (classification != "absent" && classification != "conflict" &&
            layers_ok && requested < 0) {
            reasons.push_back("layer_count_negative");
            classification = "conflict";
        }
        if (classification != "absent" && classification != "conflict" &&
            layers_ok && requested == 0) {
            if (actual != 0 || mode != "disabled_identity") {
                reasons.push_back("bl0_state_conflict");
                classification = "conflict";
            } else if (!reasons.empty() || !identity_exact || !topology_ok) {
                classification = "incomplete";
            } else if (authority_state == "source_verified" && origins_complete) {
                classification = "complete";
            } else {
                classification = "bl0_exact_unreleased";
                reasons.push_back("bl0_source_authority_incomplete");
            }
        } else if (classification != "absent" && classification != "conflict" &&
                   layers_ok && requested > 0) {
            if (actual != requested || mode == "disabled_identity") {
                reasons.push_back("positive_bl_state_conflict");
                classification = "conflict";
            } else if (!reasons.empty() || !topology_ok) {
                classification = "incomplete";
            } else if (!quality_accepted || profile.empty()) {
                classification = "incomplete";
                reasons.push_back("positive_quality_evidence_incomplete");
            } else if (authority_state != "source_verified" || !origins_complete || !stage_receipt) {
                classification = "positive_evidence_observed_unreleased";
                reasons.push_back("positive_source_or_publish_authority_unavailable");
            } else {
                classification = "positive_evidence_observed_unreleased";
                reasons.push_back("positive_release_suppressed");
            }
        } else if (classification != "absent" && classification != "conflict") {
            if (!layers_ok) {
                classification = "incomplete";
            } else {
                reasons.push_back("layer_state_invalid");
                classification = "conflict";
            }
        }
        counts[classification] += 1;
        py::list reason_list;
        for (const std::string& reason : reasons) reason_list.append(reason);
        py::dict report;
        report["row_index"] = index;
        report["product"] = product;
        report["engine"] = engine;
        report["classification"] = classification;
        report["reasons"] = reason_list;
        report["requested_layers"] = requested;
        report["actual_layers"] = actual;
        report["publication_eligible"] = false;
        report["runtime_route"] = "default_off";
        reports.append(report);
    }
    py::dict count_dict;
    for (const auto& [name, count] : counts) count_dict[name.c_str()] = count;
    py::dict result;
    result["status"] = rows.empty() ? "matrix_empty" : "matrix_observed";
    result["rows"] = reports;
    result["counts"] = count_dict;
    result["publication_eligible"] = false;
    result["runtime_route"] = "default_off";
    result["route_calls"] = 0;
    return result;
}

PYBIND11_MODULE(native_bl_identity, module) {
    module.doc() = "C++23 fail-closed BL identity and atomic publish eligibility witness";
    module.def("evaluate_bl_identity_record", &evaluate_bl_identity_record,
        py::arg("baseline"), py::arg("candidate"), py::arg("requested_layers"),
        py::arg("actual_layers"), py::arg("topology"), py::arg("quality"),
        py::arg("authority_complete"), py::arg("stage_publish_receipt"),
        py::arg("quality_profile_id"));
    module.def("evaluate_route_evidence_matrix_v1",
        &evaluate_route_evidence_matrix_v1, py::arg("rows"));
    module.def("normalize_bl0_identity_capsule_v1",
        &normalize_bl0_identity_capsule_v1,
        py::arg("baseline"), py::arg("candidate"),
        py::arg("requested_layers"), py::arg("actual_layers"),
        py::arg("topology"), py::arg("field_origins"),
        py::arg("authority_state"));
}
