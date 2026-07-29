# Native Polyhedral Engine Upgrade Plan

**Date:** 2026-07-22

**Scope:** `core/generator/native_poly/**`, `core/generator/polymesh_writer.py`, the shared boundary-layer path, native pybind topology, and their tests

**Constraint:** preserve the Python public API, CLI behavior, and native-to-Python fallback

## 1. Executive decision

The next native-poly milestone is semantic and topological correctness, not another isolated quality heuristic.

The production architecture should become:

```text
typed source patches
  -> immutable face provenance and semantic roles
  -> wall-only prism shell
  -> constrained tetrahedral core
  -> dualize the tetrahedral core only
  -> conformal prism/poly transition
  -> validity-barrier quality optimization
  -> provenance-preserving polyMesh writer
```

The current direct Voronoi prism insertion in `voronoi.py` should be quarantined behind an experimental flag. It does not know patch roles, does not reliably honor the public layer count, and cannot guarantee a conformal multi-layer interface. The existing shared `native_bl` and `poly_bl_transition` paths are the better short-term foundation.

The long-term pure-poly route should replace clipping and vertex snapping with VoroCrust-style paired boundary sites, then optimize interior sites with an actual CVT objective. This is a later phase because boundary semantics and wall-layer topology must be correct first.

## 2. Non-negotiable contracts

These are hard gates for every roadmap phase.

1. `bl_layers=0` creates zero prism cells.
2. BL is generated only on faces whose semantic role is `wall`.
3. `inlet`, `outlet`, `symmetry`, `symmetryPlane`, `empty`, and unknown patches create zero BL cells.
4. A patch name containing `wall` is not sufficient evidence that it is a wall.
5. An explicit wall selection may classify an otherwise unknown patch as a wall, but it must not silently override an explicitly non-wall role. Conflicts fail closed with a diagnostic.
6. Patch names, OpenFOAM geometric types, semantic roles, and source-face provenance survive generation, dualization, face merging, BL insertion, and writing.
7. Wall/non-wall patch-interface edges remain represented even when both patches are coplanar.
8. Negative cell volume, open cells, duplicate cells, non-manifold output faces, and inverted BL prisms are forbidden.
9. Failure in a new native path leaves the input mesh unchanged and falls back through the existing path.
10. User cell-budget accounting includes BL cells and transition cells.

`inlet` and `outlet` are often written as the OpenFOAM geometric type `patch`. Therefore the implementation must not overload one string with two meanings. It needs both `foam_type` and `semantic_role`.

## 3. Current implementation assessment

### 3.1 Verified baseline

The following read-only regression set passed on 2026-07-22:

```text
python3 -m pytest \
  tests/test_native_poly.py \
  tests/test_native_poly_dual.py \
  tests/test_native_poly_harness_edge.py \
  tests/test_write_generic_polymesh.py \
  tests/test_native_bl_helpers.py \
  tests/test_tier_layers_post_bl_phase2.py -q

138 passed in 70.35s
```

This baseline proves current test compatibility. It does not prove wall-only poly BL, mixed-patch preservation, general non-convex Voronoi clipping, or a conformal prism/poly interface; those cases are absent.

### 3.2 Direct Voronoi path

`core/generator/native_poly/voronoi.py` is a large experimental pipeline containing seed generation, clipping, repair, smoothing, writing, and BL insertion.

Critical findings:

- `_find_wall_adjacent_cells()` does not inspect patch names, patch types, or source-face roles. In practice it marks seed cells adjacent to ordinary Voronoi ridges, not wall-adjacent cells.
- `_generate_native_poly_voronoi_inner()` does not receive the public `bl_layers` value. The direct path can enter hard-coded BL logic even when the caller requests no layers.
- `_extrude_prism_layer()` assumes a cell's first face is the boundary face. That ordering is not a public topology invariant.
- Layer height, layer count, cell limits, and aspect cap are hard-coded in this path rather than derived from `BLConfig` and the user request.
- Boundary clipping applies input triangle supporting half-spaces. That is only a safe domain description for suitable convex geometry; a general non-convex triangulated boundary is not the intersection of all triangle half-spaces.
- Out-of-domain Voronoi vertices are snapped to nearest surface vertices instead of robust closest points with feature constraints.
- Candidate smoothing ranks non-orthogonality and skewness but does not impose a per-step positive-volume/star-shaped barrier.
- Dropping a bad polyhedral cell can create an unfilled cavity; it is not a topology repair.

`aniso_cvt.py` is also a prototype rather than an anisotropic CVT implementation. It computes curvature-derived scales, but the update is a nearest-surface-neighbour average rather than integration of a restricted Voronoi-cell energy. The scales do not define the actual assignment or centroid update. It should not be used as a quality guarantee.

### 3.3 Tet-to-poly dual path

`core/generator/native_poly/dual.py` is the more credible production core because it starts from the native tet engine and constructs a conformal dual.

Current limits:

- The dual uses tetrahedron centroids, boundary-face centroids, and edge midpoints. It is not a circumcentric Voronoi dual, so face orthogonality is not inherited automatically.
- The single `defaultWall` write path discards source patch roles and bypasses the generic writer classifier.
- Concave or non-star-shaped dual cells are not repaired with the topological subdivision described in the polyhedral-mesh literature.
- The optimizer is a boundary-locked Laplacian operation, not a condition-number or finite-volume-error objective with a validity barrier.
- The harness pass condition mainly checks cell existence and negative volume. Non-orthogonality, skewness, boundary error, topology, and patch preservation are not hard gates.
- The default harness does not carry BL configuration or patch metadata through dualization.

### 3.4 Quality and smoothing

`core/generator/native_poly/quality.py` currently reports useful first-order non-orthogonality and skewness values, but it is not sufficient as a production validator.

- Cell centres are averages of unique vertices, not volume centroids.
- There is no face non-planarity, cell-kernel/star-shaped, minimum pyramid volume, determinant, face-weight, volume-ratio, or boundary-fidelity metric.
- `drop_degenerate_poly_cells()` does not consume its non-orthogonality/skewness limits and can leave holes.
- `smooth_poly_in_memory()` and `smooth.py` do not reject individual moves that invert adjacent cells or worsen the hard quality gate.
- High aspect ratio in a valid wall-normal prism is not distinguished from harmful core-cell stretching.

### 3.5 PolyMeshWriter and native topology

`core/generator/polymesh_writer.py` and `auto_tessell_core/native_polymesh_bind.cpp` already provide a useful optional C++ topology path, but the writer currently loses information needed for safe BL and merging.

- Geometry-only boundary segmentation creates `wall_N` groups and assigns one supplied type. It cannot infer inlet, outlet, symmetry, or empty semantics.
- `SourceSurfacePatchClassifier` preserves a source name but currently returns `wall` for every source patch.
- Classification normally occurs after mesh generation, which is too late to decide where BL may be extruded.
- Native `build_topology()` does not return source face IDs or stable input-face-to-output-face mappings.
- A face referenced by more than two cells is reported but its first two references are still emitted as an internal face. Production mode should reject or explicitly repair it.
- If one face is degenerate, an entire cell can be dropped, potentially creating a hole.
- Greedy coplanar face merging does not prove polygon simplicity, area conservation, planarity, convexity/star-shaped validity of adjacent cells, or finite-volume metric non-regression.
- The existing C++ `build_quad_bl_topology()` accepts explicit wall face indices and boundary ranges. Its separation of selection and topology is useful, but it is quad-specific and does not solve semantic classification or general polygonal wall layers.

### 3.6 Shared BL path

`core/layers/native_bl.py::_collect_wall_faces()` has the right local behavior when patch metadata is already correct: it excludes typed inlet/outlet/symmetry/empty patches and honors explicit wall selection.

`core/layers/poly_bl_transition.py` is therefore the preferred integration point. It already expresses the intended hybrid model: preserve prism cells and dualize the tetrahedral core. Its current exact-coordinate interface matching and incomplete transition handling need strengthening, but this is safer than maintaining a second BL algorithm inside `voronoi.py`.

## 4. Literature synthesis and adopted decisions

### 4.1 Boundary-conforming Voronoi and patch preservation

**VoroCrust** constructs paired sites around a protected surface so the Voronoi boundary conforms without clipping. It supplies guarantees for non-convex and non-manifold domains and protects sharp features. This directly addresses the current half-space clipping and vertex-snapping weaknesses.

Adopt:

- Build a local-feature-size field and protect corners, feature edges, and surface patches.
- Generate paired inside/outside boundary sites whose bisector faces reproduce the boundary.
- Fill the interior only after the boundary seed shell is valid.
- Keep clipping only as a fallback, never as the final long-term geometry model.

The 2026 TU Delft implementation extends this idea to semantic CFD patches: an edge is protected when the patch group changes, even if its dihedral angle is small. This is current implementation evidence rather than a peer-reviewed theorem, but the patch-interface rule is directly applicable.

### 4.2 Tet-to-poly dual and polyhedral validity

Garimella, Kim, and Berndt construct dual polyhedra from tetrahedral meshes, collapse small entities, and optimize a corner condition-number objective. Their validity criterion uses signed tetrahedral/pyramid decompositions from a candidate cell centre; concave cases may require topological subdivision rather than vertex smoothing alone.

Adopt:

- Make the native-tet dual the production route before replacing it with a pure Voronoi engine.
- Evaluate alternative dual points: circumcenter for well-centred local tets, centroid or optimized constrained points elsewhere.
- Require a positive signed pyramid decomposition for every face of every poly cell.
- Repair concave/non-star-shaped cells by local split/subdivision; do not delete the cell.
- Constrain moved boundary points to their source facet/feature and use damped line search.

### 4.3 CVT and site optimization

Classical CVT work defines a density-weighted energy whose generators coincide with their Voronoi-cell mass centroids. Lloyd iteration is robust but slow. Lloyd-preconditioned L-BFGS is substantially faster on variable-resolution cases and applies to general domains.

Adopt only after robust boundary sites exist:

- Replace nearest-surface averaging with exact restricted-cell volume and centroid integration.
- Use a density field driven by target cell count, curvature, local feature size, gap width, and BL outer-front size.
- Freeze paired boundary sites and optimize interior sites with Lloyd-preconditioned L-BFGS.
- Rebuild the diagram after accepted steps and reject topology/validity regressions.
- Keep deterministic seed ordering and expose the actual CVT energy in diagnostics.

### 4.4 Finite-volume quality

Finite-volume literature identifies non-orthogonality, skewness, and polygon-face non-planarity as separate discretization-error sources. OpenFOAM additionally checks face weight, determinant, volume ratio, topology, and geometric consistency.

Adopt:

- Compute volume-weighted cell centroids and area-weighted face centres/normals.
- Report max, p95, p99, and bad-count distributions, not only means and maxima.
- Add face non-planarity and adjacent-cell signed pyramid minima.
- Use a validity barrier plus a weighted CFD objective; do not optimize a single metric at the expense of inversion or boundary drift.
- Treat `maxNonOrtho=70` and internal `maxSkewness=4` as compatibility defaults, while ranking candidates with tighter project targets.
- Preserve high-aspect wall prisms when volume, wall-normal alignment, growth, and transition metrics are valid.

### 4.5 Wall-only prism layers

Bottasso and Detomi assign BL attributes only to selected model faces, deflate the valid core, and fill the resulting void with prism stacks. Dyedov et al. use a gradient-limited local-feature-size field, offset faces, and variational optimization of shape and orthogonality. Ye et al. use a bijective mapping, auxiliary air tetrahedra, and positive-volume line search to generate full layers in narrow or complex regions. The open advancing-layer work emphasizes layerwise intersection checks and cache-coherent broad-phase filtering.

Adopt:

- Select wall faces before extrusion and keep the bitmap immutable.
- Use local feature size/gap width to cap total thickness while preserving requested layer count where possible.
- Use multiple normals or constrained shrinking/pruning at corners and ridges.
- Validate each accepted step with prism volume and auxiliary-cavity volume.
- On a wall/non-wall boundary edge, terminate the wall layer without assigning generated side faces to `wall`; stitch them to the adjacent non-wall patch or a valid core-transition interface according to geometry.
- Generate the BL shell before final poly-core optimization, then freeze wall-normal topology.

### 4.6 Face merging

Face merging is acceptable only as a local topology operation with rollback. The merged polygon must be simple, sufficiently planar, area-conserving, consistently oriented, and valid for both adjacent cell decompositions. It must not cross a source patch or semantic-role boundary. A merge is kept only when hard validity remains true and the finite-volume objective does not regress beyond tolerance.

## 5. Target internal architecture

No public signature needs to change. Add internal typed state and adapt at existing API boundaries.

```text
BoundaryIntent
  patch_id
  source_name
  output_name
  foam_type        # wall | patch | symmetryPlane | empty | ...
  semantic_role    # wall | inlet | outlet | symmetry | empty | unknown
  source_face_ids
  provenance_confidence
  bl_enabled

PolySurfaceState
  vertices, triangles
  triangle_intent_ids
  protected_edges, protected_vertices
  closest-source queries
  local_feature_size, target_size

PolyCellState
  points, cell_faces, cell_types
  cell_source_ids
  face_source_ids
  owner, neighbour
  boundary_intent_ids
  validity, quality
  stage_timings, fallback_trace
```

### 5.1 Role resolution

Resolve roles once, before meshing and BL:

1. Explicit structured user metadata.
2. Explicit wall patch names, unless they conflict with an explicit non-wall role.
3. Source patch metadata/provenance.
4. Conservative geometric/name inference with a confidence flag.
5. `unknown` if unresolved.

Only `semantic_role == wall` sets `bl_enabled=true`. Unknown must fail closed for BL. A legacy single-patch STL may retain the current all-wall behavior only through an explicit compatibility policy that is visible in diagnostics, not through an accidental `defaultWall` name.

### 5.2 Production pipeline

1. **Surface ingest and semantic classification**
   - Build `BoundaryIntent` and per-triangle IDs.
   - Protect geometric features and every patch-role interface.
   - Reject/repair duplicate, zero-area, self-intersecting, or non-manifold source topology before poly generation.

2. **Wall-only BL shell**
   - Feed only wall faces to shared `native_bl`.
   - Use feature-size, collision, positive-volume, and line-search infrastructure already developed there.
   - Preserve non-wall boundary faces unchanged.
   - Emit a closed, explicitly tagged outer interface for the core.

3. **Constrained tet core**
   - Fill the region inside the BL outer interface plus all non-wall boundaries with native tet.
   - Freeze prism-top/interface vertices or constrain their movement to the interface.

4. **Hybrid dualization**
   - Preserve prisms.
   - Dualize only tet-core cells.
   - Build prism/poly interface faces from shared topology IDs, not floating-point coordinate equality.
   - Locally split bad dual cells near concave interfaces.

5. **Constrained quality optimization**
   - Optimize interior poly points and allowable interface tangential degrees of freedom.
   - Use positive-volume/star-shaped barriers, boundary envelopes, and rollback.

6. **Writer and final validation**
   - Carry face provenance through native topology and merging.
   - Group boundary faces by `BoundaryIntent`, never by geometry alone.
   - Run topology, geometry, patch, BL, quality, target-cell, and deterministic-output checks.

### 5.3 Long-term pure Voronoi option

After the hybrid route is stable:

1. Implement VoroCrust-style surface sizing and paired boundary sites in a separate C++23 pybind target.
2. Protect role-change edges independently from feature angle.
3. Generate interior sites from the target density field.
4. Optimize with exact CVT energy and Lloyd-preconditioned L-BFGS.
5. Add the wall prism shell using a conformal interface method, not per-cell face extrusion.
6. Keep the tet-dual route as fallback and differential oracle.

## 6. Prioritized roadmap

### P0. Semantic boundary contract and honest baseline

Deliverables:

- Internal `BoundaryIntent`/role model.
- Pre-generation source-face classification.
- Stable face provenance IDs through writer/native topology.
- Report fields for selected wall faces, rejected non-wall faces, role confidence, and fallback path.
- Mixed-patch tests proving zero non-wall extrusion.

Exit gates:

- `bl_layers=0` creates zero prism cells on every native-poly path.
- Duct, symmetry, and empty cases retain exact patch roles/counts.
- Unknown patch is not silently layered.
- Existing 138-test baseline remains green.

### P1. One shared wall-only BL path

Deliverables:

- Direct `_extrude_prism_layer()` disabled by default.
- Public `bl_layers` and wall selection routed through `poly_bl_transition`/`native_bl`.
- Atomic execution: failure restores the unlayered mesh before fallback.
- Interface IDs replace coordinate-equality matching.
- Requested layer count, first height, total thickness, and growth are reported.

Exit gates:

- Non-wall BL coverage is exactly 0%.
- Requested wall BL coverage is 100%, or every safe termination is explicitly counted and located.
- No void, overlap, open cell, non-manifold face, or negative prism exists.
- Generated wall/non-wall termination faces have the correct adjacent non-wall role or internal transition role.

### P2. Topology and quality hardening

Deliverables:

- Volume centroids, robust face geometry, face non-planarity, signed pyramid minima, face weight, determinant, and volume ratio.
- Hard rejection of non-manifold output instead of emitting the first two references.
- Topological repair/split for bad poly cells instead of deletion.
- Provenance-aware guarded face merging with rollback.
- Validity-barrier local optimizer.

Exit gates:

- All cells have closed oriented boundaries and positive signed decompositions.
- Every internal face has exactly two cells; every boundary face has exactly one.
- Merging never crosses patch/provenance boundaries and never worsens the hard quality gate.
- `checkMesh` topology and geometry checks pass where OpenFOAM is available.

### P3. Robust tet-to-poly dual

Deliverables:

- Local dual-point policy based on tet well-centredness and optimized alternatives.
- Concave/non-star-shaped cell split templates.
- Patch-aware generic writer path for dual output.
- BL-prism-preserving core dualization as the default native-poly strategy.

Exit gates:

- Boundary Hausdorff error remains inside the source-envelope tolerance.
- Candidate quality is no worse than its tet-core baseline on the project quality score.
- Cell target error, including BL/transition cells, is at most 15% on the standard corpus and 25% on documented extreme cases.
- No fallback is hidden; strategy and reason are present in the report.

### P4. Boundary-conforming Voronoi and real CVT

Deliverables:

- Paired boundary-site shell with feature and patch-interface protection.
- Local-feature-size/target-density field.
- Exact restricted-cell mass/centroid and CVT energy.
- Lloyd-preconditioned L-BFGS interior-site optimizer.
- Deterministic C++23/pybind implementation with tet-dual fallback.

Exit gates:

- Non-convex and narrow-gap corpus requires no final triangle-half-space clipping.
- Boundary cells conform without nearest-surface-vertex snapping.
- Patch interfaces are reproduced exactly in topology.
- CVT energy decreases monotonically across accepted iterations and all hard validity gates remain true.

### P5. Production performance and broad regression

Deliverables:

- SoA/CSR topology, stable integer IDs, contiguous adjacency, spatial broad phase, and GIL-free C++ kernels.
- Stage-level profiling and deterministic parallel execution.
- 100+ STL/CAD-derived regression corpus covering manifold, dirty, concave, thin-gap, multi-patch, and high-curvature cases.
- Sanitizer and repeated-run determinism jobs.

Exit gates:

- End-to-end median and p95 improve against the recorded baseline without quality/semantic regression.
- Native pybind is at least as fast as the retained ctypes path; otherwise ctypes remains.
- Peak RSS and long-tail cases are recorded, not hidden by median-only reporting.

## 7. First three worker coding cards

### Card 1: `POLY-WALL1` - typed boundary intent and strict wall mask

Scope:

- Add an internal typed boundary-intent record with separate `foam_type` and `semantic_role`.
- Extend source-face provenance to carry an intent ID before any generator or BL stage.
- Resolve explicit wall names, source metadata, and unknown roles with the precedence in Section 5.1.
- Make the BL selector consume an immutable wall-face bitmap.
- Preserve the existing public API by adapting current strings/callbacks at the boundary.

Tests:

- Rectangular duct: four walls, one inlet, one outlet.
- Mixed wall/symmetry/empty case.
- Coplanar wall/inlet interface that must remain protected.
- Patch named `wall_like` but explicitly typed/marked as inlet.
- Explicit wall request conflicting with explicit outlet role.
- Unknown single/multiple patches and legacy compatibility diagnostics.

Acceptance:

- Non-wall selected/extruded face count is zero.
- Output patch names, roles, types, and face counts match input intent.
- Python and native topology paths produce identical intent IDs.
- No public function signature or fallback behavior changes.

### Card 2: `POLY-BL1` - unify on shared BL and honor public controls

Scope:

- Route native-poly layer requests through `poly_bl_transition` and `native_bl`.
- Disable direct Voronoi `_extrude_prism_layer()` by default; retain it only as an explicit experimental fallback during parity work.
- Thread `bl_layers`, heights/growth, and wall intent IDs through the dual/harness/tier path.
- Replace exact-coordinate interface matching with stable point/face/interface IDs.
- Make the operation transactional so any failed layer/transition validation restores the original mesh.

Tests:

- `bl_layers=0`, `1`, `2`, and `4` on a mixed-patch duct.
- Wall-only partial patch, wall-wall feature ridge, wall-inlet edge, symmetry edge, and narrow gap.
- Injected native exception proving Python/unlayered fallback and unchanged input.
- Repeated invocation in one process to detect stale native state.

Acceptance:

- Exact requested layer count where collision-free.
- Zero non-wall prism bases.
- Zero negative prism/poly volumes and zero open/non-manifold interface faces.
- Wall boundary faces remain wall; termination faces receive the correct non-wall/internal role.
- Existing native-poly and native-BL guards remain green.

### Card 3: `POLY-TOPO1` - provenance-aware native topology and safe face merge

Scope:

- Extend `native_polymesh.build_topology()` to return stable input-cell/input-face mappings and boundary intent IDs.
- Reject more-than-two-cell face incidence in strict mode; preserve the existing fallback path for compatibility diagnostics.
- Implement guarded merge predicates: same owner/neighbour or same boundary intent, shared edge, simple polygon, area conservation, normal agreement, planarity, valid adjacent signed pyramids, and quality non-regression.
- Roll back rejected merges and expose reason counters.
- Stop dropping a complete cell as an implicit repair for one degenerate face.

Tests:

- Two-cell shared face, boundary-only cell, duplicate/reversed face, and three-cell non-manifold face.
- Concave merge, self-intersecting merged loop, non-planar faces, collinear vertices, and near-zero shared edge.
- Coplanar faces from different semantic patches must not merge.
- C++/Python differential parity under cell/face/vertex-order permutations.

Acceptance:

- No topology/provenance loss.
- Every kept merge passes all hard validity predicates.
- Non-manifold input fails explicitly or falls back without emitting a falsely valid mesh.
- The kernel is measurably faster than the Python fallback on the writer benchmark and does not regress command-level E2E by more than 5%.

## 8. Test plan

### 8.1 Unit and differential tests

Add focused tests without replacing current guards:

```text
tests/test_native_poly_boundary_intent.py
tests/test_native_poly_wall_only_bl.py
tests/test_native_poly_transition.py
tests/test_native_poly_validity.py
tests/test_native_polymesh_extension.py
```

Required checks:

- Native/Python parity for topology, face geometry, validity, quality, and intent mapping.
- Face/cell permutation invariance and deterministic ordering.
- Degenerate/empty input behavior.
- Atomic fallback after injected allocation, native, collision, and quality failures.
- Repeated same-process execution.

### 8.2 Geometry corpus

Minimum targeted cases:

1. Cube and two-cell shared-face synthetic meshes.
2. Six-patch duct: four walls, inlet, outlet.
3. Wedge/symmetry case and 2-D front/back `empty` case.
4. Cylinder/pipe with wall-only BL.
5. NACA/external body with farfield non-wall patches.
6. Concave L-bracket and re-entrant corner.
7. Narrow U-gap and nearly touching surfaces.
8. Multi-component and nested shell.
9. Non-manifold, duplicated, open, and self-intersecting dirty inputs for explicit repair/fallback behavior.
10. Curved high-aspect and thin-feature cases from the existing project corpus.

### 8.3 Hard validation

For every E2E case record and gate:

- patch name/type/role and face count;
- wall requested/covered/terminated face counts;
- non-wall BL face count, which must be zero;
- actual layer distribution, first height, total thickness, growth, and wall-normal angle;
- points, cells by type, faces, and target-cell error;
- open/duplicate/non-manifold faces and disconnected cells;
- negative/min cell volume and minimum signed pyramid;
- max/p95/p99 non-orthogonality and skewness;
- face non-planarity, face weight, determinant, volume ratio, and aspect distribution by core/BL/transition class;
- source-surface Hausdorff and patch-interface error;
- `checkMesh` output where available.

### 8.4 Existing guards

Keep at least:

```text
python3 -m pytest tests/test_native_poly.py -q
python3 -m pytest tests/test_native_poly_dual.py tests/test_native_poly_harness_edge.py -q
python3 -m pytest tests/test_write_generic_polymesh.py tests/test_native_polymesh_extension.py -q
python3 -m pytest tests/test_native_bl_helpers.py tests/test_tier_layers_post_bl_phase2.py -q
```

Add the new mixed-patch wall-only suite to the required guard before enabling any new path by default.

## 9. Benchmark plan

### 9.1 Reproducible record

Write JSON and CSV records keyed by:

- commit hash and dirty-worktree flag;
- OS, CPU, compiler, build type, thread count, Python/NumPy/SciPy version;
- strategy (`tet_dual`, `direct_voronoi`, fallback), native module path, and fallback trace;
- case hash, source triangle count, requested cells, BL settings, and patch-role counts;
- stage timings and peak RSS.

Stages:

```text
surface ingest/classify
source repair/provenance
wall BL
tet core
dual/Voronoi construction
transition stitching
quality optimization
topology/merge/write
final validation
total
```

### 9.2 Benchmark matrix

Run warm-up plus at least five measured repetitions for small cases and three for large cases:

- cube: 1k, 10k, 100k target cells, no BL;
- mixed-patch duct: 10k/100k with 0, 2, and 5 wall layers;
- cylinder/pipe: curved wall, inlet/outlet;
- NACA/external body: body wall plus farfield patches;
- concave L-bracket;
- narrow U-gap;
- one dirty-surface fallback case;
- one 1M-cell scalability case after correctness phases pass.

Compare Python fallback, existing ctypes/native paths where present, and new pybind paths. Compare command-level E2E, not only microkernels.

### 9.3 Acceptance policy

Hard semantics/topology always override speed:

- Any non-wall BL cell, negative cell, open interface, patch-role loss, or boundary-envelope violation rejects the candidate.
- A native microkernel is kept only if its E2E case is not slower by more than 5% and its own stage is clearly faster.
- For stable pybind kernels, require parity across two full regression runs before removing a ctypes fallback.
- Track median and p95. A median win with a severe p95 or RSS regression is not sufficient.
- Target-cell accuracy includes all prism and transition cells.

## 10. Risk register

| Risk | Consequence | Mitigation |
|---|---|---|
| STL carries no semantic BC metadata | Wall-only BL cannot be inferred reliably | Require explicit metadata or conservative unknown; make legacy all-wall behavior explicit and reported |
| Patch classification occurs after generation | BL already extruded on wrong faces | Move role resolution to surface ingest and carry immutable IDs |
| Wall/non-wall interface topology | Cracks, artificial walls, or wrong inlet area | Protect role-change edges; explicit termination/interface IDs and manifold checks |
| Prism/poly dual mismatch | Duplicate/open interface faces | Dualize only tet core; preserve prism topology; match integer IDs, not coordinates |
| Concave/non-star-shaped poly cells | Invalid volume and solver failure | Signed-pyramid barrier plus local topological split |
| High prism aspect is treated as globally bad | Useful wall layers are collapsed | Evaluate BL-specific normal/growth/volume metrics separately from core aspect |
| Greedy face merge | Non-planar/self-intersecting faces and quality regressions | Full predicates, adjacent-cell validity, objective check, rollback |
| CVT moves boundary or patch interface | Geometry/BC drift | Freeze paired boundary sites and protected edges; boundary envelope gate |
| Pure-Python/SciPy Voronoi scaling | Excess runtime/memory and GIL cost | C++23 target after algorithm stabilizes; CSR/SoA and local diagrams |
| New native exception leaves partial files | Corrupted fallback input | Transactional temporary state and atomic final write |
| Concurrent dirty worktree | Accidental loss or mixed attribution | Worker reviews current diff, edits only card scope, never reverts unrelated changes |

## 11. Research sources used

### Accessible primary/current sources

- Abdelkader et al., **VoroCrust: Voronoi Meshing Without Clipping**, ACM TOG 2020. [Open manuscript](https://arxiv.org/abs/1902.08767), [DOI](https://doi.org/10.1145/3337680).
- Abdelkader et al., **Sampling Conditions for Conforming Voronoi Meshing by the VoroCrust Algorithm**. [Open manuscript](https://arxiv.org/abs/1803.06078).
- Sárkány, **Voronoi mesh generation tailored for urban flow simulations**, TU Delft, 2026. [Repository and full thesis](https://repository.tudelft.nl/record/uuid%3A38622300-9903-4502-8311-d2d41f2bd1dd).
- Garimella, Kim, and Berndt, **Polyhedral Mesh Generation and Optimization for Non-manifold Domains**, IMR 2013. [Accessible author copy/index](https://www.researchgate.net/publication/261948732_Polyhedral_Mesh_Generation_and_Optimization_for_Non-manifold_Domains), [DOI](https://doi.org/10.1007/978-3-319-02335-9_18).
- Garimella and Shephard, **Boundary layer meshing for viscous flows in complex domains**, IJNME 2000. [Open mirror](https://oss.jishulink.com/caenet/forums/upload/2006/8/9/7890f921-cf99-426b-b5a0-c99b537847e3.pdf), [DOI](https://onlinelibrary.wiley.com/doi/abs/10.1002/1097-0207%2820000910/20%2949%3A1/2%3C193%3A%3AAID-NME929%3E3.0.CO%3B2-R).
- Du, Faber, and Gunzburger, **Centroidal Voronoi Tessellations: Applications and Algorithms**, SIAM Review 1999. [Open manuscript](https://people.sc.fsu.edu/~mgunzburger/files_papers/gunzburger-cvt-siamreview.pdf).
- Du and Gunzburger, **Grid Generation and Optimization Based on Centroidal Voronoi Tessellations**, Applied Mathematics and Computation 2002. [Open manuscript](https://people.sc.fsu.edu/~mgunzburger/files_papers/gunzburger-cvt-grid1.pdf).
- Yang, Gunzburger, and Ju, **Fast Spherical Centroidal Voronoi Mesh Generation: A Lloyd-preconditioned LBFGS Method in Parallel**, JCP 2018. [Open manuscript](https://arxiv.org/abs/1709.06924), [DOI](https://doi.org/10.1016/j.jcp.2018.04.034).
- Denner et al., **Minimizing finite-volume discretization errors on polyhedral meshes**, APS DFD 2017. [Abstract and method summary](https://meetings-archive.aps.org/dfd/2017/e32/5/).
- Ye et al., **Fast advancing layer method for viscous mesh generation**, Chinese Journal of Aeronautics 2023. [Open article](https://www.sciencedirect.com/science/article/pii/S100093612300170X), [DOI](https://doi.org/10.1016/j.cja.2023.05.018).
- OpenFOAM Foundation, **snappyHexMesh layer generation and quality controls**. [User guide](https://doc.cfd.direct/openfoam/user-guide-v13/snappyhexmesh), [checkMesh source](https://cpp.openfoam.org/v13/applications_2utilities_2mesh_2manipulation_2checkMesh_2checkMesh_8C_source.html), [boundary types](https://doc.cfd.direct/openfoam/user-guide-v8/boundaries).

### Local full-text sources

- Bottasso and Detomi, **A procedure for tetrahedral boundary layer mesh generation**, `docs/references/mesh-quality/tetrahedral-boundary-layer-mesh-generation-2002.pdf`.
- Dyedov et al., **Variational generation of prismatic boundary-layer meshes**, `docs/references/mesh-quality/variational-prismatic-boundary-layer-meshes-2009.pdf`.
- Ye et al., **Robust full-layer prismatic mesh generation based on bijective mapping**, JCP 2025, `docs/references/mesh-quality/robust-full-layer-prismatic-mesh-generation-2025.pdf`, [DOI](https://doi.org/10.1016/j.jcp.2025.113744).

### Relevant full texts still inaccessible/paywalled

These are useful but not required for Cards 1-3. The first is the highest-value missing paper for a later pure Voronoi/prism route.

1. Gan and Liu, **Automatic and efficient hybrid viscous mesh generation based on clipped Voronoi diagrams**, IJNME 2019. [Publisher/DOI](https://doi.org/10.1002/nme.5963).
2. Syrakos et al., **A priori mesh quality metrics for three-dimensional hybrid grids**, JCP 2015. [Publisher/DOI](https://doi.org/10.1016/j.jcp.2014.09.036).
3. Roget et al., **Prismatic mesh generation using minimum distance fields**, Computers & Fluids 2020. [Publisher/DOI](https://doi.org/10.1016/j.compfluid.2020.104429).

## 12. Final recommendation

Start with `POLY-WALL1`, then `POLY-BL1`, then `POLY-TOPO1`. Do not start C++ VoroCrust or CVT work until these semantic and topology gates pass. The immediate quality gain will come from making the existing tet-dual plus shared-prism architecture correct and measurable; the pure boundary-conforming Voronoi engine is the subsequent research milestone.
