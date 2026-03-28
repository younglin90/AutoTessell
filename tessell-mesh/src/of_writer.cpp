/**
 * OpenFOAM polyMesh writer
 *
 * Converts tessell::Mesh3D / tessell::Mesh2D into OpenFOAM's binary-ASCII
 * constant/polyMesh/ directory layout:
 *
 *   points      — vertex coordinates
 *   faces       — face → vertex connectivity (internal faces first, then boundary)
 *   owner       — face → owning cell (lower cell-id side)
 *   neighbour   — face → neighbour cell (internal faces only)
 *   boundary    — named patch descriptors
 *
 * For 2-D: triangulation is extruded one cell thick in +z.
 * Front/back faces use the "empty" boundary type for 2-D OpenFOAM flow.
 */

#include <tessell/of_writer.hpp>

#include <algorithm>
#include <array>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>
#include <unordered_map>

namespace fs = std::filesystem;

namespace tessell {

namespace {

// ──────────────────────────────────────────────────────────────
// OpenFOAM file header helpers
// ──────────────────────────────────────────────────────────────

void write_header(std::ofstream& f,
                  const std::string& object_name,
                  const std::string& class_name = "labelList")
{
    f << "FoamFile\n{\n"
      << "    version     2.0;\n"
      << "    format      ascii;\n"
      << "    class       " << class_name << ";\n"
      << "    object      " << object_name << ";\n"
      << "}\n\n";
}

// ──────────────────────────────────────────────────────────────
// Face canonicalization (for internal-face detection)
// ──────────────────────────────────────────────────────────────

// A face sorted for map lookup (canonical key)
using FaceKey = std::array<int, 4>;  // tri → [a,b,c,−1]; quad → [a,b,c,d] sorted

FaceKey make_face_key(const Tri& t) {
    FaceKey k = {t[0], t[1], t[2], -1};
    std::sort(k.begin(), k.begin() + 3);
    return k;
}

// ──────────────────────────────────────────────────────────────
// 3-D tet → polyMesh conversion
// ──────────────────────────────────────────────────────────────

struct OFMesh {
    std::vector<Vec3> points;

    // Each face as a list of vertex indices (stored as Tri for tet meshes)
    std::vector<Tri>  faces;

    // owner[i] = cell that owns face i
    // neighbour[i] = neighbour cell (−1 if boundary face)
    std::vector<int>  owner;
    std::vector<int>  neighbour;

    // Named patches: (name, type, startFace, nFaces)
    struct Patch { std::string name, type; int start, n; };
    std::vector<Patch> patches;
};

OFMesh convert_tet_mesh(const Mesh3D& mesh) {
    // Map: sorted face → (tet_A, local_face_in_A)
    //      If a second tet shares the face → internal face
    struct FaceRecord {
        int tet;    // first tet to own this face
        int face;   // the outward-oriented face (vertices in this order)
    };
    std::map<FaceKey, FaceRecord> seen;

    // Each tet has 4 triangular faces; local vertex orders for outward normals:
    //   face 0: (0,2,1)  face 1: (0,1,3)  face 2: (1,2,3)  face 3: (2,0,3)
    // (right-hand rule, outward from centroid)
    static const int TET_FACES[4][3] = {
        {0, 2, 1},
        {0, 1, 3},
        {1, 2, 3},
        {2, 0, 3},
    };

    std::vector<Tri> int_faces, bnd_faces;
    std::vector<int> int_owner, int_neigh, bnd_owner;

    int n_tets = (int)mesh.tets.size();
    for (int c = 0; c < n_tets; ++c) {
        const Tet& tet = mesh.tets[c];
        for (int lf = 0; lf < 4; ++lf) {
            Tri face = {
                tet[TET_FACES[lf][0]],
                tet[TET_FACES[lf][1]],
                tet[TET_FACES[lf][2]]
            };
            FaceKey key = make_face_key(face);
            auto it = seen.find(key);
            if (it == seen.end()) {
                seen[key] = {c, (int)bnd_faces.size()};
                bnd_faces.push_back(face);
                bnd_owner.push_back(c);
            } else {
                // Second tet sees this face → internal face
                // Orientation: outward from lower-id tet
                int other_tet = it->second.tet;
                int slot      = it->second.face;

                if (other_tet < c) {
                    int_faces.push_back(bnd_faces[slot]);
                    int_owner.push_back(other_tet);
                    int_neigh.push_back(c);
                } else {
                    int_faces.push_back(face);
                    int_owner.push_back(c);
                    int_neigh.push_back(other_tet);
                }
                // Remove from bnd lists
                bnd_faces.erase(bnd_faces.begin() + slot);
                bnd_owner.erase(bnd_owner.begin() + slot);
                // Update all slots after this one
                for (auto& s : seen) {
                    if (s.second.face > slot) --s.second.face;
                }
                seen.erase(it);
            }
        }
    }

    // Sort internal faces by (owner, neighbour)
    std::vector<int> int_idx(int_faces.size());
    std::iota(int_idx.begin(), int_idx.end(), 0);
    std::sort(int_idx.begin(), int_idx.end(), [&](int a, int b) {
        if (int_owner[a] != int_owner[b]) return int_owner[a] < int_owner[b];
        return int_neigh[a] < int_neigh[b];
    });

    OFMesh of;
    of.points = mesh.vertices;

    // Internal faces first
    for (int i : int_idx) {
        of.faces.push_back(int_faces[i]);
        of.owner.push_back(int_owner[i]);
        of.neighbour.push_back(int_neigh[i]);
    }

    // Then boundary faces (one patch for now: "walls")
    int start = (int)of.faces.size();
    for (int i = 0; i < (int)bnd_faces.size(); ++i) {
        of.faces.push_back(bnd_faces[i]);
        of.owner.push_back(bnd_owner[i]);
        of.neighbour.push_back(-1);
    }

    if (!bnd_faces.empty()) {
        of.patches.push_back({"walls", "wall", start, (int)bnd_faces.size()});
    }

    return of;
}

// ──────────────────────────────────────────────────────────────
// Write helpers
// ──────────────────────────────────────────────────────────────

void write_points(const fs::path& dir, const std::vector<Vec3>& pts) {
    std::ofstream f(dir / "points");
    write_header(f, "points", "vectorField");
    f << pts.size() << "\n(\n";
    f << std::scientific;
    f.precision(10);
    for (const auto& p : pts) {
        f << "( " << p[0] << " " << p[1] << " " << p[2] << " )\n";
    }
    f << ")\n";
}

void write_faces(const fs::path& dir, const std::vector<Tri>& faces) {
    std::ofstream f(dir / "faces");
    write_header(f, "faces", "faceList");
    f << faces.size() << "\n(\n";
    for (const auto& tri : faces) {
        f << "3( " << tri[0] << " " << tri[1] << " " << tri[2] << " )\n";
    }
    f << ")\n";
}

void write_owner(const fs::path& dir, const std::vector<int>& owner,
                 int n_cells, int n_int_faces)
{
    std::ofstream f(dir / "owner");
    write_header(f, "owner");
    f << "// nCells: " << n_cells << "  nInternalFaces: " << n_int_faces << "\n";
    f << owner.size() << "\n(\n";
    for (int v : owner) f << v << "\n";
    f << ")\n";
}

void write_neighbour(const fs::path& dir, const std::vector<int>& neighbour,
                     int n_int_faces)
{
    std::vector<int> int_neigh(neighbour.begin(),
                               neighbour.begin() + n_int_faces);
    std::ofstream f(dir / "neighbour");
    write_header(f, "neighbour");
    f << int_neigh.size() << "\n(\n";
    for (int v : int_neigh) f << v << "\n";
    f << ")\n";
}

void write_boundary(const fs::path& dir,
                    const std::vector<OFMesh::Patch>& patches)
{
    std::ofstream f(dir / "boundary");
    write_header(f, "boundary", "polyBoundaryMesh");
    f << patches.size() << "\n(\n";
    for (const auto& p : patches) {
        f << "    " << p.name << "\n    {\n"
          << "        type       " << p.type << ";\n"
          << "        nFaces     " << p.n    << ";\n"
          << "        startFace  " << p.start << ";\n"
          << "    }\n";
    }
    f << ")\n";
}

} // anonymous namespace

// ──────────────────────────────────────────────────────────────
// Public API: 3-D
// ──────────────────────────────────────────────────────────────

void write_openfoam_3d(const std::string& case_dir,
                       const Mesh3D& mesh,
                       const OFWriteOptions& /*opts*/)
{
    fs::path poly = fs::path(case_dir) / "constant" / "polyMesh";
    fs::create_directories(poly);

    OFMesh of = convert_tet_mesh(mesh);

    int n_int = (int)of.neighbour.size();

    // Count cells
    int n_cells = (int)mesh.tets.size();

    write_points(poly, of.points);
    write_faces(poly, of.faces);
    write_owner(poly, of.owner, n_cells, n_int);
    write_neighbour(poly, of.neighbour, n_int);
    write_boundary(poly, of.patches);
}

// ──────────────────────────────────────────────────────────────
// Public API: 2-D (extrude triangulation one cell thick)
// ──────────────────────────────────────────────────────────────

void write_openfoam_2d(const std::string& case_dir,
                       const Mesh2D& mesh2d,
                       const OFWriteOptions& opts)
{
    double dz = opts.extrude_thickness;

    // Build 3-D points: bottom layer (z=0) then top layer (z=dz)
    int nv = (int)mesh2d.vertices.size();
    std::vector<Vec3> points3d;
    points3d.reserve(2 * nv);
    for (const auto& v : mesh2d.vertices) {
        points3d.push_back({v[0], v[1], 0.0});
    }
    for (const auto& v : mesh2d.vertices) {
        points3d.push_back({v[0], v[1], dz});
    }
    // Bottom vertex i → index i
    // Top vertex i    → index i + nv

    // Each 2-D triangle → one prism (wedge): 2 tri faces + 3 quad side faces
    // Prism vertices: (b0,b1,b2) bottom, (t0,t1,t2) top
    // In OF we use triangular faces (tris) for the end caps and quads for sides.

    // For simplicity we split each quad side face into 2 triangles.
    // OF supports quad faces; let's use quads for the sides.

    int nt = (int)mesh2d.triangles.size();

    // Build face lists
    struct QuadFace { std::array<int,4> v; };
    std::vector<Tri>      tri_faces;  // end caps
    std::vector<QuadFace> quad_faces; // side walls
    std::vector<int>      owner_all;
    std::vector<int>      neigh_all;

    // Internal prism faces: shared between neighbouring prisms.
    // For each 2D edge shared by two triangles → internal quad face.
    // Boundary 2D edges → external quad faces (wall/inlet/outlet etc.)

    // Build edge → triangle adjacency
    std::map<std::pair<int,int>, int> edge_to_tri; // canonical edge → tri id
    for (int t = 0; t < nt; ++t) {
        for (int e = 0; e < 3; ++e) {
            int a = mesh2d.triangles[t][e];
            int b = mesh2d.triangles[t][(e+1)%3];
            auto key = std::make_pair(std::min(a,b), std::max(a,b));
            edge_to_tri[key] = t; // second insertion overwrites → gives neighbour
        }
    }

    // Count internal faces first
    std::vector<QuadFace> int_quads;
    std::vector<int>      int_owner, int_neigh;

    std::map<std::pair<int,int>, int> edge_tri_first;
    for (int t = 0; t < nt; ++t) {
        for (int e = 0; e < 3; ++e) {
            int a = mesh2d.triangles[t][e];
            int b = mesh2d.triangles[t][(e+1)%3];
            auto key = std::make_pair(std::min(a,b), std::max(a,b));
            auto it = edge_tri_first.find(key);
            if (it == edge_tri_first.end()) {
                edge_tri_first[key] = t;
            } else {
                int other = it->second;
                // Internal quad face: verts in order for correct outward normal
                // (from lower cell)
                int own = std::min(t, other);
                int nbr = std::max(t, other);
                QuadFace qf;
                qf.v = {a, b, b + nv, a + nv};
                int_quads.push_back(qf);
                int_owner.push_back(own);
                int_neigh.push_back(nbr);
            }
        }
    }

    // Boundary quad faces
    std::vector<QuadFace> bnd_quads;
    std::vector<int>      bnd_owner;
    edge_tri_first.clear();
    for (int t = 0; t < nt; ++t) {
        for (int e = 0; e < 3; ++e) {
            int a = mesh2d.triangles[t][e];
            int b = mesh2d.triangles[t][(e+1)%3];
            auto key = std::make_pair(std::min(a,b), std::max(a,b));
            auto it = edge_tri_first.find(key);
            if (it == edge_tri_first.end()) {
                edge_tri_first[key] = t;
            } else {
                edge_tri_first.erase(it); // internal, already processed
            }
        }
    }
    for (auto& [key, t] : edge_tri_first) {
        int a = key.first, b = key.second;
        QuadFace qf;
        qf.v = {a, b, b + nv, a + nv};
        bnd_quads.push_back(qf);
        bnd_owner.push_back(t);
    }

    // Bottom end caps (z=0) — "frontAndBack" empty BC
    std::vector<Tri> bot_caps, top_caps;
    for (int t = 0; t < nt; ++t) {
        Tri bot = {mesh2d.triangles[t][0], mesh2d.triangles[t][2], mesh2d.triangles[t][1]};
        Tri top = {mesh2d.triangles[t][0] + nv, mesh2d.triangles[t][1] + nv, mesh2d.triangles[t][2] + nv};
        bot_caps.push_back(bot);
        top_caps.push_back(top);
    }

    // ── Write OpenFOAM files ──
    fs::path poly = fs::path(case_dir) / "constant" / "polyMesh";
    fs::create_directories(poly);

    // points
    write_points(poly, points3d);

    // faces: internal quads | boundary quads | bottom caps | top caps
    // (OpenFOAM format: internal first, then boundary patches in order)
    {
        std::ofstream f(poly / "faces");
        write_header(f, "faces", "faceList");
        int total = (int)(int_quads.size() + bnd_quads.size() +
                          bot_caps.size() + top_caps.size());
        f << total << "\n(\n";
        for (auto& qf : int_quads) {
            f << "4( " << qf.v[0] << " " << qf.v[1] << " "
              << qf.v[2] << " " << qf.v[3] << " )\n";
        }
        for (auto& qf : bnd_quads) {
            f << "4( " << qf.v[0] << " " << qf.v[1] << " "
              << qf.v[2] << " " << qf.v[3] << " )\n";
        }
        for (auto& t : bot_caps) {
            f << "3( " << t[0] << " " << t[1] << " " << t[2] << " )\n";
        }
        for (auto& t : top_caps) {
            f << "3( " << t[0] << " " << t[1] << " " << t[2] << " )\n";
        }
        f << ")\n";
    }

    // owner / neighbour
    {
        std::ofstream fo(poly / "owner"), fn(poly / "neighbour");
        write_header(fo, "owner");
        write_header(fn, "neighbour");

        int n_int = (int)int_quads.size();
        int n_bnd = (int)bnd_quads.size() + (int)bot_caps.size() + (int)top_caps.size();
        int n_all = n_int + n_bnd;
        fo << n_all << "\n(\n";
        fn << n_int << "\n(\n";

        for (int i = 0; i < n_int; ++i) {
            fo << int_owner[i] << "\n";
            fn << int_neigh[i] << "\n";
        }
        for (int i = 0; i < (int)bnd_quads.size(); ++i) fo << bnd_owner[i] << "\n";
        for (int t = 0; t < nt; ++t) fo << t << "\n";  // bot caps
        for (int t = 0; t < nt; ++t) fo << t << "\n";  // top caps

        fo << ")\n";
        fn << ")\n";
    }

    // boundary
    {
        int start = (int)int_quads.size();
        std::ofstream f(poly / "boundary");
        write_header(f, "boundary", "polyBoundaryMesh");
        f << "3\n(\n";
        f << "    walls\n    {\n"
          << "        type       wall;\n"
          << "        nFaces     " << bnd_quads.size() << ";\n"
          << "        startFace  " << start << ";\n"
          << "    }\n";
        start += (int)bnd_quads.size();
        f << "    front\n    {\n"
          << "        type       empty;\n"
          << "        nFaces     " << bot_caps.size() << ";\n"
          << "        startFace  " << start << ";\n"
          << "    }\n";
        start += (int)bot_caps.size();
        f << "    back\n    {\n"
          << "        type       empty;\n"
          << "        nFaces     " << top_caps.size() << ";\n"
          << "        startFace  " << start << ";\n"
          << "    }\n";
        f << ")\n";
    }
}

} // namespace tessell
