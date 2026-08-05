# TET-SPHERE-PROVENANCE-ROOTCAUSE-L1

Date: 2026-07-31
State: `L1 evidence / CORRECTNESS_KEEP`; test-only instrumentation.

## Hypothesis

Sphere's pre-first-CVT provenance debt can be assigned to the first existing
mesh-stage boundary that fails the current source component/facet audit.

## Method

The isolated test subprocess temporarily wraps only its own imported
`scipy.spatial.Delaunay` callable.  It records a candidate only when the direct
caller is the existing nested generator `_run_delaunay` boundary, so offset-ring
proxy calls do not count.  The wrapper first calls the original Delaunay with
unchanged arguments, then records the original returned simplices through the
existing immutable source-component/facet audit.  A second local CVT wrapper
records the pre-first-CVT state for comparison.  Read-only line tracing also
captures the existing post-sliver-filter and post-filter-compaction arrays; it
never changes a local, return value, or branch.

The current-audit conjunction is existing component bijection, source-face
preservation, and zero unowned candidate faces.  It is a diagnosis predicate,
not a new acceptance policy.

## Exact result and blocker

Three runs show the base Delaunay candidate, post-sliver-filter candidate, and
post-filter-compaction candidate all still satisfy the current source component
and facet predicate: component bijection and source faces preserved, zero
unowned candidate faces, zero same-side debt, and ambiguity debt `184`.

The first pre-CVT record is already failed (`108` same-side, `636` missing
source vertices, `1280` missing source faces, and `1280` unowned faces).
Therefore the first failing stage is not established by these existing stage
boundaries.

The exact blocker is the intervening Phase-A path: it contains multiple
optional/inlined point and tet rebindings without a stable callable commit or
audit boundary.  Attributing the first failure to one of those operations would
require adding production stage instrumentation or inventing a stage label.
Both are outside this report-only card.  Result: `DEFER`.

No generator, predicate, threshold, refusal, writer, transaction, routing,
fallback, target, boundary-layer, dependency, or `vendor/dependencies/` behavior is
changed.  No repair, rollback, or relaxation is authorized by this evidence.
