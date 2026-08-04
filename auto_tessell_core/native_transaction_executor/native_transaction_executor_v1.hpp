#pragma once

#include <pybind11/pybind11.h>

#include <string>

namespace native_transaction_executor {

pybind11::dict canonical_artifact_sha256_v1(const pybind11::dict& value);

pybind11::dict begin_transaction_v1(
    const pybind11::dict& intent,
    const pybind11::dict& authority_ledger,
    const pybind11::object& corridor_receipt);

pybind11::dict validate_candidate_v1(
    const pybind11::dict& transaction,
    const pybind11::dict& candidate);

pybind11::dict validate_disk_reread_v1(
    const pybind11::dict& transaction,
    const pybind11::dict& disk_reread);

pybind11::dict publish_transaction_v1(const pybind11::dict& transaction);

pybind11::dict rollback_transaction_v1(
    const pybind11::dict& transaction,
    const std::string& reason);

pybind11::dict run_writer_transaction_v1(
    const pybind11::dict& transaction,
    const pybind11::function& writer_callback,
    const pybind11::function& reread_callback);

}  // namespace native_transaction_executor
