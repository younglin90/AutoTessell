#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;
using P = std::array<double, 3>;

namespace {
P add(P a, P b) { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
P sub(P a, P b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
P mul(P a, double s) { return {a[0] * s, a[1] * s, a[2] * s}; }
double dot(P a, P b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double norm(P a) { return std::sqrt(dot(a, a)); }
P unit(P a, const char* what) {
    const double n = norm(a);
    if (!(n > 1e-14) || !std::isfinite(n)) throw std::invalid_argument(std::string(what) + "_degenerate");
    return mul(a, 1.0 / n);
}
P project_tangent(P v, P n) { return sub(v, mul(n, dot(v, n))); }

py::dict refused(const char* reason) {
    py::dict out;
    out["accepted"] = false;
    out["status"] = "native_tet_bl_front_qopt_refused";
    out["reason"] = reason;
    out["candidate_discarded"] = true;
    out["publication_eligible"] = false;
    return out;
}

py::dict optimize(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& wall,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& front,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edges,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals,
    const py::list& features, const py::list& patches,
    const py::list& physical_groups, const py::list& components,
    std::int64_t requested_layers, std::int64_t max_iterations = 8,
    double correction_cap = 0.25, double min_improvement = 1e-10) {
    if (wall.ndim() != 2 || front.ndim() != 2 || wall.shape(1) != 3 ||
        front.shape(1) != 3 || wall.shape(0) != front.shape(0) ||
        edges.ndim() != 2 || edges.shape(1) != 4 ||
        normals.ndim() != 2 || normals.shape(1) != 3) {
        throw std::invalid_argument("wall/front Nx3, edges Ex4, normals Fx3 required");
    }
    if (requested_layers == 0) {
        py::dict out = refused("disabled_identity");
        out["accepted"] = true;
        out["status"] = "native_tet_bl_front_qopt_bl0_identity";
        out["candidate_discarded"] = false;
        return out;
    }
    if (requested_layers < 0 || max_iterations < 0 ||
        !(std::isfinite(correction_cap) && correction_cap > 0.0) ||
        !(std::isfinite(min_improvement) && min_improvement >= 0.0) ||
        edges.shape(0) == 0 || normals.shape(0) == 0 ||
        features.size() != static_cast<size_t>(normals.shape(0)) ||
        patches.size() != static_cast<size_t>(normals.shape(0)) ||
        physical_groups.size() != static_cast<size_t>(normals.shape(0)) ||
        components.size() != static_cast<size_t>(normals.shape(0))) {
        return refused("invalid_options_or_labels");
    }

    const auto* wd = wall.data();
    const auto* fd = front.data();
    const auto* ed = edges.data();
    const auto* nd = normals.data();
    const auto get_wall = [&](std::int64_t i) {
        if (i < 0 || i >= wall.shape(0)) throw std::invalid_argument("wall_vertex_out_of_range");
        const auto o = static_cast<size_t>(i) * 3U;
        return P{wd[o], wd[o + 1U], wd[o + 2U]};
    };
    const auto get_front = [&](std::int64_t i) {
        if (i < 0 || i >= front.shape(0)) throw std::invalid_argument("front_vertex_out_of_range");
        const auto o = static_cast<size_t>(i) * 3U;
        return P{fd[o], fd[o + 1U], fd[o + 2U]};
    };
    const auto get_normal = [&](std::int64_t face) {
        if (face < 0 || face >= normals.shape(0)) throw std::invalid_argument("normal_face_out_of_range");
        const auto o = static_cast<size_t>(face) * 3U;
        return unit(P{nd[o], nd[o + 1U], nd[o + 2U]}, "face_normal");
    };

    std::map<std::int64_t, std::set<std::string>> feature_at_vertex;
    std::map<std::int64_t, std::set<std::string>> patch_at_vertex;
    for (py::ssize_t i = 0; i < edges.shape(0); ++i) {
        const auto o = static_cast<size_t>(i) * 4U;
        const auto a = ed[o], b = ed[o + 1U], f = ed[o + 2U];
        if (f < 0 || f >= normals.shape(0)) return refused("source_face_out_of_range");
        const auto feature = py::str(features[f]).cast<std::string>();
        const auto patch = py::str(patches[f]).cast<std::string>();
        feature_at_vertex[a].insert(feature);
        feature_at_vertex[b].insert(feature);
        patch_at_vertex[a].insert(patch);
        patch_at_vertex[b].insert(patch);
    }
    for (const auto& [v, labels] : feature_at_vertex) {
        if (labels.size() > 1 || patch_at_vertex[v].size() > 1) {
            return refused("feature_or_patch_junction_locked");
        }
    }

    struct Edge { std::int64_t a, b, face, id; };
    std::vector<Edge> es;
    es.reserve(static_cast<size_t>(edges.shape(0)));
    for (py::ssize_t i = 0; i < edges.shape(0); ++i) {
        const auto o = static_cast<size_t>(i) * 4U;
        es.push_back({ed[o], ed[o + 1U], ed[o + 2U], ed[o + 3U]});
    }
    std::sort(es.begin(), es.end(), [](const Edge& x, const Edge& y) {
        return std::tie(x.id, x.face, x.a, x.b) < std::tie(y.id, y.face, y.a, y.b);
    });

    auto evaluate = [&](const std::vector<P>& candidate) {
        double max_angle = 0.0;
        double max_residual = 0.0;
        double max_edge_skew = 0.0;
        for (const auto& e : es) {
            const P tangent = unit(sub(candidate[e.b], candidate[e.a]), "candidate_edge");
            const P d = mul(add(sub(get_front(e.a), candidate[e.a]), sub(get_front(e.b), candidate[e.b])), 0.5);
            const double residual = std::abs(dot(d, tangent));
            const double dn = norm(d);
            const double angle = dn > 1e-14
                ? std::atan2(residual, std::max(1e-14, std::sqrt(std::max(0.0, dn * dn - residual * residual)))) * 180.0 / std::acos(-1.0)
                : 0.0;
            const double original_length = norm(sub(get_wall(e.b), get_wall(e.a)));
            const double candidate_length = norm(sub(candidate[e.b], candidate[e.a]));
            const double skew = std::abs(candidate_length - original_length) / std::max(1e-14, std::max(candidate_length, original_length));
            max_angle = std::max(max_angle, angle);
            max_residual = std::max(max_residual, residual);
            max_edge_skew = std::max(max_edge_skew, skew);
        }
        return std::array<double, 3>{max_angle, max_residual, max_edge_skew};
    };

    std::vector<P> best;
    best.reserve(static_cast<size_t>(wall.shape(0)));
    for (py::ssize_t i = 0; i < wall.shape(0); ++i) best.push_back(get_wall(i));
    const auto before = evaluate(best);
    double current_angle = before[0];
    std::int64_t accepted_iterations = 0;
    double max_correction = 0.0;

    for (std::int64_t iteration = 0; iteration < max_iterations; ++iteration) {
        std::vector<P> correction(static_cast<size_t>(wall.shape(0)), P{0.0, 0.0, 0.0});
        for (const auto& e : es) {
            const P tangent = unit(sub(best[e.b], best[e.a]), "edge_tangent");
            const P da = sub(get_front(e.a), best[e.a]);
            const P db = sub(get_front(e.b), best[e.b]);
            const double residual = 0.5 * dot(add(da, db), tangent);
            const P na = get_normal(e.face);
            const P nb = get_normal(e.face);
            correction[e.a] = add(correction[e.a], mul(project_tangent(tangent, na), 0.5 * residual));
            correction[e.b] = add(correction[e.b], mul(project_tangent(tangent, nb), 0.5 * residual));
        }
        bool accepted = false;
        for (int backtrack = 0; backtrack <= 8; ++backtrack) {
            const double scale = std::ldexp(0.5, backtrack);
            std::vector<P> candidate = best;
            double local_max = 0.0;
            for (size_t i = 0; i < candidate.size(); ++i) {
                const double limit = correction_cap;
                const double n = norm(correction[i]);
                const double applied = std::min(1.0, limit / std::max(limit, n)) * scale;
                candidate[i] = add(candidate[i], mul(correction[i], applied));
                local_max = std::max(local_max, n * applied);
            }
            const auto q = evaluate(candidate);
            if (q[0] + min_improvement < current_angle && q[2] <= before[2] + 1e-10) {
                best = std::move(candidate);
                current_angle = q[0];
                max_correction = std::max(max_correction, local_max);
                ++accepted_iterations;
                accepted = true;
                break;
            }
        }
        if (!accepted) break;
    }
    if (accepted_iterations == 0) return refused("front_angle_unimproved");

    py::array_t<double> corrected(py::array::ShapeContainer(std::vector<py::ssize_t>{wall.shape(0), static_cast<py::ssize_t>(3)}));
    py::array_t<double> corrections(py::array::ShapeContainer(std::vector<py::ssize_t>{wall.shape(0), static_cast<py::ssize_t>(3)}));
    auto* out = corrected.mutable_data();
    auto* delta = corrections.mutable_data();
    for (py::ssize_t i = 0; i < wall.shape(0); ++i) {
        const auto o = static_cast<size_t>(i) * 3U;
        out[o] = best[static_cast<size_t>(i)][0];
        out[o + 1U] = best[static_cast<size_t>(i)][1];
        out[o + 2U] = best[static_cast<size_t>(i)][2];
        delta[o] = best[static_cast<size_t>(i)][0] - wd[o];
        delta[o + 1U] = best[static_cast<size_t>(i)][1] - wd[o + 1U];
        delta[o + 2U] = best[static_cast<size_t>(i)][2] - wd[o + 2U];
    }
    const auto after = evaluate(best);
    py::dict quality;
    quality["max_wall_front_before"] = before[0];
    quality["max_wall_front_after"] = after[0];
    quality["max_tangent_residual_before"] = before[1];
    quality["max_tangent_residual_after"] = after[1];
    quality["max_edge_skew_before"] = before[2];
    quality["max_edge_skew_after"] = after[2];
    quality["accepted_iterations"] = accepted_iterations;
    quality["max_correction"] = max_correction;
    py::dict result;
    result["accepted"] = true;
    result["status"] = "native_tet_bl_front_qopt_candidate_accepted";
    result["reason"] = "deterministic_projected_jacobi_improved";
    result["corrected_wall_points"] = corrected;
    result["corrections"] = corrections;
    result["quality"] = quality;
    result["candidate_discarded"] = false;
    result["publication_eligible"] = false;
    return result;
}
}

PYBIND11_MODULE(native_tet_bl_front_qopt, m) {
    m.doc() = "C++23 quality-first native Tet wall-front optimizer";
    m.def("optimize_native_tet_wall_front", &optimize,
        py::arg("wall_points"), py::arg("front_points"), py::arg("edges"),
        py::arg("face_normals"), py::arg("feature_names"), py::arg("patch_names"),
        py::arg("physical_groups"), py::arg("components"),
        py::arg("requested_layers"), py::arg("max_iterations") = 8,
        py::arg("correction_cap") = 0.25, py::arg("min_improvement") = 1e-10);
}
