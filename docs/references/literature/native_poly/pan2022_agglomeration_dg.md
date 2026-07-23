# Agglomeration-based Geometric Multigrid Solvers for Compact Discontinuous Galerkin Discretizations on Unstructured Meshes

## Bibliography and access

- Y. Pan and P.-O. Persson (UC Berkeley / LBNL).
- *Journal of Computational Physics* 449 (2022) 110775. Available online 18 Oct 2021.
- DOI: `10.1016/j.jcp.2021.110775`
- Local PDF: `papers/pdf/22_pan_2022_agglomeration_dg.pdf`
- Status: `FULL_READ` (12/12 pages), read 2026-07-23.
- Screening correction: `gap_search_3d_agglomeration.md` characterizes this paper as
  "aspect-ratio-aware agglomerate selection on 3D unstructured meshes". That is
  **wrong on both counts** — the agglomeration heuristic has no aspect-ratio or any
  other shape objective, and every numerical experiment is 2D (3D is explicitly
  future work in the conclusions). The abstract's "arbitrary element shapes and
  dimensions" refers to what the *formulation* tolerates, not what is demonstrated.

## Problem and assumptions

Goal: an h-multigrid preconditioner (right-preconditioned GMRES, single V-cycle,
damped block-Jacobi smoother) for the Compact Discontinuous Galerkin (CDG) method
applied to Poisson and convection-diffusion. The mesh hierarchy is built by
recursively agglomerating the input unstructured mesh until one element remains.
The paper's central premise is the *opposite* of a mesh-quality argument: because DG
needs no C0 continuity, modal polynomial bases can be defined on arbitrarily shaped
polyhedra, so agglomerate shape barely matters. The only restriction on an element
is that it must not self-intersect.

## Agglomeration algorithm (Algorithms 1-2)

- **Validity definition:** a partition of the element set is valid iff the union of
  elements in each subset is a **connected** domain. That is the entire constraint —
  no convexity, no aspect ratio, no size grading, no face-planarity requirement.
  Resulting blocks are "in general non-convex" and may be non-simply-connected
  (airfoil hierarchy).
- **Greedy vertex-star heuristic:** each element carries an integer weight = number
  of not-yet-processed neighbors; a priority queue is processed in ascending weight
  order. For the popped element (if weight >= 2): find its vertex adjacent to the
  most unprocessed elements (ties broken at random), and agglomerate *all*
  unprocessed elements touching that vertex into one block. If weight < 2, the
  orphan element is appended to the smallest adjacent existing block. Repeat until
  the queue is empty; recurse per level until a single element remains.
- **Cost:** O(n log n) time, O(n) memory (n = mesh size; only one integer per queue
  entry).
- METIS is cited as the standard alternative; the authors deliberately use the
  crude heuristic "to demonstrate the generality of the method for mesh partitions
  of arbitrary shape and quality" — i.e., the partitioner is intentionally not
  optimized, to show solver insensitivity.

## What the solver needs from agglomerated cell geometry

Remarkably little — this is the crux for FV transfer:

- **Basis:** modal polynomials (1, x, y, ...) per block; no reference-element
  mapping, no nodal placement, hence no geometric regularity requirement.
- **Quadrature:** integration over a block = sum of quadratures over its constituent
  input-mesh sub-elements. No new quadrature rules are ever built on the polygonal
  shapes; the fine mesh's rules are reused at every level for free.
- **Transfer operators:** prolongation is simple injection (same modal basis family
  on every level); restriction is its L2 adjoint via mass matrices
  (M_{l+1} R = (M_l L)^T). Operator coarsening is Galerkin RAT, A_{l+1} = R A_l L,
  applied to the **flux formulation** (M, G, D, C blocks coarsened separately, then
  Schur complement) — direct coarsening of the primal operator degrades convergence
  as h→0 (confirming Fortunato-Rycroft-Saye 2019).
- **CDG-specific:** the switch function controls sparsity of the non-compact C
  block; a "consistent" switch (each element has at least one +1 and one -1 face,
  Eq. 22) minimizes second-neighbor couplings lost by coarsening and is empirically
  important (natural/random switch clearly deteriorates convergence).
- Nowhere are face centroids, cell centroids, planarity, non-orthogonality, or
  skewness of the agglomerates computed or needed.

## Curved / exact boundary handling

Nothing special is done. Agglomerates are exact unions of input-mesh elements, so
the domain boundary (including the NACA airfoil) is inherited verbatim from the
fine mesh at every level; there is no re-approximation, no curved-face machinery,
and no discussion of geometric fidelity. Boundary conditions enter only through the
flux definitions with penalty C_D = γ/h_avg on Dirichlet parts.

## Cell-quality metric

**None reported and none enforced.** The only shape-related evidence is Section
5.1.1: a regular quadrilateral hierarchy vs a deliberately irregular non-convex
hierarchy on the same square mesh. The irregular hierarchy costs more GMRES
iterations, but the penalty is *independent of h* — presented as evidence of shape
insensitivity, not as a quality control mechanism.

## Experiments (all 2D, p = 1 only)

- Poisson on [0,1]^2, uniform n×n quads: flux coarsening flat under refinement;
  primal coarsening degrades as h→0. Larger Dirichlet penalty helps block Jacobi;
  C_D = 10^4/h_avg adopted.
- Regular vs irregular hierarchies (above).
- NACA airfoil, 605-element unstructured mesh: consistent switch converges well
  despite non-simply-connected agglomerates; natural (random-enumeration) switch
  deteriorates badly.
- Convection-diffusion β v·∇u + Δu = f on the airfoil mesh: robust for small β,
  deteriorates for β ≳ 10 (expected; line smoothers / ordered ILU suggested).
- Settings: V-cycle, npre = 0, npost = 3, block Jacobi α = 2/3, GMRES tol 1e-8.
  Iteration counts only — **no wall-clock timings**.

## Limitations

- All experiments 2D; 3D, parallelization, and other equations are future work.
- No agglomerate quality metric, no shape control, no size-grading control.
- p = 1 only; higher p deferred to a p-multigrid front end (hp-multigrid sketch).
- Solver-level machinery (switch functions, flux coarsening) is CDG/LDG-specific.
- No timing or memory benchmark; the hierarchy is admitted to be "not optimal".

## AutoTessell applicability (route-2 agglomeration verdict)

This paper **strengthens the demotion** of agglomeration to a quality-gated
secondary route, and in fact weakens the entry under which it was screened:

- It is 2D-demonstrated, DG-only evidence. Every property that lets it ignore cell
  shape — modal basis without reference mapping, composite sub-element quadrature,
  L2-projection transfer — is exactly what a cell-centered FV/OpenFOAM
  discretization does *not* have. FV needs owner/neighbour face geometry,
  centroids, planarity, non-orthogonality and skewness bounds; this paper needs
  none of them, so its success transfers zero evidence to the FV setting.
- Its "validity" bar (connectedness of each block) is necessary but far below
  polyMesh admissibility. It confirms that solver-side agglomeration literature
  systematically under-specifies the geometry contract AutoTessell must satisfy.
- The one transferable seed: the greedy **vertex-star grouping** (merge all cells
  around a chosen vertex) is structurally the same move as node-dual/Fluent-style
  cell assembly, with O(n log n) cost and a natural orphan-absorption rule
  (append to smallest adjacent block — a pattern reusable for sliver absorption).
  If route 2's agglomeration leg is ever exercised, this is a cheap deterministic
  baseline to benchmark against METIS (cf. Dargaville 2021), but it must be wrapped
  in AutoTessell's own FV quality gates because the source paper enforces none.
- The composite-quadrature idea (treat an agglomerate as a union of primal tets for
  all integration) mirrors what `native_poly` already does for volumes/centroids
  via decomposition; no change needed there.

## Falsifiable implementation cards

### `POLY-AGGLOM-VSTAR1`

Implement the Pan-Persson greedy vertex-star agglomerator (priority queue by
unprocessed-neighbor count, vertex-star merge, smallest-adjacent-block orphan
absorption) as a route-2 candidate partitioner over a tet primal, emitting each
block as a candidate polyhedral cell. Pass only if, on the standard fixture set,
(a) every block is edge-connected and star-testable under `POLY-STAR-VALID1`,
(b) the resulting polyMesh passes checkMesh-level non-orthogonality/skewness gates
at a rate reported side-by-side against a METIS baseline, and (c) results are
deterministic under a fixed tie-breaking seed. The paper provides no quality
evidence, so this card is a measurement, not an endorsement; failure of (b) on
most fixtures is further confirmation of the demotion.

## Snowball references (FV-side agglomeration trail cited by this paper)

| Ref | Why |
| --- | --- |
| Chan, Xu, Zikatanov 1998, *An agglomeration multigrid method for unstructured grids* | Classic FV-adjacent agglomeration multigrid — the [5] in the paper's claim that agglomeration "has been used successfully for finite volume methods". |
| Jones, Vassilevski 2001, *AMGe based on element agglomeration*, SIAM J. Sci. Comput. | Element-agglomeration AMG; algebraic admissibility conditions for agglomerated elements. |
| Strauss, Azevedo 2003, *On the development of an agglomeration multigrid solver for turbulent flows* | Actual CFD/FV agglomeration multigrid application — closest cited evidence to an FV context. |
| Ekström, Berggren 2010, *Agglomeration multigrid for the vertex-centered dual DG method* | Agglomeration on a vertex-centered **dual** mesh — intersects route 2's dual leg directly. |
| Fortunato, Rycroft, Saye 2019, *Efficient operator-coarsening multigrid schemes for LDG*, SIAM J. Sci. Comput. | Source of the flux-vs-primal coarsening result this paper depends on; scopes what is DG-solver-specific vs geometric. |
