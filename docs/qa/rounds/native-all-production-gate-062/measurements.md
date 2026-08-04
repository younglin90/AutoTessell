# Measurements — native-all-production-gate-062

## Card

Default-off C++23 `NativeQualityWitness/v3` was added to the existing `native_quality_witness` module. It seals the complete user policy, measures signed internal orientation/non-orthogonality, face-centre skewness, family-tagged aspect ratio, positive writer-supplied cell volume, writer UID/lineage rows, and candidate/reread parity.

## Build

- Command: `cmake --build auto_tessell_core/build --target native_quality_witness --clean-first -j2`
- Result: PASS; clean C++23 compile and link.
- Compiler warnings: none after size-type normalization.
- Existing v1/v2 bindings: retained.

## Focused evidence

| Case | Result | Measured evidence |
| --- | --- | --- |
| Cube, BL=0 | PASS | skewness max `0.0`, aspect max `1.0`, cell volume min `1.0`, topology duplicate/non-manifold/inverted `0/0/0` |
| Cube, BL=1 | PASS | actual layer `1`, positive-thickness and wall-edge lineage evidence required and present; skewness max `0.0`, aspect max `1.0`, volume min `1.0` |
| Correct two-tet internal winding | PASS | signed internal non-orthogonality max `0.0°` |
| Reversed two-tet internal winding | PASS refusal | `quality_threshold_exceeded` at configured `30°` limit; no `abs(dot(...))` masking |
| Candidate vs reread | PASS | policy/source/semantic/config/writer digests, entity UIDs, and quality distributions equal; 16-ULP envelope declared |
| Duplicate face | PASS refusal | `quality_duplicate_face` |
| Missing positive-BL evidence | PASS refusal | `quality_wall_edge_lineage_missing` |
| Unknown policy key | PASS refusal | `quality_policy_unknown_key` |

## Test totals

- v3 policy/BL/parity/signed-orientation tests: `9 passed`.
- Existing quality/writer regression tests: `18 passed`.
- Combined focused gate: `27 passed`.

## Scope boundary

This is an evidence-only, default-off witness card. It does not prove native Tet/Hex/Poly/Tri/Quad/TRI+QUAD production routing, CAD/STL authority, curved positive-BL bijectivity, complex-shape release corpus, or user-interface-to-writer coverage. Those remain separate cards and release blockers.
