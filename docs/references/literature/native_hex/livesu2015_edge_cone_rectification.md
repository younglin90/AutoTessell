# Livesu 2015 - Practical Hex-Mesh Optimization via Edge-Cone Rectification

## Bibliographic record

- Marco Livesu, Alla Sheffer, Nicholas Vining, Marco Tarini, *Practical Hex-Mesh Optimization via Edge-Cone Rectification*, ACM Transactions on Graphics 34(4), Art. 71 (SIGGRAPH 2015).
- DOI: `10.1145/2766905`
- Legal open manuscript: <https://www.cs.ubc.ca/labs/imager/tr/2015/untangler/downloads/untangler.pdf> (authors' project page).
- Local copy: `docs/references/papers/source/pdf/36_livesu_2015_edge_cone_rectification.pdf`, SHA-256 `54e61f8497bebe3c292b36bcee3e97707a8eb2ecd8147d72e6506952a80af81a`.
- Status: `FULL_READ` (11/11 pages, 2026-07-23).
- Reference material: results archive `untangler_res.zip` on the same project page (input/output mesh pairs for every experiment).

## Problem and claimed scope

Post-pass optimizer for hex meshes with fixed connectivity: takes a low-quality
initial hex mesh (possibly with thousands of inverted elements), moves vertices
only, and returns an inversion-free mesh with high average and minimum Scaled
Jacobian while closely preserving the input surface. Both **untangling and
quality improvement in one framework** — it is not a two-stage
untangle-then-smooth pipeline. No theoretical guarantee of success (the
existence of an inversion-free embedding for a given hex connectivity is open,
citing Erickson 2014); the claim is empirical robustness across polycube,
frame-field, grid-based, and octree (Maréchal/Hexotic) inputs, including
artificially corrupted meshes with up to ~96% inverted elements.

## Math: the edge-cone reformulation (question 1)

Hex validity is classically tested through the 8 corner tetrahedra of each hex
(Fig. 2a): the hex is convex iff all corner tets have positive volume, and
corner quality is maximal when the three outgoing corner edges are mutually
orthogonal. The paper's key move is a **regrouping, not a relaxation**: the
same corner tets, collected over the whole mesh, can be iterated as **cones of
tetrahedra around each *directed* edge** (Fig. 2b). Traversing all cones visits
exactly the set of all corner tets, so cone shape optimization is *equivalent*
to hex shape optimization.

Definitions. For directed edge `e_ij = v_j − v_i`: let `Q = {q_k}` be the
umbrella of quads (from all hexes containing `e_ij`) containing `i` but not
`j`, and `T = {t_k}` the triangle fan of vertices on `Q` connected to `v_i`,
consistently wound, cyclic (`t_|T| = t_0`). Triangle `t_k` has vertices
`u_k, v_i, u_{k+1}` and normal `n_k`.

**Non-inversion = per-edge cone containment.** Tetrahedron
`(e_ij, u_k, u_{k+1})` has positive volume iff `v_j` lies on the positive side
of the supporting plane of `t_k`. So the whole mesh is inversion-free iff

```text
e_ij · n_k > 0    for every directed edge e_ij and every base triangle t_k in T(e_ij)   (Eq. 3)
```

i.e. the axis of every cone makes an angle < 90° with every base-face normal.
Per-tet quality (scaled Jacobian) is maximized when the axis is *parallel* to
each base normal, giving the shape energy

```text
E_cone = Σ_{e_ij ∈ E} Σ_{k=1..|T(e_ij)|} ( e_ij/‖e_ij‖ − n_k )²               (Eq. 2)
```

with `n_k` itself a (normalized cross-product) function of vertex positions
(Eq. 4). Both directions of each edge are counted separately on purpose — the
two half-edges can have very differently constrained cones.

**Quadratization.** The normalizations `‖e_ij‖` and the cross-product norm are
what make the problem nonlinear. Both are replaced by **pre-estimated target
edge lengths** `L_ij` (Section 3.4):

```text
EQ_cone = Σ_ij Σ_k ( e_ij/L_ij − n_k )²                                        (Eq. 5)
n_k = (u_k − v_i) × (u_{k+1} − v_i) / (L_{k,i} · L_{k+1,i})                    (Eq. 6)
```

With normals frozen at their current values, `EQ_cone` is a convex quadratic in
vertex positions and Eq. 3 becomes a set of **linear inequality constraints** —
a standard QP.

## Algorithm (question 2)

### Strict global iteration (Section 3.1.1)

1. Compute all cone base normals `n_k` from current positions (Eq. 6).
2. Solve one global QP: minimize `EQ_cone + E_boundary` subject to
   `e_ij · n_k > 0` (convex, unique minimum).
3. Repeat until positions stop changing.

If this converges, the output is **guaranteed inversion-free** (at the fixed
point the constraints hold for the actual output normals). But an intermediate
constraint set can be **infeasible** (Fig. 3c: base configurations that admit no
inversion-free axis direction; also degenerate zero-length normals), so the
strict scheme can terminate without a solution on badly tangled input.
Empirically, two thirds of the *regular* test meshes and all corrupted ones hit
at least one infeasible local system — the strict formulation alone is not
usable in practice.

### Local-global framework with penalties (Section 3.1.2) — the actual method

**Local step** (per directed edge, independent, parallelizable): find target
axis direction

```text
n̂_ij = argmin Σ_k (n̂_ij − n_k)²   s.t.  n̂_ij · n_k > ε > 0,  ‖n̂_ij‖² ≤ 1     (Eq. 9-11)
```

Small convex QP in 3 variables (Gurobi), but in most configurations the plain
average of base normals already satisfies the constraints, so the QP solver is
invoked only on violation. Default `ε = cos(85°)`. **If infeasible**, return
either the current edge direction or the normal average, whichever has the
smaller worst angle `α_ij` to the base normals — the iteration proceeds anyway.

**Global step**: solve for all vertex positions minimizing the quadratic

```text
E = EQ_cone + E_penalty + E_regularize + E_boundary                            (Eq. 25)
E_penalty = Σ_ij W(α_ij) · w^P_ij · ‖ e_ij/L̂_ij − n̂_ij ‖²                     (Eq. 14, 18)
```

solved with GMRES (unconstrained quadratic — the hard constraints are replaced
by penalties precisely so the solver can proceed when they are unsatisfiable).
Penalty details:

- `L̂_ij = (‖e_ij‖ + L_ij)/2` — average of current and target length.
- Weight update `w^P_ij = max(w^P_ij, ‖e_ij/L̂_ij − n̂_ij‖⁶)` (Eq. 15), never
  decreased; power 6 empirical (lower under-penalizes, higher ill-conditions).
  Distance between unit vectors is bounded by 2, so the penalty has a natural
  upper bound and the scheme must terminate.
- Cone-tightness factor `W(α_ij) = 1 + 10·exp(−cos²α_ij / (2σ²))`, `σ = 0.3`
  (Eq. 16) — tighter cones (α near 90°) are penalized harder.
- Edges whose local step was infeasible (`α_ij ≥ 90°`) are **skipped** in the
  penalty sum.
- Inner penalty loop: minimize Eq. 25, update weights, repeat; typically ≤ 5
  linear solves.

**Regularization** (Section 3.2, Eq. 19): direction/length similarity of
topologically parallel edges within a hex and consecutive edges across
face-adjacent hexes, normalized by target lengths. Ablation: removing it makes
22% of meshes fail to converge; using it *alone* (no cone term) fails on 66% of
regular and all corrupted meshes. It stabilizes, it does not substitute.

**Target edge lengths** (Section 3.4, Eq. 22): least-squares balance of
(a) preserving current surface edge lengths, (b) pulling interior edges to the
mesh average, (c) parallel/consecutive similarity. For graded meshes
(octree-based), input edge lengths are used directly as targets. Optional
selective re-targeting (Eq. 23-24) blends target toward current length where
local MSJ is already good (Gaussian weight, σ = 0.15) so good regions are left
alone.

**Max-min quality mode** (Section 3.6): after all cones are feasible
(`α_ij < 90°` everywhere), tighten per-cone constraints to
`n̂_ij · n_k > cos(α_ij + 0.01)` — every local solve must beat its own current
worst angle; keep the previous target when infeasible; leave cones already
above the literature high-quality threshold (MSJ 0.5) untouched. The penalty
weight peak is moved to the current global worst angle ω (Eq. 27). Stop when ω
stops improving or hits a user floor. This is a **monotone worst-element
push-up loop** bolted onto the same solver.

## Boundary handling (question 3) — the part we care most about

Three modes, explicitly discussed (Section 3.3):

1. **Frozen surface (hard positional constraints).** "The simplest, and most
   frequently used way ... is to fix the positions of the surface vertices.
   **Our system supports this option**, when the surface needs to be preserved
   exactly." So ECR runs with surface vertices fully frozen; the interior
   problem stays convex quadratic. The paper immediately warns this is often
   too restrictive (see verdict below).
2. **Tangential sliding (their recommended default).** Per-vertex quadratic
   attraction selected by vertex class (Eq. 21):
   - regular surface vertex `v ∈ S`: tangent-**plane** term `β(n̂·v + d̂)²`
     (plane through closest surface point `v̂`, normal = input surface normal) —
     the vertex slides in the local tangent plane at zero cost;
   - feature vertex `v ∈ F`: tangent-**line** term `α(v − (v̂ + a·t̂))² + a²`
     with auxiliary scalar `a` — slides along the feature tangent;
   - corner `v ∈ C`: **point** anchor `α(v − v̂)²`.
   Weights `α = 20`, `β = 10` by default. Surface-edge local steps get an extra
   `+ β n̂_ij · n̆` term (Eq. 20, `n̆` = average original surface normal at the
   edge ends, β = 10) discouraging target axes that point out of the surface.
3. **Fully free** (not used; shown only to criticize Aigerman-style results).

Evidence on the frozen mode:

- **Fig. 11 (Dragon):** a hex with three surface quad faces is tangled such
  that *no inversion-free solution exists without slightly relaxing the
  boundary vertices*. Frozen-surface untangling is provably impossible on such
  configurations — this is a property of the input, not of ECR.
- **Competitors that always freeze the surface** (Ruiz-Gironés 2014a/b,
  Mesquite's constrained mode) fail to untangle meshes ECR handles, and the
  paper attributes part of that to the frozen surface — though it also shows
  failures where the surface mesh is fine (Armadillo leg, Fig. 4e), so frozen
  boundary is not the only failure driver.
- **Hard-constraint stress test:** a random interior vertex displaced by up to
  400% of the average edge length and *held fixed as a hard constraint* still
  yields an inversion-free result — sparse hard anchors are handled gracefully.
- **Stiffness sweep (block model):** `α = β = 100` gives MSJ 0.12 at mean
  surface distance 2.3e-5; `α = β = 5000` gives MSJ 0.03 at 2.0e-5. Quality
  degrades smoothly, not catastrophically, as boundary attraction stiffens;
  the solver still returns inversion-free output in both settings.

**Frozen-surface verdict for our post-snap lane:** ECR degrades gracefully
under frozen boundaries — the machinery runs unchanged and the penalty scheme
cannot diverge — but the achievable minimum quality is capped by the frozen
surface configuration, and specific pathologies (a cell with ≥ 3 boundary
faces, degenerate surface quads) are *unfixable* without letting those
vertices move. The paper's own preferred middle ground, tangent-plane sliding,
is exactly compatible with our wall-preservation invariant: to first order,
sliding in the wall tangent plane does not increase `wall_dev` (0.008 gate
< 0.02), and feature/corner vertices stay pinned to lines/points. That mode,
not full freezing, is the right port target.

## Experiments (questions 4-6)

- 15+ models, 2.5K-160K hexes, from polycube (bust, armadillo, bunny, dancing
  children, cap, block, dragon), singularity-restricted field (hanger,
  impeller), grid-based (cad6, part29, it-vhs: 1K-3K inverted), octree/Hexotic
  (asm001, asm106, clef2: 0 inverted but min MSJ 0.02-0.08). All become
  inversion-free; e.g. it-vhs −0.86 → +0.35 min MSJ; Hexotic asm106 0.02 →
  0.25 with mean surface deviation 8.6e-5 (Metro). Mean surface deviation is
  1e-5 to 1e-3 across the table — on par with the meshers themselves.
- Corrupted stress tests (Table 2): 82-96% inverted elements, all untangled
  (e.g. asm001 96% inverted, min MSJ −0.99 → +0.12).
- **Convergence** (Fig. 10): typically **< 5 local-global iterations** on
  regular inputs, 20-25 on corrupted ones; each global step ≤ ~5 penalty/GMRES
  solves. Not monotone per-iteration in inverted-element count, but converges.
- **Cost** (i7-4770K, 16 GB, 2015): 2 s (2.5K hexes) to 250 s (dragon 14K, 84
  inverted); corrupted asm001 (25K hexes, 24K inverted) 779 s; claimed < 2 min
  for a typical 200K-hex mesh. Runtime scales with size *and* initial
  inversion count.
- Beats Mesquite (Knupp 2001+2003) and Ruiz-Gironés 2014a/b on both min and
  avg MSJ everywhere compared; untangles where they fail. Generic tet-mesh
  optimization on the 8-corner-tet overlap decomposition (Aigerman-Lipman
  2013) fails with fixed boundary and over-deviates with free boundary.

## Limitations (stated by the authors)

- No inversion-free guarantee; feasibility of the connectivity itself is an
  open problem, and frozen-boundary infeasible configurations exist (Fig. 11).
- Extreme grading: current/target edge-length ratios ≥ ~32 ill-condition the
  matrices and can break the solver.
- Garbage target lengths (from heavily distorted input used as its own length
  estimate) can prevent convergence.
- Needs a QP solver (Gurobi) for constrained local steps — though only on the
  minority of cones where the normal average violates constraints — and GMRES
  for the global solve. 2015 runtimes are minutes-scale on 10-100K hexes.
- Optimizes MSJ / cone angles, not OpenFOAM skewness directly. Angle
  rectification strongly correlates with face-orthogonality and centroid-offset
  skew, but our boundary-skew 2.84 → lower push needs verification against the
  actual OpenFOAM skew metric, not assumed.

## Applicability to AutoTessell frozen-surface post-snap lane

Where it lands in our pipeline: after wall-fit snap in
`core/generator/native_hex/mesher.py` (snap + `HEX-SKEW-INNER-RELAX` at
`mesher.py:1530`, post-snap boundary Laplacian at `mesher.py:1142`, pre/post
skew scans at `mesher.py:1107`). Our current post-snap toolset is Laplacian
smoothing with accept/revert guards — no inversion-aware objective, no
per-cone feasibility notion, no tangential sliding; boundary vertices either
move freely (risking wall_dev) or are frozen.

- ECR replaces "smooth then revert if skew worsened" with an objective that
  *cannot* silently trade inversions for smoothness, and its per-cone worst
  angle α_ij gives a localized quality field for free.
- Mode for us: **corners/feature vertices pinned (point/line terms), regular
  wall vertices on tangent-plane terms with large β** — preserves wall targets
  to first order while unlocking the quality the fully frozen mode caps. A
  fully frozen mode also works (paper-supported) as the conservative first
  step: interior-only ECR is strictly better-informed than interior Laplacian.
- The wall_dev_max 0.008 → 0.02 gate leaves real headroom: the paper's mean
  deviations (1e-4 relative scale) suggest tangent-plane sliding costs little
  normal deviation, but our gate is a max, not a mean — needs a direct check.
- The 3.6 max-min loop is the natural mechanism for "push boundary skew 2.84
  further below 3.0": monotone worst-cone improvement with a stop rule.

## Falsifiable implementation cards

### HEX-ECR-1 - cone feasibility census (diagnostic, cheap)

- Compute per-directed-edge worst cone angle α_ij on the post-snap mesh
  (Eq. 6 normals, no solver needed).
- Pass: report histogram + count of infeasible cones (α ≥ 90°) and near-tight
  cones (α > 85°); correlate the worst-α edges with the current worst-skew
  boundary faces on the cylinder benchmark.
- Falsifier: if worst-skew faces do NOT coincide with worst-α cones, ECR is
  optimizing the wrong proxy for our skew gate and the port priority drops.

### HEX-ECR-2 - interior-only ECR (frozen surface)

- Port local-global loop with all surface vertices hard-frozen; local step =
  normal average with feasibility check (skip Gurobi; fall back to
  min-worst-angle choice per paper); global step = GMRES on Eq. 25 without
  E_boundary.
- Pass: on the cylinder post-snap mesh, zero negative-volume cells, wall_dev
  unchanged bit-for-bit (surface frozen), internal skew and non-ortho not
  worse, boundary skew ≤ current 2.84.
- Stop rule: if boundary skew is unchanged (frozen ring dominates), do not
  iterate harder — move to HEX-ECR-3.

### HEX-ECR-3 - tangent-plane sliding mode

- Add Eq. 21 vertex-class terms: wall vertices on tangent planes of their
  snap targets, feature edges on tangent lines, corners pinned. β sweep
  {10, 100, 1000}.
- Pass: boundary skew < 2.84 with wall_dev_max < 0.02 (hard veto) on the
  cylinder gate case; report the β-vs-(skew, wall_dev_max) frontier.
- Falsifier: if every β violating nothing also improves nothing, the paper's
  sliding benefit does not transfer to our OpenFOAM skew metric.

### HEX-ECR-4 - metric bridge

- Verify the assumed MSJ/cone-angle ↔ OpenFOAM skewness correlation: scatter
  per-cell min corner-tet scaled Jacobian vs per-face skew on ≥ 3 bench
  meshes.
- Pass: monotone-ish relation in the bad tail (worst 5%). If not, ECR gains
  must be re-scored under our own checker before more porting effort.

## Snowball references (≤ 5)

1. Ruiz-Gironés, Roca, Sarrate, Montenegro, Escobar (2014a), "Simultaneous
   untangling and smoothing of quadrilateral and hexahedral meshes...",
   Advances in Engineering Software — the frozen-surface Gauss-Seidel
   competitor; its documented failures define what frozen-boundary methods
   cannot fix.
2. Aigerman, Lipman (2013), "Injective and bounded distortion mappings in 3D",
   ACM TOG 32(4) — the local-global template ECR adapts; also the negative
   result for tet-decomposition hex optimization.
3. Erickson (2014), "Efficiently hex-meshing things with topology", Discrete &
   Computational Geometry 52(3) — theory of when a hex connectivity admits a
   valid embedding (why no method can guarantee untangling).
4. Pébay, Thompson, Shepherd, Knupp et al. (2007), "New applications of the
   verdict library...", IMR 16 — the standard hex quality metric definitions
   (MSJ, the 0.5 high-quality threshold) used as gates throughout.
5. Knupp (2003), "A method for hexahedral mesh shape optimization", IJNME
   58(2) — the shape-optimization half of Mesquite; baseline for what
   one-vertex-at-a-time achieves (Knupp 2001 untangling already in the sweep).

## Decision

Port target confirmed for the post-snap quality lane, in two stages:
interior-only frozen-surface ECR first (safe under the wall_dev hard veto),
then tangent-plane sliding for the remaining boundary-skew margin. Run
HEX-ECR-1 and HEX-ECR-4 (pure diagnostics) before writing any solver code —
they decide whether cone rectification actually moves our OpenFOAM skew gate.
Do not claim ECR guarantees inversion-free output; it is empirical, and
frozen-boundary infeasible configurations (≥ 3 boundary faces per cell) need a
topological fix (pillowing, section 3 of the citation sweep), not more
smoothing.
