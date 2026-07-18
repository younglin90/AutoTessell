# native_tet hard-geometry matrix (P4C=0, draft, N=2000)

_Generated 2026-07-18 11:31 — engine: self-implemented native_tet, pytetwild fallback OFF._

Protocol per shape: draft / tier_hint=native_tet / N=2000 / P4C disabled / 120s timeout, subprocess-isolated.

- **area-ratio** = Σ|boundary face area| / STL surface area (≈1 = boundary tracks the surface)
- **vol-ratio** = Σ|cell volume| / STL closed volume (≈1 = solid fills the body, no over/under-fill)
- **degen** = cells with |det|/6 < 1e-9 (vertex-based, face-orientation independent)
- **neg** = negative signed-volume cells; **nonTet** = cells whose vertex set != 4

| shape | wt/bodies | cells | area-ratio | vol-ratio | degen | neg | nonTet | skew | nonOrtho | verdict | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cube.stl | Y/1 | 2346 | 1.000 | 1.006 | 0 | 0 | 0 | 1.81 | 88.2 | PASS | 7s |
| cylinder.stl | Y/1 | 1851 | 1.000 | 1.003 | 0 | 0 | 0 | 44.94 | 89.2 | FAIL | 5s |
| sphere.stl | Y/1 | 2453 | 1.000 | 1.008 | 0 | 0 | 0 | 2.62 | 89.2 | PASS | 29s |
| sphere_watertight.stl | Y/1 | 2453 | 1.000 | 1.008 | 0 | 0 | 0 | 2.62 | 89.2 | PASS | 29s |
| naca0012.stl | Y/1 | 4041 | 1.000 | 1.004 | 17 | 0 | 0 | 58.83 | 90.0 | FAIL | 100s |
| trimesh_box.stl | Y/1 | 1758 | 1.000 | 1.006 | 0 | 0 | 0 | 1.90 | 86.1 | PASS | 2s |
| external_flow_isolated_box.stl | Y/1 | 2346 | 1.000 | 1.006 | 0 | 0 | 0 | 1.81 | 88.2 | PASS | 8s |
| very_thin_disk_0_01mm.stl | Y/1 | 2129 | 1.000 | 1.000 | 4 | 0 | 0 | 23809523916666683947502010368.00 | 89.6 | FAIL | 7s |
| extreme_aspect_ratio_needle.stl | Y/1 | 126 | 1.000 | 1.001 | 0 | 0 | 0 | 559.20 | 90.0 | FAIL | 4s |
| high_genus_dual_torus.stl | Y/1 | 7776 | 0.562 | 0.472 | 0 | 0 | 0 | 19.76 | 89.7 | FAIL | 55s |
| multi_scale_sphere_with_micro_spikes.stl | Y/9 | 2296 | 0.996 | 1.006 | 0 | 0 | 0 | 1.50 | 74.1 | PASS | 16s |
| many_small_features_perforated_plate.stl | Y/65 | 1962 | 0.011 | 0.003 | 0 | 0 | 0 | 36.41 | 89.8 | FAIL | 5s |
| sharp_features_micro_ridge.stl | N/1 | 1727 | 0.345 | 1.006 | 0 | 0 | 0 | 125.38 | 90.0 | FAIL | 18s |

## Notes

- **Update 2026-07-18 (BETA2831):** `closest_points_all_shared` (`core/utils/aabb.py`)
  was profiled (cProfile) as 71% of native_tet's wall time on curved-closed
  surfaces — a BVH leaf routine called once per query point (660k calls on
  sphere.stl) instead of batched. Vectorizing the leaf branch over the whole
  active-query set dropped that function's cumtime 62.4s→2.8s with bit-identical
  results (oracle-equivalence tested). All 3 former TIMEOUT rows now complete
  well inside the 120s wall: `sphere.stl` 143.5s→**29s**, `sphere_watertight.stl`
  same, `high_genus_dual_torus.stl` >120s→**55s**. sphere/sphere_watertight are
  now clean PASS. **high_genus_dual_torus is not** — it was masked by the
  timeout and now shows a real solid-invariant defect: area-ratio 0.562,
  vol-ratio 0.472 (mesh covers/fills roughly half the input surface/volume).
  This joins the perforated_plate/sharp_ridge cluster below (coverage collapse
  on complex topology) as the next thing to root-cause, not a speed problem.
- **nonOrtho ≈ 88–90 is endemic** (boundary tets), present even on PASS shapes
  (cube 88.2). It is not the FAIL discriminator here — **skewness** is.
- **`very_thin_disk` skew 2.4e28** is an effectively-degenerate sliver reported with
  a finite-but-astronomical skewness rather than a hard `inf`.

## Excluded inputs (1st pass)

- `broken_sphere.stl` — intentional-bad (broken)
- `degenerate_faces_sliver_triangles.stl` — intentional-bad (degenerate)
- `hemisphere_open.stl` — open surface
- `hemisphere_open_partial.stl` — open surface
- `highly_skewed_mesh_flat_triangles.stl` — intentional-bad (skewed/flat)
- `mixed_features_wing_with_spike.stl` — mixed_* (intentional)
- `mixed_watertight_and_open.stl` — mixed_* (intentional)
- `nonmanifold_disconnected.stl` — non-manifold / disconnected
- `self_intersecting_crossed_planes.stl` — self-intersecting (intentional)
- `coarse_to_fine_gradation_two_spheres.stl` — multi-body (2 spheres)
- `five_disconnected_spheres.stl` — multi-body (5 spheres)
- `trimesh_duct.stl` — open tube (uncertain watertight)
- `large_mesh_250k_faces.stl` — large (excluded 1st pass)
- `sphere_20k.stl` — medium/redundant with sphere.stl
- `*.step` — non-STL
