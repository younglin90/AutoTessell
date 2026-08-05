// C++23 Gate4 staged-tree and output-boundary 1:N lineage witness.
// JSON is an input/inspection envelope; the native canonical bytes and
// recomputed tree/boundary readback are the release-critical evidence.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iterator>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

namespace py = pybind11;
namespace fs = std::filesystem;

namespace {

struct Entry {
    std::string path;
    std::string kind;
    std::uintmax_t size{};
    std::string sha256;
};

struct Semantic {
    std::string kind;
    std::map<std::int64_t, std::map<std::string, std::string>> rows;
};

struct Record {
    std::string uid;
    std::string scope;
    std::string source_kind;
    std::int64_t source_id{};
    std::string owner;
    std::string operation;
    std::string role;
    std::int64_t layer{};
    std::string parent;
    bool has_parent = false;
    double positive_measure{};
    bool has_positive_measure = false;
    std::map<std::string, std::string> semantic;
};

std::string file_sha256(const fs::path& path, std::uintmax_t* size = nullptr) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) return {};
    std::vector<std::uint8_t> bytes(
        (std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
    if (size != nullptr) *size = bytes.size();
    return brep_evidence::sha256_hex(bytes);
}

std::string relative_path(const fs::path& root, const fs::path& path) {
    const fs::path relative = path.lexically_relative(root);
    if (relative.empty() || relative.is_absolute()) throw std::runtime_error("artifact_relative_path_invalid");
    for (const auto& component : relative) {
        if (component == fs::path("..")) throw std::runtime_error("artifact_root_escape");
    }
    return relative.generic_string();
}

std::vector<Entry> collect_tree(const fs::path& root) {
    std::error_code ec;
    const fs::file_status root_status = fs::symlink_status(root, ec);
    if (ec || !fs::is_directory(root_status)) throw std::runtime_error("artifact_root_not_directory");
    if (fs::is_symlink(root_status)) throw std::runtime_error("artifact_symlink_forbidden");
    std::vector<Entry> entries;
    fs::recursive_directory_iterator iterator(root, fs::directory_options::none, ec);
    if (ec) throw std::runtime_error("artifact_tree_open_failed");
    for (const fs::recursive_directory_iterator end; iterator != end; iterator.increment(ec)) {
        if (ec) throw std::runtime_error("artifact_tree_iterate_failed");
        const fs::path path = iterator->path();
        const fs::file_status status = iterator->symlink_status(ec);
        if (ec) throw std::runtime_error("artifact_status_failed");
        if (fs::is_symlink(status)) throw std::runtime_error("artifact_symlink_forbidden:" + relative_path(root, path));
        Entry entry;
        entry.path = relative_path(root, path);
        if (fs::is_directory(status)) {
            entry.kind = "directory";
            entry.sha256 = brep_evidence::sha256_hex({});
        } else if (fs::is_regular_file(status)) {
            entry.kind = "regular";
            entry.sha256 = file_sha256(path, &entry.size);
            if (entry.sha256.empty()) throw std::runtime_error("artifact_file_unreadable");
        } else {
            throw std::runtime_error("artifact_special_file_forbidden:" + entry.path);
        }
        entries.push_back(std::move(entry));
    }
    std::sort(entries.begin(), entries.end(), [](const Entry& a, const Entry& b) { return a.path < b.path; });
    return entries;
}

std::string tree_digest(const fs::path& root, std::size_t& count) {
    const auto entries = collect_tree(root);
    std::string canonical;
    for (const Entry& entry : entries) {
        canonical += entry.path + '\0' + entry.kind + '\0' + std::to_string(entry.size) + '\0' + entry.sha256 + '\n';
    }
    count = entries.size();
    const std::vector<std::uint8_t> bytes(canonical.begin(), canonical.end());
    return brep_evidence::sha256_hex(bytes);
}

std::vector<std::string> boundary_uids(const fs::path& root) {
    const fs::path path = root / "boundary";
    std::ifstream stream(path);
    if (!stream || fs::is_symlink(fs::symlink_status(path))) throw std::runtime_error("boundary_readback_unavailable");
    const std::string text((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
    std::regex nfaces_regex(R"(nFaces\s+([0-9]+)\s*;)"), start_regex(R"(startFace\s+([0-9]+)\s*;)");
    std::vector<std::int64_t> counts, starts;
    for (std::sregex_iterator it(text.begin(), text.end(), nfaces_regex), end; it != end; ++it) counts.push_back(std::stoll((*it)[1].str()));
    for (std::sregex_iterator it(text.begin(), text.end(), start_regex), end; it != end; ++it) starts.push_back(std::stoll((*it)[1].str()));
    if (counts.empty() || counts.size() != starts.size()) throw std::runtime_error("boundary_readback_unavailable");
    std::vector<std::string> result;
    for (std::size_t patch = 0; patch < counts.size(); ++patch) {
        for (std::int64_t local = 0; local < counts[patch]; ++local) {
            result.push_back("boundary_face_" + std::to_string(starts[patch] + local));
        }
    }
    return result;
}

std::string required_string(const py::dict& dict, const char* key, std::vector<std::string>& reasons) {
    if (!dict.contains(key) || !py::isinstance<py::str>(dict[key])) {
        reasons.push_back(std::string("field_missing_or_invalid:") + key);
        return {};
    }
    const std::string value = py::str(dict[key]).cast<std::string>();
    if (value.empty()) reasons.push_back(std::string("field_empty:") + key);
    return value;
}

bool integer_value(const py::dict& dict, const char* key, std::int64_t& out, std::vector<std::string>& reasons) {
    if (!dict.contains(key)) {
        reasons.push_back(std::string("field_missing:") + key);
        return false;
    }
    try { out = py::cast<std::int64_t>(dict[key]); return true; }
    catch (...) { reasons.push_back(std::string("field_invalid:") + key); return false; }
}

void append_u32(std::vector<std::uint8_t>& bytes, std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) bytes.push_back(static_cast<std::uint8_t>((value >> shift) & 0xffU));
}

void append_i64(std::vector<std::uint8_t>& bytes, std::int64_t value) {
    const auto raw = static_cast<std::uint64_t>(value);
    for (int shift = 56; shift >= 0; shift -= 8) bytes.push_back(static_cast<std::uint8_t>((raw >> shift) & 0xffU));
}

void append_string(std::vector<std::uint8_t>& bytes, const std::string& value) {
    append_u32(bytes, static_cast<std::uint32_t>(value.size()));
    bytes.insert(bytes.end(), value.begin(), value.end());
}

py::dict refusal(const std::vector<std::string>& reasons) {
    py::dict out;
    out["accepted"] = false;
    py::list values;
    for (const auto& reason : reasons) values.append(reason);
    out["reasons"] = values;
    out["publication_eligible"] = false;
    out["release_eligible"] = false;
    out["candidate_discarded"] = true;
    return out;
}

py::dict audit(
    const std::string& root_string,
    const py::list& semantic_rows,
    const py::list& lineage_records,
    std::int64_t requested_layers,
    std::int64_t actual_layers,
    const std::string& baseline_tree_sha256) {
    std::vector<std::string> reasons;
    if (requested_layers < 0 || actual_layers < 0) reasons.push_back("layer_count_invalid");
    if (requested_layers != actual_layers) reasons.push_back("layer_count_mismatch");
    Semantic semantic;
    for (const auto& item : semantic_rows) {
        py::dict row;
        try { row = item.cast<py::dict>(); }
        catch (...) { reasons.push_back("semantic_row_not_object"); continue; }
        if (semantic.kind.empty()) {
            semantic.kind = required_string(row, "entity_kind", reasons);
        }
        std::int64_t id = 0;
        if (!integer_value(row, "source_id", id, reasons)) continue;
        std::map<std::string, std::string> fields;
        for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) fields[key] = required_string(row, key, reasons);
        if (!semantic.rows.emplace(id, std::move(fields)).second) reasons.push_back("semantic_source_id_duplicate");
    }
    std::vector<Record> records;
    std::set<std::string> output_uids;
    for (const auto& item : lineage_records) {
        py::dict row;
        try { row = item.cast<py::dict>(); }
        catch (...) { reasons.push_back("lineage_record_not_object"); continue; }
        Record record;
        record.uid = required_string(row, "output_uid", reasons);
        record.scope = required_string(row, "entity_scope", reasons);
        record.owner = required_string(row, "semantic_owner_id", reasons);
        record.operation = required_string(row, "operation", reasons);
        record.role = required_string(row, "boundary_role", reasons);
        if (row.contains("parent_uid") && !row["parent_uid"].is_none()) {
            record.has_parent = true;
            record.parent = required_string(row, "parent_uid", reasons);
        }
        if (!integer_value(row, "layer_index", record.layer, reasons)) record.layer = -1;
        if (row.contains("positive_measure")) {
            try {
                record.positive_measure = py::cast<double>(row["positive_measure"]);
                record.has_positive_measure = true;
            } catch (...) {
                reasons.push_back("positive_measure_invalid");
            }
        }
        py::dict source_ref;
        if (!row.contains("source_ref") || !py::isinstance<py::dict>(row["source_ref"])) {
            reasons.push_back("source_entity_unknown");
        } else {
            source_ref = row["source_ref"].cast<py::dict>();
            record.source_kind = required_string(source_ref, "kind", reasons);
            if (!integer_value(source_ref, "id", record.source_id, reasons)) record.source_id = -1;
        }
        for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) record.semantic[key] = required_string(row, key, reasons);
        if (!output_uids.insert(record.uid).second) reasons.push_back("output_uid_duplicate");
        if (record.scope != "output_boundary" && record.scope != "internal_interface") reasons.push_back("entity_scope_invalid");
        if (record.operation != "identity" && record.operation != "surface_refine" && record.operation != "bl_extrude" && record.operation != "transition") reasons.push_back("operation_invalid");
        if (record.role != "wall" && record.role != "inner" && record.role != "outer" && record.role != "sidewall") reasons.push_back("boundary_role_invalid");
        const auto semantic_it = semantic.rows.find(record.source_id);
        if (record.source_kind != semantic.kind || semantic_it == semantic.rows.end()) reasons.push_back("source_entity_unknown");
        else {
            const std::string expected_owner = "sem/" + semantic.kind + "/" + std::to_string(record.source_id);
            if (record.owner != expected_owner) reasons.push_back("semantic_owner_ambiguous");
            for (const auto& [key, value] : record.semantic) if (semantic_it->second.at(key) != value) reasons.push_back("semantic_payload_mismatch");
        }
        records.push_back(std::move(record));
    }
    fs::path root = fs::absolute(fs::path(root_string)).lexically_normal();
    std::size_t entry_count = 0;
    std::string tree_sha;
    std::vector<std::string> actual_uids;
    try {
        tree_sha = tree_digest(root, entry_count);
        actual_uids = boundary_uids(root);
    } catch (const std::exception& error) {
        reasons.push_back(error.what());
    }
    std::set<std::string> claimed_boundary_uids;
    for (const auto& record : records) if (record.scope == "output_boundary") claimed_boundary_uids.insert(record.uid);
    std::set<std::string> actual_set(actual_uids.begin(), actual_uids.end());
    if (claimed_boundary_uids != actual_set) reasons.push_back("output_boundary_uid_missing");
    if (requested_layers == 0 && actual_layers == 0) {
        if (!baseline_tree_sha256.empty() && baseline_tree_sha256 != tree_sha) reasons.push_back("bl0_tree_identity_failed");
        for (const auto& record : records) if (record.role != "wall" || record.operation != "identity" || record.layer != 0 || record.has_parent) reasons.push_back("bl0_role_contract_failed");
    }
    if (actual_layers > 0) {
        bool wall = false, inner = false, outer = false;
        for (const auto& record : records) { wall |= record.role == "wall"; inner |= record.role == "inner"; outer |= record.role == "outer"; }
        if (!wall || !inner || !outer) reasons.push_back("bl_role_chain_invalid");
        std::map<std::string, std::size_t> record_by_uid;
        for (std::size_t index = 0; index < records.size(); ++index) record_by_uid.emplace(records[index].uid, index);
        for (const auto& record : records) {
            if (!record.has_positive_measure || !std::isfinite(record.positive_measure) || record.positive_measure <= 0.0)
                reasons.push_back("bl_positive_measure_failed");
            if (record.role == "wall") {
                if (record.layer != 0 || record.has_parent) reasons.push_back("bl_wall_role_contract_failed");
                continue;
            }
            if (record.role == "inner" && record.layer <= 0) reasons.push_back("bl_inner_layer_invalid");
            if (record.role == "outer" && record.layer != actual_layers) reasons.push_back("bl_outer_layer_invalid");
            if (record.role == "sidewall" && record.layer <= 0) reasons.push_back("bl_sidewall_layer_invalid");
            if (!record.has_parent) {
                reasons.push_back("bl_parent_missing");
                continue;
            }
            const auto parent_it = record_by_uid.find(record.parent);
            if (parent_it == record_by_uid.end()) {
                reasons.push_back("bl_parent_unknown");
                continue;
            }
            const Record& parent = records[parent_it->second];
            if (parent.owner != record.owner) reasons.push_back("bl_parent_owner_switch");
            if (parent.layer >= record.layer) reasons.push_back("bl_parent_layer_nonmonotone");
        }
        for (const auto& record : records) {
            std::set<std::string> visited;
            const Record* current = &record;
            while (current != nullptr && current->has_parent) {
                if (!visited.insert(current->uid).second) {
                    reasons.push_back("bl_parent_cycle");
                    break;
                }
                const auto parent_it = record_by_uid.find(current->parent);
                if (parent_it == record_by_uid.end()) break;
                current = &records[parent_it->second];
            }
        }
    }
    std::sort(records.begin(), records.end(), [](const Record& a, const Record& b) { return std::tie(a.scope, a.uid) < std::tie(b.scope, b.uid); });
    std::vector<std::uint8_t> canonical;
    const std::string header = "autotessell/gate4-lineage-witness/v1";
    canonical.insert(canonical.end(), header.begin(), header.end());
    canonical.push_back(0);
    for (const auto& record : records) {
        for (const auto& value : {record.scope, record.uid, record.source_kind, record.owner, record.operation, record.role, record.parent}) append_string(canonical, value);
        append_i64(canonical, record.source_id);
        append_i64(canonical, record.layer);
        std::ostringstream measure;
        measure << std::setprecision(17) << record.positive_measure;
        append_string(canonical, measure.str());
        for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) append_string(canonical, record.semantic.at(key));
    }
    const std::string lineage_sha = brep_evidence::sha256_hex(canonical);
    py::dict out;
    if (!reasons.empty()) return refusal(reasons);
    out["accepted"] = true;
    out["status"] = "native_gate4_lineage_witness_passed";
    out["publication_eligible"] = false;
    out["release_eligible"] = false;
    out["tree_sha256"] = tree_sha;
    out["lineage_sha256"] = lineage_sha;
    out["entry_count"] = entry_count;
    out["actual_boundary_uids"] = actual_uids;
    out["output_boundary_count"] = claimed_boundary_uids.size();
    out["canonical_byte_count"] = canonical.size();
    out["cpp_standard"] = "cxx_std_23";
    out["candidate_discarded"] = false;
    return out;
}

}  // namespace

PYBIND11_MODULE(native_gate4_lineage_witness, module) {
    module.doc() = "C++23 staged-tree and actual-boundary Gate4 lineage witness";
    module.def("audit_staged_lineage", &audit,
        py::arg("root"), py::arg("semantic_rows"), py::arg("lineage_records"),
        py::arg("requested_layers"), py::arg("actual_layers"),
        py::arg("baseline_tree_sha256") = "");
}
