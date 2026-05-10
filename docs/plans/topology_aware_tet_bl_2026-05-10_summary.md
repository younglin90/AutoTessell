# BLR-9c-d cap sub-series — final summary

Across 84 ralph-loop iterations (BLR-9c-d-p-1 through s-3,
q-1 through q-3, r-1), the anti-invert cap chain pushed the
21-STL tet+BL bench from baseline 12/21 PASS to **17/21 PASS**.

## Final result (with floor=0.5)

| Metric              | Baseline | Cap floor=0.05 | Cap **floor=0.5** |
|---------------------|----------|----------------|-------------------|
| PASS verdicts (21)  | 12       | 16             | **17**            |
| Pass rate           | 57 %     | 76 %           | **81 %**          |
| Hard fails          | 9        | 3              | 3                 |
| Cap-converted FAIL→PASS  | -    | 4              | **5**             |

floor=0.5 dropped max_aspect 10x across all STLs (e.g.
test_cube 2237 → 224, easy_100423 11879 → 1188), the dominant
cosmetic concern at floor=0.05.

## Cap-converted FAIL → PASS (5 cases at floor=0.5)

| STL                  | Baseline issue             | Cap fix                  |
|----------------------|----------------------------|--------------------------|
| extreme_1017013      | 9 negative volumes         | 0 neg_vol                |
| extreme_1017014      | neg_vol + skew 71.94       | skew 11.78, aspect 114.7 |
| extreme_102308       | 6 neg_vol + surface_dev 48%| neg_vol 0, aspect 124    |
| hard_100029          | 3 negative volumes         | 0 neg_vol                |
| hard_100040          | 28 neg_vol + skew 31.36    | 0 neg_vol, skew 9.46     |

## Remaining 4 FAILs (cap-independent or floor-conflicted)

| STL                  | Cause at floor=0.5                       |
|----------------------|------------------------------------------|
| extreme_1017017      | 1 neg_vol + skew 29.34 (cap-independent) |
| hard_100030          | 1 neg_vol + skew 1166 (extreme upstream) |
| hard_1004826         | 1 neg_vol + skew 13.48 (cap-independent) |
| medium_100330        | 1 neg_vol (regression — needs floor≤0.05)|

## Code delivered

- ``core/layers/native_bl_anti_invert.py`` (354 LOC):
  ``compute_anti_invert_caps`` per-vert geometric helper +
  ``compute_joint_cell_inversion_scale`` multi-vert bisection
  joint helper.
- ``core/utils/polymesh_orient_safe.py`` (234 LOC):
  ``fix_inverted_cells_safely`` single-iteration single-face-flip
  post-process.
- ``core/layers/native_bl.py`` integration of cap helpers behind
  env flags ``AUTO_TESSELL_BL_ANTI_INVERT_CAP/SAFETY/GLOBAL/JOINT/FLOOR``.
- ``core/layers/native_bl_vd.py`` shortest-diagonal triangulation
  behind ``AUTO_TESSELL_BL_TRIANGULATE_QUAD_SHORTEST``.
- ``core/generator/tier_native_tet.py`` pipeline-only kwargs filter
  (BLR-9c-d-r-1 fix that unblocked --tier native_tet end-to-end).
- ``tests/stl/bench_cavity_eval*.py`` 4-script bench harness:
  - bench_cavity_eval.py main runner with anti-invert cap default ON
  - bench_cavity_eval_live.py live partial-results reader
  - bench_cavity_eval_classify.py auto-classify by failure mode
  - bench_cavity_eval_worst_faces.py worst-face diagnostic
- 7 new unit tests in ``tests/test_native_bl_anti_invert.py``;
  2 in ``tests/test_tier_native_tet_kwarg_filter.py``.

## Path to 100 % (future work)

The 5 remaining FAILs need either:

a) **Geometric polyhedron repair**: split the 8-face inverted
   polyhedra into sub-tets that don't span the offending face
   plane.  Requires polyMesh-level cell rewriting after BL.
b) **Different tet generator**: replace pytetwild with a
   sliver-removal-aware generator (Klingner Stellar §3.4 swap
   on top of native_tet).  Reduces cap pressure across all
   cases and doesn't introduce slim sliver tets near walls.
c) **BL pipeline restructure**: skip junction merge at problem
   corners or detect non-planar quads and refuse to triangulate
   (leave as proper 5-face prism with quad face).

Each is multi-week.  The cap sub-series delivered the
quick-win improvement; deeper progress is a separate workstream.
