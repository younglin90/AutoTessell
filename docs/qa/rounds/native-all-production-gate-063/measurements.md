# Measurements — native-all-production-gate-063

## Card

Default-off C++23 `native_wall_edge_metric_corridor` preflight was added. It certifies a directed wall-edge frame and anisotropic SPD metric before any product writer is invoked. It does not create mesh entities or alter count targets.

## Build

- Command: `cmake -S auto_tessell_core -B auto_tessell_core/build -DBUILD_NATIVE_WALL_EDGE_METRIC_CORRIDOR=ON`.
- Command: `cmake --build auto_tessell_core/build --target native_wall_edge_metric_corridor -j2`.
- Result: PASS; compile and link completed with no compiler warnings.
- Runtime route: `default_off_preflight_only`; writer calls: `0`.

## Direct evidence

| Case | Result | Evidence |
| --- | --- | --- |
| BL=0 | PASS | `disabled_identity`, actual layers `0`, layer work `0`, collision queries `0`, writer calls `0`, source authority digests retained |
| BL=1 planar directed sector | PASS | schedule `[0.1]`, total `0.1`, `metric_spd=true`, `t=(1,0,0)`, `c=(0,1,0)`, `n=(0,0,1)` |
| BL=1 quality | PASS | metric skew max `0`, signed non-orthogonality max `0°`, metric aspect `1`, positive measure `1` |
| Repeat/candidate-reread | PASS | deterministic receipt SHA-256 and digest parity |
| Unknown user input | PASS refusal | `policy_unknown_key` |
| Inconsistent first/final/total/growth | PASS refusal | `layer_schedule_inconsistent` |
| Source metadata tamper | PASS refusal | `source_binding_lost` |
| Hidden sector | PASS refusal | `visibility_failed` |
| Close obstacle | PASS refusal | `collision_clearance_failed` |
| Edge normal parallel to tangent | PASS refusal | `feature_frame_ambiguous` |
| Excess anisotropic metric aspect | PASS refusal | `metric_quality_failed` |

## Test totals

- Corridor card tests: `5 passed`.
- Previous NativeQualityWitness/writer regression gate: `27 passed`.
- Combined focused gate after the corridor build: `32 passed`.

## Scope boundary

This card is a shared, default-off feasibility certificate. It does not claim actual Native Tet/Hex/Poly/Tri/Strict Quad/TRI+QUAD writer integration, complex CAD/STL positive-BL transaction success, feature/physical-group output preservation, UI-to-writer delivery, or release packaging. The two unreadable DOI blockers remain recorded in `unreadable-dois.md`.
