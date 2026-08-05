#pragma once

// C++23 fail-closed OCCT provisioning-manifest verifier.  The manifest is a
// deliberately small canonical text certificate so the ingress kernel does
// not need a second JSON parser or a Python fallback.
#include <pybind11/pybind11.h>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

namespace native_hex_occt_manifest {

namespace py = pybind11;

struct Result {
    bool accepted = false;
    std::string reason;
    std::string manifest_sha256;
    std::string occt_version;
    std::string occt_abi;
    std::string compiler_abi;
    std::string build_identity;
    std::size_t header_count = 0U;
    std::size_t library_count = 0U;
};

inline bool valid_digest(const std::string& value) {
    if (value.size() != 64U) return false;
    return std::all_of(value.begin(), value.end(), [](char byte) {
        return (byte >= '0' && byte <= '9') || (byte >= 'a' && byte <= 'f');
    });
}

inline std::string file_sha256(const std::filesystem::path& path) {
    if (!std::filesystem::is_regular_file(path) || std::filesystem::is_symlink(path)) {
        return {};
    }
    std::ifstream stream(path, std::ios::binary);
    if (!stream) return {};
    const std::vector<std::uint8_t> bytes(
        (std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
    return brep_evidence::sha256_hex(bytes);
}

inline bool safe_relative_file(
    const std::filesystem::path& root,
    const std::string& relative,
    std::filesystem::path& resolved) {
    const std::filesystem::path candidate(relative);
    if (relative.empty() || candidate.is_absolute()) return false;
    for (const auto& part : candidate) {
        if (part == "..") return false;
    }
    std::error_code error;
    resolved = std::filesystem::weakly_canonical(root / candidate, error);
    const auto canonical_root = std::filesystem::weakly_canonical(root, error);
    if (error || resolved.empty() || canonical_root.empty()) return false;
    const auto relative_to_root = std::filesystem::relative(resolved, canonical_root, error);
    if (error || relative_to_root.empty()) return false;
    for (const auto& part : relative_to_root) {
        if (part == "..") return false;
    }
    return std::filesystem::is_regular_file(resolved) &&
           !std::filesystem::is_symlink(root / candidate);
}

inline Result audit(
    const std::string& sdk_root_text,
    const std::string& manifest_path_text,
    const std::string& expected_occt_version = {},
    const std::string& expected_occt_abi = {},
    const std::string& expected_compiler_abi = {},
    const std::string& expected_build_identity = {}) {
    Result result;
    const std::filesystem::path sdk_root(sdk_root_text);
    const std::filesystem::path manifest_path(manifest_path_text);
    if (sdk_root_text.empty() || manifest_path_text.empty() ||
        !std::filesystem::is_directory(sdk_root) ||
        std::filesystem::is_symlink(sdk_root) ||
        !std::filesystem::is_regular_file(manifest_path) ||
        std::filesystem::is_symlink(manifest_path)) {
        result.reason = "provisioning_manifest_path_missing_or_symlink";
        return result;
    }
    std::ifstream stream(manifest_path, std::ios::binary);
    if (!stream) {
        result.reason = "provisioning_manifest_unreadable";
        return result;
    }
    const std::string raw(
        (std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
    if (raw.empty() || raw.back() != '\n') {
        result.reason = "provisioning_manifest_final_newline_missing";
        return result;
    }

    std::map<std::string, std::string> values;
    std::string canonical;
    std::string supplied_manifest_digest;
    std::istringstream lines(raw);
    std::string line;
    bool found_manifest_digest = false;
    while (std::getline(lines, line)) {
        if (!line.empty() && line.back() == '\r') {
            result.reason = "provisioning_manifest_crlf_rejected";
            return result;
        }
        if (line.empty()) {
            result.reason = "provisioning_manifest_empty_line";
            return result;
        }
        const std::size_t equals = line.find('=');
        if (equals == std::string::npos || equals == 0U) {
            result.reason = "provisioning_manifest_key_value_invalid";
            return result;
        }
        const std::string key = line.substr(0U, equals);
        const std::string value = line.substr(equals + 1U);
        if (key == "manifest_sha256") {
            if (found_manifest_digest) {
                result.reason = "provisioning_manifest_order_or_duplicate_invalid";
                return result;
            }
            supplied_manifest_digest = value;
            found_manifest_digest = true;
            continue;
        }
        if (found_manifest_digest || !values.emplace(key, value).second) {
            result.reason = "provisioning_manifest_order_or_duplicate_invalid";
            return result;
        }
        canonical += line;
        canonical.push_back('\n');
    }
    if (!found_manifest_digest || !valid_digest(supplied_manifest_digest)) {
        result.reason = "provisioning_manifest_digest_missing_or_invalid";
        return result;
    }
    const std::vector<std::uint8_t> canonical_bytes(canonical.begin(), canonical.end());
    const std::string recomputed_manifest_digest = brep_evidence::sha256_hex(canonical_bytes);
    if (supplied_manifest_digest != recomputed_manifest_digest) {
        result.reason = "provisioning_manifest_digest_mismatch";
        return result;
    }
    for (const char* key : {
             "schema", "sdk_root", "occt_version", "occt_abi", "compiler_abi",
             "build_identity"}) {
        if (!values.contains(key) || values.at(key).empty()) {
            result.reason = std::string("provisioning_manifest_field_missing:") + key;
            return result;
        }
    }
    if (values.at("schema") != "autotessell/native-hex-occt-provisioning/v1") {
        result.reason = "provisioning_manifest_schema_unsupported";
        return result;
    }
    std::error_code root_error;
    const std::string canonical_root =
        std::filesystem::weakly_canonical(sdk_root, root_error).string();
    if (root_error || values.at("sdk_root") != canonical_root) {
        result.reason = "provisioning_manifest_sdk_root_mismatch";
        return result;
    }
    if ((!expected_occt_version.empty() && values.at("occt_version") != expected_occt_version) ||
        (!expected_occt_abi.empty() && values.at("occt_abi") != expected_occt_abi) ||
        (!expected_compiler_abi.empty() && values.at("compiler_abi") != expected_compiler_abi) ||
        (!expected_build_identity.empty() && values.at("build_identity") != expected_build_identity)) {
        result.reason = "provisioning_manifest_expected_identity_mismatch";
        return result;
    }

    for (const auto& [key, value] : values) {
        if (key.rfind("header.", 0U) != 0U && key.rfind("library.", 0U) != 0U) {
            continue;
        }
        const std::size_t separator = value.rfind('|');
        if (separator == std::string::npos || separator == 0U ||
            separator + 1U >= value.size()) {
            result.reason = "provisioning_manifest_file_record_invalid";
            return result;
        }
        const std::string relative = value.substr(0U, separator);
        const std::string expected_sha = value.substr(separator + 1U);
        if (!valid_digest(expected_sha)) {
            result.reason = "provisioning_manifest_file_digest_invalid";
            return result;
        }
        std::filesystem::path resolved;
        if (!safe_relative_file(sdk_root, relative, resolved) ||
            file_sha256(resolved) != expected_sha) {
            result.reason = std::string("provisioning_manifest_file_hash_mismatch:") + key;
            return result;
        }
        if (key.rfind("header.", 0U) == 0U) {
            ++result.header_count;
        } else {
            ++result.library_count;
        }
    }
    if (!values.contains("header.STEPCAFControl_Reader.hxx") ||
        !values.contains("library.TKSTEPCAF") || result.header_count == 0U ||
        result.library_count == 0U) {
        result.reason = "provisioning_manifest_required_occt_files_missing";
        return result;
    }
    result.accepted = true;
    result.manifest_sha256 = supplied_manifest_digest;
    result.occt_version = values.at("occt_version");
    result.occt_abi = values.at("occt_abi");
    result.compiler_abi = values.at("compiler_abi");
    result.build_identity = values.at("build_identity");
    return result;
}

inline py::dict as_dict(const Result& value, bool compiled_with_occt) {
    py::dict result;
    result["accepted"] = value.accepted;
    result["authoritative"] = false;
    result["status"] = value.accepted
        ? "pass_native_hex_occt_provisioning_manifest"
        : "reject_native_hex_occt_provisioning_manifest";
    result["reason"] = value.reason;
    result["manifest_sha256"] = value.manifest_sha256;
    result["occt_provisioning_manifest_sha256"] = value.manifest_sha256;
    result["occt_version"] = value.occt_version;
    result["occt_abi"] = value.occt_abi;
    result["compiler_abi"] = value.compiler_abi;
    result["build_identity"] = value.build_identity;
    result["header_count"] = value.header_count;
    result["library_count"] = value.library_count;
    result["compiled_with_occt"] = compiled_with_occt;
    result["publication_eligible"] = false;
    return result;
}

}  // namespace native_hex_occt_manifest
