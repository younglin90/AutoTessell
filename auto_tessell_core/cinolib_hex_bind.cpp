/**
 * cinolib_hex_bind.cpp
 *
 * pybind11 bindings for cinolib voxel-based hex meshing.
 *
 * Input : vertices (N,3) float64, faces (M,3) int32
 * Output: hex_vertices (V,3) float64, hex_cells (C,8) int32
 *
 * Algorithm:
 *   1. Build a cinolib Trimesh from the input surface
 *   2. Voxelize it into a VoxelGrid
 *   3. Convert INSIDE+BOUNDARY voxels → hex cells
 *   4. Return numpy arrays
 */

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

// cinolib is header-only with inline .cpp includes — do NOT define CINO_STATIC_LIB
// (STATIC_LIB mode requires compiling cinolib separately, which we skip here)

#include <cinolib/geometry/vec_mat.h>
#include <cinolib/meshes/trimesh.h>
#include <cinolib/voxelize.h>
#include <cinolib/voxel_grid.h>
#include <cinolib/voxel_grid_to_hexmesh.h>
#include <cinolib/meshes/hexmesh.h>

namespace py = pybind11;

// ---------------------------------------------------------------------------
// Helper: convert numpy (N,3) double → std::vector<cinolib::vec3d>
// ---------------------------------------------------------------------------
static std::vector<cinolib::vec3d> to_vec3d(py::array_t<double> arr) {
    auto buf = arr.request();
    if (buf.ndim != 2 || buf.shape[1] != 3)
        throw std::runtime_error("vertices must be shape (N, 3)");
    const double *p = static_cast<const double *>(buf.ptr);
    int N = buf.shape[0];
    std::vector<cinolib::vec3d> out(N);
    for (int i = 0; i < N; i++)
        out[i] = cinolib::vec3d(p[3*i], p[3*i+1], p[3*i+2]);
    return out;
}

// ---------------------------------------------------------------------------
// Helper: convert numpy (M,3) int32 → std::vector<std::vector<uint>>
// ---------------------------------------------------------------------------
static std::vector<std::vector<uint>> to_polys(py::array_t<int> arr) {
    auto buf = arr.request();
    if (buf.ndim != 2 || buf.shape[1] != 3)
        throw std::runtime_error("faces must be shape (M, 3)");
    const int *p = static_cast<const int *>(buf.ptr);
    int M = buf.shape[0];
    std::vector<std::vector<uint>> out(M, std::vector<uint>(3));
    for (int i = 0; i < M; i++) {
        out[i][0] = static_cast<uint>(p[3*i]);
        out[i][1] = static_cast<uint>(p[3*i+1]);
        out[i][2] = static_cast<uint>(p[3*i+2]);
    }
    return out;
}

// ---------------------------------------------------------------------------
// Main binding function
// ---------------------------------------------------------------------------
py::tuple voxel_hex_mesh(
    py::array_t<double, py::array::c_style | py::array::forcecast> vertices,
    py::array_t<int,    py::array::c_style | py::array::forcecast> faces,
    int resolution
) {
    using namespace cinolib;

    auto verts_v = to_vec3d(vertices);
    auto polys_v = to_polys(faces);

    // Build surface trimesh
    Trimesh<> surf(verts_v, polys_v);

    // Voxelize
    VoxelGrid g;
    voxelize(surf, static_cast<uint>(resolution), g);

    // Convert voxels → hexmesh (keep INSIDE and BOUNDARY voxels)
    Hexmesh<> hex;
    voxel_grid_to_hexmesh(g, hex, VOXEL_INSIDE | VOXEL_BOUNDARY);

    uint Vh = hex.num_verts();
    uint Ch = hex.num_polys();

    // Extract vertices
    py::array_t<double> out_verts({(py::ssize_t)Vh, (py::ssize_t)3});
    auto ov = out_verts.mutable_unchecked<2>();
    for (uint i = 0; i < Vh; i++) {
        const vec3d &p = hex.vert(i);
        ov(i, 0) = p.x();
        ov(i, 1) = p.y();
        ov(i, 2) = p.z();
    }

    // Extract hex cells (8 vertices each)
    py::array_t<int> out_cells({(py::ssize_t)Ch, (py::ssize_t)8});
    auto oc = out_cells.mutable_unchecked<2>();
    for (uint i = 0; i < Ch; i++) {
        auto ids = hex.poly_verts_id(i);
        if (ids.size() != 8)
            throw std::runtime_error("Expected 8-node hex cell, got " + std::to_string(ids.size()));
        for (int j = 0; j < 8; j++)
            oc(i, j) = static_cast<int>(ids[j]);
    }

    return py::make_tuple(out_verts, out_cells);
}

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------
PYBIND11_MODULE(cinolib_hex, m) {
    m.doc() = "cinolib voxel-based hex meshing (AutoTessell extension)";

    m.def(
        "voxel_hex_mesh",
        &voxel_hex_mesh,
        py::arg("vertices"),
        py::arg("faces"),
        py::arg("resolution") = 50,
        R"doc(
Voxelize a closed surface mesh and convert to a hex mesh.

Parameters
----------
vertices : ndarray, shape (N, 3), float64
    Surface mesh vertices.
faces : ndarray, shape (M, 3), int32
    Triangle indices into vertices.
resolution : int, optional
    Max voxels per side (default 50). Higher = finer but more memory.

Returns
-------
hex_verts : ndarray, shape (V, 3), float64
hex_cells : ndarray, shape (C, 8), int32
    Each row contains 8 vertex indices of one hexahedron.
)doc"
    );
}
