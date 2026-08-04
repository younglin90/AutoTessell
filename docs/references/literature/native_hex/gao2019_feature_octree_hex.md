# Gao 2019 - Feature Preserving Octree-Based Hexahedral Meshing

## Bibliographic record

- Xifeng Gao, Hanxiao Shen, Daniele Panozzo, *Feature Preserving Octree-Based
  Hexahedral Meshing*, Computer Graphics Forum 38(5) (SGP 2019), pp. 135-149.
- DOI: `10.1111/cgf.13795`
- Legal open manuscript: <https://cims.nyu.edu/gcl/papers/2019-OctreeMeshing.pdf>
- Local PDF: `docs/references/papers/source/pdf/33_gao_2019_feature_octree_hex.pdf`
  (SHA-256 `992d72ad3bd94e83f904d1b87949430d22675c686de7190531af14c552aba8f2`)
- Status: `FULL_READ` (15/15 pages, 2026-07-23). Pages 13-15 are references.
- Reference implementation vendored in-repo: `Feature-Preserving-Octree-Hex-Meshing/`.

## Problem and claimed scope

Input: manifold, watertight, self-intersection-free triangle mesh with annotated
sharp features, a Hausdorff tolerance `eps`, and a target edge length `l`. Output
claim: a *pure* hexahedral mesh that (1) is manifold, (2) has positive scaled
Jacobian at all eight corners of every hex (Verdict/[SEK*07] definition), (3) stays
within `eps` of the input surface, and (4) has no boundary self-intersections. The
authors call such a mesh *valid*. Guiding principle: satisfy each validity property
once, then never leave the valid space during later stages.

## Algorithm read from the paper

1. **Octree** (Sec 3.1). Recursively split bounding-box cells that intersect the
   surface or contain an input vertex, with max edge <= `l`. Enforce Marechal's two
   rules: *balancing* (neighbor level difference <= 1) and *pairing* (if one child
   splits, its siblings split too).
2. **Dual all-hex conversion** (Sec 3.2) — the paper's key structural trick, and
   the difference from Marechal's primal hanging-node templates: view the octree as
   a *conforming hybrid polyhedral* mesh and take its dual.
   - 2D: a hanging node dualizes to a triangle; pairing makes triangles appear in
     pairs enclosing a quad — a *trapezoid* — always isolated in a sea of quads.
     One local split (2 added vertices) makes each trapezoid all-quad; no
     propagation.
   - 3D: a hanging node dualizes to a pyramid; pairing makes four pyramids + 1 cube
     + 4 triangular prisms co-occur as a *3D frustum*, split into 13 hexes by
     adding 12 vertices. Boundary insertion creates exactly **three** types of
     neighboring polyhedra (between frustums at same level; touching frustums at
     different levels), each with its own fixed splitting rule (Fig 5). Result is
     pure-hex and inversion-free by construction (axis-aligned geometry).
   - Cells are segmented inside/outside; the outside part is kept as a **scaffold
     mesh** [JSP17] that surrounds the target mesh and blocks global
     self-intersection throughout all later deformation.
3. **Feature matching** (Sec 3.3) — topology first, geometry later. The feature
   annotation partitions the input surface into corners, curves, and patches.
   Corner configurations that an octree boundary cannot represent (valence > 6) or
   that force distortion (angle < 30 deg) are tagged *invalid*: validity is still
   maintained around them but exact preservation is not enforced.
   - Corner map: each feature corner -> spatially closest quad-mesh vertex.
   - Curve map: sample each input feature line at spacing `l/2`, project samples to
     closest points on quad-mesh edges, build a per-vertex distance field to the
     mapped samples, then trace the curve by **weighted Dijkstra** on quad-mesh
     edges. Each traced curve becomes a *cut* for subsequent traces, so mapped
     curves can never cross.
   - Patch map: extract patches bounded by the mapped feature graph on both
     domains, match by composed nodes/curves, and verify the correspondence in
     **both directions** to establish patch bijectivity.
   - Failure fallback: if patch topology differs, split octree cells intersecting
     the input patch; if Dijkstra finds no path, split cells intersecting that
     feature line; rebuild and retry. Terminates in 1-2 iterations in practice.
4. **Variational padding + untangling** (Sec 3.4). Two feature classes:
   - *Soft* (high-frequency concave) features: pad **globally** — offset the whole
     boundary polyline/surface both inward (target mesh) and outward (scaffold),
     adding one hex layer on each side; the extra DOF resolves the inversions that
     concave capture would otherwise force.
   - *Hard* (sharp) features: an element with >= 2 feature-labeled edges
     degenerates; pad **locally** — take the degenerate elements plus one
     expansion ring, offset the local boundary inward, and insert one hex ring.
   - *Untangling*: disassemble the affected hexes into independent unit cubes,
     then minimize `E = E_D + lambda_S * E_S`, where `E_D` is the [GPW*17]
     distortion (each hex = 8 corner tetrahedra, symmetric Dirichlet
     `||J||_F^2 + ||J^-1||_F^2` vs a right-angled ideal corner tet of equal
     volume) and `E_S` is a quadratic cluster-contraction stitching term [FL16]
     (`lambda_S` ramped from 1 up to 1e16 by the FL16 rule). Minimized with SLIM
     [RPPSH17] using flip-avoiding line search on the corner tets; vertex clusters
     are merged only when the merge introduces no negative Jacobian.
5. **Geometric fitting** (Sec 3.5). Minimize `E_D + lambda_B * E_B` with the
   [GPW*17] feature term: corner -> exact point, curve sample -> point + tangent
   sliding via auxiliary variable, generic boundary vertex -> point-to-tangent-
   plane. `lambda_B` starts at 50, same ramp. Corners with angle < 30 deg are
   filtered from exact preservation (optional). The scaffold boundary is left
   *free* (contra [JSP17]) for faster convergence, and would be frozen only on
   detected self-intersection — never triggered in their experiments.
6. **Stopping / outer loop** (Sec 3.6). At most 30 fitting iterations; stop early
   when (a) max Hausdorff distance <= `eps` (measured with Metro) and (b) average
   surface deviation changes < 1% between iterations. Otherwise force-split the
   octree cells intersecting out-of-bound hexes and restart from step 2. `l` and
   `eps` are the only user parameters.

## Guarantees: proved vs empirical

- **By-construction (strong):** the dual conversion yields pure hex, conforming,
  inversion-free output — the trapezoid/frustum case analysis is exhaustive given
  balancing + pairing, and the initial embedding is axis-aligned. This part is
  effectively a proof sketch, not just an experiment.
- **Invariant maintenance (mechanism, not proof):** positivity of the 8 corner
  Jacobians is preserved because every geometric change goes through SLIM's
  flip-avoiding line search, and every topological merge is accepted only if it
  keeps all Jacobians positive. This makes each *accepted* state valid — a
  transactional design — but the paper explicitly says it **cannot prove** that a
  locally injective fit satisfying the constraints always exists; the refinement
  fallback is the escape hatch, validated empirically on 202 models.
- **Self-intersection freedom:** by scaffold construction, checked empirically.
- **Known soundness gap (stated by the authors):** positive scaled Jacobian at 8
  corners is *necessary but not sufficient* for a bijective trilinear map. 5 of
  202 outputs contained exactly one non-bijective boundary element each. They
  point to conservative tests (Johnen 2017 [JWR17]; Zhang 2019 subtet test) as
  the missing integration.
- **Assumes clean input:** manifold, watertight, no self-intersections, and
  *correct feature annotation* — dihedral threshold 140 deg plus manual fixes for
  incomplete rings, missing small features, spurious near-duplicate features.

## Experiments

- 202 models: 93 organic [FBL16] + 109 manually annotated CAD. 100% meshed with
  fixed parameters `l = b/2^6`, `eps = 0.005 d` (d = bbox diagonal), no tuning.
- Feature preservation error / diagonal (min/avg/max): corners 0 / 7.1e-5 /
  9.6e-4; curves 4e-10 / 2.1e-4 / 1.1e-3; patches 5.4e-5 / 6.1e-4 / 3.5e-3.
- vs MeshGems-Hexa [Mar09/Mar16]: consistently higher minimum scaled Jacobian
  (e.g. cheese: 0.142 vs 0.009), similar average SJ (MeshGems favors many perfect
  interior cells, Gao spreads distortion), fewer elements (often 5-10x fewer),
  and *bounded* Hausdorff (always < eps) where MeshGems has high HR variance.
- Cost is the flip side: single-thread minutes-to-hours (worst > 20 h,
  red_circular_box ~1194 min) vs seconds for MeshGems; 60 GB reserved memory per
  process; padding/untangling + fitting dominate ~10x the memory of the octree
  stages. Runtime grows ~linearly with output hex count.
- Singular-edge ratio is essentially uncorrelated with `eps` (Fig 11): tighter
  tolerance buys fidelity, not structural regularity.

## Limitations (authors' own)

1. Large memory footprint (global SLIM assembly).
2. Long runtime (locally injective volumetric parametrization at scale).
3. Positive corner scaled Jacobian does not imply trilinear bijectivity (5/202
   affected; single boundary element each, discardable for Poisson but not for
   nonlinear elasticity).
Additional observed limits: no control of interior singularity placement (fixed by
octree adaptivity — inferior to field-aligned methods when those succeed);
sub-30-degree corners deliberately not preserved; feature annotation needs manual
repair on real CAD tessellations.

## Vendored code vs paper (`Feature-Preserving-Octree-Hex-Meshing/`)

The vendored C++ implements the full paper pipeline; stage-to-code map:

- Octree + balancing/pairing: `grid_meshing/octree.cpp`; flags `graded`,
  `paired = true` in `grid_meshing/grid_hex_meshing.h:138`.
- Dual all-hex conversion: `dual_octree_meshing -> octree_mesh -> conforming_mesh
  -> dual_conforming_mesh -> connectivity_modification`
  (`grid_meshing/grid_hex_meshing.h:54`) — the frustum/polyhedron splitting rules
  of Figs 4-5 live in `connectivity_modification`.
- Scaffold: `scaffold(Mesh_Domain&)` at `grid_meshing/grid_hex_meshing.cpp:2125`
  (`scaffold_type`, `scaffold_layer` args).
- Feature matching: `surface_mapping` -> `node_mapping`, `curve_mapping`
  (DijkstraComputePaths at `grid_meshing/grid_hex_meshing.cpp:2617`),
  `patch_mapping` / `patch_trees` (`grid_hex_meshing.h:66-72`).
- Padding + untangling: `mesh_padding` (global, `grid_hex_meshing.cpp:3058`) and
  `local_padding` / `padding_arbitrary_hex_mesh_step1/2` (hard features);
  SLIM + stitching in `slim_m.cpp` and `optimization.cpp`.
- Fitting + stop: `deformation`, `feature_alignment`,
  `stop_criterior_satisfied` + `hausdorff_ratio_check`, with Metro vendored as
  `metro_hausdorff.cpp`.

No paper stage is missing from the code; the code additionally has a voxel (non
octree) path (`voxel_meshing`) and mesh cleaning (`clean_hex_mesh`,
`drop_small_pieces`) not detailed in the paper.

## AutoTessell applicability

- **Surface deviation control.** Gao's `eps` is a hard outer-loop gate on *max*
  Hausdorff enforced by targeted refinement (split only cells whose hexes break
  the bound). Our `wall_dev < 0.02` gate is a post-hoc check; the portable idea is
  the *closed loop*: when wall_dev fails, refine exactly the offending octree
  cells and re-run projection instead of failing the mesh. Their measured bound
  (0.5% of diagonal, always met) is far tighter than our 0.02 gate, but paid for
  with minutes-to-hours of SLIM time — our budget will not absorb the full
  deformation machinery, only the targeting logic.
- **Feature provenance (the Phase-3 answer).** The paper gives the implementable
  recipe the provenance card needs: (1) corner -> nearest boundary vertex,
  assigned once; (2) curve -> Dijkstra trace over boundary edges weighted by a
  distance field to `l/2`-spaced curve samples, with already-traced curves acting
  as cuts; (3) patch -> bidirectional correspondence check over the induced
  feature graph. Identity is *topological and assigned once*; per-iteration
  motion then only slides along the assigned entity (tangent constraint with
  auxiliary variable). This is exactly "stable face/ridge/corner provenance"
  as opposed to our current per-iteration nearest-feature re-search.
- **Validity discipline.** The "enter valid space once, never leave it" pattern —
  accept a merge/move only if all corner Jacobians stay positive — matches and
  strengthens the HEX-OCT-4 transaction design. Note their honesty about the
  ceiling: corner-positive is not trilinear-bijective; a census/gate should say
  "positive corner SJ" rather than "valid hex" unless a subtet/Johnen test runs.
- **Padding.** The soft/hard feature padding split is the literature version of
  pillowing-at-features; it presupposes the untangling optimizer, so it belongs
  with HEX-SHEET-2 (pillowing) rather than as a standalone port.
- **What not to port.** The global SLIM deformation and scaffold (60 GB, 20 h
  worst case) are out of budget for a production gate; use the vendored binary as
  a reference oracle for provenance tests, not as an inline engine.

## Card confirmations / refinements

- **HEX-OCT-4 (constrained projection transaction) — CONFIRMED, refined.** Gao
  independently validates the transaction pattern at scale: flip-avoiding line
  search = the "trial move + commit on validity" rule; cluster merges gated on
  Jacobian positivity = the same rule for topological edits. Refinement to the
  card: add the paper's caveat that the positivity floor should be understood as
  corner-tet positivity, necessary but not sufficient for element bijectivity
  (aligns with the existing beta-margin upgrade from Knupp / HEX-UNTANGLE-1).
- **Feature provenance card (P1, `evidence_matrix.md`) — CONFIRMED with concrete
  algorithm.** Corner/curve/patch topological assignment + Dijkstra-with-cuts +
  bidirectional patch check is the published, code-available mechanism. The
  plan's decision rule stands: Gao 2019 supplies *target identity*; vertex
  *motion* stays inside our measured guarded snap (t* mechanism) — the paper's
  tangent-sliding constraint is precisely compatible with that split, since it
  also separates "which entity" (fixed) from "where along it" (optimized).
- **HEX-OCT-2 (transition contract) — supporting evidence for Option A.** The
  trapezoid/frustum dual construction is a second, simpler published route to
  all-hex transitions (3 boundary polyhedron types with fixed splits), vendored
  and testable; it competes with Pitzalis 2021 templates as the all-hex path.
- No new card names required.

## Snowball references (<= 5)

1. [JSP17] Jiang, Schaefer, Panozzo 2017, *Simplicial Complex Augmentation
   Framework for Bijective Maps*, ACM TOG 36(6) — the scaffold mechanism.
2. [RPPSH17] Rabinovich, Poranne, Panozzo, Sorkine-Hornung 2017, *Scalable
   Locally Injective Mappings* (SLIM), ACM TOG 36(2) — the solver.
3. [FL16] Fu, Liu 2016, *Computing Inversion-Free Mappings by Simplex Assembly*,
   ACM TOG 35(6) — the stitching/untangling formulation.
4. [GPW*17] Gao, Panozzo, Wang, Deng, Chen 2017, *Robust Structure
   Simplification for Hex Re-meshing*, ACM TOG 36(6) — distortion + feature
   energies; also the post-process coarsening they recommend for IGA.
5. [JWR17] Johnen, Weill, Remacle 2017, *Robust and Efficient Validation of the
   Linear Hexahedral Element*, arXiv:1706.01613 — the bijectivity test that
   closes the positive-corner-SJ gap.

## Decision

Adopt Gao 2019 as the primary source for the Phase-3 feature-provenance card
(corner/curve/patch assignment algorithm) and as corroboration of the HEX-OCT-4
transactional projection design; use the vendored implementation as a test oracle.
Do not port the global SLIM deformation, scaffold, or padding-untangling loop into
the production path — their cost profile (hours, tens of GB) contradicts our
engine budget; only the targeted-refinement-on-deviation loop and the
assign-once/slide-along provenance split are portable.
