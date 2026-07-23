# Zhong et al. - Anisotropic Surface Meshing with Conformal Embedding

## Bibliography and access

- Zichun Zhong, Liang Shuai, Miao Jin, and Xiaohu Guo.
- *Graphical Models* 76(5), pages 468-483, 2014.
- DOI: `10.1016/j.gmod.2014.03.011`.
- Local full text supplied by the user:
  `C:/Users/user/Downloads/zhong2014.pdf`.
- Review status: `FULL_READ` on 2026-07-23. All 16 pages, nine equations,
  topology-specific algorithms, experiments, tables, limitations, and 47
  references were inspected. PDF pages 2, 5, 7, 13, and 15 were rendered at
  2x resolution and visually checked against the extracted equations, pipeline
  figure, quality table, failure example, and limitation text.

The supplied PDF is an article-in-press layout and numbers its PDF pages
1-16. The final journal pagination is 468-483.

## Problem and contract

The paper accepts a triangulated surface carrying a user-specified Riemannian
metric and returns an anisotropic triangle mesh with a user-specified number
of vertices. Desired edge directions and aspect ratios are encoded in the
metric. The method converts anisotropic meshing on the surface into weighted
isotropic CVT in a two-dimensional conformal embedding, then maps the dual
triangulation back to the original surface.

The input is assumed to be a legal manifold triangulation dense enough to
resolve the metric field. The method is not an input-repair algorithm. It does
not address triangle soups, self-intersections, inconsistent orientation,
semantic patch boundaries, CAD curves, or non-manifold input.

## Metric model

For a vector `a` and symmetric positive-definite tangent metric `M(x)`, the
anisotropic squared length is

```text
||a||^2_M(x) = a^T M(x) a.                         (1)
```

The metric is factorized as

```text
M(x) = R(x)^T S(x)^2 R(x),                         (2)
Q(x) = S(x) R(x),
||Q(x)a||^2 = a^T M(x) a.                         (3)
```

For a surface embedded in 3D, the paper constructs the ambient rank-two form

```text
M = [v_min, v_max, n]
    diag(s_1^2, s_2^2, 0)
    [v_min, v_max, n]^T,                           (4)
```

where `v_min` and `v_max` are principal-curvature directions, `n` is the unit
normal, and `s_2/s_1` is the requested stretching ratio. It is positive
definite on the tangent plane and zero in the normal direction. The authors
smooth both stretching ratios and directions because raw piecewise-linear
curvature estimates are noisy and discontinuous.

This paper assumes that a smooth, directionally consistent metric can be
constructed. It does not resolve principal-direction sign ambiguity,
umbilics, field singularities, patch seams, or metric gradation limits in a
reproducible way.

## Complete algorithm

### 1. Adjust input edge lengths to the metric

For triangle `ABC`, approximate its metric factor by

```text
Q_ABC = [Q(x_A) + Q(x_B) + Q(x_C)] / 3.
```

Transform each triangle edge by `Q_ABC` and use its Euclidean length as the
desired anisotropic length. Adjacent triangles generally assign different
lengths to a shared edge, so the method averages the two values to obtain one
consistent intrinsic edge length.

Metric deformation can violate a triangle inequality. The recovery sequence
is:

1. For two adjacent triangles `ABD` and `BCD`, form

```text
Q_avg = [Q_A + Q_B + Q_C + Q_D] / 4.
```

2. Compute all relevant lengths under `Q_avg`, recover angles by the cosine
   rule, and flip `BD` to `AC` when the modified Delaunay comparison improves
   the minimum-angle configuration.
3. If an invalid triangle remains, bisect its longest edge. The inserted
   vertex receives the average metric of the two endpoints, and the two
   incident triangles become four.

The authors say these operations remove all invalid triangles only when the
metric is sufficiently smooth. This is an explicit precondition, not an
unconditional guarantee.

### 2. Conformally embed the adjusted intrinsic surface

The embedding depends on topology:

- closed genus zero: spherical harmonic map to `S^2`;
- closed genus one: Euclidean discrete Ricci flow and periodic embedding in
  `E^2`;
- closed genus greater than one: hyperbolic discrete Ricci flow and periodic
  embedding in `H^2`; and
- topological disk: a planar conformal map.

The embedding preserves the angles of the adjusted intrinsic triangles as
closely as its discrete method allows. It therefore retains local aspect
ratios induced by the anisotropic metric while introducing an area scale.

### 3. Compensate area distortion and compute weighted CVT

At each vertex, define the reported conformal-area factor as

```text
cf(v) = [sum incident adjusted triangle areas]
        / [sum incident embedded triangle areas].             (6)
```

Adjusted triangle area is recovered from intrinsic edge lengths `a,b,c` by
Heron's formula:

```text
A_ABC = 1/4 sqrt((a+b+c)(b+c-a)(c+a-b)(a+b-c)).     (7)
```

The paper linearly interpolates `cf` within embedded triangles and uses
`cf(v)^2` as the weighted-CVT density. It states that this produces constant
sizing on the adjusted-edge-length surface. Lloyd iteration repeatedly
constructs a Voronoi diagram and moves each site to the density-weighted
centroid of its cell.

The Voronoi implementation is also topology-specific:

- spherical Voronoi on `S^2` for genus zero;
- ordinary 2D Voronoi for disks, with boundary sites projected to the disk
  boundary;
- periodic Euclidean Voronoi with neighbor copies for genus one; and
- a power-diagram equivalent on a Klein disk plus periodic neighbor copies
  for high genus.

For genus `g > 1`, the naive construction requires `16g^2 - 8g` neighbor
patches, so the paper uses a cited pruning technique to remove unnecessary
site copies. The cited CVT literature supplies convergence of Lloyd iteration
on `S^2`, `E^2`, and `H^2`; that does not prove convergence or successful
completion of the entire metric-adjustment and conformal-embedding pipeline.

### 4. Generate and evaluate the anisotropic mesh

The final triangulation is the dual of the converged Voronoi diagram. Each
site is mapped from the parameter domain to the original source surface using
barycentric coordinates.

The isotropic triangle-quality measure is

```text
G = 2 sqrt(3) A / (p h),
```

where `A` is triangle area, `p` its semiperimeter, and `h` its longest edge.
The reported statistics are minimum and average `G`, minimum and average of
the per-triangle minimum angle, percentage of triangles with minimum angle
below 30 degrees, and an angle histogram.

For an anisotropic output triangle, the paper first affine-transforms the
triangle by the average `Q` of its three vertices and computes the same
isotropic measures in metric space. This is an important benchmark rule:
ordinary world-space angles incorrectly penalize intentionally elongated
anisotropic elements.

## Experimental evidence

The implementation used Visual C++ 2010 and Matlab R2013a on a 2.40 GHz Intel
Xeon E5620 with 20 GB RAM. Most reported CVT runs use 100 iterations, except
one 8,000-site Cyclide case using 200.

Representative cases include:

- ellipsoid: 10,242 input vertices, 1,000 output vertices, stretching up to
  10, 225 s parameterization plus 181.71 s CVT;
- genus-one Cyclide: 25,920 input, 8,000 output, stretching 2-29, 36 s plus
  548.21 s;
- Kitten: 134,438 input, 5,000 output, stretching 1-5, 81 s plus 271.79 s;
- genus-two Eight: 10,000 input, 1,000 output, stretching 1-5, 91 s plus
  315.59 s; and
- a second Cyclide: 21,600 input, 1,000 output, stretching 2-18, 24 s plus
  39.15 s.

On the 8,000-site Cyclide comparison after 100 optimization iterations:

| Method | Time (s) | `G_min` | `G_avg` | min angle | avg min angle | `<30 deg` |
|---|---:|---:|---:|---:|---:|---:|
| Proposed | 310.10 | 0.3771 | 0.9068 | 22.5709 | 52.4795 | 0.0187% |
| Du-Wang continuous ACVT | 9749.08 | 0.1989 | 0.8546 | 7.9089 | 48.5434 | 1.7860% |
| Valette discrete ACVT | 539.90 | 0.1421 | 0.7590 | 5.0111 | 39.9945 | 10.6049% |

The paper summarizes this as roughly 36 times faster than its continuous
ACVT comparison and roughly twice as fast as the discrete comparison. The
Du-Wang baseline is the authors' more accurate clipping reimplementation, not
the original sampling approximation, so this is not a bit-for-bit comparison
with published reference code.

The metric-legalization experiment is especially relevant. A Dolphin image
mesh initially had 5,286 invalid metric triangles out of 207,368. Metric-aware
edge flips removed them all, but the resulting minimum angle was only 6.35
degrees. On the Kitten, five Laplacian passes over two-rings still left 16,405
invalid triangles, whereas 50 passes over ten-rings removed them. This shows
that success may require very heavy metric smoothing that sacrifices requested
anisotropy and local detail.

In the topology comparison, a coarse 3D AVD method produced non-manifold
vertices and edges on the close-sheet Cyclide, while the parameter-domain
method did not in that example. This is experimental evidence, not a general
topological guarantee.

## Guarantees, assumptions, and limitations

Supported claims:

- the output has the user-requested number of CVT sites;
- Lloyd iteration has cited convergence results on the chosen canonical
  embedding domains once a valid embedded problem exists;
- the dual sites are mapped to source triangles using barycentric coordinates;
  and
- quality is evaluated in the same metric that defines anisotropy.

Explicit limitations in the paper:

- the input tessellation must be dense enough to resolve metric variation;
- adjusted lengths may violate triangle inequalities;
- conformal methods are sensitive to skinny or degenerate initial triangles;
- Ricci-flow circle packing becomes difficult on anisotropically distorted
  triangulations;
- the authors reduce requested stretching ratios on most test surfaces to
  make embedding feasible;
- particularly large anisotropy cannot be handled reliably; and
- hyperbolic Ricci flow is the only described high-genus route and is highly
  sensitive to triangulation quality.

Additional missing production guarantees:

- no Hausdorff, envelope, chord, or normal-deviation bound;
- no sharp-feature, corner, CAD-curve, or semantic patch preservation rule;
- no general manifoldness, topology-equivalence, or self-intersection proof;
- no deterministic initialization or stopping contract for Lloyd iteration;
- no bound on metric gradation or on distortion caused by metric smoothing;
- no minimum metric-space or world-space angle guarantee; and
- no native implementation path independent of the several geometry kernels
  cited by the paper.

Mapping sites to the source does not bound the lifted dual faces between those
sites. Close sheets and thin gaps therefore still need an independent
two-sided surface-envelope test.

## AutoTessell mapping

AutoTessell currently has no anisotropic metric-field surface engine.
`core/preprocessor/native_remesh/isotropic.py` operates on one global scalar
edge target and world-space lengths. The `adaptive_sizing` path in
`core/preprocessor/native_remesh/face.py` merely scales that one target by the
global fraction of detected feature vertices; it is not a per-vertex sizing
field and contains no principal directions or metric tensor.

`core/preprocessor/native_remesh/cvt.py` is also not the CVT described here.
It moves each existing vertex toward an area-weighted average of incident face
centroids. It constructs neither Voronoi cells nor their dual Delaunay mesh,
does not change sample count/connectivity, and has no density or canonical
embedding. Calling it `lloyd_cvt` should not be interpreted as evidence that
the paper's algorithm is implemented.

Adopt first:

- a native, validated tangent metric representation with eigenvalue,
  gradation, singularity, and orientation diagnostics;
- metric-space edge length and triangle-quality evaluation;
- curvature-direction smoothing with explicit limits on lost anisotropy;
- metric-aware local flip/split candidates inside the existing transactional
  remeshing architecture; and
- exact requested-site accounting separated from topology and envelope gates.

Defer as a primary production route:

- topology-specific global spherical/Euclidean/hyperbolic embedding;
- global Lloyd CVT as the only optimizer;
- large fixed smoothing neighborhoods and stretching reduction without a
  quantified error budget; and
- parameter-domain manifoldness as a replacement for physical-space checks.

The paper is most valuable to AutoTessell as the specification for metric
construction, metric-space evaluation, and known failure cases. A full native
reimplementation of all topology-specific conformal maps is substantially
larger and more fragile than adding a metric-aware local-operation mode.

## Falsifiable implementation cards

1. `TRI-METRIC-FIELD1`: implement a per-vertex tangent metric storing two
   eigenvalues and an unoriented tangent frame. Require finite positive tangent
   eigenvalues, bounded condition number and edge-to-edge gradation, stable
   transport through umbilics, and identical metrics under face/index
   permutations. Reject rather than silently repair invalid metrics.
2. `TRI-METRIC-QUALITY1`: implement the paper's metric-space edge lengths and
   transformed `G`, minimum-angle, and `<30 degree` statistics. Validate
   against analytic planar fields with identity, constant rotation/stretch,
   and smoothly varying tensors. Pass only if identity reproduces isotropic
   diagnostics and rigid coordinate rotations leave all results invariant.
3. `TRI-METRIC-LEGALIZE1`: add transactional metric-aware flip and longest-edge
   split candidate tests. Every commit must satisfy triangle inequalities,
   link condition, positive world/metric orientation, feature provenance,
   local quality floor, face cap, and two-sided envelope. Pass the paper's
   invalid-triangle stress pattern without topology or feature changes.
4. `TRI-METRIC-SMOOTH1`: smooth eigenvalues and cross-field directions with a
   declared maximum change in log-anisotropy and orientation. Report rejected
   or clamped requests. Accept only if metric-invalid triangles decrease while
   the requested-versus-realized metric error remains below a configured
   tolerance on curvature singularities, sharp seams, and noisy scans.
5. `TRI-ANISO-LOCAL1`: compare a metric-aware local split/collapse/flip/
   relocation engine against uniform isotropic remeshing at equal face and
   envelope budgets. Promote only if lower-tail metric quality improves on
   ellipsoid, torus, close-sheet Cyclide, saddle, and sharp-CAD cases without
   regression in topology, patch semantics, world-space fidelity, runtime,
   or repeatability.
6. `TRI-CONFORMAL-SPIKE1`: keep full conformal embedding as an isolated research
   spike. It must cover disk, genus zero, genus one, and genus greater than one
   with deterministic failure diagnostics. Stop if it requires silent
   stretching reduction or cannot pass physical-space topology and envelope
   verification; do not make it the default native engine before those gates.

## Backward references and follow-up priority

- Du and Wang, *Anisotropic Centroidal Voronoi Tessellations and Their
  Applications* (2005): ACVT definition and comparison baseline.
- Zhong et al., *Particle-Based Anisotropic Surface Meshing* (2013): the 3D
  AVD predecessor and close-sheet failure comparison.
- Alliez et al., *Anisotropic Polygonal Remeshing* (2003): principal-direction
  metric construction and smoothing precedent.
- Rong et al., *Centroidal Voronoi Tessellation in Universal Covering Space of
  Manifold Surfaces* (2011): topology-specific canonical-domain CVT basis.
- Jin et al., *Discrete Surface Ricci Flow* (2008): intrinsic conformal
  embedding kernel and its triangulation sensitivity.
- Yan et al., *Isotropic Remeshing with Fast and Exact Computation of
  Restricted Voronoi Diagram* (2009): topology control cited by the paper and
  a parameterization-free alternative.
- Cheng, Dey, and Ramos (2006), and Boissonnat, Wormser, and Yvinec (2008):
  refinement-based anisotropic meshing with stronger geometric/topological
  analysis than the CVT route.
