# Native Poly Literature Evidence Matrix

Status: active systematic review. `FULL_READ` means every page, equations,
algorithm, experiments, limitations, and references were inspected. Representative
pages were also rendered and visually checked.

| Paper | Status | Evidence relevant to AutoTessell | Candidate cards | Important caution |
| --- | --- | --- | --- | --- |
| Abdelkader et al. 2020, VoroCrust | FULL_READ | Stratum-aware ball protection; C1-C4 coverage/gradation; paired surface seeds; half-covered-pair sliver elimination; variable-radius interior sampling | `POLY-VOROCRUST-PROTECT1`, `POLY-VOROCRUST-SEEDPAIR1`, `POLY-VOROCRUST-SLIVER1`, `POLY-VOROCRUST-EDGE1` | Requires faithful watertight input; quality degrades near sharp features; isotropic and no boundary layers; short interior edges remain |
| Garimella et al. 2013, generalized tet dual | FULL_READ | Entity-classified primal-to-dual construction for boundaries/interfaces/non-manifolds; star-shaped signed-subtet validity; condition-number untangling | `POLY-DUAL-CLASSIFY1`, `POLY-DUAL-POINT1`, `POLY-STAR-VALID1`, `POLY-DUAL-UNTANGLE1`, `POLY-CONCAVE-SPLIT1` | General dual is not necessarily Voronoi or planar-faced; concave boundary failures require topology changes; preliminary experiments |
| Nishikawa 2022, FV flux correction | FULL_READ | Single-flux-per-face correction matrix for arbitrary polygonal/non-planar faces; correction and control-volume definition must use the same triangulation | `POLY-FVERR-PLANAR1`, future `POLY-FV-FLUXCORR1` solver-adapter research | Solver discretization evidence only: does not repair invalid cells or justify accepting warped faces; correction alone without a consistent volume remains first order on the paper's prism test |
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

## 2026-07-26 `POLY-NO-DROP-HOLES1` measured evidence

Direct SciPy Voronoi was isolated with `auto_escalate=False`, seed 8, Lloyd 0,
no budgeted hex route. Legacy `quality.py` deletion removed 17/19 cube cells,
12/12 cylinder cells (the empty candidate lost selection), and 24/36 sphere
cells. Cube boundary components changed 1 -> 2 and sphere 1 -> 8; absolute
domain-volume sums fell 99.85% and 89.28%. Cube cell 6 specifically exposed
the former internal face `(19,20,22,49,50,62,70)` owned on the other side by
cell 16. This directly confirms the Sorgente-derived warning that cell deletion
can manufacture a boundary/hole.

The raw writer census found an independent silent-loss defect: cube wrote
18/19 cells and cylinder 8/12; sphere wrote 36/36. Strict writer mode now
rejects any cell/face loss or non-manifold extra face reference before files
are created. Python and optional C++ topology paths share the returned census
and have parity tests for both rejection classes.

Bounded interior-node trials were hard-gated by identical topology/patches,
bit-identical boundary positions, owner-neighbour incidence, non-increasing
negative/zero volume counts, domain-volume relative error `<=1e-10`, then
quality non-regression. Cube and cylinder did not reduce the bad population;
sphere reduced 24 -> 16 but violated domain volume. **Measured verdict: KILL
the relocation mechanism; diagnostic trial only, unconditional rollback.** ON
preserves the raw cells and uses strict writer failure rather than silently
disabling legacy deletion into writer-invalid output. OFF remains byte-identical
on all three fixtures. Fixed-primal polydual and budget+BL hex-base paths are
flag no-ops.

## 2026-07-30 `POLY-DUAL-CLASSIFY-COVERAGE1` provenance hardening

An explicit ``boundary_face_entities`` mapping is now an all-or-nothing
source-provenance contract: before any dual geometry or polyMesh output is
written, every extracted canonical primal boundary triangle must have a mapping.
Missing entries produce a deterministic failure containing the sorted tuple of
missing canonical triangles. Unclassified calls retain the existing
``defaultWall`` behavior, and complete mappings retain the existing classified
cap partition, points, cells, and writer semantics. This is a conservative
coverage guard only; it does not alter geometry, topology, routing, defaults,
or cell targets.

## 2026-07-26 `POLY-ROUTE-ATTRIB1` measured evidence

Diagnostic module: `core/generator/native_poly/route_attribution.py`.
Entry point: `scripts/diagnose_native_poly_routes.py`. The module constructs a
deterministic star-shaped tet primal from each tracked STL once, records the
primal digest, then runs direct `tet_to_poly_dual` and the
`tier_native_poly` harness on that same `(V,T)` with `auto_escalate=False`.
The tier's imported tet provider is replaced only inside the diagnostic
scope. No production route, writer default, or drop behavior is changed.

| fixture | primal digest / size | route result | mesh identity | census (cells, faces, boundary, patches) | volume / negative | area deviation | quality (max NO, max skew, mean ψ) | repeat / drop |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cube | `8088739d…` / 9 pts, 12 tets | direct = tier harness | `e995f90d…` both | 9, 56, 30, 1 | 1.000000 / 0 | ~0.000% | 19.91°, 0.355, 0.219 | identical / 0 calls |
| cylinder | `0c862037…` / 67 pts, 128 tets | direct = tier harness | `f496e6b8…` both | 67, 484, 226, 1 | 0.796718 / 0 | 3.328% | 77.70°, 63.634, 0.353 | identical / 0 calls |
| sphere | bounded fixture | timeout at 30 s | no selection | no census | no conclusion | no conclusion | no conclusion | bounded |

Both completed fixtures selected the tier path
`tier_native_poly:harness/tet_to_poly_dual`; selected and disk identities
matched, direct/tier identities matched, and two repeats per route were
byte-identical. The drop wrapper saw no invocation and dropped no cells. The
historical cylinder 15.5%/negative direct result was replayed separately on a
2,419-tet primal (593 dual cells, 15.2049% and 4 negative in the current
`facegeom_experiment` run), whereas the S5 ledger's tier result is a different
1,781-cell generation with 0.154% and zero negative. The shared-primal test
therefore attributes the discrepancy to upstream primal/measurement protocol,
not a tier-only drop or writer improvement. Keep both historical numbers as
non-comparable ledger context; no optimization card may use them as a paired
baseline. Sphere timeout is an explicit bound, not a quality result.

## 2026-07-27 — Phase 2 invalid-dual re-audit

- The historical non-manifold fan `2/18` report does not reproduce against the
  current code path.
- Current fixture result: final `invalid_star_cells=0`,
  `invalid_star_subtets=0`; the Garimella intermediate candidate is rejected
  transactionally and centroid fallback is valid.
- **Decision:** fan-component splitting plus fallback already closes the known
  failure. No concave-split or condition-number untangler was added; keep both
  Phase 2 cards dormant until a fresh final-invalid fixture appears.

### 2026-07-27 — sphere runtime re-audit

The isolated sphere dual test completed successfully in `171.34 s`
(`1 passed`). The aggregate native-poly dual suite exceeded a `300 s` shell
bound after the first two fast tests; this is a performance/fixture-cost
finding, not a new invalid-cell failure. The historical fan fixture remains
final-valid, so no Phase 2 repair was justified. The sphere cost should be
tracked as a separate performance card before any optimization changes the
dual construction.

### `POLY-DUAL-PERF-PLANE1` result

The first bounded implementation targets only the repeated plane-membership
tests in `_area_split` and `_is_on_plane`: the original per-plane Python
`any/all` loops now use the same signed-distance predicate over a pre-shaped
plane matrix. No face, point, area, topology, or acceptance rule changed.
`cProfile` attributed the old fixed-primal run to these functions and their
`np.all` reductions (`205.3 s` cumulative of `216.8 s` profiled wall). After
the change, two direct repeats took `4.8930 s` and `5.3240 s`, with identical
disk digest
`c32d581c7a6a042b7b05d1633e82ca97abd6ecfe0d4bc6d7edc0acb86cb2f14f`,
`669` cells / `5474` points, and zero invalid star cells/subtets. The primal
digest remained identical. `test_native_poly_dual.py`: `7 passed`; the full
native-poly plus boundary-provenance set: `75 passed, 38 skipped`. This closes
the measured performance card without changing the poly quality gate or
geometry.

### Stage split (fixed primal, 2026-07-27)

The new report-only benchmark fixes one native-tet primal and separates the
stages. With `sphere.stl`, `seed_density=8`, the primal stage took `1.5787 s`
and produced `669` points / `1632` tets with digest
`d068ad3c73dfd13230bc901b69937e833062a75b25b7bdde2a51ebfcd6004818`.
Three direct dual repeats on that identical `(V,T)` took `159.0619 s`,
`162.6962 s`, and `163.1518 s`; each produced `669` cells / `5474` points,
`invalid_star_cells=0`, and `invalid_star_subtets=0`. Therefore over 99% of
the measured wall time is in the dual construction, not native-tet primal
generation. The next performance investigation is inside `tet_to_poly_dual`
(especially repeated convex-hull/face grouping), not a primal-engine repair.

### `POLY-FVERR-RANDPERT1` MMS prerequisite — 2026-07-27

A report-only cell-centred two-point-flux Laplacian MMS harness was added at
`core/generator/native_poly/fv_mms.py`. It uses the manufactured solution
`u=x²+y²+z²`, exact Dirichlet values, deterministic Cartesian hex grids, and
interior-node perturbations up to Katz's 25% level. The regular grid reproduces
L2 order `2.0, 2.0`; the uncorrected two-point kernel under 25% random
perturbation gives orders `0.7658, 0.6690`. This is a diagnostic falsification
of the *uncorrected kernel* as a second-order method, not a claim about the
production native-poly route.

Applied to actual fixed-primal native-poly outputs, the solver reports:

| shape | cells / points | result |
|---|---:|---|
| sphere, seed 8 | 669 / 5474 | solved; max non-ortho `63.8878°`, skew proxy `0.235625`, L2 `0.559198` |
| cube, seed 8 | 15 / 78 | rejected: non-positive internal two-point coefficient |
| cylinder, seed 6 | 1583 / 10891 | rejected: zero-area face |

The rejections are explicit prerequisite failures and are not converted into
solution-error numbers. The native-poly production path and gates are
unchanged. `tests/test_native_poly_fv_mms.py` passes `2`; the random-perturbed
MMS benchmark is deterministic for a fixed seed.

### Correction diagnostic follow-up — 2026-07-27

The harness now also exposes an optional bounded deferred non-orthogonal
correction. This is report-only and is not wired into native-poly production.
On the synthetic Cartesian grid with 25% deterministic interior perturbation,
the corrected diagnostic recovered L2 orders `2.0094, 2.1250` (uncorrected:
`0.7658, 0.6690`). This validates the measurement harness's ability to expose
the expected non-orthogonal error mechanism; it does not validate the same
scheme on arbitrary native-poly cells.

The native-poly sphere is an explicit counterexample to promotion: the same
fixed primal (`669` cells / `5474` dual points) changed from uncorrected
`L2=0.559198` to corrected `L2=1707.868144`, with
`max_non_ortho=63.8878°`. The correction therefore remains a diagnostic
experiment and the production FV-accuracy card stays open pending a
solver-consistent face-flux implementation and prerequisite mesh repair for
the cube/cylinder rejects. `tests/test_native_poly_fv_mms.py` now passes `3`.

### Native-output prerequisite repeatability audit — 2026-07-27

The native-output adapter was repeated before interpreting any FV error. Under
the default environment, two cylinder runs with the same `seed_density=6`
selected different upstream fallback outcomes: `(1619 cells, 11053 points,
10 zero-area faces, 2 non-positive internal coefficients)` versus `(1618
cells, 11110 points, 6 zero-area faces, 0 non-positive coefficients)`. This
is a measurement-protocol failure, not evidence for a solver correction.

With `AUTO_TESSELL_P4C_PYTETWILD=0` fixed to the pure native path, the two
cylinder repeats were byte-stable at `(73 cells, 596 points)`, but still had
`20` non-positive internal two-point coefficients. The fixed cube run had
`15 cells / 78 points`, `5` zero-area faces, and `8` negative internal
coefficients. The native dual validity diagnostics simultaneously reported
`7/51` invalid cells/subtets for cube and `71/553` for cylinder in this
protocol. Both the default and fixed-native protocols therefore fail the
FV prerequisite contract; no solver-order claim is made until upstream dual
validity and path determinism are repaired.

### Upstream dual-invalidity path isolation — 2026-07-27

The two current dual-face assembly routes were isolated without changing
source behavior. Forcing the legacy ConvexHull route (path A) produced the
same result as the topology-ring route (path B): cube `7 invalid cells / 51
invalid subtets` and cylinder `71 / 541` in the fixed-native protocol. The
dispatch choice and the classified Garimella point candidate are therefore
not sufficient root causes.

The concrete cube example is boundary cell `0`: internal 6-gon and 5-gon
faces produce negative region-center subtets, and boundary face id `63` is
the zero-area triangle `[43,67,42]`. All seven cube invalid cells are boundary
cells; cylinder has `65` boundary-invalid and `6` interior-invalid cells in
the same audit. This points to dual face construction/coplanar-cap handling
(warped internal polygons and degenerate boundary caps), not to the FV
discretization. No unconditional face deletion or invalid-mesh acceptance
change was made; a transactional dual-face repair card is required.

### Dual-face geometry census — 2026-07-27

The fixed-native face census quantifies the repair target. Cube has `62`
unique internal faces with `24` warped above relative deviation `1e-8`, a
maximum relative warpage `0.45028`, and `2` zero-area internal faces; its `27`
boundary faces include `3` zero-area caps. Cylinder has `352` internal faces,
`220` warped above the same threshold with maximum relative warpage `0.62611`,
and `212` boundary faces with `9` warped caps. These are far beyond numerical
noise and explain the FV prerequisite failure. The next card must construct or
reject each affected face transactionally while preserving owner/neighbour,
boundary area, patch identity, and deterministic output; simply deleting the
zero-area faces is not admissible.

### Literature update for the repair boundary — 2026-07-27

- Nishikawa (2022), *A flux correction for finite-volume discretizations*,
  DOI `10.1016/j.jcp.2022.111481`, derives a correction for non-planar faces
  and explicitly requires a consistent control-volume definition. This
  supports the MMS measurement, but does not license applying a correction to
  cells with zero-area faces or invalid owner/neighbour geometry.
- Bonaventura and Della Rocca (2018), *Convergence analysis of a cell centered
  finite volume diffusion operator on non-orthogonal polyhedral meshes*,
  arXiv `1806.09180`, analyzes corrected two-point flux under admissible,
  sufficiently regular meshes and notes that coercivity can fail on highly
  irregular meshes. The negative coefficients observed here violate that
  prerequisite; this paper is not evidence for a gate relaxation.
- Walton, Hassan, and Morgan (2017), *Advances in co-volume mesh generation
  and mesh optimisation techniques*, DOI `10.1016/j.compstruc.2016.06.009`,
  treats Delaunay–Voronoi dual quality and the containment of Voronoi vertices
  in their primal elements as a generation objective. This is the closest
  literature direction for the next dual-face repair card.

Decision: keep `POLY-FVERR-RANDPERT1` open as a prerequisite measurement and
start the next card with dual validity/face construction, not a production FV
flux correction.

### `POLY-DUAL-FACE-REPAIR1` bounded candidates — 2026-07-27

Three small face-construction candidates were measured on the fixed-native
`AUTO_TESSELL_P4C_PYTETWILD=0`, `seed_density=6` protocol before retaining any
default behavior:

| candidate | cube | cylinder | sphere | decision |
| --- | --- | --- | --- | --- |
| preserve every `ConvexHull.simplices` triangle | `7/51 -> 7/21`, boundary faces `27 -> 322` | `71/553 -> 18/78`, boundary faces `212 -> 2588` | `2/14 -> 0/0`, boundary faces `3842 -> 26570` | **falsified**: invalidity reduction is purchased by destroying face pairing/topology |
| source-triangle cap reconstruction (temporary opt-in) | `7/51 -> 2/30`, area ratio `1.0`, boundary faces `27 -> 36` | `71/553 -> 70/440`, area ratio `1.03328 -> 1.0`, boundary faces `212 -> 384` | `2/14 -> 2/14`, area ratio `1.0` | **falsified as full repair**: cap zeros improve, internal invalidity/warpage remains and sphere regresses |
| exact `ConvexHull` first, `QJ` only on Qhull failure | `2/30` | `70/440` | `0/0` | **retained** as a minimal default-safe numerical fix; not a closure of the card |

The first two candidates were removed rather than left as hidden production
switches. The retained change avoids unconditional Qhull point perturbation,
while preserving the old `QJ` recovery path for genuinely degenerate point
sets. It passed `22` focused native-poly tests and `py_compile`. The fixed
native FV prerequisite still rejects cube/cylinder because non-positive
internal coefficients remain; no FV gate or star-validity threshold was
relaxed. The remaining issue is the topology-ring internal face geometry:
the fixed-native census still has `24/62` warped cube internal faces and
`220/352` warped cylinder internal faces. The next card must repair or reject
those faces transactionally without converting them into unpaired boundary
faces.

A follow-up diagnostic split of each topology-ring polygon into paired
triangles was also falsified. A fan using an existing ring vertex changed the
fixed-native invalid counts to cube `7/69`, cylinder `65/903`, and sphere
`36/144`; a fan around a newly added shared face-centre point was worse at
cube `15/177`, cylinder `73/1269`, and sphere `278/1776`. Both were removed.
This rules out naive triangulation as the next repair mechanism.

The topology-ring walk itself was then audited. It had no early-closure loss:
all internal-edge rings were complete and closed (`42/42` cube, `156/156`
cylinder, `1331/1331` sphere), with zero missing incident tets and zero
self-intersecting projected rings. Ring geometry is nevertheless not benign:
max best-fit-plane deviation was `0.07581` cube, `0.20622` cylinder, and
`0.25778` sphere; projected concavity occurred in `0`, `14`, and `38` rings.
This falsifies ring-order repair as the primary mechanism and keeps the
upstream dual-point/face-consistency card open.

### Well-centered primal audit — 2026-07-27

The same fixed-native tets were audited by solving each tet circumcenter and
checking its barycentric coordinates. Only `20/40` cube, `8/212` cylinder,
and `196/1913` sphere tets were well-centered; the remaining circumcenters
were outside the primal tet. This is consistent with the Walton--Hassan--
Morgan Delaunay/Voronoi prerequisite and explains why a centroid dual produces
warped edge rings: it is robustly inside each tet, but it is not equidistant
from every primal edge. A raw circumcenter diagnostic was worse (`14/136`,
`68/932`, and `449/3782` invalid candidate cell/subtets for cube/cylinder/
sphere) and was not retained. The next repair should therefore be framed as
an upstream well-centered/weighted-dual experiment with transactional fallback,
not as a face-order or face-deletion patch.

### `POLY-DUAL-WELL-CENTER1` bounded interior-move diagnostic — 2026-07-27

The literature follow-up selected VanderZee et al., *Well-Centered
Triangulation* (`arXiv:0802.2108`), because its optimization moves interior
vertices while keeping connectivity and boundary vertices fixed.  The related
simple-domain study (`arXiv:0806.2332`) distinguishes well-centeredness from
general angle/sliver quality, while Cheng--Dey--Shewchuk's weighted Delaunay
refinement (DOI `10.1137/S0097539703418808`) is the stronger future route for
deterministic boundary-conforming quality.

A standalone deterministic local experiment proposed moves toward neighbour
means and incident circumcenter means.  A move was accepted only when incident
tet orientation and near-zero-volume checks passed and the local negative
circumcenter-barycentric penalty decreased.  Boundary displacement was exactly
zero:

| shape | accepted moves | well-centered before -> after | negative penalty before -> after | centroid dual invalid before -> after | Garimella candidate |
| --- | ---: | --- | --- | --- | --- |
| cube | 6 | `20/40 -> 20/40` | `7205.0 -> 92.0912` | `2/30 -> 2/30` | rejected `11/240` |
| cylinder | 10 | `8/212 -> 24/212` | `5133.97 -> 875.166` | `70/440 -> 70/440` | rejected `68/558` |
| sphere | 129 | `196/1913 -> 228/1913` | `9200.91 -> 1866.95` | `0/0 -> 0/0` | rejected `82/404` |

The local lane improves primal circumcenter containment but does not change the
exported centroid-dual invalidity, and the clipped-circumcenter candidate is
still rejected by the existing star guard.  It is therefore **measured,
insufficient as a dual repair**, and remains diagnostic-only.  Raw
circumcenter activation is still prohibited; the card remains open for a
weighted-Delaunay or dual-face-aware objective.

A second report-only point-placement split was also measured: use the exact
circumcenter only for already well-centered primal tets and keep the centroid
for every other tet.  The candidate invalid counts were cube `11/156`,
cylinder `70/457`, and sphere `10/56`; the existing whole-candidate guard still
rejected all three, and the exported result remained the centroid fallback.
Per-cell silent mixing was not attempted because tet dual points are shared by
multiple primal-vertex cells and could break face-point consistency.

### `POLY-DUAL-TOPOLOGY-1` necessary-condition audit — 2026-07-27

The same native outputs were checked for the 3D well-centered necessary
condition that every interior vertex have at least seven incident edges.  The
fixed-native census found one interior point below seven on cube (minimum
valence `6`), one on cylinder (minimum `6`), and seven on sphere (minimum `0`;
the zero-valence point is an unused exported primal point).  Counts were
computed from the actual tet incidence, not from the nominal point array.

| shape | boundary vertices | interior points | interior valence < 7 | minimum valence |
| --- | ---: | ---: | ---: | ---: |
| cube | 8 | 7 | 1 | 6 |
| cylinder | 66 | 7 | 1 | 6 |
| sphere | 642 | 64 | 7 | 0 |

This is evidence for a topology obstruction, not proof that every low-valence
point causes the observed dual invalidity.  The next diagnostic must map the
low-valence/orphan points to incident tets, dual cells, and warped internal
faces before attempting any connectivity-changing operation.

The first topology-map run reported non-boundary edges with fewer than three
incident tets, but a code audit found a diagnostic bug: its boundary-edge set
used only the first edge of each boundary triangle. That run is superseded and
must not be used as evidence. After fixing the edge-set construction, the same
fixed-native outputs have **zero** incomplete interior edge links: cube `0/42`,
cylinder `0/156`, sphere `0/1331` (`incomplete_rings_lt3 / closed internal
edges`). Recovery-off, recovery-on, and Phase-A-on replay all remained `0/0/0`,
so there is no measured recovery/filtering boundary to repair. The low-valence
cube/cylinder vertices still have six closed, planar
candidate rings, while normal edges carry the observed warpage (`max 0.05126`
cube, `0.11737` cylinder, `0.15141` sphere). Thus no upstream edge-link repair
card is justified by this measurement.

Decision: `POLY-DUAL-TOPOLOGY-1` **measured, false alarm due diagnostic bug**.
The native-tet audit agrees with the corrected map (`valid=True`, zero open and
non-manifold boundary edges). Keep the topology card closed for the current
fixtures and return to a dual-point/face-consistency candidate only after a new
independent mechanism is measured.
### `POLY-DUAL-TOPOLOGY-1` checker cross-check — 2026-07-27 (superseded)

The apparent open-link examples above came from the same diagnostic edge-set
bug, not from the generated tets. With the corrected map, cube/cylinder/sphere
have zero incomplete non-boundary edge links, and the native-tet audit reports
zero open/non-manifold boundary edges and one boundary component in all cases.
The proposed `POLY-DUAL-CONNECTIVITY-REPAIR1` card is therefore **not opened**.

### `POLY-DUAL-FACE-WARP1` report-only primal relocation — 2026-07-27

The next bounded mechanism minimized affected closed internal centroid-dual
ring warpage by moving interior primal vertices toward their one-ring mean.
Orientation/nonzero-volume guards were mandatory and boundary displacement was
zero. Accepted moves were cube `0`, cylinder `4`, sphere `109`; max ring
warpage changed `0.051261 -> 0.051261`, `0.117367 -> 0.117367`, and
`0.151415 -> 0.144893`. Dual invalid cells/subtets changed `2/30 -> 2/30`,
`70/440 -> 70/440`, and `0/0 -> 0/0`.

Decision: **measured, insufficient**. The report-only objective does not
resolve cube/cylinder FV validity and is not connected to production. A future
candidate must change dual face construction or include an explicit
star-validity/owner-neighbour objective, not just ring planarity.

### `POLY-FVERR-RANDPERT1` report-only MMS prerequisite — 2026-07-27

The isolated scalar MMS diagnostic in `core/generator/native_poly/fv_mms.py`
was executed on `n=4,8,16` Cartesian grids. It is not an OpenFOAM replacement
and is not connected to native_poly generation or gates. The manufactured
solution is `u=x²+y²+z²` with exact Dirichlet boundary data.

| perturbation | correction | L2 errors (`n=4,8,16`) | observed orders | result |
| --- | --- | --- | --- | --- |
| `0.0` | off | `1.5625e-2, 3.90625e-3, 9.765625e-4` | `2.000, 2.000` | baseline verified |
| `0.25` | off | `1.95425e-2, 1.14931e-2, 7.22836e-3` | `0.766, 0.669` | non-orthogonal degradation measured |
| `0.0` | report-only correction | `8.13143e-2, 1.96935e-2, 4.38054e-3` | `2.046, 2.169` | second-order retained; larger constant |
| `0.25` | report-only correction | `8.53081e-2, 2.11889e-2, 4.85770e-3` | `2.009, 2.125` | Katz-style order recovered |

Decision: `POLY-FVERR-RANDPERT1` is no longer blocked as a measurement card,
but the correction remains **diagnostic-only**. The result supports measuring
face non-orthogonality/warpage together with solution error; it does not justify
relaxing the existing FV prerequisite or enabling a production flux correction.

## 2026-07-27 `POLY-FVERR-FACEPAIR1` report-only measurement

Added a deterministic per-cell residual following Juretić's proposed
`min_pairing sum |S_i n_i + S_j n_j| / sum |S_i|`. Opposite equal-area face
vectors contribute zero; odd face counts leave one explicit unmatched-vector
penalty rather than inventing a face. The metric is report-only and is wired
through `PolyPhase0Metrics` and `CheckMeshResult`; no gate or mesh operation
uses it.

Analytic checks distinguish a six-face cube-like cell (`0.0`) from a regular
tetra-like four-face cell (strictly positive residual), and the Phase-0 metric
plus MMS tests pass `14/14`. This closes only the implementation/calibration
sub-card. A native-poly versus native-hex versus native-tet census is still
required before interpreting a threshold or making an FV accuracy claim.

### `POLY-PHASE0-MATCHING-CPP23-1` polynomial evaluator — 2026-07-31

The exact subset dynamic program became exponential on seed-10 dual cells with
up to 37 incident faces, leaving `NativeMeshChecker` CPU-active beyond 180
seconds. The pairing objective now uses its exact maximum-weight-matching
reduction and an independently authored C++23 Edmonds/Galil primal-dual kernel.
The same kernel serves polygonal Python orchestration and the native triangular
Phase-0 path; the exhaustive Python solver remains the small-input oracle.

After mixed-scale blocker repair, the sphere checker completes three exact
runs in `2.694/2.619/2.543 s`, at least `66.8x` faster than the timeout lower
bound. All non-pairing report fields
and all five polyMesh hashes remain identical; `mesh_ok=true`, negative volume
zero. Native/exhaustive parity passed 1,500 deterministic cases through 14
vectors with worst scaled difference `3.56e-16`; dense equal, antipodal,
near-tie, odd-37, sparse-positive-saving, exhaustive mixed-scale permutation,
and harness tests terminate. Exact binary64 integer weights replace global
quantization, and the scalar is summed directly from selected pair costs to
avoid cancellation. This is a
report-only `L1_PASS / CORRECTNESS_KEEP`; no gate, route, mesh, target-cell, or
boundary-layer behavior changed. See
`poly_phase0_matching_cpp23_evidence_2026-07-31.md`.

### `POLY-DUAL-BOUNDARY-SEMANTICS-L0/L1` — 2026-07-28

The new read-only audit requires every exported classified dual boundary cap
to have one valid owner, positive area, exactly one containing primal boundary
triangle, the matching patch name/type, and a per-source-triangle cap-area sum
equal to the primal triangle area. A hand tetrahedron L0 accepts exact caps
and rejects a wrong patch label. The classified two-patch bipyramid L1 passes:
all `18` boundary caps map uniquely and its maximum source-area error is zero.

The measurement exposed a reader/provenance gap rather than a generator defect:
`parse_foam_boundary` discarded OpenFOAM's patch `type`, making a valid
`source_low` `patch` appear as the default `wall`. The parser now retains the
additive `type` field; focused boundary semantics, parser, and dual-classified
tests pass `19/19`. This is still only a synthetic-primal L1 certificate. A
native-poly L2 source-surface claim remains blocked by native-tet's global
source-surface ledger, so the audit is not wired as a production acceptance
gate yet.

### `POLY-DUAL-TET-INPUT-CONTRACT-L0` — 2026-07-30

**Release connection.** This is a bounded Gate-5/Gate-10 card, not a target-cell
or routing change. A direct call to `tet_to_poly_dual` previously converted raw
connectivity with `np.asarray(..., dtype=np.int64)` before validating it:
`3.9` silently became `3`, and `-1` became NumPy reverse indexing. The former
produced a successful one-tet output; the latter produced a different successful
three-cell output. Out-of-range and wrong-shape rows instead escaped as Python
exceptions. Those outcomes cannot establish a valid polyMesh or a truthful
robust failure.

**Primary-source provenance and license.** The sole external source consulted
for this card was the current official OpenFOAM Foundation
[`checkMesh` source](https://github.com/OpenFOAM/OpenFOAM-dev/blob/master/applications/utilities/mesh/manipulation/checkMesh/checkMesh.C),
accessed 2026-07-30: it documents separate topology and geometry validation and
an `-allTopology` option. The repository
[`README.org`](https://github.com/OpenFOAM/OpenFOAM-dev/blob/master/README.org)
and [`COPYING`](https://github.com/OpenFOAM/OpenFOAM-dev/blob/master/COPYING)
identify the source as GPL-3.0-or-later. No OpenFOAM code, algorithm, test data,
or third-party dependency was copied; this card only applies the independent
boundary rule that invalid mesh addressing must be refused before writing.

**Mechanism and boundary.** `dual.py` now accepts finite `(Nv, 3)` coordinates
and raw non-boolean integral `(Nt, 4)` connectivity only. It rejects malformed,
fractional, boolean, string, negative, out-of-range, repeated-index, and
zero-volume tetrahedra before importing the writer path or creating `case_dir`.
It deliberately does **not** add a positive-orientation requirement, so existing
valid accepted input semantics are preserved. The implementation changes neither
dual point placement, source classification, routing, target-cell behavior, nor
any default for valid inputs.

**L0/L1 evidence.** The hand-checkable unit tetrahedron retains
`cells/points/faces = 4/15/18`; all invalid witnesses return the same explicit
failure on two calls, leave both input arrays unchanged, and create no output
directory. The classified two-patch bipyramid remains the L1 representative
fixture. The focused L0/L1 subset reports `16 passed, 4 deselected in 2.48s`
after excluding only the existing sphere/harness cases. The full
`tests/test_native_poly_dual.py` baseline exceeded the local 124-second command
budget because of those existing sphere/harness tests, so it is a timeout
record, not a pass claim. This closes only the raw-input failure ambiguity;
campaign shape, corpus topology, positive-layer, and adverse-fixture coverage
remain open.
