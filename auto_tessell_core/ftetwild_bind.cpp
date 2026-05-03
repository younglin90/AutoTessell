// pybind11 binding for vendored fTetWild (third_party/fTetWild, MPL-2.0).
// Authored for AutoTessell to remove the external `wildmeshing` PyPI dependency.
// Calls into floatTetWild::tetrahedralization().
//
// Returned mesh is binary-identical to the upstream fTetWild CLI / wildmeshing
// PyPI package for the same input + Parameters + RNG seed.
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <Eigen/Core>
#include <geogram/basic/common.h>
#include <geogram/basic/logger.h>
#include <geogram/mesh/mesh.h>

#include <floattetwild/FloatTetwild.h>
#include <floattetwild/Parameters.h>
#include <floattetwild/Logger.hpp>
#include <floattetwild/Types.hpp>

#include <vector>
#include <string>

namespace py = pybind11;

namespace {

// Build a geogram triangle mesh from numpy V (N,3) double + F (M,3) int.
void build_geo_mesh(GEO::Mesh& sf_mesh,
                    const py::array_t<double, py::array::c_style | py::array::forcecast>& V,
                    const py::array_t<int,    py::array::c_style | py::array::forcecast>& F)
{
    auto v = V.unchecked<2>();
    auto f = F.unchecked<2>();
    sf_mesh.clear();
    sf_mesh.vertices.create_vertices(static_cast<GEO::index_t>(v.shape(0)));
    for (GEO::index_t i = 0; i < static_cast<GEO::index_t>(v.shape(0)); ++i) {
        double* p = sf_mesh.vertices.point_ptr(i);
        p[0] = v(i, 0); p[1] = v(i, 1); p[2] = v(i, 2);
    }
    sf_mesh.facets.create_triangles(static_cast<GEO::index_t>(f.shape(0)));
    for (GEO::index_t i = 0; i < static_cast<GEO::index_t>(f.shape(0)); ++i) {
        sf_mesh.facets.set_vertex(i, 0, static_cast<GEO::index_t>(f(i, 0)));
        sf_mesh.facets.set_vertex(i, 1, static_cast<GEO::index_t>(f(i, 1)));
        sf_mesh.facets.set_vertex(i, 2, static_cast<GEO::index_t>(f(i, 2)));
    }
}

py::tuple tetrahedralize_impl(
    py::array_t<double> V, py::array_t<int> F,
    double stop_quality, int max_its,
    double epsilon, double edge_length_r,
    int max_threads, bool skip_simplify, bool coarsen,
    bool smooth_open_boundary, bool floodfill,
    bool use_input_for_wn, bool manifold_surface,
    bool correct_surface_orientation,
    int log_level)
{
    static bool geo_initialized = false;
    if (!geo_initialized) {
        GEO::initialize();
        geo_initialized = true;
    }
    if (log_level >= 4) {
        GEO::Logger::instance()->set_quiet(true);
    }

    GEO::Mesh sf_mesh;
    build_geo_mesh(sf_mesh, V, F);

    floatTetWild::Parameters params;
    params.stop_energy        = stop_quality;
    params.max_its            = max_its;
    params.eps_rel            = epsilon;
    params.ideal_edge_length_rel = edge_length_r;
    params.num_threads        = (max_threads <= 0) ? 1 : max_threads;
    params.coarsen            = coarsen;
    params.smooth_open_boundary = smooth_open_boundary;
    params.use_floodfill      = floodfill;
    params.use_input_for_wn   = use_input_for_wn;
    params.manifold_surface   = manifold_surface;
    params.correct_surface_orientation = correct_surface_orientation;
    params.log_level          = log_level;
    params.is_quiet           = (log_level >= 4);

    Eigen::MatrixXd VO;
    Eigen::MatrixXi TO;
    int rc = floatTetWild::tetrahedralization(
        sf_mesh, params, VO, TO, /*boolean_op=*/-1, /*skip_simplify=*/skip_simplify);

    py::array_t<double> V_out({(py::ssize_t)VO.rows(), (py::ssize_t)3});
    auto vo = V_out.mutable_unchecked<2>();
    for (py::ssize_t i = 0; i < VO.rows(); ++i) {
        vo(i, 0) = VO(i, 0); vo(i, 1) = VO(i, 1); vo(i, 2) = VO(i, 2);
    }
    py::array_t<int64_t> T_out({(py::ssize_t)TO.rows(), (py::ssize_t)4});
    auto to = T_out.mutable_unchecked<2>();
    for (py::ssize_t i = 0; i < TO.rows(); ++i) {
        to(i, 0) = TO(i, 0); to(i, 1) = TO(i, 1);
        to(i, 2) = TO(i, 2); to(i, 3) = TO(i, 3);
    }
    return py::make_tuple(V_out, T_out, rc);
}

}  // namespace

PYBIND11_MODULE(ftetwild, m) {
    m.doc() = "AutoTessell vendored fTetWild bindings (MPL-2.0).";
    m.def("tetrahedralize", &tetrahedralize_impl,
          py::arg("V"), py::arg("F"),
          py::arg("stop_quality")          = 10.0,
          py::arg("max_its")               = 80,
          py::arg("epsilon")               = 1e-3,
          py::arg("edge_length_r")         = 0.05,
          py::arg("max_threads")           = 1,
          py::arg("skip_simplify")         = false,
          py::arg("coarsen")               = true,
          py::arg("smooth_open_boundary")  = false,
          py::arg("floodfill")             = false,
          py::arg("use_input_for_wn")      = false,
          py::arg("manifold_surface")      = false,
          py::arg("correct_surface_orientation") = true,
          py::arg("log_level")             = 4,
          R"pbdoc(Tetrahedralize a triangle surface mesh via vendored fTetWild.

          Returns:
              (V_out (N,3) float64, T_out (M,4) int64, return_code int).
          )pbdoc");
}
