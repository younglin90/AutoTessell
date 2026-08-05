# POLY-VORONOI-ORIENTATION-VALIDITY-REPAIR-1 Evidence

Date: 2026-07-31

Status: bounded orientation repair passed its declared validity acceptance;
one separate stale BL=0 cell-count oracle remains unresolved. Master
integration remains prohibited pending stack review.

## Root cause

`_ccw_sort_face_vertices` derives a plane normal from SVD. Its sign is
arbitrary. Faces were therefore sorted consistently in their local plane but
not relative to the owning cell. A shared ridge could have the same winding in
both owners, and a cell could contain a mixture of inward and outward loops.

A read-only small-sphere probe captured three final cells and 132 faces. It
found 59 inward loops and one negative-volume cell. Orienting each loop away
from its cell centroid reduced negative cells from one to zero, with zero
degenerate cells, an identical canonical topology digest, and identical
coordinates.

## Mechanism

After all drop and smoothing passes, each final cell computes the centroid of
its unique existing vertices. A Newell-style polygon normal is compared with
the vector from the cell centroid to the face centroid. Only a negative,
scale-resolved alignment reverses the loop. Reversal keeps the first provenance
anchor vertex fixed. Near-zero alignments are left unchanged and the mandatory
pre-write validator remains fail-closed.

The pass changes no coordinate, face membership, sorted canonical face key,
cell order, or cell count. Adjacent cells orient a shared face oppositely.

Primary metric: five unchanged legacy native-Poly success failures `5 -> 0`.

## Verification

- Focused orientation tests: `5 passed in 3.11s`.
- Mixed-winding tetra: negative=0, degenerate=0, coordinates and topology
  unchanged.
- Two-cell fixture: shared face has exact opposite cyclic winding.
- Coplanar ambiguous fixture: no forced direction, typed refusal, writer=0.
- Synthetic orientation output: identical across three runs.
- Real sphere polyMesh bytes: identical across three runs.
- Native-Poly legacy plus pre-write tests: `16 passed in 16.23s`.
- Full focused Poly stack: `40 passed in 18.47s`.
- Dense cylinder, `target_edge_length=0.02`: 78.252 seconds, 8948 cells,
  95288 points, 65071 reversed faces, zero ambiguous faces, negative cells
  `4497 -> 0`, degenerate=0, five canonical polyMesh files, no reconstruction.

An additional no-drop-holes sweep produced eight passes and one failure. The
remaining assertion requests `bl_layers=0` but expects 36 sphere cells. The
corrected BL=0 invariant generates 27 base cells; the prior hidden prism path
supplied the other nine. This stale oracle was not edited in the orientation
card.

## Limits

- Dense cylinder quality remains grade D; validity does not imply release
  quality.
- Full PipelineOrchestrator terminal-refusal reconstruction suppression remains
  a separate common card.
- Explicit source-patch corpus validation remains required before a shape and
  provenance release gate can pass.

Rollback conditions: coordinate, membership, canonical face-key, cell-order,
patch provenance, or cell-count drift; shared-face equal winding; degenerate or
negative-volume increase; invalid writer invocation; nondeterminism; timeout;
or any `vendor/dependencies/` change.
