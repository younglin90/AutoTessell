# Native-Tri Citation Snowball: Batch 2

Date screened: 2026-07-23  
Scope: backward and forward citation sets of the six P0 global methods from
batch 1 (Alliez et al. 2005, Yan et al. 2009, Yan et al. 2014 LRVD,
Hu et al. 2016/2017, Wang et al. 2018/2019, Mahmoud et al. 2025), plus targeted
searches for the four topics batch 1 flagged as underrepresented: robust exact
self-intersection/fold-over predicates, constrained feature-graph updates,
deterministic parallel commit schemes, and CFD patch/provenance preservation.

This is a discovery and access-screening artifact, not a reading log. No entry
below is assigned `FULL_READ`. Every DOI below was verified against Crossref,
Semantic Scholar, doi.org, arXiv, or the publisher/author record during this
screen; where a DOI could not be verified the entry says so explicitly and a
publisher URL is given instead. Batch-1 papers are not re-listed.

## Screening method and labels

- `P0`: foundational or directly actionable for the first native-tri cards.
- `P1`: important alternative or extension to compare before fixing the design.
- `P2`: useful specialist evidence; read after the core families.
- `INCLUDE`: primary research within the native triangular surface-remeshing
  scope.
- `CONTEXT`: primary research with a narrower input/application contract.
- `EXCLUDE`: secondary work or a neighboring problem; retained only to explain
  the snowball boundary.
- `OPEN`: a legal author, institutional, or publisher full text was located.
- `ABSTRACT_ONLY`: bibliographic record/abstract is accessible, but this screen
  did not locate a legal open full text. These are the DOI-bearing inaccessible
  candidates to add to the central inaccessible-paper ledger after deduplication.

## Metadata normalization found during screening

1. Loseille and Menier's cavity-primitive paper is chapter `_30`, not `_31`, of
   the IMR 22 proceedings volume: `10.1007/978-3-319-02335-9_30` (presented
   2013, volume printed 2014).
2. Cheng et al. (2019) is `10.1016/j.cag.2019.05.019`; nearby values ending in
   `.014` circulate in some listings and do not match the Crossref record.
3. `10.1145/1778765.1778856` (Lp CVT) and `10.1145/3450626.3459748` (RXMesh)
   are not indexed by the Semantic Scholar DOI endpoint but resolve correctly
   through doi.org and Crossref; both were title-verified via Crossref.
4. Marchandise et al., "Optimal parametrizations for surface remeshing," was
   published online in 2012 and in print in Engineering with Computers 2014;
   the DOI `10.1007/s00366-012-0309-3` covers both.

## A. Forward extensions of the error-bounded and angle-tail operator family

Forward citations of Hu et al. 2016/2017 and Wang et al. 2018/2019.

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P1 | X.-X. Cheng, X.-M. Fu, C. Zhang, S. Chai (2019), **Practical Error-Bounded Remeshing by Adaptive Refinement** | `10.1016/j.cag.2019.05.019` | Crossref/publisher record only — ABSTRACT_ONLY | Direct forward extension of Hu's error-bounded contract: alternates edge-based remeshing with an adaptively adjusted edge-length field, arguing refinement density usually satisfies the error bound at much lower cost than per-operation Hausdorff checks. Key cost/benefit comparison for `TRI-ERROR-GATE1`. **INCLUDE**. |
| P1 | W.-X. Zhang, Q. Wang, J.-P. Guo, S. Chai, L. Liu, X.-M. Fu (2022), **Constrained Remeshing Using Evolutionary Vertex Optimization** | `10.1111/cgf.14471` | Wiley record only — ABSTRACT_ONLY | Later constrained remeshing from the same group: evolutionary per-vertex optimization under hard constraints (error bound, feature preservation). Direct evidence for how hard constraints and quality objectives are separated in a modern pipeline. **INCLUDE**. |
| P1 | J. Liu, Y. Yao, Y. Fei, G. Zhang, L. Zheng (2024), **Surface Remeshing with Preservation of Sharp Features through Iterative Identification and Optimization of Sample Points** | `10.1016/j.cag.2024.103949` | Elsevier record only — ABSTRACT_ONLY | Dynamic identification of feature sample points during iterative optimization instead of a fixed pre-tagged feature graph. Directly relevant to the underrepresented constrained feature-graph-update topic: the feature set itself is updated as the mesh evolves. **INCLUDE**. |
| P2 | H. Zheng, C. Lv (2025), **Isotropic Remeshing with Inter-Angle Optimization** | `10.48550/arXiv.2507.13641` | [arXiv](https://arxiv.org/abs/2507.13641) — OPEN | Recent Wang-family variant: monitors angle transformations to predict how edge-length adjustments affect later optimization. Incremental evidence for angle-tail scheduling; no new validity contract. **INCLUDE**. |

## B. Robust exact predicates and intersection-safe local edits

The batch-1 gap on self-intersection/fold-over safety. Backward citations of
Hu 2016/2017 (envelope checks) and of the fTetWild/TetWild tool family already
vendored in this repository.

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P0 | J. R. Shewchuk (1997), **Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates** | `10.1007/PL00009321` | [Author page and PDF](https://www.cs.cmu.edu/~quake/robust.html) — OPEN | The root of every filtered exact predicate used by the CVT/RVD and envelope families. Any native fold-over/orientation guard should be built on these expansions or a descendant. **INCLUDE**. |
| P0 | T. Brochu, R. Bridson (2009), **Robust Topological Operations for Dynamic Explicit Surfaces** | `10.1137/080737617` | [Author PDF](https://www.cs.ubc.ca/~rbridson/docs/brochu-sisc2009-eltopo.pdf) — OPEN | El Topo: every local operation (refine, coarsen, smooth, topology change) is collision-tested before commit; unsafe non-critical operations are rolled back, critical ones get robust collision response. The clearest published precedent for AutoTessell's per-operation guarded-commit design. **INCLUDE**. |
| P0 | B. Wang, T. Schneider, Y. Hu, M. Attene, D. Panozzo (2020), **Exact and Efficient Polyhedral Envelope Containment Check** | `10.1145/3386569.3392426` | [NYU faculty digital archive](https://archive.nyu.edu/handle/2451/61221) — OPEN | Conservative, exact check that a candidate triangle stays inside a polyhedral envelope of the input; explicitly demonstrated inside two surface remeshing algorithms. The strongest published replacement for Hu's sampled Hausdorff gate and the direct upgrade path for `TRI-ERROR-GATE1`. Reference implementation `fast-envelope`; partial CGAL 5.3 port. **INCLUDE**. |
| P0 | M. Attene (2020), **Indirect Predicates for Geometric Constructions** | `10.1016/j.cad.2020.102856` | [arXiv](https://arxiv.org/abs/2105.09772) — OPEN | Exact predicates whose inputs are implicit intermediate constructions (e.g., an intersection point) rather than rounded explicit coordinates; the predicate layer beneath the fast-envelope check and modern robust remeshing. **INCLUDE**. |
| P1 | B. Lévy (2016), **Robustness and Efficiency of Geometric Programs: The Predicate Construction Kit (PCK)** | `10.1016/j.cad.2015.10.004` | [HAL record and PDF](https://inria.hal.science/hal-01225202) — OPEN | Generates filtered exact predicates from high-level specifications; used by geogram's RVD machinery (a batch-1 P0 dependency). Practical route if native-tri needs custom predicates beyond Shewchuk's four. **INCLUDE**. |
| P1 | B. Lévy (2024), **Exact Predicates, Exact Constructions and Combinatorics for Mesh CSG** | `10.48550/arXiv.2405.12949` | [arXiv](https://arxiv.org/abs/2405.12949) — OPEN | Recent synthesis of exact predicates plus exact constructions with careful combinatorics for mesh booleans; state of the art for the co-refinement side of intersection safety. **INCLUDE**. |
| P2 | Q. Zhou, E. Grinspun, D. Zorin, A. Jacobson (2016), **Mesh Arrangements for Solid Geometry** | `10.1145/2897824.2925901` | [Project page and PDF](https://www.cs.columbia.edu/cg/mesh-arrangements/) — OPEN | Exact resolution of all triangle-triangle intersections into a valid simplicial complex. A neighboring problem (booleans), but its winding-number and exact-arrangement machinery is the standard answer when a native pipeline must *repair* self-intersections rather than merely forbid them. **CONTEXT**. |
| P2 | G. Cherchi, M. Livesu, R. Scateni, M. Attene (2020), **Fast and Robust Mesh Arrangements using Floating-Point Arithmetic** | `10.1145/3414685.3417818` | [Author PDF](https://www.gianmarcocherchi.com/pdf/mesh_arrangement.pdf) — OPEN | Arrangement of intersecting triangles made practical with indirect predicates and floating-point filtering; the performance-oriented successor to Zhou et al. 2016. Same boundary note as above. **CONTEXT**. |

## C. CVT and RVD: backward foundations and forward accelerations

Backward and forward citations of Alliez et al. 2005, Yan et al. 2009, and
Yan et al. 2014 (LRVD).

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P1 | Q. Du, V. Faber, M. Gunzburger (1999), **Centroidal Voronoi Tessellations: Applications and Algorithms** | `10.1137/S0036144599352836` | [Author PDF](http://people.sc.fsu.edu/~mgunzburger/files_papers/gunzburger-cvt-siamreview.pdf) — OPEN | The theory paper behind every CVT route in batch 1: energy definition, Lloyd iteration, convergence discussion. Needed before implementing or auditing any CVT comparison engine. **INCLUDE**. |
| P0 | Y. Liu, W. Wang, B. Lévy, F. Sun, D.-M. Yan, L. Lu, C. Yang (2009), **On Centroidal Voronoi Tessellation — Energy Smoothness and Fast Computation** | `10.1145/1559755.1559758` | [HAL/Inria PDF](https://hal.inria.fr/inria-00547936/file/cvt_tog.pdf) — OPEN | Proves C^2 smoothness of the CVT energy, justifying the quasi-Newton (L-BFGS) optimization that Yan et al. 2009 relies on. The direct backward dependency of the batch-1 P0 exact-RVD paper. **INCLUDE**. |
| P1 | B. Lévy, Y. Liu (2010), **Lp Centroidal Voronoi Tessellation and its Applications** | `10.1145/1778765.1778856` | [Mirror PDF](https://www.cs.jhu.edu/~misha/ReadingSeminar/Papers/Levy10.pdf) — OPEN | Generalizes CVT to higher moments, aligning cells to a metric/feature cross-field without explicit feature tagging. Key comparison for soft versus hard feature handling in a global engine. **INCLUDE**. |
| P2 | G. Rong, Y. Liu, W. Wang, X. Yin, X. Gu, X. Guo (2011), **GPU-Assisted Computation of Centroidal Voronoi Tessellation** | `10.1109/TVCG.2010.53` | [HAL PDF](https://hal.inria.fr/inria-00602490/file/GPU-CVT.pdf) — OPEN | Early GPU CVT via parameter-space discretization. Superseded in exactness by later exact-RVD work but useful as a baseline for the GPU-acceleration question. **INCLUDE**. |
| P1 | N. Ray, D. Sokolov, S. Lefebvre, B. Lévy (2018), **Meshless Voronoi on the GPU** | `10.1145/3272127.3275092` | [HAL PDF](https://hal.inria.fr/hal-01927559/file/voroGPU.pdf) — OPEN | Computes Voronoi cells independently per seed on the GPU with security-radius certification. The modern forward path from Yan 2009's exact RVD toward parallel execution, and a bridge to the Mahmoud 2025 systems track. **INCLUDE**. |

## D. Delaunay-refinement and feature-graph contracts

The underrepresented constrained feature-graph topic: how sharp feature curves
and corners are represented and provably preserved.

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P1 | J.-D. Boissonnat, S. Oudot (2005), **Provably Good Sampling and Meshing of Surfaces** | `10.1016/j.gmod.2005.01.004` | [Author PDF](http://geometrica.saclay.inria.fr/team/Steve.Oudot/papers/bo-pgsms-05/bo-pgsms-05.pdf) — OPEN | Restricted-Delaunay refinement with topology (closed-ball) and geometry guarantees driven by local feature size. The theoretical guarantee vocabulary (epsilon-sample, topological ball property) the native checker should borrow for its contracts. **INCLUDE**. |
| P1 | S.-W. Cheng, T. K. Dey, E. A. Ramos (2010), **Delaunay Refinement for Piecewise Smooth Complexes** | `10.1007/s00454-008-9109-3` | [Author PDF (SODA version)](https://cse.hkust.edu.hk/~scheng/pub/soda2007a-psc.pdf) — OPEN | The formal model for meshing a surface *with* its sharp feature graph: piecewise smooth complexes, protecting balls around 1-dimensional features, and termination proofs. The strongest published contract for feature-graph preservation. **INCLUDE**. |
| P1 | C. Jamin, P. Alliez, M. Yvinec, J.-D. Boissonnat (2015), **CGALmesh: A Generic Framework for Delaunay Mesh Generation** | `10.1145/2699463` | [HAL PDF](https://hal.inria.fr/hal-01071759/file/cgalmesh.pdf) — OPEN | Production embodiment of protecting-ball feature preservation and refinement oracles; documents the engineering compromises between theory and robustness. Reference design for a feature-graph API. **INCLUDE**. |
| P2 | M. Ma, X. Yu, N. Lei, H. Si, X. Gu (2017), **Guaranteed Quality Isotropic Surface Remeshing Based on Uniformization** | `10.1016/j.proeng.2017.09.811` | Procedia Engineering (IMR 26) is open access via the publisher DOI — OPEN | Discrete uniformization to a constant-curvature domain, then guaranteed-quality planar Delaunay refinement lifted back. A guarantee-flavored member of the global parameterization family; same high-genus fragility caveat as batch-1 global routes. **INCLUDE**. |

## E. Deterministic and parallel commit schemes for mesh edits

Backward citations of Mahmoud et al. 2025 plus the CFD cavity-operator line.

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P0 | A. Loseille, V. Menier (2014), **Serial and Parallel Mesh Modification Through a Unique Cavity-Based Primitive** | `10.1007/978-3-319-02335-9_30` | [HAL record and PDF](https://hal.inria.fr/hal-00935356) — OPEN | Collapses every operator (insert, collapse, swap, relocate) into one cavity remesh primitive with a single validity check, for both surface and volume. The unifying abstraction Mahmoud 2025 adopts on GPU; adopting it early would shrink AutoTessell's per-operator guard surface. **INCLUDE**. |
| P1 | A. Loseille, F. Alauzet, V. Menier (2017), **Unique Cavity-Based Operator and Hierarchical Domain Partitioning for Fast Parallel Generation of Anisotropic Meshes** | `10.1016/j.cad.2016.09.008` | [HAL record and PDF](https://hal.archives-ouvertes.fr/hal-01426152) — OPEN | The parallel completion of the cavity line: hierarchical partitioning, interface deferral, out-of-core arguments, billion-element CFD meshes. Primary evidence for partition-then-defer-interfaces as a deterministic-enough parallel commit scheme. **INCLUDE**. |
| P1 | A. Loseille, V. Menier, F. Alauzet (2015), **Parallel Generation of Large-size Adapted Meshes** | `10.1016/j.proeng.2015.10.122` | Procedia Engineering (IMR 24) is open access via the publisher DOI — OPEN | Earlier open account of the same parallel strategy with metric-based static load balancing. Useful for the scheduling details the CAD paper compresses. **INCLUDE**. |
| P1 | A. H. Mahmoud, S. D. Porumbescu, J. D. Owens (2021), **RXMesh: A GPU Mesh Data Structure** | `10.1145/3450626.3459748` | [UC eScholarship](https://escholarship.org/uc/item/8r5848vp) and [author PDF](https://ahdhn.github.io/files/RXMesh_SIGGRAPH2021.pdf) — OPEN | The static patch-based GPU data structure (patches plus ribbons in shared memory) that Mahmoud 2025 extends to dynamic updates. Required background before reading the batch-1 P0 systems paper. **INCLUDE**. |
| P0 | Z. Jiang, J. Dai, Y. Hu, Y. Zhou, J. Dumas, Q. Zhou, G. S. Bajwa, D. Zorin, D. Panozzo, T. Schneider (2022), **Declarative Specification for Unstructured Mesh Editing Algorithms** | `10.1145/3550454.3555513` | [Author-hosted PDF](https://web.uvic.ca/~teseo/profile/publications/toolkit/2022-WildMeshingToolkit.pdf) — OPEN | The wildmeshing-toolkit paper: mesh editing expressed as per-element invariants, operation scheduling, and attribute transfer, with automatic shared-memory parallelization that guarantees the invariants. This is the closest published blueprint for AutoTessell's guarded-transaction native-tri architecture, from the same lineage as the vendored TetWild code. **INCLUDE**. |
| P2 | C. Marot, J. Pellerin, J.-F. Remacle (2019), **One Machine, One Minute, Three Billion Tetrahedra** | `10.1002/nme.5987` | [arXiv](https://arxiv.org/abs/1805.08831) — OPEN | Extreme-scale parallel Delaunay with careful conflict management. Volume meshing, so a neighboring contract, but its lock-free scheduling evidence matters for the parallel roadmap. **CONTEXT**. |
| P2 | C. Tsolakis, N. Chrisochoides (2024), **Parallel Metric-Based Anisotropic Mesh Adaptation Using Speculative Execution on Shared Memory** (arXiv title: Parallel Adaptive Anisotropic Meshing on cc-NUMA Machines) | `10.48550/arXiv.2404.18030` | [arXiv](https://arxiv.org/abs/2404.18030) — OPEN | Speculative-execution adaptation with rollback on shared memory, validated on CFD benchmarks. A CPU counterpart to Mahmoud 2025's speculative GPU commits. **CONTEXT**. |
| P2 | D. Ibanez (2018), **Scalable Deterministic State-of-the-Art: The Omega_h Open-Source Adaptation Library** | No journal DOI located ("DOI unverified") | [OSTI record and PDF](https://www.osti.gov/biblio/1458399) — OPEN | Omega_h's explicit design goal: adaptation results independent of parallel partitioning and ordering, via read-only pass plus derived-copy updates. The only located artifact that states bitwise parallel determinism as a contract; software-report form, tet/tri volume focus. **CONTEXT**. |

## F. CFD surface adaptation, patch and provenance preservation

The underrepresented CFD patch/provenance topic: keeping boundary-patch
classification and attribute maps valid through remeshing.

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P0 | C. Dapogny, C. Dobrzynski, P. Frey (2014), **Three-Dimensional Adaptive Domain Remeshing, Implicit Domain Meshing, and Applications to Free and Moving Boundary Problems** | `10.1016/j.jcp.2014.01.005` | [HAL PDF](https://hal.sorbonne-universite.fr/hal-00804636/file/domrem2.pdf) — OPEN | The mmg/mmgs paper: local-operator surface plus volume remeshing with an explicit Hausdorff parameter and preserved boundary references, deployed in production CFD/level-set pipelines. The closest existing open-source analogue of AutoTessell's target contract and the primary engineering benchmark for the native-tri engine. **INCLUDE**. |
| P1 | P. J. Frey, F. Alauzet (2005), **Anisotropic Mesh Adaptation for CFD Computations** | `10.1016/j.cma.2004.11.025` | Elsevier record only — ABSTRACT_ONLY | The canonical metric-based CFD adaptation paper: error-estimate-driven metrics feeding local surface/volume operators. Defines the CFD-side requirements (metric intersection, gradation, boundary fidelity) a native surface remesher must serve. **INCLUDE**. |
| P0 | Z. Jiang, T. Schneider, D. Zorin, D. Panozzo (2020), **Bijective Projection in a Shell** | `10.1145/3414685.3417769` | [NYU GCL PDF](https://cims.nyu.edu/gcl/papers/2020-BijectivePrism.pdf) — OPEN | Prismatic shell with a bijective projection operator that transfers attributes between the input and any admissible remeshed surface inside the shell. The strongest published mechanism for exact patch/provenance preservation independent of the edit sequence. **INCLUDE**. |
| P1 | S. Liu, Y. Ji, et al. (2024), **Smooth Bijective Projection in a High-Order Shell** | `10.1145/3658207` | ACM record only — ABSTRACT_ONLY | Curved (Bezier) shell version with smooth bijective transfer; relevant if AutoTessell later carries curved-geometry attributes. **INCLUDE**. |
| P0 | L. Zhu, M. Tao, Y. Hu, D. Panozzo, D. Zorin (2026), **BijectiveRemesh: Maintaining Bijective Mappings for Data Transfer Across Remeshed Manifolds** | `10.48550/arXiv.2605.30744` | [arXiv](https://arxiv.org/abs/2605.30744) — OPEN | Maintains a continuous bijective map across sequences of splits, collapses, swaps, and smoothing by chaining per-operation local bijective atlases, on both triangle and tet meshes. This is exactly the per-operation provenance transaction AutoTessell's patch-preservation invariant needs; newest and most directly applicable provenance paper found. **INCLUDE**. |
| P1 | E. Marchandise, J.-F. Remacle, C. Geuzaine (2012/2014), **Optimal Parametrizations for Surface Remeshing** | `10.1007/s00366-012-0309-3` | [Gmsh preprint PDF](https://gmsh.info/doc/preprints/gmsh_stl3_preprint.pdf) — OPEN | Gmsh's production STL-to-CFD-surface route: partition into parameterizable charts, remesh in parameter space, preserve chart boundaries. Evidence for how an engineering mesher handles patch decomposition when no CAD topology survives. **INCLUDE**. |

## G. Deliberate exclusions and boundary cases

| Priority | Candidate | DOI | Access | Exclusion reason |
| --- | --- | --- | --- | --- |
| — | K. Hu, D.-M. Yan, B. Benes (2016), **Error-Bounded Surface Remeshing with Minimal Angle Elimination** (SIGGRAPH poster) | `10.1145/2945078.2945138` | ACM poster record | **EXCLUDE**: two-page poster of the batch-1 P0 TVCG paper; no additional evidence. |
| — | Pacific Graphics 2017 short paper, **Computing Restricted Voronoi Diagram on Graphics Hardware** | "DOI unverified" (Eurographics record blocked during this screen) | [Diglib bitstream PDF](https://diglib.eg.org/bitstream/handle/10.2312/pg20171320/023-026.pdf) | **EXCLUDE from primary evidence**: 4-page short paper superseded by Ray et al. 2018; author metadata could not be verified this screen. Revisit only if the Ray route is adopted. |
| — | J.-F. Remacle, C. Geuzaine, G. Compère, E. Marchandise (2010), **High-Quality Surface Remeshing Using Harmonic Maps** | `10.1002/nme.2824` | Publisher record; Gmsh preprints | **EXCLUDE from batch 2**: superseded for our purposes by Marchandise et al. 2012, which generalizes the parameterization choice. Candidate for batch 3 only if chart-based remeshing is pursued. |
| — | F. Alauzet, A. Loseille (2016), **A Decade of Progress on Anisotropic Mesh Adaptation for CFD** | `10.1016/j.cad.2015.09.005` (not re-verified this screen) | Publisher record | **EXCLUDE from primary evidence**: survey; use as a recall audit for the CFD-adaptation branch, like Khan et al. in batch 1. |
| — | CGAL 6.1 ACVD remeshing announcement (2025) | none | [CGAL blog](https://www.cgal.org/2025/05/22/Surface_remeshing/) | **EXCLUDE**: software release note; the underlying algorithm family (Valette's discrete clustering) is already screened in batch 1. |
| — | **Feature Sensitive Geometrically Faithful Highly Regular Direct Triangular Isotropic Surface Remeshing** (c. 2022) | "DOI unverified" | ResearchGate record only | **EXCLUDE from batch 2**: metadata could not be verified against any publisher or index record during this screen; re-attempt identification in batch 3 before screening. |
| — | K. Pingali et al. (2011), **The Tao of Parallelism in Algorithms**; G. Blelloch et al. (2012), **Internally Deterministic Parallel Algorithms Can Be Fast** | varies | publisher records | **EXCLUDE**: general parallel-programming evidence (Delaunay refinement appears only as a benchmark); the mesh-specific commit schemes in section E dominate them for our decisions. |

## Inaccessible DOI queue from this batch

Five screened candidates have no located legal open full text. Listed for user
download and addition to the central inaccessible-paper ledger:

1. X.-X. Cheng, X.-M. Fu, C. Zhang, S. Chai (2019), "Practical Error-Bounded
   Remeshing by Adaptive Refinement," Computers & Graphics 82.
   DOI: `10.1016/j.cag.2019.05.019`
2. W.-X. Zhang, Q. Wang, J.-P. Guo, S. Chai, L. Liu, X.-M. Fu (2022),
   "Constrained Remeshing Using Evolutionary Vertex Optimization," Computer
   Graphics Forum 41(2). DOI: `10.1111/cgf.14471`
3. J. Liu, Y. Yao, Y. Fei, G. Zhang, L. Zheng (2024), "Surface Remeshing with
   Preservation of Sharp Features through Iterative Identification and
   Optimization of Sample Points," Computers & Graphics.
   DOI: `10.1016/j.cag.2024.103949`
4. P. J. Frey, F. Alauzet (2005), "Anisotropic Mesh Adaptation for CFD
   Computations," Computer Methods in Applied Mechanics and Engineering 194.
   DOI: `10.1016/j.cma.2004.11.025`
5. S. Liu, Y. Ji, et al. (2024), "Smooth Bijective Projection in a High-Order
   Shell," ACM Transactions on Graphics. DOI: `10.1145/3658207`

## Recommended full-read order

1. Brochu and Bridson 2009, then Wang et al. 2020 (fast envelope), then
   Attene 2020: fix the per-operation safety stack — collision/rollback
   semantics, exact envelope gate, and the predicate layer beneath both.
2. Jiang et al. 2022 (wildmeshing toolkit) with Loseille and Menier 2014:
   choose the operation abstraction (invariant-checked scheduled operations
   versus a single cavity primitive) before writing more native-tri operators.
3. Jiang et al. 2020 (shell) and Zhu et al. 2026 (BijectiveRemesh): decide the
   patch/provenance mechanism — a static shell domain versus chained
   per-operation atlases — against the existing `TRI-SG-PROVENANCE1` candidate.
4. Dapogny et al. 2014, plus Frey and Alauzet 2005 when obtained: extract the
   CFD-facing contract (Hausdorff parameter, boundary references, metric
   inputs) the native engine must expose.
5. Cheng et al. 2019 and Zhang et al. 2022 when obtained, with Zheng and
   Lv 2025: compare cheap refinement-based error control against
   per-operation exact gates before fixing the error-gate cost budget.
6. Liu et al. 2009, Du et al. 1999, Lévy and Liu 2010, Ray et al. 2018: only
   if the batch-1 CVT/RVD comparison engine is green-lit; read in that order.
7. Boissonnat and Oudot 2005, Cheng, Dey, Ramos 2010, CGALmesh 2015: adopt the
   guarantee vocabulary and protecting-ball feature contract for the checker.
8. RXMesh 2021 before re-reading Mahmoud 2025; then Loseille et al. 2017 and
   Ibanez's Omega_h report when parallel commit design starts.

## Coverage assessment and next snowball

Batch 2 screened 35 candidates (31 primary INCLUDE/CONTEXT entries in
sections A-F plus boundary cases) and closed all four gaps batch 1 flagged:

- self-intersection/fold-over safety now has a full stack (Shewchuk, Attene,
  PCK, El Topo, fast envelope, arrangements);
- constrained feature-graph updates have both the theory contract (piecewise
  smooth complexes, protecting balls) and a dynamic-feature-set forward paper;
- deterministic parallel commit has the cavity line, wildmeshing-toolkit
  invariants, RXMesh, speculative CPU adaptation, and Omega_h's determinism
  contract;
- CFD patch/provenance preservation has mmg, the Gmsh route, the metric-based
  CFD contract, and the shell/BijectiveRemesh transfer mechanisms.

Saturation status: the final two probe searches (GPU dynamic remeshing;
2025-era isotropic remeshing with angle guarantees) returned only members of
already-screened families (Zheng and Lv 2025 is a Wang-family variant; Ma et
al. 2017 is a global-parameterization variant; everything else was already in
batch 1 or 2). By the batch-1 stopping rule — two consecutive searches adding
no new algorithm family — the *global method* snowball is saturated. One area
remains thin rather than empty: deterministic parallel commit evidence that is
specifically *surface* remeshing (most located work is volume/CFD or
GPU-systems). A batch 3 is optional and should be small: (a) identify the
unverified "Feature Sensitive Geometrically Faithful..." record, (b) run the
Khan et al. 2020 survey corpus as the planned recall audit, and (c) sweep
forward citations of Jiang et al. 2022 and Zhu et al. 2026 once per quarter,
since the transactional-remeshing family is still actively publishing.
