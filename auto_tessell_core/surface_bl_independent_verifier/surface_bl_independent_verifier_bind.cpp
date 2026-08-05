// Separate C++23 verification path. It intentionally shares no mesh-quality implementation.
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
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
#include <utility>
#include <vector>

namespace py = pybind11;
using P = std::array<double, 3>;
using T = std::array<std::int64_t, 3>;

P d(P a, P b) noexcept { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
P addp(P a, P b) noexcept { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
P mul(P a, double s) noexcept { return {a[0] * s, a[1] * s, a[2] * s}; }
P x(P a, P b) noexcept {
    return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]};
}
double q(P a, P b) noexcept { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double l(P a) noexcept { return std::sqrt(q(a, a)); }
P unit(P a, double eps) {
    const double n = l(a);
    if (!(n > eps) || !std::isfinite(n)) return {0.0, 0.0, 0.0};
    return mul(a, 1.0 / n);
}
double clamp_unit(double value) noexcept { return std::max(-1.0, std::min(1.0, value)); }

struct B {
    P lo{std::numeric_limits<double>::infinity(), std::numeric_limits<double>::infinity(),
         std::numeric_limits<double>::infinity()};
    P hi{-std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity(),
         -std::numeric_limits<double>::infinity()};
};
void add(B& b, P p) noexcept {
    for (int i = 0; i < 3; ++i) {
        b.lo[i] = std::min(b.lo[i], p[i]);
        b.hi[i] = std::max(b.hi[i], p[i]);
    }
}
B merged(B a, const B& b) noexcept {
    for (int i = 0; i < 3; ++i) {
        a.lo[i] = std::min(a.lo[i], b.lo[i]);
        a.hi[i] = std::max(a.hi[i], b.hi[i]);
    }
    return a;
}
bool overlap(const B& a, const B& b, double eps) noexcept {
    for (int i = 0; i < 3; ++i)
        if (a.hi[i] + eps < b.lo[i] || b.hi[i] + eps < a.lo[i]) return false;
    return true;
}

struct Q2 { double x; double y; };
Q2 project(P p, int dropped) noexcept {
    if (dropped == 0) return {p[1], p[2]};
    if (dropped == 1) return {p[0], p[2]};
    return {p[0], p[1]};
}
double orient2(Q2 a, Q2 b, Q2 c) noexcept {
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}
bool between(double a, double b, double value, double eps) noexcept {
    return value >= std::min(a, b) - eps && value <= std::max(a, b) + eps;
}
bool on_segment(Q2 a, Q2 b, Q2 p, double eps) noexcept {
    return std::abs(orient2(a, b, p)) <= eps && between(a.x, b.x, p.x, eps) &&
           between(a.y, b.y, p.y, eps);
}
bool segment2_intersects(Q2 a, Q2 b, Q2 c, Q2 d, double eps) noexcept {
    const double o1 = orient2(a, b, c), o2 = orient2(a, b, d);
    const double o3 = orient2(c, d, a), o4 = orient2(c, d, b);
    if (((o1 > eps && o2 < -eps) || (o1 < -eps && o2 > eps)) &&
        ((o3 > eps && o4 < -eps) || (o3 < -eps && o4 > eps))) return true;
    return on_segment(a, b, c, eps) || on_segment(a, b, d, eps) ||
           on_segment(c, d, a, eps) || on_segment(c, d, b, eps);
}
bool point_in_triangle2(Q2 p, Q2 a, Q2 b, Q2 c, double eps) noexcept {
    const double u = orient2(a, b, p), v = orient2(b, c, p), w = orient2(c, a, p);
    return (u >= -eps && v >= -eps && w >= -eps) ||
           (u <= eps && v <= eps && w <= eps);
}

bool point_in_triangle(P p, P a, P b, P c, double eps) noexcept {
    const P n = x(d(b, a), d(c, a));
    const double nn = l(n);
    if (!(nn > eps) || std::abs(q(n, d(p, a))) > eps * std::max(1.0, nn)) return false;
    const double s0 = q(x(d(b, a), d(p, a)), n);
    const double s1 = q(x(d(c, b), d(p, b)), n);
    const double s2 = q(x(d(a, c), d(p, c)), n);
    const double tol = eps * std::max(1.0, nn * nn);
    return (s0 >= -tol && s1 >= -tol && s2 >= -tol) ||
           (s0 <= tol && s1 <= tol && s2 <= tol);
}

bool coplanar_triangles_intersect(P a0, P a1, P a2, P b0, P b1, P b2, P normal,
                                   double eps) noexcept {
    int dropped = 0;
    if (std::abs(normal[1]) > std::abs(normal[dropped])) dropped = 1;
    if (std::abs(normal[2]) > std::abs(normal[dropped])) dropped = 2;
    const Q2 a[3] = {project(a0, dropped), project(a1, dropped), project(a2, dropped)};
    const Q2 b[3] = {project(b0, dropped), project(b1, dropped), project(b2, dropped)};
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 3; ++j)
            if (segment2_intersects(a[i], a[(i + 1) % 3], b[j], b[(j + 1) % 3], eps)) return true;
    return point_in_triangle2(a[0], b[0], b[1], b[2], eps) ||
           point_in_triangle2(b[0], a[0], a[1], a[2], eps);
}

bool segment_triangle(P p0, P p1, P a, P b, P c, double eps) noexcept {
    const P n = x(d(b, a), d(c, a));
    const double nn = l(n);
    if (!(nn > eps)) return false;
    const double scale = std::max(1.0, nn);
    const double da = q(n, d(p0, a)), db = q(n, d(p1, a));
    if (std::abs(da) <= eps * scale && std::abs(db) <= eps * scale) {
        return coplanar_triangles_intersect(p0, p1, p1, a, b, c, n, eps);
    }
    if ((da > eps * scale && db > eps * scale) || (da < -eps * scale && db < -eps * scale)) return false;
    const double denom = da - db;
    if (std::abs(denom) <= eps * scale) return false;
    const double t = da / denom;
    if (t < -eps || t > 1.0 + eps) return false;
    return point_in_triangle(addp(p0, mul(d(p1, p0), t)), a, b, c, eps);
}

bool triangles_intersect(P a0, P a1, P a2, P b0, P b1, P b2, double eps) noexcept {
    const P na = x(d(a1, a0), d(a2, a0));
    const P nb = x(d(b1, b0), d(b2, b0));
    const double la = l(na), lb = l(nb);
    if (!(la > eps) || !(lb > eps)) return false;
    const P cross_normals = x(na, nb);
    const bool parallel = l(cross_normals) <= eps * la * lb;
    if (parallel) {
        if (std::abs(q(na, d(b0, a0))) > eps * std::max(1.0, la)) return false;
        return coplanar_triangles_intersect(a0, a1, a2, b0, b1, b2, na, eps);
    }
    return segment_triangle(a0, a1, b0, b1, b2, eps) || segment_triangle(a1, a2, b0, b1, b2, eps) ||
           segment_triangle(a2, a0, b0, b1, b2, eps) || segment_triangle(b0, b1, a0, a1, a2, eps) ||
           segment_triangle(b1, b2, a0, a1, a2, eps) || segment_triangle(b2, b0, a0, a1, a2, eps);
}

struct Node { B box; int left = -1; int right = -1; std::vector<std::size_t> leaf; };
int build_bvh(std::vector<Node>& nodes, const std::vector<B>& boxes, std::vector<std::size_t> ids) {
    const int index = static_cast<int>(nodes.size());
    Node node;
    for (const std::size_t id : ids) node.box = merged(node.box, boxes[id]);
    nodes.push_back(std::move(node));
    if (ids.size() <= 8) {
        nodes[index].leaf = std::move(ids);
        return index;
    }
    int axis = 0;
    double extent = nodes[index].box.hi[0] - nodes[index].box.lo[0];
    for (int i = 1; i < 3; ++i) {
        const double e = nodes[index].box.hi[i] - nodes[index].box.lo[i];
        if (e > extent) { extent = e; axis = i; }
    }
    std::sort(ids.begin(), ids.end(), [&](std::size_t a, std::size_t b) {
        const double ca = (boxes[a].lo[axis] + boxes[a].hi[axis]) * 0.5;
        const double cb = (boxes[b].lo[axis] + boxes[b].hi[axis]) * 0.5;
        return ca < cb;
    });
    const auto mid = ids.begin() + static_cast<std::ptrdiff_t>(ids.size() / 2);
    std::vector<std::size_t> left(ids.begin(), mid), right(mid, ids.end());
    nodes[index].left = build_bvh(nodes, boxes, std::move(left));
    nodes[index].right = build_bvh(nodes, boxes, std::move(right));
    return index;
}
void collect_cross(int a, int b, const std::vector<Node>& nodes, double eps,
                   std::vector<std::pair<std::size_t, std::size_t>>& pairs) {
    if (!overlap(nodes[a].box, nodes[b].box, eps)) return;
    if (nodes[a].left < 0 && nodes[b].left < 0) {
        for (const auto i : nodes[a].leaf) for (const auto j : nodes[b].leaf) if (i < j) pairs.emplace_back(i, j);
        return;
    }
    if (nodes[a].left < 0) {
        collect_cross(a, nodes[b].left, nodes, eps, pairs);
        collect_cross(a, nodes[b].right, nodes, eps, pairs);
        return;
    }
    if (nodes[b].left < 0) {
        collect_cross(nodes[a].left, b, nodes, eps, pairs);
        collect_cross(nodes[a].right, b, nodes, eps, pairs);
        return;
    }
    collect_cross(nodes[a].left, nodes[b].left, nodes, eps, pairs);
    collect_cross(nodes[a].left, nodes[b].right, nodes, eps, pairs);
    collect_cross(nodes[a].right, nodes[b].left, nodes, eps, pairs);
    collect_cross(nodes[a].right, nodes[b].right, nodes, eps, pairs);
}
void collect_self(int node, const std::vector<Node>& nodes, double eps,
                  std::vector<std::pair<std::size_t, std::size_t>>& pairs) {
    if (nodes[node].left < 0) {
        for (std::size_t i = 0; i < nodes[node].leaf.size(); ++i)
            for (std::size_t j = i + 1; j < nodes[node].leaf.size(); ++j)
                pairs.emplace_back(nodes[node].leaf[i], nodes[node].leaf[j]);
        return;
    }
    collect_self(nodes[node].left, nodes, eps, pairs);
    collect_self(nodes[node].right, nodes, eps, pairs);
    collect_cross(nodes[node].left, nodes[node].right, nodes, eps, pairs);
}

bool lineage(const py::handle& r) {
    if (!py::isinstance<py::dict>(r)) return false;
    py::dict v = py::reinterpret_borrow<py::dict>(r);
    for (const char* k : {"source_wall_edge", "source_face", "side", "layer", "patch", "feature",
                          "physical_group", "component"})
        if (!v.contains(k) || v[k].is_none()) return false;
    return true;
}
double percentile95(std::vector<double> values) {
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    const auto index = static_cast<std::size_t>(std::ceil(0.95 * static_cast<double>(values.size())) - 1.0);
    return values[std::min(index, values.size() - 1)];
}
double percentile99(std::vector<double> values) {
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    const auto index = static_cast<std::size_t>(std::ceil(0.99 * static_cast<double>(values.size())) - 1.0);
    return values[std::min(index, values.size() - 1)];
}

py::dict verify(const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
                const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& triangles,
                const py::array_t<double, py::array::c_style | py::array::forcecast>& normals,
                const py::list& provenance, bool authoritative_source, bool volume_artifact,
                double eps = 1e-12, double max_aspect_p99 = 10.0, double max_aspect = 20.0,
                double max_skew_p95 = 0.25, double max_skew = 0.50,
                double max_non_orthogonality_p95_deg = 35.0,
                double max_non_orthogonality_deg = 50.0) {
    if (points.ndim() != 2 || points.shape(1) != 3 || triangles.ndim() != 2 || triangles.shape(1) != 3 ||
        normals.ndim() != 2 || normals.shape(1) != 3)
        throw std::invalid_argument("points Nx3, triangles Tx3, normals Tx3 required");
    if (normals.shape(0) != triangles.shape(0) || provenance.size() != static_cast<std::size_t>(triangles.shape(0)))
        throw std::invalid_argument("independent inputs must match");
    for (double value : {eps, max_aspect_p99, max_aspect, max_skew_p95, max_skew,
                         max_non_orthogonality_p95_deg, max_non_orthogonality_deg})
        if (!std::isfinite(value) || value < 0.0) throw std::invalid_argument("quality limits must be finite and non-negative");

    const double* pd = points.data();
    const auto* td = triangles.data();
    const double* nd = normals.data();
    auto point = [&](std::int64_t id) {
        if (id < 0 || id >= points.shape(0)) throw std::invalid_argument("independent index out of range");
        const std::size_t o = static_cast<std::size_t>(id) * 3;
        return P{pd[o], pd[o + 1], pd[o + 2]};
    };
    std::int64_t invalid = 0, inverted = 0, duplicate = 0, nonmanifold = 0, ambiguous = 0;
    std::set<T> seen;
    std::map<std::pair<std::int64_t, std::int64_t>, std::vector<std::int64_t>> edge;
    std::vector<B> boxes(static_cast<std::size_t>(triangles.shape(0)));
    std::vector<bool> valid(static_cast<std::size_t>(triangles.shape(0)), false);
    std::vector<double> areas, aspects, skews, nonorthos;
    bool provenance_ok = true;
    py::list entities;
    for (py::ssize_t i = 0; i < triangles.shape(0); ++i) {
        const std::size_t o = static_cast<std::size_t>(i) * 3;
        T t{td[o], td[o + 1], td[o + 2]}, key = t;
        std::sort(key.begin(), key.end());
        if (!seen.insert(key).second) duplicate++;
        if (t[0] == t[1] || t[0] == t[2] || t[1] == t[2]) invalid++;
        for (int e = 0; e < 3; ++e) {
            auto a = t[e], b = t[(e + 1) % 3];
            if (a > b) std::swap(a, b);
            edge[{a, b}].push_back(i);
        }
        py::dict entity;
        entity["entity_id"] = i;
        bool geometry_ok = true;
        P a{}, b{}, c{}, n{nd[o], nd[o + 1], nd[o + 2]};
        try { a = point(t[0]); b = point(t[1]); c = point(t[2]); }
        catch (...) { geometry_ok = false; invalid++; }
        double oriented = 0.0, area = 0.0, aspect = 0.0, skew = 0.0, nonortho = 0.0;
        if (geometry_ok) {
            boxes[static_cast<std::size_t>(i)] = B{};
            add(boxes[static_cast<std::size_t>(i)], a); add(boxes[static_cast<std::size_t>(i)], b); add(boxes[static_cast<std::size_t>(i)], c);
            const P cross = x(d(b, a), d(c, a));
            const double cross_norm = l(cross), normal_norm = l(n);
            area = 0.5 * cross_norm;
            if (!(area > eps) || !(normal_norm > eps) || !std::isfinite(area)) {
                invalid++;
            } else {
                oriented = 0.5 * q(cross, n) / normal_norm;
                if (!std::isfinite(oriented) || oriented <= eps) {
                    if (oriented < -eps) inverted++; else invalid++;
                } else {
                    const double e0 = l(d(b, a)), e1 = l(d(c, b)), e2 = l(d(a, c));
                    const double longest = std::max({e0, e1, e2}), shortest = std::min({e0, e1, e2});
                    if (!(longest > eps) || !(shortest > eps)) invalid++;
                    else {
                        aspect = longest * longest / (2.0 * std::sqrt(3.0) * area);
                        skew = 1.0 - shortest / longest;
                        const P geometric_unit = unit(cross, eps), supplied_unit = unit(n, eps);
                        nonortho = std::acos(clamp_unit(q(geometric_unit, supplied_unit))) * 180.0 / std::acos(-1.0);
                        if (!std::isfinite(aspect) || !std::isfinite(skew) || !std::isfinite(nonortho)) invalid++;
                        else { valid[static_cast<std::size_t>(i)] = true; areas.push_back(area); aspects.push_back(aspect); skews.push_back(skew); nonorthos.push_back(nonortho); }
                    }
                }
            }
        }
        entity["oriented_area"] = oriented; entity["area"] = area; entity["aspect_ratio"] = aspect;
        entity["tangential_skew"] = skew; entity["non_orthogonality_deg"] = nonortho;
        const bool ok = lineage(provenance[static_cast<std::size_t>(i)]);
        provenance_ok = provenance_ok && ok;
        entity["lineage_complete"] = ok; entity["provenance"] = provenance[static_cast<std::size_t>(i)]; entities.append(entity);
    }
    for (const auto& [k, v] : edge) if (v.size() > 2) nonmanifold++;
    std::vector<std::size_t> valid_ids;
    for (std::size_t i = 0; i < valid.size(); ++i) if (valid[i]) valid_ids.push_back(i);
    std::vector<Node> nodes; std::vector<std::pair<std::size_t, std::size_t>> candidates;
    if (!valid_ids.empty()) { const int root = build_bvh(nodes, boxes, std::move(valid_ids)); collect_self(root, nodes, eps, candidates); }
    for (const auto& [i, j] : candidates) {
        const T ti{td[i * 3], td[i * 3 + 1], td[i * 3 + 2]}, tj{td[j * 3], td[j * 3 + 1], td[j * 3 + 2]};
        bool shared = false; for (auto id : ti) for (auto other : tj) shared = shared || id == other;
        if (shared) continue;
        const P a0 = point(ti[0]), a1 = point(ti[1]), a2 = point(ti[2]);
        const P b0 = point(tj[0]), b1 = point(tj[1]), b2 = point(tj[2]);
        if (triangles_intersect(a0, a1, a2, b0, b1, b2, eps)) ambiguous++;
    }
    const double min_area = areas.empty() ? 0.0 : *std::min_element(areas.begin(), areas.end());
    const double aspect_p99 = percentile99(aspects), aspect_max = aspects.empty() ? 0.0 : *std::max_element(aspects.begin(), aspects.end());
    const double skew_p95 = percentile95(skews), skew_max = skews.empty() ? 0.0 : *std::max_element(skews.begin(), skews.end());
    const double nonortho_p95 = percentile95(nonorthos), nonortho_max = nonorthos.empty() ? 0.0 : *std::max_element(nonorthos.begin(), nonorthos.end());
    const bool quality_ok = !areas.empty() && aspect_p99 <= max_aspect_p99 && aspect_max <= max_aspect && skew_p95 <= max_skew_p95 &&
                            skew_max <= max_skew && nonortho_p95 <= max_non_orthogonality_p95_deg && nonortho_max <= max_non_orthogonality_deg;
    py::dict quality;
    quality["recomputed"] = true; quality["min_area"] = min_area; quality["aspect_ratio_p99"] = aspect_p99; quality["aspect_ratio_max"] = aspect_max;
    quality["tangential_skew_p95"] = skew_p95; quality["tangential_skew_max"] = skew_max;
    quality["non_orthogonality_p95_deg"] = nonortho_p95; quality["non_orthogonality_max_deg"] = nonortho_max;
    py::dict thresholds;
    thresholds["aspect_ratio_p99"] = max_aspect_p99; thresholds["aspect_ratio_max"] = max_aspect;
    thresholds["tangential_skew_p95"] = max_skew_p95; thresholds["tangential_skew_max"] = max_skew;
    thresholds["non_orthogonality_p95_deg"] = max_non_orthogonality_p95_deg;
    thresholds["non_orthogonality_max_deg"] = max_non_orthogonality_deg;
    quality["gate_passed"] = quality_ok; quality["thresholds"] = thresholds;
    py::dict top; top["invalid"] = invalid; top["inverted"] = inverted; top["duplicate"] = duplicate; top["non_manifold"] = nonmanifold;
    top["non_incident_intersection_or_ambiguity"] = ambiguous; top["broad_phase_candidate_pairs"] = candidates.size(); top["narrow_phase_intersections"] = ambiguous;
    const bool topology_ok = invalid == 0 && inverted == 0 && duplicate == 0 && nonmanifold == 0 && ambiguous == 0;
    const bool base = authoritative_source && topology_ok && provenance_ok && quality_ok && triangles.shape(0) > 0;
    std::string verdict = !authoritative_source ? "UNVERIFIED" : (base ? "PASS_FOR_REVIEW" : "REFUSED");
    py::dict out; out["verdict"] = verdict; out["source_authority_verified"] = authoritative_source; out["volume_artifact_present"] = volume_artifact;
    out["topology"] = top; out["provenance_complete"] = provenance_ok; out["per_entity"] = entities; out["quality"] = quality;
    out["surface_quality_recomputed"] = true; out["volume_quality_recomputed"] = volume_artifact;
    out["reason"] = verdict == "PASS_FOR_REVIEW" ? "independent_gates_passed" : (!authoritative_source ? "missing_authoritative_source" : (!quality_ok ? "surface_quality_gate_failed" : "independent_topology_or_lineage_gate_failed"));
    return out;
}

PYBIND11_MODULE(native_surface_bl_independent_verifier, m) {
    m.doc() = "Independent C++23 surface BL verifier";
    m.def("verify_surface_artifact", &verify, py::arg("points"), py::arg("triangles"), py::arg("normals"), py::arg("provenance"),
          py::arg("authoritative_source"), py::arg("volume_artifact"), py::arg("epsilon") = 1e-12,
          py::arg("max_aspect_p99") = 10.0, py::arg("max_aspect") = 20.0, py::arg("max_skew_p95") = 0.25,
          py::arg("max_skew") = 0.50, py::arg("max_non_orthogonality_p95_deg") = 35.0,
          py::arg("max_non_orthogonality_deg") = 50.0);
}
