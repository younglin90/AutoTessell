# Quad-dominant actual output certificate L0 — 2026-07-31

## Scope

The existing `native_quad_dominant` pair merger can emit zero remainder
triangles on a fixture.  That fact alone is not strict-quad product evidence,
and its separate tri/quad arrays alone are not a released mixed-product
certificate.  This card adds a runtime-disconnected diagnostic over the
actual mesher result.

## Hard gates

The diagnostic verifies byte-exact source/output vertices when canonical arrays
are supplied.  It records SHA-256 identifiers for source vertices, source
triangles, output vertices, output triangles, and output quads.  It then keeps
the missing product evidence explicit:

- feature graph;
- boundary structure;
- topology;
- physical-group meaning; and
- face/patch provenance.

No current quad-dominant result emits those five bindings.  Therefore every
adapter result has `accepted=false`, `product_claimed=false`, and
`source_certificate_complete=false`.

## Product separation

- `quad`: actual quad-dominant output remains `candidate_mixed`, even with
  zero triangle remainder, and rejects as `representation_not_strict_quad`.
- `tri_quad`: representation-level candidate labeling may be valid, but the
  product output rejects with `quad_dominant_source_certificate_required`.
- `tri`: unchanged and independent; this adapter does not route or relabel it.

No mesh, threshold, source coordinate, feature, boundary, topology, patch,
physical group, evaluator, UI, routing, writer, target-cell, or boundary-layer
behavior changes.  `vendor/dependencies/` is unchanged.

## Evidence

The planar two-triangle square actual mesher output (`0T + 1Q`) is evaluated
three times.  Strict quad rejects deterministically.  Mixed rejects until a
producer binds every missing source fact.  A mismatched source vertex array
rejects before any product claim.

Future work: a producer-owned immutable source certificate must bind the
five missing facts to the emitted separate arrays; only then may a separate
product card consider tri/quad acceptance.  It must not upgrade this local
pair merger into strict quad output.
