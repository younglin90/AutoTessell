/**
 * 2-D Constrained Delaunay Triangulation via CDT (MPL-2.0).
 * CDT is header-only — no special init needed.
 */

#include <tessell/mesh2d.hpp>

#include <CDT.h>
#include <stdexcept>
#include <unordered_map>

namespace tessell {

namespace {

// Convert our Vec2 list to CDT vertex type
CDT::V2d<double> to_cdt(const Vec2& v) {
    return CDT::V2d<double>{v[0], v[1]};
}

} // anonymous namespace

Mesh2D triangulate_2d(
    const std::vector<Vec2>& boundary,
    const std::vector<std::vector<Vec2>>& holes,
    const Mesh2DOptions& /*opts*/)
{
    if (boundary.size() < 3) {
        throw std::invalid_argument("boundary must have at least 3 vertices");
    }

    CDT::Triangulation<double> cdt(
        CDT::VertexInsertionOrder::AsProvided,
        CDT::IntersectingConstraintEdges::TryResolve,
        1e-10
    );

    // ── Collect all vertices (boundary + holes) ──
    std::vector<CDT::V2d<double>> cdt_verts;
    cdt_verts.reserve(boundary.size());
    for (const auto& v : boundary) {
        cdt_verts.push_back(to_cdt(v));
    }
    for (const auto& hole : holes) {
        for (const auto& v : hole) {
            cdt_verts.push_back(to_cdt(v));
        }
    }
    cdt.insertVertices(cdt_verts);

    // ── Constraint edges ──
    std::vector<CDT::Edge> cdt_edges;

    // Outer boundary (closed polygon)
    CDT::VertInd base = 0;
    for (CDT::VertInd i = 0; i < (CDT::VertInd)boundary.size(); ++i) {
        CDT::VertInd next = (i + 1) % (CDT::VertInd)boundary.size();
        cdt_edges.push_back(CDT::Edge{base + i, base + next});
    }

    // Hole polygons
    CDT::VertInd offset = (CDT::VertInd)boundary.size();
    for (const auto& hole : holes) {
        for (CDT::VertInd i = 0; i < (CDT::VertInd)hole.size(); ++i) {
            CDT::VertInd next = (i + 1) % (CDT::VertInd)hole.size();
            cdt_edges.push_back(CDT::Edge{offset + i, offset + next});
        }
        offset += (CDT::VertInd)hole.size();
    }

    cdt.insertEdges(cdt_edges);

    // Remove exterior triangles and holes
    cdt.eraseOuterTrianglesAndHoles();

    // ── Build result ──
    Mesh2D result;

    result.vertices.reserve(cdt.vertices.size());
    for (const auto& v : cdt.vertices) {
        result.vertices.push_back({v.x, v.y});
    }

    result.triangles.reserve(cdt.triangles.size());
    for (const auto& t : cdt.triangles) {
        result.triangles.push_back({
            (int)t.vertices[0],
            (int)t.vertices[1],
            (int)t.vertices[2]
        });
    }

    // Build a single "wall" patch from the boundary edges
    BoundaryPatch wall;
    wall.name = "wall";
    wall.type = "wall";
    // Boundary edge indices: outer boundary + hole edges
    // CDT stores fixed edges; we identify them by index
    for (int i = 0; i < (int)cdt_edges.size(); ++i) {
        wall.face_ids.push_back(i);
    }
    result.boundary_segments.push_back(std::move(wall));

    return result;
}

} // namespace tessell
