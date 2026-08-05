# TET-MUTATION-BOUNDARY-MARKER-L1

Date: 2026-07-31
State: `L1_PASS / CORRECTNESS_KEEP`; isolated test instrumentation only.

## Hypothesis

An existing strict-audit call can be attributed to a named non-source candidate
mutation without changing the generator if, and only if, a test subprocess
records exact C-order pre/post array fingerprints around that mutation.  The
strict-audit wrapper calls the original audit first, then attaches `pre` or
`post` only on one exact fingerprint match.  No match, multiple matches, or a
no-op candidate remains unattributed and downstream policy must defer.

## Marker contract

The L1 test patches only its subprocess copies of:

- `cvt3d.lloyd_cvt_3d`, to record changed candidate pre/post arrays under the
  name `cvt3d_candidate_relocation`;
- `rescue_gate.audit_internal_face_sidedness`, to call original arguments and
  result first, then append read-only metadata.

CVT3D relocation retains connectivity; it is a named candidate mutation, not a
topology repair claim.  The marker does not touch production imports,
transactions, strict refusal, thresholds, writer, routing, or target policy.

## L0 and L1

L0 proves exact pre/post labels, while unrelated and unchanged arrays remain
unattributed.  L1 runs cube and sphere at existing 2,000-cell requests three
times each in isolated interpreters.  Results must remain failures with zero
`constant/polyMesh` artifact; every attribution retains
`runtime_classification_unchanged=true` and
`same_side_relaxation_authorized=false`.

If the first same-side event has a unique post-CVT fingerprint, it is reported
as `post_named_non_source_mutation`.  If an earlier/unmatched event exists,
the result is explicitly `defer_insufficient_mutation_metadata`.  Neither
classification permits same-side relaxation.

Timeout is `UNVERIFIED`, not an attribution result.

## Scope and rollback

Only this report-only marker module, test, and note change.  No production
generator, predicate, threshold, strict refusal, writer, transaction, routing,
default, target-cell, CMake, or `vendor/dependencies/` code changes.

Kill or roll back if marker data is attached without exact unique hashes,
changes an original audit invocation/result, permits output, or changes
runtime classification.

## Provenance

Klingner and Shewchuk (2007), DOI `10.1007/978-3-540-75103-8_1`, motivates
per-operation evidence.  This card copies no external implementation.

## Reproduction

```bash
/home/younglin90/work/claude_code/AutoTessell/.venv/bin/python -m pytest -q \
  tests/test_native_tet_mutation_boundary_marker_l1.py \
  tests/test_native_tet_cvt3d_sidedness_transaction.py \
  tests/test_native_tet_final_strict_topology_checkpoint.py
git diff --check
```

This card establishes no remedy, validity, target-cell, boundary-layer, or
release claim.
