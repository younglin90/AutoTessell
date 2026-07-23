# Native Poly Gap Search — 3D Volume Agglomeration Evidence

Status: screening pass (candidate discovery), not FULL_READ. Purpose: close the
evidence hole identified in `evidence_matrix.md` — Sorgente et al. 2023's
agglomeration evidence (`POLY-AGGLOM-*` cards) is 2D polygonal DFN, while the
decided architecture's **route 2 (primal-dual/agglomeration)** needs 3D volume
primary evidence for its agglomeration leg.

## Scope statement

The gap: no paper in batch 1 or batch 2 demonstrates **3D polyhedral cells built
by agglomerating tetrahedra/simplices and then used as actual mesh elements**
with reported validity/quality outcomes. Gao et al. 2017 (batch 2) is the
closest but is hex-dominant and field-driven. This pass screened four themes:

1. 3D agglomeration of tet/simplicial primal meshes (graph-partition, ML/GNN,
   spatial-index, quality-driven) whose agglomerates are used as elements.
2. 3D polyhedral quality metrics beyond Sorgente 2022 and their solver
   correlation (finite-volume/CFD, OpenFOAM-style non-orthogonality/skewness).
3. Tet-primal → polyhedral dual constructions beyond Garimella 2013, including
   the industrial (Fluent/Star-CCM+-style) conversion literature.
4. Restricted/clipped 3D CVT optimization for route 1 quality.

Every DOI below was resolved through Crossref or the arXiv record before being
recorded. Papers with no legal open full text located are marked
`ABSTRACT_ONLY` and queued for user download.

Saturation: the final two search rounds (solver-side agglomeration probe
covering AgglomeraTe/MGLET-adjacent work; patent verification) surfaced no
algorithm family beyond those already tabled — graph-partition (METIS), ML/GNN,
R-tree/octree spatial indexing, quality-driven merging, and node-dual
agglomeration. Stop condition met.

## Theme 1 — 3D agglomeration from a tet/simplicial primal

| Priority | Screen | Candidate | DOI | Access | Relevance |
| --- | --- | --- | --- | --- | --- |
| P0 | INCLUDE | Bassi, Botti, Colombo, Di Pietro, Tesini 2012, *On the flexibility of agglomeration based physical space discontinuous Galerkin discretizations*, J. Comput. Phys. | `10.1016/j.jcp.2011.08.018` | ABSTRACT_ONLY (Elsevier; no legal OA found) | The foundational paper using arbitrarily-shaped 3D agglomerated elements as actual solution elements (Euler/Navier-Stokes). Defines what an agglomerate must satisfy to be an element at all. |
| P0 | INCLUDE | Dargaville, Buchan, Smedley-Stevenson, Smith, Pain 2021, *A comparison of element agglomeration algorithms for unstructured geometric multigrid*, J. Comput. Appl. Math. | `10.1016/j.cam.2020.113379` | OPEN (arXiv:2005.09104) | Head-to-head of 7 agglomeration algorithms on 3D tet meshes (AMGe-style + METIS). In 3D, METIS aggressive agglomeration wins on runtime and agglomerate-size fidelity. Direct algorithm-selection evidence for route 2's agglomeration leg. |
| P0 | INCLUDE | Sukumar, Tupek 2022, *Virtual elements on agglomerated finite elements to increase the critical time step in elastodynamic simulations*, Int. J. Numer. Methods Eng. | `10.1002/nme.7052` | OPEN (arXiv:2110.00514) | Agglomerates badly-shaped 3D tets/prisms into polyhedral VEM elements used directly in analysis; shows quality-insensitivity after agglomeration. Primary 3D evidence that agglomeration is a *bad-cell repair* operator, not only coarsening. |
| P0 | INCLUDE | Antonietti, Corti, Martinelli 2026, *Polytopal mesh agglomeration via geometrical deep learning for three-dimensional heterogeneous domains*, Math. Comput. Simul. | `10.1016/j.matcom.2025.10.019` | OPEN (arXiv:2406.10587) | The 3D upgrade of the GNN agglomeration line: quality-metric-driven GNN bisection vs k-means vs METIS on real 3D geometries (medical imaging), agglomerates consumed by a PolyDG solver. Directly fills the 2D→3D hole left by Sorgente 2023. |
| P1 | INCLUDE | Antonietti et al. 2025, *MAGNET: an open-source library for mesh agglomeration by graph neural networks*, Eng. Comput. | `10.1007/s00366-025-02223-y` | ABSTRACT_ONLY (OA status unverified; publisher page https://link.springer.com/article/10.1007/s00366-025-02223-y) | Open-source 2D/3D agglomeration reference implementation (GNN + classical baselines). Reference-only per native-first policy, but its quality metrics and test harness are reusable as ground truth. |
| P1 | INCLUDE | Feder et al. 2025, *R3MG: R-tree based agglomeration of polytopal grids with applications to multilevel methods*, J. Comput. Phys. | `10.1016/j.jcp.2025.113773` | ABSTRACT_ONLY (Elsevier; authors unverified — Crossref returns title/journal only) | Dimension-independent, fully automated R-tree agglomeration producing nested polytopal hierarchies. A non-ML, non-METIS algorithm family (spatial indexing) worth benchmarking for determinism. |
| P2 | CONTEXT | Botti, Colombo, Bassi 2017, *h-multigrid agglomeration based solution strategies for discontinuous Galerkin discretizations of incompressible flow problems*, J. Comput. Phys. | `10.1016/j.jcp.2017.07.002` | OPEN (arXiv:1703.03592) | Recursive agglomeration hierarchies on 3D unstructured grids; agglomerates are solver-level, evidence for gradation/nesting constraints rather than mesh export. |
| P2 | CONTEXT | Pan, Persson 2022, *Agglomeration-based geometric multigrid solvers for compact discontinuous Galerkin discretizations on unstructured meshes*, J. Comput. Phys. | `10.1016/j.jcp.2021.110775` | ABSTRACT_ONLY (author preprint likely on persson.berkeley.edu, unverified) | Aspect-ratio-aware agglomerate selection on 3D unstructured meshes; secondary evidence for agglomerate shape objectives. |
| P2 | CONTEXT | Antonietti, Farenga, Fraccaroli, Manuzzi 2024, *Agglomeration of polygonal grids using graph neural networks with applications to multigrid solvers*, Comput. Math. Appl. | `10.1016/j.camwa.2023.11.015` | OPEN (arXiv:2210.17457) | 2D methodology paper for the GNN line (quality-aware bisection recursion). Read only as background for the 3D paper above. |
| P2 | CONTEXT | Cremonesi et al. 2025, *Particle Virtual Element Method (PVEM): an agglomeration technique for mesh optimization in explicit Lagrangian free-surface fluid modelling*, Comput. Methods Appl. Mech. Eng. | `10.1016/j.cma.2024.117461` | ABSTRACT_ONLY (Elsevier; authors unverified from Crossref record) | Agglomeration as an online mesh-optimization operator inside a running solver. Dimensionality of the demonstrations unverified at screen time — check before citing as 3D evidence. |
| P2 | CONTEXT | Antonietti, Manuzzi 2022, *Machine learning based refinement strategies for polyhedral grids with applications to virtual element and polyhedral discontinuous Galerkin methods*, J. Comput. Phys. | `10.1016/j.jcp.2022.111531` | ABSTRACT_ONLY (Elsevier) | Refinement (inverse of agglomeration) with the same quality-preservation framing; useful for a future adaptive loop, not for the current gap. |

## Theme 2 — 3D polyhedral quality metrics and FV-solver correlation

| Priority | Screen | Candidate | DOI | Access | Relevance |
| --- | --- | --- | --- | --- | --- |
| P0 | INCLUDE | Juretić, Gosman 2010, *Error Analysis of the Finite-Volume Method with Respect to Mesh Type*, Numer. Heat Transfer B | `10.1080/10407791003685155` | ABSTRACT_ONLY (Taylor & Francis) | The closest thing to a primary "poly cells vs hex vs tet accuracy" FV study; directly supports (or bounds) the claim that good polyhedral meshes approach hex accuracy. Anchors the `POLY-QUALITY-CORRELATE1` weights for OpenFOAM-style solvers. |
| P1 | INCLUDE | Katz, Sankaran 2011, *Mesh quality effects on the accuracy of CFD solutions on unstructured meshes*, J. Comput. Phys. | `10.1016/j.jcp.2011.06.023` | ABSTRACT_ONLY (Elsevier; AIAA conference version `10.2514/6.2011-652` also paywalled) | Systematic truncation/discretization-error vs mesh-distortion study for node/cell-centered FV schemes. Solver-correlation evidence for which geometric metrics actually predict error. |
| P1 | INCLUDE | Jasak 1996, *Error Analysis and Estimation for the Finite Volume Method with Applications to Fluid Flows*, PhD thesis, Imperial College London | no DOI (thesis) | OPEN (Imperial College Spiral repository / widely mirrored) | Defines the non-orthogonality and skewness error decomposition OpenFOAM's `checkMesh` thresholds descend from. Primary source for the metric definitions the engine must gate on. |
| P2 | INCLUDE | *Convergence analysis of a cell centered finite volume diffusion operator on non-orthogonal polyhedral meshes* | arXiv:1806.09180 (journal DOI unverified) | OPEN (arXiv) | Proves convergence behavior of a cell-centered diffusion operator on non-orthogonal polyhedral cells — theoretical backing for how much non-orthogonality an FV scheme tolerates. |
| — | CONTEXT | Sorgente, Biasotti, Manzini, Spagnuolo 2023 survey (`10.1111/cgf.14779`) | already FULL_READ in batch 2 | OPEN | Retained as the metric-taxonomy anchor; this theme adds the missing *FV/CFD correlation* layer on top of it. |

## Theme 3 — tet-primal → polyhedral dual beyond Garimella 2013

| Priority | Screen | Candidate | DOI | Access | Relevance |
| --- | --- | --- | --- | --- | --- |
| P0 | INCLUDE | Lee, Sang Yong 2015, *Polyhedral Mesh Generation and A Treatise on Concave Geometrical Edges*, Procedia Eng. (IMR 24) | `10.1016/j.proeng.2015.10.131` | OPEN (Procedia is open access on ScienceDirect) | Industrial-style tet-dual polyhedral generation with explicit treatment of the concave-boundary-edge failure mode — exactly the failure Garimella 2013 flags as requiring topology changes. Directly upgrades `POLY-DUAL-*` cards. |
| P1 | INCLUDE | Oaks, Paoletti 2000, *Polyhedral Mesh Generation*, Proc. 9th International Meshing Roundtable | no DOI (IMR proceedings) | OPEN (IMR proceedings archive; mirrored copies) | The original tet-dual polyhedral mesher paper behind the AVL FIRE lineage; defines the baseline node-dual construction commercial tools descend from. |
| P2 | INCLUDE | Menon, Gessner (Ansys Inc.) 2021, US Patent 11,170,573 B2 *Adaptive polyhedra mesh refinement and coarsening* (companion US 10,803,661 B2) | patent, no DOI | OPEN (USPTO / Google Patents) | Verified algorithmic detail of Fluent-side polyhedral refinement and its reverse agglomeration (child-face/cell agglomeration, node-usage-count-driven node removal). Reference-only, but it is the only public algorithm-level record of the Fluent coarsening path. |
| — | CONTEXT | ANSYS Fluent User's Guide §6.7.1 *Converting the Domain to a Polyhedra* | grey literature | OPEN (mirrored) | Documents the production tet→poly conversion: per-cell decomposition into node-associated "duals" then agglomeration around original nodes. Not primary research; scopes what the industry-standard dual actually is. |
| P2 | CONTEXT | *Smoothing and untangling for polyhedral mesh based on element shape transformation* 2024, Adv. Eng. Softw. | DOI unverified; publisher URL https://www.sciencedirect.com/science/article/abs/pii/S0965997824001947 | ABSTRACT_ONLY | Post-dualization polyhedral smoothing/untangling; complements the Kim 2014 untangling pair already in batch 2. |

## Theme 4 — restricted/clipped 3D CVT for route 1

| Priority | Screen | Candidate | DOI | Access | Relevance |
| --- | --- | --- | --- | --- | --- |
| P1 | INCLUDE | Lévy, Liu 2010, *Lp Centroidal Voronoi Tessellation and its applications*, ACM SIGGRAPH 2010 | `10.1145/1833349.1778856` | OPEN (author page, inria/alice) | Generalizes CVT energy (anisotropy, Lp norms) with practical 3D clipped-cell optimization. The principled replacement for the fake Lloyd loop flagged in the batch-1 code audit (`voronoi.py:1017-1149`). |
| P2 | INCLUDE | Cantin Charawi, Gruson, Wu, Desrosiers, Thomas 2026, *DCCVT: Differentiable Clipped Centroidal Voronoi Tessellation* | arXiv:2601.13603 (preprint, no journal DOI) | OPEN (arXiv) | Fully differentiable clipped 3D CVT; modern formulation of the domain-restricted centroid objective route 1 needs. Preprint — treat as method reference, not settled evidence. |
| P2 | INCLUDE | Du, Faber, Gunzburger 1999, *Centroidal Voronoi Tessellations: Applications and Algorithms*, SIAM Review | `10.1137/s0036144599352836` | ABSTRACT_ONLY (SIAM; author copies circulate, unverified) | The foundational CVT theory (energy, Lloyd convergence). Needed once to define what the "true restricted-cell CVT" contract in the architecture decision actually means. |
| — | CONTEXT | Du, Gunzburger, Ju 2003, *Constrained Centroidal Voronoi Tessellations for Surfaces*, SIAM J. Sci. Comput. | `10.1137/s1064827501391576` | ABSTRACT_ONLY | Surface-constrained CVT — relevant only if route 1 later pins boundary seeds to the surface manifold. |
| — | CONTEXT | Yan, Wang, Lévy, Liu 2013 (`10.1016/j.cad.2011.09.004`) | already FULL_READ in batch 2 | OPEN | Remains the clipped-Voronoi construction anchor; theme 4 adds the *optimization objective* on top of it. |

## Inaccessible DOI queue (user download requested)

| Title | Authors | Year | DOI |
| --- | --- | --- | --- |
| On the flexibility of agglomeration based physical space discontinuous Galerkin discretizations | Bassi, Botti, Colombo, Di Pietro, Tesini | 2012 | `10.1016/j.jcp.2011.08.018` |
| Error Analysis of the Finite-Volume Method with Respect to Mesh Type | Juretić, Gosman | 2010 | `10.1080/10407791003685155` |
| Mesh quality effects on the accuracy of CFD solutions on unstructured meshes | Katz, Sankaran | 2011 | `10.1016/j.jcp.2011.06.023` |
| R3MG: R-tree based agglomeration of polytopal grids with applications to multilevel methods | Feder et al. (authors unverified) | 2025 | `10.1016/j.jcp.2025.113773` |
| MAGNET: an open-source library for mesh agglomeration by graph neural networks | Antonietti et al. | 2025 | `10.1007/s00366-025-02223-y` |
| Agglomeration-based geometric multigrid solvers for compact discontinuous Galerkin discretizations on unstructured meshes | Pan, Persson | 2022 | `10.1016/j.jcp.2021.110775` |
| Machine learning based refinement strategies for polyhedral grids ... | Antonietti, Manuzzi | 2022 | `10.1016/j.jcp.2022.111531` |
| Particle Virtual Element Method (PVEM) ... | (authors unverified) | 2025 | `10.1016/j.cma.2024.117461` |
| Centroidal Voronoi Tessellations: Applications and Algorithms | Du, Faber, Gunzburger | 1999 | `10.1137/s0036144599352836` |

## Recommended full-read order

1. **Dargaville et al. 2021** (OPEN) — algorithm-selection evidence; decides whether route 2's agglomeration leg starts from METIS-style partitioning.
2. **Sukumar, Tupek 2022** (OPEN) — agglomeration as bad-tet repair with 3D validity outcomes; closest to route 2's actual use case.
3. **Antonietti, Corti, Martinelli 2026** (OPEN) — 3D quality-driven agglomeration state of the art; extracts the quality metrics used to steer merging.
4. **Lee 2015** (OPEN) — concave-edge treatment for the dual leg; pairs with the Garimella 2013 caution.
5. **Bassi et al. 2012** (queue) — element-admissibility requirements for agglomerates.
6. **Juretić, Gosman 2010** (queue) + **Katz, Sankaran 2011** (queue) + **Jasak 1996** (OPEN) — FV metric-correlation layer for the shared quality contract.
7. **Lévy, Liu 2010** (OPEN) — route 1 restricted-CVT objective.

## Verdict — does route 2's agglomeration leg survive?

**Yes, but demoted to a constrained, quality-gated secondary leg; dualization
remains the geometry-defining primary leg of route 2.** Reasoning:

- The 2D→3D hole **is closable**: at least four primary 3D sources (Bassi 2012;
  Dargaville 2021; Sukumar-Tupek 2022; Antonietti-Corti-Martinelli 2026) build
  3D polyhedral agglomerates from simplicial primals and use them as actual
  elements, with reported validity/quality outcomes. Agglomeration is not a
  2D-only technique.
- However, **all strong 3D evidence comes from DG/VEM discretizations**, whose
  element-admissibility requirements (polytopal, shape-regular in a weak sense)
  are far looser than OpenFOAM's FV contract (owner-neighbor faces, face
  planarity tolerance, non-orthogonality/skewness bounds, star-shaped safety).
  No screened primary paper demonstrates OpenFOAM-grade FV quality metrics on
  graph-agglomerated 3D cells. The only production FV lineage that ships
  agglomeration (Fluent coarsening patent US 11,170,573) applies it to cells it
  previously refined — i.e. it agglomerates its *own* children, not arbitrary
  tets.
- The industrial FV route (Oaks-Paoletti 2000; Fluent §6.7.1; Star-CCM+) defines
  polyhedral geometry by **node-dual construction**, then optimizes — supporting
  dualization as route 2's primary geometry generator.
- Concrete role for agglomeration, with direct primary backing: (a) bad-tet
  absorption before dualization or as post-dual repair (Sukumar-Tupek pattern),
  and (b) cell-budget reduction under the hard gates already defined in
  `evidence_matrix.md`, steered by quality metrics (Antonietti 2026 pattern,
  Sorgente 2023 energy generalized to the 3D Sorgente 2022 indicators). Both
  must run inside the transactional-edit framework from Gao et al. 2017.
- Gate to keep the leg: `POLY-AGGLOM-CFD1` (preregistered CFD benchmark) is now
  the *decisive* experiment — if agglomerated 3D cells cannot pass the FV
  metric thresholds that dual cells pass on the same fixtures, the leg drops to
  reference-only.
