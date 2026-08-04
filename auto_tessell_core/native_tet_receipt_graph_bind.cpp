// Minimal immutable source/output receipt graph for strict Native Tet ingress.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace py = pybind11;

namespace {

const char* const semantic_keys[] = {
    "feature", "patch", "physical_group", "component", "provenance"};

struct SourceRow {
    std::string id;
    std::vector<long long> cycle;
    std::map<std::string, std::string> semantic;
};

struct OutputRow {
    std::string source_id;
    std::string output_id;
    std::vector<long long> cycle;
    std::map<std::string, std::string> semantic;
    long long incidence = -1;
};

bool digest64(const std::string& value) {
    if (value.size() != 64) return false;
    return std::all_of(value.begin(), value.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')
            || (c >= 'A' && c <= 'F');
    });
}

std::vector<long long> ids(const py::handle& value) {
    std::vector<long long> result;
    for (const py::handle item : value.cast<py::sequence>()) {
        result.push_back(py::cast<long long>(item));
    }
    return result;
}

std::vector<long long> canonical_cycle(const std::vector<long long>& input) {
    if (input.size() < 3 || std::set<long long>(input.begin(), input.end()).size() != input.size()) {
        throw std::runtime_error("receipt_cycle_invalid");
    }
    std::vector<long long> best;
    for (size_t offset = 0; offset < input.size(); ++offset) {
        std::vector<long long> candidate;
        for (size_t local = 0; local < input.size(); ++local) {
            candidate.push_back(input[(offset + local) % input.size()]);
        }
        if (best.empty() || candidate < best) best = std::move(candidate);
    }
    return best;
}

std::string cycle_text(const std::vector<long long>& cycle) {
    std::ostringstream out;
    for (const auto value : cycle) out << value << ',';
    return out.str();
}

std::map<std::string, std::string> semantic(const py::dict& row) {
    std::map<std::string, std::string> result;
    for (const char* key : semantic_keys) {
        if (!row.contains(key)) throw std::runtime_error("receipt_semantic_field_missing");
        const auto value = py::cast<std::string>(row[key]);
        if (value.empty()) throw std::runtime_error("receipt_semantic_field_empty");
        result.emplace(key, value);
    }
    return result;
}

py::dict refusal(const std::vector<std::string>& reasons) {
    py::dict result;
    result["accepted"] = false;
    result["publication_eligible"] = false;
    result["candidate_discarded"] = true;
    py::list values;
    for (const auto& reason : reasons) values.append(reason);
    result["reasons"] = values;
    return result;
}

py::dict build_graph(
    const py::list& source_rows,
    const py::list& output_rows,
    const std::string& source_digest,
    const std::string& semantic_digest,
    long long expected_incidence) {
    std::vector<std::string> reasons;
    if (!digest64(source_digest)) reasons.push_back("source_digest_invalid");
    if (!digest64(semantic_digest)) reasons.push_back("semantic_digest_invalid");
    if (expected_incidence != 1 && expected_incidence != 2) reasons.push_back("incidence_contract_invalid");
    std::map<std::string, SourceRow> sources;
    for (const auto& item : source_rows) {
        try {
            const py::dict row = item.cast<py::dict>();
            SourceRow value;
            value.id = py::cast<std::string>(row["source_face_id"]);
            if (value.id.empty() || !sources.emplace(value.id, value).second) {
                reasons.push_back("source_face_id_duplicate_or_empty");
                continue;
            }
            value.cycle = canonical_cycle(ids(row["source_vertex_ids"]));
            value.semantic = semantic(row);
            sources[value.id] = std::move(value);
        } catch (const std::exception& error) {
            reasons.push_back(error.what());
        }
    }
    std::vector<OutputRow> outputs;
    std::set<std::string> output_ids;
    for (const auto& item : output_rows) {
        try {
            const py::dict row = item.cast<py::dict>();
            OutputRow value;
            value.source_id = py::cast<std::string>(row["source_face_id"]);
            value.output_id = py::cast<std::string>(row["output_face_id"]);
            value.cycle = canonical_cycle(ids(row["output_vertex_ids"]));
            value.semantic = semantic(row);
            value.incidence = py::cast<long long>(row["incidence"]);
            if (value.output_id.empty() || !output_ids.insert(value.output_id).second) {
                reasons.push_back("output_face_id_duplicate_or_empty");
            }
            const auto source = sources.find(value.source_id);
            if (source == sources.end()) {
                reasons.push_back("source_face_id_unknown");
            } else {
                if (source->second.cycle != value.cycle) reasons.push_back("orientation_or_source_cycle_mismatch");
                if (source->second.semantic != value.semantic) reasons.push_back("semantic_payload_mismatch");
            }
            if (value.incidence != expected_incidence) reasons.push_back("boundary_incidence_mismatch");
            outputs.push_back(std::move(value));
        } catch (const std::exception& error) {
            reasons.push_back(error.what());
        }
    }
    if (outputs.size() != sources.size()) reasons.push_back("source_output_coverage_mismatch");
    if (!reasons.empty()) return refusal(reasons);
    std::sort(outputs.begin(), outputs.end(), [](const OutputRow& a, const OutputRow& b) {
        return a.output_id < b.output_id;
    });
    std::ostringstream canonical;
    canonical << "autotessell/native-tet-receipt-graph/v1\n" << source_digest << '\n' << semantic_digest << '\n';
    for (const auto& row : outputs) {
        canonical << row.source_id << '\0' << row.output_id << '\0'
                  << cycle_text(row.cycle) << '\0' << row.incidence << '\0';
        for (const char* key : semantic_keys) canonical << row.semantic.at(key) << '\0';
    }
    const std::string bytes = canonical.str();
    const std::vector<std::uint8_t> raw(bytes.begin(), bytes.end());
    py::dict result;
    result["accepted"] = true;
    result["publication_eligible"] = false;
    result["candidate_discarded"] = false;
    result["source_face_count"] = sources.size();
    result["output_face_count"] = outputs.size();
    result["incidence_contract"] = expected_incidence;
    result["graph_sha256"] = brep_evidence::sha256_hex(raw);
    result["orientation_reversal_forbidden"] = true;
    result["coordinate_matching_strict"] = false;
    return result;
}

}  // namespace

PYBIND11_MODULE(native_tet_receipt_graph, module) {
    module.doc() = "C++23 immutable source/output receipt graph.";
    module.def("build_graph", &build_graph,
        py::arg("source_rows"), py::arg("output_rows"),
        py::arg("source_digest"), py::arg("semantic_digest"),
        py::arg("expected_incidence") = 1);
}
