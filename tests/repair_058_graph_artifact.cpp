diff --git a/auto_tessell_core/native_tet_bl_authoritative_graph_bind.cpp b/auto_tessell_core/native_tet_bl_authoritative_graph_bind.cpp
--- a/auto_tessell_core/native_tet_bl_authoritative_graph_bind.cpp
+++ b/auto_tessell_core/native_tet_bl_authoritative_graph_bind.cpp
@@ -491,1 +491,21 @@
+py::dict artifact(
+    const py::array_t<double, py::array::c_style | py::array::forcecast>& points_array,
+    const py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>& tets_array) {
+    const auto points = load_points(points_array);
+    const auto tets = load_tets(tets_array, static_cast<std::int64_t>(points.size()));
+    py::dict result = serialize_internal(points, tets);
+    if (!result["accepted"].cast<bool>()) return result;
+    const Graph graph = build_graph(points, tets);
+    result["status"] = tets.empty()
+        ? "bl0_identity_artifact"
+        : "authoritative_candidate_artifact";
+    result["candidate_artifact"] = true;
+    result["faces_table"] = face_list(graph);
+    result["face_count"] = graph.faces.size();
+    result["collision_surface_source"] = tets.empty() ? "none" : "writer_owned_face_table";
+    result["collision_checked"] = false;
+    result["publication_eligible"] = false;
+    return result;
+}
+
 }  // namespace

