// C++23 authoritative STL ingress for smooth surface BL corpus admission.
// It recomputes source bytes, canonical facet/vertex IDs, and boundary edges;
// the sidecar supplies semantic meaning and directed wall ownership.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include "surface_bl_front_shared/brep_evidence_sha256.hpp"

namespace py = pybind11;
using VertexKey = std::array<std::uint32_t, 3>;
using EdgeKey = std::array<std::int64_t, 2>;

namespace {

struct EdgeUse { std::int64_t face; std::int64_t first; std::int64_t second; };
struct ParsedStl {
    std::string format;
    std::vector<std::array<std::int64_t, 3>> facets;
    std::map<VertexKey, std::int64_t> vertices;
    std::map<EdgeKey, std::vector<EdgeUse>> edges;
};

py::dict refuse(const std::string& reason) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "stl_authority_refused";
    result["reason"] = reason;
    result["eligible_for_surface_bl"] = false;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["candidate_discarded"] = true;
    return result;
}

bool digest(const std::string& value) {
    if (value.size() != 64) return false;
    for (const char ch : value) if (!(ch >= '0' && ch <= '9') && !(ch >= 'a' && ch <= 'f')) return false;
    return true;
}

std::uint32_t u32le(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
    if (offset + 4U > bytes.size()) throw std::runtime_error("stl_truncated");
    return static_cast<std::uint32_t>(bytes[offset]) |
           (static_cast<std::uint32_t>(bytes[offset + 1U]) << 8U) |
           (static_cast<std::uint32_t>(bytes[offset + 2U]) << 16U) |
           (static_cast<std::uint32_t>(bytes[offset + 3U]) << 24U);
}

VertexKey vertex_key(const std::uint8_t* raw) {
    VertexKey key{};
    std::memcpy(key.data(), raw, sizeof(key));
    return key;
}

EdgeKey edge_key(std::int64_t a, std::int64_t b) { return a < b ? EdgeKey{a, b} : EdgeKey{b, a}; }

void add_facet(ParsedStl& parsed, const std::array<VertexKey, 3>& keys) {
    std::array<std::int64_t, 3> ids{};
    for (std::size_t i = 0; i < 3U; ++i) {
        const auto [it, inserted] = parsed.vertices.emplace(keys[i], parsed.vertices.size());
        ids[i] = it->second;
        (void)inserted;
    }
    const std::int64_t face = static_cast<std::int64_t>(parsed.facets.size());
    parsed.facets.push_back(ids);
    for (std::size_t i = 0; i < 3U; ++i) {
        const std::int64_t first = ids[i];
        const std::int64_t second = ids[(i + 1U) % 3U];
        parsed.edges[edge_key(first, second)].push_back({face, first, second});
    }
}

ParsedStl parse_stl(const std::vector<std::uint8_t>& bytes) {
    ParsedStl parsed;
    if (bytes.size() >= 84U) {
        const std::uint64_t count = u32le(bytes, 80U);
        const std::uint64_t expected = 84U + count * 50U;
        if (expected == bytes.size()) {
            parsed.format = "binary_stl";
            for (std::uint64_t face = 0; face < count; ++face) {
                const std::size_t base = 84U + static_cast<std::size_t>(face) * 50U;
                std::array<VertexKey, 3> keys{};
                for (std::size_t vertex = 0; vertex < 3U; ++vertex) keys[vertex] = vertex_key(bytes.data() + base + 12U + vertex * 12U);
                add_facet(parsed, keys);
            }
            return parsed;
        }
    }
    parsed.format = "ascii_stl";
    std::string text(bytes.begin(), bytes.end());
    std::istringstream stream(text);
    std::string token;
    while (stream >> token) {
        if (token != "facet") continue;
        std::string normal;
        double nx = 0.0, ny = 0.0, nz = 0.0;
        if (!(stream >> normal >> nx >> ny >> nz) || normal != "normal") throw std::runtime_error("ascii_stl_facet_invalid");
        std::array<VertexKey, 3> keys{};
        for (std::size_t vertex = 0; vertex < 3U; ++vertex) {
            bool found = false;
            while (stream >> token) {
                if (token == "vertex") {
                    float x = 0.0F, y = 0.0F, z = 0.0F;
                    if (!(stream >> x >> y >> z)) throw std::runtime_error("ascii_stl_vertex_invalid");
                    std::array<float, 3> values{x, y, z};
                    std::memcpy(keys[vertex].data(), values.data(), sizeof(values));
                    found = true;
                    break;
                }
            }
            if (!found) throw std::runtime_error("ascii_stl_vertex_missing");
        }
        add_facet(parsed, keys);
    }
    if (parsed.facets.empty()) throw std::runtime_error("stl_facets_missing");
    return parsed;
}

std::vector<std::uint8_t> read_bytes(const std::string& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("stl_source_unreadable");
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

bool text(const py::dict& value, const char* key) {
    return value.contains(key) && py::isinstance<py::str>(value[key]) && !value[key].cast<std::string>().empty();
}

bool sequential_ids(const py::handle& handle, std::size_t count) {
    if (!py::isinstance<py::list>(handle)) return false;
    const py::list values = handle.cast<py::list>();
    if (values.size() != count) return false;
    for (std::size_t index = 0; index < count; ++index) {
        try { if (py::cast<std::int64_t>(values[index]) != static_cast<std::int64_t>(index)) return false; }
        catch (...) { return false; }
    }
    return true;
}

py::dict validate_file(const std::string& path, const py::dict& sidecar, const std::string& sidecar_sha256) {
    if (!digest(sidecar_sha256)) return refuse("sidecar_digest_invalid");
    std::vector<std::uint8_t> bytes;
    ParsedStl parsed;
    try {
        bytes = read_bytes(path);
        parsed = parse_stl(bytes);
    } catch (const std::exception& error) {
        return refuse(error.what());
    }
    const std::string raw_sha256 = brep_evidence::sha256_hex(bytes);
    if (!text(sidecar, "schema") || sidecar["schema"].cast<std::string>() != "NativeSurfaceAuthoritySidecar/v2") return refuse("sidecar_schema_unsupported");
    if (!text(sidecar, "source_kind") || sidecar["source_kind"].cast<std::string>() != "stl") return refuse("source_kind_invalid");
    if (!text(sidecar, "source_sha256") || sidecar["source_sha256"].cast<std::string>() != raw_sha256) return refuse("source_digest_mismatch");
    if (!text(sidecar, "provenance") || !sidecar.contains("physical_group_map") || !py::isinstance<py::dict>(sidecar["physical_group_map"]) || sidecar["physical_group_map"].cast<py::dict>().empty()) return refuse("semantic_authority_incomplete");
    const auto facet_count = parsed.facets.size();
    const auto vertex_count = parsed.vertices.size();
    std::set<EdgeKey> boundary_edges;
    for (const auto& [edge, uses] : parsed.edges) if (uses.size() == 1U) boundary_edges.insert(edge);
    try {
        if (sidecar["entity_count"].cast<std::int64_t>() != static_cast<std::int64_t>(facet_count)) return refuse("facet_count_mismatch");
        if (sidecar["canonical_facet_count"].cast<std::int64_t>() != static_cast<std::int64_t>(facet_count)) return refuse("canonical_facet_count_mismatch");
        if (sidecar["canonical_vertex_count"].cast<std::int64_t>() != static_cast<std::int64_t>(vertex_count)) return refuse("canonical_vertex_count_mismatch");
        if (sidecar["canonical_boundary_edge_count"].cast<std::int64_t>() != static_cast<std::int64_t>(boundary_edges.size())) return refuse("canonical_boundary_edge_count_mismatch");
    } catch (...) { return refuse("canonical_count_missing"); }
    if (!sequential_ids(sidecar["canonical_facet_ids"], facet_count) || !sequential_ids(sidecar["canonical_vertex_ids"], vertex_count)) return refuse("canonical_id_sequence_invalid");
    if (!text(sidecar, "source_format") || sidecar["source_format"].cast<std::string>() != parsed.format) return refuse("source_format_mismatch");
    if (!py::isinstance<py::list>(sidecar["entities"]) || sidecar["entities"].cast<py::list>().size() != facet_count) return refuse("entity_authority_incomplete");
    const py::list entities = sidecar["entities"].cast<py::list>();
    for (std::size_t index = 0; index < facet_count; ++index) {
        if (!py::isinstance<py::dict>(entities[index])) return refuse("entity_authority_incomplete");
        const py::dict entity = entities[index].cast<py::dict>();
        try { if (entity["entity_id"].cast<std::int64_t>() != static_cast<std::int64_t>(index)) return refuse("entity_id_sequence_invalid"); }
        catch (...) { return refuse("entity_label_incomplete"); }
        for (const char* key : {"patch", "feature", "physical_group", "component"}) if (!text(entity, key)) return refuse("entity_label_incomplete");
    }
    if (!py::isinstance<py::list>(sidecar["directed_wall_curves"])) return refuse("directed_wall_curve_missing");
    const py::list curves = sidecar["directed_wall_curves"].cast<py::list>();
    std::set<EdgeKey> covered;
    std::set<std::pair<std::int64_t, std::int64_t>> directed;
    for (const py::handle& item : curves) {
        if (!py::isinstance<py::dict>(item)) return refuse("wall_curve_record_invalid");
        const py::dict curve = item.cast<py::dict>();
        if (!text(curve, "curve_id") || !py::isinstance<py::list>(curve["directed_edges"])) return refuse("wall_curve_direction_missing");
        for (const py::handle& edge_item : curve["directed_edges"].cast<py::list>()) {
            if (!py::isinstance<py::sequence>(edge_item)) return refuse("wall_curve_edge_invalid");
            const py::sequence edge = edge_item.cast<py::sequence>();
            if (edge.size() != 3U) return refuse("wall_curve_edge_invalid");
            std::int64_t first = 0, second = 0, face = 0;
            try { first = edge[0].cast<std::int64_t>(); second = edge[1].cast<std::int64_t>(); face = edge[2].cast<std::int64_t>(); }
            catch (...) { return refuse("wall_curve_edge_invalid"); }
            const EdgeKey key = edge_key(first, second);
            const auto it = parsed.edges.find(key);
            if (it == parsed.edges.end() || it->second.size() != 1U || it->second.front().face != face) return refuse("wall_curve_face_binding_mismatch");
            if (!directed.insert({first, second}).second || directed.contains({second, first}) || !covered.insert(key).second) return refuse("wall_curve_duplicate_or_reversed_edge");
        }
    }
    if (covered != boundary_edges) return refuse(boundary_edges.empty() ? "unexpected_wall_curve" : "wall_curve_coverage_incomplete");
    py::dict result;
    result["accepted"] = true;
    result["status"] = "stl_authority_verified_native_readback";
    result["eligible_for_surface_bl"] = true;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["candidate_discarded"] = false;
    result["source_sha256"] = raw_sha256;
    result["source_format"] = parsed.format;
    result["facet_count"] = facet_count;
    result["vertex_count"] = vertex_count;
    result["boundary_edge_count"] = boundary_edges.size();
    result["sidecar_sha256"] = sidecar_sha256;
    result["canonical_ids_verified"] = true;
    result["directed_wall_edges_verified"] = true;
    return result;
}

}  // namespace

PYBIND11_MODULE(native_surface_stl_authority_ingress, module) {
    module.doc() = "C++23 authoritative STL source and directed wall-edge ingress";
    module.def("validate_stl_file", &validate_file,
               py::arg("source_path"), py::arg("sidecar"), py::arg("sidecar_sha256"));
}
