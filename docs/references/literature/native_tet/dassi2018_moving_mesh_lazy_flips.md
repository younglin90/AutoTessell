# Dassi, Kamenski, Farrell, Si — Tetrahedral Mesh Improvement Using Moving Mesh Smoothing, Lazy Searching Flips, and RBF Surface Reconstruction (2018)

**Authors:** Franco Dassi (U. Milano-Bicocca), Lennard Kamenski, Patricio Farrell, Hang Si (WIAS Berlin)
**Venue:** Computer-Aided Design (Elsevier), special issue (eds. Canann, Owen, Si)
**DOI:** `10.1016/j.cad.2017.11.010`
**Pages read:** 12/12 (in-press journal PDF; the local file is 12 two-column pages, not 40)
**Status:** FULL_READ (`docs/references/papers/source/pdf/13_dassi_2018_moving_mesh_lazy_flips.pdf`)
**Date:** 2026-07-23

## Summary

A tet mesh improvement framework combining three components: (1) **MMPDE moving-mesh
smoothing** — vertex positions evolve by the gradient flow of a variational meshing
functional, with analytic element-wise velocities and a proven mesh-validity guarantee;
(2) **lazy searching flips** — a fully reversible, depth-bounded recursive edge-removal
search that accepts the first improving flip sequence and rolls back non-improving ones;
(3) **RBF surface reconstruction** (polyharmonic spline) to project boundary vertices
onto a smooth approximation of a curved boundary. On PLC and organic models the combined
scheme beats CGAL and mmg3d and matches/exceeds Stellar on dihedral-angle distributions
while keeping vertex counts near the input (Stellar aggressively removes vertices).

## Core algorithm

### 1. MMPDE smoothing (Section 2)

- Energy: `Ih = Σ_K |K| G(J_K, det J_K)` with the Huang equidistribution+alignment
  functional
  `G(J, det J) = θ (tr(J Jᵀ))^{dp/2} + (1−2θ) d^{dp/2} (det J)^p`, θ ∈ (0, 0.5], p > 1
  (paper uses θ = 1/3, p = 3/2). `J_K = (F'_K)⁻¹` is the inverse Jacobian of the map
  from a regular reference simplex of volume 1/#Th to element K. Minimizing Ih drives
  the mesh toward uniform size + regular shape (Eq. (1): equal |K| and
  tr(JᵀJ)/d = det(JᵀJ)^{1/d}).
- Vertex velocities are **analytic**, assembled element-wise like a FE stiffness matrix
  (Eq. (5): `−G_K E_K⁻¹ + E_K⁻¹ (∂G/∂J) Ê E_K⁻¹ + (∂G/∂det J)(det Ê/det E_K) E_K⁻¹`,
  with `v_0 = −Σ v_j`), then summed over the patch: `dx_i/dt = Σ_{K∈ω_i} |K| v^K_{i_K}`.
  Trivially parallel (OpenMP in the paper); all nodes move simultaneously.
- **Step control:** explicit Runge–Kutta Dormand–Prince, integrated to a fixed horizon
  (t = 10 in experiments) or until the energy change falls below absolute/relative
  tolerances `|Ih(t_{n+1}) − Ih(t_n)| ≤ ε`.
- **Validity guard (the key theoretical asset):** the continuous flow keeps the mesh
  nonsingular if it starts nonsingular — minimum element height and volume stay bounded
  below by a constant depending only on the initial mesh and #Th (Huang–Kamenski,
  Math. Comp. 2017). The discrete integration inherits this if the ODE solver is
  energy-diminishing (algebraically stable RK under a mild step-size restriction).
  So no per-step inversion checks/rollbacks are needed *in theory*; connectivity is
  frozen during a smoothing step.
- **Boundary velocity adjustment:** fixed vertices → v = 0; PLC facet vertices →
  project v onto the facet plane; segment vertices → project onto the segment line;
  corners → v = 0. Curved boundaries → null the normal component (∇φ·v = 0) or
  move-then-project onto the surface.

### 2. Lazy searching flips (Section 3)

- Goal: remove an edge [a,b] shared by n ≥ 3 tets (n-to-m flip, m = 2n−4). Exhaustive
  search over all edge-removal triangulations is Catalan-number `C_{n−2}` expensive; the
  authors instead do a **depth-first search that stops at the first improving
  configuration** ("lazy") and **reverses** any explored non-improving flip sequence.
- Mechanics (`flipnm(A[0..n−1], level)` + `flipnm_post`):
  - Step 1: if n = 3 and the 3-to-2 flip is possible → done.
  - Step 2: try each adjacent face [a,b,p_i] with a 2-to-3 flip; on success |A| drops by
    one and the freed array slot stores the flip record (flag + position i) — the flip
    log lives inside A itself, **no extra memory**; recurse on the reduced ring.
  - Step 3 (the "searching" part): if `level > 0` and no face is flippable, try to
    remove an **adjacent edge** [a,p_i] or [b,p_i] by a recursive `flipnm` call at
    `level−1` on its own tet ring B. Success shrinks the [a,b] ring and can unlock it.
    Faces/edges in A ∩ B are skipped to avoid interference.
  - Reversal: stored records allow exact inverse flips (3-to-2 undoes 2-to-3, nested B
    sequences undo recursively) — the whole exploration is **transactional**.
- **Gain gate:** a candidate 2-to-3 flip is accepted during search only if it is
  geometrically flippable AND improves the local quality; only 2 of the 3 new tets need
  checking ([a,p_{i−1},p_i,p_{i+1}], [b,p_{i−1},p_i,p_{i+1}]) since the third contains
  [a,b] and disappears if the removal succeeds.
- **Flip criterion is pluggable** and the scheme alternates per outer iteration between
  (1) simultaneously maximizing θ_min,K and minimizing θ_max,K (a two-quantity
  criterion the authors flag as novel) and (2) minimizing aspect ratio
  `q_ar = √(2/3)·L/h`.
- Flips are sequential (search can propagate to neighbors-of-neighbors; hard to
  parallelize).

### 3. RBF surface reconstruction (Section 4)

- Implicit surface `F = 0` interpolated by a polyharmonic spline `‖x‖³` (conditionally
  positive definite of order 2) plus low-degree polynomial term, using Carr et al. 2001
  on/off-surface conditions: `s(x_i) = 0` at surface vertices, `s(x_i + ε n_i) = ε` at
  offset points along vertex normals (avoids the trivial zero solution).
- Used to **project moved/new boundary vertices onto the smooth reconstruction**:
  smoothed boundary vertices and edge-split midpoints are projected by a steepest-descent
  tangent-plane/tangent-parabola iteration (Hartmann 1999, first derivatives only).
- Edge **contraction** on the boundary is done into an existing endpoint (which lies on
  the surface by construction), never into a midpoint.

### Scheduling (Algorithm 1, Section 5)

Five nested repeat-until loops, from inner to outer:
1. `smooth (MMPDE) → RBF projection → lazy flips` until no motion/flip or Q ≥ θlim;
2. contract edges `l_e < 0.5 l_ave` + lazy flips;
3. split edges `l_e > 1.5 l_ave` + RBF projection + lazy flips;
4. split tets with `θ_min,K < θlim` by 1-to-4 barycenter insertion + lazy flips;
5. outer loop: switch the lazy-flip criterion (min/max dihedral ↔ aspect ratio) and
   repeat until no operation fires or Q(Th) > θlim.

Global stop metric `Q(Th) = min_K θ_min,K`. The refinement stages (2–4) exist purely to
break stagnation of smooth+flip; the authors state they made no effort to optimize them.
No termination proof is given for the outer loop.

## Lazy flips vs AutoTessell's unflippable-wedge problem

Direct relevance to the FSL finding (0/9 eligible slivers via plain 2-3 flips; 61
unflippable coplanar-flat wedges on dual_torus):

- The paper explicitly states the motivating failure mode: *"In most situations, an edge
  may not be flipped if we restrict ourselves to adjacent faces of the edge."* That is
  exactly a plain 2-3/3-2 pass. Their answer is Step 3 recursion: when no adjacent face
  of [a,b] admits an improving 2-to-3 flip, remove an **adjacent edge** first, which
  rewrites the link of [a,b] and can make it removable. So yes — **lazy compound flips
  are a plausible unlock for a subset of our 61 wedges**, specifically those blocked by
  *combinatorial* obstruction (no single improving face flip exists, but a 2-step
  sequence does).
- Two caveats bound the expectation:
  1. **Exactly coplanar/degenerate geometry can be unflippable at any depth** — a 2-to-3
     flip through a flat wedge creates a zero/negative-volume tet and fails the
     flippability test regardless of search order. For those, the paper's own remedy is
     not deeper search but the stagnation stages (edge contract / split / 1-to-4
     insert). Expect the 61 wedges to partition into "search-unlockable" and
     "needs-topology-change" classes; the reversible search is the cheap way to measure
     that split empirically.
  2. The algorithm as written assumes **interior edges** (cyclically ordered tet ring).
     Wedges whose central edge lies on the boundary need a boundary-aware variant
     (partial ring, 2-to-2 boundary flips) which the paper does not develop.
- The reversal mechanism (in-array flip log + exact inverse sequence) is precisely the
  transactional rollback pattern AutoTessell already prefers — trying an aggressive
  compound flip is safe because failure restores the exact prior state bit-for-bit.

## Boundary handling — does it violate the #1 invariant?

**Yes, in two of its three boundary modes; the paper itself provides the compliant mode.**

- **RBF mode (ellipsoid example): violates surface preservation.** Boundary vertices are
  moved by smoothing and projected onto the RBF reconstruction, and the paper says
  outright that the *"RBF reconstruction smoothes the initially rough surface
  approximation"* — the output boundary is a smoothed implicit approximant, not the
  input surface. Edge splitting likewise projects midpoints onto the reconstruction,
  off the input facets. This directly conflicts with AutoTessell's exact pre-meshing
  surface preservation invariant.
- **PLC mode: geometrically preserving, not vertex-preserving.** Facet/segment vertices
  slide within their plane/line (corners pinned), so the *geometric* surface of a planar
  PLC is preserved but boundary vertex positions and the surface triangulation change.
  If AutoTessell's invariant is "the surface triangulation is untouched", this mode also
  violates it; if it is "the geometric surface is unchanged", planar-facet sliding is
  admissible.
- **Frozen-boundary mode (spine, elephant): fully compliant.** For the two complex
  models the authors themselves fix all boundary vertices (TetGen `-Y`) and improve only
  the interior. The scheme still beats Stellar on θ_min, θ_max, and deviation — i.e.,
  **MMPDE smoothing (interior vertices, v = 0 on boundary) and lazy flips (interior
  edges only) remain fully usable with a frozen boundary; only the RBF component drops
  out.** They do note frozen-boundary results have worse θ_min than the movable-boundary
  PLC cases — the price of the invariant.

## Experiments

- **Models:** Rand1 (random-vertex cube, #Th = 5104), LShape (TetGen `-pa0.019`,
  #Th = 4072), TetgenExample (non-convex PLC with a hole, #Th = 3545) — PLC set;
  ellipsoid (curved, RBF-projected boundary); Spine (#Th = 688,420) and Elephant
  (#Th = 260,401) with frozen boundaries (initial surfaces from the authors' higher-
  dimensional-embedding remesher, min face angle ≈ 33°; volumes by TetGen `-Y`).
- **Metrics:** dihedral-angle histograms, θ_min/θ_max over the mesh, mean dihedral angle
  and standard deviation, aspect-ratio histograms. No runtime/timing data anywhere.
- **Baselines:** Stellar (Klingner–Shewchuk), CGAL 4.8 remeshing, mmg3d.
- **Component ablation:** lazy flips alone ≈ Stellar's flip pass; MMPDE smoothing alone
  **beats** Stellar's smoothing pass (larger θ_min, noticeably smaller θ_max, smaller σ)
  on LShape and TetgenExample. The smoothing is where this paper wins, not the flips.
- **Full scheme:** θ_min larger than CGAL/mmg3d, comparable to Stellar; θ_max smaller
  than all baselines in all examples but one; mean dihedral ≈ 69.6° (optimum
  arccos(1/3) ≈ 70.56°) with the smallest σ; aspect ratios mostly < 1.8 (Stellar
  < 2.6). Vertex count stays near the input, versus Stellar's aggressive vertex removal.
  Ellipsoid: mean dihedral ≈ 70.69°, σ ≈ 18.16°.

## Limitations

Stated by the authors:
- Complicated curved boundaries are an open problem — the simple move-then-project can
  fail; proposed fix is parametrizing the boundary directly into the MMPDE (future work).
- Edge contraction/splitting are deliberately unoptimized stagnation-breakers.
- Lazy flips are sequential and hard to parallelize (propagation to neighbors).
- Anisotropic/metric-driven extension left to future work.

Inferred:
- No termination or complexity guarantee for Algorithm 1's nested loops; θlim is not
  guaranteed reachable (loops can exit on "no operation done" below target).
- No timing comparisons at all — cost of DP-integrated smoothing per pass vs a Laplacian
  sweep is unquantified; t = 10 horizon is empirical.
- Search depth `level` is never studied quantitatively (no depth-vs-quality data).
- All guarantees for MMPDE validity assume the energy-diminishing property; the explicit
  Dormand–Prince solver used is not algebraically stable, so in practice the guarantee
  is only heuristic unless step size is monitored (the paper does not discuss this gap).
- Quality targets are dihedral-angle-centric; no direct sliver-count or CFD-solver
  metric (non-orthogonality, skewness) reporting.

## AutoTessell applicability

Evidence-matrix disposition confirmed and sharpened: this is a strong candidate for the
`TET-IMPROVE-1` transaction stage, with the constraint that **only the frozen-boundary
subset (MMPDE interior smoothing + lazy interior flips) is invariant-compliant**; the
RBF pass must not be ported as-is.

Candidate cards:

| Card | Mechanism | Target | Acceptance signal | Risk |
|------|-----------|--------|-------------------|------|
| `TET-LAZY-1` | Reversible recursive edge removal (`flipnm` with `level ∈ {1,2}`, in-array flip log, exact rollback) replacing the plain 2-3 flip pass in the FSL sequence; interior edges only, boundary edges skipped | 61 unflippable coplanar-flat wedges on dual_torus; 0/9 sliver flip eligibility | > 0 wedges removed at level ≥ 1 where level 0 removed none; classify remaining wedges as geometric vs combinatorial; min dihedral up, zero surface-vertex motion, bit-exact rollback on failed searches | Exponential search bounded only by `level`; exactly-degenerate wedges stay unflippable; sequential cost on large rings |
| `TET-LAZY-2` | Dual-criterion flip gating: alternate (max θ_min ∧ min θ_max) with (min aspect ratio) across improvement rounds, per Algorithm 1 line 20 | naca residual skew ≈ 60.3 (max-angle-driven skew that a pure min-dihedral gate ignores) | Max dihedral / skew percentile drops without min-dihedral regression across a full alternation cycle | Criterion oscillation re-flipping the same edges; needs a per-edge no-progress counter |
| `TET-MM-1` | MMPDE gradient-flow smoothing (Huang functional θ = 1/3, p = 3/2; analytic Eq. (5) velocities; energy-monotone integration with adaptive step + energy-decrease check per step) for interior vertices, boundary velocities hard-zeroed; replaces one-pass smoothing heuristics as a transactional stage | CYLSKEW near-wall skew; general dihedral distribution tightening (mean → ~69–70°, σ down) | Energy Ih monotone per accepted step; no inverted elements (theory-backed); near-wall skew percentile improves with frozen boundary; rollback to pre-stage snapshot if Ih stalls without quality gain | Frozen near-wall vertices cap achievable gain (paper's own frozen-boundary θ_min is worse than movable); explicit RK not algebraically stable — must enforce energy decrease explicitly; per-pass cost >> Laplacian |
| `TET-MM-2` | Stagnation-breaking schedule as guarded transactions: contract `l < 0.5 l_ave` → split `l > 1.5 l_ave` → 1-to-4 barycenter split of `θ_min,K < θlim` tets, each followed by a `TET-LAZY-1` pass; interior entities only | Wedges/slivers surviving `TET-LAZY-1` (the geometric-obstruction class) | Residual unflippable-wedge count → 0 or near 0 after one schedule round; cell-count growth bounded (< few %); surface untouched | Changes cell count and sizing field; interacts with BL layers; contraction near boundary must be forbidden, not just endpoint-snapped |

Sequencing note: run `TET-LAZY-1` first — it is cheap, transactional, and directly
measures how many of the 61 wedges are combinatorially vs geometrically blocked, which
decides whether `TET-MM-2` is needed at all.

## References worth snowballing

1. Huang & Kamenski, *A geometric discretization and a simple implementation for
   variational mesh generation and adaptation*, JCP 301 (2015) — the exact velocity
   formulas (Eqs. (39)–(41)) `TET-MM-1` would implement. [ref 13]
2. Huang & Kamenski, *On the mesh nonsingularity of the moving mesh PDE method*,
   Math. Comp. 2017 — the validity/nonsingularity proof and its ODE-solver conditions.
   [ref 14]
3. Klingner & Shewchuk, *Aggressive tetrahedral mesh improvement*, IMR 2007 — Stellar
   baseline; already summarized (`papers/01_klingner_2007_aggressive_summary.md`),
   cross-link. [ref 2]
4. Freitag & Ollivier-Gooch, *Tetrahedral mesh improvement using swapping and
   smoothing*, IJNME 1997 — the canonical smoothing+flipping combination study and the
   baseline FSL-style pass ours resembles. [ref 1]
5. Dassi, Kamenski & Si, *Tetrahedral mesh improvement using moving mesh smoothing and
   lazy searching flips*, Procedia Eng 163 (2016) — the IMR precursor with additional
   PLC examples referenced for "more PLC examples, see [41]". [ref 41]
