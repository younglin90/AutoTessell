# Native Engine Continuous Release Campaign

## Campaign ledger

- campaign_id: `native-release-20260730`
- state: `CAMPAIGN_ACTIVE`
- cycle: `92`
- policy: `shape-preservation > validity > provenance > boundary layers > cell count > quality > reproducibility > performance`
- last_verified_master: `30a77f168056b95376e64e7b1df87dc1cbd73b84`
- allowed_to_stop: `false`
- next_action: `Develop only a source-locked bounded local 2↔3/3↔2 strict transaction for same-side Tet debt.`

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

## Cycle 28 checkpoint -- 2026-07-30

### C++23 fused boundary-layer edge adjacency evidence

- `5c619751` extends the existing native front scan with a contiguous `(F,3)`
  adjacent-face array.  Each edge reference retains candidate-face order and
  local edge index.  Boundary slots are `-1`; shared slots select the first
  different face id in the same order as the Python oracle.
- The production prism writer now indexes adjacency directly.  It no longer
  performs the second NumPy lexsort, creates six edge arrays, materializes tuple
  keys, stores Python face lists, or probes a Python dictionary in the layer
  loop.  The extension-absent fallback retains the prior map path.
- Adjacency grouping is linear after the summary's existing edge sort.  Overall
  complexity remains `O(F log F + sum(d_v^2))` time and `O(F + V + E)` space.
- Planar 80,000-triangle benchmark: Python edge dictionary `1.958444371 s`,
  `69.42 MiB` traced Python heap.  Complete fused native summary+adjacency median
  `0.047959233 s`, `40.84x`; returned adjacency is `1.83 MiB` contiguous storage.
  Every face/local-edge neighbor matches exactly.
- Focused post-merge topology/provenance validation passes `26`.  Wider BL
  writer validation passes `125`; generated five-file polyMesh byte parity is
  retained.  GCC 13.3 strict C++23 build is warning-free.
- No wall geometry, topology threshold, patch semantics, dependency, external
  source, or `third_party/` file changed.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-bl-edge-adjacency-1-5c619751.bundle`,
  SHA-256 `41dcdae73b010dfad4693440833992c6775f4ddfa0c523ca17264c9588632d89`.
  Worktree, branch, and isolated builds were removed.

### Gate re-evaluation

| Gate | Status | Cycle-28 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | GCC 13.3 strict C++23 target warning-free; platform/compiler matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/wider BL suites pass; immutable-head full suite remains. |
| 4 Shape preservation | UNVERIFIED | Full generated polyMesh byte parity passes; full corpus remains. |
| 5 Mesh validity | UNVERIFIED | Non-manifold hard rejection and connectivity ordering preserved; all-engine corpus remains. |
| 6 Cell count | FAIL | Tet target remains deferred behind topology/validity; Poly target unresolved. |
| 7 Boundary layer | UNVERIFIED | Duplicate edge scan removed with exact layer-side connectivity; full wall corpus remains. |
| 8 Quality | UNVERIFIED | No quality rule changed; complete fixture matrix remains. |
| 9 Reproducibility | FAIL | Local-edge adjacency deterministic; external P4C topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Boundary/non-manifold/duplicate ownership parity passes; adverse corpus incomplete. |
| 11 Performance | UNVERIFIED | Edge-map bottleneck closed with 40.84x measured gain; frozen all-engine budgets remain. |
| 12 Packaging | UNVERIFIED | Native wheel/artifact evidence incomplete. |
| 13 License/provenance | UNVERIFIED | Independent first-party C++23; GPL/no-third-party policy held; inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | C++23 migration and campaign evidence updated; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Rotate away from BL to the highest-impact remaining Tet or Poly Python hot
  kernel that consumes already-flat arrays.  Keep strict topology/shape and
  provenance ahead of target-cell count; require end-to-end gain, exact hashes,
  and a warning-free first-party C++23 ABI before integration.

## Cycle 29 checkpoint -- 2026-07-30

### C++23 strict Tet CDT constraint audit

- `7fcc1f91` replaces the Python tuple/set and packed-integer CDT audit hot path
  with first-party `native_tet_predicates.audit_cdt_constraints`.  Flat canonical
  edge/face records are sorted, uniqued, and merged without packed keys, removing
  sparse `int64` overflow from the strict topology decision.
- The direct ABI accepts exact C-contiguous `int64` `(F,3)` and `(T,4)` arrays,
  releases the GIL only after validation, and returns deterministic
  lexicographically sorted missing edges.  Negative, fractional, object, and
  overflowing unsigned provenance indices fail closed.  The Python oracle and
  extension-absent fallback remain independent and exact.
- The `F=2,536`, `T=9,859` audit changes from the frozen `61.982 ms` baseline to
  native median `6.101 ms` (`10.16x`); the overflow-safe Python oracle median is
  `149.271 ms`, making the native transaction `24.46x` faster.  GCC 13.3 strict
  C++23 builds warning-free.
- Focused validation passes `28`; post-merge isolated-build validation passes
  `25` with the known generated-cube L1 assertion deselected.  That assertion
  fails identically on immutable pre-card `master` (`present_edges=0`) and no
  topology threshold was relaxed.
- `615ee589` makes the direct extension test use the shared loader so
  `AUTOTESSELL_EXT_BUILD_DIR` outranks a stale repo-local module.  No algorithm
  changed.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-tet-cdt-audit-2-615ee589.bundle`,
  SHA-256 `8016976d852512f04a2258bcce18972b06e3b6cd1d49b5dd452b71dda4a6801c`.
  Worktree, branch, and isolated builds were removed.

### C++23 Poly Garimella dual-point kernel

- `e6149462` adds first-party `native_polymesh.compute_tet_dual_points` with a
  strict contiguous `float64`/`int64` ABI.  Each tetrahedron uses fixed stack
  arrays and a partial-pivot `3x3` solve, allocates no heap storage in the inner
  loop, and emits a contiguous point array plus an explicit `uint8` placement
  status census.
- Backend-independent preflight makes native and Python paths reject the same
  non-finite points and negative, out-of-range, or repeated indices.  The public
  ndarray API is unchanged.  Primal points and tetrahedra are read-only; the
  full classified-dual topology, owner/neighbour, patch, and provenance outputs
  match the Python fallback.
- On `50,000` tetrahedra, Python median is `2.826957 s` and native median is
  `0.004894 s` (`577.586x`).  Quantized `1e-9` provenance keys and all placement
  statuses match exactly.  Random, well-centered, clipped, singular,
  near-singular, `1e100` scale, empty, invalid, non-contiguous, and three-run
  deterministic fixtures pass.
- GCC 13.3 strict C++23 builds warning-free.  Focused/native-extension validation
  passes `23`; post-merge isolated-build validation also passes `23`.  A combined
  heavy sphere suite timed out after `184 s` without a failing node id and remains
  `UNVERIFIED`, not PASS.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-poly-dual-points-1-e6149462.bundle`,
  SHA-256 `a635e614468d1b5123df61aea528dc96022280572f556d195267291480c0a893`.
  Worktree, branch, and isolated builds were removed.

### Cycle-29 gate re-evaluation

| Gate | Status | Cycle-29 evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | One primary worktree, `master` only, clean before this ledger update; no `third_party/` diff. |
| 2 Build | UNVERIFIED | Tet and Poly targets build warning-free with GCC 13.3 strict C++23; supported matrix incomplete. |
| 3 Automated tests | UNVERIFIED | Both focused suites pass; known Tet baseline failure and timed-out heavy Poly/full suite remain. |
| 4 Shape preservation | UNVERIFIED | Strict CDT counts and classified Poly topology/provenance parity pass; full corpus remains. |
| 5 Mesh validity | UNVERIFIED | No geometry mutation was introduced; all-engine validity corpus remains. |
| 6 Cell count | FAIL | Deferred behind topology/validity as directed; Poly target remains unresolved. |
| 7 Boundary layer | UNVERIFIED | No BL contract changed; full wall corpus remains. |
| 8 Quality | UNVERIFIED | Dual placement parity passes; complete fixture matrix remains. |
| 9 Reproducibility | FAIL | Both new kernels are deterministic for three runs; external P4C topology hashes still vary. |
| 10 Robustness | UNVERIFIED | Sparse-index and degenerate dual fixtures pass; adverse corpus incomplete. |
| 11 Performance | UNVERIFIED | CDT `10.16x` and Poly dual `577.586x`; frozen all-engine budgets remain. |
| 12 Packaging | FAIL | Audit found that current wheel/installer contains none of the first-party native extensions. |
| 13 License/provenance | UNVERIFIED | Independent first-party C++23; GPL/no-third-party policy held; distribution inventory incomplete. |
| 14 Documentation/operations | UNVERIFIED | Cycle evidence recorded; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Add an isolated scikit-build-core distribution profile that builds and installs
  exactly the eight first-party native extensions while forcing cinolib,
  robusthex, fTetWild, and cfMesh adapters OFF.  Move unconditional Eigen lookup
  out of the first-party-only path, add exact install rules, and validate a fresh
  wheel outside the repository with real kernel smoke tests and forbidden-adapter
  scans.  Keep the current GPL distribution metadata and matching source archive.

## Cycle 30 checkpoint -- 2026-07-30

### First-party native wheel and corresponding-source profile

- `3a0f1818` replaces the pure-Python setuptools build with scikit-build-core
  `1.x` and an explicit first-party distribution profile.  It compiles and
  installs exactly `native_metrics`, `native_bl`, `native_polymesh`,
  `native_snap`, `native_surface_padding`, `native_hex_quality`,
  `native_tet_predicates`, and `native_tet_qopt`.
- When the distribution profile is active, cinolib, robusthex, fTetWild, and
  cfMesh adapters are forcibly OFF.  Their source and binaries are forbidden in
  both wheel and source archive.  Unconditional Eigen discovery was removed from
  the first-party-only path; the three legacy adapter consumers retain their
  existing conditional requirement.
- All eight targets use strict C++23 with compiler extensions disabled and the
  wheel profile treats warnings as errors.  GCC 13.3 builds all eight with zero
  warnings.  A range-loop structured binding in `native_surface_padding` was
  changed to a const reference, removing one copy and the only strict warning.
- `native_tet_predicates` now declares Boost.Multiprecision explicitly as a
  build-only BSL-1.0 header dependency.  The wheel's dynamic dependency closure
  contains no Boost runtime library; Shewchuk `predicates.c` remains project-local
  public-domain source compiled with `-fno-fast-math`.
- The source archive contains all eight binding sources, CMake configuration,
  Python sources, Shewchuk source, GPL `LICENSE`/`NOTICE`, and the distribution
  inventory/provenance records.  It contains no adapter source, `third_party/`,
  compiled binary, build/cache data, or worktree snapshot.
- `215cb01c` adopts PEP 639 `GPL-3.0-or-later` metadata and restricts license-file
  discovery to the root `LICENSE` and `NOTICE`.  This closes leakage of ignored
  external-checkout `AlgoHex/LICENSE` and `voro/LICENSE` into a locally built
  source archive.
- Release artifacts must be built from a fresh tracked snapshot.  A dirty source
  directory containing ignored external checkouts can still influence backend
  license discovery; it is not accepted as release evidence.  The post-merge
  evidence below was built from `git archive` of `master` commit `5ffcae3c`.
- Post-merge fresh-snapshot wheel:
  `auto_tessell-1.0.0-cp312-cp312-linux_x86_64.whl`, `3,060,754` bytes,
  SHA-256 `073fcaefcd14dfaf76e1ba414ff0974edfda32a07d99a902667517a7d93a65e4`.
  It contains exactly eight native extensions and zero forbidden adapter module.
- Matching source archive: `auto_tessell-1.0.0.tar.gz`, `10,245,552` bytes,
  SHA-256 `6a2764547832a638d0feac4dd0fd626cea7ee09ef7b0f20c6320525a923ebde8`.
  The committed artifact verifier reports `modules=8 forbidden=0 source=present`.
- A fresh Python 3.12 environment outside the repository installed the wheel and
  all declared dependencies.  Eight real native kernel calls pass and `pip check`
  reports no broken requirements.  Static packaging tests pass `3` post-merge.
- Full-history bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-wheel-first-party-2-215cb01c.bundle`,
  SHA-256 `fc2794466ed4bdaa4f73fdb4cc495b811c86de08aa7cfaf576111bcbb85d81a7`.
  Worktree, branch, fresh environment, and generated artifacts were removed.

### Cycle-30 gate re-evaluation

| Gate | Status | Cycle-30 evidence / next evidence |
|---|---|---|
| 1 Repository | FAIL | `master` is clean and research worktrees are gone, but tracked `installer/dist/AutoTessell-1.2.0-Setup.exe` is an unresolved build artifact. |
| 2 Build | UNVERIFIED | Linux GCC 13.3 strict C++23 first-party matrix passes; Windows and declared compiler matrix remain. |
| 3 Automated tests | UNVERIFIED | Packaging contract and eight-kernel smoke pass; full suite and known engine failures remain. |
| 4 Shape preservation | UNVERIFIED | Packaging does not change geometry; full corpus remains. |
| 5 Mesh validity | UNVERIFIED | Packaging does not change generated meshes; all-engine corpus remains. |
| 6 Cell count | FAIL | Tet target remains deferred behind topology/validity; Poly target unresolved. |
| 7 Boundary layer | UNVERIFIED | Installed native BL kernel smoke passes; full wall corpus remains. |
| 8 Quality | UNVERIFIED | Installed metrics/hex-quality/qopt smoke passes; complete fixture matrix remains. |
| 9 Reproducibility | FAIL | Source archive hash reproduced, but independently built wheel bytes differ; deterministic binary build remains. |
| 10 Robustness | UNVERIFIED | Fresh-install kernel smoke passes; adverse mesh corpus incomplete. |
| 11 Performance | UNVERIFIED | Native extensions are no longer silently omitted from Linux wheel; frozen benchmark budgets remain. |
| 12 Packaging | FAIL | Linux first-party wheel subgate passes; Windows wheel, repair/audit, installer, uninstall/reinstall, and UI workflow remain. |
| 13 License/provenance | UNVERIFIED | GPL/PEP639/source mapping improved; dependency inventory still has unresolved release assertions. |
| 14 Documentation/operations | UNVERIFIED | Native wheel profile documented; version/release/rollback operations remain inconsistent. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Continue C++23 engine rotation with the highest-impact Hex and Tri/Quad flat-
  array Python kernels while a common release lane audits version identity and
  unresolved dependency licenses.  Do not delete the tracked installer binary
  without a separate reviewed artifact-retention decision.  Keep shape,
  topology, and provenance ahead of target-cell count.

## Cycle 31 checkpoint -- 2026-07-31

### Single-source release identity

- `e8964a42` makes `core/version.py` the canonical `1.2.0` source for runtime,
  API, wheel/sdist metadata, Qt, Electron, Godot, frontend, and installer
  declarations.  PEP 621 metadata uses the scikit-build-core regex provider;
  local Python fallback constants were removed.
- A fresh tracked snapshot produced `auto_tessell-1.2.0` wheel and source
  archive.  The wheel contains exactly eight first-party native modules; all
  eight installed kernels smoke-tested.  Independent wheel bytes still differ,
  so binary reproducibility remains open.
- Version focused/packaging validation passes `12` post-merge.  Bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\release-version-single-source-1-9ccca2b7.bundle`,
  SHA-256 `e758250b30119984ff2f2f7bb0d3f9688c48121c60e34071daa3297c2d1259f8`.

### Exact Python-wheel dependency evidence

- `779f6b3c` records exact PyPI wheel URL, SHA-256, METADATA, declared license
  fields, and license-file hashes for nine direct runtime and two direct build
  dependencies.  PEP 639 expressions are copied only when present; legacy
  metadata remains unnormalized and no SPDX expression is inferred.
- `python-wheel-core --require-resolved` passes.  Global
  `--require-resolved` truthfully fails with eight remaining CMake/external/
  Boost rows.  Focused post-merge validation passes `16`.
- Bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\license-python-wheel-evidence-1-779f6b3c.bundle`,
  SHA-256 `5ef73650e4eb2922ead76ee0cbeaff369e77da8d39c489a28f593f84f0066e49`.

### Native Hex C++23 feature-edge extraction

- `99f8af8c` ports feature-edge classification to first-party C++23 using one
  contiguous `3F` edge-record array, one normal array, deterministic sort/run
  scans, exact output reservation, and GIL release after strict ABI validation.
  Python dictionaries, per-edge lists, and scalar NumPy dispatch leave the hot
  path.  Surface coordinates, feature threshold, ordering, weights, topology,
  and provenance are unchanged byte-for-byte.
- On `115,200` triangles, Python median `0.829629 s` becomes native
  `0.020881 s` (`39.73x`); maximum RSS changes `169,448 -> 73,220 KiB`
  (`56.79%` lower).  Full Hex/snap validation passes `200`, with `9` existing
  skips; strict GCC 13.3 C++23 build reports zero warnings.
- Advisor verification found a stale repo-local extension outranking
  `AUTOTESSELL_EXT_BUILD_DIR`.  `21667a07` loads the explicit binary through a
  path-stable package alias even after a single-phase extension was cached;
  `a6fc5dec` makes an existing explicit candidate fail closed on import error.
  Post-merge focused validation passes `23`; advisor benchmark remains exact at
  `39.51x`.  Promotion is `L1_PASS / EXPERIMENTAL_KEEP`.
- Final bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-hex-feature-edges-1-a6fc5dec-v3.bundle`,
  SHA-256 `2c3ba7b9bca3d362c50bf1db26aa3a6bc5b5d4a92132b5b6c3e12edd77495d32`.

### Native Tri/Quad C++23 bulk pair-quality selection

- `0b2a0ab5` fuses oriented-quad construction, scaled-Jacobian/aspect/warpage
  evaluation, stable candidate ordering, and greedy face consumption into
  `native_metrics.select_quad_pairs`.  Exact contiguous `float64`/`int64`
  inputs, contiguous POD candidates, a dense consumed-face byte vector, strict
  output provenance checks, and GIL release replace per-candidate NumPy arrays
  and Python objects.  Python remains the independent fallback/oracle.
- On `7,200` triangles and `10,680` candidate pairs, kernel median changes
  `2.090906 -> 0.001536 s` (`1361.13x`); public route changes
  `2.294814 -> 0.228755 s` (`10.03x`); traced Python heap falls `95.95%`.
  Topology/order/classification match exactly and quality differs by at most
  `1e-14`.  Derived non-finite quality from huge finite coordinates is rejected.
- Focused validation passes `51`; wider related regression passes `134`;
  advisor post-merge validation passes `38`.  GCC 13.3 strict C++23 reports zero
  warnings.  No permanent quality threshold or routing default changed.
- Bundle:
  `D:\AutoTessell-cleanup-backup-20260730\research-bundles\native-triquad-pair-quality-1-0b2a0ab5.bundle`,
  SHA-256 `7c5bc29dd9df3951314117243551c9a566ac6544cad8f3523c300a7b85d8b07d`.

### Cycle-31 gate re-evaluation

| Gate | Status | Cycle-31 evidence / next evidence |
|---|---|---|
| 1 Repository | FAIL | `master` is clean with one worktree and one branch, but tracked `installer/dist/AutoTessell-1.2.0-Setup.exe` remains an unresolved build artifact. |
| 2 Build | UNVERIFIED | New Hex and Tri/Quad targets pass strict GCC 13.3 C++23; supported OS/compiler matrix remains incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/wider engine and packaging suites pass; immutable-head full suite remains. |
| 4 Shape preservation | UNVERIFIED | Feature segments and Tri/Quad connectivity are exact against Python oracles; full corpus remains. |
| 5 Mesh validity | UNVERIFIED | Non-finite derived quad quality now fails closed; all-engine validity corpus remains. |
| 6 Cell count | FAIL | Tet target remains deferred behind strict topology; Poly target response remains unresolved. |
| 7 Boundary layer | UNVERIFIED | No boundary-layer contract changed; full wall corpus remains. |
| 8 Quality | UNVERIFIED | Tri/Quad metric and classification parity pass; complete fixture matrix remains. |
| 9 Reproducibility | FAIL | New kernels are deterministic, but independently built wheel bytes and external P4C topology hashes still differ. |
| 10 Robustness | UNVERIFIED | Strict input/output ABI, huge-finite rejection, stale-extension override, and explicit-load failure pass; adverse corpus remains. |
| 11 Performance | UNVERIFIED | Hex `39.73x` and Tri/Quad public `10.03x` pass card targets; frozen all-engine budgets remain. |
| 12 Packaging | FAIL | Version identity and source evidence improved; Windows wheel/installer/UI/uninstall matrix remains. |
| 13 License/provenance | UNVERIFIED | Python core profile resolves 11 exact artifacts; global inventory still reports eight unresolved rows. |
| 14 Documentation/operations | UNVERIFIED | Version checker and research evidence improved; release/rollback operations remain incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Execute the Cycle-32 Tet strict-topology and Poly target-control cards selected
  by the parallel audit.  Tet target count stays deferred until topology and
  validity are truthful.  Do not weaken exact surface, provenance, orientation,
  or positive-volume gates.

## Cycle 32 checkpoint -- 2026-07-31

### Native build identity and ABI evidence

- `9eda50a2` merges a tracked exact public-symbol contract for all eight
  first-party native modules and a standalone fail-closed manifest generator and
  verifier.  Evidence records source identity, contract and binding-source
  hashes, binary hashes, Python SOABI, compiler identity, and C++23 level.
- The stale repository build now fails deterministically and names five missing
  symbols.  A clean GCC 13.3 C++23 build passes `8/8`; the prior missing-kernel
  fixture changes from `34 passed, 2 failed, 21 skipped` to `57 passed`.
- A no-Git source archive derives a content-addressed `archive:sha256` identity.
  A normal extracted-sdist wheel build, external install, eight real kernel
  smokes, and artifact verification pass without a caller-invented identity.
- Bundle: `native-build-evidence-manifest-1-41417ee5.bundle`, SHA-256
  `3ba661273b6803318aac686c4f51484ec2103fe0900d877437f65ec37abdb6a9`.

### Tet source-component bijection

- `364d0b68` merges the first-party C++23 source-to-boundary component audit.
  Exact source-coordinate provenance is recovered independently of candidate
  point order; flat sorted face/edge records and contiguous disjoint sets replace
  Python dictionaries on the native path.
- Exact 1, 2, and 5 component fixtures pass.  Lost, merged, split, unanchored,
  interiorized, ambiguous, and malformed-native cases fail closed.  The cylinder
  remains `1495` cells and `353` points with exact pre-card point/tet hashes.
- A 1,000-component benchmark is `1.781 ms` native versus `52.000 ms` Python
  (`29.19x`).  Advisor isolated C++23 build and focused post-merge checks pass.
- Bundle: `native-tet-component-bijection-1-61d91e44.bundle`, SHA-256
  `6d02384047324eeb7719b39fe805218fc3b1ce54d9fc7a99e099b61ee9bf876d`.

### Poly residual-star refusal

- `3534c748` prevents a residual star-invalid dual from falling through to the
  writer after both Garimella and centroid candidates fail the existing signed
  subtet gate.  A frozen 15-point/40-tet cube changes from `3/3` false successes
  and five artifacts per run to `0/3` false successes and zero artifacts.
- The valid classified bipyramid retains all five exact file hashes and
  `source_high:wall` / `source_low:patch` provenance.  Focused isolated-native
  validation passes `20`; long Poly corpus runs timed out and remain unverified.
- Bundle: `native-poly-star-fail-closed-1-54a3dcc3-v2.bundle`, SHA-256
  `58741841b47eb7f5aa5b624e3ce978961c4a55a7f624bde594049d1b174f4604`.

## Cycle 33 checkpoint -- 2026-07-31

### Hex writer strict topology

- `dbc41b40` makes the native-Hex writer use the existing C++23 topology audit
  in strict mode.  Collapsed cells and faces owned by three or more cells now
  fail before any polyMesh artifact is created instead of silently dropping or
  truncating topology.
- Valid owner/neighbour/connectivity bytes are exact for three runs.  Full Hex
  validation passes `182` with `9` existing skips.  An 8,000-cell benchmark
  changes `0.232136 -> 0.238589 s` (`+2.78%`), within the declared card budget.
- Bundle: `native-hex-strict-topology-1-39264bfe.bundle`, SHA-256
  `a3d98bc13c27c90cc378e35637f6cf6c057bc9ffb3aa6a44a5fc130e06b478e4`.

### Tri/Quad curvature sizing C++23 kernel

- `b718af05` ports Dunyach curvature sizing to
  `native_metrics.estimate_triangle_curvature_sizing`: contiguous face normals,
  `3F` edge records, deterministic sort/run incidence, stable accumulation, and
  strict C-contiguous `float64`/`int64` ABI.  Python remains the oracle/fallback.
- On `67,600` vertices and `134,162` faces, median time changes
  `5.427370 -> 0.058734 s` (`92.41x`) with exact output SHA.  Cube transaction
  reports, coordinates, connectivity, and hashes remain exact.  Wider validation
  passes `146`; advisor isolated-native validation passes `32`.
- Bundle: `native-triquad-curvature-sizing-1-bbe2fec5-v2.bundle`, SHA-256
  `8b159247aa18fd2eac7a362f5d2a0435a95222cb698b83c96373bcae4436734d`.

### Poly primal conformity C++23 audit

- `d56dd3ae` adds `native_polymesh.audit_tet_primal_conformity`, using flat
  canonical tetrahedron and face records with deterministic sort/run scans.
  Duplicate canonical tetrahedra and faces with more than two owners fail before
  dual construction; negative orientation remains diagnostic rather than an
  over-strict rejection.
- A three-owner primal changes from `3/3` false successes and five artifacts to
  zero false successes/artifacts.  Valid bipyramid bytes and patch provenance are
  exact.  A 50,000-tet audit changes `0.435978 -> 0.011680 s` (`37.33x`).
- Bundle: `native-poly-primal-conformity-1-2cd713a5-v2.bundle`, SHA-256
  `2706304a346d948ab82ce474247b5d0ca5b459637f5f48c9630d1aebbcaa83e6`.

### Source-aware Tet topology and roundoff-safe exact provenance

- `a1c15a1d` redefines local Tet manifold validity to allow any positive number
  of closed components, while every production P4C, fTetWild, and final-result
  acceptance uses a composite local-topology plus exact source-component
  certificate.  Open, non-manifold, duplicate, degenerate, lost, merged, split,
  or invented components still fail closed.
- The Poly sphere cross-lane regression was traced to `4.63e-18..1.57e-16`
  coordinate roundoff, not lost topology: all 42 source-prefix ids remained on
  the boundary and boundary keys/area were unchanged.  Native-prefix points are
  restored bitwise only after boundary-membership proof and a finite
  scale-relative machine-roundoff cap.  Reordered P4C output, meaningful motion,
  interiorized vertices, cap overflow, and ambiguous provenance are not repaired.
- Signed zero, subnormal/tiny scale, huge finite scale, and warnings-as-errors
  cases are covered.  Post-merge Tet/Poly focused validation passes `41` with one
  unavailable-vendor skip.
- Bundle: `native-tet-source-topology-cycle33-v2-7d5d513c.bundle`, SHA-256
  `66d517f038e2d0e460be7b4b3f8b529d0444751ccd8741433ec35fcd8e1246c7`.

### Harness isolation and gate re-evaluation

- `f88dc0c7` isolates the Poly best-candidate byte-restoration unit from the real
  Tet generator.  It now proves all five iteration-1 polyMesh files are restored
  after a worse iteration-2 candidate.  Production and geometry thresholds are
  unchanged; the separate real-sphere star-validity failure remains visible.
- Current Gate status:

| Gate | Status | Cycle-33 evidence / next evidence |
|---|---|---|
| 1 Repository | FAIL | `master` is clean, but the tracked installer executable remains and the Cycle-34 Hex worktree is active. |
| 2 Build | UNVERIFIED | Clean GCC 13.3 C++23 targeted builds pass; supported OS/compiler matrix is incomplete. |
| 3 Automated tests | UNVERIFIED | Focused/wider suites pass; real Poly sphere star-validity and full-suite evidence remain. |
| 4 Shape preservation | UNVERIFIED | Exact localized hashes and proof-gated Tet restoration pass; complete corpus remains. |
| 5 Mesh validity | UNVERIFIED | New Hex/Poly/Tet false-success paths reject; all-engine corpus remains. |
| 6 Cell count | FAIL | Deferred behind shape/topology as directed; Poly and Tet targets remain unresolved. |
| 7 Boundary layer | UNVERIFIED | No Cycle-32/33 BL contract change; positive-layer corpus remains. |
| 8 Quality | UNVERIFIED | Curvature and valid-output parity pass; complete fixture specifications remain. |
| 9 Reproducibility | FAIL | New kernels are deterministic; independent wheel bytes and external P4C hashes remain unresolved. |
| 10 Robustness | UNVERIFIED | New malformed topology/ABI cases reject; adverse corpus remains incomplete. |
| 11 Performance | UNVERIFIED | Card budgets pass; frozen end-to-end engine budgets remain. |
| 12 Packaging | FAIL | Native build manifest improves evidence; Windows wheel/installer/UI/uninstall matrix remains. |
| 13 License/provenance | UNVERIFIED | Independent C++23, no third-party code copy; global inventory still has unresolved rows. |
| 14 Documentation/operations | UNVERIFIED | Research and build-evidence docs improved; release operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Complete Cycle-34 Hex wall-fit candidate preparation, then run the next
  all-engine validity, full-test, and packaging evidence scan.  Keep target-cell
  optimization deferred until shape, topology, validity, and provenance are
  mechanically stable.

## Cycle 34 checkpoint -- 2026-07-31

### Hex candidate-preparation experiment discarded

- The native candidate-preparation path remained byte-exact and reduced traced
  Python memory by `54.11%`, but whole-stage speedup was only `1.8166x` against
  the predeclared `3x` gate.  The code was not merged.
- The failed hypothesis is archived in
  `native-hex-wallfit-candidate-prep-failed-2df9ef50-v2.bundle`, SHA-256
  `37abed717d13f1b0025a00055ef73b0b3c66952959be9e14fef1162d8041808f`.

### Poly orphan-primal refusal

- `ba7b6307` makes orphan primal points fail before dual artifacts are written.
  False success changes `1 -> 0`; artifact count changes `8 -> 0`; valid output
  and provenance remain exact.  The 50,000-element path regresses `5.77%`,
  inside the declared `10%` budget.  Focused validation passes `37`.
- Bundle: `native-poly-orphan-primal-1-ba7b6307-v2.bundle`, SHA-256
  `e181cd8f68e8d9e67ce8219a1248eb150193e9873cbfce90cf8a97a4f67a12d6`.

### Tri/Quad fused preflight preparation

- `ab5f386f` fuses the read-only candidate preflight without changing candidate
  order, topology, thresholds, or output.  Median time changes
  `0.223395 -> 0.051049 s` (`4.376x`); traced memory falls `11.08%`.
- Focused/wider/build-contract validation passes `54/88/7`.
- Bundle: `native-triquad-preflight-prep-1-ab5f386f.bundle`, SHA-256
  `815254b01aa01c1ff9825ca7ab7fd8d2d3232d15e9f76e271030f4152db476d8`.

## Cycle 35 checkpoint -- 2026-07-31

### Tet metric-sweep source-topology transaction

- `d0204b56` makes every accepted metric sweep pass the existing C++23-backed
  local-boundary and exact source-component certificate before commit.  A bad
  candidate is rolled back to the exact pre-sweep arrays; no repair, threshold,
  target-cell, or surface motion is introduced.
- The frozen sphere changes from a false failure with thousands of
  non-manifold boundary edges to `669` points and `1,631` valid tets.  Three
  runs have identical point/connectivity SHA-256
  `a87a55050628cf6987b0479cd35ed6b541dbbb52ce3cd94c5d92ee545f42082a`;
  open edges, non-manifold edges, negative volumes, and zero volumes are all
  zero.  Post-merge validation passes `37` with one vendor skip.
- Bundle: `native-tet-cycle35-d0204b56.bundle`, SHA-256
  `379d498736196205206556610e1d74c37613cc2c9ac4a46f7089b6e636ed5c4d`.

### Hex batched initial wall-fit projection

- `70f59963` uses the existing C++23 closest-triangle-candidate kernel for the
  initial projection batch under a strict ABI.  Projection order, subsequent
  candidate checks, validity gates, and output remain exact.
- Post-merge benchmark changes `0.582053 -> 0.449075 s` (`1.296x`), with
  identical `5,042,560`-byte traced peak, output SHA, and `1,538` accepted
  snaps.  Expanded post-merge regression passes `89`.
- Bundle: `native-hex-cycle35-70f59963.bundle`, SHA-256
  `7f6314cdd72d9794bbbe83137c748f4d031469404c52df78822c029956c20233`.

### Tri C++23 flip-quality batch

- `923f3bcf` ports the four-triangle flip-quality census to
  `native_metrics.triangle_quality_batch`.  Flip candidates, ordering,
  orientation, epsilon, topology, and reports remain exact.
- Post-merge cylinder median changes `0.747307 -> 0.523409 s` (`1.428x`);
  the direct 50,000-triangle kernel is `2,765x` faster.  Fresh GCC 13.3 C++23
  warnings-as-errors build and `199` post-merge tests pass.
- Bundle: `native-triquad-flip-quality-1-923f3bcf.bundle`, SHA-256
  `00669912c7badbf891ee1067cb483256056f76acb00a3221fe494dc145533d78`.

### Poly bounded star-kernel witness

- `0aaa19b8` replaces arithmetic-center-only classification with a bounded,
  deterministic half-space projection used only when the arithmetic witness
  fails.  The projected witness is never written; the unchanged signed-subtet
  predicate and `1e-12` tolerance make the final decision.
- Frozen seed-10 changes `2/14 -> 0/0` invalid star cells/subtets and writes an
  exact deterministic `698/5737/7072` cell/point/face result in three runs.
  The residual invalid cube remains `success=false` with zero artifacts; its
  four feasible false negatives are removed and the true residual is `1/9`.
  Fresh C++23 build, `32` focused tests, and the Tet-to-Poly sphere route pass.
  Full checker/harness runs timed out and remain unverified.
- Bundle: `native-poly-star-kernel-center1-0aaa19b8.bundle`, SHA-256
  `82f5e08768796978368619d17b5d263fe08873f38bd69f7447da240640bacb00`.

### Cycle-35 gate re-evaluation

| Gate | Status | Cycle-35 evidence / next evidence |
|---|---|---|
| 1 Repository | FAIL | `master` is clean, but the tracked installer executable and active Cycle-36 research worktrees remain. |
| 2 Build | UNVERIFIED | Fresh GCC 13.3 C++23 targeted builds pass; supported Windows/compiler matrix remains incomplete. |
| 3 Automated tests | UNVERIFIED | Tet `37`, Hex `89`, Tri/Quad `199`, and Poly `32` post-merge checks pass; immutable-head full suite remains. |
| 4 Shape preservation | UNVERIFIED | Tet source-topology rollback and exact all-lane hashes pass; complete representative corpus remains. |
| 5 Mesh validity | UNVERIFIED | Frozen Tet and Poly false-failure paths now yield valid outputs; all-engine adverse corpus remains. |
| 6 Cell count | FAIL | Still deferred behind shape/topology/validity as directed. |
| 7 Boundary layer | UNVERIFIED | No Cycle-35 layer contract change; 0/1/multiple-layer corpus remains. |
| 8 Quality | UNVERIFIED | Card-specific quality parity passes; complete engine/fixture specifications remain. |
| 9 Reproducibility | FAIL | New paths are deterministic; independent wheel bytes and external P4C hashes remain unresolved. |
| 10 Robustness | UNVERIFIED | New malformed ABI/topology and residual non-star cases fail closed; adverse corpus remains incomplete. |
| 11 Performance | UNVERIFIED | Hex and Tri card budgets pass; frozen all-engine end-to-end budgets remain. |
| 12 Packaging | FAIL | Windows wheel/installer/UI/uninstall matrix remains. |
| 13 License/provenance | UNVERIFIED | Independent first-party C++23 changes and no `third_party/` edits; global inventory still has unresolved rows. |
| 14 Documentation/operations | UNVERIFIED | Card evidence is current; release/rollback operations remain incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Cycle 36 runs Tet topology-audit profiling, Hex wall-fit local-scale batching,
  Quad hot-path profiling, and the next Poly card in parallel.  Keep strict
  shape/topology/validity and provenance ahead of target-cell count.  Full
  checker timeout evidence remains queued; it is not a pass.

## Cycle 36 checkpoint -- 2026-07-31

### Tet source-component face census

- `1bc65359` replaces the exact component certificate's global sorted `4T`
  face array with a reserved first-party C++23 hash-incidence census.  The
  32-component median changes `0.681927 -> 0.034191 s` (`19.95x`) and RSS
  changes `133,972 -> 113,808 KiB` while all component, malformed-input,
  topology, and provenance reports remain exact.  Post-merge validation passes
  `37`.
- Bundle: `native-tet-cycle36-1bc65359.bundle`, SHA-256
  `eac808a61e3164475ca318d4e64f28eda76cea3bb7d38274971858a316124fb7`.

### Hex wall-fit local scale C++23 batch

- `b061e55e` computes each incident cell edge scale once in
  `native_hex_quality.boundary_vertex_local_scales`.  Whole wall-fit changes
  `0.481632 -> 0.213631 s` (`2.2545x`); the isolated scale stage is `51.68x`.
  Output, statistics, topology, provenance, and traced peak memory are exact.
  Expanded validation passes `110`; post-merge focused validation passes `45`.
- Bundle: `native-hex-cycle36-b061e55e.bundle`, SHA-256
  `8c46d5cf798203aaecc389d8cba1172a7320dac0d22658411800b94fc6ea2448`.

### Quad fused transaction C++23

- `81d5b17a` fuses guarded prepare/select/assembly while Python retains an
  independent vectorized topology and provenance audit.  The frozen public
  path changes `0.052478 -> 0.018678 s` (`2.810x`), or `119.87x` versus the
  full Python oracle.  Hashes and diagnostics remain exact; expanded validation
  passes `153` and post-merge validation passes `66`.
- Full text remained inaccessible for DOI `10.1002/nme.7644` and DOI
  `10.1137/1.9781611978575.6`.
- Bundle: `native-quad-cycle36-81d5b17a.bundle`, SHA-256
  `77c9dea0a297b5ff579a12835f0364bc479a98725fcfa9aeebc74801209df0a3`.

### Explicit native build precedence

- `e7ee5016` makes `AUTOTESSELL_EXT_BUILD_DIR` load its exact first-party
  module even when a stale module name is already cached.  A present but broken
  explicit ABI fails closed; an absent explicit candidate retains the defined
  fallback.  Fresh eight-module C++23 warnings-as-errors build and `174`
  affected tests pass.
- Bundle: `common-native-loader-cycle36-e7ee5016.bundle`, SHA-256
  `c8fa366594bbc11d0fa2a91c1f4fdd64f2aead115b3b4b6410495e8fac629137`.

### Poly exact pairing C++23

- `1c6ff93f` replaces the exponential Phase-0 face pairing with an independent
  `O(V^3)` / `O(V^2)` general weighted matching kernel.  A mandatory adversarial
  review rejected the first candidate for mixed-scale quantization, objective
  cancellation, and an ABI-contract omission.  None of that candidate reached
  `master`.
- The amended exact-binary64 implementation passes all prior counterexamples,
  `1,500` exhaustive cases, an additional `2,400` mixed-scale permutation
  checks, and the independent re-review.  The sphere checker changes from a
  `>180 s` timeout to `2.54..2.69 s` (`>=66.8x`), with exact five-file hashes,
  `mesh_ok=true`, and zero negative cells.  Fresh post-merge cross-validation
  passes `112` after rebuilding the previously stale native-polymesh module.
- Bundle: `native-poly-cycle36-1c6ff93f.bundle`, SHA-256
  `4c09e6f88f29b6e25db3162f50d99fa7fe4dd8c34c11ec17b33c23dd978d16f0`.

## Cycle 37 checkpoint -- 2026-07-31

### Tet inverted-cell strict certificate

- `b8025929` adds exact `n_inverted_tets` evidence to the final source-topology
  certificate.  A reversed tetrahedron changes from a false valid result to a
  fail-closed result with count one.  The unmodified sphere remains `669/1,631`,
  inverted count zero, and exact SHA-256
  `a87a55050628cf6987b0479cd35ed6b541dbbb52ce3cd94c5d92ee545f42082a`.
  A 48,000-tet audit regresses `6.14%`, inside the fixed `10%` budget.  Focused
  validation passes `75`; post-merge validation passes `56`.
- Bundle: `native-tet-cycle37-b8025929.bundle`, SHA-256
  `c41725149e89877a39693ddff79cf3dcf3a63a864bfdb2dc932ff560efda7bef`.

### Hex original-source invariant

- `1f1f5b97` removes the hidden PRE3 isotropic-remesh substitution from the
  native-Hex generator.  The adverse replacement had changed a closed source
  from watertight to open, Euler `2 -> 0`, area `-0.4193%`, and volume
  `-0.5895%` while returning success.  The generator now uses only the exact
  input source; adverse runtime changes `2.958305 -> 0.453269 s` (`6.526x`).
- Cube, cylinder, gear, bracket, and adverse output/statistic hashes remain
  exact, with zero reported negative, inverted, or degenerate cells.  Full Hex
  validation passes `193` with `11` pre-existing skips.
- Bundle: `native-hex-cycle37-1f1f5b97.bundle`, SHA-256
  `a1a9ffb14f52e2793685f63d1dc24c20cba9369fcd04d9df04fc0c03d43a475d`.

### Quad similarity-range robustness

- `8fa06841` applies only local exact-power-of-two similarity normalization to
  C++23 and Python-oracle quality calculations.  The same planar patch changes
  from `3/8` to `8/8` accepted scales over `1e-150..1e150`; invalid topology,
  warped, concave, wall, and protected-feature gates remain fail closed.
- The frozen 60x60 hashes remain exact.  Median time is `0.020220 s`, `+9.89%`
  and below the fixed `0.02116 s` cap.  Expanded validation passes `168`; the
  post-Poly rebase cross-suite passes `93`, and post-merge validation passes
  `39`.
- Full text remained inaccessible for DOI `10.1145/3731143`.
- Bundle: `native-quad-cycle37-8fa06841.bundle`, SHA-256
  `48229b97777f972c86dabb0bd46226d0c32d24ffcbe35bb4662c497c966fbc6c`.

### Cycle-37 gate re-evaluation

| Gate | Status | Cycle-36/37 evidence / next evidence |
|---|---|---|
| 1 Repository | FAIL | Research worktrees and branches are zero and `master` is clean after this ledger commit, but the tracked installer executable remains. |
| 2 Build | UNVERIFIED | Repeated fresh GCC 13.3 C++23 warnings-as-errors targets pass; supported OS/compiler matrix remains incomplete. |
| 3 Automated tests | UNVERIFIED | Expanded engine and cross-engine suites pass; immutable-head full unit/integration/regression suite remains. |
| 4 Shape preservation | UNVERIFIED | Hex hidden source substitution is removed and all card hashes pass; complete representative corpus remains. |
| 5 Mesh validity | UNVERIFIED | Tet inversion false pass is closed and frozen outputs remain valid; all-engine adverse corpus remains. |
| 6 Cell count | FAIL | Deliberately deferred behind shape/topology/validity as directed. |
| 7 Boundary layer | UNVERIFIED | Zero/one/multiple-layer release corpus remains. |
| 8 Quality | UNVERIFIED | Poly pairing and Quad scale-range metrics pass; complete fixture specifications remain. |
| 9 Reproducibility | FAIL | New paths are deterministic; independent wheel bytes and external P4C hashes remain unresolved. |
| 10 Robustness | UNVERIFIED | Mixed-scale, stale-ABI, inverted-cell, and source-substitution cases are covered; adverse corpus remains incomplete. |
| 11 Performance | UNVERIFIED | All Cycle-36/37 card budgets pass; frozen all-engine end-to-end budgets remain. |
| 12 Packaging | FAIL | Windows wheel/installer/UI/uninstall matrix remains. |
| 13 License/provenance | UNVERIFIED | Changes are independent first-party C++23/Python with no `third_party/` edits; global inventory remains. |
| 14 Documentation/operations | UNVERIFIED | Evidence is current; release and rollback operations remain incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on all preceding gates. |

### Next automatic action

- Start the next all-engine cycle from this immutable head.  Keep strict input
  shape, topology, validity, provenance, and realistic boundary-layer contracts
  ahead of target-cell count.  Prioritize the full immutable-head suite and
  representative shape/validity corpus while continuing one bounded engine
  hypothesis per lane.

## Cycle 44 checkpoint -- 2026-07-31

### Integrated evidence since Cycle 37

- Common contract cards restored stale CVT and WildMesh dependency/build
  contracts.  The current first-party native build manifest verifies all eight
  modules at `e5a2e4aa` under GCC 13.3 / C++23.  No `third_party/` file changed.
- Native Poly gained C++23 batched hull-face assembly and an immutable sharded
  L3 runner.  The frozen sphere path is byte deterministic and the native block
  is `4.271x` faster; the full 225-node Poly census still reports one failure,
  two timeouts, and one module with a skip, so Gate 3 remains failed.
- Native Tri/Quad gained a strict opt-in C++23 flip filter.  Default behavior is
  unchanged; public-path median improves `1.669x` and the direct kernel
  `64.99x`, with exact frozen hashes.
- Native Tet now preserves immutable input-source evidence through all
  source-certifying call sites and writes Tet point coordinates with 17
  significant digits.  Cylinder disk ownership changed from `95/216` to
  `216/216`, unowned points from `121` to `0`, and round-trip coordinate error
  from `4.995e-10` to zero.  Post-merge focused validation passes `10`.
- Tet shared-facet sidedness auditing then exposed previously published
  overlapping tetrahedral complexes: pipeline cylinder `112` same-side faces;
  self-only cylinder `72`, cube `142`, and sphere `108`.  `b709899d` now fails
  closed with zero output artifacts instead of reporting these meshes as
  successful.  Post-merge focused validation passes `8`; Tet functionality and
  Gate 5 are not claimed.
- Native Hex added a conservative oriented-box inward-shell certificate, then
  ported the report-only local-front backtracking kernel to first-party C++23 in
  `e5a2e4aa`.  On the hard bracket, raw inverted hexes change `160 -> 0` and
  intersections `4161 -> 0` without outer-coordinate, topology, or provenance
  change.  The C++ median is `0.000694 s` versus Python `0.032543 s`
  (`46.89x`); real-extension and build-contract validation passes `22` with
  zero skips.  This is not a production Boundary-Layer Gate claim.
- WildMesh runtime dependencies now declare Shapely and Rtree with explicit
  license boundaries outside the future MIT native core.  The global resolved
  distribution inventory and release notices remain incomplete.

### Active failed evidence and automatic queue

- Poly Cycle 41 has a five-commit prerequisite stack that fixes pinned Lloyd
  compaction, explicit BL0 propagation, mandatory pre-write validity, and cell
  face orientation.  Related checks pass, and a dense cylinder changes from
  `4497` negative cells to zero, but the stack is deliberately unmerged while
  `test_native_poly_solid_volume.py` times out.
- A proposed Poly concave-shell admission was rejected after independent shell
  checks found `30` non-simple face loops, `42/73` cells with invalid closed-edge
  incidence, and `20` self-intersecting cells (`154` pairs).  The active card
  isolates the first dual face-loop/seam assembly defect; no threshold is being
  relaxed.
- The active Tet card isolates the first mutation that changes shared-facet
  sidedness from zero to positive, preferring transaction rollback/avoidance
  before any local-cavity repair.
- The active CAD-front contract card records authoritative STEP face identity,
  orientation, and seam connectivity without inferring missing physical groups.
  Production Hex boundary-layer promotion remains blocked by CAD semantics,
  inner-interface closure, and all-hex core fill.
- Target-cell accuracy remains deliberately behind shape, topology, validity,
  provenance, and requested boundary-layer behavior.

### Cycle-44 gate re-evaluation

| Gate | Status | Evidence / next evidence |
|---|---|---|
| 1 Repository | FAIL | `master` is clean, but active research worktrees remain and `installer/dist/AutoTessell-1.2.0-Setup.exe` is tracked. |
| 2 Build | UNVERIFIED | GCC 13.3 C++23 first-party modules pass; supported OS/compiler/release matrix remains. |
| 3 Automated tests | FAIL | Poly immutable census has one failure, two timeouts, and one skip-bearing module; complete unit/integration/UI suite remains. |
| 4 Shape preservation | UNVERIFIED | Card-level hashes pass; complete representative multi-engine corpus remains. |
| 5 Mesh validity | FAIL | Tet representative fixtures now correctly refuse overlapping complexes; a successful zero-overlap path is absent. |
| 6 Cell count | FAIL | Explicitly deferred behind higher-priority contracts. |
| 7 Boundary layer | UNVERIFIED | BL0 fixes and Hex report-only evidence exist; authoritative CAD 0/1/multi-layer release corpus remains. |
| 8 Quality | UNVERIFIED | Hex bracket local front is valid but inner core is absent; Poly dense output remains grade D. |
| 9 Reproducibility | FAIL | New card paths are deterministic; independent wheel bytes and external P4C hashes remain unresolved. |
| 10 Robustness | UNVERIFIED | New fail-closed cases are covered; adverse corpus remains incomplete. |
| 11 Performance | UNVERIFIED | Card budgets pass; frozen end-to-end engine budgets remain. |
| 12 Packaging | FAIL | Windows wheel/installer/UI/install/uninstall matrix remains. |
| 13 License/provenance | UNVERIFIED | Card provenance is recorded and `third_party/` is unchanged; resolved inventory/notices/source-offer proof remains. |
| 14 Documentation/operations | UNVERIFIED | Checkpoints are current; installation, troubleshooting, release, and rollback evidence remains incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on Gates 1--14 and a versioned clean artifact/checksum manifest. |

### Next automatic action

- Continue the three active topology/provenance cards, integrate only critic-
  accepted evidence, then rerun the Poly L3 census and start the next Tri/Quad
  validity card.  Do not stop or claim release readiness while any gate is
  `FAIL` or `UNVERIFIED`.

## Cycle 48 checkpoint -- 2026-07-31

### Integrated contract and fail-closed evidence

- `f35534ab` adds a separate authoritative STEP provenance payload while the
  legacy `(V,F)` stream remains byte/order exact.  On the T-junction, BRep face
  coverage is `3,392/3,392`; applied orientation and canonical seams remove
  `843` same-direction conflicts.  Missing physical-group authority remains
  unknown rather than inferred.
- `844bea90` preserves explicit XDE layer, display-color, and assembly identity
  metadata.  Layers are authoritative grouping metadata only:
  `physical_group_authority=false`; colors and absent face names never become
  boundary-condition semantics.  Runtime XDE fixtures pass `14` checks.
- `c1270dda` adds negative XDE fixtures and closes a real fail-open: conflicting
  explicit layers for one BRep face now raise before payload publication.  The
  post-merge reader suite passes `19` with one unrelated skip.
- `2dc38585` fixes the native Tri route's current honest contract with a
  24-call fail-closed corpus.  Four fixtures, BL0/BL1, and three repetitions
  preserve source/output bytes and feature inventory on rejection.  This does
  not certify topology-changing Tri edits.
- `8d5aa334` rolls back the JJ3 Tet smoothing candidate whenever sidedness debt
  increases.  Cylinder reaches zero same-side faces with exact source evidence;
  cube and sphere stay artifact-free refusals when invalid.
- `217615cf` extends the same nonincrease transaction to both accepted CVT
  passes.  Unsafe cube CVT candidates return exact pre-CVT arrays and stop
  before later mutators; the retained cube state is still invalid and Gate 5
  remains failed.  Post-merge focused validation passes `7`.

### Rejected and deferred research

- Poly source-cap seam and boundary-separator prerequisites are retained on an
  unmerged DEFER stack.  They remove observed T-junction and separator
  self-intersection defects, but do not resolve the full pipeline timeout.
- Closed-ring fan materialization was killed because invalid star subtets rise
  `878 -> 1,065`.  No triangulation heuristic was merged.
- The true Poly high-skew defect is source-cap center cells.  A minimum sector
  partition requires at least `14` new cells/cut surfaces and changes ownership
  of `64` source-adjacent caps.  That needs an explicit policy for cell/patch
  semantics; it is not automatically implemented.

### Cycle-48 gate re-evaluation

| Gate | Status | Cycle-48 evidence / next evidence |
|---|---|---|
| 1 Repository | FAIL | `master` is clean at checkpoint; active research worktrees and tracked installer executable remain. |
| 2 Build | UNVERIFIED | Native manifest verifies eight modules on GCC 13.3/C++23; supported matrix remains. |
| 3 Automated tests | FAIL | Poly L3 still has a failure, two timeouts, and a skip-bearing module; full suite remains. |
| 4 Shape preservation | UNVERIFIED | STEP/Tri rejection contracts preserve inputs; topology-changing Tri and complete engine corpus remain. |
| 5 Mesh validity | FAIL | Tet now refuses unsafe JJ3/CVT outputs; successful zero-overlap cube/sphere path remains absent. |
| 6 Cell count | FAIL | Still deliberately secondary. |
| 7 Boundary layer | UNVERIFIED | BL0 accounting is explicit; authoritative CAD-to-front and positive-layer corpus remain. |
| 8 Quality | UNVERIFIED | Poly cap-cell skew and all-hex core/interface remain unresolved. |
| 9 Reproducibility | FAIL | Card-local hashes pass; independent wheel/P4C evidence remains. |
| 10 Robustness | UNVERIFIED | XDE and topology fail-closed cases expanded; adverse corpus incomplete. |
| 11 Performance | UNVERIFIED | Card budgets pass; all-engine benchmark budgets remain. |
| 12 Packaging | FAIL | Windows wheel/installer/UI/install/uninstall matrix remains. |
| 13 License/provenance | UNVERIFIED | New provenance is recorded; global inventory/notices/source-offer proof remains. |
| 14 Documentation/operations | UNVERIFIED | Ledger current; release/troubleshooting/rollback operations incomplete. |
| 15 Release candidate | UNVERIFIED | Depends on Gates 1--14. |

### Next automatic action

- Do not stop.  Continue Tet initial-overlap root cause, Tri certificate
  preflight, and the policy-bounded Poly feasibility queue.  Merge only
  independently reviewed cards, clean their worktrees, and keep target-cell
  work behind shape, topology, validity, provenance, and boundary layers.

## Cycle 49 checkpoint -- 2026-07-31

### Integrated native Tri provenance diagnostic

- `4da76b27` merges `TRI-SOURCE-CERTIFICATE-PREFLIGHT-1` as
  `CORRECTNESS_KEEP`, runtime-disconnected evidence.  The diagnostic exposes
  canonical declared feature edges and a dedicated SHA-256 hash.  It preserves
  the distinction between no declaration, an explicit empty declaration, and a
  non-empty canonical declaration; invalid non-source declarations fail closed.
- Independent review accepted the card.  Post-merge certificate, shell-
  provenance, and local-guard tests pass `17/17`; no routing, default, mesh
  output, threshold, or `third_party/` change occurred.
- Bundle:
  `/mnt/d/AutoTessell-cleanup-backup-20260730/research-bundles/triquad49-source-certificate-4da76b27.bundle`
  SHA-256 `d1765878c8117a681b1e9a228d4e7159033b197911ff2790ac9a580fdd63bc3b`.
  The merged Tri worktree and branch were removed only after bundle verification.

### Surface-engine product split

- User product contract now distinguishes three independent surface meshers:
  `tri` emits triangles only; `quad` emits quads only and otherwise fails
  closed; `tri_quad` may emit both types and reports both counts.
- Existing `native_quad_dominant` is not a strict quad-only engine because it
  permits residual triangles.  It is a future `tri_quad` candidate only; it
  must never satisfy the `quad` contract by name or fallback.
- First card is contract/routing/evaluator separation with default and mesh
  output unchanged.  C++23 geometry kernels remain the implementation target;
  Python may carry only orchestration/schema diagnostics until native parity is
  proved.

### Tet active evidence

- The unsafe Tet Phase-A smoothing attempt was deferred, not merged.  Exact
  patch archive:
  `/mnt/d/AutoTessell-cleanup-backup-20260730/research-bundles/tet45-phase-a-smoothing-deferred-20260731.patch`,
  SHA-256 `fbe9c4f8785b8c480bb840b3a61d8fd547450e5cff40c50fb787c50b0f81b450`.
- Earliest sphere source loss is BETA2825 degenerate removal.  Active
  `TET-DEGENERATE-REMOVAL-SOURCE-TRANSACTION-1` may commit a candidate only
  when immutable source components are bijective, source faces remain present,
  unowned source facets are zero, and inversion does not increase; otherwise it
  restores exact pre-candidate arrays.

### Cycle-49 gate re-evaluation

Gate states unchanged from Cycle 48.  Gate 1 remains `FAIL` because the Tet
and Poly research worktrees remain and the installer executable is tracked.
Gate 4 remains `UNVERIFIED`: Tri evidence certifies only fail-closed diagnostic
inputs, not topology-changing surface output.  Gate 5 remains `FAIL`; Gate 6
is deliberately secondary.

### Next automatic action

- Run the distinct `tri`/`quad`/`tri_quad` contract-card baseline without
  changing defaults or output.  Continue Tet BETA2825 source transaction in
  parallel.  Keep the Poly cap-sector proposal deferred until a source-cell
  ownership policy exists.  Do not stop while a gate is `FAIL` or
  `UNVERIFIED`.

## Cycle 50 checkpoint -- 2026-07-31

### Integrated strictness infrastructure

- `167bcd0e` merges a runtime-disconnected surface product certificate.  The
  public semantic modes are `tri`, `quad`, and `tri_quad`.  `quad` rejects any
  triangle or triangular handoff; legacy `native_quad_dominant` is always
  `candidate_mixed`, even when its triangle remainder is empty.  Post-merge
  contract plus native-quad tests pass `59/59`; routing, defaults, output,
  UI, and `third_party/` remain unchanged.
- `542314e1` wraps BETA2825 degenerate removal in an immutable-source
  transaction.  Commit requires candidate component bijection, source-face
  preservation, zero unowned source facets, and nonincreasing inversion.
  Unsafe component-loss and winding-inversion candidates restore exact
  pre-candidate objects.  Cube and isolated sphere `2k` candidates satisfy
  the conditions; default sphere has no BETA candidate and no improvement is
  claimed.  Post-merge focused tests pass `10/10` in `56.65 s`.
- Tet bundle:
  `/mnt/d/AutoTessell-cleanup-backup-20260730/research-bundles/tet45-degenerate-source-transaction-542314e1.bundle`,
  SHA-256 `0f6deb8d68917c0e3021e5020cac145bccefa2143c71c301df588d8fe06aa8be`.
  Surface-mode bundle:
  `/mnt/d/AutoTessell-cleanup-backup-20260730/research-bundles/surface-mode-contract-167bcd0e.bundle`,
  SHA-256 `d6c182c0dc4629f52fcc2e85502c17c4d53b980df9a90174e4c389dc0ddc7fdd`.
  Both bundles verify; their merged worktrees and branches were removed.

### Literature availability correction

- Local repository still lacks the three historical quad PDFs.  As of this
  cycle, SIAM exposes free PDF access for
  `10.1137/1.9781611979138.18`; it is not an access blocker.  Full text for
  `10.1002/nme.7644` and `10.1137/1.9781611978575.6` remains unavailable
  without publisher, institutional, author, or purchase access.  No new
  inaccessible DOI was discovered.

### Next automatic action

- Continue `TRI-SOURCE-TOPOLOGY-AUDIT-CPP23-1` as a report-only,
  default-OFF `CORRECTNESS_KEEP` accelerator.  It cannot promote topology-
  changing tri output.  Then add public routing only after independent
  tri/quad/tri_quad product contracts and evaluator reports exist.  Gate 1--15
  remain unmet; continue.

## Cycle 51 checkpoint -- 2026-07-31

### Integrated tri-only C++23 audit

- `0a915eb0` merges `TRI-SOURCE-TOPOLOGY-AUDIT-CPP23-1` as default-OFF,
  runtime-disconnected `CORRECTNESS_KEEP`.  The first-party C++23 audit uses
  sorted directed edge records and DSU components to report only finite input
  validity, closed-oriented status, edge count, component count, and Euler
  characteristic.  It never edits mesh arrays, routing, defaults, acceptance,
  or output.
- Explicit external Release build loading validates direct ABI, invalid-input
  rejection, immutable input, deterministic repetition, malformed-native
  fail-closed behavior, and full source-certificate equality (cube/cylinder/
  sphere, three repeats).  Post-merge explicit-native tests pass `24/24` in
  `16.86 s`.  Native audit median on the documented 20,480-face fixture is
  `0.003275630 s` versus Python `0.676991239 s`; this is observability only,
  not a route-promotion claim.
- Bundle:
  `/mnt/d/AutoTessell-cleanup-backup-20260730/research-bundles/tri-source-topology-audit-cpp23-0a915eb0.bundle`,
  SHA-256 `af15a7ded250567e089d23ece196d2337db0d4edcf1330d39c0f99d8455375ee`.
  The exact two external native build directories (`13.0 MiB`) and merged Tri
  worktree/branch were removed after validation.

### Quad research availability

- User-supplied PDFs for `10.1137/1.9781611978575.6` and
  `10.1137/1.9781611979138.18` are byte-verified and `FULL_READ`; their
  independent strict-quad lessons are recorded in native-quad literature.
  The remaining unavailable full text is only `10.1002/nme.7644`.
- Both methods require narrow topology/parameterization prerequisites and lack
  AutoTessell's source envelope, feature/patch provenance, deterministic, and
  explicit-rejection contracts.  They cannot be copied or promoted directly.

### Next automatic action

- Run strict-quad C++23 output/preflight planning separately from `tri_quad`.
  Run Tet report-only calibration to identify which strict predicates may be
  safely reclassified as diagnostics without weakening source semantics.  Run
  independent native-hex card selection.  Poly source-cap partition remains
  deferred pending a user policy.  Gate 1--15 remain unmet; continue.

## Cycle 52 checkpoint -- 2026-07-31

### Integrated safe foundations

- `09988567` adds diagnostic-only Tet ambiguity classes.  Legacy ambiguity
  count, strict `valid`, refusal, writer gate, source/provenance, and CVT
  rollback remain unchanged.  Near/floor-only ambiguity still refuses output;
  same-side overlap remains hard.  Post-merge focused tests pass `13/13` in
  `54.89 s`.  Bundle SHA-256:
  `7698921896faa6b393f26e85d1f469b818354a89e1e6f023170a2b82b91997a4`.
- `799489c2` adds a default-OFF Hex local-front admission preflight.  Python
  owns file/face/entity provenance, exact triangle-to-quad mapping, and
  clearance; C++23 checks only bounded numeric rows.  Unknown authority,
  duplicate/missing rows, wrong geometry, or insufficient clearance reject
  before candidate construction.  It emits no shell/case/output.  Explicit
  native post-merge tests pass `9/9`.  Bundle SHA-256:
  `5521cd826e9e951e5f3d2c9b10508c8de744f72e2571ce7a0ef97e4fc5198825`.
- `53f6b2dc` adds default-OFF strict-quad fixed-vertex two-triangle-pair
  preflight.  It requires zero candidate triangles, degree-four quads,
  byte-identical vertices, exact canonical pair provenance, topology/feature
  preservation, and Python-only patch/physical-payload authority.  It is not
  a general quad mesher and does not route or output a mesh.  Explicit native
  post-merge tests pass `18/18`.  Bundle SHA-256:
  `b2dcd9de0a0919a382f55f63d969a1499dca72697be16816d438de11cef9cef5`.

### Cleanup and gate status

- All three integrated worktrees/branches and their exact external review
  builds were removed only after bundle verification.  Poly remains the sole
  registered research worktree and is a protected DEFER stack.
- No release gate changes to `PASS`: these cards are report-only/default-OFF
  `CORRECTNESS_KEEP` infrastructure.  Gate 4, 5, 7, and all full-release gates
  remain open.

### Next automatic action

- Start separate strict-quad route/evaluator planning only after a real
  candidate can satisfy the fixed-pair certificate.  Use Tet ambiguity classes
  to measure L1 cube/sphere stage distributions, never to suppress refusal.
  Expand authoritative Hex source-front corpus without activating a shell.
  Keep Poly deferred until owner semantics are explicitly authorized.  Gate
  1--15 remain unmet; continue.

## Cycle 53 checkpoint -- 2026-07-31

### Integrated evidence-only hardening

- `4ddddc32` materializes a default-OFF strict-quad fixed-pair product only
  after the existing fixed-vertex certificate succeeds.  It copies certified
  source vertices, accepts supplied quads, emits zero triangles, and retains
  immutable patch/hash evidence.  It does not infer pairs, route a mesh,
  change a default, or fall back to mixed output.  Post-merge focused tests:
  `21 passed, 4 skipped` (no optional external native module).  Bundle SHA-256:
  `51af1bb8b55ce09de541f992f709b3e309a3bb68524d07bb905fa14dc79dc264`.
- `88f9b366` adds the Hex local-front authority corpus L1 admission evidence.
  The runtime allowlist executes before any sidecar or numeric preflight;
  unknown authority rejects with no candidate or artifact delta.  It does not
  activate a shell or construct an output mesh.  Independent review accepted;
  post-merge focused tests: `13 passed, 2 skipped`.  Bundle SHA-256:
  `30c8c5e3d366fbd8346bc107945195e75e92603d88d71b409a3242dbf7dc75ff`.
- `0cf28a3a` adds a Tet ambiguity stage ledger L1.  It records immutable
  dtype/shape/byte hashes and exact legacy ambiguity partitions after existing
  stages.  It is not imported by the generator and changes no predicate,
  strict refusal, target-cell path, writer, transaction, or source array.
  Cube and sphere isolated three-run evidence is deterministic and emits no
  writer artifact; post-merge ledger plus strict-topology/result regression:
  `13 passed` in `92.87 s`.  Bundle SHA-256:
  `42c7bf053c7a3ee8ebef2ea235d29565a25d3851e00178d11fa0431b8da1b234`.
- Both integrated research worktrees and their merged branches were removed
  only after bundle creation.  The sole registered research worktree is the
  protected, unmerged Poly DEFER stack.  `third_party/` remains unchanged.
- Native C++ source identity evidence verifies all eight declared modules on
  GCC `13.3.0` / C++23 for `0cf28a3a`; this is source identity evidence, not a
  clean supported-platform Release-build claim.

### Cycle-53 gate re-evaluation

Gate states remain deliberately conservative.  Gate 1 is `FAIL` while the
protected Poly research worktree and tracked installer executable remain.
Gate 4 remains `UNVERIFIED`: all three surface products have contract or
certificate evidence, not a full source-preserving output corpus.  Gate 5
remains `FAIL`: Tet cube/sphere successful zero-overlap output is absent.
Gate 6 stays `FAIL` and secondary by policy.  Gates 2--3 and 7--15 remain
`UNVERIFIED` or previously recorded `FAIL` pending their mechanical evidence.

### Next automatic action

- Begin a report-only evaluator/planning card that keeps `tri`, strict `quad`,
  and `tri_quad` metrics and acceptance reports separate; do not alter routing
  or output.  In parallel, extend authoritative Hex source-front fixtures and
  use the Tet ledger only to localize the first strict-overlap source.  Keep
  Poly source-cap work deferred until an explicit owner-semantics policy exists.
  Gate 1--15 remain unmet; continue.

## Cycle 54 checkpoint -- 2026-07-31

### Integrated fail-closed diagnostics

- `cdbc36f6` adds `native_surface_product`, a first-party C++23,
  default-OFF, report-only evaluator.  It reads only immutable C-contiguous
  `int64` triangle `(T,3)` and quad `(Q,4)` arrays through no-copy spans and
  distinguishes local `tri`, `quad`, `tri_quad`, and invalid topology.  It
  does not certify a product: every result reports
  `product_accepted=false` with
  `source_product_certificate_required`, because source envelope, feature,
  patch, physical-group, and provenance proof are absent.  Explicit external
  Release build and post-merge test: `8 passed`.  Bundle SHA-256:
  `0dbca3e43e19a8ffc8fbc6e961c69bf4bec61a30d1e8dc626efc1d049da645b7`.
- `8848aff7` adds Hex authority corpus L2 metadata validation.  Duplicate
  authority keys, duplicate explicit order, empty metadata, and runtime-invalid
  key/path/order types fail closed before source reads, sidecar, numeric
  preflight, candidate construction, or artifacts.  Canonical order is stable
  under caller iteration reordering.  Post-merge focused tests:
  `20 passed, 2 skipped` (optional native extension).  Bundle SHA-256:
  `da2541e59f418eb539ff81740b8dd810be1dfde2a97bda75853e3641da06b6c5`.
- `ee30ae7d` records the first Tet same-side strict-overlap source in isolated
  subprocesses only.  The existing audit is invoked first with unchanged
  arguments; the diagnostic then records exact source/candidate hashes,
  ambiguity counts, source-component/patch provenance, and call index.  It
  changes no generator/predicate/threshold/refusal/writer/transaction/target
  path.  Cube and sphere retain strict failure and writer artifact `0`;
  post-merge L1: `4 passed` in `37.98 s`.  Bundle SHA-256:
  `46ca16d5c081c65415f2f608d28f33ec2b6cc29c1752bfeb37e0ed9217dd9e6c`.
- The Cycle-54 C++ temporary Release build and all merged Cycle-54 worktrees
  and branches were removed after their bundle evidence was created.  Poly
  remains the sole protected DEFER worktree.  `third_party/` remains unchanged.

### Cycle-54 gate re-evaluation

No release gate becomes `PASS`.  Gate 1 remains `FAIL` while the protected
unmerged Poly worktree and tracked installer executable remain.  Gate 4 is
`UNVERIFIED`: the surface evaluator deliberately refuses product certification
without source evidence.  Gate 5 is `FAIL`: Tet successful zero-overlap output
is still absent.  Gate 6 remains `FAIL` and secondary by policy.  The remaining
gates retain their prior `FAIL`/`UNVERIFIED` state pending mechanical evidence.

### Next automatic action

- Bind local surface classification to existing source certificates only after
  a full no-false-certification contract is specified.  Continue Tet
  same-side-overlap policy analysis without weakening strict refusal, extend
  CAD-authoritative Hex corpus evidence, and keep Poly source-cap work deferred
  until explicit owner semantics are authorized.  Gate 1--15 remain unmet;
  continue.

## Cycle 55 checkpoint -- 2026-07-31

### Integrated build and authority evidence

- `4d7b6a05` corrects the first-party native Hex build contract: the already
  exposed `local_front_numeric_admission` ABI was omitted from the manifest.
  The C++ implementation, strict no-convert argument contract, routing, and
  output are unchanged.  A stale cached binary initially exposed the mismatch;
  rebuilding the exact native target yields focused ABI tests `10 passed` and
  native manifest `8/8 PASS`.  Bundle SHA-256:
  `b3c86dc8a664274bcbf78e2b8d8151a908ea23e9ce06e63f539530231ed22bc3`.
- `f938840f` adds Hex authority source-digest L3.  It streams input bytes in
  fixed 1 MiB chunks, compares canonical SHA-256 declarations, and rejects
  malformed metadata, missing/unreadable files, or byte mismatches before
  sidecar/numeric/candidate work.  `Path.read_bytes` is forbidden by a runtime
  test to prevent whole-file allocation.  Post-merge focused tests:
  `26 passed`.  Bundle SHA-256:
  `eeb6c79e7e871180013c27fa0be40f8956910c144ca64033921a7e3abbea6e5e`.
- `30a77f16` records an explicit Tet overlap policy table without touching
  runtime code.  Same-side overlap is unrelaxable; source/provenance debt
  requires repair before ambiguity; only ambiguity without either debt is
  eligible for a future independent calibration study, never runtime
  relaxation.  Post-merge L1 policy tests: `6 passed` in `37.47 s`; strict
  refusal and writer artifact `0` remain unchanged.  Bundle SHA-256:
  `7525adf67dd5d4d48642d92817f29625fea085c553981be6c0f2705e58f7998a`.
- All Cycle-55 merged worktrees and branches were removed after bundle evidence.
  Poly remains the only protected DEFER worktree; `third_party/` remains
  unchanged.

### Cycle-55 gate re-evaluation

Gate 2 gains only current native ABI/source-identity evidence, not a supported
platform matrix.  All release gates remain unmet: Gate 1 is `FAIL` because the
protected Poly worktree and tracked installer executable remain; Gate 4 is
`UNVERIFIED`; Gate 5 is `FAIL`; Gate 6 remains `FAIL` and secondary.  No
diagnostic or contract card relaxes an existing topology, shape, validity, or
provenance gate.

### Next automatic action

- Continue source-certificate binding for separate `tri`, strict `quad`, and
  `tri_quad` products; use Tet policy evidence only to select a safe remedy
  hypothesis, never to suppress a same-side refusal.  Continue authoritative
  Hex CAD corpus evidence and keep Poly source-cap work deferred pending owner
  semantics.  Gate 1--15 remain unmet; continue.

## Cycle 62 reconciliation checkpoint -- 2026-07-31

### Reconciled `master`

- Reconciled against `master` `3448c9ae809ec38288545eb3c86d6728f48427a2`.
  Cycle 56--61 implementation commits are reachable through the recorded merge
  commits below.  This checkpoint adds no release claim.
- Protected Poly DEFER worktree remains registered and must not be removed:
  `/home/younglin90/work/claude_code/AutoTessell-wt-poly-cycle41`, branch
  `codex/native-poly-cycle41-solid-volume-timeout-1`, `HEAD`
  `70ce4b9be25e4f278388c90907e8139ba47e1a54`.  Current independent Hex and
  Tet Cycle-62 worktrees are also active; Gate 1 cannot pass.

### Cycle 56--61 exact evidence

| Cycle | implementation / merge | exact evidence | release interpretation |
| --- | --- | --- | --- |
| 56 | `5fefec43` / `e58facf0` | `native_metrics` ABI ledger added the already-exported `triangle_surface_topology_audit` and `strict_quad_pair_preflight`; build-contract scanner `5 passed`; clean Release direct native tests `26 passed`. | ABI ledger repair only; no routing, product, or mesh-output claim. |
| 57 | `172a45c6` / `560c223d` | linked extension binaries now fail closed; evidence/wheel tests `8 passed`; clean all-eight C++23 Release build generated and verified a manifest. | regular-file build provenance only. |
| 58 | `ceb30c93` / `bb6db558` | staged-install verifier added; focused tests `10 passed`; clean external Release install staged eight modules, manifest, and contract; verifier passed. | one staged install row, not clean end-user packaging evidence. |
| 59 | `49eadd70` / `078278c6` | inventory tests `13 passed, 7 expected diagnostic skips`; clean Release install staged exactly eight shipped modules; report-only `native_surface_product` absent; verifier passed. | tri/quad ABI inventory only; diagnostic remains default-OFF and non-shipping. |
| 60 | `573a1cf5` / `02482700` | configuration-matrix tests `17 passed`; clean Release stage manifest records `Linux`, GCC `13.3.0`, C++23, install profile `ON`, and four external adapters `OFF`; verifier passed. | one recorded Linux configuration, not multi-OS or supported-matrix evidence. |
| 61 | `666784a1` / `7aa5103e` | deterministic selected-scope Gate-3 AST audit tests `15 passed`; 96 skip/xfail/flaky markers collected; 21 exact unresolved DEFER rows recorded. | Gate 3 remains blocked; no test was weakened. |

### Bundle and archive evidence

- Cycle 57 bundle:
  `/mnt/d/AutoTessell-cleanup-backup-20260730/research-bundles/native-build-evidence-regular-binary-l0-560c223d.bundle`,
  SHA-256 `874a1398b48d5c1e78908aff483455cce2430d70cf630dfd13cea0e73f6751a3`.
  `git bundle verify` passed; contains complete history with `560c223d`.
- Cycle 58 bundle:
  `/mnt/d/AutoTessell-cleanup-backup-20260730/research-bundles/native-clean-install-evidence-l0-bb6db558.bundle`,
  SHA-256 `7cab1b62f73efff87d02e8ca06c7d8c06ebc15bfa2eca6e76bc39e808fee0437`.
  `git bundle verify` passed; contains complete history with `bb6db558`.
- No matching bundle path was located in the external archive for Cycles 56,
  59, 60, or 61.  Their commits and focused evidence are retained in Git, but
  no archive or SHA-256 is credited here.  The older
  `native-build-evidence-manifest-1-41417ee5.bundle` verifies but predates this
  cycle range and is not used as Cycle-56 evidence.

### Focused versus full validation

- The counts in the table are focused cards or explicit clean-build/install
  checks.  They are not the Gate-3 full unit/integration/regression suite.
- No full-suite execution result is recorded for Cycles 56--61.  This is
  `UNVERIFIED`, not a timeout and not a pass.  No full-suite timeout is claimed
  by this reconciliation.
- Cycle-61's 21 unresolved marker rows are tracked in
  `tests/gate3_marker_defer_l0.json`; the exact scanner detects marker, line,
  reason, and scope drift fail-closed.

### Gate re-evaluation

| Gate | state | current limiting evidence |
| --- | --- | --- |
| 1 Repository | `FAIL` | protected Poly plus active research worktrees/branches remain. |
| 2 Build | `UNVERIFIED` | one clean Linux/GCC Release install row exists; declared supported OS/compiler/configuration matrix is not complete. |
| 3 Automated tests | `FAIL` | full suite absent and 21 selected-scope skip/xfail DEFER rows unresolved. |
| 4 Shape preservation | `UNVERIFIED` | surface diagnostics/certificates do not supply a full source-preserving product corpus. |
| 5 Mesh validity | `FAIL` | no full representative corpus proof of zero invalid/inverted outputs. |
| 6 Cell count | `FAIL` | target tracking remains secondary and lacks engine-corpus acceptance evidence. |
| 7 Boundary layer | `UNVERIFIED` | no full 0/1/multi-layer engine-corpus release evidence. |
| 8 Quality | `UNVERIFIED` | no final fixture-specific quality corpus result. |
| 9 Reproducibility | `UNVERIFIED` | no complete three-run, thread/order release corpus. |
| 10 Robustness | `UNVERIFIED` | no complete adversarial fixture corpus result. |
| 11 Performance | `UNVERIFIED` | focused timings/builds are not a release benchmark matrix. |
| 12 Packaging | `UNVERIFIED` | staged native install exists; full clean user install/CLI/UI/reinstall evidence is absent. |
| 13 License/provenance | `UNVERIFIED` | inventories exist; final release-package audit remains absent. |
| 14 Documentation/operations | `UNVERIFIED` | release checklist, troubleshooting, and operational replay remain incomplete. |
| 15 Release candidate | `FAIL` | no versioned candidate, complete evidence manifest, or zero blocking issues. |

### Research register and next automatic action

- Reference-only scan: arXiv `2512.08450` (2025 connectivity-preserving
  cortical surface tetrahedralization) may inform future metrics discussion;
  no code reuse.  The 2025 Boundary Recovery article (PMCID `PMC2841449`) is
  post-processing context only and does not authorize geometry repair.
- Continue the active Cycle-62 Tet source-provenance root-cause and Hex BREP
  certificate cards without weakening strict refusal or shape gates.  Preserve
  the protected Poly worktree.  Separately resolve the 21 Gate-3 DEFER markers
  with stable reasons or verified replacement coverage, then schedule an actual
  full-suite card.  Gate 1--15 remain unmet; continue.

## Cycle 80 pre-merge reconciliation -- 2026-07-31

### Ledger/Git reconciliation

- Last recorded ledger checkpoint: Cycle 62, `master`
  `3448c9ae809ec38288545eb3c86d6728f48427a2`.
- Current pre-merge base: `master`
  `76661a3de4f7a35b4477362ed23363b11591b7a2`.
- Git-reachable commits after Cycle 62 were not ledgered.  This checkpoint
  explicitly reconciles that gap; it does not invent outcomes for those commits.

### Tet same-side transaction candidate

- Candidate commits: `0cd7acb1`, `45947bd6`, `2002a409`.
- Advisor validation runner: `PASS`, concurrency `1`, `60.47 s`, three focused
  files.  Default OFF preserves strict refusal, emits no `polyMesh`, and emits
  no transaction artifact.  Opt-in
  `AUTO_TESSELL_TET_SAME_SIDE_RETRIANGULATION=1` retains source component
  bijection and source faces, has unowned faces `0`, inverted tets `0`, and
  reduces same-side debt `108 -> 0`.
- Strict topology is unchanged.  Target cells remain secondary.  No
  `third_party/` modification is included.
- Ruff is `UNVERIFIED`: `109` pre-existing `mesher.py` violations.

### Release state

- Gates 1--15 remain unmet; no gate changes to `PASS`.
- `allowed_to_stop: false` remains binding.

## Cycle 92 pre-merge checkpoint -- 2026-07-31

### Tet cube Delaunay ambiguity classification

- Formal runner passed at concurrency `1` in `5.39 s`.  The CVT-off candidate
  has internal faces `2869`, opposite-side `2577`, same-side `0`, and ambiguous
  `292`.
- All `292` ambiguous faces are exact predicate-zero cases; floor-only
  same-side and opposite-side counts are `0`.  This is unconstrained Qhull
  coplanar degeneracy, not a tolerance change or duplicate connectivity.

### Release state

- No code/default change and no Gate `PASS`.  Next action is a source-locked,
  bounded local `2↔3`/`3↔2` strict connectivity transaction only.
- `allowed_to_stop: false` remains binding.

## Cycle 93 pre-merge checkpoint -- 2026-07-31

### Tet same-side local 2↔3 transaction feasibility

- Formal runner `c1` passed at concurrency `1` in `0.722 s` with timeout
  `60 s`; durable evidence is `/tmp/cycle93_evidence.json`.
- The exact two-tet same-side fixture was passed directly to
  `flow3._face23_candidate`.  It rejected with `orientation`; this is the
  required convex-bipyramid / signed-volume tiling guard, not a tolerance
  relaxation.  The opposite-side control returned `ok` and a `(3, 4)`
  candidate.
- Therefore a direct `2→3` flip of the offending same-side face is not a
  legal repair.  This does not claim a bounded neighboring-face sequence is
  impossible.
- Current blockers: sidedness audit exposes aggregate counts only (no
  deterministic same-side witness selector); `flip_edges_32` scans rather
  than exposes a targetable `3→2` candidate; and the generic boundary check
  compares boundary keys/area only, not source-component/facet provenance.

### Release state

- No code, default, strict-topology, or Gate change.  Gates 1--15 remain
  unmet.
- Next action: design one bounded source-locked neighboring-face sequence;
  after every speculative candidate require source component bijection,
  source faces preserved, unowned faces `0`, inversion `0`, non-increasing
  ambiguity, and strictly reduced same-side debt, otherwise exact rollback.
  No topology or predicate relaxation.
- `allowed_to_stop: false` remains binding.

## Cycle 94 pre-merge checkpoint -- 2026-07-31

### Tet cube CVT-off one-hop local-flip probe

- The first runner execution (`c1`) is `UNVERIFIED`: it reproduced with CVT
  enabled and found no same-side target.  It supplies no correctness result.
- Corrected explicit `AUTO_TESSELL_CVT3D_OFF=1` probes passed at concurrency
  `1`, timeout `60 s`: `c2` in `5.55 s` and asserted `c3` in `5.54 s`.
  Evidence: `/tmp/cycle94_c2_evidence.json` and
  `/tmp/cycle94_c3_evidence.json`.
- First deterministic target: face `(195, 196, 241)`, owners `(499, 526)`,
  apexes `(242, 189)`, signs `(-1, -1)`.  Base global audit has same-side
  `4`, ambiguity `4`, inversion `0`, source bijection `true`, source faces
  preserved `false`, and unowned faces `9`.
- Its complete capped one-hop neighborhood has six faces.  All six direct
  `2→3` candidates rejected with `orientation`; there was no legal candidate
  for a post-candidate source/ambiguity/inversion audit.  No multi-hop or
  broad search was run.

### Release state

- No current-API code card: wiring the existing `2→3` operation cannot enter
  this target neighborhood.  No code, default, strict-topology, or Gate
  change; Gates 1--15 remain unmet.
- Next action requires a targetable `3→2` operator or a different bounded
  cavity, plus independent source-boundary repair.  Any future candidate
  remains fail-closed under the existing source, inversion, ambiguity, and
  same-side contracts; no relaxation.
- `allowed_to_stop: false` remains binding.

## Cycle 95 pre-merge checkpoint -- 2026-07-31

### Independent fixed-pair Tri+Quad transaction L0

- `c41c9299` adds an independent fixed-pair mixed-surface transaction;
  `13c65e36` requires authoritative source patch payloads before any
  materialization.  This is not a `native_quad_dominant` relabel or a
  triangular handoff.
- The explicit pair plan must be nonempty and non-total.  The transaction
  derives at least one quad and at least one residual triangle from immutable
  source triangles, then retains separate read-only arrays, source ordinals /
  pairs, and derived patch and physical-group payloads plus hashes.
- Authoritative patch IDs, physical groups, and feature edges are required.
  No-op/full-pair plans, malformed or cross-payload pairs, feature removal,
  source nonmanifold topology, and source-contract failures reject
  fail-closed.  The enabled result remains `unwritten` and
  `product_claimed=false`; no dedicated writer exists yet.
- First focused runner (`c1`) is `ERROR` / `UNVERIFIED` in `5.91 s` because a
  rejection preflight constructor field was missing.  It supplies no pass.
  Final advisor runner passed at concurrency `1` in `4.03 s` with `10`
  focused tests.  Local final `c5` also passed in `4.19 s`.

### Release state

- Default remains OFF.  No pipeline, UI, writer, routing, `third_party/`, or
  Gate change; Gates 1--15 remain unmet and no Gate is `PASS`.
- Next action: a dedicated Tri+Quad writer transaction and its explicit route
  only after a writer artifact contract preserves the separate arrays and all
  source bindings.  No triangular conversion or quad-dominant promotion.
- `allowed_to_stop: false` remains binding.

## Cycle 96 pre-merge checkpoint -- 2026-07-31

### Tri+Quad atomic artifact writer L0

- `a85ba923` adds a dedicated default-OFF writer for an already admitted
  fixed-pair Tri+Quad product.  It accepts no pipeline handoff and neither
  calls another surface producer nor triangulates quads.
- A same-parent mode-`0700` staging directory holds separate immutable
  `vertices`, `triangles`, `quads`, triangle-source-index, and quad-source-
  pair arrays.  The canonical manifest binds source hashes, provenance,
  authoritative payloads, per-file digests, and a content hash.
- Files and staging directory are synced; exact readback verifies manifest,
  payloads, dtypes, shapes, file hashes, and array bytes before atomic
  publication.  Disabled, non-admitted, preexisting, symlink, write-failure,
  and readback-failure paths publish no artifact and remove only owned staging.
- Advisor runner `c1` passed at concurrency `1` in `4.34 s` with `4` focused
  tests.

### Release state

- No pipeline, UI, OpenFOAM, default route, product claim, or Gate change.
  Gates 1--15 remain unmet and no Gate is `PASS`.
- Next action: independent product dispatch and a user-facing artifact
  contract, explicitly requested and never default-on.  Preserve the separate
  Tri+Quad arrays; no triangular conversion or quad-dominant promotion.
- `allowed_to_stop: false` remains binding.

## Cycle 97 pre-merge checkpoint -- 2026-07-31

### Explicit Python-only Tri+Quad dispatch L0

- `030a15e5` adds an explicit Python-only dispatch request/result boundary for
  the independent fixed-pair Tri+Quad product.  It is runtime-disconnected and
  has no CLI, UI, pipeline, plugin, OpenFOAM, or default-route registration.
- The request carries exact source vertices/triangles, canonical partial pair
  plan, authoritative feature edges, authoritative patch IDs, authoritative
  physical groups, and a fresh output target.  Dispatch materializes first;
  it calls the writer only when the admitted product and both explicit product
  and writer gates are enabled.
- With both gates off no writer runs and no artifact exists.  With product-only
  enablement the accepted product remains unwritten.  With both gates enabled,
  the atomic artifact has separate triangle/quad/provenance arrays and a
  manifest.  Bare/non-authoritative payloads reject before writing; a
  preexisting target rejects without overwrite.
- Every result remains `route_selected=false`, `ui_claimed=false`, and
  `product_claimed=false`.  This is not a native-Tri, strict-Quad, or
  `native_quad_dominant` claim, relabel, conversion, or default change.
- Advisor runner `c1` passed at concurrency `2` in `4.41 s` for `15` focused
  product/writer/dispatch tests; focused ruff, black, and local strict mypy
  also passed.  Full strict mypy is `ERROR` / `UNVERIFIED`: `1011` baseline
  errors across `119` imported files in `69.67 s`; it is not a pass claim.

### Release state

- No Gate changes to `PASS`; Gates 1--15 remain unmet.  No `third_party/`
  change is included.
- Next action: define a public authoritative-source ingress and independent
  route contract; do not infer authority or alter existing native-Tri,
  strict-Quad, or default behavior.
- `allowed_to_stop: false` remains binding.

## Cycle 98 pre-merge checkpoint -- 2026-07-31

### Independent strict-Quad product, artifact, and dispatch L0

- `fa80b24f` binds the fixed-pair strict-Quad product to authoritative source
  physical groups.  Missing, bare, non-authoritative, or mixed-pair group
  payloads fail closed.  The immutable product retains canonical quad source
  pairs and groups plus source patch, physical-group, feature, and provenance
  hashes; no Tri+Quad product is reused.
- Phase-A's first runner is ruff `ERROR` / `UNVERIFIED` from two import-order
  findings; it supplies no pass.  After the local import-only repair, final
  Phase-A runner passed at concurrency `2` in `4.56 s`.
- `dc848f25` adds a separate default-OFF strict-Quad writer.  An accepted
  strict product only is atomically staged/read back and published to a fresh
  non-symlink target.  Its artifact contains exactly `vertices.npy`,
  `quads.npy`, `quad_source_pairs.npy`, and `manifest.json`; there is no
  triangle array or Tri+Quad conversion.  Phase-B advisor runner passed at
  concurrency `2` in `4.10 s`.
- `c48bc40a` adds an explicit Python-only dispatch request.  It requires exact
  source arrays, canonical full pair plan, features, authoritative patch IDs
  and physical groups, and a fresh target.  It materializes first and calls
  the writer only after accepted product admission and both explicit gates.
  Phase-C advisor runner passed at concurrency `2` in `3.99 s`.
- All paths remain runtime-disconnected with no native-Tri, Tri+Quad, default,
  UI, pipeline, plugin, OpenFOAM, or public-route claim.

### Release state

- No Gate changes to `PASS`; Gates 1--15 remain unmet.  No `third_party/`
  change is included.
- Next action: define real external authoritative-source ingress and an
  independent strict-Quad route contract; do not infer authority or alter
  existing product defaults.
- `allowed_to_stop: false` remains binding.

## Cycle 99 pre-merge checkpoint -- 2026-07-31

### Native-Tri actual-product authority audit

- No code change.  The current explicit native-Tri L2 route copies source
  vertices and faces, returns `accepted=false`, and records
  `source_contract_unavailable` (or unsupported boundary layers).  Equal
  source/output hashes and identity provenance prove only that fail-closed
  clone, not an independent native-Tri product.
- The L0 candidate certificate accepts only byte-exact source vertices/faces
  and identity one-source-face provenance.  It therefore rejects every
  topology-changing candidate.  The actual-output diagnostic remains
  `accepted=false`, `mesher_success_allowed=false`, and
  `product_claimed=false` even for the exact clone.
- The L1 source diagnostic can record optional raw patch IDs and feature edges
  for clone evidence, but it has no authoritative patch/feature wrappers, no
  physical-group authority, no output patch/group payload, and no public route
  ingress.  There is no real operator transaction, whole-triangle envelope,
  or split/collapse provenance contract for an edited TRI result.
- Consequently no native-Tri writer or dispatch was added: emitting the
  current clone as an actual product would be a false no-op/topology-change
  claim.  No strict-Quad or Tri+Quad product is reused.

### Release state

- No Gate changes to `PASS`; Gates 1--15 remain unmet.  No `third_party/`
  change is included.
- Native-Tri product next action: require a real operator transaction with
  authoritative source patch/feature/physical evidence, exact edited-face
  provenance, and whole-triangle envelope proof before any writer.  Campaign
  next action: clean native Release build evidence.
- `allowed_to_stop: false` remains binding.

## Cycle 100 pre-merge checkpoint -- 2026-07-31

### Fresh native Release build evidence

- No code change.  Fresh build root `/tmp/autotessell-cycle100-release` used
  source `tessell-mesh`, Release configuration, Python/tests `OFF`, and
  parallelism `2`.
- Advisor runner `c1`: configure `PASS` in `43.52 s`; build `PASS` in
  `114.54 s`.  Produced native artifacts include `libtessell_mesh_core.a` and
  `geogram`.
- Gate 2 remains `UNVERIFIED`: this one clean configuration does not establish
  the supported native configuration/build matrix.

### Release state

- No Gate changes to `PASS`; Gates 1--15 remain unmet.  No `third_party/`
  change is included.
- Next action: inventory supported native configurations and run their clean
  builds before any Gate-2 promotion claim.
- `allowed_to_stop: false` remains binding.

## Cycle 102 pre-merge checkpoint -- 2026-07-31

### First-party native Release profile clean build

- Cycle 101 was read-only supported-configuration inventory only; no ledger
  code card was created.  No code change in this cycle.
- Fresh `/tmp` first-party native Release profile used Unix Makefiles because
  Ninja was unavailable.  External adapters were all `OFF`; the declared
  eight-target contract was retained.
- Advisor runner: configure `PASS` in `3.03 s`; `native_build_evidence` build
  `PASS` in `30.50 s`; contract verification `PASS` in `0.06 s`.
- Gate 2 remains `UNVERIFIED`: declared record names Ninja, and supported
  configuration matrix/other-OS evidence remains absent.  Unix Makefiles is
  measured evidence, not an invented generator-neutral support claim.

### Release state

- No Gate changes to `PASS`; Gates 1--15 remain unmet.  No `third_party/`
  change is included.
- Next action: acquire and verify Ninja only with authorization, or define
  generator-neutral support evidence before relying on this Release profile.
- `allowed_to_stop: false` remains binding.

## Cycle 91 pre-merge checkpoint -- 2026-07-31

### Tet cube CVT-off same-side audit

- The first `/tmp` runner probe had a missing workspace `PYTHONPATH` and is
  `UNVERIFIED`; it supplies no correctness result.  The corrected bounded
  runner passed at concurrency `1` in `7.12 s`.
- Transaction candidate evidence: source component bijection `true`, source
  faces preserved `true`, unowned faces `0`, inverted tets `0`, and same-side
  debt `4 -> 0`.  It still rolled back because ambiguous internal faces rose
  `4 -> 292` under the unchanged strict predicate.
- Post-rollback base evidence is separate: source faces preserved `false`
  (missing `12`, unowned `9`, area mismatch `1`, feature mismatch `1`, overlap
  pairs `2`); boundary has nonmanifold edges `4`, degenerate tets `1`, and
  ambiguous internal faces `4`.

### Release state

- Default behavior is unchanged.  No Gate `PASS`; Gates 1--15 remain unmet.
  Next action is no-relaxation ambiguity root cause and constrained
  connectivity only.
- `allowed_to_stop: false` remains binding.

## Cycle 90 pre-merge checkpoint -- 2026-07-31

### Tet cube same-side bounded evidence

- Selected cube `target_cells=2000` with BSP, edge recovery, Phase-B, and
  Phase-C disabled.  Advisor runner concurrency `1`: CVT ON took `2.82 s`;
  pre-CVT inversion was `34`, and candidate strict internal-face debt
  increased, so fail-closed with no artifact.
- CVT OFF with same-side opt-in took `2.93 s`; inversion was `0` and debt
  reduced `4 -> 0`, but the strict source contract rejected the candidate.
  The transaction rolled back and no artifact was written.

### Release state

- No code change and no Gate `PASS`.  Next action is to isolate the missing
  strict-source predicate in the CVT-off candidate only if topology remains
  unrelaxed.  Gates 1--15 remain unmet.
- `allowed_to_stop: false` remains binding.

## Cycle 89 pre-merge checkpoint -- 2026-07-31

### Tet same-side transaction integration

- `0889ea07` adds the actual opt-in sphere-path regression.  With
  `AUTO_TESSELL_TET_SAME_SIDE_RETRIANGULATION=1`, the transaction is accepted,
  strict topology is valid, source components are bijective, source faces are
  preserved, unowned faces and inverted tets are `0`, and same-side debt is
  strictly reduced before `polyMesh` is written.
- Advisor validation runner: `PASS`, concurrency `1`, `29.03 s`.  Default
  behavior remains unchanged.

### Release state

- This representative sphere result is not a Gate `PASS` or release claim.
  Gates 1--15 remain unmet; next action is representative strict-corpus
  validation.
- `allowed_to_stop: false` remains binding.

## Cycle 88 pre-merge checkpoint -- 2026-07-31

### Hex output boundary to B-Rep ordinal L0

- `536cd92e` adds a default-OFF, report-only source-triangle identity binding.
  It revalidates source snapshot/payload first, then requires exact boundary
  geometry, orientation, and B-Rep ordinal identity.
- Physical groups remain unknown.  Every report remains `accepted=false`; it
  creates no candidate, mesh output, route, or product claim.
- Actual Hex quad/new-vertex B-Rep binding remains `DEFER`: stable output IDs
  and an authoritative CAD surface witness are absent.  Advisor validation
  runner: `PASS`, concurrency `1`, `4.27 s`, three suites.
- Routing, defaults, C++, and `third_party/` remain unchanged.

### Release state

- Gates 1--15 remain unmet; no gate changes to `PASS`.
- `allowed_to_stop: false` remains binding.

## Cycle 87 pre-merge checkpoint -- 2026-07-31

### Hex reader snapshot provenance L0

- `16136736` adds an explicit exact-OFF, reader-owned provenance path.  It
  streams a private `0700` / `0600` source snapshot in `1 MiB` chunks, hashes
  and `fsync`s it, and lets the reader consume only that snapshot path.
- Snapshot cleanup and the canonical reader-payload digest are report-only.
  Strict B-Rep arrays/hashes/coverage remain required; physical groups are
  exactly unavailable.  Every result remains nonaccepting with no candidate,
  mesh, or artifact.
- Advisor validation runner: `PASS`, concurrency `1`, `4.23 s`, three suites.
  Routing, defaults, C++, and `third_party/` remain unchanged.

### Release state

- Output-boundary -> B-Rep remains `DEFER`; no physical or output-product
  claim is made.  Gates 1--15 remain unmet; no gate changes to `PASS`.
- `allowed_to_stop: false` remains binding.

## Cycle 86 pre-merge checkpoint -- 2026-07-31

### Hex CAD/B-Rep source-front authority L0

- `f07e284d` adds a default-OFF, runtime-disconnected report-only CAD/B-Rep
  source-front authority audit.  It validates the caller declaration before
  provenance, reader, candidate, or artifact access.
- The audit requires strict B-Rep authority arrays, hashes, and face-ordinal
  coverage.  Physical groups are accepted only as exactly unavailable; no
  physical-group claim is inferred.  Every result remains `accepted=false`,
  `candidate=false`, `mesh=false`, `artifact=0`.
- Advisor validation runner: `PASS`, concurrency `1`, `6.06 s`, three suites.
  Routing, defaults, C++, and `third_party/` remain unchanged.

### Release state

- Source-byte -> reader-payload and output-boundary -> B-Rep bindings remain
  `DEFER`; no generated Hex source certificate or physical-group authority is
  claimed.  Gates 1--15 remain unmet; no gate changes to `PASS`.
- `allowed_to_stop: false` remains binding.

## Cycle 85 pre-merge checkpoint -- 2026-07-31

### Tet Cycle-78 cleanup proof

- `codex/native-tet-cycle78-whole-p3-bypass` at
  `2c949ffbe02ce58c07376e402d870394809ad8b0` is an ancestor of `master`;
  `master-only=44`, `branch-only=0`.  It has no unique research evidence and
  is eligible only for normal `git branch -d` cleanup, never force removal.
- Strict Tet source/topology evidence remains Git-reachable in `master`; this
  proof makes no runtime-policy change.

### Release state

- Gate 1 receives no `PASS` while the protected Poly branch and tracked
  installer remain.  Gates 1--15 remain unmet.
- `allowed_to_stop: false` remains binding.

## Cycle 84 pre-merge checkpoint -- 2026-07-31

### Poly cleanup proof

- `codex/poly-cycle-cleanup-verify` at
  `a367cbd9d1ad26dd2084cf2c136319764bdc2cc5` is clean and an ancestor of
  `master`; `master-only=18`, `branch-only=0`.  It has no unique research
  evidence, so its worktree and branch are eligible only for normal
  `git worktree remove` and `git branch -d` cleanup, never force removal.
- Protected `codex/native-poly-cycle41-solid-volume-timeout-1` remains
  retained and untouched.

### Release state

- Gate 1 remains `FAIL` because protected research state and the tracked
  installer remain.  No gate changes to `PASS`; Gates 1--15 remain unmet.
- `allowed_to_stop: false` remains binding.

## Cycle 83 pre-merge checkpoint -- 2026-07-31

### Tri+Quad geometry/topology binding L0

- `85d35124` adds a default-OFF, runtime-disconnected actual-output
  geometry/topology diagnostic.  It layers Cycle-81 pair/residual provenance
  and Cycle-82 payload evidence with explicit authoritative feature edges,
  exact oriented boundary equality, edge/vertex manifold checks, component and
  Euler equality, and immutable-array checks.
- Disabled, incomplete, malformed, non-authoritative, duplicate, reversed,
  non-source, removed-feature, tampered, and nonmanifold inputs reject.  A
  complete row remains `accepted=false` and `product_claimed=false`.
- No routing, default, C++, or `third_party/` change is included.  Advisor
  validation runner: `PASS`, concurrency `1`, `4.68 s`, two focused suites.

### Release state

- Gates 1--15 remain unmet; no gate changes to `PASS`.
- `allowed_to_stop: false` remains binding.

## Cycle 82 pre-merge checkpoint -- 2026-07-31

### Tri+Quad payload-binding L0

- `69e7cb99` adds a default-OFF, runtime-disconnected actual-output
  payload-binding diagnostic.  It validates explicit source/output patch and
  authoritative physical-group payloads against Cycle-81 exact pair/residual
  provenance.
- Missing, malformed, non-authoritative, mixed-pair, reordered, or mismatched
  payloads reject.  A complete payload binding still records
  `accepted=false` and `product_claimed=false`.
- No routing, default, C++, or `third_party/` change is included.  Advisor
  validation runner: `PASS`, concurrency `1`, `5.84 s`, two focused suites.

### Release state

- Gates 1--15 remain unmet; no gate changes to `PASS`.
- `allowed_to_stop: false` remains binding.

## Cycle 81 pre-merge checkpoint -- 2026-07-31

### Tri+Quad output provenance L0

- `8b4ea112` adds canonical accepted triangle-pair provenance and residual
  triangle source-index provenance to actual `native_quad_dominant` output.
  Output vertices, triangles, quads, and diagnostics remain byte-identical in
  value and order.  Every source triangle is partitioned exactly once.
- Actual-output diagnostic records exact face-partition facts, but remains
  `accepted=false` and `product_claimed=false`.  Missing hard source evidence
  is feature, boundary, topology, physical group, and provenance; there is no
  `tri_quad` success/relabel or strict-quad change.
- No routing, default, C++, or `third_party/` change is included.  Advisor
  validation runner: `PASS`, concurrency `1`, `4.53 s`, three focused suites.

### Release state

- Gates 1--15 remain unmet; no gate changes to `PASS`.
- `allowed_to_stop: false` remains binding.
