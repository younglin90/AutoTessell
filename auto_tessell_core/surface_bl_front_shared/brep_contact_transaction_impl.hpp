#pragma once

#include <cstdint>

inline py::dict plan_brep_shared_surface_wall_edge_front(
    const py::dict& evidence, std::int64_t requested_layers, const py::sequence& candidates) {
    py::dict result;
    result["requested_layers"] = requested_layers;
    result["source_immutable"] = true;
    result["runtime_route"] = "default_off";
    result["atomic_rollback"] = true;
    if (requested_layers == 0) {
        result["accepted"] = true;
        result["status"] = "disabled_identity";
        result["actual_layers"] = 0;
        result["generated_faces"] = py::list();
        return result;
    }
    if (requested_layers < 0) return refusal("negative_layer_count");
    if (candidates.size() == 0U) return refusal("missing_brep_front_candidates");
    py::list staged;
    for (const py::handle item : candidates) {
        const auto candidate = item.cast<py::dict>();
        if (!candidate.contains("edge_id") || !candidate.contains("candidate_face_id") ||
            !candidate.contains("vertices")) {
            result["accepted"] = false;
            result["status"] = "refused_brep_transaction";
            result["reason"] = "candidate_record_incomplete";
            result["actual_layers"] = 0;
            result["generated_faces"] = py::list();
            return result;
        }
        const auto witness_result = witness(
            evidence,
            candidate["edge_id"].cast<std::int64_t>(),
            candidate["candidate_face_id"].cast<std::int64_t>(),
            candidate["vertices"].cast<py::sequence>());
        if (!witness_result["accepted"].cast<bool>() || !witness_result["permitted"].cast<bool>()) {
            result["accepted"] = false;
            result["status"] = "refused_brep_transaction";
            result["reason"] = "contact_witness_rollback";
            result["witness"] = witness_result;
            result["actual_layers"] = 0;
            result["generated_faces"] = py::list();
            return result;
        }
        py::dict staged_record;
        staged_record["edge_id"] = candidate["edge_id"];
        staged_record["candidate_face_id"] = candidate["candidate_face_id"];
        staged_record["vertices"] = candidate["vertices"];
        staged_record["geometric_class"] = witness_result["geometric_class"];
        staged.append(staged_record);
    }
    result["accepted"] = true;
    result["status"] = "candidate_plan_ready";
    result["actual_layers"] = requested_layers;
    result["generated_faces"] = staged;
    result["count_is_report_only"] = true;
    result["witnesses_computed_in_cpp"] = true;
    return result;
}
