#pragma once
#include "types.hpp"

namespace tessell {

struct Mesh2DOptions {
    double target_edge_length = 0.1;  // absolute length
    bool   quality_refine     = true; // Delaunay quality refinement
    double min_angle_deg      = 20.0; // Ruppert's minimum angle (if refining)
};

/**
 * Triangulate a 2-D polygon (with optional holes) using CDT.
 *
 * boundary  — outer polygon vertices in CCW order (last connects back to first)
 * holes     — list of hole polygons (CW order, any simple polygon)
 *
 * The result contains triangles covering the interior region.
 * Boundary segments are stored as a single "wall" patch by default.
 */
Mesh2D triangulate_2d(
    const std::vector<Vec2>& boundary,
    const std::vector<std::vector<Vec2>>& holes = {},
    const Mesh2DOptions& opts = {}
);

} // namespace tessell
