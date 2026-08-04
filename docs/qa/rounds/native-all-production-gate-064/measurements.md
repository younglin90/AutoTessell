# Measurements — native-all-production-gate-064

## Card

Default-off C++23 `native_transaction_intent` admission was added with a thin Python orchestration adapter. It proves that a lossless Electron/API request has exactly one primary consumer in the selected writer manifest before any writer call.

## Build

- Command: `cmake -S auto_tessell_core -B auto_tessell_core/build -DBUILD_NATIVE_TRANSACTION_INTENT=ON`.
- Command: `cmake --build auto_tessell_core/build --target native_transaction_intent -j2`.
- Result: PASS; compile, link, and Python adapter import pass with no compiler warnings.
- Runtime route: default-off; generated entities `0`; writer calls `0`.

## Direct evidence

| Case | Result | Evidence |
| --- | --- | --- |
| All sink categories | PASS | 11 explicit request parameters map one-to-one to source, surface/volume metric, BL, wall-edge, feature, topology, quality, count, replay, and provenance sinks |
| BL=0 | PASS | zero writer work, armed single-use rollback token, quality precedes count |
| BL=1 | PASS | accepted only with corridor receipt, exact actual layer and SPD edge evidence |
| Target-count change | PASS | request and intent SHA-256 both change; count remains secondary |
| Repeat intent | PASS | deterministic receipt SHA-256 |
| Duplicate/implicit/type/nonfinite input | PASS refusal | named request-schema, duplicate, type, and nonfinite reasons |
| Ambiguous/unconsumed manifest | PASS refusal | `intent_parameter_sink_ambiguous` / `intent_unknown_parameter` |
| Authority/topology tamper | PASS refusal | `intent_authority_ledger_missing` |
| Quality contract missing | PASS refusal | `intent_quality_contract_missing` |
| Missing/mismatched corridor | PASS refusal | `intent_positive_bl_corridor_missing` / `intent_layer_schedule_inconsistent` |
| Rollback token | PASS | armed token consumed once; staged candidate discarded on later failure |

## Test totals

- Intent C++ contract tests: `9 passed`.
- Python adapter tests: `2 passed`.
- Previous corridor/quality/writer regression gate: `32 passed`.
- Combined focused gate: `43 passed`.

## Scope boundary

This card proves request-to-manifest binding only. It does not bind a real Tet/Hex/Poly/Tri/Quad/TRI+QUAD writer, Electron UI endpoint, CAD/STL ingress, or candidate/disk mesh transaction. Protected Poly remains untouched. Actual writer binding and complex positive-BL release corpus remain blockers.
