# BOOLMERGE5a: N-surface native-tet union routing

## Goal

Extend the desktop native-tet boolean-union route from exactly two input
surfaces to any `N >= 2`, preserving upload order and existing single-input API
behavior.

## Changes

- Permit multi-surface generation only for `mesh_type=tet` with tier `auto`,
  `native_tet`, or `tier_native_tet`.
- Coerce `auto` to `native_tet`.
- Pass every surface after the primary through `additional_input_paths` in
  upload order.
- Cover three-surface server routing and three-input per-surface OR inclusion.

## Out of scope

- Boolean intersection or difference.
- Hex-dominant or poly multi-surface generation.
- Patch provenance and boundary-layer assignment per source surface.
- Mesher or orchestrator algorithm changes.

## Verification

- `TestMultiSurface`
- Focused boolean-merge tests
- Python compilation and whitespace/error-marker diff checks

## Result

- `TestMultiSurface`: `24 passed`
- Boolean-merge focused suites: `11 passed`
- Changed Python files compile successfully.
- Scoped `git diff --check` passes.
