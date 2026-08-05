// C++23 private consumer for an actual surface-to-Tet boundary receipt.
// It validates the receipt against read-back Tet boundary triangles; it does not publish a route.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <map>
#include <set>
#include <stdexcept>
#include <string>

namespace py = pybind11;
using Face = std::array<std::int64_t, 3>;

namespace {

std::string text(const py::dict& row, const char* key) {
    if (!row.contains(key) || row[key].is_none()) return {};
    return py::str(row[key]).cast<std::string>();
}

py::dict refuse(const char* reason, std::int64_t requested) {
    py::dict out;
    out["accepted"] = false;
    out["status"] = "surface_tet_boundary_receipt_rollback";
    out["reason"] = reason;
    out["requested_layers"] = requested;
    out["actual_layers"] = 0;
    out["runtime_route"] = "default_off";
    out["publication_eligible"] = false;
    out["candidate_discarded"] = true;
    out["atomic_rollback"] = true;
    return out;
}

Face face_from(const py::handle& value) {
    if (!py::isinstance<py::sequence>(value)) throw std::invalid_argument("face_vertices_sequence");
    const py::sequence row = py::reinterpret_borrow<py::sequence>(value);
    if (py::len(row) != 3) throw std::invalid_argument("face_vertices_width");
    Face face{py::cast<std::int64_t>(row[0]), py::cast<std::int64_t>(row[1]), py::cast<std::int64_t>(row[2])};
    std::sort(face.begin(), face.end());
    return face;
}

bool sealed(const py::dict& receipt) {
    return receipt.contains("accepted") && receipt["accepted"].cast<bool>() &&
           receipt.contains("receipt_sealed") && receipt["receipt_sealed"].cast<bool>() &&
           (text(receipt, "runtime_route") == "default_off" ||
            text(receipt, "runtime_route") == "native_tet_production_receipt") &&
           !text(receipt, "source_sha256").empty();
}

bool semantic_row_complete(const py::dict& row) {
    for (const char* key : {"source_face", "output_face", "feature", "patch", "physical_group", "component", "provenance"})
        if (text(row, key).empty()) return false;
    return row.contains("triangle") && !row["triangle"].is_none();
}

py::dict consume(const py::dict& surface_receipt, const py::list& boundary_binding,
                 const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tet_boundary_faces,
                 std::int64_t requested_layers) {
    if (requested_layers < 0) return refuse("negative_layer_count", requested_layers);
    if (!sealed(surface_receipt)) return refuse("surface_receipt_incomplete", requested_layers);
    if (tet_boundary_faces.ndim() != 2 || tet_boundary_faces.shape(1) != 3) throw std::invalid_argument("tet_boundary_faces must be Fx3");
    if (!surface_receipt.contains("interface_triangles") || !py::isinstance<py::list>(surface_receipt["interface_triangles"])) return refuse("surface_interface_missing", requested_layers);
    const py::list interfaces = surface_receipt["interface_triangles"].cast<py::list>();
    if (requested_layers > 0 && interfaces.empty()) return refuse("surface_interface_missing", requested_layers);

    std::set<Face> actual_faces;
    const auto* face_data = tet_boundary_faces.data();
    for (py::ssize_t i = 0; i < tet_boundary_faces.shape(0); ++i) {
        const std::size_t o = static_cast<std::size_t>(i) * 3U;
        Face face{face_data[o], face_data[o + 1U], face_data[o + 2U]};
        std::sort(face.begin(), face.end());
        if (!actual_faces.insert(face).second)
            return refuse("duplicate_tet_boundary_face", requested_layers);
    }

    std::map<std::string, py::dict> by_output;
    std::set<Face> interface_faces;
    for (const py::handle& value : interfaces) {
        if (!py::isinstance<py::dict>(value)) return refuse("surface_interface_row_invalid", requested_layers);
        const py::dict row = value.cast<py::dict>();
        if (!semantic_row_complete(row)) return refuse("surface_interface_semantics_incomplete", requested_layers);
        const std::string output = text(row, "output_face");
        if (!by_output.emplace(output, row).second) return refuse("duplicate_surface_interface", requested_layers);
        try {
            if (!interface_faces.insert(face_from(row["triangle"])).second) return refuse("duplicate_surface_interface_triangle", requested_layers);
        } catch (...) { return refuse("surface_interface_triangle_invalid", requested_layers); }
    }
    if (boundary_binding.size() != interfaces.size()) return refuse("surface_tet_binding_count_mismatch", requested_layers);
    std::set<std::string> bound_outputs;
    std::set<Face> bound_faces;
    for (const py::handle& value : boundary_binding) {
        if (!py::isinstance<py::dict>(value)) return refuse("tet_boundary_binding_row_invalid", requested_layers);
        const py::dict row = value.cast<py::dict>();
        for (const char* key : {"source_face", "output_face", "volume_boundary_face", "feature", "patch", "physical_group", "component", "provenance"})
            if (text(row, key).empty()) return refuse("tet_boundary_binding_semantics_incomplete", requested_layers);
        const std::string output = text(row, "output_face");
        const auto it = by_output.find(output);
        if (it == by_output.end() || !bound_outputs.insert(output).second) return refuse("tet_boundary_interface_binding_mismatch", requested_layers);
        for (const char* key : {"source_face", "feature", "patch", "physical_group", "component", "provenance"})
            if (text(row, key) != text(it->second, key)) return refuse("tet_boundary_semantic_mismatch", requested_layers);
        Face volume_face{};
        try { volume_face = face_from(row["volume_face_vertices"]); }
        catch (...) { return refuse("tet_boundary_face_vertices_invalid", requested_layers); }
        if (!actual_faces.contains(volume_face) || !bound_faces.insert(volume_face).second) return refuse("tet_boundary_face_readback_mismatch", requested_layers);
        if (!interface_faces.contains(face_from(it->second["triangle"]))) return refuse("surface_interface_triangle_missing", requested_layers);
        if (volume_face != face_from(it->second["triangle"])) return refuse("tet_boundary_interface_geometry_mismatch", requested_layers);
    }
    if (bound_outputs.size() != by_output.size()) return refuse("surface_tet_binding_incomplete", requested_layers);
    if (requested_layers == 0) {
        if (actual_faces.size() != bound_faces.size()) return refuse("tet_boundary_source_boundary_set_mismatch", requested_layers);
        for (const Face& face : actual_faces)
            if (!bound_faces.contains(face)) return refuse("tet_boundary_source_boundary_set_mismatch", requested_layers);
    }
    const std::string route = text(surface_receipt, "runtime_route");
    py::dict out;
    out["accepted"] = true;
    out["status"] = "surface_tet_boundary_receipt_consumed";
    out["reason"] = "actual_tet_boundary_receipt_verified";
    out["requested_layers"] = requested_layers;
    out["actual_layers"] = requested_layers;
    out["runtime_route"] = route;
    out["publication_eligible"] = false;
    out["candidate_discarded"] = false;
    out["atomic_rollback"] = false;
    out["source_sha256"] = text(surface_receipt, "source_sha256");
    out["source_face_count"] = surface_receipt.contains("canonical_source_faces") ? py::len(surface_receipt["canonical_source_faces"]) : 0;
    out["interface_count"] = interfaces.size();
    out["tet_boundary_face_count"] = tet_boundary_faces.shape(0);
    out["receipt_digest"] = text(surface_receipt, "receipt_digest") + "|tet-boundary|" + std::to_string(bound_outputs.size());
    return out;
}

py::dict validate_ingress(
    const py::dict& surface_receipt,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& source_vertices,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& source_faces,
    std::int64_t requested_layers) {
    if (requested_layers < 0) return refuse("negative_layer_count", requested_layers);
    if (!sealed(surface_receipt)) return refuse("surface_receipt_incomplete", requested_layers);
    if (requested_layers > 0 &&
        (!surface_receipt.contains("positive_bl_volume_partition_available") ||
         !surface_receipt["positive_bl_volume_partition_available"].cast<bool>()))
        return refuse("positive_bl_volume_partition_unavailable", requested_layers);
    if (!surface_receipt.contains("canonical_source_vertices") ||
        !surface_receipt.contains("canonical_source_faces"))
        return refuse("surface_receipt_canonical_geometry_missing", requested_layers);
    const auto expected_vertices = py::array_t<double, py::array::c_style | py::array::forcecast>::ensure(
        surface_receipt["canonical_source_vertices"]);
    const auto expected_faces = py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>::ensure(
        surface_receipt["canonical_source_faces"]);
    if (!expected_vertices || !expected_faces) return refuse("surface_receipt_canonical_geometry_invalid", requested_layers);
    if (source_vertices.ndim() != 2 || source_vertices.shape(1) != 3 ||
        expected_vertices.ndim() != 2 || expected_vertices.shape(1) != 3 ||
        source_faces.ndim() != 2 || source_faces.shape(1) != 3 ||
        expected_faces.ndim() != 2 || expected_faces.shape(1) != 3)
        return refuse("surface_receipt_canonical_geometry_shape", requested_layers);
    if (source_vertices.shape(0) != expected_vertices.shape(0) ||
        source_faces.shape(0) != expected_faces.shape(0))
        return refuse("surface_receipt_canonical_geometry_count_mismatch", requested_layers);
    const auto n_vertices = static_cast<std::size_t>(source_vertices.size());
    const auto n_faces = static_cast<std::size_t>(source_faces.size());
    if (!std::equal(source_vertices.data(), source_vertices.data() + n_vertices, expected_vertices.data()) ||
        !std::equal(source_faces.data(), source_faces.data() + n_faces, expected_faces.data()))
        return refuse("surface_receipt_canonical_geometry_mismatch", requested_layers);
    py::dict out;
    out["accepted"] = true;
    out["status"] = "surface_tet_boundary_receipt_ingress_locked";
    out["reason"] = "authoritative_surface_receipt_ingress_verified";
    out["requested_layers"] = requested_layers;
    out["actual_layers"] = requested_layers;
    out["runtime_route"] = "native_tet_production_receipt";
    out["publication_eligible"] = false;
    out["candidate_discarded"] = false;
    out["atomic_rollback"] = false;
    out["source_sha256"] = text(surface_receipt, "source_sha256");
    out["receipt_digest"] = text(surface_receipt, "receipt_digest");
    out["source_point_count"] = source_vertices.shape(0);
    out["source_face_count"] = source_faces.shape(0);
    return out;
}

}  // namespace

PYBIND11_MODULE(native_tet_surface_boundary_receipt_consumer, module) {
    module.doc() = "Private C++23 actual surface-to-Tet boundary receipt consumer";
    module.def("consume_surface_boundary_receipt", &consume, py::arg("surface_receipt"), py::arg("boundary_binding"),
               py::arg("tet_boundary_faces"), py::arg("requested_layers"));
    module.def("validate_surface_boundary_receipt_ingress", &validate_ingress,
               py::arg("surface_receipt"), py::arg("source_vertices"), py::arg("source_faces"),
               py::arg("requested_layers"));
}
