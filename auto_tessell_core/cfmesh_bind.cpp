// pybind11 binding for vendored cfMesh + OpenFOAM (third_party/cfmesh, GPL-3).
// Authored for AutoTessell.
//
// Approach: instead of binding the cfMesh class API in-process (which requires
// reproducing OpenFOAM's argList/Time setup machinery), we call the already-
// built standalone cartesianMesh / tetMesh / pMesh executables via popen on
// a prepared OpenFOAM case directory.  This is the simplest, most stable
// in-tree wiring: AutoTessell stays free of OpenFOAM runtime objects, and the
// vendored exes do exactly what an external `cartesianMesh -case <dir>` call
// would do — but with no external OpenFOAM installation required.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <stdexcept>

namespace py = pybind11;
namespace fs = std::filesystem;

namespace {

std::string vendor_bin_dir()
{
    if (const char* env = std::getenv("AUTO_TESSELL_CFMESH_BIN_DIR")) {
        return std::string(env);
    }
    fs::path here = fs::canonical("/proc/self/exe").parent_path();
    fs::path cand = here.parent_path() / "third_party" / "cfmesh" / "build";
    if (fs::exists(cand)) return cand.string();
    return std::string();
}

std::string find_exe(const std::string& name)
{
    if (auto dir = vendor_bin_dir(); !dir.empty()) {
        fs::path p = fs::path(dir) / name;
        if (fs::exists(p)) return p.string();
    }
    fs::path src_root = fs::path(__FILE__).parent_path().parent_path();
    fs::path cand = src_root / "third_party" / "cfmesh" / "build" / name;
    if (fs::exists(cand)) return cand.string();
    return name;  // hope it's in PATH
}

void write_dict(const fs::path& p, const std::string& body)
{
    std::ofstream f(p);
    f << body;
}

void write_control_dict(const fs::path& case_dir, const std::string& app)
{
    std::ostringstream oss;
    oss << "FoamFile { version 2.0; format ascii; class dictionary; "
        << "object controlDict; }\n"
        << "application " << app << ";\n"
        << "startFrom startTime; startTime 0; stopAt endTime; endTime 1;\n"
        << "deltaT 1; writeControl runTime; writeInterval 1;\n";
    write_dict(case_dir / "system" / "controlDict", oss.str());
}

void write_mesh_dict_cartesian(const fs::path& case_dir,
                               const std::string& stl_relpath,
                               double max_cell_size,
                               double min_cell_size,
                               double boundary_cell_size,
                               int bl_n_layers,
                               double bl_thickness_ratio,
                               double bl_max_first_layer,
                               double feature_angle_deg,
                               bool keep_cells_intersecting_boundary)
{
    // BETA2846 — surface 보존을 위한 완전한 meshDict.
    // 핵심: maxCellSize 만으로는 STL feature 보존 X. minCellSize +
    // boundaryCellSize + keepCellsIntersectingBoundary + localRefinement 가
    // 함께 있어야 cfMesh 가 input surface 충실도 유지.
    std::ostringstream oss;
    oss << "FoamFile { version 2.0; format ascii; class dictionary; "
        << "object meshDict; }\n"
        << "surfaceFile \"" << stl_relpath << "\";\n"
        << "maxCellSize " << max_cell_size << ";\n";
    if (min_cell_size > 0.0) {
        oss << "minCellSize " << min_cell_size << ";\n";
    }
    if (boundary_cell_size > 0.0) {
        oss << "boundaryCellSize " << boundary_cell_size << ";\n";
    }
    // Surface 가까이의 cell 을 항상 유지 → boundary 정확도 향상.
    oss << "keepCellsIntersectingBoundary "
        << (keep_cells_intersecting_boundary ? 1 : 0) << ";\n";
    // BETA2851 — cfMesh quality settings 완화 (BETA2848 너무 aggressive).
    // 기본값을 cfMesh 자체 default 에 가깝게 → 비현실적 smoothing 반복으로 인한
    // 시간 폭증 방지. evaluator 임계는 이미 90° 까지 허용.
    oss << "meshQualitySettings\n{\n"
        << "    maxNonOrthogonality 65;\n"
        << "    maxBoundarySkewness 20;\n"
        << "    maxInternalSkewness 4;\n"
        << "    maxConcave         85;\n"
        << "    minVol             1e-13;\n"
        << "    minDeterminant     0.001;\n"
        << "    minFaceWeight      0.02;\n"
        << "    minVolRatio        0.01;\n"
        << "    minTwist           0.02;\n"
        << "}\n";
    // Surface refinement 는 user 가 명시적으로 boundary_cell_size 를 설정한
    // 경우만 적용. default (0) 시 cfMesh 가 maxCellSize 로 균일 sizing.
    if (boundary_cell_size > 0.0) {
        oss << "surfaceMeshRefinement\n{\n"
            << "    surface\n    {\n"
            << "        surfaceFile \"" << stl_relpath << "\";\n"
            << "        cellSize " << boundary_cell_size << ";\n"
            << "    }\n}\n";
    }
    // edgeMeshRefinement 는 별도 .eMesh 파일 필요 (surfaceFeatureEdges 로 생성).
    // 자동 생성 없으면 생략 — surfaceMeshRefinement 와 keepCellsIntersectingBoundary
    // 만으로도 cube 같은 단순 형상은 충분.
    if (bl_n_layers > 0) {
        oss << "boundaryLayers\n{\n"
            << "    nLayers " << bl_n_layers << ";\n"
            << "    thicknessRatio " << bl_thickness_ratio << ";\n";
        if (bl_max_first_layer > 0.0) {
            oss << "    maxFirstLayerThickness " << bl_max_first_layer << ";\n";
        }
        oss << "    optimiseLayer 1;\n"
            << "    optimisationParameters\n    {\n"
            << "        nSmoothNormals 3;\n"
            << "        maxNumIterations 5;\n"
            << "        featureSizeFactor 0.4;\n"
            << "        relThicknessTol 0.1;\n"
            << "    }\n}\n";
    }
    write_dict(case_dir / "system" / "meshDict", oss.str());
}

bool run_exe(const std::string& exe_path, const fs::path& case_dir,
             std::string& out_log)
{
    std::ostringstream cmd;
    cmd << "cd \"" << case_dir.string() << "\" && "
        << "\"" << exe_path << "\" 2>&1";
    FILE* pipe = popen(cmd.str().c_str(), "r");
    if (!pipe) return false;
    std::ostringstream log;
    char buf[1024];
    while (fgets(buf, sizeof(buf), pipe)) {
        log << buf;
    }
    int rc = pclose(pipe);
    out_log = log.str();
    return WIFEXITED(rc) && WEXITSTATUS(rc) == 0;
}

py::dict cartesian_mesh_impl(
    const std::string& stl_path,
    const std::string& case_dir_str,
    double max_cell_size,
    double min_cell_size,
    double boundary_cell_size,
    int bl_n_layers,
    double bl_thickness_ratio,
    double bl_max_first_layer,
    double feature_angle_deg,
    bool keep_cells_intersecting_boundary)
{
    fs::path case_dir = fs::absolute(case_dir_str);
    fs::create_directories(case_dir / "system");
    fs::create_directories(case_dir / "constant" / "triSurface");
    fs::create_directories(case_dir / "constant" / "polyMesh");

    fs::path stl_dst = case_dir / "constant" / "triSurface" /
                       fs::path(stl_path).filename();
    if (fs::absolute(stl_path) != stl_dst) {
        fs::copy_file(stl_path, stl_dst,
                      fs::copy_options::overwrite_existing);
    }

    write_control_dict(case_dir, "cartesianMesh");
    write_mesh_dict_cartesian(
        case_dir, "constant/triSurface/" + fs::path(stl_path).filename().string(),
        max_cell_size, min_cell_size, boundary_cell_size,
        bl_n_layers, bl_thickness_ratio, bl_max_first_layer,
        feature_angle_deg, keep_cells_intersecting_boundary);

    std::string exe = find_exe("cartesianMesh");
    std::string log;
    bool ok = run_exe(exe, case_dir, log);

    py::dict r;
    r["success"] = ok;
    r["log"] = log;
    r["case_dir"] = case_dir.string();
    r["polymesh_dir"] = (case_dir / "constant" / "polyMesh").string();
    r["exe_path"] = exe;
    return r;
}

py::dict tet_mesh_impl(
    const std::string& stl_path,
    const std::string& case_dir_str,
    double max_cell_size,
    double min_cell_size,
    double boundary_cell_size,
    int bl_n_layers,
    double bl_thickness_ratio,
    double bl_max_first_layer,
    double feature_angle_deg,
    bool keep_cells_intersecting_boundary)
{
    fs::path case_dir = fs::absolute(case_dir_str);
    fs::create_directories(case_dir / "system");
    fs::create_directories(case_dir / "constant" / "triSurface");
    fs::create_directories(case_dir / "constant" / "polyMesh");

    fs::path stl_dst = case_dir / "constant" / "triSurface" /
                       fs::path(stl_path).filename();
    if (fs::absolute(stl_path) != stl_dst) {
        fs::copy_file(stl_path, stl_dst,
                      fs::copy_options::overwrite_existing);
    }

    write_control_dict(case_dir, "tetMesh");
    write_mesh_dict_cartesian(
        case_dir, "constant/triSurface/" + fs::path(stl_path).filename().string(),
        max_cell_size, min_cell_size, boundary_cell_size,
        bl_n_layers, bl_thickness_ratio, bl_max_first_layer,
        feature_angle_deg, keep_cells_intersecting_boundary);

    std::string exe = find_exe("tetMesh");
    std::string log;
    bool ok = run_exe(exe, case_dir, log);

    py::dict r;
    r["success"] = ok;
    r["log"] = log;
    r["case_dir"] = case_dir.string();
    r["polymesh_dir"] = (case_dir / "constant" / "polyMesh").string();
    r["exe_path"] = exe;
    return r;
}

py::dict poly_mesh_impl(
    const std::string& stl_path,
    const std::string& case_dir_str,
    double max_cell_size,
    double min_cell_size,
    double boundary_cell_size,
    int bl_n_layers,
    double bl_thickness_ratio,
    double bl_max_first_layer,
    double feature_angle_deg,
    bool keep_cells_intersecting_boundary)
{
    fs::path case_dir = fs::absolute(case_dir_str);
    fs::create_directories(case_dir / "system");
    fs::create_directories(case_dir / "constant" / "triSurface");
    fs::create_directories(case_dir / "constant" / "polyMesh");

    fs::path stl_dst = case_dir / "constant" / "triSurface" /
                       fs::path(stl_path).filename();
    if (fs::absolute(stl_path) != stl_dst) {
        fs::copy_file(stl_path, stl_dst,
                      fs::copy_options::overwrite_existing);
    }

    write_control_dict(case_dir, "pMesh");
    write_mesh_dict_cartesian(
        case_dir, "constant/triSurface/" + fs::path(stl_path).filename().string(),
        max_cell_size, min_cell_size, boundary_cell_size,
        bl_n_layers, bl_thickness_ratio, bl_max_first_layer,
        feature_angle_deg, keep_cells_intersecting_boundary);

    std::string exe = find_exe("pMesh");
    std::string log;
    bool ok = run_exe(exe, case_dir, log);

    py::dict r;
    r["success"] = ok;
    r["log"] = log;
    r["case_dir"] = case_dir.string();
    r["polymesh_dir"] = (case_dir / "constant" / "polyMesh").string();
    r["exe_path"] = exe;
    return r;
}

}  // namespace

PYBIND11_MODULE(cfmesh_native, m) {
    m.doc() = "AutoTessell vendored cfMesh bindings (GPL-3.0).";
    m.def("cartesian_mesh", &cartesian_mesh_impl,
          py::arg("stl_path"), py::arg("case_dir"),
          py::arg("max_cell_size") = 0.2,
          py::arg("min_cell_size") = 0.0,
          py::arg("boundary_cell_size") = 0.0,
          py::arg("bl_n_layers") = 0,
          py::arg("bl_thickness_ratio") = 1.2,
          py::arg("bl_max_first_layer") = 0.0,
          py::arg("feature_angle_deg") = 30.0,
          py::arg("keep_cells_intersecting_boundary") = true,
          "Run vendored cfMesh cartesianMesh (hex-dominant) — surface preservation + optional BL.");
    m.def("tet_mesh", &tet_mesh_impl,
          py::arg("stl_path"), py::arg("case_dir"),
          py::arg("max_cell_size") = 0.2,
          py::arg("min_cell_size") = 0.0,
          py::arg("boundary_cell_size") = 0.0,
          py::arg("bl_n_layers") = 0,
          py::arg("bl_thickness_ratio") = 1.2,
          py::arg("bl_max_first_layer") = 0.0,
          py::arg("feature_angle_deg") = 30.0,
          py::arg("keep_cells_intersecting_boundary") = true,
          "Run vendored cfMesh tetMesh (Delaunay) — surface preservation + optional BL.");
    m.def("poly_mesh", &poly_mesh_impl,
          py::arg("stl_path"), py::arg("case_dir"),
          py::arg("max_cell_size") = 0.2,
          py::arg("min_cell_size") = 0.0,
          py::arg("boundary_cell_size") = 0.0,
          py::arg("bl_n_layers") = 0,
          py::arg("bl_thickness_ratio") = 1.2,
          py::arg("bl_max_first_layer") = 0.0,
          py::arg("feature_angle_deg") = 30.0,
          py::arg("keep_cells_intersecting_boundary") = true,
          "Run vendored cfMesh pMesh (polyhedral) — surface preservation + optional BL.");
}
