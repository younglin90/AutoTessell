# TET-INITIAL-OVERLAP-SOURCE-L1

Date: 2026-07-31
State: `L1_PASS / CORRECTNESS_KEEP`; report-only and runtime-disconnected.

## Hypothesis

The first observed same-side internal face can be classified with the existing
source-component and planar-facet provenance audit without changing strict
topology policy.  This distinguishes a same-side debt whose input-surface
provenance remains exact from debt already accompanied by source provenance
loss.  It is evidence for a later policy decision, not evidence that the
strict constraint is too strong.

## Mechanism

The test wraps only the existing `audit_internal_face_sidedness` symbol in an
isolated subprocess.  It calls the original with unchanged positional and
keyword arguments first, then passes the already-audited arrays plus immutable
input surface to the report-only recorder.  Recording stops after the first
same-side result; the original audit continues for all later calls.

Each record stores exact source/candidate dtype-shape-byte hashes, call index,
internal-face counts, source-component counts, planar patch ownership/area/
feature evidence, overlap-pair count, and one evidence-only class:

- `same_side_overlap_source_provenance_preserved`;
- `same_side_overlap_planar_patch_overlap`;
- `same_side_overlap_source_provenance_debt`;
- ambiguity-only, planar-patch-only, or no-strict-overlap classes.

The recorder raises if any source/candidate array hash changes during either
existing audit.  It does not edit source coordinates, connectivity, predicate
tolerances, transactions, refusal behavior, target-cell policy, or output.

## L0 and L1 contract

L0 uses a hand-checkable two-tet shared-face fixture.  Same-side apexes retain
the exact six source boundary faces and classify as provenance-preserved strict
overlap; opposite apexes classify as no strict overlap.  Neither input array is
changed.

L1 runs the existing cube request (10,000 cells) and sphere request (2,000
cells) three times each in isolated interpreters.  It records the exact first
same-side call index/class and every preceding audit call.  Run signatures
include final result hashes, audit-call count, records, and first-overlap
record.  Results must remain failures with no `constant/polyMesh` artifact.
Cube preserves the current refusal string and 5,913 returned cells only as a
legacy guard, not a target-cell acceptance rule.

Timeout is `UNVERIFIED`, never success.  A missing same-side record is itself
durable evidence (`first_strict_overlap=null`), not a fabricated root cause.

## Scope and rollback

Only this diagnostic module, test, and evidence note change.  No generator,
predicate, strict refusal, writer, transaction, routing, default, CMake,
target-cell, or `third_party/` file changes.

Kill or roll back if recorder calls alter audit arguments/results, mutate an
array, allow an artifact, weaken a strict failure, fabricate a first overlap,
or make a policy decision from diagnostic classes.

## Provenance

Uses first-party `audit_internal_face_sidedness` and
`audit_source_component_bijection`.  Shewchuk (1997), DOI
`10.1007/PL00009321`, supports robust orientation as an independent diagnostic
dimension; no external implementation or generated output is copied.

## Reproduction

```bash
/home/younglin90/work/claude_code/AutoTessell/.venv/bin/python -m pytest -q \
  tests/test_native_tet_initial_overlap_source_l1.py \
  tests/test_native_tet_ambiguity_stage_ledger_l1.py \
  tests/test_native_tet_final_strict_topology_checkpoint.py
git diff --check
```

This card neither repairs overlap nor declares tet validity, cell-count
support, boundary-layer support, or release readiness.
