# Zhang et al. - Constrained Remeshing Using Evolutionary Vertex Optimization

## Bibliography and access

- Wen-Xiang Zhang, Qi Wang, Jia-Peng Guo, Shuangming Chai, Ligang Liu,
  Xiao-Ming Fu (corresponding). University of Science and Technology of China.
- *Computer Graphics Forum* 41(2), 237-247, 2022 (Eurographics 2022).
- DOI: `10.1111/cgf.14471`.
- Local full text: `papers/pdf/32_zhang_2022_evolutionary_vertex_optimization.pdf`.
- Review status: `FULL_READ` on 2026-07-23. Pages 11/11 text-extracted and read
  (the local PDF is the 11-page published CGF version, not a double-spaced
  manuscript). Title, authors, and DOI verified from page 1. This is the method
  Liu 2024 cites as "CREVO"; that shorthand does not appear in the paper itself.
- Authors state a C++ implementation, source code, and an executable are in the
  paper's supplementary material.

## Problem and contract

Remeshing is posed as one constrained optimization over both connectivity and
geometry:

```text
min_R E(R)   s.t.  c(R) <= 0,
```

where `E` is a real objective (e.g. vertex count `Nv`, worst angle) and `c`
collects hard constraints (e.g. two-sided Hausdorff bound, Delaunay condition,
manifoldness). Both `E` and `c` may be non-differentiable; two-sided Hausdorff
distance and mesh complexity explicitly are.

The method is a **retaining strategy**: start from an initialization that
already satisfies every hard constraint, then apply only local operations that
keep the mesh inside the feasible set. The paper's criticism of prior retaining
methods (Hu 2017, Liu 2015, Wang 2019) is that they use constraint checks only
to *reject* candidate operations whose geometry was computed by
constraint-blind rules (endpoint collapse, QEM point, tangential Laplacian);
the constraints never inform *where* the vertex goes, so optimization stalls
early ("early entrapment"). The contribution is to make the geometric half of
each operation a constrained search.

## What "evolutionary vertex optimization" actually is

Not population-of-meshes. Each local operation (edge collapse, edge split,
vertex relocation) is decomposed into

1. a **topological component** with a fixed connectivity pattern, chosen by
   existing scheduling rules from prior work; and
2. a **geometric component**: the position of exactly one vertex (the collapse
   vertex, the inserted vertex, or the relocated vertex), optimized while all
   other vertices stay fixed.

The geometric component is solved by **differential evolution (DE)** in R^3,
variant `DE/target-to-best/1/bin`, which is derivative-free. Constraints are
folded into the objective with an infinite barrier:

```text
I(R) = 0 if c(R) <= 0, +infinity otherwise;    f(v) = E(R(v)) + I(R(v)).
```

Per vertex update:

- **Initialization:** population `{v_i^0}` of `Np` points sampled uniformly at
  random on the one-ring faces of the vertex being optimized.
- **Mutation (target-to-best/1):**

```text
u_i^k = v_i^k + F (v_best^k - v_i^k) + F (v_r1^k - v_r2^k),
```

  with `v_best^k` the current best member, `r1 != r2 != i` random indices, and
  mutation scale `F in (0,1)`.
- **Crossover (binomial):** per coordinate `j in {x,y,z}`,

```text
w_j,i^k = u_j,i^k  if rand[0,1] <= Cr or j = j_rand,   else v_j,i^k,
```

  where `j_rand` guarantees at least one donor coordinate survives.
- **Selection (greedy):** `v_i^{k+1} = w_i^k` iff `f(w_i^k) <= f(v_i^k)`;
  monotone non-worsening by construction.
- **Termination:** relative objective change `< 1e-4` over 5 successive
  iterations, or 100 iterations.
- **Defaults from parameter sweeps:** `Np = 20`, `F = 0.7`, `Cr = 0.9`. Runtime
  grows roughly linearly in `Np`; small `F` and large `Cr` cost time; large
  `Cr` with medium `F` gives the fewest vertices.

Because the barrier is infinite, an infeasible candidate can never be selected
over a feasible one, and the population is seeded near the current (feasible or
nearly feasible) configuration. Constraints are therefore **hard gates**, not
penalties - identical in spirit to explicit-check rejection, but the DE search
actively hunts for feasible, objective-improving positions instead of testing
one heuristic point.

## Application 1: error-bounded Delaunay mesh simplification

```text
min_R Nv   s.t.  d_H(M, R) <= delta_H,   R is a Delaunay mesh.
```

- **Initialization:** Liu et al. 2015 edge splits + planar edge flips convert
  `M` to a Delaunay mesh without changing the shape, so `d_H = 0` initially.
- **Simplification:** edge collapse only. For each edge `e`, DE minimizes the
  pure barrier `I(v)` over the collapse-vertex position - i.e. a *feasibility
  search*: find any position keeping `d_H(M, R_e) <= delta_H` and the local
  Delaunay condition. If one is found, `e` is collapsible. All edges are
  traversed repeatedly until no edge is collapsible.
- `d_H(M, R_e)` during the search is evaluated with the *local* method of
  Hu et al. 2017 (the collapse only perturbs a small patch); final reported
  distances use Metro.
- **Specified-vertex-count variant** (the Yi 2018 goal): the cost of an edge is
  `min_v d_H(M, R_e)` s.t. Delaunay, solved by DE; edges are collapsed
  cheapest-first with a priority queue, updating the costs of affected edges
  (one-ring edges of vertices whose Delaunay status the collapse can touch)
  until the target count is reached. Running this variant with a
  stop-when-cost-exceeds-threshold rule reproduces the bounded-error goal but
  is about 6x slower than plain traversal (1774.9 s vs 278.8 s on an
  11764-vertex model), so priority ordering is not worth it for the
  bounded-error task.

## Application 2: error-bounded small/large-angle improvement

Inputs: min/max angle thresholds, a vertex budget (upper bound), and
`delta_H`. The angle interval is explicitly a **soft** constraint used to
select which triangles get topological operations; Hausdorff bound and
manifoldness are hard.

Workflow follows Wang et al. 2019: vertex insertion to break large angles,
edge collapse to remove small angles, valence-optimizing flips, then
smoothing - but with two changes: initialization reduces the vertex count
below budget by remeshing a gradually increased target edge length under
explicit Hausdorff checks (as in Yang 2020), and every vertex position (the
inserted vertex in angle-removal, and each bad-triangle vertex in the
smoothing step, one at a time) is computed by DE:

```text
large angles:  min_v  max_{alpha in f, f in Omega(v)} alpha
small angles:  max_v  min_{alpha in f, f in Omega(v)} alpha
s.t.  d_H(M, R) <= delta_H,   R is a manifold mesh,
```

with `Omega(v)` the one-ring triangles of `v`. Convergence on one example:
75 iterations take `theta_max` from >165 deg to 89.92 deg and `theta_min` to
33.71 deg at `Nv = 6858`, `d_H = 0.1704%`.

## Guarantee analysis

- **Hausdorff bound and Delaunay/manifold status: hard invariants by
  construction** - the initialization satisfies them and every accepted
  operation re-verifies them - *up to the correctness of the distance
  evaluator*. The in-loop evaluator is Hu 2017's local sampled computation and
  the final report is Metro; both are sampled, so the same caution as Hu 2016
  applies: a sampled two-sided distance can underestimate the continuous
  maximum. The paper never claims exact envelope containment (contrast
  Mandad 2015 / `TRI-TOL-*`).
- **Angles: purely empirical, no certificate.** The conclusion states outright
  that final angles cannot be guaranteed to fall in the specified range for
  arbitrary models. Over the 1606-model set at `delta_H = 0.2%`, budget 8000:
  `theta_min` avg 36.07 deg, std 5.27, **worst 10.07 deg**; `theta_max` avg
  89.21 deg, worst 156.62 deg; `N_<30` avg 9.677 but max 4321; `N_>90` avg
  31.4 but max 5880.
- **Verdict on the "theta_min ~ 40 deg" claim from Liu 2024:** that figure is
  a *single-model empirical* number (Fandisk, reported as 40.0 deg in Liu
  2024's comparison table), consistent with this paper's best-case results
  (e.g. `theta_min = 38.93` and `38.67 deg` appear in Figs. 11/18). It is not
  a certified bound and not even the dataset average (36 deg). CREVO's
  strength is the *distribution*: most models land in the mid-30s with both
  tails removed (`N_<30 = N_>90 = 0` on the showcased models), which no other
  corpus method achieves empirically. Hu 2016's 30 deg remains the only
  certified-style claim, at far higher cost.
- **Termination:** simplification terminates because collapses monotonically
  remove vertices and a full no-collapsible-edge traversal stops the loop. The
  angle-improvement loop inherits Wang 2019's heuristic iteration with no
  convergence proof; the paper caps it in practice (Fig. 6 runs 75 iterations).
- **Determinism:** DE is randomized. Ten runs on ten models give final-count
  standard deviations of 9.4-19.4 vertices - small but nonzero. A production
  port needs a seeded RNG for reproducibility.
- **Robustness to tessellation:** randomly splitting input edges to make five
  alternative tessellations changes the simplified output by <5% in vertex
  count and leaves angle histograms similar - good empirical insensitivity.

## Experiments and runtime reality

Setup: C++, single desktop i7-9700 (3.0 GHz), 16 GB. Defaults
`delta_H = 0.1%` (simplification), `0.2%` (angles), both w.r.t. the
bounding-box diagonal.

- **Headline (Fig. 1, Pegaso 14988 vertices):** simplifies to a Delaunay mesh
  with 2568 vertices at `d_H = 0.0968%`; Liu 2015 and Yi 2018 need 10923 and
  10275 vertices for the same bound, and forced to 2568 vertices they blow the
  bound (0.4856% / 0.3923%). Initialization 0.035 s, simplification
  **188.4 s**.
- **Angle improvement (Fig. 3, Dinosaur 13000 vertices,** `N_<30 = 6351`,
  `N_>90 = 9524`): 47.6 s to reach `Nv = 5887`, `N_<30 = N_>90 = 0`,
  `theta in [36.76, 87.62] deg`. Wang 2019 with added explicit checks
  ([WYL19]*) only reaches `[24.47, 108.26] deg` at more vertices.
- **Cost profile:** two-sided Hausdorff evaluation is ~60% of runtime in both
  applications. Time grows with input size (Fig. 19, inputs to ~1.5M
  vertices, hundreds to ~18000 s); pre-simplifying with Yang 2020 under the
  same bound then running CREVO recovers most of the quality at a fraction of
  the cost. Yi 2018 *fails outright* above 200k input vertices; its
  distances land in `[0.9%, 1%]` vs CREVO's `[0.09%, 0.1%]`.
- **Relocation-strategy ablation (Fig. 20):** inside the same pipeline, final
  vertex counts on one model: QEM-point (Dyer 2007) 6441, endpoint collapse
  (Liu 2015) 9687, pure random one-ring sampling 4835, directional
  direct-search 3588, **DE 2353**. So the DE search itself, not the barrier
  formulation, provides most of the win; even naive feasible sampling already
  beats the deterministic heuristics.
- **vs grid-refinement sampling (HSS, Zint 2018, 100 models):** DE has a
  better quality/time tradeoff; HSS needs 4.1x CREVO's time to match its
  vertex counts.
- **Extensive testing:** 1606 models (1/3 CAD, 2/3 organic). Simplification
  succeeds on all; vertex-count ratio vs [LXFH15]* averages 4.6x fewer
  (max 40.9x). Same-count comparison vs Yi 2018 on the full set: Hausdorff
  ratio avg 4.19x smaller, at comparable time (ratio avg 1.17).
- **Relative to the corpus:** ~13 s per 1k input vertices for simplification
  and ~4 s per 1k vertices for angle improvement puts CREVO between Cheng 2019
  (fast, `theta_min` 11 deg) and Hu 2016 (certified 30 deg, ~470x slower than
  plain remeshers, can loop). Liu 2024 measures the same order: its Joint
  method 1.88 s vs CREVO ~100 s class on one model. Not real-time; authors
  say so explicitly.

## Topology-operation interplay

DE never changes connectivity. All connectivity edits are the standard fixed
patterns (split, collapse, flip) scheduled by prior methods' rules: Liu 2015's
split/flip schedule for Delaunay initialization, collapse traversal or
priority queue for simplification, Wang 2019's insertion/collapse/flip
schedule for angles. The paper's observation is precisely that the topological
half needs no new machinery - the underexploited degrees of freedom are the
vertex positions. That makes the technique a **drop-in replacement for the
geometric half of any local-operation loop**, including ours.

## Limitations and claim boundary

- No angle certificate; worst case over the dataset is `theta_min 10 deg`.
- **Locked angles:** angles between sharp feature edges cannot be improved
  without violating the Hausdorff bound - a structural failure mode the
  authors illustrate; feature-adjacent quality is bounded by geometry, not by
  the optimizer.
- Feature preservation is only implicit: small `delta_H` keeps sharp features;
  once the tolerance grows they erode. The authors mention detecting and
  fixing features in advance as the remedy but do not present that machinery.
- Sampled (not exact) Hausdorff evaluation in the accept gate and the final
  audit.
- Randomized output; only statistical repeatability shown.
- ~60% of runtime in distance evaluation; wall-clock is minutes per 10k-vertex
  model - unsuitable as a default always-on pass, fine as a quality tier.
- Manifold input assumed throughout; no repair capability, no self-intersection
  discussion beyond the constraint set, no boundary-loop policy stated.
- Per-vertex DE optimizes each vertex greedily one at a time
  (Gauss-Seidel-style); no global convergence statement.

## AutoTessell applicability

Where it plugs in: the relocation step of the Botsch/Dunyach loop in
`core/preprocessor/native_remesh/isotropic.py` currently does tangential
smoothing plus projection/nearest-vertex snapping with all feature vertices
frozen, and collapse targets are heuristic points. Both are exactly the
"constraint-blind geometry + explicit reject" pattern this paper shows is
leaving large quality/simplification headroom (Fig. 20: heuristic points give
2.7-4x more vertices than DE under identical gates).

The deeper attraction for us: our accept gates are already non-differentiable
(planned envelope budget, link condition, fold-over, feature classes,
min-angle floors, GWN sanity). DE does not care - any gate stack becomes the
barrier, and any scalar quality (worst one-ring angle, normalized quality,
even downstream-solver proxies) becomes the objective. This composes cleanly
with, rather than replaces, the corpus's safety cards: `TRI-COLLAPSE-SAFE1`
guards stay mandatory inside the barrier, `TRI-ERROR-GATE1` /
`TRI-ENV-ACCUM1` supply the distance gate, and Hu's worst-angle queue
(`TRI-WORST-ANGLE1`) supplies scheduling while DE supplies positions.

Cost control is the adoption risk. Mitigations visible in the paper: local
(patch-restricted) distance evaluation, `Np = 20` is enough, cheap-gate-first
ordering (evaluate link/fold-over/Delaunay before any distance query so
infeasible candidates die cheaply), and coarse-first pre-simplification before
the expensive optimizer. Seed the RNG for determinism.

## Falsifiable implementation cards

Deduped against `evidence_matrix.md`: extends `TRI-ODT-RELAX1` (relocation),
`TRI-ANGLE-PAIR1`/`TRI-ANGLE-BOUNDS1` (angle removal), and the
`TRI-COLLAPSE-SAFE1`/`TRI-ERROR-GATE1` guard stack; does not duplicate them.

1. `TRI-EVO-RELOCATE1`: replace the smoothing+projection relocation in the
   isotropic loop with seeded per-vertex DE (`Np = 20`, `F = 0.7`,
   `Cr = 0.9`, one-ring init, target-to-best/1/bin) whose barrier is the full
   gate stack (link, fold-over, feature class, envelope budget) and whose
   objective is the worst one-ring angle. Accept only if, on the tri bench
   set, the 1st-percentile minimum angle improves over the current relocation
   at <=5x relocation-phase runtime and byte-identical reruns under a fixed
   seed.
2. `TRI-EVO-COLLAPSE-SEARCH1`: in decimation, when the heuristic collapse
   point (endpoint/midpoint/QEM) fails the gates, run a bounded DE feasibility
   search (`I(v)` barrier only) over the one-ring before declaring the edge
   uncollapsible; order gates cheap-first so distance queries run last. Accept
   only if reachable vertex-count reduction at fixed envelope improves by
   >=25% (paper indicates 2.7-4x headroom) without any gate violation in an
   independent final audit.
3. `TRI-EVO-MAXMIN1`: add an optional max-angle elimination tier - Wang-style
   insertion/collapse scheduling with DE min-max / max-min one-ring angle
   objectives under the envelope gate - targeting empirical
   `theta in [30, 90] deg` with zero out-of-range angles on non-feature-locked
   triangles. Accept only if it reaches `N_<30 = N_>90 = 0` on >=80% of the
   bench set while the envelope audit passes, and report (not fail on)
   feature-locked residual angles.

## High-value references from this paper

- Yi, Liu, He (2018), *Delaunay Mesh Simplification with Differential
  Evolution*, ACM TOG 37(6): the direct predecessor - DE over an edge-operation
  sequence rather than vertex positions; the head-to-head baseline.
- Liu, Xu, Fan, He (2015), *Efficient Construction and Simplification of
  Delaunay Meshes*, ACM TOG 34(6): shape-preserving Delaunay-ization used as
  CREVO's zero-error initialization.
- Dyer, Zhang, Moeller (2007), *Delaunay Mesh Construction*, SGP: local
  Delaunay condition on interior edges defining the Delaunay-mesh constraint.
- Zint, Grosso (2018), *Discrete Mesh Optimization on GPU*, IMR: grid-sampling
  alternative (HSS) and the natural GPU-parallel route if DE relocation is too
  slow serially.
- Cignoni, Rocchini, Scopigno (1998), *Metro: Measuring Error on Simplified
  Surfaces*, CGF 17(2): the sampled two-sided Hausdorff auditor used for all
  reported distances.
