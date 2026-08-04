#pragma once

namespace native_tet_writer_outer {

inline std::string canonical_value(const py::handle& value) {
    if (value.is_none()) return "null;";
    if (py::isinstance<py::bool_>(value)) return value.cast<bool>() ? "bool:1;" : "bool:0;";
    if (py::isinstance<py::int_>(value)) return "int:" + std::to_string(value.cast<long long>()) + ";";
    if (py::isinstance<py::float_>(value)) {
        std::ostringstream stream;
        stream << "float:" << std::setprecision(std::numeric_limits<double>::max_digits10)
               << value.cast<double>() << ";";
        return stream.str();
    }
    if (py::isinstance<py::str>(value)) {
        const auto text = value.cast<std::string>();
        return "str:" + std::to_string(text.size()) + ":" + text + ";";
    }
    if (py::isinstance<py::dict>(value)) {
        std::vector<std::pair<std::string, std::string>> entries;
        for (const auto item : value.cast<py::dict>()) {
            const auto key = py::cast<std::string>(item.first);
            entries.emplace_back(key, canonical_value(item.second));
        }
        std::sort(entries.begin(), entries.end());
        std::string result = "dict{";
        for (const auto& entry : entries) {
            result += "key:" + std::to_string(entry.first.size()) + ":" + entry.first + ":";
            result += entry.second;
        }
        return result + "};";
    }
    if (py::isinstance<py::list>(value) || py::isinstance<py::tuple>(value)) {
        const auto sequence = value.cast<py::sequence>();
        std::string result = "seq[";
        for (py::ssize_t index = 0; index < static_cast<py::ssize_t>(sequence.size()); ++index) {
            result += canonical_value(sequence[index]);
        }
        return result + "];";
    }
    throw std::invalid_argument("input_parameter_type_unsupported");
}

inline std::string input_parameters_sha256(const py::dict& parameters) {
    const std::string canonical = canonical_value(parameters);
    const std::vector<std::uint8_t> bytes(canonical.begin(), canonical.end());
    return brep_evidence::sha256_hex(bytes);
}

inline bool sealed_input_parameters(
    const py::dict& policy, std::int64_t requested_layers,
    py::dict& parameters, std::string& digest) {
    if (!policy.contains("input_parameters") ||
        !py::isinstance<py::dict>(policy["input_parameters"]) ||
        !policy.contains("input_parameters_sha256") ||
        !is_hex64(policy["input_parameters_sha256"])) return false;
    parameters = policy["input_parameters"].cast<py::dict>();
    digest = policy["input_parameters_sha256"].cast<std::string>();
    try {
        if (input_parameters_sha256(parameters) != digest) return false;
        if (!parameters.contains("boundary_layer_count") ||
            parameters["boundary_layer_count"].cast<std::int64_t>() != requested_layers) return false;
    } catch (const std::exception&) {
        return false;
    }
    for (const char* key : {"first_height", "growth_ratio", "target_cells", "target_faces",
                            "wall_edge_mode", "feature_angle", "min_signed_volume",
                            "min_scaled_jacobian", "max_skewness", "max_non_orthogonality",
                            "max_aspect_ratio"}) {
        if (!parameters.contains(key)) return false;
    }
    return true;
}

struct SurfaceFace {
    Triangle cycle{};
    std::int64_t owner = -1;
};

inline std::vector<SurfaceFace> writer_outer_faces(
    const std::vector<Point>& points, const std::vector<Tet>& tets) {
    struct Accumulator { Triangle cycle{}; std::int64_t owner = -1; int count = 0; };
    std::map<std::array<std::int64_t, 3>, Accumulator> faces;
    for (std::size_t cell = 0; cell < tets.size(); ++cell) {
        const auto& tet = tets[cell];
        const Point cell_center = scale(
            add(add(points[static_cast<std::size_t>(tet[0])], points[static_cast<std::size_t>(tet[1])]),
                add(points[static_cast<std::size_t>(tet[2])], points[static_cast<std::size_t>(tet[3])])), 0.25);
        for (int omitted = 0; omitted < 4; ++omitted) {
            Triangle cycle{};
            int cursor = 0;
            for (int vertex = 0; vertex < 4; ++vertex) {
                if (vertex != omitted) cycle[static_cast<std::size_t>(cursor++)] = tet[static_cast<std::size_t>(vertex)];
            }
            const Point a = points[static_cast<std::size_t>(cycle[0])];
            const Point b = points[static_cast<std::size_t>(cycle[1])];
            const Point c = points[static_cast<std::size_t>(cycle[2])];
            const Point normal = cross(sub(b, a), sub(c, a));
            const Point face_center = scale(add(add(a, b), c), 1.0 / 3.0);
            if (dot(normal, sub(face_center, cell_center)) < 0.0) std::swap(cycle[1], cycle[2]);
            auto key = cycle;
            std::sort(key.begin(), key.end());
            auto& entry = faces[key];
            if (entry.count == 0) { entry.cycle = cycle; entry.owner = static_cast<std::int64_t>(cell); }
            ++entry.count;
            if (entry.count > 2) throw std::invalid_argument("writer_outer_non_manifold_face");
        }
    }
    std::vector<SurfaceFace> result;
    for (const auto& item : faces) if (item.second.count == 1) {
        result.push_back({item.second.cycle, item.second.owner});
    }
    return result;
}

struct CollisionEvidence {
    std::size_t broad_phase_pairs = 0;
    std::size_t narrow_phase_hits = 0;
    std::int64_t first_left = -1;
    std::int64_t first_right = -1;
    std::string digest;
};

inline CollisionEvidence collision_evidence(
    const std::vector<Point>& points, const std::vector<SurfaceFace>& faces) {
    CollisionEvidence result;
    std::ostringstream canonical;
    canonical << "writer-owned-outer-surface/v1\n";
    for (std::size_t left = 0; left < faces.size(); ++left) {
        for (std::size_t right = left + 1; right < faces.size(); ++right) {
            if (shares_vertex(faces[left].cycle, faces[right].cycle)) continue;
            if (!aabb_overlap(triangle_aabb(points, faces[left].cycle), triangle_aabb(points, faces[right].cycle))) continue;
            ++result.broad_phase_pairs;
            canonical << left << ':' << right << ';';
            if (triangles_intersect(points, faces[left].cycle, faces[right].cycle)) {
                ++result.narrow_phase_hits;
                if (result.first_left < 0) {
                    result.first_left = static_cast<std::int64_t>(left);
                    result.first_right = static_cast<std::int64_t>(right);
                }
            }
        }
    }
    const std::string text = canonical.str();
    const std::vector<std::uint8_t> bytes(text.begin(), text.end());
    result.digest = brep_evidence::sha256_hex(bytes);
    return result;
}

inline py::array_t<std::int64_t> surface_array(const std::vector<SurfaceFace>& faces) {
    const std::vector<py::ssize_t> shape = {static_cast<py::ssize_t>(faces.size()), static_cast<py::ssize_t>(3)};
    py::array_t<std::int64_t> result(shape);
    auto output = result.mutable_unchecked<2>();
    for (py::ssize_t row = 0; row < static_cast<py::ssize_t>(faces.size()); ++row)
        for (int column = 0; column < 3; ++column) output(row, column) = faces[static_cast<std::size_t>(row)].cycle[static_cast<std::size_t>(column)];
    return result;
}

inline py::dict admit_writer_owned_outer_surface(
    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tets_array,
    const py::dict& policy, std::int64_t requested_layers,
    const py::dict& ledger, const py::dict& authority) {
    py::dict parameters;
    std::string parameter_digest;
    if (!sealed_input_parameters(policy, requested_layers, parameters, parameter_digest))
        return refuse("policy", "input_parameters_unsealed_or_incomplete");
    if (!ledger.contains("outer_face_authority") ||
        !py::isinstance<py::list>(ledger["outer_face_authority"]))
        return refuse("authority", "writer_outer_face_authority_required");
    const auto points = load_points(points_array);
    const auto tets = load_tets(tets_array, static_cast<std::int64_t>(points.size()));
    if (tets.empty()) return refuse("topology", "positive_bl_candidate_has_no_cells");
    for (const auto& tet : tets) if (!std::isfinite(signed_volume6(points, tet)) || signed_volume6(points, tet) <= 0.0)
        return refuse("volume", "tet_signed_volume_nonpositive");
    std::vector<SurfaceFace> faces;
    try { faces = writer_outer_faces(points, tets); }
    catch (const std::exception&) { return refuse("topology", "writer_outer_non_manifold_face"); }
    const auto authority_rows = ledger["outer_face_authority"].cast<py::list>();
    if (static_cast<py::ssize_t>(authority_rows.size()) != static_cast<py::ssize_t>(faces.size()))
        return refuse("authority", "writer_outer_face_authority_count_mismatch");
    py::list writer_face_ledger;
    for (std::size_t index = 0; index < faces.size(); ++index) {
        const py::dict source = authority_rows[static_cast<py::ssize_t>(index)].cast<py::dict>();
        for (const char* key : {"source_face_id", "source_edge_id", "feature", "patch", "physical_group", "component", "provenance"})
            if (!source.contains(key)) return refuse("authority", "writer_outer_lineage_incomplete");
        py::dict row = source;
        row["writer_face_id"] = "writer-outer-face-" + std::to_string(index);
        row["owner_cell"] = faces[index].owner;
        row["role"] = "outer";
        py::list cycle;
        for (const auto vertex : faces[index].cycle) cycle.append(vertex);
        row["oriented_vertex_cycle"] = cycle;
        writer_face_ledger.append(row);
    }
    const auto evidence = collision_evidence(points, faces);
    py::dict result = admit(points_array, tets_array, surface_array(faces), policy, requested_layers,
                            py::none(), ledger, authority);
    result["writer_owned_outer_surface"] = true;
    result["collision_surface_source"] = "writer_owned_outer_faces";
    result["outer_face_count"] = faces.size();
    result["writer_face_ledger"] = writer_face_ledger;
    result["collision_broad_phase_pairs"] = evidence.broad_phase_pairs;
    result["collision_narrow_phase_hits"] = evidence.narrow_phase_hits;
    if (evidence.first_left < 0) result["collision_first_pair"] = py::none();
    else result["collision_first_pair"] = py::make_tuple(evidence.first_left, evidence.first_right);
    result["collision_digest"] = evidence.digest;
    result["input_parameters"] = parameters;
    result["input_parameters_sha256"] = parameter_digest;
    if (evidence.narrow_phase_hits > 0) {
        result["accepted"] = false;
        result["status"] = "candidate_refused";
        result["refusal_stage"] = "collision";
        result["refusal_reason"] = "writer_owned_outer_surface_self_intersection";
        result["candidate_discarded"] = true;
        result["rollback_required"] = true;
    }
    return result;
}

}  // namespace native_tet_writer_outer
