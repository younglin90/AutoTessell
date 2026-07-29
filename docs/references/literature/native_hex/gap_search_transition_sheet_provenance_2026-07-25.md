# Native Hex gap search: transition-sheet repair and feature provenance

**Date:** 2026-07-25
**Scope:** documentation-only snowball search; no engine or gate changes.

## Scope and screening protocol

This search follows the labels used by `evidence_matrix.md` and
`forward_citation_sweep_2026-07-23.md`:

- **P0:** directly addresses octree transition/hanging-node quality or a
  surface/feature-constrained local repair lane.
- **P1:** plausible implementation input for transition, feature, or
  multi-region repair, but not a direct match to the current failure mode.
- **P2:** context, measurement, or a neighboring problem.
- **INCLUDE / CONTEXT / EXCLUDE:** whether the paper remains actionable for
  native_hex after the existing ECR/HexOpt and sheet-extraction falsifications.
- **OPEN / ABSTRACT_ONLY:** access status at screening time. A publisher DOI
  is recorded only when it was visible on the publisher record or a publisher
  DOI landing page; otherwise it is explicitly marked unverified.

The search used publisher records, author manuscripts, arXiv, PMC, and
institutional repositories. Existing FULL_READ papers are retained only as
context or as a bridge to a newly screened follow-up; they are not counted as
new evidence.

## Screening results

### A. Octree transitions, hanging nodes, and transition-cell quality

| Priority | Decision | Candidate | DOI / access | Why it matters |
|---|---|---|---|---|
| P0 | INCLUDE | Elsheikh et al. (2014), *A consistent octree hanging node elimination algorithm for hexahedral mesh generation* | `10.1016/j.advengsoft.2014.05.005` — publisher abstract, ABSTRACT_ONLY | Directly treats transition elements at fine/coarse octree interfaces. Its decoupling templates precondition concave refinement regions before applying refinement templates, explicitly targeting poor transition quality and excessive refinement. |
| P0 | INCLUDE | Chen, Yang, Sun (2026), *Edge-subdivision-based adaptive refinement for unstructured meshes with element quality control* | `10.1016/j.cja.2026.104154` — publisher OPEN | Enumerates hanging-node topologies, distinguishes allowable/forbidden transition subdivisions, and applies warpage/skew/aspect controls to transition elements. It is the closest new hit to a measurable transition-quality repair gate, although its input class is broader than octree dualization. |
| P1 | CONTEXT | Ito, Shih, Soni (2009), *Octree-based reasonable-quality hexahedral mesh generation using a new set of refinement templates* | `10.1002/nme.2470` — Wiley abstract / author PDF, existing corpus | Buffer layers, refinement templates, angle smoothing, and local untangling are useful baselines, but this is already in the completed corpus and does not isolate the current post-snap transition-sheet damage. |
| P1 | CONTEXT | Awad et al. (2016), *All-Hex Meshing of Multiple-Region Domains without Cleanup* | `10.1016/j.proeng.2016.11.055` — PMC/Elsevier OPEN, existing corpus | Strongly balanced octree plus geometry intersection avoids flat angles in multi-region domains. It is a construction-time alternative for bracket-like multi-patch cases, not a post-repair pass. |
| P1 | CONTEXT | Tong, Zhang (2024), *HybridOctree_Hex: Hybrid octree-based adaptive all-hexahedral mesh generation with Jacobian control* | `10.1016/j.jocs.2024.102278` — arXiv/publisher record, existing corpus | Uses transition templates plus smart Laplacian/optimization with a Jacobian floor. Relevant as a comparator, but already screened and does not supply a provenance-aware local repair for our scattered failures. |
| P2 | CONTEXT | Zhang, Bajaj (2006), *Adaptive and Quality Quadrilateral/Hexahedral Meshing from Volumetric Data* | `10.1016/j.cma.2005.02.016` — PMC/author manuscript OPEN, existing corpus | Feature-sensitive adaptive octree extraction followed by relaxation. Useful historical context for why transition quality and boundary projection must be measured separately. |
| P2 | EXCLUDE | Huo et al. (2020), *A smoothed finite element method for octree-based polyhedral meshes with large number of hanging nodes and irregular elements* | `10.1016/j.cma.2019.112646` — publisher abstract | Handles hanging nodes in a solver formulation rather than repairing conforming hex transition cells; no direct native_hex mechanism. |

### B. Feature, curve, corner, and surface-constrained local repair

| Priority | Decision | Candidate | DOI / access | Why it matters |
|---|---|---|---|---|
| P0 | INCLUDE | Tong, Zhang (2026), *HexOpt: Efficient and robust hexahedral mesh optimization using Rectified Hybrid Quadratic Jacobian and geometry-aware mapping* | `10.1016/j.cad.2026.104073` — ScienceDirect OPEN | Surface-constrained optimization explicitly keeps corner points at corners, edge points on edges, and face points on the input surface. The journal record resolves the DOI; this supersedes the earlier “DOI unverified” note for the 2024 arXiv entry. It is still generic optimization, so the next read must test whether its localized feature handling can explain the current transition failures. |
| P1 | INCLUDE | Zhang, Bajaj, Xu (2005), *Surface Smoothing and Quality Improvement of Quadrilateral/Hexahedral Meshes with Geometric Flow* | `10.1007/3-540-29090-7_27` — institutional PDF OPEN, DOI record | Tangential feature-preserving surface flow plus interior relocation. It offers a provenance-aware smoothing vocabulary, but normal motion conflicts with the project’s surface-preservation invariant and must not be ported without a wall-fit transaction. |
| P1 | INCLUDE | Wang et al. (2015), *Hexahedral mesh smoothing via local element regularization and global mesh optimization* | `10.1016/j.cad.2014.09.003` — publisher abstract | Local element regularization is stitched by a global sparse solve with explicit surface constraints. It may provide a low-cost local-to-global repair baseline, but it is not transition-sheet-specific. |
| P1 | INCLUDE | Zheng, Duan, Lei, Luo (2025), *Feature-aware Singularity Structure Optimization for Hex Mesh* | `10.1016/j.cad.2024.103825` — publisher abstract, ABSTRACT_ONLY | Sheet collapse/inflate operations align singularity structure to feature lines. This is a strong new candidate for bracket-like multi-patch damage where bad faces span several provenance patches, rather than a generic skew optimizer. |
| P1 | INCLUDE | Edge-angle optimization (2018), *Hexahedral mesh quality improvement via edge-angle optimization* | `10.1016/j.cag.2017.07.002` — publisher abstract, ABSTRACT_ONLY | Optimizes only local regions around inverted/poor cells and then smooths. Its published boundary deformation step conflicts with the hard wall-fit contract, so only the local objective and rejection logic are candidates. |
| P1 | INCLUDE | Shepherd, Tuttle, Silva, Zhang (2006), *Quality Improvement and Feature Capture in Hexahedral Meshes* | UUSCI-2006-029 — institutional PDF OPEN; no DOI found | Adds a boundary sheet of well-shaped hexes to give poor boundary cells extra degrees of freedom and inserts multiple sheets for sharp features. This is the most direct targeted-repair analogue to the current “bad cells near a constrained boundary” observation. |
| P2 | CONTEXT | Qian, Zhang (2010), *Sharp Feature Preservation in Octree-Based Hexahedral Mesh Generation for CAD Assembly Models* | `10.1007/978-3-642-15414-0_15` — ABSTRACT_ONLY / existing corpus | Feature extraction, two-step pillowing, and smoothing explicitly cover manifold and non-manifold assemblies. It is retained as the provenance baseline, not a new snowball hit. |
| P2 | EXCLUDE | Liu et al. (2015), *Recovery of Sharp Features in Mesh Models* | `10.1007/s40304-015-0059-9` — publisher abstract | Repairs sharp features in surface meshes with holes; no volume transition or hex-cell repair mechanism. |
| P2 | EXCLUDE | Si, Chen (2023), *A Visualization System for Hexahedral Mesh Quality Study* | arXiv:2308.12158 — OPEN | Useful for future diagnostics, but it is a visualization system rather than a repair method. |

### C. Adjacent topology and quality references

| Priority | Decision | Candidate | DOI / access | Why it matters |
|---|---|---|---|---|
| P1 | INCLUDE | Knupp (2003), *A method for hexahedral mesh shape optimization* | `10.1002/nme.768` — Wiley OPEN record | Condition-number objective with guaranteed untangled optimization. A baseline for a transactional local objective if the transition-specific papers do not yield a usable repair. |
| P2 | CONTEXT | Mitchell, Tautges (1995), *Pillowing doublets: refining a mesh to ensure that faces share at most one edge* | no DOI; OSTI OPEN | Safety predicate for sheet insertion and doublet removal. The operation is topological, not a direct quality fix, but it is relevant to the current multi-patch failure class. |
| P2 | CONTEXT | Ledoux, Shepherd (2010), *Topological modifications of hexahedral meshes via sheet operations: a theoretical study* | `10.1007/s00366-009-0145-2` — ABSTRACT_ONLY / existing queue | Completeness and safety vocabulary for sheet insertion/extraction/collapse; no direct quality evidence. |

**Screening count: 19 records.** New actionable candidates are the 2014
transition preconditioning paper, the 2026 transition-element quality-control
paper, the 2026 geometry-aware HexOpt journal record, the 2025
feature-aware sheet optimizer, and the 2006 boundary-sheet report. The rest
are context, existing FULL_READ bridges, or explicit exclusions.

## Inaccessible DOI / download queue

These are the records that need a user-supplied download before FULL_READ; no
claim is promoted from ABSTRACT_ONLY to evidence until the note exists.

| Candidate | DOI / URL | Needed decision |
|---|---|---|
| Elsheikh et al. 2014 | `10.1016/j.advengsoft.2014.05.005` | Does decoupling preconditioning produce a reusable transition-sheet quality gate, or only avoid template mismatch? |
| Zheng et al. 2025 | `10.1016/j.cad.2024.103825` | Can sheet inflate/collapse be restricted to bad transition components while preserving patch provenance? |
| Wang et al. 2015 | `10.1016/j.cad.2014.09.003` | Can local regularization be constrained to transition cells without moving wall-fit targets? |
| Edge-angle optimization 2018 | `10.1016/j.cag.2017.07.002` | Is the local region/rejection logic reusable when boundary movement is prohibited? |
| Qian, Zhang 2010 | `10.1007/978-3-642-15414-0_15` | Exact feature/pillowing invariants for multi-patch and non-manifold assemblies. |
| Ledoux, Shepherd 2010 | `10.1007/s00366-009-0145-2` | Sheet-operation safety predicates and deterministic traversal requirements. |
| Quality improvement method for graded hexahedral element meshes | DOI unverified; publisher record `S0167839610000531` | Verify bibliographic DOI before screening; likely secondary to Wang 2015. |
| Shepherd et al. 2006 | `UUSCI-2006-029` institutional PDF | Extract the boundary-sheet construction and its feature-capture guarantees. |

## Recommended FULL_READ order

1. **Elsheikh et al. 2014** — direct octree transition preconditioning and
   concavity handling.
2. **Chen et al. 2026** — explicit transition-element quality metrics and
   allowable/forbidden hanging-node topologies.
3. **Shepherd et al. 2006** — boundary-sheet repair with feature capture.
4. **Zheng et al. 2025** — feature-aware sheet collapse/inflate for
   multi-patch damage.
5. **HexOpt 2026** — surface-constrained local/global optimization; compare
   its feature treatment against the project’s wall-fit invariant.
6. **Wang et al. 2015** — local regularization plus constrained global solve.
7. **Edge-angle optimization 2018** — local region selection and rejection
   logic only; boundary deformation is out of scope.
8. **Awad et al. 2016** — multi-region construction-time alternative if
   post-snap repair remains structurally impossible.

## Saturation decision

**Saturated for this snowball scope after two consecutive search rounds with
no new mechanism family.** The first rounds added (1) transition
preconditioning/template conditioning, (2) explicit hanging-node transition
quality control, and (3) feature-aware sheet inflation/collapse. The final
round returned only variants of the same four families: constrained
optimization, local smoothing, sheet operations, and octree templates.

The remaining uncertainty is not “find another generic untangler.” It is which
of the three new mechanisms survives the project’s hard invariants:

1. transition-topology preconditioning before snap,
2. a local transition-element validity/quality transaction,
3. provenance-constrained sheet insertion/inflation for multi-patch damage.

No code card should open until the first two P0 papers and the boundary-sheet
report are FULL_READ and compared against the existing four-shape falsification
matrix.

## Source URLs checked

- https://www.sciencedirect.com/science/article/pii/S0965997814000817
- https://www.sciencedirect.com/science/article/pii/S1000936126000919
- https://www.sciencedirect.com/science/article/pii/S0010448526000436
- https://www.sciencedirect.com/science/article/pii/S009784931730095X
- https://www.sciencedirect.com/science/article/pii/S0010448514002036
- https://www.sciencedirect.com/science/article/pii/S1877750324000711
- https://pmc.ncbi.nlm.nih.gov/articles/PMC2740490/
- https://pmc.ncbi.nlm.nih.gov/articles/PMC5568131/
- https://www.sci.utah.edu/publications/SCITechReports/UUSCI-2006-029.pdf
- https://www.cs.utexas.edu/~bajaj/cvc/papers/2004/conference/zhang.pdf
- https://arxiv.org/abs/2410.11656
- https://arxiv.org/abs/2308.12158
