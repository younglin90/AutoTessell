// Default-off C++23 sectorized wall-edge front with deterministic BVH visibility.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <functional>
#include <limits>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;

namespace {

Point sub(const Point& a, const Point& b) noexcept { return {a[0]-b[0], a[1]-b[1], a[2]-b[2]}; }
Point add(const Point& a, const Point& b) noexcept { return {a[0]+b[0], a[1]+b[1], a[2]+b[2]}; }
Point mul(const Point& a, double s) noexcept { return {a[0]*s, a[1]*s, a[2]*s}; }
Point cross(const Point& a, const Point& b) noexcept {
    return {a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]};
}
double dot(const Point& a, const Point& b) noexcept { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
double norm(const Point& a) noexcept { return std::sqrt(dot(a, a)); }

Point unit(const Point& value, const char* name)
{
    const double length = norm(value);
    if (!(length > 1.0e-14) || !std::isfinite(length)) {
        throw std::invalid_argument(std::string(name) + " must be finite and nonzero");
    }
    return mul(value, 1.0 / length);
}

struct Box {
    Point lo{std::numeric_limits<double>::infinity(), std::numeric_limits<double>::infinity(), std::numeric_limits<double>::infinity()};
    Point hi{-std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()};
};

void extend(Box& box, const Point& p) noexcept
{
    for (int axis = 0; axis < 3; ++axis) {
        box.lo[axis] = std::min(box.lo[axis], p[axis]);
        box.hi[axis] = std::max(box.hi[axis], p[axis]);
    }
}

bool overlap(const Box& a, const Box& b) noexcept
{
    return a.lo[0] <= b.hi[0] && a.hi[0] >= b.lo[0]
        && a.lo[1] <= b.hi[1] && a.hi[1] >= b.lo[1]
        && a.lo[2] <= b.hi[2] && a.hi[2] >= b.lo[2];
}

struct Triangle {
    std::int64_t id;
    std::array<std::int64_t, 3> ids;
    Point a;
    Point b;
    Point c;
    Point centroid;
    Box box;
};

struct BvhNode {
    Box box;
    std::int64_t triangle{-1};
    int left{-1};
    int right{-1};
};

class FlatBvh {
public:
    explicit FlatBvh(std::vector<Triangle> triangles) : triangles_(std::move(triangles))
    {
        std::sort(triangles_.begin(), triangles_.end(), [](const Triangle& a, const Triangle& b) {
            return std::tuple{a.centroid[0], a.centroid[1], a.centroid[2], a.id}
                < std::tuple{b.centroid[0], b.centroid[1], b.centroid[2], b.id};
        });
        if (!triangles_.empty()) {
            build(0, static_cast<int>(triangles_.size()));
        }
    }

    template<class Callback>
    void query(const Box& box, Callback&& callback) const
    {
        if (!nodes_.empty()) {
            query_node(0, box, callback);
        }
    }

private:
    int build(int begin, int end)
    {
        const int node_index = static_cast<int>(nodes_.size());
        nodes_.push_back({});
        Box box;
        for (int i = begin; i < end; ++i) {
            extend(box, triangles_[static_cast<size_t>(i)].a);
            extend(box, triangles_[static_cast<size_t>(i)].b);
            extend(box, triangles_[static_cast<size_t>(i)].c);
        }
        nodes_[static_cast<size_t>(node_index)].box = box;
        if (end - begin == 1) {
            nodes_[static_cast<size_t>(node_index)].triangle = triangles_[static_cast<size_t>(begin)].id;
            return node_index;
        }
        const int middle = begin + (end - begin) / 2;
        const int left = build(begin, middle);
        const int right = build(middle, end);
        nodes_[static_cast<size_t>(node_index)].left = left;
        nodes_[static_cast<size_t>(node_index)].right = right;
        return node_index;
    }

    template<class Callback>
    void query_node(int index, const Box& box, Callback& callback) const
    {
        const BvhNode& node = nodes_[static_cast<size_t>(index)];
        if (!overlap(node.box, box)) {
            return;
        }
        if (node.triangle >= 0) {
            callback(node.triangle);
            return;
        }
        query_node(node.left, box, callback);
        query_node(node.right, box, callback);
    }

    std::vector<Triangle> triangles_;
    std::vector<BvhNode> nodes_;
};

bool contains_edge(const Triangle& triangle, std::int64_t first, std::int64_t second) noexcept
{
    bool has_first = false;
    bool has_second = false;
    for (const auto id : triangle.ids) {
        has_first = has_first || id == first;
        has_second = has_second || id == second;
    }
    return has_first && has_second;
}

bool segment_triangle_hit(const Point& origin, const Point& endpoint, const Triangle& triangle) noexcept
{
    constexpr double epsilon = 1.0e-12;
    const Point direction = sub(endpoint, origin);
    const Point edge1 = sub(triangle.b, triangle.a);
    const Point edge2 = sub(triangle.c, triangle.a);
    const Point pvec = cross(direction, edge2);
    const double determinant = dot(edge1, pvec);
    if (std::abs(determinant) <= epsilon) {
        return false;
    }
    const double inverse = 1.0 / determinant;
    const Point tvec = sub(origin, triangle.a);
    const double u = dot(tvec, pvec) * inverse;
    if (u < -epsilon || u > 1.0 + epsilon) return false;
    const Point qvec = cross(tvec, edge1);
    const double v = dot(direction, qvec) * inverse;
    if (v < -epsilon || u + v > 1.0 + epsilon) return false;
    const double distance = dot(edge2, qvec) * inverse;
    return distance >= -epsilon && distance <= 1.0 + epsilon;
}

Box segment_box(const Point& a, const Point& b, double epsilon) noexcept
{
    Box box;
    extend(box, a);
    extend(box, b);
    for (int axis = 0; axis < 3; ++axis) {
        box.lo[axis] -= epsilon;
        box.hi[axis] += epsilon;
    }
    return box;
}

py::dict rollback(const std::string& reason, std::int64_t requested)
{
    py::dict result;
    result["accepted"] = false;
    result["status"] = "refused_rollback";
    result["reason"] = reason;
    result["requested_layers"] = requested;
    result["actual_layers"] = 0;
    result["generated_vertices"] = py::list();
    result["generated_faces"] = py::list();
    result["provenance"] = py::list();
    result["source_immutable"] = true;
    return result;
}

py::dict plan_sector_bvh(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edges,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals,
    const py::list& patches,
    const py::list& features,
    const py::list& groups,
    const py::list& sides,
    std::int64_t requested,
    double first_height,
    double growth,
    const py::object& source_triangles = py::none(),
    double absolute_epsilon = 1.0e-12,
    double relative_epsilon = 1.0e-10)
{
    if (points.ndim() != 2 || points.shape(1) != 3 || edges.ndim() != 2 || edges.shape(1) != 5
        || normals.ndim() != 2 || normals.shape(1) != 3) {
        throw std::invalid_argument("points Nx3, edges Ex5, and normals Fx3 are required");
    }
    if (requested == 0) {
        py::dict result = rollback("disabled_identity", 0);
        result["accepted"] = true;
        result["status"] = "disabled_identity";
        result["actual_layers"] = 0;
        return result;
    }
    if (requested < 0) return rollback("negative_layer_count", requested);
    if (!std::isfinite(first_height) || first_height <= 0.0) return rollback("invalid_first_height", requested);
    if (!std::isfinite(growth) || growth < 1.0) return rollback("invalid_growth_ratio", requested);
    if (edges.shape(0) == 0) return rollback("empty_wall_edge_selection", requested);
    if (source_triangles.is_none()) return rollback("missing_conservative_visibility_inputs", requested);
    if (patches.size() != static_cast<size_t>(normals.shape(0))
        || features.size() != static_cast<size_t>(normals.shape(0))
        || groups.size() != static_cast<size_t>(normals.shape(0))
        || sides.size() != static_cast<size_t>(edges.shape(0))) {
        throw std::invalid_argument("metadata lengths do not match sectors");
    }

    const auto triangle_array = source_triangles.cast<py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>>();
    if (triangle_array.ndim() != 2 || triangle_array.shape(1) != 3) throw std::invalid_argument("source_triangles must be Tx3");
    const auto* point_data = points.data();
    const auto* edge_data = edges.data();
    const auto* normal_data = normals.data();
    const auto* triangle_data = triangle_array.data();
    const auto point_at = [&](std::int64_t id) -> Point {
        if (id < 0 || id >= points.shape(0)) throw std::invalid_argument("point index out of range");
        const size_t offset = static_cast<size_t>(id) * 3U;
        return {point_data[offset], point_data[offset+1U], point_data[offset+2U]};
    };

    std::vector<Triangle> triangles;
    triangles.reserve(static_cast<size_t>(triangle_array.shape(0)));
    Box all_box;
    for (py::ssize_t row = 0; row < triangle_array.shape(0); ++row) {
        const size_t offset = static_cast<size_t>(row) * 3U;
        const std::array<std::int64_t, 3> ids{triangle_data[offset], triangle_data[offset+1U], triangle_data[offset+2U]};
        const Point a = point_at(ids[0]);
        const Point b = point_at(ids[1]);
        const Point c = point_at(ids[2]);
        Triangle triangle{row, ids, a, b, c, mul(add(add(a, b), c), 1.0/3.0), {}};
        extend(triangle.box, a); extend(triangle.box, b); extend(triangle.box, c);
        extend(all_box, a); extend(all_box, b); extend(all_box, c);
        triangles.push_back(triangle);
    }
    const double diagonal = norm(sub(all_box.hi, all_box.lo));
    const double epsilon = std::max(absolute_epsilon, relative_epsilon * diagonal);
    FlatBvh bvh(std::move(triangles));

    struct Sector { std::int64_t edge; std::int64_t a; std::int64_t b; std::int64_t face; std::string side; };
    std::vector<Sector> sectors;
    sectors.reserve(static_cast<size_t>(edges.shape(0)));
    for (py::ssize_t row = 0; row < edges.shape(0); ++row) {
        const size_t offset = static_cast<size_t>(row) * 5U;
        sectors.push_back({edge_data[offset], edge_data[offset+1U], edge_data[offset+2U], edge_data[offset+3U], py::cast<std::string>(sides[row])});
    }
    std::sort(sectors.begin(), sectors.end(), [](const Sector& a, const Sector& b) {
        return std::tuple{a.edge, a.face, a.side, a.a, a.b} < std::tuple{b.edge, b.face, b.side, b.a, b.b};
    });
    for (size_t i = 1U; i < sectors.size(); ++i) {
        if (std::tuple{sectors[i-1U].edge, sectors[i-1U].face, sectors[i-1U].side}
            == std::tuple{sectors[i].edge, sectors[i].face, sectors[i].side}) {
            return rollback("duplicate_sector_key", requested);
        }
    }

    py::list vertices;
    py::list faces;
    py::list lineage;
    std::int64_t generated_id = 0;
    for (const Sector& sector : sectors) {
        if (sector.face < 0 || sector.face >= normals.shape(0)) return rollback("source_face_out_of_range", requested);
        const Point first = point_at(sector.a);
        const Point second = point_at(sector.b);
        const Point tangent = unit(sub(second, first), "edge tangent");
        const size_t no = static_cast<size_t>(sector.face) * 3U;
        const Point normal = unit(Point{normal_data[no], normal_data[no+1U], normal_data[no+2U]}, "sector normal");
        const Point co_normal = unit(cross(normal, tangent), "sector co-normal");
        const std::string patch = py::cast<std::string>(patches[sector.face]);
        const std::string feature = py::cast<std::string>(features[sector.face]);
        const std::string group = py::cast<std::string>(groups[sector.face]);

        for (std::int64_t layer = 1; layer <= requested; ++layer) {
            const double step = first_height * std::pow(growth, static_cast<double>(layer - 1));
            const Point offset_a = add(first, mul(co_normal, step));
            const Point offset_b = add(second, mul(co_normal, step));
            const Point area_a = cross(sub(second, first), sub(offset_b, first));
            const Point area_b = cross(sub(offset_b, first), sub(offset_a, first));
            if (dot(area_a, normal) <= absolute_epsilon || dot(area_b, normal) <= absolute_epsilon) return rollback("non_positive_oriented_strip", requested);

            std::int64_t witness = -1;
            const Box query = segment_box(first, offset_a, epsilon);
            bvh.query(query, [&](std::int64_t triangle_id) {
                if (witness >= 0) return;
                const auto tri = triangle_array.unchecked<2>(triangle_id, 0);
                const std::array<std::int64_t, 3> ids{tri(0), tri(1), tri(2)};
                if (contains_edge(Triangle{triangle_id, ids, {}, {}, {}, {}, {}}, sector.a, sector.b)) return;
                const Point ta = point_at(ids[0]); const Point tb = point_at(ids[1]); const Point tc = point_at(ids[2]);
                Triangle candidate{triangle_id, ids, ta, tb, tc, {}, {}};
                Box tri_box; extend(tri_box, ta); extend(tri_box, tb); extend(tri_box, tc);
                if (!overlap(query, tri_box)) return;
                if (segment_triangle_hit(first, offset_a, candidate)
                    || segment_triangle_hit(second, offset_b, candidate)
                    || segment_triangle_hit(offset_a, offset_b, candidate)) witness = triangle_id;
                else {
                    const Point tri_normal = cross(sub(tb, ta), sub(tc, ta));
                    if (norm(tri_normal) > 1.0e-14 && std::abs(dot(unit(tri_normal, "triangle normal"), co_normal)) < 1.0e-10) witness = triangle_id;
                }
            });
            if (witness >= 0) return rollback("visibility_witness_triangle_" + std::to_string(witness), requested);

            const std::int64_t ga = generated_id++;
            const std::int64_t gb = generated_id++;
            py::dict va; va["id"] = ga; va["x"] = offset_a[0]; va["y"] = offset_a[1]; va["z"] = offset_a[2];
            py::dict vb; vb["id"] = gb; vb["x"] = offset_b[0]; vb["y"] = offset_b[1]; vb["z"] = offset_b[2];
            vertices.append(va); vertices.append(vb);
            py::dict f0; f0["source_a"] = sector.a; f0["source_b"] = sector.b; f0["generated_b"] = gb; f0["generated_a"] = ga; f0["layer"] = layer;
            py::dict f1 = f0; f1["source_b"] = gb; f1["generated_b"] = ga;
            faces.append(f0); faces.append(f1);
            py::dict record;
            record["source_wall_edge"] = sector.edge; record["source_face"] = sector.face; record["patch"] = patch;
            record["feature"] = feature; record["physical_group"] = group; record["side"] = sector.side;
            record["layer"] = layer; record["normal"] = py::make_tuple(normal[0], normal[1], normal[2]);
            record["co_normal"] = py::make_tuple(co_normal[0], co_normal[1], co_normal[2]);
            record["visibility_witness"] = -1; record["candidate_ordinal"] = static_cast<std::int64_t>(lineage.size());
            lineage.append(record);
        }
    }
    py::dict result;
    result["accepted"] = true; result["status"] = "candidate_plan_ready"; result["reason"] = "accepted_sector_bvh_plan";
    result["requested_layers"] = requested; result["actual_layers"] = requested;
    result["generated_vertices"] = vertices; result["generated_faces"] = faces; result["provenance"] = lineage;
    result["bvh_triangle_count"] = static_cast<std::int64_t>(triangle_array.shape(0));
    result["source_immutable"] = true; result["count_is_report_only"] = true;
    return result;
}

}  // namespace

PYBIND11_MODULE(native_surface_bl_front_sector, module)
{
    module.doc() = "Default-off sectorized C++23 surface wall-edge BL planner";
    module.def("plan_surface_wall_edge_sectors", &plan_sector_bvh,
        py::arg("points"), py::arg("edges"), py::arg("normals"), py::arg("patches"),
        py::arg("features"), py::arg("physical_groups"), py::arg("sides"),
        py::arg("requested_layers"), py::arg("first_height"), py::arg("growth"),
        py::arg("source_triangles") = py::none(), py::arg("absolute_epsilon") = 1.0e-12,
        py::arg("relative_epsilon") = 1.0e-10);
}
