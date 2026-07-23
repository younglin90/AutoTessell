# Native Hex forward-citation sweep (2026-07-23)

## Scope

Forward-citation sweep from the FULL_READ corpus (Maréchal 2009, Zhang et al. 2013, Nieser et al. 2011, Gao et al. 2017) and batch 2 (Ito 2009, HybridOctree_Hex 2024, Sokolov 2016, Ray 2016, HexEx, HexHex, Pietroni survey). Those papers are **not re-listed**. Four sweep axes, each tied to a current engine gap:

1. Modern octree / 2-refinement all-hex work → gap: **octree-template replacement** (current adaptive path emits generic polyhedral transitions, not proven all-hex).
2. Hex untangling / scaled-Jacobian optimization post-passes → gap: **post-snap boundary skew** (skew gate currently ≤3.0 on cylinder after wall-fit snap).
3. Dual sheet/pillowing operations → gap: **targeted quality repair** near boundary without global remesh.
4. Hex-dominant census honesty → gap: **truthful cell-type/hex-fraction reporting** (HEX-HD-1).

Vendored-code identification (verified via `git remote` in the repo):

- `Feature-Preserving-Octree-Hex-Meshing/` = `github.com/gaoxifeng/Feature-Preserving-Octree-Hex-Meshing` → implements **Gao, Shen, Panozzo (2019), "Feature Preserving Octree-Based Hexahedral Meshing", CGF 38(5), DOI `10.1111/cgf.13795`**.
- `HybridOctree_Hex/` is **not actually present** at the repo top level (contrary to earlier notes); its paper (Tong, Halilaj, Zhang 2024, DOI `10.1016/j.jocs.2024.102278`) was already FULL_READ in batch 2. Code lives at `github.com/CMU-CBML/HybridOctree_Hex` if vendoring is desired.
- `AlgoHex/` = Bommes-group frame-field/IGM pipeline (context for the deferred IGM path; HexHex batch-2 entry covers its extraction end).

DOI policy: "verified" = DOI observed on the publisher's own page (dl.acm.org / Springer / Wiley / ScienceDirect) or via a doi.org redirect to the publisher record. Unverifiable DOIs are marked and queued.

## 1. Octree / 2-refinement forward citations (gap: octree-template replacement, feature preservation)

| Priority | Candidate | DOI | Access | Screen | Relevance to engine gap |
|---|---|---|---|---|---|
| P0 | Gao, Shen, Panozzo (2019), "Feature Preserving Octree-Based Hexahedral Meshing", CGF 38(5) | `10.1111/cgf.13795` (verified, Wiley) | OPEN — author PDF <https://cims.nyu.edu/gcl/papers/2019-OctreeMeshing.pdf>; code vendored in-repo | INCLUDE | The paper behind our vendored reference code. Adds over Zhang 2013: explicit sharp-feature preservation, user-controlled max surface deviation, **all cells with positive scaled Jacobian and no self-intersections by construction**. Directly targets feature-preservation and validity-gate gaps; its feature-curve snapping is the strongest published answer to our ridge/corner provenance card (P1). |
| P0 | Pitzalis, Livesu, Cherchi, Gobbetti, Scateni (2021), "Generalized Adaptive Refinement for Grid-based Hexahedral Meshing", ACM TOG 40(6) | `10.1145/3478513.3480508` (verified, ACM) | OPEN — author PDF <https://www.gianmarcocherchi.com/pdf/gen_adapt_grid_hexmeshing.pdf>; code `github.com/cg3hci/Gen-Adapt-Ref-for-Hexmeshing` | INCLUDE | Direct modern successor to the Maréchal/Zhang transition problem: installs conforming all-hex templates on *weakly balanced* adaptive grids, relaxing the strong-balance requirement Zhang 2013 imposes. Fewer refinement propagations → smaller meshes for the same surface error. Primary candidate for our octree-template replacement. |
| P1 | Livesu, Pitzalis, Cherchi (2022), "Optimal Dual Schemes for Adaptive Grid Based Hexmeshing", ACM TOG 41(2) | `10.1145/3494456` (verified, ACM) | OPEN — arXiv <https://arxiv.org/abs/2103.07745> | INCLUDE | Enumerates **all** transitions a dual method must handle and proves which adaptive grids admit pure-hex conversion. This is the formal answer to our "all-hex transition honesty" falsification rule: it tells us exactly when the dual path can and cannot claim all-hex. Companion theory to the Pitzalis 2021 templates. |
| P1 | Tong, Zhang (2025), "Element-Saving Hexahedral 3-Refinement Templates" | arXiv `10.48550/arXiv.2512.14862` (preprint; no journal DOI yet) | OPEN — <https://arxiv.org/abs/2512.14862> | INCLUDE | Direct forward citation of Zhang 2013: new 3-refinement template family that reduces element count versus classic templates. If we port Zhang-style templates, this is the updated template set to compare cell-count growth against. Watch for journal version. |
| P1 | Tong, Zhang (2025), "MCHex: Marching Cubes Based Adaptive Hexahedral Mesh Generation with Guaranteed Positive Jacobian" | arXiv `10.48550/arXiv.2511.02064` (preprint; no journal DOI yet) | OPEN — <https://arxiv.org/abs/2511.02064> | INCLUDE | Same group as HybridOctree_Hex; claims **guaranteed positive Jacobian** from a marching-cubes-based adaptive construction. If the guarantee mechanism is template-level (not optimization-level), it is directly relevant to our adaptive generic-cell validity card (P0). |
| P2 | Qian, Zhang (2010), "Sharp Feature Preservation in Octree-Based Hexahedral Mesh Generation for CAD Assembly Models", IMR 19 | `10.1007/978-3-642-15414-0_15` (verified, Springer) | ABSTRACT_ONLY (Springer paywall) | CONTEXT | Two-step pillowing to eliminate triangle-shaped quads along sharp curves and doublets; assembly (non-manifold interface) conformity. Superseded for our purposes by Gao 2019, but its pillowing-at-features trick feeds section 3. |

## 2. Untangling / quality optimization post-passes (gap: post-snap boundary skew)

| Priority | Candidate | DOI | Access | Screen | Relevance to engine gap |
|---|---|---|---|---|---|
| P0 | Livesu, Sheffer, Vining, Tarini (2015), "Practical Hex-Mesh Optimization via Edge-Cone Rectification", ACM TOG 34(4) | `10.1145/2766905` (verified via doi.org redirect to ACM) | OPEN — project page + PDF <https://www.cs.ubc.ca/labs/imager/tr/2015/untangler/> | INCLUDE | The canonical hex untangling/optimization post-pass: reformulates positive-Jacobian enforcement as per-edge cone rectification, alternating local edge-cone fixes with global smoothing. Exactly the shape of stage we need after wall-fit snap to push boundary skew below the current ≤3.0 gate without moving surface vertices off their targets. |
| P0 | Tong, Zhang (2024/2026), "HexOpt" — arXiv title "Fast and Robust Hexahedral Mesh Optimization via Augmented Lagrangian, L-BFGS, and Line Search"; journal version "HexOpt: Efficient and robust hexahedral mesh optimization using rectified hybrid quadratic Jacobian and geometry-aware mapping", Computer-Aided Design 196:104073 (2026) | journal **DOI unverified** (`10.1016/j.cad.2025.104073` does not resolve; arXiv page lists no journal DOI). arXiv DOI `10.48550/arXiv.2410.11656` | OPEN — arXiv <https://arxiv.org/abs/2410.11656> | INCLUDE | Post-pass that maximizes a min mixed scaled-Jacobian/Jacobian energy **while constraining surface points to stay on the input triangle mesh** (augmented Lagrangian). This is precisely our post-snap situation: quality optimization subject to surface-preservation, our #1 product invariant. Modern replacement/companion to Edge-Cone Rectification. |
| P2 | Knupp (2001), "Hexahedral and Tetrahedral Mesh Untangling", Engineering with Computers 17:261-268 | `10.1007/s003660170006` (verified, Springer) | ABSTRACT_ONLY (Springer paywall) | CONTEXT | Classic untangling objective (optimize non-inversion directly rather than quality). Historical baseline; the two P0 papers subsume it algorithmically. |
| P2 | Garanzha, Kaporin, Kudryavtseva, Protais, Ray, Sokolov (2021), "Foldover-free maps in 50 lines of code", ACM TOG 40(4) | `10.1145/3450626.3459847` (verified, ACM) | OPEN — arXiv <https://arxiv.org/abs/2102.03069>, HAL hal-03127350 | CONTEXT | Regularized-barrier untangling with a tiny reference implementation. Formulated for simplicial maps, but the barrier construction transfers to hex corner-Jacobian samples; useful if we want a minimal in-house untangler before porting the heavier P0 machinery. |

## 3. Dual sheet / pillowing operations (gap: targeted boundary quality repair)

| Priority | Candidate | DOI | Access | Screen | Relevance to engine gap |
|---|---|---|---|---|---|
| P1 | Mitchell, Tautges (1995), "Pillowing doublets: refining a mesh to ensure that faces share at most one edge", IMR 4, pp. 231-240 | no DOI (proceedings; OSTI record 125090) | OPEN — <https://www.osti.gov/biblio/125090> | INCLUDE | The primary pillowing algorithm: shrink-set selection, separation, and insertion of a hex layer. Doublet removal is the exact repair our snapped boundary cells occasionally need (two boundary faces sharing two edges → unsmoothable skew). Small enough to port natively. |
| P1 | Ledoux, Shepherd (2010), "Topological modifications of hexahedral meshes via sheet operations: a theoretical study", Engineering with Computers 26(4):433-447 | `10.1007/s00366-009-0145-2` (verified, Springer) | ABSTRACT_ONLY (Springer paywall) | INCLUDE | Formal foundation for sheet insertion/extraction/collapse as the complete topology-editing algebra of conforming hex meshes. Needed to reason about which local repairs preserve the all-hex property — the theory behind any pillowing/sheet code we write. |
| P1 | Cherchi, Alliez, Scateni, Lyon, Bommes (2019), "Selective Padding for Polycube-Based Hexahedral Meshing", CGF 38(1):580-591 | `10.1111/cgf.13593` (verified, Wiley) | OPEN — HAL <https://inria.hal.science/hal-01970790>; author PDF <https://www.gianmarcocherchi.com/pdf/selective_padding.pdf> | INCLUDE | Padding (=pillowing) applied *selectively* where minimum scaled Jacobian is poor near the surface, instead of a global buffer layer. Cross-cuts sections 2 and 3: it is a targeted post-snap boundary-skew reducer that adds far fewer cells than Maréchal-style global buffers. |
| P2 | Borden, Benzley, Shepherd (2002), "Hexahedral Sheet Extraction", IMR 11, pp. 147-152 | no DOI (proceedings) | OPEN — CiteSeerX PDF <https://citeseerx.ist.psu.edu/document?doi=4aa72491ef5c8f82e5cb8c799eb7ec15aa30f9d1&repid=rep1&type=pdf> | INCLUDE | The extraction dual of pillowing: removing a sheet to coarsen or to delete a degenerate layer. Needed if a pillowing/snap iteration overshoots (cell count or sliver layer). |
| P2 | Gao, Martin, Deng, Cohen-Or, Panozzo et al. (2017), "Robust Structure Simplification for Hex Re-meshing", ACM TOG 36(6) | `10.1145/3130800.3130848` (verified, ACM) | OPEN — author copy via <https://gaoxifeng.github.io/> publications page | CONTEXT | Global sheet/chord collapse ranking to simplify base-complex structure. Beyond our near-term repair need, but defines the safety predicates (no doublet creation, feature preservation) a collapse must check — reusable for our targeted version. |

## 4. Hex-dominant honesty (gap: truthful cell census / hex-fraction reporting)

| Priority | Candidate | DOI | Access | Screen | Relevance to engine gap |
|---|---|---|---|---|---|
| P1 | Ray, Sokolov, Reberol, Ledoux, Lévy (2018), "Hex-dominant meshing: Mind the gap!", Computer-Aided Design 102:94-103 | `10.1016/j.cad.2018.04.012` (verified, ACM/Elsevier) | OPEN — HAL <https://inria.hal.science/hal-01927557> | INCLUDE | Generates hex-dominant meshes with **zero degenerate/flipped cells** and makes the non-hex remainder ("the gap") explicit and quantified. The reporting model our HEX-HD-1 truthful-census card should copy: hex fraction by count and volume, plus per-cell validity, never inferred from the engine name. |
| P1 | Pellerin, Johnen, Verhetsel, Remacle (2018), "Identifying combinations of tetrahedra into hexahedra: a vertex based strategy", Computer-Aided Design 105 | `10.1016/j.cad.2018.05.004` (verified, Elsevier PII S001044851830304X) | OPEN — arXiv <https://arxiv.org/abs/1705.02451>; code <https://www.hextreme.eu/> | INCLUDE | Complete enumeration of tet→hex/prism/pyramid combinations (shows prior recombiners used 10 of 174 valid subdivisions). Gives the exact combinatorial definition of "is this group of cells really a hex" — the correct basis for a cell-type census and for any future recombination mode. |
| P2 | Yamakawa, Shimada (2003), "Fully-automated hex-dominant mesh generation with directionality control via packing rectangular solid cells", IJNME 57(15) | `10.1002/nme.754` (verified, Wiley) | OPEN — author PDF <http://www.contrib.andrew.cmu.edu/~shimada/papers/02-ijnme-yamakawa.pdf> | CONTEXT | Early hex-dominant generator that already reported hex-dominance metrics; historical baseline for census expectations by geometry class. |
| P2 | Yamakawa, Shimada (2002), "HEXHOOP: Modular Templates for Converting a Hex-Dominant Mesh to an ALL-Hex Mesh", Engineering with Computers 18:211-228 | `10.1007/s003660200019` (verified, Springer) | ABSTRACT_ONLY (Springer paywall) | CONTEXT | Template family that converts prisms/pyramids in a hex-dominant mesh into hexes. Relevant to the all-hex transition honesty rule: an "all-hex after conversion" claim must cite a mechanism of this class, at the cost of subdivided (finer) cells. |
| P2 | Yu, Liu, Zhang (2022), "HexDom: Polycube-Based Hexahedral-Dominant Mesh Generation", in Mesh Generation and Adaptation, SEMA SIMAI vol. 30 | `10.1007/978-3-030-92540-6_7` (verified, Springer) | OPEN — arXiv <https://arxiv.org/abs/2103.04183>; code `github.com/CMU-CBML/HexDom` | CONTEXT | Zhang-group hex-dominant pipeline whose output explicitly mixes hex/prism/tet — an example of honest mixed-cell labeling in the same group whose all-hex work we port. |
| P2 | Chen, Zheng, Liao et al. (2026), "An approach to hex-dominant meshing with high-quality hexahedral element distribution", Engineering with Computers 42(2) | `10.1007/s00366-025-02241-w` (verified, Springer) | ABSTRACT_ONLY (Springer paywall) | CONTEXT | Most recent hex-dominant entry found; focuses on *where* the hexes end up (quality distribution), a refinement of the plain hex-ratio metric. Screen the abstract-level metrics into our census schema; full read only if the queue download succeeds. |
| P2 | Livesu, Pietroni, Puppo, Sheffer, Cignoni (2020), "LoopyCuts: Practical Feature-Preserving Block Decomposition for Strongly Hex-Dominant Meshing", ACM TOG 39(4) | `10.1145/3386569.3392472` (verified, ACM) | OPEN — arXiv/author copy via authors' pages | CONTEXT | "Strongly hex-dominant" block decomposition; useful as a taxonomy anchor for what fraction counts as "strongly" dominant, not as a near-term engine path. |

## Inaccessible DOI queue (for user download)

| Title | Authors | Year | DOI |
|---|---|---|---|
| Sharp Feature Preservation in Octree-Based Hexahedral Mesh Generation for CAD Assembly Models | Qian, Zhang | 2010 | `10.1007/978-3-642-15414-0_15` |
| Hexahedral and Tetrahedral Mesh Untangling | Knupp | 2001 | `10.1007/s003660170006` |
| Topological modifications of hexahedral meshes via sheet operations: a theoretical study | Ledoux, Shepherd | 2010 | `10.1007/s00366-009-0145-2` |
| HEXHOOP: Modular Templates for Converting a Hex-Dominant Mesh to an ALL-Hex Mesh | Yamakawa, Shimada | 2002 | `10.1007/s003660200019` |
| An approach to hex-dominant meshing with high-quality hexahedral element distribution | Chen, Zheng, Liao et al. | 2026 | `10.1007/s00366-025-02241-w` |
| HexOpt (journal version, CAD 196:104073) — arXiv copy is open, journal DOI unverified | Tong, Zhang | 2026 | DOI unverified — <https://www.sciencedirect.com/journal/computer-aided-design> |

## Recommended full-read order

1. **Gao, Shen, Panozzo 2019** (`10.1111/cgf.13795`) — vendored code in-repo; feature preservation + positive-SJ guarantee; unblocks the P1 ridge/corner provenance card.
2. **Pitzalis et al. 2021** (`10.1145/3478513.3480508`) — the template set to replace our polyhedral transitions; read together with its open code.
3. **Livesu et al. 2022 Optimal Dual Schemes** (`10.1145/3494456`) — decides when the dual path may claim all-hex (HEX-OCT-2 decision input).
4. **Livesu et al. 2015 Edge-Cone Rectification** (`10.1145/2766905`) — post-snap untangling/skew stage design.
5. **HexOpt** (arXiv 2410.11656) — surface-constrained scaled-Jacobian maximization; compare against #4 before implementing either.
6. **Ray et al. 2018 Mind the gap!** (`10.1016/j.cad.2018.04.012`) — census/reporting contract for HEX-HD-1.
7. **Pellerin et al. 2018** (`10.1016/j.cad.2018.05.004`) — combinatorial hex-identification for the census kernel.
8. **Cherchi et al. 2019 Selective Padding** (`10.1111/cgf.13593`) + **Mitchell/Tautges 1995** — targeted pillowing pair for boundary repair.
9. Ledoux/Shepherd 2010 (once downloaded) — sheet-operation theory backing item 8.
10. Element-Saving templates + MCHex (arXiv preprints) — monitor; read before finalizing template choice if journal versions land.

## Saturation verdict

**Saturated for this scope.** The sweep converged on four research families: (a) CMU Zhang group (HybridOctree_Hex, HexOpt, MCHex, Element-Saving, HexDom, Qian pillowing), (b) CNR-IMATI/Cagliari Livesu group (Generalized Adaptive Refinement, Optimal Dual Schemes, Edge-Cone, Selective Padding, LoopyCuts), (c) Inria/UCLouvain hextreme group (Mind the gap, Pellerin recombination, Sokolov/Ray — largely covered in batch 2), (d) Sandia sheet-operation lineage (Mitchell/Tautges, Borden, Ledoux/Shepherd). The final two searches (Mind-the-gap and HexDom follow-ups) returned only additional members of these same families plus already-covered batch-2 papers — no new family emerged, meeting the stop criterion. 22 candidates screened (7 beyond the covered corpus rated P0/P1 INCLUDE). Remaining known-uncovered territory is deliberate: IGM/frame-field generation depth (deferred per the architecture decision) and machine-learning polycube work (immature for production).
