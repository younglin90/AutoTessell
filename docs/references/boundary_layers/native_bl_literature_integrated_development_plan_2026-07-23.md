# Native Boundary-Layer Meshing: Literature-Integrated Development Plan

Date: 2026-07-23  
Status: implementation plan, not a solved-quality claim  
Primary target: deterministic native tetrahedral volume meshing with full prismatic wall layers  
Secondary targets: shared surface sizing for native tri/quad and later transfer to native hex/poly

## 1. Executive decision

The current bottleneck will not be solved by further scalar tuning of wall shrink,
feature reduction, or the generic aspect-ratio threshold. The production path must
move from append-only prism construction to a validity-preserving shell-and-cavity
architecture.

The recommended engine is a hybrid of the six reviewed papers:

1. Use the 2022 visibility-graph method as the production feasibility skeleton for
   multiple normals at arbitrary manifold corners.
2. Use the 2017 generalized spherical Voronoi construction to propose canonical
   directions and topology, and as a geometric oracle for the visibility search.
3. Use the 2021 anisotropic source metric as the shared sizing contract for surface
   remeshing, boundary-layer placement, and core transition.
4. Bootstrap an extremely thin, strictly positive multilayer prism shell.
5. In strict mode, expand that shell with a bijective symmetric-Dirichlet/ARAP solve
   and an auxiliary air mesh.
6. Use the 2013 visibility-cavity operator for bulk replacement, local layer
   insertion, and deterministic recovery while preserving a valid tetrahedral mesh.
7. Use the 2019 entropy/FMM method only for concavity detection and adaptive
   topology fallback; it must not silently weaken a strict height contract.
8. Cut intersecting bulk tetrahedra and refill the remaining core under an explicit
   cell ledger. Appending prisms to an unchanged core cannot satisfy the present cap.

The first implementation should be a direct three-layer C++ truth prototype. The
coarse-thick-shell plus Hermite acceleration from the 2025 paper is a later
optimization, activated only after the direct method establishes correct contracts
and metrics.

## 2. Current measured bottleneck

The retained native-tet candidate has the following measured state:

| Quantity | Current value | Consequence |
| --- | ---: | --- |
| Wall faces | 788 | Three fixed layers require 2,364 prisms. |
| Existing core cells | 2,575 | An unchanged core yields 4,939 final cells. |
| Cell cap | 4,664 | At least 275 core cells must be removed or coarsened. |
| Requested first height | 0.001 | The score currently checks this declaration. |
| Requested growth | 1.2 | Three requested heights sum to 0.00364. |
| Realized total thickness | 0.001 | The actual effective first height is about 0.000274725. |
| Maximum generic aspect | 4,132.59 | This mixes intended BL anisotropy with degeneration. |
| Boundary skewness | 119.856 | This is a real quality failure, not a metric-only issue. |
| Internal skewness | 41.229 | The shell/core transition is also poor. |
| Maximum non-orthogonality | 89.998 degrees | A near-degenerate internal configuration remains. |
| Negative/duplicate cells | 0 | Topological validity alone is not the missing property. |

The strict total thickness is

\[
T = h_1\sum_{i=0}^{L-1}r^i
  = 0.001(1+1.2+1.2^2)
  = 0.00364.
\]

The current result therefore performs an undocumented adaptive compression while
claiming the requested first height. Contract correction is the first task.

There is also a validator defect: the native combined metric path samples at most
25,000 cells for the mesh-wide maximum aspect ratio. A sampled maximum cannot be a
production hard gate. In addition, the current ratio is based on pairwise vertex
distances and is not an element-class-aware CFD boundary-layer metric.

## 3. Evidence extracted from the papers

### 3.1 Aubry et al. 2017: spherical Voronoi multiple normals

The incident triangular faces and convex ridges of a corner are mapped to circular
edge and reflex-vertex sites on the unit sphere. A generalized spherical Voronoi
diagram then produces both the directions and the virtual-face connectivity.

Useful mechanisms:

- three bisector types: vertex/vertex, edge/edge, and vertex/edge;
- a distance-based, canonical topology instead of a fixed corner taxonomy;
- angular resampling of Voronoi cell boundaries into multiple normals;
- virtual strips that connect convex ridges to other ridges or real faces.

Limits relevant to AutoTessell:

- the implementation details for spherical parabolas and several robust predicates
  are not provided;
- the formulation assumes triangular input and locally uniform extrusion speed;
- concave shocks, global collisions, tangential adaptation, and core refill are not
  solved;
- reported difficult examples can invert after about five layers.

Decision: use this construction for candidate generation and a canonical preferred
topology, but verify all candidates through the 2022 visibility conditions.

### 3.2 Ye et al. 2022: visibility graph on an arbitrary manifold

The manifold around a vertex is converted into visible and feasible regions on the
unit sphere. Candidate normals become graph nodes; an edge exists only when the
shortest spherical arc remains feasible. A valid graph must satisfy both
normal-to-facet and normal-to-normal visibility.

Useful mechanisms:

- a finite multiple-normal solution for an oriented arbitrary manifold;
- H-partition into regions with equal face-visibility signatures;
- bitset-based face coverage and connected-subgraph search;
- spherical polygon reconnection for topology optimization;
- projected worst-angle optimization for normal positions;
- explicit stitching when neighboring feature vertices have different normal counts.

Limits relevant to AutoTessell:

- H-partition, connected-subgraph enumeration, and topology search are exponential
  without merging, pruning, and beam limits;
- using only one representative per region can lose a feasible connection;
- recursive tet/pyramid templates for all degenerate prism cases are incomplete;
- the strength is corner robustness, not uniformly better average prism quality.

Decision: use this as the production feasibility kernel, retaining multiple candidate
points per spherical region and validating against the original, unmerged face set.

### 3.3 Loseille and Lohner 2013: validity-preserving cavity insertion

The local mesh update is

\[
H_{k+1}=H_k-C_P+B_P,
\]

where the connected cavity is removed and its exterior faces are joined to the new
point. The key invariant is exact visibility: every new tetrahedron has positive
orientation. Existing layer tetrahedra are protected by excluding a constrained set
from the cavity.

Useful mechanisms:

- ball and shell adjacency for cavity construction;
- cavity growth across every face invisible from the proposed point;
- surface-component and non-manifold checks;
- constrained set `K` for preserving earlier layers;
- ordered insertion of three lifted triangle vertices to reconstruct a prism as
  three tetrahedra with shared hybrid provenance;
- bounded retry, normal merge, and multiple-normal insertion.

Limits relevant to AutoTessell:

- the input must already be a valid simplicial volume mesh;
- validity is preserved, but sizing and high quality are not guaranteed;
- insertion order matters because of non-tetrahedralizable Schonhardt-like cases;
- hybrid recovery beyond tet/prism provenance is a separate problem.

Decision: build a transactional C++ cavity kernel before converting to OpenFOAM
polyMesh. Do not continue expanding the current post-write append path.

### 3.4 Aubry et al. 2021: anisotropic sources

The normal physical size radiates continuously from a source as

\[
s(d)=(r-1)d+s_0,
\]

and is represented by an SPD metric whose eigenvalues are inverse squared physical
sizes. The paper's proxy combines sources while preserving the most restrictive
direction, then resolves a second direction in its orthogonal plane. Generic metric
intersection or log-Euclidean averaging can rotate or weaken the BL eigenstructure.

Useful mechanisms:

- BLV, BLV-Eikonal, and BLV-Eikonal-Multi source types;
- surface FMM and geodesic gradients for tangential sizing;
- curvature and nearby-component influence before surface remeshing;
- isotropic clipping and diffusion radius;
- AABB source bounds and lower-envelope pruning.

Limits relevant to AutoTessell:

- the AABB metric bounds are approximations, not a proven tight error bound;
- conservative pruning must be checked against exhaustive source evaluation;
- the source metric guides meshing but does not itself construct valid layers.

Decision: implement a separate C++ `native_metric_sources` module. Native tri and
native tet must consume the same proxy so the wall surface and volume transition are
not designed independently.

### 3.5 Aubry et al. 2019: entropy solution and tangential adaptivity

Concave ridges are treated as seeds of Eikonal shocks/Voronoi bisectors. A metric-
normalized surface FMM identifies short edges, folded fronts, and negative elements.
Recovery escalates from prism-diagonal swaps to collapse, cavity remeshing, and
Steiner insertion. Tangential split/collapse adapts the advancing front to the volume
sizing field.

Useful mechanisms:

- local shock detection instead of exact construction of the full 3D Voronoi diagram;
- diagonal propagation before a top-edge collapse;
- local and row/linelet-wide anisotropic refinement/coarsening;
- explicit recognition that virtual multiple-normal fans must be tangentially split;
- a robust fallback order from semi-structured to locally unstructured topology.

Limits relevant to AutoTessell:

- local shock handling does not solve collisions between distant fronts;
- fixed topology, exact isosurface following, and prescribed sizing cannot generally
  all be satisfied;
- the authors report poor minimum layer heights when collapse quality is unrestricted;
- Steiner fallback may violate local sizing.

Decision: use it as an adaptive-mode fallback and risk detector. It is not allowed in
strict mode unless the requested height and topology contract remain satisfied.

### 3.6 Ye et al. 2025: bijective full-layer prism generation

An extremely thin valid shell is deformed toward an ideal orthogonal target. A
symmetric-Dirichlet/ARAP energy is minimized with local SVD rotations and a global
sparse least-squares solve. An auxiliary air mesh shares the top-front nodes; keeping
all viscous and air simplices positive prevents local inversion and global front
self-intersection. A line search accepts only energy-reducing, positive steps.

Useful mechanisms:

- bootstrap height halving until the top front is intersection-free and every prism
  passes all signed tetrahedral sub-configuration tests;
- target adjustment in narrow gaps;
- symmetric-Dirichlet barrier against singular Jacobians;
- reusable sparse structure and positivity-preserving line search;
- optional thick single-layer solve, coupled top/bottom prism remeshing, and Hermite
  interpolation to regain many layers;
- a preservation layer that leaves room for isotropic core filling.

Limits relevant to AutoTessell:

- the sparse global solve dominates runtime and memory and may require 60-170
  iterations in the reported 3D examples;
- reported wall-clock times range from tens of minutes to hours;
- the method remains sensitive to the number of complex corners and poor input
  surface triangles;
- it can trade some prism quality for full coverage and does not prove convergence to
  the requested target;
- the accelerated Hermite path solves a geometry-compatible growth ratio and is not
  automatically an exact `h1/growth/total` implementation.

Decision: first test a direct three-layer solve at the current small scale. Add the
accelerated thick-shell route only if the direct method is correct but too slow.

## 4. Target architecture

```text
surface audit and provenance
  -> feature graph and manifold one-rings
  -> shared anisotropic source metric
  -> budgeted native surface redistribution
  -> spherical candidate and visibility graph
  -> thin positive prism shell
  -> strict bijective expansion OR adaptive entropy/cavity advancement
  -> preservation/exclusion band
  -> cut intersecting core tetrahedra
  -> constrained cavity/core refill
  -> element-class-aware full validator
  -> OpenFOAM polyMesh writer and evidence bundle
```

The solver remains native-first. Python may orchestrate experiments and bindings, but
geometry predicates, metric queries, BVH collision, sparse optimization, cavity
transactions, and exhaustive validation belong in C++.

## 5. Versioned boundary-layer contract

### 5.1 Strict mode

Strict mode treats the following as invariants:

- requested first height;
- requested growth ratio;
- requested layer count;
- implied total thickness;
- wall coverage and wall provenance;
- zero inverted, duplicate, non-manifold, or self-intersecting cells;
- final cell cap.

If geometry makes these incompatible, the engine returns a deterministic infeasibility
certificate. It must not emit a compressed mesh and label it strict.

### 5.2 Adaptive mode

Adaptive mode may alter local height, growth, layer count, and topology to maintain
coverage and validity. It must record, per column or feature component:

- requested and realized first height;
- requested and realized total thickness;
- requested and realized growth sequence;
- local compression ratio and reason;
- layer-count reduction;
- split/collapse/cavity/Steiner operations;
- minimum physical clearance and the limiting opposing primitive.

### 5.3 Feasibility and cell ledger

Before meshing, compute

\[
N_{core,max}=N_{cap}-N_{BL}-N_{transition}.
\]

For the current fixed topology, `N_BL = 788 * 3 = 2364`, hence
`N_core,max = 2300` when no extra transition cell is added. The current 2,575-cell
core must lose at least 275 cells. The preservation concept should initially reuse the
outermost requested layer or a core sizing exclusion band, not append another prism
layer.

## 6. Proposed C++ modules

### 6.1 `native_surface_feature_graph`

Responsibilities:

- orient and validate surface one-rings;
- classify smooth, convex, and concave ridges with hysteresis;
- retain patch, CAD, and original-wall provenance;
- expose feature chains for surface remeshing and normal stitching.

Core records: `LocalManifold`, `FeatureEdge`, `FeatureChain`, `PatchProvenance`.

### 6.2 `native_metric_sources`

Responsibilities:

- `Metric3` eigenframe and physical-size representation;
- BLV and Eikonal source construction;
- exhaustive and conservatively pruned queries;
- surface geodesic FMM and trianglewise gradients;
- diffusion radius, isotropic clipping, and nearby-source coupling.

The production pruning path is enabled only after randomized equivalence tests show
that it returns the same restrictive metric as exhaustive evaluation.

### 6.3 `native_spherical_normals`

Responsibilities:

- feasible spherical regions and maximum-inscribed-cap single normal;
- great-circle and vertex/edge bisector candidates;
- H-partition with visibility bitsets;
- exact spherical arc containment;
- connected set-cover branch-and-bound;
- topology beam and projected normal optimization;
- deterministic feature-chain stitching.

Retain several candidates per spherical region: center, Voronoi candidate,
boundary-safe point, and useful edge midpoint. All merged-region choices are checked
against original faces.

### 6.4 `native_prism_shell`

Responsibilities:

- bootstrap a tiny positive multilayer shell;
- store top/bottom correspondence and virtual-cell provenance;
- test all required prism subtetrahedron orientations;
- build the ideal strict or adaptive target;
- provide coupled split/collapse/swap/relocate transactions when remeshing is enabled.

### 6.5 `native_bl_bijective`

Responsibilities:

- target/current simplex Jacobians;
- stable symmetric-Dirichlet proxy weights, including the `sigma -> 1` limit;
- local SVD rotations and global Eigen sparse solve;
- auxiliary air mesh and dynamic top-front BVH;
- positivity- and energy-preserving line search;
- stagnation and infeasibility evidence.

The matrix sparsity pattern and symbolic factorization should be reused. Direct sparse
factorization is acceptable for the first truth prototype; iterative/preconditioned
alternatives are an optimization experiment, not a prerequisite.

### 6.6 `native_bl_cavity`

Responsibilities:

- tet neighbor topology and vertex-ball/edge-shell CSR;
- exact visibility cavity growth;
- constrained earlier-layer set `K`;
- transactional commit/rollback;
- deterministic insertion scheduling with bounded backtracking;
- normal merge and multiple-normal insertion;
- shared `hybrid_parent` provenance for prism reconstruction;
- core cut and constrained refill interface.

Every transaction is validated before commit. A failed candidate leaves the original
mesh byte-identical.

### 6.7 `native_bl_validator_v6`

Responsibilities:

- exhaustive, never sampled, hard gates;
- separate prism, tet, pyramid, hex, and generic-poly metrics;
- exact request-versus-realization evidence;
- mesh topology, wall provenance, envelope, and collision evidence;
- deterministic JSON report with metric witnesses and cell IDs.

## 7. Validator v6

### 7.1 Universal hard gates

- finite coordinates and indices;
- positive cell orientation/volume;
- no duplicate cells or duplicate geometric faces;
- manifold internal face incidence;
- boundary patch closure and wall provenance;
- top-front and nonadjacent-cell intersection-free result;
- final cell count not greater than the declared cap;
- byte-identical topology/coordinates for three repeated deterministic runs.

### 7.2 Prism gates

- all signed subtetrahedral configurations required by the prism validity model;
- minimum scaled Jacobian;
- equiangle and centroid skewness;
- base triangle quality;
- wall-normal alignment and first-layer orthogonality;
- side-face non-orthogonality and face weight;
- requested/realized height and growth errors;
- layer-to-layer tangential metric length and smoothness;
- top/front collision clearance.

Raw physical aspect ratio remains a diagnostic because anisotropy of order
`10^3-10^5` may be intentional. Metric-space aspect and determinant-based quality are
the meaningful hard checks. This does not excuse the current severe skewness and
near-90-degree non-orthogonality, which remain hard failures.

### 7.3 Tet gates

- exact signed volume;
- radius ratio or mean-ratio quality;
- minimum/maximum dihedral angle;
- sliver metric;
- metric-space edge lengths;
- interface face skewness and non-orthogonality.

### 7.4 Boundary and internal skew policy

Boundary and internal face skewness must be reported and gated separately. Any change
from the current single threshold requires an explicit validator version update and a
benchmark replay; it must not be introduced as a silent relaxation.

## 8. Implementation phases and falsifiable gates

### Phase 0: contract and validator correction

Deliverables:

- strict/adaptive configuration schema;
- requested/realized evidence fields;
- exhaustive element-class-aware C++ validator;
- removal of sampled maxima from production gates.

Acceptance:

- strict three-layer flat fixture realizes `h1`, `r`, and `T` within 1%;
- an intentionally inverted prism is rejected in every orientation;
- rigid transforms and uniform scale do not change dimensionless quality;
- the retained current mesh still fails skew/non-orthogonality;
- infeasible strict requests return a reason code instead of a mesh.

### Phase 1: shared metric and budgeted surface preparation

Deliverables:

- full SPD metric path through native edge operations;
- exhaustive BLV source query;
- feature-preserving split/collapse/swap/relocate under a fixed face budget;
- surface envelope and provenance checks.

Acceptance:

- rotating an anisotropic metric rotates selected operations;
- a planar BLV source matches the analytic size law;
- exhaustive and pruned source queries agree within numerical tolerance;
- surface fidelity and manifoldness pass after every committed operation;
- wall-face budget keeps `layer_count * wall_faces` inside the cell ledger.

### Phase 2: spherical multiple-normal first layer

Deliverables:

- feasible regions and single-normal trigger;
- convex-ridge fallback with exact face coverage;
- Voronoi-assisted candidates;
- visibility branch-and-bound and deterministic stitching;
- first-layer virtual tet/pyramid/prism templates.

Acceptance:

- planar fan selects one normal;
- sharp/mixed corner obtains full face coverage with positive first-layer cells;
- every graph edge has positive spherical feasibility clearance;
- cracks, duplicate cells, and non-manifold virtual edges are zero;
- graph/topology hashes are identical in three repeats;
- exhaustive small graph fixtures agree with the pruned search.

### Phase 3: direct strict three-layer bijective prototype

Deliverables:

- thin positive three-layer shell;
- air mesh;
- symmetric-Dirichlet local/global solver;
- exact positivity line search;
- fixed strict target and adaptive target experiment arms.

Acceptance:

- every accepted iteration is energy non-increasing;
- minimum signed volume stays positive and the top front remains intersection-free;
- strict target reaches at least 95% of requested thickness within the iteration cap,
  or emits a reproducible stagnation/infeasibility witness;
- three repeats are deterministic;
- quality comparison includes worst skewness, non-orthogonality, prism Jacobian,
  growth error, wall time, and peak RSS.

Reject any candidate that obtains a better score by silently shrinking the target.

### Phase 4: visibility cavity and core replacement

Deliverables:

- C++ cavity transaction kernel;
- constrained prism-parent insertion;
- deletion of core cells intersecting the BL shell;
- constrained refill and core coarsening under the ledger.

Acceptance:

- each cavity is connected and every exterior face is exactly visible from its new
  point;
- all committed tetrahedra are positive;
- external boundary keys and patch tags are unchanged;
- the current case has `core_cells <= 2300` and `final_cells <= 4664`;
- shell/core overlap, holes, and nonconformal faces are zero;
- transition tetrahedra pass their own quality gates.

### Phase 5: adaptive entropy and tangential operations

Deliverables:

- concave-edge seeded metric FMM;
- diagonal swap, collapse, cavity remesh, and controlled Steiner fallback;
- local and linelet/row tangential split/collapse;
- full realized-topology evidence.

Acceptance:

- no premature layer termination in the concave U/T-junction corpus;
- distant-front collisions are still caught by the global BVH path;
- adaptive height and topology changes are fully reported;
- minimum height and quality gates prevent the degradation acknowledged in the paper;
- this path is never called by strict mode unless all strict invariants remain true.

### Phase 6: accelerated thick-shell and Hermite route

Entry condition: the direct prototype is correct but fails the declared time/RSS
budget.

Deliverables:

- one thick bijective shell;
- coupled top/bottom prism remeshing;
- prescribed cumulative-height Hermite subdivision for strict mode;
- derivative rollback/smoothing and linear positive fallback.

Acceptance:

- at least 3x wall-clock or peak-RSS improvement over the direct route;
- no regression of strict `h1`, growth, layer count, or total thickness;
- no negative prism and no top-front self-intersection;
- quality remains within the predeclared regression envelope.

## 9. Benchmark corpus

### Analytic unit fixtures

- flat plate and planar triangle fan;
- convex cube corner;
- concave wedge and mixed convex/concave corner;
- narrow parallel plates with known clearance;
- near-coplanar ridge perturbations;
- rotated anisotropic metric and cylinder;
- deliberately inverted and self-intersecting prisms;
- cavities that require insertion-order changes or Steiner fallback.

### Research regression fixtures

- current retained native-tet hard-bracket case;
- U-shape concavity;
- T-junction and narrow-gap model;
- Sharov/chiffonade-like corner families;
- multi-element airfoil for nearby-source coupling;
- DLR-F6-like synthetic corner subset before any full industrial model.

Every benchmark stores input hash, configuration, topology hash, per-class quality
histograms, worst-cell witnesses, runtime, peak RSS, and the exact reason for any
rejection.

## 10. Autoresearch execution policy

Each experiment is a small, falsifiable card:

1. The planner declares one hypothesis, the exact files/modules in scope, benchmark
   cases, acceptance metrics, reject rules, and rollback rule.
2. A worker implements only that card in an isolated worktree.
3. A verifier rebuilds, runs the declared corpus, checks evidence independently, and
   rejects claim drift.
4. A critic compares against the retained baseline and confirms that no contract or
   validator was relaxed.
5. Only mechanically passing candidates are promoted. Failed candidates are archived
   with their evidence, not patched indefinitely in place.

Stop or redesign when:

- the spherical graph is locally valid but the requested strict height has a global
  collision witness;
- the input one-ring is not an consistently oriented manifold;
- cell-ledger feasibility fails before generation;
- a candidate improves an aggregate score while violating any hard invariant;
- only the first layer succeeds but the three-layer contract remains unverified;
- three consecutive cards fail for the same demonstrated architectural reason.

## 11. Immediate next run

The next native-only deterministic run should perform the following sequence:

1. Freeze the retained v5 output and evidence as an archive baseline.
2. Implement Phase 0 contract fields and the validator-v6 prism/tet split.
3. Re-evaluate the current mesh without changing geometry.
4. Implement a minimal C++ planar/corner spherical feasibility kernel.
5. Produce only one first layer on analytic fixtures; do not touch the bulk writer.
6. Add the direct three-layer thin-shell/air-mesh truth prototype on the current 788-
   face wall.
7. Run fixed strict target versus explicit adaptive target as separate experiment arms.
8. Only after shell validity is proven, connect the visibility cavity and enforce the
   `core <= 2300` ledger.

This sequence resolves the present ambiguity first: whether the strict request is
geometrically feasible and whether the quality failure originates in normal topology,
global shell deformation, or the shell/core interface.

## 12. Source and licensing policy

The papers are design references. Their algorithms should be independently
reimplemented and tested; text, figures, and unavailable source code must not be
copied. External C++ libraries may be adopted only after license compatibility and
attribution review. The native deterministic validity kernel remains authoritative;
machine-learning models may predict sizes, features, or candidates but cannot bypass
geometric hard gates.

## 13. Reviewed references

1. R. Aubry, S. Dey, E. L. Mestreau, B. K. Karamete, *Boundary layer mesh
   generation on arbitrary geometries*, International Journal for Numerical Methods
   in Engineering (2017), DOI: 10.1002/nme.5514.
2. H. Ye, J. Chen, T. Liu, Z. Xiao, J. Zheng, Y. Zheng, *Multiple normals
   configuration on an arbitrary manifold for viscous mesh generation*, International
   Journal for Numerical Methods in Engineering (2022), DOI: 10.1002/nme.7104.
3. A. Loseille, R. Lohner, *Robust Boundary Layer Mesh Generation* (2013),
   DOI: 10.1007/978-3-642-33573-0_29.
4. R. Aubry, S. Dey, E. L. Mestreau, M. Williamschen, W. Szymczak,
   *Anisotropic sources for surface and volume boundary layer mesh generation*,
   Journal of Computational Physics (2021), DOI: 10.1016/j.jcp.2020.109855.
5. R. Aubry, B. K. Karamete, E. L. Mestreau, C. Jones, S. Dey, *Entropy solution
   at concave corners and ridges, and volume boundary layer tangential adaptivity*,
   Journal of Computational Physics (2019), DOI: 10.1016/j.jcp.2018.09.030.
6. H. Ye, T. Liu, H. Ni, J. Chen, *Robust full-layer prismatic mesh generation
   based on bijective mapping*, Journal of Computational Physics 524 (2025) 113744,
   DOI: 10.1016/j.jcp.2025.113744.

The corresponding PDFs and verified hashes are indexed in
`docs/references/mesh-quality/README.md`.
