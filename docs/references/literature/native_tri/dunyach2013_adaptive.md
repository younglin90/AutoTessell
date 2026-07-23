# Dunyach et al. - Adaptive Remeshing for Real-Time Mesh Deformation

## Bibliography and access

- Marion Dunyach, David Vanderhaeghe, Loic Barthe, Mario Botsch.
- Eurographics 2013 - Short Papers, pages 29-32, The Eurographics Association.
- DOI: `10.2312/conf/EG2013/short/029-032`.
- Official record and full text: `https://diglib.eg.org/items/bd0987f0-b1d0-45cc-bde4-2a99ebf51946`.
- Author-hosted PDF checked against the official record:
  `https://cg.cs.tu-dortmund.de/publications/2013-remeshing.pdf`.
- Review status: `FULL_READ` on 2026-07-23. All four pages, both figures,
  Table 1, equations (1)-(6), limitations, and the complete reference list were
  visually inspected from rendered pages as well as read from extracted text.

## Problem and scope

The paper targets adaptive isotropic triangle remeshing fast enough to be
interleaved with interactive deformation. It seeks two properties: sampling
density that increases with surface curvature, and triangles that remain close
to equilateral. Its contribution is deliberately narrow: replace the single
target length in Botsch and Kobbelt's uniform local-operation loop with a
curvature-derived sizing field, then modify relaxation so that it preserves the
relative sizing.

The paper calls the input parameter `epsilon` an approximation tolerance, but
it does not provide an error-bounded algorithm. It explicitly reports that RMS
error is below `epsilon` while maximum Hausdorff error typically is not. The
method is therefore a sizing heuristic derived from a local smooth-surface
model, not a geometric envelope certificate.

The algorithm assumes the triangle connectivity and discrete differential
operators needed by a manifold surface-remeshing loop. It is not presented as
a triangle-soup repair, self-intersection removal, or non-manifold handling
method. Boundary valence is mentioned, but robustness and topology predicates
are deferred to the underlying remeshing framework rather than specified here.

## Baseline operation loop

The uniform baseline from [BK04] applies the following stages for 5-10 outer
iterations:

1. Correct edge lengths. Collapse an edge shorter than `(4/5) L` and split an
   edge longer than `(4/3) L`.
2. Flip an interior edge only when the flip decreases
   `sum_v (valence(v) - target(v))^2` over the four affected vertices, with
   target valence 6 for an interior vertex and 4 for a boundary vertex.
3. Relax vertex positions tangentially.
4. Optionally project the relaxed vertices back to the original surface; the
   paper locates the closest source triangle with a kD-tree.

For the uniform relaxation, let `N_i` be the one-ring neighbors of `x_i` and
let `n_i` be its unit normal. The weighted neighbor center and tangent-plane
projection are

```text
c_i = sum_{j in N_i} w_j x_j / sum_{j in N_i} w_j
x_i <- c_i + n_i n_i^T (x_i - c_i),             (1)
```

normally with `w_j = 1`. The paper specifies the outer stage order, but not the
edge traversal order, conflict schedule, or whether collapse and split are
separate sub-sweeps. Those details must not be inferred from this short paper.

Important source check: some indexed text reverses the two fractions. The
rendered paper is unambiguous: collapse below `4/5 L`, split above `4/3 L`.
This hysteresis interval avoids immediately undoing a length correction.

## Curvature-derived sizing field

### Local geometric derivation

For a chord of length `l` approximating a circular arc of radius `r` with
sagitta error `epsilon`, Figure 1 and equation (2) give

```text
r^2 = (r - epsilon)^2 + (l/2)^2
l   = 2 sqrt(2 r epsilon - epsilon^2).           (2)
```

For a general planar curve, the osculating-circle model substitutes
`r = 1/kappa`. On a surface, the method is isotropic and therefore uses the
most restrictive normal section,

```text
kappa = max(abs(kappa_min), abs(kappa_max)).
```

The chord length is converted to the side length of an equilateral triangle
whose circum-diameter is `l` by the factor `3/sqrt(12) = sqrt(3)/2`. Hence

```text
L(x_i) = sqrt(6 epsilon / kappa_i - 3 epsilon^2),
L(x_i) in [L_min, L_max].
```

The derivation is local and assumes an osculating smooth surface. The paper
does not define behavior for `kappa_i = 0`, a negative radicand caused by an
invalid tolerance range, or an undefined curvature estimate. A production
implementation needs explicit finite-value handling, using `L_max` for flat
regions and rejecting or conservatively clamping invalid inputs.

### Discrete curvature

The method uses the cotangent discretization and the Voronoi area `A_i` from
[MDSB03]:

```text
H_i     = 0.5 ||Delta x_i||,                                      (3)
K_i     = (1/A_i) (2 pi - sum_{j in N(i)} theta_i),                (4)
kappa_i = H_i + sqrt(H_i^2 - K_i).                                (5)
```

Here the angle sum is over triangles incident on `x_i`. The paper describes
equation (5) as the maximum absolute curvature estimate. It does not specify
boundary angle-defect handling, obtuse-triangle area handling beyond citing
[MDSB03], smoothing of noisy curvature, or a numerical guard for
`H_i^2 - K_i < 0`. These omissions matter because noise in `kappa_i` directly
becomes noise in target edge length.

For an edge `e = (x_1, x_2)`, length correction uses the conservative endpoint
minimum

```text
L(e) = min(L(x_1), L(x_2)).
```

Thus a high-curvature endpoint controls the whole edge. No gradation or
Lipschitz limiter is defined, so abrupt sizing changes can remain.

## Sizing-aware relaxation

Ordinary neighbor-centroid smoothing would erase a nonuniform vertex density.
The adaptive method instead uses incident triangle barycenters `b_j`:

```text
c_i = sum_{t_j in T_i} |t_j| L(b_j) b_j
      / sum_{t_j in T_i} |t_j| L(b_j),             (6)
```

where `L(b_j)` is the average of the three vertex sizing values. The center is
then projected into the tangent plane using equation (1). This is adapted from
Optimal Delaunay Triangulation smoothing [CH11]. The authors choose element
barycenters instead of circumcenters for robustness and simplicity.

The paper does not provide an inversion, fold-over, minimum-angle, or envelope
acceptance test for the relocation. AutoTessell must simulate and guard a move
before commit; equation (6) is a proposed target, not sufficient acceptance
logic.

## Feature behavior

For a feature-edge set, such as edges selected by a large dihedral angle, the
paper prescribes:

- discard a split, collapse, or flip that would destroy a feature edge;
- pin a corner vertex incident on more than two feature edges;
- constrain a vertex incident on exactly two feature edges to move along its
  feature line;
- compute a feature vertex's sizing value as the average of its non-feature
  neighbors, avoiding artificial oversampling caused by a sharp crease's
  curvature estimate;
- apply equation (6) along the feature line by replacing the incident
  triangles with the two incident feature edges, and replacing triangle areas
  and barycenters with edge lengths and midpoints.

The paper does not define how features are propagated through every topology
operation, how a feature junction with no non-feature neighbor is sized, or how
patch boundaries and user semantics are represented. AutoTessell must treat
wall, patch-interface, boundary, and user-selected feature provenance as hard
constraints. A dihedral detector can supplement those semantics but cannot
replace them.

## Deformation-specific refinement

The sculpting application performs one adaptive-remeshing iteration after each
small deformation step. Before that iteration it tentatively splits each edge
in the region of interest at its midpoint. The edge is split only if the
deformed midpoint differs by more than `epsilon` from the midpoint of the
deformed edge endpoints. This reuses `epsilon` instead of introducing another
parameter.

This midpoint test measures failure of a linear edge to represent the applied
deformation; it is not a static source-to-remesh Hausdorff test. It should not
be used as AutoTessell's final surface-fidelity gate.

## Experimental evidence

Table 1 evaluates the authors' method with 5 outer iterations and
back-to-surface projection. Their timings were measured on one core of an Intel
Xeon E5645 at 2.4 GHz with 6 GB RAM:

| Model | Output vertices | Time | Minimum angle | Mean per-triangle minimum angle |
|---|---:|---:|---:|---:|
| Feline | 21k | 1.4 s | 26 deg | 51 deg |
| Elk | 31k | 2.0 s | 32 deg | 51 deg |
| Horse | 6k | 0.94 s | 28 deg | 51 deg |
| Joint | 3.1k | 0.64 s | 15 deg | 47 deg |
| Fandisk | 4k | 0.25 s | 18 deg | 49 deg |

The authors report at least an order-of-magnitude speed advantage over the
listed high-quality remeshers and much better smallest angles than their
implementations of two real-time methods. This is indicative rather than a
controlled benchmark: comparator results came from different machines, some
models and outputs differ, and the paper itself says the timings are not
directly comparable. The table reports no Hausdorff maxima, topology failures,
feature drift, memory use, or repeatability.

Figure 2 visually demonstrates adaptive Feline remeshing, uniform Joint
remeshing, and feature-preserving interactive sculpting. It is qualitative
evidence only. In the sculpting workflow, the authors state that projection can
be disabled without visible quality loss because each deformation is small and
smooth; that observation does not justify disabling projection for an offline
CFD surface mesher.

## Explicit limitations and missing guarantees

- `epsilon` is not an exact approximation bound. RMS error is below it, but
  maximum Hausdorff error typically exceeds it.
- Discrete curvature and the derived sizing field are the stated source of the
  approximation mismatch.
- The implementation is single-threaded.
- No convergence proof or complexity bound is given for the local-operation
  loop.
- No self-intersection, fold-over, manifold, or exact topology guarantee is
  stated in this paper.
- No deterministic conflict schedule is specified.
- No cap-aware behavior is described when the requested tolerance implies too
  many vertices.
- Feature handling is geometric and local; semantic provenance is outside the
  paper's scope.

## AutoTessell gap and decision

The current native isotropic path in
`core/preprocessor/native_remesh/isotropic.py` already has constant-length
split, collapse, valence flip, and relaxation stages with the same `4/3` and
`4/5` thresholds. It does not implement this paper's curvature sizing or
area-and-sizing-weighted barycenter. Its optional projection snaps to an
original vertex rather than the closest point on an original triangle. Its
feature path locks detected vertices instead of distinguishing pinned corners
from vertices allowed to slide along a feature polyline. These differences are
material, not parameter tuning.

Adopt the paper's local curvature-to-size derivation, conservative edge size,
sizing-aware relaxation target, and corner/feature-line distinction. Do not
adopt its use of `epsilon` as if it were a hard error guarantee. Keep an
independent two-sided envelope check, topology guards, semantic provenance,
deterministic ordering, and a cap-aware stopping rule.

## Falsifiable implementation cards

1. `TRI-CURV-SIZE1`: implement equations (3)-(5), the clamped sizing formula,
   and `L(e) = min(L_1,L_2)`. On analytic plane, sphere, and cylinder meshes,
   require finite values, `L_max` on the plane, and local target lengths that
   track the analytic curvature ordering. Reject the card if curvature noise
   creates non-finite sizes, cap overflow, or worse two-sided surface error
   than the constant-size baseline at equal vertex count.
2. `TRI-ADAPT-LOOP1`: replace the global `h` only in the length-correction
   predicates while retaining the exact hysteresis `collapse < 4/5 L(e)` and
   `split > 4/3 L(e)`. Require deterministic output, manifold/orientation
   invariants, no protected-edge loss, and a measurable reduction in vertices
   on mixed flat/high-curvature corpus cases at matched envelope error.
3. `TRI-ODT-RELAX1`: use equation (6) as the proposed relocation followed by
   tangent projection and closest-triangle source projection. Commit only when
   local orientation, minimum angle, semantic constraints, and envelope guards
   pass. Require a better lower-tail angle metric without fidelity regression
   against the current centroid target.
4. `TRI-FEATURE-SLIDE1`: pin feature junctions and slide degree-two feature
   vertices along their provenance-carrying feature polylines. Require zero
   semantic feature loss, bounded line drift, and no non-manifold or duplicate
   faces on sharp CAD-like fixtures. A global feature-vertex lock is the
   baseline, not the acceptance target.

## Reference inventory and snowball priorities

The paper cites 21 works. All were checked in the rendered reference section:

- [ACdVDI03] Alliez et al., *Isotropic Surface Remeshing*.
- [ACSD03] Alliez et al., *Anisotropic Polygonal Remeshing*.
- [ACSYD05] Alliez et al., *Variational Tetrahedral Meshing*.
- [AUGA08] Alliez et al., *Recent Advances in Remeshing of Surfaces*.
- [AWC04] Angelidis et al., *Sweepers*.
- [BK03] Bendels and Klein, *Mesh Forging*.
- [BK04] Botsch and Kobbelt, *A Remeshing Approach to Multiresolution
  Modeling*.
- [BKP10] Botsch et al., *Polygon Mesh Processing*.
- [BS08] Botsch and Sorkine, *On Linear Variational Surface Deformation
  Methods*.
- [CH11] Chen and Holst, *Efficient Mesh Optimization Schemes Based on Optimal
  Delaunay Triangulations*.
- [dC76] do Carmo, *Differential Geometry of Curves and Surfaces*.
- [FAKG10] Fuhrmann et al., *Direct Resampling for Isotropic Surface
  Remeshing*.
- [GD99] Gain and Dodgson, *Adaptive Refinement and Decimation under Free-Form
  Deformation*.
- [KRK06] Kil et al., *3D Warp Brush Modeling*.
- [MDSB03] Meyer et al., *Discrete Differential-Geometry Operators for
  Triangulated 2-Manifolds*.
- [SAG03] Surazhsky et al., *Isotropic Remeshing of Surfaces: A Local
  Parameterization Approach*.
- [SCC11] Stanculescu et al., *Freestyle: Sculpting Meshes with Self-Adaptive
  Topology*.
- [SG03] Surazhsky and Gotsman, *Explicit Surface Remeshing*.
- [vFTS06] von Funck et al., *Vector Field Based Shape Deformations*.
- [VRS03] Vorsatz et al., *Dynamic Remeshing and Applications*.
- [YLL09] Yan et al., *Isotropic Remeshing with Fast and Exact Computation of
  Restricted Voronoi Diagram*.

Highest-priority backward snowball reads are:

1. [BK04], DOI `10.2312/SGP/SGP04/189-196`, because Dunyach et al. defer the
   exact local topology loop and the two length thresholds to it.
2. [MDSB03], DOI `10.1007/978-3-662-05105-4_2`, for mixed Voronoi areas,
   boundary cases, and the precise cotangent curvature operator.
3. [CH11], DOI `10.1016/j.cma.2010.11.007`, to determine the energy and validity
   assumptions behind the barycenter ODT relaxation.
4. [VRS03] and [BKP10] for feature propagation, corner classification, and
   constrained sliding details that this short paper summarizes only.
5. [ACSD03] for the original error-to-sizing derivation and the anisotropic
   alternative.
6. [FAKG10], DOI `10.2312/PE/VMV/VMV10/009-016`, and [YLL09] for the
   high-quality and parallel/RVD comparators used in Table 1.

Forward snowballing should specifically search for later work that cites
Dunyach et al. for error-bounded remeshing. Any such claim must be checked
against this paper's explicit admission that maximum Hausdorff error typically
exceeds `epsilon`.
