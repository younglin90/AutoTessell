# TET-DEGENERATE-REMOVAL-SOURCE-TRANSACTION-1

## Scope

Guard the existing BETA2825 signed 3-2, interior-collapse, and coplanar-flap
candidate as one fail-closed transaction.  The algorithm, thresholds, source
coordinates, and later strict-writer oracle are unchanged.

## Root-cause trace

The earlier `TET-SPHERE-POST-SMOOTH-PROVENANCE-ROOTCAUSE-1` trace isolated
candidate-stage risk: local degeneracy removal is permitted to change tet
connectivity while the original area and absolute-volume checks do not prove
source component ownership.  A local quality or degeneracy reduction cannot
compensate for lost source-face provenance or a new inversion.

The deferred Phase-A experiment remains outside the repository:

- archive: `/mnt/d/AutoTessell-cleanup-backup-20260730/research-bundles/tet45-phase-a-smoothing-deferred-20260731.patch`
- SHA-256: `fbe9c4f8785b8c480bb840b3a61d8fd547450e5cff40c50fb787c50b0f81b450`

## Commit contract

The candidate is committed only when all independent conditions hold against
the immutable input arrays:

1. `audit_source_component_bijection(...).bijective == true`
2. `source_faces_preserved == true`
3. `n_unowned_candidate_faces == 0`
4. `candidate_inverted_tets <= before_inverted_tets`

Any failed condition returns the exact pre-candidate points and tets.  The
transaction performs no geometry repair, deletion beyond the existing
candidate, threshold relaxation, or source movement.

## Evidence

L0 uses a closed source tetrahedron:

- unchanged candidate commits;
- duplicate/opposite tet candidate rolls back after component/provenance and
  inversion failure;
- winding-only inversion rolls back even though provenance remains valid.

L1 records the live BETA2825 candidate at the Cube and Sphere 2k paths.  It
requires a source certificate and non-increasing inversion count at commit
time.  The existing cylinder regression repeats the transaction three times
and requires identical transaction reports and mesh hashes.

## Acceptance boundary

This card is `CORRECTNESS_KEEP` only.  It does not claim strict-topology,
mesh-validity, target-cell, boundary-layer, or release-gate success.  Final
source-aware strict topology remains the hard writer gate.

## Reproduction

```bash
pytest -q \
  tests/test_native_tet_degenerate_removal_source_transaction.py \
  tests/test_native_tet_final_strict_topology_checkpoint.py \
  tests/test_native_tet_result_consistency.py
```
