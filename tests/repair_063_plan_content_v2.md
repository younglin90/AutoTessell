# Improvement plan - native-all-production-gate-063

## Planner transport

- Sole planner: current Codex main session (GPT-5); user prohibited other agents.
- Reasoning/service: main session; separately-addressable reasoning, priority service, and `fast` API field were not exposed.
- Wait: 0 seconds because this was a direct planner request. Fast-off remains lifecycle policy without claiming an unsupported argument was passed.
- This planner changed no implementation, build, test, route, worktree, merge, or branch.

## Planned card

**063-MWC - Authoritative Wall-Edge Metric Corridor.** Add a default-OFF C++23 pure preflight kernel, `certify_wall_edge_metric_corridor(authority_ledger, sealed_policy, geometry, obstacles) -> receipt`. It returns a deterministic signed corridor certificate or named refusal before any Native Tet/Hex/Poly/Tri/Strict Quad/TRI+QUAD or surface-mesher writer runs. It does not generate a mesh, modify a source, adjust a count, or promote a route.

This is bounded: current `native_tri_wall_edge_bl_preflight` is Tri-specific and `surface_bl_front_sector` independently calculates co-normals/visibility. The new primitive provides one admissibility method without replacing either implementation or binding product writers in 063.

## Scope and invariants

- Inputs are authoritative directed face/edge/sector IDs plus feature, patch, physical group, component, provenance, source/semantic/config/writer hashes, a sealed complete user-policy digest, geometry, and obstacle authority.
- BL=0 is accepted `disabled_identity`: requested=actual=0, no offsets/front entities/collision queries/writer work, and unchanged authority digests.
- BL>=1 certifies every requested layer or discards the whole candidate. No partial layer can be emitted.
- A ridge/corner never uses normal averaging; a missing directed sector refuses.
- User `target_cells`/`target_faces` are sealed but cannot influence frame, clearance, topology, or quality acceptance.
- The protected Poly branch remains untouched.

## Equations and complete input semantics

Relevant user inputs: wall selection/mode; count; first/final/total height; growth; sizing/metric/anisotropy; diffusion/attenuation; feature/ridge/corner handling; collision tolerances; per-product quality limits; seed/replay; count target/tolerance; and all authority digests. Unknown, nonfinite, unset-required, or conflicting values refuse.

For authority-oriented normal `n` and directed endpoints `p0,p1`:

```text
t = normalize(p1-p0)
c = normalize(n x t)
R = [t c n]
M = R diag(h_t^-2,h_c^-2,h_n^-2) R^T
L_M(d) = sqrt(d^T M d)
h_k = h0 r^k, k=0,...,N-1
H = sum(h_k)
```

`c` is surface-strip direction and `n` volume-shell direction. Signs come only from the directed source sector. `M` must be SPD. Supplied total/final height must equal `H`/`h_(N-1)` within sealed tolerance; otherwise `layer_schedule_inconsistent`. This makes all user controls effective and prevents implicit precedence.

## Quality and authority gates

Use lexicographic acceptance:

```text
(invalid_or_inverted, duplicate_or_nonmanifold, collision_or_visibility_failure,
 source_or_sector_binding_loss, max_metric_skew, max_signed_non_orthogonality,
 max_metric_aspect, -min_positive_area_or_volume, count_error)
```

The first eight terms strictly precede count. Metric edge length and `J_Q=sum(1/(Q_k+epsilon))` are diagnostics in this card, not an unvalidated optimizer. Receipt fields are all hashes, stable entity/sector IDs, `t,c,n`, metric eigenvalues, schedule, obstacles/clearances, distributions/worst IDs, BL0 work counters, and receipt SHA-256.

Refuse with `wall_edge_authority_missing`, `directed_sector_missing`, `feature_frame_ambiguous`, `metric_not_spd`, `nonpositive_layer_height`, `growth_ratio_invalid`, `layer_schedule_inconsistent`, `collision_clearance_failed`, `visibility_failed`, `metric_quality_failed`, `source_binding_lost`, `policy_digest_mismatch`, or `candidate_disk_receipt_mismatch`.

Any refusal: no generated entities, actual=0, discarded=true, rollback=true. Accepted BL0 has rollback=false. Candidate/reread must match non-floats exactly and floats within declared ULP envelope.

## Implementation boundary

1. C++23 pure geometry/metric/certificate module plus thin binding only.
2. Reuse existing authority-ledger data; no external dependency and no GPL code copy/link.
3. Test schedule, signed frame, SPD, collision/visibility, BL0, BL1/3, ledger tamper, and repeat digest.
4. Do not connect writers, Electron UI, count adjustment, or release routes.

## Verification ladder

- Target state: `L1_PASS / CORRECTNESS_KEEP`, default-OFF/runtime-disconnected.
- L0: hand-computed planar directed edge; BL0 identity; bad growth/total; reversed sector; non-SPD; obstacle collision; repeated digest.
- L1: authoritative cube and sphere/curved patch for surface, Tet, Hex, Poly, Tri, Strict Quad, TRI+QUAD at BL0/1; strict input topology, proposed positive measure, common policy/source receipt, repeat equality.
- L2: NACA/trailing edge, ridge/patch, narrow gap, complex CAD/STL at BL0/1/3/8 and growth/metric/diffusion matrix. Deterministic refusal is valid; false acceptance or metadata loss is a regression.
- L3: after writer integration only - all-engine corpus, candidate/disk parity, tamper tests, independent release packaging.

## Evidence and release blockers

Preserve input/receipt bytes and SHA-256, authority hashes, selected edge/sector IDs, obstacles, quality distributions, commands, and repeat hashes. This does not close actual-writer authority, feature/physical-group preservation, complex positive-BL transactions, candidate/disk parity, repeatability, or release packaging. `10.1002/nme.7644` and `10.1016/j.compfluid.2026.107032` block general curved positive-BL release thresholds.
