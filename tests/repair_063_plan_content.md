# Improvement plan - native-all-production-gate-063

## Planner transport

- Planner: current Codex main session (GPT-5), as explicitly requested by the operator; no other agent was spawned.
- Reasoning/service: main session; no separately addressable reasoning level or priority-service setting was exposed.
- Wait: 0 seconds. This was a direct planner request, not an asynchronous job.
- Fast: no API `fast` field was exposed. Fast-off remains lifecycle policy; no unsupported API option is claimed.
- No implementation, build, test, route, worktree, merge, or branch was changed by this planner task.

## Bounded card: 063-MWC

Implement an **Authoritative Wall-Edge Metric Corridor** as a default-OFF C++23 pure preflight kernel. It receives an authoritative CAD/B-Rep/STL edge-sector ledger and complete sealed user policy, then returns either a deterministic corridor certificate or a named refusal. It does not generate a mesh or change a writer.

This is the narrow reusable bridge for Native Tet, Hex, Poly, Tri, Strict Quad, TRI+QUAD, and the surface mesher. It replaces neither product writer nor existing Tri/surface preflights in this card; it gives every writer the same first question: is this requested BL geometrically, metrically, and authoritatively admissible?

## Invariants

- BL=0: `requested_layers=actual_layers=0`, `disabled_identity`, zero offset/front entities, zero collision queries and writer work, unchanged source/semantic/config/writer hashes.
- BL>=1: all requested layers are certified or the entire candidate is discarded. No partial layer is emitted.
- Source edge/face IDs, directed sectors, feature, patch, physical group, component, provenance and all authority digests are mandatory inputs.
- A ridge/corner is never normal-averaged. Missing directed-sector authority is a named refusal.
- `target_cells` and `target_faces` are sealed inputs but are secondary: they cannot affect frame selection, clearance, topology, or quality acceptance.
- Preserve the protected Poly branch; this card has no route or fallback change.

## Exact API and equations

`certify_wall_edge_metric_corridor(authority_ledger, sealed_policy, geometry, obstacles) -> receipt`

The relevant user-input projection must include wall selection/mode, layer count, first/final/total height, growth, sizing/metric/anisotropy mode, diffusion/attenuation, feature/ridge/corner mode, collision tolerances, quality limits, seed/replay, count target/tolerance, and source/semantic/config/writer digests. Unknown, nonfinite or conflicting values refuse.

For authoritative directed endpoints `p0,p1` and authority-oriented face normal `n`:

```text
t = normalize(p1-p0)
c = normalize(n x t)
R = [t c n]
M = R diag(h_t^-2, h_c^-2, h_n^-2) R^T
L_M(d) = sqrt(d^T M d)
```

`c` drives the surface strip and `n` drives the volume shell. Their signs come from a directed source half-edge/sector, never coordinates or averaged normals. Require `M` symmetric positive definite; otherwise `metric_not_spd`.

The one canonical schedule is:

```text
h_k = h0 r^k, k=0,...,N-1
H = sum(h_k)
```

When `total_height`/`final_height` are supplied, compare them to `H`/`h_(N-1)` with the sealed tolerance. Contradiction returns `layer_schedule_inconsistent`, rather than selecting an arbitrary user knob.

Evaluate each proposed strip/shell displacement with the lexicographic tuple:

```text
(invalid_or_inverted, duplicate_or_nonmanifold, collision_or_visibility_failure,
 source_or_sector_binding_loss, max_metric_skew, max_signed_non_orthogonality,
 max_metric_aspect, -min_positive_area_or_volume, count_error)
```

The first eight components always precede count. Metric edge length and `J_Q = sum(1/(Q_k+epsilon))` are diagnostic in 063; a future optimizer may use them only after this feasibility kernel is proven.

## Receipt and rollback

Receipt fields: schema, policy/source/semantic/config/writer hashes, stable source edge/face/sector IDs, `t,c,n`, metric eigenvalues, schedule, obstacle IDs/clearances, quality distributions/worst IDs, BL=0 work counters, and receipt SHA-256.

Refusals: `wall_edge_authority_missing`, `directed_sector_missing`, `feature_frame_ambiguous`, `metric_not_spd`, `nonpositive_layer_height`, `growth_ratio_invalid`, `layer_schedule_inconsistent`, `collision_clearance_failed`, `visibility_failed`, `metric_quality_failed`, `source_binding_lost`, `policy_digest_mismatch`, `candidate_disk_receipt_mismatch`.

Any refusal has no generated entities, `actual_layers=0`, `candidate_discarded=true`, and `rollback_required=true`. Accepted BL=0 has `rollback_required=false`. Candidate/reread receipts must agree exactly except for explicitly declared ULP-bounded floating recomputation.

## Implementation boundary

1. C++23 pure geometry/metric/certificate module and thin binding only.
2. Reuse existing native authority-ledger data. Add no external dependency and copy/link no GPL code.
3. Add native tests for schedule, signed frame, SPD, collision/visibility, BL=0 identity, BL=1/3, ledger tamper and repeat digest.
4. Do not bind writers, UI, count adjustment or release routes in this card.

## Verification ladder

- Promotion target: `L1_PASS / CORRECTNESS_KEEP`; default OFF and runtime-disconnected.
- L0: hand-checkable directed planar edge; BL=0 identity; invalid growth/total; reversed sector; non-SPD metric; obstacle collision; deterministic repetition.
- L1: authoritative cube and sphere/curved-patch adapters for surface, Tet, Hex, Poly, Tri, Strict Quad and TRI+QUAD at BL=0/1. Require strict topology input, positive proposed measures, common policy/source receipt and byte-identical repetition.
- L2: NACA/trailing-edge, ridge/patch junction, narrow gap, complex CAD and STL at BL=0/1/3/8 plus growth/metric/diffusion matrix. Deterministic refusal is acceptable; false acceptance or metadata loss is a regression.
- L3: only after writer binding: all-engine corpus, candidate/disk reread parity, tampered ledger/obstacle tests and independent release packaging.

## Release blockers

This card does not close actual-writer authority, feature/physical-group preservation, complex positive-BL transactions, candidate/disk parity, repeatability, or release packaging. DOI `10.1002/nme.7644` and `10.1016/j.compfluid.2026.107032` remain blockers for general curved positive-BL release thresholds.
