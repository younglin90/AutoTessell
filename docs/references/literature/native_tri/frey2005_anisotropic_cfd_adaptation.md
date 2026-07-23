# Frey and Alauzet - Anisotropic Mesh Adaptation for CFD Computations

## Bibliography and access

- Pascal J. Frey and Frederic Alauzet.
- *Computer Methods in Applied Mechanics and Engineering*, 194 (2005),
  5068-5082. Received 8 December 2003, revised 24 June 2004, accepted
  26 November 2004.
- DOI: `10.1016/j.cma.2004.11.025`.
- Local full text:
  `papers/pdf/20_frey_2005_anisotropic_cfd_adaptation.pdf`.
- Review status: `FULL_READ` on 2026-07-23. Pages 15/15. All 15 pages were
  text-extracted; pages 4, 5, 6, 9, and 10 were rendered at 2x resolution and
  the error-bound equations (3)-(9), the unit-mesh relations (10)-(12), the
  metric truncation (13), the relative estimate (14), the metric edge length
  (16), the surface geometric metric (17), and the anisotropic Delaunay
  measure were visually checked against the extraction.

## Problem and contract

Given a PDE solution `u_h` computed on a mesh `T_h` of a bounded domain
`Omega` in `R^3`, generate a new mesh on which the approximation error is
bounded by a user tolerance with a minimal number of degrees of freedom. The
paper's route is indirect: by Cea's lemma (proved for elliptic problems,
assumed to transfer to hyperbolic ones),

```text
||u - u_h|| <= c ||u - Pi_h u||,
```

so controlling the **interpolation error** `u - Pi_h u` of the exact solution
by the mesh controls the approximation error. The interpolation error is a
purely geometric quantity — the distance between a Cartesian surface and its
piecewise linear interpolant — which is why the authors call this a
*geometric error estimate*, independent of the equation being solved
(Navier-Stokes, advection-diffusion, thermal, waves).

This is the canonical statement of Hessian-metric-based anisotropic
adaptation: error bound -> metric tensor field -> **unit mesh** with respect
to that field.

## Interpolation-error bound (Section 2)

For a tetrahedron `K = [a,b,c,d]` and the linear interpolant `Pi_h u`
coinciding with `u` at vertices, a Taylor expansion with integral remainder
around the interior maximum-error point `x` (where `grad(u - Pi_h u)(x) = 0`)
gives, with `a'` the intersection of line `ax` with the opposite face and
`k <= 3/4`:

```text
|e(x)| <= (9/32) max_{y in K} |<aa', H_u(y) aa'>|          (2)
```

Writing `|H_u| = R |Lambda| R^-1` (eigendecomposition with absolute
eigenvalues, Eq. 3), the practical chain of bounds is:

```text
||u - Pi_h u||_{inf,K} <= (9/32) max_{y in K} max_{v in K} <v, |H_u(y)| v>   (5)
   maximum on a face:   <= (2/9)  max over face vectors                      (6)
   maximum on an edge:  <= (1/8)  max_{y in ab} <ab, |H_u(y)| ab>            (7)
```

Since any `v` in `K` is a combination of edges, the vector maximum reduces to
the edge set `E_K`:

```text
||u - Pi_h u||_{inf,K} <= c_d max_{x in K} max_{e in E_K} <e, |H_u(x)| e>    (9)
```

with `c_d` a dimension constant (9/32 interior case in 3D). Finally a
constant-over-`K` metric tensor `M(K)` is postulated such that

```text
max_{x in K} <e, |H_u(x)| e> <= <e, M(K) e>   for all e in E_K,
```

with the ellipsoid region of `M(K)` minimal in volume, giving the element
error model

```text
e_K = c max_{e in E_K} <e, M(K) e>.                                          (10)
```

The error on `K` is therefore the squared longest edge length **measured in
the metric**.

## Unit mesh (the central contract)

Fix the tolerated error `epsilon` and rescale `M(K) := (c/epsilon) M(K)`.
Then the requirement "error <= epsilon on every element" becomes

```text
<e, M(K) e> = 1  for all e in E_K   ==   (l_M(e))^2 = 1.                (11,12)
```

A mesh is a **unit mesh** when every edge has length ~1 under the metric.
Because the metric varies in space, the edge length is the integrated metric
length along the parametrized edge `gamma(t) = P + t PX`:

```text
l_M(PX) = Integral_0^1 sqrt( t(PX) M(t) PX ) dt.                             (16)
```

All mesh generation (surface and volume) is then re-expressed as: produce a
mesh whose edges satisfy `l_M(e) ~ 1`.

## Metric tensor construction

### Truncation (Eq. 13)

The vertex metric is built from the Hessian eigendecomposition with
eigenvalue clamping:

```text
M = R Lambda~ R^-1,
lambda~_i = min( max( c |lambda_i| / epsilon, 1/h_max^2 ), 1/h_min^2 ),
```

where `h_min`/`h_max` are the smallest/largest allowed edge sizes. This
clamping exists because a locally linear solution has a vanishing eigenvalue
and would request infinite size; `h_min` also bounds the explicit-scheme time
step. **Note:** the paper imposes *no explicit anisotropy-ratio cap*; the
ratio is only implicitly bounded by `h_max/h_min`. In the M6 experiment the
realized aspect ratio is about 10. A production system that wants a direct
ratio cap must add it as an extra clamp on the eigenvalue spread — that is an
extension, not something transcribed from this paper.

### Relative and local normalization (Eq. 14)

The absolute bound (9) is dimensional; to mix variables and to capture weak
phenomena next to strong shocks, the estimate is normalized:

```text
|| (u - Pi_h u) / (alpha |u|_eps + hbar ||grad u||_2) ||_{inf,K}
   <= c max_x max_e < e, |H_u(x)| / (alpha |u(x)|_eps + hbar ||grad u(x)||_2) e >,
```

with `|u|_eps = max(|u|, eps ||u||_{inf,Omega})`, `hbar` the element
diameter, and `0 < alpha < 1`. The gradient term makes the estimate *local*,
so weak features are refined even in the presence of shocks elsewhere.

## Operations on metrics (Section 2.5)

- **Intersection (simultaneous reduction).** When several metrics coexist at
  one vertex (multiple variables, or geometric ∩ computational), the combined
  metric `M_{1∩2}` is the metric of maximal ellipsoid volume whose ellipsoid
  is contained in `E_M1 ∩ E_M2`. It is computed by simultaneous reduction of
  the two quadratic forms: form `N = M_1^-1 M_2`, take its eigenvectors as
  the common basis `P = (e1 e2 e3)`, express both metrics diagonally there,
  and keep the larger eigenvalue per direction.
- **Interpolation along an edge.** For endpoint metrics `M_1`, `M_2` on
  segment `gamma(t)`, the paper uses the monotone scheme

  ```text
  M(t) = ( (1-t) M_1^{-1/2} + t M_2^{-1/2} )^{-2},  0 <= t <= 1,          (15)
  ```

  implemented in the simultaneous-reduction basis: with `h_{j,i} =
  1/sqrt(eigenvalue_i(M_j))`, interpolate the sizes linearly,
  `H_i(t) = (1-t) h_{1,i} + t h_{2,i}`, and rebuild
  `M(t) = tP^-1 diag(1/H_i(t)^2) P^-1`. This turns the discrete vertex map
  into a continuous metric field (the same scheme extends to interpolation
  inside a tetrahedron).
- **Gradation.** The intersected metric must additionally be smoothed for
  mesh gradation before use; the paper delegates the operator to Borouchaki,
  Hecht, Frey 1998 (ref [9]) and only states that the gradation-corrected
  metric `M~` is what finally governs all mesh modifications.

## Adaptation loop and convergence behavior

The scheme is a fixed-point iteration (mesh `i` -> mesh `i+1`):

1. Solve on `T_h^i` (finite element / finite volume).
2. Recover the Hessian of the adaptation variable at vertices.
3. Build the vertex metric (13)-(14); intersect with the geometric surface
   metric (17); apply gradation -> `M~`.
4. Adapt the **surface** mesh to `M~` by local modification.
5. Adapt the **volume** mesh to `M~` by anisotropic constrained Delaunay.
6. Interpolate the solution to the new mesh; continue solving.

Convergence is *asserted schematically* ("by repeating this procedure a
'limit' mesh is obtained"), not proved: in the experiments the loop is simply
run for a fixed 9 adaptations, one every 250 solver time steps. Two
stabilizing choices are stated: most existing vertices are **preserved**
across remeshing to limit solution-interpolation round-off error, and new
volume vertices largely come from the background (previous-iteration) mesh.

### Hessian recovery (Section 4.1)

At vertex `P` with ball `B(P)`, write the order-2 Taylor expansion at each
neighbor `P_i` and collect the 6 unknown Hessian coefficients into the
overdetermined system `A X = B` (`n = |B(P)| >= 6` rows), solved via normal
equations `tA A X = tA B` (6x6, Gauss elimination). If `|B(P)| < 6`, the
ball is enlarged with second-ring vertices. (Gradient `grad u(P)` is assumed
available; alternatives cited: variational recovery, Green-formula recovery.)

## Unit-mesh generation operators (Section 3)

### Surface (2D-on-surface treatment)

The surface is a bare triangulation with **no CAD link**. A C^1 geometric
support is built from local quadrics fitted at vertices, giving principal
curvatures `kappa_1, kappa_2` and directions. In the local frame
`(h1 h2 h3)` (two principal tangent directions + normal), the **geometric
metric** is

```text
G = (h1 h2 h3) diag( alpha kappa_1^-2, beta kappa_2^-2, 1 ) t(h1 h2 h3),   (17)
```

i.e., element size proportional to the radii of curvature, minimizing the
tangent-plane deviation between the mesh and the underlying surface. `G` is
intersected with the computational metric `M` when one exists, and the
gradation-corrected `G ∩ M` drives the operators: **edge collapse** (short
edges), **edge split** into unit-length segments (long edges), **edge flip**,
**node removal, node repositioning, degree relaxation** — all measured with
`l_M~`. (No explicit numeric long/short thresholds are given in this paper;
the standard `[1/sqrt(2), sqrt(2)]` band is later Alauzet practice, not this
text.)

### Volume (3D treatment)

A constrained Delaunay procedure first builds an **empty mesh** (boundary
only, no internal vertices), then inserts internal points selected by edge
length analysis using the **anisotropic Delaunay kernel**: Euclidean distance
is replaced by `l_M`, the circumcenter `O_K` solves
`l_M(O_K, P_i) = l_M(O_K, P_j)` for all vertex pairs, `r_K = l_M(O_K, P_j)`,
and the cavity of an inserted point uses the Delaunay measure
`alpha_M(P,K) = l_M(O_K,P) / l_M(O_K,P_j) < 1`. Because this system is
nonlinear and the metric discrete, the implementation **freezes the metric
locally** and works with Euclidean approximations. Surface and volume are
adapted by different codes (Yams for surface, Gamanic3d for volume) sharing
the single metric field — the architectural point AutoTessell cares about.

## Experimental evidence

- **ONERA M6 wing, transonic Euler** (Mach 0.8395, incidence 3.06 deg,
  lambda shock; adaptation variable = Mach number; 9 adaptations, every 250
  time steps). Initial mesh 7,815 vertices / 37,922 tets. Final isotropic
  mesh: 231,113 vertices / 1,316,631 tets. Final anisotropic mesh: 23,516
  vertices / 132,676 tets — roughly **one order of magnitude fewer DOF at
  the same error level**, with max aspect ratio ~10. CPU (Pentium 4): surface
  31 s / volume 132 s / 250 solver steps 2,782 s isotropic, versus 3 s /
  25 s / 318 s anisotropic.
- **Supersonic business jet** (Dassault data; Mach 1.8, incidence 3 deg,
  altitude 15,200 m; sonic-boom near-field prediction). Initial 34,412
  vertices / 178,632 tets -> final (iteration 9) 124,320 vertices / 734,046
  tets; Mach cones sharply captured with minimal numerical diffusion.
- Solver NSC3KE; both cases are inviscid Euler — no boundary-layer/RANS
  anisotropy is exercised, so the ~10 aspect ratios are shock-driven, far
  from the 1000:1 ratios BL metrics demand.

## Limitations and claim boundary

- Cea's lemma is only proved elliptic; its use for hyperbolic CFD is an
  assumption backed by practice, not analysis.
- The element metric `M(K)` (minimal-volume ellipsoid dominating the Hessian
  over `K`) is postulated; its computation is delegated to the INRIA report
  RR-4759, and the vertex-based discrete metric is an approximation of it.
- No convergence proof for the fixed-point loop; iteration count is fixed by
  hand. No mesh-quality statistics (dihedral angles, sliver counts) are
  reported for the anisotropic tet meshes.
- No explicit anisotropy-ratio cap; only `h_min`/`h_max` clamping.
- The Hessian least-squares recovery has no accuracy analysis here, and
  recovered Hessians on coarse meshes are known (from later literature) to be
  noisy — the truncation (13) is the only safeguard.
- Gradation control, the surface local-quadric construction, and the
  anisotropic Delaunay kernel are all referenced, not specified — this paper
  is the *architecture* reference; the operator details live in [1], [9],
  [17], [21].
- Metric interpolation (15) predates the log-Euclidean framework; it is
  monotone along a segment but the paper offers no spd-cone geometry
  argument.

## AutoTessell applicability — the shared sizing contract

The BL plan
(`docs/references/boundary_layers/native_bl_literature_integrated_development_plan_2026-07-23.md`,
section 1 item 3) commits to one anisotropic source metric shared by surface
remeshing, BL placement, and core transition. This paper defines exactly the
algebra such a contract needs, and its own Section 3.2 demonstrates the
pattern: two independent metric sources (geometric `G`, computational `M`)
merged by intersection into one field that then governs *both* the surface
and the volume mesher.

**What survives without a flow solution (solver-independent — adopt):**

1. The unit-mesh contract itself: sizing is a vertex field of 3x3 SPD
   tensors, and every operator decision reduces to `l_M(e) ~ 1` via the
   integrated length (16).
2. Eigenvalue truncation (13): `lambda~_i = min(max(lambda_i^src,
   1/h_max^2), 1/h_min^2)` — identical machinery whatever produced
   `lambda_i^src`.
3. Metric intersection by simultaneous reduction (Section 2.5) — the merge
   operator for curvature metric ∩ user size ∩ BL metric ∩ gradation.
4. Metric interpolation (15) in the simultaneous-reduction basis — the
   continuity operator turning vertex metrics into a field.
5. Gradation smoothing of the merged field (via ref [9]).
6. The curvature source (17): `diag(alpha kappa_1^-2, beta kappa_2^-2, ·)`
   in the principal frame. This *is* the Hessian replacement: for surface
   approximation the curvature tensor plays the role `|H_u|` plays for
   solution interpolation (Remark 2.1 makes the equivalence explicit — the
   interpolation error *is* a surface-to-linear-approximation distance).

**What is solver-dependent (drop until a flow field exists):** Cea's-lemma
justification, Hessian least-squares recovery (4.1), the relative/local
normalization (14), and the solve-adapt fixed-point loop with solution
interpolation. When AutoTessell's metric sources are geometry/curvature, the
loop degenerates to a single (or few) remesh passes because the source field
does not change with the mesh — only gradation re-smoothing iterates.

Code targets: the metric algebra module should be shared by
`core/preprocessor/native_remesh/` (anisotropic surface path per Alliez 2003
/ Zhong 2013), `core/layers/native_bl.py` (BL placement), and the volume
sizing transition in `core/generator/`. None of these currently share a
tensor sizing field.

## Falsifiable implementation cards

1. `SIZING-METRIC-ALG1`: implement a shared metric-algebra module (vertex
   field of 3x3 SPD tensors) with exactly the paper's four operations:
   eigen-truncation to `[1/h_max^2, 1/h_min^2]` plus an explicit
   anisotropy-ratio cap (our extension — flagged as such), simultaneous-
   reduction intersection, size-linear interpolation (15), and integrated
   edge length (16) by quadrature. Property tests: intersection result is
   SPD, its ellipsoid is contained in both inputs, and it dominates both
   quadratic forms; interpolation is monotone per direction and endpoint-
   exact; truncation is idempotent. Accept only if all properties hold on
   randomized SPD pairs including near-degenerate (ratio 10^6) tensors.
2. `SIZING-CURV-SOURCE1`: build the curvature source metric (17) from the
   fitted-quadric principal curvatures in the local frame, feed it through
   `SIZING-METRIC-ALG1` intersection with a user uniform-size metric and
   gradation, and drive the surface remesher by `l_M`. Accept only if (a)
   the realized edge-length histogram in the metric concentrates near 1,
   and (b) surface Hausdorff deviation decreases monotonically as the
   curvature coefficients `alpha, beta` tighten, on curved benchmarks
   (sphere, torus, blended CAD fillets).
3. `SIZING-BL-INTERSECT1`: express the BL normal-direction size law as a
   metric tensor (small size along the wall normal, tangential sizes from
   the surface metric) and merge it with the curvature metric by
   simultaneous reduction, then verify the single merged field reproduces
   both requirements: first-layer thickness within 5% of the BL law at wall
   vertices, and tangential sizing unchanged (within 5%) where the BL metric
   is weaker. Fail if intersection ordering (BL-first vs curvature-first)
   changes the result — the operator must be associative-in-practice on
   these inputs.

## High-value references from this paper

- Alauzet and Frey (2003), INRIA RR-4759, *Estimateur d'erreur geometrique
  et metriques anisotropes, Partie I*: the full derivation of the error
  estimate and the element metric `M(K)` — the missing proofs of this paper.
- Borouchaki, Hecht, Frey (1998), *Mesh gradation control*, IJNME 43(6):
  the gradation operator applied to the merged metric.
- Castro-Diaz, Hecht, Mohammadi, Pironneau (1997), *Anisotropic unstructured
  mesh adaptation for flow simulations*: origin of the relative-error
  normalization idea.
- Frey (2000), *About surface remeshing*, 9th IMR: the surface local-
  modification operator set and geometric support used in Section 3.2.
- George (1997), *Improvement on Delaunay based 3D automatic mesh
  generator*, FEAD 25: the Delaunay kernel extended anisotropically by
  Gamanic3d.
