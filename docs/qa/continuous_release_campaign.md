# Native Engine Continuous Release Campaign

## Campaign ledger

- campaign_id: `native-release-20260730`
- state: `CAMPAIGN_ACTIVE`
- cycle: `3`
- policy: `shape-preservation > validity > provenance > boundary layers > cell count > quality > reproducibility > performance`
- last_verified_master: `de60438a2ce942365be6c116999d29170356a786`
- allowed_to_stop: `false`
- next_action: `TET-VVV10-STRICT-TOPOLOGY-GATE1: reject topology-invalid flip_face_23 candidates before native tet writer acceptance.`

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

## Active research queue

1. `TET-VVV10-STRICT-TOPOLOGY-GATE1` — strict candidate topology defects, lower is better, target `0`.
2. `POLY-TARGET-REBUDGET-1` — cube BL0 target-band failures, lower is better, target `0`.
3. `LIC-NATIVE-CORE-PROVENANCE-MANIFEST-1` — unrecorded native bindings, lower is better, target `0`.
4. `FULL-VALIDATION-BASELINE-1` — run phase-attributed engine evidence without weakening gates.
5. `TET-VVV12-STRICT-TOPOLOGY-GATE1` — run only after VVV10 retest isolates residual defects.

## DOI and provenance record

Supplied PDFs indexed in `papers/PAPER_INDEX.md` and
`docs/references/literature/master_bibliography.csv`. Current campaign uses paper
ideas only; no external implementation code is copied. `third_party/` is out of
scope. Future MIT-core boundary follows
`docs/licensing/mit-core-transition-policy.md`.
