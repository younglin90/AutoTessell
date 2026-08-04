# Measurements — round 069

## Implementation

- CMake reconfigured successfully with OCCT still fail-closed because
  `AUTOTESSELL_OCCT_SDK_ROOT` is unset.
- Built `native_tet_persisted_volume_artifact_cli` and
  `native_tet_persisted_volume_artifact` successfully.
- Focused regression with `PYTHONPATH=auto_tessell_core/build`: **7 passed**.
- The child test covered two independent fresh-process replays, source
  orientation tamper refusal, and non-positive persisted Tet refusal.

## Observed metrics

- Fixture certificate reported `topology_duplicate=0`, `non_manifold=0`,
  `inverted=0`, `positive_measure=true`, and deterministic certificate hash.
- The child recomputed a positive tetra measure and finite edge aspect ratio
  from disk; it did not receive producer arrays or Python objects.
- User-controlled BL schedule regression for N=0/1/3/8 and h0/growth passed
  in the existing Tet writer test.

## Failure and limit

The first combined run had one environment import failure because
`native_tet_bl_writer` was not built/PYTHONPATH-configured; rebuilding the
target and rerunning produced 7/7 passes. This card is still not production
release evidence: no actual all-engine mesher invokes the child route yet.
