# TET-SPHERE-PRE-CVT-PROVENANCE-L1

Date: 2026-07-31
State: `L1 evidence / CORRECTNESS_KEEP`; report-only test instrumentation.

## Hypothesis

Sphere's same-side debt before the first CVT call is accompanied by a stable,
locatable component/facet provenance debt vector.  Recording that vector before
CVT distinguishes an already-invalid source relationship from any later CVT
candidate transition.

## Method

The isolated subprocess wraps only its local `cvt3d.lloyd_cvt_3d` symbol.  At
the first entry, it uses the existing immutable source/provenance audit record;
then it calls original CVT with unchanged arguments and returns its unchanged
result.  No production path imports the test.

The detailed display order is fixed only for diagnosis:

1. `n_missing_source_vertices`
2. `n_missing_source_faces`
3. `n_unowned_candidate_faces`
4. `n_uncovered_source_patches`
5. area mismatch, feature-boundary mismatch, overlap pairs

This ordering is not an acceptance priority, repair order, or relaxation rule.

## Exact three-run result

At the existing sphere `target_cells=2000` diagnostic configuration before first
CVT:

- component bijection: `false`; source faces preserved: `false`;
- same-side debt: `108`; ambiguity debt: `0`;
- missing source vertices: `636` (first detailed debt);
- missing source faces: `1280`;
- unowned candidate faces: `1280`;
- uncovered source patches: `1280`;
- area mismatch, feature mismatch, planar overlap: `0` each.

The generator stays unsuccessful with no `constant/polyMesh` artifact.  This
does not identify a safe repair, authorize CVT rollback, permit fallback, or
relax strict topology.  Any attempted implementation remains `DEFER` until a
source-preserving candidate proves the complete existing topology contract.

## Scope

No generator, predicate, threshold, refusal, writer, transaction, routing,
fallback, target-cell, boundary-layer, dependency, or `third_party/` behavior
changes.  No external code is used or copied.
