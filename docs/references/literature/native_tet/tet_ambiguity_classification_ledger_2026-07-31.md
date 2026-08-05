# TET-AMBIGUITY-CLASSIFICATION-LEDGER-1

Date: 2026-07-31

Status: `CORRECTNESS_KEEP / REPORT-ONLY`.  This card does not relax a writer,
candidate transaction, default, routing decision, quality threshold, source
certificate, or target-cell policy.

## Question

Native Tet's strict internal-face audit reports one aggregate
`n_ambiguous_internal_faces`.  That aggregate is necessary for fail-closed
publication, but it did not reveal whether a refusal came from a zero
orientation predicate or from a scale-floor classification with nonzero signs.
The latter is not by itself a license to publish: it may still be a tiny,
invalid tetrahedron or a same-side overlap.

The primary metric is diagnostic partition conservation:

```text
legacy_ambiguous
  = zero_tolerance_predicate_zero
  + floor_only_same_sign
  + floor_only_opposite_sign
```

No class makes `InternalFaceSidednessAudit.valid` true.  A nonzero legacy
ambiguity count still refuses final output.

## Mechanism

`audit_internal_face_sidedness` preserves its existing tolerant signs and
legacy ambiguous expression:

```text
(abs(volume6) <= 1e-12 * bbox_diagonal^3) OR tolerant_sign == 0
```

It adds a second, zero-tolerance predicate query for classification only.
The new fields are part of `InternalFaceSidednessAudit` only:

- `n_predicate_zero_internal_faces`: at least one zero-tolerance predicate
  sign is zero;
- `n_floor_only_same_side_internal_faces`: legacy ambiguous, both
  zero-tolerance signs are nonzero and equal;
- `n_floor_only_opposite_side_internal_faces`: legacy ambiguous, both
  zero-tolerance signs are nonzero and opposite.

The historical `n_ambiguous_internal_faces`, `valid`, `TetBoundaryAudit`,
candidate acceptance, `has_strict_writer_topology`, source topology,
provenance, and writer behavior are unchanged.  In particular,
`floor_only_same_side` remains a visible overlap risk, while
`floor_only_opposite_side` remains a diagnostic-only numerical-band result.

## Why no relaxation is promoted

Frozen cube target 10,000 returns 5,913 cells with final counts
`same-side=4`, `ambiguous=128`, and `degenerate=32`.  Its CVT candidate changes
`same-side 4 -> 12`, `ambiguous 128 -> 0`, and `degenerate 32 -> 0`.  The
candidate must remain rejected because it adds definite overlaps.  Fewer
ambiguities cannot pay for one same-side face.

The existing source-aware component rule already contains the only validated
topological calibration in this area: multiple disconnected boundary
components are locally valid only with exact source-to-candidate component
bijection.  It continues to reject lost, merged, split, unanchored, open,
non-manifold, duplicate, degenerate, inverted, or provenance-violating meshes.

## Acceptance and rollback

### L0

- valid opposite-apex face reports all three classes as zero;
- near-coplanar opposite signs classify as `floor_only_opposite_sign=1` and
  remain invalid;
- near-coplanar same signs classify as `floor_only_same_sign=1` and remain
  invalid;
- a zero sign classifies as `predicate_zero=1` and remains invalid;
- every case preserves the partition equation and strict writer refusal;
- three repeated zero-sign audits compare equal.

### L1

- frozen cube-10,000 keeps `ambiguous=128`, exact CVT rollback, failed result,
  and zero writer artifact;
- cube and sphere source-aware transaction fixtures repeat the audit three
  times on their returned arrays and conserve the aggregate count;
- source component, source face, immutable-coordinate, inversion, duplicate,
  and boundary checks remain independent hard evidence.

Rollback the card if a new category changes a legacy aggregate, any legacy
acceptance/refusal path, deterministic audit output, or source/validity
evidence.  No policy card may evaluate a practical ambiguity tolerance until
L1 shows its complete class distribution and separately proves zero inversion,
zero degeneracy, zero same-side faces, and intact source semantics.

## Research and provenance

Shewchuk, *Adaptive Precision Floating-Point Arithmetic and Fast Robust
Geometric Predicates*, 1997, DOI `10.1007/PL00009321`, supports separating
robust sign classification from floating-point magnitude diagnostics.  The
project's existing strict sidedness card also cites TetGen and uses the
first-party robust-predicate wrapper.  No external source code was copied;
`vendor/dependencies/` is unchanged.
