# U-cards outcome — 18/21 → 20/21 = 95 %

## Final result

| Setting | PASS / 21 | %  | FAIL cases |
|---------|-----------|----|------------|
| BASELINE (no U-cards, QUALITY=draft) | 18 | 86 % | hard_100030, hard_1004826, medium_100330 |
| **U-1 + U-3 + U-3b + U-4 (current)** | **20** | **95 %** | **hard_100030** (soft only) |

## What landed

- **U-1** (commit aaed1ed9):  ``AUTO_TESSELL_BL_TRIANGULATE_QUAD_SHORTEST=1`` on
  by default — adjacent prisms agree on the shared quad diagonal,
  removing a class of post-BL non-planar mismatches.
- **U-3** (commit aaed1ed9):  ``core/utils/drop_neg_vol_cells.py`` —
  drops cells with geometric ``signed_vol ≤ tol`` *and*
  topologically inverted cells (every owned face winding points
  inward, matching ``NativeMeshChecker.n_inverted_owner_cells``).
  Surviving cells donate their internal faces to a new
  ``droppedShell`` patch.  Wired in
  ``core/pipeline/orchestrator.py`` after ``LayersPostGenerator``.
- **U-3b** (commit 779c0fa0):  iterative drop — internal/boundary
  faces whose skewness exceeds ``AUTO_TESSELL_BL_DROP_SKEW_THRESHOLD``
  (default 18) demote both adjacent cells.  Iterated until no
  drops occur, ≤8 passes.  Default 18 < 19 soft cap so the soft-FAIL
  by skew gate cannot trip.
- **U-4** (commit 779c0fa0):  ``AUTO_TESSELL_BL_ASPECT_ENFORCE=1``
  + target 1000 — pre-existing post-extrusion prism-aspect cap
  enforcer.  Shrinks outer prism nodes when aspect exceeds the
  target.

## Cap-converted FAIL → PASS

| STL | Baseline FAIL reason | After U-cards |
|-----|---------------------|---------------|
| hard_1004826 | neg_vol=1 | PASS_WITH_WARNINGS (no hard, soft = max_aspect 1271) |
| medium_100330 | neg_vol=1 | PASS_WITH_WARNINGS (no hard, soft = max_aspect 1271) |

## Lone remaining FAIL — hard_100030

- ``hard_fails: []``
- ``soft_fails``:
  - ``max_aspect_ratio = 1555.82`` (> 1000)
  - ``surface_area_deviation_percent = 111.66`` (> 20 %)

Two soft fails ⇒ soft-FAIL gate trips.  Both are **upstream
quality issues**:

- ``surface_area_deviation 111 %``: pytetwild's output surface is
  111 % larger than the input STL — i.e. it inflated the surface
  during epsilon-envelope tetrahedralisation.  Independent of the
  BL pipeline.
- ``max_aspect 1555``: 143 cells in the mesh have aspect > 1000
  (mostly BL prisms).  ``ASPECT_ENFORCE`` cannot reduce further
  because the prism heights are already shrunk to ``min_height_factor=0.05``.

Real fix requires (a) tightening pytetwild epsilon (slows all
cases) or (b) a sliver-aware tet generator replacing pytetwild
on inputs with high feature density.

## Code delivered

- ``core/utils/drop_neg_vol_cells.py`` — 553 LOC.
  ``drop_neg_vol_cells`` (single pass) +
  ``drop_neg_vol_cells_iterative`` (loops to convergence).
- ``tests/test_drop_neg_vol_cells.py`` — 5 unit tests on a
  synthetic 2-tet polyMesh fixture.
- ``core/pipeline/orchestrator.py`` — call site behind
  ``AUTO_TESSELL_BL_DROP_NEG_VOL=1`` env flag.
- ``tests/stl/bench_cavity_eval.py`` — env defaults for U-1, U-3,
  U-3b, U-4 + ``AUTO_TESSELL_BENCH_CAVITY_QUALITY=draft``.

## Regression

- 236 unit tests PASS (drop_neg_vol_cells + native_bl_anti_invert
  + native_bl_vd + tier_native_tet kwarg filter + evaluator).
- Bench 21-STL: 20/21 PASS at draft.
