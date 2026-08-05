#pragma once

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <cmath>
#include <cstdint>
#include <string>

namespace autotessell_brep_authority {

namespace py = pybind11;

inline bool text(const py::dict& value, const char* key) {
    return value.contains(key) && !py::str(value[key]).cast<std::string>().empty();
}

inline py::dict reject(const std::string& reason, std::int64_t requested) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "refused_rollback";
    result["reason"] = reason;
    result["requested_layers"] = requested;
    result["actual_layers"] = 0;
    result["runtime_route"] = "default_off";
    result["publication_eligible"] = false;
    result["route_calls"] = 0;
    result["candidate_discarded"] = true;
    return result;
}

inline bool finite_positions(const py::array_t<double, py::array::c_style | py::array::forcecast>& positions) {
    if (positions.ndim() != 2 || positions.shape(1) != 3) return false;
    for (py::ssize_t i = 0; i < positions.size(); ++i) if (!std::isfinite(positions.data()[i])) return false;
    return true;
}

} // namespace autotessell_brep_authority
