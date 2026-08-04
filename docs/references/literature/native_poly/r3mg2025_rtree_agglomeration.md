# R3MG: R-tree Based Agglomeration of Polytopal Grids with Applications to Multilevel Methods

## Bibliography and access

- Marco Feder (Univ. of Pisa), Andrea Cangiani (SISSA), Luca Heltai (Univ. of Pisa).
- *Journal of Computational Physics* 526 (2025) 113773.
- DOI: `10.1016/j.jcp.2025.113773`
- Local PDF: `docs/references/papers/source/pdf/21_r3mg_2025_rtree_agglomeration_multigrid.pdf`
- Status: `FULL_READ` (pages 23/23, read 2026-07-23). Note: the task brief listed
  51 pages; the actual published PDF is 23 pages, all read via full-text
  extraction. Figures were not rendered (poppler unavailable); all figure
  content is cross-checked against the captions and in-text descriptions.
- Software: `PolyDEAL` C++ library on deal.II, MPI-parallel, R*-tree via
  Boost.Geometry (<https://github.com/fdrmrc/Polydeal>).

## Problem and assumptions

Given an arbitrary fine polygonal/polyhedral/simplicial/hex mesh with no
hierarchy information (e.g. a CAD model meshed by external software), build
coarse "polytopal" grids and a nested hierarchy of them, cheaply and
automatically, for use with polytopal discontinuous Galerkin (DG) methods and
geometric multigrid preconditioning. The competing baseline is METIS k-way
graph partitioning, which processes only mesh topology and ignores geometry.

Key framing: an "agglomerated element" here is the **set-union of fine cells
that share an R-tree ancestor node**. The element geometry is never re-meshed.
Its boundary remains the collection of fine-mesh facets; interfaces between
agglomerates may consist of many faces separated by hanging nodes/edges
(explicitly stated in Sec. 5.2). The DG discretization is built to tolerate
exactly this: tensor-product polynomial bases are defined on each agglomerate's
**bounding box** and restricted to the physical element, and quadrature is done
on the retained fine-cell sub-tessellation.

## Algorithm

1. Compute the axis-aligned minimum bounding rectangle MBR(T_i) of every fine
   cell (i = 1..N).
2. Insert all MBRs into an R*-tree of order (m, M) [Beckmann et al. 1990,
   Boost.Geometry implementation]. They set M = 2^d and m = M/2 = 2^{d-1}, so
   in 2D each node holds up to 4 children, in 3D up to 8 — mimicking
   quad/octree branching. R*-tree insertion heuristics minimize MBR area,
   MBR-MBR overlap, and perimeter, and maximize node fill.
3. Pick a target level l in {1..L} of the tree. For every node n on level l,
   recursively collect all leaves (fine cells) under n (Algorithms 1-2, a
   plain tree walk).
4. Flag each leaf set as one agglomerate. Traversing all nodes of a level
   yields a partition of the fine mesh; traversing successive levels yields a
   **nested hierarchy by construction** (children of a node are
   sub-agglomerates of its agglomerate).

Input parameter is the extraction level (vs METIS's n_partitions). Multiple
material regions are handled by building one independent tree per region and
gluing; the coarsest common grid is then dictated by the shallowest tree.
MPI-parallel version agglomerates within each locally owned partition; ghost
polytopal elements are owned by other ranks and exchanged in a setup phase.

## Theory and guarantees

- **Balance (size, not shape):** inherited from the R-tree invariants — every
  node holds between m and M entries and all leaves are at the same depth, so
  every level-l agglomerate contains between roughly m^{l-1} and M^{l-1} fine
  cells. This is a cardinality-balance guarantee only.
- **Nestedness:** exact, by construction, at zero extra cost. This is the
  paper's central structural claim and the enabler for cheap injection-based
  multigrid transfer operators (prolongation = natural injection, restriction
  = its transpose, matrix-free).
- **Shape regularity: NO theorem.** Closeness of agglomerates to their AABBs
  is an empirical observation driven by the R*-tree's area/overlap/perimeter
  minimization heuristics, quantified a posteriori via metrics (below). There
  is no proven bound on aspect ratio, no proof agglomerates are even
  **face-connected** (spatial proximity of MBRs is not adjacency; the issue is
  never discussed), no convexity or star-shapedness claim.
- **Determinism:** not discussed explicitly. The pipeline is heuristic but has
  no randomization; given a fixed fine-mesh iteration order, Boost R*-tree
  insertion is reproducible. Contrast METIS, whose k-way partitioner is
  seeded-randomized. Reproducibility across cell orderings is NOT guaranteed
  (R-tree structure depends on insertion order).
- **Dimension independence:** genuine — the algorithm sees only d-dimensional
  boxes; 2D/3D and quad/hex/tet/Voronoi fine cells are all uniform cases.
- **Multigrid convergence theory:** explicitly open — "theoretical analysis of
  the convergence properties of the multigrid method covering an arbitrary
  number of agglomeration levels is under investigation" (Sec. 6). DG
  stability/convergence on such rough elements leans entirely on the
  Cangiani-Dong-Georgoulis line [27-29].

## Experiments

Grids: structured square 32x32 (O1), structured disk 20,480 quads (O2),
unstructured square 93,184 quads (O3), 1024-cell CVT (O4), structured unit
cube 32,768 hex (O5), CAD piston hex mesh via CUBIT (O6), brain 634,472 tets
(O7), multi-material liver 284,201 tets (O8).

- **Structure preservation:** on O1, level extraction reproduces exact 4x4 and
  8x8 Cartesian coarsenings; METIS at equal element count gives jagged, skinny
  polygons even on a Cartesian fine grid. On the CVT, levels give a clean
  2^l x 2^l square-like pattern.
- **Quality metrics** (averages, level 1 / level 2; R-tree vs METIS at equal
  element count): Uniformity Factor UF = diam(K)/h, Circle Ratio CR
  (inscribed/circumscribed radius, circumscribed approximated by diam/2, CGAL
  for inscribed), Box Ratio BR = |K|/|MBR(K)|, global Overlap Factor
  OF = |Omega| / sum|MBR(K_i)|. R-tree beats METIS on essentially all
  averages: e.g. O3 level 1 BR 0.92 vs 0.60, OF 0.93 vs 0.58; O1 is exactly
  optimal (all 1.0). Caveat the paper itself flags: **minimum** CR can be
  slightly worse than METIS on the disk (axis-aligned boxes vs curved,
  non-axis-aligned geometry — worst-case elongated boundary agglomerates).
- **Cost:** agglomeration wall-clock is level-independent and orders of
  magnitude below METIS_PartGraphKway on 2D O3, refined piston, and brain
  meshes (Fig. 15); authors call the cost "negligible with respect to all the
  components involved in a full pipeline".
- **DG accuracy:** Poisson with manufactured solutions; p-refinement gives
  exponential convergence on all 2D/3D agglomerated grids, h-refinement gives
  optimal rates; R-tree curves are equal or marginally better than METIS
  (METIS slightly better in L2 on the piston). So agglomerate shape barely
  matters for polytopal-DG accuracy — the discretization is designed to be
  shape-insensitive.
- **R3MG preconditioning:** V-cycle (Chebyshev smoothers, direct coarse solve)
  preconditioning CG. Iteration counts roughly level- and size-independent:
  O1 ~6, O2 ~12-14, O3 ~13-17, cube 4-6, piston 9-13; unpreconditioned CG
  needs 10^2-10^4+ iterations and fails to converge at p=3 on O3.

## Limitations

- Element geometry is inherited wholesale from the fine mesh: agglomerate
  "faces" are unmerged fine facets with hanging nodes. Nothing is planarized,
  simplified, or optimized. Cell data (quadrature, bases) always references
  the fine sub-tessellation — the fine mesh must be kept in memory.
- No shape-regularity, connectivity, or aspect-ratio guarantee; curved and
  non-axis-aligned geometry degrades worst-case CR (axis-aligned box bias).
- Quality is assessed only with polytopal-DG proxy metrics (UF/CR/BR/OF).
  **No FV metric appears anywhere**: no non-orthogonality, skewness, face
  planarity/warpage, or owner-neighbor face construction. No FV solver is run.
- Multi-region agglomeration is region-respecting but coarsest-level size is
  hostage to the shallowest region tree.
- Multigrid theory open; scalability study deferred; assembly cost dominated
  by sub-tessellation quadrature (mitigation via quadrature-free integration
  [10,55] is cited as outlook, not done).

## AutoTessell applicability — generator vs hierarchy verdict

**Blunt verdict: R3MG is a multigrid-hierarchy builder, not a mesh generator.
It never produces cells an FV solver would consume directly.** The paper's own
title and usage are honest about this ("applications to multilevel methods").
The output "polytopal mesh" is a labeling of fine cells plus a tree — the
geometry that OpenFOAM would need (merged planar owner-neighbor faces, cell
centers/volumes with bounded non-orthogonality and skewness) is never
constructed, never measured, and never claimed. Every accuracy result relies
on a bounding-box DG basis and fine-mesh quadrature, i.e. a discretization
built specifically so that agglomerate shape quality is almost irrelevant.
This is the exact DG-vs-FV admissibility gap already identified in
`gap_search_3d_agglomeration.md`: R3MG adds a fifth data point to the pattern
that all strong 3D agglomeration evidence lives in DG/VEM land.

What survives for AutoTessell's demoted route-2 agglomeration leg:

- **As a grouping oracle, R-tree beats METIS on our actual selection
  criteria:** near-free cost (level-independent, orders faster than METIS),
  deterministic given a fixed cell ordering (no seeded randomness), balanced
  cardinality by construction, geometry-aware grouping that empirically stays
  close to AABBs (BR ~0.85-1.0 vs METIS ~0.55-0.77), and exact structured-grid
  preservation. If the quality-gated agglomeration leg ever runs, the
  *candidate-set generator* should be an AABB R-tree walk, not a graph
  partitioner — with the caveat that face-connectivity of each group must be
  checked and repaired by us, since R3MG never guarantees it.
- **Nested hierarchy for free** is genuinely valuable if AutoTessell later
  needs coarsening for a multigrid-friendly export, LOD preview meshes in the
  GUI, or region-balanced parallel partitioning — none of which are on the
  critical path today.
- **Boundary preservation:** trivially exact in the union sense (boundary =
  fine boundary facets, so surface preservation, our #1 invariant, is
  untouched), but at the price of never simplifying the boundary; near curved
  boundaries the worst-shaped agglomerates concentrate (min-CR caveat).
- BR and OF are cheap, implementable shape proxies worth adding to the
  evaluator's polyhedral metric set, with the explicit caveat that they are
  DG-grade proxies, not validated FV predictors.

The decisive experiment remains `POLY-AGGLOM-CFD1` from the gap search: R3MG
provides zero evidence toward passing it, only a faster and more deterministic
way to *propose* groups that the FV gates must then judge.

## Falsifiable implementation card

One card is justified (candidate-generator substitution inside the already
quality-gated leg); no second card because the paper contributes no FV-side
evidence.

### `POLY-AGGLOM-RTREE1`

Implement an AABB R*-tree grouping pass (order M = 2^d, m = 2^{d-1}) over a
tet primal as the candidate-set generator for route 2's agglomeration leg,
replacing/benchmarking METIS-style graph partitioning. Each level-l node's
leaf set is a candidate agglomerate; face-connectivity of every candidate must
be verified and disconnected candidates split before acceptance. Pass only if,
on the standard fixtures: (a) grouping wall-clock is at least 10x below the
METIS baseline at equal element counts; (b) output is bit-identical across
repeated runs with a fixed canonical cell ordering; (c) mean Box Ratio of
accepted agglomerates is >= the METIS baseline; and (d) downstream FV gates
(the `POLY-AGGLOM-CFD1` thresholds) pass at a rate >= the METIS baseline.
Failing (d) demotes R-tree grouping to hierarchy/LOD use only, consistent
with this paper's hierarchy-builder verdict.

## Snowball references (verified against the paper's bibliography)

1. Beckmann, Kriegel, Schneider, Seeger 1990, *The R\*-tree: an efficient and
   robust access method for points and rectangles*, ACM SIGMOD — the actual
   grouping heuristics (area/overlap/perimeter minimization) that produce the
   box-like agglomerates; primary source for `POLY-AGGLOM-RTREE1`.
2. Cangiani, Dong, Georgoulis 2021, *hp-version discontinuous Galerkin methods
   on essentially arbitrarily-shaped elements*, Math. Comput. 91 (333), DOI
   `10.1090/mcom/3667` — the admissibility theory that lets R3MG ignore
   element shape; defines exactly what FV cannot ignore.
3. Antonietti, Houston, Pennesi 2018, *Fast numerical integration on polytopic
   meshes with applications to discontinuous Galerkin finite element methods*,
   J. Sci. Comput. 77, DOI `10.1007/s10915-018-0802-y` — quadrature-free
   integration; whether one can ever drop the retained fine sub-tessellation.
4. Antonietti, Houston, Pennesi, Süli 2020, *An agglomeration-based massively
   parallel non-overlapping additive Schwarz preconditioner for high-order DG
   methods on polytopic grids*, Math. Comput. 89 (325) — the parallel
   agglomerated-preconditioner lineage R3MG competes with.
5. Chan, Xu, Zikatanov 1998, *An agglomeration multigrid method for
   unstructured grids*, Contemp. Math. — the original agglomeration-multigrid
   root; historical anchor for the hierarchy-builder (not generator) reading.
