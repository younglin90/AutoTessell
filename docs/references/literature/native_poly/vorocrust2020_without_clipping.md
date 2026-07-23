# VoroCrust: Voronoi Meshing Without Clipping

## Bibliography and access

- Ahmed Abdelkader, Chandrajit L. Bajaj, Mohamed S. Ebeida, Ahmed H. Mahmoud,
  Scott A. Mitchell, John D. Owens, and Ahmad A. Rushdi.
- *ACM Transactions on Graphics* 39(3), Article 23, 2020, 1-16.
- DOI: `10.1145/3337680`
- Legal full text: <https://arxiv.org/pdf/1902.08767>
- Status: `FULL_READ` (18-page arXiv version, including appendix and references).
- Visual check: pages 5, 8, 11, and 13 were rendered and inspected. Algorithm 1,
  the ball/sliver constructions, result tables, and limitation figures were legible
  and consistent with extracted text.

## Problem and assumptions

VoroCrust constructs a boundary-conforming subset of an ordinary Voronoi diagram
without clipping cells against the domain. The input is a watertight,
self-intersection-free triangular PLC faithfully approximating a piecewise-smooth
complex in both Hausdorff distance and normals. The boundary may be curved,
non-convex, non-manifold, and contain arbitrarily sharp features. It is not an
input-repair method: holes, cracks, noise, and unfaithful triangulations remain out
of scope.

The main parameters are a maximum sizing field `sz`, a sharp-angle threshold
`theta_sharp < pi/2`, and a Lipschitz constant `L < 1` for ball radii. The reported
experiments normally use `L = 0.25`; increasing `L` reduces refinement but enlarges
ball neighborhoods and can worsen element quality.

## Algorithm

1. Classify sharp corners, crease chains, and smooth surface patches.
2. Protect corners, then creases, then cover smooth patches with a union of balls.
3. Refine recursively until four ball conditions hold:
   - C1: every covered boundary point is co-smooth with the ball center;
   - C2: overlapping balls have a smooth path inside their union;
   - C3: same-stratum radii obey local `L`-Lipschitz gradation;
   - C4: deep coverage and sample separation. The implementation uses
     `alpha = 1 - sqrt(3)/2`, approximately 0.13.
4. Initialize a new radius conservatively with
   `min(sz(p), 0.49*d(p,q_non-smooth), r_q + L*d(p,q))`.
5. Use maximal Poisson-disk sampling on strata. Shrinking a lower-dimensional
   protection ball recursively restarts affected protection/coverage phases.
6. Each qualifying triplet of surface balls produces the two intersections of the
   bounding spheres, one seed on each side of the boundary. Facets between
   oppositely labelled seeds reproduce the surface.
7. Eliminate half-covered seed pairs (weighted-alpha slivers) by shrinking the
   least-cost ball, restoring coverage, and repeating.
8. Fill the interior outside the protected union with variable-radius dart/spoke
   sampling. Optional interior CVT or a structured lattice may improve the volume.

## Guarantees and limitations

- The paper claims topologically correct conforming Voronoi output, true convex
  Voronoi cells, planar facets, preservation of sharp features, and the orthogonal
  Delaunay dual under its input and sampling assumptions.
- Surface and volume quality bounds inherited from the theoretical construction
  deteriorate near sharp features, where good aspect ratios may be geometrically
  impossible.
- The practical sliver loop uses a 100-iteration fallback to a weaker
  `alpha/2` deep-coverage condition; the authors report never triggering it.
- Short interior Voronoi edges remain possible and can constrain CFD time steps.
- The method is isotropic; narrow gaps may over-refine, and boundary layers are not
  generated.
- Surface coverage dominates runtime. Representative reported surface-seed counts
  range from about 11k to 498k; this is not a lightweight postprocess.
- In the RVD comparison, clipping produced 3%-96% non-convex cells depending on
  model/seed choice. This is an experiment, not a universal bound on all clipping
  implementations.

## Current-code gap

- `native_poly/voronoi.py` starts from a jittered Cartesian lattice and retains
  seeds via ray casting. It has no corner/crease/patch ball complex, no C1-C4
  refinement, no paired inside/outside surface seeds, and no sliver proof.
- The current boundary construction appends every input surface vertex as an outer
  seed, then snaps any outside Voronoi vertex to its nearest input vertex. This is
  neither VoroCrust mirroring nor a conforming-Voronoi construction, and snapping
  destroys the Voronoi/orthogonal-dual property.
- `_lloyd_3d_iteration` moves a seed to the arithmetic mean of its finite Voronoi
  vertices. A CVT update requires the volume centroid of the domain-restricted cell;
  the mean of vertices is generally different.
- Cells with infinite regions are skipped rather than bounded by a certified domain
  construction. `clip_boundary` defaults to false, while the partial-cell branch is
  explicitly heuristic.
- Feature seed pinning is useful but does not establish boundary conformity.

## Falsifiable implementation cards

### `POLY-VOROCRUST-PROTECT1`

Implement typed strata and corner/crease/surface protection balls with C1-C4
predicates and a deterministic shrink/restart queue. Pass only if a regression set
containing sharp concavities, narrow gaps, and non-manifold material interfaces has
zero uncovered boundary samples, zero forbidden cross-stratum overlaps, and a
measured radius-gradation violation below `1e-12`.

### `POLY-VOROCRUST-SEEDPAIR1`

Generate labelled inside/outside seed pairs from valid ball triplets, reject seeds
covered by a fourth ball, and extract only opposite-label Voronoi facets. Pass only
if every output boundary face has opposite labels, the reconstructed boundary has
the expected component/genus/interface topology, and no boundary clipping or
nearest-vertex snapping occurs.

### `POLY-VOROCRUST-SLIVER1`

Detect half-covered pairs and transactionally shrink the least-cost ball, restoring
C1-C4 after every batch. Pass when no half-covered pair or unlabelled Steiner
surface vertex remains and refinement terminates under a mechanically enforced
iteration/sample budget.

### `POLY-VOROCRUST-EDGE1`

Add a short-Voronoi-edge penalty or restricted resampling stage. Pass only if the
minimum interior edge improves without worsening topology, boundary Hausdorff
error, cell validity, or the 99th-percentile non-orthogonality on the benchmark set.

