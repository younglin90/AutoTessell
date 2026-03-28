#pragma once
#include <array>
#include <string>
#include <vector>

namespace tessell {

// ──────────────────────────────────────────────
// Shared data types
// ──────────────────────────────────────────────

using Vec2 = std::array<double, 2>;
using Vec3 = std::array<double, 3>;
using Tri  = std::array<int, 3>;   // triangle face (CCW)
using Tet  = std::array<int, 4>;   // tetrahedron

struct BoundaryPatch {
    std::string name;
    std::string type;          // "patch", "wall", "symmetry", "empty"
    std::vector<int> face_ids; // indices into global face list
};

// Result of a 2D triangulation (before extrusion)
struct Mesh2D {
    std::vector<Vec2>    vertices;
    std::vector<Tri>     triangles;
    std::vector<BoundaryPatch> boundary_segments; // per-edge patches
};

// Result of a 3D tetrahedral mesh
struct Mesh3D {
    std::vector<Vec3> vertices;
    std::vector<Tet>  tets;
    // Surface patches — each entry maps a named patch to its surface triangles
    std::vector<BoundaryPatch> patches;
};

} // namespace tessell
