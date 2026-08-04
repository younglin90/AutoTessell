# Improvement plan — native-all-production-gate-066

## Goal

native-all-production-gate-066

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


## Planner transport and critical card

The sole planner was agent 019fcdab-7218-76a0-8f90-281092f7401d (Hooke), requested as gpt-5.6-terra, high reasoning, priority service, fast OFF by lifecycle policy. The API exposes no explicit fast field; this is recorded rather than claimed as an API argument. It completed after a long wait and was closed normally. It did not implement or test code.

### 066-AQTE-ActualWriterBinding

Bind the default-off C++23 AQTE callback boundary to actual Native Tet and surface wall-edge writers. A writer callback must return an exact AQTE candidate containing its own artifact handle/hash, writer-issued UIDs, source/parent IDs, feature/patch/physical-group/component/provenance rows, BL roles/layers, strict topology, family quality witness, and positive measure. A separate reread callback must return the persisted artifact; only parity permits publish.

Sequence:

    authoritative ledger -> intent -> AQTE capability -> actual C++ writer callback
    -> staged candidate -> independent persisted reread -> publish or rollback

BL=0 requires actual layer work zero and source/entity/lineage identity. BL>=1 requires exact actual layers, wall/front/side roles, positive measure, source-sector binding, collision/visibility safety, and full atomic discard on refusal. Quality ordering is topology -> orientation/measure -> authority/lineage -> BL -> signed non-orthogonality/skewness -> family aspect -> count.

The hot state transition is C++23. Python only transports mappings and callback handles. No default, geometry, quality, topology mutation, coordinate rematching, ID minting, Tri clone, quad relabel, or count override is permitted.

L0 covers callback state, single-use, rollback and receipt tamper. L1 covers actual Tet/surface C++ writer calls on cube/curved patch at BL=0/1 with artifact and reread parity. L2 covers sphere/NACA/ridge/narrow gap/T-junction/complex CAD/STL and BL=0/1/3/8. L3 covers separate-process reread, repeatability, package provenance and receipt tamper.

### Implementation decision

Added C++ run_writer_transaction_v1(transaction, writer_callback, reread_callback) and the lossless Python transport. Actual Tet and surface writer smoke tests call the C++ writer inside the callback. Both safely refuse before publish when writer-issued UID or complete quality witness is absent. Existing private artifact staging remains intact.
