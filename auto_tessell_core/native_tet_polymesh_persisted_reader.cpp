#include "native_tet_polymesh_persisted_reader.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <filesystem>
#include <cmath>
#include <fstream>
#include <limits>
#include <regex>
#include <sstream>
#include <set>
#include <string>
#include <vector>

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

namespace autotessell_tet_polymesh {
namespace {

std::string trim(const std::string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

bool read_regular(const std::filesystem::path& path, std::string& output) {
    if (std::filesystem::is_symlink(path) || !std::filesystem::is_regular_file(path)) return false;
    std::ifstream stream(path, std::ios::binary);
    if (!stream) return false;
    std::ostringstream buffer;
    buffer << stream.rdbuf();
    output = buffer.str();
    return true;
}

bool list_lines(const std::string& raw, std::vector<std::string>& lines) {
    std::istringstream stream(raw);
    std::string line;
    bool inside = false;
    while (std::getline(stream, line)) {
        const auto value = trim(line);
        if (value == "(") {
            inside = true;
            continue;
        }
        if (inside && value == ")") return true;
        if (inside && !value.empty()) lines.push_back(value);
    }
    return false;
}

bool parse_points(const std::string& raw, std::vector<std::array<double, 3>>& output) {
    std::vector<std::string> lines;
    if (!list_lines(raw, lines)) return false;
    for (const auto& line : lines) {
        const auto left = line.find('(');
        const auto right = line.rfind(')');
        if (left == std::string::npos || right <= left) return false;
        std::istringstream row(line.substr(left + 1, right - left - 1));
        std::array<double, 3> point{};
        if (!(row >> point[0] >> point[1] >> point[2])) return false;
        if (!std::all_of(point.begin(), point.end(), [](double value) { return std::isfinite(value); })) return false;
        output.push_back(point);
    }
    return !output.empty();
}

bool parse_faces(const std::string& raw, std::vector<std::vector<int>>& output) {
    std::vector<std::string> lines;
    if (!list_lines(raw, lines)) return false;
    for (const auto& line : lines) {
        const auto left = line.find('(');
        const auto right = line.rfind(')');
        if (left == std::string::npos || right <= left) return false;
        int count = 0;
        std::istringstream prefix(line.substr(0, left));
        if (!(prefix >> count) || count != 3) return false;
        std::istringstream row(line.substr(left + 1, right - left - 1));
        std::vector<int> face(3);
        if (!(row >> face[0] >> face[1] >> face[2])) return false;
        if (std::set<int>(face.begin(), face.end()).size() != 3) return false;
        output.push_back(std::move(face));
    }
    return !output.empty();
}

bool parse_ints(const std::string& raw, std::vector<int>& output) {
    std::vector<std::string> lines;
    if (!list_lines(raw, lines)) return false;
    for (const auto& line : lines) {
        std::istringstream row(line);
        int value = 0;
        if (!(row >> value)) return false;
        output.push_back(value);
    }
    return true;
}

bool parse_boundary(const std::string& raw, std::vector<std::pair<int, int>>& output) {
    const std::regex pattern(R"(nFaces\s+([0-9]+)\s*;\s*startFace\s+([0-9]+)\s*;)");
    for (std::sregex_iterator it(raw.begin(), raw.end(), pattern), end; it != end; ++it) {
        output.emplace_back(std::stoi((*it)[2]), std::stoi((*it)[1]));
    }
    return !output.empty();
}

std::string digest(const std::array<std::string, 5>& names, const std::array<std::string, 5>& raw) {
    std::string bytes;
    for (std::size_t index = 0; index < names.size(); ++index) {
        bytes += names[index];
        bytes.push_back('\0');
        bytes += raw[index];
        bytes.push_back('\0');
    }
    return brep_evidence::sha256_hex(std::vector<std::uint8_t>(bytes.begin(), bytes.end()));
}

}  // namespace

bool read_artifact(const std::filesystem::path& root, Artifact& artifact) {
    const std::array<std::string, 5> names = {"points", "faces", "owner", "neighbour", "boundary"};
    std::array<std::string, 5> raw{};
    for (std::size_t index = 0; index < names.size(); ++index) {
        if (!read_regular(root / names[index], raw[index])) {
            artifact.error = "polymesh_file_missing";
            return false;
        }
    }
    if (!parse_points(raw[0], artifact.points) || !parse_faces(raw[1], artifact.faces) ||
        !parse_ints(raw[2], artifact.owner) || !parse_ints(raw[3], artifact.neighbour) ||
        !parse_boundary(raw[4], artifact.boundary_ranges)) {
        artifact.error = "polymesh_ascii_parse_failed";
        return false;
    }
    if (artifact.owner.size() != artifact.faces.size() || artifact.neighbour.size() > artifact.faces.size()) {
        artifact.error = "polymesh_incidence_size_invalid";
        return false;
    }
    int cells = 0;
    for (const int owner : artifact.owner) {
        if (owner < 0) {
            artifact.error = "polymesh_owner_invalid";
            return false;
        }
        cells = std::max(cells, owner + 1);
    }
    for (const int neighbour : artifact.neighbour) {
        if (neighbour < 0 || neighbour >= cells) {
            artifact.error = "polymesh_neighbour_invalid";
            return false;
        }
    }
    for (const auto& face : artifact.faces) {
        for (const int vertex : face) {
            if (vertex < 0 || static_cast<std::size_t>(vertex) >= artifact.points.size()) {
                artifact.error = "polymesh_face_vertex_invalid";
                return false;
            }
        }
    }
    int cursor = static_cast<int>(artifact.neighbour.size());
    for (const auto& [start, count] : artifact.boundary_ranges) {
        if (count < 0 || start != cursor || start < 0 || start + count > static_cast<int>(artifact.faces.size())) {
            artifact.error = "polymesh_boundary_range_invalid";
            return false;
        }
        cursor = start + count;
    }
    if (cursor != static_cast<int>(artifact.faces.size())) {
        artifact.error = "polymesh_boundary_coverage_gap";
        return false;
    }
    artifact.canonical_sha256 = digest(names, raw);
    return true;
}

}  // namespace autotessell_tet_polymesh
