# Native Poly Literature Evidence Matrix

Status: active systematic review. `FULL_READ` means every page, equations,
algorithm, experiments, limitations, and references were inspected. Representative
pages were also rendered and visually checked.

| Paper | Status | Evidence relevant to AutoTessell | Candidate cards | Important caution |
| --- | --- | --- | --- | --- |
| Abdelkader et al. 2020, VoroCrust | FULL_READ | Stratum-aware ball protection; C1-C4 coverage/gradation; paired surface seeds; half-covered-pair sliver elimination; variable-radius interior sampling | `POLY-VOROCRUST-PROTECT1`, `POLY-VOROCRUST-SEEDPAIR1`, `POLY-VOROCRUST-SLIVER1`, `POLY-VOROCRUST-EDGE1` | Requires faithful watertight input; quality degrades near sharp features; isotropic and no boundary layers; short interior edges remain |
| Garimella et al. 2013, generalized tet dual | FULL_READ | Entity-classified primal-to-dual construction for boundaries/interfaces/non-manifolds; star-shaped signed-subtet validity; condition-number untangling | `POLY-DUAL-CLASSIFY1`, `POLY-DUAL-POINT1`, `POLY-STAR-VALID1`, `POLY-DUAL-UNTANGLE1`, `POLY-CONCAVE-SPLIT1` | General dual is not necessarily Voronoi or planar-faced; concave boundary failures require topology changes; preliminary experiments |
| Sorgente et al. 2022, 3D quality indicator | FULL_READ | Separate star-kernel, size-degeneration, and combinatorial indicators; geometry-only pre-solver screening; empirical VEM correlation | `POLY-QUALITY-VECTOR1`, `POLY-VALIDITY-FIRST1`, `POLY-NO-DROP-HOLES1`, `POLY-QUALITY-CORRELATE1` | VEM/isotropic-Poisson evidence, not a universal CFD quality theorem; sufficient assumptions are not necessary |
| Sorgente et al. 2023, quality agglomeration | FULL_READ | Constrained adjacency graph; union-quality data term; alpha-beta labeling; explicit element-count/accuracy tradeoff | `POLY-AGGLOM-GRAPH1`, `POLY-AGGLOM-PAIR1`, `POLY-AGGLOM-LOOKAHEAD1`, `POLY-AGGLOM-CFD1` | Algorithm and evidence are 2D polygonal DFN, not 3D volume agglomeration; pair-only energy misses larger unions |

## Architecture decision

Native Poly should expose two separate production routes sharing one validity and
quality contract:

1. **Conforming Voronoi route:** VoroCrust-style boundary protection and seed
   pairing, followed by graded interior sampling and optional true restricted-cell
   CVT optimization.
2. **Primal-dual/agglomeration route:** a classified, quality tet primal followed by
   topology-preserving generalized dualization or constrained agglomeration.

Both routes must pass the same hard gates before OpenFOAM quality optimization:

1. complete owner-neighbor and patch/material classification;
2. positive volume and star-shaped/kernel validity;
3. boundary/interface topology and two-sided geometric fidelity;
4. minimum face/edge scale and face-planarity constraints;
5. only then non-orthogonality, skewness, complexity, and cell-budget objectives.

### 2026-07-23 update (after 9-paper full-read batch)

- **Route-2 agglomeration-leg demotion is now confirmed by 5 independent full
  reads** (Bassi 2012, Pan-Persson 2022, R3MG 2025, MAGNET 2025, PVEM 2025).
  Every strong agglomeration result lives in DG/VEM land, where per-facet
  quadrature, modal/physical-frame bases, and stabilization absorb arbitrary
  cell shape — machinery a cell-centered FV code does not possess. None of the
  five computes a single FV metric (face planarity, non-orthogonality, skewness,
  owner-neighbor face construction) on its agglomerates. Their success transfers
  zero evidence to OpenFOAM export; `POLY-AGGLOM-CFD1` remains the decisive
  gate for the leg.
- **NEW primary FV evidence FOR the polydual main generator: Juretić & Gosman
  2010.** The face-pair cancellation analysis shows cells built of face pairs
  (opposite orientation, equal area) cancel leading truncation errors:
  hexagon-like polyhedral duals are only ~1.155x square/hex truncation error and
  need only ~2x cells for equal mean error, while perfect-quality tetrahedra are
  the *worst* FV cells (no face pairs; ~10x cells needed). This is the closest
  primary-source FV-theory support for polydual as a first-class engine —
  valid for well-shaped, face-paired polyhedra.
- **Quality-gate audit results** (Juretić 2010 + Katz-Sankaran 2011 vs our
  `core/evaluator/native_checker.py` gates):
  - *Non-orthogonality*: supported as a metric (appears in the diffusion error
    via `1/cos(alpha_N)` and `tan(alpha_N)`); degradation is smooth, so the
    65-70 deg limit is a calibration choice, not theory.
  - *Skewness*: supported as a metric (drives convection interpolation error),
    but the paper's `psi = |m|/|d|` normalization differs from our/OpenFOAM
    units — the definition mismatch must be reconciled before citing thresholds
    (`POLY-FVERR-SKEWDEF1`).
  - *Aspect ratio*: unsupported by FV evidence (explicitly deferred by Juretić;
    Katz shows AR up to 1e6 is fine for aligned cell-centered BL cells) — the
    gate must not reject aligned boundary-layer stretching.
  - *Face planarity/warpage*: a MISSING gate. Katz Table 5 proves single-point
    flux on non-planar faces is first order; generalized-dual poly faces are
    warped; neither non-ortho nor skew detects this (`POLY-FVERR-PLANAR1`).
  - *Uniformity `fx` and face pairing*: missing metrics. `fx != 0.5` reduces
    diffusion to first order; face pairing is the dominant shape driver on good
    meshes and no conventional checker measures it (`POLY-FVERR-UNIFORMITY1`,
    `POLY-FVERR-FACEPAIR1`).

## Current-code audit

- `voronoi.py:2022-2035` creates a jittered Cartesian seed lattice and filters by
  ray casting. This is neither variable-radius Poisson sampling nor VoroCrust.
- `voronoi.py:2128-2160` adds all surface vertices as outer seeds and snaps outside
  Voronoi vertices to nearest surface vertices. Snapping invalidates exact Voronoi
  geometry and the orthogonal-dual contract.
- `voronoi.py:1017-1149` labels its loop Lloyd/CVT, but updates with the arithmetic
  mean of finite Voronoi vertices, not the volume centroid of a domain-restricted
  cell. Infinite cells are skipped and the domain is absent from the objective.
- `aniso_cvt.py:201-219` computes curvature-based `scales` but never uses them in
  assignment or relocation; seeds are pulled toward the mean of eight nearest
  surface vertices. It is not anisotropic volume CVT.
- `dual.py:458-512` uses tet centroids and then convex-hulls each point set. This
  differs from entity-classified generalized dual construction and can replace the
  intended topology with a convex approximation.
- `dual.py:862` emits one `defaultWall`, losing multi-patch/material semantics.
- `quality.py:143-202` measures only internal-face non-orthogonality/skewness and
  face count. It lacks star-kernel, face validity/warpage, and size-degeneration
  metrics.
- `quality.py:369-432` may drop complete cells. Without an explicit cavity/domain
  contract this can manufacture holes or turn former internal faces into external
  walls; it must not be a quality-repair primitive.
- `tier_native_poly.py` preferentially routes budgeted output through a hex base;
  therefore current "Native Poly" benchmarks must report which route actually ran.

## Ordered implementation program

| Priority | Card | Mechanical stop condition |
| --- | --- | --- |
| P0 | `POLY-QUALITY-VECTOR1` + `POLY-VALIDITY-FIRST1` | Analytic fixtures classify convex/star-shaped/non-star-shaped/warped/negative cells correctly and deterministically |
| P0 | `POLY-NO-DROP-HOLES1` | Every accepted repair preserves boundary components, patch ownership, owner-neighbor consistency, and domain volume |
| P0 | `POLY-DUAL-CLASSIFY1` | Multi-patch and multi-material fixtures preserve all geometric entity mappings |
| P1 | `POLY-DUAL-POINT1` + `POLY-STAR-VALID1` | Classified generalized dual has zero invalid cells on convex and non-manifold fixtures |
| P1 | `POLY-AGGLOM-GRAPH1` + `POLY-AGGLOM-PAIR1` | Deterministic constrained unions reduce cells without any hard-contract regression |
| P2 | `POLY-VOROCRUST-PROTECT1` + `POLY-VOROCRUST-SEEDPAIR1` | Conforming unclipped Voronoi boundary passes topology, label, and two-sided fidelity gates |
| P2 | `POLY-VOROCRUST-SLIVER1` + `POLY-VOROCRUST-EDGE1` | No half-covered surface pair and controlled minimum interior edge on the regression set |
| P3 | `POLY-QUALITY-CORRELATE1` + `POLY-AGGLOM-CFD1` | Preregistered CFD benchmarks justify weights and any claimed cell-count/accuracy advantage |

## Access ledger

All four selected papers were read in full. No DOI in this batch remains
inaccessible.

## 2026-07-23 full-read batch (9 papers)

| Paper | Status | Evidence relevant to AutoTessell | Candidate cards | Important caution |
| --- | --- | --- | --- | --- |
| Juretić, Gosman 2010, FV error vs mesh type | FULL_READ (pages 27/27) | Face-pair cancellation as the dominant FV shape driver; hexagon-like poly duals ~1.155x square truncation error and ~2x cells for equal mean error vs ~10x for tets; skewness drives convection, non-orthogonality drives diffusion, uniformity `fx != 0.5` makes diffusion first order | `POLY-FVERR-SKEWDEF1`, `POLY-FVERR-UNIFORMITY1`, `POLY-FVERR-FACEPAIR1` | Truncation analysis is 2D; 3D claims via face-pair argument only; tested polygons are near-regular Delaunay duals, not distorted/agglomerated cells; no gate thresholds derived; aspect ratio explicitly not analyzed |
| Katz, Sankaran 2011, mesh quality vs CFD accuracy | FULL_READ (pages 17/17) | Cell-centered FV holds second order under 25% random node perturbation (all cell types, inviscid+viscous); single-point flux on non-planar faces is provably first order; AR up to 1e6 acceptable for aligned BL cells; prism/hex BL cells lowest error per DOF | `POLY-FVERR-PLANAR1`, `POLY-FVERR-RANDPERT1` | No OpenFOAM-style metric values reported — thresholds cannot be read off; random skew only (systematic skew untested); 3D study inviscid prism-only; no general polyhedral cells tested |
| Bassi et al. 2012, agglomeration DG | FULL_READ (pages 21/21) | DG-on-agglomerates contract: connectedness is the only admissibility requirement; MGridGen two-phase agglomeration with aspect-ratio objective; per-facet quadrature + inertia-frame orthonormal basis; h-adaptivity via per-cell agglomeration-factor upper bound | `POLY-AGGLOM-FACEGEOM1`, `POLY-AGGLOM-SHAPE1` | 2D Poisson/BR2 only (screening said 3D Euler/NS — wrong); never computes an agglomerate-face normal, centroid, or planarity; ~156 fine sub-elements per polygon cost; zero transfer to FV admissibility |
| Pan, Persson 2022, agglomeration multigrid CDG | FULL_READ (pages 12/12) | Greedy vertex-star agglomerator (O(n log n), orphan absorption into smallest adjacent block) as deterministic route-2 baseline; composite sub-element quadrature; connectedness is the entire validity bar | `POLY-AGGLOM-VSTAR1` | No aspect-ratio or any shape objective (screening claim wrong); all experiments 2D, p=1; no quality metric enforced or reported; DG-specific machinery (modal basis, flux coarsening) has no FV analogue |
| Feder, Cangiani, Heltai 2025, R3MG | FULL_READ (pages 23/23) | R*-tree AABB grouping: near-free cost, deterministic given fixed cell order, cardinality-balanced, nested hierarchy by construction; beats METIS on BR/OF/UF/CR averages; BR and OF are cheap implementable shape proxies | `POLY-AGGLOM-RTREE1` | Hierarchy builder, not a mesh generator — agglomerate faces are unmerged fine facets with hanging nodes; no face-connectivity guarantee; no FV metric anywhere; no shape-regularity theorem; worst-case CR degrades on curved boundaries |
| Antonietti, Dassi, Manuzzi 2022, ML refinement | FULL_READ (pages 22/22) | Deterministic UF/Ball-Ratio quality metrics; k-means 2-seed cutting-plane split with vertex snapping + validity gate + perturbation retry; ML-picks-branch/deterministic-code-gates template matches our AI-advisory constraint | `POLY-QUALITY-UFBR1`, `POLY-AGGLOM-KMEANSCUT1` | Refinement paper, not agglomeration (filename misleading); no GNN trained here; VEM/PolyDG error is the arbiter; CNN margin nearly vanishes out-of-distribution; no FV metrics, no CAD boundaries |
| Antonietti et al. 2025, MAGNET | FULL_READ (pages 26/26) | Deterministic element-wise metric suite (CR, sphericity, UF, volume difference, heterogeneity preservation), all [0,1]; face-adjacency connected-component post-split guard; honest finding: GNN quality margin over METIS/k-means is essentially zero | `POLY-AGG-METRIC1`, `POLY-AGG-CONNSPLIT1` | PDE validation is 2D-only (3D evidence is metric box plots without a 3D solve); no shape-regularity guarantee; connectivity must be repaired post hoc; agglomerates can span boundary-condition discontinuities |
| Fu et al. 2025, PVEM | FULL_READ (pages 21/21) | Merge-with-best-neighbor sliver repair (node-preserving, no smoothing solve); `h = 6V/A` as a single-scalar degeneracy indicator; triangular-face invariant sidesteps warpage; real 3D free-surface evidence with 1-4 orders-of-magnitude time-step gains | `POLY-QUALITY-HCHAR1`, `POLY-QUALITY-AGGLOM1` | Stabilized-VEM consumer — shape-tolerance claims do not transfer to FV; agglomerates are transient repair artifacts; no per-cell quality analysis of the produced polyhedra; do NOT relax FV gates on this evidence |
| Du, Faber, Gunzburger 1999, CVT review | FULL_READ (pages 40/40) | CVT energy/critical-point theory; frozen-boundary interior Lloyd remains a monotone energy descent (per-seed centroid condition survives restriction); centroidal generators give second-order covolume/FD truncation error; density-graded sizing `rho ~ h^-(N+2)` heuristic | `POLY-CVT-LLOYD1`, `POLY-CVT-DENSITY1` | No Lloyd convergence proof in N>=2; converged state can be a saddle; Gersho's conjecture open in 3D (cell-shape optimality conjectural); `rho^-1/3` sizing is 1D-only; clipped-cell centroid containment and boundary-face invariance need our own guards |

### Corrections to gap_search_3d_agglomeration.md screening

Recorded here verbatim from the FULL_READ notes; the screening file itself is
left unedited as a record of the screening pass.

- **Bassi 2012 is 2D Poisson/BR2, not 3D Euler/NS.** The gap-search row credits
  it with "arbitrarily-shaped 3D agglomerated elements ... (Euler/Navier-
  Stokes)"; the paper is explicitly 2D ("For the sake of simplicity, the focus
  is here on the two-dimensional case") and its model problem is the Poisson
  equation with BR2. The gap-search verdict's "four primary 3D sources" claim
  therefore drops to **three** (Dargaville 2021, Sukumar-Tupek 2022,
  Antonietti-Corti-Martinelli 2026) for element-level 3D evidence.
- **Pan 2022 has no aspect-ratio awareness.** The screening row says
  "aspect-ratio-aware agglomerate selection on 3D unstructured meshes"; that is
  wrong on both counts — the agglomeration heuristic has no aspect-ratio or any
  other shape objective, and every numerical experiment is 2D (3D is explicitly
  future work).
- **Antonietti 2022 is a refinement paper, not agglomeration.** The verified
  title is about polyhedral grid refinement (splitting cells); agglomeration
  appears only as a test input (PARMETIS hinge mesh) and as future work. No GNN
  is trained or used in this paper.
- **MAGNET's PDE validation is 2D-only.** The 3D tests (hybrid cube, brain,
  statue) are genuine 3D agglomeration, but the PolyDG verification (Poisson +
  heat) is 2D only; 3D evidence is quality-metric box plots without a 3D solve.
- **R3MG is a multigrid-hierarchy builder, not a mesh generator.** It never
  produces cells an FV solver would consume directly: the output "polytopal
  mesh" is a labeling of fine cells plus a tree, and merged planar
  owner-neighbor faces are never constructed, measured, or claimed.

### Consolidated card list (2026-07-23 batch, grouped by theme)

All card names verified against their source notes.

**Gate calibration (FV error theory):**

| Card | Source | One-line intent |
| --- | --- | --- |
| `POLY-FVERR-PLANAR1` | Katz 2011 | Add face non-planarity/warpage metric and gate to `NativeMeshChecker` |
| `POLY-FVERR-RANDPERT1` | Katz 2011 | Reproduce the random-perturbation MMS protocol to map our gate numbers to solution error |
| `POLY-FVERR-SKEWDEF1` | Juretić 2010 | Reconcile our/OpenFOAM skewness definitions with the paper's `psi = |m|/|d|` |
| `POLY-FVERR-UNIFORMITY1` | Juretić 2010 | Report uniformity `fx` distribution per engine (diffusion order driver) |
| `POLY-FVERR-FACEPAIR1` | Juretić 2010 | Measure a per-cell face-pairing residual; confirm polydual scores near hex, far from tet |

**Quality metrics (evaluator additions):**

| Card | Source | One-line intent |
| --- | --- | --- |
| `POLY-QUALITY-UFBR1` | Antonietti 2022 | Deterministic Uniformity Factor + Ball Ratio per-cell metrics, report-only first |
| `POLY-AGG-METRIC1` | MAGNET 2025 | Element-wise CR, sphericity, UF, volume-difference metrics for poly cells |
| `POLY-QUALITY-HCHAR1` | PVEM 2025 | Per-cell `h = 6V/A` characteristic length; catches pancake cells volume gates miss |

**Repair (merge/split operators):**

| Card | Source | One-line intent |
| --- | --- | --- |
| `POLY-QUALITY-AGGLOM1` | PVEM 2025 | Node-preserving merge-with-best-neighbor repair for cells failing the h/star gate |
| `POLY-AGG-CONNSPLIT1` | MAGNET 2025 | Face-adjacency connected-component guard splitting any proposed cell grouping |

**Route-2 agglomeration experiments (quality-gated secondary leg):**

| Card | Source | One-line intent |
| --- | --- | --- |
| `POLY-AGGLOM-VSTAR1` | Pan 2022 | Greedy vertex-star agglomerator as deterministic partitioner baseline vs METIS |
| `POLY-AGGLOM-RTREE1` | R3MG 2025 | R*-tree AABB grouping as candidate-set generator, with connectivity check + FV gates |
| `POLY-AGGLOM-FACEGEOM1` | Bassi 2012 | Collapse merged interfaces to explicit polygonal faces and measure FV metrics |
| `POLY-AGGLOM-SHAPE1` | Bassi 2012 | MGridGen-style two-phase agglomerator with aspect-ratio objective and cell budget |
| `POLY-AGGLOM-KMEANSCUT1` | Antonietti 2022 | Deterministic 2-seed k-means cutting-plane split for oversized/concave dual cells |

**Route-1 CVT (conforming Voronoi leg):**

| Card | Source | One-line intent |
| --- | --- | --- |
| `POLY-CVT-LLOYD1` | Du 1999 | Frozen-boundary interior Lloyd pass with monotone-energy assert and rollback gate |
| `POLY-CVT-DENSITY1` | Du 1999 | Density-graded interior seed sampling `rho = h^-alpha`, sweep alpha in {3..6} |
