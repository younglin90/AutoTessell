# Centroidal Voronoi Tessellations: Applications and Algorithms

## Bibliography and access

- Qiang Du, Vance Faber, and Max Gunzburger.
- *SIAM Review*, Vol. 41, No. 4, 1999, pp. 637-676.
- DOI: `10.1137/s0036144599352836`
- Local copy: `papers/pdf/15_du_1999_cvt_review.pdf`.
- Status: `FULL_READ` (40/40 pages, 2026-07-23). Note: the task brief listed
  28 pages; the actual PDF is the full 40-page SIAM Review article. All 40
  pages were extracted and read.
- Read context: foundational reference for poly route-1 (conforming
  Voronoi / VoroCrust-style), specifically the planned optional true
  restricted-cell CVT optimization step. The paper treats *unconstrained*
  CVT of a domain; the restriction analysis below is ours, not the paper's.

## Theory: energy functional and critical-point characterization

**Definitions.** Given open `Omega subset R^N`, generators `{z_i}_{i=1..k}`,
Voronoi regions `V_i = { x in Omega : |x - z_i| < |x - z_j|, j != i }` (1.1),
and density `rho >= 0` on `Omega`, the mass centroid of a region `V` is

```
z* = ( \int_V y rho(y) dy ) / ( \int_V rho(y) dy )        (1.2)
```

A **centroidal Voronoi tessellation (CVT)** is the special configuration
where `z_i = z_i*` for all `i` (1.3): each generator is the mass centroid of
its own Voronoi region. Solutions are generally non-unique (e.g. the k-strip
vs k-triangle tessellations of a square, Fig 1.2; square/triangle/hexagon
lattices of the plane).

**Energy functional (transcribed).** Over independent points AND independent
tessellations:

```
F( (z_i, V_i), i=1..k ) = sum_{i=1..k} \int_{y in V_i} rho(y) |y - z_i|^2 dy   (3.1)
```

and the reduced (points-only) energy, with `V_i` *defined* as the Voronoi
regions of the `z_i`:

```
K( (z_i), i=1..k ) = sum_{i=1..k} \int_{y in V_i(Z)} rho(y) |y - z_i|^2 dy     (3.4)
```

**Critical-point characterization.**

- *Proposition 3.1* — a **necessary** condition for `F` to be minimized is
  that simultaneously (a) `{V_i}` are the Voronoi regions of `{z_i}` and
  (b) each `z_i` is the mass centroid of `V_i`. I.e. minimizers of `F` are
  CVTs. Proof: first variation in `z_j` forces the centroid condition;
  pointwise `rho(y)|y - z_j|^2 <= rho(y)|y - z_i|^2` forces the Voronoi
  partition.
- *Proposition 3.2* — `F` and `K` have the same minimizer.
- *Lemma 3.4* — `K` is continuous (for compact `Omega`, continuous `rho`),
  so a **global minimizer exists**.
- *Proposition 3.5* — at any local minimizer generators are distinct
  (`z_i != z_j`); degenerate coincident seeds are never locally optimal
  when `rho > 0` a.e.
- **The CVT property is necessary but NOT sufficient** for optimality:
  Section 6.1 exhibits a 2-generator square tessellation along the diagonal
  that is a fixed point of Lloyd's map but a **saddle point** of the energy
  (energy `5/12 + eps^2/18 - eps^4/36` decreases as the diagonal rotates to
  the midline). So a converged Lloyd state can be a saddle, not a minimum.

**Gradient structure (Section 6.1).** With `T = F o G` the Lloyd map
(`G`: seeds -> Voronoi vertices, `F`: vertices -> centroids), and
`M = diag( \int_{V_i} rho dy )`:

```
dG/dZ (Z) = 2 M(G(Z)) (Z - T(Z))                          (6.3)
d2G/dZ2 at a fixed point = 2 M ( I - dT/dz )              (Prop 6.3)
```

So stationary points of the reduced energy are exactly fixed points of
Lloyd's map, and local strict convexity of the energy forces the Jacobian
eigenvalues of `T` to be real and `< 1` (necessary for local contraction).

## Algorithms and convergence facts

**Lloyd's method (Section 5.2).** Iterate: (1) build Voronoi tessellation of
current seeds; (2) move each seed to the mass centroid of its region;
(3) repeat until converged. Fixed points = CVTs. Lloyd is the special case
of the general descent scheme `Z <- Z - alpha B dG/dZ` with `alpha = 1/2`,
`B = M^{-1}` (Section 6.2), hence for small enough steps energy strictly
decreases until stationarity.

**What is PROVEN in this paper:**

- Existence of a global minimizer (Lemma 3.4).
- CVT = necessary optimality condition (Prop 3.1); saddle points exist.
- 1D, smooth strictly positive **log-concave** density: the Lloyd map is a
  local contraction near fixed points, so Lloyd is **locally convergent**
  (Prop 6.4, via Gerschgorin on the tridiagonal Jacobian), and the energy is
  locally strictly convex there (Prop 6.5).
- 1D uniform density: Lloyd converges **linearly** with rate
  `1 - ||T_k|| ~ pi^2 / (4 k^2)` — painfully slow for large k; the
  overrelaxed variant (`alpha = 1`, `B = M^{-1}`) roughly doubles the rate
  (`~ pi^2 / (2 k^2)`).
- Random (MacQueen) k-means: almost-sure convergence of the **energy**
  [40]; discrete sequential k-means converges to a **local** minimum [55].
- Exhaustive discrete clustering is `O(m^{kN+1})` (Thm 5.1); finding the
  optimal clustering is **NP-hard** in general [12, 13, 48].

**What is NOT proven (explicit gaps):**

- No convergence proof for Lloyd in dimension `N >= 2`, not even local, and
  no global convergence in any dimension. (Global convergence to *some*
  critical point in multi-D came only in later work, e.g. Du-Emelianenko-Ju
  2006 — outside this paper.)
- No convergence *rate* except the 1D uniform case.
- Gersho's conjecture (asymptotically all cells congruent to one optimal
  basic cell) is proven only in 2D (regular hexagon, Newman [44]); **open
  in 3D** — so "CVT cells become nice truncated-octahedron-like cells" is a
  conjecture, not a theorem, in our dimension.
- Newton's method: locally quadratic for smooth densities, but `dT/dz` is
  expensive in `N > 1`; quasi-Newton suggested, no analysis given.
- Annealing-style noisy Lloyd (LBG variant [38]) for global optimization:
  heuristic, "no convergence theory was provided."

**Density-function weighting (for graded sampling).** 1D asymptotics
(Section 6.4.1, deterministic analog of Wong [63]): for the optimal CVT with
`k -> inf`,

```
|V_i| ~ c tau / rho^{1/3}(m_i)      and     energy per cell ~ equidistributed
```

i.e. cell size scales as `rho^{-1/3}` **in 1D**. The paper does NOT derive
the N-dimensional exponent (heuristically `rho^{-1/(N+2)}`, i.e. `rho^{-1/5}`
in 3D via Gersho-type arguments — not established here). Practical
consequence: to target a local size field `h(x)` in 3D, take
`rho ~ h^{-5}` as the starting guess but **calibrate empirically**, since
the exponent is unproven in 3D. The numerical experiments (Section 7) show
CVT generators follow density peaks much less aggressively than Monte Carlo
sampling — CVT spreads generators to cover low-density regions, which is
exactly the graded-but-not-clumped behavior we want for interior seeds.

## Applications relevant to meshing

- **Finite-difference/covolume schemes (Section 2.4):** on a Voronoi-
  Delaunay dual grid, choosing `z_i` = centroid of `V_i` makes the
  divergence/gradient difference equations second-order in truncation error;
  covolume methods get `O(h^2)` L2 error on centroidal grids vs `O(h)` on
  general grids. This is the core numerical argument for why CVT-optimized
  poly cells are better finite-volume cells: generator-at-centroid is
  precisely the collocation-point-at-cell-centroid property OpenFOAM's
  skewness/non-orthogonality metrics reward.
- **Optimal quadrature (Section 2.2):** CVT minimizes the Lipschitz-class
  quadrature error bound — same functional, `p`-th power metrics give
  generalized centroids.
- **Grid generation (Section 8):** the authors explicitly propose CVT for
  unstructured grid generation and note Lloyd-like iterations already
  existed in adaptive-grid methods; they conjecture CVT grids may avoid
  "grid crossovers and slivers." Aspirational in 1999 — no meshing
  experiments in the paper itself.
- Numerical experiments (Section 7) are all 2D squares: uniform density
  converges toward hexagonal-like lattices (square lattice is an unstable
  fixed point, Fig 7.2 — another saddle-escape illustration); graded
  densities give smoothly graded, well-shaped polygons.

## Limitations for our restricted (frozen-boundary) setting

Our planned step is a **restricted-cell CVT** pass in 3D: boundary seed
pairs/triples (VoroCrust-style) are **frozen** to preserve the reconstructed
surface exactly; only interior seeds move; every cell is clipped against
`Omega`. The paper analyzes unconstrained CVT of `Omega`. What survives:

**Survives the restriction:**

1. *Energy framework.* `F`/`K` are already defined on regions clipped to
   `Omega` (definition (1.1) intersects with `Omega`), so the functional
   needs no modification — we simply minimize over the sub-vector of free
   (interior) seeds.
2. *Centroid condition on free seeds.* Prop 3.1's first-variation argument
   is per-seed: varying only free `z_j` still yields `z_j = centroid(V_j)`
   as the necessary condition for the free coordinates. Frozen boundary
   seeds simply are not required to be centroids (and won't be).
3. *Partition optimality.* For ANY fixed generator set the Voronoi partition
   minimizes `F` over partitions — independent of which seeds are frozen.
4. *Monotone descent of frozen-boundary Lloyd.* Both half-steps (re-Voronoi;
   move free seeds to centroids) individually do not increase `F`, so an
   interior-only Lloyd pass is still a monotone energy descent and its fixed
   points are exactly the restricted stationary points. This is the
   theoretical license for the `POLY-CVT-LLOYD1` card.
5. *Gradient identity componentwise.* (6.3) is diagonal in seeds:
   `dG/dz_i = 2 M_i (z_i - T_i(Z))` holds for each free seed, enabling
   restricted gradient/quasi-Newton variants and a cheap stationarity check
   (`max_i |z_i - centroid_i|`).

**Does NOT survive / needs guards:**

1. *Every convergence proof.* Local contraction (Prop 6.4) and the linear
   rate are 1D-only; nothing transfers to restricted 3D. We get monotone
   energy descent with no rate and no guarantee of reaching a minimizer.
2. *Fixed point != minimum.* The saddle-point example survives in the worst
   way: a converged restricted Lloyd state can still be a saddle. A mesh
   quality gate must decide acceptance; energy convergence alone is not a
   quality certificate.
3. *Centroid containment.* In a convex domain Voronoi cells are convex and
   contain their centroids. Our clipped cells adjacent to a nonconvex
   boundary can be nonconvex; the centroid of a clipped cell can fall
   outside the cell or even outside `Omega`. The paper never handles this
   (its regions are convex or the issue is ignored). Free-seed updates need
   a containment check + projection/damping.
4. *Boundary-face invariance is OUR constraint, not the paper's.* The
   surface reconstruction relies on mirrored boundary seed pairs generating
   the boundary faces. Moving an interior seed too close to the boundary can
   steal territory from a boundary cell and re-cut the surface polygons.
   The unconstrained theory is silent on this; each Lloyd step needs a
   per-seed guard (e.g. interior seed must stay farther from each boundary
   sample than the corresponding frozen pair half-gap), with rollback.
5. *`rho^{-1/3}` sizing is 1D.* Use `rho ~ h^{-(N+2)} = h^{-5}` in 3D only
   as an uncalibrated heuristic; the paper proves nothing in 3D (Gersho's
   conjecture open).
6. *Cell-shape optimality in 3D is conjectural.* Even unconstrained 3D CVT
   is not proven to produce near-congruent well-shaped cells; near a frozen
   boundary the cells are provably NOT centroidal (their seeds are pinned),
   so quality improvement is expected only in the interior bulk, fading in
   the boundary layer of cells. Set expectations in the gate accordingly.

## Falsifiable implementation cards

### `POLY-CVT-LLOYD1` — frozen-boundary interior Lloyd pass with quality gate

Add an optional post-pass to the poly route-1 pipeline: iterate
(re-Voronoi + clip; move ONLY interior seeds to clipped-cell mass
centroids), with per-seed guards (centroid containment in cell, minimum
clearance to frozen boundary seed pairs, damping factor on violation) and
full rollback on gate failure. Termination: `max_i |z_i - c_i|` below
tolerance or iteration cap (expect slow, Lloyd is linearly convergent at
best). Pass criteria: (a) energy `K` monotonically non-increasing across
iterations (assert every step); (b) boundary faces bit-identical (same
vertex set / same polygons) before vs after the pass; (c) NativeMeshChecker
grade of the mesh does not regress and interior skewness/non-orthogonality
quantiles improve on the cube + at least 2 bench STLs; (d) on gate failure
the emitted mesh is byte-identical to the pre-pass mesh. Failure of (b) on
any fixture falsifies the guard design, not the card's tolerance tuning.

### `POLY-CVT-DENSITY1` — density-graded interior seed sampling

Drive interior seed sampling by a density `rho(x) = h(x)^{-alpha}` derived
from the sizing field (surface curvature / feature distance), with
`alpha = 5` as the 3D starting exponent (1D theory gives `alpha = 3`; 3D is
uncalibrated — sweep `alpha in {3, 4, 5, 6}`). Pass criteria: (a) realized
local cell diameters correlate with `h(x)` (Spearman rho > 0.8 on a graded
fixture); (b) cell-energy `\int_{V_i} rho |y - z_i|^2` distribution after
`POLY-CVT-LLOYD1` is tighter (lower coefficient of variation) than uniform
sampling at equal seed count; (c) no grade regression vs uniform sampling on
the bench set. If no `alpha` in the sweep beats uniform sampling on (c), the
card is falsified for our fixtures.

## Snowball references (max 5)

1. S. Lloyd, "Least square quantization in PCM," IEEE Trans. Inform. Theory
   28 (1982) 129-137 — the original Lloyd's method [39].
2. A. Gersho, "Asymptotically optimal block quantization," IEEE Trans.
   Inform. Theory 25 (1979) 373-380 — Gersho's conjecture, asymptotic cell
   congruence, basis for the `rho^{-1/(N+2)}` sizing heuristic [14].
3. D. Newman, "The hexagon theorem," IEEE Trans. Inform. Theory 28 (1982)
   137-139 — proof that the 2D asymptotic optimal cell is the regular
   hexagon [44].
4. J. MacQueen, "Some methods for classification and analysis of
   multivariate observations," Proc. 5th Berkeley Symp. (1967) 281-297 —
   random k-means and a.s. energy convergence [40].
5. A. Okabe, B. Boots, K. Sugihara, *Spatial Tessellations: Concepts and
   Applications of Voronoi Diagrams*, Wiley, 1992 — comprehensive Voronoi
   reference, computation algorithms [47].
