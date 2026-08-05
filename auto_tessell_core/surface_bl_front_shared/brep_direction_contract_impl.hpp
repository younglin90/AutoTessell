#pragma once

#include "brep_contact_geometry.hpp"

#include <cmath>
#include <cstdint>
#include <set>
#include <string>

namespace {

inline bool direction_vec3(const py::handle value, brep_contact::Vec3& result) {
    const py::sequence sequence = value.cast<py::sequence>();
    if (sequence.size() != 3U) return false;
    result = {sequence[0].cast<double>(), sequence[1].cast<double>(),
              sequence[2].cast<double>()};
    return brep_contact::finite(result) && brep_contact::norm(result) > 0.0;
}

inline py::dict validate_brep_direction_contract_v2(const py::dict& ledger,
                                                    const py::sequence& records) {
    if (!ledger.contains("schema") ||
        ledger["schema"].cast<std::string>() != "BRepLayerInput/v1") {
        return refusal("layer_input_schema_mismatch");
    }
    if (!ledger.contains("source_digest") ||
        ledger["source_digest"].cast<std::string>().size() != 64U) {
        return refusal("layer_input_source_digest_missing");
    }
    if (!ledger.contains("sectors") || !ledger.contains("authority")) {
        return refusal("layer_input_authority_incomplete");
    }
    const py::sequence sectors = ledger["sectors"].cast<py::sequence>();
    if (records.size() != sectors.size()) return refusal("direction_record_count_mismatch");

    std::set<std::int64_t> sector_ids;
    const std::string source_digest = ledger["source_digest"].cast<std::string>();
    for (const py::handle sector_item : sectors) {
        const py::dict sector = sector_item.cast<py::dict>();
        if (!sector.contains("sector_id") || !sector.contains("source_digest") ||
            sector["source_digest"].cast<std::string>() != source_digest) {
            return refusal("sector_source_binding_invalid");
        }
        if (!sector_ids.insert(sector["sector_id"].cast<std::int64_t>()).second) {
            return refusal("duplicate_sector_id");
        }
    }

    std::set<std::int64_t> direction_ids;
    for (const py::handle record_item : records) {
        const py::dict record = record_item.cast<py::dict>();
        for (const char* key : {"sector_id", "edge_tangent", "face_normal", "surface_du",
                                "surface_dv", "uv_point", "uv_inward", "domain_side",
                                "trimmed_interior_status", "pcurve_digest", "surface_digest",
                                "certificate_digest", "pcurve_branch_rank", "pcurve_branch_count",
                                "seam_branch_count", "pcurve_branch_status", "is_closed_pcurve",
                                "period_shift", "uv_canonical", "effective_occurrence_reversed",
                                "branch_digest"}) {
            if (!record.contains(key)) return refusal("direction_record_incomplete");
        }
        const std::int64_t sector_id = record["sector_id"].cast<std::int64_t>();
        if (!sector_ids.contains(sector_id) || !direction_ids.insert(sector_id).second) {
            return refusal("direction_sector_binding_invalid");
        }
        for (const char* key : {"edge_tangent", "face_normal", "surface_du", "surface_dv"}) {
            brep_contact::Vec3 vector{};
            if (!direction_vec3(record[key], vector)) return refusal("direction_vector_invalid");
        }
        const py::sequence uv_point = record["uv_point"].cast<py::sequence>();
        const py::sequence uv_inward = record["uv_inward"].cast<py::sequence>();
        if (uv_point.size() != 2U || uv_inward.size() != 2U) {
            return refusal("uv_direction_invalid");
        }
        for (const py::handle value : uv_point) {
            if (!std::isfinite(value.cast<double>())) return refusal("uv_point_nonfinite");
        }
        for (const py::handle value : uv_inward) {
            if (!std::isfinite(value.cast<double>())) return refusal("uv_inward_nonfinite");
        }
        const std::int64_t domain_side = record["domain_side"].cast<std::int64_t>();
        if (domain_side != -1 && domain_side != 1) return refusal("domain_side_invalid");
        if (record["trimmed_interior_status"].cast<std::string>() != "one_side_certified") {
            return refusal("trimmed_interior_uncertain");
        }
        for (const char* key : {"pcurve_digest", "surface_digest", "certificate_digest"}) {
            if (record[key].cast<std::string>().size() != 64U) {
                return refusal("direction_digest_invalid");
            }
        }
        const std::int64_t branch_rank = record["pcurve_branch_rank"].cast<std::int64_t>();
        const std::int64_t branch_count = record["pcurve_branch_count"].cast<std::int64_t>();
        const std::int64_t seam_branch_count = record["seam_branch_count"].cast<std::int64_t>();
        const bool is_closed_pcurve = record["is_closed_pcurve"].cast<bool>();
        if (branch_count != (is_closed_pcurve ? 2 : 1) ||
            seam_branch_count != branch_count || branch_rank < 0 || branch_rank >= branch_count) {
            return refusal("pcurve_branch_contract_invalid");
        }
        const std::string branch_status = record["pcurve_branch_status"].cast<std::string>();
        if ((is_closed_pcurve && branch_status != "branches_certified") ||
            (!is_closed_pcurve && branch_status != "single_branch")) {
            return refusal("pcurve_branch_unresolved");
        }
        const py::sequence period_shift = record["period_shift"].cast<py::sequence>();
        const py::sequence uv_canonical = record["uv_canonical"].cast<py::sequence>();
        if (period_shift.size() != 2U || uv_canonical.size() != 2U) {
            return refusal("periodic_ledger_invalid");
        }
        for (const py::handle value : period_shift) {
            if (!std::isfinite(value.cast<double>())) return refusal("period_shift_nonfinite");
        }
        for (const py::handle value : uv_canonical) {
            if (!std::isfinite(value.cast<double>())) return refusal("uv_canonical_nonfinite");
        }
    }
    if (direction_ids.size() != sector_ids.size()) return refusal("direction_sector_incomplete");

    py::dict result;
    result["accepted"] = true;
    result["status"] = "brep_direction_contract_ready";
    result["schema"] = "AuthoritativeBrepLayerSector/v2";
    result["source_digest"] = source_digest;
    result["sector_count"] = static_cast<std::int64_t>(sector_ids.size());
    result["direction_certificate_count"] = static_cast<std::int64_t>(direction_ids.size());
    result["domain_side_is_explicit"] = true;
    result["trimmed_interior_is_certified"] = true;
    result["uncertain_is_refusal"] = true;
    result["runtime_route"] = "default_off_brep_diagnostic";
    return result;
}

}  // namespace
