# Shewchuk 1998 - Tetrahedral Mesh Generation by Delaunay Refinement

## Bibliography and access

- Jonathan Richard Shewchuk, *Proceedings of the 14th Annual Symposium on Computational Geometry*, pp. 86-95, 1998.
- DOI: https://doi.org/10.1145/276884.276894
- Public copy read: https://www.cs.jhu.edu/~misha/Spring16/Shewchuk98.pdf
- Status: `FULL_READ` (10/10 pages); rendered inspection of pp. 4, 7, and 9.

## Problem, assumptions, and guarantees

The input is a facet-bounded 3D piecewise-linear complex (PLC): vertices,
segments, and planar facets closed under intersection. The main theorem assumes
the projection condition; in the common convex-facet case, incident constraints
must be separated by at least 90 degrees. With radius-edge bound `B > 2`, the
algorithm terminates, produces a conforming Delaunay tetrahedral mesh, and
grades edge lengths according to local feature size. The paper does **not**
guarantee a positive minimum dihedral angle, elimination of slivers, or
size-optimality in 3D.

## Algorithm read from the paper

1. Build the Delaunay tetrahedralization of all input vertices.
2. Recover missing/encroached subsegments first. A segment is encroached when a
   vertex lies in its diametral sphere; bisect it and recurse.
3. Recover subfacets second. Maintain an independent 2D Delaunay triangulation
   for each PLC facet. Split an encroached subfacet at its circumcenter, unless
   that point encroaches a subsegment.
4. Refine skinny tetrahedra last by inserting their circumcenters. Reject a
   circumcenter that encroaches a subsegment/subfacet and refine that boundary
   constraint first.
5. Remove exterior convex-hull tetrahedra once all constraints are recovered,
   before quality refinement.

The priority `subsegment -> subfacet -> skinny tet` is essential. The termination
proof tracks insertion radii through a parent-child graph: splitting a skinny tet
multiplies the lower bound by `B`, while boundary encroachment can reduce it by
`1/sqrt(2)`. No decreasing cycle exists for `B >= 2`; good grading needs strict
`B > 2`.

## Quality and slivers

The radius-edge ratio catches needles, wedges, and caps but can miss arbitrarily
flat slivers. The experiments report useful dihedral-angle improvement, but the
paper explicitly labels it empirical. Boundary slivers, especially near small
input angles, remain difficult. Smoothing and topology transformations are
recommended after refinement.

## Evidence for Native Tet

- `edge_recovery.py` inserts midpoint samples but does not implement
  encroachment spheres, segment/subfacet priority, or the insertion-radius
  invariant used by the proof.
- `cdt_strong.py` globally re-Delaunays midpoint samples and accepts only a
  lower missing-edge count. That is a heuristic, not this refinement algorithm.
- A target such as `radius_edge <= 2` is not a sliver guarantee. Native Tet must
  report radius-edge and minimum/maximum dihedral tails separately.

## Falsifiable implementation cards

### TET-DR-1 - Encroachment-priority refinement kernel

- Implement explicit protected subsegments/subfacets and queues ordered as
  `segment, facet, tetrahedron`.
- Accept only insertions preserving positive orientation with exact-sign
  predicates and the protected complex.
- Test: on PLCs satisfying the projection condition and `B > 2`, every input
  constraint is represented as a chain/patch, all non-protected tets satisfy the
  radius-edge bound, and the queue terminates under a fixed insertion cap.

### TET-DR-2 - Honest sliver gate

- Never infer dihedral quality from radius-edge alone.
- Test: a canonical equatorial four-point sliver must fail the dihedral/volume
  gate while passing a permissive radius-edge gate.

### TET-DR-3 - Small-angle scope label

- Detect PLC angles below the theorem's supported range and mark the run as
  heuristic or route it to relaxed-insertion-radius CDT/fTetWild mode.
- Test: decreasing wedge angle must not cause unbounded refinement or a false
  `guaranteed` status.
