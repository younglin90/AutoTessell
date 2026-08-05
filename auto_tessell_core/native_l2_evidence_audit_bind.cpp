// C++23 private content-addressed L2 evidence audit for all native products.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "native_volume_authority_bound_impl.hpp"
#include "native_tet_polymesh_persisted_reader.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <limits>
#include <regex>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace py=pybind11;
namespace {
struct SHA256{
 std::array<std::uint32_t,8> h{0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
 std::array<std::uint8_t,64> buf{};std::uint64_t bits=0;size_t used=0;
 static std::uint32_t r(std::uint32_t x,int n){return(x>>n)|(x<<(32-n));}
 void block(const std::uint8_t*p){static constexpr std::uint32_t k[64]={0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};std::uint32_t w[64];for(int i=0;i<16;++i)w[i]=(std::uint32_t(p[4*i])<<24)|(std::uint32_t(p[4*i+1])<<16)|(std::uint32_t(p[4*i+2])<<8)|p[4*i+3];for(int i=16;i<64;++i){auto s0=r(w[i-15],7)^r(w[i-15],18)^(w[i-15]>>3);auto s1=r(w[i-2],17)^r(w[i-2],19)^(w[i-2]>>10);w[i]=w[i-16]+s0+w[i-7]+s1;}std::uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],x=h[7];for(int i=0;i<64;++i){auto S1=r(e,6)^r(e,11)^r(e,25);auto ch=(e&f)^((~e)&g);auto t1=x+S1+ch+k[i]+w[i];auto S0=r(a,2)^r(a,13)^r(a,22);auto maj=(a&b)^(a&c)^(b&c);auto t2=S0+maj;x=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;}h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=x;}
 void update(const std::string&s){for(unsigned char c:s){buf[used++]=c;bits+=8;if(used==64){block(buf.data());used=0;}}}
 std::string finish(){buf[used++]=0x80;while(used!=56){if(used==64){block(buf.data());used=0;}buf[used++]=0;}for(int i=7;i>=0;--i)buf[used++]=static_cast<std::uint8_t>(bits>>(8*i));block(buf.data());std::ostringstream o;for(auto x:h)o<<std::hex<<std::setfill('0')<<std::setw(8)<<x;return o.str();}
};
std::string sha(const std::string&s){SHA256 x;x.update(s);return x.finish();}
struct P{double x{},y{},z{};};P sub(P a,P b){return{a.x-b.x,a.y-b.y,a.z-b.z};}P cross(P a,P b){return{a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}double dot(P a,P b){return a.x*b.x+a.y*b.y+a.z*b.z;}double norm(P a){return std::sqrt(dot(a,a));}
std::string txt(const py::dict&d,const char*k){return d.contains(k)&&!d[k].is_none()?py::str(d[k]).cast<std::string>():std::string{};}bool flag(const py::dict&d,const char*k){return d.contains(k)&&!d[k].is_none()&&d[k].cast<bool>();}bool h64(const std::string&s){if(s.size()!=64)return false;return std::all_of(s.begin(),s.end(),[](char c){return(c>='0'&&c<='9')||(c>='a'&&c<='f');});}
py::dict bad(const char*r){py::dict d;d["accepted"]=false;d["status"]="native_l2_evidence_audit_rollback";d["reason"]=r;d["runtime_route"]="default_off";d["publication_eligible"]=false;d["candidate_discarded"]=true;d["atomic_rollback"]=true;return d;}
std::vector<P>points(const py::sequence&o){std::vector<P>v;for(py::handle h:o){auto s=py::reinterpret_borrow<py::sequence>(h);if(py::len(s)!=3)throw std::invalid_argument("point_width");v.push_back({py::cast<double>(s[0]),py::cast<double>(s[1]),py::cast<double>(s[2])});}return v;}
std::vector<std::vector<int>> rows(const py::sequence&o){std::vector<std::vector<int>>v;for(py::handle h:o){auto s=py::reinterpret_borrow<py::sequence>(h);std::vector<int>x;for(py::handle z:s)x.push_back(py::cast<int>(z));v.push_back(std::move(x));}return v;}
std::string key(std::vector<int>x){std::sort(x.begin(),x.end());std::string s;for(int i:x)s+=std::to_string(i)+",";return s;}
double p95(std::vector<double>x){if(x.empty())return 0.;std::sort(x.begin(),x.end());return x[std::min(x.size()-1,static_cast<size_t>(std::ceil(.95*x.size())-1))];}

struct Q2{double x{},y{};};
double cross2(Q2 a,Q2 b,Q2 c){return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);}
bool between2(double a,double b,double x){return x>=std::min(a,b)-1e-10&&x<=std::max(a,b)+1e-10;}
Q2 project2(P p,int axis){return axis==0?Q2{p.y,p.z}:axis==1?Q2{p.x,p.z}:Q2{p.x,p.y};}
bool seg2(Q2 a,Q2 b,Q2 c,Q2 d){
    auto o1=cross2(a,b,c),o2=cross2(a,b,d),o3=cross2(c,d,a),o4=cross2(c,d,b);
    if(((o1>1e-10&&o2<-1e-10)||(o1<-1e-10&&o2>1e-10))&&((o3>1e-10&&o4<-1e-10)||(o3<-1e-10&&o4>1e-10)))return true;
    return (std::abs(o1)<=1e-10&&between2(a.x,b.x,c.x)&&between2(a.y,b.y,c.y))||
           (std::abs(o2)<=1e-10&&between2(a.x,b.x,d.x)&&between2(a.y,b.y,d.y))||
           (std::abs(o3)<=1e-10&&between2(c.x,d.x,a.x)&&between2(c.y,d.y,a.y))||
           (std::abs(o4)<=1e-10&&between2(c.x,d.x,b.x)&&between2(c.y,d.y,b.y));
}
bool inside2(Q2 p,Q2 a,Q2 b,Q2 c){
    const auto u=cross2(a,b,p),v=cross2(b,c,p),w=cross2(c,a,p);
    return (u>=-1e-10&&v>=-1e-10&&w>=-1e-10)||(u<=1e-10&&v<=1e-10&&w<=1e-10);
}
bool segment_triangle_hit(P p0,P p1,P a,P b,P c){
    const P d=sub(p1,p0),e1=sub(b,a),e2=sub(c,a),h=cross(d,e2);
    const double det=dot(e1,h);
    if(std::abs(det)<=1e-12)return false;
    const double inv=1./det;const P q=sub(p0,a);
    const double u=inv*dot(q,h);if(u<-1e-10||u>1.+1e-10)return false;
    const P r=cross(q,e1);const double v=inv*dot(d,r);if(v<-1e-10||u+v>1.+1e-10)return false;
    const double t=inv*dot(e2,r);return t>=-1e-10&&t<=1.+1e-10;
}
bool triangles_intersect(const std::vector<P>&p,const std::vector<int>&a,const std::vector<int>&b){
    std::array<P,3>A{p[a[0]],p[a[1]],p[a[2]]},B{p[b[0]],p[b[1]],p[b[2]]};
    const P na=cross(sub(A[1],A[0]),sub(A[2],A[0])),nb=cross(sub(B[1],B[0]),sub(B[2],B[0]));
    const P parallel=cross(na,nb);
    if(norm(parallel)<=1e-12){
        if(std::abs(dot(na,sub(B[0],A[0])))>1e-10)return false;
        int axis=0;if(std::abs(na.y)>std::abs(na.x))axis=1;if(std::abs(na.z)>std::max(std::abs(na.x),std::abs(na.y)))axis=2;
        std::array<Q2,3>aa{project2(A[0],axis),project2(A[1],axis),project2(A[2],axis)};
        std::array<Q2,3>bb{project2(B[0],axis),project2(B[1],axis),project2(B[2],axis)};
        for(int i=0;i<3;++i)for(int j=0;j<3;++j)if(seg2(aa[i],aa[(i+1)%3],bb[j],bb[(j+1)%3]))return true;
        return inside2(aa[0],bb[0],bb[1],bb[2])||inside2(bb[0],aa[0],aa[1],aa[2]);
    }
    for(int i=0;i<3;++i)if(segment_triangle_hit(A[i],A[(i+1)%3],B[0],B[1],B[2]))return true;
    for(int i=0;i<3;++i)if(segment_triangle_hit(B[i],B[(i+1)%3],A[0],A[1],A[2]))return true;
    return false;
}
struct M{int duplicate=0,nonmanifold=0,inverted=0,degenerate=0,self_intersection=0;double maxskew=0,p95skew=0,maxaspect=0,p95aspect=0,maxno=0,p95no=0,minjac=1e300;std::set<int>boundary;};
M surface(const std::vector<P>&p,const std::vector<std::vector<int>>&tr,const std::vector<std::vector<int>>&qu){M m;std::vector<std::vector<int>>fs=tr;fs.insert(fs.end(),qu.begin(),qu.end());std::vector<int>kind;for(size_t i=0;i<tr.size();++i)kind.push_back(3);for(size_t i=0;i<qu.size();++i)kind.push_back(4);std::set<std::string>seen;std::map<std::string,std::vector<std::pair<int,int>>>edges;std::vector<P>ns(fs.size());std::vector<double>sk,ar,no;for(size_t i=0;i<fs.size();++i){auto c=fs[i];bool ok=c.size()==static_cast<size_t>(kind[i]);for(int id:c)if(id<0||static_cast<size_t>(id)>=p.size())ok=false;std::set<int>u(c.begin(),c.end());if(!ok||u.size()!=c.size()){++m.degenerate;continue;}std::string fk=std::to_string(kind[i])+":"+key(c);if(!seen.insert(fk).second)++m.duplicate;P n{};if(kind[i]==3)n=cross(sub(p[c[1]],p[c[0]]),sub(p[c[2]],p[c[0]]));else{P a=cross(sub(p[c[1]],p[c[0]]),sub(p[c[2]],p[c[0]])),b=cross(sub(p[c[2]],p[c[0]]),sub(p[c[3]],p[c[0]]));n={a.x+b.x,a.y+b.y,a.z+b.z};}double area=.5*norm(n);if(area<=1e-14){++m.degenerate;continue;}ns[i]=n;std::vector<double>le;for(size_t k=0;k<c.size();++k)le.push_back(norm(sub(p[c[(k+1)%c.size()]],p[c[k]])));double mn=*std::min_element(le.begin(),le.end()),mx=*std::max_element(le.begin(),le.end());if(mn<=1e-14){++m.degenerate;continue;}m.maxaspect=std::max(m.maxaspect,mx/mn);ar.push_back(mx/mn);m.minjac=std::min(m.minjac,area/(mx*mx));for(size_t k=0;k<c.size();++k){int a=c[k],b=c[(k+1)%c.size()];if(a>b)std::swap(a,b);edges[std::to_string(a)+","+std::to_string(b)].push_back({static_cast<int>(i),c[k]<c[(k+1)%c.size()]?1:-1});P e1=sub(p[c[(k+c.size()-1)%c.size()]],p[c[k]]),e2=sub(p[c[(k+1)%c.size()]],p[c[k]]);double den=norm(e1)*norm(e2);if(kind[i]==3)sk.push_back(.5*(1.-mn/mx));else if(den>1e-14)sk.push_back(std::abs(std::acos(std::max(-1.,std::min(1.,dot(e1,e2)/den)))*180./3.141592653589793-90.)/90.);}}for(const auto&[e,r]:edges){if(r.size()>2)m.nonmanifold++;if(r.size()==1)m.boundary.insert(r[0].first);if(r.size()==2&&r[0].second==r[1].second)m.inverted++;if(r.size()==2){double den=norm(ns[r[0].first])*norm(ns[r[1].first]);no.push_back(den>1e-14?std::acos(std::min(1.,std::abs(dot(ns[r[0].first],ns[r[1].first]))/den))*180./3.141592653589793:90.);}}for(size_t i=0;i<fs.size();++i)for(size_t j=i+1;j<fs.size();++j){std::set<int>a(fs[i].begin(),fs[i].end()),b(fs[j].begin(),fs[j].end());bool share=false;for(int x:a)if(b.count(x))share=true;if(share)continue;P amin{1e300,1e300,1e300},amax{-1e300,-1e300,-1e300},bmin{1e300,1e300,1e300},bmax{-1e300,-1e300,-1e300};for(int id:fs[i]){auto z=p[id];amin.x=std::min(amin.x,z.x);amin.y=std::min(amin.y,z.y);amin.z=std::min(amin.z,z.z);amax.x=std::max(amax.x,z.x);amax.y=std::max(amax.y,z.y);amax.z=std::max(amax.z,z.z);}for(int id:fs[j]){auto z=p[id];bmin.x=std::min(bmin.x,z.x);bmin.y=std::min(bmin.y,z.y);bmin.z=std::min(bmin.z,z.z);bmax.x=std::max(bmax.x,z.x);bmax.y=std::max(bmax.y,z.y);bmax.z=std::max(bmax.z,z.z);}if(triangles_intersect(p,fs[i],fs[j]))m.self_intersection++;}m.maxskew=sk.empty()?0:*std::max_element(sk.begin(),sk.end());m.p95skew=p95(sk);m.p95aspect=p95(ar);m.maxno=no.empty()?0:*std::max_element(no.begin(),no.end());m.p95no=p95(no);return m;}
double cell_volume(const std::vector<P>&p,const std::vector<int>&c){if(c.size()<4)return 0.;P a=sub(p[c[1]],p[c[0]]),b=sub(p[c[2]],p[c[0]]),d=sub(p[c[3]],p[c[0]]);return dot(a,cross(b,d))/6.;}

struct PersistBinding {
    py::dict row;
    std::string source_face, source_face_a, source_face_b, tangent_face;
    int wall0=-1, wall1=-1, front0=-1, front1=-1;
    std::vector<int> final_cell_ids, final_front_face_ids, final_wall_face_ids;
};
std::string read_file(const std::filesystem::path& path, bool& ok) {
    std::ifstream in(path, std::ios::binary);
    if (!in) { ok=false; return {}; }
    std::ostringstream out; out << in.rdbuf(); ok=true; return out.str();
}
std::map<std::string,std::string> read_kv(const std::filesystem::path& path, bool& ok) {
    std::map<std::string,std::string> out; bool local=false; auto raw=read_file(path,local);
    if(!local){ok=false;return out;} std::istringstream in(raw); std::string line;
    while(std::getline(in,line)){if(line.empty()||line[0]=='#')continue;auto p=line.find('=');if(p==std::string::npos){ok=false;return{};}out[line.substr(0,p)]=line.substr(p+1);}
    ok=true;return out;
}
std::filesystem::path safe_child(const std::filesystem::path& root,const std::string& rel,bool& ok) {
    if(rel.empty()){ok=false;return{};} auto p=(root/std::filesystem::path(rel)).lexically_normal();
    auto r=root.lexically_normal(); auto q=p.lexically_relative(r); if(q.empty()||q.string()==".."||q.string().rfind("../",0)==0||std::filesystem::is_symlink(p)){ok=false;return{};} ok=true;return p;
}
std::vector<P> read_points_file(const std::filesystem::path& path,bool& ok) {
    bool local=false;auto raw=read_file(path,local);if(!local){ok=false;return{};}std::vector<P> out;std::istringstream in(raw);std::string line;
    while(std::getline(in,line)){if(line.empty()||line[0]=='#')continue;std::istringstream row(line);P p;if(!(row>>p.x>>p.y>>p.z)){ok=false;return{};}out.push_back(p);}
    ok=true;return out;
}
std::vector<std::vector<int>> read_rows_file(const std::filesystem::path& path,bool& ok) {
    bool local=false;auto raw=read_file(path,local);if(!local){ok=false;return{};}std::vector<std::vector<int>> out;std::istringstream in(raw);std::string line;
    while(std::getline(in,line)){if(line.empty()||line[0]=='#')continue;std::istringstream row(line);std::vector<int> ids;int id;while(row>>id)ids.push_back(id);if(ids.empty()){ok=false;return{};}out.push_back(std::move(ids));}
    ok=true;return out;
}
py::list py_points(const std::vector<P>& values){py::list out;for(const auto&p:values)out.append(py::make_tuple(p.x,p.y,p.z));return out;}
py::list py_rows(const std::vector<std::vector<int>>& values){py::list out;for(const auto&row:values){py::list x;for(int id:row)x.append(id);out.append(x);}return out;}
std::vector<std::string> split_tab(const std::string& line){std::vector<std::string> out;std::string item;std::istringstream in(line);while(std::getline(in,item,'\t'))out.push_back(item);return out;}
py::list read_ledger_file(const std::filesystem::path& path,std::map<std::string,std::vector<int>>& source_vertices,bool& ok) {
    bool local=false;auto raw=read_file(path,local);if(!local){ok=false;return py::list{};}py::list out;std::istringstream in(raw);std::string line;
    while(std::getline(in,line)){if(line.empty()||line[0]=='#')continue;auto v=split_tab(line);if(v.size()<9){ok=false;return py::list{};}py::dict row;row["source_face_id"]=v[0];row["source_edge"]=v[1];row["feature_id"]=v[2];row["patch_id"]=v[3];row["physical_group"]=v[4];row["component_id"]=v[5];row["orientation"]=v[6];row["source_vertex_ids"]=v[7];row["provenance"]=v[8];std::vector<int> ids;std::istringstream ids_in(v[7]);std::string token;while(std::getline(ids_in,token,',')){try{ids.push_back(std::stoi(token));}catch(...){ok=false;return py::list{};}}if(ids.size()<3){ok=false;return py::list{};}source_vertices[v[0]]=std::move(ids);out.append(row);}
    ok=true;return out;
}
std::vector<P> source_face_normal(const std::vector<P>& points,const std::map<std::string,std::vector<int>>& source_vertices,const std::string& face,bool& ok){
    auto it=source_vertices.find(face);if(it==source_vertices.end()||it->second.size()<3){ok=false;return{};}auto ids=it->second;for(int id:ids)if(id<0||static_cast<size_t>(id)>=points.size()){ok=false;return{};}P n=cross(sub(points[ids[1]],points[ids[0]]),sub(points[ids[2]],points[ids[0]]));double nn=norm(n);if(nn<=1e-14){ok=false;return{};}n={n.x/nn,n.y/nn,n.z/nn};ok=true;return{n};
}
bool parse_id_list(const std::string& raw, std::vector<int>& out) {
    if(raw.empty()) return false;
    std::istringstream in(raw); std::string token;
    while(std::getline(in,token,',')){try{int id=std::stoi(token);if(id<0)return false;out.push_back(id);}catch(...){return false;}}
    return !out.empty();
}
std::vector<PersistBinding> read_bindings_file(const std::filesystem::path& path,bool& ok){
    bool local=false;auto raw=read_file(path,local);if(!local){ok=false;return{};}std::vector<PersistBinding> out;std::istringstream in(raw);std::string line;
    while(std::getline(in,line)){if(line.empty()||line[0]=='#')continue;auto v=split_tab(line);if(v.size()<20){ok=false;return{};}PersistBinding b;b.source_face=v[0];b.source_face_a=v[1];b.source_face_b=v[2];b.tangent_face=v[17];try{b.wall0=std::stoi(v[13]);b.wall1=std::stoi(v[14]);b.front0=std::stoi(v[15]);b.front1=std::stoi(v[16]);if(v.size()>=23&&(!parse_id_list(v[20],b.final_cell_ids)||!parse_id_list(v[21],b.final_front_face_ids)||!parse_id_list(v[22],b.final_wall_face_ids))){ok=false;return{};}}catch(...){ok=false;return{};}b.row["source_edge"]=v[3];b.row["wall_edge"]=v[4];b.row["bl_strip"]=v[5];b.row["first_strip_face"]=v[18];b.row["output_boundary_face"]=v[6];b.row["volume_boundary_face"]=v[7];b.row["feature"]=v[8];b.row["patch"]=v[9];b.row["physical_group"]=v[10];b.row["component"]=v[11];b.row["provenance"]=v[12];b.row["orientation"]=v[19];b.row["wall_front_orthogonality_degrees"]=0.0;if(!b.source_face.empty())b.row["source_face"]=b.source_face;if(!b.source_face_a.empty())b.row["source_face_a"]=b.source_face_a;if(!b.source_face_b.empty())b.row["source_face_b"]=b.source_face_b;out.push_back(std::move(b));}
    ok=true;return out;
}
py::list py_bindings(const std::vector<PersistBinding>& values){py::list out;for(const auto&b:values)out.append(b.row);return out;}

}

namespace autotessell_tet_polymesh {
namespace {
std::string trim_copy(const std::string& value){auto a=value.find_first_not_of(" \t\r\n");if(a==std::string::npos)return{};auto b=value.find_last_not_of(" \t\r\n");return value.substr(a,b-a+1);}
bool read_list_body(const std::string& raw,std::vector<std::string>& lines){std::istringstream in(raw);std::string line;bool inside=false;while(std::getline(in,line)){auto t=trim_copy(line);if(t=="("){inside=true;continue;}if(inside&&t==")"){return true;}if(inside&&!t.empty())lines.push_back(t);}return false;}
bool parse_points_raw(const std::string& raw,std::vector<std::array<double,3>>& out){std::vector<std::string> lines;if(!read_list_body(raw,lines))return false;for(const auto&line:lines){auto l=line.find('('),r=line.rfind(')');if(l==std::string::npos||r<=l+1)continue;std::istringstream row(line.substr(l+1,r-l-1));std::array<double,3> p{};if(!(row>>p[0]>>p[1]>>p[2]))return false;out.push_back(p);}return !out.empty();}
bool parse_faces_raw(const std::string& raw,std::vector<std::vector<int>>& out){std::vector<std::string> lines;if(!read_list_body(raw,lines))return false;for(const auto&line:lines){auto l=line.find('('),r=line.rfind(')');if(l==std::string::npos||r<=l)continue;int count=0;std::istringstream prefix(line.substr(0,l));if(!(prefix>>count)||count!=3)return false;std::istringstream row(line.substr(l+1,r-l-1));std::vector<int> ids(3);if(!(row>>ids[0]>>ids[1]>>ids[2]))return false;out.push_back(std::move(ids));}return !out.empty();}
bool parse_ints_raw(const std::string& raw,std::vector<int>& out){std::vector<std::string> lines;if(!read_list_body(raw,lines))return false;for(const auto&line:lines){std::istringstream row(line);int value;while(row>>value)out.push_back(value);}return true;}
bool parse_boundary_raw(const std::string& raw,std::vector<std::pair<int,int>>& ranges){std::regex re(R"(nFaces\s+([0-9]+)\s*;\s*startFace\s+([0-9]+)\s*;)");for(std::sregex_iterator it(raw.begin(),raw.end(),re),end;it!=end;++it)ranges.emplace_back(std::stoi((*it)[2]),std::stoi((*it)[1]));return !ranges.empty();}
bool read_regular(const std::filesystem::path& path,std::string& raw){if(std::filesystem::is_symlink(path)||!std::filesystem::is_regular_file(path))return false;bool ok=false;raw=read_file(path,ok);return ok;}
}
bool read_artifact(const std::filesystem::path& root,Artifact& a){
 std::array<std::string,5> names={"points","faces","owner","neighbour","boundary"};std::array<std::string,5> raw{};for(size_t i=0;i<names.size();++i)if(!read_regular(root/names[i],raw[i])){a.error="polymesh_file_missing";return false;}
 if(!parse_points_raw(raw[0],a.points)||!parse_faces_raw(raw[1],a.faces)||!parse_ints_raw(raw[2],a.owner)||!parse_ints_raw(raw[3],a.neighbour)||!parse_boundary_raw(raw[4],a.boundary_ranges)){a.error="polymesh_ascii_parse_failed";return false;}
 if(a.owner.size()!=a.faces.size()||a.neighbour.size()>a.faces.size()){a.error="polymesh_incidence_size_invalid";return false;}for(const auto&f:a.faces){if(f.size()!=3||std::set<int>(f.begin(),f.end()).size()!=3){a.error="polymesh_face_not_triangle";return false;}for(int id:f)if(id<0||static_cast<size_t>(id)>=a.points.size()){a.error="polymesh_face_vertex_invalid";return false;}}
 int cells=0;for(int id:a.owner)if(id<0){a.error="polymesh_owner_invalid";return false;}else cells=std::max(cells,id+1);for(int id:a.neighbour)if(id<0||id>=cells){a.error="polymesh_neighbour_invalid";return false;}int cursor=static_cast<int>(a.neighbour.size());for(const auto&[start,count]:a.boundary_ranges){if(start!=cursor||count<0||start<0||start+count>static_cast<int>(a.faces.size())){a.error="polymesh_boundary_range_invalid";return false;}cursor=start+count;}if(cursor!=static_cast<int>(a.faces.size())){a.error="polymesh_boundary_coverage_gap";return false;}
 std::string tree;for(size_t i=0;i<raw.size();++i){tree+=names[i];tree.push_back('\0');tree+=raw[i];tree.push_back('\0');}a.canonical_sha256=sha(tree);return true;
}
}

py::dict audit(const std::string&engine,const py::bytes&source_obj,const py::bytes&output_obj,const py::dict&authority,const py::dict&ledger,const py::dict&manifest,const py::sequence&binding,const py::sequence&points_obj,const py::sequence&tri_obj,const py::sequence&quad_obj,const py::sequence&cell_obj,std::int64_t req,std::int64_t actual,const std::string&baseline,const std::string&candidate){
 if(engine!="native_tet"&&engine!="native_hex"&&engine!="native_poly"&&engine!="native_tri"&&engine!="strict_quad"&&engine!="tri_quad"&&engine!="surface")return bad("engine_kind_invalid");
 if(req<0||actual<0)return bad("negative_layer_count");
 std::string src=source_obj.cast<std::string>(),out=output_obj.cast<std::string>(),sd=sha(src),od=sha(out);if(!h64(sd)||!h64(od))return bad("native_hash_failed");if(txt(manifest,"schema")!="native-l2-evidence-manifest/v1"||txt(manifest,"engine")!=engine||txt(manifest,"output_sha256")!=od||!h64(txt(manifest,"build_sha256"))||!h64(txt(manifest,"config_sha256")))return bad("manifest_digest_or_schema_mismatch");if(!autotessell_native::receipt_sealed_default_off(authority)||!flag(authority,"direct_lineage")||txt(authority,"source_sha256")!=sd)return bad("authority_source_digest_mismatch");if(txt(ledger,"schema")!="native-l2-authoritative-ledger/v1"||!flag(ledger,"immutable")||txt(ledger,"source_sha256")!=sd||!ledger.contains("source_faces")||py::len(ledger["source_faces"])==0)return bad("authoritative_ledger_invalid");std::set<std::string>source_ids;for(py::handle h:py::reinterpret_borrow<py::sequence>(ledger["source_faces"])){py::dict f=py::reinterpret_borrow<py::dict>(h);for(const char*k:{"source_face_id","source_edge","feature_id","patch_id","physical_group","component_id","orientation"})if(txt(f,k).empty())return bad("ledger_field_missing");if(!source_ids.insert(txt(f,"source_face_id")).second)return bad("ledger_duplicate_source_face");}auto repeat_src=manifest["repeat_source_sha256"].cast<py::sequence>(),repeat_out=manifest["repeat_output_sha256"].cast<py::sequence>();if(py::len(repeat_src)!=3||py::len(repeat_out)!=3)return bad("repeatability_triplet_missing");for(py::handle h:repeat_src)if(py::str(h).cast<std::string>()!=sd)return bad("source_repeatability_mismatch");for(py::handle h:repeat_out)if(py::str(h).cast<std::string>()!=od)return bad("output_repeatability_mismatch");if(req==0){if(actual!=0||!flag(manifest,"bl0_exact_identity")||baseline!=candidate||!h64(baseline))return bad("bl0_exact_identity_failed");}else{if(actual!=req||!manifest.contains("total_thickness")||manifest["total_thickness"].cast<double>()<=0||!flag(manifest,"thickness_monotone")||!manifest.contains("growth_ratio_error")||manifest["growth_ratio_error"].cast<double>()>.02)return bad("positive_bl_contract_failed");if(baseline==candidate)return bad("positive_bl_clone");}
 std::vector<P> pts=points(points_obj);std::vector<std::vector<int>> tr=rows(tri_obj),qu=rows(quad_obj),cells=rows(cell_obj);if(tr.empty()&&qu.empty()&&cells.empty())return bad("persisted_geometry_missing");std::set<std::string>used,outputs;double maxwall=0;std::vector<double>walls;for(py::handle h:binding){py::dict r=py::reinterpret_borrow<py::dict>(h);for(const char*k:{"source_edge","wall_edge","bl_strip","output_boundary_face","volume_boundary_face","feature","patch","physical_group","component","provenance"})if(txt(r,k).empty())return bad("boundary_binding_incomplete");std::string outid=txt(r,"output_boundary_face");if(!outputs.insert(outid).second)return bad("duplicate_boundary_binding");std::vector<std::string> sfaces;std::string sf=txt(r,"source_face");if(!sf.empty())sfaces.push_back(sf);std::string sfa=txt(r,"source_face_a"),sfb=txt(r,"source_face_b");if(sf.empty()&&!sfa.empty())sfaces.push_back(sfa);if(!sfb.empty())sfaces.push_back(sfb);if(sfaces.empty())return bad("source_binding_invalid");for(const auto&face:sfaces)if(!source_ids.count(face)||!used.insert(face).second)return bad("source_binding_invalid");if(req>0){if(!r.contains("wall_front_orthogonality_degrees"))return bad("wall_front_metric_missing");double w=r["wall_front_orthogonality_degrees"].cast<double>();if(!std::isfinite(w)||w>25.)return bad("wall_front_quality_failed");walls.push_back(w);maxwall=std::max(maxwall,w);}}
 if(req>0&&used.size()!=source_ids.size())return bad("source_boundary_coverage_incomplete");
 M m=surface(pts,tr,qu);if(m.duplicate||m.nonmanifold||m.inverted||m.degenerate||m.self_intersection)return bad("surface_topology_failed");double minvol=1e300;int badvol=0;if(engine=="native_tet"||engine=="native_hex"||engine=="native_poly"){for(const auto&c:cells){if(engine=="native_tet"&&c.size()!=4){++badvol;continue;}if(engine=="native_hex"&&c.size()!=8){++badvol;continue;}if(engine=="native_poly"&&c.size()<4){++badvol;continue;}for(int id:c)if(id<0||static_cast<size_t>(id)>=pts.size())++badvol;if(engine=="native_tet"||engine=="native_poly"){double v=cell_volume(pts,c);minvol=std::min(minvol,v);if(v<=0)++badvol;}else{double v=norm(cross(sub(pts[c[1]],pts[c[0]]),sub(pts[c[3]],pts[c[0]])));minvol=std::min(minvol,v);if(v<=1e-14)++badvol;}}if(cells.empty()||badvol)return bad("volume_geometry_failed");}
 if(m.minjac<=0||m.maxskew>.5||m.p95skew>(engine=="surface"?.30:.25)||m.maxaspect>5||m.p95aspect>3||(engine!="native_tet"&&engine!="native_hex"&&engine!="native_poly"&&engine!="surface"&& (m.maxno>50||m.p95no>35))) return bad("quality_gate_failed");
 py::dict topo;topo["duplicate"]=m.duplicate;topo["non_manifold"]=m.nonmanifold;topo["inverted"]=m.inverted;topo["degenerate"]=m.degenerate;topo["self_intersection"]=m.self_intersection;topo["boundary_faces"]=m.boundary.size();py::dict q;q["max_skewness"]=m.maxskew;q["p95_skewness"]=m.p95skew;q["max_tangent_aspect"]=m.maxaspect;q["p95_tangent_aspect"]=m.p95aspect;q["minimum_scaled_jacobian"]=m.minjac;q["max_non_orthogonality_degrees"]=m.maxno;q["p95_non_orthogonality_degrees"]=m.p95no;q["max_wall_front_orthogonality_degrees"]=maxwall;q["p95_wall_front_orthogonality_degrees"]=p95(walls);q["minimum_cell_volume_or_jacobian"]=minvol;py::dict r;r["accepted"]=true;r["status"]="native_l2_evidence_audit_sealed";r["engine"]=engine;r["source_sha256"]=sd;r["output_sha256"]=od;r["requested_layers"]=req;r["actual_layers"]=actual;r["runtime_route"]="default_off";r["publication_eligible"]=false;r["receipt_sealed"]=true;r["repeatable_three_runs"]=true;r["topology"]=topo;r["quality"]=q;r["candidate_discarded"]=false;r["atomic_rollback"]=false;r["audit_digest"]="native-l2-audit-v1|"+engine+"|"+sd+"|"+od+"|"+txt(manifest,"build_sha256")+"|"+txt(manifest,"config_sha256");return r;
}

bool validate_producer_run_records(const std::filesystem::path& path, const std::string& output_hash, const std::string& geometry_hash) {
    bool ok=false; auto raw=read_file(path,ok); if(!ok) return false;
    std::set<std::string> ids, nonces; std::istringstream in(raw); std::string line; int count=0;
    while(std::getline(in,line)) {
        if(line.empty()||line[0]=='#') continue;
        auto f=split_tab(line); if(f.size()<4 || f[0].empty() || f[1].empty() || !h64(f[2]) || !h64(f[3])) return false;
        if(f[2]!=output_hash || f[3]!=geometry_hash || !ids.insert(f[0]).second || !nonces.insert(f[1]).second) return false;
        ++count;
    }
    return count==3;
}

bool validate_surface_layer_records(const std::filesystem::path& path, int expected, size_t point_count,
                                    size_t face_count, const std::map<std::string,std::vector<int>>& source_vertices) {
    bool ok=false; auto raw=read_file(path,ok); if(!ok) return false;
    std::istringstream in(raw); std::string line; int count=0;
    while(std::getline(in,line)) {
        if(line.empty()||line[0]=='#') continue;
        auto f=split_tab(line); if(f.size()<14) return false;
        try {
            int layer=std::stoi(f[1]), wall0=std::stoi(f[3]), wall1=std::stoi(f[4]);
            int front0=std::stoi(f[5]), front1=std::stoi(f[6]);
            std::vector<int> final_ids; if(!parse_id_list(f[7],final_ids)) return false;
            if(layer!=count+1 || f[0].empty() || f[2].empty() || !source_vertices.count(f[2]) ||
               wall0<0 || wall1<0 || front0<0 || front1<0 ||
               static_cast<size_t>(wall0)>=point_count || static_cast<size_t>(wall1)>=point_count ||
               static_cast<size_t>(front0)>=point_count || static_cast<size_t>(front1)>=point_count ||
               f[8].empty() || f[9].empty() || f[10].empty() || f[11].empty() || f[12].empty() || f[13].empty()) return false;
            for(int id:final_ids) if(id<0 || static_cast<size_t>(id)>=face_count) return false;
        } catch(...) { return false; }
        ++count;
    }
    return count==expected;
}

bool validate_surface_layer_semantics(const std::filesystem::path& path, const py::list& source_faces) {
    std::map<std::string,std::array<std::string,6>> semantic;
    for(py::handle h:source_faces){
        auto row=py::reinterpret_borrow<py::dict>(h);
        semantic[txt(row,"source_face_id")]={txt(row,"feature_id"),txt(row,"patch_id"),txt(row,"physical_group"),txt(row,"component_id"),txt(row,"orientation"),txt(row,"provenance")};
    }
    bool ok=false; auto raw=read_file(path,ok); if(!ok) return false;
    std::istringstream in(raw); std::string line;
    while(std::getline(in,line)){
        if(line.empty()||line[0]=='#') continue;
        auto f=split_tab(line); if(f.size()<14) return false;
        auto it=semantic.find(f[2]); if(it==semantic.end()) return false;
        const auto& expected=it->second;
        if(f[8]!=expected[0]||f[9]!=expected[1]||f[10]!=expected[2]||f[11]!=expected[3]||f[12]!=expected[4]) return false;
    }
    return true;
}

py::dict audit_persisted(const std::string& root_arg){
    std::filesystem::path root=std::filesystem::absolute(std::filesystem::path(root_arg)).lexically_normal();
    if(!std::filesystem::is_directory(root))return bad("persisted_root_missing");
    bool ok=false;auto kv=read_kv(root/"evidence.atne",ok);const bool pack_v2=kv["schema"]=="native-l2-persisted-evidence/v2";if(!ok||(kv["schema"]!="native-l2-persisted-evidence/v1"&&!pack_v2))return bad("persisted_envelope_invalid");if(pack_v2&&(!kv.count("authority_level")||kv["authority_level"].empty()))return bad("persisted_authority_level_missing");if(pack_v2&&kv["authority_level"]=="L0_actual_brep_fixture"){for(const char*k:{"authority_canonical_positions_digest","authority_face_ordinal_digest","authority_orientation_digest","authority_seam_digest","authority_mapping_digest"})if(!kv.count(k)||!h64(kv[k]))return bad("persisted_brep_authority_metadata_missing");}
    for(const char*k:{"engine","source_path","output_path","points_path","triangles_path","quads_path","cells_path","ledger_path","binding_path","geometry_sha256","source_sha256","output_sha256","build_sha256","config_sha256","baseline_digest","candidate_digest","requested_layers","actual_layers","bl0_exact_identity","thickness_monotone","growth_ratio_error"})if(!kv.count(k)||kv[k].empty())return bad("persisted_envelope_field_missing");
    bool path_ok=true;auto source_path=safe_child(root,kv["source_path"],path_ok);if(!path_ok)return bad("persisted_source_path_invalid");auto output_path=safe_child(root,kv["output_path"],path_ok);if(!path_ok)return bad("persisted_output_path_invalid");
    bool read_ok=false;auto source_raw=read_file(source_path,read_ok);if(!read_ok)return bad("persisted_source_missing");auto output_raw=read_file(output_path,read_ok);if(!read_ok)return bad("persisted_output_missing");
    auto source_hash=sha(source_raw),output_hash=sha(output_raw);if(source_hash!=kv["source_sha256"]||output_hash!=kv["output_sha256"])return bad("persisted_raw_digest_mismatch");
    std::vector<std::string>run_hashes;for(int i=1;i<=3;++i){auto name="run_output_"+std::to_string(i);if(!kv.count(name))return bad("persisted_run_path_missing");auto rp=safe_child(root,kv[name],path_ok);if(!path_ok)return bad("persisted_run_path_invalid");auto rr=read_file(rp,read_ok);if(!read_ok)return bad("persisted_run_output_missing");auto rh=sha(rr);if(rh!=output_hash)return bad("persisted_run_repeatability_mismatch");run_hashes.push_back(rh);}
    auto read_rel=[&](const std::string&key){bool local=true;auto p=safe_child(root,kv[key],local);if(!local)return std::filesystem::path{};return p;};
    auto pp=read_rel("points_path"),tp=read_rel("triangles_path"),qp=read_rel("quads_path"),cp=read_rel("cells_path"),lp=read_rel("ledger_path"),bp=read_rel("binding_path");if(pp.empty()||tp.empty()||qp.empty()||cp.empty()||lp.empty()||bp.empty())return bad("persisted_geometry_path_invalid");
    bool points_ok=false,tri_ok=false,quad_ok=false,cell_ok=false,ledger_ok=false,bind_ok=false;auto pts=read_points_file(pp,points_ok);auto tr=read_rows_file(tp,tri_ok);auto qu=read_rows_file(qp,quad_ok);auto cells=read_rows_file(cp,cell_ok);std::map<std::string,std::vector<int>>source_vertices;auto source_faces=read_ledger_file(lp,source_vertices,ledger_ok);auto bindings=read_bindings_file(bp,bind_ok);if(!points_ok||!tri_ok||!quad_ok||!cell_ok||!ledger_ok||!bind_ok)return bad("persisted_geometry_or_provenance_parse_failed");if(pack_v2&&bindings.empty())return bad("persisted_boundary_binding_missing");if(pack_v2){std::map<std::string,std::array<std::string,6>> semantic;for(py::handle h:source_faces){auto row=py::reinterpret_borrow<py::dict>(h);semantic[txt(row,"source_face_id")]={txt(row,"feature_id"),txt(row,"patch_id"),txt(row,"physical_group"),txt(row,"component_id"),txt(row,"orientation"),txt(row,"provenance")};}for(const auto& b:bindings){auto it=semantic.find(b.source_face);if(it==semantic.end())return bad("persisted_binding_source_unknown");const auto& expected=it->second;if(txt(b.row,"feature")!=expected[0]||txt(b.row,"patch")!=expected[1]||txt(b.row,"physical_group")!=expected[2]||txt(b.row,"component")!=expected[3]||txt(b.row,"orientation")!=expected[4]||txt(b.row,"provenance")!=expected[5])return bad("persisted_binding_semantics_mismatch");}}
    bool raw_geom_ok=false;auto points_raw=read_file(pp,raw_geom_ok);if(!raw_geom_ok)return bad("persisted_points_missing");auto tri_raw=read_file(tp,raw_geom_ok);if(!raw_geom_ok)return bad("persisted_triangles_missing");auto quad_raw=read_file(qp,raw_geom_ok);if(!raw_geom_ok)return bad("persisted_quads_missing");auto cell_raw=read_file(cp,raw_geom_ok);if(!raw_geom_ok)return bad("persisted_cells_missing");if(sha(points_raw+tri_raw+quad_raw+cell_raw)!=kv["geometry_sha256"])return bad("persisted_geometry_digest_mismatch");
    py::dict authority;authority["accepted"]=true;authority["receipt_sealed"]=true;authority["receipt_digest"]=kv.count("authority_receipt_digest")?kv["authority_receipt_digest"]:"persisted-authority";authority["runtime_route"]="default_off";authority["direct_lineage"]=true;authority["source_sha256"]=source_hash;
    py::dict led;led["schema"]="native-l2-authoritative-ledger/v1";led["immutable"]=true;led["source_sha256"]=source_hash;led["source_faces"]=source_faces;
    py::dict manifest;manifest["schema"]="native-l2-evidence-manifest/v1";manifest["engine"]=kv["engine"];manifest["output_sha256"]=output_hash;manifest["build_sha256"]=kv["build_sha256"];manifest["config_sha256"]=kv["config_sha256"];py::list rs,ro;for(int i=0;i<3;++i){rs.append(source_hash);ro.append(run_hashes[i]);}manifest["repeat_source_sha256"]=rs;manifest["repeat_output_sha256"]=ro;manifest["bl0_exact_identity"]=kv["bl0_exact_identity"]=="true";manifest["total_thickness"]=std::stod(kv["total_thickness"]);manifest["thickness_monotone"]=kv["thickness_monotone"]=="true";manifest["growth_ratio_error"]=std::stod(kv["growth_ratio_error"]);
    std::int64_t req=0,actual=0;try{req=std::stoll(kv["requested_layers"]);actual=std::stoll(kv["actual_layers"]);}catch(...){return bad("persisted_layer_field_invalid");}
    const bool has_producer_runs=kv.count("producer_runs_path"), has_layer_records=kv.count("layer_records_path");
    if(has_producer_runs!=has_layer_records) return bad("persisted_direct_layer_evidence_pair_missing");
    if(has_producer_runs){
        auto prp=read_rel("producer_runs_path"), lrp=read_rel("layer_records_path");
        if(prp.empty()||lrp.empty()||!validate_producer_run_records(prp,output_hash,kv["geometry_sha256"])||
           !validate_surface_layer_records(lrp,static_cast<int>(req),pts.size(),tr.size(),source_vertices) ||
           !validate_surface_layer_semantics(lrp,source_faces))
            return bad("persisted_direct_layer_evidence_invalid");
    }
    authority["authority_level"]=pack_v2?kv["authority_level"]:"L0_synthetic";auto result=audit(kv["engine"],py::bytes(source_raw),py::bytes(output_raw),authority,led,manifest,py_bindings(bindings),py_points(pts),py_rows(tr),py_rows(qu),py_rows(cells),req,actual,kv["baseline_digest"],kv["candidate_digest"]);if(!result["accepted"].cast<bool>())return result;result["evidence_pack_schema"]=kv["schema"];result["authority_level"]=pack_v2?kv["authority_level"]:"L0_synthetic";result["publication_eligible"]=false;
    py::dict quality=result["quality"].cast<py::dict>();if(req==0){quality["wall_front_status"]="not_applicable_bl0";result["geometry_recomputed"]=true;result["evidence_root"]=root.string();result["status"]="native_l2_persisted_evidence_sealed";return result;}
    std::vector<double>angles,outplane;for(const auto&b:bindings){std::string face=!b.source_face.empty()?b.source_face:b.source_face_a;bool geom_ok=false;auto ns=source_face_normal(pts,source_vertices,face,geom_ok);if(!geom_ok||b.wall0<0||b.wall1<0||b.front0<0||b.front1<0||static_cast<size_t>(b.wall0)>=pts.size()||static_cast<size_t>(b.wall1)>=pts.size()||static_cast<size_t>(b.front0)>=pts.size()||static_cast<size_t>(b.front1)>=pts.size())return bad("persisted_wall_front_binding_invalid");P t=sub(pts[b.wall1],pts[b.wall0]);double tn=norm(t);if(tn<=1e-14)return bad("persisted_wall_edge_degenerate");t={t.x/tn,t.y/tn,t.z/tn};P n=ns[0],u=cross(n,t);double un=norm(u);if(un<=1e-14)return bad("persisted_wall_tangent_degenerate");u={u.x/un,u.y/un,u.z/un};P d={(pts[b.front0].x+pts[b.front1].x-pts[b.wall0].x-pts[b.wall1].x)/2.,(pts[b.front0].y+pts[b.front1].y-pts[b.wall0].y-pts[b.wall1].y)/2.,(pts[b.front0].z+pts[b.front1].z-pts[b.wall0].z-pts[b.wall1].z)/2.};double dn=norm(d);if(dn<=1e-14)return bad("persisted_first_front_degenerate");P dt={d.x-n.x*dot(d,n),d.y-n.y*dot(d,n),d.z-n.z*dot(d,n)};double theta=std::atan2(std::abs(dot(dt,t)),std::abs(dot(dt,u)))*180./3.141592653589793;double normal_angle=std::asin(std::min(1.,std::abs(dot(d,n))/dn))*180./3.141592653589793;if(!std::isfinite(theta)||theta>25.)return bad("persisted_wall_front_quality_failed");angles.push_back(theta);outplane.push_back(normal_angle);}
    quality["max_wall_front_orthogonality_degrees"]=angles.empty()?0.:*std::max_element(angles.begin(),angles.end());quality["p95_wall_front_orthogonality_degrees"]=p95(angles);quality["max_wall_front_out_of_plane_degrees"]=outplane.empty()?0.:*std::max_element(outplane.begin(),outplane.end());quality["wall_front_angle_source"]="cxx_geometry_recomputed";result["geometry_recomputed"]=true;result["evidence_root"]=root.string();result["status"]="native_l2_persisted_evidence_sealed";return result;
}


bool validate_positive_layer_records(const std::filesystem::path& path, int expected) {
    bool ok=false; auto raw=read_file(path,ok); if(!ok) return false;
    std::istringstream in(raw); std::string line; int count=0;
    while(std::getline(in,line)){
        if(line.empty()||line[0]=='#') continue;
        auto fields=split_tab(line); if(fields.size()<8) return false;
        try {
            int layer=std::stoi(fields[0]); double h=std::stod(fields[1]);
            double thickness=std::stod(fields[2]); double cumulative=std::stod(fields[3]);
            double ratio=std::stod(fields[4]);
            if(layer!=count||!std::isfinite(h)||!std::isfinite(thickness)||!std::isfinite(cumulative)||!std::isfinite(ratio)||h<=0||thickness<=0||cumulative<=0||ratio<=0) return false;
        } catch(...) { return false; }
        ++count;
    }
    return count==expected;
}


py::dict audit_persisted_tet(const std::string& root_arg){
 std::filesystem::path root=std::filesystem::absolute(std::filesystem::path(root_arg)).lexically_normal();if(!std::filesystem::is_directory(root))return bad("persisted_root_missing");bool ok=false;auto kv=read_kv(root/"evidence.atne",ok);if(!ok||kv["schema"]!="native-l2-persisted-evidence/v1"||kv["engine"]!="native_tet"||kv["artifact_format"]!="openfoam-polymesh-ascii/v1")return bad("native_tet_polymesh_envelope_invalid");for(const char*k:{"source_path","polymesh_root","baseline_polymesh_root","run_polymesh_root_1","run_polymesh_root_2","run_polymesh_root_3","ledger_path","binding_path","source_sha256","artifact_tree_sha256","build_sha256","config_sha256","baseline_digest","candidate_digest","requested_layers","actual_layers","bl0_exact_identity"})if(!kv.count(k)||kv[k].empty())return bad("native_tet_polymesh_envelope_field_missing");if(kv.count("authority_level")){if(kv["authority_level"]!="L0_actual_brep_fixture")return bad("native_tet_authority_level_invalid");for(const char*k:{"authority_canonical_positions_digest","authority_face_ordinal_digest","authority_orientation_digest","authority_seam_digest","authority_mapping_digest"})if(!kv.count(k)||!h64(kv[k]))return bad("native_tet_authority_digest_missing");}
 auto safe=[&](const std::string&rel){bool local=true;auto p=safe_child(root,rel,local);if(!local)return std::filesystem::path{};return p;};auto source_path=safe(kv["source_path"]),poly_path=safe(kv["polymesh_root"]),base_path=safe(kv["baseline_polymesh_root"]);if(source_path.empty()||poly_path.empty()||base_path.empty())return bad("native_tet_polymesh_path_invalid");bool read_ok=false;auto source_raw=read_file(source_path,read_ok);if(!read_ok)return bad("native_tet_source_missing");if(sha(source_raw)!=kv["source_sha256"])return bad("native_tet_source_digest_mismatch");autotessell_tet_polymesh::Artifact artifact;if(!autotessell_tet_polymesh::read_artifact(poly_path,artifact))return bad(artifact.error.c_str());if(artifact.canonical_sha256!=kv["artifact_tree_sha256"])return bad("native_tet_artifact_digest_mismatch");autotessell_tet_polymesh::Artifact baseline_artifact;if(!autotessell_tet_polymesh::read_artifact(base_path,baseline_artifact))return bad("native_tet_baseline_missing");std::vector<std::string>run_hashes;for(int i=1;i<=3;++i){auto rp=safe(kv["run_polymesh_root_"+std::to_string(i)]);if(rp.empty())return bad("native_tet_run_path_invalid");autotessell_tet_polymesh::Artifact run;if(!autotessell_tet_polymesh::read_artifact(rp,run))return bad("native_tet_run_artifact_invalid");if(run.canonical_sha256!=artifact.canonical_sha256)return bad("native_tet_run_repeatability_mismatch");run_hashes.push_back(run.canonical_sha256);}
 std::map<std::string,std::vector<int>>source_vertices;auto source_faces=read_ledger_file(safe(kv["ledger_path"]),source_vertices,ok);if(!ok)return bad("native_tet_ledger_invalid");auto bindings=read_bindings_file(safe(kv["binding_path"]),ok);if(!ok)return bad("native_tet_binding_invalid");std::int64_t req=0,actual=0;try{req=std::stoll(kv["requested_layers"]);actual=std::stoll(kv["actual_layers"]);}catch(...){return bad("native_tet_layer_field_invalid");}bool positive=req>0||actual>0;if(positive){for(const char*k:{"positive_contract","source_authority_kind","source_authority_status","wall_edge_eligible","writer_owned_id_capsule","pure_tet","layer_record_count","wall_edge_binding_count","first_thickness","growth_ratio","total_thickness","quality_aspect_cap","layer_path"})if(!kv.count(k)||kv[k].empty())return bad("native_tet_positive_bl_artifact_contract_missing");if(kv["positive_contract"]!="true"||kv["source_authority_kind"]=="unknown"||kv["writer_owned_id_capsule"]!="true")return bad("native_tet_positive_bl_artifact_contract_missing");if(kv["source_authority_status"]!="SOURCE_VERIFIED")return bad("native_tet_positive_bl_authority_provisional");if(kv["wall_edge_eligible"]!="true")return bad("native_tet_positive_bl_wall_edge_ineligible");if(kv["pure_tet"]!="true")return bad("native_tet_positive_bl_mixed_topology");for(const auto&b:bindings)if(b.final_cell_ids.empty()||b.final_front_face_ids.empty()||b.final_wall_face_ids.empty())return bad("native_tet_positive_bl_final_id_mapping_missing");try{double h=std::stod(kv["first_thickness"]),r=std::stod(kv["growth_ratio"]),t=std::stod(kv["total_thickness"]),cap=std::stod(kv["quality_aspect_cap"]);double expected=std::abs(r-1.)<1e-12?static_cast<double>(req)*h:h*(std::pow(r,static_cast<double>(req))-1.)/(r-1.);if(!std::isfinite(h)||!std::isfinite(r)||!std::isfinite(t)||!std::isfinite(cap)||h<=0||r<=0||t<=0||cap<=0||std::abs(t-expected)>std::max(1e-10,0.02*std::abs(expected)))return bad("native_tet_positive_bl_layer_geometry_invalid");if(std::stoll(kv["layer_record_count"])!=req||std::stoll(kv["wall_edge_binding_count"])<=0||!validate_positive_layer_records(safe(kv["layer_path"]),static_cast<int>(req)))return bad("native_tet_positive_bl_binding_incomplete");}catch(...){return bad("native_tet_positive_bl_layer_field_invalid");}if(artifact.canonical_sha256==baseline_artifact.canonical_sha256||kv["baseline_digest"]==kv["candidate_digest"]||kv["bl0_exact_identity"]=="true")return bad("native_tet_positive_bl_clone_or_identity");}else if(artifact.canonical_sha256!=baseline_artifact.canonical_sha256||kv["baseline_digest"]!=kv["candidate_digest"]||kv["bl0_exact_identity"]!="true")return bad("native_tet_bl0_identity_failed");
 py::list tris;std::map<int,std::set<int>>cell_vertices;std::map<int,int>face_counts;for(size_t i=0;i<artifact.faces.size();++i){for(int id:artifact.faces[i]){cell_vertices[artifact.owner[i]].insert(id);}++face_counts[artifact.owner[i]];if(i<artifact.neighbour.size()){cell_vertices[artifact.neighbour[i]].insert(artifact.faces[i].begin(),artifact.faces[i].end());++face_counts[artifact.neighbour[i]];}}for(const auto&[start,count]:artifact.boundary_ranges)for(int i=0;i<count;++i){py::list row;for(int id:artifact.faces[start+i])row.append(id);tris.append(row);}py::list cells;std::vector<P> pts;for(const auto&p:artifact.points)pts.push_back({p[0],p[1],p[2]});
 for(const auto&[id,verts]:cell_vertices){
  if(verts.size()!=4||face_counts[id]!=4)return bad("native_tet_cell_structure_invalid");
  P centroid{};for(int v:verts){centroid.x+=artifact.points[v][0];centroid.y+=artifact.points[v][1];centroid.z+=artifact.points[v][2];}
  centroid.x/=4.;centroid.y/=4.;centroid.z/=4.;double oriented_volume=0.;
  for(size_t fi=0;fi<artifact.faces.size();++fi){int sign=artifact.owner[fi]==id?1:((fi<artifact.neighbour.size()&&artifact.neighbour[fi]==id)?-1:0);if(!sign)continue;const auto&f=artifact.faces[fi];P a{artifact.points[f[0]][0],artifact.points[f[0]][1],artifact.points[f[0]][2]};P b{artifact.points[f[1]][0],artifact.points[f[1]][1],artifact.points[f[1]][2]};P d{artifact.points[f[2]][0],artifact.points[f[2]][1],artifact.points[f[2]][2]};oriented_volume+=sign*dot(sub(a,centroid),cross(sub(b,centroid),sub(d,centroid)))/6.;}
  if(!(oriented_volume>1e-14))return bad("volume_geometry_failed");
  std::vector<int> ordered(verts.begin(),verts.end());std::sort(ordered.begin(),ordered.end());if(cell_volume(pts,ordered)<=0.)std::swap(ordered[0],ordered[1]);if(cell_volume(pts,ordered)<=0.)return bad("volume_geometry_failed");py::list row;for(int v:ordered)row.append(v);cells.append(row);
 }
 if(positive){for(const auto&b:bindings){for(int id:b.final_front_face_ids)if(id<0||static_cast<size_t>(id)>=artifact.faces.size())return bad("native_tet_positive_bl_final_face_id_invalid");for(int id:b.final_wall_face_ids)if(id<0||static_cast<size_t>(id)>=artifact.faces.size())return bad("native_tet_positive_bl_final_face_id_invalid");for(int id:b.final_cell_ids)if(!cell_vertices.count(id))return bad("native_tet_positive_bl_final_cell_id_invalid");}}
 py::list point_rows;for(const auto&p:artifact.points)point_rows.append(py::make_tuple(p[0],p[1],p[2]));
 py::dict authority;authority["accepted"]=true;authority["receipt_sealed"]=true;authority["receipt_digest"]="native-tet-polymesh-authority";authority["runtime_route"]="default_off";authority["direct_lineage"]=true;authority["source_sha256"]=kv["source_sha256"];py::dict ledger;ledger["schema"]="native-l2-authoritative-ledger/v1";ledger["immutable"]=true;ledger["source_sha256"]=kv["source_sha256"];ledger["source_faces"]=source_faces;py::dict manifest;manifest["schema"]="native-l2-evidence-manifest/v1";manifest["engine"]="native_tet";manifest["output_sha256"]=artifact.canonical_sha256;manifest["build_sha256"]=kv["build_sha256"];manifest["config_sha256"]=kv["config_sha256"];py::list rs,ro;for(int i=0;i<3;++i){rs.append(kv["source_sha256"]);ro.append(run_hashes[i]);}manifest["repeat_source_sha256"]=rs;manifest["repeat_output_sha256"]=ro;manifest["bl0_exact_identity"]=!positive;manifest["total_thickness"]=positive?std::stod(kv["total_thickness"]):0.;manifest["thickness_monotone"]=true;manifest["growth_ratio_error"]=0.;
 std::string tree_raw;for(const auto&name:std::array<std::string,5>{"points","faces","owner","neighbour","boundary"}){bool local=false;auto raw=read_file(poly_path/name,local);if(!local)return bad("native_tet_artifact_file_missing");tree_raw+=name;tree_raw.push_back('\0');tree_raw+=raw;tree_raw.push_back('\0');}
 auto result=audit("native_tet",py::bytes(source_raw),py::bytes(tree_raw),authority,ledger,manifest,py_bindings(bindings),point_rows,tris,py::list(),cells,req,actual,kv["baseline_digest"],kv["candidate_digest"]);if(!result["accepted"].cast<bool>())return result;result["status"]="native_tet_polymesh_persisted_sealed";result["artifact_format"]=autotessell_tet_polymesh::kArtifactFormat;result["artifact_tree_sha256"]=artifact.canonical_sha256;result["reader_native"]=true;result["geometry_recomputed"]=true;if(!positive){result["wall_front_status"]="not_applicable_bl0";return result;}std::vector<double>angles,outplane;for(const auto&b:bindings){std::string face=!b.source_face.empty()?b.source_face:b.source_face_a;bool geom_ok=false;auto ns=source_face_normal(pts,source_vertices,face,geom_ok);if(!geom_ok||b.wall0<0||b.wall1<0||b.front0<0||b.front1<0||static_cast<size_t>(b.wall0)>=pts.size()||static_cast<size_t>(b.wall1)>=pts.size()||static_cast<size_t>(b.front0)>=pts.size()||static_cast<size_t>(b.front1)>=pts.size())return bad("native_tet_positive_bl_wall_front_binding_invalid");P t=sub(pts[b.wall1],pts[b.wall0]);double tn=norm(t);if(tn<=1e-14)return bad("native_tet_positive_bl_wall_edge_degenerate");t={t.x/tn,t.y/tn,t.z/tn};P n=ns[0],u=cross(n,t);double un=norm(u);if(un<=1e-14)return bad("native_tet_positive_bl_tangent_degenerate");u={u.x/un,u.y/un,u.z/un};P d={(pts[b.front0].x+pts[b.front1].x-pts[b.wall0].x-pts[b.wall1].x)/2.,(pts[b.front0].y+pts[b.front1].y-pts[b.wall0].y-pts[b.wall1].y)/2.,(pts[b.front0].z+pts[b.front1].z-pts[b.wall0].z-pts[b.wall1].z)/2.};double dn=norm(d);if(dn<=1e-14)return bad("native_tet_positive_bl_front_degenerate");P dt={d.x-n.x*dot(d,n),d.y-n.y*dot(d,n),d.z-n.z*dot(d,n)};double theta=std::atan2(std::abs(dot(dt,t)),std::abs(dot(dt,u)))*180./3.141592653589793;double op=std::asin(std::min(1.,std::abs(dot(d,n))/dn))*180./3.141592653589793;if(!std::isfinite(theta)||theta>25.)return bad("native_tet_positive_bl_wall_front_quality_failed");angles.push_back(theta);outplane.push_back(op);}auto q=result["quality"].cast<py::dict>();q["max_wall_front_orthogonality_degrees"]=angles.empty()?0.:*std::max_element(angles.begin(),angles.end());q["p95_wall_front_orthogonality_degrees"]=p95(angles);q["max_wall_front_out_of_plane_degrees"]=outplane.empty()?0.:*std::max_element(outplane.begin(),outplane.end());q["aspect_cap"]=std::stod(kv["quality_aspect_cap"]);result["wall_front_status"]="cxx_geometry_recomputed";result["status"]="native_tet_positive_bl_persisted_sealed";return result;
}

PYBIND11_MODULE(native_l2_evidence_audit,m){m.doc()="Private C++23 content-addressed L2 evidence audit";m.def("audit_native_l2_evidence",&audit,py::arg("engine"),py::arg("source_bytes"),py::arg("output_bytes"),py::arg("authority_receipt"),py::arg("authoritative_ledger"),py::arg("manifest"),py::arg("boundary_binding"),py::arg("points"),py::arg("triangles"),py::arg("quads"),py::arg("cells"),py::arg("requested_layers"),py::arg("actual_layers"),py::arg("baseline_digest"),py::arg("candidate_digest"));m.def("audit_native_l2_persisted_evidence",&audit_persisted,py::arg("evidence_root"));m.def("audit_native_tet_polymesh_persisted_evidence",&audit_persisted_tet,py::arg("evidence_root"));}
