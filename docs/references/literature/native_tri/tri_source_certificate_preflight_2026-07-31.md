# TRI-SOURCE-CERTIFICATE-PREFLIGHT-1 evidence

Date: 2026-07-31

Promotion state: `L1_PASS / CORRECTNESS_KEEP`.

## Scope

`diagnose_native_tri_source_certificate()` is a runtime-disconnected,
read-only diagnostic layered beside the existing exact-clone L0 certificate.
It does not call the route or operator loop, does not emit a mesh, and never
accepts a topology-changing candidate.  The only accepting result remains an
exact L0 source clone with one ordered source-face reference per output face.

The diagnostic freezes the minimum evidence that a later runtime certificate
must provide:

1. immutable source vertex/face and source-payload hashes, including the
   canonical declared feature-edge ownership set;
2. finite, nondegenerate, closed, orientable two-manifold source/candidate
   audits plus component and Euler comparisons;
3. explicit feature-edge ownership whenever observed sharp source edges exist;
4. complete, unambiguous per-candidate-face source references with all source
   faces covered; and
5. static-shell construction, sampled containment, and centroid pullback
   outcomes recorded with their sampled/diagnostic status intact.

The sampled shell values are not a whole-triangle containment certificate.
They cannot authorize a route, a local edit, feature transfer, boundary
transfer, target-face behavior, or boundary-layer behavior.  An exact
Wang-2020 C1/C2/C3 envelope plus explicit feature-path transfer remains a
separate C++23-first card.

Declared feature ownership is valid only when every declared pair is a
canonical undirected edge of the immutable source mesh.  A non-source
diagonal is rejected rather than retained as detached metadata.  Reordering a
valid declaration leaves its evidence hash unchanged; changing its ownership
set changes the hash.

## Cylinder adverse result

The direct experimental operator loop changes the capped cylinder from
`66V/128F` to `18V/32F` after 204 accepted local operations.  The static
linear shell with explicit `local_scale_fraction=0.2` builds, but the output
fails sampled containment at candidate face `0`; its centroid census is
`4 mapped / 28 unmapped / 0 ambiguous`.  The source has 64 observed sharp
edges and the direct loop provides neither explicit feature ownership nor
candidate face provenance.  The diagnostic therefore reports
`certifiable_candidate_faces=0`, `accepted=false`, and ordered refusal
reasons.  No partial face result is promoted.

By contrast, the unchanged cylinder clone has `128/128` L0 reference faces,
three byte-identical reports, and remains the only accepted result.  This
separates evidence for the existing fail-closed contract from a claim that
the topology-changing path is ready.
