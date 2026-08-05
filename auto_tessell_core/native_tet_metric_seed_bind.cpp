// Deterministic metric-aware BCC interior candidates for Native Tet.
//
// This module deliberately does not classify points, move source vertices, or
// publish a mesh.  Python supplies the authoritative source envelope and may
// reject candidates before a private Delaunay stage.  The C++ side owns only
// deterministic metric lattice construction and parameter validation.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

namespace {

using Vec3 = std::array<double, 3>;

Vec3 read_vec3(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& value,
    const char* name)
{
    if (value.ndim() != 1 || value.shape(0) != 3) {
        throw std::invalid_argument(std::string(name) + " expects shape (3,)");
    }
    const auto view = value.unchecked<1>();
    Vec3 result{};
    for (std::size_t i = 0; i < 3; ++i) {
        result[i] = view(static_cast<py::ssize_t>(i));
        if (!std::isfinite(result[i])) {
            throw std::invalid_argument(std::string(name) + " requires finite values");
        }
    }
    return result;
}

py::array_t<double> generate_metric_bcc_candidates(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& bbox_min_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& bbox_max_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& metric_diagonal_array,
    const double metric_spacing,
    const std::int64_t max_candidates)
{
    const Vec3 bbox_min = read_vec3(bbox_min_array, "bbox_min");
    const Vec3 bbox_max = read_vec3(bbox_max_array, "bbox_max");
    const Vec3 metric = read_vec3(metric_diagonal_array, "metric_diagonal");
    if (!std::isfinite(metric_spacing) || metric_spacing <= 0.0) {
        throw std::invalid_argument("metric_spacing must be finite and positive");
    }
    if (max_candidates <= 0) {
        throw std::invalid_argument("max_candidates must be positive");
    }

    std::array<std::int64_t, 3> cells{};
    std::array<double, 3> step{};
    for (std::size_t axis = 0; axis < 3; ++axis) {
        const double span = bbox_max[axis] - bbox_min[axis];
        if (!std::isfinite(span) || span <= 0.0 || metric[axis] <= 0.0) {
            throw std::invalid_argument("bbox span and metric diagonal must be positive");
        }
        const double metric_span = span * std::sqrt(metric[axis]);
        const double count = std::ceil(metric_span / metric_spacing);
        if (!std::isfinite(count) || count < 1.0
            || count > static_cast<double>(std::numeric_limits<std::int64_t>::max())) {
            throw std::invalid_argument("metric lattice cell count invalid");
        }
        cells[axis] = static_cast<std::int64_t>(count);
        step[axis] = span / static_cast<double>(cells[axis]);
    }

    const long double cell_count = static_cast<long double>(cells[0])
        * static_cast<long double>(cells[1]) * static_cast<long double>(cells[2]);
    if (cell_count * 2.0L > static_cast<long double>(max_candidates)) {
        throw std::invalid_argument("metric lattice exceeds max_candidates");
    }

    std::vector<Vec3> candidates;
    candidates.reserve(static_cast<std::size_t>(cell_count));

    // BCC body centers are the primary interior candidates.  Add the strict
    // interior corner sublattice as a second deterministic basis; boundary
    // vertices are intentionally excluded because source support is owned by
    // the caller and must never be duplicated here.
    for (std::int64_t i = 0; i < cells[0]; ++i) {
        for (std::int64_t j = 0; j < cells[1]; ++j) {
            for (std::int64_t k = 0; k < cells[2]; ++k) {
                candidates.push_back(Vec3{
                    bbox_min[0] + (static_cast<double>(i) + 0.5) * step[0],
                    bbox_min[1] + (static_cast<double>(j) + 0.5) * step[1],
                    bbox_min[2] + (static_cast<double>(k) + 0.5) * step[2]});
            }
        }
    }
    for (std::int64_t i = 1; i < cells[0]; ++i) {
        for (std::int64_t j = 1; j < cells[1]; ++j) {
            for (std::int64_t k = 1; k < cells[2]; ++k) {
                candidates.push_back(Vec3{
                    bbox_min[0] + static_cast<double>(i) * step[0],
                    bbox_min[1] + static_cast<double>(j) * step[1],
                    bbox_min[2] + static_cast<double>(k) * step[2]});
            }
        }
    }

    py::array_t<double> result({
        static_cast<py::ssize_t>(candidates.size()), static_cast<py::ssize_t>(3)});
    auto output = result.mutable_unchecked<2>();
    for (std::size_t row = 0; row < candidates.size(); ++row) {
        for (std::size_t axis = 0; axis < 3; ++axis) {
            output(static_cast<py::ssize_t>(row), static_cast<py::ssize_t>(axis))
                = candidates[row][axis];
        }
    }
    return result;
}

} // namespace

PYBIND11_MODULE(native_tet_metric_seed, module)
{
    module.doc() = "Deterministic metric-aware BCC interior candidates";
    module.def(
        "generate_metric_bcc_candidates",
        &generate_metric_bcc_candidates,
        py::arg("bbox_min"), py::arg("bbox_max"), py::arg("metric_diagonal"),
        py::arg("metric_spacing"), py::arg("max_candidates"));
}
