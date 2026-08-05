# STRICT-QUAD-PAIR-PREFLIGHT-CPP23-1 evidence

Promotion state: `L1_PASS / CORRECTNESS_KEEP`.

## Exact scope

This card audits an already supplied **fixed-vertex two-triangle pairing
subset**.  It is not a strict-quad mesher, does not generate quads, and does
not authorize the existing `native_quad_dominant` mixed product.  It requires
an empty candidate-triangle array, at least one degree-four quad, and an exact
partition of source triangles into two-face provenance pairs.  Source and
candidate vertex arrays must be bit-identical.  A future route that inserts or
moves vertices needs a separate bidirectional envelope and provenance
contract before it can reuse this diagnostic.

The card is runtime-disconnected and default OFF.  It does not add a pipeline,
CLI, UI, writer, selector, product classification, fallback, or output route.
`native_quad_dominant` remains `candidate_mixed` and continues to use its
triangular handoff outside this card.

## Research boundary

The local user-supplied Zhu PDFs were rechecked against their manifest:

- Zhu et al. 2025, DOI `10.1137/1.9781611978575.6`, open surfaces with multiple
  boundaries and negative Euler characteristic.  The paper motivates explicit
  oriented topology and boundary-loop preconditions.
- Zhu et al. 2026, DOI `10.1137/1.9781611979138.18`, genus-one surfaces with
  singularity feasibility and parameter-domain preconditions.

Neither paper supplies AutoTessell's immutable source coordinates, feature and
physical-payload provenance, output writer, failure contract, or general
strict-quad extraction.  No algorithm, code, output, dependency, or threshold
was copied.  The only retained independent idea is fail-closed preflight
before a future strict output attempt.  `vendor/dependencies/` is unchanged.

## Contract

The native C++23 audit accepts only C-contiguous `float64 (V,3)` vertex arrays
and `int64` source triangles `(F,3)`, candidate triangles `(T,3)`, quads
`(Q,4)`, pair provenance `(Q,2)`, and feature edges `(E,2)`.  It reports
read-only structural facts:

- finite coordinates and bit-identical source/candidate vertices;
- `T=0`, `Q>0`, exactly four distinct vertices per quad;
- `F=2Q`, sorted unique source-face partition, and canonical oriented quad
  reconstruction from each pair; source triangles are non-degenerate and each
  paired four-vertex set is exactly coplanar (conservative no-tolerance test);
- oriented-manifold incidence, exact directed boundary-edge equality,
  component and Euler equality;
- declared source feature edges surviving as candidate quad edges.

Python is an independent oracle.  It additionally owns generic patch and
physical-group payload authority: both source triangles in each pair must
have the same immutable payload and the output quad must carry that payload.
When `AUTO_TESSELL_STRICT_QUAD_PREFLIGHT_CPP23=1`, malformed native output or
any native/Python structural disagreement raises fail-closed.  Missing native
symbol falls back to Python.  The diagnostic never repairs, reorders, moves,
inserts, deletes, triangulates, or writes a mesh.

## L0 and L1 acceptance

L0 hand-checkable open square: `V=4, F=2, Q=1, T=0, C=1, chi=1, B=4` with four
declared boundary features.  Three repeats must be byte-identical.  Triangle
handoff, wrong ordering, duplicate/missing provenance, moved vertex, feature
loss, payload mismatch, non-coplanar pair, non-finite data, strict-ABI violation, and malformed
native payload must reject.  The primary metric is zero false acceptance.

L1 uses a hand-authored closed cube `12T -> 6Q` with all twelve cube feature
edges and exact paired patch payloads: `C=1, chi=2, B=0`.  OFF and ON reports,
reasons, and hashes must match across three repeats.  Cylinder and sphere use
no supplied fixed-vertex pair product and must reject explicitly; they are not
claimed as strict-quad coverage.  Target count, element quality, boundary
layers, performance promotion, general quadrangulation, and release gates are
outside this card.

## Reproduction

```bash
AUTOTESSELL_EXT_BUILD_DIR=<release-build> \
pytest -q tests/test_native_strict_quad_pair_preflight_cpp23.py
```

## Measured result

GCC 13.3 Release C++23 build in an external temporary build directory compiled
`native_metrics` without warning output.  With that build selected through
`AUTOTESSELL_EXT_BUILD_DIR`, the focused L0/L1 suite passed `13/13` and the
focused suite plus the pre-existing surface-product contract passed `18/18`.
The recorded L1 outcome is strict pair evidence only: cube passes, while the
empty fixed-vertex candidate supplied for cylinder and sphere rejects.  There
is no general strict-quad, target-count, quality, boundary-layer, routing, or
release claim.
