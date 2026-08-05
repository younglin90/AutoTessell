#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;
using P = std::array<double, 3>;
using T = std::array<std::int64_t, 3>;

P sub(P a, P b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
P cross(P a, P b) { return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]}; }
double dot(P a, P b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double norm(P a) { return std::sqrt(dot(a, a)); }

py::dict refuse(const char* reason, std::int64_t requested) {
    py::dict r;
    r["accepted"] = false;
    r["status"] = "surface_bl_actual_transaction_refused";
    r["reason"] = reason;
    r["requested_layers"] = requested;
    r["actual_layers"] = 0;
    r["candidate_discarded"] = true;
    r["publication_eligible"] = false;
    r["runtime_route"] = "private_default_off";
    r["generated_faces"] = py::list();
    return r;
}

bool text(const py::dict& d, const char* key) {
    return d.contains(key) && !d[key].is_none() && !py::str(d[key]).cast<std::string>().empty();
}

std::vector<P> read_points(const py::array_t<double, py::array::c_style | py::array::forcecast>& a) {
    if (a.ndim() != 2 || a.shape(1) != 3) throw std::invalid_argument("points_shape");
    const double* data = a.data();
    std::vector<P> result;
    result.reserve(static_cast<size_t>(a.shape(0)));
    for (py::ssize_t i = 0; i < a.shape(0); ++i) {
        P p{data[static_cast<size_t>(i) * 3], data[static_cast<size_t>(i) * 3 + 1], data[static_cast<size_t>(i) * 3 + 2]};
        if (!std::isfinite(p[0]) || !std::isfinite(p[1]) || !std::isfinite(p[2])) throw std::invalid_argument("point_not_finite");
        result.push_back(p);
    }
    return result;
}

std::vector<T> read_triangles(const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& a, std::int64_t point_count, const char* name) {
    if (a.ndim() != 2 || a.shape(1) != 3) throw std::invalid_argument(std::string(name) + "_shape");
    const auto* data = a.data();
    std::vector<T> result;
    result.reserve(static_cast<size_t>(a.shape(0)));
    for (py::ssize_t i = 0; i < a.shape(0); ++i) {
        T t{data[static_cast<size_t>(i) * 3], data[static_cast<size_t>(i) * 3 + 1], data[static_cast<size_t>(i) * 3 + 2]};
        for (auto id : t) if (id < 0 || id >= point_count) throw std::invalid_argument(std::string(name) + "_index_out_of_range");
        result.push_back(t);
    }
    return result;
}

bool authority_ok(const py::dict& authority) {
    for (const char* key : {"source_kind", "source_sha256", "boundary_mapping_sha256", "physical_group_sha256", "provenance"}) {
        if (!text(authority, key)) return false;
    }
    return true;
}

py::dict seal(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& source_triangles,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& candidate_triangles,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& source_normals,
    const py::dict& authority,
    const py::dict& writer_receipt,
    const py::list& provenance,
    std::int64_t requested_layers,
    double epsilon = 1.0e-12) {
    if (requested_layers < 0) return refuse("requested_layers_invalid", requested_layers);
    auto p = read_points(points);
    auto source = read_triangles(source_triangles, static_cast<std::int64_t>(p.size()), "source_triangles");
    auto candidate = read_triangles(candidate_triangles, static_cast<std::int64_t>(p.size()), "candidate_triangles");
    if (source_normals.ndim() != 2 || source_normals.shape(1) != 3 || source_normals.shape(0) != source_triangles.shape(0)) {
        throw std::invalid_argument("source_normals_shape");
    }
    if (!authority_ok(authority)) return refuse("authority_unsealed", requested_layers);
    if (requested_layers > 0 && (!writer_receipt.contains("accepted") || !writer_receipt["accepted"].cast<bool>())) {
        return refuse("writer_receipt_refused", requested_layers);
    }
    if (requested_layers == 0) {
        if (candidate != source || provenance.size() != 0) return refuse("bl0_identity_mismatch", 0);
        py::dict r;
        r["accepted"] = true;
        r["status"] = "surface_bl_actual_transaction_bl0_identity";
        r["reason"] = "disabled_identity";
        r["requested_layers"] = 0;
        r["actual_layers"] = 0;
        r["candidate_discarded"] = false;
        r["publication_eligible"] = false;
        r["runtime_route"] = "private_default_off";
        r["generated_faces"] = py::list();
        r["topology_invalid"] = 0;
        r["topology_inverted"] = 0;
        r["topology_duplicate"] = 0;
        r["topology_non_manifold"] = 0;
        r["source_immutable"] = true;
        return r;
    }
    if (candidate.size() < source.size()) return refuse("source_faces_not_preserved", requested_layers);
    for (size_t i = 0; i < source.size(); ++i) if (candidate[i] != source[i]) return refuse("source_face_prefix_changed", requested_layers);
    if (provenance.size() * 2 != candidate.size() - source.size()) return refuse("generated_lineage_length_mismatch", requested_layers);

    std::set<T> seen;
    std::map<std::pair<std::int64_t, std::int64_t>, int> edges;
    std::int64_t invalid = 0, duplicate = 0, non_manifold = 0, inverted = 0;
    const double* nd = source_normals.data();
    for (size_t fi = 0; fi < candidate.size(); ++fi) {
        const T& t = candidate[fi];
        T key = t;
        std::sort(key.begin(), key.end());
        if (!seen.insert(key).second) ++duplicate;
        if (t[0] == t[1] || t[0] == t[2] || t[1] == t[2]) ++invalid;
        for (int e = 0; e < 3; ++e) {
            auto a = t[e], b = t[(e + 1) % 3];
            if (a > b) std::swap(a, b);
            if (++edges[{a, b}] > 2) ++non_manifold;
        }
        P a = p[static_cast<size_t>(t[0])], b = p[static_cast<size_t>(t[1])], c = p[static_cast<size_t>(t[2])];
        if (!(norm(cross(sub(b, a), sub(c, a))) > epsilon)) ++invalid;
        if (fi < source.size()) {
            P n{nd[fi * 3], nd[fi * 3 + 1], nd[fi * 3 + 2]};
            double nn = norm(n);
            double oriented = nn > epsilon ? 0.5 * dot(cross(sub(b, a), sub(c, a)), n) / nn : -1.0;
            if (!(oriented > epsilon)) ++inverted;
        }
    }
    for (size_t i = 0; i < provenance.size(); ++i) {
        py::dict row = provenance[i].cast<py::dict>();
        for (const char* key : {"source_wall_edge", "source_face", "layer", "patch", "feature", "physical_group", "component", "provenance"}) {
            if (!text(row, key)) return refuse("direct_id_or_provenance_missing", requested_layers);
        }
        if (!row.contains("final_face_ids")) return refuse("direct_id_or_provenance_missing", requested_layers);
        py::sequence ids = row["final_face_ids"].cast<py::sequence>();
        if (ids.size() != 2 || ids[0].cast<std::int64_t>() != static_cast<std::int64_t>(source.size() + 2 * i) ||
            ids[1].cast<std::int64_t>() != static_cast<std::int64_t>(source.size() + 2 * i + 1)) {
            return refuse("final_face_id_binding_mismatch", requested_layers);
        }
    }
    for (const auto& [edge, count] : edges) if (count > 2) ++non_manifold;
    if (invalid || inverted || duplicate || non_manifold) return refuse("final_surface_topology_failed", requested_layers);

    py::list out;
    for (size_t i = source.size(); i < candidate.size(); ++i) {
        py::list row;
        for (auto id : candidate[i]) row.append(id);
        out.append(row);
    }
    py::dict result;
    result["accepted"] = true;
    result["status"] = "surface_bl_actual_transaction_ready";
    result["reason"] = "source_authority_lineage_topology_bound";
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = requested_layers;
    result["candidate_discarded"] = false;
    result["publication_eligible"] = false;
    result["runtime_route"] = "private_default_off";
    result["generated_faces"] = out;
    result["topology_invalid"] = invalid;
    result["topology_inverted"] = inverted;
    result["topology_duplicate"] = duplicate;
    result["topology_non_manifold"] = non_manifold;
    result["source_immutable"] = true;
    return result;
}

PYBIND11_MODULE(native_surface_bl_actual_transaction, m) {
    m.doc() = "Private C++23 surface BL authority-bound transaction sealer";
    m.def("seal_surface_bl_actual_transaction", &seal, py::arg("points"), py::arg("source_triangles"), py::arg("candidate_triangles"), py::arg("source_normals"), py::arg("authority"), py::arg("writer_receipt"), py::arg("provenance"), py::arg("requested_layers"), py::arg("epsilon") = 1.0e-12);
}
