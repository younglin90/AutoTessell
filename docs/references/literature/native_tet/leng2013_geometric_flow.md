# Leng, Zhang & Xu — Geometric Flow Quality Improvement for Multi-Component Tet Meshes (2013)

**Title:** A Novel Geometric Flow Approach for Quality Improvement of Multi-Component Tetrahedral Meshes
**Authors:** Juelin Leng (CAS), Yongjie (Jessica) Zhang (CMU), Guoliang Xu (CAS)
**Year / Venue:** 2013, Computer-Aided Design 45(8):1182–1197
**DOI:** `10.1016/j.cad.2013.05.004`
**Pages read:** 16/16 (published journal version; extends IMR-20 2011 conference paper [27])
**Status:** FULL_READ (PDF: `docs/references/papers/source/pdf/11_leng_2013_geometric_flow_quality.pdf`)
**Date:** 2026-07-23

## One-line summary

Post-processing quality improvement for segmented multi-component tet meshes
(octree/iso-contouring output): classify vertices into 4 groups, fair boundary
curves/surfaces with volume-preserving geometric flows (normal motion), regularize
them with tangential-only L2-gradient flows, smooth all vertices against a
penalized aspect-ratio energy, and interleave with face-swap/edge-removal — no
vertex insertion, vertex count preserved.

## Core algorithm

### Vertex classification (Section 2.2)

Given a mesh of components {T_i} conforming at interfaces:
- **Boundary surface patch** = common surface of two components, plus each
  component's exterior boundary.
- **Boundary curve** = curve shared by ≥ 2 surface patches.
- **Corner vertex** = vertex shared by ≥ 2 boundary curves.

Four vertex groups, each with its own update rule:
1. **Interior vertices** — free 3D relocation.
2. **Surface vertices** — manifold vertices on a patch; move along the **normal**
   (fairing) and along the **tangent plane** (regularization + smoothing).
3. **Curve vertices** — on boundary curves; move along curve **normal** (fairing)
   and curve **tangent** (regularization + smoothing).
4. **Fixed vertices** — corner vertices and all other **non-manifold vertices**;
   never moved.

### Quality metric (Section 2.3)

Volume-to-length ratio of Liu & Joe: `Q = 8·3^(5/2)·V / (Σ e_j²)^(3/2)` ∈ [0,1]
(1 = regular tet). Chosen because it detects all sliver classes, including
near-coplanar tets that pass longest/shortest-edge and min-dihedral tests.
Boundary triangles use the analogous area-to-length ratio `4√3·A / Σ e_j²`.

### The four geometric-optimization stages (Sections 3.1–3.5)

1. **Curve fairing — curve diffusion flow** (Eq. 3.1):
   `dx_i/dt = −(Δκ_i) n_i` — a 1D analogue of surface diffusion. κ_i, n_i are
   discretized from the quadratic curve interpolating x_{i−1}, x_i, x_{i+1}
   (Theorem 3.1: linear convergence, quadratic for uniform sampling). Δκ is a
   second difference over arc length. Solved with **explicit Euler** (Eq. 3.3),
   endpoints clamped. Degenerate normal (collinear points) regularized as
   `n_i = κ_i/(κ_i + ε)`, ε = 0.001. Property: arc-length shortening,
   **area-preserving** for closed orientable curves — motion is purely normal.
2. **Curve regularization** (Eqs. 3.5–3.6): energy
   `E = ½ Σ (‖x_i − x_{i−1}‖ − h)²` with h = mean edge length; L2-gradient flow
   restricted to the **tangential direction only** (Φ_i = e_i, tangent from
   quadratic fit). Equidistributes vertices along the curve.
3. **Surface fairing — Averaged Mean Curvature Flow (AMCF)** (Eq. 3.10):
   `∂x/∂t = [H(x) − h̄(t)] n(x)` with h̄ the surface-average mean curvature and
   patch boundary curves held fixed (∂S(t) = Γ). Theorem 3.2 proves
   dV/dt = ∫ v_n dA = 0, so the flow is **volume-preserving** (per component, in
   the integral sense) while it removes bumpiness by **normal motion**. Discrete
   H, n from local quadratic fitting; h̄ via mass-lumped Voronoi-like vertex
   areas (mixed circumcenter/midpoint, Fig. 3.4). Explicit discretization.
4. **Surface regularization** (Eqs. 3.11–3.12): edge-length equidistribution
   energy over 1-rings, `h = (4/√3 · Ā)^{1/2}`; gradient projected onto the two
   orthogonal **tangential directions** e_i^(1), e_i^(2) (from Loop-subdivision
   limit surface or quadratic fit). Tangential-only by construction.
   Discussion 3.1: local h_i variant proposed for adaptive meshes but the
   experiments all use a global h.
5. **Optimization-based mesh smoothing** (Eqs. 3.13–3.16): penalized active-set
   objective `E = Σ_{η∈T_q} (Q̄_η − q)^p`, Q̄ = 1/Q ∈ [1,∞), active set
   `T_q = {η : Q_η ≤ 1/q}`, parameters **p = 4, q = 1/0.9** (i.e. only tets with
   Q ≤ 0.9 are penalized; p = 4 punishes the worst tets hardest). Gauss–Seidel
   style vertex-by-vertex descent; search direction is the negative first
   variation projected per class: interior → full R³; surface → tangent plane;
   curve → curve tangent; fixed → zero. Step α line-searched so that the
   **worst local quality strictly improves**. Active set updated after every
   vertex move. (Vs. Stellar: Stellar optimizes only the single worst adjacent
   tet; here all bad neighbors contribute.)

### Step control and inversion safety

- All flows use explicit Euler; per-iteration vertex displacement capped at
  **1% of the average edge length** (step size adaptively reduced to enforce it).
- **Inversion guard** (Remark 3.1): after any candidate relocation from flows
  (3.1), (3.6), (3.10), (3.12), if any incident tet inverts, multiply τ by
  0.618 and retry until no inversion. All tets stay positive throughout.
- Fairing stops "once the bumpiness is removed" (no formal stopping criterion).

### Topological transformations (Section 3.6, Algorithm 3.1)

Operation set: **2–3 flip, 3–2 flip, 4–4 flip, 2–2 flip** (boundary edge shared
by two tets), plus **edge removal** (Shewchuk [15]) for edges of valence > 4,
implemented as a sequence of 2–3 flips ending in a 4–4 flip (interior) or a 2–2
flip (exterior boundary, half-ring). A dedicated **boundary edge removal**
retriangulates the two polygons left on an interface after removing a boundary
edge, maximizing the worst new tet.

Trigger/scheduling: transforms run only on tets with `Q < ε`; for each bad tet,
all 4 face removals and all 6 edge removals are *tried*, and the single
operation that maximizes the worst quality of the new tets is applied — only if
it beats the current Q_η. Operations are **rejected if the boundary would be
ruined or the local min quality would decrease**. Because the octree generator
produces structured interior tets, edge removal is applied only to boundary
edges in practice.

### Overall schedule (Algorithm 3.2)

1. Interior smoothing → curve fairing → interior smoothing → curve
   regularization → interior smoothing → surface fairing → interior smoothing →
   surface regularization (interior smoothing is interleaved because boundary
   motion degrades near-boundary tets; fairing must precede regularization
   because tangents of a non-smooth curve/surface are unreliable).
2. Global mesh smoothing (3.16) for all non-fixed vertices.
3. `for l = 1..5: TopologicalTransformation(0.3 + 0.1·l, L=2); smoothing` —
   a rising-threshold ladder (ε: 0.4 → 0.8) that alternates hill-climbing
   smoothing with topology changes to escape local optima.

## Boundary handling vs. AutoTessell's surface-preservation invariant — WARNING

**This method deliberately moves boundary vertices, including in the normal
direction.** Curve fairing (3.1) and surface fairing (AMCF, 3.10) are
*designed* to displace boundary vertices off the input surface to remove
segmentation/voxel bumpiness; the input surface is treated as noisy, not as
ground truth. "Shape preservation" in this paper means (a) per-component
**volume** is preserved to ~0.1% (integral property of AMCF, not pointwise),
(b) patch boundary curves are clamped during surface fairing, and (c) corners
and non-manifold vertices are pinned. Vertices with sharp-feature (ridge) tags
are extracted into curves in preprocessing, so features survive as curves — but
the geometry between features is smoothed.

This **directly violates AutoTessell's #1 invariant** (pre-meshing surface must
be preserved exactly). Any port must drop the fairing stages entirely. The
paper does contain clean **tangential-only modes** that are separable:
- curve regularization (3.6) — tangent-projected,
- surface regularization (3.12) — tangent-plane-projected,
- the boundary branches of optimization smoothing (3.16) — tangent-projected.

Caveat even for these: the "tangent plane" comes from a quadratic-fit /
Loop-limit smooth proxy, so on a faceted CAD surface a tangential Euler step
still drifts off the exact input geometry (chord error at curved regions,
crossing facet ridges). An exact-preservation port must add a
**project-back-to-input-surface step** (closest point on the original triangle
patch, with barriers at feature edges) after every tangential move, or restrict
motion to within the current facet. On truly planar patches tangential motion
is exactly surface-preserving.

## Multi-component / non-manifold handling

- "Component" = a volumetric region of a segmented domain (grain, tissue,
  material) — components conform at shared interfaces; each tet carries a
  component index, boundary faces carry the pair of component indices.
- Interfaces are first-class boundary surface patches; the AMCF's volume
  preservation guarantees no component "invades" its neighbor (measured:
  Σ|ΔV| = 0.1% for 92-grain, 0.09% for 52-grain, 0.18% for ATcpnα).
- Non-manifold junctions are handled by demotion: curves shared by ≥ 2 patches
  become 1D flow problems; corner/non-manifold vertices are frozen. This is the
  paper's main structural idea — dimension-reduce the non-manifold locus rather
  than trying to smooth across it.
- Vertex insertion is explicitly avoided because inserting near non-manifold
  boundaries "will ruin the boundary" — flagged as the open problem.

## Experiments

- **Single-component vs Stellar** (12 Klingner/Shewchuk meshes with random
  boundary perturbation of 0.2× avg edge length added): comparable min dihedral
  / min Q to Stellar overall, better on semi-structured meshes (DRAGON: min
  dihedral 9.8°→33.0° vs Stellar 24.1°; COW: 7.1°→25.1° vs 17.3°) because
  Stellar barely moves boundary vertices; clearly worse on fully random meshes
  (RAND1: 0.22 vs Stellar 0.36 min Q; RAND2: 0.13 vs 0.16) — no vertex
  insertion to break local optima. Consistently better boundary-triangle
  quality. **5–30× faster** (STAYPUFT 102k tets: 188.5 s vs Stellar 5619.3 s;
  vertex count unchanged, tet count ±<1%).
- **92-grain Ti alloy** (58k verts / 333k tets): min Q 0.001 → 0.26, min
  dihedral 0.07° → 13.3°, 658 s. Geometric optimization alone ("Improved I")
  only reaches min Q 0.009 — **topological transforms are essential** for
  bad-valence residuals.
- **52-grain Ti alloy** (512k verts / 3.0M tets): min Q 0.01 → 0.36, min
  dihedral 0.49° → 15.7°, 2657 s (~44 min for 3M tets, C++, 2.83 GHz single
  core).
- **ATcpnα biomolecule** (164k verts / 730k tets): min Q 0.001 → 0.33, avg
  0.68 → 0.78.
- **41-component brain surface mesh** (97k verts / 211k triangles, surface-only
  pipeline + edge flips): all angles into [17.6°, 131.7°], avg area-to-length
  0.82 → 0.91, 206 s.

## Limitations

Stated:
- Weak on very poor/random meshes; gets stuck in local optima without vertex
  insertion, and insertion near non-manifold boundaries is unsolved.
- Vertex count is fixed by design (no refinement/coarsening).
- Global uniform h in regularization energies (local h_i only sketched) —
  fights sizing gradation on adaptive meshes.
- Explicit Euler ⇒ small steps (1% avg edge/iter); many iterations.

Inferred:
- **No exact boundary preservation** — approximate volume preservation only
  (see warning above); unacceptable as-is for AutoTessell Phase-1 output.
- No formal quality guarantees or termination proof; hill-climbing heuristic.
- Min dihedral after improvement (13°–16°) is decent for FEM but below what
  fTetWild-class optimization reaches on clean single-material input.
- Quadratic-fit curvature/tangent estimation assumes locally smooth, dense
  sampling; on coarse CFD-grade surface meshes the fitted tangent plane can be
  poor near high curvature.
- No boundary-layer / anisotropy awareness; the equidistribution energy
  actively destroys intentional anisotropic spacing.

## AutoTessell applicability

Evidence-matrix row (Leng 2013): "test as post-improvement stage for
multi-component meshes and patch-separated regions only" — **confirmed by full
read, with a sharpened constraint: only the tangential/interior machinery is
admissible; the fairing flows (normal motion) must be excluded** because they
modify the surface. The interior penalized smoothing (p=4 active-set energy) is
a strict upgrade over the plain interior Laplacian already used in native_poly,
and the tangent-projected boundary smoothing is a candidate for the open
near-wall problems, provided an exact on-surface projection is added.

### Candidate cards

- **TET-FLOW-1 — Tangent-projected boundary vertex smoothing with exact
  surface re-projection.**
  Mechanism: optimization smoothing (3.15/3.16) for surface/curve vertices with
  search direction projected to the tangent plane, followed by closest-point
  projection back onto the *original* input surface triangulation (barrier at
  feature edges; curve vertices constrained to their feature polyline).
  Target: CYLSKEW near-wall skew and naca residual skew ~60.3, where boundary
  vertices are currently frozen and interior-only smoothing plateaus.
  Acceptance: max skew / min dihedral improves on CYLSKEW + naca benches; every
  boundary vertex lies exactly on the input surface (distance = 0 to source
  patch, feature vertices on feature curves); zero inverted cells; surface
  Hausdorff check passes at machine tolerance.
  Risk: projection can stall or oscillate at facet ridges; tangent from a
  smooth proxy vs faceted truth may point off-patch near high curvature —
  needs per-patch clamping and the 0.618 backtracking guard.

- **TET-FLOW-2 — Penalized active-set interior smoothing (replace plain
  Laplacian).**
  Mechanism: energy Σ_{Q≤0.9} (1/Q − 1/0.9)^4 minimized vertex-by-vertex with
  worst-local-quality line search and inversion backtracking (τ ← 0.618τ);
  interior vertices only, boundary untouched — fully invariant-safe.
  Target: FSL coplanar-flat wedge slivers and generic min-Q lift in native_tet
  / native_poly (native_poly currently uses plain interior Laplacian, which the
  paper's own taxonomy notes can degrade or invert elements).
  Acceptance: min volume-to-length Q and sliver count improve on the FSL bench
  and the 12-STL quality matrix vs the Laplacian baseline; no boundary vertex
  displacement (bitwise); no runtime regression > 2× on the bench.
  Risk: local optima on very bad regions (paper's RAND result) — must be
  paired with existing flip passes; per-move active-set updates cost O(ring).

- **TET-FLOW-3 — Rising-threshold smoothing/flip ladder scheduler.**
  Mechanism: Algorithm 3.2's outer loop — alternate smoothing with a transform
  pass over tets with Q < ε, ε stepping 0.4 → 0.8; for each bad tet, try all
  4 face flips + 6 edge removals, apply the argmax-of-worst-new-quality op,
  reject if local min quality drops or a boundary facet would change.
  Target: residual bad-tail after native_tet's existing improvement stage
  (naca-class residual skew), and multi-component/patch-separated meshes when
  boolean-merge lands (the paper's Improved-I vs Improved-II gap shows flips
  are what remove bad-valence residuals that smoothing alone cannot).
  Acceptance: monotone non-decreasing worst-Q across ladder steps; naca max
  skew < 60; boundary facet set unchanged (interface/exterior faces preserved
  exactly); bounded pass count (L=2 per rung, 5 rungs).
  Risk: interacts with existing native_tet flip logic (double application);
  argmax-of-worst is greedy and can churn near threshold boundaries — cap via
  the no-improvement early-break in Algorithm 3.1.

## References worth snowballing (max 5)

1. **[15] Shewchuk 2002**, "Two discrete optimization algorithms for the
   topological improvement of tetrahedral meshes" (unpublished ms.) — the edge
   removal / multi-face removal primitives used here and in Stellar.
2. **[16] Liu & Sun 2006**, "Small polyhedron reconnection" (IMR 15) — larger
   20–40-tet repartitioning to break the local-optimum wall the paper hits on
   RAND meshes without vertex insertion.
3. **[21] Chen 2004**, "Mesh smoothing schemes based on optimal Delaunay
   triangulations" (IMR 13) — interpolation-error-based smoothing; the main
   alternative objective family for TET-FLOW-2.
4. **[12] Freitag & Ollivier-Gooch 1997**, "Tetrahedral mesh improvement using
   swapping and smoothing" (IJNME) — the canonical smoothing+swap scheduling
   study; baseline for TET-FLOW-3's ladder.
5. **[32] Escher & Simonett 1998**, "The volume preserving mean curvature flow
   near spheres" (Proc. AMS) — existence theory behind AMCF, only relevant if
   a (non-exact-surface) smoothing mode is ever added for voxel-derived input.

(Note: [35] Klingner & Shewchuk 2007 is already in the library as
`01_klingner_2007_aggressive_tet`.)
