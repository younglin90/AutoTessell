diff --git a/auto_tessell_core/native_tet_bl_writer_bind.cpp b/auto_tessell_core/native_tet_bl_writer_bind.cpp
--- a/auto_tessell_core/native_tet_bl_writer_bind.cpp
+++ b/auto_tessell_core/native_tet_bl_writer_bind.cpp
@@ -499,1 +499,94 @@
+std::set<std::int64_t> vertex_set_from_handle(const py::handle& value) {
+    const auto vertices = value.cast<std::vector<std::int64_t>>();
+    return std::set<std::int64_t>(vertices.begin(), vertices.end());
+}
+
+py::dict generate_authoritative_artifact(
+    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array_in,
+    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& triangles_array,
+    const py::array_t<double, py::array::c_style | py::array::forcecast>& normals_array,
+    std::int64_t requested_layers, double first_height, double growth_ratio,
+    double minimum_volume, const py::dict& authority) {
+    py::dict result = generate_authoritative(
+        points_array_in, triangles_array, normals_array, requested_layers,
+        first_height, growth_ratio, minimum_volume, authority);
+    if (requested_layers == 0 || !result["accepted"].cast<bool>()) {
+        result["status"] = "bl0_identity_artifact_bridge";
+        result["artifact_bridge_work_performed"] = false;
+        return result;
+    }
+
+    py::dict artifact;
+    try {
+        const py::module_ graph_module = py::module_::import("native_tet_bl_authoritative_graph");
+        artifact = graph_module.attr("artifact")(result["points"], result["tets"]).cast<py::dict>();
+    } catch (const py::error_already_set&) {
+        result["accepted"] = false;
+        result["status"] = "authoritative_artifact_bridge_refused";
+        result["candidate_discarded"] = true;
+        result["rollback_required"] = true;
+        result["refusal_reason"] = "authoritative_graph_module_unavailable";
+        return result;
+    }
+    if (!artifact.contains("accepted") || !artifact["accepted"].cast<bool>()) {
+        result["accepted"] = false;
+        result["status"] = "authoritative_artifact_bridge_refused";
+        result["candidate_discarded"] = true;
+        result["rollback_required"] = true;
+        result["refusal_reason"] = "authoritative_graph_refused";
+        result["artifact"] = artifact;
+        return result;
+    }
+
+    py::dict ledger = result["ledger"].cast<py::dict>();
+    if (ledger.contains("graph_digest_pending_python_canonicalization")) {
+        ledger.attr("pop")("graph_digest_pending_python_canonicalization");
+    }
+    ledger["graph_sha256"] = artifact["graph_sha256"];
+    ledger["artifact_tree_sha256"] = artifact["artifact_tree_sha256"];
+    ledger["serialization_sha256"] = artifact["serialization_sha256"];
+    ledger["graph_binding"] = "direct_writer_vertex_cycle";
+    const py::list graph_faces = artifact["faces_table"].cast<py::list>();
+    const py::dict disk_ids = artifact["disk_face_ids"].cast<py::dict>();
+
+    for (const char* section_name : {"boundary_children", "interface_children"}) {
+        const py::list sections = ledger[section_name].cast<py::list>();
+        for (const auto section_item : sections) {
+            py::dict section = section_item.cast<py::dict>();
+            const py::list children = section["children"].cast<py::list>();
+            for (const auto child_item : children) {
+                py::dict child = child_item.cast<py::dict>();
+                const auto target = vertex_set_from_handle(child["vertex_ids"]);
+                bool found = false;
+                for (const auto face_item : graph_faces) {
+                    const py::dict face = face_item.cast<py::dict>();
+                    if (vertex_set_from_handle(face["vertex_cycle"]) != target) continue;
+                    const auto writer_face_id = face["writer_face_id"].cast<std::string>();
+                    if (!disk_ids.contains(py::str(writer_face_id))) break;
+                    child["disk_face_id"] = disk_ids[py::str(writer_face_id)];
+                    child["graph_face_id"] = writer_face_id;
+                    found = true;
+                    break;
+                }
+                if (!found) {
+                    result["accepted"] = false;
+                    result["status"] = "authoritative_artifact_bridge_refused";
+                    result["candidate_discarded"] = true;
+                    result["rollback_required"] = true;
+                    result["refusal_reason"] = "writer_face_cycle_not_in_graph";
+                    result["artifact"] = artifact;
+                    return result;
+                }
+            }
+        }
+    }
+
+    result["ledger"] = ledger;
+    result["artifact"] = artifact;
+    result["status"] = "authoritative_candidate_artifact_bridge";
+    result["authoritative_artifact_bridge"] = true;
+    result["collision_surface_source"] = "writer_owned_graph_faces";
+    result["publication_eligible"] = false;
+    return result;
+}
 }
