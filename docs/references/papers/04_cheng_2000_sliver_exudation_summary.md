# Cheng et al. 2000 - Sliver Exudation

## Why It Matters For Native Tet

- Target problem: Delaunay refinement can still leave sliver tetrahedra even when vertices are well-spaced.
- Core idea: assign small real weights to vertices so the weighted Delaunay triangulation avoids slivers.
- Mechanism: for each vertex, compute weight subintervals that would admit bad slivers, then choose a weight outside those forbidden intervals.
- Algorithmic form: maintain weighted Delaunay while increasing one vertex weight; topology changes only at discrete flip events. The paper describes this as skyline search over forbidden rectangles.
- Parallel option: color the vertex neighborhood graph; vertices in one color class can receive weights independently.

## Direct Implementation Lesson

- Do not treat this as a simple post-filter. Correct version needs regular triangulation support, weighted predicates, and flip-event maintenance.
- Boundary conformity is explicitly hard for bounded and non-convex domains. Native tet should keep this as an internal-sliver pass unless boundary-preserving weighted flips are fully proved and tested.
- Current project path already matches the safe subset: `AUTO_TESSELL_NATIVE_TET_WEIGHTED_23=1` gates local weighted 2-3/3-2/4-4 regularization behind boundary-face, cell-delta, negative-volume, and quality guards.

## Next Native Tet Use

1. Keep local weighted regularization opt-in until matrix evidence shows no boundary regressions.
2. Add diagnostics that report which slivers are internal versus boundary-touching before any weighted operation.
3. If internal sliver cases remain in 100+ regression, extend from sampled weights to skyline-like forbidden interval search for a small vertex neighborhood.
4. Only after that, consider C++ regular triangulation primitives for performance and exact weighted predicates.

PDF: `docs/references/papers/source/pdf/04_cheng_2000_sliver_exudation.pdf`
