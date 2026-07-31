# Tet whole-P3 bypass feasibility — 2026-07-31

## Scope

`UNVERIFIED / DEFER`.  The only safe existing whole-postprocessing seam is
`_phase_bc_skip`: setting `AUTO_TESSELL_PHASE_BC_SKIP=1` and a threshold of
`1.0` disables the documented Phase-B/C plus NNN/RRR/SSS/VVV post-processing
before invoking required P4-C fallback.  No production source, algorithm,
threshold, writer, routing, C++, or third-party code was changed.

## Bounded execution result

One isolated sphere skip worker was started with target 2000,
phase-B/phase-C/BSP/edge recovery disabled.  It did not produce evidence JSON
within the local Codex Desktop foreground hard limit of 64 seconds; the runner
was terminated by that limit while P4-C fallback was active.  Therefore this
card has **no valid current-vs-skip comparison** and no three-repeat result.

Do not infer source audit, inversion, same-side, quality, writer, success, or
determinism from this timeout.  They remain `UNVERIFIED` for whole-P3 skip.

## Decision

No production bypass candidate.  Run the retained diagnostic worker only in a
dedicated environment that permits P4-C completion for six isolated runs;
record timeout, source audit, validity, quality, writer, and hashes before any
policy proposal.  The collected fast regression only verifies that the
diagnostic uses the pre-existing `_phase_bc_skip` seam.
