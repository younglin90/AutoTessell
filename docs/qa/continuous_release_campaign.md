# Native Engine Continuous Release Campaign

## Campaign ledger

- campaign_id: `native-release-20260730`
- state: `CAMPAIGN_ACTIVE`
- cycle: `9`
- policy: `shape-preservation > validity > provenance > boundary layers > cell count > quality > reproducibility > performance`
- last_verified_master: `4246cf6f478a69290264862e967a968c2c8124bb`
- allowed_to_stop: `false`
- next_action: `Rebase the protected Tet worktree onto current master, then run TET-STRICT-TOPOLOGY-CORPUS-PROBE-1 with target count diagnostic-only.`

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
