# Cheng, Fu, Zhang, Chai - Practical Error-Bounded Remeshing by Adaptive Refinement

## Bibliography and access

- Xiao-Xiang Cheng, Xiao-Ming Fu (corresponding), Chi Zhang, Shuangming Chai.
  University of Science and Technology of China.
- *Computers & Graphics*, Special Section on SMI 2019. Received 11 March 2019,
  revised 17 May 2019, accepted 21 May 2019.
- DOI: `10.1016/j.cag.2019.05.019`.
- Local full text: `docs/references/papers/source/pdf/19_cheng_2019_error_bounded_remeshing.pdf`.
- Review status: `FULL_READ` on 2026-07-23. Pages 11/11 text-extracted and read
  (the local file is the 11-page "ARTICLE IN PRESS" journal proof, not the
  92-page double-spaced manuscript the task brief anticipated). All sections,
  Table 1, and all 55 references were inspected. Figures are described from
  their captions and in-text discussion; the raster content itself was not
  rendered.

## Problem and contract

Input: a 3D triangular mesh `M` with `N` vertices and bounding-box diagonal
`d_bb`. Output: a mesh `R` with two-sided Hausdorff distance to `M` bounded by
a user threshold `delta`, and "as regular as possible" triangles. The vertex
count `N_r` is explicitly **not** a priority — the paper trades vertex budget
for robustness and speed.

```text
d_1(X,Y) = max_{x in X} min_{y in Y} d(x,y),
d_2(R,M) = max( d_1(R,M), d_1(M,R) ) <= delta.
```

The core inversion relative to prior error-bounded work (Cohen 1996,
Borouchaki-Frey 2005, Mandad 2015, Hu 2017 "EBFR"): those methods keep every
intermediate mesh inside the error-bounded space and reject any local operator
that would violate the bound. Cheng et al. **allow intermediate meshes to
violate the bound** and repair the violation afterwards by adding vertices,
based on the empirical observation that more uniformly distributed vertices
almost always drive the Hausdorff distance below the bound (their Fig. 3).

Two failure modes of Hu's EBFR motivate this: (1) the greedy minimal-angle
improvement runs into **infinite loops** — a collapse of the edge opposite the
minimal angle is rejected by the error gate, the longest edge of that triangle
is split instead, which recreates the same minimal angle, and the cycle
repeats (their Fig. 4); EBFR fails on 38 of their 107 test models. (2)
Checking the error constraint for **every** local operator is very slow
(Ant: 758.37 s EBFR vs 7.45 s here).

## Algorithm

### Alternating pipeline

```text
1. Initialize target edge length field L(x) on M.
2. Edge-based remeshing of R using L(x)  (Dunyach-style local operators).
3. If the sampled (approximated) Hausdorff distance > delta:
       adaptively shrink L(x) where violated; go to 2.
   Else: compute d_2(R,M) with Metro.
       If d_2 <= delta: stop.
       Else: densify the sample set, adjust L(x); go to 2.
```

Typical behavior: about 15 alternating passes, each running roughly 3
edge-based remeshing iterations.

### Sizing initialization (Dunyach 2013)

Per-vertex target length from the maximum absolute principal curvature
`kappa_i = max(|kappa_max|, |kappa_min|)`:

```text
L(v_i) = sqrt( 6*delta/kappa_i - 3*delta^2 ),
```

then the length field is Laplacian-smoothed three times to avoid an unevenly
varying field.

### Approximate-to-accurate error measurement

The exact two-sided Hausdorff distance is too costly (they cite Tang 2009),
so a sampled surrogate is bounded first. Four sample-point classes on a mesh
`X` (either `R` or `M`):

- S1 vertices, S2 edge midpoints, S3 triangle barycenters,
- S4 evenly distributed interior samples (density escalated on demand).

Constraint surrogate: `d(p,M) <= delta` for all `p in S_R` and `d(q,R) <=
delta` for all `q in S_M`. The check is **progressive**: first the one-sided
`R -> M` direction, then `M -> R`, and within each direction S1 through S4
incrementally — once earlier classes pass, few later samples fail, so most
iterations are cheap. Only when the sampled surrogate passes is Metro
(Cignoni 1998) run as the final audit; if Metro exceeds `delta`, S4 is
densified and the loop continues.

### Detection and adjustment of L(x)

Only violating sample points `P` are acted on. For `R -> M` violations, the
closest triangle on `M` under each violating sample is collected into set `T`;
for `M -> R` violations, the `M`-triangles containing violating samples form
`T`. Every vertex of every triangle in `T` has its target length multiplied by
a scalar `lambda < 1` (default 0.9). One Laplacian smoothing iteration is then
applied to the length field, holding fixed both the just-updated lengths and
the global smallest target length. The field transfers to `R` by projecting
each `R`-vertex onto `M` and taking `min(L(u1),L(u2),L(u3))` over the hit
triangle. Because `T` is typically a union of small isolated regions,
refinement stays local ("adaptive").

A "superfluous" alternative — checking all classes S1-S4 simultaneously every
iteration — detects more regions, inserts more vertices, and is slower
(their Fig. 7); the progressive scheme is the practical winner.

### Edge-based remeshing and the modified thresholds

The inner remesher is Dunyach's adaptive variant of Botsch-Kobbelt: split /
collapse against the per-edge target `L(e) = min(L(v_a), L(v_b))`, valence-
optimizing flips (target valence 6 interior / 4 boundary, sum-of-squared
deviation decrease test), and relocation by the area-and-sizing weighted
barycenter average projected to the tangent plane and then onto `M`:

```text
x~ = sum_j w_j c_j / sum_j w_j,  w_j = Area(t_j) * L(c_j),
x  = x~ + n_i n_i^T (v_i - x~),  then project onto M.
```

**Key modification:** since under the error-bound derivation `L(v_i)` is the
*maximum allowable* edge length (not a preferred length), the classical
hysteresis `split > (4/3)L`, `collapse < (4/5)L` is replaced by
`split > L`, `collapse < L/2`. This converges in fewer iterations with fewer
vertices (Elephant: 24.48 s / more vertices with the 4/3-4/5 rule vs 11.39 s
with theirs).

### Features and boundaries

Sharp feature and boundary curves are **assumed pre-identified**. Curve
endpoints are pinned; interior curve vertices may only slide along their
curve. Without feature identification the method still meets the error bound
but spends far more vertices near creases (Block: 6,319 vertices with
features vs 59,560 without; Fandisk: 4,078 vs 38,337).

## Guarantee analysis — strict reading

- **The error bound is a posteriori verified, not a priori constructed.**
  Nothing in the refinement rule proves the Hausdorff distance will fall below
  `delta`; the loop simply refines until a verification passes. The bound
  status of a delivered result is therefore "passed the final audit", which is
  categorically the same as Hu 2017 (operation-level a posteriori checks) —
  the difference is *granularity* (per-iteration global check vs per-operation
  local check), not proof status.
- **The final "exact" audit is Metro, which is itself a sampling tool.** The
  paper's own related-work section states that only the approximated sampled
  Hausdorff distance is bounded in [7,9], and positions its
  approximate-to-accurate strategy as bounding "the exact Hausdorff
  distance"; but Metro estimates the distance from dense surface sampling, so
  a maximum between Metro's samples can still be missed. There is no
  conservative triangle-to-surface bound anywhere in the pipeline. Treat the
  contract as "sampled-audit-bounded with an independent dense second
  audit", not a continuous-geometry certificate.
- **No termination guarantee.** The conclusion states this outright: success
  on all 107 test models, "no theoretical guarantee of success for any
  model." Convergence is empirical; the per-iteration Hausdorff distance is
  even non-monotone (spikes in their Fig. 11), only trending downward.
- **No quality guarantee.** The minimal angle is whatever Dunyach-style
  remeshing delivers: Table 1 `theta_min` ranges from 11.23 deg to 30.04 deg
  and `theta < 30 deg` fractions up to 5.66%. Compare EBFR, which certifies
  >= 30 deg minimum angle on the models where it terminates. Quality here is
  a byproduct, not an enforced constraint.
- **No topology/self-intersection statement.** As with Dunyach and Botsch,
  there is no stated link-condition, orientation, or self-intersection
  invariant in the paper; the error bound does not imply an embedding.
- What **is** solid: the identification of a concrete, reproducible failure
  mode of Hu-style greedy angle improvement (the split/collapse 2-cycle of
  Fig. 4) and large-scale empirical robustness evidence (107/107 vs 69/107).

## Experiments

- Hardware: i7-4790K, 8 GB RAM. Default `delta = 0.3% d_bb` (comparisons vs
  EBFR at `0.2% d_bb` to match the EBFR executable's fixed bound);
  default `lambda = 0.9`.
- Table 1, 40+ models: inputs 2.8k-534k vertices; outputs mostly 4k-30k
  vertices; times 0.58-104 s; all reported `d_2` within bound.
- **Vs EBFR (Hu 2017):** EBFR fails (loops) on 38/107 models. On successful
  models EBFR is on average 470x slower overall; on six matched models 60x
  slower. But EBFR outputs are far sparser with certified 30 deg minimum
  angle (Ant: EBFR 997 vertices, theta_min 30.03 vs theirs 4,695 vertices,
  theta_min 23.22; Horse: 835 vs 9,114). The methods optimize different
  objectives.
- **Hybrid result (important):** using their output as EBFR's initial mesh
  rescues EBFR on most of its failures — of the 38 EBFR-failing models, EBFR
  seeded with their result fails on only 11. Refinement-first is empirically
  a robustness pre-conditioner for greedy angle improvement.
- **Vs quality-first remeshers** (RAR/Dunyach, IFM/Jakob instant fields, MPS
  maximal Poisson-disk, LCT local convex triangulation): those violate the
  error bound on the five comparison models; this method stays in bound at
  comparable visual quality but with more vertices.
- `lambda` sweep: larger `lambda` (gentler shrinking) gives fewer vertices
  but more iterations; 0.9 is the chosen trade-off.
- Tessellation invariance: source/sparse/dense/noisy versions of one shape
  all succeed; the noisy variant costs the most vertices because its bumpy
  geometry genuinely contains detail that must be resolved to stay in band.

## Limitations (authors' own, plus strict additions)

Authors admit:

- **Vertex inflation is the main limitation.** The algorithm essentially only
  adds vertices; nothing reduces them afterwards. Small-feature-dense models
  drive target lengths very low locally (their Fig. 19). Average output is
  ~15k vertices, which they deem acceptable.
- Mesh quality is inherited from Dunyach's remesher; no angle optimization.
- No theoretical guarantee of success (termination) for arbitrary input.
- Isotropic scalar sizing only; anisotropic extension is future work.

Strict additions from this review:

- The final audit is Metro (sampled), so "exact Hausdorff" in the pipeline
  description overstates the certificate; the S4-densification loop can also
  in principle ping-pong (densify, refine, re-audit) with no bound on rounds.
- Feature/boundary curves must be supplied externally; no detection, no
  junction/corner semantics beyond endpoint pinning.
- No topology, orientation, watertightness, or self-intersection invariant.
- The `L/2` collapse threshold abandons Botsch's oscillation-avoiding
  hysteresis rationale; the paper shows it converges faster here but gives no
  non-oscillation argument for the modified pair.
- Determinism (sample layouts, processing order, tie-breaking) is unspecified.

## AutoTessell applicability

This paper answers the key architectural question for `TRI-ERROR-GATE1`
differently from Hu: **where to put the error check.** Hu gates every local
operation (safe intermediates, slow, and loop-prone under an angle
objective); Cheng gates once per outer iteration and repairs violations by
localized sizing refinement (fast, robust, vertex-hungry, quality-agnostic).
For AutoTessell — where surface preservation is the #1 invariant and the
native_remesh loop in `core/preprocessor/native_remesh/isotropic.py` already
implements Botsch thresholds with a global sizing — the practical synthesis
is a two-stage design: a Cheng-style refine-to-bound pass to enter the
error-bounded space robustly, followed by a Hu-style gated improvement pass
for angles, mirroring their 38-to-11 failure-reduction experiment. Concretely
relevant code deltas: per-vertex target-length field with violation-driven
`lambda` shrinking plus field smoothing (currently absent — sizing is one
global scalar), progressive S1-S4 sampled two-sided audit (cheaper than the
existing whole-mesh gates), and the max-allowable-length threshold semantics
(`split > L`, `collapse < L/2`) that only apply when `L` is derived from an
error bound rather than a preference.

Do not adopt: the claim that Metro constitutes an exact final certificate;
any use of intermediate meshes (they may be out of tolerance by design — the
pipeline must never surface them as results); the unguarded assumption that
refinement always reaches the bound (a round budget with a hard failure
report is required).

## Falsifiable implementation cards

(Existing card families checked against `evidence_matrix.md`; the following
are new, non-duplicate names.)

1. `TRI-REFINE-REPAIR1`: implement the iteration-level detect-and-refine loop
   — allow intermediate out-of-tolerance meshes, detect violating sample
   regions, shrink the per-vertex target-length field by `lambda` on the
   affected source triangles, smooth the field once holding updated and
   minimum lengths fixed, and re-run edge-based remeshing. Enforce a hard
   outer-round budget and vertex-count cap with explicit failure reporting.
   Accept only if, versus a per-operation Hu-style gate on the same inputs,
   wall time drops materially while an independent final audit stays within
   `delta` and vertex inflation stays under a declared multiple of the
   Hu-style output.
2. `TRI-PROGRESSIVE-SAMPLE1`: implement the approximate-to-accurate audit —
   progressive S1 (vertices), S2 (edge midpoints), S3 (barycenters), S4
   (interior samples with escalating density) checks per direction, with the
   dense independent audit run only after the sparse surrogate passes.
   Because every stage is sampled, attach a declared sampling-gap margin
   (audit against `delta - margin`). Accept only if the staged audit is
   cheaper than the flat all-samples audit at equal final-audit pass rate on
   thin gaps, creases, and high-curvature patches.
3. `TRI-REFINE-PREPASS1`: use the refine-to-bound output as the initial mesh
   for the worst-angle improvement pass (`TRI-ERROR-GATE1` +
   `TRI-WORST-ANGLE1` machinery), reproducing the paper's rescue experiment.
   Additionally instrument the known infinite-loop signature (reject-collapse
   then split recreating the same minimal angle) and break such 2-cycles with
   an operation-history check. Accept only if the hybrid strictly dominates
   angle-pass-only on failure rate across the bench STL set without violating
   the error bound.

## High-value references from this paper (snowball)

- Tang, Lee, Kim (2009), *Interactive Hausdorff Distance Computation for
  General Polygonal Models*: the cited exact-Hausdorff machinery — the
  candidate for turning the sampled audit into a conservative certificate.
- Cignoni, Rocchini, Scopigno (1998), *Metro: Measuring Error on Simplified
  Surfaces*: the de-facto final audit tool; its sampling semantics define
  what this paper's "exact" check actually guarantees.
- Gao, Panozzo, Wang, Deng, Chen (2017), *Robust Structure Simplification for
  Hex Re-meshing*: Hausdorff-constrained hex simplification using Hu-style
  gating — direct crossover target for native_hex.
- Fu, Liu, Guo (2015), *Computing Locally Injective Mappings by Advanced
  MIPS*: the authors' proposed route to add angle quality to this framework
  (conformal AMIPS energy).
- Jakob, Tarini, Panozzo, Sorkine-Hornung (2015), *Instant Field-Aligned
  Meshes*: strongest quality-first baseline in their comparison; useful as
  the quality reference point when benchmarking error-bounded outputs.
