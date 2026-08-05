# TET-STRICT-OVERLAP-POLICY-L0

Date: 2026-07-31
State: `L1_PASS / CORRECTNESS_KEEP`; policy evidence only, runtime-disconnected.

## Hypothesis

The initial-overlap L1 record can make future research choices explicit without
changing the current strict internal-face contract.  A same-side face with
complete source-component and source-facet provenance is geometric overlap,
not tolerance noise: it is unrelaxable.  Ambiguity with zero same-side debt is
eligible only for a separately predeclared calibration study.  It is never
permission to change a predicate floor, accept a candidate, or publish output.

## Fixed policy table

| Existing L1 evidence | Evidence disposition | Runtime effect |
|---|---|---|
| `n_same_side_internal_faces > 0`, source provenance preserved | `unrelaxable_same_side` | none; retain strict refusal |
| `n_same_side_internal_faces > 0`, provenance debt also present | `unrelaxable_same_side` | none; retain refusal and diagnose provenance separately |
| ambiguity only | `future_calibration_eligible` | none; require an independent card and fresh hard gates |
| planar patch overlap/provenance debt without same-side | `provenance_repair_required` | none; not a threshold-calibration case |
| no debt observed | `no_strict_overlap_observed` | none |

Every evidence result explicitly carries `runtime_classification_unchanged=true`
and `runtime_relaxation_authorized=false`.

Precedence is fixed: same-side first, then any source/provenance debt, then
ambiguity-only calibration evidence.  An ambiguity count never masks missing
source faces or planar-patch overlap.

## L0 and L1 evidence

L0 exercises a hand-checkable same-side two-tet case retaining its exact six
source boundary faces, a near-coplanar ambiguity-only case, and a provenance
debt case.  The first is unrelaxable despite source preservation; only the
ambiguity row is future-calibration eligible, and still has no runtime effect.

L1 reuses the isolated initial-overlap recorder for cube (10,000 requested
cells) and sphere (2,000 requested cells), three times each.  Policy outputs
must be deterministic; both generator results remain failures and no
`constant/polyMesh` artifact may exist.  Cube's current refusal text and 5,913
returned cells remain legacy guards only, not target-cell policy.

Timeout is `UNVERIFIED`, never policy evidence.  If no same-side call is
observed, the table records `no_strict_overlap_observed`; it does not invent a
root cause.

## Scope and rollback

Only the report-only policy module, test, and this note change.  No generator,
predicate, threshold, strict refusal, transaction, writer, routing, default,
target-cell, CMake, or `vendor/dependencies/` file changes.

Kill or roll back if an evidence disposition changes runtime behavior, labels
same-side overlap calibration-eligible, allows output, alters L1 source data,
or treats a timeout as success.

## Provenance

Uses first-party initial-overlap evidence and no external code.  Shewchuk
(1997), DOI `10.1007/PL00009321`, remains context for keeping exact same-side
orientation separate from near-zero ambiguity; it does not justify relaxation.

## Reproduction

```bash
/home/younglin90/work/claude_code/AutoTessell/.venv/bin/python -m pytest -q \
  tests/test_native_tet_strict_overlap_policy_l0.py \
  tests/test_native_tet_initial_overlap_source_l1.py \
  tests/test_native_tet_final_strict_topology_checkpoint.py
git diff --check
```

This card establishes no tet repair, validity, target-cell, boundary-layer, or
release claim.
