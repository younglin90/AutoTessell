# POLY-BL0-FALLBACK-INVARIANT-1 Evidence

Date: 2026-07-31

Status: `DEFER / prerequisite`; the boundary-layer invariant is retained on
the research branch but is not eligible for `master` integration by itself.

## Failure isolation

The tier wrapper preserved `bl_layers=0` after the native-Poly harness failed,
but `generate_native_poly_voronoi` dropped that request at every direct
Voronoi inner call. The inner generator had no layer-count parameter and used
the process-wide `_TTT3_POLY_BL_EXTRUDE_ENABLE=True` switch. Any nonempty wall
adjacency therefore entered prism extrusion, including explicit BL=0 runs.

The preceding bounded cylinder run added 100 prisms, reported 7074
negative-volume cells after the boundary-layer passes, and timed out after 180
seconds.

## Mechanism

The public layer request is forwarded unchanged to every inner candidate,
including automatic escalation and repair retry paths. The inner generator
requires both a positive request and the existing feature switch before
extrusion. One and two layers remain exact. Requests above the existing safe
maximum are capped at two and emit `poly_bl_layers_reduced` with the requested
count, actual cap, and reason.

Primary metric: BL=0 prism-path entries and BL-induced negative-volume delta.
Acceptance is `1 -> 0` entries and `7074 -> 0` BL-induced negative volumes.

## Verification

- New L0 contract tests: `13 passed in 3.91s`.
- Pinned-compaction, tier target, and existing native-Poly regressions:
  `19 passed in 16.28s`.
- Production and test modules: `py_compile` passed.
- `git diff --check`: passed.
- Bounded cylinder node: timed out after 180 seconds.
- BL extrusion, prism, and `POL_LAYERS` log entries: zero.
- Original mask mismatch: zero.
- Last-resort reconstructed surface: absent.
- Child process leak: absent.

The invariant therefore works, but the cylinder still does not satisfy the
card's release boundary. Direct Voronoi produced an invalid grade-D candidate
with 4497 negative-volume cells, wrote about 7.3 MB of canonical polyMesh
files, then continued evaluating another invalid candidate until timeout.
This violates fail-closed, artifact-free refusal, and runtime requirements.

The next prerequisite must make best-of-N candidates transactional: isolated
temporary ownership, validity rejection before canonical promotion, atomic
promotion of the selected valid candidate only, and exact cleanup on refusal,
timeout, or exception. Until that card passes bounded validation, neither this
card nor `POLY-LLOYD-PINNED-COMPACTION-1` may be integrated.

Rollback conditions: BL=0 extrusion, incorrect positive layer count, silent
BL3+ behavior, shape/topology/provenance or validity regression, canonical
partial output, timeout, nondeterminism, or any `vendor/dependencies/` change.
