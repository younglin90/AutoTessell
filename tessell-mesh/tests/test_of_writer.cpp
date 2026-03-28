#include <doctest/doctest.h>

#include <tessell/mesh2d.hpp>
#include <tessell/of_writer.hpp>

#include <filesystem>
#include <fstream>
#include <sstream>

namespace fs = std::filesystem;
using namespace tessell;

// ──────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────

static std::string read_file(const fs::path& p) {
    std::ifstream f(p);
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static bool file_exists(const fs::path& p) {
    return fs::exists(p) && fs::is_regular_file(p);
}

// ──────────────────────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────────────────────

TEST_CASE("2D → OpenFOAM: required files are created") {
    auto tmp = fs::temp_directory_path() / "tessell_test_of";
    fs::remove_all(tmp);
    fs::create_directories(tmp);

    std::vector<Vec2> square = {{0,0},{1,0},{1,1},{0,1}};
    auto mesh = triangulate_2d(square);

    OFWriteOptions opts;
    opts.extrude_2d        = true;
    opts.extrude_thickness = 0.1;
    write_openfoam_2d(tmp.string(), mesh, opts);

    fs::path poly = tmp / "constant" / "polyMesh";
    CHECK(file_exists(poly / "points"));
    CHECK(file_exists(poly / "faces"));
    CHECK(file_exists(poly / "owner"));
    CHECK(file_exists(poly / "neighbour"));
    CHECK(file_exists(poly / "boundary"));

    fs::remove_all(tmp);
}

TEST_CASE("2D → OpenFOAM: points file has correct vertex count") {
    auto tmp = fs::temp_directory_path() / "tessell_test_of_pts";
    fs::remove_all(tmp);
    fs::create_directories(tmp);

    // 4 boundary vertices → 8 points after extrusion (z=0 + z=dz)
    std::vector<Vec2> square = {{0,0},{1,0},{1,1},{0,1}};
    auto mesh = triangulate_2d(square);
    int nv_2d = (int)mesh.vertices.size();

    OFWriteOptions opts;
    opts.extrude_2d        = true;
    opts.extrude_thickness = 0.1;
    write_openfoam_2d(tmp.string(), mesh, opts);

    auto content = read_file(tmp / "constant" / "polyMesh" / "points");
    // Find the count line (first non-header integer)
    std::istringstream iss(content);
    std::string line;
    int count = -1;
    while (std::getline(iss, line)) {
        if (line.empty() || line[0] == '/' || line[0] == 'F' || line[0] == '{' || line[0] == '}')
            continue;
        try { count = std::stoi(line); break; } catch (...) {}
    }
    CHECK(count == 2 * nv_2d);

    fs::remove_all(tmp);
}

TEST_CASE("2D → OpenFOAM: boundary file contains 'empty' patches") {
    auto tmp = fs::temp_directory_path() / "tessell_test_of_bnd";
    fs::remove_all(tmp);
    fs::create_directories(tmp);

    std::vector<Vec2> tri = {{0,0},{1,0},{0,1}};
    auto mesh = triangulate_2d(tri);

    OFWriteOptions opts;
    opts.extrude_2d        = true;
    opts.extrude_thickness = 0.1;
    write_openfoam_2d(tmp.string(), mesh, opts);

    auto content = read_file(tmp / "constant" / "polyMesh" / "boundary");
    CHECK(content.find("empty") != std::string::npos);

    fs::remove_all(tmp);
}
