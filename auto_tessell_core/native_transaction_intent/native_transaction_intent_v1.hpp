#pragma once

#include <pybind11/pybind11.h>

#include <string>

namespace native_transaction_intent {

pybind11::dict canonical_sha256_v1(const pybind11::dict& value);

pybind11::dict authorize_native_transaction_v1(
    const pybind11::dict& authority_ledger,
    const pybind11::dict& raw_request,
    const pybind11::dict& engine_manifest,
    const pybind11::dict& quality_policy_v3,
    const pybind11::object& corridor_receipt);

pybind11::dict rollback_transaction_intent_v1(
    const pybind11::dict& intent,
    const std::string& reason);

}  // namespace native_transaction_intent
