// C++23 Native Hex post-boundary-layer B-Rep receipt kernel.
// This is an authority auditor, not a mesher. It consumes immutable output
// wall quads and an explicit source-face ledger, then fails closed.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "brep_evidence_sha256.hpp"
#include "native_hex_semantic_ledger.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <set>
#include <string>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;

struct Triangle {
    Point a;
    Point b;
    Point c;
    std::int64_t ordinal;
};

static Point sub(const Point& left, const Point& right) {
    return {left[0] - right[0], left[1] - right[1], left[2] - right[2]};
}

static Point cross(const Point& left, const Point& right) {
    return {
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    };
}

static double dot(const Point& left, const Point& right) {
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

static double norm(const Point& value) {
    return std::sqrt(dot(value, value));
}

static bool valid_digest(const std::string& value) {
    if (value.size() != 64U) return false;
    return std::all_of(value.begin(), value.end(), [](char value) {
        return (value >= '0' && value <= '9') || (value >= 'a' && value <= 'f');
    });
}

static double segment_distance(const Point& point, const Point& start, const Point& end) {
    const Point direction = sub(end, start);
    const double denominator = std::max(dot(direction, direction), 1.0e-30);
    const double parameter = std::clamp(dot(sub(point, start), direction) / denominator, 0.0, 1.0);
    const Point closest = {
        start[0] + parameter * direction[0],
        start[1] + parameter * direction[1],
        start[2] + parameter * direction[2],
    };
    return norm(sub(point, closest));
}

static double point_triangle_distance(
    const Point& point, const Triangle& triangle) {
    const Point ab = sub(triangle.b, triangle.a);
    const Point ac = sub(triangle.c, triangle.a);
    const Point ap = sub(point, triangle.a);
    const double d1 = dot(ab, ap);
    const double d2 = dot(ac, ap);
    if (d1 <= 0.0 && d2 <= 0.0) return norm(ap);

    const Point bp = sub(point, triangle.b);
    const double d3 = dot(ab, bp);
    const double d4 = dot(ac, bp);
    if (d3 >= 0.0 && d4 <= d3) return norm(bp);

    const double vc = d1 * d4 - d3 * d2;
    if (vc <= 0.0 && d1 >= 0.0 && d3 <= 0.0) {
        return segment_distance(point, triangle.a, triangle.b);
    }

    const Point cp = sub(point, triangle.c);
    const double d5 = dot(ab, cp);
    const double d6 = dot(ac, cp);
    if (d6 >= 0.0 && d5 <= d6) return norm(cp);

    const double vb = d5 * d2 - d1 * d6;
    if (vb <= 0.0 && d2 >= 0.0 && d6 <= 0.0) {
        return segment_distance(point, triangle.a, triangle.c);
    }

    const double va = d3 * d6 - d5 * d4;
    if (va <= 0.0 && (d4 - d3) >= 0.0 && (d5 - d6) >= 0.0) {
        return segment_distance(point, triangle.b, triangle.c);
    }

    const Point normal = cross(ab, ac);
    const double normal_norm = norm(normal);
    if (!(normal_norm > 1.0e-30)) return std::numeric_limits<double>::infinity();
    return std::abs(dot(normal, ap)) / normal_norm;
}

static py::dict refusal(
    const std::string& reason,
    std::int64_t requested_layers,
    std::size_t output_face_count,
    std::size_t source_face_count) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "reject_native_hex_brep_boundary_receipt";
    result["reason"] = reason;
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = 0;
    result["output_face_count"] = output_face_count;
    result["source_face_count"] = source_face_count;
    result["semantic_bijection"] = false;
    result["mapping_complete"] = false;
    result["positive_geometry"] = false;
    result["writer_order_bound"] = false;
    result["writer_order_sha256"] = "";
    result["mapping_cardinality"] = "unverified";
    result["receipt_sha256"] = "";
    return result;
}

static py::dict audit(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& output_quads,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& source_triangles,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& source_face_ordinals,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& output_to_source_face,
    const py::list& semantic_rows,
    const std::string& source_sha256,
    const std::string& output_sha256,
    std::int64_t requested_layers,
    std::int64_t actual_layers,
    double first_height,
    bool positive_layer,
    bool positive_geometry,
    double distance_tolerance,
    double minimum_normal_cosine,
    const py::object& writer_order,
    const std::string& ingress_certificate_sha256,
    const std::string& semantic_ledger_sha256,
    const std::string& provisioning_manifest_sha256) {
    const std::size_t output_count = output_quads.ndim() == 3
        ? static_cast<std::size_t>(output_quads.shape(0)) : 0U;
    const std::size_t source_triangle_count = source_triangles.ndim() == 3
        ? static_cast<std::size_t>(source_triangles.shape(0)) : 0U;
    const std::size_t source_face_count = semantic_rows.size();
    if (output_quads.ndim() != 3 || output_quads.shape(1) != 4 || output_quads.shape(2) != 3) {
        throw std::invalid_argument("output_quads_must_be_Mx4x3");
    }
    if (source_triangles.ndim() != 3 || source_triangles.shape(1) != 3 || source_triangles.shape(2) != 3) {
        throw std::invalid_argument("source_triangles_must_be_Nx3x3");
    }
    if (output_count == 0U || source_triangle_count == 0U || source_face_count == 0U) {
        return refusal("receipt_geometry_empty", requested_layers, output_count, source_face_count);
    }
    if (source_face_ordinals.ndim() != 1 || static_cast<std::size_t>(source_face_ordinals.shape(0)) != source_triangle_count) {
        return refusal("source_face_ordinal_count_mismatch", requested_layers, output_count, source_face_count);
    }
    if (output_to_source_face.ndim() != 1 || static_cast<std::size_t>(output_to_source_face.shape(0)) != output_count) {
        return refusal("output_face_mapping_count_mismatch", requested_layers, output_count, source_face_count);
    }
    if (!valid_digest(source_sha256) || !valid_digest(output_sha256)) {
        return refusal("receipt_digest_input_invalid", requested_layers, output_count, source_face_count);
    }
    const bool certificate_bound =
        !ingress_certificate_sha256.empty() ||
        !semantic_ledger_sha256.empty() ||
        !provisioning_manifest_sha256.empty();
    if (certificate_bound &&
        (!valid_digest(ingress_certificate_sha256) ||
         !valid_digest(semantic_ledger_sha256) ||
         !valid_digest(provisioning_manifest_sha256))) {
        return refusal("receipt_ingress_digest_input_invalid",
                       requested_layers, output_count, source_face_count);
    }
    if (certificate_bound) {
        const native_hex_semantic::Result semantic =
            native_hex_semantic::build(semantic_rows, source_face_count);
        if (!semantic.accepted) {
            return refusal(semantic.reason, requested_layers, output_count, source_face_count);
        }
        if (semantic.digest != semantic_ledger_sha256) {
            return refusal("semantic_ledger_digest_mismatch",
                           requested_layers, output_count, source_face_count);
        }
    }
    if (requested_layers < 0 || actual_layers != requested_layers) {
        return refusal("receipt_layer_count_mismatch", requested_layers, output_count, source_face_count);
    }
    if (!std::isfinite(distance_tolerance) || distance_tolerance < 0.0 ||
        !std::isfinite(minimum_normal_cosine) || minimum_normal_cosine < 0.0 ||
        minimum_normal_cosine > 1.0) {
        return refusal("receipt_tolerance_invalid", requested_layers, output_count, source_face_count);
    }
    if (requested_layers > 0 && (!positive_layer || !std::isfinite(first_height) || first_height <= 0.0)) {
        return refusal("receipt_positive_boundary_layer_missing", requested_layers, output_count, source_face_count);
    }
    if (!positive_geometry) {
        return refusal("receipt_positive_geometry_missing", requested_layers, output_count, source_face_count);
    }

    auto sources = source_triangles.unchecked<3>();
    auto source_ids = source_face_ordinals.unchecked<1>();
    auto mappings = output_to_source_face.unchecked<1>();
    std::vector<Triangle> triangles;
    triangles.reserve(source_triangle_count);
    for (std::size_t index = 0; index < source_triangle_count; ++index) {
        Triangle triangle{
            {
                sources(static_cast<py::ssize_t>(index), 0, 0),
                sources(static_cast<py::ssize_t>(index), 0, 1),
                sources(static_cast<py::ssize_t>(index), 0, 2),
            },
            {
                sources(static_cast<py::ssize_t>(index), 1, 0),
                sources(static_cast<py::ssize_t>(index), 1, 1),
                sources(static_cast<py::ssize_t>(index), 1, 2),
            },
            {
                sources(static_cast<py::ssize_t>(index), 2, 0),
                sources(static_cast<py::ssize_t>(index), 2, 1),
                sources(static_cast<py::ssize_t>(index), 2, 2),
            },
            source_ids(static_cast<py::ssize_t>(index)),
        };
        if (!std::all_of(triangle.a.begin(), triangle.a.end(), [](double value) { return std::isfinite(value); }) ||
            !std::all_of(triangle.b.begin(), triangle.b.end(), [](double value) { return std::isfinite(value); }) ||
            !std::all_of(triangle.c.begin(), triangle.c.end(), [](double value) { return std::isfinite(value); }) ||
            !(norm(cross(sub(triangle.b, triangle.a), sub(triangle.c, triangle.a))) > 1.0e-30)) {
            return refusal("source_triangle_invalid", requested_layers, output_count, source_face_count);
        }
        if (triangle.ordinal < 0 || static_cast<std::size_t>(triangle.ordinal) >= source_face_count) {
            return refusal("source_face_ordinal_out_of_range", requested_layers, output_count, source_face_count);
        }
        triangles.push_back(triangle);
    }

    for (std::size_t row_index = 0; row_index < source_face_count; ++row_index) {
        py::dict row;
        try {
            row = semantic_rows[static_cast<py::ssize_t>(row_index)].cast<py::dict>();
        } catch (...) {
            return refusal("semantic_row_not_object", requested_layers, output_count, source_face_count);
        }
        for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) {
            if (!row.contains(key) || py::str(row[key]).cast<std::string>().empty()) {
                return refusal(std::string("semantic_field_missing:") + key, requested_layers, output_count, source_face_count);
            }
        }
    }

    auto outputs = output_quads.unchecked<3>();
    std::vector<bool> used(source_face_count, false);
    double maximum_distance = 0.0;
    double minimum_alignment = 1.0;
    std::vector<std::int64_t> mapping_values;
    mapping_values.reserve(output_count);
    for (std::size_t face_index = 0; face_index < output_count; ++face_index) {
        std::array<Point, 4> quad{};
        for (int corner = 0; corner < 4; ++corner) {
            for (int axis = 0; axis < 3; ++axis) {
                quad[static_cast<std::size_t>(corner)][static_cast<std::size_t>(axis)] =
                    outputs(static_cast<py::ssize_t>(face_index), corner, axis);
                if (!std::isfinite(quad[static_cast<std::size_t>(corner)][static_cast<std::size_t>(axis)])) {
                    return refusal("output_quad_nonfinite", requested_layers, output_count, source_face_count);
                }
            }
        }
        const Point normal = cross(sub(quad[1], quad[0]), sub(quad[2], quad[0]));
        const double output_norm = norm(normal);
        if (!(output_norm > 1.0e-30)) {
            return refusal("output_quad_degenerate", requested_layers, output_count, source_face_count);
        }
        const std::int64_t ordinal = mappings(static_cast<py::ssize_t>(face_index));
        if (ordinal < 0 || static_cast<std::size_t>(ordinal) >= source_face_count) {
            return refusal("output_source_face_ordinal_invalid", requested_layers, output_count, source_face_count);
        }
        const Point unit_output = {
            normal[0] / output_norm, normal[1] / output_norm, normal[2] / output_norm,
        };
        const Point centroid = {
            (quad[0][0] + quad[1][0] + quad[2][0] + quad[3][0]) * 0.25,
            (quad[0][1] + quad[1][1] + quad[2][1] + quad[3][1]) * 0.25,
            (quad[0][2] + quad[1][2] + quad[2][2] + quad[3][2]) * 0.25,
        };
        double best_distance = std::numeric_limits<double>::infinity();
        double best_alignment = -1.0;
        for (const Triangle& triangle : triangles) {
            if (triangle.ordinal != ordinal) continue;
            const Point source_normal = cross(sub(triangle.b, triangle.a), sub(triangle.c, triangle.a));
            const double source_norm = norm(source_normal);
            const Point unit_source = {
                source_normal[0] / source_norm, source_normal[1] / source_norm, source_normal[2] / source_norm,
            };
            const double distance = point_triangle_distance(centroid, triangle);
            const double alignment = std::abs(dot(unit_output, unit_source));
            if (distance < best_distance || (distance == best_distance && alignment > best_alignment)) {
                best_distance = distance;
                best_alignment = alignment;
            }
        }
        if (!std::isfinite(best_distance) || best_distance > distance_tolerance ||
            best_alignment < minimum_normal_cosine) {
            return refusal("output_brep_distance_or_normal_failed", requested_layers, output_count, source_face_count);
        }
        used[static_cast<std::size_t>(ordinal)] = true;
        maximum_distance = std::max(maximum_distance, best_distance);
        minimum_alignment = std::min(minimum_alignment, best_alignment);
        mapping_values.push_back(ordinal);
    }
    if (std::any_of(used.begin(), used.end(), [](bool value) { return !value; })) {
        return refusal("source_face_semantic_bijection_incomplete", requested_layers, output_count, source_face_count);
    }

    const bool writer_order_bound = !writer_order.is_none();
    std::string writer_order_sha256;
    if (writer_order_bound) {
        if (!py::isinstance<py::list>(writer_order)) {
            return refusal("writer_order_ledger_not_list", requested_layers, output_count, source_face_count);
        }
        const py::list rows = writer_order.cast<py::list>();
        if (rows.size() != output_count) {
            return refusal("writer_order_count_mismatch", requested_layers, output_count, source_face_count);
        }
        std::set<std::int64_t> writer_orders;
        std::set<std::int64_t> output_face_ids;
        std::string writer_canonical = "native-hex-writer-order-bound-v1|";
        for (std::size_t index = 0; index < output_count; ++index) {
            py::dict row;
            try {
                row = rows[static_cast<py::ssize_t>(index)].cast<py::dict>();
            } catch (...) {
                return refusal("writer_order_row_invalid", requested_layers, output_count, source_face_count);
            }
            for (const char* key : {
                     "writer_order", "output_face_id", "source_mesh_face", "source_face",
                     "feature", "patch", "output_patch", "physical_group", "component",
                     "provenance", "direct"}) {
                if (!row.contains(key)) {
                    return refusal(std::string("writer_order_field_missing:") + key,
                                   requested_layers, output_count, source_face_count);
                }
            }
            try {
                const std::int64_t order = row["writer_order"].cast<std::int64_t>();
                const std::int64_t output_face_id = row["output_face_id"].cast<std::int64_t>();
                const std::int64_t source_mesh_face = row["source_mesh_face"].cast<std::int64_t>();
                const std::int64_t source_face = row["source_face"].cast<std::int64_t>();
                if (order != static_cast<std::int64_t>(index) ||
                    output_face_id < 0 || source_mesh_face < 0 ||
                    source_face < 0 || static_cast<std::size_t>(source_face) >= source_face_count ||
                    !writer_orders.insert(order).second ||
                    !output_face_ids.insert(output_face_id).second ||
                    source_face != mapping_values[index] ||
                    !row["direct"].cast<bool>()) {
                    return refusal("writer_order_binding_mismatch",
                                   requested_layers, output_count, source_face_count);
                }
                const py::dict source_row =
                    semantic_rows[static_cast<py::ssize_t>(source_face)].cast<py::dict>();
                writer_canonical += std::to_string(order) + "|";
                writer_canonical += std::to_string(output_face_id) + "|";
                writer_canonical += std::to_string(source_mesh_face) + "|";
                writer_canonical += std::to_string(source_face) + "|";
                if (py::str(row["output_patch"]).cast<std::string>().empty()) {
                    return refusal("writer_order_output_patch_empty",
                                   requested_layers, output_count, source_face_count);
                }
                writer_canonical += py::str(row["output_patch"]).cast<std::string>() + "|";
                for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) {
                    const std::string output_value = py::str(row[key]).cast<std::string>();
                    const std::string source_value = py::str(source_row[key]).cast<std::string>();
                    if (output_value.empty() || output_value != source_value) {
                        return refusal(std::string("writer_order_semantic_mismatch:") + key,
                                       requested_layers, output_count, source_face_count);
                    }
                    writer_canonical += output_value + "|";
                }
            } catch (...) {
                return refusal("writer_order_field_type_invalid",
                               requested_layers, output_count, source_face_count);
            }
        }
        const std::vector<std::uint8_t> writer_bytes(
            writer_canonical.begin(), writer_canonical.end());
        writer_order_sha256 = brep_evidence::sha256_hex(writer_bytes);
    }

    std::string canonical = certificate_bound
        ? "native-hex-brep-boundary-receipt-v3|"
        : (writer_order_bound
            ? "native-hex-brep-boundary-receipt-v2|"
            : "native-hex-brep-boundary-receipt-v1|");
    canonical += source_sha256 + "|" + output_sha256 + "|";
    if (certificate_bound) {
        canonical += ingress_certificate_sha256 + "|";
        canonical += semantic_ledger_sha256 + "|";
        canonical += provisioning_manifest_sha256 + "|";
    }
    canonical += writer_order_sha256 + "|";
    canonical += std::to_string(requested_layers) + "|" + std::to_string(actual_layers) + "|";
    canonical += std::to_string(maximum_distance) + "|" + std::to_string(minimum_alignment) + "|";
    for (const std::int64_t value : mapping_values) canonical += std::to_string(value) + ",";
    for (std::size_t row_index = 0; row_index < source_face_count; ++row_index) {
        py::dict row = semantic_rows[static_cast<py::ssize_t>(row_index)].cast<py::dict>();
        for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) {
            canonical += py::str(row[key]).cast<std::string>() + "|";
        }
    }
    const std::vector<std::uint8_t> bytes(canonical.begin(), canonical.end());
    py::dict result;
    result["accepted"] = true;
    result["status"] = certificate_bound
        ? "pass_native_hex_brep_boundary_receipt_v3"
        : (writer_order_bound
            ? "pass_native_hex_brep_boundary_receipt_v2"
            : "pass_native_hex_brep_boundary_receipt_v1");
    result["reason"] = "post_bl_brep_boundary_receipt_passed";
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = actual_layers;
    result["output_face_count"] = output_count;
    result["source_face_count"] = source_face_count;
    result["semantic_bijection"] = true;
    result["mapping_complete"] = true;
    result["positive_geometry"] = true;
    result["writer_order_bound"] = writer_order_bound;
    result["writer_order_sha256"] = writer_order_sha256;
    result["mapping_cardinality"] = writer_order_bound
        ? "explicit_many_to_one"
        : "legacy_explicit_source_mapping";
    result["max_brep_distance"] = maximum_distance;
    result["min_normal_alignment"] = minimum_alignment;
    result["receipt_sha256"] = brep_evidence::sha256_hex(bytes);
    result["ingress_certificate_sha256"] = ingress_certificate_sha256;
    result["semantic_ledger_sha256"] = semantic_ledger_sha256;
    result["provisioning_manifest_sha256"] = provisioning_manifest_sha256;
    return result;
}

PYBIND11_MODULE(native_hex_boundary_receipt, module) {
    module.doc() = "C++23 Native Hex post-BL B-Rep boundary receipt";
    module.def(
        "audit_native_hex_brep_boundary",
        &audit,
        py::arg("output_quads"),
        py::arg("source_triangles"),
        py::arg("source_face_ordinals"),
        py::arg("output_to_source_face"),
        py::arg("semantic_rows"),
        py::arg("source_sha256"),
        py::arg("output_sha256"),
        py::arg("requested_layers"),
        py::arg("actual_layers"),
        py::arg("first_height"),
        py::arg("positive_layer"),
        py::arg("positive_geometry"),
        py::arg("distance_tolerance"),
        py::arg("minimum_normal_cosine"),
        py::arg("writer_order") = py::none(),
        py::arg("ingress_certificate_sha256") = "",
        py::arg("semantic_ledger_sha256") = "",
        py::arg("provisioning_manifest_sha256") = "");
}
