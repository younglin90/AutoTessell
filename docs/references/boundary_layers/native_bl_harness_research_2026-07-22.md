# Native Wall-Face Boundary-Layer Harness Research

## Decision

Apply same hard contracts to native tet, hex-dominant, and poly:

1. Typed immutable wall-face provenance selects BL faces before extrusion.
2. Local feature size and collision distance cap total layer thickness.
3. Each accepted layer step keeps prism/cavity signed volume positive and front intersections zero.
4. Reject output unless non-manifold faces and negative volumes are zero, non-orthogonality is at most 70 degrees, skewness at most 4, and aspect ratio at most 200.

Last limits match OpenFOAM-compatible defaults in `core/schemas.py`. They are acceptance limits, not quality-optimum targets. Wall prisms may be anisotropic; ranking must also retain wall-normal alignment and layer growth.

## Tet

Constrained Delaunay recovery must preserve a BL shell before cavity replacement. Bounded shell cavities are eligible only when every replacement tet has positive signed volume and maintains boundary constraints. [Shewchuk 1998](https://doi.org/10.1145/276884.276894)

For the layer itself, use generalized advancing layers: advance selected wall faces, broad-phase test front collision, shrink or terminate at narrow gaps, and preserve a closed core interface. [Garimella and Shephard 2000](https://doi.org/10.1002/1097-0207%2820000910/20%2949%3A1/2%3C193%3A%3AAID-NME929%3E3.0.CO%3B2-R)

First card: `TET-BL-SHELL1`. Add provenance-preserving shell-cavity eligibility around `CDT2-SHELL`; defer no-cavity expansion to `CDT3-NOCAVITY`.

## Hex-Dominant

Treat BL outer-front as immutable interior boundary for octree/cartesian core. Create a wall-only closed shell, remove intersecting cut leaves, then fill transition cavity with validity-gated hybrid cells. Advancing-front collision and unfillable cavities are known all-hex failure modes, so closure and manifold checks precede smoothing. [Brückler et al. 2022](https://doi.org/10.1145/3554920)

First card: `HEX-BL-SHELL1`. Extend `HEXDOM-WALL1` through common finalization and report shell, transition, core quality separately. `HEXDOM-REPORT1` is prerequisite because missing report fields hide quality evidence.

## Poly

Keep prism BL shell outside tet-to-poly dualization. Dualize only constrained core, then preserve shell/core interface and semantic patch provenance in writer. Direct clipped Voronoi prism insertion remains experimental because clipping/snap can violate non-convex geometry and topology contracts.

VoroCrust uses protected paired boundary sites to form conforming Voronoi cells without clipping, including non-convex and non-manifold domains and sharp features. [Abdelkader et al. 2020](https://doi.org/10.1145/3337680)

First card: `POLY-BL-SHELL1`. Wire `POLY-WALL1` provenance into shared BL/transition path, require signed-pyramid positivity for every dual cell, then fix cylinder solid-volume failures before optimization.

## Loop

1. `gpt-5.6-sol` writes one research-backed card per engine. No code edits.
2. `gpt-5.6-terra` receives each card in distinct Git worktree. Tet, hex, poly run in parallel.
3. Each worker runs focused regression, then generates BL-enabled representative case.
4. `scripts/validate_native_bl_case.py` writes JSON from `NativeMeshChecker` plus duplicate-face topology detection.
5. Card passes only when hard gates and existing solid-volume tests pass. Failure creates next planner card; never widen thresholds or clean unrelated dirty state.

## Runner Setup

Set `planner.command` and `improver.command` in `harness/native_bl_quality_loop.json` to argument arrays for the available agent runner. Supported placeholders are `{brief}` and `{output}` for planner; `{brief}`, `{plan}`, `{output}`, and `{engine}` for improvers. Then run:

```bash
python3 scripts/run_native_bl_quality_loop.py prepare
python3 scripts/run_native_bl_quality_loop.py planner --run-dir <run-dir>
python3 scripts/run_native_bl_quality_loop.py improvers --run-dir <run-dir>
```

The dispatcher requires three distinct Git worktrees and rejects the current dirty worktree. This prevents parallel agents from mixing tet, hex, and poly edits with pre-existing work.

## Non-Goals

- No patch-name-derived wall selection.
- No concurrent cross-engine edits in current dirty worktree.
- No new external meshing dependency.
- No automatic reset, checkout, stash, commit, or broad cleanup.
