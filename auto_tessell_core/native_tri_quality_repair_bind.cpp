// C++23 default-off constrained Native Tri surface quality repair kernel.
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
#include <string>
#include <utility>
#include <vector>

namespace py = pybind11;
using Point = std::array<double, 3>;
using Face = std::array<std::int64_t, 3>;
using Edge = std::pair<std::int64_t, std::int64_t>;
constexpr double EPS = 1.0e-12;
constexpr double PI = 3.14159265358979323846;

Point sub(const Point& a,const Point& b) noexcept{return{a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
Point add(const Point& a,const Point& b) noexcept{return{a[0]+b[0],a[1]+b[1],a[2]+b[2]};}
Point mul(const Point& a,double s) noexcept{return{a[0]*s,a[1]*s,a[2]*s};}
Point cross(const Point& a,const Point& b) noexcept{return{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
double dot(const Point& a,const Point& b) noexcept{return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
double norm(const Point& a) noexcept{return std::sqrt(dot(a,a));}
bool finite_point(const Point& p) noexcept{return std::isfinite(p[0])&&std::isfinite(p[1])&&std::isfinite(p[2]);}
Point unit(const Point& p) noexcept{const double n=norm(p);return n>EPS&&std::isfinite(n)?mul(p,1.0/n):Point{0.,0.,0.};}
Edge edge_key(std::int64_t a,std::int64_t b) noexcept{if(a>b)std::swap(a,b);return{a,b};}

py::dict refusal(const char* reason){py::dict r;r["accepted"]=false;r["status"]="quality_gate_refused";r["reason"]=reason;return r;}

struct FaceMetric{bool valid=false;double min_angle=0.,max_angle=180.,mean_ratio=0.,edge_aspect=std::numeric_limits<double>::infinity();};
double angle(const Point& a,const Point& b){const double d=norm(a)*norm(b);return d>EPS&&std::isfinite(d)?std::acos(std::clamp(dot(a,b)/d,-1.,1.))*180./PI:std::numeric_limits<double>::quiet_NaN();}
FaceMetric face_metric(const std::vector<Point>& p,const Face& f){
    const Point& a=p[(size_t)f[0]],&b=p[(size_t)f[1]],&c=p[(size_t)f[2]];
    const double ab=norm(sub(b,a)),bc=norm(sub(c,b)),ca=norm(sub(a,c)),twice=norm(cross(sub(b,a),sub(c,a)));
    FaceMetric m;if(!(ab>EPS&&bc>EPS&&ca>EPS&&twice>EPS))return m;
    const double aa=angle(sub(b,a),sub(c,a)),bb=angle(sub(a,b),sub(c,b)),cc=angle(sub(a,c),sub(b,c));
    const double sum=ab*ab+bc*bc+ca*ca;
    m.min_angle=std::min({aa,bb,cc});m.max_angle=std::max({aa,bb,cc});
    m.mean_ratio=2.*std::sqrt(3.)*twice/sum;
    m.edge_aspect=std::max({ab,bc,ca})/std::min({ab,bc,ca});
    m.valid=std::isfinite(m.min_angle)&&std::isfinite(m.max_angle)&&std::isfinite(m.mean_ratio)&&std::isfinite(m.edge_aspect)&&m.mean_ratio>0.;
    return m;
}

struct Box{Point lo{INFINITY,INFINITY,INFINITY};Point hi{-INFINITY,-INFINITY,-INFINITY};};
void expand(Box& b,const Point& p) noexcept{for(size_t i=0;i<3;++i){b.lo[i]=std::min(b.lo[i],p[i]);b.hi[i]=std::max(b.hi[i],p[i]);}}
bool overlap(const Box& a,const Box& b) noexcept{for(size_t i=0;i<3;++i)if(a.hi[i]<b.lo[i]-EPS||b.hi[i]<a.lo[i]-EPS)return false;return true;}
bool segment_triangle(const Point& p0,const Point& p1,const Point& a,const Point& b,const Point& c){
    const Point d=sub(p1,p0),e1=sub(b,a),e2=sub(c,a),h=cross(d,e2);const double det=dot(e1,h);
    if(std::abs(det)<=EPS)return false;
    const double inv=1./det;
    const Point s=sub(p0,a);
    const double u=inv*dot(s,h);if(u<-EPS||u>1.+EPS)return false;const Point q=cross(s,e1);
    const double v=inv*dot(d,q);if(v<-EPS||u+v>1.+EPS)return false;const double t=inv*dot(e2,q);
    return t>=-EPS&&t<=1.+EPS;
}
bool triangles_intersect(const std::vector<Point>& p,const Face& a,const Face& b){
    for(const auto x:a)for(const auto y:b)if(x==y)return false;
    Box ba,bb;for(auto x:a)expand(ba,p[(size_t)x]);for(auto x:b)expand(bb,p[(size_t)x]);if(!overlap(ba,bb))return false;
    Point pa[3]={p[(size_t)a[0]],p[(size_t)a[1]],p[(size_t)a[2]]},pb[3]={p[(size_t)b[0]],p[(size_t)b[1]],p[(size_t)b[2]]};
    for(size_t i=0;i<3;++i){if(segment_triangle(pa[i],pa[(i+1)%3],pb[0],pb[1],pb[2]))return true;if(segment_triangle(pb[i],pb[(i+1)%3],pa[0],pa[1],pa[2]))return true;}
    return false;
}
std::pair<std::int64_t,std::int64_t> first_intersection(const std::vector<Point>& p,const std::vector<Face>& f){
    for(std::int64_t i=0;i<(std::int64_t)f.size();++i)
        for(std::int64_t j=i+1;j<(std::int64_t)f.size();++j)
            if(triangles_intersect(p,f[(size_t)i],f[(size_t)j]))return{i,j};
    return{-1,-1};
}
std::int64_t self_count(const std::vector<Point>& p,const std::vector<Face>& f){std::int64_t n=0;for(size_t i=0;i<f.size();++i)for(size_t j=i+1;j<f.size();++j)if(triangles_intersect(p,f[i],f[j]))++n;return n;}

struct Topology{std::int64_t invalid=0,duplicate=0,non_manifold=0;bool valid=false;};
Topology audit(const std::vector<Point>& p,const std::vector<Face>& f){
    Topology r;std::set<Face> unique;std::map<Edge,std::int64_t> counts;
    for(const auto& x:f){if(x[0]==x[1]||x[1]==x[2]||x[2]==x[0])++r.invalid;for(auto id:x)if(id<0||id>=(std::int64_t)p.size())++r.invalid;Face k=x;std::sort(k.begin(),k.end());if(!unique.insert(k).second)++r.duplicate;for(size_t i=0;i<3;++i)++counts[edge_key(x[i],x[(i+1)%3])];}
    for(const auto& e:counts)
        if(e.second>2)++r.non_manifold;
    r.valid=r.invalid==0&&r.duplicate==0&&r.non_manifold==0;
    return r;
}

Point closest_point(const Point& p,const Point& a,const Point& b,const Point& c){
    const Point ab=sub(b,a),ac=sub(c,a),ap=sub(p,a);const double d1=dot(ab,ap),d2=dot(ac,ap);if(d1<=0&&d2<=0)return a;
    const Point bp=sub(p,b);const double d3=dot(ab,bp),d4=dot(ac,bp);if(d3>=0&&d4<=d3)return b;const double vc=d1*d4-d3*d2;
    if(vc<=0&&d1>=0&&d3<=0)return add(a,mul(ab,d1/(d1-d3)));
    const Point cp=sub(p,c);
    const double d5=dot(ab,cp),d6=dot(ac,cp);
    if(d6>=0&&d5<=d6)return c;
    const double vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0)return add(a,mul(ac,d2/(d2-d6)));const double va=d3*d6-d5*d4;
    if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0)return add(b,mul(sub(c,b),(d4-d3)/((d4-d3)+(d5-d6))));
    const double inv=1./(va+vb+vc);return add(a,add(mul(ab,vb*inv),mul(ac,vc*inv)));
}
bool source_projection(const Point& p,const std::vector<Point>& sp,const std::vector<Face>& sf,Point& best,double& dist){
    dist=INFINITY;bool found=false;for(const auto& f:sf){const Point q=closest_point(p,sp[(size_t)f[0]],sp[(size_t)f[1]],sp[(size_t)f[2]]);const double d=norm(sub(p,q));if(std::isfinite(d)&&d<dist){dist=d;best=q;found=true;}}return found;
}
double support_error(const std::vector<Point>& p,const std::vector<Point>& sp,const std::vector<Face>& sf){
    double mx=0.;for(const auto& x:p){Point q{};double d=0.;if(!source_projection(x,sp,sf,q,d))return INFINITY;mx=std::max(mx,d);}return mx;
}

bool inside_source_envelope(const Point& p,const std::vector<Point>& source) noexcept{
    if(source.empty())return false;
    Point lo{INFINITY,INFINITY,INFINITY},hi{-INFINITY,-INFINITY,-INFINITY};
    lo=Point{INFINITY,INFINITY,INFINITY};hi=Point{-INFINITY,-INFINITY,-INFINITY};
    for(const auto& x:source)for(size_t k=0;k<3;++k){lo[k]=std::min(lo[k],x[k]);hi[k]=std::max(hi[k],x[k]);}
    const double scale=std::max(norm(sub(hi,lo)),1.0),tol=1.0e-9*scale;
    return finite_point(p)&&p[0]>=lo[0]-tol&&p[0]<=hi[0]+tol&&p[1]>=lo[1]-tol&&p[1]<=hi[1]+tol&&p[2]>=lo[2]-tol&&p[2]<=hi[2]+tol;
}
Point face_normal(const std::vector<Point>& p,const Face& f) noexcept{
    return unit(cross(sub(p[(size_t)f[1]],p[(size_t)f[0]]),sub(p[(size_t)f[2]],p[(size_t)f[0]])));
}
Point face_centroid(const std::vector<Point>& p,const Face& f) noexcept{
    return mul(add(add(p[(size_t)f[0]],p[(size_t)f[1]]),p[(size_t)f[2]]),1.0/3.0);
}
double pair_scale(const std::vector<Point>& p,const Face& a,const Face& b) noexcept{
    Box box;for(const auto id:a)expand(box,p[(size_t)id]);for(const auto id:b)expand(box,p[(size_t)id]);
    return std::max(norm(sub(box.hi,box.lo)),EPS);
}
bool orientation_preserved(const std::vector<Point>& before,const std::vector<Point>& after,const std::vector<Face>& faces,const std::vector<std::vector<std::int64_t>>& incident,std::int64_t vertex) noexcept{
    for(const auto fi:incident[(size_t)vertex]){
        const auto& f=faces[(size_t)fi];const Point oa=before[(size_t)f[0]],ob=before[(size_t)f[1]],oc=before[(size_t)f[2]],na=cross(sub(ob,oa),sub(oc,oa));const double nl=norm(na);
        if(!std::isfinite(nl)||nl<=EPS)return false;
        const double scale=std::max({norm(sub(ob,oa)),norm(sub(oc,oa)),1.0});const Point probe=add(mul(add(add(oa,ob),oc),1.0/3.0),mul(na,scale/(3.0*nl)));
        const Point pa=after[(size_t)f[0]],pb=after[(size_t)f[1]],pc=after[(size_t)f[2]],nb=cross(sub(pb,pa),sub(pc,pa));const double sign=dot(nb,sub(probe,pa));
        if(!std::isfinite(sign)||sign<=EPS)return false;
    }
    return true;
}
std::vector<std::pair<std::string,Point>> collision_directions(const std::vector<Point>& p,const Face& a,const Face& b){
    const Point na=face_normal(p,a),nb=face_normal(p,b),nam=unit(sub(na,nb));
    std::vector<std::pair<std::string,Point>> out;
    const auto add_direction=[&out](const char* name,const Point& d){if(norm(d)>EPS)out.emplace_back(name,d);};
    add_direction("negative_face_a_normal",mul(na,-1.0));
    add_direction("normal_a_minus_normal_b",nam);
    return out;
}

struct Metrics{std::int64_t invalid=0,self_intersecting=0;double min_angle=INFINITY,max_angle=0.,min_ratio=INFINITY,max_aspect=0.,source_error=INFINITY;std::vector<FaceMetric> faces;};
Metrics measure(const std::vector<Point>& p,const std::vector<Face>& f,const std::vector<Point>& sp,const std::vector<Face>& sf){
    Metrics m;m.faces.reserve(f.size());for(const auto& x:f){const auto q=face_metric(p,x);m.faces.push_back(q);if(!q.valid){++m.invalid;continue;}m.min_angle=std::min(m.min_angle,q.min_angle);m.max_angle=std::max(m.max_angle,q.max_angle);m.min_ratio=std::min(m.min_ratio,q.mean_ratio);m.max_aspect=std::max(m.max_aspect,q.edge_aspect);}
    m.self_intersecting=self_count(p,f);m.source_error=support_error(p,sp,sf);if(m.invalid){m.min_angle=0.;m.max_angle=180.;m.min_ratio=0.;m.max_aspect=INFINITY;}return m;
}
std::array<double,8> tuple_of(const Metrics& m){return{static_cast<double>(m.invalid),static_cast<double>(m.self_intersecting),-m.min_angle,m.max_angle,-m.min_ratio,m.max_aspect,m.source_error,0.};}
bool improves(const std::array<double,8>& a,const std::array<double,8>& b){for(size_t i=0;i<a.size();++i){if(b[i]<a[i]-1e-12)return true;if(b[i]>a[i]+1e-12)return false;}return false;}
py::dict copy_dict(const py::dict& source){py::dict out;out.attr("update")(source);return out;}
py::dict metrics_dict(const Metrics& m){py::dict d;d["invalid"]=m.invalid;d["self_intersecting"]=m.self_intersecting;d["min_angle"]=m.min_angle;d["max_angle"]=m.max_angle;d["min_mean_ratio"]=m.min_ratio;d["max_edge_aspect"]=m.max_aspect;d["source_support_error"]=m.source_error;return d;}

struct QualityObjective{double max_defect=0.,weighted_defect=0.;};
QualityObjective quality_objective(const Metrics& m) noexcept{
    const double da=std::max(0.,(10.-m.min_angle)/10.);
    const double dz=std::max(0.,(m.max_angle-150.)/30.);
    const double dq=std::max(0.,(0.05-m.min_ratio)/0.05);
    const double ds=std::max(0.,(m.max_aspect-5.)/5.);
    return{std::max({da,dz,dq,ds}),da+dz+dq+ds};
}
std::array<double,10> admission_key(const Metrics& m) noexcept{
    const auto q=quality_objective(m);
    return{static_cast<double>(m.invalid),static_cast<double>(m.self_intersecting),q.max_defect,q.weighted_defect,m.max_angle,-m.min_angle,-m.min_ratio,m.max_aspect,m.source_error,0.};
}
bool improves10(const std::array<double,10>& a,const std::array<double,10>& b){for(size_t i=0;i<a.size();++i){if(b[i]<a[i]-1e-12)return true;if(b[i]>a[i]+1e-12)return false;}return false;}
bool key_not_worse(const std::array<double,10>& before,const std::array<double,10>& after){return !improves10(after,before);}
bool source_envelope_all(const std::vector<Point>& points,const std::vector<Point>& source) noexcept{
    for(const auto& point:points)if(!inside_source_envelope(point,source))return false;
    return true;
}
py::dict admission_receipt(
 const Metrics& before,const Metrics& after,const Topology& before_topology,const Topology& after_topology,
 bool source_ok,bool envelope_ok,bool hard_valid,bool non_regression,bool strict_improvement){
    py::dict out;
    out["schema"]="autotessell/native-tri-quality-admission/v1";
    out["accepted"]=hard_valid&&non_regression&&strict_improvement;
    out["status"]=(hard_valid&&non_regression&&strict_improvement)?"quality_admission_committed":"quality_admission_refused";
    out["reason"]=(hard_valid&&non_regression&&strict_improvement)?"strict_quality_improvement":(!hard_valid?"quality_hard_gate_failed":(!source_ok?"source_support_regressed":(!envelope_ok?"source_envelope_failed":(!non_regression?"quality_regression":"no_strict_quality_improvement"))));
    out["hard_valid"]=hard_valid;
    out["source_support_ok"]=source_ok;
    out["source_envelope_ok"]=envelope_ok;
    out["non_regression"]=non_regression;
    out["strict_improvement"]=strict_improvement;
    out["before"]=metrics_dict(before);
    out["after"]=metrics_dict(after);
    const auto before_key=admission_key(before);
    const auto after_key=admission_key(after);
    out["before_tuple"]=std::vector<double>(before_key.begin(),before_key.end());
    out["after_tuple"]=std::vector<double>(after_key.begin(),after_key.end());
    out["before_invalid"]=before_topology.invalid;
    out["before_duplicate"]=before_topology.duplicate;
    out["before_non_manifold"]=before_topology.non_manifold;
    out["after_invalid"]=after_topology.invalid;
    out["after_duplicate"]=after_topology.duplicate;
    out["after_non_manifold"]=after_topology.non_manifold;
    return out;
}
py::dict admit_surface_edit(
 const py::array_t<double,py::array::c_style|py::array::forcecast>& before_points_array,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& before_triangles_array,
 const py::array_t<double,py::array::c_style|py::array::forcecast>& after_points_array,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& after_triangles_array,
 const py::array_t<double,py::array::c_style|py::array::forcecast>& source_points_array,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& source_triangles_array){
    const auto shape_ok=[](const auto& points,const auto& triangles){return points.ndim()==2&&points.shape(1)==3&&triangles.ndim()==2&&triangles.shape(1)==3;};
    if(!shape_ok(before_points_array,before_triangles_array)||!shape_ok(after_points_array,after_triangles_array)||!shape_ok(source_points_array,source_triangles_array))return refusal("admission_input_shape_invalid");
    if(before_triangles_array.shape(0)==0||after_triangles_array.shape(0)==0||source_triangles_array.shape(0)==0)return refusal("admission_empty_surface");
    std::vector<Point> before_points,after_points,source_points;std::vector<Face> before_faces,after_faces,source_faces;
    before_points.reserve((size_t)before_points_array.shape(0));after_points.reserve((size_t)after_points_array.shape(0));source_points.reserve((size_t)source_points_array.shape(0));
    const auto* bpd=before_points_array.data();const auto* apd=after_points_array.data();const auto* spd=source_points_array.data();
    for(py::ssize_t i=0;i<before_points_array.shape(0);++i)before_points.push_back(Point{bpd[3U*(size_t)i],bpd[3U*(size_t)i+1U],bpd[3U*(size_t)i+2U]});
    for(py::ssize_t i=0;i<after_points_array.shape(0);++i)after_points.push_back(Point{apd[3U*(size_t)i],apd[3U*(size_t)i+1U],apd[3U*(size_t)i+2U]});
    for(py::ssize_t i=0;i<source_points_array.shape(0);++i)source_points.push_back(Point{spd[3U*(size_t)i],spd[3U*(size_t)i+1U],spd[3U*(size_t)i+2U]});
    const auto* bfd=before_triangles_array.data();const auto* afd=after_triangles_array.data();const auto* sfd=source_triangles_array.data();
    before_faces.reserve((size_t)before_triangles_array.shape(0));after_faces.reserve((size_t)after_triangles_array.shape(0));source_faces.reserve((size_t)source_triangles_array.shape(0));
    for(py::ssize_t i=0;i<before_triangles_array.shape(0);++i)before_faces.push_back(Face{bfd[3U*(size_t)i],bfd[3U*(size_t)i+1U],bfd[3U*(size_t)i+2U]});
    for(py::ssize_t i=0;i<after_triangles_array.shape(0);++i)after_faces.push_back(Face{afd[3U*(size_t)i],afd[3U*(size_t)i+1U],afd[3U*(size_t)i+2U]});
    for(py::ssize_t i=0;i<source_triangles_array.shape(0);++i)source_faces.push_back(Face{sfd[3U*(size_t)i],sfd[3U*(size_t)i+1U],sfd[3U*(size_t)i+2U]});
    for(const auto& points:std::vector<std::reference_wrapper<const std::vector<Point>>>{before_points,after_points,source_points})for(const auto& point:points.get())if(!finite_point(point))return refusal("admission_nonfinite_point");
    const auto validate_indices=[](const std::vector<Face>& faces,size_t n){for(const auto& face:faces)for(const auto id:face)if(id<0||id>=(std::int64_t)n)return false;return true;};
    if(!validate_indices(before_faces,before_points.size())||!validate_indices(after_faces,after_points.size())||!validate_indices(source_faces,source_points.size()))return refusal("admission_face_index_invalid");
    const auto before_topology=audit(before_points,before_faces),after_topology=audit(after_points,after_faces);
    if(!before_topology.valid)return refusal("admission_before_topology_invalid");
    if(!source_envelope_all(after_points,source_points))return admission_receipt(measure(before_points,before_faces,source_points,source_faces),measure(after_points,after_faces,source_points,source_faces),before_topology,after_topology,true,false,false,false,false);
    const Metrics before=measure(before_points,before_faces,source_points,source_faces),after=measure(after_points,after_faces,source_points,source_faces);
    Box source_box;for(const auto& point:source_points)expand(source_box,point);
    const double source_tolerance=1.e-8*std::max(norm(sub(source_box.hi,source_box.lo)),1.0);
    const bool source_ok=std::isfinite(before.source_error)&&std::isfinite(after.source_error)&&after.source_error<=before.source_error+source_tolerance;
    const bool hard_valid=after_topology.valid&&after.invalid==0&&after.self_intersecting==0&&source_ok;
    const auto before_tuple=admission_key(before),after_tuple=admission_key(after);
    const bool non_regression=key_not_worse(before_tuple,after_tuple);
    const bool strict_improvement=improves10(before_tuple,after_tuple);
    return admission_receipt(before,after,before_topology,after_topology,source_ok,true,hard_valid,non_regression,strict_improvement);
}


struct Point2{double x=0.,y=0.;};
struct Tri2{int a=0,b=0,c=0;};
py::list point_list(const std::vector<Point>& p);
double orient2(const Point2& a,const Point2& b,const Point2& c) noexcept{return(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);}
bool point_in_polygon2(const Point2& p,const std::vector<Point2>& polygon) noexcept{
    bool inside=false;if(polygon.size()<3)return false;
    for(size_t i=0,j=polygon.size()-1;i<polygon.size();j=i++){
        const auto& a=polygon[i];const auto& b=polygon[j];
        if(((a.y>p.y)!=(b.y>p.y))&&(p.x<(b.x-a.x)*(p.y-a.y)/(b.y-a.y+1.e-30)+a.x))inside=!inside;
    }
    return inside;
}
bool proper_cross2(const Point2& a,const Point2& b,const Point2& c,const Point2& d,double eps) noexcept{
    const double o1=orient2(a,b,c),o2=orient2(a,b,d),o3=orient2(c,d,a),o4=orient2(c,d,b);
    return((o1>eps&&o2<-eps)||(o1<-eps&&o2>eps))&&((o3>eps&&o4<-eps)||(o3<-eps&&o4>eps));
}
bool circumcircle_contains2(const std::vector<Point2>& points,const Tri2& tri,int index,double eps) noexcept{
    const Point2& a=points[(size_t)tri.a],&b=points[(size_t)tri.b],&c=points[(size_t)tri.c],&p=points[(size_t)index];
    const double ax=a.x-p.x,ay=a.y-p.y,bx=b.x-p.x,by=b.y-p.y,cx=c.x-p.x,cy=c.y-p.y;
    const double det=(ax*ax+ay*ay)*(bx*cy-by*cx)-(bx*bx+by*by)*(ax*cy-ay*cx)+(cx*cx+cy*cy)*(ax*by-ay*bx);
    const double orientation=orient2(a,b,c);
    return orientation>0.?det>eps:orientation<0.&&det<-eps;
}
bool delaunay_polygon2(const std::vector<Point2>& polygon,std::vector<Tri2>& result) {
    if(polygon.size()<3)return false;
    double min_x=polygon[0].x,max_x=polygon[0].x,min_y=polygon[0].y,max_y=polygon[0].y;
    for(const auto& p:polygon){min_x=std::min(min_x,p.x);max_x=std::max(max_x,p.x);min_y=std::min(min_y,p.y);max_y=std::max(max_y,p.y);}
    const double span=std::max({max_x-min_x,max_y-min_y,1.e-12}),cx=.5*(min_x+max_x),cy=.5*(min_y+max_y);
    std::vector<Point2> points=polygon;
    points.push_back({cx-32.*span,cy-16.*span});
    points.push_back({cx,cy+32.*span});
    points.push_back({cx+32.*span,cy-16.*span});
    std::vector<Tri2> triangles{{(int)polygon.size(),(int)polygon.size()+1,(int)polygon.size()+2}};
    const double eps=1.e-12*std::max(1.,span*span*span*span);
    for(int index=0;index<(int)polygon.size();++index){
        std::vector<Tri2> bad;std::map<Edge,int> boundary;
        for(const auto& tri:triangles)if(circumcircle_contains2(points,tri,index,eps)){
            bad.push_back(tri);
            for(const Edge edge:{edge_key(tri.a,tri.b),edge_key(tri.b,tri.c),edge_key(tri.c,tri.a)})++boundary[edge];
        }
        if(bad.empty())return false;
        std::vector<Tri2> kept;kept.reserve(triangles.size()+bad.size());
        for(const auto& tri:triangles){
            bool remove=false;
            for(const auto& candidate:bad)if(tri.a==candidate.a&&tri.b==candidate.b&&tri.c==candidate.c){remove=true;break;}
            if(!remove)kept.push_back(tri);
        }
        for(const auto& [edge,count]:boundary)if(count==1){
            Tri2 tri{(int)edge.first,(int)edge.second,index};
            if(orient2(points[(size_t)tri.a],points[(size_t)tri.b],points[(size_t)tri.c])<0.)std::swap(tri.a,tri.b);
            if(std::abs(orient2(points[(size_t)tri.a],points[(size_t)tri.b],points[(size_t)tri.c]))>eps)kept.push_back(tri);
        }
        triangles=std::move(kept);
    }
    double polygon_area=0.;
    for(size_t i=0;i<polygon.size();++i){const auto& a=polygon[i];const auto& b=polygon[(i+1)%polygon.size()];polygon_area+=a.x*b.y-b.x*a.y;}
    polygon_area*=.5;if(polygon_area<=eps)return false;
    double covered=0.;result.clear();
    for(const auto tri:triangles){
        if(tri.a>=(int)polygon.size()||tri.b>=(int)polygon.size()||tri.c>=(int)polygon.size())continue;
        const Point2 center{(points[(size_t)tri.a].x+points[(size_t)tri.b].x+points[(size_t)tri.c].x)/3.,(points[(size_t)tri.a].y+points[(size_t)tri.b].y+points[(size_t)tri.c].y)/3.};
        if(!point_in_polygon2(center,polygon))continue;
        bool crosses=false;
        const std::array<std::pair<int,int>,3> edges{{{tri.a,tri.b},{tri.b,tri.c},{tri.c,tri.a}}};
        for(const auto [a,b]:edges)for(size_t i=0;i<polygon.size();++i){
            const int c=(int)i,d=(int)((i+1)%polygon.size());
            if(a==c||a==d||b==c||b==d)continue;
            if(proper_cross2(points[(size_t)a],points[(size_t)b],polygon[i],polygon[(i+1)%polygon.size()],eps)){crosses=true;break;}
        }
        if(crosses)continue;
        const double area=std::abs(orient2(points[(size_t)tri.a],points[(size_t)tri.b],points[(size_t)tri.c]))*.5;
        if(area<=eps)continue;
        covered+=area;result.push_back(tri);
    }
    return result.size()==polygon.size()-2&&std::abs(covered-polygon_area)<=1.e-7*std::max(1.,polygon_area);
}
bool collect_fan_ring(const std::vector<Face>& faces,std::int64_t center,std::vector<std::int64_t>& incident,std::vector<std::int64_t>& ring){
    std::map<std::int64_t,std::vector<std::int64_t>> adjacency;std::set<Edge> boundary;
    incident.clear();
    for(std::int64_t fi=0;fi<(std::int64_t)faces.size();++fi){
        const auto& face=faces[(size_t)fi];int local=-1;for(int k=0;k<3;++k)if(face[(size_t)k]==center)local=k;
        if(local<0)continue;
        const auto a=face[(size_t)((local+1)%3)],b=face[(size_t)((local+2)%3)];const Edge edge=edge_key(a,b);
        if(!boundary.insert(edge).second)return false;adjacency[a].push_back(b);adjacency[b].push_back(a);incident.push_back(fi);
    }
    if(incident.size()<16||boundary.size()!=incident.size()||adjacency.size()>512)return false;
    for(auto& [vertex,neighbours]:adjacency){if(neighbours.size()!=2)return false;std::sort(neighbours.begin(),neighbours.end());}
    const auto start=adjacency.begin()->first;ring.clear();ring.push_back(start);std::int64_t previous=-1,current=start;
    for(size_t step=0;step<adjacency.size();++step){
        const auto& neighbours=adjacency[current];const auto next=neighbours[0]!=previous?neighbours[0]:neighbours[1];
        if(next==start){if(step+1!=adjacency.size())return false;break;}
        if(std::find(ring.begin(),ring.end(),next)!=ring.end())return false;
        ring.push_back(next);previous=current;current=next;
    }
    return ring.size()==adjacency.size();
}
bool triangulate_fan_ring(const std::vector<Point>& points,const std::vector<Face>& faces,std::vector<std::int64_t> ring,const std::vector<std::int64_t>& incident,std::vector<Face>& output){
    if(ring.size()<3||incident.empty())return false;
    Point centroid{};for(const auto vertex:ring)centroid=add(centroid,points[(size_t)vertex]);centroid=mul(centroid,1./(double)ring.size());
    Point normal{};
    for(const auto fi:incident){const auto& face=faces[(size_t)fi];normal=add(normal,cross(sub(points[(size_t)face[1]],points[(size_t)face[0]]),sub(points[(size_t)face[2]],points[(size_t)face[0]])));}
    normal=unit(normal);if(norm(normal)<=EPS)return false;
    Point u{};double best=0.;
    for(const auto vertex:ring){const Point projected=sub(sub(points[(size_t)vertex],centroid),mul(normal,dot(sub(points[(size_t)vertex],centroid),normal)));const double length=norm(projected);if(length>best){best=length;u=mul(projected,1./length);}}
    if(best<=EPS)return false;
    const Point w=unit(cross(normal,u));std::vector<Point2> polygon;polygon.reserve(ring.size());
    for(const auto vertex:ring){const Point d=sub(points[(size_t)vertex],centroid);polygon.push_back({dot(d,u),dot(d,w)});}
    double signed_area=0.;for(size_t i=0;i<polygon.size();++i)signed_area+=polygon[i].x*polygon[(i+1)%polygon.size()].y-polygon[(i+1)%polygon.size()].x*polygon[i].y;
    if(signed_area<0.){std::reverse(ring.begin(),ring.end());std::reverse(polygon.begin(),polygon.end());}
    std::vector<Tri2> local;if(!delaunay_polygon2(polygon,local))return false;
    output.clear();output.reserve(local.size());
    for(const auto tri:local){
        Face face{ring[(size_t)tri.a],ring[(size_t)tri.b],ring[(size_t)tri.c]};
        const Point n=cross(sub(points[(size_t)face[1]],points[(size_t)face[0]]),sub(points[(size_t)face[2]],points[(size_t)face[0]]));
        if(norm(n)<=EPS)return false;if(dot(n,normal)<0.)std::swap(face[1],face[2]);
        output.push_back(face);
    }
    return output.size()+2==ring.size();
}
py::list face_list(const std::vector<Face>& faces){py::list out;for(const auto& face:faces)out.append(std::vector<std::int64_t>{face[0],face[1],face[2]});return out;}
py::dict propose_worst_fan_patch(
 const py::array_t<double,py::array::c_style|py::array::forcecast>& points_array,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& triangles_array,
 std::int64_t max_centers,std::int64_t minimum_valence){
    if(points_array.ndim()!=2||points_array.shape(1)!=3||triangles_array.ndim()!=2||triangles_array.shape(1)!=3||max_centers<1||max_centers>4||minimum_valence<3)return refusal("fan_patch_parameters_invalid");
    std::vector<Point> points;std::vector<Face> faces;const auto* pd=points_array.data();const auto* fd=triangles_array.data();
    for(py::ssize_t i=0;i<points_array.shape(0);++i){Point p{pd[3U*(size_t)i],pd[3U*(size_t)i+1U],pd[3U*(size_t)i+2U]};if(!finite_point(p))return refusal("fan_patch_nonfinite_point");points.push_back(p);}
    for(py::ssize_t i=0;i<triangles_array.shape(0);++i){Face f{fd[3U*(size_t)i],fd[3U*(size_t)i+1U],fd[3U*(size_t)i+2U]};for(const auto id:f)if(id<0||id>=(std::int64_t)points.size())return refusal("fan_patch_face_index_invalid");faces.push_back(f);}
    const auto topology=audit(points,faces);if(!topology.valid||faces.empty())return refusal("fan_patch_input_topology_invalid");
    std::vector<std::int64_t> valence(points.size(),0);for(const auto& face:faces)for(const auto id:face)++valence[(size_t)id];
    std::vector<std::int64_t> centers;for(std::int64_t id=0;id<(std::int64_t)valence.size();++id)if(valence[(size_t)id]>=minimum_valence)centers.push_back(id);
    std::sort(centers.begin(),centers.end(),[&](const auto a,const auto b){return valence[(size_t)a]!=valence[(size_t)b]?valence[(size_t)a]>valence[(size_t)b]:a<b;});
    struct Patch{std::int64_t center;std::vector<std::int64_t> incident,ring;std::vector<Face> faces;};
    std::vector<Patch> patches;std::set<std::int64_t> selected_faces;
    for(const auto center:centers){
        if((std::int64_t)patches.size()>=max_centers)break;
        Patch patch{center,{},{},{}};
        if(!collect_fan_ring(faces,center,patch.incident,patch.ring))continue;
        bool overlap=false;for(const auto fi:patch.incident)if(selected_faces.count(fi)){overlap=true;break;}if(overlap)continue;
        if(!triangulate_fan_ring(points,faces,patch.ring,patch.incident,patch.faces))continue;
        for(const auto fi:patch.incident)selected_faces.insert(fi);patches.push_back(std::move(patch));
    }
    if(patches.empty())return refusal("fan_patch_no_closed_quality_ring");
    std::vector<Face> candidate;candidate.reserve(faces.size());
    for(std::int64_t fi=0;fi<(std::int64_t)faces.size();++fi)if(!selected_faces.count(fi))candidate.push_back(faces[(size_t)fi]);
    py::list correspondence;py::list centers_out;std::int64_t replacement_count=0;
    for(const auto& patch:patches){
        centers_out.append(patch.center);
        for(const auto& face:patch.faces){
            const auto new_index=(std::int64_t)candidate.size();candidate.push_back(face);++replacement_count;
            const Point new_centroid=mul(add(add(points[(size_t)face[0]],points[(size_t)face[1]]),points[(size_t)face[2]]),1./3.);
            std::int64_t best_face=patch.incident.front();double best_distance=INFINITY;
            for(const auto old_index:patch.incident){const auto& old=faces[(size_t)old_index];const Point old_centroid=mul(add(add(points[(size_t)old[0]],points[(size_t)old[1]]),points[(size_t)old[2]]),1./3.);const double distance=norm(sub(new_centroid,old_centroid));if(distance<best_distance-1.e-15||(std::abs(distance-best_distance)<=1.e-15&&old_index<best_face)){best_distance=distance;best_face=old_index;}}
            correspondence.append(std::vector<std::int64_t>{best_face,new_index});
        }
    }
    py::dict out;out["schema"]="autotessell/native-tri-worst-fan-patch/v1";out["accepted"]=true;out["status"]="fan_patch_proposed";out["reason"]="closed_fan_retriangulation_proposed";out["candidate_vertices"]=point_list(points);out["candidate_faces"]=face_list(candidate);out["face_correspondence"]=correspondence;out["selected_centers"]=centers_out;out["removed_faces"]=(std::int64_t)selected_faces.size();out["replacement_faces"]=replacement_count;return out;
}

bool passes(const Metrics& m,double amin,double amax,double qmin){return m.invalid==0&&m.self_intersecting==0&&m.min_angle>=amin&&m.max_angle<=amax&&m.min_ratio>=qmin;}
py::list point_list(const std::vector<Point>& p){py::list out;for(const auto& x:p)out.append(std::vector<double>{x[0],x[1],x[2]});return out;}

py::dict repair_surface_quality(
 const py::array_t<double,py::array::c_style|py::array::forcecast>& points,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& triangles,
 const py::array_t<double,py::array::c_style|py::array::forcecast>& source_points,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& source_triangles,
 const py::array_t<std::uint8_t,py::array::c_style|py::array::forcecast>& locked_vertices,
 std::int64_t max_iterations,double minimum_angle,double maximum_angle,double minimum_mean_ratio){
    if(points.ndim()!=2||points.shape(1)!=3||triangles.ndim()!=2||triangles.shape(1)!=3||source_points.ndim()!=2||source_points.shape(1)!=3||source_triangles.ndim()!=2||source_triangles.shape(1)!=3||locked_vertices.ndim()!=1||locked_vertices.size()!=points.shape(0))return refusal("repair_input_shape_invalid");
    if(max_iterations<0||!std::isfinite(minimum_angle)||!std::isfinite(maximum_angle)||!std::isfinite(minimum_mean_ratio)||minimum_angle<0||maximum_angle>180||minimum_angle>=maximum_angle||minimum_mean_ratio<=0)return refusal("repair_parameters_invalid");
    std::vector<Point> working,support;working.reserve((size_t)points.shape(0));support.reserve((size_t)source_points.shape(0));const auto* pd=points.data();const auto* sd=source_points.data();
    for(py::ssize_t i=0;i<points.shape(0);++i){Point x{pd[3U*(size_t)i],pd[3U*(size_t)i+1U],pd[3U*(size_t)i+2U]};if(!finite_point(x))return refusal("nonfinite_repair_point");working.push_back(x);}
    for(py::ssize_t i=0;i<source_points.shape(0);++i){Point x{sd[3U*(size_t)i],sd[3U*(size_t)i+1U],sd[3U*(size_t)i+2U]};if(!finite_point(x))return refusal("nonfinite_source_point");support.push_back(x);}
    std::vector<Face> faces,support_faces;faces.reserve((size_t)triangles.shape(0));support_faces.reserve((size_t)source_triangles.shape(0));const auto* fd=triangles.data();const auto* sfd=source_triangles.data();
    for(py::ssize_t i=0;i<triangles.shape(0);++i){Face f{fd[3U*(size_t)i],fd[3U*(size_t)i+1U],fd[3U*(size_t)i+2U]};for(auto id:f)if(id<0||id>=points.shape(0))return refusal("repair_face_index_invalid");faces.push_back(f);}
    for(py::ssize_t i=0;i<source_triangles.shape(0);++i){Face f{sfd[3U*(size_t)i],sfd[3U*(size_t)i+1U],sfd[3U*(size_t)i+2U]};for(auto id:f)if(id<0||id>=source_points.shape(0))return refusal("repair_source_face_index_invalid");support_faces.push_back(f);}
    const auto topo=audit(working,faces);if(!topo.valid||faces.empty()||support_faces.empty())return refusal("repair_input_topology_invalid");
    std::vector<bool> locked((size_t)locked_vertices.size(),false);const auto* ld=locked_vertices.data();for(py::ssize_t i=0;i<locked_vertices.size();++i)locked[(size_t)i]=ld[i]!=0;
    std::vector<std::set<std::int64_t>> neighbours(working.size());std::vector<std::vector<std::int64_t>> incident(working.size());
    for(size_t fi=0;fi<faces.size();++fi)for(size_t li=0;li<3;++li){const auto v=faces[fi][li];incident[(size_t)v].push_back((std::int64_t)fi);for(size_t oi=0;oi<3;++oi)if(oi!=li)neighbours[(size_t)v].insert(faces[fi][oi]);}
    Metrics before=measure(working,faces,support,support_faces);const Metrics initial=before;py::list receipts,snapshots;std::set<std::int64_t> changed;std::int64_t moves=0,attempts=0;std::string stop="operation_budget_exhausted";
    for(std::int64_t iteration=0;iteration<max_iterations;++iteration){
        std::int64_t worst=-1,partner=-1;
        if(before.self_intersecting>0){
            const auto pair=first_intersection(working,faces);
            worst=pair.first;partner=pair.second;
        }
        if(worst<0){
            for(std::int64_t fi=0;fi<(std::int64_t)faces.size();++fi){
                const auto& m=before.faces[(size_t)fi];
                if(m.valid&&m.min_angle>=minimum_angle&&m.max_angle<=maximum_angle&&m.mean_ratio>=minimum_mean_ratio)continue;
                if(worst<0){worst=fi;continue;}
                const auto& a=before.faces[(size_t)worst];
                const std::array<double,4> ak{a.min_angle,-a.max_angle,a.mean_ratio,-a.edge_aspect};
                const std::array<double,4> bk{m.min_angle,-m.max_angle,m.mean_ratio,-m.edge_aspect};
                if(bk<ak)worst=fi;
            }
        }
        if(worst<0){stop="quality_gates_passed";break;}
        std::vector<std::int64_t> candidates{faces[(size_t)worst][0],faces[(size_t)worst][1],faces[(size_t)worst][2]};
        if(partner>=0)for(const auto vertex:faces[(size_t)partner])candidates.push_back(vertex);
        std::sort(candidates.begin(),candidates.end());
        candidates.erase(std::unique(candidates.begin(),candidates.end()),candidates.end());
        bool moved=false;const auto old_tuple=tuple_of(before);
        if(partner>=0){
            const auto directions=collision_directions(working,faces[(size_t)worst],faces[(size_t)partner]);const double scale=pair_scale(working,faces[(size_t)worst],faces[(size_t)partner]);
            bool have_best=false;std::vector<Point> best_candidate;Metrics best_after{};std::array<double,8> best_tuple{};py::dict best_receipt;std::int64_t best_vertex=-1;
            for(const auto vertex:candidates){
                py::dict base;base["iteration"]=iteration;base["face_index"]=worst;base["vertex_index"]=vertex;base["operator"]="collision_pair_separation";base["tuple_before"]=std::vector<double>(old_tuple.begin(),old_tuple.end());base["collision_partner_face"]=partner;
                if(locked[(size_t)vertex]){py::dict x=copy_dict(base);x["accepted"]=false;x["reason"]="locked_feature_vertex";receipts.append(x);continue;}
                for(const auto& [direction_name,direction]:directions){
                    for(const double fraction:{.2,.3,.4,.5,.7,.9}){
                        py::dict x=copy_dict(base);x["direction"]=direction_name;x["step_fraction"]=fraction;
                        const Point raw=add(working[(size_t)vertex],mul(direction,scale*fraction));
                        Point projected{};double support_distance=0.;if(!source_projection(raw,support,support_faces,projected,support_distance)){x["accepted"]=false;x["reason"]="source_support_projection_failed";receipts.append(x);continue;}
                        if(!inside_source_envelope(projected,support)){x["accepted"]=false;x["reason"]="projected_source_envelope_failed";receipts.append(x);continue;}
                        auto candidate=working;candidate[(size_t)vertex]=projected;
                        if(!orientation_preserved(working,candidate,faces,incident,vertex)){x["accepted"]=false;x["reason"]="orientation_preservation_failed";receipts.append(x);continue;}
                        const Metrics after=measure(candidate,faces,support,support_faces);const auto after_tuple=tuple_of(after);x["tuple_after"]=std::vector<double>(after_tuple.begin(),after_tuple.end());x["source_support_projection"]=true;x["source_support_error"]=support_distance;
                        if(after.invalid!=0||after.self_intersecting>=before.self_intersecting){x["accepted"]=false;x["reason"]="collision_not_reduced";receipts.append(x);continue;}
                        x["accepted"]=false;x["reason"]="collision_candidate_not_best";receipts.append(x);
                        if(!have_best||improves(best_tuple,after_tuple)){have_best=true;best_candidate=std::move(candidate);best_after=after;best_tuple=after_tuple;best_receipt=copy_dict(x);best_vertex=vertex;}
                    }
                }
            }
            if(have_best){
                best_receipt["accepted"]=true;best_receipt["reason"]="strict_collision_reduction";receipts.append(best_receipt);working=std::move(best_candidate);before=best_after;++moves;changed.insert(best_vertex);snapshots.append(point_list(working));moved=true;
            }
        }else{
            for(const auto vertex:candidates){
                py::dict base;base["iteration"]=iteration;base["face_index"]=worst;base["vertex_index"]=vertex;base["operator"]="tangential_relocation";base["tuple_before"]=std::vector<double>(old_tuple.begin(),old_tuple.end());
                if(locked[(size_t)vertex]){py::dict x=copy_dict(base);x["accepted"]=false;x["reason"]="locked_feature_vertex";receipts.append(x);continue;}
                ++attempts;Point centroid{},normal{};double weight=0.;for(const auto fi:incident[(size_t)vertex]){const auto& f=faces[(size_t)fi];const Point a=working[(size_t)f[0]],b=working[(size_t)f[1]],c=working[(size_t)f[2]],nv=cross(sub(b,a),sub(c,a));const double area2=norm(nv);if(area2<=EPS)continue;const double area=.5*area2;centroid=add(centroid,mul(add(add(a,b),c),area/3.));normal=add(normal,nv);weight+=area;}
                if(weight<=EPS||norm(normal)<=EPS){py::dict x=copy_dict(base);x["accepted"]=false;x["reason"]="one_ring_degenerate";receipts.append(x);continue;}centroid=mul(centroid,1./weight);const Point nu=unit(normal),disp=sub(centroid,working[(size_t)vertex]);const Point tang=sub(disp,mul(nu,dot(disp,nu)));
                for(int back=0;back<12;++back){const double beta=std::ldexp(.5,-back);const Point raw=add(working[(size_t)vertex],mul(tang,beta));Point projected{};double support_distance=0.;if(!source_projection(raw,support,support_faces,projected,support_distance)){py::dict x=copy_dict(base);x["beta"]=beta;x["accepted"]=false;x["reason"]="source_support_projection_failed";receipts.append(x);continue;}
                    auto candidate=working;candidate[(size_t)vertex]=projected;
                    if(!orientation_preserved(working,candidate,faces,incident,vertex)){py::dict x=copy_dict(base);x["beta"]=beta;x["accepted"]=false;x["reason"]="orientation_preservation_failed";receipts.append(x);continue;}
                    const Metrics after=measure(candidate,faces,support,support_faces);const auto after_tuple=tuple_of(after);py::dict x=copy_dict(base);x["beta"]=beta;x["tuple_after"]=std::vector<double>(after_tuple.begin(),after_tuple.end());x["source_support_projection"]=true;
                    if(!improves(old_tuple,after_tuple)){x["accepted"]=false;x["reason"]="quality_tuple_not_improved";receipts.append(x);continue;}
                    x["accepted"]=true;x["reason"]="strict_quality_tuple_improved";x["source_support_error"]=support_distance;receipts.append(x);working=std::move(candidate);before=after;++moves;changed.insert(vertex);snapshots.append(point_list(working));moved=true;break;}
                if(moved)break;
            }
        }
        if(!moved){stop="no_strict_local_improvement";break;}
    }
    const auto final_tuple=tuple_of(before);py::dict out;out["schema"]="autotessell/native-tri-quality-repair/v1";out["accepted"]=passes(before,minimum_angle,maximum_angle,minimum_mean_ratio);out["status"]=out["accepted"].cast<bool>()?"quality_repair_ready":"quality_gate_refused";out["reason"]=out["accepted"].cast<bool>()?(moves?"quality_repair_committed":"already_quality_ready"):stop;out["candidate_vertices"]=point_list(working);out["accepted_snapshots"]=snapshots;out["faces_unchanged"]=true;out["topology_input_valid"]=true;out["self_intersection_checked"]=true;out["before"]=metrics_dict(initial);out["after"]=metrics_dict(before);out["accepted_moves"]=moves;out["attempted_candidates"]=attempts;out["locked_vertex_count"]=(std::int64_t)std::count(locked.begin(),locked.end(),true);out["changed_vertex_count"]=(std::int64_t)changed.size();out["tuple_after"]=std::vector<double>(final_tuple.begin(),final_tuple.end());out["receipts"]=receipts;return out;
}
PYBIND11_MODULE(native_tri_quality_repair,m){m.doc()="Default-off C++23 constrained Native Tri surface quality repair";m.def("repair_surface_quality",&repair_surface_quality,py::arg("points"),py::arg("triangles"),py::arg("source_points"),py::arg("source_triangles"),py::arg("locked_vertices"),py::arg("max_iterations")=96,py::arg("minimum_angle")=10.,py::arg("maximum_angle")=150.,py::arg("minimum_mean_ratio")=.05);
    m.def("admit_surface_edit",&admit_surface_edit,py::arg("before_points"),py::arg("before_triangles"),py::arg("after_points"),py::arg("after_triangles"),py::arg("source_points"),py::arg("source_triangles"));
    m.def("propose_worst_fan_patch",&propose_worst_fan_patch,py::arg("points"),py::arg("triangles"),py::arg("max_centers")=2,py::arg("minimum_valence")=16);}
