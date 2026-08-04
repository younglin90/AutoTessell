# Improvement plan - native-all-production-gate-064

## Planner transport

- Sole planner: current Codex main session (GPT-5); no sub-agent was created.
- Requested policy: `gpt-5.6-terra`, high reasoning, priority service, and `fast=off` apply when a separately-addressable planner exists. This direct interface exposes none of model, reasoning, service, or `fast` arguments, so none is claimed to have been passed. Fast-off remains repository lifecycle policy.
- Real planner-agent wait: `0 s` (no planner agent existed). Research included one completed public-search wait of about `10 s`; an unrelated dependency lookup stalled about `88 s` and was terminated without being used as evidence.
- This planner made no code, build, test, route, worktree, merge, commit, or push change. It writes only the planning artifacts.

## Planned card

**064-ATB - Authoritative Transaction Binding v1.** Implement a default-OFF C++23 admission kernel that turns the complete runtime UI/request parameter set plus authoritative source ledger into a signed `NativeTransactionIntent`. Before any writer mutates a candidate, it proves every enabled applicable user input has one unambiguous named consumer in Native Tet, Hex, Poly, Tri, Strict Quad, TRI+QUAD, or surface mesher.

This is a binding card, not a mesher rewrite. It consumes the 062 `NativeQualityWitness/v3` policy digest and the 063 wall-edge metric-corridor receipt. It creates no geometry, modifies no source, and binds no product writer in 064. The protected Poly branch is untouched.

## Why this card now

Users can adjust every input, but release evidence remains invalid if any value is hard-coded, dropped, duplicated, or interpreted differently by surface and volume routes. Aubry's metric contract needs actual consumers; 062/063 provide quality and wall-edge facts but not all-engine consumption proof. A fail-closed intent closes that common gap without calling a default-OFF sidecar a release route.

## Invariants and data contract

`authorize_native_transaction_v1(authority_ledger, raw_request, engine_manifest, quality_policy_v3, corridor_receipt) -> intent_or_refusal` is pure deterministic C++23.

- `raw_request` is a lossless typed map from the Electron/API boundary: parameter id, type, explicit value/null, UI schema version, control id, selected engine/product. It is not a C++ list of defaults.
- The selected writer build issues `engine_manifest`: `(parameter_id, applicability predicate, exactly_one_sink, semantic_role, writer_stage)`. Sinks are `source_authority`, `surface_metric`, `volume_metric`, `bl_schedule`, `wall_edge_sector`, `feature_protection`, `topology_transaction`, `quality_gate`, `count_tuning`, `seed_replay`, and `output_provenance`.
- The intent seals raw request bytes, resolved values, manifest bytes, source/semantic/config/writer hashes, v3 policy hash, optional corridor hash, engine/product, schema versions, and ordered sink map. It returns SHA-256 receipt bytes and zero geometry-work counters.
- An input may be inapplicable only through a recorded writer-manifest predicate. Every applicable parameter has exactly one primary sink; dependent read-only checks are recorded separately and cannot overwrite it.
- BL=0 is `disabled_identity`: requested=actual=0, no offset/front/collision/surface-layer writer stage, unchanged source/authority digests.
- BL>=1 needs an accepted 063 corridor, finite complete schedule, selected wall-edge/patch/feature lineage, and v3 quality limits. The intent only permits one atomic attempt; it does not certify mesh creation.

## Exact equations and quality ordering

The 063 frame, SPD metric, and schedule are rechecked rather than independently recomputed:

```text
t = (p1-p0)/||p1-p0||
c = (n x t)/||n x t||
R = [t c n]
M = R diag(h_t^-2,h_c^-2,h_n^-2) R^T,  M = M^T positive definite
h_k = h_0 r^k, H_N = sum(k=0..N-1) h_k
```

For supplied final and total heights require:

```text
|h_final-h_(N-1)| <= tau_h max(1,|h_final|,|h_(N-1)|)
|H_user-H_N| <= tau_H max(1,|H_user|,|H_N|).
```

The existing signed v3 volume-face quantity remains authoritative:

```text
theta_f = acos(clamp(((C_n-C_o) dot S_f)/(||C_n-C_o|| ||S_f||),-1,1))*180/pi.
```

No `abs(dot)` is allowed. Acceptance is lexicographic:

```text
(topology_invalid, inverted_or_nonpositive, source_or_lineage_loss,
 corridor_or_BL_contract_failure, nonorthogonality, skewness, family_aspect,
 target_count_error).
```

`target_count_error` is reachable only after earlier terms pass. The exact consumption gate is:

```text
Applicable = {p in request | manifest.applicable(p)}
forall p in Applicable: |PrimarySink(p)| = 1
Covered = SHA256(canonical(request,effective_values,manifest,authority,receipts)).
```

## Named refusal and rollback gates

Every refusal returns `accepted=false`, `candidate_discarded=true`, `rollback_required=true`, `generated_entity_count=0`, and stable reason code. No writer runs afterward.

- `intent_request_schema_missing`, `intent_unknown_parameter`, `intent_duplicate_parameter`, `intent_parameter_type_invalid`, `intent_parameter_nonfinite`
- `intent_engine_or_product_unknown`, `intent_writer_manifest_missing`, `intent_writer_manifest_digest_mismatch`, `intent_parameter_not_applicable_unexplained`, `intent_parameter_unconsumed`, `intent_parameter_sink_ambiguous`
- `intent_authority_ledger_missing`, `intent_source_semantic_writer_digest_missing`, `intent_policy_v3_missing`, `intent_policy_digest_mismatch`
- `intent_bl0_identity_violation`, `intent_positive_bl_corridor_missing`, `intent_wall_edge_lineage_missing`, `intent_metric_not_spd`, `intent_layer_schedule_inconsistent`
- `intent_feature_patch_group_component_missing`, `intent_quality_contract_missing`, `intent_count_precedes_quality`, `intent_candidate_disk_intent_mismatch`.

After acceptance the kernel exposes a single-use `rollback_token`. Any later corridor/v3/topology failure invalidates it and discards staged output and provenance rows together.

## Exact implementation boundary for the main session

1. Add `auto_tessell_core/native_transaction_intent/native_transaction_intent_v1.hpp` and `.cpp`: typed canonical request/manifest, applicability and sink validation, SHA-256 receipt, named refusal, rollback-token state. C++23 only in this admission path.
2. Add thin `native_transaction_intent_bind.cpp`, and CMake target under existing default-OFF option. No runtime Python computation path.
3. Add a thin `core/evaluator/` request-serialization/receipt-validation adapter. It cannot invent defaults, filter unknown keys, calculate geometry, or mint writer IDs.
4. Add direct tests for seven labels, all parameter categories, BL=0 identity, BL=1/3 prerequisites, ambiguity/unconsumed inputs, authority tamper, and deterministic receipt.
5. Do not edit product writers, Electron UI, output formats, protected Poly route, or packaging. The next card binds one writer at a time to the accepted token.

## Quality and authority gates

- Use only CAD/B-Rep/STL authoritative-ledger source entries. Seal source exactness mode, source/semantic/config/writer hashes, selected patches/features/physical-groups/components/provenance root. Coordinate re-identification is forbidden.
- Surface and volume routes receive the same sealed request hash, preventing wall-edge metric drift.
- Aspect remains family-tagged: Tet dihedral, Hex scaled Jacobian, Poly star/face metric, Tri metric-angle, Quad scaled-Jacobian/warpage, BL metric distortion.
- Candidate and reread require identical intent/source/semantic/writer/policy/corridor hashes and writer-issued IDs; numerical measurements retain v3's 16-ULP envelope only.

## Verification ladder

- **L0:** C++ unit tests for canonical map ordering, unknown/duplicate/type/nonfinite/unconsumed/ambiguous refusal, exact coverage, BL=0 zero-work, BL schedule mismatch, repeated receipt.
- **L1:** authoritative cube and curved-patch ledgers for every engine/product at BL=0/1. Vary every declared input and prove a named effective/sink record or named refusal; strict input topology is zero; no writer call.
- **L2:** cube, sphere, NACA, ridge/patch junction, narrow gap, T-junction, complex CAD/B-Rep and STL at BL=0/1/3/8 with growth/metric/feature/count/replay matrix. Deterministic unsupported-consumption refusal is correct; false acceptance is regression.
- **L3:** after per-writer binding, actual candidate/disk transactions require `non-manifold=duplicate=inverted=0`, source/feature/physical-group/component/provenance parity, v3 quality, positive-BL evidence, repeatability, then count proximity.

## Evidence and release blockers

Preserve raw/effective canonical bytes, writer manifest/build digest, authority ledger, v3 and corridor receipts, sink rows, rollback-token lifecycle, UIDs, candidate/disk intent hashes, refusal reasons, commands and quality distributions. Sources stay local; receipts need only SHA-256 and stable IDs.

064 does not close actual all-engine writer binding, complex positive-BL transactions, CAD/STL ingress, feature/physical-group preservation, packaging, or corpus release. Native Poly remains protected. `10.1002/nme.7644` and `10.1016/j.compfluid.2026.107032` remain required before general curved-positive-BL release thresholds.

## Actual 064 planner transport correction

The generated transport text above is stale and is superseded by this record. The sole planner agent was `019fcd6c-88a8-7c23-a88c-1d08390f1fdc`, requested as `gpt-5.6-terra`, high reasoning, priority service, with fast off by lifecycle policy. It completed after approximately 11 minutes of the allowed wait and was then closed. The API exposes no explicit `fast` field. The agent reviewed local papers, literature, and public code, and performed no implementation.

The lifecycle had already advanced the round to implementation after planner completion; a manual second `mark-planned` correctly reported implementation phase. Implementation is authorized in the main session only. The intent-binding kernel remains default-off and does not claim actual writer release integration.
