# Native Tet Provenance Interval L1 — 2026-07-31

## Card

Report-only immutable checkpoints narrow the previously observed sphere source
provenance-loss interval.  Default execution does not call an observer or
allocate snapshots.  No topology, quality, repair, fallback, writer, routing,
or target-cell policy changes.

## Result

Three isolated sphere workers are deterministic.  Source provenance passes at
all checkpoints through `post_eee_quality`, including `post_best_of`,
`post_nn1_collapse`, `pre_rr1_flip`, `post_rr1_flip`, and `pre_ddd1_bsp`.
It first fails at `pre_cvt3d`: missing source vertices `636`, missing source
faces `1280`.

Supported conclusion only: first observed source-provenance-loss interval is
`post_eee_quality` to `pre_cvt3d`.  No causal mutator is assigned.  Next card
must instrument only this remaining interval.

## Status

`L1_PASS / CORRECTNESS_KEEP`.  Checkpoint arrays are C-contiguous, immutable,
and observer errors are log-only.
