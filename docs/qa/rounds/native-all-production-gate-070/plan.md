# Native all-production gate 070 — implementation plan

## Scope and decision

This round is deliberately Tet-only: bind the receipt-bound actual Native
Tet producer to the persisted C++ child verifier. Hex, Poly, Tri, Strict
Quad, and Tri+Quad are not attached merely because they can share a file
format; each still needs its own actual producer and topology predicate.
The protected Poly branch and protected reference remain unchanged.

The quality-first order is authoritative source/provenance, topology and
positive measure, geometric quality, BL schedule, and only then counts.
Default/non-receipt paths remain non-release evidence.

## Planner review

The sole planner was requested as `gpt-5.6-terra`, high reasoning, priority
service tier, with fast mode explicitly off. It reviewed the actual route,
primary literature, and public source code and did not edit the worktree.
The tool API has no separate `fast` field; this records the explicit prompt
instruction and does not claim an unavailable switch.

## Planned card — 070-A actual persisted-child binding

1. Route `TierNativeTet._runner -> receipt_stage -> staged_runner ->
   PolyMeshWriter -> close/fsync -> fresh C++ child -> atomic publish ->
   destination fresh C++ child`.
2. Add a deterministic line-oriented
   `native-tet-persisted-contract/v2` sidecar containing source bytes and
   digest, CAD/STL kind, source/semantic/feature/patch/physical-group/
   component digests, exact source-to-boundary mapping, build identity,
   raw polyMesh digest, requested/effective/origin parameters, and BL state.
3. Replace the fixture-only CLI ledger input with the v2 sidecar. It must
   reject symlinks, unknown records, malformed fields, digest drift, and
   non-Tet topology; it recomputes source coverage, duplicate/non-manifold/
   orientation, positive signed volume, min dihedral, mean/radius ratio,
   aspect, non-orthogonality, skewness, and certificate digests.
4. Add a native stage-seal operation that fsyncs the complete staged tree
   before child verification. After atomic publish/fsync, rerun the child on
   the destination and compare raw-tree and semantic certificates.
5. Preserve requested/effective/origin for every user parameter, including
   target-size clamps. A pending or unsupported control stays explicit and
   is never silently promoted.

## Quality and authority gates

BL=0 must record requested_layers=actual_layers=0, zero layer work, and
identity of the pre/post-BL persisted mesh. BL>=1 must be refused on this
route unless a writer-owned BL ledger contains exact N/h0/growth and the
persisted geometry verifies it; this card must not synthesize a schedule.
Topology, source coverage, positive measure, and quality must pass before
cell counts are reported as diagnostics. No target-count relaxation may
override a failed quality or authority gate.

## Verification ladder and acceptance/refusal matrix

- One receipt-bound live Tet run verifies both stage and destination in fresh
  processes with identical raw-tree and semantic digests.
- Three independent full producer replays are byte- and certificate-
  deterministic; BL=0 identity and parameter provenance are present.
- Refuse missing/unreadable/symlinked files, unknown schema, source/build/
  config/tree digest drift, missing mapping, reversed cycles, semantic drift,
  duplicate/non-manifold/inverted topology, nonpositive Tet, child failure,
  stage mutation, or destination disagreement.
- Keep the existing fixture child tests, but label them fixture evidence.
  Promote only live producer output with authoritative CAD/STL source maps.

## Implementation gate and rollback

Implementation starts only after this plan, `literature.md`, and
`unreadable-dois.md` are complete and `round_lifecycle.py mark-planned`
accepts. Each card adds measurements, focused tests, failure/refusal cases,
and a durable result. Any child or destination mismatch rejects the candidate
and restores the prior destination without a promotion receipt.
