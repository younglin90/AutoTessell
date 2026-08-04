#pragma once

#include <pybind11/pybind11.h>

#include <string>

namespace native_wall_edge_metric_corridor {

pybind11::dict seal_corridor_policy_v1(const pybind11::dict& policy);

pybind11::dict certify_wall_edge_metric_corridor(
    const pybind11::dict& authority_ledger,
    const pybind11::dict& sealed_policy,
    const pybind11::dict& geometry,
    const pybind11::dict& obstacles);

pybind11::dict compare_corridor_receipts(
    const pybind11::dict& candidate,
    const pybind11::dict& reread);

}  // namespace native_wall_edge_metric_corridor
