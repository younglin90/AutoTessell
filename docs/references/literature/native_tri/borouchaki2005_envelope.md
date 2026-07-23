# Borouchaki and Frey - Simplification of Surface Mesh Using Hausdorff Envelope

## Bibliography and access

- Houman Borouchaki and Pascal J. Frey.
- *Computer Methods in Applied Mechanics and Engineering*, 194(48-49),
  4864-4884, 2005. Received 8 December 2003, revised 24 June 2004, accepted
  26 November 2004.
- DOI: `10.1016/j.cma.2004.11.016`.
- Local full text supplied by the user:
  `C:/Users/user/Downloads/borouchaki2005.pdf`.
- Review status: `FULL_READ` on 2026-07-23. All 21 pages were text-extracted.
  Pages 1, 4, 6, 8, 9, 11, and 20 were rendered at 2x resolution; the title and
  DOI, tolerance equations, local distance accumulation, fitted-quadric
  relocation, full algorithm, experiments, conclusion, and references were
  visually checked against the extraction.

## Problem and contract

Given a reference triangle mesh `T_ref`, reduce its element count while
controlling geometric deviation and preventing excessive triangle-shape
degradation. The paper treats two geometric requirements independently:

1. **Proximity:** the simplified surface remains inside a global tolerance
   envelope at prescribed distance `delta` from the reference mesh.
2. **Regularity:** each new triangle normal stays inside cones of aperture
   `theta` centered on reference vertex normals.

The base derivation assumes a smooth surface with a unique continuous tangent
plane. Discontinuous interface curves and surface-traced curves require known,
pre-tagged critical edges and two additional curve tolerance regions. The
paper is a simplification method, not a repair procedure for non-manifold,
self-intersecting, inconsistently oriented, or open triangle soup.

## Tolerance regions and acceptance equations

For closed bounded sets `F_1` and `F_2`, define the directed distance and
symmetric Hausdorff distance by

```text
rho(F_1,F_2) = sup_{X in F_1} d(X,F_2),
d_H(F_1,F_2) = max(rho(F_1,F_2), rho(F_2,F_1)).
```

Every new triangle `K` should satisfy

```text
d_H(K,T_ref) <= delta,
<nu_k(K), nu(K)> >= cos(theta)  for every reference vertex k of K,
```

where `nu(K)` is the new face normal and `nu_k(K)` is the stored reference
surface normal associated with the corresponding vertex.

The normal constraint is not redundant with distance. It prevents a triangle
that remains spatially close to a reference surface from adopting a grossly
wrong tangent orientation. Conversely, normal cones alone cannot prevent
surface drift.

## Edge removal and accumulated local error

Collapsing edge `PQ` identifies `P` with `Q`. Let `B(P)` be the current
triangle ball incident on `P`, and let `R(Q)` be the new local triangle patch.
For every new triangle `K'`, the triangle inequality yields

```text
d_H(K',T_ref)
  <= d_H(K',B(P)) + d_H(B(P),T_ref)
  <= d_H(K',B(P)) + max_{K in B(P)} d_H(K,T_ref).
```

Each current triangle carries an accumulated value `h(K)`. A newly created
triangle receives

```text
h(K') = d_H(K',B(P)) + max_{K in B(P)} h(K),
```

and is accepted only if `h(K') <= delta` and the normal-cone test passes.
This is the paper's key incremental envelope idea: old local errors are not
forgotten after repeated collapses.

For a special projection-covering configuration, the local Hausdorff distance
can be reduced to maxima over convex polygons obtained by projecting pairs of
triangles. The paper then discusses two cheaper alternatives:

- `d_H(B(P),R(Q)) = max_{K' in R(Q)} d(proj_{K'}(P),P)` is an upper bound for
  the individual `d_H(K',B(P))`, but loses triangle-specific information.
- In practice, the paper approximates `d_H(K',B(P))` by the distance to a
  triangle `K_tilde` in `B(P)` sharing an edge with `K'`, using projections of
  `P` and `Q` and their mutual distance.

The second choice is described as an approximation, not proved as a universal
upper bound. The conclusion explicitly says the algorithm relies on a
discrete approximation and that a finer algebraic formulation is future work.
Therefore the implementation should not label the practical accumulated
quantity as an exact Hausdorff certificate without an independent conservative
bound.

## Mesh-quality and optimization operators

A collapse must also retain a fraction `beta` of the worst local input
triangle quality:

```text
q(K') >= beta min_{K in B(P)} q(K),
q(K) = 4 sqrt(3) Area(K) / sum_{e in K} |e|^2.
```

This quality equals one for an equilateral triangle and tends to zero for a
degenerate triangle. It is a relative non-degradation rule, not a hard lower
bound on the new patch's minimum angle.

After an edge removal, the algorithm attempts flips on new edges when the
adjacent triangles are nearly coplanar and the flip improves shape quality.
The near-coplanarity restriction is the paper's local geometry safeguard for
flips. Point relocation then improves quality and exposes more collapses.

For a vertex `P`, a local frame uses two tangent vectors and reference normal.
Neighbor points fit the height field

```text
z approximately a x^2 + 2 b x y + c y^2
```

by minimizing

```text
sum_i (a x_i^2 + 2 b x_i y_i + c y_i^2 - z_i)^2.
```

The unconstrained quality target `P*` is the average of positions completing
equilateral triangles on the boundary edges of `B(P)`. It is projected onto
the fitted quadric. The paper reduces exact projection to a fifth-degree
polynomial and uses the iterative approximation

```text
U_0 = P*,
U_{k+1} = U_k - F(U_k) grad F(U_k) / ||grad F(U_k)||^2,
```

until successive iterates are sufficiently close. A simpler normal-direction
projection is also permitted. The relocation is committed only when the
geometry and relative-quality constraints remain satisfied.

## Full simplification schedule

The paper progressively relaxes working tolerances from `(delta_0,theta_0)` to
the requested `(delta,theta)`:

```text
T <- T_ref
Delta <- delta_0 < delta
Theta <- theta_0 < theta
while Delta <= delta and Theta <= theta:
    optimize all edges
    remove and optimize all admissible edges under Delta, Theta, beta
    repeat removal/optimization while T changes
    relocate admissible vertices under Delta, Theta, beta
    increment Delta and Theta
```

The authors say edges may be sorted by expected quality improvement, but their
presented implementation imposes no special processing order. They describe
the suggested algorithm as linear in the number of reference edges; this is an
empirical/design characterization, not a formal bound covering all repeated
passes, closest-point searches, and data-structure costs.

## Critical curves

For a known feature/interface curve, the method adds:

- a radius-`delta` cylinder controlling positional deviation of the new
  critical edge from the reference curve; and
- a cone of aperture `theta` centered on the reference curve's principal
  normal, controlling edge-direction regularity.

A collapse on the curve must satisfy both the surface triangle tests and the
curve distance/direction tests. A feature vertex is relocated along a fitted
quadric curve, not frozen. This is important for AutoTessell: preserving a
crease does not require immobilizing all its degree-two vertices, but does
require persistent curve provenance and a curve-constrained target.

The method assumes critical curves are already known and represented by
reference edges. It provides neither feature detection nor policies for
junction corners, patch semantics, competing nearby features, or changes to a
feature graph.

## Validation method and guarantee boundary

The paper validates an output by sampling points on every triangle of one mesh
and finding their closest triangles in the other mesh. The search starts at a
bucket-grid nearest vertex, walks through incident vertex balls until the
closest element is stable, and uses barycentric cases for point-to-triangle,
edge, or vertex distance. The process is run in both directions.

This is a sampled symmetric audit. It can miss a maximum between samples and
is separate from the incremental local `h(K)` values used during operators.
Neither the practical local approximation nor the sampled final validation is
an exact continuous Hausdorff computation. A production claim must account for
sampling fill distance or use an exact/conservative triangle-to-surface bound.

The paper also does not specify a link condition, Euler/genus preservation,
fold-over test, duplicate-face rejection, local/global self-intersection test,
or boundary-loop policy. Spatial and normal tolerances do not imply topology
or an intersection-free embedding.

## Experimental evidence

- A smoothed biomedical isosurface with 1,126,102 reference triangles was
  reduced to 227,624 triangles at `(0.35%,33 degrees)` in 301 s and to 165,886
  at `(1%,45 degrees)` in 231 s, including validation. Mean quality changed
  from 0.90 to 0.83 and 0.79 respectively.
- A CAD wheel with 161,840 triangles and mean quality 0.63 was reduced to
  20,064 triangles at `(0.2%,33 degrees)` in 94 s with mean quality 0.77. At
  `(0.5%,36 degrees)` it reached 7,772 triangles in 39 s with mean quality
  0.66. The examples intentionally suppress geometric details permitted by
  the selected tolerance.
- A scanned statue with 28,055,742 triangles was reduced to 1,041,126 at
  `(0.01%,33 degrees)`. Tolerances from `0.02%` through `0.5%` yielded between
  390,196 and 62,784 triangles; each reported run completed in under one hour
  with mean quality about 0.9.
- Tolerance `delta` is a percentage of the reference bounding-box diagonal.
  Runtime was measured on an HP J5600 550 MHz workstation, so absolute timing
  is not transferable to current hardware or to stronger topology and exact
  error gates.

The evidence is large-scale for its era and includes mechanical and scanned
geometry, but there is no adversarial topology suite, deterministic replay,
minimum-angle distribution, intersection count, memory measurement, or
downstream volume-mesh evaluation.

## Limitations and claim boundary

- The practical local distance is an approximation accumulated through a
  sequence of operations; conservatism is not proved for every configuration.
- Final distance validation samples triangles and can underestimate the true
  continuous maximum.
- The smooth-surface derivation assumes meaningful reference normals. Noise or
  inconsistent orientation can invalidate the regularity cones.
- Feature curves must be supplied; the method does not infer or semantically
  classify them.
- No topology, boundary, self-intersection, or watertightness invariant is
  stated.
- The relative quality rule can preserve a poor patch rather than drive it to
  a declared absolute minimum quality.
- Progressive relaxation increments and stopping tolerances are not specified
  numerically, and unsorted edge processing leaves determinism unspecified.
- The fitted quadric is a local approximation; a failed or ill-conditioned fit
  needs a guarded fallback that the paper does not detail.
- Curvature is not used to set a target size field. Geometry affects operator
  feasibility, while simplification continues until no allowed operation
  remains.

## AutoTessell code mapping

`core/preprocessor/native_remesh/quadric_decimate.py` implements plane-QEM
cost, an optimal QEM target, and a cheapest-edge heap. It currently lacks the
paper's accumulated reference-envelope value, normal cones, relative triangle
quality test, feature-curve cylinder, and progressive tolerance schedule. More
critically, it has no link condition, fold-over simulation, duplicate-face or
self-intersection rejection. Therefore it is neither this algorithm nor a
bounded-error decimator.

`core/preprocessor/native_remesh/isotropic.py` protects feature vertices and
may snap relocated points to nearest original vertices. Nearest-vertex
snapping is not a Hausdorff envelope and can introduce quantization, while
freezing every feature vertex is weaker geometrically and more restrictive
numerically than the paper's feature-curve-constrained relocation.

Adopt:

- a per-face accumulated conservative error budget that survives many local
  operations;
- independent positional and normal-deviation gates;
- absolute quality floors in addition to relative non-degradation;
- feature-curve distance and tangent/normal constraints with persistent
  provenance; and
- progressive tolerance only as a deterministic continuation strategy.

Do not directly adopt the paper's adjacent-triangle approximation as a hard
Hausdorff certificate. Replace it with a proved conservative local bound or
pair it with a sampling-gap margin and exact final audit.

## Falsifiable implementation cards

1. `TRI-ENV-ACCUM1`: attach a conservative source-envelope budget to every
   live face and propagate it through simulated collapses using the triangle
   inequality. Validate the bound against exact or interval-conservative
   triangle-to-reference queries on random and adversarial local patches.
   Accept only if the propagated value never underestimates the audit.
2. `TRI-ENV-BIDIR1`: add a dynamic two-sided local error gate: output-to-input
   checks changed faces, while input-to-output invalidates source samples whose
   closest targets touch the changed patch. Include a declared sampling-gap
   margin. Pass only if a denser independent final audit remains below
   `delta` on thin gaps, nested shells, high curvature, and sharp creases.
3. `TRI-NORMAL-CONE1`: store provenance-aware reference normals and reject a
   candidate when any new face exceeds its class-specific normal angle.
   Benchmark positional-only versus positional-plus-normal gating; retain the
   cone only if it reduces 99.9th-percentile normal error without violating
   face and runtime budgets.
4. `TRI-FEATURE-CURVE1`: distinguish feature corners, curve vertices, patch
   interfaces, and ordinary vertices. Pin corners; constrain degree-two curve
   vertices to their source curve and tangent cone. Pass only if the feature
   graph, junction valence, patch labels, and maximum curve drift are invariant
   under split, collapse, flip, and relocate.
5. `TRI-COLLAPSE-SAFE1`: place envelope and quality checks behind mandatory
   link, orientation, duplicate-face, boundary-loop, and self-intersection
   guards. Pass only if every accepted collapse preserves the recorded
   topological signature and produces strictly positive-area consistently
   oriented triangles.
6. `TRI-RELAX-DETERMINISTIC1`: define exact `(Delta,Theta)` increments,
   candidate ordering, tie breaks, operation budget, and no-change stop rule.
   Pass only if repeated runs are byte-identical and terminate on already
   simplified, degenerate, feature-dense, and tolerance-infeasible cases.
7. `TRI-QUALITY-ABS1`: supplement the paper's relative `beta` rule with a hard
   minimum-angle or normalized-quality floor. Accept a collapse only when the
   local worst quality stays above the feasible floor and does not regress;
   measure downstream tet, hex-dominant, and poly volume-mesh failure rates.

## High-value references from this paper

- Cohen et al. (1996), *Simplification Envelopes*: global envelope foundation.
- Frey and Borouchaki (2003), *Surface Meshing Using a Geometric Error
  Estimate*: proximity/regularity surface-meshing context.
- Gueziec (1996), *Surface Simplification inside a Tolerance Volume*:
  tolerance-volume simplification predecessor.
- Hamann (1993), *Curvature Approximation for Triangulated Surfaces*: fitted
  local-quadric basis for relocation.
- Taubin (1995), *A Signal Processing Approach to Fair Surface Design*:
  non-shrinking smoothing used before the biomedical example.

