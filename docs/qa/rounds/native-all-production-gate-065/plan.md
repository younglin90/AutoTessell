# Improvement plan - native-all-production-gate-065

## Planner transport

- Sole planner: current Codex main session (GPT-5); the user prohibited sub-agents and none was spawned.
- Requested policy is `gpt-5.6-terra`, high reasoning, priority, `fast=off`. This direct interface exposes no model/reasoning/service/fast argument, so none is claimed as passed. `agent_fast=false` is accurately retained as lifecycle policy.
- Planner-agent wait: 0 s. An unrelated dependency lookup was cancelled after about 66 s and yielded no evidence. No implementation, build, test, routing, worktree, commit, or push occurred.

## Planned card

**065-AQTE - Authoritative Quality Transaction Executor v1.** A default-OFF C++23 state machine wrapped around every actual Native Tet, Native Hex, Native Poly, Native Tri, Strict Quad, TRI+QUAD, and surface-mesher writer attempt.

It is the production boundary missing after 062 signed `NativeQualityWitness/v3`, 063 wall-edge metric corridor, and 064 `NativeTransactionIntent/v1`: accept an armed intent, give a real writer one staged candidate sink, validate writer-owned topology/quality/lineage, independently reread persisted output, then atomically publish or discard. It is not a new mesher or seven rewrites.

## Scope and invariants

- Consume the authoritative CAD/B-Rep/STL ledger, 062 policy/witness, 063 corridor for positive BL, and 064 intent. Never re-identify source entities from coordinates.
- Every explicit UI/API parameter must retain its 064 named primary writer sink and effective typed value. Unknown, unconsumed, ambiguous, or hard-coded replacement values refuse before writer work.
- **BL=0:** `requested_layers=actual_layers=0`, no layer/front/offset topology operation, zero layer-work counter, and unchanged source/semantic/feature/patch/physical-group/component/provenance/entity-set hashes.
- **BL>=1:** stage every requested layer under the certified directed wall-edge sector/frame/schedule, or discard all staged output. Collision, visibility, missing role/lineage, topology, measure or quality failure never publishes a partial shell.
- Preserve writer-issued UIDs and parent/source/feature/patch/physical-group/component/provenance rows. Coordinate matching, Tri clones and quad relabeling are forbidden substitutes.
- Protected Native Poly stays untouched. Target cell/face count is sealed but only a final tie-breaker after strict topology, authority, BL, and quality.

## Exact core method and equations

```text
ARMED(intent, ledger, policy, corridor)
 -> STAGING(writer-owned candidate sink)
 -> PROPOSED(snapshot + lineage delta)
 -> VALIDATED(candidate quality witness)
 -> REREAD_VALIDATED(persisted output witness)
 -> PUBLISHED

any refusal -> ROLLED_BACK (candidate bytes + lineage delta discarded atomically).
```

The opaque capability is single-use. Writers can append only to the staged sink; `publish()` is executor-owned and requires candidate/reread parity. The journal includes state, writer build, request/intent/policy/corridor/authority hashes, UID set and deterministic operation sequence.

For oriented face vector `S_f`, centres `C_o,C_n,C_f`, `d=C_n-C_o`:

```text
theta_f = acos(clamp((d dot S_f)/(||d|| ||S_f||),-1,1))*180/pi
a=|(C_f-C_o) dot S_f|/||S_f||; b=|(C_n-C_f) dot S_f|/||S_f||
X=C_o+(a/(a+b))*d
sigma_f=||C_f-X||/(||d||+epsilon).
```

Boundary uses `d=C_f-C_o` and the normal projection. No `abs(d dot S_f)` is permitted for non-orthogonality. Zero/nonfinite values and reversed orientation refuse.

For authoritative wall edge `p0->p1` and normal `n`:

```text
t=(p1-p0)/||p1-p0||; c=(n x t)/||n x t||; R=[t c n]
M=R diag(h_t^-2,h_c^-2,h_n^-2) R^T, M positive definite
L_M(e)=integral_e sqrt(dx^T M dx)
h_k=h0*r^k; H_N=sum(k=0..N-1) h_k.
```

Positive BL requires `actual_layers=N`, positive layer measure, source sector preservation and sealed first/final/total-height agreement. Aspect metrics stay family-specific: Tet dihedral/mean-ratio, Hex scaled Jacobian, Poly star/face alignment, Tri metric-angle, Quad scaled-Jacobian/warpage, and BL metric distortion.

For proposed state `m`, use:

```text
K(m)=(n_duplicate+n_nonmanifold+n_self_intersection,
      n_inverted+n_nonpositive_measure,
      n_source_feature_group_component_provenance_mismatch,
      n_BL_sector_schedule_collision_visibility_failure,
      V_nonortho,V_skew,V_family_aspect,-min_positive_measure,count_error)

V_q=max(0,q_max/limit_max-1,q_p95/limit_p95-1,q_p99/limit_p99-1).
```

Admit a mutation only when the first four terms are zero and `K(after) <lex K(before)`. Count can tie-break only when every preceding quality component is equal within the sealed numerical envelope. Queue order is deterministic: `(local K contribution, writer_uid, operation_kind, sequence)`.

## Named refusal and rollback gates

Every refusal reports `accepted=false`, `candidate_discarded=true`, `rollback_required=true`, `published=false`, and a journal hash.

- `executor_intent_not_armed`, `executor_capability_reused`, `executor_writer_not_registered`, `executor_writer_manifest_mismatch`, `executor_parameter_consumption_mismatch`
- `executor_bl0_layer_work_detected`, `executor_positive_bl_corridor_missing`, `executor_bl_requested_actual_mismatch`, `executor_bl_sector_or_schedule_lost`, `executor_collision_or_visibility_failed`
- `executor_topology_invalid`, `executor_nonpositive_or_inverted`, `executor_source_authority_lost`, `executor_feature_patch_group_component_lost`, `executor_provenance_or_uid_lost`
- `executor_signed_orientation_invalid`, `executor_quality_threshold_exceeded`, `executor_quality_regression`, `executor_count_precedes_quality`
- `executor_candidate_receipt_missing`, `executor_disk_reread_missing`, `executor_candidate_disk_mismatch`, `executor_publish_without_commit_token`, `executor_journal_digest_mismatch`.

## Exact implementation boundary

1. Add C++23 `auto_tessell_core/native_transaction_executor/native_transaction_executor_v1.hpp/.cpp` plus thin pybind entry. It owns state, journal, token, callback validation and atomic publish.
2. Reuse, not duplicate, 062 `evaluate_v3/compare_candidate_reread_v3`, 063 corridor and 064 intent receipts.
3. Add one narrow adapter contract for each existing real writer: `native_tet`, `native_hex`, `native_poly`, `native_tri`, `strict_quad`, `tri_quad`, `surface_mesher`. It returns actual writer artifact/snapshot and writer-issued lineage; no synthetic cube artifact and no Python geometry/optimizer.
4. A thin Python adapter may marshal lossless handles only. It may not add defaults, calculate quality, mutate topology or mint IDs.
5. Do not alter Electron controls, importers, algorithms, protected Poly, output formats, packaging or count heuristics in this card.

## Quality and authority gates

- Entry ledger: strict `duplicate=non_manifold=inverted=0`, source/semantic/config/writer digests, nonempty feature/patch/physical-group/component/provenance rows.
- BL=0: zero BL work and unchanged identity hashes; ordinary actual writer result still passes strict topology and v3 quality.
- BL>=1: accepted corridor, all requested roles `{wall,front,side}`, positive measure, no collision/visibility breach, preserved metadata, strict topology zero and family quality limits.
- Publish: candidate/reread request, intent, policy, corridor, source, semantic, writer, UID-set and provenance hashes match; only v3's declared 16-ULP recomputation envelope applies to floats.

## Verification ladder

- **L0:** state graph, single-use token, deterministic queue, each named refusal, rollback, BL=0 zero-work, BL=1/3 schedule, signed reversal, and count-tie-only behavior.
- **L1:** actual writer binding for every product on authoritative cube and curved wall patch at BL=0/1. Vary every input category and prove a named sink/effective value or deterministic unsupported refusal; strict topology, full metadata, v3 quality and candidate/reread parity required.
- **L2:** cube, sphere, NACA, ridge/patch, narrow gap, T-junction, complex CAD/B-Rep and STL at BL=0/1/3/8 across spacing, growth, metric, feature, seed and count matrix. Safe refusal is valid; partial/untracked output is regression.
- **L3:** independent process reread, repeatability, writer/package provenance and adversarial receipt tampering. Count proximity is reported only after all release gates pass.

## Evidence and release blockers

Preserve request, manifest/sink, authority, policy, corridor, intent, candidate/reread and journal bytes/hashes; stable IDs and complete lineage; distributions/worst IDs; operation sequence; rollback reason; artifact paths; commands and repeat hashes.

065 does not by itself prove release: each of seven writers still needs real binding, complex CAD/STL feature/group evidence, independent package reread, corpus repeatability and 3-D curved positive-BL limits. The Poly branch remains protected. DOI `10.1002/nme.7644` and `10.1016/j.compfluid.2026.107032` remain threshold blockers.

## Actual 065 planner transport correction

The generated transport text above is stale and is superseded by this record. Planner agent `019fcd81-900a-77a2-a5a9-ecd3f047fb10` was requested as `gpt-5.6-terra`, high reasoning, priority service, with fast off by lifecycle policy. It completed after approximately 11 minutes of the allowed wait and was then closed. The API exposes no explicit `fast` field. It reviewed literature and public code and performed no implementation.

The lifecycle advanced the round to implementation after planner completion; the main session alone implements this card. AQTE remains default-off until real writer callbacks and disk evidence bind it.

## Implementation gate outcome

- Implemented the default-off C++23 AQTE state machine and pybind surface.
- Added a lossless Python transport adapter; it inserts no defaults, computes no geometry or quality, and mints no IDs.
- Added BL=0/BL=1 commit, topology/authority/corridor rejection, disk-reread tamper, single-use and rollback coverage.
- Explicitly verified that a fresh CMake configure keeps `BUILD_NATIVE_TRANSACTION_EXECUTOR=OFF`.
- Focused 065 gate: 10 executor/adapter tests passed; 25 prior intent/corridor/witness regression tests passed.
- The card remains an integration boundary, not release evidence: actual native writer callbacks and independent persisted artifacts are still required.
