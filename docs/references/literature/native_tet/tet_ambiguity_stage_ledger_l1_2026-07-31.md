# TET-AMBIGUITY-STAGE-LEDGER-L1

Date: 2026-07-31
Status: `REPORT_ONLY / NO_POLICY_CHANGE`

## Purpose

This card measures the existing three-way partition of the legacy native-tet
internal-face ambiguity count at the mesher's already-existing
`check_boundary_invariant` checkpoints.  It does not import into the
generator, change any candidate, change a transaction, alter a threshold,
change target-cell behavior, or permit a writer result.

The only primary metric is this stage-level distribution:

```text
(predicate_zero, floor_only_same_side, floor_only_opposite_side)
```

The aggregate remains an invariant, not a relaxed policy:

```text
legacy_ambiguous
  = predicate_zero
  + floor_only_same_side
  + floor_only_opposite_side
```

Every nonzero aggregate remains invalid.  In particular, neither floor-only
class permits source publication, a transaction commit, or writer output.

## Durable evidence schema

Each JSON stage record has schema version
`native_tet_ambiguity_stage_ledger_l1/v1` and contains:

- fixture, repeat, stage index, and existing stage label;
- SHA-256 of `dtype + shape + C-order bytes` for points and tets;
- point/tet cardinalities;
- internal-face total, same-side count, legacy ambiguity count, and its three
  diagnostic classes;
- partition-conservation boolean;
- duplicate, non-manifold, degenerate, inverted, and existing audit-valid
  values;
- final result success/message, writer-artifact existence, and a canonical
  digest of the existing strict source certificates.

The record retains no raw mesh data and does not reserve or evaluate a cell
target.  A result-level hash is recorded separately so repeatability cannot be
mistaken for equal category totals alone.

## L0 and L1 evidence

L0 records the valid opposite-apex case plus the existing predicate-zero,
floor-only same-sign, and floor-only opposite-sign cases.  Their exact
categories must preserve the aggregate partition and remain invalid whenever
the aggregate is nonzero.

L1 runs cube (existing 10,000 request) and sphere (existing 2,000 request)
in three isolated Python processes each.  A test-only wrapper records only the
`after_points` and `after_tets` passed to each pre-existing boundary hook,
then immediately calls the original hook with its original arguments.  The
first run freezes the observed label sequence; subsequent runs must have the
same sequence, stage-array hashes, result hash, and primary distribution.

The 480-second per-worker budget is an evidence budget, not a pass condition.
A timeout fails the test explicitly as `UNVERIFIED`; it cannot become a
successful L1 result.

Cube additionally preserves the current L0 refusal string and 5,913 returned
cells only as a legacy-output guard.  It is not a target-cell acceptance band.
Sphere likewise preserves its existing failure/writer-refusal behavior.  The
source certificate digest is compared across repeats; source, writer, and
transaction semantics remain separate hard evidence.

## Acceptance and rollback

Accept only when L0 class records conserve the aggregate and all six isolated
L1 executions preserve final result, absent writer artifact, hook sequence,
stage-array hashes, source-certificate digest, and primary distribution.

Rollback the entire card if it changes a legacy aggregate, `valid`, final
result, source certificate, transaction, writer artifact, default, threshold,
or target policy; if recorder inputs mutate; if a checkpoint is absent; or if
any worker times out.  No ambiguity class may be used for a practical
tolerance policy until independent evidence proves zero inversion, degeneracy,
same-side debt, and intact source semantics.

## Research and provenance

Shewchuk, *Adaptive Precision Floating-Point Arithmetic and Fast Robust
Geometric Predicates*, 1997, DOI `10.1007/PL00009321`, supports recording
exact-sign classification separately from floating-point magnitude bands.
This card independently calls the project's existing first-party audit only.
No external implementation was copied and `third_party/` is unchanged.
