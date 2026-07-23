# Native-Tri Citation Snowball: Batch 1

Date screened: 2026-07-23  
Scope: backward references of Hu et al. (2016/2017), Botsch and
Kobbelt (2004), and Dunyach et al. (2013), plus selected later primary
research that materially extends those algorithm families.

This is a discovery and access-screening artifact, not a reading log. No entry
below is assigned `FULL_READ`. Technical descriptions were checked against
publisher, author, or institutional records; a full-text link only means that a
legal copy was located.

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

The primary venue records expose one DOI normalization and one definite
correction for values already present in `master_bibliography.csv`:

1. Botsch and Kobbelt (2004) has two resolving records for the same title:
   ACM `10.1145/1057432.1057457` and the Eurographics venue DOI
   `10.2312/SGP/SGP04/189-196`. This batch uses the Eurographics DOI because
   its open record hosts the paper; the ACM DOI in the master is not invalid.
2. Yan et al. (2009) is `10.1111/j.1467-8659.2009.01521.x`, not
   `10.1111/j.1467-8659.2009.01552.x`.

This file does not modify the master bibliography; the corrections should be
applied centrally after review.

## A. Local operators, adaptive sizing, and feature preservation

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P0 | H. Hoppe, T. DeRose, T. Duchamp, J. McDonald, W. Stuetzle (1993), **Mesh Optimization** | `10.1145/166117.166119` | [Author project and PDF](https://hhoppe.com/proj/meshopt/) — OPEN | Early joint optimization of connectivity, vertex positions, fidelity, and complexity. Direct conceptual ancestor of Hu's competing-objective formulation. **INCLUDE**. |
| P0 | J. Vorsatz, C. Roessl, L. Kobbelt, H.-P. Seidel (2001), **Feature Sensitive Remeshing** | `10.1111/1467-8659.00532` | [Author-hosted PDF](https://www.graphics.rwth-aachen.de/media/papers/resample1.pdf) — OPEN | Particle relaxation plus a hierarchical curvature field that attracts vertices to features without a fixed threshold. Important comparison for soft feature weights versus AutoTessell's hard semantic constraints. **INCLUDE**. |
| P0 | V. Surazhsky, C. Gotsman (2003), **Explicit Surface Remeshing** | `10.2312/SGP/SGP03/020-030` | [Eurographics record and PDF](https://diglib.eg.org/items/8f1dac05-aca1-4973-87e8-27a340397957) — OPEN | Local geometry/connectivity edits, area-based smoothing, dynamic local parameterization, and connectivity regularization. A direct predecessor of the Botsch/Dunyach loop. **INCLUDE**. |
| P0 | V. Surazhsky, P. Alliez, C. Gotsman (2003), **Isotropic Remeshing of Surfaces: A Local Parameterization Approach** | No DOI located; INRIA RR-4967 / IMR 2003 | [INRIA report copy](https://citeseerx.ist.psu.edu/document?doi=b8961083b1387f4bd4262d5034d00b395bea12df&repid=rep1&type=pdf) — OPEN | Arbitrary-genus local adaptation with patchwise parameterization and local CVT relaxation. Bridges local operators and global sampling. **INCLUDE**. |
| P0 | J. Vorsatz, C. Roessl, H.-P. Seidel (2003), **Dynamic Remeshing and Applications** | `10.1145/781606.781633` | [Publisher DOI](https://doi.org/10.1145/781606.781633) — ABSTRACT_ONLY; a later [open dissertation](https://diglib.eg.org/items/449faedf-d063-45cf-b98a-281c3acd635e) is not the same publication | Dynamic meshes, local topological operators, density-controlled particle placement, and feature skeletons. **INCLUDE**; obtain the paper rather than substituting the dissertation when recording a full read. |
| P0 | M. Botsch, L. Kobbelt (2004), **A Remeshing Approach to Multiresolution Modeling** | `10.2312/SGP/SGP04/189-196` | [Eurographics record and PDF](https://diglib.eg.org/items/eb9aa09f-d8f7-464a-bc41-4b5ea7b8136d) — OPEN | Canonical split/collapse/flip, tangential smoothing, and projection loop; the immediate implementation baseline. **INCLUDE**. |
| P0 | M. Dunyach, D. Vanderhaeghe, L. Barthe, M. Botsch (2013), **Adaptive Remeshing for Real-Time Mesh Deformation** | `10.2312/conf/EG2013/short/029-032` | [Eurographics record and PDF](https://diglib.eg.org/items/bd0987f0-b1d0-45cc-bde4-2a99ebf51946) — OPEN | Curvature-adaptive target lengths added to the local-operation loop with real-time constraints. Direct basis for `TRI-SIZING1`. **INCLUDE**. |
| P0 | K. Hu, D.-M. Yan, D. Bommes, P. Alliez, B. Benes (2016/2017), **Error-Bounded and Feature Preserving Surface Remeshing with Minimal Angle Improvement** | `10.1109/TVCG.2016.2632720` | [arXiv manuscript](https://arxiv.org/abs/1611.02147) — OPEN | Seed paper: ordered local operations, worst-angle queue, topology/fold-over checks, and sampled two-sided error gate. **INCLUDE**. |
| P0 | Y. Wang, D.-M. Yan, X. Liu, C. Tang, J. Guo, X. Zhang, P. Wonka (2018/2019), **Isotropic Surface Remeshing without Large and Small Angles** | `10.1109/TVCG.2018.2837115` | [KAUST record and postprint](https://repository.kaust.edu.sa/items/617eca35-4d22-4f07-9e38-ce5b878dec54) — OPEN | Later local-operator extension targeting both angle tails through insertion/removal, connectivity optimization, and tangential smoothing. Direct candidate for comparison with Hu's minimum-angle-only queue. **INCLUDE**. |
| P1 | S. Fuhrmann, J. Ackermann, T. Kalbe, M. Goesele (2010), **Direct Resampling for Isotropic Surface Remeshing** | `10.2312/PE/VMV/VMV10/009-016` | [Eurographics record and PDF](https://diglib.eg.org/items/5f95db9b-042f-409f-aaf8-413e192f5665) — OPEN | Exact vertex budget, direct 3D mutual tessellation, topology preservation, curvature density, and tagged features. Useful alternative initialization before local polishing. **INCLUDE**. |
| P1 | C. Lv, W. Lin, J. Zheng (2022/2024), **Adaptively Isotropic Remeshing Based on Curvature Smoothed Field** | `10.1109/TVCG.2022.3227970` | [Author manuscript](https://aliexken.github.io/papers/2022_Remeshing.pdf) — OPEN | Later adaptive-sizing work using a smoothed curvature field, preprocessing for distorted faces, and histogram-guided reconnection. The paper reports possible manifold breakage, making it particularly relevant to hard topology guards. **INCLUDE**. |
| P2 | J. Du, Y. Jin, R. Tong (2015), **As-Equilateral-as-Possible Surface Remeshing** | `10.1299/jamdsm.2015jamdsm0052` | [Publisher article and PDF](https://www.jstage.jst.go.jp/article/jamdsm/9/4/9_2015jamdsm0052/_article/-char/en) — OPEN | Connectivity regularization followed by local equilateral fitting and global stitching with feature constraints. Useful quality-optimization comparator, but less central than guarded incremental edits. **INCLUDE**. |

## B. Error, envelope, topology, and complexity contracts

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P0 | H. Borouchaki, P. J. Frey (2005), **Simplification of Surface Mesh Using Hausdorff Envelope** | `10.1016/j.cma.2004.11.016` | [Publisher record](https://www.sciencedirect.com/science/article/abs/pii/S0045782505000708) — ABSTRACT_ONLY | Explicit tolerance envelope and local cone constraints combined with collapse, flip, and relocation. Direct predecessor for a conservative geometry gate. **INCLUDE; inaccessible DOI candidate**. |
| P0 | M. Mandad, D. Cohen-Steiner, P. Alliez (2015), **Isotopic Approximation within a Tolerance Volume** | `10.1145/2766950` | [Publisher DOI](https://doi.org/10.1145/2766950) — ABSTRACT_ONLY | Stronger tolerance-volume, intersection-free, and topology-preserving contract than sampled Hausdorff checks. Essential for deciding whether an exact finalization gate is feasible. **INCLUDE; inaccessible DOI candidate**. |
| P1 | D. Cohen-Steiner, P. Alliez, M. Desbrun (2004), **Variational Shape Approximation** | `10.1145/1015706.1015817` | [Open INRIA technical report](https://citeseerx.ist.psu.edu/document?doi=6aabbe52a9ffa3bc669e06907b17c524ae761b60&repid=rep1&type=pdf) — OPEN | Discrete proxy-based clustering and normal-deviation error metric; relevant as a global approximation/anisotropy baseline, not as the first native-tri operator loop. **INCLUDE**. |
| P1 | P. Alliez, M. Meyer, M. Desbrun (2002), **Interactive Geometry Remeshing** | `10.1145/566654.566588` | [Author PDF](https://pages.saclay.inria.fr/mathieu.desbrun/pubs/AMD02.pdf) — OPEN | Parameter-space control maps, sampling, Delaunay triangulation, and optimization. Important global-resampling predecessor but requires charting. **INCLUDE**. |
| P2 | E. Diamanti et al. (2020), **Error-Bounded Compatible Remeshing** | `10.1145/3386569.3392434` | [Publisher record](https://doi.org/10.1145/3386569.3392434) — ABSTRACT_ONLY | Later error-bounded work for mutually compatible meshes. Valuable if AutoTessell later needs correspondence across surfaces; not required for a single-surface native engine. **CONTEXT; inaccessible DOI candidate**. |

## C. CVT, restricted Voronoi, and discrete Voronoi routes

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P0 | P. Alliez, E. Colin de Verdiere, O. Devillers, M. Isenburg (2003), **Isotropic Surface Remeshing** | `10.1109/SMI.2003.1199601` | [INRIA report version](https://citeseerx.ist.psu.edu/document?doi=b06969098ee7e06a1c600daed738fbe9e6dd05e1&repid=rep1&type=pdf) — OPEN | Density-controlled sampling, weighted CVT in conformal parameter space, and constrained Delaunay lifting. Foundational global-isotropic route. **INCLUDE**. |
| P0 | P. Alliez, E. Colin de Verdiere, O. Devillers, M. Isenburg (2005), **Centroidal Voronoi Diagrams for Isotropic Surface Remeshing** | `10.1016/j.gmod.2004.06.007` | [Publisher article](https://www.sciencedirect.com/science/article/pii/S1524070304000463) and [HAL author record](https://cv.hal.science/pierre-alliez) — OPEN author manuscript recorded | Expanded journal treatment of weighted CVT, feature-edge sampling, and filtered exact predicates for the planar constrained triangulation. **INCLUDE**. |
| P0 | D.-M. Yan, B. Levy, Y. Liu, F. Sun, W. Wang (2009), **Isotropic Remeshing with Fast and Exact Computation of Restricted Voronoi Diagram** | `10.1111/j.1467-8659.2009.01521.x` | [Eurographics record and PDF](https://diglib.eg.org/items/0194d89c-77db-4558-a66d-2a4fbbf57923) — OPEN | Exact, robust RVD intersections plus quasi-Newton CVT optimization; primary evidence for a global-regularity comparison engine. **INCLUDE**. |
| P0 | D.-M. Yan, G. Bao, X. Zhang, P. Wonka (2014), **Low-Resolution Remeshing Using the Localized Restricted Voronoi Diagram** | `10.1109/TVCG.2014.2330574` | [KAUST record](https://repository.kaust.edu.sa/items/3f101b5f-2ee4-4051-8275-f6e55a95a47c) and [institutional PDF](https://archive.ymsc.tsinghua.edu.cn/pacm_download/38/280-2014_TVCG_LRVD.pdf) — OPEN | Handles disconnected RVD patches when target triangles approach feature size or nearby sheets. High priority for coarse/cap-constrained meshes. **INCLUDE**. |
| P1 | S. Valette, J.-M. Chassery, R. Prost (2008), **Generic Remeshing of 3D Triangular Meshes with Metric-Dependent Discrete Voronoi Diagrams** | `10.1109/TVCG.2007.70430` | [Author publication page and PDF](https://www.creatis.insa-lyon.fr/~valette/public/publication/valette-tvcg-2008/) — OPEN | Discrete metric-driven Voronoi clustering with fixed vertex budget and isotropic/anisotropic modes. Strong cap-aware alternative to continuous RVD. **INCLUDE**. |
| P1 | D.-M. Yan, P. Wonka (2016), **Non-Obtuse Remeshing with Centroidal Voronoi Tessellation** | `10.1109/TVCG.2015.2505279` | [KAUST record and PDF](https://repository.kaust.edu.sa/items/b00dc74a-ca63-4bd2-b5f8-8e50a04c861b) — OPEN | Adds a short-Voronoi-edge penalty to CVT to address both small and obtuse angles. Useful benchmark against local worst-angle repair; reported limitations near sharp features must be inspected. **INCLUDE**. |

## D. Poisson-disk and blue-noise sampling

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P1 | D.-M. Yan, P. Wonka (2013), **Gap Processing for Adaptive Maximal Poisson-Disk Sampling** | `10.1145/2516971.2516973` | [arXiv](https://arxiv.org/abs/1211.3297) and [KAUST record](https://repository.kaust.edu.sa/items/e8315a2b-f62e-40b8-8285-550834457a9e) — OPEN | Geometric gap analysis, regular triangulations, and power diagrams for adaptive maximal sampling on surfaces. Strong candidate for coverage/maximality guarantees. **INCLUDE**. |
| P1 | D.-M. Yan, J. Guo, X. Jia, X. Zhang, P. Wonka (2014), **Blue-Noise Remeshing with Farthest Point Optimization** | `10.1111/cgf.12442` | [Institutional PDF](https://archive.ymsc.tsinghua.edu.cn/pacm_download/38/279-2014_CGF_FPO.pdf) — OPEN | Farthest-point optimization generalized to non-uniform surface sampling; useful for sampling quality and angle-distribution comparisons. **INCLUDE**. |
| P1 | J. Guo, D.-M. Yan, X. Jia, X. Zhang (2015), **Efficient Maximal Poisson-Disk Sampling and Remeshing on Surfaces** | `10.1016/j.cag.2014.09.015` | [Author PDF](https://jianweiguo.net/publications/papers/2014_C%26G_MPSMesh.pdf) — OPEN | Subdivided-mesh conflict/void tracking improves memory and handles thin sheets better than a global Euclidean grid. Relevant to close-gap corpus cases. **INCLUDE**. |
| P1 | A. G. M. Ahmed, J. Guo, D.-M. Yan, J.-Y. Franceschi, X. Zhang, O. Deussen (2017), **A Simple Push-Pull Algorithm for Blue-Noise Sampling** | `10.1109/TVCG.2016.2641963` | [Author/institutional page and PDF](https://graphics.uni-konstanz.de/publikationen/Ahmed2016SimplePushPull/index.html) — OPEN | Combines minimum separation, coverage, and Voronoi-capacity constraints; demonstrates non-obtuse remeshing. Useful sampling optimizer, not a substitute for topology/error guards. **INCLUDE**. |

## E. Anisotropic and dynamic metrics

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P0 | P. Alliez, D. Cohen-Steiner, O. Devillers, B. Levy, M. Desbrun (2003), **Anisotropic Polygonal Remeshing** | `10.1145/882262.882296` | [Author PDF](https://www.geometry.caltech.edu/pubs/ACDLD03.pdf) — OPEN | Curvature-tensor field and principal-direction sampling. It produces mixed polygons and therefore also crosses into quad-dominant work, but its metric construction is directly relevant. **INCLUDE**. |
| P0 | Z. Zhong, X. Guo, W. Wang, B. Levy, F. Sun, Y. Liu, W. Mao (2013), **Particle-Based Anisotropic Surface Meshing** | `10.1145/2461912.2461946` | [Author-manuscript mirror](https://citeseerx.ist.psu.edu/document?doi=3fe25837e7bbc626f5b29d6adc0f217f58db4018&repid=rep1&type=pdf) — OPEN | Riemannian metric mapped to a higher-dimensional isotropic embedding, particle energy optimization, and restricted anisotropic Voronoi dual. High-priority anisotropic reference. **INCLUDE**. |
| P1 | R. Narain, A. Samii, J. F. O'Brien (2012), **Adaptive Anisotropic Remeshing for Cloth Simulation** | `10.1145/2366145.2366171` | [UC repository](https://escholarship.org/uc/item/5s1775xd) — OPEN | Dynamic split/collapse/flip/relocation under curvature, velocity-gradient, and compression metrics. Valuable operator scheduling and anisotropic metric evidence, but cloth-specific validity/collision assumptions limit direct transfer. **CONTEXT**. |
| P2 | Z. Zhong, L. Shuai, M. Jin, X. Guo (2014), **Anisotropic Surface Meshing with Conformal Embedding** | `10.1016/j.gmod.2014.03.011` | [Publisher record](https://www.sciencedirect.com/science/article/abs/pii/S1524070314000186) — ABSTRACT_ONLY | Parameterization-based anisotropic alternative using conformal embedding and weighted CVT. **INCLUDE; inaccessible DOI candidate**. |

## F. Repair and input preconditions

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P0 | S. Bischoff, L. Kobbelt (2005), **Structure Preserving CAD Model Repair** | `10.1111/j.1467-8659.2005.00878.x` | [Author project and PDF](https://www.graphics.rwth-aachen.de/publication/0389/) — OPEN | Hybrid local volumetric repair for cracks/intersections while retaining unaffected tessellation and enforcing an error tolerance. Relevant to the repair/remesh boundary and patch preservation. **INCLUDE**. |
| P0 | M. Attene (2010), **A Lightweight Approach to Repairing Digitized Polygon Meshes** | `10.1007/s00371-010-0416-3` | [Author manuscript](https://citeseerx.ist.psu.edu/document?doi=461dae710ffa6205f684354a7927e2f74d7cc1bc&repid=rep1&type=pdf) — OPEN | Local conversion of defective polygon soups to manifold, watertight meshes without degenerate/intersecting elements. Defines what must be repaired before algorithms that assume a 2-manifold input. **INCLUDE**. |

## G. Parallel execution

| Priority | Candidate | DOI | Legal full text / access | Relevance and screening decision |
| --- | --- | --- | --- | --- |
| P1 | C. R. S. N. Almeida, P. C. G. Mayrink, R. C. Mesquita, D. A. Lowther (2011), **A Parallel Remeshing Method** | `10.1109/TMAG.2010.2090944` | [Publisher DOI](https://doi.org/10.1109/TMAG.2010.2090944) — ABSTRACT_ONLY | Domain partitioning with section interiors processed before interfaces. Relevant historical parallel baseline, but the four-page scope and weak reported shape guarantee make it secondary to guarded serial correctness. **CONTEXT; inaccessible DOI candidate**. |
| P0 | A. H. Mahmoud, S. D. Porumbescu, J. D. Owens (2025), **Dynamic Mesh Processing on the GPU** | `10.1145/3731162` | [UC repository and PDF](https://escholarship.org/uc/item/82k732k4) — OPEN | Patch-local shared-memory topology, speculative conflict handling, rollback, and a general cavity operator demonstrated on isotropic remeshing. The most direct later systems evidence for parallelizing guarded local edits after serial semantics stabilize. **INCLUDE**. |

## H. Deliberate exclusions and boundary cases

| Priority | Candidate | DOI | Access | Exclusion reason |
| --- | --- | --- | --- | --- |
| — | P. Alliez, G. Ucelli, C. Gotsman, M. Attene (2008), **Recent Advances in Remeshing of Surfaces** | `10.1007/978-3-540-33265-7_2` | Publisher chapter | **EXCLUDE from primary evidence**: valuable survey/chapter for further snowballing, but not primary research. |
| — | D. Khan et al. (2020/2022), **Surface Remeshing: A Systematic Literature Review of Methods and Research Directions** | `10.1109/TVCG.2020.3016645` | [Institutional manuscript](https://naist.repo.nii.ac.jp/record/4224/files/Surface%20Remeshing.pdf) — OPEN | **EXCLUDE from primary evidence**: use its 233-reference corpus to audit recall after primary-paper snowballing, not as algorithmic proof. |
| — | K. Crane, F. de Goes, M. Desbrun, P. Schroeder (2013), **Digital Geometry Processing with Discrete Exterior Calculus** and other textbooks/tutorials | varies | varies | **EXCLUDE**: instructional background, not a native-tri remeshing contribution. |
| — | Pure decimation, point-cloud reconstruction, and quad-only extraction papers | varies | varies | **EXCLUDE unless they contribute a reusable hard error/topology predicate or operator semantics**. They optimize a different output contract. |

## Inaccessible DOI queue from this batch

The following primary papers passed relevance screening but had no legal open
full text located in this pass:

1. Borouchaki and Frey (2005) — `10.1016/j.cma.2004.11.016`.
2. Mandad, Cohen-Steiner, and Alliez (2015) — `10.1145/2766950`.
3. Vorsatz, Roessl, and Seidel (2003) — `10.1145/781606.781633`.
4. Zhong, Shuai, Jin, and Guo (2014) — `10.1016/j.gmod.2014.03.011`.
5. Almeida et al. (2011) — `10.1109/TMAG.2010.2090944`.
6. Diamanti et al. (2020) — `10.1145/3386569.3392434` (context only).

## Recommended full-read order

1. Botsch and Kobbelt 2004, then Dunyach et al. 2013: establish the canonical
   serial operator loop and adaptive sizing details.
2. Surazhsky and Gotsman 2003, Hu et al. 2016/2017, and Wang et al. 2018/2019:
   compare operator ordering, topology guards, and both angle tails.
3. Borouchaki and Frey 2005 plus Mandad et al. 2015: choose the geometry and
   topology contract before implementing an error gate.
4. Yan et al. 2009, Yan et al. 2014 (LRVD), and Valette et al. 2008: decide
   whether a global CVT/Voronoi candidate is justified alongside local edits.
5. Alliez et al. 2003 and Zhong et al. 2013: define the anisotropic metric path.
6. Bischoff and Kobbelt 2005 plus Attene 2010: freeze repair/remesh
   preconditions and failure reporting.
7. Mahmoud et al. 2025: only after deterministic serial operator semantics and
   rollback are fixed, design patch conflicts and parallel commit.

## Coverage assessment and next snowball

This batch covers every requested family: local operators, hard error/envelope,
CVT/RVD, Poisson/blue-noise sampling, feature preservation, anisotropy,
repair/preconditions, and parallel execution. It is not yet a saturation claim.
The next batch should:

1. extract the complete backward and forward citation sets of the six P0 global
   methods (Alliez 2005, Yan 2009, LRVD 2014, Hu 2017, Wang 2019, Mahmoud 2025);
2. use the Khan et al. systematic-review corpus only as a recall audit;
3. search specifically for robust exact self-intersection/fold-over predicates,
   constrained feature-graph updates, deterministic parallel commits, and CFD
   patch/provenance preservation, which are underrepresented in this batch;
4. stop only after two consecutive searches add no new algorithm family or
   materially stronger validity contract.
