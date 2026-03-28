/**
 * pybind11 Python bindings for tessell-mesh
 *
 * Python usage:
 *
 *   import tessell_mesh as tm
 *
 *   # ── 3-D from STL ──
 *   result = tm.tetrahedralize_stl("input.stl", quality=2.0)
 *   result.write_openfoam("/path/to/case")
 *
 *   # ── 2-D polygon ──
 *   boundary = [(0,0),(1,0),(1,1),(0,1)]
 *   result = tm.triangulate_2d(boundary, holes=[], extrude=0.1)
 *   result.write_openfoam("/path/to/case")
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <tessell/mesh2d.hpp>
#include <tessell/mesh3d.hpp>
#include <tessell/of_writer.hpp>

namespace py = pybind11;
using namespace tessell;

// ──────────────────────────────────────────────────────────────
// Python-facing result objects with .write_openfoam() method
// ──────────────────────────────────────────────────────────────

struct PyMesh3DResult {
    Mesh3D mesh;
    std::string stl_source;

    void write_openfoam(const std::string& case_dir) const {
        OFWriteOptions opts;
        write_openfoam_3d(case_dir, mesh, opts);
    }

    int num_vertices() const { return (int)mesh.vertices.size(); }
    int num_tets()     const { return (int)mesh.tets.size(); }

    // Return vertex array as Python list of 3-tuples
    std::vector<Vec3> get_vertices() const { return mesh.vertices; }
    std::vector<Tet>  get_tets()     const { return mesh.tets; }
};

struct PyMesh2DResult {
    Mesh2D mesh;
    double extrude_thickness;

    void write_openfoam(const std::string& case_dir) const {
        OFWriteOptions opts;
        opts.extrude_2d        = true;
        opts.extrude_thickness = extrude_thickness;
        write_openfoam_2d(case_dir, mesh, opts);
    }

    int num_vertices()  const { return (int)mesh.vertices.size(); }
    int num_triangles() const { return (int)mesh.triangles.size(); }

    std::vector<Vec2> get_vertices()  const { return mesh.vertices; }
    std::vector<Tri>  get_triangles() const { return mesh.triangles; }
};

// ──────────────────────────────────────────────────────────────
// Module definition
// ──────────────────────────────────────────────────────────────

PYBIND11_MODULE(tessell_mesh, m) {
    m.doc() = "tessell-mesh: C++/geogram/CDT hybrid mesh engine (2-D + 3-D)";

    // ── Mesh3D result ──
    py::class_<PyMesh3DResult>(m, "Mesh3DResult")
        .def("write_openfoam", &PyMesh3DResult::write_openfoam,
             py::arg("case_dir"),
             "Write OpenFOAM constant/polyMesh/ files to case_dir.")
        .def_property_readonly("num_vertices", &PyMesh3DResult::num_vertices)
        .def_property_readonly("num_tets",     &PyMesh3DResult::num_tets)
        .def_property_readonly("vertices",     &PyMesh3DResult::get_vertices,
             "List of (x,y,z) vertex coordinates.")
        .def_property_readonly("tets",         &PyMesh3DResult::get_tets,
             "List of (v0,v1,v2,v3) tetrahedral cell indices.");

    // ── Mesh2D result ──
    py::class_<PyMesh2DResult>(m, "Mesh2DResult")
        .def("write_openfoam", &PyMesh2DResult::write_openfoam,
             py::arg("case_dir"),
             "Extrude 1 cell thick and write OpenFOAM constant/polyMesh/ files.")
        .def_property_readonly("num_vertices",  &PyMesh2DResult::num_vertices)
        .def_property_readonly("num_triangles", &PyMesh2DResult::num_triangles)
        .def_property_readonly("vertices",      &PyMesh2DResult::get_vertices)
        .def_property_readonly("triangles",     &PyMesh2DResult::get_triangles);

    // ── 3-D: STL → tet mesh ──
    m.def("tetrahedralize_stl",
        [](const std::string& stl_path,
           bool   preprocess,
           bool   refine,
           double quality,
           double epsilon,
           bool   verbose) -> PyMesh3DResult
        {
            Mesh3DOptions opts;
            opts.preprocess = preprocess;
            opts.refine     = refine;
            opts.quality    = quality;
            opts.epsilon    = epsilon;
            opts.verbose    = verbose;
            return PyMesh3DResult{tetrahedralize_stl(stl_path, opts), stl_path};
        },
        py::arg("stl_path"),
        py::arg("preprocess") = true,
        py::arg("refine")     = true,
        py::arg("quality")    = 2.0,
        py::arg("epsilon")    = 1e-3,
        py::arg("verbose")    = false,
        R"(
        Tetrahedralize a surface STL file using geogram.

        Parameters
        ----------
        stl_path   : path to input STL (binary or ASCII)
        preprocess : run geogram surface repair before meshing (default True)
        refine     : quality refinement (default True)
        quality    : radius-to-edge ratio bound, e.g. 2.0 (default 2.0)
        epsilon    : surface tolerance relative to bbox (default 1e-3)
        verbose    : print geogram progress (default False)

        Returns
        -------
        Mesh3DResult with .write_openfoam(case_dir), .num_tets, .vertices, .tets
        )"
    );

    // ── 3-D: in-memory surface → tet mesh ──
    m.def("tetrahedralize_surface",
        [](const std::vector<Vec3>& verts,
           const std::vector<Tri>&  tris,
           bool   preprocess,
           bool   refine,
           double quality) -> PyMesh3DResult
        {
            Mesh3DOptions opts;
            opts.preprocess = preprocess;
            opts.refine     = refine;
            opts.quality    = quality;
            return PyMesh3DResult{tetrahedralize_surface(verts, tris, opts), ""};
        },
        py::arg("vertices"),
        py::arg("triangles"),
        py::arg("preprocess") = true,
        py::arg("refine")     = true,
        py::arg("quality")    = 2.0,
        "Tetrahedralize a surface given as numpy-compatible vertex/triangle arrays."
    );

    // ── 2-D: polygon → triangle mesh (+ optional extrusion) ──
    m.def("triangulate_2d",
        [](const std::vector<Vec2>& boundary,
           const std::vector<std::vector<Vec2>>& holes,
           double extrude_thickness) -> PyMesh2DResult
        {
            Mesh2DOptions opts;
            Mesh2D mesh = triangulate_2d(boundary, holes, opts);
            return PyMesh2DResult{std::move(mesh), extrude_thickness};
        },
        py::arg("boundary"),
        py::arg("holes")             = std::vector<std::vector<Vec2>>{},
        py::arg("extrude_thickness") = 0.1,
        R"(
        Constrained Delaunay triangulation of a 2-D polygon using CDT.

        Parameters
        ----------
        boundary           : outer polygon as list of (x,y) pairs (CCW)
        holes              : list of hole polygons (CW) — default []
        extrude_thickness  : z-thickness for write_openfoam() (default 0.1)

        Returns
        -------
        Mesh2DResult with .write_openfoam(case_dir), .num_triangles, .vertices, .triangles
        )"
    );
}
