# Native tri product output certificate L0 — 2026-07-31

## Current product state

`run_native_tri_l2_route` is not an independent surface mesher yet.  It emits
an unchanged source clone and reports `accepted=false` while topology-changing
operators lack a whole-surface shape and provenance certificate.

## L0 actual-output binding

The new adapter evaluates the route's actual arrays and hashes against the
existing native-tri exact-clone certificate.  It requires all of:

1. source and output vertex hashes equal;
2. source and output face hashes equal;
3. route hashes equal the independently recomputed hashes;
4. source-envelope, topology, and provenance flags agree with that
   certificate; and
5. one unambiguous source-face reference per output face.

Any mismatch rejects as `native_tri_output_source_certificate_invalid` before
a product claim.  A correct clone still reports
`reject_native_tri_route_not_product_ready`; it has proved only no-op source
preservation, not a remeshed tri product.

Every adapter result is deliberately `accepted=false`,
`mesher_success_allowed=false`, and `product_claimed=false`.  This card does
not change strict quad, tri+quad, UI, routing, shared evaluator, meshing,
target count, boundary layers, quality thresholds, or `third_party/`.

Future promotion requires an actual native-tri operator output with whole
surface envelope, topology, feature/boundary, patch/physical-group, and
per-face provenance evidence.  It must not reuse this clone certificate as a
success proof.
