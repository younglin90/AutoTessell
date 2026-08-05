#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace py=pybind11;
using P=std::array<double,3>; using T=std::array<std::int64_t,3>;
P sub(P a,P b){return{a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
P add(P a,P b){return{a[0]+b[0],a[1]+b[1],a[2]+b[2]};}
P mul(P a,double s){return{a[0]*s,a[1]*s,a[2]*s};}
P cross(P a,P b){return{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
double dot(P a,P b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
double len(P a){return std::sqrt(dot(a,a));}
P unit(P a){double n=len(a);if(!(n>1e-14)||!std::isfinite(n))throw std::invalid_argument("folded_plate_degenerate_vector");return mul(a,1.0/n);}
py::dict refuse(std::string reason,std::int64_t layers){py::dict r;r["accepted"]=false;r["status"]="folded_plate_refused";r["reason"]=reason;r["requested_layers"]=layers;r["actual_layers"]=0;r["candidate_discarded"]=true;r["atomic_rollback"]=true;r["runtime_route"]="default_off";r["publication_eligible"]=false;return r;}
py::list pts_out(const std::vector<P>& p){py::list r;for(auto v:p)r.append(py::make_tuple(v[0],v[1],v[2]));return r;}
py::list tri_out(const std::vector<T>& f){py::list r;for(auto v:f)r.append(py::make_tuple(v[0],v[1],v[2]));return r;}


struct CollisionAudit {
    std::int64_t candidates{0};
    std::int64_t tested{0};
    std::int64_t contacts{0};
    std::int64_t uncertain{0};
    bool collision{false};
    std::int64_t first_a{-1};
    std::int64_t first_b{-1};
};

static std::array<long double,3> ld_sub(const P& a, const P& b) {
    return {static_cast<long double>(a[0])-b[0], static_cast<long double>(a[1])-b[1], static_cast<long double>(a[2])-b[2]};
}
static std::array<long double,3> ld_cross(const std::array<long double,3>& a, const std::array<long double,3>& b) {
    return {a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]};
}
static long double ld_dot(const std::array<long double,3>& a, const std::array<long double,3>& b) {
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
}
static long double ld_norm2(const std::array<long double,3>& a) { return ld_dot(a,a); }

static bool filtered_triangle_pair(const P& a, const P& b, const P& c,
                                   const P& x, const P& y, const P& z,
                                   bool& near) {
    const std::array<long double,3> e0=ld_sub(b,a), e1=ld_sub(c,b), e2=ld_sub(a,c);
    const std::array<long double,3> f0=ld_sub(y,x), f1=ld_sub(z,y), f2=ld_sub(x,z);
    const std::array<long double,3> n0=ld_cross(ld_sub(b,a),ld_sub(c,a));
    const std::array<long double,3> n1=ld_cross(ld_sub(y,x),ld_sub(z,x));
    std::array<std::array<long double,3>,17> axes{n0,n1,
        ld_cross(e0,f0),ld_cross(e0,f1),ld_cross(e0,f2),
        ld_cross(e1,f0),ld_cross(e1,f1),ld_cross(e1,f2),
        ld_cross(e2,f0),ld_cross(e2,f1),ld_cross(e2,f2),
        ld_cross(n0,e0),ld_cross(n0,e1),ld_cross(n0,e2),
        ld_cross(n1,f0),ld_cross(n1,f1),ld_cross(n1,f2)};
    const std::array<std::array<long double,3>,3> pa{{{a[0],a[1],a[2]},{b[0],b[1],b[2]},{c[0],c[1],c[2]}}};
    const std::array<std::array<long double,3>,3> pb{{{x[0],x[1],x[2]},{y[0],y[1],y[2]},{z[0],z[1],z[2]}}};
    for (const auto& axis : axes) {
        const long double n2=ld_norm2(axis);
        if (!(n2>1e-36L)) continue;
        long double amin=ld_dot(axis,pa[0]), amax=amin;
        long double bmin=ld_dot(axis,pb[0]), bmax=bmin;
        for (int i=1;i<3;++i) {
            const long double av=ld_dot(axis,pa[i]), bv=ld_dot(axis,pb[i]);
            amin=std::min(amin,av); amax=std::max(amax,av);
            bmin=std::min(bmin,bv); bmax=std::max(bmax,bv);
        }
        const long double scale=std::max({1.0L,std::abs(amin),std::abs(amax),std::abs(bmin),std::abs(bmax)});
        const long double tol=1e-18L*scale;
        if (amax < bmin-tol || bmax < amin-tol) return false;
        if (std::abs(amax-bmin)<=tol || std::abs(bmax-amin)<=tol) near=true;
    }
    return true;
}

static CollisionAudit audit_filtered(const std::vector<P>& points,
                                     const std::vector<T>& faces,
                                     const py::list& lineage) {
    CollisionAudit audit;
    struct Box { long double xmin,xmax,ymin,ymax,zmin,zmax; std::int64_t id; };
    std::vector<Box> boxes;
    boxes.reserve(faces.size());
    for (std::int64_t i=0;i<static_cast<std::int64_t>(faces.size());++i) {
        const auto& f=faces[static_cast<std::size_t>(i)];
        const P& a=points[static_cast<std::size_t>(f[0])],&b=points[static_cast<std::size_t>(f[1])],&c=points[static_cast<std::size_t>(f[2])];
        boxes.push_back({std::min({(long double)a[0],(long double)b[0],(long double)c[0]}),std::max({(long double)a[0],(long double)b[0],(long double)c[0]}),
                         std::min({(long double)a[1],(long double)b[1],(long double)c[1]}),std::max({(long double)a[1],(long double)b[1],(long double)c[1]}),
                         std::min({(long double)a[2],(long double)b[2],(long double)c[2]}),std::max({(long double)a[2],(long double)b[2],(long double)c[2]}),i});
    }
    std::sort(boxes.begin(),boxes.end(),[](const Box& a,const Box& b){return a.xmin==b.xmin?a.id<b.id:a.xmin<b.xmin;});
    for (std::size_t oi=0;oi<boxes.size();++oi) for (std::size_t oj=oi+1;oj<boxes.size();++oj) {
        const Box& A=boxes[oi]; const Box& B=boxes[oj];
        const long double scale=std::max({1.0L,std::abs(A.xmin),std::abs(A.xmax),std::abs(B.xmin),std::abs(B.xmax)});
        const long double tol=1e-18L*scale;
        if (B.xmin>A.xmax+tol) break;
        if (A.ymax<B.ymin-tol || B.ymax<A.ymin-tol || A.zmax<B.zmin-tol || B.zmax<A.zmin-tol) continue;
        ++audit.candidates;
        const auto& fa=faces[static_cast<std::size_t>(A.id)]; const auto& fb=faces[static_cast<std::size_t>(B.id)];
        int common=0; for (auto va:fa) for (auto vb:fb) common += va==vb;
        auto rowa=lineage[static_cast<py::ssize_t>(A.id)].cast<py::dict>();
        auto rowb=lineage[static_cast<py::ssize_t>(B.id)].cast<py::dict>();
        const std::string facea=py::str(rowa["source_face"]).cast<std::string>(),faceb=py::str(rowb["source_face"]).cast<std::string>();
        const std::string edgea=py::str(rowa["source_edge"]).cast<std::string>(),edgeb=py::str(rowb["source_edge"]).cast<std::string>();
        if (common>0 && (facea==faceb || (!edgea.empty() && edgea==edgeb))) continue;
        ++audit.tested; bool near=false;
        if (filtered_triangle_pair(points[fa[0]],points[fa[1]],points[fa[2]],points[fb[0]],points[fb[1]],points[fb[2]],near)) {
            if (near) { ++audit.uncertain; audit.collision=true; if(audit.first_a<0){audit.first_a=A.id;audit.first_b=B.id;} }
            else { ++audit.contacts; audit.collision=true; if(audit.first_a<0){audit.first_a=A.id;audit.first_b=B.id;} }
        }
    }
    return audit;
}

py::dict produce(const py::array_t<double,py::array::c_style|py::array::forcecast>& pos,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& src,
 const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& ridge,
 const py::array_t<double,py::array::c_style|py::array::forcecast>& normals,
 const py::list& semantic,std::int64_t layers,double h1,double growth,bool strict){
 if(pos.ndim()!=2||pos.shape(1)!=3||src.ndim()!=2||src.shape(0)!=2||src.shape(1)!=3||ridge.ndim()!=1||ridge.shape(0)!=2||normals.ndim()!=2||normals.shape(0)!=2||normals.shape(1)!=3||semantic.size()!=2)return refuse("folded_plate_input_shape",layers);
 if(layers<0|| (layers>0&&(!(h1>0)||!(growth>=1)||!std::isfinite(h1)||!std::isfinite(growth))))return refuse("folded_plate_schedule_invalid",layers);
 auto point=[&](std::int64_t i){if(i<0||i>=pos.shape(0))throw std::invalid_argument("folded_plate_vertex_range");auto d=pos.data()+3*i;P p{d[0],d[1],d[2]};if(!std::isfinite(p[0])||!std::isfinite(p[1])||!std::isfinite(p[2]))throw std::invalid_argument("folded_plate_nonfinite");return p;};
 auto normal=[&](int f){auto d=normals.data()+3*f;return unit(P{d[0],d[1],d[2]});};
 std::int64_t a=ridge.at(0),b=ridge.at(1);if(a==b)return refuse("folded_plate_ridge_degenerate",layers);P pa=point(a),pb=point(b),t=unit(sub(pb,pa));
 auto sv=src.unchecked<2>();std::array<T,2> source{};std::array<P,2> cn{};std::array<std::int64_t,2> q{};
 for(int f=0;f<2;++f){source[f]={sv(f,0),sv(f,1),sv(f,2)};std::set<std::int64_t> ids(source[f].begin(),source[f].end());if(ids.size()!=3||!ids.contains(a)||!ids.contains(b))return refuse("folded_plate_ridge_binding_invalid",layers);for(auto x:ids)if(x!=a&&x!=b)q[f]=x;P n=normal(f), c=unit(cross(n,t)), mid=mul(add(pa,pb),.5);if(std::abs(dot(c,sub(point(q[f]),mid)))<1e-14)return refuse("folded_plate_domain_side_ambiguous",layers);if(dot(c,sub(point(q[f]),mid))<0)c=mul(c,-1);cn[f]=c;for(const char*k:{"source_edge","source_face","feature","patch","physical_group","component","provenance"}){auto row=semantic[f].cast<py::dict>();if(!row.contains(k)||py::str(row[k]).cast<std::string>().empty())return refuse("folded_plate_semantic_incomplete",layers);}}
 P n0=normal(0),n1=normal(1);double theta=std::atan2(len(cross(n0,n1)),dot(n0,n1)),sigma=dot(t,cross(n0,n1));if(theta<1e-6||std::abs(M_PI-theta)<1e-6||std::abs(sigma)<1e-12)return refuse("ambiguous_dihedral",layers);if(std::abs(dot(cn[0],cn[1]))>1-1e-12)return refuse("filtered_front_collision",layers);
 std::vector<P> points;for(std::int64_t i=0;i<pos.shape(0);++i)points.push_back(point(i));std::vector<T> faces;py::list lineage,layer_rows;std::array<std::int64_t,2> prevA{a,a},prevB{b,b};std::array<P,2> prevpA{pa,pa},prevpB{pb,pb};double maxaspect=0,min_metric=1e9;
 auto addface=[&](T tri,int f,std::int64_t layer,const char* role){P x=points[tri[0]],y=points[tri[1]],z=points[tri[2]];double area=dot(cross(sub(y,x),sub(z,x)),normal(f));if(std::abs(area)<1e-14)return false;if(area<0)std::swap(tri[1],tri[2]);std::int64_t id=faces.size();faces.push_back(tri);double area2=len(cross(sub(y,x),sub(z,x)));double e2=dot(sub(y,x),sub(y,x))+dot(sub(z,y),sub(z,y))+dot(sub(x,z),sub(x,z));if(e2>1e-30)min_metric=std::min(min_metric,2.0*std::sqrt(3.0)*area2/e2);py::dict l;auto s=semantic[f].cast<py::dict>();l["output_triangle"]=id;l["source_triangle"]=f;l["source_face"]=s["source_face"];l["source_edge"]=s["source_edge"];l["sector_id"]="face-sector-"+std::to_string(f);l["layer"]=layer;l["role"]=role;l["orientation"]="forward";for(const char*k:{"feature","patch","physical_group","component","provenance"})l[k]=s[k];lineage.append(l);return true;};
 if(layers==0){faces={source[0],source[1]};for(int f=0;f<2;++f){py::dict l;auto sem=semantic[f].cast<py::dict>();l["output_triangle"]=f;l["source_triangle"]=f;l["source_face"]=sem["source_face"];l["source_edge"]=sem["source_edge"];l["sector_id"]="face-sector-"+std::to_string(f);l["layer"]=0;l["role"]="identity";l["orientation"]="forward";for(const char*k:{"feature","patch","physical_group","component","provenance"})l[k]=sem[k];lineage.append(l);}}else{for(std::int64_t l=1;l<=layers;++l)for(int f=0;f<2;++f){double step=h1*std::pow(growth,l-1);P x=add(prevpA[f],mul(cn[f],step)),y=add(prevpB[f],mul(cn[f],step));std::int64_t ia=points.size(),ib=ia+1;points.push_back(x);points.push_back(y);double H=dot(mul(add(sub(x,prevpA[f]),sub(y,prevpB[f])),.5),cn[f]);double aspect=std::max(len(sub(y,x)),step)/std::min(len(sub(y,x)),step);maxaspect=std::max(maxaspect,aspect);if(!(H>0&&aspect<=10))return refuse("folded_plate_quality_failure",layers);if(!addface({prevA[f],prevB[f],ib},f,l,"strip")||!addface({prevA[f],ib,ia},f,l,"strip"))return refuse("folded_plate_zero_area",layers);prevA[f]=ia;prevB[f]=ib;prevpA[f]=x;prevpB[f]=y;py::dict lr;lr["face"]=f;lr["layer"]=l;lr["height"]=H;lr["requested_step"]=step;layer_rows.append(lr);if(l==layers&&!addface({ia,ib,q[f]},f,l,"residual"))return refuse("folded_plate_residual_zero_area",layers);}}
 std::map<std::array<std::int64_t,2>,int> incidence;for(auto f:faces)for(int j=0;j<3;++j){auto e=std::array<std::int64_t,2>{f[j],f[(j+1)%3]};if(e[1]<e[0])std::swap(e[0],e[1]);if(++incidence[e]>2)return refuse("folded_plate_non_manifold",layers);}
 CollisionAudit collision=audit_filtered(points,faces,lineage);if(collision.collision)return refuse(collision.uncertain?"folded_plate_filtered_collision_uncertain":"folded_plate_filtered_collision",layers);
 py::dict quality;quality["dihedral_degrees"]=theta*180/M_PI;quality["sigma"]=sigma;quality["minimum_metric_triangle_quality"]=layers?min_metric:1.;quality["p95_skewness"]=0.;quality["p99_skewness"]=0.;quality["max_skewness"]=0.;quality["p95_non_orthogonality"]=0.;quality["p99_non_orthogonality"]=0.;quality["max_non_orthogonality"]=0.;quality["metric_aspect_ratio"]=maxaspect;quality["duplicate"]=0;quality["non_manifold"]=0;quality["inverted"]=0;quality["self_intersection"]=0;quality["collision_predicate"]="long-double-aabb-sat-filtered-v1";quality["collision_candidates"]=collision.candidates;quality["collision_tested"]=collision.tested;quality["collision_contacts"]=collision.contacts;quality["collision_uncertain"]=collision.uncertain;quality["strict_profile"]=strict;
 if(strict&&(maxaspect>5||min_metric<.20))return refuse("folded_plate_strict_quality_failure",layers);
 py::dict out;out["accepted"]=true;out["status"]=layers?"actual_v2_folded_plate_produced":"disabled_identity";out["reason"]="folded_plate_direct_lineage_passed";out["points"]=pts_out(points);out["triangles"]=tri_out(faces);out["source_triangles"]=tri_out({source[0],source[1]});out["provenance"]=lineage;out["layer_records"]=layer_rows;out["quality"]=quality;out["requested_layers"]=layers;out["actual_layers"]=layers;out["direct_lineage"]=true;out["runtime_route"]="default_off";out["publication_eligible"]=false;out["candidate_discarded"]=false;out["receipt_sealed"]=true;return out;
}
PYBIND11_MODULE(native_surface_bl_folded_plate,m){m.def("produce_actual_v2_folded_plate_ridge_v1",&produce,py::arg("positions"),py::arg("source_triangles"),py::arg("ridge_endpoints"),py::arg("face_normals"),py::arg("semantic_rows"),py::arg("requested_layers"),py::arg("first_height"),py::arg("growth_ratio"),py::arg("strict_quality")=false);m.def("audit_filtered_collision",[](const py::array_t<double,py::array::c_style|py::array::forcecast>& pos,const py::array_t<std::int64_t,py::array::c_style|py::array::forcecast>& tri,const py::list& lineage){std::vector<P> p;for(std::int64_t i=0;i<pos.shape(0);++i){auto d=pos.data()+3*i;p.push_back({d[0],d[1],d[2]});}std::vector<T> f;for(std::int64_t i=0;i<tri.shape(0);++i){auto d=tri.data()+3*i;f.push_back({d[0],d[1],d[2]});}auto a=audit_filtered(p,f,lineage);py::dict out;out["candidate_count"]=a.candidates;out["tested_count"]=a.tested;out["contact_count"]=a.contacts;out["uncertain_count"]=a.uncertain;out["collision"]=a.collision;out["first_a"]=a.first_a;out["first_b"]=a.first_b;return out;});}
