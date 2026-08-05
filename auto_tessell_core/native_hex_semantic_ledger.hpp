#pragma once

// Canonical Native Hex semantic-ledger encoding shared by ingress and receipt.
// A semantic row is intentionally small and explicit: geometry/XDE metadata
// cannot become CFD authority unless these five application-owned fields are
// present and digest-bound.
#include <pybind11/pybind11.h>

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

namespace native_hex_semantic {

namespace py = pybind11;

struct Result {
    bool accepted = false;
    std::string reason;
    std::string canonical;
    std::string digest;
    std::size_t row_count = 0U;
};

inline bool validate_ordinal(
    const py::dict& row,
    const char* key,
    std::size_t expected,
    std::string& reason) {
    if (!row.contains(key)) return true;
    try {
        const auto value = py::cast<std::int64_t>(row[key]);
        if (value != static_cast<std::int64_t>(expected)) {
            reason = std::string("semantic_") + key + "_not_canonical";
            return false;
        }
    } catch (...) {
        reason = std::string("semantic_") + key + "_type_invalid";
        return false;
    }
    return true;
}

inline Result build(const py::list& rows, std::size_t expected_count) {
    Result result;
    result.row_count = static_cast<std::size_t>(rows.size());
    if (result.row_count != expected_count) {
        result.reason = "semantic_face_count_mismatch";
        return result;
    }

    static constexpr const char* fields[] = {
        "feature", "patch", "physical_group", "component", "provenance",
    };
    result.canonical = "native-hex-semantic-ledger-v1|";
    for (std::size_t index = 0U; index < expected_count; ++index) {
        py::dict row;
        try {
            row = rows[static_cast<py::ssize_t>(index)].cast<py::dict>();
        } catch (...) {
            result.reason = "semantic_row_not_object";
            result.canonical.clear();
            return result;
        }
        for (const char* ordinal_key : {"source_face", "face_id"}) {
            if (!validate_ordinal(row, ordinal_key, index, result.reason)) {
                result.canonical.clear();
                return result;
            }
        }
        result.canonical += "source_face=" + std::to_string(index) + "|";
        for (const char* key : fields) {
            if (!row.contains(key) || !py::isinstance<py::str>(row[key])) {
                result.reason = std::string("semantic_field_missing_or_type_invalid:") + key;
                result.canonical.clear();
                return result;
            }
            const std::string value = py::str(row[key]).cast<std::string>();
            if (value.empty()) {
                result.reason = std::string("semantic_field_empty:") + key;
                result.canonical.clear();
                return result;
            }
            // Length-prefix bytes make delimiters in user names unambiguous.
            result.canonical += key;
            result.canonical += "=";
            result.canonical += std::to_string(value.size());
            result.canonical += ":";
            result.canonical += value;
            result.canonical += "|";
        }
        result.canonical += ";";
    }
    const std::vector<std::uint8_t> bytes(result.canonical.begin(), result.canonical.end());
    result.digest = brep_evidence::sha256_hex(bytes);
    result.accepted = true;
    return result;
}

inline py::dict as_dict(const Result& value) {
    py::dict result;
    result["accepted"] = value.accepted;
    result["reason"] = value.reason;
    result["semantic_ledger_sha256"] = value.digest;
    result["canonical_byte_count"] = value.canonical.size();
    result["row_count"] = value.row_count;
    return result;
}

}  // namespace native_hex_semantic
