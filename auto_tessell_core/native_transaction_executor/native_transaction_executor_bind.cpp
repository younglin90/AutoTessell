#include <pybind11/pybind11.h>

#include "native_transaction_executor_v1.hpp"

namespace py = pybind11;

PYBIND11_MODULE(native_transaction_executor, module) {
    module.def("canonical_artifact_sha256_v1", &native_transaction_executor::canonical_artifact_sha256_v1);
    module.def("begin_transaction_v1", &native_transaction_executor::begin_transaction_v1);
    module.def("validate_candidate_v1", &native_transaction_executor::validate_candidate_v1);
    module.def("validate_disk_reread_v1", &native_transaction_executor::validate_disk_reread_v1);
    module.def("publish_transaction_v1", &native_transaction_executor::publish_transaction_v1);
    module.def("rollback_transaction_v1", &native_transaction_executor::rollback_transaction_v1);
    module.def("run_writer_transaction_v1", &native_transaction_executor::run_writer_transaction_v1);
}
