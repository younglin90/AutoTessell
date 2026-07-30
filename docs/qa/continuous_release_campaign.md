# Native Engine Continuous Release Campaign

## Campaign ledger

- campaign_id: `native-release-20260730`
- state: `CAMPAIGN_ACTIVE`
- cycle: `1`
- policy: `shape-preservation > validity > provenance > boundary layers > cell count > quality > reproducibility > performance`
- current_master: `b27f02d867d38ac900275d381214b4b85cc5c0b3`
- allowed_to_stop: `false`
- next_action: `TET-WRITER-INCIDENCE-1: eliminate native tet writer incidence defects on NACA without changing boundary provenance.`

This ledger records release evidence. `PASS` requires reproducible evidence, not a
focused-test result. A later Git state supersedes the repository checkpoint below.

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
- Poly target-forward L0 suite: `5 passed` in `12.19 s`; `target_cells` now
  reaches the BL=0 native-poly harness unchanged. Full native-poly suite timed
  out after `124 s`; target monotonicity and corpus tolerance remain unverified.
- Native tet L2 NACA diagnostic (`--native-primal --target-cells 2000`): output
  reported `3` cells without tetrahedron vertex incidence and `13` four-vertex
  cells without complete tetrahedron face encoding. Primary validity defect count: `16`.
- Same NACA baseline emitted `1827` cells for target `2000`; campaign-wide target
  tolerance is not yet declared or verified.
- Previous full `python tests/verify_goal.py` timed out after `124 s`; no full-suite claim.

### Gate status

| Gate | Status | Evidence / next evidence |
|---|---|---|
| 1 Repository | PASS | Cycle-1 checkpoint clean; re-evaluate every cycle. |
| 2 Build | UNVERIFIED | Fresh clean release build missing. |
| 3 Automated tests | UNVERIFIED | Full suite timed out; all engine/routing/UI coverage missing. |
| 4 Shape preservation | UNVERIFIED | No campaign corpus result. |
| 5 Mesh validity | FAIL | Native tet NACA writer incidence defects: `16`. |
| 6 Cell count | UNVERIFIED | Poly BL=0 forward L0 passes; NACA `1827/2000`; engine corpus/monotonicity missing. |
| 7 Boundary layer | UNVERIFIED | Focused state tests pass; engine corpus missing. |
| 8 Quality | UNVERIFIED | Campaign quality specifications and corpus missing. |
| 9 Reproducibility | UNVERIFIED | Three-run engine corpus missing. |
| 10 Robustness | UNVERIFIED | Hard-fixture matrix missing. |
| 11 Performance | UNVERIFIED | Baselines and budgets missing. |
| 12 Packaging | UNVERIFIED | Fresh-install smoke evidence missing. |
| 13 License/provenance | UNVERIFIED | GPL policy present; campaign inventory/evidence missing. |
| 14 Documentation/operations | UNVERIFIED | Release operational checklist missing. |
| 15 Release candidate | UNVERIFIED | Depends on Gates 1–14. |

## Active research queue

1. `TET-WRITER-INCIDENCE-1` — primary metric: native tet NACA incidence defects, lower is better, target `0`.
2. `POLY-TARGET-CONTRACT-1` — establish observable target-cell response while preserving source topology.
3. `TRI-QUAD-RELEASE-CARD-1` — select after independent source/test audit.
4. `FULL-VALIDATION-BASELINE-1` — split full-suite timeout into reproducible subsystem evidence.

## DOI and provenance record

Supplied PDFs indexed in `papers/PAPER_INDEX.md` and
`docs/references/literature/master_bibliography.csv`. Current campaign uses paper
ideas only; no external implementation code is copied. `third_party/` is out of
scope. Future MIT-core boundary follows
`docs/licensing/mit-core-transition-policy.md`.
