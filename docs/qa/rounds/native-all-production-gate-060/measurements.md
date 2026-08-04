# Measurements — native-all-production-gate-060

## Build

- `cmake --build auto_tessell_core/build --target native_tet_bl_admission -j2`: PASS.
- `cmake --build auto_tessell_core/build --target native_tet_polymesh_quality -j2`: PASS.
- C++23 candidate route remains `default_off`; no publication or merge was performed.

## Focused corpus

Command:

```text
PYTHONPATH=auto_tessell_core/build pytest -q \
  tests/test_native_tet_bl_admission_cpp23.py \
  tests/test_native_tet_bl_admission_bridge.py \
  tests/test_native_tet_bl_writer_v2_cpp23.py \
  tests/test_native_tet_authoritative_candidate_graph_cpp23.py \
  tests/test_native_tet_candidate_disk_quality_parity.py \
  tests/test_native_tet_authoritative_candidate_artifact_cpp23.py \
  tests/test_native_tet_writer_artifact_bridge_cpp23.py \
  tests/test_native_tet_writer_outer_admission_cpp23.py \
  tests/test_native_tet_writer_outer_collision_cpp23.py \
  tests/test_native_tet_polymesh_quality.py \
  tests/test_native_tet_quality_policy.py \
  tests/test_native_tet_polymesh_quality_signed_cpp23.py
```

- Result: **29 passed**, 4.13 s.
- Python syntax check for the new bridge/tests: PASS.

## Measured evidence

| Evidence | Result |
| --- | --- |
| Writer-owned outer faces for one positive Tet | 4 faces, deterministic sorted incidence |
| Positive outer collision evidence | broad-phase 0, narrow-phase 0, 64-hex digest |
| Overlapping two-Tet candidate | deterministic refusal; broad and narrow hit counts > 0; first pair and digest recorded |
| Source lineage fields | source face/edge, feature, patch, physical group, component and provenance echoed for all outer faces |
| User-input configurability | `target_cells=4` and `target_cells=999` both re-evaluated; changing the value changes the canonical digest |
| Tampered user-input digest | fail-closed at policy stage with `input_parameters_unsealed_or_incomplete` |
| Disk quality orientation | correct internal face 6.2085° (<10° fixture tolerance); reversed orientation 173.7915° (>170°), quality refused |
| BL=0 regression | existing identity/zero-work tests remain green in the focused corpus |

## Limits observed

- The new writer-owned surface route is an explicit candidate API; production promotion remains default-off.
- The legacy admission API still accepts its caller-supplied collision triangle argument for compatibility; callers must migrate to the new writer-owned API before release claims.
- The input digest seals and replays the complete supplied configuration, but the UI/schema inventory still needs to be expanded for every engine-specific parameter before product release.
