# Yan et al. - Isotropic Remeshing with Fast and Exact RVD

## Bibliography and access

- Dong-Ming Yan, Bruno Levy, Yang Liu, Feng Sun, and Wenping Wang.
- *Computer Graphics Forum* 28(5), pages 1445-1454, 2009.
- DOI: `10.1111/j.1467-8659.2009.01521.x`.
- Publisher record:
  `https://onlinelibrary.wiley.com/doi/10.1111/j.1467-8659.2009.01521.x`.
- Local full text: `tmp/pdfs/native_tri_batch2/yan2009_rvd.pdf`.
- Review status: `FULL_READ` on 2026-07-23. All 10 pages were text-extracted
  and read. Pages 3, 5, 6, 7, 8, 9, and 10 were rendered at 150 dpi; the
  CCVT/RCVT definitions, symbolic clipping predicates, gradients, feature
  constraints, topology-control sequence, experiments, quality table,
  limitations, and references were visually checked against the extraction.

## Problem and scope

The paper builds an isotropic triangle remesher around a parameterization-free
restricted Voronoi diagram (RVD). For input surface `S`, three-dimensional
seeds `X = {x_i}`, and Euclidean Voronoi cells `Omega_i`, each restricted cell
is

```text
R_i = Omega_i intersect S.
```

The output is the restricted Delaunay triangulation (RDT), the combinatorial
dual of the RVD. The method targets oriented triangular surface meshes and
handles boundaries, creases, corners, high genus, noisy triangulations, and
very irregular input facets without a global surface parameterization. It is
not a repair algorithm for arbitrary non-manifold or self-intersecting soups.

"Exact" has a narrow meaning here: filtered exact predicates certify the
**combinatorics of RVD clipping**. The paper does not certify exact constructed
coordinates, a Hausdorff envelope, minimum angle, intersection freedom, or
optimizer convergence.

## CVT objective, CCVT, and RCVT

For density `rho > 0`, the restricted CVT energy is

```text
F(X) = sum_i integral_{R_i} rho(x) ||x - x_i||^2 d sigma.
```

The paper distinguishes two optimizations using this same restricted-domain
energy:

- **CCVT:** every seed is constrained to `S`. Its gradient is projected into
  the local surface tangent plane and the updated seed is projected back to
  the surface. It is preferred for a sufficiently smooth input surface.
- **RCVT:** seeds are unconstrained in 3D, while their Voronoi domains remain
  restricted to `S`. It is faster and more robust on noisy or irregular input,
  but its seeds need not remain on the input surface.

For a restricted cell with mass and centroid

```text
m_i   = integral_{R_i} rho(x) d sigma,
x_i*  = integral_{R_i} rho(x) x d sigma / m_i,
```

the RCVT gradient is

```text
dF/dx_i = 2 m_i (x_i - x_i*).
```

For CCVT the gradient becomes

```text
g_S = g - (g dot N(x_i)) N(x_i).
```

The clipped RVD polygons are triangulated for integration and `rho` is
linearly interpolated within each source triangle. The authors use L-BFGS,
not Lloyd iteration, relying on the previously established `C2` smoothness of
the CVT energy away from combinatorial events. Their production schedule first
computes RCVT for a robust seed distribution, then switches to CCVT for a
small number of surface-constrained iterations. Noisy examples use RCVT alone
because CCVT gradient evaluation becomes unreliable.

This distinction matters: RCVT is not an abbreviation for approximate Lloyd
smoothing, and a one-ring centroid update is neither CCVT nor RCVT.

## Exact RVD clipping algorithm

Let the input have `m` triangles and `n` seeds. The implementation builds:

1. a 3D Delaunay triangulation of the seeds, which supplies the bisector planes
   bounding every Voronoi cell; and
2. a kd-tree over the seeds.

Each input triangle is handled independently:

1. Query the seed nearest to the triangle centroid. Its Voronoi cell contains
   that centroid and therefore intersects the triangle.
2. Clip the triangle against every bisector half-space bounding this starting
   cell, producing a convex polygon.
3. Whenever a bounding plane intersects the current polygon, enqueue the seed
   across that Delaunay facet unless it has already been visited.
4. Repeat with a FIFO queue until no incident Voronoi cell remains; attach each
   nonempty clipped polygon to its restricted cell.
5. Reset only the visited-cell flags before processing the next source
   triangle.

This replaces an all-pairs `O(mn)` scan with one kd-tree query followed by
neighbor propagation. The paper states `O(m log n)` time for RVD computation
and demonstrates good scaling, but does not derive a worst-case bound that
explicitly accounts for Delaunay construction, Voronoi cell degree, the number
of triangle-cell intersections, or clipping output size. The implementation
should treat the algorithm as output-sensitive and test the claimed scaling
rather than encoding `O(m log n)` as an unconditional complexity guarantee.

No input-mesh connectivity is needed for clipping because source triangles are
processed independently. Connectivity is required later when deciding whether
the extracted RDT reproduces the source topology.

## Symbolic vertices and certified predicates

Every RVD polygon vertex is the intersection of three defining planes and
carries a fixed-size symbolic set `Sym_v = {k_1,k_2,k_3}`. A positive ID
denotes a seed bisector; a negative ID denotes an input surface facet. This
encodes three cases:

- type A: an original surface vertex;
- type B: a surface edge intersected by one seed bisector; and
- type C: one surface facet intersected by two seed bisectors.

When clipping edge `[v_1,v_2]` by the bisector to seed `k`, the new symbolic
label is formed from the common defining planes plus `k`. Degenerate
bisector-on-edge or bisector-on-vertex cases are represented using the type-C
convention so the label remains three integers and set operations stay
constant-sized.

The decisive predicate `side(x_1,x_2,v)` is rewritten directly from the
symbolic source data instead of repeatedly using rounded intersection
coordinates. The type A, B, and C forms are rational expressions of reported
degree `2`, `4/2`, and `6/4`. Numerator and denominator signs are evaluated
separately through almost-static filters, interval arithmetic, and finally
CGAL `MP_Float`, generated with FPG. Thus near-degenerate clipping decisions
fall back to exact arithmetic while common cases remain fast.

The same symbolic labels identify RDT edges and triangles: one bisector label
defines a dual edge, while two bisector labels define a dual triangle. This
reuse is the central robustness benefit of the method.

## Features and boundaries

Boundary curves and creases are represented as feature-edge chains. Vertices
incident to more than two feature edges, plus tips, darts, and cusps, become
fixed corner seeds. Their Voronoi cells still contribute energy, but the corner
positions are not optimization variables.

Feature sampling uses a two-stage allocation:

1. run unconstrained RCVT to distribute the prescribed global seed count;
2. after convergence, snap seeds whose RVD cells contain a feature curve to
   that curve and designate them as feature seeds;
3. switch to CCVT, project each updated feature seed to the nearest point on
   its curve, and restrict its gradient to the curve tangent `T(x_i)`:

```text
g_C = (g dot T(x_i)) T(x_i).
```

Unlike Alliez et al. 2005, these feature seeds continue to optimize rather
than being frozen after a separate one-dimensional CVT. The paper does not
specify semantic patch labels, feature-junction provenance through all
degeneracies, curve self-intersection checks, or a maximum feature-drift
certificate. Nearest-curve projection also needs deterministic tie handling
for nearby or crossing features.

## RDT validity and topology control

The topological-ball property gives a sufficient condition: if each
`k`-dimensional Voronoi face intersects `S` in a `(k-1)`-dimensional
topological ball, the RDT is homeomorphic to `S`. Exact RVD combinatorics make
this condition testable, but do not make it automatically true.

The implementation first uses cheaper RDT manifoldness filters:

- duplicated Delaunay triangles;
- Delaunay edges incident to fewer than one or more than two triangles; and
- isolated Delaunay vertices.

If those pass, it performs the more expensive topological-ball checks:

- Euler-Poincare characteristic, component count, and boundary count for each
  RVC to determine whether it is a disk;
- component and extremity counts for restricted Voronoi edges; and
- uniqueness of each Voronoi-edge/surface intersection.

Topology testing is interleaved with optimization, typically every 30
iterations. A non-manifold dual triangle triggers two new seeds displaced
above and below its center along the normal. A non-manifold dual edge triggers
three seeds displaced radially around its center. Optimization then resumes.
The illustrated example recovers all handles after four topology-control
passes.

This is a repair heuristic around a sufficient test, not a terminating
Delaunay-refinement algorithm. The authors explicitly state that repeated
insertion is not guaranteed to terminate and recommend switching to Delaunay
refinement if it does not. They also identify simultaneous global optimization
with termination guarantees as an open problem.

## Experimental evidence

Experiments used CGAL for Delaunay triangulation and ANN for the kd-tree on a
2.2 GHz dual-core laptop with 2 GB memory.

- Kitten, 274k input faces and 10k seeds: one RVD computation took 2.1 s; the
  complete remesh took 228 s over 67 RVD/Delaunay iterations.
- Fandisk, 13k faces to 3k seeds: 100 iterations and 40 s, with
  `Q_min = 0.541` and minimum angle `24.35 degrees`.
- Joint, 446 faces to 3k seeds: 119 iterations and 49 s, with
  `Q_min = 0.585` and minimum angle `31.89 degrees`.
- Dancer, 13.7k faces to 10k seeds: 51 iterations and 56.7 s, with
  `Q_min = 0.604` and minimum angle `30.81 degrees`.
- Noisy Ball Joint, 68.5k faces to 10k seeds: RCVT-only optimization took 259
  iterations and 386 s. It greatly improved angle quality over discrete
  clustering, but its reported mean and RMS Hausdorff errors were slightly
  larger (`0.166%` and `0.184%` of bounding-box diagonal).
- David at 100k vertices: the method reported `Q_min = 0.544`, minimum angle
  `28.46 degrees`, mean error `0.0081%`, and RMS error `0.012%`.
- Elk at 31.1k vertices: `Q_min = 0.635`, minimum angle `36.46 degrees`, mean
  error `0.006%`, and RMS error `0.012%`.
- Against DELPSC on Homer at 7,588 vertices, the minimum angle improved from
  `2.79` to `26.0 degrees` in the reported comparison.

The mean/RMS Hausdorff columns do not establish a worst-case envelope. Results
are persuasive for lower-tail angle quality and robustness to poor source
triangles, but there is no memory profile, exact predicate fallback rate,
adversarial degeneracy suite, deterministic replay test, downstream volume-
mesh evaluation, or certified lower angle bound.

## Guarantee boundary and limitations

- The exact-predicate claim certifies RVD combinatorics, not surface fidelity.
- RDT homeomorphism is conditional on the tested topological-ball property.
- Topology-control insertion has no termination or output-size guarantee.
- CVT/L-BFGS convergence to a global minimum is not guaranteed; a stationary
  point can be a saddle, and line-search behavior is not documented here.
- Neither minimum angle nor normalized quality has a certified lower bound.
- A seed on the source, or an RVC restricted to the source, does not bound the
  deviation of every planar output triangle from the source.
- No continuous two-sided Hausdorff envelope or local operator error budget is
  enforced.
- No output self-intersection test or proof is given.
- `rho = 1/lfs^2` uses an approximated local feature size and tends toward an
  epsilon-sample, but energy minimization does not ensure the epsilon-sampling
  criterion. The paper relies on explicit topology tests instead.
- Euclidean RVD approximates the intrinsic geodesic Voronoi diagram. Thin
  nearby sheets can therefore interact through ambient distance unless the
  topology and geometry gates detect the damage.
- Feature curves are assumed to be available or detected externally.

## AutoTessell code mapping

`core/preprocessor/native_remesh/cvt.py` is named CVT but performs fixed-
topology, area-weighted one-ring face-centroid smoothing. It constructs no
Voronoi cells, restricted cells, CVT energy, analytic gradient, Delaunay dual,
or L-BFGS state. Its optional projection snaps to the nearest **input vertex**,
not the closest surface point. It should not be used as evidence that Yan's
CCVT or RCVT algorithm is implemented.

`core/preprocessor/native_remesh/isotropic.py` is a local
split/collapse/flip/relocate engine. It can remain the fast default track, but
it is architecturally distinct from an RVD/RDT remesher. Detected feature
vertices are all frozen, whereas Yan pins only feature corners and permits
curve seeds to move tangentially. Its local nearest-input-vertex projection is
neither exact RVD restriction nor a surface envelope.

`core/preprocessor/native_remesh/face.py` performs a true closest-triangle
projection after local remeshing and applies post-run watertightness,
edge-manifoldness, degeneracy, face-normal, sampled drift, protected-edge, and
triangle-quality gates. Those gates are useful but are not the RVC/RVE
topological-ball tests. Geometry drift samples output vertices and face
centers toward the input; it is not a continuous or bidirectional Hausdorff
certificate.

Therefore an exact-RVD candidate should be a separate native engine with a
shared acceptance policy, not a renamed smoothing pass or a small patch to the
local-operation loop.

## AutoTessell decision

Adopt:

- triangle-independent RVD clipping seeded by a spatial query and propagated
  over Delaunay neighbors;
- symbolic provenance for every clipped vertex and filtered exact side
  predicates;
- explicit distinction between robust unconstrained RCVT initialization and
  surface-constrained CCVT finishing;
- L-BFGS with analytic restricted-cell mass and centroid integration;
- feature corners as fixed variables and degree-two curve seeds constrained
  to curve tangents;
- cheap RDT manifold filters followed by full topological-ball validation; and
- deterministic bounded topology-control passes with a declared fallback.

Do not adopt as guarantees:

- the stated `O(m log n)` without output-sensitive measurement;
- topology insertion without a hard pass/seed budget;
- nearest projection as a Hausdorff bound;
- a high measured minimum angle as a certified minimum-angle property; or
- RCVT-only output on noisy geometry without explicit surface-fidelity gates.

## Falsifiable implementation cards

1. `TRI-RVD-CLIP1`: implement source-triangle/Voronoi-cell clipping with a
   nearest-seed start and Delaunay-neighbor FIFO traversal. Against a brute-
   force all-cell oracle on random and adversarial small meshes, require
   identical nonempty cell-triangle incidences and polygon topology.
2. `TRI-RVD-PRED1`: attach three-plane symbolic provenance to every clipped
   vertex and route A/B/C side tests through static, interval, then exact
   fallbacks. Require identical RVD/RDT combinatorics under input permutation,
   scale ranges `1e-9` to `1e9`, near-cospherical seeds, and bisectors passing
   through source vertices or edges.
3. `TRI-RVD-SCALE1`: measure Delaunay build, kd queries, clipping, predicate
   fallbacks, and dual extraction separately while varying input faces, seeds,
   incident-cell count, and thin-sheet spacing. Accept the acceleration claim
   only if observed cost follows the recorded output size and beats the brute-
   force oracle without missed cells.
4. `TRI-RCVT-LBFGS1`: implement the restricted-cell energy, mass, centroid,
   and analytic gradient, then compare them with finite differences away from
   combinatorial events. Require relative gradient error below a declared
   tolerance and monotone accepted line-search steps on smooth benchmarks.
5. `TRI-RCVT-CCVT1`: benchmark RCVT initialization followed by CCVT against
   RCVT-only, CCVT-only, and the local-operation engine at identical output
   counts. Promote only if the hybrid improves the 0.1-percentile angle and
   valence distribution without degrading the two-sided envelope, features,
   topology, determinism, or runtime budget.
6. `TRI-RVD-FEATURE1`: represent corners, feature curves, and semantic patch
   boundaries explicitly. Pin corners; constrain degree-two feature seeds to
   their own curve and tangent. Require invariant feature-graph connectivity,
   junction valence, patch labels, and maximum curve drift on intersecting and
   closely spaced features.
7. `TRI-RDT-BALL1`: implement cheap RDT manifold filters plus full RVC/RVE
   topological-ball checks from symbolic incidence. Validate against known
   sphere, torus, multi-handle, thin-tail, disconnected-shell, and deliberate
   failure fixtures; require agreement with independently computed Euler
   characteristic, component, boundary-loop, and manifold signatures.
8. `TRI-RDT-CONTROL1`: cap topology-control rounds, added seeds, and wall time;
   record the exact violated simplex and insertion provenance. Require either
   a valid homeomorphic RDT or deterministic handoff to a terminating
   refinement/local-remesh fallback, never an unbounded insertion loop.
9. `TRI-RVD-ENV1`: place a continuous or conservatively sampled two-sided
   surface-envelope and self-intersection audit after RDT extraction. Reject
   RCVT/CCVT results whose planar faces violate tolerance even when every RVD
   combinatorial predicate and topology test passes.

## High-value references from this paper

- Liu et al. (2009), *On Centroidal Voronoi Tessellation - Energy Smoothness
  and Fast Computation*, DOI `10.1145/1559755.1559758`, for the L-BFGS energy
  and smoothness foundation.
- Edelsbrunner and Shah (1997), *Triangulating Topological Spaces*, for RDT and
  the topological-ball property.
- Amenta and Bern (1999), *Surface Reconstruction by Voronoi Filtering*, for
  epsilon-sampling and local feature size.
- Cheng, Dey, and Levine (2007), *A Practical Delaunay Meshing Algorithm for a
  Large Class of Domains*, for a refinement fallback with stronger
  termination foundations.
- Meyer and Pion (2008), *FPG: A Code Generator for Fast and Certified
  Geometric Predicates*, for filtered exact predicate generation.
- Valette, Chassery, and Prost (2008), *Generic Remeshing of 3D Triangular
  Meshes with Metric-Dependent Discrete Voronoi Diagrams*, for the discrete
  clustering baseline.

