#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <cstdint>
#include <string>

namespace py = pybind11;

static py::dict rollback(const std::string& reason) {
    py::dict r;
    r["accepted"] = false;
    r["status"] = "tri_quad_producer_auditor_quality_gate_rolled_back";
    r["reason"] = reason;
    r["committed"] = false;
    r["candidate_discarded"] = true;
    r["publication_eligible"] = false;
    r["runtime_route"] = "private_default_off";
    r["route_calls"] = 0;
    r["actual_layers"] = 0;
    r["points"] = py::list(); r["triangles"] = py::list(); r["quads"] = py::list();
    r["strip_quads"] = py::list(); r["triangle_map"] = py::list();
    r["quad_map"] = py::list(); r["strip_map"] = py::list();
    return r;
}

static bool text(const py::dict& d, const char* k) {
    return d.contains(k) && !d[k].is_none() && !py::str(d[k]).cast<std::string>().empty();
}

static py::dict commit(
    const py::dict& candidate,
    const py::dict& certificate,
    const py::dict& bindings,
    std::int64_t requested_layers,
    double max_offset) {
    if (requested_layers < 0 || requested_layers > 3 ||
        (requested_layers != 0 && requested_layers != 1 && requested_layers != 3))
        return rollback("requested_layers_invalid");
    if (!(max_offset > 0.0)) return rollback("max_offset_invalid");
    if (!certificate.contains("accepted") || !certificate["accepted"].cast<bool>() ||
        !text(certificate, "auditor_schema") ||
        py::str(certificate["auditor_schema"]).cast<std::string>() != "TriQuadIndependentQualityCertificate/v4" ||
        !certificate.contains("fresh_process") || !certificate["fresh_process"].cast<bool>() ||
        !certificate.contains("producer_quality_ignored") || !certificate["producer_quality_ignored"].cast<bool>() ||
        certificate.contains("publication_eligible") && certificate["publication_eligible"].cast<bool>())
        return rollback("independent_certificate_untrusted");
    if (!certificate.contains("requested_layers") || !certificate.contains("actual_layers") ||
        certificate["requested_layers"].cast<std::int64_t>() != requested_layers ||
        certificate["actual_layers"].cast<std::int64_t>() != requested_layers)
        return rollback("certificate_layer_mismatch");
    for (const char* k : {"canonical_input_digest", "independent_certificate_digest"})
        if (!text(certificate, k)) return rollback("certificate_digest_missing");
    for (const char* k : {"source_digest", "receipt_digest", "candidate_digest", "lineage_digest", "schedule_digest", "threshold_profile_digest", "canonical_input_digest"})
        if (!text(bindings, k)) return rollback("binding_digest_missing");
    if (py::str(bindings["canonical_input_digest"]).cast<std::string>() != py::str(certificate["canonical_input_digest"]).cast<std::string>())
        return rollback("certificate_input_digest_mismatch");
    if (!certificate.contains("quality") || !py::isinstance<py::dict>(certificate["quality"]))
        return rollback("certificate_quality_missing");
    const py::dict quality = certificate["quality"].cast<py::dict>();
    if (!quality.contains("distributions") || !py::isinstance<py::dict>(quality["distributions"]) ||
        !quality.contains("adjacent_face_normal_dihedral_degrees") ||
        !quality.contains("wall_front_non_orthogonality_degrees") || !quality.contains("wall_front_tangential_leakage"))
        return rollback("certificate_distributions_missing");
    const py::dict distributions = quality["distributions"].cast<py::dict>();
    for (const char* k : {"retained_triangle", "paired_core_quad", "strip_quad", "aggregate"})
        if (!distributions.contains(k) || !py::isinstance<py::dict>(distributions[k])) return rollback("quality_class_distribution_missing");
    for (const char* k : {"retained_triangle", "paired_core_quad", "strip_quad", "aggregate"}) {
        const py::dict d = distributions[k].cast<py::dict>();
        for (const char* q : {"applicable", "count", "skewness", "tangential_aspect_ratio", "signed_jacobian", "ordered_sample_digest"})
            if (!d.contains(q)) return rollback("quality_distribution_field_missing");
        const auto count = d["count"].cast<std::size_t>();
        if (count == 0) {
            if (std::string(k) != "strip_quad" || requested_layers != 0 || d["applicable"].cast<bool>()) return rollback("quality_distribution_empty_unexpected");
            continue;
        }
        if (!d["applicable"].cast<bool>()) return rollback("quality_distribution_not_applicable");
        const py::dict skew = d["skewness"].cast<py::dict>();
        const py::dict aspect = d["tangential_aspect_ratio"].cast<py::dict>();
        const py::dict jac = d["signed_jacobian"].cast<py::dict>();
        for (const py::dict* metric : {&skew, &aspect, &jac})
            for (const char* q : {"min", "p50", "p95", "p99", "max"})
                if (!metric->contains(q)) return rollback("quality_scalar_stat_missing");
        if (skew["min"].cast<double>() > skew["p50"].cast<double>() || skew["p50"].cast<double>() > skew["p95"].cast<double>() || skew["p95"].cast<double>() > skew["p99"].cast<double>() || skew["p99"].cast<double>() > skew["max"].cast<double>())
            return rollback("quality_scalar_not_monotone");
        if (aspect["min"].cast<double>() > aspect["p50"].cast<double>() || aspect["p50"].cast<double>() > aspect["p95"].cast<double>() || aspect["p95"].cast<double>() > aspect["p99"].cast<double>() || aspect["p99"].cast<double>() > aspect["max"].cast<double>())
            return rollback("aspect_scalar_not_monotone");
        if (jac["min"].cast<double>() <= 1e-12) return rollback("signed_jacobian_threshold_failed");
        if (skew["p95"].cast<double>() > .25 || skew["p99"].cast<double>() > .40 || skew["max"].cast<double>() > .50 || aspect["p95"].cast<double>() > 3. || aspect["p99"].cast<double>() > 5. || aspect["max"].cast<double>() > 10.) return rollback("quality_threshold_failed");
    }
    const py::dict adjacent_metric = quality["adjacent_face_normal_dihedral_degrees"].cast<py::dict>();
    const py::dict wall = quality["wall_front_non_orthogonality_degrees"].cast<py::dict>();
    const py::dict leakage = quality["wall_front_tangential_leakage"].cast<py::dict>();
    if (requested_layers > 0 && (!wall["applicable"].cast<bool>() || wall["count"].cast<std::size_t>() == 0)) return rollback("coordinate_metric_not_applicable");
    if (!adjacent_metric["applicable"].cast<bool>() && adjacent_metric["count"].cast<std::size_t>() != 0) return rollback("adjacent_metric_applicability_invalid");
    if (requested_layers == 0 && wall["applicable"].cast<bool>()) return rollback("bl0_wall_metric_must_be_not_applicable");
    if (leakage["max"].cast<double>() > .025) return rollback("wall_front_leakage_failed");
    if (wall["p95"].cast<double>() > 15. || wall["p99"].cast<double>() > 20. || wall["max"].cast<double>() > 25.) return rollback("wall_front_non_orthogonality_failed");
    const py::dict adjacent = adjacent_metric;
    if (adjacent["applicable"].cast<bool>() && (adjacent["p95"].cast<double>() > 35. || adjacent["p99"].cast<double>() > 45. || adjacent["max"].cast<double>() > 50.)) return rollback("adjacent_normal_non_orthogonality_failed");
    for (const char* k : {"points", "triangles", "quads", "strip_quads", "triangle_map", "quad_map", "strip_map"})
        if (!candidate.contains(k) || !py::isinstance<py::list>(candidate[k])) return rollback("candidate_buffer_missing");
    const auto strips = candidate["strip_quads"].cast<py::list>();
    if (requested_layers == 0 && !strips.empty()) return rollback("bl0_strip_not_empty");
    if (requested_layers > 0 && strips.empty()) return rollback("positive_bl_strip_missing");
    const auto tri_count = distributions["retained_triangle"].cast<py::dict>()["count"].cast<std::size_t>();
    const auto quad_count = distributions["paired_core_quad"].cast<py::dict>()["count"].cast<std::size_t>();
    const auto strip_count = distributions["strip_quad"].cast<py::dict>()["count"].cast<std::size_t>();
    if (tri_count != candidate["triangles"].cast<py::list>().size() || quad_count != candidate["quads"].cast<py::list>().size() || strip_count != strips.size())
        return rollback("quality_distribution_count_mismatch");
    if (distributions["aggregate"].cast<py::dict>()["count"].cast<std::size_t>() != tri_count + quad_count + strip_count)
        return rollback("quality_aggregate_count_mismatch");
    py::dict r;
    r["accepted"] = true; r["status"] = "tri_quad_producer_auditor_quality_gate_committed";
    r["reason"] = "independent_certificate_and_binding_gates_passed"; r["committed"] = true;
    r["candidate_discarded"] = false; r["publication_eligible"] = false;
    r["runtime_route"] = "private_default_off"; r["route_calls"] = 0; r["actual_layers"] = requested_layers;
    for (const char* k : {"points", "triangles", "quads", "strip_quads", "triangle_map", "quad_map", "strip_map"}) r[k] = candidate[k];
    r["certificate"] = certificate; r["binding_digests"] = bindings; r["count_is_report_only"] = true;
    return r;
}

PYBIND11_MODULE(native_tri_quad_producer_auditor_quality_gate, m) {
    m.doc() = "Private C++23 all-or-nothing TRI+QUAD producer/auditor quality gate";
    m.def("commit", &commit, py::arg("candidate"), py::arg("certificate"), py::arg("bindings"), py::arg("requested_layers"), py::arg("max_offset"));
}
