# HEX-WALLFIT-PARETO-PROVENANCE-DIAG2

Date: 2026-07-30

## Scope

This is a `CORRECTNESS_KEEP` / report-only continuation of
`HEX-WALLFIT-PARETO-1`.  It changes neither the wall-fit transaction nor any
generator default.  The compact runner is:

```bash
.venv/bin/python scripts/diag_hex_transition_quality1.py --compact
```

It executes the existing candidate-quality and transition-quality diagnostic
lanes for cylinder, sphere, gear, and bracket at the reproducible 2,000-cell
setting by default.  `--max-cells 500 --shapes cylinder` is the inexpensive
canonical smoke setting.

## What is reported

For every shape the runner reports the final checker gate and the candidate
Pareto summary: candidate count, frontier size, distance-improving candidates,
strict/p95/combined non-regressions, maximum local skew/warpage deltas, and
boundary face-key/area deltas.  This keeps the wall-distance and local-quality
axes separate; it does not create a scalar acceptance score.

The runner also reports an explicit refusal:

```
candidate_provenance=UNAVAILABLE
```

Candidate records carry only vertex and incident-cell ownership.  They do not
carry source-patch or sharp-feature provenance, so bracket candidates cannot
be selected for surgery or shape-adaptive dispatch.  This is intentional
fail-closed behavior, not evidence that all candidates share `defaultWall`.

## L0/L1 verification

`tests/test_native_hex_wallfit_quality.py` passed (`4 passed`) after extending
the audit assertion to cover the recorded area delta and Pareto frontier.
The 500-cell cylinder L1 run measured 128 candidates and a frontier of 20.
All 128 reduced distance, all 128 had a local quality regression, no candidate
changed the boundary face-key set, and no negative volume was reported.  The
candidate-local area changes are reported rather than hidden (maximum absolute
delta `0.0111766073`); they are not a permission to relax the final surface
area gate.

The final 500-cell cylinder checker remained a truthful `FAIL` because its
maximum boundary skew was `2.73027265`, above its active gate.  This is a
known quality limitation, not a regression caused by the report-only card.

## L2 four-shape measurement (500-cell setting)

| shape | candidates / frontier | distance improved / quality regressed | face-key changes | final max skew | final verdict |
|---|---:|---:|---:|---:|---|
| cylinder | 128 / 20 | 128 / 128 | 0 | 2.730273 | FAIL |
| sphere | 128 / 68 | 128 / 104 | 0 | 2.851834 | PASS |
| gear | 271 / 76 | 253 / 186 | 0 | 1.389971 | FAIL |
| bracket | 125 / 38 | 112 / 75 | 0 | 360.024191 | FAIL |

All four runs reported zero final negative volumes.  Candidate-local area
changes were observed and are exposed by the runner; they do not alter the
final fidelity gate.  The bracket's extreme skew and unavailable provenance
are a conservative refusal of repair, not a basis for selecting a pillow or
transition operation.

## Decision

`L2 measured / CORRECTNESS_KEEP`.  The small-budget frontier is shape-dependent;
existing four-shape 2,000-cell evidence remains the promotion-relevant coverage
result and is also not sufficient for a global policy.  Do not promote wall-fit,
add a global threshold, relax face-key/area/signed-volume/determinism gates, or
open bracket repair until source-patch and feature provenance is retained.
