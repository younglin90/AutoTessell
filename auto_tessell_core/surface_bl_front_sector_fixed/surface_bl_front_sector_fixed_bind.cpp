// Corrected default-off C++23 sectorized wall-edge candidate planner.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;
using V = std::array<double, 3>;
V sub(V a, V b) noexcept { return {a[0]-b[0], a[1]-b[1], a[2]-b[2]}; }
V add(V a, V b) noexcept { return {a[0]+b[0], a[1]+b[1], a[2]+b[2]}; }
V mul(V a, double s) noexcept { return {a[0]*s, a[1]*s, a[2]*s}; }
V cross(V a, V b) noexcept { return {a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]}; }
double dot(V a, V b) noexcept { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
double length(V a) noexcept { return std::sqrt(dot(a, a)); }
V unit(V a, const char* label) {
    const double n = length(a);
    if (!(n > 1e-14) || !std::isfinite(n)) throw std::invalid_argument(std::string(label)+" invalid");
    return mul(a, 1.0/n);
}

struct Box { V lo{INFINITY, INFINITY, INFINITY}; V hi{-INFINITY, -INFINITY, -INFINITY}; };
void add_box(Box& b, V p) noexcept { for (int i=0;i<3;++i) { b.lo[i]=std::min(b.lo[i],p[i]); b.hi[i]=std::max(b.hi[i],p[i]); } }
bool overlaps(const Box& a, const Box& b) noexcept { return a.lo[0]<=b.hi[0]&&a.hi[0]>=b.lo[0]&&a.lo[1]<=b.hi[1]&&a.hi[1]>=b.lo[1]&&a.lo[2]<=b.hi[2]&&a.hi[2]>=b.lo[2]; }
Box segment_box(V a, V b, double eps) noexcept { Box box; add_box(box,a); add_box(box,b); for(int i=0;i<3;++i){box.lo[i]-=eps;box.hi[i]+=eps;} return box; }

struct Tri { std::int64_t id; std::array<std::int64_t,3> ids; V a,b,c,centroid; Box box; };
struct Node { Box box; std::int64_t id{-1}; int left{-1}; int right{-1}; };

class Bvh {
public:
    explicit Bvh(std::vector<Tri> triangles) : triangles_(std::move(triangles)) {
        std::sort(triangles_.begin(), triangles_.end(), [](const Tri& a,const Tri& b){return std::tuple{a.centroid[0],a.centroid[1],a.centroid[2],a.id}<std::tuple{b.centroid[0],b.centroid[1],b.centroid[2],b.id};});
        if (!triangles_.empty()) build(0, static_cast<int>(triangles_.size()));
    }
    template<class F> void query(const Box& box, F&& f) const { if (!nodes_.empty()) query_node(0,box,f); }
private:
    int build(int begin,int end){
        const int index=static_cast<int>(nodes_.size()); nodes_.push_back({}); Box box;
        for(int i=begin;i<end;++i){add_box(box,triangles_[static_cast<size_t>(i)].a);add_box(box,triangles_[static_cast<size_t>(i)].b);add_box(box,triangles_[static_cast<size_t>(i)].c);} nodes_[static_cast<size_t>(index)].box=box;
        if(end-begin==1){nodes_[static_cast<size_t>(index)].id=triangles_[static_cast<size_t>(begin)].id;return index;}
        const int middle=begin+(end-begin)/2; nodes_[static_cast<size_t>(index)].left=build(begin,middle); nodes_[static_cast<size_t>(index)].right=build(middle,end); return index;
    }
    template<class F> void query_node(int index,const Box& box,F& f) const { const Node& n=nodes_[static_cast<size_t>(index)]; if(!overlaps(n.box,box)) return; if(n.id>=0){f(n.id);return;} query_node(n.left,box,f);query_node(n.right,box,f); }
    std::vector<Tri> triangles_; std::vector<Node> nodes_;
};

bool has_edge(const Tri& t,std::int64_t a,std::int64_t b) noexcept { bool x=false,y=false;for(auto id:t.ids){x|=id==a;y|=id==b;}return x&&y; }
bool segment_hit(V origin,V endpoint,const Tri& t) noexcept {
    constexpr double e=1e-12; V d=sub(endpoint,origin), e1=sub(t.b,t.a),e2=sub(t.c,t.a),p=cross(d,e2); double det=dot(e1,p); if(std::abs(det)<=e)return false; double inv=1.0/det; V tv=sub(origin,t.a); double u=dot(tv,p)*inv;if(u<-e||u>1+e)return false;V q=cross(tv,e1);double v=dot(d,q)*inv;if(v<-e||u+v>1+e)return false;double z=dot(e2,q)*inv;return z>=-e&&z<=1+e;
}

py::dict reject(std::string reason,std::int64_t requested){py::dict r;r["accepted"]=false;r["status"]="refused_rollback";r["reason"]=reason;r["requested_layers"]=requested;r["actual_layers"]=0;r["generated_vertices"]=py::list();r["generated_faces"]=py::list();r["provenance"]=py::list();r["source_immutable"]=true;return r;}

py::dict plan(
    const py::array_t<double,py::array::c_style|py::array::forcecast>& points,
    const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& edges,
    const py::array_t<double,py::array::c_style|py::array::forcecast>& normals,
    const py::list& patches,const py::list& features,const py::list& groups,const py::list& sides,
    std::int64_t requested,double height,double growth,const py::object& source_triangles=py::none(),double eps=1e-12)
{
    if(points.ndim()!=2||points.shape(1)!=3||edges.ndim()!=2||edges.shape(1)!=5||normals.ndim()!=2||normals.shape(1)!=3) throw std::invalid_argument("points Nx3, edges Ex5, normals Fx3 required");
    if(requested==0){py::dict r=reject("disabled_identity",0);r["accepted"]=true;r["status"]="disabled_identity";return r;}
    if(requested<0)return reject("negative_layer_count",requested);if(!std::isfinite(height)||height<=0)return reject("invalid_first_height",requested);if(!std::isfinite(growth)||growth<1)return reject("invalid_growth_ratio",requested);if(source_triangles.is_none())return reject("missing_conservative_visibility_inputs",requested);
    if(patches.size()!=static_cast<size_t>(normals.shape(0))||features.size()!=static_cast<size_t>(normals.shape(0))||groups.size()!=static_cast<size_t>(normals.shape(0))||sides.size()!=static_cast<size_t>(edges.shape(0)))throw std::invalid_argument("sector metadata length mismatch");
    const auto tri_array=source_triangles.cast<py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>>();if(tri_array.ndim()!=2||tri_array.shape(1)!=3)throw std::invalid_argument("source_triangles Tx3 required");
    const double* pd=points.data();const auto* ed=edges.data();const double* nd=normals.data();const auto* td=tri_array.data();
    const auto point=[&](std::int64_t id){if(id<0||id>=points.shape(0))throw std::invalid_argument("point index out of range");size_t o=static_cast<size_t>(id)*3U;return V{pd[o],pd[o+1U],pd[o+2U]};};
    std::vector<Tri> tris;tris.reserve(static_cast<size_t>(tri_array.shape(0)));for(py::ssize_t i=0;i<tri_array.shape(0);++i){size_t o=static_cast<size_t>(i)*3U;std::array<std::int64_t,3> ids{td[o],td[o+1U],td[o+2U]};Tri t{i,ids,point(ids[0]),point(ids[1]),point(ids[2]),{}, {}};t.centroid=mul(add(add(t.a,t.b),t.c),1.0/3.0);add_box(t.box,t.a);add_box(t.box,t.b);add_box(t.box,t.c);tris.push_back(t);}Bvh bvh(std::move(tris));
    struct Sector{std::int64_t edge,a,b,face;std::string side;};std::vector<Sector> sectors;for(py::ssize_t i=0;i<edges.shape(0);++i){size_t o=static_cast<size_t>(i)*5U;sectors.push_back({ed[o],ed[o+1U],ed[o+2U],ed[o+3U],py::cast<std::string>(sides[i])});}std::sort(sectors.begin(),sectors.end(),[](const Sector&a,const Sector&b){return std::tuple{a.edge,a.face,a.side,a.a,a.b}<std::tuple{b.edge,b.face,b.side,b.a,b.b};});for(size_t i=1;i<sectors.size();++i)if(std::tuple{sectors[i-1].edge,sectors[i-1].face,sectors[i-1].side}==std::tuple{sectors[i].edge,sectors[i].face,sectors[i].side})return reject("duplicate_sector_key",requested);
    py::list vertices,faces,lineage;std::int64_t gid=0;
    for(const Sector&s:sectors){if(s.face<0||s.face>=normals.shape(0))return reject("source_face_out_of_range",requested);V a=point(s.a),b=point(s.b),t=unit(sub(b,a),"edge tangent");size_t no=static_cast<size_t>(s.face)*3U;V n=unit(V{nd[no],nd[no+1U],nd[no+2U]},"sector normal"),co=unit(cross(n,t),"sector co-normal");std::string patch=py::cast<std::string>(patches[s.face]),feature=py::cast<std::string>(features[s.face]),group=py::cast<std::string>(groups[s.face]);
        for(std::int64_t layer=1;layer<=requested;++layer){double step=height*std::pow(growth,static_cast<double>(layer-1));V oa=add(a,mul(co,step)),ob=add(b,mul(co,step));if(dot(cross(sub(b,a),sub(ob,a)),n)<=eps||dot(cross(sub(ob,a),sub(oa,a)),n)<=eps)return reject("non_positive_oriented_strip",requested);std::int64_t witness=-1;Box q=segment_box(a,oa,eps);bvh.query(q,[&](std::int64_t id){if(witness>=0)return;size_t o=static_cast<size_t>(id)*3U;std::array<std::int64_t,3> ids{td[o],td[o+1U],td[o+2U]};Tri tri{id,ids,point(ids[0]),point(ids[1]),point(ids[2]),{}, {}};if(has_edge(tri,s.a,s.b))return;Box tb;add_box(tb,tri.a);add_box(tb,tri.b);add_box(tb,tri.c);if(!overlaps(q,tb))return;if(segment_hit(a,oa,tri)||segment_hit(b,ob,tri)||segment_hit(oa,ob,tri))witness=id;});if(witness>=0)return reject("visibility_witness_triangle_"+std::to_string(witness),requested);
            std::int64_t ga=gid++,gb=gid++;py::dict va;va["id"]=ga;va["x"]=oa[0];va["y"]=oa[1];va["z"]=oa[2];py::dict vb;vb["id"]=gb;vb["x"]=ob[0];vb["y"]=ob[1];vb["z"]=ob[2];vertices.append(va);vertices.append(vb);py::dict f0;f0["source_a"]=s.a;f0["source_b"]=s.b;f0["generated_b"]=gb;f0["generated_a"]=ga;f0["layer"]=layer;py::dict f1=f0;f1["source_b"]=gb;f1["generated_b"]=ga;faces.append(f0);faces.append(f1);py::dict p;p["source_wall_edge"]=s.edge;p["source_face"]=s.face;p["patch"]=patch;p["feature"]=feature;p["physical_group"]=group;p["side"]=s.side;p["layer"]=layer;p["normal"]=py::make_tuple(n[0],n[1],n[2]);p["co_normal"]=py::make_tuple(co[0],co[1],co[2]);p["visibility_witness"]=-1;p["candidate_ordinal"]=static_cast<std::int64_t>(lineage.size());lineage.append(p);
        }
    }
    py::dict r;r["accepted"]=true;r["status"]="candidate_plan_ready";r["reason"]="accepted_sector_bvh_plan";r["requested_layers"]=requested;r["actual_layers"]=requested;r["generated_vertices"]=vertices;r["generated_faces"]=faces;r["provenance"]=lineage;r["bvh_triangle_count"]=static_cast<std::int64_t>(tri_array.shape(0));r["source_immutable"]=true;r["count_is_report_only"]=true;return r;
}

PYBIND11_MODULE(native_surface_bl_front_sector,module){module.doc()="Default-off C++23 sectorized wall-edge planner";module.def("plan_surface_wall_edge_sectors",&plan,py::arg("points"),py::arg("edges"),py::arg("normals"),py::arg("patches"),py::arg("features"),py::arg("physical_groups"),py::arg("sides"),py::arg("requested_layers"),py::arg("first_height"),py::arg("growth"),py::arg("source_triangles")=py::none(),py::arg("epsilon")=1e-12);}
