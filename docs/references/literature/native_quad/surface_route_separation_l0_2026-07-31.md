# Native surface route separation L0 — 2026-07-31

## Request identities

The CLI and L2 pipeline now expose exactly three explicit native surface
product requests:

- `native_tri`
- `native_strict_quad`
- `native_tri_quad`

They are distinct route identities.  Existing `native_quad_dominant` remains
its legacy candidate-mixed producer and is not an alias for strict QUAD.
Existing internal representation aliases remain unchanged.

## Fail-closed state

`native_tri` retains its existing source-contract rejection path.  The strict
QUAD and TRI+QUAD routes preserve source vertices/faces exactly and return
`source_product_certificate_required` until an authoritative source-product
certificate can prove source shape, feature, patch, physical-group, and
provenance preservation.  They do not construct a candidate, repair geometry,
triangulate a quad, or accept a product.

## Deferred UI

Desktop UI selection is not changed by this small routing card.  It must add
the same three explicit values and route-level tests in a scoped UI card; it
must not map strict QUAD or TRI+QUAD to `native_quad_dominant`.
