// C++23-first Native Hex CAD/B-Rep ingress certificate.
//
// The default build is deliberately fail-closed when an OCCT SDK is not
// supplied.  Python OCP, STL triangles, and the restricted box producer must
// never be silently promoted to this authority route.
#include <pybind11/pybind11.h>

#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

#include "native_hex_occt_manifest.hpp"
#include "native_hex_semantic_ledger.hpp"
#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

#ifdef AUTOTESSELL_HAVE_OCCT
#include <BRep_Tool.hxx>
#include <IFSelect_ReturnStatus.hxx>
#include <Poly_Triangulation.hxx>
#include <STEPCAFControl_Reader.hxx>
#include <Standard_Version.hxx>
#include <TDF_LabelSequence.hxx>
#include <TDocStd_Document.hxx>
#include <TopAbs.hxx>
#include <TopExp.hxx>
#include <TopExp_Explorer.hxx>
#include <TopTools_IndexedMapOfShape.hxx>
#include <TopLoc_Location.hxx>
#include <XCAFApp_Application.hxx>
#include <XCAFDoc_DocumentTool.hxx>
#include <XCAFDoc_ShapeTool.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Face.hxx>
#include <TopoDS_Shape.hxx>
#endif

namespace py = pybind11;

static std::string hex_file_sha256(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) return {};
    std::vector<std::uint8_t> bytes(
        (std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
    return brep_evidence::sha256_hex(bytes);
}

static py::dict refusal(
    const std::string& reason,
    const std::string& step_sha256,
    const std::string& sdk_root) {
    py::dict out;
    out["accepted"] = false;
    out["authoritative"] = false;
    out["status"] = "native_hex_occt_xde_ingress_refused";
    out["reason"] = reason;
    out["step_sha256"] = step_sha256;
    out["sdk_root"] = sdk_root;
    out["compiled_with_occt"] =
#ifdef AUTOTESSELL_HAVE_OCCT
        true;
#else
        false;
#endif
    out["candidate_discarded"] = true;
    out["publication_eligible"] = false;
    return out;
}

static py::dict read_step_xde(
    const std::string& step_path,
    const std::string& sdk_root,
    const std::string& expected_occt_version,
    const std::string& expected_abi,
    const py::list& semantic_rows,
    const std::string& expected_compiler_abi,
    const std::string& expected_build_identity,
    const std::string& provisioning_manifest_path) {
    const std::filesystem::path path(step_path);
    if (!std::filesystem::is_regular_file(path) || std::filesystem::is_symlink(path)) {
        return refusal("step_file_missing_or_symlink", {}, sdk_root);
    }
    const std::string step_sha256 = hex_file_sha256(path);
    if (step_sha256.empty()) return refusal("step_file_unreadable", {}, sdk_root);

#ifndef AUTOTESSELL_HAVE_OCCT
    (void)expected_occt_version;
    (void)expected_abi;
    (void)expected_compiler_abi;
    (void)expected_build_identity;
    (void)provisioning_manifest_path;
    (void)semantic_rows;
    if (sdk_root.empty()) return refusal("occt_sdk_unavailable", step_sha256, sdk_root);
    return refusal("occt_sdk_not_linked_or_manifest_mismatch", step_sha256, sdk_root);
#else
    if (sdk_root.empty()) return refusal("occt_sdk_root_required", step_sha256, sdk_root);
    const std::string compiled_version = OCC_VERSION_COMPLETE;
    if (!expected_occt_version.empty() && expected_occt_version != compiled_version) {
        return refusal("occt_version_mismatch", step_sha256, sdk_root);
    }
    if (!expected_abi.empty() && expected_abi != "occt-" + compiled_version) {
        return refusal("occt_abi_mismatch", step_sha256, sdk_root);
    }
    const std::string manifest_path = provisioning_manifest_path.empty()
        ? (std::filesystem::path(sdk_root) /
           "autotessell_native_hex_occt_provisioning.manifest").string()
        : provisioning_manifest_path;
    const native_hex_occt_manifest::Result manifest =
        native_hex_occt_manifest::audit(
            sdk_root, manifest_path, expected_occt_version, expected_abi,
            expected_compiler_abi, expected_build_identity);
    if (!manifest.accepted) {
        return refusal(
            "occt_provisioning_manifest_refused:" + manifest.reason,
            step_sha256, sdk_root);
    }

    try {
        Handle(XCAFApp_Application) application = XCAFApp_Application::GetApplication();
        Handle(TDocStd_Document) document;
        application->NewDocument("MDTV-XCAF", document);
        STEPCAFControl_Reader reader;
        reader.SetNameMode(true);
        reader.SetColorMode(true);
        reader.SetLayerMode(true);
        if (reader.Read(step_path.c_str()) != IFSelect_RetDone) {
            return refusal("stepcaf_read_failed", step_sha256, sdk_root);
        }
        if (!reader.Transfer(document)) {
            return refusal("stepcaf_transfer_failed", step_sha256, sdk_root);
        }
        Handle(XCAFDoc_ShapeTool) shape_tool = XCAFDoc_DocumentTool::ShapeTool(document->Main());
        TDF_LabelSequence roots;
        shape_tool->GetFreeShapes(roots);
        TopTools_IndexedMapOfShape faces;
        for (Standard_Integer index = 1; index <= roots.Length(); ++index) {
            const TopoDS_Shape root = shape_tool->GetShape(roots.Value(index));
            TopExp::MapShapes(root, TopAbs_FACE, faces);
        }
        if (faces.IsEmpty()) return refusal("brep_has_no_faces", step_sha256, sdk_root);
        const native_hex_semantic::Result semantic =
            native_hex_semantic::build(semantic_rows, static_cast<std::size_t>(faces.Extent()));
        if (!semantic.accepted) {
            return refusal(semantic.reason, step_sha256, sdk_root);
        }

        std::ostringstream face_stream;
        std::ostringstream triangulation_stream;
        py::list face_records;
        for (Standard_Integer index = 1; index <= faces.Extent(); ++index) {
            const TopoDS_Face face = TopoDS::Face(faces(index));
            std::int64_t edge_count = 0;
            for (TopExp_Explorer edge(face, TopAbs_EDGE); edge.More(); edge.Next()) {
                ++edge_count;
            }
            TopLoc_Location location;
            const Handle(Poly_Triangulation) triangulation =
                BRep_Tool::Triangulation(face, location);
            const std::int64_t triangle_count = triangulation.IsNull()
                ? 0
                : static_cast<std::int64_t>(triangulation->NbTriangles());
            face_stream << index - 1 << ':' << static_cast<int>(face.Orientation())
                        << ':' << edge_count << ':' << triangle_count << ';';
            triangulation_stream << index - 1 << ':' << triangle_count << ':';
            if (!triangulation.IsNull()) {
                for (Standard_Integer node = 1; node <= triangulation->NbNodes(); ++node) {
                    const auto point = triangulation->Node(node).Transformed(location);
                    triangulation_stream << std::setprecision(17)
                                         << point.X() << ',' << point.Y() << ',' << point.Z()
                                         << ';';
                }
                for (Standard_Integer triangle = 1;
                     triangle <= triangulation->NbTriangles(); ++triangle) {
                    const auto indices = triangulation->Triangle(triangle);
                    triangulation_stream << indices.Value(1) << ',' << indices.Value(2)
                                         << ',' << indices.Value(3) << ';';
                }
            }
            py::dict record = semantic_rows[index - 1].cast<py::dict>();
            record["source_face"] = index - 1;
            record["orientation"] = static_cast<int>(face.Orientation());
            record["edge_count"] = edge_count;
            record["triangle_count"] = triangle_count;
            record["direct"] = true;
            face_records.append(record);
        }
        const std::string face_stream_text = face_stream.str();
        const std::string triangulation_stream_text = triangulation_stream.str();
        const std::vector<std::uint8_t> face_bytes(
            face_stream_text.begin(), face_stream_text.end());
        const std::vector<std::uint8_t> triangulation_bytes(
            triangulation_stream_text.begin(), triangulation_stream_text.end());
        const std::string face_sha256 = brep_evidence::sha256_hex(face_bytes);
        const std::string triangulation_sha256 =
            brep_evidence::sha256_hex(triangulation_bytes);
        const std::string certificate_input =
            step_sha256 + '|' + compiled_version + "|occt-" + compiled_version + '|'
            + face_sha256 + '|' + triangulation_sha256 + '|'
            + semantic.digest + '|' + manifest.manifest_sha256 + '|'
            + std::to_string(faces.Extent());
        const std::vector<std::uint8_t> certificate_bytes(
            certificate_input.begin(), certificate_input.end());
        py::dict out;
        out["accepted"] = true;
        out["authoritative"] = true;
        out["status"] = "native_hex_occt_xde_ingress_passed";
        out["step_sha256"] = step_sha256;
        out["occt_version"] = compiled_version;
        out["occt_abi"] = "occt-" + compiled_version;
        out["face_count"] = faces.Extent();
        out["face_stream_sha256"] = face_sha256;
        out["triangulation_stream_sha256"] = triangulation_sha256;
        out["semantic_ledger_sha256"] = semantic.digest;
        out["occt_provisioning_manifest_sha256"] = manifest.manifest_sha256;
        out["certificate_sha256"] = brep_evidence::sha256_hex(certificate_bytes);
        out["face_records"] = face_records;
        out["candidate_discarded"] = false;
        out["publication_eligible"] = false;
        return out;
    } catch (const std::exception& error) {
        return refusal(std::string("occt_exception:") + error.what(), step_sha256, sdk_root);
    }
#endif
}

PYBIND11_MODULE(native_hex_occt_xde_ingress, module) {
    module.doc() = "Fail-closed Native Hex OCCT/XDE CAD ingress certificate";
    module.def(
        "audit_provisioning_manifest",
        [](const std::string& sdk_root,
           const std::string& manifest_path,
           const std::string& expected_occt_version,
           const std::string& expected_abi,
           const std::string& expected_compiler_abi,
           const std::string& expected_build_identity) {
            return native_hex_occt_manifest::as_dict(
                native_hex_occt_manifest::audit(
                    sdk_root, manifest_path, expected_occt_version,
                    expected_abi, expected_compiler_abi, expected_build_identity),
#ifdef AUTOTESSELL_HAVE_OCCT
                true
#else
                false
#endif
            );
        },
        py::arg("sdk_root"),
        py::arg("manifest_path"),
        py::arg("expected_occt_version") = "",
        py::arg("expected_abi") = "",
        py::arg("expected_compiler_abi") = "",
        py::arg("expected_build_identity") = "");
    module.def(
        "semantic_ledger_digest",
        [](const py::list& rows) {
            return native_hex_semantic::as_dict(
                native_hex_semantic::build(rows, static_cast<std::size_t>(rows.size())));
        },
        py::arg("semantic_rows"));
    module.def(
        "read_step_xde",
        &read_step_xde,
        py::arg("step_path"),
        py::arg("sdk_root") = "",
        py::arg("expected_occt_version") = "",
        py::arg("expected_abi") = "",
        py::arg("semantic_rows") = py::list(),
        py::arg("expected_compiler_abi") = "",
        py::arg("expected_build_identity") = "",
        py::arg("provisioning_manifest_path") = "");
}
