# BOOLMERGE6: Multi-surface boundary patch provenance

## Goal

Preserve each original STL as a deterministic OpenFOAM wall patch after
native-tet boolean meshing, and pass the exact source patch names to the
post-mesh boundary-layer stage.

## Changes

- Generate ordered `source_<index>_<sanitized-stem>` patch names.
- Build one `TriangleBVH` for each original STL and classify output boundary
  face centroids by nearest source surface.
- Batch each source BVH query across all boundary centroids. Resolve equal
  distances by original input order.
- Let the polyMesh writer use batch classifiers while preserving its existing
  per-face callback and fallback behavior.
- Lazily construct one classifier in native-tet and reuse it for both final
  polyMesh write sites. Fall back to the default wall patch if construction or
  classification fails.
- Seed `post_layers_wall_patch_names` for multi-surface orchestration without
  mutating caller-owned parameters or overriding an explicit caller value.

## Out of scope

- Hex-dominant or poly boolean meshing.
- Triangle-level provenance through boolean surface reconstruction.
- Changes to desktop or web routing.
- SciPy KD-tree dependencies.

## Verification

- Boundary provenance unit tests: naming, duplicate stems, nearest source,
  deterministic ties, and invalid inputs.
- Generic polyMesh writer batch and fallback tests.
- Mocked orchestrator tests for BL names and caller-map immutability.
- Existing boolean-union E2E extended to require both source patches with
  positive `nFaces`.

## Result

- Focused unit, writer, orchestrator, and union E2E suite: `22 passed`.
- Changed Python files compile successfully.
- New provenance module and tests pass Ruff.
- Scoped `git diff --check` passes.
