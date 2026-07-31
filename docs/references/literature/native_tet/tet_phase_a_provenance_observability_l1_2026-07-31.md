# Native Tet Phase-A Provenance Observability L1 — 2026-07-31

## Hypothesis

An optional report-only observer at fixed Phase-A boundaries can identify the
first *observed interval* in which the sphere source-provenance audit changes,
without changing native-tet result selection, topology, quality policy, or
writer behavior.

## Mechanism

`generate_native_tet(..., _phase_a_observer=...)` is a private, default-`None`
test seam.  The normal path makes no observer call and allocates no checkpoint
snapshot.  When supplied, the observer receives a frozen checkpoint containing
C-contiguous NumPy arrays backed by immutable bytes.  Observer exceptions are
logged and never change the generator result.

Stable checkpoints:

1. `post_filter_compaction`
2. `post_bsp_orient_fix`
3. `post_phase_a_smoothing`
4. `pre_cvt3d`

The last boundary is included to close the observed interval; it does not claim
that CVT caused any provenance change.

## L1 Result

Three isolated sphere workers produce identical evidence.

- `post_filter_compaction` and `post_bsp_orient_fix`: current source audit
  passes; same-side faces `0`; ambiguous internal faces `184`.
- `post_phase_a_smoothing`: current source audit still passes; same-side faces
  `120`; ambiguous internal faces `0`.
- `pre_cvt3d`: source audit fails; same-side faces `108`; missing source vertices
  `636`; missing source faces `1280`.

Therefore the only supported conclusion is an observed provenance-loss interval
after `post_phase_a_smoothing` and before `pre_cvt3d`.  The same-side debt's
first observed boundary is `post_phase_a_smoothing`, but source provenance still
passes there.  No causal mutator is assigned.  Further localization requires
independent checkpoints in the later optional passes.

## Scope

`L1_PASS / CORRECTNESS_KEEP`.  This is observability only.  No topology,
quality, target-cell, repair, fallback, rollback, routing, writer, or
third-party behavior changes.
