#include "native_tet_polymesh_persisted_reader.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

namespace {
using Point = std::array<double, 3>;

struct SourceFace {
    std::string id;
    std::array<int, 3> vertices{};
    std::array<std::string, 5> semantics{};
};

struct CellLineage {
    std::string uid;
    std::string source_id;
    std::array<std::string, 5> semantics{};
};

Point sub(Point a, Point b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
Point cross(Point a, Point b) {
    return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]};
}
double dot(Point a, Point b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
double norm(Point a) { return std::sqrt(dot(a, a)); }

std::vector<std::string> words(const std::string& line) {
    std::istringstream input(line);
    std::vector<std::string> result;
    std::string word;
    while (input >> word) result.push_back(word);
    return result;
}

bool same_cycle(const std::array<int, 3>& expected, const std::vector<int>& actual) {
    if (actual.size() != 3) return false;
    for (int rotation = 0; rotation < 3; ++rotation) {
        if (expected[0] == actual[static_cast<std::size_t>(rotation)] &&
            expected[1] == actual[static_cast<std::size_t>((rotation + 1) % 3)] &&
            expected[2] == actual[static_cast<std::size_t>((rotation + 2) % 3)]) return true;
    }
    return false;
}

bool same_cycle(const std::vector<int>& expected, const std::vector<int>& actual) {
    if (expected.size() != 3 || actual.size() != 3) return false;
    std::array<int, 3> expected_array{expected[0], expected[1], expected[2]};
    return same_cycle(expected_array, actual);
}

std::array<int, 3> key(const std::vector<int>& face) {
    std::array<int, 3> result{face[0], face[1], face[2]};
    std::sort(result.begin(), result.end());
    return result;
}

bool read_ledger(const std::filesystem::path& path, std::vector<SourceFace>& faces,
    std::vector<CellLineage>& cells, std::string& error) {
    if (std::filesystem::is_symlink(path) || !std::filesystem::is_regular_file(path)) {
        error = "source_ledger_not_regular";
        return false;
    }
    std::ifstream input(path);
    if (!input) {
        error = "source_ledger_open_failed";
        return false;
    }
    std::string line;
    bool schema_seen = false;
    while (std::getline(input, line)) {
        const auto fields = words(line);
        if (fields.empty()) continue;
        if (fields[0] == "schema") {
            if (schema_seen || fields.size() != 2 || fields[1] != "native-tet-source-ledger/v1") {
                error = "source_ledger_schema_invalid";
                return false;
            }
            schema_seen = true;
        } else if (fields[0] == "face") {
            if (fields.size() != 10) {
                error = "source_ledger_face_invalid";
                return false;
            }
            SourceFace face;
            face.id = fields[1];
            if (face.id.empty() || faces.end() != std::find_if(faces.begin(), faces.end(),
                [&](const SourceFace& item) { return item.id == face.id; })) {
                error = "source_ledger_face_duplicate";
                return false;
            }
            for (int index = 0; index < 3; ++index) {
                try { face.vertices[static_cast<std::size_t>(index)] = std::stoi(fields[2 + index]); }
                catch (...) { error = "source_ledger_vertex_invalid"; return false; }
            }
            if (std::set<int>(face.vertices.begin(), face.vertices.end()).size() != 3) {
                error = "source_ledger_face_vertices_invalid";
                return false;
            }
            for (int index = 0; index < 5; ++index) face.semantics[static_cast<std::size_t>(index)] = fields[5 + index];
            faces.push_back(face);
        } else if (fields[0] == "cell") {
            if (fields.size() != 8) {
                error = "source_ledger_cell_invalid";
                return false;
            }
            CellLineage cell;
            cell.uid = fields[1];
            cell.source_id = fields[2];
            for (int index = 0; index < 5; ++index) cell.semantics[static_cast<std::size_t>(index)] = fields[3 + index];
            cells.push_back(cell);
        } else {
            error = "source_ledger_unknown_record";
            return false;
        }
    }
    if (!schema_seen || faces.empty() || cells.empty()) {
        error = "source_ledger_incomplete";
        return false;
    }
    return true;
}

bool reject(const std::string& reason) {
    std::cout << "accepted=false\nreason=" << reason << "\n";
    return false;
}

bool verify(const std::filesystem::path& root, const std::filesystem::path& ledger) {
    autotessell_tet_polymesh::Artifact artifact;
    if (!autotessell_tet_polymesh::read_artifact(root, artifact)) return reject(artifact.error);
    std::vector<SourceFace> source_faces;
    std::vector<CellLineage> lineages;
    std::string error;
    if (!read_ledger(ledger, source_faces, lineages, error)) return reject(error);

    std::vector<int> boundary_ids;
    for (const auto& [start, count] : artifact.boundary_ranges) {
        for (int offset = 0; offset < count; ++offset) boundary_ids.push_back(start + offset);
    }
    if (boundary_ids.size() != source_faces.size()) return reject("source_boundary_count_mismatch");
    std::set<std::string> matched_ids;
    for (const int face_id : boundary_ids) {
        std::string matched;
        for (const auto& source : source_faces) {
            if (same_cycle(source.vertices, artifact.faces[static_cast<std::size_t>(face_id)])) {
                if (!matched.empty()) return reject("source_boundary_ambiguous");
                matched = source.id;
            }
        }
        if (matched.empty() || !matched_ids.insert(matched).second) return reject("source_boundary_coverage_mismatch");
    }
    if (matched_ids.size() != source_faces.size()) return reject("source_boundary_coverage_incomplete");

    std::map<std::array<int, 3>, std::vector<int>> face_groups;
    for (std::size_t face_id = 0; face_id < artifact.faces.size(); ++face_id) {
        face_groups[key(artifact.faces[face_id])].push_back(static_cast<int>(face_id));
    }
    for (const auto& [face_key, ids] : face_groups) {
        (void)face_key;
        if (ids.size() > 2) return reject("persisted_topology_non_manifold");
        if (ids.size() == 2 && same_cycle(artifact.faces[static_cast<std::size_t>(ids[0])],
            artifact.faces[static_cast<std::size_t>(ids[1])])) return reject("persisted_topology_inverted");
    }

    const int cell_count = artifact.owner.empty() ? 0 :
        *std::max_element(artifact.owner.begin(), artifact.owner.end()) + 1;
    if (cell_count <= 0 || lineages.size() != static_cast<std::size_t>(cell_count)) return reject("cell_lineage_count_mismatch");
    std::vector<std::set<int>> vertices(static_cast<std::size_t>(cell_count));
    for (std::size_t face_id = 0; face_id < artifact.faces.size(); ++face_id) {
        const int owner = artifact.owner[face_id];
        vertices[static_cast<std::size_t>(owner)].insert(artifact.faces[face_id].begin(), artifact.faces[face_id].end());
        if (face_id < artifact.neighbour.size()) {
            vertices[static_cast<std::size_t>(artifact.neighbour[face_id])].insert(
                artifact.faces[face_id].begin(), artifact.faces[face_id].end());
        }
    }
    double min_volume6 = std::numeric_limits<double>::infinity();
    double max_aspect = 0.0;
    for (int cell = 0; cell < cell_count; ++cell) {
        if (vertices[static_cast<std::size_t>(cell)].size() != 4) return reject("persisted_cell_not_tet");
        const auto& ids = vertices[static_cast<std::size_t>(cell)];
        std::vector<int> ordered(ids.begin(), ids.end());
        const Point& p0 = artifact.points[static_cast<std::size_t>(ordered[0])];
        const Point& p1 = artifact.points[static_cast<std::size_t>(ordered[1])];
        const Point& p2 = artifact.points[static_cast<std::size_t>(ordered[2])];
        const Point& p3 = artifact.points[static_cast<std::size_t>(ordered[3])];
        const double volume6 = std::abs(dot(sub(p1, p0), cross(sub(p2, p0), sub(p3, p0))));
        if (!(std::isfinite(volume6) && volume6 > 1.0e-14)) return reject("persisted_tet_nonpositive_volume");
        min_volume6 = std::min(min_volume6, volume6);
        double min_edge = std::numeric_limits<double>::infinity();
        double max_edge = 0.0;
        for (int first = 0; first < 4; ++first) for (int second = first + 1; second < 4; ++second) {
            const double edge = norm(sub(artifact.points[static_cast<std::size_t>(ordered[first])],
                artifact.points[static_cast<std::size_t>(ordered[second])]));
            if (!(std::isfinite(edge) && edge > 1.0e-14)) return reject("persisted_tet_edge_invalid");
            min_edge = std::min(min_edge, edge);
            max_edge = std::max(max_edge, edge);
        }
        max_aspect = std::max(max_aspect, max_edge / min_edge);
        const auto& lineage = lineages[static_cast<std::size_t>(cell)];
        if (lineage.uid != "cell-" + std::to_string(cell)) return reject("cell_lineage_uid_mismatch");
        if (std::none_of(source_faces.begin(), source_faces.end(), [&](const SourceFace& face) { return face.id == lineage.source_id; })) {
            return reject("cell_lineage_source_missing");
        }
    }

    std::ostringstream certificate;
    certificate << "native-tet-persisted-volume-child/v1\n" << artifact.canonical_sha256 << '\n'
                << cell_count << '\n' << min_volume6 << '\n' << max_aspect << '\n'
                << source_faces.size() << '\n';
    const std::string bytes = certificate.str();
    const std::string digest = brep_evidence::sha256_hex(std::vector<std::uint8_t>(bytes.begin(), bytes.end()));
    std::cout << "accepted=true\nstatus=native-tet-persisted-volume-child-verified\n"
              << "artifact_serialization_sha256=" << artifact.canonical_sha256 << '\n'
              << "certificate_sha256=" << digest << '\n'
              << "cells=" << cell_count << '\n'
              << "source_faces=" << source_faces.size() << '\n'
              << "topology_duplicate=0\nnon_manifold=0\ninverted=0\n"
              << "positive_measure=true\nmax_aspect_ratio=" << max_aspect << '\n';
    return true;
}
}  // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: native_tet_persisted_volume_artifact_cli <polyMesh> <source-ledger>\n";
        return 64;
    }
    return verify(std::filesystem::path(argv[1]), std::filesystem::path(argv[2])) ? 0 : 2;
}
