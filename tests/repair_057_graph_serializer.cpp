diff --git a/auto_tessell_core/native_tet_bl_authoritative_graph_bind.cpp b/auto_tessell_core/native_tet_bl_authoritative_graph_bind.cpp
--- a/auto_tessell_core/native_tet_bl_authoritative_graph_bind.cpp
+++ b/auto_tessell_core/native_tet_bl_authoritative_graph_bind.cpp
@@ -365,1 +365,125 @@
+std::string points_text(const std::vector<Point>& points) {
+    std::ostringstream stream;
+    stream << std::setprecision(17);
+    for (std::size_t index = 0; index < points.size(); ++index) {
+        stream << index << ':' << points[index][0] << ',' << points[index][1] << ','
+               << points[index][2] << '\n';
+    }
+    return stream.str();
+}
+
+py::dict serialize_internal(const std::vector<Point>& points, const std::vector<Tet>& tets) {
+    const Graph graph = build_graph(points, tets);
+    if (!graph.refusal.empty()) return refused(graph.refusal);
+    py::dict result;
+    result["accepted"] = true;
+    result["status"] = tets.empty() ? "empty_candidate_serialization" : "candidate_serialized";
+    result["candidate_discarded"] = false;
+    result["rollback_required"] = false;
+    result["runtime_route"] = "default_off";
+    result["publication_eligible"] = false;
+    result["work_performed"] = !tets.empty();
+    result["graph_sha256"] = graph_sha256(graph);
+    result["quality"] = quality_dict(measure_quality(points, tets, graph));
+
+    if (tets.empty()) {
+        result["points"] = "";
+        result["faces"] = "";
+        result["owner"] = "";
+        result["neighbour"] = "";
+        result["boundary"] = "";
+        result["disk_face_ids"] = py::dict();
+        result["artifact_tree_sha256"] = graph_sha256(graph);
+        result["serialization_sha256"] = graph_sha256(graph);
+        return result;
+    }
+
+    std::vector<std::size_t> order;
+    order.reserve(graph.faces.size());
+    for (std::size_t index = 0; index < graph.faces.size(); ++index) {
+        if (graph.faces[index].neighbour >= 0) order.push_back(index);
+    }
+    const std::size_t internal_count = order.size();
+    for (std::size_t index = 0; index < graph.faces.size(); ++index) {
+        if (graph.faces[index].neighbour < 0) order.push_back(index);
+    }
+
+    std::ostringstream faces;
+    std::ostringstream owner;
+    std::ostringstream neighbour;
+    std::ostringstream boundary;
+    py::dict disk_face_ids;
+    for (std::size_t disk_id = 0; disk_id < order.size(); ++disk_id) {
+        const auto& face = graph.faces[order[disk_id]];
+        faces << "3(" << face.cycle[0] << ' ' << face.cycle[1] << ' ' << face.cycle[2] << ")\n";
+        owner << face.owner << '\n';
+        if (face.neighbour >= 0) neighbour << face.neighbour << '\n';
+        disk_face_ids["face-" + std::to_string(order[disk_id])] =
+            static_cast<std::int64_t>(disk_id);
+    }
+    boundary << "defaultPatch " << (order.size() - internal_count) << ' ' << internal_count << '\n';
+
+    const std::string points_bytes = points_text(points);
+    const std::string faces_bytes = faces.str();
+    const std::string owner_bytes = owner.str();
+    const std::string neighbour_bytes = neighbour.str();
+    const std::string boundary_bytes = boundary.str();
+    std::vector<std::uint8_t> artifact_bytes;
+    for (const auto& entry : {
+        std::pair<std::string, std::string>{"points", points_bytes},
+        std::pair<std::string, std::string>{"faces", faces_bytes},
+        std::pair<std::string, std::string>{"owner", owner_bytes},
+        std::pair<std::string, std::string>{"neighbour", neighbour_bytes},
+        std::pair<std::string, std::string>{"boundary", boundary_bytes}}) {
+        append_text(artifact_bytes, entry.first);
+        append_text(artifact_bytes, entry.second);
+    }
+    const std::string artifact_digest = brep_evidence::sha256_hex(artifact_bytes);
+    result["points"] = points_bytes;
+    result["faces"] = faces_bytes;
+    result["owner"] = owner_bytes;
+    result["neighbour"] = neighbour_bytes;
+    result["boundary"] = boundary_bytes;
+    result["disk_face_ids"] = disk_face_ids;
+    result["artifact_tree_sha256"] = artifact_digest;
+    result["serialization_sha256"] = artifact_digest;
+    return result;
+}
+
+py::dict serialize(
+    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
+    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tets_array) {
+    const auto points = load_points(points_array);
+    const auto tets = load_tets(tets_array, static_cast<std::int64_t>(points.size()));
+    return serialize_internal(points, tets);
+}
+
+py::dict readback(
+    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
+    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tets_array,
+    const py::dict& serialized) {
+    const auto points = load_points(points_array);
+    const auto tets = load_tets(tets_array, static_cast<std::int64_t>(points.size()));
+    const py::dict expected = serialize_internal(points, tets);
+    if (!expected["accepted"].cast<bool>()) return expected;
+    for (const char* key : {
+        "points", "faces", "owner", "neighbour", "boundary",
+        "graph_sha256", "artifact_tree_sha256", "serialization_sha256"}) {
+        if (!serialized.contains(key) || !expected.contains(key)) {
+            return refused("readback_field_missing");
+        }
+        try {
+            if (serialized[key].cast<std::string>() != expected[key].cast<std::string>()) {
+                return refused("readback_canonical_bytes_mismatch");
+            }
+        } catch (const py::cast_error&) {
+            return refused("readback_field_type_mismatch");
+        }
+    }
+    py::dict result = expected;
+    result["status"] = "candidate_disk_readback_verified";
+    result["readback_verified"] = true;
+    result["rollback_required"] = false;
+    return result;
+}
 }  // namespace

