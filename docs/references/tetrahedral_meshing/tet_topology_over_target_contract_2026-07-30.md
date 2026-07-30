# Native Tet Topology-Over-Target Contract — 2026-07-30

## Card

`TET-STRICT-TOPOLOGY-CORPUS-PROBE-1`

## Priority

The user deferred target-cell acceptance for native tet.  Strict topology,
writer validity, source-shape admission, and validity remain the acceptance
conditions.  Target count stays recorded as Gate-6 telemetry and is not erased
or described as successful.

## Evidence

The deterministic admission regression injects a source-valid single tetrahedron
against `target_cells=2000`.  It records the exact ratio `1/2000` while still
requiring source admission, zero negative volume, under-90 non-orthogonality,
and promotion of the valid case.  The ratio is deliberately not an admission
criterion; it is retained as Gate-6 telemetry.

A real unit-cube probe is not used as an acceptance proof because the generator
is currently nondeterministic and one observed `2018`-cell candidate was
correctly rejected by the source hard gate (`hausdorff_relative=0.0647 > 0.05`,
with planar coverage below the B-grade floor).  No output was promoted.  This
is shape preservation working as intended, not a reason to weaken the shape
or topology contract.  Real strict writer/topology evidence remains in the
cylinder duplicate-repair regression.

## Research basis

CGAL 6.2 separates prescribed sizing from topology and feature-complex
preservation in its tetrahedral remeshing documentation.  This card uses that
separation as an independent contract design only; no CGAL code or dependency
is used.

- https://doc.cgal.org/latest/Tetrahedral_remeshing/index.html
- https://doc.cgal.org/latest/Tetrahedral_remeshing/group__PkgTetrahedralRemeshingRef.html
