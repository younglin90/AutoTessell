/**
 * 3-D tetrahedral mesh generation via geogram (BSD-3-Clause).
 *
 * Pipeline:
 *   STL file  ──►  GEO::mesh_load()
 *             ──►  GEO::mesh_repair()          (preprocess)
 *             ──►  GEO::mesh_tetrahedralize()   (fill volume)
 *             ──►  tessell::Mesh3D              (extract verts + tets)
 */

#include <tessell/mesh3d.hpp>

#include <geogram/basic/command_line.h>
#include <geogram/basic/command_line_args.h>
#include <geogram/basic/logger.h>
#include <geogram/mesh/mesh.h>
#include <geogram/mesh/mesh_io.h>
#include <geogram/mesh/mesh_repair.h>
#include <geogram/mesh/mesh_tetrahedralize.h>

#include <stdexcept>
#include <string>

namespace tessell {

namespace {

bool geo_initialized = false;

void ensure_geo_initialized(bool verbose) {
    if (!geo_initialized) {
        GEO::initialize(GEO::GEOGRAM_INSTALL_ALL);
        GEO::CmdLine::import_arg_group("algo");
        if (!verbose) {
            GEO::Logger::instance()->set_quiet(true);
        }
        geo_initialized = true;
    }
}

Mesh3D extract_mesh3d(const GEO::Mesh& gm) {
    Mesh3D result;

    // ── Vertices ──
    result.vertices.reserve(gm.vertices.nb());
    for (GEO::index_t v = 0; v < gm.vertices.nb(); ++v) {
        const double* p = gm.vertices.point_ptr(v);
        result.vertices.push_back({p[0], p[1], p[2]});
    }

    // ── Tetrahedra ──
    // geogram stores tets in cells; tet is cell type 4
    result.tets.reserve(gm.cells.nb());
    for (GEO::index_t c = 0; c < gm.cells.nb(); ++c) {
        if (gm.cells.type(c) != GEO::MESH_TET) continue;
        Tet t;
        for (int lv = 0; lv < 4; ++lv) {
            t[lv] = (int)gm.cells.vertex(c, (GEO::index_t)lv);
        }
        result.tets.push_back(t);
    }

    // ── Surface facets → boundary patches ──
    // If the mesh has no named surface attributes, create a single "walls" patch.
    BoundaryPatch walls;
    walls.name = "walls";
    walls.type = "wall";

    for (GEO::index_t f = 0; f < gm.facets.nb(); ++f) {
        Tri tri;
        for (int lv = 0; lv < 3; ++lv) {
            tri[lv] = (int)gm.facets.vertex(f, (GEO::index_t)lv);
        }
        walls.face_ids.push_back((int)f);
        // Store the actual triangle in vertices order
        // (we just record face index here; writer will re-read)
    }
    if (!walls.face_ids.empty()) {
        result.patches.push_back(std::move(walls));
    }

    return result;
}

} // anonymous namespace

// ──────────────────────────────────────────────────────────────
// Public API
// ──────────────────────────────────────────────────────────────

Mesh3D tetrahedralize_stl(const std::string& stl_path, const Mesh3DOptions& opts) {
    ensure_geo_initialized(opts.verbose);

    GEO::Mesh gm(3, false);
    if (!GEO::mesh_load(stl_path, gm)) {
        throw std::runtime_error("geogram: failed to load STL: " + stl_path);
    }

    if (opts.preprocess) {
        GEO::mesh_repair(gm,
            GEO::MeshRepairMode(
                GEO::MESH_REPAIR_DEFAULT |
                GEO::MESH_REPAIR_COLOCATE  |
                GEO::MESH_REPAIR_DUP_F
            ),
            opts.epsilon
        );
    }

    GEO::MeshTetrahedralizeParameters params;
    params.preprocess = opts.preprocess;
    params.refine     = opts.refine;
    params.quality    = opts.quality;

    bool ok = GEO::mesh_tetrahedralize(gm, params);
    if (!ok) {
        throw std::runtime_error(
            "geogram mesh_tetrahedralize() failed for: " + stl_path
        );
    }

    return extract_mesh3d(gm);
}

Mesh3D tetrahedralize_surface(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Tri>&  surface_triangles,
    const Mesh3DOptions& opts)
{
    ensure_geo_initialized(opts.verbose);

    // Build a geogram surface mesh from our arrays
    GEO::Mesh gm(3, false);
    gm.vertices.create_vertices((GEO::index_t)surface_vertices.size());
    for (GEO::index_t v = 0; v < (GEO::index_t)surface_vertices.size(); ++v) {
        double* p = gm.vertices.point_ptr(v);
        p[0] = surface_vertices[v][0];
        p[1] = surface_vertices[v][1];
        p[2] = surface_vertices[v][2];
    }

    gm.facets.create_triangles((GEO::index_t)surface_triangles.size());
    for (GEO::index_t f = 0; f < (GEO::index_t)surface_triangles.size(); ++f) {
        gm.facets.set_vertex(f, 0, (GEO::index_t)surface_triangles[f][0]);
        gm.facets.set_vertex(f, 1, (GEO::index_t)surface_triangles[f][1]);
        gm.facets.set_vertex(f, 2, (GEO::index_t)surface_triangles[f][2]);
    }
    gm.facets.connect();

    if (opts.preprocess) {
        GEO::mesh_repair(gm, GEO::MESH_REPAIR_DEFAULT, opts.epsilon);
    }

    GEO::MeshTetrahedralizeParameters params;
    params.preprocess = opts.preprocess;
    params.refine     = opts.refine;
    params.quality    = opts.quality;

    bool ok = GEO::mesh_tetrahedralize(gm, params);
    if (!ok) {
        throw std::runtime_error("geogram mesh_tetrahedralize() failed");
    }

    return extract_mesh3d(gm);
}

} // namespace tessell
