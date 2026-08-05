#pragma once

#include "brep_evidence_sha256.hpp"

#include <filesystem>
#include <fstream>
#include <initializer_list>
#include <sstream>
#include <string>
#include <vector>

#include <pybind11/pybind11.h>

namespace autotessell_occt {

namespace fs = std::filesystem;
namespace py = pybind11;

inline bool exists_any(const std::initializer_list<fs::path>& candidates) {
    for (const auto& candidate : candidates) {
        if (fs::is_regular_file(candidate)) return true;
    }
    return false;
}

inline py::dict audit_sdk_manifest(const std::string& sdk_root,
                                   const std::string& runtime_root,
                                   const std::string& expected_occt_version,
                                   const std::string& expected_runtime_package) {
    const fs::path root(sdk_root);
    const fs::path include_a = root / "include" / "opencascade";
    const fs::path include_b = root / "include";
    const fs::path lib_a = root / "lib";
    const fs::path lib_b = root / "lib64";
    const std::vector<std::string> required_names = {
        "BRep_Tool.hxx", "Standard_Version.hxx", "OpenCASCADEConfig.cmake",
        "TKernel", "TKMath", "TKBRep", "TKGeomBase", "TKG2d", "TKTopAlgo",
        "TKXDE", "TKXCAF", "TKSTEP", "TKSTEP209", "TKSTEPAttr", "TKSTEPBase"};
    std::vector<std::string> missing;
    std::vector<std::string> searched;
    searched.push_back(sdk_root.empty() ? "<empty-sdk-root>" : sdk_root);
    if (sdk_root.empty()) {
        missing = required_names;
    } else {
        if (!exists_any({include_a / "BRep_Tool.hxx", include_b / "BRep_Tool.hxx"})) {
            missing.push_back("BRep_Tool.hxx");
        }
        const fs::path version_header_a = include_a / "Standard_Version.hxx";
        const fs::path version_header_b = include_b / "Standard_Version.hxx";
        if (!exists_any({version_header_a, version_header_b})) missing.push_back("Standard_Version.hxx");
        if (!exists_any({
                lib_a / "cmake" / "opencascade" / "OpenCASCADEConfig.cmake",
                lib_a / "cmake" / "opencascade-7.8.1" / "OpenCASCADEConfig.cmake",
                lib_b / "cmake" / "opencascade" / "OpenCASCADEConfig.cmake"})) {
            missing.push_back("OpenCASCADEConfig.cmake");
        }
        for (const auto& name : {"TKernel", "TKMath", "TKBRep", "TKGeomBase", "TKG2d",
                                 "TKTopAlgo", "TKXDE", "TKXCAF", "TKSTEP", "TKSTEP209",
                                 "TKSTEPAttr", "TKSTEPBase"}) {
            const bool found = exists_any({
                lib_a / ("lib" + std::string(name) + ".so"),
                lib_a / ("lib" + std::string(name) + ".so.7"),
                lib_a / (std::string(name) + ".dll"),
                lib_a / (std::string(name) + ".lib"),
                lib_b / ("lib" + std::string(name) + ".so"),
                lib_b / ("lib" + std::string(name) + ".so.7")});
            if (!found) missing.push_back(name);
        }
    }

    bool version_match = expected_occt_version.empty();
    for (const auto& header : {include_a / "Standard_Version.hxx", include_b / "Standard_Version.hxx"}) {
        if (!fs::is_regular_file(header)) continue;
        std::ifstream stream(header);
        const std::string content((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
        version_match = expected_occt_version.empty() || content.find(expected_occt_version) != std::string::npos;
        break;
    }
    if (!version_match) missing.push_back("OCCT-version-mismatch");
    const bool runtime_metadata_complete = !runtime_root.empty() && fs::is_directory(runtime_root) &&
        !expected_runtime_package.empty();
    if (!runtime_metadata_complete) missing.push_back("runtime-package-manifest");
    const bool ready = missing.empty();

    std::ostringstream material;
    material << sdk_root << '\n' << runtime_root << '\n' << expected_occt_version << '\n'
             << expected_runtime_package << '\n' << (version_match ? "version-ok" : "version-bad") << '\n';
    for (const auto& item : missing) material << item << '\n';
    const std::string material_string = material.str();
    const std::vector<std::uint8_t> material_bytes(material_string.begin(), material_string.end());

    py::dict result;
    result["ready"] = ready;
    result["status"] = ready ? "occt_sdk_manifest_ready" : "occt_native_ingress_unavailable";
    result["reason"] = ready ? "sdk_manifest_ready" : "sdk_manifest_incomplete";
    result["sdk_root"] = sdk_root;
    result["runtime_root"] = runtime_root;
    result["expected_occt_version"] = expected_occt_version;
    result["expected_runtime_package"] = expected_runtime_package;
    result["version_match"] = version_match;
    result["runtime_metadata_complete"] = runtime_metadata_complete;
    py::list searched_list;
    for (const auto& item : searched) searched_list.append(item);
    py::list missing_list;
    for (const auto& item : missing) missing_list.append(item);
    result["searched_roots"] = searched_list;
    result["missing_artifacts"] = missing_list;
    result["compiler_abi"] = __VERSION__;
    result["cxx_standard"] = 23;
    result["manifest_digest"] = brep_evidence::sha256_hex(material_bytes);
    return result;
}

}  // namespace autotessell_occt
