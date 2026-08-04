#pragma once

#include <array>
#include <filesystem>
#include <string>
#include <utility>
#include <vector>

namespace autotessell_tet_polymesh {

inline constexpr const char* kArtifactFormat = "openfoam-polymesh-ascii/v1";

struct Artifact {
    std::vector<std::array<double, 3>> points;
    std::vector<std::vector<int>> faces;
    std::vector<int> owner;
    std::vector<int> neighbour;
    std::vector<std::pair<int, int>> boundary_ranges;
    std::string canonical_sha256;
    std::string error;
};

bool read_artifact(const std::filesystem::path& root, Artifact& artifact);

}  // namespace autotessell_tet_polymesh
