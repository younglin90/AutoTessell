# Native all-production gate 069 — implementation plan

## Scope and gate

This round covers the persisted-output authority contract needed by Native
Tet, Hex, Poly, Tri, Strict Quad, Tri+Quad, and the surface mesher. The
quality-first order is authoritative source/provenance, topology and positive
measure, geometric quality, boundary-layer schedule, and only then target
cell/face count. BL=0 is a zero-work identity case; BL>=1 is a real layer
case. The protected Poly branch and fixed reference remain untouched.

## Planner review

The sole planner was requested as `gpt-5.6-terra`, high reasoning, priority
service tier, with fast mode explicitly off, and reviewed papers plus public
source code. It was used only for core methodology and did not edit the
worktree. The API has no independent `fast` field, so this records the
fast-off instruction rather than claiming an unavailable switch.

## Card 069-A — persisted artifact contract V2 and Tet actual readback

1. Seal source ledger, canonical user configuration, and build receipt at the
   producer boundary. Preserve `N`, `h0`, growth ratio, effective/origin/
   default values, configuration digest, source digest, feature/patch/
   physical-group/component IDs, and cell/face lineage.
2. Route actual mesher stage -> close/fsync -> fresh C++ child reader ->
   atomic publish -> fresh C++ destination reader. The child receives only
   paths and sealed receipts, never producer arrays or in-process objects.
   Missing files, symlinks, schema/digest drift, unknown fields, silent
   clamp/widening, mapping gaps, and producer/child disagreement refuse.
3. Generalize the persisted reader to polygonal `polyMesh` syntax, while
   keeping validators separate: Tet requires triangular boundary faces and
   four-vertex cells; other engines have distinct admissibility rules.
4. Recompute from disk raw-tree and semantic digests, source-boundary
   coverage, duplicate/non-manifold/orientation failures, positive measure/
   Jacobian, min dihedral/mean-ratio/radius-ratio/aspect,
   non-orthogonality/skewness, wall-front clearance, and exact BL schedule.
   Counts are post-quality diagnostics.
5. Implement the smallest production-safe step now: a C++ child verifier for
   the persisted Tet route, fresh-process tests, tamper/refusal cases, and
   an explicit record that the other engines remain unverified until their
   actual producers use this contract.

## Acceptance and corpus

Use BL layers `N in {0,1,3,8}` and user-controlled positive `h0` and growth.
For `g != 1`, require `H_N = h0*(g^N-1)/(g-1)`; for `g == 1`, require
`H_N = N*h0`, with the persisted receipt matching within the declared
tolerance. The existing 8-source x 19-configuration x 3-replay matrix (456
audits per engine) is VERIFIED only with actual producer output and source
maps; fixture evidence stays UNVERIFIED. Release remains blocked for actual
Hex/Poly/Tri/Quad/Tri+Quad output binding and complex BL>=1 coverage not
implemented by this card.

## Implementation gate

Implementation starts only after this plan, `literature.md`, and
`unreadable-dois.md` are populated and `round_lifecycle.py mark-planned`
accepts. Each card adds measurements, focused tests, refusal cases, and a
durable result entry before closure.
