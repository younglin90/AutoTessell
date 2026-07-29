// Native tetrahedral quality-optimizer infrastructure.
//
// QOPT0 intentionally changes no mesh topology.  It provides deterministic local
// cavity extraction and local quality-vector comparison so later split/collapse/
// flip/smooth operations can share one guarded accept/rollback path.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace py = pybind11;

namespace {

using Tet = std::array<long long, 4>;
using Point = std::array<double, 3>;

struct VectorHash {
    size_t operator()(const long long value) const
    {
        return std::hash<long long>{}(value);
    }
};

bool valid_tet(const Tet& tet, const py::ssize_t point_count)
{
    Tet sorted = tet;
    std::sort(sorted.begin(), sorted.end());
    return sorted.front() >= 0 && sorted.back() < point_count
        && std::adjacent_find(sorted.begin(), sorted.end()) == sorted.end();
}

double tet_shape_quality(
    const py::detail::unchecked_reference<double, 2>& points,
    const Tet& tet)
{
    std::array<std::array<double, 3>, 4> vertex{};
    for (size_t local = 0; local < 4; ++local) {
        for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
            vertex[local][coordinate] = points(
                static_cast<py::ssize_t>(tet[local]),
                static_cast<py::ssize_t>(coordinate));
        }
    }

    const auto subtract = [](const std::array<double, 3>& left,
                             const std::array<double, 3>& right) {
        return std::array<double, 3>{
            left[0] - right[0], left[1] - right[1], left[2] - right[2]};
    };
    const auto dot = [](const std::array<double, 3>& left,
                        const std::array<double, 3>& right) {
        return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
    };
    const auto cross = [](const std::array<double, 3>& left,
                          const std::array<double, 3>& right) {
        return std::array<double, 3>{
            left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0]};
    };
    const auto norm = [&](const std::array<double, 3>& vector) {
        return std::sqrt(dot(vector, vector));
    };

    const std::array<std::array<double, 3>, 6> edges = {{
        subtract(vertex[1], vertex[0]), subtract(vertex[2], vertex[0]),
        subtract(vertex[3], vertex[0]), subtract(vertex[2], vertex[1]),
        subtract(vertex[3], vertex[1]), subtract(vertex[3], vertex[2])}};
    double longest_edge = 0.0;
    for (const auto& edge : edges) {
        longest_edge = std::max(longest_edge, norm(edge));
    }
    if (longest_edge <= 1e-30) {
        return 0.0;
    }
    const double volume6 = std::abs(dot(edges[0], cross(edges[1], edges[2])));
    const double volume = volume6 / 6.0;
    return 8.48 * volume / (longest_edge * longest_edge * longest_edge);
}

double tet_volume6(const std::vector<Point>& points, const Tet& tet)
{
    const auto& a = points[static_cast<size_t>(tet[0])];
    const auto& b = points[static_cast<size_t>(tet[1])];
    const auto& c = points[static_cast<size_t>(tet[2])];
    const auto& d = points[static_cast<size_t>(tet[3])];
    const std::array<double, 3> ab{b[0] - a[0], b[1] - a[1], b[2] - a[2]};
    const std::array<double, 3> ac{c[0] - a[0], c[1] - a[1], c[2] - a[2]};
    const std::array<double, 3> ad{d[0] - a[0], d[1] - a[1], d[2] - a[2]};
    return ab[0] * (ac[1] * ad[2] - ac[2] * ad[1])
        - ab[1] * (ac[0] * ad[2] - ac[2] * ad[0])
        + ab[2] * (ac[0] * ad[1] - ac[1] * ad[0]);
}

double tet_shape_quality(const std::vector<Point>& points, const Tet& tet)
{
    std::array<Point, 4> vertex{};
    for (size_t local = 0; local < 4; ++local) {
        vertex[local] = points[static_cast<size_t>(tet[local])];
    }
    const auto subtract = [](const Point& left, const Point& right) {
        return Point{left[0] - right[0], left[1] - right[1], left[2] - right[2]};
    };
    const auto dot = [](const Point& left, const Point& right) {
        return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
    };
    const auto cross = [](const Point& left, const Point& right) {
        return Point{
            left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0]};
    };
    const auto norm = [&](const Point& vector) {
        return std::sqrt(dot(vector, vector));
    };

    const std::array<Point, 6> edges = {{
        subtract(vertex[1], vertex[0]), subtract(vertex[2], vertex[0]),
        subtract(vertex[3], vertex[0]), subtract(vertex[2], vertex[1]),
        subtract(vertex[3], vertex[1]), subtract(vertex[3], vertex[2])}};
    double longest_edge = 0.0;
    for (const auto& edge : edges) {
        longest_edge = std::max(longest_edge, norm(edge));
    }
    if (longest_edge <= 1e-30) {
        return 0.0;
    }
    const double volume = std::abs(tet_volume6(points, tet)) / 6.0;
    return 8.48 * volume / (longest_edge * longest_edge * longest_edge);
}

std::vector<Point> load_points(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const char* name)
{
    if (points_array.ndim() != 2 || points_array.shape(1) != 3) {
        throw std::invalid_argument(std::string(name) + " expects points shaped (N, 3)");
    }
    const auto input = points_array.unchecked<2>();
    std::vector<Point> points;
    points.reserve(static_cast<size_t>(input.shape(0)));
    for (py::ssize_t row = 0; row < input.shape(0); ++row) {
        Point point{};
        for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
            const double value = input(row, static_cast<py::ssize_t>(coordinate));
            if (!std::isfinite(value)) {
                throw std::invalid_argument(std::string(name) + " requires finite points");
            }
            point[coordinate] = value;
        }
        points.push_back(point);
    }
    return points;
}

std::vector<Tet> load_tets(
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array,
    const py::ssize_t point_count,
    const char* name)
{
    if (tets_array.ndim() != 2 || tets_array.shape(1) != 4) {
        throw std::invalid_argument(std::string(name) + " expects tets shaped (M, 4)");
    }
    const auto input = tets_array.unchecked<2>();
    std::vector<Tet> tets;
    tets.reserve(static_cast<size_t>(input.shape(0)));
    for (py::ssize_t row = 0; row < input.shape(0); ++row) {
        Tet tet{};
        for (size_t local = 0; local < 4; ++local) {
            tet[local] = input(row, static_cast<py::ssize_t>(local));
        }
        if (!valid_tet(tet, point_count)) {
            throw std::invalid_argument(std::string(name) + " received invalid tet indices");
        }
        tets.push_back(tet);
    }
    return tets;
}

int compare_sorted_vectors(
    std::vector<double> old_q,
    std::vector<double> new_q,
    const double eps)
{
    std::sort(old_q.begin(), old_q.end());
    std::sort(new_q.begin(), new_q.end());
    const size_t n = std::min(old_q.size(), new_q.size());
    for (size_t index = 0; index < n; ++index) {
        if (new_q[index] + eps < old_q[index]) {
            return -1;
        }
        if (new_q[index] > old_q[index] + eps) {
            return 1;
        }
    }
    if (new_q.size() < old_q.size()) {
        return 1;
    }
    if (new_q.size() > old_q.size()) {
        return -1;
    }
    return 0;
}

py::tuple local_cavity_quality_vectors(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& seed_tets_array,
    const int max_ring)
{
    if (points_array.ndim() != 2 || points_array.shape(1) != 3) {
        throw std::invalid_argument("local_cavity_quality_vectors expects points shaped (N, 3)");
    }
    if (seed_tets_array.ndim() != 1) {
        throw std::invalid_argument("local_cavity_quality_vectors expects seed_tets shaped (K,)");
    }
    if (max_ring < 0 || max_ring > 1) {
        throw std::invalid_argument("max_ring must be 0 or 1");
    }

    const auto points = points_array.unchecked<2>();
    const auto seeds = seed_tets_array.unchecked<1>();
    const std::vector<Tet> tets = load_tets(
        tets_array, points_array.shape(0), "local_cavity_quality_vectors");

    std::unordered_map<long long, std::vector<long long>, VectorHash> vertex_to_tets;
    vertex_to_tets.reserve(tets.size() * 2U);
    for (size_t tet_index = 0; tet_index < tets.size(); ++tet_index) {
        for (const long long vertex : tets[tet_index]) {
            vertex_to_tets[vertex].push_back(static_cast<long long>(tet_index));
        }
    }

    const py::ssize_t n_seeds = seeds.shape(0);
    std::vector<long long> offsets(static_cast<size_t>(n_seeds) + 1U, 0);
    std::vector<long long> flat_tets;
    std::vector<double> flat_quality;
    long long max_cavity_size = 0;

    for (py::ssize_t seed_row = 0; seed_row < n_seeds; ++seed_row) {
        const long long seed_index = seeds(seed_row);
        if (seed_index < 0 || seed_index >= static_cast<long long>(tets.size())) {
            throw std::invalid_argument("seed_tets contains out-of-range index");
        }

        std::vector<long long> cavity;
        if (max_ring == 0) {
            cavity.push_back(seed_index);
        } else {
            std::unordered_set<long long, VectorHash> seen;
            for (const long long vertex : tets[static_cast<size_t>(seed_index)]) {
                const auto found = vertex_to_tets.find(vertex);
                if (found == vertex_to_tets.end()) {
                    continue;
                }
                for (const long long tet_index : found->second) {
                    if (seen.insert(tet_index).second) {
                        cavity.push_back(tet_index);
                    }
                }
            }
            std::sort(cavity.begin(), cavity.end());
        }

        std::vector<double> qualities;
        qualities.reserve(cavity.size());
        for (const long long tet_index : cavity) {
            qualities.push_back(tet_shape_quality(
                points, tets[static_cast<size_t>(tet_index)]));
        }
        std::sort(qualities.begin(), qualities.end());

        flat_tets.insert(flat_tets.end(), cavity.begin(), cavity.end());
        flat_quality.insert(flat_quality.end(), qualities.begin(), qualities.end());
        offsets[static_cast<size_t>(seed_row) + 1U] = static_cast<long long>(flat_tets.size());
        max_cavity_size = std::max(max_cavity_size, static_cast<long long>(cavity.size()));
    }

    py::array_t<long long> offsets_array({static_cast<py::ssize_t>(offsets.size())});
    py::array_t<long long> tets_out({static_cast<py::ssize_t>(flat_tets.size())});
    py::array_t<double> quality_out({static_cast<py::ssize_t>(flat_quality.size())});
    auto offsets_view = offsets_array.mutable_unchecked<1>();
    auto tets_view = tets_out.mutable_unchecked<1>();
    auto quality_view = quality_out.mutable_unchecked<1>();
    for (size_t index = 0; index < offsets.size(); ++index) {
        offsets_view(static_cast<py::ssize_t>(index)) = offsets[index];
    }
    for (size_t index = 0; index < flat_tets.size(); ++index) {
        tets_view(static_cast<py::ssize_t>(index)) = flat_tets[index];
        quality_view(static_cast<py::ssize_t>(index)) = flat_quality[index];
    }

    py::dict stats;
    stats["n_cavities"] = n_seeds;
    stats["max_cavity_size"] = max_cavity_size;
    stats["max_ring"] = max_ring;
    return py::make_tuple(offsets_array, tets_out, quality_out, stats);
}

int compare_quality_vectors(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& old_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& new_array,
    const double eps)
{
    if (old_array.ndim() != 1 || new_array.ndim() != 1) {
        throw std::invalid_argument("compare_quality_vectors expects 1D arrays");
    }
    if (eps < 0.0) {
        throw std::invalid_argument("eps must be non-negative");
    }
    const auto old_input = old_array.unchecked<1>();
    const auto new_input = new_array.unchecked<1>();
    std::vector<double> old_q;
    std::vector<double> new_q;
    old_q.reserve(static_cast<size_t>(old_input.shape(0)));
    new_q.reserve(static_cast<size_t>(new_input.shape(0)));
    for (py::ssize_t index = 0; index < old_input.shape(0); ++index) {
        const double value = old_input(index);
        if (!std::isfinite(value)) {
            throw std::invalid_argument("old quality vector contains non-finite value");
        }
        old_q.push_back(value);
    }
    for (py::ssize_t index = 0; index < new_input.shape(0); ++index) {
        const double value = new_input(index);
        if (!std::isfinite(value)) {
            throw std::invalid_argument("new quality vector contains non-finite value");
        }
        new_q.push_back(value);
    }
    return compare_sorted_vectors(std::move(old_q), std::move(new_q), eps);
}

bool quality_vector_accepts(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& old_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& new_array,
    const double eps)
{
    return compare_quality_vectors(old_array, new_array, eps) > 0;
}

py::tuple apply_guarded_vertex_moves(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& vertices_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& targets_array,
    const double eps)
{
    if (vertices_array.ndim() != 1) {
        throw std::invalid_argument("apply_guarded_vertex_moves expects vertices shaped (K,)");
    }
    if (targets_array.ndim() != 2 || targets_array.shape(1) != 3
        || targets_array.shape(0) != vertices_array.shape(0)) {
        throw std::invalid_argument("apply_guarded_vertex_moves expects targets shaped (K, 3)");
    }
    if (eps < 0.0) {
        throw std::invalid_argument("eps must be non-negative");
    }

    std::vector<Point> points = load_points(points_array, "apply_guarded_vertex_moves");
    const std::vector<Tet> tets = load_tets(
        tets_array, static_cast<py::ssize_t>(points.size()), "apply_guarded_vertex_moves");
    const auto vertices = vertices_array.unchecked<1>();
    const auto targets = targets_array.unchecked<2>();

    std::unordered_map<long long, std::vector<size_t>, VectorHash> vertex_to_tets;
    vertex_to_tets.reserve(tets.size() * 2U);
    for (size_t tet_index = 0; tet_index < tets.size(); ++tet_index) {
        for (const long long vertex : tets[tet_index]) {
            vertex_to_tets[vertex].push_back(tet_index);
        }
    }

    long long attempted = 0;
    long long accepted = 0;
    long long rejected_volume = 0;
    long long rejected_quality = 0;
    double max_displacement = 0.0;

    for (py::ssize_t row = 0; row < vertices.shape(0); ++row) {
        const long long vertex = vertices(row);
        if (vertex < 0 || vertex >= static_cast<long long>(points.size())) {
            throw std::invalid_argument("apply_guarded_vertex_moves received out-of-range vertex");
        }
        Point target{};
        for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
            const double value = targets(row, static_cast<py::ssize_t>(coordinate));
            if (!std::isfinite(value)) {
                throw std::invalid_argument("apply_guarded_vertex_moves requires finite targets");
            }
            target[coordinate] = value;
        }

        const auto incident_found = vertex_to_tets.find(vertex);
        if (incident_found == vertex_to_tets.end() || incident_found->second.empty()) {
            continue;
        }
        ++attempted;

        std::vector<double> old_quality;
        std::vector<double> new_quality;
        old_quality.reserve(incident_found->second.size());
        new_quality.reserve(incident_found->second.size());
        std::vector<double> old_volumes;
        old_volumes.reserve(incident_found->second.size());
        bool valid = true;
        for (const size_t tet_index : incident_found->second) {
            const double volume = tet_volume6(points, tets[tet_index]);
            old_volumes.push_back(volume);
            old_quality.push_back(tet_shape_quality(points, tets[tet_index]));
        }

        const Point old_point = points[static_cast<size_t>(vertex)];
        points[static_cast<size_t>(vertex)] = target;
        for (size_t local = 0; local < incident_found->second.size(); ++local) {
            const size_t tet_index = incident_found->second[local];
            const double new_volume = tet_volume6(points, tets[tet_index]);
            const double old_volume = old_volumes[local];
            if (std::abs(new_volume) <= 1e-20
                || std::signbit(new_volume) != std::signbit(old_volume)) {
                valid = false;
                break;
            }
            new_quality.push_back(tet_shape_quality(points, tets[tet_index]));
        }
        if (!valid) {
            points[static_cast<size_t>(vertex)] = old_point;
            ++rejected_volume;
            continue;
        }
        if (compare_sorted_vectors(std::move(old_quality), std::move(new_quality), eps) < 0) {
            points[static_cast<size_t>(vertex)] = old_point;
            ++rejected_quality;
            continue;
        }

        const double dx = target[0] - old_point[0];
        const double dy = target[1] - old_point[1];
        const double dz = target[2] - old_point[2];
        max_displacement = std::max(max_displacement, std::sqrt(dx * dx + dy * dy + dz * dz));
        ++accepted;
    }

    py::array_t<double> output({static_cast<py::ssize_t>(points.size()), py::ssize_t{3}});
    auto output_view = output.mutable_unchecked<2>();
    for (size_t row = 0; row < points.size(); ++row) {
        for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
            output_view(static_cast<py::ssize_t>(row), static_cast<py::ssize_t>(coordinate))
                = points[row][coordinate];
        }
    }
    py::dict stats;
    stats["attempted"] = attempted;
    stats["accepted"] = accepted;
    stats["rejected_volume"] = rejected_volume;
    stats["rejected_quality"] = rejected_quality;
    stats["max_displacement"] = max_displacement;
    return py::make_tuple(output, stats);
}

py::tuple apply_guarded_vertex_moves_csr(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& incident_offsets_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& incident_tets_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& vertices_array,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& targets_array,
    const double eps)
{
    if (vertices_array.ndim() != 1) {
        throw std::invalid_argument("apply_guarded_vertex_moves_csr expects vertices shaped (K,)");
    }
    if (targets_array.ndim() != 2 || targets_array.shape(1) != 3
        || targets_array.shape(0) != vertices_array.shape(0)) {
        throw std::invalid_argument("apply_guarded_vertex_moves_csr expects targets shaped (K, 3)");
    }
    if (incident_offsets_array.ndim() != 1 || incident_tets_array.ndim() != 1) {
        throw std::invalid_argument("apply_guarded_vertex_moves_csr expects 1D CSR arrays");
    }
    if (eps < 0.0) {
        throw std::invalid_argument("eps must be non-negative");
    }

    std::vector<Point> points = load_points(points_array, "apply_guarded_vertex_moves_csr");
    const std::vector<Tet> tets = load_tets(
        tets_array, static_cast<py::ssize_t>(points.size()), "apply_guarded_vertex_moves_csr");
    if (incident_offsets_array.shape(0) != static_cast<py::ssize_t>(points.size() + 1U)) {
        throw std::invalid_argument("incident_offsets must have length points + 1");
    }

    const auto offsets = incident_offsets_array.unchecked<1>();
    const auto incidents = incident_tets_array.unchecked<1>();
    for (py::ssize_t index = 0; index < offsets.shape(0); ++index) {
        if (offsets(index) < 0 || offsets(index) > incident_tets_array.shape(0)) {
            throw std::invalid_argument("incident_offsets contains invalid offset");
        }
        if (index > 0 && offsets(index) < offsets(index - 1)) {
            throw std::invalid_argument("incident_offsets must be sorted");
        }
    }
    for (py::ssize_t index = 0; index < incidents.shape(0); ++index) {
        if (incidents(index) < 0 || incidents(index) >= static_cast<long long>(tets.size())) {
            throw std::invalid_argument("incident_tets contains invalid tet index");
        }
    }

    const auto vertices = vertices_array.unchecked<1>();
    const auto targets = targets_array.unchecked<2>();
    long long attempted = 0;
    long long accepted = 0;
    long long rejected_volume = 0;
    long long rejected_quality = 0;
    double max_displacement = 0.0;

    for (py::ssize_t row = 0; row < vertices.shape(0); ++row) {
        const long long vertex = vertices(row);
        if (vertex < 0 || vertex >= static_cast<long long>(points.size())) {
            throw std::invalid_argument("apply_guarded_vertex_moves_csr received out-of-range vertex");
        }
        const long long start = offsets(vertex);
        const long long end = offsets(vertex + 1);
        if (start == end) {
            continue;
        }

        Point target{};
        for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
            const double value = targets(row, static_cast<py::ssize_t>(coordinate));
            if (!std::isfinite(value)) {
                throw std::invalid_argument("apply_guarded_vertex_moves_csr requires finite targets");
            }
            target[coordinate] = value;
        }
        ++attempted;

        std::vector<double> old_quality;
        std::vector<double> new_quality;
        std::vector<double> old_volumes;
        old_quality.reserve(static_cast<size_t>(end - start));
        new_quality.reserve(static_cast<size_t>(end - start));
        old_volumes.reserve(static_cast<size_t>(end - start));
        for (long long cursor = start; cursor < end; ++cursor) {
            const size_t tet_index = static_cast<size_t>(incidents(cursor));
            old_volumes.push_back(tet_volume6(points, tets[tet_index]));
            old_quality.push_back(tet_shape_quality(points, tets[tet_index]));
        }

        const Point old_point = points[static_cast<size_t>(vertex)];
        points[static_cast<size_t>(vertex)] = target;
        bool valid = true;
        for (long long cursor = start; cursor < end; ++cursor) {
            const size_t local = static_cast<size_t>(cursor - start);
            const size_t tet_index = static_cast<size_t>(incidents(cursor));
            const double new_volume = tet_volume6(points, tets[tet_index]);
            const double old_volume = old_volumes[local];
            if (std::abs(new_volume) <= 1e-20
                || std::signbit(new_volume) != std::signbit(old_volume)) {
                valid = false;
                break;
            }
            new_quality.push_back(tet_shape_quality(points, tets[tet_index]));
        }
        if (!valid) {
            points[static_cast<size_t>(vertex)] = old_point;
            ++rejected_volume;
            continue;
        }
        if (compare_sorted_vectors(std::move(old_quality), std::move(new_quality), eps) < 0) {
            points[static_cast<size_t>(vertex)] = old_point;
            ++rejected_quality;
            continue;
        }

        const double dx = target[0] - old_point[0];
        const double dy = target[1] - old_point[1];
        const double dz = target[2] - old_point[2];
        max_displacement = std::max(max_displacement, std::sqrt(dx * dx + dy * dy + dz * dz));
        ++accepted;
    }

    py::array_t<double> output({static_cast<py::ssize_t>(points.size()), py::ssize_t{3}});
    auto output_view = output.mutable_unchecked<2>();
    for (size_t row = 0; row < points.size(); ++row) {
        for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
            output_view(static_cast<py::ssize_t>(row), static_cast<py::ssize_t>(coordinate))
                = points[row][coordinate];
        }
    }
    py::dict stats;
    stats["attempted"] = attempted;
    stats["accepted"] = accepted;
    stats["rejected_volume"] = rejected_volume;
    stats["rejected_quality"] = rejected_quality;
    stats["max_displacement"] = max_displacement;
    return py::make_tuple(output, stats);
}

py::tuple smooth_interior_guarded(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& tets_array,
    const py::array_t<long long, py::array::c_style | py::array::forcecast>& locked_vertices_array,
    const int n_iter,
    const double relax,
    const double eps)
{
    if (locked_vertices_array.ndim() != 1) {
        throw std::invalid_argument("smooth_interior_guarded expects locked vertices shaped (K,)");
    }
    if (n_iter < 0) {
        throw std::invalid_argument("n_iter must be non-negative");
    }
    if (!std::isfinite(relax) || !std::isfinite(eps) || eps < 0.0) {
        throw std::invalid_argument("smooth_interior_guarded received invalid relax/eps");
    }

    std::vector<Point> points = load_points(points_array, "smooth_interior_guarded");
    const std::vector<Tet> tets = load_tets(
        tets_array, static_cast<py::ssize_t>(points.size()), "smooth_interior_guarded");
    std::vector<uint8_t> locked(points.size(), 0);
    const auto locked_input = locked_vertices_array.unchecked<1>();
    for (py::ssize_t index = 0; index < locked_input.shape(0); ++index) {
        const long long vertex = locked_input(index);
        if (vertex < 0 || vertex >= static_cast<long long>(points.size())) {
            throw std::invalid_argument("smooth_interior_guarded received out-of-range locked vertex");
        }
        locked[static_cast<size_t>(vertex)] = 1;
    }

    std::vector<std::vector<long long>> neighbors(points.size());
    std::vector<std::vector<size_t>> incident(points.size());
    const auto add_edge = [&](const long long a, const long long b) {
        neighbors[static_cast<size_t>(a)].push_back(b);
        neighbors[static_cast<size_t>(b)].push_back(a);
    };
    for (size_t tet_index = 0; tet_index < tets.size(); ++tet_index) {
        const Tet& tet = tets[tet_index];
        for (const long long vertex : tet) {
            incident[static_cast<size_t>(vertex)].push_back(tet_index);
        }
        add_edge(tet[0], tet[1]);
        add_edge(tet[0], tet[2]);
        add_edge(tet[0], tet[3]);
        add_edge(tet[1], tet[2]);
        add_edge(tet[1], tet[3]);
        add_edge(tet[2], tet[3]);
    }
    for (auto& row : neighbors) {
        std::sort(row.begin(), row.end());
        row.erase(std::unique(row.begin(), row.end()), row.end());
    }

    long long attempted = 0;
    long long accepted = 0;
    long long rejected_volume = 0;
    long long rejected_quality = 0;
    double max_displacement = 0.0;
    int iterations_used = 0;

    for (int iter = 0; iter < n_iter; ++iter) {
        std::vector<long long> candidates;
        std::vector<Point> targets;
        candidates.reserve(points.size());
        targets.reserve(points.size());
        for (size_t vertex = 0; vertex < points.size(); ++vertex) {
            if (locked[vertex] || neighbors[vertex].empty()) {
                continue;
            }
            Point centroid{0.0, 0.0, 0.0};
            for (const long long neighbor : neighbors[vertex]) {
                const Point& p = points[static_cast<size_t>(neighbor)];
                centroid[0] += p[0];
                centroid[1] += p[1];
                centroid[2] += p[2];
            }
            const double inv_count = 1.0 / static_cast<double>(neighbors[vertex].size());
            centroid[0] *= inv_count;
            centroid[1] *= inv_count;
            centroid[2] *= inv_count;
            const Point& old = points[vertex];
            targets.push_back(Point{
                old[0] + relax * (centroid[0] - old[0]),
                old[1] + relax * (centroid[1] - old[1]),
                old[2] + relax * (centroid[2] - old[2])});
            candidates.push_back(static_cast<long long>(vertex));
        }

        long long accepted_this_iter = 0;
        for (size_t row = 0; row < candidates.size(); ++row) {
            const long long vertex = candidates[row];
            const auto& local_incident = incident[static_cast<size_t>(vertex)];
            if (local_incident.empty()) {
                continue;
            }
            ++attempted;
            std::vector<double> old_quality;
            std::vector<double> new_quality;
            std::vector<double> old_volumes;
            old_quality.reserve(local_incident.size());
            new_quality.reserve(local_incident.size());
            old_volumes.reserve(local_incident.size());
            for (const size_t tet_index : local_incident) {
                old_volumes.push_back(tet_volume6(points, tets[tet_index]));
                old_quality.push_back(tet_shape_quality(points, tets[tet_index]));
            }

            const Point old_point = points[static_cast<size_t>(vertex)];
            points[static_cast<size_t>(vertex)] = targets[row];
            bool valid = true;
            for (size_t local = 0; local < local_incident.size(); ++local) {
                const size_t tet_index = local_incident[local];
                const double new_volume = tet_volume6(points, tets[tet_index]);
                const double old_volume = old_volumes[local];
                if (std::abs(new_volume) <= 1e-20
                    || std::signbit(new_volume) != std::signbit(old_volume)) {
                    valid = false;
                    break;
                }
                new_quality.push_back(tet_shape_quality(points, tets[tet_index]));
            }
            if (!valid) {
                points[static_cast<size_t>(vertex)] = old_point;
                ++rejected_volume;
                continue;
            }
            if (compare_sorted_vectors(std::move(old_quality), std::move(new_quality), eps) < 0) {
                points[static_cast<size_t>(vertex)] = old_point;
                ++rejected_quality;
                continue;
            }

            const Point& target = targets[row];
            const double dx = target[0] - old_point[0];
            const double dy = target[1] - old_point[1];
            const double dz = target[2] - old_point[2];
            max_displacement = std::max(max_displacement, std::sqrt(dx * dx + dy * dy + dz * dz));
            ++accepted;
            ++accepted_this_iter;
        }
        ++iterations_used;
        if (accepted_this_iter == 0) {
            break;
        }
    }

    py::array_t<double> output({static_cast<py::ssize_t>(points.size()), py::ssize_t{3}});
    auto output_view = output.mutable_unchecked<2>();
    for (size_t row = 0; row < points.size(); ++row) {
        for (size_t coordinate = 0; coordinate < 3; ++coordinate) {
            output_view(static_cast<py::ssize_t>(row), static_cast<py::ssize_t>(coordinate))
                = points[row][coordinate];
        }
    }
    py::dict stats;
    stats["attempted"] = attempted;
    stats["accepted"] = accepted;
    stats["rejected_volume"] = rejected_volume;
    stats["rejected_quality"] = rejected_quality;
    stats["max_displacement"] = max_displacement;
    stats["n_iter"] = iterations_used;
    return py::make_tuple(output, stats);
}

}  // namespace

PYBIND11_MODULE(native_tet_qopt, m)
{
    m.doc() = "Native local-cavity infrastructure for guarded tet optimization.";
    m.def("local_cavity_quality_vectors", &local_cavity_quality_vectors,
          py::arg("points"), py::arg("tets"), py::arg("seed_tets"),
          py::arg("max_ring") = 1);
    m.def("compare_quality_vectors", &compare_quality_vectors,
          py::arg("old_quality"), py::arg("new_quality"), py::arg("eps") = 0.0);
    m.def("quality_vector_accepts", &quality_vector_accepts,
          py::arg("old_quality"), py::arg("new_quality"), py::arg("eps") = 0.0);
    m.def("apply_guarded_vertex_moves", &apply_guarded_vertex_moves,
          py::arg("points"), py::arg("tets"), py::arg("vertices"), py::arg("targets"),
          py::arg("eps") = 1e-15);
    m.def("apply_guarded_vertex_moves_csr", &apply_guarded_vertex_moves_csr,
          py::arg("points"), py::arg("tets"), py::arg("incident_offsets"),
          py::arg("incident_tets"), py::arg("vertices"), py::arg("targets"),
          py::arg("eps") = 1e-15);
    m.def("smooth_interior_guarded", &smooth_interior_guarded,
          py::arg("points"), py::arg("tets"), py::arg("locked_vertices"),
          py::arg("n_iter") = 2, py::arg("relax") = 0.5, py::arg("eps") = 1e-15);
}
