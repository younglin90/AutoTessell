// C++23 private authority-bound shared wall-front transaction.
#include <pybind11/pybind11.h>
#include <cstdint>
#include <string>

namespace py = pybind11;

namespace {
py::dict reject(const char* reason, std::int64_t requested) {
    py::dict r; r["accepted"] = false; r["status"] = "refused_rollback"; r["reason"] = reason;
    r["requested_layers"] = requested; r["actual_layers"] = 0; r["runtime_route"] = "default_off";
    r["publication_eligible"] = false; r["route_calls"] = 0; r["candidate_discarded"] = true; return r;
}
py::dict seal(const py::dict& authority, const py::dict& optimizer, std::int64_t requested) {
    if (!authority.contains("accepted") || !authority["accepted"].cast<bool>() || !authority.contains("receipt_sealed") || !authority["receipt_sealed"].cast<bool>()) return reject("authority_receipt_incomplete", requested);
    if (!optimizer.contains("accepted") || !optimizer["accepted"].cast<bool>() || !optimizer.contains("receipt_sealed") || !optimizer["receipt_sealed"].cast<bool>()) return reject("optimizer_receipt_incomplete", requested);
    if (py::str(authority["runtime_route"]).cast<std::string>() != "default_off" || py::str(optimizer["runtime_route"]).cast<std::string>() != "default_off") return reject("route_mutation", requested);
    if (optimizer["actual_layers"].cast<std::int64_t>() != requested) return reject("partial_layer_transaction", requested);
    if (!authority.contains("direct_lineage") || !authority["direct_lineage"].cast<bool>()) return reject("direct_lineage_incomplete", requested);
    py::dict r; r["accepted"] = true; r["status"] = "authority_bound_transaction_sealed"; r["reason"] = "actual_v2_authority_bound_quality_receipt";
    r["requested_layers"] = requested; r["actual_layers"] = requested; r["authority_receipt"] = authority; r["optimizer_receipt"] = optimizer;
    r["runtime_route"] = "default_off"; r["publication_eligible"] = false; r["route_calls"] = 0; r["receipt_sealed"] = true; r["candidate_discarded"] = false;
    r["receipt_digest"] = std::string("authority-bound-v1|") + py::str(authority["receipt_digest"]).cast<std::string>() + "|" + py::str(optimizer["receipt_digest"]).cast<std::string>();
    return r;
}
}
PYBIND11_MODULE(native_surface_bl_front_actual_v2_transaction, module) {
    module.doc() = "Private C++23 actual-v2 authority-bound wall-front transaction";
    module.def("seal_authority_bound_surface_transaction", &seal, py::arg("authority_receipt"), py::arg("optimizer_receipt"), py::arg("requested_layers"));
}
