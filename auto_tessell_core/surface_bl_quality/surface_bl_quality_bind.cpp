// C++23 native, report-only surface quality evidence kernel.
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <limits>
#include <stdexcept>
#include <set>
#include <vector>
namespace py=pybind11; using V=std::array<double,3>; using I=std::array<std::int64_t,3>;
V sub(V a,V b)noexcept{return{a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
V addv(V a,V b)noexcept{return{a[0]+b[0],a[1]+b[1],a[2]+b[2]};}
V scale(V a,double s)noexcept{return{a[0]*s,a[1]*s,a[2]*s};}
V cross(V a,V b)noexcept{return{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
double dot(V a,V b)noexcept{return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];} double len(V a)noexcept{return std::sqrt(dot(a,a));}
bool finite(V a)noexcept{return std::isfinite(a[0])&&std::isfinite(a[1])&&std::isfinite(a[2]);}
V unit(V a){const double n=len(a);if(!(n>1e-14)||!std::isfinite(n))throw std::invalid_argument("normal must be finite and non-zero");return{a[0]/n,a[1]/n,a[2]/n};}
struct Box{V lo{INFINITY,INFINITY,INFINITY};V hi{-INFINITY,-INFINITY,-INFINITY};};
void add(Box&b,V p)noexcept{for(int i=0;i<3;++i){b.lo[i]=std::min(b.lo[i],p[i]);b.hi[i]=std::max(b.hi[i],p[i]);}}
bool overlap(const Box&a,const Box&b,double e)noexcept{for(int i=0;i<3;++i)if(a.hi[i]<=b.lo[i]+e||b.hi[i]<=a.lo[i]+e)return false;return true;}
double pct(std::vector<double>v,double p){if(v.empty())return 0.;std::sort(v.begin(),v.end());double x=(v.size()-1)*p;auto l=(size_t)std::floor(x),h=(size_t)std::ceil(x);if(l==h)return v[l];return v[l]*(1-(x-l))+v[h]*(x-l);}
py::dict distribution(const std::vector<double>&v,const char*d){py::dict o;o["status"]=v.empty()?"not_measured":"measured";o["count"]=(std::int64_t)v.size();o["p95"]=v.empty()?py::none():py::cast(pct(v,.95));o["p99"]=v.empty()?py::none():py::cast(pct(v,.99));o["max"]=v.empty()?py::none():py::cast(*std::max_element(v.begin(),v.end()));o["definition"]=d;return o;}
bool lineage(const py::handle&r){if(!py::isinstance<py::dict>(r))return false;py::dict d=py::reinterpret_borrow<py::dict>(r);for(const char*k:{"source_wall_edge","source_face","side","layer","patch","feature","physical_group","provenance"})if(!d.contains(k)||d[k].is_none())return false;return true;}
py::dict evaluate(const py::array_t<double,py::array::c_style|py::array::forcecast>&points,const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>&triangles,const py::array_t<double,py::array::c_style|py::array::forcecast>&normals,const py::list&provenance,double eps=1e-12){
 if(points.ndim()!=2||points.shape(1)!=3||triangles.ndim()!=2||triangles.shape(1)!=3||normals.ndim()!=2||normals.shape(1)!=3)throw std::invalid_argument("points Nx3, triangles Tx3, normals Tx3 required");
 if(normals.shape(0)!=triangles.shape(0)||provenance.size()!=(size_t)triangles.shape(0))throw std::invalid_argument("normals and provenance must match triangles");
 const double*pd=points.data();const auto*td=triangles.data();const double*nd=normals.data();auto point=[&](std::int64_t id){if(id<0||id>=points.shape(0))throw std::invalid_argument("triangle point index out of range");size_t o=(size_t)id*3;return V{pd[o],pd[o+1],pd[o+2]};};
 std::int64_t invalid=0,inverted=0,duplicate=0,nonmanifold=0,selfx=0;std::set<I>seen;std::map<std::pair<std::int64_t,std::int64_t>,std::vector<std::int64_t>>edges;std::vector<Box>boxes;std::vector<std::set<std::int64_t>>verts;std::vector<double>sv,nv,av;py::list entities;bool provok=true;
 for(py::ssize_t i=0;i<triangles.shape(0);++i){size_t o=(size_t)i*3;I ids{td[o],td[o+1],td[o+2]},key=ids;std::sort(key.begin(),key.end());if(!seen.insert(key).second)duplicate++;if(ids[0]==ids[1]||ids[0]==ids[2]||ids[1]==ids[2])invalid++;for(int e=0;e<3;++e){auto a=ids[e],b=ids[(e+1)%3];if(a>b)std::swap(a,b);edges[{a,b}].push_back(i);}V a,b,c;try{a=point(ids[0]);b=point(ids[1]);c=point(ids[2]);}catch(...){invalid++;continue;}Box box;add(box,a);add(box,b);add(box,c);boxes.push_back(box);verts.push_back({ids[0],ids[1],ids[2]});if(!finite(a)||!finite(b)||!finite(c)){invalid++;continue;}V n;try{n=unit(V{nd[o],nd[o+1],nd[o+2]});}catch(...){invalid++;continue;}V cr=cross(sub(b,a),sub(c,a));double oriented=.5*dot(cr,n);if(!std::isfinite(oriented)||oriented<=eps){if(oriented<-eps)inverted++;else invalid++;}double ab=len(sub(b,a)),bc=len(sub(c,b)),ca=len(sub(a,c));if(!(ab>eps&&bc>eps&&ca>eps)){invalid++;continue;}double longest=std::max({ab,bc,ca}),shortest=std::min({ab,bc,ca}),aspect=longest/shortest,skew=(aspect-1)/aspect;auto angle=[](V u,V v){double q=std::clamp(dot(u,v)/(len(u)*len(v)),-1.,1.);return std::acos(q)*180./3.14159265358979323846;};double aa=angle(sub(b,a),sub(c,a)),bb=angle(sub(a,b),sub(c,b)),cc=angle(sub(a,c),sub(b,c)),nonorth=std::max({std::abs(aa-60.),std::abs(bb-60.),std::abs(cc-60.)});sv.push_back(skew);nv.push_back(nonorth);av.push_back(aspect);bool ok=lineage(provenance[i]);provok=provok&&ok;py::dict e;e["entity_id"]=i;e["oriented_area"]=oriented;e["skewness"]=skew;e["non_orthogonality"]=nonorth;e["metric_aspect_ratio"]=aspect;e["provenance_complete"]=ok;e["provenance"]=provenance[i];entities.append(e);}
 for(const auto&[edge,fs]:edges)if(fs.size()>2)nonmanifold++;
 for(size_t i=0;i<boxes.size();++i)for(size_t j=i+1;j<boxes.size();++j){bool shared=false;for(auto id:verts[i])shared=shared||verts[j].contains(id);if(!shared&&overlap(boxes[i],boxes[j],eps))selfx++;}
 py::dict top;top["invalid"]=invalid;top["inverted"]=inverted;top["duplicate"]=duplicate;top["non_manifold"]=nonmanifold;top["self_intersecting"]=selfx;py::dict q;q["skewness"]=distribution(sv,"(longest-shortest)/longest triangle-edge proxy");q["non_orthogonality"]=distribution(nv,"maximum triangle-angle deviation from 60 degrees");q["metric_aspect_ratio"]=distribution(av,"longest/shortest physical edge; metric normalization is upstream");
 double s95=sv.empty()?INFINITY:pct(sv,.95),s99=sv.empty()?INFINITY:pct(sv,.99),sm=sv.empty()?INFINITY:*std::max_element(sv.begin(),sv.end()),n95=nv.empty()?INFINITY:pct(nv,.95),n99=nv.empty()?INFINITY:pct(nv,.99),nm=nv.empty()?INFINITY:*std::max_element(nv.begin(),nv.end()),a95=av.empty()?INFINITY:pct(av,.95),a99=av.empty()?INFINITY:pct(av,.99),am=av.empty()?INFINITY:*std::max_element(av.begin(),av.end());bool accepted=triangles.shape(0)>0&&!invalid&&!inverted&&!duplicate&&!nonmanifold&&!selfx&&provok&&s95<=.30&&s99<=.40&&sm<=.50&&n95<=45&&n99<=65&&nm<=75&&a95<=3&&a99<=5&&am<=10;
 py::dict th;th["skewness_p95"]=.30;th["skewness_p99"]=.40;th["skewness_max"]=.50;th["non_orthogonality_p95"]=45.;th["non_orthogonality_p99"]=65.;th["non_orthogonality_max"]=75.;th["metric_aspect_ratio_p95"]=3.;th["metric_aspect_ratio_p99"]=5.;th["metric_aspect_ratio_max"]=10.;py::dict defs;defs["area"]="oriented triangle area";defs["skewness"]="longest-shortest over longest edge";defs["non_orthogonality"]="maximum triangle-angle deviation from 60 degrees";defs["metric_aspect_ratio"]="physical edge ratio; metric normalization is upstream";py::dict out;out["accepted"]=accepted;out["status"]=accepted?"quality_evidence_ready":"quality_gate_refused";out["reason"]=accepted?"quality_gates_passed":"topology_provenance_or_metric_gate_failed";out["topology"]=top;out["provenance_complete"]=provok;out["quality"]=q;out["thresholds"]=th;out["per_entity"]=entities;out["definitions"]=defs;return out;
}

py::dict wall_stack_distribution(const std::vector<double>& values, const char* definition) {
    return distribution(values, definition);
}

bool stack_semantic_lineage(const py::handle& item, std::int64_t edge_id, std::int64_t layer_id) {
    if (!py::isinstance<py::dict>(item)) return false;
    const py::dict row = py::reinterpret_borrow<py::dict>(item);
    for (const char* key : {"source_wall_edge", "source_face", "layer", "patch", "feature",
                            "physical_group", "provenance", "generated_vertices"}) {
        if (!row.contains(key) || row[key].is_none()) return false;
    }
    try {
        return row["source_wall_edge"].cast<std::int64_t>() == edge_id &&
               row["layer"].cast<std::int64_t>() == layer_id;
    } catch (const py::cast_error&) {
        return false;
    }
}

py::dict wall_stack_topology(std::int64_t invalid, std::int64_t inverted,
                             std::int64_t duplicate, std::int64_t non_manifold,
                             std::int64_t self_intersecting) {
    py::dict result;
    result["invalid"] = invalid;
    result["inverted"] = inverted;
    result["duplicate"] = duplicate;
    result["non_manifold"] = non_manifold;
    result["self_intersecting"] = self_intersecting;
    return result;
}

py::dict evaluate_wall_edge_stack(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& source_points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edges,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& layer_points,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals,
    const py::list& provenance, std::int64_t requested_layers, double epsilon = 1.0e-12) {
    if (source_points.ndim() != 2 || source_points.shape(1) != 3 ||
        edges.ndim() != 2 || edges.shape(1) != 4 ||
        normals.ndim() != 2 || normals.shape(1) != 3) {
        throw std::invalid_argument("source_points Nx3, edges Ex4, normals Fx3 required");
    }
    if (requested_layers < 0 || !(epsilon > 0.0) || !std::isfinite(epsilon)) {
        throw std::invalid_argument("requested_layers and epsilon are invalid");
    }
    const auto edge_count = static_cast<std::int64_t>(edges.shape(0));
    auto empty_quality = [] {
        py::dict result;
        result["status"] = "not_measured";
        result["count"] = 0;
        result["p95"] = py::none();
        result["p99"] = py::none();
        result["max"] = py::none();
        return result;
    };
    if (requested_layers == 0) {
        py::dict result;
        result["accepted"] = true;
        result["status"] = "disabled_identity";
        result["reason"] = "disabled_identity";
        result["requested_layers"] = 0;
        result["actual_layers"] = 0;
        result["generated_vertices"] = py::list();
        result["generated_faces"] = py::list();
        result["provenance"] = py::list();
        result["topology"] = wall_stack_topology(0, 0, 0, 0, 0);
        result["provenance_complete"] = true;
        py::dict quality;
        quality["wall_edge_non_orthogonality"] = empty_quality();
        quality["tangential_skewness"] = empty_quality();
        quality["metric_distortion"] = empty_quality();
        quality["raw_aspect_ratio"] = empty_quality();
        result["quality"] = quality;
        result["source_immutable"] = true;
        result["runtime_route"] = "default_off";
        return result;
    }
    if (layer_points.ndim() != 4 || layer_points.shape(0) != requested_layers ||
        layer_points.shape(1) != edge_count || layer_points.shape(2) != 2 ||
        layer_points.shape(3) != 3) {
        throw std::invalid_argument("layer_points must be LxEx2x3 and cover requested_layers");
    }
    if (provenance.size() != static_cast<size_t>(requested_layers * edge_count)) {
        py::dict result;
        result["accepted"] = false;
        result["status"] = "quality_gate_refused";
        result["reason"] = "incomplete_requested_edge_layers";
        result["requested_layers"] = requested_layers;
        result["actual_layers"] = 0;
        result["generated_vertices"] = py::list();
        result["generated_faces"] = py::list();
        result["provenance_complete"] = false;
        result["topology"] = wall_stack_topology(0, 0, 0, 0, 0);
        result["runtime_route"] = "default_off";
        return result;
    }

    const double* source_data = source_points.data();
    const auto* edge_data = edges.data();
    const double* layer_data = layer_points.data();
    const double* normal_data = normals.data();
    auto point = [&](std::int64_t id) -> V {
        if (id < 0 || id >= source_points.shape(0)) {
            throw std::invalid_argument("edge endpoint is out of range");
        }
        const size_t offset = static_cast<size_t>(id) * 3U;
        return V{source_data[offset], source_data[offset + 1U], source_data[offset + 2U]};
    };
    auto layer_point = [&](std::int64_t layer, std::int64_t edge, int endpoint) -> V {
        const size_t offset = (static_cast<size_t>(layer) * static_cast<size_t>(edge_count) +
                               static_cast<size_t>(edge)) * 6U +
                              static_cast<size_t>(endpoint) * 3U;
        return V{layer_data[offset], layer_data[offset + 1U], layer_data[offset + 2U]};
    };
    auto finite_point = [](V p) { return finite(p); };

    std::int64_t invalid = 0, inverted = 0, duplicate = 0, non_manifold = 0;
    std::set<std::int64_t> edge_ids;
    std::map<std::pair<std::int64_t, std::int64_t>, std::int64_t> endpoint_counts;
    for (py::ssize_t index = 0; index < edges.shape(0); ++index) {
        const size_t offset = static_cast<size_t>(index) * 4U;
        const std::int64_t edge_id = edge_data[offset];
        std::int64_t a_id = edge_data[offset + 1U];
        std::int64_t b_id = edge_data[offset + 2U];
        const std::int64_t face_id = edge_data[offset + 3U];
        if (!edge_ids.insert(edge_id).second) ++duplicate;
        if (a_id > b_id) std::swap(a_id, b_id);
        if (a_id == b_id) ++invalid;
        if (++endpoint_counts[{a_id, b_id}] > 1) ++non_manifold;
        if (face_id < 0 || face_id >= normals.shape(0)) ++invalid;
        try {
            if (!finite_point(point(edge_data[offset + 1U])) ||
                !finite_point(point(edge_data[offset + 2U]))) ++invalid;
        } catch (const std::invalid_argument&) {
            ++invalid;
        }
    }

    std::vector<double> orthogonality, skewness, distortion, aspect;
    py::list entities;
    bool provenance_complete = true;
    double minimum_height = std::numeric_limits<double>::infinity();
    double minimum_area = std::numeric_limits<double>::infinity();
    for (std::int64_t layer = 1; layer <= requested_layers; ++layer) {
        for (std::int64_t edge = 0; edge < edge_count; ++edge) {
            const size_t edge_offset = static_cast<size_t>(edge) * 4U;
            const std::int64_t edge_id = edge_data[edge_offset];
            const std::int64_t a_id = edge_data[edge_offset + 1U];
            const std::int64_t b_id = edge_data[edge_offset + 2U];
            const std::int64_t face_id = edge_data[edge_offset + 3U];
            const py::handle lineage_item = provenance[static_cast<size_t>((layer - 1) * edge_count + edge)];
            if (!stack_semantic_lineage(lineage_item, edge_id, layer)) provenance_complete = false;
            if (face_id < 0 || face_id >= normals.shape(0)) {
                ++invalid;
                continue;
            }
            V lower_a, lower_b, upper_a, upper_b, normal;
            try {
                lower_a = layer == 1 ? point(a_id) : layer_point(layer - 2, edge, 0);
                lower_b = layer == 1 ? point(b_id) : layer_point(layer - 2, edge, 1);
                upper_a = layer_point(layer - 1, edge, 0);
                upper_b = layer_point(layer - 1, edge, 1);
                normal = unit(V{normal_data[static_cast<size_t>(face_id) * 3U],
                                normal_data[static_cast<size_t>(face_id) * 3U + 1U],
                                normal_data[static_cast<size_t>(face_id) * 3U + 2U]});
            } catch (const std::invalid_argument&) {
                ++invalid;
                continue;
            }
            if (!finite_point(lower_a) || !finite_point(lower_b) ||
                !finite_point(upper_a) || !finite_point(upper_b)) {
                ++invalid;
                continue;
            }
            const V lower_edge = sub(lower_b, lower_a);
            const V upper_edge = sub(upper_b, upper_a);
            const double lower_length = len(lower_edge);
            if (!(lower_length > epsilon) || !std::isfinite(lower_length)) {
                ++invalid;
                continue;
            }
            const V tangent = unit(lower_edge);
            const V co_normal = unit(cross(normal, tangent));
            const V displacement = scale(addv(sub(upper_a, lower_a), sub(upper_b, lower_b)), 0.5);
            const double height = dot(displacement, co_normal);
            const double displacement_length = len(displacement);
            const double tangential_component = len(sub(displacement, scale(co_normal, height)));
            const V edge_average = scale(addv(lower_edge, upper_edge), 0.5);
            const double strip_area = 0.5 * (
                dot(cross(lower_edge, sub(upper_a, lower_a)), normal) +
                dot(cross(sub(upper_b, lower_b), sub(upper_a, lower_b)), normal));
            if (!std::isfinite(height) || !(height > epsilon)) {
                if (height < -epsilon) ++inverted;
                else ++invalid;
                continue;
            }
            if (!std::isfinite(strip_area) || !(strip_area > epsilon)) {
                if (strip_area < -epsilon) ++inverted;
                else ++invalid;
                continue;
            }
            const double theta = std::acos(std::clamp(height / displacement_length, -1.0, 1.0)) *
                                 180.0 / std::acos(-1.0);
            const double tangential_skew = tangential_component / height;
            const double raw_aspect = std::max(lower_length, height) / std::min(lower_length, height);
            const double j00 = dot(edge_average, tangent) / lower_length;
            const double j10 = dot(edge_average, co_normal) / lower_length;
            const double j01 = dot(displacement, tangent) / height;
            const double j11 = dot(displacement, co_normal) / height;
            const double gram00 = j00 * j00 + j10 * j10;
            const double gram01 = j00 * j01 + j10 * j11;
            const double gram11 = j01 * j01 + j11 * j11;
            const double trace = gram00 + gram11;
            const double determinant = std::max(0.0, gram00 * gram11 - gram01 * gram01);
            const double discriminant = std::max(0.0, trace * trace - 4.0 * determinant);
            const double sigma_max = std::sqrt(std::max(0.0, 0.5 * (trace + std::sqrt(discriminant))));
            const double sigma_min = std::sqrt(std::max(0.0, 0.5 * (trace - std::sqrt(discriminant))));
            const double metric_distortion = sigma_min > epsilon
                ? std::max(sigma_max, 1.0 / sigma_min)
                : std::numeric_limits<double>::infinity();
            if (!std::isfinite(theta) || !std::isfinite(tangential_skew) ||
                !std::isfinite(raw_aspect) || !std::isfinite(metric_distortion)) ++invalid;
            orthogonality.push_back(theta);
            skewness.push_back(tangential_skew);
            distortion.push_back(metric_distortion);
            aspect.push_back(raw_aspect);
            minimum_height = std::min(minimum_height, height);
            minimum_area = std::min(minimum_area, strip_area);
            py::dict entity;
            entity["edge"] = edge_id;
            entity["layer"] = layer;
            entity["height"] = height;
            entity["strip_area"] = strip_area;
            entity["wall_edge_non_orthogonality"] = theta;
            entity["tangential_skewness"] = tangential_skew;
            entity["metric_distortion"] = metric_distortion;
            entity["raw_aspect_ratio"] = raw_aspect;
            entity["provenance_complete"] = stack_semantic_lineage(lineage_item, edge_id, layer);
            entities.append(entity);
        }
    }

    const auto topology = wall_stack_topology(invalid, inverted, duplicate, non_manifold, 0);
    const double theta_p95 = orthogonality.empty() ? std::numeric_limits<double>::infinity() : pct(orthogonality, 0.95);
    const double theta_max = orthogonality.empty() ? std::numeric_limits<double>::infinity() : *std::max_element(orthogonality.begin(), orthogonality.end());
    const double skew_p95 = skewness.empty() ? std::numeric_limits<double>::infinity() : pct(skewness, 0.95);
    const double skew_max = skewness.empty() ? std::numeric_limits<double>::infinity() : *std::max_element(skewness.begin(), skewness.end());
    const double distortion_p99 = distortion.empty() ? std::numeric_limits<double>::infinity() : pct(distortion, 0.99);
    const double distortion_max = distortion.empty() ? std::numeric_limits<double>::infinity() : *std::max_element(distortion.begin(), distortion.end());
    const bool accepted = edge_count > 0 && provenance_complete &&
        invalid == 0 && inverted == 0 && duplicate == 0 && non_manifold == 0 &&
        theta_p95 <= 35.0 && theta_max <= 50.0 &&
        skew_p95 <= 0.25 && skew_max <= 0.50 &&
        distortion_p99 <= 10.0 && distortion_max <= 20.0;

    py::dict quality;
    quality["wall_edge_non_orthogonality"] = wall_stack_distribution(orthogonality, "degrees from wall-normal co-normal");
    quality["tangential_skewness"] = wall_stack_distribution(skewness, "tangential advance divided by wall-normal height");
    quality["metric_distortion"] = wall_stack_distribution(distortion, "max singular stretch or inverse minimum singular stretch");
    quality["raw_aspect_ratio"] = wall_stack_distribution(aspect, "max(lower edge length,height)/min(lower edge length,height)");
    quality["minimum_height"] = minimum_height;
    quality["minimum_strip_area"] = minimum_area;
    py::dict thresholds;
    thresholds["wall_edge_non_orthogonality_p95"] = 35.0;
    thresholds["wall_edge_non_orthogonality_max"] = 50.0;
    thresholds["tangential_skewness_p95"] = 0.25;
    thresholds["tangential_skewness_max"] = 0.50;
    thresholds["metric_distortion_p99"] = 10.0;
    thresholds["metric_distortion_max"] = 20.0;
    py::dict result;
    result["accepted"] = accepted;
    result["status"] = accepted ? "quality_evidence_ready" : "quality_gate_refused";
    result["reason"] = accepted ? "wall_edge_metrics_passed" : "topology_lineage_or_metric_gate_failed";
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = accepted ? requested_layers : 0;
    result["generated_vertices"] = py::list();
    result["generated_faces"] = py::list();
    result["provenance"] = provenance;
    result["topology"] = topology;
    result["provenance_complete"] = provenance_complete;
    result["quality"] = quality;
    result["thresholds"] = thresholds;
    result["per_entity"] = entities;
    result["source_immutable"] = true;
    result["runtime_route"] = "default_off";
    return result;
}


py::dict evaluate_frozen_front_diagnostic(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& source_points,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& edges,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& layer_points,
    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals,
    const py::list& provenance, std::int64_t requested_layers,
    const py::object& collision_witness = py::none(),
    const py::object& geodesic_witness = py::none(),
    double epsilon = 1.0e-12) {
    py::dict result;
    result["runtime_route"] = "default_off";
    result["publication_eligible"] = false;
    result["source_immutable"] = true;
    result["requested_layers"] = requested_layers;
    result["actual_layers"] = 0;
    if (requested_layers < 0) {
        result["status"] = "refused_rollback";
        result["reason"] = "negative_layer_count";
        return result;
    }
    if (requested_layers == 0) {
        result["accepted"] = true;
        result["status"] = "disabled_identity";
        result["reason"] = "disabled_identity";
        result["topology"] = wall_stack_topology(0, 0, 0, 0, 0);
        py::dict frozen_empty; frozen_empty["status"] = "not_measured"; frozen_empty["checked"] = 0; frozen_empty["changed"] = 0; result["frozen_front"] = frozen_empty;
        py::dict collision_empty; collision_empty["status"] = "not_measured"; collision_empty["checked"] = 0; collision_empty["collisions"] = 0; result["collision_visibility"] = collision_empty;
        py::dict geodesic_empty; geodesic_empty["status"] = "not_measured"; geodesic_empty["checked"] = 0; result["geodesic"] = geodesic_empty;
        return result;
    }
    if (source_points.ndim() != 2 || source_points.shape(1) != 3 ||
        edges.ndim() != 2 || edges.shape(1) != 4 ||
        normals.ndim() != 2 || normals.shape(1) != 3 ||
        layer_points.ndim() != 4 ||
        layer_points.shape(0) != requested_layers ||
        layer_points.shape(1) != edges.shape(0) ||
        layer_points.shape(2) != 2 || layer_points.shape(3) != 3) {
        throw std::invalid_argument("frozen-front diagnostic shapes are invalid");
    }
    const auto edge_count = static_cast<std::int64_t>(edges.shape(0));
    const auto expected = static_cast<size_t>(requested_layers * edge_count);
    if (provenance.size() != expected) {
        result["accepted"] = false;
        result["status"] = "quality_gate_refused";
        result["reason"] = "incomplete_frozen_front_provenance";
        result["topology"] = wall_stack_topology(0, 0, 0, 0, 0);
        py::dict frozen_incomplete; frozen_incomplete["status"] = "incomplete"; frozen_incomplete["checked"] = 0; frozen_incomplete["changed"] = 0; result["frozen_front"] = frozen_incomplete;
        return result;
    }

    py::dict base = evaluate_wall_edge_stack(
        source_points, edges, layer_points, normals, provenance,
        requested_layers, epsilon);
    result["quality"] = base["quality"];
    result["thresholds"] = base["thresholds"];
    result["per_entity"] = base["per_entity"];
    result["topology"] = base["topology"];
    result["provenance_complete"] = base["provenance_complete"];

    const auto require_lineage = [](const py::handle& item, std::int64_t edge_id,
                                     std::int64_t layer_id) {
        if (!py::isinstance<py::dict>(item)) return false;
        const py::dict row = py::reinterpret_borrow<py::dict>(item);
        for (const char* key : {"source_wall_edge", "source_face", "layer",
                                "patch", "feature", "physical_group",
                                "component", "provenance"}) {
            if (!row.contains(key) || row[key].is_none()) return false;
        }
        try {
            return row["source_wall_edge"].cast<std::int64_t>() == edge_id &&
                   row["layer"].cast<std::int64_t>() == layer_id;
        } catch (const py::cast_error&) {
            return false;
        }
    };
    const auto same_semantics = [](const py::handle& first, const py::handle& next) {
        const py::dict a = py::reinterpret_borrow<py::dict>(first);
        const py::dict b = py::reinterpret_borrow<py::dict>(next);
        for (const char* key : {"source_wall_edge", "source_face", "patch",
                                "feature", "physical_group", "component",
                                "provenance"}) {
            if (py::str(a[key]) != py::str(b[key])) return false;
        }
        return true;
    };

    bool frozen_ok = true;
    std::int64_t frozen_checked = 0;
    std::int64_t frozen_changed = 0;
    std::map<std::int64_t, py::object> first_by_edge;
    const auto* edge_data = edges.data();
    for (std::int64_t layer = 1; layer <= requested_layers; ++layer) {
        for (std::int64_t edge = 0; edge < edge_count; ++edge) {
            const auto edge_offset = static_cast<size_t>(edge) * 4U;
            const auto edge_id = edge_data[edge_offset];
            const py::handle item = provenance[static_cast<size_t>((layer - 1) * edge_count + edge)];
            if (!require_lineage(item, edge_id, layer)) {
                frozen_ok = false;
                continue;
            }
            ++frozen_checked;
            if (layer == 1) {
                first_by_edge.emplace(edge_id, py::reinterpret_borrow<py::object>(item));
            } else if (!same_semantics(first_by_edge.at(edge_id), item)) {
                frozen_ok = false;
                ++frozen_changed;
            }
        }
    }
    py::dict frozen;
    frozen["status"] = frozen_ok ? "frozen" : "changed_or_incomplete";
    frozen["checked"] = frozen_checked;
    frozen["changed"] = frozen_changed;
    result["frozen_front"] = frozen;

    bool collision_ok = true;
    std::int64_t collision_checked = 0;
    std::int64_t collisions = 0;
    if (collision_witness.is_none()) {
        collision_ok = false;
    } else {
        const py::list witness = collision_witness.cast<py::list>();
        if (witness.size() != expected) {
            collision_ok = false;
        } else {
            for (const py::handle item : witness) {
                if (!py::isinstance<py::dict>(item)) {
                    collision_ok = false;
                    continue;
                }
                const py::dict row = py::reinterpret_borrow<py::dict>(item);
                if (!row.contains("visible") || !row.contains("collision") ||
                    !row.contains("method") || row["method"].is_none() ||
                    !py::isinstance<py::bool_>(row["visible"]) ||
                    !py::isinstance<py::bool_>(row["collision"])) {
                    collision_ok = false;
                    continue;
                }
                ++collision_checked;
                if (!row["visible"].cast<bool>() || row["collision"].cast<bool>()) {
                    ++collisions;
                    collision_ok = false;
                }
            }
        }
    }
    py::dict collision;
    collision["status"] = collision_ok ? "measured_clear" : "incomplete_or_collision";
    collision["checked"] = collision_checked;
    collision["collisions"] = collisions;
    result["collision_visibility"] = collision;

    bool geodesic_ok = true;
    std::int64_t geodesic_checked = 0;
    if (geodesic_witness.is_none()) {
        geodesic_ok = false;
    } else {
        const py::list witness = geodesic_witness.cast<py::list>();
        if (witness.size() != static_cast<size_t>(requested_layers)) {
            geodesic_ok = false;
        } else {
            for (const py::handle item : witness) {
                if (!py::isinstance<py::dict>(item)) {
                    geodesic_ok = false;
                    continue;
                }
                const py::dict row = py::reinterpret_borrow<py::dict>(item);
                if (!row.contains("status") || !row.contains("distance") ||
                    !row.contains("path_digest") || !row.contains("method") ||
                    row["status"].cast<std::string>() != "measured" ||
                    row["path_digest"].cast<std::string>().empty() ||
                    row["method"].cast<std::string>().empty()) {
                    geodesic_ok = false;
                    continue;
                }
                try {
                    const double distance = row["distance"].cast<double>();
                    if (!std::isfinite(distance) || distance < 0.0) {
                        geodesic_ok = false;
                        continue;
                    }
                } catch (const py::cast_error&) {
                    geodesic_ok = false;
                    continue;
                }
                ++geodesic_checked;
            }
        }
    }
    py::dict geodesic;
    geodesic["status"] = geodesic_ok ? "measured" : "unmeasured_or_incomplete";
    geodesic["checked"] = geodesic_checked;
    result["geodesic"] = geodesic;

    const bool base_ok = base["accepted"].cast<bool>();
    const bool accepted = base_ok && frozen_ok && collision_ok && geodesic_ok;
    result["accepted"] = accepted;
    result["status"] = accepted ? "quality_evidence_ready" : "quality_gate_refused";
    result["reason"] = accepted ? "frozen_front_collision_geodesic_gates_passed"
        : (!frozen_ok ? "frozen_front_changed_or_incomplete"
        : (!collision_ok ? "collision_or_visibility_witness_incomplete"
        : (!geodesic_ok ? "geodesic_witness_unmeasured"
        : "topology_lineage_or_metric_gate_failed")));
    result["actual_layers"] = accepted ? requested_layers : 0;
    return result;
}

PYBIND11_MODULE(native_surface_bl_quality,m){m.doc()="C++23 report-only surface quality evidence kernel";m.def("evaluate_surface_quality",&evaluate,py::arg("points"),py::arg("triangles"),py::arg("normals"),py::arg("provenance"),py::arg("epsilon")=1e-12);
    m.def("evaluate_wall_edge_stack", &evaluate_wall_edge_stack,
        py::arg("source_points"), py::arg("edges"), py::arg("layer_points"),
        py::arg("normals"), py::arg("provenance"), py::arg("requested_layers"),
        py::arg("epsilon") = 1.0e-12); m.def("evaluate_frozen_front_diagnostic", &evaluate_frozen_front_diagnostic, py::arg("source_points"), py::arg("edges"), py::arg("layer_points"), py::arg("normals"), py::arg("provenance"), py::arg("requested_layers"), py::arg("collision_witness") = py::none(), py::arg("geodesic_witness") = py::none(), py::arg("epsilon") = 1.0e-12);}
