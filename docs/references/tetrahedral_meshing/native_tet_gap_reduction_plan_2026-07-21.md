# Native Tet Gap Reduction Plan - 2026-07-21

Goal: close the remaining gap to TetWild/fTetWild-class replacement while preserving
surface fidelity, target cell count, boundary layers, and deterministic regression gates.

## Current Binding Gaps

- Worst non-orthogonality is still around 73 degrees on the 120-case matrix.
- Worst skewness is still around 3.37, dominated by mixed watertight/open and small-feature cases.
- Worst aspect ratio is still around 100, dominated by extreme gear/bracket/valve cases.
- Dirty/open-surface rescues work often, but current rebudget heuristics can over-catch unrelated cases.
- The core quality optimizer is still incomplete compared with TetWild/fTetWild: no full invariant-guarded
  split-collapse-swap-smooth loop, no full regular triangulation rebuild, no shell-transform cavity recovery.

## Papers Read

- Hu et al. 2018, `Tetrahedral Meshing in the Wild`.
  Source: https://www.cs.toronto.edu/~jacobson/images/tetrahedral-meshing-in-the-wild-siggraph-2018-compressed-hu-et-al.pdf
- Hu et al. 2020, `Fast Tetrahedral Meshing in the Wild`.
  Source: https://arxiv.org/abs/1908.03581
- Klingner and Shewchuk 2007, `Aggressive Tetrahedral Mesh Improvement`.
  Local: `docs/references/papers/source/pdf/01_klingner_2007_aggressive_tet.pdf`
- Cheng and Dey 2003, `Quality Meshing with Weighted Delaunay Refinement`.
  Source: https://cse.hkust.edu.hk/~scheng/pub/soda01-2.pdf
- Cheng et al. 2000, `Sliver Exudation`.
  Local: `docs/references/papers/source/pdf/04_cheng_2000_sliver_exudation.pdf`
- Chen et al. 2017, `Improved boundary constrained tetrahedral mesh generation by shell transformation`.
  Local: `docs/references/tetrahedral_meshing/1-s2.0-S0307904X17304493-main.pdf`
- Leng et al. 2013, `A novel geometric flow approach for quality improvement of multi-component tetrahedral meshes`.
  Local: `docs/references/tetrahedral_meshing/leng2013.pdf`
- Ni et al. 2017, `Sliver-suppressing tetrahedral mesh optimization with gradient-based shape matching energy`.
  Local: `docs/references/tetrahedral_meshing/ni2017.pdf`
- Wang et al. 2024, `Multi-threaded parallel tetrahedral mesh improvement by combining atomic operation and graph coloring`.
  Local: `docs/references/tetrahedral_meshing/1-s2.0-S0965997824001893-main.pdf`
- Ye et al. 2025, `Robust full-layer prismatic mesh generation based on bijective mapping`.
  Local: `docs/references/mesh-quality/robust-full-layer-prismatic-mesh-generation-2025.pdf`
- CORTET 2026, `Robust generation of simulation-ready cortical meshes`.
  Source: https://arxiv.org/html/2607.12157v1

## Implementation Direction

### 1. Stop adding broad rescue heuristics first

The latest dirty capped hull rebudget improves hemisphere variants but also catches
`hard_100030`. Before new features, narrow or revert that helper:

- Add a negative fixture for `hard_100030` against `_dirty_capped_hull_rebudget_target`.
- Require a stronger cap signature: low signed-volume shell ratio, single dominant cap plane/ring,
  or high circular boundary-ring score after repair.
- Keep hemisphere/open-cap improvements only if focused and 120-case E2E do not regress
  hard Thingiverse cases.

### 2. Implement TetWild-style invariant-guarded optimizer

TetWild/fTetWild and Klingner agree on the missing core: quality improvement must be
a schedule, not isolated local operations.

Order:

1. Split long edges toward target size.
2. Collapse short edges if local quality vector improves.
3. Swap/reconnect faces and edges if local quality vector improves.
4. Smooth vertices if local quality vector improves.

Every accepted operation needs guards:

- positive signed volume for all changed tets;
- surface/envelope distance inside tolerance;
- protected boundary/feature class preserved;
- local sorted quality vector improves, except split;
- rollback on any guard failure.

Use current `quality.py` volume-length score first. Add AMIPS or gradient-shape energy only
after the operation schedule is stable.

### 3. Add feature-classified boundary smoothing

Boundary vertices must not be globally locked. Papers support constrained motion:

- fixed corners stay fixed;
- curve/ridge vertices move only along ridge tangent;
- planar surface vertices move in tangent plane;
- smooth surface vertices move inside envelope tolerance.

This directly targets boundary-touching slivers, the usual source of worst skew/aspect.
Acceptance still uses fidelity/envelope rollback.

### 4. Add shell-transform cavity recovery before more Steiner points

Chen 2017 shows that shell transformation reduces boundary intersections and excess
Steiner insertion. Native tet should replace isolated 2-to-3 rescue with bounded cavity
reconnection:

- identify lost/intersected boundary face cavity;
- enumerate recursive shell candidates;
- score by boundary recovery count, local quality vector, and Steiner-count reduction;
- accept only if protected boundary and signed volumes pass.

This is the right path for dirty/self-intersecting and stretched-boundary STL cases.

### 5. Treat weighted exudation as a real regular triangulation task

Cheng/Dey weighted Delaunay refinement is not a post-filter. Weight sampling without
connectivity rebuild is invalid.

Required before enabling:

- C++ regular triangulation from positions plus squared weights;
- filtered/exact orientation and power in-sphere predicates;
- boundary encroachment checks;
- surface recovery after rebuild;
- deterministic weight pumping only after radius-edge refinement.

Until then, keep current exudation proxy diagnostic-only.

### 6. Use gradient-shape energy as second-stage objective

Ni 2017 is useful after the basic operation schedule exists. It targets small heights
and slivers better than edge-length-only objectives.

Plan:

- add local cavity score combining volume-length quality, signed-volume barrier, and
  gradient-shape sliver penalty;
- use it for accept/reject ranking, not as a global unguarded smoother;
- benchmark on current top skew/aspect cases.

### 7. Parallelize only after serial parity

Wang 2024 supports this order:

- first serial deterministic cavity operations;
- then graph coloring for smoothing;
- atomic ownership tokens for topology-changing cavities;
- per-worker output buffers for new elements.

Do not parallelize unstable heuristics.

### 8. Boundary layer direction

Ye 2025 and Dyedov/Bottasso support a global validity-preserving layer motion:

- initial very thin layer;
- target full layer from user thickness/count;
- line search with positive prism and auxiliary collision volume;
- adaptive target reduction in narrow gaps;
- keep requested layer count by reducing heights before dropping layers.

Native tet should judge BL quality with determinant, face orthogonality, and skewness barriers,
not raw anisotropic aspect ratio alone.

## Next Work Cards

1. `DIRTYCAP-NARROW`: prevent dirty cap rebudget over-catch on `hard_100030`.
2. `QOPT-SERIAL-SCHEDULE`: add serial split-collapse-swap-smooth driver with rollback guards.
3. `BOUNDARY-SMOOTH-FEATURE`: classify fixed/curve/surface vertices and allow envelope-bounded motion.
4. `SHELL-CAVITY-RECOVERY`: implement bounded shell-transform candidate enumeration for boundary recovery.
5. `GSM-SCORE`: add gradient-shape sliver score as local cavity acceptance term.
6. `REGULAR-TRIANGULATION`: C++ weighted regular rebuild; keep exudation disabled until green.
7. `PARALLEL-SMOOTH`: graph-color smoothing after serial gates pass.

## Papers Still Needing User Download Only If Deeper Detail Needed

- `Weighted Delaunay Refinement for Polyhedra with Small Angles`
  https://link.springer.com/chapter/10.1007/3-540-29090-7_20
- `Perturbing Slivers in 3D Delaunay Meshes`
  https://inria.hal.science/inria-00430202

## 2026-07-21 Additional Literature Sweep: Gap Reduction Direction

Scope: reduce the remaining native-tet gap versus TetWild/fTetWild-class tools:
worst non-orthogonality near 73 degrees, worst skewness near 2.76 after the
tiny-hole bracket fix, worst aspect ratio near 100, plus dirty-surface and CAD
feature recovery.

Read / checked:

- Hu et al. 2018/2020 TetWild/fTetWild: robust dirty-input tetrahedralization is
  built around a surface envelope, exact predicates, local operations, and
  constrained Delaunay tetrahedralization, not broad case heuristics.
- Klingner and Shewchuk 2007: the missing quality core is a worst-first local
  improvement schedule. The operation set must include smart smoothing,
  vertex insertion, edge removal, 2-to-3, 3-to-2, 4-to-4, boundary smoothing,
  and multi-face removal. Acceptance should compare sorted local quality
  vectors and roll back on inversion.
- Cheng/Dey 2000/2003: true sliver exudation needs a weighted/regular
  triangulation rebuild. Weight scoring without connectivity rebuild is only a
  diagnostic and should remain disabled.
- Chen et al. 2017 and Zeng/Chen/Fu 2023: boundary recovery should reduce
  constraint intersections before Steiner insertion, using shell/cavity
  transformation and accurate intersection queries. This is the right path for
  dirty STL and BL-generated low-quality boundary faces.
- Leng et al. 2013: boundary vertices need feature classes: fixed corners, curve
  vertices, surface vertices, and interior vertices. Boundary motion must be
  shape-preserving, not globally locked.
- Ni et al. 2017: gradient-based shape matching energy directly penalizes
  near-coplanar slivers with small height; use as a local acceptance term after
  topology guards exist.
- Wang et al. 2024: parallel improvement should wait until serial deterministic
  cavity operations are stable. Then graph coloring fits smoothing, while
  topology-changing cavities need atomic ownership.
- Tournois/Srinivasan/Alliez 2009 is relevant for sliver perturbation under
  Delaunay connectivity, but the HAL full PDF was blocked by Anubis from the
  current environment.

Decision:

1. Do not add another broad case rescue first. Current worst cases now need a
   real optimizer, not more shape-specific knobs.
2. First implementation target is `QOPT-SERIAL-SCHEDULE`: C++ local cavity
   engine with lexicographic quality-vector acceptance, positive-volume guard,
   envelope/fidelity guard, and deterministic rollback.
3. Operation order: interior smart smoothing, feature-constrained boundary
   smoothing, 2-to-3/3-to-2/4-to-4 flips, edge removal with link triangulation,
   bounded vertex insertion, multi-face removal.
4. Add `GSM-SCORE` only after the operation schedule exists. It should augment
   accept/reject scoring for sliver cavities, not run as unconstrained global
   smoothing.
5. Add `SHELL-CAVITY-RECOVERY` for boundary conformance before more Steiner
   points. Use AABB/intersection hashing and recursive/annealed shell candidate
   search for dirty STL and BL boundary faces.
6. Keep `REGULAR-TRIANGULATION` as a larger architecture card. Do not enable
   exudation until weighted connectivity rebuild and boundary recovery are
   implemented.
7. Parallelize last.

New papers / links needing user download only if deeper full-text detail is
needed:

- Tournois, Srinivasan, Alliez. `Perturbing Slivers in 3D Delaunay Meshes`.
  HAL PDF blocked here: https://inria.hal.science/inria-00430202/PDF/slivers_paper.pdf
- Cheng, Dey, Ray. `Weighted Delaunay Refinement for Polyhedra with Small
  Angles`. Full text not available here except ResearchGate/Springer metadata:
  https://link.springer.com/chapter/10.1007/3-540-29090-7_20
- Si. `Three dimensional boundary conforming Delaunay mesh generation`.
  DepositOnce link appears in references but direct API fetch is blocked here:
  https://api-depositonce.tu-berlin.de/server/api/core/bitstreams/3157c794-7ad0-4888-ad90-98b778906413/content

Immediate coding card from this sweep:

- `QOPT0-CAVITY-INFRA`: build C++ local-star/cavity extraction, local metric
  vector sort, rollback storage, deterministic operation queue, and no-op parity
  tests. This unlocks real TetWild/fTetWild gap reduction without risking broad
  regressions.

## 2026-07-21 QOPT0 Cavity Infra Result

Change: added `native_tet_qopt` pybind11 target and Python fallback wrapper
`core/generator/native_tet/qopt.py`.

Implemented:

- deterministic local vertex-star cavity extraction for seed tetrahedra;
- per-cavity sorted shape-quality vectors using the native-tet shape metric;
- lexicographic local quality-vector comparison;
- conservative tie behavior: equal quality with fewer local cells is accepted,
  equal quality with more cells is rejected;
- native/Python parity tests.

This is infrastructure only. It deliberately does not change mesh topology yet.
The next card should plug existing smoothing/flip/split/collapse attempts through
this shared quality-vector gate before adding new operations.

Verified:

- `cmake --build . --target native_tet_qopt`: passed.
- `python3 -m pytest tests/test_native_tet_qopt_extension.py -q`: 5 passed.
- `python3 -m pytest tests/test_native_tet_predicates_extension.py tests/test_native_tet_qopt_extension.py -q`: 17 passed.
- `python3 -m pytest tests/test_native_tet_harness.py tests/test_native_tet_convex_extrusion.py tests/test_native_tet_rescue_gate.py tests/test_native_tet_thin_extrusion.py tests/test_native_bl_helpers.py tests/test_tier_native_tet_kwarg_filter.py tests/test_native_tet_qopt_extension.py -q`: 113 passed.

Next coding card:

- `QOPT1-GUARDED-SMOOTH`: route one existing local operation through QOPT0
  first. Best low-risk target is interior smoothing acceptance, because it does
  not change connectivity. Add local rollback, positive-volume guard, and
  quality-vector acceptance, then run the 120-case matrix before any topology
  operation uses the gate.

## 2026-07-21 QOPT1 Guarded Smooth Result

Change: `smooth_interior(..., quality_guard=True)` now uses the QOPT sorted
quality-vector gate plus signed-volume preservation instead of the previous
minimum-quality-only guard. The Phase A native-tet smoothing call now enables
this guard.

Implemented:

- QOPT-backed global smoothing accept/reject helper;
- signed-volume sign preservation and near-zero volume rejection;
- actual-move accounting: rejected smoothing no longer reports moved vertices;
- focused tests proving a harmful Laplacian move is rejected while the unchecked
  path still moves.

Verified:

- `python3 -m pytest tests/test_native_tet_qopt_smooth.py tests/test_native_tet_qopt_extension.py -q`: 7 passed.
- `python3 -m pytest tests/test_native_tet_qopt_smooth.py tests/test_native_tet_qopt_extension.py tests/test_native_tet_phaseA.py::test_smooth_interior_locks_surface tests/test_native_tet_phaseD.py::test_smooth_interior_vectorized_matches_expected tests/test_native_tet_phaseD.py::test_smooth_interior_vectorized_scales_fast -q`: 10 passed.
- `python3 -m pytest tests/test_native_tet_harness.py tests/test_native_tet_convex_extrusion.py tests/test_native_tet_rescue_gate.py tests/test_native_tet_thin_extrusion.py tests/test_native_bl_helpers.py tests/test_tier_native_tet_kwarg_filter.py tests/test_native_tet_qopt_extension.py tests/test_native_tet_qopt_smooth.py -q`: 115 passed.
- Focused E2E smoke `/tmp/autotessell_qopt1_focus_v2`: 6/6 PASS.
- Full native-tet replacement matrix `/tmp/autotessell_qopt1_matrix_v1`: 120/120 PASS.

Main metric movement versus `/tmp/autotessell_native_tet_replacement_matrix_tinyhole_v1`:

- No top-metric regression observed.
- Worst non-ortho unchanged: `mixed_watertight_and_open.stl__scale_aniso` 73.03.
- Worst skew unchanged: `pipe.step` 2.761.
- Worst aspect unchanged: `04_extreme_gear.stl` 99.77.
- `03_hard_bracket.stl`, `pipe.step`, `hard_1004826.stl`, and
  `04_extreme_gear.stl` metrics matched the previous baseline exactly.

Next coding card:

- `QOPT2-LOCAL-VERTEX-GATE`: move from global iteration accept/reject to
  per-vertex local-star accept/reject. This should allow useful interior
  smoothing to survive even when another vertex in the same bulk iteration would
  worsen its local cavity.

## 2026-07-21 QOPT2 Local Vertex Gate Result

Change: added native `apply_guarded_vertex_moves` to `native_tet_qopt` and
routed guarded interior Laplacian smoothing through it.

Implemented:

- C++ sequential per-vertex guarded relocation;
- local incident-tet star extraction inside the native kernel;
- signed-volume sign preservation and near-zero-volume rejection per moved
  vertex;
- local sorted quality-vector comparison per moved vertex;
- accepted/rejected stats: attempted, accepted, rejected-by-volume,
  rejected-by-quality, max displacement;
- Python fallback with the same public API.

Verified:

- `cmake --build . --target native_tet_qopt`: passed.
- `python3 -m pytest tests/test_native_tet_qopt_extension.py tests/test_native_tet_qopt_smooth.py -q`: 9 passed.
- Focused smoothing suite: 12 passed.
- Native tet guard with QOPT tests: 117 passed.
- Focused E2E smoke `/tmp/autotessell_qopt2_focus_v1`: 6/6 PASS.
- Full native-tet replacement matrix `/tmp/autotessell_qopt2_matrix_v1`: 120/120 PASS.

Main metric movement versus `/tmp/autotessell_qopt1_matrix_v1`:

- No metric changes on the 120-case matrix.
- Worst non-ortho unchanged: `mixed_watertight_and_open.stl__scale_aniso` 73.03.
- Worst skew unchanged: `pipe.step` 2.761.
- Worst aspect unchanged: `04_extreme_gear.stl` 99.77.

Performance note:

- Matrix elapsed sum changed from about 1334 s to 1401 s. The affected Phase A
  smooth event was not visible in the E2E generator logs, so this should be
  treated as noisy end-to-end timing until a targeted smoothing microbenchmark
  is added. Do not claim speed improvement from QOPT2.

Next coding card:

- `QOPT3-TARGETED-SMOOTH-BENCH`: add a deterministic smoothing microbenchmark
  and expose QOPT accepted/rejected stats in generator logs. Only after measured
  overhead is understood should topology operations use the same gate.

## 2026-07-21 QOPT3 Targeted Smooth Bench Result

Change: added a deterministic QOPT smoothing benchmark and exposed guarded
smoothing stats through `SmoothResult`, `native_tet_smooth` log fields, and
`_work/native_tet_qopt_smooth.json` for Phase A paths that execute smoothing.

Implemented:

- `scripts/benchmark_native_tet_qopt_smooth.py`;
- structured grid tet benchmark with deterministic interior perturbation;
- guarded vs unguarded smoothing timing;
- pre/post min and mean shape quality;
- QOPT attempted, accepted, rejected-volume, rejected-quality counters;
- stats fields on `SmoothResult`.

Benchmark:

- Command:
  `python3 scripts/benchmark_native_tet_qopt_smooth.py --grid 9 --iters 2 --repeat 3 --out /tmp/autotessell_qopt3_smooth_bench_v3.json`
- Mesh: 729 points, 3072 tets, 386 locked boundary vertices.
- Unguarded mean elapsed: 0.00694 s.
- Guarded mean elapsed: 0.00868 s.
- Overhead on this microbench: about 25%.
- Guarded moves: 613 accepted / 686 attempted, 73 rejected by quality, 0 rejected by volume.
- Quality still improved: min_q 0.221 -> 0.307, mean_q 0.533 -> 0.586.

Verified:

- `python3 -m pytest tests/test_native_tet_qopt_smooth.py tests/test_native_tet_qopt_extension.py -q`: 10 passed.
- Native tet guard with QOPT tests: 118 passed.
- Focused E2E `/tmp/autotessell_qopt3_log_smoke_v2`: 1/1 PASS on `03_hard_bracket.stl`.

Decision:

- Keep QOPT2/QOPT3 as correctness infrastructure.
- Do not claim performance improvement yet. Current native gate overhead is
  acceptable for safety, but should be optimized before topology operations use
  it heavily.

Next coding card:

- `QOPT4-ADJACENCY-REUSE`: avoid rebuilding vertex-to-tet adjacency on every
  guarded smoothing call. Add a reusable native adjacency/incident-star handle or
  a batch API that receives precomputed CSR. Target: reduce QOPT guarded
  smoothing overhead below 10% on the deterministic benchmark before wiring
  split/collapse/flip through the same gate.

## 2026-07-21 QOPT4 Native Fused Smooth Result

Initial CSR reuse alone did not hit the overhead target. The final keepable
version adds a fused native guarded Laplacian smoother:
`native_tet_qopt.smooth_interior_guarded`.

Implemented:

- native neighbor adjacency and incident-tet star construction;
- in-kernel centroid target computation for all eligible interior vertices;
- in-kernel sequential guarded relocation;
- local signed-volume and sorted quality-vector guards;
- Python wrapper falls back to CSR guarded vertex moves when fused native is not
  available;
- parity tests comparing fused native smoothing with the public
  `smooth_interior(..., quality_guard=True)` path.

Microbenchmark:

- Command:
  `python3 scripts/benchmark_native_tet_qopt_smooth.py --grid 9 --iters 2 --repeat 5 --out /tmp/autotessell_qopt4_smooth_bench_v2.json`
- Mesh: 729 points, 3072 tets, 386 locked boundary vertices.
- Unguarded Python mean elapsed: 0.00662 s.
- Guarded fused-native mean elapsed: 0.00216 s.
- Guarded path is now faster than the old unguarded Python smoothing on this
  benchmark.
- Guarded moves: 613 accepted / 686 attempted, 73 rejected by quality, 0
  rejected by volume.

Verified:

- `cmake --build . --target native_tet_qopt`: passed.
- `python3 -m pytest tests/test_native_tet_qopt_extension.py tests/test_native_tet_qopt_smooth.py -q`: 12 passed.
- Native tet guard with QOPT tests: 120 passed.
- Focused E2E `/tmp/autotessell_qopt4_focus_v1`: 3/3 PASS.
- Full native-tet replacement matrix `/tmp/autotessell_qopt4_matrix_v1`: 120/120 PASS.

Main metric movement versus `/tmp/autotessell_qopt2_matrix_v1`:

- No metric changes on the 120-case matrix.
- Worst non-ortho unchanged: `mixed_watertight_and_open.stl__scale_aniso` 73.03.
- Worst skew unchanged: `pipe.step` 2.761.
- Worst aspect unchanged: `04_extreme_gear.stl` 99.77.
- Matrix elapsed sum improved from about 1401 s to 1321 s.

Next coding card:

- `QOPT5-FLIP-GATE`: route one topology-changing operation through the same
  local quality-vector gate. Start with the smallest low-risk internal flip
  candidate and keep rollback/positive-volume/fidelity guards mandatory.

## 2026-07-21 Moderate-Euler Hull Tuning Result

Change: `_build_inside_grid_tets` now uses a smaller default grid factor for
moderate positive-Euler dirty hulls (`10 <= euler <= 128`, aspect <= 3). Early
dirty cap hull rescue keeps its dense factor (`AUTO_TESSELL_DIRTY_HULL_GRID_FACTOR`,
default 1.5) so hemisphere-open cases do not regress.

Verified:

- `python3 -m pytest tests/test_native_tet_harness.py -q`: 23 passed.
- `python3 -m pytest tests/test_native_tet_harness.py tests/test_native_tet_convex_extrusion.py tests/test_native_tet_rescue_gate.py tests/test_native_tet_thin_extrusion.py tests/test_native_bl_helpers.py tests/test_tier_native_tet_kwarg_filter.py -q`: 108 passed.
- `/tmp/autotessell_native_tet_replacement_matrix_moderate_euler_v2`: 120/120 PASS.

Main metric movement versus `/tmp/autotessell_native_tet_replacement_matrix_hemi_v1`:

- `mixed_watertight_and_open.stl`: cells 6732 -> 3000, non-ortho 72.76 -> 70.92,
  skew 3.37 -> 2.26, aspect 31.01 -> 79.61.
- Worst skew in the matrix moved from `mixed_watertight_and_open.stl` 3.37 to
  `many_small_features_perforated_plate.stl` 3.34.
- Worst non-ortho unchanged at 73.03.
- Worst aspect unchanged at `04_extreme_gear.stl` 99.77.
- `hemisphere_open.stl` and `hard_100030.stl` focused metrics stayed unchanged
  after restoring the dense early dirty-hull factor.

Keep rationale: removes the current worst-skew case and reduces cell count for the
mixed dirty/open hull path while preserving the 120-case gate. Residual risk: aspect
for mixed dirty/open rises, so the next optimizer card should target aspect with
local quality-vector operations rather than more grid-factor heuristics.

## 2026-07-21 BL Side-Quad Skew Result

Change: `AUTO_TESSELL_BL_SIDE_KEEP_QUAD_FLATNESS` default changed from `0.80`
to `0.0`. Flat BL side quads are now kept unless the owner-centre skew scorer
shows that a triangular split is better.

Reason: on the perforated plate, splitting nearly flat side quads created the
matrix worst boundary skew. Keeping the flat quad preserves the finite-volume
face centre/normal relation better for this front.

Verified:

- `python3 -m pytest tests/test_native_bl_helpers.py -q`: 62 passed.
- `python3 -m pytest tests/test_native_tet_harness.py tests/test_native_tet_convex_extrusion.py tests/test_native_tet_rescue_gate.py tests/test_native_tet_thin_extrusion.py tests/test_native_bl_helpers.py tests/test_tier_native_tet_kwarg_filter.py -q`: 108 passed.
- `/tmp/autotessell_native_tet_replacement_matrix_bl_keepquad_v1`: 120/120 PASS.

Main metric movement versus `/tmp/autotessell_native_tet_replacement_matrix_moderate_euler_v2`:

- `many_small_features_perforated_plate.stl`: skew 3.34 -> 1.61.
- cells, non-ortho, aspect, and min face weight unchanged for that case.
- Matrix worst skew moved from 3.34 to `03_hard_bracket.stl` 2.90.
- Matrix worst non-ortho unchanged at 73.03.
- Matrix worst aspect unchanged at `04_extreme_gear.stl` 99.77.

Keep rationale: this is a topology representation fix, not a geometry heuristic.
It lowers boundary skew in the worst case with no observed regression in the
120-case gate.

## 2026-07-21 QOPT5/VVV7 Plateau Diagnosis

Change:

- `flip_faces_23` now uses the QOPT sorted quality-vector gate instead of only
  minimum-quality comparison.
- VVV7/VVV8 smoothing now builds neighbor lists only for top-K candidate
  vertices, not for the full mesh.
- `max_input_vertices` guard now runs before rescue paths, so oversized inputs
  cannot bypass the OOM guard.

Verified:

- `python3 -m pytest tests/test_native_tet_phaseB.py tests/test_native_tet_phaseE.py tests/test_native_tet_constraints.py tests/test_flip_signed_validity.py -q`: 35 passed.
- Native tet guard with QOPT tests: 155 passed.
- Focused E2E `/tmp/autotessell_qopt5_focus_v1`: 3/3 PASS.
- Full matrix `/tmp/autotessell_native_tet_qopt5_vvv7_matrix_v1`: 120/120 PASS.

Main metric movement versus `/tmp/autotessell_qopt4_matrix_v1`:

- No metric changes on the 120-case matrix.
- Worst non-ortho unchanged: `mixed_watertight_and_open.stl__scale_aniso` 73.03.
- Worst skew unchanged: `pipe.step` 2.761.
- Worst aspect unchanged: `04_extreme_gear.stl` 99.77.
- Matrix elapsed sum: 1320.9 s -> 1372.6 s; generator time 51.5 s -> 54.6 s.
  Treat as runtime-neutral/regressed until repeated under lower system noise.

Why local improvement has plateaued:

- The current default path rarely creates acceptable local candidates for the
  worst matrix cases. Quality-vector gates keep meshes safe, but they cannot
  improve cases where the candidate set is too small or topology is unchanged.
- `2-3/3-2/4-4` flips and local Laplacian moves have a small cavity. Literature
  reports that limited local flips plateau on hard slivers and recommends larger
  cavity reconstruction, edge removal, vertex insertion, and global schedules.
- TetWild/fTetWild quality comes from an interleaved pipeline: robust triangle
  insertion, envelope constraints, and repeated optimization while maintaining a
  valid tetrahedralization. We currently have partial pieces, not the same
  schedule.

Research-backed next cards:

- `CDT1`: add a robust constrained-Delaunay/triangle-insertion gate for one
  hard case family, starting with dirty/open `mixed_watertight_and_open`.
  Reference: Diazzi et al. 2023/2024 robust CDT, 100% Thingi10k-valid success.
- `MFRC1`: implement a bounded multi-face reconstruction cavity for worst local
  slivers where ordinary flips fail. Reference: Ma and Wang 2021 MFRC.
- `STELLAR1`: port one edge-removal / vertex-insertion cleanup pass from the
  Stellar/Klingner-Shewchuk line, guarded by the QOPT sorted quality vector.
- `FTW-SCHED1`: change scheduling, not single kernels: interleave insertion,
  envelope projection, smoothing, and cleanup before final BL, matching fTetWild
  more closely.

Useful sources:

- TetWild: https://www.cs.toronto.edu/~jacobson/images/tetrahedral-meshing-in-the-wild-siggraph-2018-compressed-hu-et-al.pdf
- fTetWild: https://arxiv.org/abs/1908.03581
- Freitag/Ollivier-Gooch smoothing/swapping: https://people.eecs.berkeley.edu/~jrs/meshpapers/FreitagGooch.pdf
- Aggressive Tetrahedral Mesh Improvement: https://people.eecs.berkeley.edu/~jrs/papers/aggress.pdf
- Stellar/Klingner thesis: https://people.eecs.berkeley.edu/~jrs/stellar/KlingnerPhD_small.pdf
- MFRC: https://pmc.ncbi.nlm.nih.gov/articles/PMC8611015/
- Robust CDT DOI: https://dl.acm.org/doi/10.1145/3618352

## 2026-07-22 Research-Backed Parallel Work

Native tet:

- `CDT1`: added `diagnose_cdt_recovery_blockers()` and plateau logging around
  `run_cdt_recovery`. This records whether missing surface edges are blocked by
  duplicate midpoint candidates, no cavity, oversized cavity, protected-edge
  encroachment, empty boundary, or insertion-ready status.
- `MFRC1`: added standalone bounded edge-ring MFRC helper. It enumerates small
  ring retriangulations, preserves cavity boundary faces and volume, then accepts
  only when the sorted quality vector improves.
- `STELLAR1`: added guarded edge-midpoint insertion cleanup helper with volume
  and QOPT sorted-quality-vector acceptance.

Verified:

- `python3 -m pytest tests/test_native_tet_cdt_recovery.py tests/test_native_tet_mfrc.py tests/test_native_tet_stellar.py -q`: 11 passed.
- Native tet guard with CDT/MFRC/Stellar tests: 166 passed.

Parallel hex/poly:

- Hex-dominant planning: `docs/references/hex_meshing/native_hex_dominant_upgrade_plan_2026-07-22.md`.
  First implementation cards completed: `HEXDOM-WALL1` and `HEXDOM-FINAL1`.
- Native poly planning: `docs/references/poly_meshing/native_poly_upgrade_plan_2026-07-22.md`.
  First implementation cards completed: `POLY-WALL1` and `POLY-BL1`.

Cross-engine verified:

- `python3 -m pytest tests/test_native_hex.py tests/test_native_hex_snap.py tests/test_native_poly.py tests/test_native_poly_harness_edge.py tests/test_native_poly_dual.py tests/test_tier_layers_post_routing.py tests/test_tier_layers_post_bl_phase2.py tests/test_native_tet_cdt_recovery.py tests/test_native_tet_mfrc.py tests/test_native_tet_stellar.py -q`: 124 passed.

Next active cards:

- `HEXDOM-DIST1`: exact/bounded surface-band diagnostic for adaptive hex
  refinement, replacing centroid-only decisions step by step.
- `POLY-TOPO1`: provenance-preserving topology/role helper for native poly.
- Native tet next: use CDT plateau diagnostics on hard cases, then choose
  insertion-ready vs shell-cavity recovery path based on dominant blocker count.
