# Particle Virtual Element Method (PVEM): an Agglomeration Technique for Mesh Optimization in Explicit Lagrangian Free-Surface Fluid Modelling

## Bibliography and access

- Cheng Fu, Massimiliano Cremonesi, Umberto Perego, Blaz Hudobivnik, Peter Wriggers.
- *Computer Methods in Applied Mechanics and Engineering* 433 (2025) 117461.
- DOI: `10.1016/j.cma.2024.117461` — open access (CC BY).
- Status: `FULL_READ` (21/21 pages, 2026-07-23). Note: the screening record listed
  "38 pages"; the actual PDF page tree contains 21 pages and the body ends at
  printed page 21 (references). All 21 were read via full text extraction.
- Extraction caveat: the text layer drops superscripts and Greek letters, so some
  mesh-size counts (Sections 6.3–6.4) are recoverable only to order of magnitude;
  figures were not rendered (no local rasterizer), but all figure captions and every
  table value were extracted and are internally consistent.
- Screened as "PVEM / polytopal VEM". Confirmed: it is a solver-plus-mesh-repair
  paper — 3D first-order mixed velocity–pressure VEM for weakly compressible
  Lagrangian flow, combined with a runtime **agglomeration** operator that merges
  sliver tetrahedra into polyhedral virtual elements to raise the explicit stable
  time step. It is *not* a quality-indicator paper in the Sorgente 2022 sense.

## Problem and assumptions

PFEM (Particle FEM) remeshes a Lagrangian fluid at runtime with 3D Delaunay plus
alpha-shape trimming. 3D Delaunay gives no shape guarantee and emits slivers;
under explicit central-difference integration the CFL condition ties the stable
time step to the *worst* element, so one sliver collapses the step size. Smoothing
(Meduri et al. 2019) is expensive and fails when sliver nodes are pinned on
boundaries. The paper's answer: keep the nodes, merge bad cells into bigger
polyhedral VEs that the VEM can integrate directly.

### Cell-assumption set (transcribed)

The assumptions the formulation places on polytopal cells are operational, not
analytic:

1. **Arbitrary polytopes admitted.** VEs may have "an arbitrary number of nodes and
   shapes (polygons in 2D and polyhedra in 3D), possibly non-convex" (Sec. 1). No
   star-shapedness, convexity, or aspect-ratio hypothesis is stated or checked
   anywhere in the paper.
2. **All faces triangular by construction.** Because VEs arise only from
   agglomerating linear tetrahedra, "the element faces are always triangular and
   the standard shape functions of linear triangles completely define the
   displacement model over the face" (Sec. 4.2). Face planarity is therefore
   trivially exact — the projection boundary integral (Eq. 36) is computed with
   one-point Gauss quadrature per triangle. Non-planar polygonal faces never occur.
3. **First-order only.** Linear ansatz (k = 1); projected gradients are constant
   per element (Eqs. 32–41). The VEM on a plain 4-node tet coincides with linear
   FEM, so VEM cost is paid only where agglomeration happened.
4. **Characteristic length as the sole shape metric.** For a VE,
   `h = 6V/A` in 3D (`4A/P` in 2D), V = volume, A = total surface area — an
   inscribed-sphere-diameter analogue that the authors admit "is not rigorous"
   for a general polyhedron "but provides a reasonable estimate" (Eq. 55).
5. **Stabilization absorbs shape badness.** Dof-based stabilization
   (Eq. 50–52) with scaling `beta = beta0` (2D) or `beta0 * h` (3D),
   `beta0 ≈ 0.001`, plus Direct Pressure Stabilization (constant-pressure L2
   projection, Eqs. 16–21) to fix the LBB violation of equal-order v–p pairs.
   Row-sum lumped mass, no mass stabilization needed (Sec. 4.4).
6. **Distortion screens.** Alpha-shape index `alpha_e = R_circ,e / h_mesh` with
   thresholds `alpha_in = 2` (bulk) and `alpha_fs = 1.2` (free surface) deletes
   non-physical Delaunay elements; the *agglomeration* gate is time-step-based:
   element e is distorted iff `dt_e < kappa * dt_mean`, kappa in [0.4, 0.6]
   (Eqs. 56–57).

## Method: greedy agglomeration (Algorithm 1)

For every element in the distorted subset, repeatedly merge with the neighbor that
maximizes the agglomerate's stable time step (equivalently its `h = 6V/A`), until
`dt >= kappa * dt_mean`. Properties claimed (Sec. 5.1): no node motion (works with
boundary-pinned slivers), no data convection (nodes keep all state), no auxiliary
equation solve, applied only locally (VEs are a small mesh fraction), and VEs are
discarded at the next global Delaunay remesh — agglomerates are *transient*
repair artifacts, not persistent mesh entities.

## Experiments

- **2D analytical benchmark** (Sec. 6.1): quadrilateral, hexagonal, and Voronoi
  polygonal meshes all reproduce a manufactured steady Navier–Stokes solution;
  quadrilateral convergence study over 5 refinements (36 → 10 201 nodes).
- **2D sloshing** (Sec. 6.2): ~6 000 nodes / ~11 000 triangles. PVEM min step
  3.04e-5 s vs PFEM 2.55e-6 s (Table 1) — 12x on the minimum; only ~0.2% of
  elements become VEs, concentrated at the free surface.
- **3D dam break** (Sec. 6.3): kappa = 0.4. Min step 1.27e-6 s vs 1.06e-7
  (PFEM+smoothing) vs 1.69e-10 (raw Delaunay) — 1 and ~4 orders of magnitude
  (Table 2). VE fraction 1–6% of elements over the run. Wall clock 4 h vs 14 h
  for the smoothing-based solver. Wavefront position matches Koshizuka/Martin–
  Moyce/Hu–Sueyoshi references. (Node/element counts lost superscripts in the
  text layer — order 1e4–1e5.)
- **3D water drop into tank** (Sec. 6.4): kappa = 0.4. Min step 4.81e-6 vs
  7.73e-7 (smoothing) vs 1.23e-9 (none) (Table 3); 6 h vs 14 h runtime.

So yes: **real 3D volume evidence**, two 3D free-surface problems, with
quantitative time-step and wall-clock tables — but accuracy is validated only
against wavefront/height curves and snapshots, never via per-cell quality or
discretization-error statistics on the agglomerates.

## Limitations

- No per-cell quality analysis of the agglomerated polyhedra: no star-kernel,
  aspect, or conditioning measurement, and no study of how VE shape affects
  accuracy. The only monitored quantity is `h = 6V/A` / the stable time step.
- Degenerate cells are *handled* (that is the whole point — slivers are absorbed)
  but never *measured*; anisotropy is not discussed at all.
- The greedy merge maximizes h stepwise; no optimality or termination bound is
  proven (termination is empirical — merging monotonically grows V faster than A
  in practice, but a pathological chain is not excluded).
- All-triangular faces are guaranteed only because primitives are tets; nothing
  transfers to general polyhedral cells with non-planar polygonal faces.
- Explicit-dynamics framing: benefits hinge on VEM's projection + stabilization
  tolerating arbitrary cell shapes. A finite-volume discretization (OpenFOAM)
  has no such stabilization; the paper's tolerance claims do not transfer.
- Implicit-analysis benefits are conjectured in the conclusions, not tested.

## AutoTessell applicability

We generate *persistent* polyhedral meshes for FV solvers; this paper generates
*transient* polyhedral cells for a stabilized VEM solver. Direct transfers:

1. **Justifies an agglomeration-repair pass in `native_poly`.** Our current
   posture on degenerate dual cells is drop/fallback
   (`core/utils/drop_neg_vol_cells.py`, hull replacement in
   `core/generator/native_poly/dual.py`). PVEM (with Sukumar–Tupek 2022 and
   Sorgente 2023 as siblings) is now the third independent source showing
   *merge-with-best-neighbor* as the cheap, node-preserving fix for sliver-class
   cells — no smoothing solve, no node motion, surface untouched. That is exactly
   the repair shape our `POLY-CONCAVE-SPLIT1` card lacks a dual for (split vs
   merge).
2. **Justifies `6V/A` as a first-class degeneracy indicator.** It is cheaper than
   our star-kernel checks, dimensionally clean, and PVEM demonstrates it is the
   single scalar that predicts explicit-solver viability. Worth adding to
   `core/evaluator/native_checker.py` alongside min-volume: a cell with healthy
   volume but bloated area (pancake/spider dual cells) is invisible to a volume
   gate but caught by `6V/A`.
3. **Challenges over-strict per-cell shape gates — but only for VEM-class
   consumers.** PVEM runs non-convex, unshapely polyhedra with no accuracy loss
   *because* the VEM projection + dof stabilization absorbs shape badness. Our
   quality contract targets OpenFOAM FV, where face non-orthogonality and
   skewness directly poison gradients. So: do **not** relax FV gates on this
   evidence; do note that if a VEM export target is ever added, the contract can
   legitimately be much looser (h-based, not shape-based).
4. **Face-planarity lesson.** PVEM sidesteps warped faces entirely by keeping
   faces triangular. For our polydual engine the analogous cheap invariant is:
   when a dual face fails a planarity gate, triangulating it (fan/centroid split)
   restores an exactly integrable boundary at the cost of face count — a lighter
   repair than cell rejection.

What it adds beyond Sorgente 2022: Sorgente correlates *static* per-cell
indicators (star-kernel, size, combinatorial) with VEM accuracy; PVEM contributes
the *dynamic* side — an O(local) repair operator plus evidence that a pure size
indicator (`6V/A` via CFL) is sufficient as an online gate when the consumer is a
stabilized VEM. It neither confirms nor refutes Sorgente's shape indicators (it
never measures them), so our Sorgente-derived gates stand; PVEM slots in as the
*remediation* step behind those gates rather than a replacement for them.

## Falsifiable implementation cards

### `POLY-QUALITY-HCHAR1`

Add per-cell characteristic length `h = 6V/A` to `NativeMeshChecker`
(`core/evaluator/native_checker.py`) and report the mesh minimum and histogram.
Pass if (a) on a unit-cube uniform poly mesh, min(h) is within 20% of the
analytic inscribed-diameter estimate; (b) on a fixture with one injected
pancake cell (volume normal, area 10x inflated), the cell is ranked worst by h
while a pure min-volume gate misses it; (c) the metric is invariant under rigid
transforms and scales linearly with uniform scaling.

### `POLY-QUALITY-AGGLOM1`

Implement a node-preserving merge-with-best-neighbor repair for cells failing the
`h = 6V/A` (or star-validity) gate in `native_poly`: greedily union the failing
cell with the neighbor maximizing the agglomerate's h, re-derive the shared-face
set, and stop when the gate passes or no neighbor improves h. Pass only if
(a) total mesh volume is conserved to 1e-10 relative; (b) boundary faces and
surface geometry are bit-identical (no node motion); (c) every produced cell
passes `POLY-STAR-VALID1` or is explicitly reported as unrepaired; (d) on a
sliver-dual fixture the min stable-timestep proxy min(h) increases by at least
the PVEM-observed order of magnitude.

## Snowball references (max 5)

1. N. Sukumar, M.R. Tupek, *Virtual elements on agglomerated finite elements to
   increase the critical time step in elastodynamic simulations*, IJNME 123 (2022)
   4702–4725 — origin of the agglomeration idea PVEM ports to fluids. [ref 42]
2. T. Sorgente, F. Vicini, S. Berrone, S. Biasotti, G. Manzini, M. Spagnuolo,
   *Mesh quality agglomeration algorithm for the virtual element method applied to
   discrete fracture networks*, Calcolo 60 (2023) 27 — Sorgente-group
   quality-driven agglomeration; the bridge between Sorgente 2022 indicators and
   PVEM-style repair. [ref 52]
3. S. Meduri, M. Cremonesi, U. Perego, *An efficient runtime mesh smoothing
   technique for 3D explicit Lagrangian free-surface fluid flow simulations*,
   IJNME 117 (2019) 430–452 — the smoothing baseline PVEM beats; relevant to our
   untangler design space. [ref 18]
4. K. Park, H. Chi, G.H. Paulino, *On nonconvex meshes for elastodynamics using
   virtual element methods with explicit time integration*, CMAME 356 (2019)
   669–684 — explicit-VEM evidence that non-convex cells are viable. [ref 27]
5. P.F. Antonietti, S. Berrone, M. Busetto, M. Verani, *Agglomeration-based
   geometric multigrid schemes for the virtual element method*, SIAM J. Numer.
   Anal. 61 (2023) 223–249 — agglomeration as a multilevel primitive. [ref 51]
