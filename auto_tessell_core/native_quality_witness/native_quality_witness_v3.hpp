#pragma once

#include <pybind11/pybind11.h>

namespace native_quality_witness_v3 {

pybind11::dict seal_policy_v3(const pybind11::dict& policy);
pybind11::dict evaluate_v3(const pybind11::dict& snapshot,
                           const pybind11::dict& authority,
                           const pybind11::dict& sealed_policy,
                           const std::string& stage);
pybind11::dict compare_candidate_reread_v3(const pybind11::dict& candidate,
                                           const pybind11::dict& reread);

}  // namespace native_quality_witness_v3
