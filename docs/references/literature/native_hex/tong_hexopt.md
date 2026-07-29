# Tong & Zhang 2024 - HexOpt: Fast and Robust Hexahedral Mesh Optimization via Augmented Lagrangian, L-BFGS, and Line Search

## Bibliographic record

- Hua Tong, Yongjie Jessica Zhang, *Fast and Robust Hexahedral Mesh Optimization via
  Augmented Lagrangian, L-BFGS, and Line Search*, arXiv:2410.11656v3 [cs.CG],
  23 Dec 2024 (SIAM copyright 2025; journal version in CAD 196:104073, 2026 —
  DOI confirmed 2026-07-25 via native_hex transition-sheet snowball:
  `10.1016/j.cad.2026.104073`. No re-read needed; content already covered
  from the arXiv preprint above).
- Local PDF: `papers/pdf/37_tong_hexopt_arxiv.pdf`,
  SHA-256 `1bc0f38e0d500fa8f01e3c6f74ec2f63c0a2fa23dfc81cdb79cc6b881819f54e`.
- Code + meshes: <https://github.com/CMU-CBML/HexOpt> (CMU CBML group).
- Status: `FULL_READ` (10/10 pages, 2026-07-23).

## Problem and claimed scope

Post-optimization of an existing all-hex mesh `H` against a watertight, manifold input
triangle mesh `T` with annotated sharp features. Two simultaneous goals: (1) maximize
the minimum scaled Jacobian of `H`; (2) force the quad surface `SH` to lie exactly on
`T`. Handles tangled/inverted inputs (they intentionally tangle all interior vertices
before optimizing). No claim of a theoretical quality lower bound — empirical only.
This is exactly the shape of our post-snap quality lane: quality maximization **under a
stay-on-surface constraint** (our wall_dev hard veto).

## Formulation (transcribed)

Quality metric: per hex `h`, scaled Jacobian sampled at the 8 corners plus the body
center (center edge vectors = opposite-face-center differences); `SJ(h)` = min of the 9
values, range [-1, 1].

Three-stage objective design (2D landscapes in their Fig. 2):

1. **ReSJ** (Eq 2.2) — rectified scaled Jacobian, threshold `Θ`:
   `ReSJ(h,Θ) = SJ(h) if SJ(h) ≤ Θ else Θ`. Rejected: non-differentiable points and
   local minima in the negative region; ablation shows it fails to converge on *all*
   models.
2. **ReHJ** (Eq 2.3) — hybrid: use the raw Jacobian in the inverted region (more convex,
   everywhere differentiable there):
   `ReHJ = J(h) if J(h) ≤ 0; SJ(h) if J(h) > 0 and SJ(h) ≤ Θ; Θ otherwise`.
   Rejected: `SJ` is dimensionless so its gradient scales inversely with edge length —
   adaptive meshes blow up (fails on anc101, isidore_horse).
3. **ReHQJ** (Eq 2.5–2.6, adopted) — rescale both branches to *quadratic* measures with
   the element's average edge length `ē` treated as a **constant** (excluded from the
   gradient):

   ```text
   QJ(x)  = J(x) / ē
   QSJ(x) = SJ(x) * ē²
   ReHQJ(h,Θ) = QJ(h)   if J(h) ≤ 0
              = QSJ(h)  if J(h) > 0 and SJ(h) ≤ Θ
              = Θ       if SJ(h) > Θ
   ```

   This makes gradients proportional to element size — scaling-invariant optimization on
   adaptive meshes. Untangling needs no barrier: inverted elements simply live on the
   `QJ` branch and are pushed positive by the same energy.

Constrained problem (Eq 2.7): `max Σ_h ReHQJ(h,Θ)  s.t.  Z_k = Z_k^t`, where `Z_k` is
the stacked surface-vertex vector (Ns points) and `Z_k^t` are their **target projection
points, recomputed every iteration** (Algorithm 2.1 line 3).

Augmented Lagrangian (Eq 2.8–2.9):

```text
min L = -Σ_h ReHQJ(h,Θ) + Σ_k [ λ_i (Z_k - Z_k^t) + (ρ/2)(Z_k - Z_k^t)² ]
λ_i ← λ_i + ρ (Z_k - Z_k^t)        after each iteration
ρ   ← 2ρ                            each time Σ ReSJ(h,Θ) = Nh·Θ is reached
```

`Θ` schedule: start at `Θ = 0` (all-positive-Jacobian first), converge, then increment
`Θ` by **0.01** with the previous solution as warm start; repeat until infeasible. Outer
termination: all surface points within `1e-8` of their targets.

## Surface-constraint parameterization (key question 2)

Per-vertex **closest-point projection onto T, recomputed every outer iteration** — no
UV, no fixed barycentric anchor. Three vertex classes (their Fig. 3):

- **Sharp corner** → target is the exact corner point (pinned, exact).
- **Sharp-edge point** → closest projection among candidate sharp edges (slides *along*
  the feature curve).
- **Face point** → closest projection among all triangles (slides *across* the surface
  freely).

Because targets chase the moving vertex, the AL term is effectively a
point-to-surface distance penalty: face points are **not** frozen at snapped positions —
they slide tangentially wherever quality wants, while the AL/ρ-doubling drives normal
deviation to ≤ 1e-8. Target search is a global traversal over all corners/edges/faces
each iteration (they note a search box gives similar results but global search maximizes
success — this is the dominant cost).

## Algorithm (key question 3)

Outer loop (Alg 2.1): recompute targets → one L-BFGS update (Alg 2.2) → every 100
iterations run **smart Laplacian smoothing** on `H` (escapes local minima where surface
points get stuck; "smart" = quality-guarded). Constants: history `m = 15`, `λ = 0`
initial, `ρ = 1e-8` initial (very soft start), Armijo `c1 = 1e-4`.

L-BFGS specifics: standard two-loop recursion; initial scaling `H0 = (s^T y / y^T y) I`;
safeguard: if `y^T s == 0` set the curvature-pair weight to `1e8` (skip degenerate
pair). Armijo backtracking from `a = 1`, shrink factor stated as `η = 0.5` in the text
but `0.9` in Algorithm 2.2 line 27 (**internal inconsistency — check the released code
before porting**); abort backtracking below `1e-8` (accept failure, next outer iteration
retries with new targets). Inversion handling is purely energetic (the `QJ` branch);
there is no feasibility barrier and no per-step positivity guarantee — validity is only
certified at convergence of each `Θ` stage.

## Experiments (key question 4)

8 models on i7-12700 / 64 GB, inputs from HexaLab + their HybridOctreeHex, covering
polycube (rkm012_1, mount2), cross-field (impeller, mid2Fem), interactive (bunny, CAD4),
octree (anc101, isidore_horse). All interiors intentionally tangled to min SJ = -1.0.

| Model | #Elem | PreSJ min | PostSJ min | PreMaxDist | Time L-BFGS/GD (s) |
|---|---|---|---|---|---|
| rkm012_1 | 18,751 | -1.0 | 0.60 | 2.1e-3 | 25/42 |
| mount2 | 6,208 | -1.0 | 0.37 | 5.5e-3 | 10/36 |
| impeller | 11,174 | -1.0 | 0.43 | 9.5e-4 | 20/48 |
| mid2Fem | 908 | -1.0 | 0.48 | 2.6e-4 | 5/10 |
| bunny | 2,832 | -1.0 | 0.12 | 0.0 | 8/18 |
| CAD4 | 2,704 | -1.0 | 0.12 | 0.0 | 9/20 |
| anc101 | 135,982 | -1.0 | 0.33 | 3.7e-3 | 69/198 |
| isidore_horse | 182,124 | -1.0 | 0.54 | 2.7e-2 | 54/171 |

- **PostMaxDist = 0 for all models** (max relative surface deviation / bbox diagonal) —
  the surface lands exactly on `T`.
- Post min SJ always exceeds the *original* (untangled) mesh's min SJ; claims to surpass
  Edge-Cone Rectification (Livesu 2015 [18]) and to eliminate self-intersections, but
  gives **no side-by-side ECR numbers** — the comparison is a prose claim, not a table.
- L-BFGS ≈ 2x slower per iteration than GD, ~10x fewer iterations; net ~50–65% wall-time
  reduction. ~182k hexes in 54 s.
- Convergence shape: 60–70% of the final min-SJ gain arrives in the first ~10% of
  runtime — early stopping is practical.
- Ablations: ReHJ diverges on the two adaptive octree meshes; ReSJ diverges everywhere.
  Best results on aspect-ratio≈1 meshes; authors state the sweet spot is
  **post-optimization of octree-based meshes** — exactly our engine family.

## Limitations and robustness (key question 5)

- No theoretical lower bound on the achieved min scaled Jacobian (explicit limitation).
- Automatic sharp-feature path-finding is unreliable when large-aspect elements sit near
  features (mount2, CAD4): boundary quads with two adjacent edges on a straight path
  have SJ = 0; fixing that needs padding/pillowing (adds singularities). Their fallback:
  the **user must supply the one-to-one corner/edge correspondence** between `T` and
  `SH`.
- High-aspect-ratio elements are hard (SJ hypersensitive along short edges).
- Feasibility can become empty as `Θ` grows — loop just stops at the last feasible `Θ`.

## Determinism (key question 6)

Not discussed in the paper. The algorithm itself has no randomness (deterministic
projections, two-loop L-BFGS, fixed schedules), so determinism reduces to floating-point
reduction order and closest-candidate tie-breaking in the global target search. For our
port: pin the traversal order and tie-break rule and it is bitwise-reproducible — matches
the plan's "solver iteration order must be pinned" flag.

## Applicability — frozen vs sliding verdict for our wall-fit contract

Current AutoTessell contract is **frozen**: `_wall_fit_snap`
(`core/generator/native_hex/mesher.py:749`) projects boundary vertices onto the surface
with per-vertex accept/revert, then surface vertices are hard-frozen and only interior
vertices relax (`core/generator/native_hex/mesher.py:964`, `:1532`, `:1895` — "frozen ⇒
wall_dev 불변").

HexOpt is **sliding, not frozen**: face points glide across `T`, edge points along
feature curves, corners pinned. It does *not* preserve snapped positions — it preserves
*membership on the surface* (to 1e-8, PostMaxDist = 0).

**Verdict: sliding is admissible for us — wall_dev-compatible by construction.**
Tangential slide on the input triangle surface keeps point-to-surface deviation at ~0,
so the wall_dev gate holds even though snapped positions change. What we lose vs frozen:
(a) mid-optimization iterates are transiently off-surface (soft ρ start at 1e-8), so the
gate must be checked at *stage convergence*, not per-step — or ρ must start hard;
(b) tangential drift can degrade surface-mesh sizing/feature alignment, so feature edges
and corners must be classified first (their corner/edge/face taxonomy) or slide will
round sharp features — this is their own reported failure mode when feature paths are
mis-detected. Recommended contract: keep the frozen lane as the safe default, add a
HexOpt-style sliding lane whose acceptance test is the existing wall_dev + skew gates on
the bench; adopt only if strictly better (plan's ECR-vs-HexOpt bake-off rule).

## Confirm/refine cards

### HEXOPT-CONFIRM-1 — plan Wave-1 premise confirmed

- The plan's claim ("HexOpt maximizes scaled Jacobian while constraining surface points
  to the input triangle mesh via augmented Lagrangian") is accurate as read. The
  surface-vertex taxonomy (corner pinned / edge slides on curve / face slides on
  surface) is the exact mechanism. Confirmed; no plan edit needed on this point.

### HEXOPT-REFINE-1 — plan contract wording needs a correction

- Plan line "surface vertices move only *on* their wall-fit targets" is stronger than
  what HexOpt does: targets are *recomputed every iteration* (moving-target closest
  point), i.e. vertices move on the **surface**, not on fixed targets. If we want fixed
  targets we are implementing a stricter variant than the paper; the bench should test
  both. Refine the plan wording to "on the input surface (moving closest-point
  targets)".

### HEXOPT-IMPL-1 — ReHQJ energy port

- Port Eq 2.5–2.6 exactly: `QJ = J/ē` for `J ≤ 0`, `QSJ = SJ·ē²` for `0 < SJ ≤ Θ`, `ē`
  held constant in the gradient. Pass: on a synthetically tangled cube grid, energy-only
  descent (no constraints) untangles to all-positive Jacobians; gradient magnitude is
  invariant under uniform mesh rescale (x0.01 / x100).

### HEXOPT-IMPL-2 — AL + Θ-continuation schedule

- `Θ: 0 → +0.01` warm-started stages; `ρ: 1e-8`, doubled at stage completion;
  `λ` update per Eq 2.9; stage gate = `Σ ReSJ = Nh·Θ` AND `max‖x−x^t‖ ≤ tol` where tol
  is our wall_dev gate (not blindly 1e-8). Pass: on the octree cube/tube bench, boundary
  skew strictly decreases from 2.84 and wall_dev gate holds at every exported stage.

### HEXOPT-IMPL-3 — resolve the 0.5-vs-0.9 backtracking discrepancy

- Text says η=0.5, Algorithm 2.2 says 0.9. Check `CMU-CBML/HexOpt` source for the real
  constant before porting; record which one wins on our bench. Pass: constant documented
  with a source-code citation in the port.

## Snowball references (≤5)

1. [18] Livesu, Sheffer, Vining, Tarini, *Practical hex-mesh optimization via edge-cone
   rectification*, ACM TOG 34, 2015 — the ECR baseline HexOpt claims to beat; our
   bake-off counterpart (already in plan).
2. [30] Tong, Halilaj, Zhang, *HybridOctreeHex*, J. Comput. Science 78, 2024 — the
   companion octree generator whose fixed-rate steepest descent HexOpt replaces; sizing
   context for our octree lane.
3. [8] Huang, Zhang, Wang, Liu, Fu, *Untangling all-hex meshes via adaptive boundary
   optimization*, Graphical Models 121, 2022 — the three-stage untangler HexOpt cites as
   effective-but-slower; alternative if AL stalls.
4. [16] Lin, Jin, Liao, Jian, *Quality guaranteed all-hex mesh generation by a
   constrained volume iterative fitting algorithm*, CAD 67, 2015 — per-step
   positive-Jacobian fitting (the frozen/feasible-path philosophy; contrast lane).
5. [32] Wang, Zheng, Yu, Shao, Gao, *Structure-aware geometric optimization of
   hexahedral mesh*, CAD 138, 2021 — base-complex/singularity-aware alternative; cited
   as failing on tangled meshes (negative result worth knowing).

## Decision

Use HexOpt as the primary design for the Phase-1 post-snap quality lane: ReHQJ energy +
AL sliding surface constraint + L-BFGS/Armijo + periodic smart Laplacian. Keep the
current frozen wall-fit snap as the safe default until the sliding lane beats it on the
bench under the wall_dev and skew gates. Do not adopt their automatic feature
path-finding (their own weak spot); reuse our existing feature classification to feed
the corner/edge/face taxonomy.
