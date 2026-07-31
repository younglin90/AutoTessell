# Surface product routing evidence — 2026-07-31

## Card state

`DEFER / CORRECTNESS_KEEP`.  Test and documentation only.  No routing, UI,
product, threshold, acceptance, or mesh-output change.

## Product registry versus user route

`SurfaceProductMode` has three distinct semantic labels: `tri`, `quad`, and
`tri_quad`.  This is a report-only representation contract, not an exposed
surface-mesher selection.

The actual L2 pipeline recognizes `native_tri` and `native_quad_dominant`, but
has no `native_quad_strict` route and no separate `native_tri_quad_mixed`
route.  The desktop L2 selector exposes `native_isotropic`, `native_cvt`, and
`disabled`; it exposes none of those three product identities.  Therefore the
product identities are not three distinct user-selectable surface mesher
routes.

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
