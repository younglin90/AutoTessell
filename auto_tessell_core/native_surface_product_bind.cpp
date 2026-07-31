// Report-only C++23 topology classifier for native surface products.
//
// This module has no routing, meshing, repair, or writer side effects.  It
// accepts only immutable C-contiguous int64 topology arrays, validates each
// local face row, and emits a deterministic tri / strict-quad / tri-quad
// *local* classification.  It cannot certify a mesh product because it does
// not receive source geometry, feature/patch provenance, or an envelope
// certificate.  It is intentionally default-OFF in CMake.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <array>
#include <cstdint>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>

namespace py = pybind11;

namespace {

using Label = std::int64_t;

struct TopologyView {
    std::span<const Label> labels;
    std::size_t rows{};
};

[[nodiscard]] TopologyView immutable_topology_view(const py::array& values,
                                                    const std::size_t columns,
                                                    const std::string_view name)
{
    if (!values.dtype().is(py::dtype::of<Label>())) {
        throw py::type_error(std::string(name)
                             + " must have dtype int64; conversion is disabled");
    }
    if (values.ndim() != 2 || values.shape(1) != static_cast<py::ssize_t>(columns)) {
        throw py::value_error(std::string(name) + " must have shape (N, "
                              + std::to_string(columns) + ")");
    }
    if ((values.flags() & py::array::c_style) == 0) {
        throw py::value_error(std::string(name)
                              + " must be C-contiguous; conversion is disabled");
    }
    if (values.writeable()) {
        throw py::value_error(std::string(name)
                              + " must be read-only to preserve caller topology");
    }

    const auto row_count = values.shape(0);
    if (row_count < 0
        || static_cast<std::size_t>(row_count)
               > std::numeric_limits<std::size_t>::max() / columns) {
        throw py::value_error(std::string(name) + " has an unsupported row count");
    }
    const auto rows = static_cast<std::size_t>(row_count);
    const auto element_count = rows * columns;
    const auto* data = static_cast<const Label*>(values.data());
    return {std::span<const Label>{data, element_count}, rows};
}

template <std::size_t Arity>
[[nodiscard]] bool has_valid_rows(const TopologyView topology,
                                  const Label vertex_count) noexcept
{
    for (std::size_t row = 0; row < topology.rows; ++row) {
        const auto offset = row * Arity;
        const auto face = topology.labels.subspan(offset, Arity);
        for (std::size_t i = 0; i < Arity; ++i) {
            if (face[i] < 0 || face[i] >= vertex_count) {
                return false;
            }
            for (std::size_t j = i + 1; j < Arity; ++j) {
                if (face[i] == face[j]) {
                    return false;
                }
            }
        }
    }
    return true;
}

[[nodiscard]] py::dict evaluate_surface_product(const py::array& triangles,
                                                 const py::array& quads,
                                                 const Label vertex_count)
{
    if (vertex_count < 0) {
        throw py::value_error("vertex_count must be non-negative");
    }

    const auto triangle_view = immutable_topology_view(triangles, 3, "triangles");
    const auto quad_view = immutable_topology_view(quads, 4, "quads");
    const bool triangle_rows_valid = has_valid_rows<3>(triangle_view, vertex_count);
    const bool quad_rows_valid = has_valid_rows<4>(quad_view, vertex_count);
    const bool has_local_faces = triangle_view.rows > 0 || quad_view.rows > 0;
    const bool local_topology_valid = has_local_faces && triangle_rows_valid && quad_rows_valid;
    const char* classification = "invalid";
    if (local_topology_valid && triangle_view.rows > 0 && quad_view.rows == 0) {
        classification = "tri";
    } else if (local_topology_valid && triangle_view.rows == 0 && quad_view.rows > 0) {
        classification = "quad";
    } else if (local_topology_valid && triangle_view.rows > 0 && quad_view.rows > 0) {
        classification = "tri_quad";
    }

    py::dict report;
    report["contract"] = "native_surface_product_evaluator_l0";
    report["vertex_count"] = vertex_count;
    report["triangle_count"] = triangle_view.rows;
    report["quad_count"] = quad_view.rows;
    report["triangles_immutable"] = true;
    report["quads_immutable"] = true;
    report["triangle_rows_valid"] = triangle_rows_valid;
    report["quad_rows_valid"] = quad_rows_valid;
    report["local_topology_valid"] = local_topology_valid;
    report["classification"] = classification;
    report["product_accepted"] = false;
    report["product_rejection"] = "source_product_certificate_required";
    return report;
}

} // namespace

PYBIND11_MODULE(native_surface_product, module)
{
    module.doc() = "Default-OFF report-only native surface product evaluator";
    module.def("evaluate_surface_product",
               &evaluate_surface_product,
               py::arg("triangles").noconvert(),
               py::arg("quads").noconvert(),
               py::arg("vertex_count"),
               "Classify immutable triangle/quad topology without conversion or mesh mutation.");
}
