# Improvement plan — native-all-production-gate-062

## Goal

Implement

## Scope and invariants

-

## Planned card

- Mechanism:
- Default state:
- Expected benefit:
- Failure/rollback condition:

## Quality and authority gates

-

## Verification ladder

- L0:
- L1:
- L2:
- L3:

## Evidence to preserve

-

## 062 bounded re-review

- Scope: planner-only. No code, build, routine test, route promotion, worktree, commit, or push change is authorized.
- Planner transport: requested one `gpt-5.6-terra`/high/priority planner and lifecycle fast-off. This session exposes no multi-agent spawn/wait API; direct spawn failed because it is absent. No fast field is exposed. This is a source-backed review, not a fabricated planner result; keep the lifecycle state in `planning` and do not run `mark-planned`.

## Planned card

- Mechanism: default-off C++23 `NativeQualityWitness/v3`, a pure evaluator over an authoritative mesh snapshot and writer-issued IDs. It neither creates geometry nor infers authority from coordinates.
- Default state: evidence-only; retain v1/v2 compatibility. No product is promoted until actual writer and disk reread both bind v3.
- Expected benefit: one signed orientation-aware non-orthogonality/skewness kernel, sealed complete user policy, deterministic per-entity distributions/worst IDs, candidate/disk parity.
- Failure/rollback: malformed/unknown policy, digest mismatch, missing writer/source/semantic identity, invalid incidence, nonfinite geometry, BL contract failure, parity mismatch, or threshold failure returns named refusal plus `accepted=false`, `candidate_discarded=true`, `rollback_required=true`.

## Exact minimal implementation files

1. Add `auto_tessell_core/native_quality_witness/native_quality_witness_v3.hpp` and `.cpp`: typed snapshot/authority/policy/receipt structures, canonical policy bytes, signed face/surface kernels, candidate/reread comparison.
2. Modify `auto_tessell_core/native_quality_witness/native_quality_witness_bind.cpp` only to bind `seal_policy_v3`, `evaluate_v3`, `compare_candidate_reread_v3`; retain legacy APIs.
3. Modify `auto_tessell_core/CMakeLists.txt` only to compile the C++23 source into `native_quality_witness` under its existing option.
4. Modify `core/evaluator/native_canonical_quality_witness.py` only as orchestration: pass writer UID/lineage and policy bytes to C++, use one snapshot adapter for candidate/disk, never mint v3 IDs from sorted coordinates.
5. Modify `core/evaluator/native_quality_witness_admission.py` only to validate v3 receipt/refusals, not calculate metrics in Python.
6. Add `tests/test_native_quality_witness_v3_cpp23.py` and `tests/test_native_quality_witness_v3_candidate_disk_parity.py`. Product-writer/UI/count adaptation are follow-on cards.

## Equations and stable identity

- Volume face input is writer-issued owner-to-neighbour `S_f`, centres `C_o,C_n,C_f`, and `d=C_n-C_o`.
- Internal non-orthogonality: `theta=acos(clamp((d·S_f)/(|d||S_f|),-1,1))*180/pi`; boundary uses `d=C_f-C_o`. Never apply `abs`: reversal is near 180 degrees or a face-orientation refusal.
- Internal skewness: `a=abs((C_f-C_o)·S_f)/|S_f|`, `b=abs((C_n-C_f)·S_f)/|S_f|`, `X=C_o+(a/(a+b))d`, `sigma=|C_f-X|/(|d|+epsilon)`. Zero/nonfinite denominator refuses. Boundary: `n=S_f/|S_f|`, `X=C_o+((C_f-C_o)·n)n`, `sigma=|C_f-X|/(|C_f-C_o|+epsilon)`.
- `StableEntityUid=(product,writer_epoch,output_kind,writer_entity_id)` persists candidate-to-disk. Positive BL also carries role `{wall,front,side}`, layer, source face/edge, feature, patch, physical group, component, provenance digest. Coordinate sorting, nearest-point and unordered-vertex IDs are forbidden.
- Aspect stays family-tagged: Tet diagnostic, Hex scaled Jacobian, Poly star/edge diagnostic, Tri metric-angle, Quad scaled Jacobian/warpage; unlike definitions are never combined.

## Sealed complete user policy and API

- `QualityPolicyV3` rejects unknown keys and canonicalizes tagged fixed-order values before SHA-256. It seals engine/source mode, target cells/faces secondary, sizing/metric/anisotropy, BL enable/count/first/final/total/growth/min-height, wall-edge selection/mode, feature/ridge/corner, topology/repair/source/semantic modes, every per-product/per-partition topology/Jacobian/area/volume/non-ortho/skew/aspect/warpage limit, seed/replay/count tolerance, and source/semantic/config/writer/candidate/disk digests. Unset optional values are explicit tagged nulls.
- `seal_policy_v3(policy)->{accepted,policy_bytes,policy_sha256}`; `evaluate_v3(snapshot,authority,policy,stage)` returns full rows/distributions/worst UID/topology/BL/wall-edge/digests; `compare_candidate_reread_v3(candidate,disk)` requires equal policy/source/semantic/writer/entity-set hashes, exact non-floats, and only a named 16-ULP floating recomputation envelope.
- Refusals: `quality_policy_unknown_key`, `quality_policy_incomplete`, `quality_policy_digest_mismatch`, `quality_writer_uid_missing`, `quality_lineage_missing`, `quality_owner_neighbour_invalid`, `quality_face_orientation_invalid`, `quality_zero_area_or_distance`, `quality_nonfinite_geometry`, `quality_bl0_identity_violation`, `quality_positive_bl_contract_missing`, `quality_wall_edge_lineage_missing`, `quality_candidate_disk_entity_set_mismatch`, `quality_candidate_disk_metric_mismatch`, `quality_threshold_exceeded`.

## Gates and future validation

- BL=0: identity, requested=actual=0, no wall/front/side rows, zero layer-work. BL>=1: finite positive first/total thickness, requested=actual, full wall/front/side and open-side source-edge lineage, wall-edge normal/co-normal/feature evidence; closed unpaired side refuses.
- L0 all products BL=0 identity/zero-work/digest and reversed-face signed check. L1 Tet/Hex/Poly closed plus Tri/Strict Quad/TRI+QUAD planar at BL=0/1, vary every policy input, strict topology zero. L2 cube/sphere/NACA/ridge/open-patch/narrow-gap/complex CAD-STL at BL=0/1/3/8 plus growth/repeat matrix, UIDs/receipts identical. L3 tamper policy/source/semantic/writer/disk, omit lineage, reverse face, violate threshold/height, and require named refusal/rollback.

## Known blockers

- Current witness still has `abs(dot)` and coordinate-derived disk identities; Tet disk quality is a separate narrow kernel.
- No full cross-engine UI-to-writer parameter inventory proves every user setting reaches an actual writer.
- Writer-owned collision, feature-sector transition, curved offset bijectivity, and production-destination binding remain separate cards.
- Cube-only/default-off sidecar evidence is not release evidence; missing curved-BL DOI equations block release thresholds.

## Actual 062 execution correction

The bounded re-review text above was stale transport metadata and is superseded by this record. Curie planner `019fcd34-0bb1-7f43-8b4a-e0dff6ada1cc` was requested with `gpt-5.6-terra`, high reasoning, priority service, and fast-off policy. It completed after one 900000 ms wait. The API exposes no `fast` field, so fast-off is recorded as a lifecycle policy rather than an API parameter. `mark-planned` passed before implementation.

Implementation is authorized for this card. The v3 route remains default-off and evidence-only; it does not claim product release promotion. The card is complete only when the C++ module builds and the direct BL=0/BL>=1, policy-seal, duplicate-topology, and candidate/reread parity tests pass.

## Card status

- C++23 v3 policy seal, signed orientation-aware quality evaluation, writer UID/lineage admission, and candidate/reread parity were implemented.
- No coordinate-derived IDs are minted by v3; no `abs(dot(...))` is used in its internal orientation equation.
- Existing v1/v2 APIs remain untouched for rollback and compatibility.
- Product routing and cross-engine promotion remain follow-on cards; this bounded witness is not release evidence by itself.
