# Surface product routing evidence — 2026-07-31

## Card state

`PARTIALLY_UNBLOCKED / CORRECTNESS_KEEP`.  Explicit CLI/pipeline route
identities now exist, but strict QUAD and TRI+QUAD remain fail-closed until
their source-product certificates exist.  GUI selection remains deferred.

## Product registry versus user route

`SurfaceProductMode` has three distinct semantic labels: `tri`, `quad`, and
`tri_quad`.  This is a report-only representation contract, not an exposed
surface-mesher selection.

The CLI and L2 pipeline expose distinct `native_tri`, `native_strict_quad`,
and `native_tri_quad` identities.  `native_tri` uses its existing explicit
fail-closed source contract.  Strict QUAD and TRI+QUAD return the input
unchanged with `source_product_certificate_required`; neither route borrows
`native_quad_dominant`.

The desktop L2 selector still exposes `native_isotropic`, `native_cvt`, and
`disabled`; GUI exposure remains deferred rather than silently aliasing a
different product.

## Strict-quad safety result

`native_quad_dominant` is permanently classified as `candidate_mixed`, even
when a particular input happens to leave zero triangle remainder.  A strict
`quad` request for that producer fails with
`representation_not_strict_quad`.  It cannot obtain a strict-quad certificate
from the representation contract.

## Unblock condition

Add three explicit, separately named user-facing route values with an
end-to-end request-to-producer mapping: native TRI, strict QUAD, and TRI+QUAD.
The strict QUAD route must require the strict product certificate and reject
candidate-mixed/triangular handoff payloads.  The TRI+QUAD route must retain
its separate representation.  Add CLI/UI/routing integration tests and source
certificate validation before product promotion.
