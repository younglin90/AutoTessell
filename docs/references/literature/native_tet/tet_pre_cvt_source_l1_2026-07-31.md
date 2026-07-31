# TET-PRE-CVT-SOURCE-L1

Date: 2026-07-31
State: `L1 evidence / CORRECTNESS_KEEP`; isolated test instrumentation only.

## Hypothesis

For the canonical cube and sphere configurations, the exact arrays entering the
first existing `lloyd_cvt_3d` call establish whether strict same-side debt was
already present before CVT.  This separates pre-existing topology debt from a
post-CVT candidate transition without changing the generator.

## Method

The test subprocess replaces only its local `cvt3d.lloyd_cvt_3d` symbol.  Before
the original function is called, it captures the first call's exact arrays with
the existing `capture_initial_strict_overlap_source_l1` audit/provenance record.
The original CVT call then receives its unmodified original arguments and its
result is returned unchanged.

The record contains source and candidate array hashes, same-side and ambiguity
counts, and existing source-face/component evidence.  It is evidence only: it
does not change strict classification, select a candidate, authorize rollback,
relax an acceptance rule, or write a mesh.

Cube and sphere use the existing 2,000-cell diagnostic settings and each runs
three isolated repeats.  The generator must remain unsuccessful and create no
`constant/polyMesh` artifact.  A missing first CVT call, timeout, malformed
record, or non-deterministic payload is `DEFER`, not evidence of clean input.

## Measured result

- Cube: before first CVT, same-side debt is `0`; ambiguity debt is `20`
  (`strict_ambiguity_without_same_side_overlap`).  The later CVT candidate
  still fails closed; this record does not make the ambiguous pre-state valid.
- Sphere: before first CVT, same-side debt is `108`; ambiguity debt is `0`
  (`same_side_overlap_source_provenance_debt`), with source provenance already
  failing.  CVT therefore cannot be assigned as the initial source of that
  debt.

Both values are exact three-run L1 assertions under the stated diagnostic
configuration.  Neither result permits a rollback, fallback, or relaxation.

## Scope

No generator, predicate, threshold, refusal, writer, transaction, routing,
target, boundary-layer, fallback, dependency, or `third_party/` behavior is
modified.  This card makes no topology remedy or release claim.
