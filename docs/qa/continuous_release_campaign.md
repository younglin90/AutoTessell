# Native Engine Continuous Release Campaign

## Campaign ledger

- campaign_id: `native-release-20260730`
- state: `CAMPAIGN_ACTIVE`
- cycle: `6`
- policy: `shape-preservation > validity > provenance > boundary layers > cell count > quality > reproducibility > performance`
- last_verified_master: `a1be3c4761a6e21a38b84be52bf0f804f59cd56d`
- allowed_to_stop: `false`
- next_action: `parallel lanes: CMAKE-NATIVE-SURFACE-PADDING-TARGET-1, FACE-REMESH-EXPLICIT-ROUTING-1, TET-INPUT-VERTEX-L0-HELPER-RESTORE-1.`

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
