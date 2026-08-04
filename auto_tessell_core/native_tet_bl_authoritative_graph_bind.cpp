// C++23 authoritative candidate face graph and shared PolyMesh-like quality kernel.
//
// This is an in-memory, default-off verifier.  It does not publish or repair.
// The same oriented face table is used for candidate and serialized/disk
// readback parity tests.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <iomanip>
#include <sstream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;
using Tet = std::array<std::int64_t, 4>;
using FaceKey = std::array<std::int64_t, 3>;
using FaceCycle = std::array<std::int64_t, 3>;

namespace {

constexpr double kEpsilon = 1.0e-12;
constexpr double kPi = 3.141592653589793238462643383279502884;

Point sub(Point a, Point b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point add(Point a, Point b) { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
Point scale(Point a, double value) { return {a[0] * value, a[1] * value, a[2] * value}; }
Point cross(Point a, Point b) {
    return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]};
}
double dot(Point a, Point b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double norm(Point a) { return std::sqrt(dot(a, a)); }

double signed_volume6(const std::vector<Point>& points, const Tet& tet) {
    return dot(sub(points[static_cast<std::size_t>(tet[1])], points[static_cast<std::size_t>(tet[0])]),
               cross(sub(points[static_cast<std::size_t>(tet[2])], points[static_cast<std::size_t>(tet[0])]),
                     sub(points[static_cast<std::size_t>(tet[3])], points[static_cast<std::size_t>(tet[0])])));
}

std::vector<Point> load_points(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& array) {
    if (array.ndim() != 2 || array.shape(1) != 3) throw std::invalid_argument("points_must_be_Nx3");
    const auto input = array.unchecked<2>();
    std::vector<Point> points;
    points.reserve(static_cast<std::size_t>(input.shape(0)));
    for (py::ssize_t row = 0; row < input.shape(0); ++row) {
        Point point{};
        for (int axis = 0; axis < 3; ++axis) {
            point[static_cast<std::size_t>(axis)] = input(row, axis);
            if (!std::isfinite(point[static_cast<std::size_t>(axis)])) {
                throw std::invalid_argument("point_nonfinite");
            }
        }
        points.push_back(point);
    }
    return points;
}

std::vector<Tet> load_tets(
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& array,
    std::int64_t point_count) {
    if (array.ndim() != 2 || array.shape(1) != 4) throw std::invalid_argument("tets_must_be_Kx4");
    const auto input = array.unchecked<2>();
    std::vector<Tet> tets;
    tets.reserve(static_cast<std::size_t>(input.shape(0)));
    for (py::ssize_t row = 0; row < input.shape(0); ++row) {
        Tet tet{};
        for (int vertex = 0; vertex < 4; ++vertex) {
            tet[static_cast<std::size_t>(vertex)] = input(row, vertex);
            if (tet[static_cast<std::size_t>(vertex)] < 0 ||
                tet[static_cast<std::size_t>(vertex)] >= point_count) {
                throw std::invalid_argument("tet_vertex_out_of_range");
            }
        }
        if (std::set<std::int64_t>(tet.begin(), tet.end()).size() != 4) {
            throw std::invalid_argument("tet_degenerate");
        }
        tets.push_back(tet);
    }
    return tets;
}

FaceCycle outward_face_cycle(const std::vector<Point>& points, const Tet& tet, int omitted) {
    FaceCycle cycle{};
    int cursor = 0;
    for (int vertex = 0; vertex < 4; ++vertex) {
        if (vertex != omitted) cycle[static_cast<std::size_t>(cursor++)] = tet[static_cast<std::size_t>(vertex)];
    }
    const Point a = points[static_cast<std::size_t>(cycle[0])];
    const Point b = points[static_cast<std::size_t>(cycle[1])];
    const Point c = points[static_cast<std::size_t>(cycle[2])];
    const Point normal = cross(sub(b, a), sub(c, a));
    const Point to_opposite = sub(points[static_cast<std::size_t>(tet[static_cast<std::size_t>(omitted)])], a);
    if (dot(normal, to_opposite) > 0.0) std::swap(cycle[1], cycle[2]);
    return cycle;
}

FaceKey sorted_face(const FaceCycle& cycle) {
    FaceKey key = cycle;
    std::sort(key.begin(), key.end());
    return key;
}

bool same_cycle(FaceCycle first, FaceCycle second) {
    for (int rotation = 0; rotation < 3; ++rotation) {
        if (first[0] == second[static_cast<std::size_t>(rotation)] &&
            first[1] == second[static_cast<std::size_t>((rotation + 1) % 3)] &&
            first[2] == second[static_cast<std::size_t>((rotation + 2) % 3)]) return true;
    }
    return false;
}

bool opposite_cycle(FaceCycle first, FaceCycle second) {
    std::swap(first[1], first[2]);
    return same_cycle(first, second);
}

struct Face {
    FaceCycle cycle{};
    FaceKey key{};
    std::int64_t owner = -1;
    std::int64_t neighbour = -1;
};

struct Graph {
    std::vector<Face> faces;
    std::string refusal;
};

Graph build_graph(const std::vector<Point>& points, const std::vector<Tet>& tets) {
    Graph graph;
    std::set<std::array<std::int64_t, 4>> unique_tets;
    std::map<FaceKey, std::size_t> by_key;
    for (std::size_t cell = 0; cell < tets.size(); ++cell) {
        const auto& tet = tets[cell];
        const double signed_volume = signed_volume6(points, tet) / 6.0;
        if (!std::isfinite(signed_volume) || signed_volume <= 0.0) {
            graph.refusal = "tet_signed_volume_nonpositive";
            return graph;
        }
        auto sorted_tet = tet;
        std::sort(sorted_tet.begin(), sorted_tet.end());
        if (!unique_tets.insert(sorted_tet).second) {
            graph.refusal = "duplicate_tet";
            return graph;
        }
        for (int omitted = 0; omitted < 4; ++omitted) {
            const FaceCycle cycle = outward_face_cycle(points, tet, omitted);
            const FaceKey key = sorted_face(cycle);
            const auto existing = by_key.find(key);
            if (existing == by_key.end()) {
                Face face;
                face.cycle = cycle;
                face.key = key;
                face.owner = static_cast<std::int64_t>(cell);
                by_key.emplace(key, graph.faces.size());
                graph.faces.push_back(face);
                continue;
            }
            Face& face = graph.faces[existing->second];
            if (face.neighbour >= 0) {
                graph.refusal = "non_manifold_face";
                return graph;
            }
            if (!opposite_cycle(face.cycle, cycle)) {
                graph.refusal = "face_orientation_mismatch";
                return graph;
            }
            face.neighbour = static_cast<std::int64_t>(cell);
        }
    }
    return graph;
}

py::list face_list(const Graph& graph) {
    py::list result;
    for (std::size_t index = 0; index < graph.faces.size(); ++index) {
        const auto& face = graph.faces[index];
        py::dict row;
        row["writer_face_id"] = "face-" + std::to_string(index);
        row["vertex_cycle"] = py::make_tuple(face.cycle[0], face.cycle[1], face.cycle[2]);
        row["owner"] = face.owner;
        row["neighbour"] = face.neighbour;
        row["role"] = face.neighbour < 0 ? "boundary" : "internal";
        result.append(row);
    }
    return result;
}

void append_u64(std::vector<std::uint8_t>& bytes, std::uint64_t value) {
    for (int shift = 0; shift < 8; ++shift) bytes.push_back(static_cast<std::uint8_t>((value >> (8 * shift)) & 0xffU));
}

void append_i64(std::vector<std::uint8_t>& bytes, std::int64_t value) {
    append_u64(bytes, static_cast<std::uint64_t>(value));
}

void append_text(std::vector<std::uint8_t>& bytes, const std::string& value) {
    append_u64(bytes, value.size());
    bytes.insert(bytes.end(), value.begin(), value.end());
}

std::string graph_sha256(const Graph& graph) {
    std::vector<std::uint8_t> bytes;
    append_text(bytes, "autotessell-native-tet-authoritative-graph/v1");
    append_u64(bytes, graph.faces.size());
    for (std::size_t index = 0; index < graph.faces.size(); ++index) {
        const auto& face = graph.faces[index];
        append_text(bytes, "face-" + std::to_string(index));
        for (const auto value : face.cycle) append_i64(bytes, value);
        append_i64(bytes, face.owner);
        append_i64(bytes, face.neighbour);
        append_text(bytes, face.neighbour < 0 ? "boundary" : "internal");
    }
    return brep_evidence::sha256_hex(bytes);
}

struct Quality {
    double max_non_orthogonality = 0.0;
    double p95_non_orthogonality = 0.0;
    double max_skewness = 0.0;
    double p95_skewness = 0.0;
    double max_aspect_ratio = 0.0;
};

Point cell_center(const std::vector<Point>& points, const Tet& tet) {
    return scale(add(add(points[static_cast<std::size_t>(tet[0])], points[static_cast<std::size_t>(tet[1])]),
                      add(points[static_cast<std::size_t>(tet[2])], points[static_cast<std::size_t>(tet[3])])), 0.25);
}

Point face_center(const std::vector<Point>& points, const FaceCycle& cycle) {
    return scale(add(add(points[static_cast<std::size_t>(cycle[0])], points[static_cast<std::size_t>(cycle[1])]),
                      points[static_cast<std::size_t>(cycle[2])]), 1.0 / 3.0);
}

double percentile(std::vector<double> values) {
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    const auto index = std::min(values.size() - 1,
        static_cast<std::size_t>(std::ceil(0.95 * static_cast<double>(values.size()))) - 1);
    return values[index];
}

Quality measure_quality(const std::vector<Point>& points, const std::vector<Tet>& tets, const Graph& graph) {
    Quality quality;
    std::vector<Point> centers;
    centers.reserve(tets.size());
    for (const auto& tet : tets) centers.push_back(cell_center(points, tet));
    std::vector<double> non_orthogonality;
    std::vector<double> skewness;
    for (const auto& face : graph.faces) {
        const Point a = points[static_cast<std::size_t>(face.cycle[0])];
        const Point b = points[static_cast<std::size_t>(face.cycle[1])];
        const Point c = points[static_cast<std::size_t>(face.cycle[2])];
        const Point area_vector = cross(sub(b, a), sub(c, a));
        const double area_twice = norm(area_vector);
        const Point normal = scale(area_vector, 1.0 / std::max(area_twice, kEpsilon));
        const Point owner_center = centers[static_cast<std::size_t>(face.owner)];
        const Point center_line = face.neighbour >= 0
            ? sub(centers[static_cast<std::size_t>(face.neighbour)], owner_center)
            : sub(face_center(points, face.cycle), owner_center);
        const double line_length = norm(center_line);
        const double alignment = dot(normal, scale(center_line, 1.0 / std::max(line_length, kEpsilon)));
        non_orthogonality.push_back(std::acos(std::clamp(alignment, -1.0, 1.0)) * 180.0 / kPi);

        const Point fc = face_center(points, face.cycle);
        const double projection_distance = face.neighbour >= 0
            ? std::abs(dot(sub(fc, owner_center), center_line) / std::max(dot(center_line, center_line), kEpsilon))
            : dot(sub(fc, owner_center), normal);
        const Point projection = add(owner_center, scale(center_line, projection_distance));
        skewness.push_back(norm(sub(fc, projection)) / std::max(std::sqrt(area_twice), kEpsilon));
    }
    std::vector<double> aspect;
    aspect.reserve(tets.size());
    for (const auto& tet : tets) {
        double minimum_edge = std::numeric_limits<double>::infinity();
        double maximum_edge = 0.0;
        for (int first = 0; first < 4; ++first) for (int second = first + 1; second < 4; ++second) {
            const double edge = norm(sub(points[static_cast<std::size_t>(tet[first])],
                                          points[static_cast<std::size_t>(tet[second])]));
            minimum_edge = std::min(minimum_edge, edge);
            maximum_edge = std::max(maximum_edge, edge);
        }
        aspect.push_back(maximum_edge / std::max(minimum_edge, kEpsilon));
    }
    if (!aspect.empty()) quality.max_aspect_ratio = *std::max_element(aspect.begin(), aspect.end());
    if (!non_orthogonality.empty()) {
        quality.max_non_orthogonality = *std::max_element(non_orthogonality.begin(), non_orthogonality.end());
        quality.p95_non_orthogonality = percentile(non_orthogonality);
        quality.max_skewness = *std::max_element(skewness.begin(), skewness.end());
        quality.p95_skewness = percentile(skewness);
    }
    return quality;
}

py::dict quality_dict(const Quality& quality) {
    py::dict result;
    result["max_non_orthogonality"] = quality.max_non_orthogonality;
    result["p95_non_orthogonality"] = quality.p95_non_orthogonality;
    result["max_skewness"] = quality.max_skewness;
    result["p95_skewness"] = quality.p95_skewness;
    result["max_aspect_ratio"] = quality.max_aspect_ratio;
    return result;
}

py::dict refused(const std::string& reason) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "candidate_refused";
    result["refusal_reason"] = reason;
    result["candidate_discarded"] = true;
    result["rollback_required"] = true;
    result["runtime_route"] = "default_off";
    result["publication_eligible"] = false;
    return result;
}

py::dict build(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tets_array) {
    const auto points = load_points(points_array);
    const auto tets = load_tets(tets_array, static_cast<std::int64_t>(points.size()));
    const Graph graph = build_graph(points, tets);
    if (!graph.refusal.empty()) return refused(graph.refusal);
    py::dict result;
    result["accepted"] = true;
    result["status"] = tets.empty() ? "empty_candidate_graph" : "authoritative_candidate_graph";
    result["candidate_discarded"] = false;
    result["rollback_required"] = false;
    result["runtime_route"] = "default_off";
    result["publication_eligible"] = false;
    result["work_performed"] = !tets.empty();
    result["faces"] = face_list(graph);
    result["face_count"] = graph.faces.size();
    result["graph_sha256"] = graph_sha256(graph);
    if (!tets.empty()) result["quality"] = quality_dict(measure_quality(points, tets, graph));
    return result;
}

py::dict quality(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tets_array) {
    const auto points = load_points(points_array);
    const auto tets = load_tets(tets_array, static_cast<std::int64_t>(points.size()));
    const Graph graph = build_graph(points, tets);
    if (!graph.refusal.empty()) return refused(graph.refusal);
    py::dict result;
    result["accepted"] = true;
    result["status"] = "shared_candidate_disk_quality";
    result["quality"] = quality_dict(measure_quality(points, tets, graph));
    result["graph_sha256"] = graph_sha256(graph);
    result["face_count"] = graph.faces.size();
    return result;
}

std::string points_text(const std::vector<Point>& points) {
    std::ostringstream stream;
    stream << std::setprecision(17);
    for (std::size_t index = 0; index < points.size(); ++index) {
        stream << index << ':' << points[index][0] << ',' << points[index][1] << ','
               << points[index][2] << '\n';
    }
    return stream.str();
}

py::dict serialize_internal(const std::vector<Point>& points, const std::vector<Tet>& tets) {
    const Graph graph = build_graph(points, tets);
    if (!graph.refusal.empty()) return refused(graph.refusal);
    py::dict result;
    result["accepted"] = true;
    result["status"] = tets.empty() ? "empty_candidate_serialization" : "candidate_serialized";
    result["candidate_discarded"] = false;
    result["rollback_required"] = false;
    result["runtime_route"] = "default_off";
    result["publication_eligible"] = false;
    result["work_performed"] = !tets.empty();
    result["graph_sha256"] = graph_sha256(graph);
    result["quality"] = quality_dict(measure_quality(points, tets, graph));

    if (tets.empty()) {
        result["points"] = "";
        result["faces"] = "";
        result["owner"] = "";
        result["neighbour"] = "";
        result["boundary"] = "";
        result["disk_face_ids"] = py::dict();
        result["artifact_tree_sha256"] = graph_sha256(graph);
        result["serialization_sha256"] = graph_sha256(graph);
        return result;
    }

    std::vector<std::size_t> order;
    order.reserve(graph.faces.size());
    for (std::size_t index = 0; index < graph.faces.size(); ++index) {
        if (graph.faces[index].neighbour >= 0) order.push_back(index);
    }
    const std::size_t internal_count = order.size();
    for (std::size_t index = 0; index < graph.faces.size(); ++index) {
        if (graph.faces[index].neighbour < 0) order.push_back(index);
    }

    std::ostringstream faces;
    std::ostringstream owner;
    std::ostringstream neighbour;
    std::ostringstream boundary;
    py::dict disk_face_ids;
    for (std::size_t disk_id = 0; disk_id < order.size(); ++disk_id) {
        const auto& face = graph.faces[order[disk_id]];
        faces << "3(" << face.cycle[0] << ' ' << face.cycle[1] << ' ' << face.cycle[2] << ")\n";
        owner << face.owner << '\n';
        if (face.neighbour >= 0) neighbour << face.neighbour << '\n';
        disk_face_ids[py::str("face-" + std::to_string(order[disk_id]))] =
            static_cast<std::int64_t>(disk_id);
    }
    boundary << "defaultPatch " << (order.size() - internal_count) << ' ' << internal_count << '\n';

    const std::string points_bytes = points_text(points);
    const std::string faces_bytes = faces.str();
    const std::string owner_bytes = owner.str();
    const std::string neighbour_bytes = neighbour.str();
    const std::string boundary_bytes = boundary.str();
    std::vector<std::uint8_t> artifact_bytes;
    for (const auto& entry : {
        std::pair<std::string, std::string>{"points", points_bytes},
        std::pair<std::string, std::string>{"faces", faces_bytes},
        std::pair<std::string, std::string>{"owner", owner_bytes},
        std::pair<std::string, std::string>{"neighbour", neighbour_bytes},
        std::pair<std::string, std::string>{"boundary", boundary_bytes}}) {
        append_text(artifact_bytes, entry.first);
        append_text(artifact_bytes, entry.second);
    }
    const std::string artifact_digest = brep_evidence::sha256_hex(artifact_bytes);
    result["points"] = points_bytes;
    result["faces"] = faces_bytes;
    result["owner"] = owner_bytes;
    result["neighbour"] = neighbour_bytes;
    result["boundary"] = boundary_bytes;
    result["disk_face_ids"] = disk_face_ids;
    result["artifact_tree_sha256"] = artifact_digest;
    result["serialization_sha256"] = artifact_digest;
    return result;
}

py::dict serialize(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tets_array) {
    const auto points = load_points(points_array);
    const auto tets = load_tets(tets_array, static_cast<std::int64_t>(points.size()));
    return serialize_internal(points, tets);
}

py::dict readback(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tets_array,
    const py::dict& serialized) {
    const auto points = load_points(points_array);
    const auto tets = load_tets(tets_array, static_cast<std::int64_t>(points.size()));
    const py::dict expected = serialize_internal(points, tets);
    if (!expected["accepted"].cast<bool>()) return expected;
    for (const char* key : {
        "points", "faces", "owner", "neighbour", "boundary",
        "graph_sha256", "artifact_tree_sha256", "serialization_sha256"}) {
        if (!serialized.contains(key) || !expected.contains(key)) {
            return refused("readback_field_missing");
        }
        try {
            if (serialized[key].cast<std::string>() != expected[key].cast<std::string>()) {
                return refused("readback_canonical_bytes_mismatch");
            }
        } catch (const py::cast_error&) {
            return refused("readback_field_type_mismatch");
        }
    }
    py::dict result = expected;
    result["status"] = "candidate_disk_readback_verified";
    result["readback_verified"] = true;
    result["rollback_required"] = false;
    return result;
}
py::dict artifact(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tets_array) {
    const auto points = load_points(points_array);
    const auto tets = load_tets(tets_array, static_cast<std::int64_t>(points.size()));
    py::dict result = serialize_internal(points, tets);
    if (!result["accepted"].cast<bool>()) return result;
    const Graph graph = build_graph(points, tets);
    result["status"] = tets.empty()
        ? "bl0_identity_artifact"
        : "authoritative_candidate_artifact";
    result["candidate_artifact"] = true;
    result["faces_table"] = face_list(graph);
    result["face_count"] = graph.faces.size();
    result["collision_surface_source"] = tets.empty() ? "none" : "writer_owned_face_table";
    result["collision_checked"] = false;
    result["publication_eligible"] = false;
    return result;
}

}  // namespace

PYBIND11_MODULE(native_tet_bl_authoritative_graph, module) {
    module.doc() = "Default-off C++23 authoritative Tet face graph and shared quality kernel.";
    module.def("build", &build, py::arg("points"), py::arg("tets"));
    module.def("quality", &quality, py::arg("points"), py::arg("tets"));
    module.def("serialize", &serialize, py::arg("points"), py::arg("tets"));
    module.def("readback", &readback, py::arg("points"), py::arg("tets"), py::arg("serialized"));
    module.def("artifact", &artifact, py::arg("points"), py::arg("tets"));
}

