#pragma once
#include <pybind11/pybind11.h>
#include <string>

namespace autotessell_native {

namespace py = pybind11;

inline bool receipt_sealed_default_off(const py::dict& receipt) {
    return receipt.contains("accepted") && receipt["accepted"].cast<bool>()
        && receipt.contains("receipt_sealed") && receipt["receipt_sealed"].cast<bool>()
        && receipt.contains("runtime_route")
        && py::str(receipt["runtime_route"]).cast<std::string>() == "default_off"
        && receipt.contains("receipt_digest")
        && !py::str(receipt["receipt_digest"]).cast<std::string>().empty();
}

inline bool authority_receipt_ready(const py::dict& receipt) {
    return receipt_sealed_default_off(receipt)
        && receipt.contains("direct_lineage")
        && receipt["direct_lineage"].cast<bool>();
}

inline bool optimizer_receipt_ready(const py::dict& receipt, long long requested_layers) {
    return receipt_sealed_default_off(receipt)
        && receipt.contains("actual_layers")
        && receipt["actual_layers"].cast<long long>() == requested_layers;
}

inline std::string receipt_digest(const py::dict& receipt) {
    if (!receipt.contains("receipt_digest")) return {};
    return py::str(receipt["receipt_digest"]).cast<std::string>();
}

}  // namespace autotessell_native
