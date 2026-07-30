# Native Tet Strict-Topology Duplicate-Group Repair — 2026-07-30

## Card

`TET-STRICT-TOPOLOGY-CLASSIFY-RELAX-1`

Primary metric: strict polyMesh write succeeds without accepting a residual
three-or-more cell face incidence.

Rollback condition: reject the cleanup unless output boundary face keys are
identical and the post-cleanup tet audit reports no duplicate, degenerate,
open-edge, non-manifold-edge, or non-manifold-face entity.

## Evidence

`tests/benchmarks/cylinder.stl`, `target_cells=2000`, with external rescue
paths disabled, reached final sync with 1,499 tets and four strict writer
rejections.  The four faces each had four incidences.  Investigation found two
exact duplicate tetrahedron groups, not zero-volume tets:

- duplicate groups: 2
- duplicated rows: 4
- zero-volume tets: 0
- minimum absolute tet volume: `7.658280936520336e-06`

Dropping only one duplicate leaves a three-cell face.  Dropping every member
of each duplicate group yields 1,495 tets with:

- boundary face keys unchanged: 216 before / 216 after
- boundary area unchanged: `4.900018975620`
- non-manifold faces: 4 -> 0
- duplicate tets: 2 -> 0
- degenerate tets: 0
- open and non-manifold boundary edges: 0
- strict writer: accepted, 1,495 written tet cells

## Decision

Do not relax OpenFOAM's one-owner/one-neighbour face model.  A true 3+-cell
face cannot be represented safely by silently discarding a cell.

Allow one narrowly bounded recovery before the strict writer:

1. identify exact duplicate tetrahedron groups by sorted vertex ids;
2. remove all members of each group, never an arbitrary representative;
3. prove boundary face-key equality;
4. prove the full post-cleanup topology audit; and
5. otherwise retain the original candidate so the strict writer fails closed.

This makes the topology gate materially less brittle for redundant internal
cells while keeping genuine non-manifold output rejected.

## External Research

CGAL 6.2 Tetrahedral Remeshing describes topology-preserving atomic operations
and separates feature-complex preservation from sizing optimization:

- https://doc.cgal.org/latest/Tetrahedral_remeshing/index.html
- https://doc.cgal.org/latest/Tetrahedral_remeshing/group__PkgTetrahedralRemeshingRef.html

The implementation is independent; no CGAL or third-party source was copied.
