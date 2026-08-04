# Improvement plan — native-all-production-gate-060

## Goal

native-all-production-gate-060

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

## 060 detailed plan

### Planner transport

- Arendt planner `019fcd0e-1298-7652-bb78-30174cffd667` completed after one 900000 ms wait with `timed_out=false`; no code or routine tests were delegated.
- Requested gpt-5.6-terra/high/priority. The agent API exposes no `fast` field; fast-off is lifecycle policy only. The prior short-timeout/forced-close failure mode is not repeated.

### Core card — WriterOwnedOuterSurfaceAdmission

- 060-A — issue `OuterFaceDescriptor` at writer generation time with writer face ID, oriented cycle, owner/neighbour, role, source-face/source-edge inverse, feature/patch/physical-group/component and provenance.
- 060-B — run deterministic AABB plus exact-predicate collision admission on writer-owned outer faces. Remove caller-provided collision triangles from the authoritative bridge and record first pair, pair counts and collision digest.
- 060-C — use one signed-direction PolyMeshQualityKernel for candidate and disk reread. Internal non-orthogonality uses signed owner-to-neighbour dot; boundary uses oriented face-area and face-centre vector. Preserve max/p95 and worst writer-face IDs.
- 060-D — make the complete user input policy/configuration explicit and canonical-digest-bound: BL count, layer thickness/growth/first height, wall-edge/feature controls, target count, skewness/non-orthogonality/aspect/scaled-Jacobian/min-volume limits, topology and authority options. No hidden C++ acceptance values.
- Default remains candidate-only/default-off. BL0 returns bitwise identity before ledger, collision, quality, graph, serializer, or sidecar work.

### Gates and rollback

- Require sealed source/semantic/BL-config/quality-policy digests, source oriented face/edge IDs and all feature/boundary/patch/physical-group/component/provenance inverse records.
- Reject duplicate/non-manifold/inverted/non-positive Tet, missing inverse, closed-source unpaired side face, collision, quality-policy failure, graph/readback mismatch or tamper. Set `candidate_discarded=true` and request atomic rollback.
- Do not claim cube positive BL until an explicit feature-sector transition exists; fail with a deterministic reason.

### Verification ladder

- L0: BL0 bitwise identity and zero-work, including no quality/collision sidecar.
- L1: planar triangle and smooth tetra BL1/2; vary each user input and verify re-evaluation plus policy/receipt digest change.
- L2: sphere BL1/3, three deterministic runs; compare outer graph, collision digest, quality max/p95/worst face and serialized bytes. Narrow-gap must refuse identically.
- L3: cube feature-sector refusal; stage -> disk reread -> one-byte tamper -> graph/quality mismatch -> atomic rollback. Count tuning remains after quality gates.

### Evidence

- Preserve planner memo, literature/DOI record, user-input echo, all source/semantic/BL/policy digests, writer-face ledger/inverse, graph/serialization/readback hashes, collision counts/first pair/digest, candidate/disk quality, measurements and rollback/refusal reasons.
