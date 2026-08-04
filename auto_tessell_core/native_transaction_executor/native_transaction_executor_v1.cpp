#include "native_transaction_executor_v1.hpp"

#include <pybind11/stl.h>

#include <algorithm>
#include <cmath>
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

namespace native_transaction_executor {
namespace {

std::set<std::string> g_used_intents;

std::string canonical(const py::handle& value) {
    if (value.is_none()) return "null;";
    if (py::isinstance<py::bool_>(value)) return value.cast<bool>() ? "bool:1;" : "bool:0;";
    if (py::isinstance<py::int_>(value)) return "int:" + std::to_string(value.cast<long long>()) + ";";
    if (py::isinstance<py::float_>(value)) {
        const double number = value.cast<double>();
        if (!std::isfinite(number)) throw std::invalid_argument("executor_quality_threshold_exceeded");
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
    throw std::invalid_argument("executor_candidate_receipt_missing");
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

py::dict without_key(const py::dict& source, const char* excluded) {
    py::dict result;
    for (const auto item : source) if (py::cast<std::string>(item.first) != excluded) result[item.first] = item.second;
    return result;
}

std::string artifact_digest(const py::dict& value) {
    auto normalized = without_key(value, "artifact_sha256");
    if (normalized.contains("writer_stage")) normalized["writer_stage"] = "normalized_artifact";
    return sha(canonical(normalized));
}

py::dict refuse(const char* reason) {
    py::dict out;
    out["accepted"] = false; out["schema"] = "autotessell/native-transaction-executor/v1";
    out["status"] = "native_transaction_executor_refused"; out["reason"] = reason;
    out["published"] = false; out["candidate_discarded"] = true; out["rollback_required"] = true;
    out["generated_entity_count"] = 0; out["writer_calls"] = 0; out["journal_sha256"] = sha(reason);
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

bool zero_topology(const py::dict& value) {
    if (!value.contains("topology") || !py::isinstance<py::dict>(value["topology"])) return false;
    const auto topology = value["topology"].cast<py::dict>();
    for (const char* key : {"duplicate", "non_manifold", "inverted"}) {
        if (!topology.contains(key) || py::isinstance<py::bool_>(topology[key]) || topology[key].cast<long long>() != 0) return false;
    }
    return true;
}

bool authority_fields_match(const py::dict& left, const py::dict& right) {
    for (const char* key : {"source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"}) {
        if (!left.contains(key) || !right.contains(key) || !hex64(left[key]) || left[key].cast<std::string>() != right[key].cast<std::string>()) return false;
    }
    return true;
}

void journalize(py::dict& state) {
    state["journal_sha256"] = sha(canonical(without_key(state, "journal_sha256")));
}

bool valid_lineage(const py::dict& candidate, const std::vector<std::string>& uids) {
    if (!candidate.contains("lineage_rows") || !py::isinstance<py::list>(candidate["lineage_rows"])) return false;
    const auto rows = candidate["lineage_rows"].cast<py::list>();
    if (static_cast<std::size_t>(rows.size()) != uids.size()) return false;
    std::set<std::string> seen;
    for (const auto item : rows) {
        if (!py::isinstance<py::dict>(item)) return false;
        const auto row = item.cast<py::dict>();
        std::string uid;
        if (!string_value(row, "entity_uid", uid) || !std::binary_search(uids.begin(), uids.end(), uid) || !seen.insert(uid).second) return false;
        for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) {
            std::string ignored;
            if (!string_value(row, key, ignored)) return false;
        }
    }
    return seen.size() == uids.size();
}

bool valid_candidate(const py::dict& transaction, const py::dict& candidate, std::string& reason) {
    std::string state, intent_sha, stage, writer_build;
    bool accepted = false, published = true, lineage_complete = false;
    if (!string_value(transaction, "transaction_state", state) || state != "staging") { reason = "executor_capability_reused"; return false; }
    if (!bool_value(candidate, "accepted", accepted) || !accepted || !bool_value(candidate, "published", published) || published ||
        !string_value(candidate, "writer_stage", stage) || (stage != "staged_candidate" && stage != "disk_reread") ||
        !string_value(candidate, "intent_receipt_sha256", intent_sha) || intent_sha != transaction["intent_receipt_sha256"].cast<std::string>() ||
        !string_value(candidate, "writer_build_sha256", writer_build) || writer_build != transaction["writer_build_sha256"].cast<std::string>() ||
        !bool_value(candidate, "source_feature_patch_group_component_provenance_complete", lineage_complete) || !lineage_complete) { reason = "executor_writer_manifest_mismatch"; return false; }
    if (!authority_fields_match(transaction, candidate) || !candidate.contains("policy_sha256") || candidate["policy_sha256"].cast<std::string>() != transaction["quality_policy_v3_sha256"].cast<std::string>()) { reason = "executor_source_authority_lost"; return false; }
    if (transaction["corridor_receipt_sha256"].is_none()) {
        if (candidate.contains("corridor_receipt_sha256") && !candidate["corridor_receipt_sha256"].is_none()) { reason = "executor_positive_bl_corridor_missing"; return false; }
    } else if (!candidate.contains("corridor_receipt_sha256") || candidate["corridor_receipt_sha256"].cast<std::string>() != transaction["corridor_receipt_sha256"].cast<std::string>()) { reason = "executor_positive_bl_corridor_missing"; return false; }
    if (!zero_topology(candidate)) { reason = "executor_topology_invalid"; return false; }
    if (!candidate.contains("entity_uids") || !py::isinstance<py::list>(candidate["entity_uids"])) { reason = "executor_provenance_or_uid_lost"; return false; }
    std::vector<std::string> uids;
    try { uids = candidate["entity_uids"].cast<std::vector<std::string>>(); } catch (...) { reason = "executor_provenance_or_uid_lost"; return false; }
    if (uids.empty() || !std::all_of(uids.begin(), uids.end(), [](const std::string& uid) { return !uid.empty(); }) || std::adjacent_find(uids.begin(), uids.end()) != uids.end()) { reason = "executor_provenance_or_uid_lost"; return false; }
    std::sort(uids.begin(), uids.end());
    if (!valid_lineage(candidate, uids)) { reason = "executor_feature_patch_group_component_lost"; return false; }
    if (!candidate.contains("quality") || !py::isinstance<py::dict>(candidate["quality"])) { reason = "executor_candidate_receipt_missing"; return false; }
    const auto quality = candidate["quality"].cast<py::dict>();
    bool quality_accepted = false;
    std::string family;
    if (!bool_value(quality, "accepted", quality_accepted) || !quality_accepted || !string_value(quality, "aspect_family", family) ||
        !std::set<std::string>{"tet_dihedral", "hex_scaled_jacobian", "poly_star_face", "tri_metric_angle", "quad_scaled_jacobian_warpage", "bl_metric_distortion"}.contains(family)) { reason = "executor_candidate_receipt_missing"; return false; }
    for (const char* key : {"signed_non_orthogonality_max", "skewness_max", "aspect_ratio_max", "positive_measure_min"}) {
        if (!quality.contains(key) || py::isinstance<py::bool_>(quality[key]) || !std::isfinite(quality[key].cast<double>())) { reason = "executor_quality_threshold_exceeded"; return false; }
    }
    const long long layers = transaction["boundary_layer_count"].cast<long long>();
    if (!candidate.contains("boundary_layer") || !py::isinstance<py::dict>(candidate["boundary_layer"])) { reason = "executor_bl_requested_actual_mismatch"; return false; }
    const auto boundary = candidate["boundary_layer"].cast<py::dict>();
    long long actual = -1, work = -1;
    try { actual = boundary["actual_layers"].cast<long long>(); work = boundary["layer_work"].cast<long long>(); } catch (...) { reason = "executor_bl_requested_actual_mismatch"; return false; }
    if (layers == 0) {
        if (actual != 0 || work != 0 || !boundary.contains("rows") || !py::isinstance<py::list>(boundary["rows"]) || !boundary["rows"].cast<py::list>().empty()) { reason = "executor_bl0_layer_work_detected"; return false; }
    } else {
        if (actual != layers || work <= 0 || !boundary.contains("positive_measure") || !boundary["positive_measure"].cast<bool>() || !boundary.contains("rows") || !py::isinstance<py::list>(boundary["rows"])) { reason = "executor_bl_sector_or_schedule_lost"; return false; }
        std::set<std::string> roles;
        for (const auto item : boundary["rows"].cast<py::list>()) if (py::isinstance<py::dict>(item) && item.cast<py::dict>().contains("role")) roles.insert(item.cast<py::dict>()["role"].cast<std::string>());
        if (!roles.contains("wall") || !roles.contains("front") || !roles.contains("side")) { reason = "executor_bl_sector_or_schedule_lost"; return false; }
    }
    bool topology_checked = false, quality_checked = false;
    if (!bool_value(candidate, "strict_topology_checked", topology_checked) || !topology_checked || !bool_value(candidate, "quality_checked", quality_checked) || !quality_checked) { reason = "executor_candidate_receipt_missing"; return false; }
    if (!candidate.contains("artifact_sha256") || !hex64(candidate["artifact_sha256"]) || artifact_digest(candidate) != candidate["artifact_sha256"].cast<std::string>()) { reason = "executor_candidate_receipt_missing"; return false; }
    return true;
}

}  // namespace

py::dict canonical_artifact_sha256_v1(const py::dict& value) {
    try { py::dict out; out["accepted"] = true; out["sha256"] = artifact_digest(value); return out; }
    catch (const std::exception&) { return refuse("executor_candidate_receipt_missing"); }
}

py::dict begin_transaction_v1(const py::dict& intent, const py::dict& authority_ledger, const py::object& corridor_receipt) {
    try {
        bool accepted = false;
        std::string schema, token_state, intent_sha;
        if (!bool_value(intent, "accepted", accepted) || !accepted || !string_value(intent, "schema", schema) || schema != "autotessell/native-transaction-intent/v1" ||
            !string_value(intent, "rollback_token_state", token_state) || token_state != "armed" || !string_value(intent, "receipt_sha256", intent_sha) || !hex64(intent["receipt_sha256"]) ||
            !authority_fields_match(intent, authority_ledger)) return refuse("executor_intent_not_armed");
        if (g_used_intents.contains(intent_sha)) return refuse("executor_capability_reused");
        long long layers = intent["boundary_layer_count"].cast<long long>();
        if (!authority_ledger.contains("accepted") || !authority_ledger["accepted"].cast<bool>() ||
            !zero_topology(authority_ledger) || !authority_ledger.contains("lineage_rows") ||
            !py::isinstance<py::list>(authority_ledger["lineage_rows"]) || authority_ledger["lineage_rows"].cast<py::list>().empty()) return refuse("executor_intent_not_armed");
        if (layers > 0) {
            if (corridor_receipt.is_none() || !py::isinstance<py::dict>(corridor_receipt)) return refuse("executor_positive_bl_corridor_missing");
            const auto corridor = corridor_receipt.cast<py::dict>();
            if (!corridor.contains("accepted") || !corridor["accepted"].cast<bool>() || !corridor.contains("actual_layers") || corridor["actual_layers"].cast<long long>() != layers ||
                !corridor.contains("receipt_sha256") || !hex64(corridor["receipt_sha256"]) || !intent.contains("corridor_receipt_sha256") || intent["corridor_receipt_sha256"].is_none() ||
                intent["corridor_receipt_sha256"].cast<std::string>() != corridor["receipt_sha256"].cast<std::string>()) return refuse("executor_positive_bl_corridor_missing");
        }
        g_used_intents.insert(intent_sha);
        py::dict out;
        out["accepted"] = true; out["schema"] = "autotessell/native-transaction-executor/v1"; out["transaction_state"] = "staging";
        out["intent_receipt_sha256"] = intent["receipt_sha256"]; out["writer_build_sha256"] = intent["writer_build_sha256"];
        out["quality_policy_v3_sha256"] = intent["quality_policy_v3_sha256"]; out["boundary_layer_count"] = layers;
        if (corridor_receipt.is_none()) out["corridor_receipt_sha256"] = py::none();
        else out["corridor_receipt_sha256"] = corridor_receipt.cast<py::dict>()["receipt_sha256"];
        for (const char* key : {"source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"}) out[key] = intent[key];
        out["transaction_id"] = sha(intent_sha + "|staging"); out["generated_entity_count"] = 0; out["writer_calls"] = 0; out["published"] = false;
        out["candidate_discarded"] = false; out["rollback_required"] = false; journalize(out); return out;
    } catch (const std::exception&) { return refuse("executor_intent_not_armed"); }
}

py::dict validate_candidate_v1(const py::dict& transaction, const py::dict& candidate) {
    try {
        std::string reason;
        if (!valid_candidate(transaction, candidate, reason)) return refuse(reason.c_str());
        py::dict out = transaction; out["transaction_state"] = "candidate_validated"; out["candidate"] = candidate;
        out["candidate_artifact_sha256"] = candidate["artifact_sha256"]; out["writer_calls"] = 1; out["generated_entity_count"] = candidate["entity_uids"].cast<py::list>().size(); journalize(out); return out;
    } catch (const std::exception&) { return refuse("executor_candidate_receipt_missing"); }
}

py::dict validate_disk_reread_v1(const py::dict& transaction, const py::dict& disk_reread) {
    try {
        if (!transaction.contains("transaction_state") || transaction["transaction_state"].cast<std::string>() != "candidate_validated" || !transaction.contains("candidate")) return refuse("executor_candidate_receipt_missing");
        const auto candidate = transaction["candidate"].cast<py::dict>();
        std::string reason;
        py::dict staging;
        staging["transaction_state"] = "staging";
        for (const char* key : {"intent_receipt_sha256", "writer_build_sha256", "quality_policy_v3_sha256", "boundary_layer_count", "corridor_receipt_sha256", "source_sha256", "semantic_sha256", "config_sha256", "writer_sha256"}) {
            if (!transaction.contains(key)) return refuse("executor_candidate_disk_mismatch");
            staging[key] = transaction[key];
        }
        if (!valid_candidate(staging, disk_reread, reason)) return refuse(reason.c_str());
        if (!disk_reread.contains("writer_stage") || disk_reread["writer_stage"].cast<std::string>() != "disk_reread" || disk_reread["artifact_sha256"].cast<std::string>() != candidate["artifact_sha256"].cast<std::string>()) return refuse("executor_candidate_disk_mismatch");
        py::dict out = transaction; out["transaction_state"] = "reread_validated"; out["disk_reread"] = disk_reread; out["disk_artifact_sha256"] = disk_reread["artifact_sha256"]; journalize(out); return out;
    } catch (const std::exception&) { return refuse("executor_candidate_disk_mismatch"); }
}

py::dict publish_transaction_v1(const py::dict& transaction) {
    if (!transaction.contains("transaction_state") || transaction["transaction_state"].cast<std::string>() != "reread_validated") return refuse("executor_publish_without_commit_token");
    py::dict out = transaction; out["transaction_state"] = "published"; out["published"] = true; out["rollback_required"] = false; out["publish_token_sha256"] = sha(transaction["transaction_id"].cast<std::string>() + "|publish"); journalize(out); return out;
}

py::dict rollback_transaction_v1(const py::dict& transaction, const std::string& reason) {
    if (reason.empty() || !transaction.contains("transaction_state")) return refuse("executor_journal_digest_mismatch");
    const auto state = transaction["transaction_state"].cast<std::string>();
    if (state == "published" || state == "rolled_back") return refuse("executor_capability_reused");
    py::dict out = transaction; out["transaction_state"] = "rolled_back"; out["published"] = false; out["candidate_discarded"] = true; out["rollback_required"] = false; out["rollback_reason"] = reason; journalize(out); return out;
}


py::dict run_writer_transaction_v1(
    const py::dict& transaction,
    const py::function& writer_callback,
    const py::function& reread_callback) {
    try {
        if (!transaction.contains("transaction_state") || transaction["transaction_state"].cast<std::string>() != "staging") return refuse("executor_capability_reused");
        py::object candidate_object = writer_callback(transaction);
        if (!py::isinstance<py::dict>(candidate_object)) return refuse("executor_writer_manifest_mismatch");
        const auto candidate = candidate_object.cast<py::dict>();
        py::dict staged = validate_candidate_v1(transaction, candidate);
        if (!staged["accepted"].cast<bool>()) return staged;
        py::object disk_object = reread_callback(staged);
        if (!py::isinstance<py::dict>(disk_object)) return refuse("executor_candidate_disk_mismatch");
        py::dict reread = validate_disk_reread_v1(staged, disk_object.cast<py::dict>());
        if (!reread["accepted"].cast<bool>()) return reread;
        return publish_transaction_v1(reread);
    } catch (const std::exception&) {
        py::dict rolled_back = rollback_transaction_v1(transaction, "executor_writer_callback_exception");
        return rolled_back["accepted"].cast<bool>() ? rolled_back : refuse("executor_writer_callback_exception");
    }
}
}  // namespace native_transaction_executor
