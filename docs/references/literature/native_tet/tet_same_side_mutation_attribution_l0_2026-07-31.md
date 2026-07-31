# TET-SAME-SIDE-MUTATION-ATTRIBUTION-L0

Date: 2026-07-31
State: `L1_PASS / CORRECTNESS_KEEP`; report-only remedy research.

## Hypothesis

The first same-side internal face can be attributed pre- or post- a named
non-source candidate mutation only if audit-call metadata explicitly contains
that mutation name and boundary phase.  Existing L1 records preserve audit-call
order but intentionally do not carry a mutation marker.  Therefore they must
produce `defer_insufficient_mutation_metadata`, not a guessed root cause.

## Evidence table

| First same-side call evidence | Classification | Runtime effect |
|---|---|---|
| named marker, `pre` | `pre_named_non_source_mutation` | none |
| named marker, `post` | `post_named_non_source_mutation` | none |
| marker absent or `unattributed` | `defer_insufficient_mutation_metadata` | none; add a separate marker-only card first |
| no same-side call | `no_same_side_observed` | none |

The L0 marker name `cvt3d_candidate_relocation` is an example boundary label:
CVT3D relocates candidate coordinates while retaining connectivity.  It is not
claimed to be a topological repair and the name does not change production
behavior.  Future topology-mutator labels require the same explicit pre/post
evidence.

Every result carries `runtime_classification_unchanged=true` and
`same_side_relaxation_authorized=false`.  A post marker is causal ordering
evidence only; it never relaxes same-side rejection.

Malformed metadata fails closed with `ValueError`: non-integral, boolean, or
negative call/count fields; non-enum phase values; blank names; a name on an
unattributed row; or a missing name on a pre/post row.  Only valid unnamed
`unattributed` metadata reaches `DEFER`.

## L0 and L1

L0 supplies hand-authored named pre/post audit metadata and an unattributed
event.  Both named positions classify exactly; missing metadata explicitly
defers.

L1 reuses three isolated cube (10,000 cells) and sphere (2,000 cells) initial-
overlap evidence workers.  Current records carry no mutation markers, so they
are only `DEFER` or `NO_SAME_SIDE_OBSERVED`.  This is expected: audit-call index
alone cannot establish causality.  Generator results remain failures and no
`constant/polyMesh` artifact may exist.  Cube's refusal text and 5,913 cells
remain legacy guards, not target-cell policy.

Timeout is `UNVERIFIED`, never a stage attribution.

## Scope and rollback

Only this report-only diagnostic, test, and evidence note change.  No
generator, predicate, threshold, strict refusal, writer, transaction, routing,
default, target-cell, CMake, or `third_party/` code changes.

Kill or roll back if call order is guessed, a `DEFER` becomes an attribution,
same-side is relaxed, a writer artifact appears, or the diagnostic changes
runtime behavior.

## Research and provenance

Klingner and Shewchuk, *Aggressive Tetrahedral Mesh Improvement* (2007), DOI
`10.1007/978-3-540-75103-8_1`, motivates per-operation rather than aggregate
quality evidence.  This card uses only first-party audit records; no external
implementation is copied.

## Reproduction

```bash
/home/younglin90/work/claude_code/AutoTessell/.venv/bin/python -m pytest -q \
  tests/test_native_tet_same_side_mutation_attribution_l0.py \
  tests/test_native_tet_initial_overlap_source_l1.py \
  tests/test_native_tet_final_strict_topology_checkpoint.py
git diff --check
```

This card establishes no remedy, topology mutation, validity, target-cell,
boundary-layer, or release claim.
