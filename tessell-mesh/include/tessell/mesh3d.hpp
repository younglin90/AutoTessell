#pragma once
#include "types.hpp"
#include <string>

namespace tessell {

struct Mesh3DOptions {
    bool   preprocess     = true;  // geogram surface repair before meshing
    bool   refine         = true;  // quality refinement
    double quality        = 2.0;   // geogram quality param (radius/edge ratio ≥ 2.0)
    double epsilon        = 1e-3;  // surface approximation tolerance (relative to bbox)
    bool   verbose        = false;
};

/**
 * Tetrahedralize a closed surface mesh loaded from an STL file.
 * Uses geogram's mesh_tetrahedralize() with optional preprocessing.
 *
 * Returns a Mesh3D with:
 *   - vertices: 3-D coordinates
 *   - tets:     4-vertex tetrahedra
 *   - patches:  named surface boundary patches (from STL solid names)
 */
Mesh3D tetrahedralize_stl(
    const std::string& stl_path,
    const Mesh3DOptions& opts = {}
);

/**
 * Tetrahedralize a surface mesh provided as vertices + triangles in memory.
 * Useful when STL has already been loaded and repaired in Python.
 */
Mesh3D tetrahedralize_surface(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Tri>&  surface_triangles,
    const Mesh3DOptions& opts = {}
);

} // namespace tessell
