# Native Tet Topology-Over-Target Contract — 2026-07-30

## Card

`TET-STRICT-TOPOLOGY-CORPUS-PROBE-1`

## Priority

The user deferred target-cell acceptance for native tet.  Strict topology,
writer validity, source-shape admission, and validity remain the acceptance
conditions.  Target count stays recorded as Gate-6 telemetry and is not erased
or described as successful.

## Evidence

On the unit-cube draft request (`target_cells=2000`, `max_iter=1`), the current
harness records `3635` cells (`+81.75%`).  This is a Gate-6 failure, not a
strict-topology failure.  The same run admits the final source-shape contract,
reports zero negative volumes and non-orthogonality below 90 degrees, and writes
only tetrahedron-encoded cells with a writer cell count equal to the result.

The regression therefore no longer accepts or rejects topology based on a
numeric target ratio.  It keeps the requested count, actual count, and ratio in
the test calculation for later target-following work.

## Research basis

CGAL 6.2 separates prescribed sizing from topology and feature-complex
preservation in its tetrahedral remeshing documentation.  This card uses that
separation as an independent contract design only; no CGAL code or dependency
is used.

- https://doc.cgal.org/latest/Tetrahedral_remeshing/index.html
- https://doc.cgal.org/latest/Tetrahedral_remeshing/group__PkgTetrahedralRemeshingRef.html
