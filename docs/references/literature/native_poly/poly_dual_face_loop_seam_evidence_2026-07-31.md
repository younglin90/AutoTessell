# Native poly dual source-cap seam evidence (2026-07-31)

## Card

`POLY-DUAL-FACE-LOOP-SEAM-ROOTCAUSE-1`

Primary gate: every source-triangle barycentric cap has exact point
provenance and closes each incident dual-cell shell.  Shape preservation,
mesh validity, and source patch semantics are hard gates.  Star-cell admission
and target-cell control are out of scope.

## Root cause

The unclassified path reused `scipy.spatial.ConvexHull` cap loops.  Qhull is
allowed to omit collinear boundary-edge midpoints and source vertices lying
inside a coplanar cap.  A cylinder end-cap exposed the first exact seam:

- separator face: `[320, 192, 193, 321, 353]`
- hull cap: `[532, 510, 320, 321, 464]`
- point `353`, the primal edge `(0, 5)` midpoint, lies on cap edge
  `(320, 321)` but was absent from that cap loop.

That is a T-junction, not a tolerance problem.  Moving points or relaxing
validity would violate the shape contract.

## Repair

Boundary vertices are registered for both classified and unclassified input.
Both paths now construct each source cap from the source triangle's exact
barycentric subface:

`[source vertex, edge midpoint, source face centroid, edge midpoint]`.

The change moves no point and preserves classified patch labels.  Unclassified
input retains the single `defaultWall` patch.  ConvexHull remains responsible
for the non-cap dual-cell faces; star-cell admission is unchanged.

## Verification

Focused provenance and compatibility tests:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
AUTOTESSELL_EXT_BUILD_DIR=/home/younglin90/work/claude_code/AutoTessell/auto_tessell_core/build \
PYTHONPATH=. /home/younglin90/work/claude_code/AutoTessell/.venv/bin/python \
  -m pytest -q -p no:cacheprovider \
  tests/test_native_poly_dual.py::test_tet_to_poly_dual_unclassified_caps_close_source_triangle_seams \
  tests/test_native_poly_dual.py::test_tet_to_poly_dual_preserves_classified_multi_patch_caps \
  tests/test_native_poly_dual.py::test_tet_to_poly_dual_preserves_a_valid_integer_tet_input
```

Result: `3 passed in 2.02s`.

Cube solid-volume regression:

```text
4 passed in 35.62s
```

The new pyramid fixture verifies all 24 exact source caps, source vertex
provenance, per-cell closed-edge incidence, and unchanged `defaultWall`
semantics.

## Remaining gate

This prerequisite does not relax the cylinder's rejected star cells
(`54/73`, `539` invalid sub-tetrahedra).  Runtime-only admission still exposes
warped boundary-edge separator self-intersections and high skewness.  Those are
separate fail-closed cards; this commit must remain unmerged until the native
poly module meets its integration acceptance contract.
