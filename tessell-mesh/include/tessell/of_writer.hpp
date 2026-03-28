#pragma once
#include "types.hpp"
#include <string>

namespace tessell {

struct OFWriteOptions {
    // 2-D extrusion (for 2-D OpenFOAM cases using "empty" BC)
    bool   extrude_2d       = false;
    double extrude_thickness = 0.1;   // z-thickness for 2-D cases

    // Boundary type for walls not otherwise named
    std::string default_wall_type = "wall";
};

/**
 * Write a 3-D tetrahedral mesh to OpenFOAM's constant/polyMesh/ format.
 *
 * case_dir  — path to the OpenFOAM case root (must exist)
 * mesh      — tetrahedral mesh from tetrahedralize_stl()
 *
 * Produces: points, faces, owner, neighbour, boundary
 * Internal faces come first (owner < neighbour), then boundary faces.
 */
void write_openfoam_3d(
    const std::string& case_dir,
    const Mesh3D& mesh,
    const OFWriteOptions& opts = {}
);

/**
 * Write a 2-D triangulation to OpenFOAM format.
 * The 2-D mesh is extruded 1 cell thick in the z direction.
 * Front/back faces get the "empty" boundary type for 2-D flow.
 *
 * case_dir    — path to the OpenFOAM case root
 * mesh        — 2-D triangulation from triangulate_2d()
 * patch_names — optional map from edge index to patch name
 */
void write_openfoam_2d(
    const std::string& case_dir,
    const Mesh2D& mesh,
    const OFWriteOptions& opts = {}
);

} // namespace tessell
