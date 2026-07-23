# Hu et al. 2020 - Fast Tetrahedral Meshing in the Wild

## Bibliography and access

- Yixin Hu, Teseo Schneider, Bolun Wang, Denis Zorin, and Daniele Panozzo,
  *ACM Transactions on Graphics* 39(4), Article 117, 18 pages, 2020.
- DOI: https://doi.org/10.1145/3386569.3392385
- Public copy read: https://cims.nyu.edu/gcl/papers/2020-fTetWild.pdf
- Project: https://wildmeshing.github.io/ftetwild/
- Status: `FULL_READ` (18/18 pages); rendered inspection of pp. 5, 7, 9, and 10.

## Contract and guarantee boundary

Input is an arbitrary floating-point triangle soup. Parameters are target edge
length `l` and geometric tolerance `epsilon`. The algorithm maintains a valid
floating-point tetrahedral mesh at every stage: all tets have positive volume,
checked with exact predicates. Successfully inserted triangles form a tracked
surface contained in the input's `epsilon`-envelope.

The guarantee is deliberately narrower than a naive reading suggests:

- an input triangle may fail insertion; the paper reports no such failure in its
  dataset but explicitly does not prove that all input triangles insert;
- the final mesh has no theoretical quality bound;
- extracting an "inside" volume with flood fill or winding number is heuristic
  for open shells, inconsistent nested orientations, or ill-defined solids;
- surface accuracy is tolerance-bounded, not exact boundary preservation.

## Algorithm

1. Preprocess inside a smaller `epsilon_prep = 0.8 epsilon` envelope: merge
   near-coincident vertices and collapse manifold edges only if incident
   triangles remain inside the smaller envelope.
2. Build a background Delaunay mesh of preprocessed vertices plus uniform box
   samples, excluding samples closer than `epsilon` to the surface.
3. Insert one input triangle at a time. Find cut tets, snap nearby vertices when
   orientation stays positive, intersect the triangle plane with tet edges, and
   use a precomputed subdivision table. Global vertex ordering makes shared-face
   triangulation consistent. Reject the whole transaction if a sub-tet volume is
   too small.
4. Improve with split, collapse, swap, and smoothing; after every three
   improvement iterations retry rejected triangles.
5. Reject every operation that inverts a tet or moves the tracked surface out of
   the envelope.
6. Optionally classify tets with flood fill, generalized winding number, or
   provenance-aware Boolean rules.

The table has 41 realizable edge-cut configurations in seven symmetry classes.
This table-driven connectivity step, transaction rollback, and rejected-face
retry are the core robustness mechanism; BSP seeding plus unconstrained
re-Delaunay is not equivalent.

## Envelope and quality details

Triangle containment is checked by sampling with a conservative compensation
for sampling error. Checking only tracked vertices is insufficient: an edge or
triangle interior can leave the tolerance tube while its vertices remain inside.

Quality uses conformal 3D AMIPS
`trace(J^T J) / det(J)^(2/3)`, with optimum 3. Floating-point AMIPS becomes
permutation-unstable for extremely bad tets (around energy `1e8`). fTetWild
evaluates a rational cubic form in this regime but still computes the search
direction in floating point. The standard experiment stops at max AMIPS below
10 or 80 iterations.

## Experiments

The paper reports 100% completion on Thingi10k when larger time limits are
allowed and 99.97% within 3 hours/32 GB, with 49.8 s average over successful
runs. The authors stress that average times across methods are not directly
comparable because success subsets differ. Envelope checks grow expensive as
`epsilon` shrinks. Output quality is empirically similar to TetWild; no formal
quality theorem is claimed.

## Evidence for Native Tet

- `ftetwild_main_loop.py:115-132` performs a one-shot BSP point proposal followed
  by Bowyer-Watson insertion. It does not implement per-triangle cut-tet
  discovery, snapping, the subdivision table, or atomic triangle transactions.
- The loop never maintains a rejected-triangle set or retries it every three
  improvement iterations.
- `ftetwild_main_loop.py:146-154` and `envelope.py:145-159` inspect only boundary
  vertices, so the current code cannot claim tracked-triangle containment or a
  symmetric Hausdorff bound.
- `ftetwild_main_loop.py:177-183` locks all original surface vertices and protects
  original surface edges, whereas the paper allows the tracked surface to move
  within the envelope. This sacrifices the mechanism used to heal near defects.
- The module's 4/3 split and 4/5 collapse thresholds are not stated in this
  paper; they should not be attributed to its Algorithm 1.
- The code filters by `inside_robust` without exposing the paper's explicit
  flood-fill versus winding-number semantic choice and failure mode.

## Falsifiable implementation cards

### TET-WILD-1 - Incremental triangle transaction

- Implement cut-tet discovery with exact predicates, delta snapping,
  table-driven subdivision, shared-face global ordering, and atomic rollback.
- Test all 41 realizable cut configurations and all adjacent-face consistency
  pairs; every accepted output tet must have exact-positive orientation.

### TET-WILD-2 - Tracked surface and retry queue

- Record every inserted input triangle's cover/provenance and every rejected
  triangle's reason. Retry after each three optimizer passes.
- Test: a near-degenerate insertion rejected initially becomes insertable after
  local quality improvement without losing previously tracked covers.

### TET-WILD-3 - Triangle envelope containment

- Replace vertex-only checks with conservative triangle containment; report the
  one-sided tracked-to-input tolerance separately from input-to-tracked coverage.
- Test: construct a bowed edge/triangle whose endpoints pass but interior exceeds
  `epsilon`; the new gate must reject it.

### TET-WILD-4 - Stable AMIPS transaction

- Trigger high-precision/permutation-invariant energy evaluation for extreme
  elements and use exact orientation for line-search acceptance.
- Test: all 24 vertex permutations of Appendix B's tet return the same accept/
  reject decision within a declared tolerance.

### TET-WILD-5 - Explicit volume semantics

- Expose `flood_fill`, `winding`, and `provenance_boolean` as separate modes.
- Test open shells and inverted nested components; no mode may silently label a
  heuristic result as a uniquely defined solid.
