# STRICT-QUAD-FIXED-PAIR-PRODUCT-L0

Date: 2026-07-31

Promotion target: `L1_PASS / CORRECTNESS_KEEP`.  This is a
runtime-disconnected, default-OFF in-memory surface-product materializer.  It
does not claim a general strict-quad mesher, volume mesh, output format,
target-face solution, boundary layer, or release readiness.

## Narrow contract

The caller supplies an already-formed fixed-vertex candidate:

- source and candidate vertex arrays;
- source triangles, required-empty candidate triangles, quads, and ordered
  two-triangle pair provenance;
- declared source feature edges;
- caller-owned source triangle and candidate quad patch payloads.

`materialize_strict_quad_fixed_pair_product_l0` first calls the existing
`strict_quad_pair_preflight` Python authority.  Only an accepted preflight is
combined with the existing `SurfaceProductMode.QUAD` certificate.  The latter
must itself classify `STRICT_QUAD`, have zero triangles, positive quads, and
no triangular handoff.  Only then, and only when
`AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0=1`, does the route return a
read-only in-memory product.

Every other path returns `product=None` with an explicit rejection reason.  It
does not call `native_quad_dominant`, pair triangles, infer features or
patches, triangulate a quad, substitute `tri_quad`, choose a route, write a
mesh, or modify source geometry.

## Preserved evidence

The existing preflight remains the only authority for:

- bit-identical source/candidate coordinates;
- finite source geometry, source triangle validity, and no candidate
  triangles;
- `Q > 0`, four distinct source vertices per quad;
- exact ordered source-triangle partition, canonical pair orientation, and
  exact coplanarity;
- oriented manifold incidence, directed boundary equality, component and Euler
  equality, and source feature-edge preservation;
- Python-only patch payload preservation.

The materialized product copies source vertices and quad connectivity into
C-contiguous, read-only arrays and retains the preflight's source and quad
hashes.  Its quad patch payload is normalized into an immutable tuple only
after preflight has accepted it.

## L0/L1 acceptance

L0 square:

- default OFF: a valid `2T -> 1Q` candidate reports explicit disabled status
  and returns no product;
- enabled: the same candidate materializes one strict quad with no triangles,
  exact source bytes, exact feature/patch provenance, and three identical
  reports;
- nonempty candidate triangles, moved coordinates, wrong quad orientation,
  duplicate/missing provenance, feature loss, patch mismatch, and noncoplanar
  pairing all reject with no fallback.

L1 cube:

- hand-authored `12T -> 6Q` exact pairing with twelve source feature edges and
  six patch identities materializes three identical read-only products;
- cylinder and sphere have no supplied fixed-pair candidate and reject
  explicitly.  They are not strict-quad coverage claims.

The existing native `strict_quad_pair_preflight` C++23 cross-check is still
optional and default OFF.  Its malformed or divergent result fails closed
before materialization; this card adds no C++ source.

## Scope and rollback

Only the disconnected `native_quad` product module and export, its L0/L1 test,
and this evidence note change.  No pipeline, `native_quad_dominant`, product
classification policy, evaluator volume checker, tier selector, schema,
CLI/UI, writer, CMake, target-cell policy, boundary-layer logic, or
`vendor/dependencies/` code changes.

Kill/revert the card for any false strict product, mutable returned arrays,
source/hash/payload mismatch, nonempty product triangles, route/output
connection, fallback to a mixed product, nondeterminism, or changed existing
surface-product/preflight behavior.

## Provenance

This card composes first-party contracts only.  It relies on the local
fixed-pair preflight evidence and its Zhu DOI notes; it copies no paper or
open-source implementation.  `vendor/dependencies/` remains unchanged.
