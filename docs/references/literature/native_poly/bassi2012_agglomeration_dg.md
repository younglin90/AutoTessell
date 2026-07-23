# On the Flexibility of Agglomeration Based Physical Space Discontinuous Galerkin Discretizations

## Bibliography and access

- F. Bassi, L. Botti, A. Colombo, D.A. Di Pietro, P. Tesini.
- *Journal of Computational Physics* 231 (2012) 45-65.
- DOI: `10.1016/j.jcp.2011.08.018`
- Local copy: `papers/pdf/18_bassi_2012_agglomeration_dg.pdf`
- Status: `FULL_READ` (pages 21/21, read 2026-07-23). Text extracted via pypdf;
  all 21 pages read including figures' captions and both result tables.
- **Screening correction:** the row for this paper in
  `gap_search_3d_agglomeration.md` describes it as "arbitrarily-shaped **3D**
  agglomerated elements ... (Euler/Navier-Stokes)". The paper itself is
  explicitly **2D** ("For the sake of simplicity, the focus is here on the
  two-dimensional case, although the technique readily extends to higher space
  dimensions", Sec. 1) and its model problem is the **Poisson equation** (BR2),
  not Euler/NS. The 3D Euler/NS agglomeration work is later Bassi-group output
  (e.g. Botti-Colombo-Bassi 2017, already tabled as P2 CONTEXT).

## Problem and scope

Show that DG's insensitivity to element shape can be exploited to use
**agglomerates of fine-mesh elements as the actual solution elements**: define
polynomial spaces directly on arbitrarily shaped physical-frame elements, run
BR2 for second-order PDEs on them, drive agglomeration for h-adaptivity, and
approximate curved boundaries through the underlying fine mesh instead of
high-order mesh generation. Domain is 2D; fine mesh R may be non-conforming and
curved (polynomial mappings of degree m >= 1 from reference simplex/square).

## Agglomeration algorithm (Q1)

- **Primal:** any standard fine mesh R (triangles/quads, possibly curved,
  possibly non-conforming) produced by an ordinary mesh generator. An
  agglomerated element T is the open union of a subset R_T of fine elements;
  T_h must partition the domain and each T must be connected. That is the
  entire admissibility contract — no convexity, no star-shapedness, no
  planarity, no bound on face count.
- **Algorithm:** the multilevel graph-agglomeration library **MGridGen**
  (Moulitsas-Karypis), used with default settings: (i) coarse graphs by a
  "globular" agglomeration heuristic; (ii) an uncoarsening/refinement phase
  that minimizes a dual objective — weighted sum of aspect ratios plus maximum
  aspect ratio. Aspect ratio is the **only** shape control anywhere in the
  pipeline.
- **h-adaptivity hook:** the authors modified MGridGen so each fine element
  carries a target agglomeration factor card(R_T)-bar, treated as an **upper
  bound** on the achieved card(R_T) (a lower bound is possible but rejected —
  it degrades mesh quality). Refinement/coarsening halves/doubles the local
  factor by comparing normalized per-element L2 errors against thresholds
  (two libMesh-style strategies, Examples 2-3).
- The fine mesh never changes: no nodes are moved, added, or deleted, and no
  refinement-tree bookkeeping exists. Agglomeration is purely a relabeling of
  fine elements into groups.

## DG-on-agglomerates machinery — what DG needs from a cell (Q2)

1. **Basis:** monomials of total degree <= k in a translated element frame
   centered at the barycenter and **aligned with the principal axes of
   inertia**, L2-normalized, then orthonormalized by modified Gram-Schmidt
   (applied twice for machine-precision orthonormality). Output is the r_ii,
   r_ij coefficients, used to evaluate basis functions and derivatives
   anywhere in T. The inertia-frame choice keeps mass-matrix conditioning and
   the divergence-theorem conservation error Er_grad-u independent of aspect
   ratio; the naive global-frame monomial choice blows up (Fig. 1).
2. **Integration:** every integral over T is a sum over fine sub-elements
   E in R_T mapped to reference elements with standard Gauss rules (Eq. 23).
   Needed exactness q = k*m + j grows with geometric order; a reduction
   algorithm picks the minimum degree of exactness such that the diagonal
   mass-matrix entries are within tol of exact (Eq. 25), extended to face
   integrals. So DG needs **only an integrable decomposition** of the cell —
   never a face normal, centroid, or planarity of the agglomerate itself.
3. **Faces:** two definitions — a *mesh face* (shared boundary portion with
   one neighbor) vs a *facet* (image of one fine-element face). Faces are
   always processed as unions of facets, each with its own geometric map.
   Stabilization eta_F > max over sharing elements of card(F_T) guarantees
   BR2 coercivity (Theorem 1, extending Brezzi et al. 2000); in practice
   eta_F > 1 + card(F_F \ {F})/2. Both face definitions give near-identical
   results (Fig. 9).
4. **Geometric representation:** the agglomerate has none of its own — its
   geometry *is* the collection of (possibly curved) fine sub-elements and
   facets.

**Contrast with the FV contract:** an OpenFOAM-style FV cell needs a planar
(or tolerably warped) polygonal face with a single well-defined normal and
centroid, an owner-neighbor centroid line with bounded non-orthogonality and
skewness, and positive-volume star-shaped safety. None of these quantities is
ever *computed* in this paper, let alone bounded. The machinery that makes
arbitrary agglomerates work (per-facet integration + physical-frame
orthonormal basis + face-count-scaled penalty) has no FV analogue.

## Cell-geometry quality control (Q3)

Essentially none beyond MGridGen's aspect-ratio objective. Arbitrary shapes
are tolerated and even showcased (L-shaped element, Fig. 3; curved-boundary
agglomerate, Fig. 4b). No validity test, no planarity measure, no
non-orthogonality/skewness, no convexity. Quality shows up only as (a) basis
conditioning — solved by the inertia frame + MGS, not by fixing the mesh —
and (b) the stabilization bound, which depends on face *counts*, not face
*geometry*.

## Boundary treatment (Q4)

Curved boundaries are preserved through the fine mesh: each boundary mesh
face is the union of its facets, each with its own (e.g. quadratic 8-node)
geometric approximation. Refining R near the boundary improves the location
of the discrete boundary and its normals/curvature **without changing the DOF
count** of T_h (only quadrature cost grows). Annulus test (exact solution
u = cos(pi*r), homogeneous Dirichlet on the exact boundary): with a fixed
32x32 agglomerated grid over fine meshes of (32*2^i)x32 quadratic quads,
k-convergence approaches the exponential reference as i grows; at i = 0 the
geometric consistency error floors the L2 error near 1e-5. This "decouple
geometry from solution" trick is DG-specific — it relies on sub-facet
quadrature, which FV cannot use.

## Experiments

- 2D Poisson, BR2, exact solution of Karniadakis-Sherwin (Eq. 20).
- **Approximation:** polygonal grids of 64/255/1028/4122 elements agglomerated
  from a 200x200 uniform quad grid; optimal h-convergence for both L2
  projection and BR2 with k = 1..6. Errors on polygonal grids are almost
  invariably *larger* than on uniform quad grids of comparable size.
- **h-adaptivity (k = 1):** both strategies redistribute error and hold
  second-order convergence; adapted grids always beat uniform polygonal grids
  at equal element count; different starting grids converge to overlapping
  error curves.
- **Cost:** the 255-element polygonal grid averages **156 fine sub-elements
  per polygon** and 14 facets per mesh face. Versus a standard 256-quad grid,
  exact assembly needs >50x the element quadrature points and about 8x the
  face points; reduced quadrature cuts points ~3x (elements) / ~2x (faces)
  with negligible error change, leaving a matrix-assembly penalty of about
  10-17x and shape-function-evaluation penalty of 37-79x (Tables 2-3).

## Limitations

- All demonstrations 2D; 3D is claimed by extension only.
- Elliptic model problem only — no Euler/NS, no convection.
- Quadrature efficiency admitted to be an open issue; the per-fine-element
  integration cost is the price of tolerating arbitrary shapes.
- No mesh-quality metrics reported for the agglomerates; no cell-validity
  concept at all.
- Agglomerate faces are never geometric entities — nothing here says a
  face-based FV solver could consume these meshes.

## AutoTessell applicability — effect on the agglomeration-leg demotion

**Strengthens the demotion, on two counts.**

1. It is *weaker* as evidence than the screening assumed: the gap-search row
   credited it with 3D Euler/NS agglomerated elements; the actual paper is a
   2D Poisson study. The "four primary 3D sources" count in the gap-search
   verdict should be revised down to three (Dargaville 2021, Sukumar-Tupek
   2022, Antonietti-Corti-Martinelli 2026) for element-level 3D evidence.
2. It makes the DG-vs-FV requirement gap *explicit and mechanical*. Everything
   that lets an arbitrary agglomerate act as an element here — per-facet
   quadrature over the retained fine mesh, physical-frame orthonormal bases,
   penalty scaled by face counts — is machinery a cell-centered FV code does
   not possess. The paper never computes a single agglomerate-face normal,
   centroid, planarity, or non-orthogonality. So its "arbitrary shapes are
   fine" conclusion transfers to OpenFOAM export *not at all*; it is the
   cleanest citation for why agglomeration evidence from the DG world cannot
   underwrite an FV mesh product.

What *is* reusable: (a) MGridGen's two-phase agglomerate construction with an
aspect-ratio objective is a concrete, non-ML baseline algorithm for the
quality-gated agglomeration leg (pairs with the Dargaville 2021 METIS
comparison); (b) the locally-driven agglomeration-factor upper bound is a
clean interface for cell-budget-driven coarsening; (c) the honest cost data
(156 sub-elements/cell) warns that keeping the primal around for geometry is
expensive — AutoTessell's agglomerates must instead *become* real polyhedra
with planar-enough faces, which is exactly the property this paper never
needed and never checked. `POLY-AGGLOM-CFD1` remains the decisive gate.

## Falsifiable implementation cards

### `POLY-AGGLOM-FACEGEOM1`

When the agglomeration leg merges 3D cells, each merged interface must be
collapsed to explicit polygonal faces and measured: max facet-normal deviation
from the aggregate face normal, face non-planarity (OpenFOAM `checkMesh`
definition), and resulting owner-neighbor non-orthogonality/skewness. Pass
only if agglomerated cells meet the same FV thresholds the dual leg meets on
identical fixtures; cells relying on "union of facets" geometry (the Bassi
2012 representation) with planarity above threshold must be rejected or
split, never exported. This operationalizes the DG-vs-FV gap this paper
demonstrates and feeds directly into `POLY-AGGLOM-CFD1`.

### `POLY-AGGLOM-SHAPE1`

Implement an MGridGen-style two-phase agglomerator (globular growth +
refinement minimizing weighted-sum and max aspect ratio) with a per-cell
agglomeration-factor upper bound, as a deterministic non-ML baseline for the
agglomeration leg. Pass if, on the `POLY-AGGLOM-CFD1` fixtures, it produces
connected agglomerates honoring the per-cell budget bound and its
aspect-ratio distribution is no worse than METIS aggressive agglomeration
(Dargaville 2021 winner); tie-break by the `POLY-AGGLOM-FACEGEOM1` FV
metrics, which neither source paper reports.

## Snowball references (<= 5)

1. Moulitsas, Karypis 2001, *Multilevel algorithms for generating coarse
   grids for multigrid methods*, SC2001 (+ MGridGen tech report) — the actual
   agglomeration algorithm and aspect-ratio objective used here; primary
   source for `POLY-AGGLOM-SHAPE1`.
2. Rashid, Selimotic 2006, *A three-dimensional finite element method with
   arbitrary polyhedral elements*, IJNME 67, 226-252 — the 3D
   arbitrary-polyhedron CG counterpart cited as the alternative approach.
3. Mousavi, Xiao, Sukumar 2010, *Generalized Gaussian quadrature rules on
   arbitrary polygons*, IJNME 82, 99-113 — the direct-polygon quadrature the
   authors flag as the future replacement for sub-element integration.
4. Tesini 2008, *An h-multigrid approach for high-order discontinuous
   Galerkin methods*, PhD thesis, Univ. Bergamo — origin of the
   physical-frame polynomial-space construction.
5. Gassner, Lörcher, Munz, Hesthaven 2009, *Polymorphic nodal elements and
   their application in discontinuous Galerkin methods*, JCP 228, 1573-1590 —
   the quadrature-free polyhedral-element DG alternative.
