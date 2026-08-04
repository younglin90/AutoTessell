#include "native_transaction_intent_v1.hpp"

#include <pybind11/stl.h>

#include <algorithm>
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

namespace native_transaction_intent {
namespace {

std::string canonical(const py::handle& value) {
    if (value.is_none()) return "null;";
    if (py::isinstance<py::bool_>(value)) return value.cast<bool>() ? "bool:1;" : "bool:0;";
    if (py::isinstance<py::int_>(value)) return "int:" + std::to_string(value.cast<long long>()) + ";";
    if (py::isinstance<py::float_>(value)) {
        const double number = value.cast<double>();
        if (!std::isfinite(number)) throw std::invalid_argument("intent_parameter_nonfinite");
        std::ostringstream stream;
        stream << "float:" << std::setprecision(std::numeric_limits<double>::max_digits10) << number << ";";
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
    throw std::invalid_argument("intent_parameter_type_invalid");
}

std::string sha(const std::string& bytes) {
    return brep_evidence::sha256_hex(std::vector<std::uint8_t>(bytes.begin(), bytes.end()));
}

bool hex64(const py::handle& value) {
    if (!py::isinstance<py::str>(value)) return false;
    const auto text = value.cast<std::string>();
    return text.size() == 64U && std::all_of(text.begin(), text.end(), [](char item) {
        return (item >= '0' && item <= '9') || (item >= 'a' && item <= 'f') || (item >= 'A' && item <= 'F');
    });
}

py::dict refuse(const char* reason) {
    py::dict out;
    out["accepted"] = false;
    out["schema"] = "autotessell/native-transaction-intent/v1";
    out["status"] = "native_transaction_intent_refused";
    out["reason"] = reason;
    out["generated_entity_count"] = 0;
    out["writer_calls"] = 0;
    out["candidate_discarded"] = true;
    out["rollback_required"] = true;
    return out;
}

bool string_value(const py::dict& value, const char* key, std::string& result, bool nonempty = true) {
    if (!value.contains(key) || !py::isinstance<py::str>(value[key])) return false;
    result = value[key].cast<std::string>();
    return !nonempty || !result.empty();
}

bool bool_value(const py::dict& value, const char* key, bool& result) {
    if (!value.contains(key) || !py::isinstance<py::bool_>(value[key])) return false;
    result = value[key].cast<bool>();
    return true;
}

py::dict without_key(const py::dict& source, const char* excluded) {
    py::dict result;
    for (const auto item : source) if (py::cast<std::string>(item.first) != excluded) result[item.first] = item.second;
    return result;
}

bool valid_declared_value(const py::dict& parameter, std::string& reason) {
    std::string type;
    bool explicit_value = false;
    if (!string_value(parameter, "type", type) || !bool_value(parameter, "explicit", explicit_value)) { reason = "intent_parameter_type_invalid"; return false; }
    if (!explicit_value) { reason = "intent_request_schema_missing"; return false; }
    if (!parameter.contains("value")) { reason = "intent_request_schema_missing"; return false; }
    const auto value = parameter["value"];
    if (type == "null") {
        if (!value.is_none()) { reason = "intent_parameter_type_invalid"; return false; }
    } else if (type == "boolean") {
        if (!py::isinstance<py::bool_>(value)) { reason = "intent_parameter_type_invalid"; return false; }
    } else if (type == "integer") {
        if (!py::isinstance<py::int_>(value) || py::isinstance<py::bool_>(value)) { reason = "intent_parameter_type_invalid"; return false; }
    } else if (type == "number") {
        if ((!py::isinstance<py::float_>(value) && !py::isinstance<py::int_>(value)) || py::isinstance<py::bool_>(value) || !std::isfinite(value.cast<double>())) { reason = "intent_parameter_nonfinite"; return false; }
    } else if (type == "string") {
        if (!py::isinstance<py::str>(value)) { reason = "intent_parameter_type_invalid"; return false; }
    } else if (type == "array") {
        if (!py::isinstance<py::list>(value) && !py::isinstance<py::tuple>(value)) { reason = "intent_parameter_type_invalid"; return false; }
    } else {
        reason = "intent_parameter_type_invalid";
        return false;
    }
    return true;
}

bool authority_ok(const py::dict& ledger, std::string& reason) {
    bool accepted = false;
    if (!bool_value(ledger, "accepted", accepted) || !accepted) { reason = "intent_authority_ledger_missing"; return false; }
    for (const char* key : {"source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"})
        if (!ledger.contains(key) || !hex64(ledger[key])) { reason = "intent_source_semantic_writer_digest_missing"; return false; }
    std::string mode, root;
    if (!string_value(ledger, "source_mode", mode) || !string_value(ledger, "provenance_root", root)) { reason = "intent_authority_ledger_missing"; return false; }
    if (!ledger.contains("topology") || !py::isinstance<py::dict>(ledger["topology"])) { reason = "intent_authority_ledger_missing"; return false; }
    const auto topology = ledger["topology"].cast<py::dict>();
    for (const char* key : {"duplicate", "non_manifold", "inverted"}) {
        if (!topology.contains(key) || py::isinstance<py::bool_>(topology[key]) || topology[key].cast<long long>() != 0) { reason = "intent_authority_ledger_missing"; return false; }
    }
    if (!ledger.contains("lineage_rows") || !py::isinstance<py::list>(ledger["lineage_rows"]) || ledger["lineage_rows"].cast<py::list>().empty()) { reason = "intent_feature_patch_group_component_missing"; return false; }
    for (const auto item : ledger["lineage_rows"].cast<py::list>()) {
        if (!py::isinstance<py::dict>(item)) { reason = "intent_feature_patch_group_component_missing"; return false; }
        const auto row = item.cast<py::dict>();
        for (const char* key : {"entity_id", "feature", "patch", "physical_group", "component", "provenance"}) {
            std::string value;
            if (!string_value(row, key, value)) { reason = "intent_feature_patch_group_component_missing"; return false; }
        }
    }
    return true;
}

bool quality_ok(const py::dict& quality, long long& layers, std::string& reason) {
    bool accepted = false;
    if (!bool_value(quality, "accepted", accepted) || !accepted || !quality.contains("policy_sha256") || !hex64(quality["policy_sha256"]) ||
        !quality.contains("policy") || !py::isinstance<py::dict>(quality["policy"])) { reason = "intent_quality_contract_missing"; return false; }
    const auto policy = quality["policy"].cast<py::dict>();
    if (!policy.contains("boundary_layer_count") || py::isinstance<py::bool_>(policy["boundary_layer_count"])) { reason = "intent_quality_contract_missing"; return false; }
    try { layers = policy["boundary_layer_count"].cast<long long>(); } catch (...) { reason = "intent_quality_contract_missing"; return false; }
    if (layers < 0) { reason = "intent_quality_contract_missing"; return false; }
    return true;
}

bool corridor_ok(const py::object& object, long long layers, std::string& reason) {
    if (layers == 0 && object.is_none()) return true;
    if (!py::isinstance<py::dict>(object)) { reason = "intent_positive_bl_corridor_missing"; return false; }
    const auto receipt = object.cast<py::dict>();
    bool accepted = false;
    if (!bool_value(receipt, "accepted", accepted) || !accepted || !receipt.contains("receipt_sha256") || !hex64(receipt["receipt_sha256"])) { reason = "intent_positive_bl_corridor_missing"; return false; }
    long long actual = -1;
    try { actual = receipt["actual_layers"].cast<long long>(); } catch (...) { reason = "intent_layer_schedule_inconsistent"; return false; }
    if (actual != layers) { reason = "intent_layer_schedule_inconsistent"; return false; }
    if (layers > 0) {
        bool spd = false;
        if (!bool_value(receipt, "metric_spd", spd) || !spd || !receipt.contains("edges") || !py::isinstance<py::list>(receipt["edges"]) || receipt["edges"].cast<py::list>().empty()) { reason = "intent_positive_bl_corridor_missing"; return false; }
    }
    return true;
}

}  // namespace

py::dict canonical_sha256_v1(const py::dict& value) {
    try {
        const auto bytes = canonical(value);
        py::dict out;
        out["accepted"] = true;
        out["canonical_bytes"] = bytes;
        out["sha256"] = sha(bytes);
        return out;
    } catch (const std::exception&) { return refuse("intent_parameter_type_invalid"); }
}

py::dict authorize_native_transaction_v1(const py::dict& authority_ledger, const py::dict& raw_request,
                                         const py::dict& engine_manifest, const py::dict& quality_policy_v3,
                                         const py::object& corridor_receipt) {
    try {
        std::string reason;
        if (!authority_ok(authority_ledger, reason)) return refuse(reason.c_str());
        if (!raw_request.contains("request_sha256") || !hex64(raw_request["request_sha256"])) return refuse("intent_request_schema_missing");
        std::string request_digest;
        try { request_digest = sha(canonical(without_key(raw_request, "request_sha256"))); }
        catch (const std::invalid_argument& error) { return refuse(std::string(error.what()) == "intent_parameter_nonfinite" ? "intent_parameter_nonfinite" : "intent_request_schema_missing"); }
        std::string schema, engine, product, ui_schema, control_schema;
        if (!string_value(raw_request, "schema", schema) || schema != "autotessell/native-request/v1" ||
            !string_value(raw_request, "engine", engine) || !string_value(raw_request, "product", product) ||
            !string_value(raw_request, "ui_schema_version", ui_schema) || !string_value(raw_request, "control_schema_version", control_schema) || engine != product) return refuse("intent_engine_or_product_unknown");
        const std::set<std::string> products = {"native_tet", "native_hex", "native_poly", "native_tri", "strict_quad", "tri_quad", "surface_mesher"};
        if (!products.contains(engine)) return refuse("intent_engine_or_product_unknown");
        if (!raw_request.contains("parameters") || !py::isinstance<py::list>(raw_request["parameters"])) return refuse("intent_request_schema_missing");
        std::map<std::string, py::dict> parameters;
        for (const auto item : raw_request["parameters"].cast<py::list>()) {
            if (!py::isinstance<py::dict>(item)) return refuse("intent_parameter_type_invalid");
            const auto parameter = item.cast<py::dict>();
            std::string id, control;
            if (!string_value(parameter, "parameter_id", id) || !string_value(parameter, "control_id", control) || !parameters.emplace(id, parameter).second) return refuse("intent_duplicate_parameter");
            if (!valid_declared_value(parameter, reason)) return refuse(reason.c_str());
        }
        if (parameters.empty()) return refuse("intent_request_schema_missing");

        if (!engine_manifest.contains("manifest_sha256") || !hex64(engine_manifest["manifest_sha256"]) ||
            sha(canonical(without_key(engine_manifest, "manifest_sha256"))) != engine_manifest["manifest_sha256"].cast<std::string>()) return refuse("intent_writer_manifest_digest_mismatch");
        std::string manifest_schema, manifest_engine, manifest_product, build_sha;
        if (!string_value(engine_manifest, "schema", manifest_schema) || manifest_schema != "autotessell/native-writer-manifest/v1" ||
            !string_value(engine_manifest, "engine", manifest_engine) || !string_value(engine_manifest, "product", manifest_product) ||
            !string_value(engine_manifest, "writer_build_sha256", build_sha) || !hex64(py::str(build_sha)) || manifest_engine != engine || manifest_product != product ||
            !engine_manifest.contains("sinks") || !py::isinstance<py::list>(engine_manifest["sinks"])) return refuse("intent_writer_manifest_missing");
        struct Sink { bool applicable = false; std::string sink, role, stage, reason; py::dict row; };
        std::map<std::string, Sink> sinks;
        const std::set<std::string> allowed_sinks = {"source_authority", "surface_metric", "volume_metric", "bl_schedule", "wall_edge_sector", "feature_protection", "topology_transaction", "quality_gate", "count_tuning", "seed_replay", "output_provenance"};
        for (const auto item : engine_manifest["sinks"].cast<py::list>()) {
            if (!py::isinstance<py::dict>(item)) return refuse("intent_writer_manifest_missing");
            const auto row = item.cast<py::dict>();
            std::string id;
            bool applicable = false;
            if (!string_value(row, "parameter_id", id) || !bool_value(row, "applicable", applicable) || !sinks.emplace(id, Sink{}).second) return refuse("intent_parameter_sink_ambiguous");
            auto& sink = sinks[id]; sink.applicable = applicable; sink.row = row;
            if (applicable) {
                if (!string_value(row, "primary_sink", sink.sink) || !allowed_sinks.contains(sink.sink) || !string_value(row, "semantic_role", sink.role) || !string_value(row, "writer_stage", sink.stage)) return refuse("intent_parameter_sink_ambiguous");
            } else if (!string_value(row, "inapplicable_reason", sink.reason)) return refuse("intent_parameter_not_applicable_unexplained");
        }
        if (sinks.size() != parameters.size()) return refuse("intent_unknown_parameter");
        for (const auto& [id, parameter] : parameters) if (!sinks.contains(id)) return refuse("intent_parameter_unconsumed");
        long long layers = 0;
        if (!quality_ok(quality_policy_v3, layers, reason)) return refuse(reason.c_str());
        if (!corridor_ok(corridor_receipt, layers, reason)) return refuse(reason.c_str());

        py::dict out;
        out["accepted"] = true; out["schema"] = "autotessell/native-transaction-intent/v1"; out["status"] = "native_transaction_intent_armed";
        out["engine"] = engine; out["product"] = product; out["ui_schema_version"] = ui_schema; out["control_schema_version"] = control_schema;
        out["request_sha256"] = raw_request["request_sha256"]; out["manifest_sha256"] = engine_manifest["manifest_sha256"];
        out["writer_build_sha256"] = build_sha; out["quality_policy_v3_sha256"] = quality_policy_v3["policy_sha256"];
        for (const char* key : {"source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"}) out[key] = authority_ledger[key];
        if (!corridor_receipt.is_none()) out["corridor_receipt_sha256"] = corridor_receipt.cast<py::dict>()["receipt_sha256"];
        else out["corridor_receipt_sha256"] = py::none();
        py::list sink_rows, effective_values;
        long long applicable_count = 0;
        for (const auto& [id, sink] : sinks) {
            py::dict row = sink.row; row["parameter_id"] = id; sink_rows.append(row);
            py::dict effective = parameters.at(id); effective_values.append(effective);
            if (sink.applicable) ++applicable_count;
        }
        out["sink_rows"] = sink_rows; out["effective_values"] = effective_values;
        out["parameter_count"] = static_cast<long long>(parameters.size()); out["applicable_parameter_count"] = applicable_count;
        out["boundary_layer_count"] = layers; out["quality_precedes_count"] = true; out["count_gate"] = "secondary_after_quality_topology_authority";
        out["generated_entity_count"] = 0; out["writer_calls"] = 0; out["candidate_discarded"] = false; out["rollback_required"] = false;
        out["rollback_token_state"] = "armed";
        out["coverage_sha256"] = sha(canonical(sink_rows));
        out["rollback_token_sha256"] = sha(out["coverage_sha256"].cast<std::string>() + "|single-use");
        out["receipt_sha256"] = sha(canonical(out));
        return out;
    } catch (const std::exception&) { return refuse("intent_parameter_type_invalid"); }
}

py::dict rollback_transaction_intent_v1(const py::dict& intent, const std::string& reason) {
    if (reason.empty() || !intent.contains("accepted") || !intent["accepted"].cast<bool>() || !intent.contains("rollback_token_state") || intent["rollback_token_state"].cast<std::string>() != "armed" || !hex64(intent["rollback_token_sha256"])) return refuse("intent_candidate_disk_intent_mismatch");
    py::dict out; out["accepted"] = true; out["schema"] = "autotessell/native-transaction-intent/v1"; out["status"] = "native_transaction_intent_rolled_back";
    out["intent_receipt_sha256"] = intent["receipt_sha256"]; out["rollback_reason"] = reason; out["rollback_token_state"] = "consumed";
    out["generated_entity_count"] = 0; out["writer_calls"] = 0; out["candidate_discarded"] = true; out["rollback_required"] = false;
    return out;
}

}  // namespace native_transaction_intent
