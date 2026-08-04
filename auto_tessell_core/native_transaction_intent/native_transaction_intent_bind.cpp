#include <pybind11/pybind11.h>

#include "native_transaction_intent_v1.hpp"

namespace py = pybind11;

PYBIND11_MODULE(native_transaction_intent, module) {
    module.def("canonical_sha256_v1", &native_transaction_intent::canonical_sha256_v1);
    module.def("authorize_native_transaction_v1", &native_transaction_intent::authorize_native_transaction_v1);
    module.def("rollback_transaction_intent_v1", &native_transaction_intent::rollback_transaction_intent_v1);
}
