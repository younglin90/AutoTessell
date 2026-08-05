#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "native_tri_authority_source_certificate.hpp"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace py = pybind11;
namespace authority = autotessell_native_tri_authority;

namespace {

struct SemanticRow {
    std::int64_t face_id = -1;
    authority::Triangle vertices{};
    std::string feature;
    std::string patch;
    std::string physical_group;
    std::string component;
    std::string provenance;
};

py::dict refusal(const char* reason) {
    py::dict result;
    result["accepted"] = false;
    result["status"] = "native_tri_authority_source_refused";
    result["reason"] = reason;
    result["certificate_accepted"] = false;
    result["eligible_for_tri_bl"] = false;
    result["actual_layers"] = 0;
    result["publication_eligible"] = false;
    result["candidate_discarded"] = true;
    result["artifact_emitted"] = false;
    result["runtime_route"] = "private_default_off";
    result["route_calls"] = 0;
    result["generated_vertices"] = py::list();
    result["generated_faces"] = py::list();
    result["provenance"] = py::list();
    return result;
}

bool text(const py::dict& value, const char* key) {
    return value.contains(key) && !value[key].is_none() &&
           !py::str(value[key]).cast<std::string>().empty();
}

bool hex64(const std::string& value) {
    return value.size() == 64U &&
           std::all_of(value.begin(), value.end(), [](const char item) {
               return (item >= '0' && item <= '9') || (item >= 'a' && item <= 'f');
           });
}

bool integer(const py::dict& value, const char* key, std::int64_t& output) {
    if (!value.contains(key) || value[key].is_none() || py::isinstance<py::bool_>(value[key]))
        return false;
    try {
        output = value[key].cast<std::int64_t>();
        return true;
    } catch (const py::error_already_set&) {
        return false;
    }
}

std::string lower_extension(const std::filesystem::path& path) {
    std::string extension = path.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(),
                   [](const unsigned char value) { return static_cast<char>(std::tolower(value)); });
    return extension;
}

bool read_regular_file(const std::filesystem::path& path,
                       std::vector<std::uint8_t>& bytes) {
    std::error_code error;
    if (!std::filesystem::is_regular_file(path, error) ||
        std::filesystem::is_symlink(path, error))
        return false;
    std::ifstream input(path, std::ios::binary);
    if (!input) return false;
    input.seekg(0, std::ios::end);
    const auto size = input.tellg();
    if (size <= 0) return false;
    input.seekg(0, std::ios::beg);
    bytes.resize(static_cast<std::size_t>(size));
    input.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    return input.good() || input.eof();
}

bool parse_vertices(const py::handle& value, authority::Triangle& vertices) {
    if (!py::isinstance<py::sequence>(value)) return false;
    const py::sequence sequence = value.cast<py::sequence>();
    if (sequence.size() != 3) return false;
    for (int index = 0; index < 3; ++index) {
        if (py::isinstance<py::bool_>(sequence[index])) return false;
        try {
            vertices[static_cast<std::size_t>(index)] =
                sequence[index].cast<std::int64_t>();
        } catch (const py::error_already_set&) {
            return false;
        }
    }
    return true;
}

bool parse_semantic_rows(const py::list& records,
                         const authority::CanonicalSource& source,
                         std::vector<SemanticRow>& rows,
                         std::string& reason) {
    if (records.size() != source.faces.size()) {
        reason = "tri_semantic_ledger_coverage_incomplete";
        return false;
    }
    std::map<std::int64_t, SemanticRow> by_face;
    for (const py::handle& item : records) {
        if (!py::isinstance<py::dict>(item)) {
            reason = "tri_semantic_ledger_record_invalid";
            return false;
        }
        const py::dict record = item.cast<py::dict>();
        SemanticRow row;
        std::int64_t source_facet_id = -1;
        if (!integer(record, "face_id", row.face_id) ||
            !integer(record, "source_facet_id", source_facet_id) ||
            source_facet_id != row.face_id ||
            !record.contains("vertices") ||
            !parse_vertices(record["vertices"], row.vertices)) {
            reason = "tri_semantic_ledger_face_binding_invalid";
            return false;
        }
        if (row.face_id < 0 || row.face_id >= static_cast<std::int64_t>(source.faces.size()) ||
            row.vertices != source.faces[static_cast<std::size_t>(row.face_id)] ||
            by_face.contains(row.face_id)) {
            reason = "tri_semantic_ledger_face_binding_invalid";
            return false;
        }
        for (const char* key : {"feature", "patch", "physical_group", "component", "provenance"}) {
            if (!text(record, key)) {
                reason = "tri_semantic_ledger_field_missing";
                return false;
            }
        }
        row.feature = py::str(record["feature"]).cast<std::string>();
        row.patch = py::str(record["patch"]).cast<std::string>();
        row.physical_group = py::str(record["physical_group"]).cast<std::string>();
        row.component = py::str(record["component"]).cast<std::string>();
        row.provenance = py::str(record["provenance"]).cast<std::string>();
        by_face.emplace(row.face_id, row);
    }
    rows.clear();
    rows.reserve(by_face.size());
    for (std::int64_t face = 0; face < static_cast<std::int64_t>(source.faces.size()); ++face) {
        if (!by_face.contains(face)) {
            reason = "tri_semantic_ledger_face_binding_incomplete";
            return false;
        }
        rows.push_back(by_face.at(face));
    }
    return true;
}

void append_field(std::ostringstream& stream, const std::string& value) {
    stream << value.size() << ':' << value << '|';
}

std::string semantic_stream(const std::vector<SemanticRow>& rows) {
    std::ostringstream stream;
    stream << "rows=" << rows.size() << '|';
    for (const SemanticRow& row : rows) {
        stream << row.face_id << ':' << row.vertices[0] << ',' << row.vertices[1] << ','
               << row.vertices[2] << '|';
        append_field(stream, row.feature);
        append_field(stream, row.patch);
        append_field(stream, row.physical_group);
        append_field(stream, row.component);
        append_field(stream, row.provenance);
    }
    return stream.str();
}

py::list point_rows(const std::vector<authority::Point>& points) {
    py::list output;
    for (const auto& point : points) output.append(py::make_tuple(point[0], point[1], point[2]));
    return output;
}

py::list face_rows(const std::vector<authority::Triangle>& faces) {
    py::list output;
    for (const auto& face : faces) output.append(py::make_tuple(face[0], face[1], face[2]));
    return output;
}

py::list semantic_rows(const std::vector<SemanticRow>& rows) {
    py::list output;
    for (const SemanticRow& row : rows) {
        py::dict value;
        value["face_id"] = row.face_id;
        value["source_facet_id"] = row.face_id;
        value["vertices"] = py::make_tuple(row.vertices[0], row.vertices[1], row.vertices[2]);
        value["feature"] = row.feature;
        value["patch"] = row.patch;
        value["physical_group"] = row.physical_group;
        value["component"] = row.component;
        value["provenance"] = row.provenance;
        output.append(value);
    }
    return output;
}

py::dict topology_dict(const authority::TopologySummary& topology) {
    py::dict value;
    value["duplicate"] = topology.duplicate;
    value["non_manifold"] = topology.non_manifold;
    value["open_edges"] = topology.open_edges;
    value["degenerate"] = topology.degenerate;
    value["inverted"] = topology.inverted;
    value["self_intersection"] = topology.self_intersection;
    value["self_intersection_checked"] = topology.self_intersection_checked;
    value["strict_zero"] = topology.duplicate == 0 && topology.non_manifold == 0 &&
                            topology.open_edges == 0 && topology.degenerate == 0 &&
                            topology.inverted == 0 && topology.self_intersection_checked &&
                            topology.self_intersection == 0;
    return value;
}

py::dict validate_impl(const std::string& source_path,
                       const py::dict& trust_anchor,
                       const py::list& semantic_ledger,
                       const std::int64_t requested_layers) {
    if (requested_layers < 0) return refusal("tri_requested_layers_invalid");
    const std::filesystem::path path(source_path);
    const std::string extension = lower_extension(path);
    if (extension == ".step" || extension == ".stp" || extension == ".iges" ||
        extension == ".igs" || extension == ".brep") {
        return refusal("occt_sdk_unavailable");
    }
    if (extension != ".stl" && extension != ".astl")
        return refusal("tri_source_extension_unsupported");
    std::vector<std::uint8_t> bytes;
    if (!read_regular_file(path, bytes)) return refusal("tri_source_file_not_regular_or_readable");
    const std::string raw_sha256 = brep_evidence::sha256_hex(bytes);
    for (const char* key : {"source_sha256", "semantic_ledger_sha256", "issuer", "key_id"}) {
        if (!text(trust_anchor, key)) return refusal("tri_external_trust_anchor_incomplete");
    }
    std::int64_t registered_byte_count = -1;
    if (!integer(trust_anchor, "source_byte_count", registered_byte_count) ||
        registered_byte_count < 0 ||
        static_cast<std::uint64_t>(registered_byte_count) !=
            static_cast<std::uint64_t>(bytes.size()))
        return refusal("tri_external_source_byte_count_mismatch");
    const std::string registered_source = py::str(trust_anchor["source_sha256"]).cast<std::string>();
    if (!hex64(registered_source) || registered_source != raw_sha256)
        return refusal("tri_external_source_registration_mismatch");
    authority::CanonicalSource source;
    std::string parse_reason;
    if (!authority::parse_stl(bytes, source, parse_reason)) return refusal(parse_reason.c_str());
    std::vector<SemanticRow> rows;
    if (!parse_semantic_rows(semantic_ledger, source, rows, parse_reason))
        return refusal(parse_reason.c_str());
    const std::string geometry_stream = authority::canonical_geometry_stream(source);
    const std::string geometry_sha256 = authority::sha256_text(geometry_stream);
    const std::string ledger_stream = semantic_stream(rows);
    const std::string ledger_sha256 = authority::sha256_text(ledger_stream);
    const std::string registered_ledger =
        py::str(trust_anchor["semantic_ledger_sha256"]).cast<std::string>();
    if (!hex64(registered_ledger) || registered_ledger != ledger_sha256)
        return refusal("tri_external_semantic_ledger_registration_mismatch");
    const authority::TopologySummary topology = authority::audit_topology(source);
    if (!topology.self_intersection_checked)
        return refusal("tri_source_self_intersection_audit_unavailable");
    if (topology.duplicate != 0 || topology.non_manifold != 0 || topology.open_edges != 0 ||
        topology.degenerate != 0 || topology.inverted != 0 || topology.self_intersection != 0)
        return refusal("tri_source_strict_topology_failed");
    std::ostringstream certificate_stream;
    certificate_stream << "NativeTriAuthorityCertificate/v2|" << source.source_kind << '|'
                       << raw_sha256 << '|' << geometry_sha256 << '|' << ledger_sha256 << '|'
                       << py::str(trust_anchor["issuer"]).cast<std::string>() << '|'
                       << py::str(trust_anchor["key_id"]).cast<std::string>();
    const std::string certificate_sha256 = authority::sha256_text(certificate_stream.str());
    py::dict certificate;
    certificate["schema"] = "NativeTriAuthorityCertificate/v2";
    certificate["source_kind"] = source.source_kind;
    certificate["source_path"] = path.string();
    certificate["source_sha256"] = raw_sha256;
    certificate["source_byte_count"] = bytes.size();
    certificate["canonical_geometry_sha256"] = geometry_sha256;
    certificate["semantic_ledger_sha256"] = ledger_sha256;
    certificate["certificate_sha256"] = certificate_sha256;
    certificate["reader_id"] = "native-tri-cpp-stl-reader/v2";
    certificate["issuer"] = trust_anchor["issuer"];
    certificate["key_id"] = trust_anchor["key_id"];
    certificate["canonical_points"] = point_rows(source.points);
    certificate["canonical_triangles"] = face_rows(source.faces);
    certificate["face_ledger"] = semantic_rows(rows);
    certificate["topology"] = topology_dict(topology);
    certificate["source_provenance_authoritative"] = true;
    certificate["canonicalization"] = "exact_coordinate_identity_only";
    certificate["physical_groups_inferred"] = false;
    certificate["feature_ids_inferred"] = false;
    py::dict result;
    result["certificate_accepted"] = true;
    result["certificate"] = certificate;
    result["source_sha256"] = raw_sha256;
    result["source_byte_count"] = bytes.size();
    result["source_certificate_sha256"] = certificate_sha256;
    result["semantic_ledger_sha256"] = ledger_sha256;
    result["canonical_geometry_sha256"] = geometry_sha256;
    result["source_provenance_authoritative"] = true;
    result["source_face_count"] = source.faces.size();
    result["source_vertex_count"] = source.points.size();
    result["topology"] = topology_dict(topology);
    result["runtime_route"] = "private_default_off";
    result["publication_eligible"] = false;
    result["route_calls"] = 0;
    result["candidate_discarded"] = requested_layers > 0;
    result["artifact_emitted"] = false;
    result["generated_vertices"] = py::list();
    result["generated_faces"] = py::list();
    result["provenance"] = py::list();
    if (requested_layers == 0) {
        result["accepted"] = true;
        result["status"] = "native_tri_authority_certificate_sealed";
        result["reason"] = "source_certificate_and_bl0_identity_ready";
        result["eligible_for_tri_bl"] = false;
        result["actual_layers"] = 0;
        result["bl0_identity"] = true;
    } else {
        result["accepted"] = false;
        result["status"] = "native_tri_bl_refused";
        result["reason"] = "native_tri_bl_writer_unavailable";
        result["eligible_for_tri_bl"] = false;
        result["actual_layers"] = 0;
        result["bl0_identity"] = false;
    }
    return result;
}

py::dict validate_guarded(const std::string& source_path,
                          const py::dict& trust_anchor,
                          const py::list& semantic_ledger,
                          const std::int64_t requested_layers) {
    try {
        return validate_impl(source_path, trust_anchor, semantic_ledger, requested_layers);
    } catch (const std::exception&) {
        return refusal("tri_authority_certificate_malformed");
    }
}

}  // namespace

PYBIND11_MODULE(native_tri_cad_stl_authority_ingress, module) {
    module.doc() = "Private C++23 Native Tri source authority certificate ingress";
    module.def("validate_native_tri_authority_source", &validate_guarded,
               py::arg("source_path"), py::arg("trust_anchor"),
               py::arg("semantic_ledger"), py::arg("requested_layers"));
}
