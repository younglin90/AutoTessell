# Native Engine Continuous Release Campaign

## Campaign ledger

- campaign_id: `native-release-20260730`
- state: `CAMPAIGN_ACTIVE`
- cycle: `24`
- policy: `shape-preservation > validity > provenance > boundary layers > cell count > quality > reproducibility > performance`
- last_verified_master: `b99966a87c3014a4353e3133840ba1dc58d4c840`
- allowed_to_stop: `false`
- next_action: `Prevent duplicate native-BL insertion in poly_bl_transition and repair the resulting prism/hybrid face winding so the valid PolyMeshWriter single-tet fixture remains signed-positive after transition; preserve requested layer reporting and wall geometry.`

This ledger records release evidence. `PASS` requires reproducible evidence, not a
focused-test result. `last_verified_master` is the pre-ledger checkpoint; the
ledger commit itself necessarily advances `HEAD`.

## Cycle 1 checkpoint — 2026-07-30

### Repository evidence

- branch: `master`
- worktrees: `1` (primary only)
- working tree: clean
- submodules: no modified submodule reported
- `third_party/`: no modification reported
- archived prior experimental branches: `/home/younglin90/work/claude_code/AutoTessell-archive-20260730/`

### Known retained evidence

- Boundary-layer state tests: `21 passed`; guard tests: `24 passed`.
- Hex source-quad and sparse-chain focused suites: `36 passed`, then `15 passed`.
- Native tri curvature/provenance focused suite: `23 passed`.
- Native quad input manifold preflight: `27 passed` in `12.15 s`; non-manifold,
  duplicate, degenerate, and inconsistent-orientation triangles now return a
  validation error before pairing. Valid fixture coordinates are unchanged.
- Poly target-forward L0 suite: `5 passed` in `12.19 s`; `target_cells` now
  reaches the BL=0 native-poly harness unchanged. Full native-poly suite timed
  out after `124 s`; target monotonicity and corpus tolerance remain unverified.
- Native tet L2 NACA diagnostic (`--native-primal --target-cells 2000`): output
  reported `3` cells without tetrahedron vertex incidence and `13` four-vertex
  cells without complete tetrahedron face encoding. Primary validity defect count: `16`.
- Native tet now fails closed before `polyMesh` creation on a 3+-cell face:
  NACA strict count `13`, cylinder strict count `10`; focused writer/result
  tests `6 passed` in `14.04 s`. This removes false-success output, not the
  upstream manifold-topology limitation.
- Tet Klingner sweep incidence guard: direct focused suite `37 passed` in
  `4.04 s`; a direct NACA rerun reports strict count `10`, `success=False`,
  and no `polyMesh`. The guard rolls back a sweep that increases non-manifold
  face count; remaining pre-sweep topology defects are still open.
- `verify_goal.py` now records selected phase evidence and explicit `NOT_RUN`
  phases. L0: `3 passed` in `1.77 s`; GUI phase passed. After BL0 propagation
  repair, parameter phase with `target_cells=2000`, `boundary_layer=0` passes:
  tier params retain both zero values and strategy reports `num_layers=0`,
  `enabled=False`.
- Hex implicit cube target contract: actual cells `125,216,1000,2197` for
  requests `128,256,1000,2000`; max error `15.63%`, monotone, negative volume
  `0`; focused suite `14 passed` in `37.69 s`. Full solid-volume guard timed
  out at `120 s` and remains unverified.
- Poly target observation reports requested/actual/error explicitly. Real cube
  BL0 probes remain target failures: `50 -> 15`, `100 -> 15`; target rebudget
  is an active functional card.
- Native-tri has an opt-in production route only as an explicit unchanged
  rejection until source certificate exists; three-run cube/sphere route suite
  passed. Existing isotropic default is unchanged.
- Fresh wheel smoke passed: wheel build, external fresh virtualenv install,
  installed CLI help, and copied sphere analysis. SHA256/phase evidence is
  produced by `scripts/verify_package_wheel.py`; native CMake and installers
  remain unverified.
- Same NACA baseline emitted `1827` cells for target `2000`; campaign-wide target
  tolerance is not yet declared or verified.
- Previous full `python tests/verify_goal.py` timed out after `124 s`; no full-suite claim.

### Gate status

| Gate | Status | Evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | Cycle-1 checkpoint clean; re-evaluate every cycle. |
| 2 Build | UNVERIFIED | Python wheel smoke passes; native C++ clean build missing. |
| 3 Automated tests | UNVERIFIED | Phase-attributed verifier added; full engine/routing/UI suite missing. |
| 4 Shape preservation | UNVERIFIED | No campaign corpus result. |
| 5 Mesh validity | FAIL | Tet cube harness strict writer still rejects 2–4 non-manifold faces. |
| 6 Cell count | FAIL | Poly cube target `50/100 -> 15`; tet valid output missing; hex L0 only passes. |
| 7 Boundary layer | UNVERIFIED | Explicit BL0 propagation passes; positive-layer engine corpus missing. |
| 8 Quality | UNVERIFIED | Campaign quality specifications and corpus missing. |
| 9 Reproducibility | UNVERIFIED | Three-run engine corpus missing. |
| 10 Robustness | UNVERIFIED | Quad invalid topology rejects explicitly; tet NACA/cylinder fail explicitly; matrix missing. |
| 11 Performance | UNVERIFIED | Baselines and budgets missing. |
| 12 Packaging | UNVERIFIED | Python wheel clean-install smoke passes; native/installer clean install missing. |
| 13 License/provenance | UNVERIFIED | GPL policy present; campaign inventory/evidence missing. |
| 14 Documentation/operations | UNVERIFIED | Release operational checklist missing. |
| 15 Release candidate | UNVERIFIED | Depends on Gates 1–14. |

## Cycle 4 checkpoint — 2026-07-30

### Integration and cleanup evidence

- `3f9ffa46` (`fix(tet): reject nonmanifold metric sweep candidates`) merged after
  bundle backup. Metric-sweep unit/rescue/writer/boundary suites: `14 passed` in
  `2.31 s`. The target-cell suite remains `3 failed, 2 passed`; identical failures
  occur on the pre-card `866b64ef` baseline. The guard rejects the metric-sweep
  candidate for target `2000`; later VVV stages still produce writer-rejected
  non-manifold faces. This is a narrow topology safeguard, not a Gate-5 claim.
- `d16ba5aa` (`docs-inventory-declared-distribution-dependencies`) merged after
  rebase and bundle backup. Direct-declaration inventory covers Python base `9`
  and CMake direct `6`; verifier metric `0`, focused suite `7 passed`. All license
  assertions remain unresolved unless a local path is recorded; no SPDX/license
  inference was added. External adapter entries are explicitly outside future MIT
  native-core eligibility.
- `POLY-DUAL-REBUDGET-1` did not improve cube BL0 actual cells (`50 -> 15`,
  `100 -> 15`). Failed diff archive:
  `/home/younglin90/work/claude_code/AutoTessell-archive-20260730/failed-poly-dual-rebudget1.patch`
  (`sha256:04bbe40d0823c3fe8f629bb63ad8bfb4c02c811a709134ad861da20357cb2f5c`).
  Its clean rollback branch was bundle-backed, then removed without merge.
- Prior tet failed experiments remain archived:
  `failed-tet-vvv3b-topology.patch` and `failed-tet-vvv10-topology.patch`.
- Current Git before this ledger write: clean `master`, primary worktree plus one
  active native-poly worktree. No `third_party/` change reported.

### Gate re-evaluation

| Gate | Status | Cycle-4 evidence / next evidence |
|---|---|---|
| 1 Repository | UNVERIFIED | `master` clean before ledger write; active research worktree remains by design. Final closure scan pending. |
| 2 Build | UNVERIFIED | Native C++ clean Release build has no evidence. Existing build cache is not a clean-build proof. |
| 3 Automated tests | UNVERIFIED | CI uses `-x` and excludes display tests; skip/xfail inventory unresolved. |
| 4 Shape preservation | UNVERIFIED | Card-local boundary probes pass; campaign corpus absent. |
| 5 Mesh validity | FAIL | Native tet target 500/2000/10000 strict writer rejects non-manifold output. |
| 6 Cell count | FAIL | Native tet target suite fails; native poly cube BL0 `50/100 -> 15`. |
| 7 Boundary layer | UNVERIFIED | BL0 propagation passes; positive-layer corpus absent. |
| 8 Quality | UNVERIFIED | No campaign quality matrix/spec evidence. |
| 9 Reproducibility | UNVERIFIED | No three-run complete engine corpus. |
| 10 Robustness | UNVERIFIED | Invalid-input evidence is partial; full fixture matrix absent. |
| 11 Performance | UNVERIFIED | No frozen Release benchmark budgets. |
| 12 Packaging | UNVERIFIED | Python wheel smoke only; native and installer proof absent. |
| 13 License/provenance | UNVERIFIED | Binding manifest plus direct-declaration inventory pass; resolved artifacts/notices/source-offer evidence absent. |
| 14 Documentation/operations | UNVERIFIED | Release operations/checklist evidence absent. |
| 15 Release candidate | UNVERIFIED | Gates 1–14 remain open. |

## Cycle 5 checkpoint — 2026-07-30

### Integration, failure, and cleanup evidence

- `cce47cb3` made an explicit native-hex `boundary_layer=0` a complete no-op:
  explicit strategy/override zero succeeds with `layers_post_disabled_zero`, negative
  layer counts reject, and positive requests remain on their existing route. Direct
  suite: `28 passed in 46.99 s`. This is BL0 evidence only, not a positive-layer
  Gate-7 claim.
- `5ee28a00` adds a test-only native-tet strict-topology checkpoint. It confirms
  BETA2825/later phases as the source of the `2000`-cell non-manifold/duplicate
  writer failure; it does not alter generation behavior.
- `c36755e5` adds `BUILD_CINOLIB_HEX=OFF` as the default clean native-CMake
  configuration. A temporary fresh Release build with external adapters off built
  the declared native targets; it is partial Gate-2 evidence only.
- `37af2036` preserves an explicit native-poly target primal-vertex-floor failure
  through the tier without Voronoi fallback. Focused off-path tests pass, but an
  actual cube target route still exceeds the short validation budget; Gate 6 stays
  failed.
- `34122af9` adds the runtime-disconnected native-tri L0 source-clone certificate.
  It rejects moved/topology-edited/malformed-provenance candidates; direct
  certificate plus tri-route suite: `11 passed in 2.10 s`. It is not enabled as a
  topology-changing route.
- Tet `BETA2825-3TO2-TRANSACTION-GUARD-L1` was rejected, not merged. Cube target
  `2000` produced strict-writer-clean topology but failed the shape hard gate:
  `plane_area_coverage=0.7152778`, `hausdorff_relative=0.07763`, and cell error
  `-46.35%`. Failure evidence is outside the repository:
  `failed-tet-beta2825-3to2-transaction-guard-code.patch`
  (`sha256:a44308fef6c5e160ff183b5615889dbbca74836020f6d518553c647162f72b93`) and
  `failed-tet-beta2825-3to2-transaction-guard-test.patch`
  (`sha256:103bf2cb1932af300e93f180472dc02b873918b3830fb892c0f0bbabac155c1a`).
  Its exact worktree and unmerged branch were removed after archive verification.
- `7c8713fe` exports the already implemented native-face public API. It removes
  the collection ImportError (`7 tests collected`); direct public import and
  unused-import check pass. The now-runnable suite reports `5 failed, 2 passed in
  34.43 s`: three explicit face calls return `native operation failed: TypeError`,
  and two explicit engine names are not accepted by the pipeline routing allow-list.
  The export change itself makes no geometry or routing decision. Archive patch:
  `0001-fix-native-remesh-export-face-remesh-public-API.patch`
  (`sha256:52cba2e93181900f5a9f1e24e359389911cac48c0e5d64b3b8849a344f56fafd`).
- No card changed `third_party/`. Active worktrees remain deliberate campaign
  state; they prevent a Repository Gate PASS.

### Gate re-evaluation

| Gate | Status | Cycle-5 evidence / next evidence |
|---|---|---|
| 1 Repository | UNVERIFIED | `master` is clean at this checkpoint, but active research worktrees remain. |
| 2 Build | UNVERIFIED | Fresh partial native CMake Release build passes with optional Cinolib off; supported-config matrix remains absent. |
| 3 Automated tests | FAIL | Native-face collection now works, but its direct suite has 5 concrete failures; full unskipped suite not run. |
| 4 Shape preservation | UNVERIFIED | Card-local clone/boundary evidence only; campaign corpus absent. |
| 5 Mesh validity | FAIL | Native tet target 500/2000/10000 strict-writer failures remain on baseline. |
| 6 Cell count | FAIL | Native tet target suite fails; native poly cube BL0 `50/100 -> 15`; target preflight is still unmerged. |
| 7 Boundary layer | UNVERIFIED | Hex BL0 no-op passes; positive-layer corpus and actual-layer evidence absent. |
| 8 Quality | UNVERIFIED | No complete engine/fixture quality specification matrix. |
| 9 Reproducibility | UNVERIFIED | No complete three-run engine corpus. |
| 10 Robustness | UNVERIFIED | Native-face TypeError and incomplete invalid-input matrix remain. |
| 11 Performance | UNVERIFIED | No frozen Release benchmark budgets. |
| 12 Packaging | UNVERIFIED | Wheel smoke only; native/installer clean-install proof absent. |
| 13 License/provenance | UNVERIFIED | Binding/dependency manifests are partial; resolved artifacts/notices/source-offer proof absent. |
| 14 Documentation/operations | UNVERIFIED | Release operations/checklist evidence absent. |
| 15 Release candidate | UNVERIFIED | Gates 1–14 remain open. |

## Active research queue

1. `POLY-TARGET-PREFLIGHT-BUDGET-1` — active: validate a fail-closed, pre-tet refusal for an explicit BL0 target whose clamped uniform seed work exceeds the declared harness budget. No target-success claim.
2. `FACE-REMESH-TYPEERROR-ROOTCAUSE-1` — active: isolate the direct native-face TypeError and repair one shape-preserving cause only.
3. `FACE-REMESH-EXPLICIT-ROUTING-1` — queued after the direct face contract: register explicit native-face/native-quad engine names without changing default routing or fallback semantics.
4. `TET-POST-SWEEP-SURFACE-GATE-1` — queued: audit and fail-close the first post-sweep mutation that can bypass the existing plane/Hausdorff evidence.
5. `FULL-VALIDATION-BASELINE-1` — establish clean Release and unskipped test evidence without weakening gates.
6. `LIC-RESOLVED-ARTIFACT-SBOM-1` — inventory resolved wheel/installer artifacts and notices from fresh temporary outputs; no license inference.

## DOI and provenance record

Supplied PDFs indexed in `papers/PAPER_INDEX.md` and
`docs/references/literature/master_bibliography.csv`. Current campaign uses paper
ideas only; no external implementation code is copied. `third_party/` is out of
scope. Future MIT-core boundary follows
`docs/licensing/mit-core-transition-policy.md`.

## Cycle 6 checkpoint — 2026-07-30

### Integration, recovery, and cleanup evidence

- `1a8d892a` was merged through `d3c87f57`. The native-hex tier now forwards
  `target_edge_length`, `seed_density`, and other quality-aware arguments through
  a typed `_runner`, then attaches only route/contract provenance
  (`hex_uniform_grid`, `native_hex`). Focused wrapper plus native-hex suite:
  `17 passed in 26.25 s` after merge. Existing route-contract file lint has two
  baseline violations; the changed module passes isolated strict mypy and ruff.
  Archive: `hex-runner-contract-1a8d892a/0001-fix.patch`
  (`sha256:69bcd5b9d3be4f7b6ec711fb363264aa21b5e8028d27fe45796e063822693f0a`).
- `3d0a9b0d` was merged through `c316de12`. The public planar-surface export now
  delegates unchanged inputs to the existing native padding writer. Collection now
  finds `11` surface-padding tests; its isolated delegation test passes in
  `2.18 s`. The native module target is absent, so the full surface-padding suite
  honestly reports `10 failed, 1 passed` with
  `native_surface_padding is unavailable; build ... target ... first`. No Python
  fallback was added. Archive:
  `surface-planar-padding-export-3d0a9b0d/0001-fix-surface-expose-planar-padding-export.patch`
  (`sha256:526dd66afd09ae08c3b4344cc3cc46ba809c73db89a271adeba35f6fcbb9adfc`).
- `b3bc437f` was merged through `a1be3c47`. Optional
  `AUTO_TESSELL_TET_METRIC_SOURCE_TXN=1` adds an exact pre-sweep snapshot and
  source-metric transaction around only the metric-tensor sweep. It rejects any
  non-finite or worsened normalized symmetric Hausdorff, plane coverage, or area
  coverage result and returns the original arrays. Default remains OFF. L0 plus
  metric-sweep tests: `4 passed in 2.23 s`; isolated strict mypy passes. Cube
  `target=2000` OFF and ON both retain the same known strict-topology rejection
  (`4` non-manifold references) followed by the pre-existing rebudget
  `max_cells` keyword error; this is not a new success or regression. Archive:
  `tet-metric-source-transaction-b3bc437f/0001-feat-native-tet-guard-metric-sweep-source-fidelity.patch`
  (`sha256:0fcb08aaaee95ce9d57a8b7f62579bce84c9e79e00f33cd20fc37dac6ac03f0a`).
- A failed first hex merge left only empty Git merge metadata. Staged, unstaged,
  and conflict diffs were all zero before the metadata was removed and the merge
  retried successfully. No user source file was reset, checked out, or deleted.
- Before next-card creation, `master` had one clean primary worktree, branch
  `master` only, no dirty or untracked files, no submodule change, no
  `third_party/` diff, and `git diff --check` passed. Archived clean recovery
  worktrees and merged branches were removed exactly. New cycle worktrees are
  limited to the three active cards below.

### Automated-test baseline

- Full unskipped collection after the three integrations: `3938 tests collected,
  1 error in 5.21 s`. The remaining collector error is a missing native-tet L0
  helper: `_input_vertices_exactly_present_l0`.
- This is an improvement from the prior three collection errors. It is not a
  full-test PASS; native surface padding still lacks a built target and native-tet
  target/validity failures remain.

### Active parallel lanes

1. `CMAKE-NATIVE-SURFACE-PADDING-TARGET-1` — branch
   `codex/cmake-native-surface-padding-1`; only CMake/build-script wiring for the
   already tracked, self-contained pybind target. No external dependency or
   routing change.
2. `FACE-REMESH-EXPLICIT-ROUTING-1` — branch
   `codex/face-explicit-routing-1`; accept explicit native face/quad names only,
   preserving default routing and current shape gates.
3. `TET-INPUT-VERTEX-L0-HELPER-RESTORE-1` — branch
   `codex/tet-input-vertex-contract-1`; restore or truthfully relocate the missing
   test-only input-vertex certificate before the later tet target contract card.

### Gate re-evaluation

| Gate | Status | Cycle-6 evidence / next evidence |
|---|---|---|
| 1 Repository | UNVERIFIED | Clean one-worktree scan passed before the three active isolated lanes; final closure waits for their merge/cleanup. |
| 2 Build | UNVERIFIED | Fresh partial native Release evidence exists; native surface-padding target is not wired. |
| 3 Automated tests | FAIL | Full collection has one missing tet helper; surface-padding full suite has `10` native-target failures. |
| 4 Shape preservation | UNVERIFIED | Tet transaction adds a default-OFF rollback guard; campaign corpus absent. |
| 5 Mesh validity | FAIL | Native tet target route still rejects strict non-manifold topology. |
| 6 Cell count | FAIL | Native tet target route fails before rebudget (`max_cells` keyword) after strict writer rejection; poly target control remains unresolved. |
| 7 Boundary layer | UNVERIFIED | BL0 evidence only; positive-layer corpus absent. |
| 8 Quality | UNVERIFIED | No complete engine/fixture quality specification matrix. |
| 9 Reproducibility | UNVERIFIED | No complete three-run engine corpus. |
| 10 Robustness | UNVERIFIED | Explicit native face route and input-vertex contracts still incomplete. |
| 11 Performance | UNVERIFIED | No frozen Release benchmark budgets. |
| 12 Packaging | UNVERIFIED | Wheel smoke only; native module/installer clean-install proof absent. |
| 13 License/provenance | UNVERIFIED | Existing inventory and manifest are partial; no resolved artifact proof. |
| 14 Documentation/operations | UNVERIFIED | Release operations/checklist evidence absent. |
| 15 Release candidate | UNVERIFIED | Gates 1–14 remain open. |

### Next automatic actions

- Verify and integrate passing isolated lanes in campaign order; archive before
  exact worktree and merged-branch removal.
- Re-run full collection after the tet L0 helper card. If it clears, schedule a
  classified full-test baseline rather than treating collection as a test pass.
- Follow tet helper cleanup with the separate `TET-TARGET-MAX-CELLS-CONTRACT-1`
  card. It may not overlap another `mesher.py` mutation.

## Cycle 7 checkpoint — 2026-07-30

### User-priority update

- Native-tet target-cell work is deferred.  Strict topology is the immediate
  primary metric; a release Gate-6 failure is recorded but does not block the
  next strict-topology card.
- The topology acceptance rule may be made less brittle only when a proof shows
  that the relaxed/recovered candidate preserves the exterior boundary and has
  no invalid or residual non-manifold entity.  A real 3+-cell face is never
  silently encoded as a successful OpenFOAM mesh.

### Integration, recovery, and cleanup evidence

- `c884ac8e` merged through `7a9a8735`.  Explicit `native_face_remesh` and
  `native_quad_dominant` now reject a positive `target_faces` before invoking
  an engine or fallback; `None` and `0` retain the existing route.  Focused
  route suite: `32 passed in 24.36 s`; post-merge native-face suite:
  `12 passed in 2.78 s`.  Archive patches:
  `face-explicit-target-contract-c884ac8e/` and
  `face-explicit-routing-21cc0214/`.
- `380a0cda` merged through `2a530343`.  The native-tet final sync now removes
  every member of an exact duplicate-tetrahedron group only if boundary face
  keys are unchanged and the resulting tet audit has zero duplicate,
  degenerate, open-edge, non-manifold-edge, and non-manifold-face entities.
  Residual true non-manifold output still reaches the strict writer and fails
  closed.  No external source was copied; the independent provenance note is
  `docs/references/tetrahedral_meshing/strict_topology_duplicate_group_repair_2026-07-30.md`.
- Cylinder strict-topology probe (`target_cells=2000`, external rescue off):
  baseline `1499` tets with `4` non-manifold faces and `2` exact duplicate
  groups; recovered result `1495` tets, boundary keys `216 -> 216`, boundary
  area unchanged, and all audited duplicate/degenerate/open/non-manifold counts
  `0`.  Requested/actual cell error is `-505` (`-25.25%`), intentionally not
  accepted as a target-cell success under the new priority.
- Strict topology focused suite after merge: `24 passed in 16.89 s`.  The
  cylinder regression passed three independent runs (`17.50 s`, `17.53 s`,
  `17.92 s`).  The generic strict-writer non-manifold rejection tests remain
  green.
- `FULL-VALIDATION-BASELINE-1` ran with a `900 s` watchdog, reached about
  `14%`, and ended without a pytest summary.  `master` changed during the run,
  so this is invalid baseline evidence, not a pass or a fail.  It must be
  rerun on an immutable commit.
- Both merged face worktrees/branches and the merged tet worktree/branch were
  archived then removed exactly.  Tet archive:
  `tet-strict-topology-duplicate-repair-380a0cda/0001-fix-native-tet-duplicate-group-topology-repair.patch`
  (`sha256:52fc3314c95bf75993dd4e1eec845cf91a841f788c19464b0e7fe6cfb0557947`).
  No `third_party/` file changed.

### Research record

- CGAL 6.2 Tetrahedral Remeshing documentation was checked for this card:
  topology-preserving atomic operations and feature-complex preservation are
  separated from sizing optimization.  Sources:
  `https://doc.cgal.org/latest/Tetrahedral_remeshing/index.html` and
  `https://doc.cgal.org/latest/Tetrahedral_remeshing/group__PkgTetrahedralRemeshingRef.html`.
  The card uses only the independently implemented contract above.

### Gate re-evaluation

| Gate | Status | Cycle-7 evidence / next evidence |
|---|---|---|
| 1 Repository | UNVERIFIED | `master` clean after cleanup; active campaign lanes prevent terminal closure. |
| 2 Build | UNVERIFIED | Native Release matrix remains incomplete. |
| 3 Automated tests | UNVERIFIED | Focused regressions pass; full immutable-head run remains missing. |
| 4 Shape preservation | UNVERIFIED | Duplicate repair proves pre/post tet boundary equality; corpus proof remains missing. |
| 5 Mesh validity | UNVERIFIED | Cylinder strict topology is repaired and writer-valid; cube/corpus strict topology is next. |
| 6 Cell count | FAIL | Existing tet/poly target contracts remain unmet.  Tet target work is deferred by user priority. |
| 7 Boundary layer | UNVERIFIED | BL0-only evidence; positive-layer corpus remains missing. |
| 8 Quality | UNVERIFIED | No complete engine/fixture specification matrix. |
| 9 Reproducibility | UNVERIFIED | Card-local cylinder 3-run pass only; campaign corpus is missing. |
| 10 Robustness | UNVERIFIED | Strict duplicate-group recovery is one fixture; full adverse corpus remains missing. |
| 11 Performance | UNVERIFIED | No frozen Release benchmark budgets. |
| 12 Packaging | UNVERIFIED | Wheel smoke only; native/installer clean-install proof missing. |
| 13 License/provenance | UNVERIFIED | Current GPL and no-third-party policy upheld; artifact proof remains incomplete. |
| 14 Documentation/operations | UNVERIFIED | Release operations/checklist proof missing. |
| 15 Release candidate | UNVERIFIED | Gates 1–14 remain open. |

### Next automatic actions

- `TET-STRICT-TOPOLOGY-CUBE-PROBE-1`: run the known cube target route as a
  topology probe only; classify whether duplicate-group recovery clears it or
  a true residual face incidence remains.  Do not rebudget or relax target
  tolerance in this card.
- `HEX-NEXT-CARD-SCAN-1`: select one independently testable native-hex card in
  parallel, then assign a clean worktree.
- After those, select native-poly and native-tri/quad cards from their own
  research/evidence records.  Gate 6 remains recorded but is not the tet lane's
  scheduling priority.

## Cycle 8 checkpoint — 2026-07-30

### User-priority application

- Native-tet strict topology is scheduled before target-cell control.  Gate 6
  remains an explicit `FAIL`, but it is not an acceptance condition for the
  current tet topology cards.
- The only relaxed tet assertion is the stale exact final count (`1495`).  The
  replacement requires positive duplicate-repair evidence, unchanged boundary,
  zero residual duplicate/degenerate/open/non-manifold entities, strict writer
  success, and tetrahedron encoding for every written cell.  A true 3+-cell
  face, invalid cell, or shape-contract failure remains fail-closed.

### Integration, recovery, and cleanup evidence

- `ff5a0275` merged through `8dd402f0`.  Native-tet harness candidates now
  remeasure final arrays immediately before evaluator/best-case selection.  A
  missing, non-finite, or planar source-coverage failure is rejected before
  output promotion.  Focused source-contract suite: `8 passed in 2.01 s`.
  Archive: `tet-harness-source-shape-contract-ff5a0275/`
  (`sha256:65b7349ecdd9e411b6a76cc4b80de2fd857765e5cef8500b04285b8863b8886b`).
- `4185f419` merged through `54f0fc1b`.  The cylinder strict-topology regression
  now treats the observed final count (`1493`) as Gate-6 evidence rather than a
  topology invariant.  Parent post-merge topology/rescue suite: `8 passed in
  16.57 s`.  Archive: `tet-strict-topology-contract-calibration-4185f419/`
  (`sha256:3c5c93b4842f967b99044d698284380bb868c0a4bd507c0b5e06380a5b8b0627`).
- `e561609b` merged through `129ffaeb`.  Native-hex wallfit candidate labels
  now require a valid authoritative source manifest; missing, altered, or
  ambiguous sidecars report `UNAVAILABLE` rather than inferred provenance.
  Focused suite: `10 passed in 2.34 s`.  Archives:
  `hex-wallfit-candidate-provenance-e4768527/` and
  `hex-wallfit-candidate-provenance-e561609b/`.
- `372cc430` merged through `c6fb8f93`.  Native-poly fails before writer output
  when an explicit boundary entity mapping omits an extracted boundary face.
  Focused suite: `2 passed in 2.14 s`.  Archive:
  `poly-dual-classify-coverage-372cc430/`
  (`sha256:19cf89ce1174b09ada79afed247d5b7cfb108a9d74eb4cdab7d91607266a3989`).
- `a303bbc1` merged through `363a3836`.  Native quad decoding now rejects lossy
  raw triangle indices and nonexistent/degenerate protected wall edges before
  pairing; valid input ordering and coordinates remain unchanged.  Parent
  focused suite: `32 passed in 2.27 s`.  Archive:
  `quad-input-identity-a303bbc1/`
  (`sha256:229e907f1beae171c52048a33bcbfa1f5e55f269c89ada88f6203f4873ed6535`).
- All four integrated lanes were rebased or conflict-reviewed against current
  `master`, post-merge tested, archive-verified, then removed exactly.  The
  current repository scan has one primary worktree, `master` only, a clean
  working tree, `git diff --check` pass, and no `third_party/` diff.
- Strict global mypy is still baseline-blocked: invoking it for the changed quad
  module follows the import graph and reports `2784` existing errors in `152`
  files.  This card introduced no reported new focused type error; the global
  type baseline remains release work, not a PASS.

### Gate re-evaluation

| Gate | Status | Cycle-8 evidence / next evidence |
|---|---|---|
| 1 Repository | UNVERIFIED | Current scan is clean with one primary worktree; terminal scan must repeat after the next isolated lanes. |
| 2 Build | UNVERIFIED | Native Release configuration matrix remains incomplete. |
| 3 Automated tests | UNVERIFIED | Focused suites pass; immutable-head full test evidence remains missing. |
| 4 Shape preservation | UNVERIFIED | Tet final-array source guard and local face/quad contracts strengthened; representative corpus proof remains missing. |
| 5 Mesh validity | UNVERIFIED | Cylinder duplicate repair is writer-valid; strict topology must be classified over the cube/corpus without target acceptance coupling. |
| 6 Cell count | FAIL | Tet target work is explicitly deferred; existing poly target-following failure remains. |
| 7 Boundary layer | UNVERIFIED | BL0 evidence exists; positive-layer corpus remains missing. |
| 8 Quality | UNVERIFIED | No complete engine/fixture quality specification matrix. |
| 9 Reproducibility | UNVERIFIED | Card-local deterministic checks exist; engine corpus is missing. |
| 10 Robustness | UNVERIFIED | Quad input identity and explicit failure reporting improved; adverse corpus is incomplete. |
| 11 Performance | UNVERIFIED | No frozen Release benchmark budgets. |
| 12 Packaging | UNVERIFIED | Wheel smoke only; native and installer clean-install proof missing. |
| 13 License/provenance | UNVERIFIED | GPL/no-third-party policy held; resolved release-artifact proof remains incomplete. |
| 14 Documentation/operations | UNVERIFIED | Release operations/checklist proof missing. |
| 15 Release candidate | UNVERIFIED | Gates 1–14 remain open. |

### Next automatic actions

- `TET-STRICT-TOPOLOGY-CORPUS-PROBE-1`: classify strict topology, writer
  validity, and source metrics on cube and cylinder with target count recorded
  only as diagnostic.  Do not weaken real topology or shape gates.
- In parallel, research and select one bounded native-hex, native-poly, and
  native-tri/quad card from current Gate-4/5/7/10 deficits.  No external code
  reuse and no `third_party/` modification.
- Run an immutable-head validation baseline only after the next integration
  cycle; retain all unrun/full-suite gates as `UNVERIFIED`.

## Cycle 9 checkpoint — 2026-07-30

### Repository integration and storage cleanup evidence

- Common pytest collection (`37f8e2d0`), native-hex input preflight
  (`51046a1c` after rebase), and native-poly invalid dual-tet input preflight
  (`59930f43` after rebase) were reviewed, tested, and merged sequentially.
  Current integrated master before this ledger commit is
  `4246cf6f478a69290264862e967a968c2c8124bb`.
- Post-merge focused validation in the rebuilt environment reports `29 passed
  in 26.03 s`: common collection `2`, hex preflight `14`, and poly preflight
  `13`.  An additional representative native-hex target/layer selection reports
  `6 passed` before integration.  These are focused results, not Gate-3 proof.
- The three merged worktrees and their branches were removed through Git.  The
  only remaining research worktree is the protected, clean
  `codex/tet-vonly-contract-probe-1` lane at pre-integration commit `3a5c387b`.
- Two complete-history bundles were written to
  `D:\\AutoTessell-cleanup-backup-20260730`: pre-cleanup SHA-256
  `451f260b9dcd48e873fce7b3cfcec2eb5c722e2471e2dc5454961a0a799161e5`
  and post-integration SHA-256
  `5a1b59cca595de3810850ae6f03c9940fc81633577b3acec107f80aefc300609`.
  Both pass `git bundle verify`.
- Exact ignored/generated paths were moved to the D: quarantine, including
  selected FetchContent source directories and Python/build caches.  The whole
  tracked `build_make/_deps` tree was not deleted.  The quarantine is about
  `344 MiB`.
- The prior project archive was copied to D:, verified by recursive diff, then
  removed from WSL.  The full former `.venv` library and both project
  micromamba environments were archived to D: before their exact originals
  were removed.  The current project `.venv` was rebuilt without the optional
  AI/GPU extra; declared native/GUI/CAD/Netgen imports and the focused suite
  pass.  The old full environment remains recoverable from D:.
- WSL filesystem used space fell from about `226 GiB` to `207 GiB`.  The D:
  backup root is about `14 GiB`.  C: space is not yet reclaimed because the
  non-sparse `ext4.vhdx` has not been compacted.
- Offline VHDX compaction is blocked in this session because the Windows token
  is not elevated (`ADMIN=False`).  Sparse-VHD conversion was not attempted.
  Compaction requires an elevated Windows session after WSL shutdown and an
  offline VHDX backup.
- `git diff --check` and `git fsck --full` pass.  `git fsck` reports historical
  dangling objects only; no prune or aggressive GC was run.  No `third_party/`
  file changed.

### Gate re-evaluation

| Gate | Status | Cycle-9 evidence / next evidence |
|---|---|---|
| 1 Repository | UNVERIFIED | Primary master is clean before this ledger write; one protected active Tet worktree remains. |
| 2 Build | UNVERIFIED | Rebuilt Python environment imports pass; clean native Release matrix remains missing. |
| 3 Automated tests | UNVERIFIED | New merged focused suite is `29 passed`; immutable-head full suite remains missing. |
| 4 Shape preservation | UNVERIFIED | No cleanup changed geometry code; representative corpus proof remains missing. |
| 5 Mesh validity | UNVERIFIED | Tet strict-topology corpus probe remains next. |
| 6 Cell count | FAIL | Tet target remains diagnostic/deferred; poly target following remains unresolved. |
| 7 Boundary layer | UNVERIFIED | Positive-layer corpus remains missing. |
| 8 Quality | UNVERIFIED | Complete engine/fixture quality matrix remains missing. |
| 9 Reproducibility | UNVERIFIED | Complete three-run corpus remains missing. |
| 10 Robustness | UNVERIFIED | Hex/poly input preflight evidence is focused only. |
| 11 Performance | UNVERIFIED | Frozen Release benchmark budgets remain missing. |
| 12 Packaging | UNVERIFIED | Current environment smoke passes; installer proof remains missing. |
| 13 License/provenance | UNVERIFIED | GPL/no-third-party policy held; release-artifact proof remains incomplete. |
| 14 Documentation/operations | UNVERIFIED | Cleanup recovery evidence added; release operations proof remains incomplete. |
| 15 Release candidate | UNVERIFIED | Gates 1–14 remain open. |

### Next automatic action

- Rebase the protected Tet lane onto current master and execute
  `TET-STRICT-TOPOLOGY-CORPUS-PROBE-1`.  Treat target-cell count as diagnostic;
  retain essential shape, validity, writer, and residual non-manifold gates.

## Cycle 10 checkpoint -- 2026-07-30

### Native C++23 integration evidence

- `8a6b82a3` through `7cd77710` connected the existing first-party exact Tet
  predicate and quality-optimization sources to the CMake and Python runtime
  paths.  The native-only Release build now compiles seven explicit targets
  with Python 3.12 and pybind11 3.0.4.  Tet topology/predicate/QOPT focused
  validation reports `70 passed`; the full native extension set exposed one
  pre-existing evaluator topology materialization failure.
- The Tet optimizer now stores adjacency and incident stars in flat sorted CSR
  arrays instead of nested vectors and reuses candidate buffers.  On a
  4,096-point/20,250-tet guarded smoothing fixture, median runtime changed from
  `0.104483 s` to `0.013313 s` (`7.85x`) with maximum coordinate delta
  `3.331e-16`.  The fused 80,000-tet quality snapshot changed from
  `0.103394 s` to `0.015934 s` (`6.49x`) with maximum relative metric delta
  `3.533e-11`.
- `fdd93772` ports triangle-only Phase-0 evaluator metrics to a C++23 CSR
  topology kernel.  It avoids `list[list[int]]`, per-cell Python sets, and
  repeated NumPy temporaries while retaining the polygon fallback.  All 29
  report fields match the Python oracle on boundary-only and internal-face
  tetra fixtures.  The native extension regression now reports `125 passed`
  with zero skips; the previous topology materialization failure is closed.
- On a 2,000-cell/8,000-face tetra corpus, Phase-0 median runtime changed from
  `1.038211 s` to `0.000764 s` (`1359x`), with maximum absolute field delta
  `1.676e-14`.  The native metrics target builds with
  `-Wall -Wextra -Wpedantic` and no warning.
- Strict mypy remains baseline-blocked: the two touched Python files report 43
  errors, including pre-existing imported-module and untyped-test errors.
  This is not treated as a passing type gate.
- The cube Phase-A route remains intermittently non-reproducible in the
  existing stochastic P4C fallback: repeated baseline and native-disabled runs
  can preserve only 7 of 8 source corners.  This is not caused by the C++23
  cards, but it keeps shape/reproducibility release evidence open.
- Both integrated branches have complete-history bundles under
  `D:\\AutoTessell-cleanup-backup-20260730\\research-bundles`; the latest
  SHA-256 values are `c2171ae8bf62f8ad9c44d843007b6fea7bd926d01a49deeed8f11c71600185c3`
  and `0ff2d85abc6a0b8f6b603d72a01235efc3454d5e9a5bb14ec92b9d162d9d4d0f`.
  No `third_party/` file changed.

### Gate re-evaluation

| Gate | Status | Cycle-10 evidence / next evidence |
|---|---|---|
| 1 Repository | UNVERIFIED | Main is clean before this ledger update; the protected Tet research worktree remains active. |
| 2 Build | UNVERIFIED | Seven native Release targets build cleanly on Ubuntu/GCC 13; supported-platform matrix is incomplete. |
| 3 Automated tests | UNVERIFIED | Native extension set is `125 passed`; immutable-head full suite remains missing. |
| 4 Shape preservation | FAIL | Existing stochastic P4C cube fallback intermittently preserves only 7/8 source corners. |
| 5 Mesh validity | UNVERIFIED | Tet strict-topology corpus and all-engine validity corpus remain incomplete. |
| 6 Cell count | FAIL | Tet target remains diagnostic/deferred; poly target following remains unresolved. |
| 7 Boundary layer | UNVERIFIED | BL0 evidence exists; positive-layer corpus and native profile remain missing. |
| 8 Quality | UNVERIFIED | Tet quality parity is proven locally; complete engine/fixture matrix is missing. |
| 9 Reproducibility | FAIL | P4C cube fallback varies across identical repeated runs. |
| 10 Robustness | UNVERIFIED | Exact predicates and evaluator CSR coverage improved; adverse corpus is incomplete. |
| 11 Performance | UNVERIFIED | Two native microbenchmarks pass leverage thresholds; frozen end-to-end budgets are missing. |
| 12 Packaging | UNVERIFIED | Native modules build locally; clean installer and artifact proof remain missing. |
| 13 License/provenance | UNVERIFIED | First-party sources only and no-third-party policy held; release inventory remains incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration plan exists; complete release operations proof is missing. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Profile representative native boundary-layer and Tet routes.  Select one
  shape-preserving Python kernel with a measured dominant cost, freeze parity
  and rollback conditions, then port only that kernel to an isolated C++23
  target or an existing native module.

## Cycle 11 checkpoint -- 2026-07-30

### Native boundary-layer and Tet topology evidence

- `f0c7f07e` adds a first-party C++23 uniform-grid spatial hash for opposite
  boundary-front proximity.  On 5,000 vertices it matches the bounded Python
  mask and changes median runtime from `0.362497 s` to `0.001875 s`
  (`193.33x`).  It removes the old 25-million-entry dense-pair route.  Focused
  boundary-layer validation reports `84 passed`.
- `c9bd7867` makes a selected wall front with a true 3-owner edge fail before
  backup, output, or quality-report writes.  The error records the edge and
  all incident wall-face IDs.  Input polyMesh bytes remain unchanged.
- `f9c163b7` ports the repeated Tet strict-topology audit to C++23.  It uses
  reserved canonical tet/face/edge hash tables plus flat union-find, releases
  the GIL, and removes NumPy face/edge materialization.  Expected time and
  auxiliary space are `O(T+B)` under ordinary hash occupancy.
- On `35,937` points and `196,608` tetrahedra, the native audit takes
  `0.264357 s` versus `1.789529 s` (`6.77x`).  All eight audit counters match;
  the Python fallback's traced temporary heap peak is `114.43 MiB`.  Clean
  native-only Release build compiles all eight first-party modules with GCC
  13.3.  Post-merge Tet predicate/rescue/Klingner/strict-result suites report
  `61 passed`.
- The old cube-10k diagnostic expected writer failure even after current
  `master` safely removes an exact duplicate tet group.  Baseline reproduces
  this stale assertion.  The updated test requires pre-repair defect evidence,
  exact two-cell group removal, unchanged boundary keys, and a strict-valid
  final audit.  No topology threshold was relaxed.
- Complete-history bundles pass verification.  SHA-256:
  `ac05f664dfbf14c2fb045bacd9dd947790a6838501537f0c39c4d65bdd06cf08`,
  `109057201c762129b791e798c69a2f6f9cf017bf7d744e771287c3598651b40d`,
  and `c48de3ff8db731b228ddb3721c5d34580a28e88bbfd2e925023f07f41900be85`.
  The obsolete protected Tet worktree was also proven merged, bundled, and
  removed.  No `third_party/` file changed.

### Gate re-evaluation

| Gate | Status | Cycle-11 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` clean before ledger commit, integrated research branches removed, `git diff --check` and no-third-party checks pass. |
| 2 Build | UNVERIFIED | Eight native Release targets build warning-free on Ubuntu/GCC 13; supported OS/compiler matrix is incomplete. |
| 3 Automated tests | UNVERIFIED | Focused native suites pass; immutable-head full suite remains missing. |
| 4 Shape preservation | FAIL | Strict topology and BL fail-closed contracts improved; stochastic P4C still has a 7/8-corner case. |
| 5 Mesh validity | UNVERIFIED | Cube-10k exact duplicate repair is strict-valid; full Tet/all-engine corpus remains incomplete. |
| 6 Cell count | FAIL | Tet target remains diagnostic/deferred by user priority; poly target following remains unresolved. |
| 7 Boundary layer | UNVERIFIED | BL0 and front-failure evidence exists; positive-layer corpus is incomplete. |
| 8 Quality | UNVERIFIED | No complete engine/fixture quality matrix. |
| 9 Reproducibility | FAIL | P4C cube fallback remains non-deterministic. |
| 10 Robustness | UNVERIFIED | Non-manifold BL front now fails closed; adverse all-engine matrix is incomplete. |
| 11 Performance | UNVERIFIED | Three native kernels exceed local leverage thresholds; frozen end-to-end budgets remain missing. |
| 12 Packaging | UNVERIFIED | Native modules build locally; clean installer/artifact proof remains missing. |
| 13 License/provenance | UNVERIFIED | New code is first-party, GPL remains, third-party is untouched; release inventory remains incomplete. |
| 14 Documentation/operations | UNVERIFIED | Migration evidence updated; complete release operations proof is missing. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Profile native Poly and tri/quad representative topology routes.  Select one
  Python allocation/search hotspot with measurable production cost.  Preserve
  exact input coordinates, topology, physical groups, and provenance while
  porting one kernel to an existing first-party C++23 module.

## Cycle 12 checkpoint -- 2026-07-30

### Native Poly incidence evidence

- `875f676c` ports `native_poly.dual._build_tet_topology` to the first-party
  `native_polymesh` C++23 module.  One connectivity scan builds reserved
  vertex, canonical-edge, and canonical-face incidence buckets.  First-seen
  key order is retained separately from hash lookup order, so downstream dict
  traversal and provenance remain byte-for-byte compatible.
- Structured `24,389`-vertex / `131,712`-tet benchmark: `11.105566 s` Python
  versus `7.890530 s` native (`1.41x`).  Traced Python heap is `335.47 MiB`
  versus `159.19 MiB` (`52.55%` reduction).  All `24,389` vertex keys,
  `160,804` edge keys, `268,128` face keys, insertion order, and owner lists
  match exactly.
- `native_polymesh` now requires C++23 without compiler extensions and builds
  with `-Wall -Wextra -Wpedantic` or `/W4`.  Clean native-only build compiles
  all eight targets.  Post-merge extension and focused dual suite reports
  `22 passed`; representative sphere dual reports `1 passed in 51.68 s`.
- Wider combined Poly validation timed out at `124 s`; it is not counted as a
  pass.  Full-validation lane remains required.  The card bundle verifies at
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-poly-tet-incidence-1-875f676c.bundle`,
  SHA-256 `18309759d9787bda4a3c064446c91ea1dfe037474f01735b08a64bc962a7b527`.
  Worktree and branch were removed after integration.  No `third_party/`
  source changed.
- CGAL 6.2 and OpenVolumeMesh topology documentation were reviewed for data
  structure principles.  No external implementation was copied; code and
  tests are independent first-party work.

### Gate re-evaluation

| Gate | Status | Cycle-12 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One clean primary worktree and `master` branch only after integration. |
| 2 Build | UNVERIFIED | Eight native targets warning-clean on Ubuntu/GCC 13; platform matrix remains incomplete. |
| 3 Automated tests | UNVERIFIED | Focused Poly suite passes; wide batch timed out and immutable-head full suite is missing. |
| 4 Shape preservation | FAIL | Poly incidence is exact-parity; stochastic Tet P4C 7/8-corner case remains. |
| 5 Mesh validity | UNVERIFIED | Representative sphere dual passes; complete all-engine corpus remains missing. |
| 6 Cell count | FAIL | Poly target following and deferred Tet target remain unresolved. |
| 7 Boundary layer | UNVERIFIED | Positive-layer corpus remains incomplete. |
| 8 Quality | UNVERIFIED | Complete engine/fixture quality matrix missing. |
| 9 Reproducibility | FAIL | Tet P4C non-determinism remains. |
| 10 Robustness | UNVERIFIED | Poly input/ordering contracts strengthened; adverse corpus incomplete. |
| 11 Performance | UNVERIFIED | Poly topology heap and time improve; end-to-end budgets missing. |
| 12 Packaging | UNVERIFIED | Clean installer/artifact proof missing. |
| 13 License/provenance | UNVERIFIED | Independent first-party code; GPL/no-third-party policy held; release inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Profile tri/quad operator adjacency and candidate-evaluation loops.  Port one
  measured kernel without changing source coordinates, protected edges,
  triangle identity, physical groups, or deterministic operator ordering.

## Cycle 13 checkpoint -- 2026-07-30

### Rejected native-quad edge-map experiment

- Baseline profiling found `_edge_faces` at `2.105385 s` and `78.43 MiB`
  traced Python heap for `180,000` triangles and `270,600` unique edges.
- A first-party C++23 compatibility prototype preserved exact edge insertion
  order and incident-face lists.  Its isolated result was only `1.13x` faster
  (`2.316470 s` to `2.041235 s`) with `8.44%` traced-heap reduction.
- End-to-end quad-dominant conversion on `9,800` triangles was neutral/slower:
  `3.586859 s` Python versus `3.593937 s` native (`0.998x`).  Vertices,
  triangles, quads, and diagnostics matched exactly; focused validation was
  `59 passed` with two known all-NaN warnings.
- The prototype was rejected and not merged.  Retrying the same standalone
  dict-returning edge-map hypothesis is prohibited.  Recoverable bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-quad-edge-incidence-rejected.bundle`,
  SHA-256 `215957ab39e8e9f5d5a93ef6215bcdb3c424fb7f861648d4604eca479755eecc`.
  Its worktree and branch were removed.  `master` source and `third_party/`
  were unchanged.

### Next automatic action

- Measure a fused native-quad input-validation plus edge-incidence kernel.
  It must eliminate the duplicate full surface scan and Python vertex-link
  graph together, preserve exact error precedence/messages, and improve the
  representative end-to-end conversion.  Otherwise reject it too.

## Cycle 14 checkpoint -- 2026-07-30

### Native quad fused-preflight evidence

- `1217f038` fuses quad finite/index validation, canonical face identity,
  zero-area detection, directed edge manifold/orientation checks, vertex-link
  connectivity, and ordered edge-to-face incidence in one C++23 kernel.
  Python fallback also reuses the edge owners collected by validation, so both
  routes eliminate the prior second surface scan.
- Planar `9,800`-triangle public-route benchmark under identical allocation
  tracing: `19.717281 s` fallback versus `17.251941 s` native (`1.143x`);
  traced Python heap `15.54 MiB` versus `11.27 MiB` (`27.48%` reduction).
  Source vertices, residual triangles, `4,900` quads, all ordering, and every
  diagnostic field match exactly.
- Degenerate, duplicate, zero-area, inconsistent-edge, non-manifold-edge, and
  non-manifold-vertex fixtures assert exact native/Python error parity.
  Post-merge quad-dominant, messy-grid, multires, and native-metrics suites
  report `93 passed`; two known all-NaN warnings remain.
- Bundle verification passes at
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-quad-fused-preflight-1-1217f038.bundle`,
  SHA-256 `71af03d3da90d6f012bed091a2b926020a3ac9321043e94f3c74a2eaf4cdbd51`.
  Worktree and branch were removed.  `third_party/` remains unchanged.

### Gate re-evaluation

| Gate | Status | Cycle-14 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean after integration. |
| 2 Build | UNVERIFIED | Changed native target is warning-clean on Ubuntu/GCC 13; platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused 93-test suite passes; immutable-head full suite missing. |
| 4 Shape preservation | FAIL | Quad source arrays are exact; Tet P4C 7/8-corner case remains. |
| 5 Mesh validity | UNVERIFIED | Quad invalid topology fails closed; complete corpus missing. |
| 6 Cell count | FAIL | Poly target following and deferred Tet target unresolved. |
| 7 Boundary layer | UNVERIFIED | Positive-layer corpus incomplete. |
| 8 Quality | UNVERIFIED | Quad quality output unchanged; matrix incomplete. |
| 9 Reproducibility | FAIL | Tet P4C non-determinism remains. |
| 10 Robustness | UNVERIFIED | Quad preflight strengthened; all-engine adverse matrix incomplete. |
| 11 Performance | UNVERIFIED | Quad end-to-end time/heap improve; frozen release budgets missing. |
| 12 Packaging | UNVERIFIED | Clean installer/artifact proof missing. |
| 13 License/provenance | UNVERIFIED | Independent first-party C++; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | Migration and failure ledger updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Reproduce the Tet P4C cube source-corner loss under identical inputs and
  seeds.  Localize whether nondeterminism enters external fallback output,
  candidate acceptance, or post-fallback topology passes.  Shape preservation
  remains hard priority; target-cell tuning stays deferred.

## Cycle 15 checkpoint -- 2026-07-30

### Tet P4C immutable-source acceptance evidence

- Baseline cube Phase-A failed once in five independent processes with only
  `6/8` exact source corners.  Direct instrumentation then localized the first
  divergence to raw `pytetwild` output: four of twelve identical calls returned
  only `7/8` exact corners, and final output copied the same deficient candidate.
- `fee82ef1` connects the existing exact source-vertex certificate to every P4C
  tier before candidate acceptance.  A higher-quality candidate that loses any
  immutable source coordinate is rejected; the next tier is attempted, and the
  original native mesh remains if all tiers reject.  No tolerance, snapping,
  source-corner insertion, topology repair, or `third_party/` modification was
  added.  Target-cell count remains subordinate to this shape gate.
- Twelve independent stochastic P4C cube runs pass the `8/8` corner contract;
  four runs took the longer retry path.  Focused source/surface/Phase-A/Phase-C/
  result-consistency validation reports `10 passed` both before and after the
  verified merge.
- The external fallback remains topology-nondeterministic.  Repository evidence
  shows fresh-process variation even with one thread and optimization disabled;
  fTetWild has multiple internal unordered/random worklists.  Those third-party
  sources were inspected only to localize behavior and were not edited.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-tet-p4c-source-gate-1-fee82ef1.bundle`,
  SHA-256 `f0ff062d50d287d72f0ab53e2064bbc10db59ce79596f9d9d3067121f4f8339f`.
  Worktree and branch were removed after bundle and merge verification.

### Gate re-evaluation

| Gate | Status | Cycle-15 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | Eight native targets previously build warning-clean on Ubuntu/GCC 13; platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused Tet suite passes; immutable-head full suite missing. |
| 4 Shape preservation | UNVERIFIED | Known P4C exact-corner acceptance hole is closed across 12 repeats; full corpus and exact surface-ledger integration remain. |
| 5 Mesh validity | UNVERIFIED | Source presence now gates P4C; complete strict-topology corpus missing. |
| 6 Cell count | FAIL | Deferred Tet target and Poly target following remain unresolved. |
| 7 Boundary layer | UNVERIFIED | Positive-layer corpus incomplete. |
| 8 Quality | UNVERIFIED | P4C quality rule retained behind source fidelity; complete matrix missing. |
| 9 Reproducibility | FAIL | External P4C point/tet topology hashes still vary across identical fresh processes. |
| 10 Robustness | UNVERIFIED | Source-loss candidate now fails closed; all-engine adverse matrix incomplete. |
| 11 Performance | UNVERIFIED | P4C retry cost is observable; frozen release budgets missing. |
| 12 Packaging | UNVERIFIED | Clean installer/artifact proof missing. |
| 13 License/provenance | UNVERIFIED | First-party gate only; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | Migration evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Profile evidence selects native-Poly face geometry: `_area_split`,
  `_flip_if_inward`, and `_is_on_plane` account for about `3.81 s` of an
  `8.93 s` representative dual conversion.  Design one C++23 ragged-face batch
  API with exact sequential arithmetic and face/owner/patch/output parity.

## Cycle 16 checkpoint -- 2026-07-30

### Native Poly face-geometry C++23 evidence

- `03ae22b4` batches polygon fan area, source-plane membership, and outward
  orientation in the first-party `native_polymesh` module.  Ragged faces are
  parsed once into flat offset/index storage; connectivity is validated before
  the GIL is released.  Numerical loops create no per-face NumPy gather/cross/
  signed-distance temporaries and retain strict sequential double arithmetic.
- A `20,000`-quad benchmark reports area classification `1.195620 s ->
  0.001883 s` (`635.03x`) and orientation `0.593882 s -> 0.001343 s`
  (`442.05x`).  Masks and on/off areas match exactly within the frozen
  `1e-12` arithmetic comparison.
- Deterministic sphere primal (`706` points / `1,913` tets): complete dual
  median `6.023769 s -> 3.473974 s` (`1.73x`).  Both routes emit `699` cells,
  `5,755` points, zero invalid stars/subtets, and identical full polyMesh
  SHA-256 snapshots.  Traced Python peak changes only `22.063 MiB ->
  21.937 MiB`; retained final nested face objects dominate that metric.
- Focused binding, topology, adverse-input, and sphere tests pass `52`; merged
  master batch passes `40`.  A separate full polyMesh-validity fixture exceeded
  `124 s`, so complete validation remains `UNVERIFIED` rather than inferred.
- The C++23 target builds warning-free with GCC 13.3.  No `third_party/` file,
  threshold, face order, owner/neighbour order, patch label, or provenance rule
  changed.  pybind11 and CGAL documentation were architectural references only;
  no external code was copied.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-poly-face-geometry-1-03ae22b4.bundle`,
  SHA-256 `939388db9bed304fd302e956cd177cb7e18ccd1a9b9508aa75ced01934017375`.
  Worktree, branch, and exact temporary build directory were removed.

### Gate re-evaluation

| Gate | Status | Cycle-16 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | Changed C++23 target builds warning-free on Ubuntu/GCC 13; supported platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/post-merge suites pass; a validity fixture timed out and immutable-head full suite is missing. |
| 4 Shape preservation | UNVERIFIED | Poly output is byte-identical; full corpus and P4C source-surface transaction remain. |
| 5 Mesh validity | UNVERIFIED | Sphere invalid star/subtet count is zero; complete strict-topology corpus missing. |
| 6 Cell count | FAIL | Deferred Tet target and Poly target following remain unresolved. |
| 7 Boundary layer | UNVERIFIED | Positive-layer corpus incomplete. |
| 8 Quality | UNVERIFIED | Poly topology-selection arithmetic is parity-locked; complete matrix missing. |
| 9 Reproducibility | FAIL | External P4C point/tet topology hashes still vary across identical fresh processes. |
| 10 Robustness | UNVERIFIED | Native connectivity rejection and adverse Poly fixtures pass; all-engine matrix incomplete. |
| 11 Performance | UNVERIFIED | Poly kernel/end-to-end gains pass card thresholds; frozen all-engine release budgets missing. |
| 12 Packaging | UNVERIFIED | Clean installer/artifact proof missing. |
| 13 License/provenance | UNVERIFIED | Independent first-party code; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Reuse the existing native Tet audit as a mandatory P4C topology prefilter,
  then recompute final source fidelity from the committed arrays.  Do not snap
  missing geometry, edit external fTetWild, or resume target-cell tuning.

## Cycle 17 checkpoint -- 2026-07-30

### Tet P4C native topology transaction evidence

- Eight raw cube P4C candidates reported zero open edges, non-manifold edges,
  non-manifold faces, duplicates, and degenerate tetrahedra through the C++23
  audit.  Their point/tet counts still varied, confirming that a clean sample
  does not make topology deterministic or remove the need for a transaction.
- `6ce92dd0` makes the existing first-party native audit mandatory for every
  P4C tier before quality/cell count can authorize replacement.  Empty/open,
  non-manifold, duplicate, or degenerate candidates fail closed and the next
  tier is tried.  Boundary component count is logged but not forced to one,
  because disconnected source components are valid inputs.
- No topology repair, snapping, threshold relaxation, external implementation,
  or `third_party/` edit was introduced.  The exact source-vertex gate remains
  earlier in the same acceptance conjunction.  Target-cell tuning remains
  deferred behind shape/topology.
- Focused source/topology tests report `14 passed`; eight independent P4C
  pipeline runs pass, with one retry; wider strict audit/result suites report
  `32 passed` before and after merge.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-tet-p4c-topology-gate-1-6ce92dd0.bundle`,
  SHA-256 `fbfd4f52a196c61ca1ea741673973c5d09d9b4266606b009830d260c10643fe1`.
  Worktree and branch were removed after verification.

### Gate re-evaluation

| Gate | Status | Cycle-17 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | Existing native audit target is warning-clean on Ubuntu/GCC 13; platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/post-merge Tet suites pass; immutable-head full suite missing. |
| 4 Shape preservation | UNVERIFIED | Exact source presence and candidate topology are gated; final P4C shape metrics remain stale and full ledger/corpus is missing. |
| 5 Mesh validity | UNVERIFIED | Invalid P4C topology now rejects before commit; complete strict all-engine corpus missing. |
| 6 Cell count | FAIL | Deferred Tet target and Poly target following remain unresolved. |
| 7 Boundary layer | UNVERIFIED | Positive-layer corpus incomplete. |
| 8 Quality | UNVERIFIED | Quality improvement cannot override source/topology gates; complete matrix missing. |
| 9 Reproducibility | FAIL | External P4C point/tet topology hashes still vary across identical fresh processes. |
| 10 Robustness | UNVERIFIED | Candidate topology fails closed; all-engine adverse matrix incomplete. |
| 11 Performance | UNVERIFIED | Native topology audit has prior 6.77x evidence; frozen release budgets missing. |
| 12 Packaging | UNVERIFIED | Clean installer/artifact proof missing. |
| 13 License/provenance | UNVERIFIED | Existing first-party audit reused; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | Acceptance evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Recompute plane coverage, plane area coverage, and Hausdorff evidence after
  the final P4C/post-validation arrays are fixed.  Do not trust or return the
  pre-fallback values when `_p4c_rewrote` is true.

## Cycle 18 checkpoint -- 2026-07-30

### Tet final-array shape evidence

- Baseline cube P4C returned grade `A` with plane coverage, plane-area coverage,
  and Hausdorff all `-1`; the shape pass had measured no final P4C array.  A
  non-skip path could instead retain values from a different pre-P4C mesh.
- `93d1972d` remeasures the final post-orientation/post-cleanup arrays after the
  writer and quality snapshot.  The direct result now exactly matches an
  independent remeasurement: plane coverage `1.0`, plane-area coverage `1.0`,
  relative Hausdorff `0.00045423924592147394`, `recomputed=true`.
- P4C grade A/B retains the existing realistic 5% relative Hausdorff limit and
  plane/area thresholds.  If remeasurement fails, all fidelity fields remain
  `-1`, a warning and error reason are recorded, and grade is `D`; stale values
  cannot create a success claim.  No mesh coordinate/connectivity is changed.
- Exact and displaced-corner evidence tests pass.  Focused pre-merge reports
  `9 passed`, wider strict shape/topology reports `7 passed`, and post-merge
  repeats `7 passed`.  No `third_party/` file changed.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-tet-final-shape-evidence-1-93d1972d.bundle`,
  SHA-256 `4450588858c62f78ecec2bdbcb74bd9a99ec8d0aa86c5e02a87106288dda9e63`.
  Worktree and branch were removed after verification.

### Gate re-evaluation

| Gate | Status | Cycle-18 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | No native target changed this card; supported platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/post-merge shape suites pass; immutable-head full suite missing. |
| 4 Shape preservation | UNVERIFIED | Known P4C final metric gap is closed on cube; exact full surface-ledger corpus remains. |
| 5 Mesh validity | UNVERIFIED | P4C topology gates remain; complete strict all-engine corpus missing. |
| 6 Cell count | FAIL | Deferred Tet target and Poly target following remain unresolved. |
| 7 Boundary layer | UNVERIFIED | Positive-layer corpus incomplete. |
| 8 Quality | UNVERIFIED | P4C grade now includes final shape evidence; complete matrix missing. |
| 9 Reproducibility | FAIL | External P4C point/tet topology hashes still vary across identical fresh processes. |
| 10 Robustness | UNVERIFIED | Shape evidence fails closed; all-engine adverse matrix incomplete. |
| 11 Performance | UNVERIFIED | Final evidence overhead is bounded on cube; frozen release budgets missing. |
| 12 Packaging | UNVERIFIED | Clean installer/artifact proof missing. |
| 13 License/provenance | UNVERIFIED | First-party measurement only; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | Final-evidence contract documented; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Port the profiled Poly star-validity audit (`1.865 s` representative cost)
  as a read-only C++23 CSR batch.  Preserve exact invalid cell/subtet counts,
  example ordering, and fail-closed behavior before considering mutable Poly
  topology work.

## Cycle 19 checkpoint -- 2026-07-30

### Native Poly star-validity C++23 evidence

- `be7fb679` ports the read-only Garimella face-edge-region validity audit to
  the first-party `native_polymesh` C++23 module.  Ragged faces and cell-face
  incidence use flat offset/index storage; owner/neighbour orientation is
  encoded in one signed 64-bit reference.  One reusable sorted vertex buffer
  replaces nested Python lists, copied/reversed faces, sets, NumPy gathers,
  cross products, and dot-product temporaries.
- Array and connectivity checks execute before GIL release.  The native loop
  accesses no Python object; bounded diagnostic dictionaries are created only
  after reacquiring the GIL.  Sequential double arithmetic, cell/face/edge
  traversal order, threshold, example order, and fail-closed counts remain.
- Representative final polyMesh (`17,746` points / `20,284` faces / `4,885`
  cells): median audit `2.452648831 s -> 0.003886981 s` (`630.99x`).  Native
  and Python both report `295` invalid cells and `729` invalid subtets.
- Six complete dual conversions, three per route, produced one identical
  complete polyMesh SHA-256 snapshot.  Focused binding/dual tests pass `4`;
  wider extension/no-drop tests pass `24`; non-sphere dual contracts pass
  `15`; post-merge native rebuild plus focused regression passes `25`.
- GCC 13.3 C++23 build is warning-free.  No tolerance, topology, geometry,
  provenance, public result, `third_party/` file, or external code changed.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-poly-star-validity-1-be7fb679.bundle`,
  SHA-256 `f966ebfc06303d2f41d3de615d37c11ddb63e1a68b597ff50327d712ea71bbee`.
  Worktree, branch, isolated build, and benchmark output were removed.

### Gate re-evaluation

| Gate | Status | Cycle-19 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | Changed C++23 target rebuilds warning-free on Ubuntu/GCC 13; supported platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/wider/post-merge Poly suites pass; immutable-head full suite missing. |
| 4 Shape preservation | UNVERIFIED | Six Poly outputs are byte-identical; full all-engine corpus remains. |
| 5 Mesh validity | UNVERIFIED | Native audit exactly preserves Python validity decisions; complete strict corpus missing. |
| 6 Cell count | FAIL | Tet target remains deferred behind topology; Poly target following remains unresolved. |
| 7 Boundary layer | UNVERIFIED | Positive-layer corpus incomplete. |
| 8 Quality | UNVERIFIED | Validity threshold and results unchanged; complete quality matrix missing. |
| 9 Reproducibility | FAIL | Poly parity holds; external P4C point/tet topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Malformed native connectivity rejects; all-engine adverse matrix incomplete. |
| 11 Performance | UNVERIFIED | Star kernel passes card threshold; frozen all-engine release budgets missing. |
| 12 Packaging | UNVERIFIED | Clean installer/artifact proof missing. |
| 13 License/provenance | UNVERIFIED | Independent first-party code; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Profile native surface self-intersection candidate generation.  Replace the
  quadratic broadcast and large-mesh approximate search with a deterministic
  first-party C++23 exact broad phase only if the existing Python narrow-phase
  result, candidate ordering, input geometry, and failure semantics remain.

## Cycle 20 checkpoint -- 2026-07-30

### Native surface exact AABB broad-phase evidence

- `853c6799` adds deterministic exact sweep-and-prune candidate generation to
  first-party C++23 `native_metrics`.  Flat AABB arrays, stable sweep order,
  widest-axis selection, canonical pairs, and final lexicographic sorting
  replace quadratic NumPy matrices in native builds.
- Public large-mesh detection no longer depends on centroid `k=16` nearest
  neighbours or turns a KDTree exception into a false-clean result.  Python
  fallback retains prior optional-extension behavior.
- Only broad phase moved.  Public repair still excludes every shared-vertex
  pair and uses its `1e-12` segment predicate.  Tet-private detection still
  excludes two-shared-vertex pairs and uses its `1e-10` interval predicate.
  Input coordinates, faces, narrow arithmetic, ordering, and reports remain.
- Sphere (`642` vertices / `1,280` faces): all `7,866` candidates match.
  Broad median `0.068847826 s -> 0.002956569 s` (`23.29x`); full public detect
  `0.081276332 s -> 0.015302687 s` (`5.31x`), `216` tests, zero intersections.
  Tet-private detect `0.741000228 s -> 0.663361401 s` (`1.12x`) with all
  `4,750` legacy detections unchanged.  Sparse `100,000` boxes take
  `0.001812726 s`, candidate count zero.
- Native ABI suite passes `39`; wider repair/native-tri suite passes `95`;
  post-merge native rebuild and focused suites pass `45`.  Dense random
  triangles now expose the exact-candidate Python narrow bottleneck and make
  the wider batch about `106 s`; next card ports narrow predicates separately.
- GCC 13.3 C++23 build is warning-free.  `third_party/`, geometry, thresholds,
  adjacency policy, and external dependencies remain unchanged.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-si-broadphase-1-853c6799.bundle`,
  SHA-256 `2bda871f487dc0b637d1f5f126ff1e7c9e93a73f03cd5e1c22b1fb15f311699d`.
  Worktree, branch, and isolated build were removed.

### Gate re-evaluation

| Gate | Status | Cycle-20 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | Changed native target rebuilds warning-free on Ubuntu/GCC 13; supported platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/wider/post-merge suites pass; immutable-head full suite missing. |
| 4 Shape preservation | UNVERIFIED | Native large-mesh broad phase is complete; full corpus evidence remains. |
| 5 Mesh validity | UNVERIFIED | Candidate completeness improved without narrow-policy change; strict corpus incomplete. |
| 6 Cell count | FAIL | Tet target remains deferred behind topology; Poly target remains unresolved. |
| 7 Boundary layer | UNVERIFIED | Positive-layer corpus incomplete. |
| 8 Quality | UNVERIFIED | No quality threshold changed; complete matrix missing. |
| 9 Reproducibility | FAIL | Broad output deterministic; external P4C point/tet topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Large elongated AABB candidates no longer missed in native builds; all-engine matrix incomplete. |
| 11 Performance | UNVERIFIED | Sparse/representative gains pass; dense exact narrow phase is the next measured bottleneck. |
| 12 Packaging | UNVERIFIED | CMake native extensions are not yet included in wheel evidence. |
| 13 License/provenance | UNVERIFIED | Independent first-party code; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | Migration evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Port public segment-based and Tet-private interval-based triangle narrow
  predicates as explicitly separate native modes.  Preserve each epsilon,
  adjacency exclusion, coplanar behavior, lexicographic pair order, and count.

## Cycle 21 checkpoint -- 2026-07-30

### Native surface triangle narrow-phase evidence

- `a29b322a` adds separate first-party C++23 public-segment and Tet-private
  interval predicates.  Their adjacency exclusions, `1e-12`/`1e-10` epsilon,
  coplanar rejection, candidate order, tested counts, and output order remain
  independent and match the existing Python oracles.
- Flat contiguous vertices, triangles, and candidates are validated before
  GIL release.  Fixed `std::array<double,3>` arithmetic removes per-pair set,
  gather, cross, norm, dot, and temporary-array allocations.  Python objects
  are created only after the native loop.
- Deterministic random corpus (`12,020` candidates): public `4,477` and private
  `4,899` hits match exactly.  Sphere public detection
  `0.082783340 s -> 0.001095325 s` (`75.58x`), preserving `216/0`
  tested/intersections.  Tet-private detection
  `0.749367660 s -> 0.001488219 s` (`503.53x`), preserving `4,750` pairs.
- The dense self-intersection suite returns from about `106 s` to `2.94 s`.
  Combined pre-merge validation passes `136`; post-merge native rebuild and
  metrics/self-intersection/surface-defect suites pass `75`.  Two unrelated
  existing all-NaN metric warnings remain.
- GCC 13.3 C++23 build is warning-free.  No fast-math, threshold, geometry,
  adjacency policy, `third_party/`, external code, or dependency changed.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-si-narrowphase-1-a29b322a.bundle`,
  SHA-256 `0f1b48d03ed5c634de1e1d9005450583b3a5cf0ea9a5aac2fb3e1da8755e3928`.
  Worktree, branch, and isolated build were removed.

### Gate re-evaluation

| Gate | Status | Cycle-21 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | Changed native target rebuilds warning-free on Ubuntu/GCC 13; supported platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/wider/post-merge suites pass; immutable-head full suite missing. |
| 4 Shape preservation | UNVERIFIED | Exact native candidate+narrow results preserve both Python contracts; full corpus remains. |
| 5 Mesh validity | UNVERIFIED | Intersection diagnostics are exact and fast in native builds; strict all-engine corpus incomplete. |
| 6 Cell count | FAIL | Tet target remains deferred behind topology; Poly target remains unresolved. |
| 7 Boundary layer | UNVERIFIED | Positive-layer collision corpus remains the next priority. |
| 8 Quality | UNVERIFIED | No quality threshold changed; complete matrix missing. |
| 9 Reproducibility | FAIL | Native intersection output deterministic; external P4C topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Dense and sparse native intersection paths pass; all-engine adverse matrix incomplete. |
| 11 Performance | UNVERIFIED | SI dense regression closed; frozen all-engine budgets missing. |
| 12 Packaging | UNVERIFIED | CMake native extensions are not yet included in wheel evidence. |
| 13 License/provenance | UNVERIFIED | Independent first-party code; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Profile boundary-layer ray/triangle collision distance.  Replace quadratic
  Python masks and the large-mesh skipped-collision path with an exact
  first-party `native_bl` kernel only under wall-shape/layer-count parity.

## Cycle 22 checkpoint -- 2026-07-30

### Native boundary-layer ray narrow-phase evidence

- `bacd281a` adds a first-party C++23 exhaustive nearest-positive-hit kernel to
  `native_bl`.  It preserves the Python oracle's `1e-12` determinant,
  barycentric, positive-distance, incident exclusion, triangle-order, and
  nearest-hit rules for finite input.  Non-finite native ABI input now fails
  validation instead of entering geometric arithmetic.
- Triangles are converted once to contiguous vertex/edge records.  The GIL is
  released for fixed-order ray/triangle traversal; stack-resident `Point3`
  arithmetic removes NumPy `(chunk,T,3)` temporaries.  The caller-owned dense
  incident mask remains explicit debt for the next indexed card.
- Deterministic `512`-ray / `2,048`-triangle corpus:
  `0.199042844 s -> 0.018527825 s` (`10.743x`), identical finite-hit mask and
  maximum absolute distance error `0`.
- Focused build and native/helper tests pass `54`; the post-merge boundary,
  narrow-gap, layer-state, BL0-routing, and topology set passes `92`.
  The wider set passes `173/174`; its sole poly-hybrid negative-volume failure
  reproduces unchanged on pre-card `master` (`1280` reported by the result
  object while the same checker log reports `0`) and is not a ray-kernel
  regression.
- GCC 13.3 C++23 build is warning-free.  Geometry, layer request semantics,
  epsilon, fast-math, parallel reduction, dependencies, and `third_party/`
  remain unchanged.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-bl-ray-kernel-1-bacd281a.bundle`,
  SHA-256 `0a0abfd374db02177dabc2e94353334cf155c70fe04207b4ed7317bca9f1b2e6`.
  Worktree, branch, and isolated build were removed.

### Gate re-evaluation

| Gate | Status | Cycle-22 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | Changed native target rebuilds warning-free on Ubuntu/GCC 13; supported platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/post-merge suites pass; baseline poly-hybrid checker defect and immutable-head full suite remain. |
| 4 Shape preservation | UNVERIFIED | Ray hit policy is parity-tested; full wall-envelope corpus remains. |
| 5 Mesh validity | FAIL | Baseline poly-hybrid result/log negative-volume disagreement is open; strict all-engine corpus incomplete. |
| 6 Cell count | FAIL | Tet target remains deferred behind topology; Poly target remains unresolved. |
| 7 Boundary layer | UNVERIFIED | BL0/positive-layer focused tests pass; >20k collision fail-open path remains. |
| 8 Quality | UNVERIFIED | No quality threshold changed; complete matrix missing. |
| 9 Reproducibility | FAIL | Native ray traversal deterministic; external P4C topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Finite ABI validation added; large-wall collision checking still skips. |
| 11 Performance | UNVERIFIED | Narrow kernel gains pass; dense incident mask and frozen all-engine budgets remain. |
| 12 Packaging | UNVERIFIED | CMake native extensions are not yet included in wheel evidence. |
| 13 License/provenance | UNVERIFIED | Independent first-party code; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Add an indexed native wall-collision entry point.  Exclude incident faces by
  vertex id inside C++, use conservative spatial pruning only when a finite
  search distance is supplied, preserve deterministic triangle order and the
  existing exact narrow predicate, and remove the dense `R x T` mask plus the
  `20,000`-triangle fail-open cap only after direct and downstream parity.

## Cycle 23 checkpoint -- 2026-07-30

### Indexed boundary-layer wall-collision evidence

- `de5fa5d7` adds `native_bl.indexed_wall_collision_distances`.  The C++23 ABI
  reads original points and integer face connectivity, excludes incident faces
  without Python masks, and returns nearest positive distance in wall-vertex
  order.  No triangle-coordinate or origin gather is required.
- Finite search uses an epsilon-expanded conservative centroid hash, accounts
  for non-unit direction norms, pads cell queries against quotient rounding,
  and falls back to exhaustive traversal on unsafe scale/overflow.  Candidate
  ids are sorted to original triangle order before the unchanged narrow test.
- The Python wrapper no longer allocates a full `R x T` incident mask, invokes
  SciPy per ray, or returns an unchecked empty result above `20,000` triangles.
  Its extension-absent path uses bounded batches.  Finite positive search now
  has the same capped meaning at every mesh size; unlimited search remains
  exhaustive.
- Sparse `4,096` rays / `20,001` triangles: `0.005826434 s`, all `4,096` hits
  exactly `1.0`; the previous code skipped this input.  Unlimited indexed
  `512 x 2,048` traversal is `1.181x` direct native cost because it performs
  mandatory incident-id checks; finite production traversal is the optimized
  path.
- Direct ABI/helper tests pass `60`; post-merge boundary topology, layer state,
  BL0 routing, and wrapper tests pass `98`.  Representative native-BL and
  numerical-quality tests pass `81` with the already reproduced poly-hybrid
  checker disagreement deselected.
- GCC 13.3 C++23 build is warning-free.  No geometry, connectivity, patch,
  requested layer, epsilon, fast-math, dependency, or `third_party/` change.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-bl-indexed-collision-1-de5fa5d7.bundle`,
  SHA-256 `6ab50458d8f6cb32a4fb9d95edcd0de17a0d427b6a37bb663f1937444b0c8bce`.
  Worktree, branch, and isolated build were removed.

### Gate re-evaluation

| Gate | Status | Cycle-23 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | Changed native target rebuilds warning-free on Ubuntu/GCC 13; supported platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused and representative suites pass; baseline poly-hybrid checker defect and immutable-head full suite remain. |
| 4 Shape preservation | UNVERIFIED | Wall collision search is conservative and wall coordinates unchanged; full corpus remains. |
| 5 Mesh validity | FAIL | Poly-hybrid result/log reports `1280/0` negative volumes for one run; authoritative audit must be repaired. |
| 6 Cell count | FAIL | Tet target remains deferred behind topology; Poly target remains unresolved. |
| 7 Boundary layer | UNVERIFIED | BL0/positive-layer focused tests pass and >20k skip is closed; full corpus remains. |
| 8 Quality | UNVERIFIED | No quality threshold changed; complete matrix missing. |
| 9 Reproducibility | FAIL | Native collision result deterministic; external P4C topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Large-wall collision no longer silently skips; all-engine adverse matrix incomplete. |
| 11 Performance | UNVERIFIED | Sparse large-wall gain passes; frozen all-engine budgets remain. |
| 12 Packaging | UNVERIFIED | CMake native extensions are not yet included in wheel evidence. |
| 13 License/provenance | UNVERIFIED | Independent first-party code; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Reproduce and isolate the `NativeMeshChecker` poly-hybrid negative-volume
  result/log disagreement.  Establish one authoritative oriented cell-volume
  oracle, then move its ragged face/cell traversal to first-party C++23 only if
  topology, sign, ordering, tolerance, and diagnostic parity are exact.

## Cycle 24 checkpoint -- 2026-07-30

### Native oriented-volume audit evidence

- `b99966a8` adds first-party C++23
  `native_metrics.compute_oriented_cell_volume_audit`.  It reuses flat face
  centres, raw normals, areas, cell centres, owner, and neighbour arrays; owner
  contributes with `+`, neighbour with `-`.  The GIL is released for contiguous
  loops and only two `O(C)` result arrays are allocated.
- The audit returns signed cell volumes plus absolute pyramid sums.  Report-only
  negative classification uses a fixed per-cell `1e-12 * absolute_sum`
  tolerance.  Existing absolute-pyramid quality magnitudes and release gates
  are unchanged pending corpus/OpenFOAM parity.
- Checker observability is now truthful: the final event reports effective,
  raw-pyramid, owner-heuristic, oriented-negative, and oriented-degenerate
  counts.  The previous result/log `1280/0` disagreement cannot recur silently.
- Unit cube outward/reversed values are `+1/-1`; a shared owner/neighbour face
  contributes positively to both cells; native/Python fallback arrays match.
  Three disconnected tets with one reversed cell report effective/raw/oriented
  `1/0/1`; the outward control reports `0/0/0`.
- The sphere hybrid's `1,280` negative result is confirmed by an all-incident
  signed audit and must not be threshold-relaxed.  A valid `PolyMeshWriter`
  single-tet remains positive after first BL, then produces exactly `4`
  negative prism cells after duplicate BL plus hybrid transition.  That is the
  next generation-path defect.
- Post-merge native metrics/checker/poly-transition validation passes `66`; two
  pre-existing all-NaN reduction warnings remain.
- GCC 13.3 C++23 build is warning-free.  No geometry, gate threshold,
  dependency, or `third_party/` change.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-checker-volume-audit-1-b99966a8.bundle`,
  SHA-256 `1f5f0dc6af744848e3d0da8b8894ab8454e4dc3d02533850deba84094e727ed3`.
  Worktree, branch, and isolated build were removed.

### Gate re-evaluation

| Gate | Status | Cycle-24 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | Changed native target rebuilds warning-free on Ubuntu/GCC 13; supported platform matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused audit/checker suites pass; invalid hybrid regression remains and immutable-head full suite is missing. |
| 4 Shape preservation | UNVERIFIED | Audit is read-only; full corpus remains. |
| 5 Mesh validity | FAIL | Signed audit confirms 4-cell minimal and 1,280-cell sphere hybrid inversions. |
| 6 Cell count | FAIL | Tet target remains deferred behind topology; Poly target remains unresolved. |
| 7 Boundary layer | FAIL | First BL is valid, but duplicate BL plus hybrid transition inverts prism cells. |
| 8 Quality | UNVERIFIED | Magnitude metrics unchanged; complete matrix missing. |
| 9 Reproducibility | FAIL | Audit deterministic; external P4C topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Invalid winding now observable; generation repair missing. |
| 11 Performance | UNVERIFIED | Flat native audit removes Python orchestration cost; frozen all-engine budgets remain. |
| 12 Packaging | UNVERIFIED | CMake native extensions are not yet included in wheel evidence. |
| 13 License/provenance | UNVERIFIED | Independent first-party code; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Use the valid `PolyMeshWriter` single-tet reproduction to stop a second BL
  insertion inside `poly_bl_transition`, or reject it before mutation if the
  existing hybrid already contains layers.  Then verify oriented volumes,
  wall envelope, requested/used layer report, connectivity, and exact rollback
  semantics before touching the owner-only checker gate.

## Cycle 25 checkpoint -- 2026-07-30

### Native boundary-layer lineage guard evidence

- `01f1a34e` adds a dedicated versioned `native_bl_state.json`.  It streams
  SHA-256 over the authoritative points/faces/owner/neighbour/boundary files,
  atomically records `pending` before mutation, and records `completed` plus
  output digest only after successful generation.  Optional Poly transition
  rewrites refresh the output digest.
- A current mesh matching a completed output is rejected before reads, backups,
  or writes.  A pending state is retryable only while the mesh exactly matches
  its primal digest.  All other lineage is ambiguous and fails closed.  No
  topology/prism/patch heuristic is accepted as provenance.
- `boundary layer = 0` now bypasses BLConfig, allocation, backup, generation,
  and dual conversion.  A pristine case is byte-identical before/after and
  reports requested/actual zero.  Zero cannot silently remove an existing
  layer stack.  Negative layer requests also return before writes.
- Correct single-tet one-call transition: requested/actual layers `2/2`, prism
  cells `8`, original four surface coordinates retained, negative volumes `0`.
  Direct-prelayer then transition and a second transition are both rejected
  with exact whole-case byte snapshots unchanged.
- Focused pre-merge validation passes `26` with three optional skips.  Post-
  merge validation passes `29`.  The wider BL batch passes `143`; its eight
  failures reproduce unchanged on pre-card master: three native-BL persistence
  defects and five tet-subdivision contract defects.  They are queued, not
  hidden or threshold-relaxed.
- No native geometry threshold, topology rule, dependency, external source, or
  `third_party/` file changed.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\poly-bl-duplicate-guard-1-01f1a34e.bundle`,
  SHA-256 `34139717d032f2faaa8b3521aad6428705561c1a5a29d422470c8036eb2b8386`.
  Worktree and branch were removed.

### Gate re-evaluation

| Gate | Status | Cycle-25 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | No native ABI changed in this card; supported build matrix remains incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/post-merge pass; eight baseline failures and immutable-head full suite remain. |
| 4 Shape preservation | UNVERIFIED | Single-tet surface coordinates preserved and duplicate mutation blocked; full corpus remains. |
| 5 Mesh validity | UNVERIFIED | Duplicate-BL minimal inversion is prevented; persistence defects and all-engine corpus remain. |
| 6 Cell count | FAIL | Tet target remains intentionally deferred behind topology/validity; Poly target unresolved. |
| 7 Boundary layer | UNVERIFIED | BL0 exact no-op and duplicate positive-layer rejection pass; full wall corpus remains. |
| 8 Quality | UNVERIFIED | No threshold changed; aspect/anti-invert accepted-point persistence is queued. |
| 9 Reproducibility | FAIL | Lineage hashes deterministic; external P4C topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Crash/partial-write lineage fails closed; adverse corpus incomplete. |
| 11 Performance | UNVERIFIED | Hashing uses bounded 1 MiB reads; frozen all-engine budgets remain. |
| 12 Packaging | UNVERIFIED | Native extensions and state artifact packaging evidence incomplete. |
| 13 License/provenance | UNVERIFIED | First-party provenance mechanism; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration and campaign ledger updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Repair the reproduced native-BL persistence defect: an accepted aspect-cap or
  anti-invert point set must be the single point set written, measured, hashed,
  and returned.  Preserve wall coordinates and fail closed if a post-write
  transform diverges.  Then resume C++23 porting at the remaining BL front-
  topology/allocation hot path.

## Cycle 26 checkpoint -- 2026-07-30

### Native boundary-layer final-state persistence evidence

- `2110b1eb` moves the sole polyMesh commit after every accepted point
  transform.  Final validity measurement, wall-envelope evidence, quality JSON,
  disk points, and lineage output hash now describe one `final_points` array.
- Aspect enforcement no longer changes memory after disk was written.  The
  persistence test observes exactly one point write, exact accepted/disk point
  parity, and result/JSON aspect metrics equal to a disk recomputation.
- Anti-invert scaling is applied with joint mode both disabled and enabled, and
  to original moved vertices plus all layer offsets.  Global/selective and
  joint-on/off tests all keep displacement at or below the injected `1e-3`
  geometric cap.
- A legacy minimum-thickness floor could increase both per-vertex and joint
  safety upper bounds.  That unsafe promotion is removed.  Selective mode uses
  exact safe ratios; homogeneous mode uses their minimum; joint scaling can
  only reduce them.
- Focused post-merge persistence/provenance/checker/transition validation passes
  `43`.  The wider native BL regression passes `172` in `153.71 s`.
- No surface point, topology contract, quality threshold, dependency, external
  source, or `third_party/` file changed.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-bl-persistence-1-2110b1eb.bundle`,
  SHA-256 `11ee2994d2f0ff492c28e6018e5578ed930ea1f39525c4d4e55f128ef10a7975`.
  Worktree and branch were removed.

### Gate re-evaluation

| Gate | Status | Cycle-26 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | No native ABI changed in this card; supported build matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused and wider BL suites pass; five baseline tet-subdivision contract failures and full suite remain. |
| 4 Shape preservation | UNVERIFIED | Final wall-envelope evidence now matches persisted geometry; full corpus remains. |
| 5 Mesh validity | UNVERIFIED | Safety caps cannot be weakened by floors and final geometry is measured; all-engine corpus remains. |
| 6 Cell count | FAIL | Tet target remains deferred behind topology/validity; Poly target unresolved. |
| 7 Boundary layer | UNVERIFIED | Persistence, BL0, duplicate guard, and focused positive layers pass; full corpus remains. |
| 8 Quality | UNVERIFIED | Aspect metrics now match disk; complete fixture matrix remains. |
| 9 Reproducibility | FAIL | Disk/result/state divergence closed; external P4C topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Joint/selective safety matrix passes; adverse corpus incomplete. |
| 11 Performance | UNVERIFIED | No measured regression; frozen all-engine budgets remain. |
| 12 Packaging | UNVERIFIED | Native extension wheel evidence incomplete. |
| 13 License/provenance | UNVERIFIED | First-party fix; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration and campaign ledger updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Port the `build_layer_front` compact summary path to first-party C++23 using
  flat sorted edge records and contiguous vertex/face data.  Preserve exact
  counts, first non-manifold edge, feature classification, deterministic order,
  wall topology, and full generate-native-BL polyMesh hashes.  Keep Python as
  parity oracle/fallback.

## Cycle 27 checkpoint -- 2026-07-30

### C++23 compact boundary-layer front summary evidence

- `67154481` adds first-party `native_bl.layer_front_summary`.  It consumes
  contiguous face ids, triangle connectivity, and points; validates the ABI;
  releases the GIL; and uses reserved flat edge and vertex-face records plus
  dense byte flags instead of Python dict/set/dataclass graphs.
- Edge grouping is canonical and deterministic.  Equal-edge references retain
  candidate-face order.  The first non-manifold edge remains lexicographically
  first and its incident face ids retain original order.  Feature cosine `0.9`
  and blocked-vertex semantics are unchanged.
- Complexity is `O(F log F + sum(d_v^2))` time and `O(F + V + E)` storage.  The
  degree-squared feature test is deliberately retained for exact oracle parity.
- Planar 45,000-triangle benchmark: Python `12.833594212 s`, native median
  `0.025557641 s`, `502.14x`.  Traced Python heap `85.27 -> 3.50 MiB`, `95.90%`
  reduction; C++ allocator memory is not included in this traced-heap metric.
  Counts match exactly: faces `45,000`, vertices `22,801`, edges `67,800`,
  boundary `600`, non-manifold `0`, feature `0`, blocked `600`.
- Open, cube-feature, shuffled/non-contiguous face id, ordered non-manifold,
  empty, degenerate, seeded soup, invalid ABI, extension-disabled fallback, and
  full generated polyMesh five-file byte parity pass.  Wider production BL
  validation passes `124`; post-merge focused validation passes `26`.
- `f255ca78` fixes extension search order found during post-merge verification:
  explicit `AUTOTESSELL_EXT_BUILD_DIR` now outranks a stale repo-local build.
  This closes a false-skip risk in isolated native ABI validation.
- GCC 13.3 strict C++23 build is warning-free; compiler extensions are disabled.
  No topology threshold, wall geometry, dependency, external source, or
  `third_party/` file changed.
- Full two-commit bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-bl-front-summary-2-f255ca78.bundle`,
  SHA-256 `b1e1c6b55200218ec0393ccf9c14693465b3cc1fcc69fb744910fa900569c090`.
  Worktree, branch, and isolated builds were removed.

### Gate re-evaluation

| Gate | Status | Cycle-27 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | GCC 13.3 strict C++23 target warning-free; supported OS/compiler matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Native/fallback/wider BL suites pass; immutable-head full suite remains. |
| 4 Shape preservation | UNVERIFIED | Generated polyMesh byte parity passes; full corpus remains. |
| 5 Mesh validity | UNVERIFIED | Exact non-manifold rejection preserved; all-engine corpus remains. |
| 6 Cell count | FAIL | Tet target remains deferred behind topology/validity; Poly target unresolved. |
| 7 Boundary layer | UNVERIFIED | Front topology, BL0, provenance, persistence pass; full wall corpus remains. |
| 8 Quality | UNVERIFIED | Feature/blocked classification parity passes; complete fixture matrix remains. |
| 9 Reproducibility | FAIL | Edge and face order deterministic; external P4C topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Invalid ABI and non-manifold fixtures fail explicitly; adverse corpus incomplete. |
| 11 Performance | UNVERIFIED | Front-summary bottleneck closed with 502.14x measured gain; frozen all-engine budgets remain. |
| 12 Packaging | UNVERIFIED | Explicit build override fixed; wheel/native artifact evidence incomplete. |
| 13 License/provenance | UNVERIFIED | Independent first-party C++23; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 evidence and loader contract documented; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Port the remaining `_build_edge_to_wall_faces` production cache to C++23 or
  fuse it with front-summary output so the same `3F` edge scan is not repeated.
  Preserve sorted edge keys, owner-face order, layer-side connectivity, and full
  polyMesh byte hashes; reject the card if an extra Python materialization erases
  the end-to-end gain.
