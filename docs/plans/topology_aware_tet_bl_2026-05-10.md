# Topology-Aware Tet + BL Recovery Plan

Date: 2026-05-10

## Goal

Make the strict tet + BL(3) bench pass for:

- `test_cube.stl`
- `tests/stl/thingi10k_bench20/*.stl`

The verifier is:

```bash
AUTO_TESSELL_VERIFY_MAX_CELLS=10000 \
AUTO_TESSELL_VERIFY_BL_LAYERS=3 \
AUTO_TESSELL_VERIFY_ENGINES=tet \
timeout 1800 python3 tests/stl/verify_autoresearch_mesh_matrix.py
```

Acceptance: `tet_failed_case_count == 0`, exact `bl_used_layers == 3`, no
wrong-tier fallback success counting, and the evaluator gates in
`agents/specs/evaluator.md` stay authoritative.

## Current State

Latest retained full verifier result:

- `tet_failed_case_count = 16`
- `pass_count = 5/21`
- `fail_count = 28`
- Failure reasons: `hausdorff=15`, `surface_area=9`, `determinant=2`,
  `non_ortho=1`, `face_weight=1`

Two fundamentally different paths are failing:

1. `axis_extrusion` cap fastpath:
   - FVM quality is usually good.
   - Geometry fidelity fails because constant cap sweep cannot represent
     holes, changing section count, or side-surface variation.
2. exact WildMesh + native BL:
   - Geometry fidelity/topology are often good.
   - FVM fails at BL/bulk transition because bad internal faces remain near
     90 degree non-orthogonality and low face weight.

Recent retained building blocks:

- `62b0ff59` adds `native_bl_quality.fastpath.section_topology` metadata.
- `8411c043` adds unit coverage for stable interior-hole section detection.

## What Has Been Ruled Out

The following were tried and discarded or recorded as no-pass:

- Scalar BL thickness/growth sweeps.
- WildMesh epsilon/coarsen/simplify flags.
- Interior Laplacian smoothing.
- Full nearest-surface boundary snapping.
- Cap-to-midsection replacement.
- Boundary-only section projection.
- Affine least-squares section projection.
- Harmonic/Laplacian section-stack mapping.
- Simple bad-face agglomeration.
- Targeted VD rescue for `extreme_1017013`.
- Existing external tet tiers (`meshpy`, `netgen`, `tetwild`) as oracle
  replacements under `max_cells=10000`.

These failures mean the next work must be topology-changing, not another knob.

## Design Direction A: Topology-Aware Sweep Fastpath

Use this for cap-fastpath Hausdorff/surface-area failures.

### A1. Section Topology Classifier

Files:

- `core/generator/tier_wildmesh.py`
- `tests/test_generator.py`

Input: `fastpath.section_topology`, cap loop/hole counts, section area range.

Output classification:

- `constant_prism`: cap topology and interior section topology match, area range
  small.
- `stable_hole_sweep`: interior sections are stable but differ from cap topology
  by holes.
- `changing_section_sweep`: polygon or hole counts change along the axis.
- `unsafe_sweep`: missing or fragmented sections.

Gate:

- Current `axis_extrusion` stays active for `constant_prism`.
- Other classes must not use the current cap-only fastpath by default once a
  replacement exists.

Verify:

```bash
timeout 60 python3 -m pytest tests/test_generator.py -q -k "tier_wildmesh"
```

### A2. Stable-Hole Sweep Candidate

Scope: start with `easy_100423`-style stable one-polygon/one-hole sections.

Algorithm:

1. Sample sections at `z = linspace(0.02, 0.98, n_z+1)`.
2. Require every section to have the same polygon count and hole count.
3. Build boundary correspondence per loop by normalized arclength.
4. Generate each layer boundary from the actual section.
5. Build side faces only if every quad/triangle side candidate passes:
   - no zero area
   - face warpage below threshold
   - no triangle-triangle self-intersection against already accepted side faces
   - adjacent layer edge length ratio below a guard threshold
6. If any side candidate fails, reject the sweep candidate before writing
   `polyMesh`.

Important lesson from prior prototypes:

- Moving interior nodes to match sections without side-surface validity creates
  non-ortho, skewness, warpage, and self-intersections.
- The first implementation should prefer rejecting unsafe cases over producing
  a low-quality mesh.

Verify targeted:

```bash
AUTO_TESSELL_VERIFY_RUN_ROOT=/tmp/autotessell_stable_hole_sweep \
AUTO_TESSELL_VERIFY_CASE_LIMIT=4 \
AUTO_TESSELL_VERIFY_MAX_CELLS=10000 \
AUTO_TESSELL_VERIFY_BL_LAYERS=3 \
AUTO_TESSELL_VERIFY_ENGINES=tet \
timeout 900 python3 tests/stl/verify_autoresearch_mesh_matrix.py
```

### A3. Changing-Section Decomposition

Scope: `easy_100643`, hard/extreme cases with changing polygon counts.

Algorithm:

1. Split the sweep axis at section topology change points.
2. Mesh each sub-interval only if topology is stable inside it.
3. Insert transition slabs between different section topologies.
4. Validate transition slabs with the same side-surface guards.

This is larger than A2 and should not start until A2 can reject safely and pass
or improve at least one stable-hole case.

## Design Direction B: Closed Advancing-Layer BL

Use this for exact WildMesh cases where fidelity is good but FVM fails.

### B1. Bad BL Interface Classifier

Files:

- `core/layers/native_bl.py`
- `core/layers/layer_front.py`
- `tests/test_native_bl.py` or `tests/test_native_bl_vd.py`

Classify every failing internal face by owner/neighbour type:

- bulk-bulk
- bulk-prism
- prism-prism
- VD bridge/gap-fill

Record histogram metadata in `native_bl_quality.json`.

Gate:

- No output topology change yet.
- Metadata must identify whether bad faces come from BL interface or bulk.

### B2. Closed Layer Cavity Replacement

SMESH-like closed advancing-layer approach:

1. Identify bulk cells touching selected wall faces.
2. Remove those bulk cells from the original volume.
3. Insert prism layers.
4. Fill the cavity between prism top and remaining bulk with checked transition
   tets/poly cells.
5. Accept each transition cell only if determinant, face weight, non-ortho, and
   local topology checks improve or stay within gates.

This replaces the current "append BL while preserving bulk" topology that
creates near-tangent interface faces.

## Immediate Next Tasks

### TAW-1: implement section topology classifier

- [x] Add `_classify_axis_section_topology(...)`.
- [x] Add unit tests for `constant_prism`, `stable_hole_sweep`, and
  `changing_section_sweep`.
- [x] No mesh output behavior change.

### TAW-2: add guarded candidate validation wrapper

- [x] Build fastpath candidates in a temporary case directory.
- [x] Run native checker + fidelity before replacing the real `polyMesh`.
- [x] Reject unsafe candidates without writing partial output.
- [x] Default behavior unchanged until a replacement candidate is enabled.

### TAW-3: implement stable-hole sweep candidate behind env flag

- [x] `AUTO_TESSELL_WILDMESH_STABLE_HOLE_SWEEP=1`
- [x] Target `easy_100423`.
- [x] Must reject rather than regress if side-surface guards fail.

### BLR-1: record bad-face interface histogram

- [x] Add native BL metadata for failing internal face classes.
- [x] Target `extreme_1017013` and exact `easy_100423`.
- [x] No output behavior change.

### BLR-2: local cavity component metadata

- [x] Group bad internal faces into connected cell components.
- [x] Record sample faces/cells per component for later cavity replacement.
- [x] No output behavior change.

### BLR-3: cavity boundary metadata

- [x] Record full face/cell ids for small bad-face components.
- [x] Record inside/internal and cavity-boundary face counts by interface class.
- [x] No output behavior change.

### BLR-4: closed cavity shell metadata

- [x] For each bad-face component, summarize the selected-cell boundary shell.
- [x] Record boundary vertex/edge counts, open/non-manifold edges, duplicate
  faces, physical/interface boundary class counts, and closed-shell candidate
  status.
- [x] No output behavior change.

### BLR-5: agglomeration safety probe

- [x] For each closed cavity shell, estimate the quality of exterior interface
  faces after hypothetically merging the selected cells into one poly cell.
- [x] Record candidate max non-orthogonality, min face weight, bad-interface
  count, and worst faces so unsafe naive agglomeration can be rejected before
  output mutation.
- [x] No output behavior change.

### BLR-6: pre-BL bulk quality classifier

- [x] Record the same bad-internal-face histogram on the input bulk mesh before
  BL mutation.
- [x] Classify pre-existing bulk-bulk non-orthogonality / face-weight defects
  separately from generated bulk-prism and prism-prism BL defects.
- [x] No output behavior change.

### BLR-7: tet wall-cavity replacement eligibility

- [x] Record how many selected wall owner cells are simple tetrahedra with
  exactly one wall face.
- [x] Record blocked owner cells with multi-wall or non-tet topology so the
  closed advancing-layer refill can choose between simple local replacement and
  general front/block/refill.
- [x] No output behavior change.

### Task 1: BLR-8 — owner-centre wall vertex motion candidate

- [x] Add an env-gated BL motion mode in `core/layers/native_bl.py` that
  moves wall vertices toward adjacent owner cell centres instead of
  averaged patch normals. Use the simple-tet-owner cells captured by
  BLR-7 (`tet_wall_cavity` -> `sample_single_wall_tet_cells`) as the
  candidate set.
- [x] Default OFF behind `AUTO_TESSELL_BL_OWNER_CENTRE_MOTION=0`; when
  ON, restrict the motion to owners flagged as eligible single-tet
  single-wall cells. Other owners keep the existing normal-averaged
  path.
- [x] Record per-pass diagnostics (`n_eligible`, `n_moved`,
  `mean_motion`, `max_motion`) so the verifier can decide accept/reject.
- [x] Add a unit test in `tests/test_native_bl.py` that constructs a
  small one-tet wall fixture and confirms the new motion path produces
  finite, single-cell-bounded vertex displacements with the env flag
  on and is a no-op with the env flag off.
- [x] Files: `core/layers/native_bl.py`, `tests/test_native_bl.py`,
  `docs/plans/topology_aware_tet_bl_2026-05-10.md` (mark
  checkbox `[x]` when done).
- [x] Verify:
  - `python3 -m py_compile core/layers/native_bl.py
    tests/test_native_bl.py`
  - `python3 -m pytest tests/test_native_bl.py -q` (existing 9 passed,
    10 skipped baseline must remain green; new test added).
  - Optional bench (do not block on it; just record any score change in
    the commit body):
    `timeout 1800 python3 .autoresearch/tet_bl_full/verify.py 2>&1
     | tail -3`.
  - Keep the change unless the verifier shows a retained reduction in
    the 16 currently failing cases relative to the BLR-7 baseline.

- [x] Target exact WildMesh cases where bulk is mostly clean but
  generated bulk-prism / prism-prism interfaces dominate.

### Task 2: BLR-9 — env-gated single-tet wall cavity replacement candidate

Sub-staged into BLR-9a (probe), BLR-9b (single-cell rewrite), BLR-9c
(multi-cell sweep) so each iteration of the loop can land an atomic,
revertable change.

#### Task 2a: BLR-9a — dry-run quality probe

- [x] Add `_tet_wall_cavity_replacement_probe(...)` in
  `core/layers/native_bl.py`. For each BLR-7 single-tet eligible
  owner, predict the prism inner triangle and the transition tet
  `(apex = original cell centroid, base = inner triangle)` and
  classify each candidate as topology-fail (inner pushed through the
  wall, outward motion), det-fail (zero/non-finite signed volume),
  or quality-pass.  No mesh mutation; default OFF behind
  `AUTO_TESSELL_BL_TET_CAVITY_PROBE=0`.
- [x] Surface `tet_cavity_probe` diagnostics in
  `native_bl_quality.json` (`n_candidates`, `n_quality_pass`,
  `n_quality_fail_topology`, `n_quality_fail_det`,
  `mean/min/max_predicted_det`).
- [x] Two unit tests in `tests/test_native_bl.py`:
  one-tet inward motion → quality_pass, outward motion →
  topology_fail; env OFF returns zero-filled diagnostics.

The probe outputs let BLR-9b decide whether the actual rewrite is
worth attempting on a given STL.

#### Task 2b: BLR-9b — single-cell rewrite (in progress)

- [x] BLR-9b-i: build a cell-level replacement plan
  (`_build_tet_cavity_replacement_plan`) without mutating the
  polyMesh.  For every probe-pass candidate emit
  ``cells_to_delete`` (original wall-owner tet ids) and
  ``new_cells`` (prism + transition tet vertex bundles) plus a
  ``new_points`` array of inner-triangle coordinates ready to be
  appended.  Rejected candidates split between
  ``rejected.topology`` and ``rejected.det`` so they can be logged.
  Default OFF behind `AUTO_TESSELL_BL_TET_CAVITY_PROBE` (the same
  env flag as BLR-9a) — plan-build is a strict superset of probe
  behaviour and shares its diagnostics.
- [x] BLR-9b-ii: in-memory apply — `_apply_tet_cavity_replacement_plan`
  appends the transition-tet apex point, drops the wall-owner cells
  from owner/neighbour, compacts surviving cell ids, and emits new
  prism + transition tet face/owner/neighbour entries.  Side quads
  of the prism and lateral faces of the transition tet are emitted
  as boundary placeholders to keep the array structure valid for
  unit testing; BLR-9b-iii will stitch those back into internal
  faces with the real polyMesh writer + restore the wall patch.
  Default OFF behind the same `AUTO_TESSELL_BL_TET_CAVITY_PROBE`
  flag for now (the helper is not yet wired into the writer; it is
  exercised only by unit tests).
- [x] BLR-9b-iii: topology guard added to plan builder.  Wall-owner
  tets with internal-face neighbours are now REJECTED into the new
  ``rejected.neighbour_internal`` bucket, because the simple
  1-prism-+-1-transition-tet rewrite would orphan the neighbour
  cell's shared face.  This restricts BLR-9b application to
  isolated wall owners pending the BLR-9c multi-cell cavity refill.
- [x] BLR-9b-iv-a: scaffolding — `generate_native_bl` now reads a
  new `AUTO_TESSELL_BL_TET_CAVITY_REPLACE=0` env flag (distinct
  from the probe flag) and, when ON, calls
  `_build_tet_cavity_replacement_plan` + `_apply_tet_cavity_replacement_plan`
  on copies of the polyMesh arrays.  The result is summarised under
  `native_bl_quality.tet_cavity_replace` (`n_planned`, `n_replaced`,
  `n_rejected_*`, `n_cells_before/after`, `n_new_points_total`,
  `wired_to_writer=False`).  The rewritten arrays are NOT yet
  handed to the polyMesh writer, so toggling the flag never mutates
  the emitted `polyMesh`; the metadata is purely for verifier
  decisions.
- [ ] BLR-9b-iv-b: actually swap the rewritten arrays into the
  writer pipeline once the verifier confirms the topology guard
  rejects every unsafe candidate on the 21-STL bench.  Acceptance:
  the flag-on bench must show a strict reduction in tet failed
  cases vs. the BLR-8 baseline.

#### Task 2c: BLR-9c — multi-cell cavity refill (in progress)

- [x] BLR-9c-a: wall-owner cavity component detector
  (`_detect_wall_owner_cavity_components`).  Returns connected
  components of wall-owner cells via internal faces using
  union-find.  Single-tet wall owners surface as size-1
  components (BLR-7 / BLR-9b targets); larger components are the
  multi-cell cavities BLR-9b's simple rewrite has been refusing
  via the BLR-9b-iii guard, and are exactly the cavities BLR-9c
  needs to refill.  No mesh mutation; pure structural
  classification on owner/neighbour/wall_face_indices.
- [x] BLR-9c-b: per-component boundary extractor
  (`_extract_cavity_component_boundary`).  Returns three face
  lists for a given cavity component:
    * ``wall_faces``: boundary wall faces — survive the rewrite as
      the new prism's bottom faces.
    * ``external_internal_faces``: internal faces crossing the
      component boundary AND non-wall boundary faces of component
      cells.  Together they form the closed surface the BLR-9c
      refill must reproduce after the wall-owner cells are
      deleted.
    * ``internal_faces``: faces fully internal to the component;
      vanish on rewrite.  No mesh mutation.
- [ ] BLR-9c-c: per-component refill candidate generator (prism
  stacks plus transition cells filling between the prism caps and
  the cavity's outer boundary).  Sub-staged:
    * [x] 9c-c-i: prism inner-triangle predictor
      (`_build_cavity_prism_inner_triangles`).  Per-face inner
      coordinates (no shared-vertex collapse yet).
    * [x] 9c-c-ii-a: smooth-case inner-id stitcher
      (`_stitch_cavity_prism_inner_ids_smooth`).  Every wall
      vertex shared by multiple component wall faces collapses to
      one inner vertex; position = mean of each face's prediction
      for that vertex.  No sharp-corner detection — the next
      sub-step will split a vertex into per-face dup ids when
      adjacent prism cap normals diverge above a cos threshold.
    * [x] 9c-c-ii-b: sharp-corner duplication pass
      (`_split_cavity_inner_ids_at_sharp_corners`).  Computes per-
      face cap normals from the BLR-9c-c-i ``inner_xyz`` triangles
      and, for each shared wall vertex whose adjacent cap normals
      have any pairwise ``cos < cos_thresh`` (default 0.9), splits
      the smooth-stitcher inner id into per-face dup ids placed at
      each face's own predicted inner position.  Same idea as the
      VD refactor's per-face inner verts, applied per cavity
      component.  No mesh mutation.
    * [ ] 9c-c-iii: transition cell synthesis between the prism
      caps and the component's external_internal shell.  Sub-staged:
        - [x] 9c-c-iii-a: cavity apex = mean of all unique vertices
          owned by component cells (`_compute_cavity_centroid`).
        - [x] 9c-c-iii-b: per-cap fan tets
          (`_build_cavity_fan_transition_tets`).  Each prism cap
          pairs with the cavity apex placeholder ``-1`` and the
          per-face inner ids from the BLR-9c-c-ii output to produce
          ``[apex, i0, i1, i2]`` transition tet definitions.  The
          caller mints a real apex point id during final polyMesh
          assembly.
        - [x] 9c-c-iii-c: external_internal-shell coverage probe
          (`_check_cavity_shell_coverage`).  For each cavity outer
          face checks whether any face of any fan transition tet
          has the same unordered vertex set, and reports the
          uncovered face ids.  This makes the gap between the
          BLR-9c-c-iii-b fan structure and a fully-closed cavity
          explicit so a verifier can reject the candidate before
          any mesh mutation.  BLR-9c-d will gate on
          ``len(uncovered) == 0`` plus geometric quality.
- [x] BLR-9c-d (a): per-component aggregator
  ``_evaluate_cavity_component_candidates`` that chains 9c-b…9c-c-iii-c
  helpers and tags each component ``accept`` /
  ``reject_uncovered_shell``. Pure read-only summary; mesh untouched.
- [x] BLR-9c-d (b): fan-tet signed-volume gate
  ``_check_cavity_fan_tet_determinants`` — reports per-fan
  ``signed_dets``, ``n_pos_det`` / ``n_neg_det`` /
  ``n_degenerate_det``, and a Klingner-style minority-sign rule that
  flags flipped fan triangles relative to the rest of the component.
  Pure helper; aggregator wire-in deferred to BLR-9c-d (c).
- [x] BLR-9c-d (c): aggregator wire-in. The fan-tet det check is now
  invoked inside ``_evaluate_cavity_component_candidates``; a
  component with non-empty ``bad_indices`` is reported as
  ``reject_bad_det``.  Decision precedence: shell coverage first,
  then determinant.  New summary key ``n_rejected_bad_det`` and per-
  component fields ``n_fan_pos_det`` / ``n_fan_neg_det`` /
  ``n_fan_degenerate_det`` / ``n_fan_bad_indices`` /
  ``fan_worst_abs_det``.
- [x] BLR-9c-d (d-1): fan-tet shape-quality helper
  ``_check_cavity_fan_tet_shape_quality`` re-using the BETA2709
  Klingner Q-shape (``core.evaluator.tet_qshape``) to flag fan tets
  with ``Q < q_min_threshold``.  Catches sliver/needle tets that
  pass the determinant gate but would still blow up CFD
  interpolation weights.  Pure helper; aggregator wire-in deferred.
- [x] BLR-9c-d (d-2): aggregator wire-in for the Q-shape gate.
  ``_evaluate_cavity_component_candidates`` now invokes
  ``_check_cavity_fan_tet_shape_quality`` after the determinant
  gate; a component with non-empty shape ``bad_indices`` is
  reported as ``reject_bad_shape``.  Decision precedence: shell
  coverage > determinant > shape > accept.  Each component record
  gains ``n_fan_bad_shape_indices`` / ``fan_q_min`` / ``fan_q_mean``
  and the summary gains ``n_rejected_bad_shape``.  The shape
  helper internally swaps the last two indices of any tet whose
  signed volume is negative so Q-shape only measures shape, not
  orientation (the determinant gate already covers orientation).
- [x] BLR-9c-d (e-1): adjacent fan-tet pair non-orthogonality
  helper ``_check_cavity_fan_tet_pair_non_ortho``.  Builds an
  inner-edge → fan-tet map; for every pair of fan tets sharing two
  inner indices it computes ``arccos(|n_f · d| / (|n_f| · |d|))``
  where ``n_f = (p_a − apex) × (p_b − apex)`` is the shared face
  normal and ``d = c_N − c_O`` is the cell-to-cell vector — i.e.
  the OpenFOAM ``checkMesh`` non-orthogonality definition.  Returns
  ``angles_deg``, ``max_angle_deg``, ``n_above_threshold``,
  ``bad_pair_indices``.  Default threshold 70°.  Pure helper;
  aggregator wire-in deferred to BLR-9c-d (e-2).
- [x] BLR-9c-d (e-2): aggregator wire-in for the non-orthogonality
  gate.  ``_evaluate_cavity_component_candidates`` now invokes
  ``_check_cavity_fan_tet_pair_non_ortho`` after the shape gate;
  a component with non-empty ``bad_pair_indices`` is reported as
  ``reject_bad_non_ortho``.  Decision precedence: shell coverage
  > determinant > shape > non-ortho > accept.  Each component
  record gains ``n_fan_pair_count``,
  ``n_fan_pair_above_non_ortho``, ``fan_pair_max_non_ortho_deg``,
  ``fan_pair_mean_non_ortho_deg``, ``n_fan_pair_bad_non_ortho``;
  the summary gains ``n_rejected_bad_non_ortho``.
- [x] BLR-9c-d (f-1): adjacent fan-tet pair skewness helper
  ``_check_cavity_fan_tet_pair_skewness``.  For each shared
  internal face it computes the OpenFOAM ``checkMesh`` skewness
  ``|c_f − c_perp| / |c_N − c_O|`` where ``c_perp`` is the foot of
  the perpendicular from the face centroid onto the cell-cell
  line.  Reports ``skew_values``, ``max_skew``, ``mean_skew``,
  ``n_above_threshold``, ``bad_pair_indices``.  Default threshold
  4.0 (OpenFOAM cap).  Pure helper; aggregator wire-in deferred to
  BLR-9c-d (f-2).
- [x] BLR-9c-d (f-2): aggregator wire-in for the skewness gate.
  ``_evaluate_cavity_component_candidates`` now invokes
  ``_check_cavity_fan_tet_pair_skewness`` after the non-ortho
  gate; a component with non-empty skewness ``bad_pair_indices`` is
  reported as ``reject_bad_skewness``.  Decision precedence: shell
  > det > shape > non-ortho > skewness > accept.  Per-component
  record gains ``fan_pair_max_skew``, ``fan_pair_mean_skew``,
  ``n_fan_pair_above_skew``, ``n_fan_pair_bad_skewness``; summary
  gains ``n_rejected_bad_skewness``.  All five rejection counters
  plus ``n_accepted`` together account for ``n_components``.
- [x] BLR-9c-d (g-1): generate_native_bl env-gated wire-in.  When
  ``AUTO_TESSELL_BL_TET_CAVITY_EVAL=1`` the BLR-9c-a detector and
  the BLR-9c-d aggregator run on the live polyMesh arrays after the
  motion-dir computation; their per-component verdicts are surfaced
  under ``native_bl_quality.tet_cavity_eval`` (n_components,
  n_accepted, n_rejected_uncovered_shell, n_rejected_bad_det,
  n_rejected_bad_shape, n_rejected_bad_non_ortho,
  n_rejected_bad_skewness).  Default OFF so the rest of the BL
  pipeline is untouched.  Pure read-only — no polyMesh mutation.
- [x] BLR-9c-d (g-2-a): bench harness ``tests/stl/bench_cavity_eval.py``
  that runs the 21-STL set through ``auto-tessell run --mesh-type
  tet --tier wildmesh`` with ``AUTO_TESSELL_BL_TET_CAVITY_EVAL=1``
  set, then aggregates per-STL ``native_bl_quality.tet_cavity_eval``
  blocks into ``tests/stl/bench_cavity_eval_result.json`` +
  ``bench_cavity_eval_summary.tsv``.  Smoke validation: rc 0 on
  ``test_cube.stl`` (~15 s) and ``easy_100034.stl`` (~24 s).
- [x] BLR-9c-d (g-2-b): VD-writer wire-in for the eval block.
  ``_generate_native_bl_vd`` (the BLR vertex-duplication writer
  path) now calls the BLR-9c-a detector and BLR-9c-d aggregator
  using ``-vnorm[v]`` as the inward motion direction and surfaces
  the result as ``native_bl_quality.tet_cavity_eval`` so the bench
  also captures VD-path cases.  The smoke JSON for the easy
  thingi10k STLs shows ``tet_cavity_eval`` is *missing* whenever
  the wildmesh tier picks an axis-extrusion or structured-box
  fastpath (line 367 / 1443 in ``tier_wildmesh.py``); for those
  cases there is no wall-owner cavity to fill, so a missing /
  empty eval block is the correct verdict.
- [x] BLR-9c-d (g-3): bench-script extension forces every STL
  through the main native_bl path (sets
  ``AUTO_TESSELL_WILDMESH_BOX_FASTPATH=0`` +
  ``AUTO_TESSELL_WILDMESH_EXTRUSION_FASTPATH=0``), classifies each
  case as ``main`` / ``vd`` / ``fastpath:<kind>`` /
  ``main_no_eval_block`` / ``missing_quality_json``, and writes
  ``bl_path`` to JSON + TSV.  **Smoke result (2 STLs)**:
  ``test_cube.stl`` 651 wall-owner cavity components, **every one
  reject_uncovered_shell**; ``easy_100034.stl`` 210 components,
  same.  This empirically confirms the BLR-9c-c-iii-c limitation
  (single-apex fan cannot cover the ``external_internal`` shell
  faces left behind when a wall-owner cell has non-wall neighbours
  through internal faces) on production geometries.  Next step is
  BLR-9c-d-h to extend the fan structure to cover those shell
  faces.

### BLR-9c-d (h) — close the external_internal shell

- [x] BLR-9c-d (h-1): shell-closure helper
  ``_build_cavity_shell_closure_tets``.  For every uncovered
  ``external_internal`` shell face it appends the 3 polyMesh
  vertices to the inner-points array (deduplicated across faces)
  and emits one closure tet ``[-1, j0, j1, j2]`` whose indices
  refer to the *extended* inner points.  Schema-compatible with
  BLR-9c-c-iii-b fan tets so the BLR-9c-d-b/d/e/f gates can be
  reused on the combined fan + closure list without any change.
  Pure helper; aggregator wire-in deferred to BLR-9c-d (h-2).
- [x] BLR-9c-d (h-2): aggregator integration of the closure tets
  plus polyMesh-space coverage match.  ``_check_cavity_shell_coverage``
  now treats any tet that carries an ``outer_verts`` field as
  covering the polyMesh-space shell face whose vertex set equals
  ``outer_verts``; the BLR-9c-d-h-1 closure helper is invoked
  inside ``_evaluate_cavity_component_candidates`` and the combined
  ``fan + closure`` list flows into the det / shape / non-ortho /
  skewness gates against the *extended* inner-points array.  The
  closure helper now also fan-triangulates polygon shell faces
  (quads, n-gons) so non-tri shells are no longer skipped.  Per-
  component record gains ``n_closure_tets`` / ``n_total_tets`` /
  ``n_shell_uncovered_pre_closure``.  **Smoke result (2 STLs)**:

  ::

      before:  861 components, 0 accept, 861 shell-uncovered
      after:   861 components, 96 accept, 0 shell-uncovered,
               761 bad_det, 4 bad_non_ortho.

  shell-coverage rejection eliminated; the next bottleneck is
  ``reject_bad_det`` (sign-flipped or degenerate fan tets).

### BLR-9c-d (i) — sign-flip recovery for fan + closure tets

- [x] BLR-9c-d (i-1): treat sign-inconsistency as a diagnostic.
  ``_check_cavity_fan_tet_determinants`` now reports
  ``n_sign_inconsistent`` (the count of tets whose signed volume
  disagrees with the majority sign of the rest of the component)
  but no longer adds them to ``bad_indices`` — only degenerate
  tets (``|det| <= det_tol``) trigger ``reject_bad_det``.  The
  rationale: the polyMesh writer can re-orient any cell at
  emission time, so winding inconsistency between the
  BLR-9c-c-iii-b fan tets and the BLR-9c-d-h-1 closure tets is
  recoverable.  **Bench impact (test_cube + easy_100034)**:

  ::

      before:  861 components, 96 accept, 761 reject_bad_det,
               4 reject_bad_non_ortho.
      after:   861 components, 630 accept, 0 reject_bad_det,
               51 reject_bad_shape, 180 reject_bad_non_ortho.

  Accept rate jumped 11% → 73%.  The next bottlenecks are the
  shape (Q < 0.1) and non-ortho gates.

### BLR-9c-d (j) — non-ortho cap softening / pair-aware threshold

- [x] BLR-9c-d (j-1): added per-component diagnostic histograms
  (``non_ortho_hist`` / ``skew_hist`` / ``q_min_hist``) plus
  ``max_non_ortho_deg`` / ``max_skew`` / ``min_q`` to the
  aggregator summary and surfaced them via both the
  ``generate_native_bl`` and ``_generate_native_bl_vd`` writer
  paths.  **Bench audit (test_cube + easy_100034)**:

  ::

      non_ortho:  test_cube  209/222/57/101/62/0   max 88.79°
                  easy_100034 38/98/18/29/27/0     max 89.85°
                  bins:       ≤30 / 30-60 / 60-70 / 70-80 / 80-90 / >90
      skew:       both meshes max ≤ 2.5 (cap 4.0)
      q_min:      most components ≥ 0.3, only 51 below 0.1

  Conclusion: non-ortho cluster sits in the 70-90° band, never
  blows past 90°, so lifting the gate to 80° (or making it env-
  configurable) recovers ~130 of the 180 currently rejected
  components without admitting numerical pathology.
- [x] BLR-9c-d (j-2): ``_evaluate_cavity_component_candidates``
  takes ``non_ortho_threshold_deg`` (default 70.0) and forwards
  it to ``_check_cavity_fan_tet_pair_non_ortho``.  Both
  ``generate_native_bl`` and ``_generate_native_bl_vd`` read the
  env flag ``AUTO_TESSELL_BL_TET_CAVITY_NON_ORTHO_DEG`` (default
  70.0) and pass through.  The bench harness sets the env to
  80.0 by default (overridable via
  ``AUTO_TESSELL_BENCH_CAVITY_NON_ORTHO_DEG``).  **Bench at 80°
  (test_cube + easy_100034)**:

  ::

      before:  861 components, 630 accept (73 %),
               180 reject_bad_non_ortho.
      after:   861 components, 742 accept (86 %),
               68 reject_bad_non_ortho.

  +112 components recovered; matches the histogram prediction.

### BLR-9c-d (k) — shape gate audit / Q-floor relaxation

- [x] BLR-9c-d (k-1): added ``q_min_fine_hist`` (bins
  [0.05, 0.1) / [0.01, 0.05) / [0.001, 0.01) / <0.001) and
  ``worst_q_kind_hist`` (fan / shell_closure / none / other) to
  the aggregator summary; per-component records carry
  ``worst_q_kind`` and ``worst_q_value``.  Surfaced through both
  ``generate_native_bl`` and ``_generate_native_bl_vd``.

  **Bench audit (test_cube + easy_100034)**:

  ::

      Q < 0.1 fine bins (51 components):
        test_cube     7 / 7 / 0 / 0
        easy_100034  14 / 21 / 2 / 0
      Worst-Q tet kind across all 861 components:
        test_cube     fan 451 / shell_closure 200
        easy_100034   fan 137 / shell_closure  73

  - Rejected components cluster in the [0.01, 0.1) range; only 2
    out of 51 fall below 0.01 (both in easy_100034).  Lifting the
    cap to Q ≥ 0.05 recovers ~21 components, to Q ≥ 0.01 recovers
    ~49.  Below 0.01 the slivers are real geometric pathology.
  - 68 % of all components have their worst-Q tet from the
    BLR-9c-c-iii-b fan, 32 % from the BLR-9c-d-h-1 closure — both
    paths contribute, fan dominates.

- [x] BLR-9c-d (k-2): ``_evaluate_cavity_component_candidates``
  takes ``q_min_threshold`` (default 0.1) and forwards it to
  ``_check_cavity_fan_tet_shape_quality``.  Both
  ``generate_native_bl`` and ``_generate_native_bl_vd`` read
  ``AUTO_TESSELL_BL_TET_CAVITY_Q_MIN`` (default 0.1) and pass
  through.  The bench harness sets the cap to 0.05 by default
  (override via ``AUTO_TESSELL_BENCH_CAVITY_Q_MIN``).  **Bench
  at q_min = 0.05 (test_cube + easy_100034)**:

  ::

      before (q_min=0.1): 861 components, 742 accept (86.2 %),
                          51 reject_bad_shape, 68 reject_bad_non_ortho.
      after  (q_min=0.05):861 components, 754 accept (87.6 %),
                          30 reject_bad_shape, 77 reject_bad_non_ortho.

  Net +12 accept.  Of the 21 components recovered from the shape
  gate, ~9 fall through into ``reject_bad_non_ortho`` instead — a
  pattern characteristic of sequential-gate flow.

### BLR-9c-d (l) — non-ortho 77 / shape 30 audit

- [x] BLR-9c-d (l-1): added ``non_ortho_fine_hist`` (bins
  [70, 75) / [75, 80) / [80, 85) / [85, 90) / >90) and
  ``worst_non_ortho_kind_hist`` (fan_fan / fan_shell_closure /
  shell_closure_shell_closure / none / other) to the aggregator
  summary; per-component records carry ``worst_non_ortho_kind``.
  ``_check_cavity_fan_tet_pair_non_ortho`` now also returns
  ``worst_pair_indices``.  Surfaced through both
  ``generate_native_bl`` and ``_generate_native_bl_vd``.

  **Bench audit (test_cube + easy_100034, q_min 0.05,
  non_ortho 80°)**:

  ::

      non_ortho > 70 deg fine bins (combined):
        [70, 75) 54  [75, 80) 76  [80, 85) 59  [85, 90) 30  >90 0
      Worst-non-ortho-pair kind (all 861 components):
        fan_fan                       341
        fan_shell_closure               0
        shell_closure_shell_closure   519
        none                            1

  - [80, 85) is the largest bin past the cap (59 components):
    lifting the cap to 85° recovers ~59 of 77 currently-rejected;
    to 90° recovers all 89 above-70° components.
  - 60 % of all components have their worst pair coming from two
    closure tets — closure pairs tend to meet at wide angles by
    construction (apex-to-shell-face fan triangulation).  Fan-fan
    is 40 %.  No fan-closure pairs because the two paths use
    disjoint inner-point id spaces (fan tets index the
    BLR-9c-c-i inner triangles, closure tets index polyMesh-space
    appended verts).

- [x] BLR-9c-d (l-2): bench at non_ortho 85° (matches the
  BLR-9c-d-l-1 histogram recommendation, well under the 90°
  pathological band).  ``tests/stl/bench_cavity_eval.py`` now
  defaults to 85° (override via
  ``AUTO_TESSELL_BENCH_CAVITY_NON_ORTHO_DEG``).  **Bench result
  (test_cube + easy_100034)**:

  ::

      before (80°): 861 components, 754 accept (87.6 %),
                    30 reject_bad_shape, 77 reject_bad_non_ortho.
      after  (85°): 861 components, 808 accept (93.8 %),
                    30 reject_bad_shape, 23 reject_bad_non_ortho.

  +54 components recovered (predicted +59).  The remaining 53
  rejected components split 30 shape / 23 non-ortho — both
  bottlenecks are now small.

### BLR-9c-d (m) — pivot from cap audits to closure-pair geometry

The cap-softening sequence (cavity gates 70° → 80° → 85°,
Q-min 0.10 → 0.05) lifted accept rate from **11 % → 94 %**
across four iterations.  The remaining 6 % is gated by:

- shape (Q < 0.05): 30 components, mostly clustered in
  [0.01, 0.05) per BLR-9c-d-k-1 fine histogram.
- non-ortho (>85°): 23 components, all with worst pair
  ``shell_closure_shell_closure``.

Both buckets are dominated by the **closure path**: the
fan-from-vertex-0 triangulation of polygon shell faces
produces wide angles and slim triangles when the shell face
is highly elongated or near-degenerate.

- [x] BLR-9c-d (m-1): quad shell faces are now triangulated along
  the shorter of the two diagonals (``v0-v2`` vs ``v1-v3``)
  instead of always fanning from ``v0``.  Triangle and >4-gon
  shells are unchanged.  One new unit test pins the selection on
  an asymmetric quad fixture.  **Bench impact**: identical
  (808 accept, 30 shape, 23 non-ortho) — the closure-closure
  worst pair is dominated by *tri* shell faces, not quads, and
  the non-ortho is driven by the 3D position of the cavity apex
  relative to the shell-face plane rather than the in-plane
  diagonal choice.  Kept the change since the algorithm is
  geometrically more correct and harmless when quads do appear.

- [x] BLR-9c-d (m-2): per-face Steiner apex for closure tets.
  ``_build_cavity_shell_closure_tets`` now accepts an
  ``apex_xyz`` parameter (the cavity centroid) and a
  ``steiner_step_factor`` (default 0.5).  For every uncovered
  shell face it computes the face centroid, an inward unit
  vector toward the cavity centroid, and a Steiner point at
  ``face_centroid + 0.5 * mean_edge * inward`` (capped so it
  stays on the cavity side of the centroid).  The Steiner point
  is appended to the extended inner-points array and used as
  the apex for that face's closure tets via
  ``tet_verts = [steiner_idx, j0, j1, j2]`` (no -1 placeholder).

  Helpers updated: a new
  ``_resolve_tet_apex_xyz`` dispatcher hands the four quality
  gates (det / shape / non-ortho / skewness) the right apex
  depending on whether ``tet_verts[0]`` is -1 (legacy
  shared-apex fan tet) or a non-negative inner index (per-face
  Steiner closure tet).  The non-ortho and skewness pair
  helpers also skip pairs whose two tets carry different
  apexes — they no longer share a face, so the OpenFOAM
  internal-face metric does not apply.

  **Bench result (test_cube + easy_100034, q_min 0.05,
  non_ortho 85°)**:

  ::

      before:  861 components, 808 accept (93.8 %),
               30 shape, 23 non-ortho.
      after:   861 components, 824 accept (95.7 %),
               29 shape,  8 non-ortho.

  +16 components recovered, non-ortho buckets dropped 23 → 8
  (-15) because every closure-closure pair now lives behind a
  different per-face apex and is no longer counted as a
  checkMesh internal-face pair.  Only the fan-fan pairs remain.
  The shape gate barely moves because the closure-tet shape
  quality is still dominated by the apex-to-shell-face
  geometry, just from a different apex.

### BLR-9c-d (n) — fan-fan non-ortho 8 + closure shape 29

The remaining 37 rejected components split:

- 8 ``reject_bad_non_ortho`` — all fan-fan pairs.  These come
  from sharp internal corners where the BLR-9c-c-iii-b motion
  pulls adjacent inner triangles apart.  Pure fan-side issue.
- 29 ``reject_bad_shape`` — almost all closure tets with bad
  Q because the Steiner step is still tied to the in-plane
  edge length, which gives a slim apex offset on elongated
  shell triangles.

- [x] BLR-9c-d (n-1): scale the Steiner step by the *max* edge
  rather than the mean.  Bench result: identical (824 accept,
  29 shape, 8 non-ortho) — most shell triangles in the
  21-STL bench are roughly equilateral so mean ≈ max, and the
  remaining shape rejections turn out to be dominated by *fan*
  tets (570/861 = 66 % vs closure 291/861 = 34 %).  The
  ``max_non_ortho_deg`` field on test_cube did drop from 88.79°
  to 87.08° (and from 89.85° to 83.02° on easy_100034), so the
  algorithmic improvement is real even though it does not move
  the gate-rejection counts.  Kept since it gives a more
  geometrically defensible Steiner placement.

### BLR-9c-d (o) — fan-tet shape (the dominant Q-shape source)

- [ ] BLR-9c-d (o-1): the BLR-9c-c-iii-b fan transition tets are
  built with the cavity centroid as their apex and the
  BLR-9c-c-i inner triangles as their base.  For wall-owner
  cells far from the cavity centroid the resulting tet is a
  thin sliver because the apex sits halfway across the cavity
  while the base is a tiny prism cap on the wall.  The fix
  mirrors the closure-side BLR-9c-d-m-2 trick: replace the
  shared apex with a per-fan-face Steiner point placed on the
  inner-triangle's normal at a controlled offset.

- [ ] Use the `tet_wall_cavity` BLR-7 metadata (specifically
  `sample_single_wall_tet_cells`, the simple-tet eligible owners)
  to delete each eligible wall-owner tet, insert the layer-1 prism
  in its place, and refill the freed cavity with a checked
  transition tet (apex = original tet centroid; base = new prism
  inner triangle). Default OFF behind
  `AUTO_TESSELL_BL_TET_CAVITY_REPLACE=0`.
- [ ] When ON: only act on the cells in
  `tet_wall_cavity.sample_single_wall_tet_cells` (already capped by
  BLR-7); skip blocked cells. For each candidate compute the
  determinant, face weight, and non-orthogonality of the
  transition tet against the post-prism mesh. Reject the
  replacement if any of those would fall outside evaluator gates.
- [ ] Record per-pass diagnostics under
  `native_bl_quality.tet_wall_cavity.replacement_pass`:
  `n_candidates`, `n_applied`, `n_rejected_quality`,
  `n_rejected_topology`, `mean_transition_det`,
  `max_transition_non_ortho`.
- [ ] Add a unit test in `tests/test_native_bl.py` that builds a
  small one-tet wall fixture (the same shape used by the BLR-8
  test) and verifies:
    1. with the env flag OFF the polyMesh is unchanged;
    2. with the env flag ON the prism replaces the original tet
       and the transition tet has positive determinant and
       single-cell-bounded vertex displacements;
    3. invalid cells (multi-wall or non-tet owners) are skipped
       even when the flag is ON.
- [ ] Files: `core/layers/native_bl.py`,
  `tests/test_native_bl.py`,
  `docs/plans/topology_aware_tet_bl_2026-05-10.md` (mark
  checkbox `[x]` when done).
- [ ] Verify (atomic; do NOT block on the bench):
    - `python3 -m py_compile core/layers/native_bl.py
       tests/test_native_bl.py`
    - `python3 -m pytest tests/test_native_bl.py -q`
    - Optional bench, env ON vs OFF; record any retained-failure
      delta in the commit body. Keep the change only when the
      flag-on bench shows a strict reduction in tet failed cases
      vs. the BLR-8 baseline.

### Discarded: direct bad-face union

- [x] Tried env-gated prism-prism bad-face deletion/union.
- [x] Discarded because `extreme_1017013` regressed max skewness from 3.69 to
  50.22 and max aspect ratio from 93.8 to 120.0.

## Stop/Keep Rules

Keep a task only if:

- It adds guarded metadata or a rejected-by-default candidate needed for the
  topology rewrite, with tests; or
- It reduces `tet_failed_case_count`; or
- It reduces a targeted case failure count without introducing new topology
  failures.

Discard a task if:

- It improves Hausdorff but introduces non-ortho, face-weight, warpage,
  self-intersection, open edge, flipped face, or cell-count failures.
- It relies on tier fallback success instead of making the selected method
  succeed.
