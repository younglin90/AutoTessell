/**
 * robusthex_bind.cpp
 *
 * pybind11 bindings for robust_hex_dominant_meshing (gaoxifeng/robust_hex_dominant_meshing).
 *
 * Calls batch_process() which generates a hex-dominant mesh in HYBRID format,
 * then parses the output file and returns vertex/cell arrays.
 *
 * batch_process parameters:
 *   input      - path to .stl or .obj surface mesh
 *   output     - base path for output files (appended with ".HYBRID")
 *   dimension  - 3 for volumetric hex-dominant meshing
 *   tlen       - target edge length ratio (e.g. 1.0)
 *   scale      - scale factor controlling cell size (e.g. 3.0 = ~3 cells per edge)
 *   smooth_iter- smoothing iterations (default 10)
 */

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <stdexcept>

// batch.h declares batch_process()
#include "batch.h"

namespace py = pybind11;

// ---------------------------------------------------------------------------
// HYBRID format parser
// Header line: nVerts nFaces nPolyRows
// nVerts lines: x y z
// nFaces lines: nCorners v0 v1 ... (face vertex list)
// nPolyRows lines (3 per poly): face_ids / hex_flag / pf_flags
// Returns: (vertices (V,3), cells (C, max_poly_verts)) as numpy arrays
// We flatten polyhedral cells by looking at their face–vertex connectivity.
// ---------------------------------------------------------------------------
struct HybridMesh {
    std::vector<std::array<float, 3>> verts;
    // Each cell: list of unique vertex ids (order may vary)
    std::vector<std::vector<int>> cells;
    std::vector<bool> hex_flags; // true = hexahedron, false = other
};

static HybridMesh parse_hybrid(const std::string &path) {
    std::ifstream f(path);
    if (!f.is_open())
        throw std::runtime_error("Cannot open HYBRID file: " + path);

    HybridMesh mesh;

    // Header
    int nVerts, nFaces, nPolyRows;
    f >> nVerts >> nFaces >> nPolyRows;
    int nPolys = nPolyRows / 3;

    // Vertices
    mesh.verts.resize(nVerts);
    for (int i = 0; i < nVerts; i++)
        f >> mesh.verts[i][0] >> mesh.verts[i][1] >> mesh.verts[i][2];

    // Faces (face vertex lists)
    std::vector<std::vector<int>> faces(nFaces);
    for (int i = 0; i < nFaces; i++) {
        int n; f >> n;
        faces[i].resize(n);
        for (int j = 0; j < n; j++) f >> faces[i][j];
    }

    // Polyhedral cells
    mesh.cells.reserve(nPolys);
    mesh.hex_flags.reserve(nPolys);
    for (int i = 0; i < nPolys; i++) {
        // Row 1: face count + face ids
        int nf; f >> nf;
        std::vector<int> fids(nf);
        for (int j = 0; j < nf; j++) f >> fids[j];

        // Row 2: hex flag (single bool)
        int hflag; f >> hflag;
        mesh.hex_flags.push_back(hflag != 0);

        // Row 3: per-face flip flags
        int nflips; f >> nflips;
        for (int j = 0; j < nflips; j++) { int dummy; f >> dummy; }

        // Collect unique vertex ids from all faces of this cell
        std::vector<int> cell_verts;
        std::vector<bool> seen(nVerts, false);
        for (int fid : fids) {
            for (int vid : faces[fid]) {
                if (!seen[vid]) {
                    seen[vid] = true;
                    cell_verts.push_back(vid);
                }
            }
        }
        mesh.cells.push_back(std::move(cell_verts));
    }

    return mesh;
}

// ---------------------------------------------------------------------------
// Main Python-callable function
// ---------------------------------------------------------------------------
py::dict robust_hex_mesh(
    const std::string &input_path,
    const std::string &output_base,
    float  scale       = 3.0f,
    float  tlen        = 1.0f,
    int    smooth_iter = 10
) {
    // batch_process writes to output_base + ".HYBRID"
    char in_buf[1024], out_buf[1024];
    snprintf(in_buf,  sizeof(in_buf),  "%s", input_path.c_str());
    snprintf(out_buf, sizeof(out_buf), "%s", output_base.c_str());

    batch_process(in_buf, out_buf, /*dimension=*/3, tlen, scale, smooth_iter);

    std::string hybrid_path = output_base + ".HYBRID";
    HybridMesh m = parse_hybrid(hybrid_path);

    int V = static_cast<int>(m.verts.size());
    int C = static_cast<int>(m.cells.size());

    // Find max cell size (for uniform ndarray; pad with -1)
    int max_cell = 8; // hex has 8; we pad others
    for (auto &c : m.cells)
        if (static_cast<int>(c.size()) > max_cell)
            max_cell = static_cast<int>(c.size());

    py::array_t<double> out_verts({(py::ssize_t)V, (py::ssize_t)3});
    auto ov = out_verts.mutable_unchecked<2>();
    for (int i = 0; i < V; i++) {
        ov(i, 0) = m.verts[i][0];
        ov(i, 1) = m.verts[i][1];
        ov(i, 2) = m.verts[i][2];
    }

    py::array_t<int> out_cells({(py::ssize_t)C, (py::ssize_t)max_cell});
    auto oc = out_cells.mutable_unchecked<2>();
    for (int i = 0; i < C; i++) {
        int sz = static_cast<int>(m.cells[i].size());
        for (int j = 0; j < max_cell; j++)
            oc(i, j) = j < sz ? m.cells[i][j] : -1;
    }

    py::array_t<bool> out_hex({(py::ssize_t)C});
    auto oh = out_hex.mutable_unchecked<1>();
    for (int i = 0; i < C; i++)
        oh(i) = m.hex_flags[i];

    py::dict result;
    result["vertices"]  = out_verts;
    result["cells"]     = out_cells;
    result["hex_flags"] = out_hex;
    return result;
}

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------
PYBIND11_MODULE(robusthex, m) {
    m.doc() = "robust_hex_dominant_meshing Python bindings (AutoTessell extension)";

    m.def(
        "robust_hex_mesh",
        &robust_hex_mesh,
        py::arg("input_path"),
        py::arg("output_base"),
        py::arg("scale")       = 3.0f,
        py::arg("tlen")        = 1.0f,
        py::arg("smooth_iter") = 10,
        R"doc(
Generate a hex-dominant mesh from a surface mesh (STL/OBJ).

Parameters
----------
input_path  : str  — path to input STL or OBJ file
output_base : str  — base path for output files (appended with ".HYBRID")
scale       : float — cell size scale (default 3.0; larger = coarser)
tlen        : float — target edge length ratio (default 1.0)
smooth_iter : int   — smoothing iterations (default 10)

Returns
-------
dict with:
  vertices  : ndarray (V, 3) float64
  cells     : ndarray (C, max_verts_per_cell) int32 — padded with -1
  hex_flags : ndarray (C,) bool — True = hexahedron cell
)doc"
    );
}
