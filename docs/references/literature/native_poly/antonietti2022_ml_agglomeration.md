# Machine Learning Based Refinement Strategies for Polyhedral Grids with Applications to Virtual Element and Polyhedral Discontinuous Galerkin Methods

## Bibliography and access

- P.F. Antonietti (MOX, Politecnico di Milano), F. Dassi (Milano-Bicocca), E. Manuzzi (MOX).
- *Journal of Computational Physics* 469 (2022) 111531.
- DOI: `10.1016/j.jcp.2022.111531`
- Local PDF: `papers/pdf/23_antonietti_2022_ml_agglomeration.pdf`
- Status: `FULL_READ` (22/22 pages, 2026-07-23).
- **Title correction.** The local filename says "ml_agglomeration", but the verified
  title is about polyhedral grid **refinement** (splitting cells), not agglomeration
  (merging cells). Agglomeration appears only (a) as a test input — a hinge mesh of
  9361 cells produced by agglomerating tetrahedra with PARMETIS — and (b) as future
  work ("use graph neural networks to classify the connectivity graph" for
  agglomeration; that is a *different, later* Antonietti-group paper). No GNN is
  trained or used in this paper.

## Problem and assumptions

General polytopal FEMs (VEM, PolyDG, HHO, mimetic FD) accept arbitrarily shaped
polyhedral cells, but there is no established way to refine such a cell while
preserving grid structure and quality. The paper extends the authors' 2D work
(JCP 452 (2022) 110900) to 3D. Everything is volumetric-FEM oriented: quality is
judged by discretization error per DoF, not by FV/CFD metrics such as
non-orthogonality or face planarity, and no CAD boundary is involved (unit cube
plus one agglomerated hinge).

## Method

All refinement is done by the same deterministic engine (Algorithm 1): slice one
polyhedron with a cutting plane, recursively, until all sub-elements are below the
target size `h̄ = diam(P)/2` or `nmax = 8` elements exist. ML only chooses *which
cutting-plane rule* to use.

**Algorithm 1 (general refinement of a polyhedron P):**
1. choose a cutting plane;
2. if any vertices lie closer than `tol` (= `diam(P)·1e-3`) to the plane, adjust
   the plane to pass through the >= 3 closest ones (vertex snapping — avoids
   sliver faces);
3. if the plane passes the **validity check**, slice; else run the **emergency
   strategy**: perturb plane position/orientation until a valid configuration is
   found;
4. repeat on each sub-element above the target size.

The validity check is a hard deterministic gate with two parts:
- *Geometrical*: reject cuts that create holes or other degenerate topology
  (possible when slicing non-convex cells — their Fig. 2 shows a cube-minus-pyramid
  whose slice yields a cell with a hole);
- *Numerical*: reject cuts creating edges/faces below a prescribed threshold.

**Cutting-plane strategies (the menu the ML chooses from):**
- *Diameter*: plane through the midpoint of the two farthest-apart vertices,
  normal along that direction. Cheap, greedy, ignores shape; produces skew.
- *K-means* (Algorithm 2): voxelize a bounding-box grid of n = 20^3 points, keep
  points inside P (point-in-polyhedron test), 2-cluster with k-means; the plane
  bisects the centroid pair (`n = (c2-c1)/||c2-c1||`, `x0 = (c1+c2)/2`).
  Equivalent to a 2-seed CVT. Robust on structureless cells, most expensive.
- *"Classical"*: for known shapes (tet / prism / cube), template multi-plane
  subdivisions as in standard FEM (tet → 8, cube → 8, prism → 8), applied via a
  "reference shape" built by Algorithm 3: farthest-first traversal picks n
  vertices, Quickhull triangulates them, then merge the m triangle pairs closest
  to 180 deg to recover quads. Self-similar children → recursively applicable.

**CNN classifier (Algorithm 4).** A 3D CNN maps a 16x16x16 binary voxelization of
the cell to 4 class probabilities {tetrahedron, prism, cube, other}. If the label
is a known shape, apply the corresponding classical strategy on the reference
shape; if "other", fall back to k-means. Architecture: 3x (Conv(f=8/4/2, m=8) →
ReLU → AvgPool(2,2)) → Linear → Softmax. Average pooling is chosen deliberately to
blur small-scale detail so classification follows the *overall* shape. Training:
22,500 images (6000 each perturbed tet/prism/cube, 4500 Voronoi "other"),
60/20/20 split, Adam, batch 128, L2 reg 0.1, lr 1e-3, 50 epochs, ~15 min on a GTX
1050 Ti (MATLAB). Class "other" is under-represented on purpose so ambiguous cells
tend to receive a shape label; "other" (k-means) is reserved for cells that really
have no structure.

## Quality metrics (deterministic — reusable without any ML)

Both metrics come from the Attene et al. polytopal-quality benchmark
(arXiv:1906.01627) and are pure geometry:

- **Uniformity Factor**: `UF(P) = diam(P) / h`, with
  `diam(P) = sup{||x-y||, x,y in P}` and `h = max_i diam(P_i)` the mesh size.
  Range [0,1]; higher = more uniform element sizes across the mesh.
- **Ball Ratio**: `BR(P) = max{r : B(r) subset P} / min{r : P subset B(r)}`
  (inradius over circumradius); in practice they approximate the circumscribed
  radius by `diam(P)/2`. Range [0,1]; higher = rounder cells.

Complexity is measured by counts of vertices/edges/faces/elements plus total and
per-element refinement time.

## Experiments (baselines are deterministic)

- **Five unit-cube grids** (tet, cube, prism, random Voronoi, CVT), 3 uniform
  refinement sweeps, comparing diameter vs k-means vs CNN-enhanced. Diameter
  disrupts the grid structure and — despite the cheapest plane computation — ends
  up costliest because its low-quality children accumulate vertices. K-means gives
  the highest Ball Ratio; CNN gives the highest Uniformity Factor and the lowest
  entity counts/time. On the CVT grid the CNN labels cells "cube" and matches
  k-means quality at a fraction of the cost — genuine generalization (no CVT cells
  in training).
- **PARMETIS-agglomerated hinge** (9361 agglomerated tet sets; non-convex,
  stretched cells; out-of-distribution for the CNN), 1 refinement sweep. CNN
  labels 52% "tetrahedron" / 47% "other" / 1% "prism". Advantage over the diameter
  strategy is only slight in mesh complexity and quality; k-means wins Ball Ratio.
  The authors state the ML benefit compounds over *sequential* refinements and is
  modest for a single sweep, and that generalization must be re-assessed in new
  scenarios.
- **FEM error studies** (3D Poisson on the unit cube; uniform + fixed-fraction
  r = 0.4 adaptive refinement): with **VEM** (orders 1-3) the CNN strategy clearly
  wins — same error at fewer DoF (error curves shifted left), attributed to VEM's
  sensitivity to vertex proliferation/distortion since its DoF live on the
  boundary. With **PolyDG** all three strategies are comparable, and the winner
  even flips with the penalty parameter (diameter best at alpha = 10, CNN at
  alpha = 2) — interior DoF make PolyDG insensitive to cell shape.
- **No ML-vs-METIS partitioner comparison exists in this paper.** METIS/PARMETIS
  appears only as the producer of the hinge input mesh. The claim "ML beats
  METIS-style agglomeration" belongs to the group's later GNN-agglomeration papers,
  not this one.

## Limitations

- Refinement only; no agglomeration algorithm is proposed here.
- Only two quality metrics (UF, BR); the authors admit these miss multi-structure
  effects and small spikes (their Fig. 12). No non-orthogonality, skewness, face
  planarity, or FV-relevant metrics.
- Unit-cube domains plus one hinge; no CAD boundary conformity, no curved
  surfaces, no boundary-layer concerns.
- CNN quality depends on the training distribution; on the out-of-distribution
  hinge mesh the margin over the naive deterministic baseline nearly vanished.
- FEM (VEM/PolyDG) error is the arbiter; nothing transfers directly to OpenFOAM
  FV acceptance.

## AutoTessell applicability (AI-advisory constraint)

The paper's own architecture already matches our ROADMAP constraint: the CNN never
produces geometry. It only *selects among deterministic strategies*, and every cut
still passes the deterministic validity check + vertex-snap tolerance + emergency
perturbation loop. A wrong CNN label degrades quality/cost but cannot yield an
invalid mesh; a hard gate owns acceptance. This is the right template for any
future ML hook in `native_poly`: ML picks a branch, deterministic code executes
and gates it.

Direct deterministic reuse (no ML needed):

1. **UF/BR metrics** are one-line additions to the evaluator and give a
   cheap roundness/uniformity signal for poly cells that our current checker does
   not report.
2. **The k-means 2-seed cutting-plane split** (Algorithm 2) is a deterministic
   (fixable seed) way to split oversized or concave dual cells — exactly the
   mechanism `garimella2013_general_dual.md` card `POLY-CONCAVE-SPLIT1` needs a
   concrete plane-choice rule for. Combined with Algorithm 1's vertex snapping and
   small-edge/small-face validity gate, it avoids creating the sliver faces our
   polyDual quality pass currently has to clean up afterwards.
3. **The validity-check pattern** (reject topologically bad or sliver-producing
   cuts, then perturb) maps onto our transactional check-then-rollback style.

The CNN itself is low value for us now: our poly cells come from tet-mesh
dualization, not template refinement, and the classical strategies assume
FEM-style self-similar subdivision we do not perform.

## Falsifiable implementation cards

### `POLY-QUALITY-UFBR1`

Add deterministic Uniformity Factor (`diam(P)/h`) and Ball Ratio
(inradius / (diam/2)) per-cell metrics to the native poly quality report
(`core/evaluator/native_checker.py` + poly pipeline stats). Pass if both metrics
reproduce exact analytic values on unit cube/regular tet fixtures (BR cube =
(1/2)/(sqrt(3)/2), UF = 1 on a uniform grid), are invariant under rigid transform
+ uniform scale, and are emitted in the report for every poly mesh without
changing any acceptance decision (report-only first).

### `POLY-AGGLOM-KMEANSCUT1`

Implement the deterministic 2-seed k-means cutting-plane split (voxel-sample cell
interior, seeded/deterministic k-means, plane bisecting the centroid pair) with
Algorithm 1's gates: vertex snapping within `diam*1e-3`, rejection of cuts
producing edges/faces below threshold or non-manifold children, and bounded
plane-perturbation retry. Target: splitting oversized/concave dual cells flagged
by the star-shaped validity test. Pass if on concave fixtures every produced child
is star-shaped-valid, children volumes sum to the parent within tolerance, no new
edge/face is below the threshold, and repeated runs with the same seed are
bit-identical.

## Snowball references (max 5)

1. Antonietti & Manuzzi, *Refinement of polygonal grids using CNNs with
   applications to PolyDG and VEM*, JCP 452 (2022) 110900 — the 2D companion; DOI
   `10.1016/j.jcp.2021.110900`.
2. Attene et al., *Benchmark of polygon quality metrics for polytopal element
   methods*, arXiv:1906.01627 — source of UF/BR and a larger deterministic metric
   suite worth mining for the poly evaluator.
3. Bassi, Botti, Colombo, Di Pietro, Tesini, *On the flexibility of agglomeration
   based physical space DG discretizations*, JCP 231 (2012) 45-65 — already
   extracted locally (`papers/md/18_bassi_2012_extract.txt`).
4. Berrone, Borio, D'Auria, *Refinement strategies for polygonal meshes applied to
   adaptive VEM discretization*, Finite Elem. Anal. Des. 186 (2021) 103502 —
   deterministic direction-based polygonal refinement (the paper's non-ML basis).
5. Liu, Wang, Levy, Sun, Yan, Lu, Yang, *On centroidal Voronoi tessellation —
   energy smoothness and fast computation*, ACM TOG 28(4) (2009) — CVT foundation
   behind the k-means strategy.
