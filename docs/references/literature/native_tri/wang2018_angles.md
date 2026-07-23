# Wang et al. - Isotropic Surface Remeshing without Large and Small Angles

## Bibliography and access

- Yiqun Wang, Dong-Ming Yan, Xiaohan Liu, Chengcheng Tang, Jianwei Guo,
  Xiaopeng Zhang, Peter Wonka.
- *IEEE Transactions on Visualization and Computer Graphics*, volume 25,
  issue 7, pages 2430-2442, 2019. Published online 18 May 2018.
- DOI: `10.1109/TVCG.2018.2837115`.
- IEEE document number: `8361045`.
- Local full text: `tmp/pdfs/native_tri_batch2/wang2018_angles.pdf`.
- Review status: `FULL_READ` on 2026-07-23. All 14 PDF pages, equations,
  Algorithm 1, Figures 1-14, Table 1, limitations, and references were read.
  Pages 1, 4-7, and 9-13 were rendered; the algorithm, operation diagrams,
  equations, plots, table, and limit tests were visually checked against the
  extracted text.

## Problem and stated contract

The paper targets isotropic triangle remeshing with explicit lower and upper
angle targets. Its inputs are a two-manifold triangle mesh `M`, desired angle
bounds `beta_min` and `beta_max`, an optional target vertex count `n_t`, and
pre-specified feature curves when they must be preserved. The default
experimental bounds are `[35 deg, 86 deg]`.

The central idea is to pair two high-level operations:

1. remove a large angle by inserting one vertex using a specialized
   split-plus-flip construction; and
2. improve a small angle by deleting one vertex using a targeted collapse.

Running both `k` times per iteration nominally preserves the requested vertex
count. Valence optimization and tangential smoothing follow each half. The
method can initialize directly from a raw mesh or post-process another
remesher's output without changing its vertex count.

This is an angle-quality optimizer, not a repair algorithm. It assumes the
two-manifold connectivity and feature labels needed by its local operators. It
does not specify self-intersection repair, non-manifold repair, exact
predicates, or a watertightness restoration procedure.

## Initialization and sizing

For uniform remeshing, the paper derives a single target length from surface
area `|M|` and the target number of vertices `N`, assuming `2N` equal-area
equilateral triangles:

```text
triangle area approximately |M| / (2N)
L = (2 / fourth_root(3)) sqrt(|M| / (2N))
rho(x) = L.
```

For adaptive remeshing it reuses the curvature-radius model from Dunyach et
al. Let `r_i` be curvature radius and `epsilon` the approximation parameter:

```text
rho(x_i) = sqrt(6 epsilon r_i - 3 epsilon^2),
rho(x_i) in [h_min, h_max].
```

Instead of asking the user for all three sizing parameters, it solves a
quadratic in `epsilon` from the idealized total-area relation

```text
|M| = sum_i (sqrt(3) / 4) rho(x_i)^2
    = sum_i (sqrt(3) / 4) (6 epsilon r_i - 3 epsilon^2),
```

then derives `h_min` and `h_max` from the extrema of `rho`. The initialization
uses the conservative endpoint minimum and repeatedly applies

```text
split    if ||x_a - x_b|| > (4/3) min(rho(x_a), rho(x_b)),
collapse if ||x_a - x_b|| < (4/5) min(rho(x_a), rho(x_b))
```

until reaching `n_t` vertices. The paper does not specify curvature
discretization here, treatment of a negative radicand, a gradation limiter, or
the exact policy used when the next length operation would overshoot `n_t`.
As in Dunyach et al., `epsilon` is derived from a local curvature model and is
not established as a global Hausdorff certificate.

## Optimization loop

At each iteration, triangles outside the requested angle interval are placed
in separate large-angle and small-angle lists, `L_l` and `L_s`. Algorithm 1 is:

```text
repeat
    LargeAngleRemoval(k)
    ValenceOptimization()
    VertexSmoothing()
    SmallAngleImprovement(k)
    ValenceOptimization()
    VertexSmoothing()
until every angle theta is in [beta_min, beta_max].
```

The first `k` listed triangles are processed in each half. The paper does not
define list ordering, deterministic tie-breaking, conflict scheduling, or
whether the lists are fully rebuilt after every accepted local change.

### Large-angle removal by vertex insertion

For a bad triangle without an incident feature edge:

1. identify its longest edge and merge conceptually with the neighboring
   triangle across that edge to form a quadrilateral;
2. split the shared longest edge at its midpoint, inserting one vertex;
3. choose one of the four local edges to flip; and
4. choose the flip whose affected angles minimize their root-mean-square
   deviation from the ideal `60 deg`, then tangentially smooth the inserted
   vertex.

The operation is therefore not ordinary longest-edge bisection. The
split-plus-selected-flip changes the local point distribution and
connectivity specifically to reduce the triggering maximum angle. The paper
describes the score in prose but does not give a formal equation, candidate
ordering, epsilon, or tie-break rule.

Feature and boundary cases use explicit local constructions (Figure 4):

- if one short edge is a feature and the edge opposite the large angle is not,
  use the smooth-case construction;
- if the longest edge is a feature or boundary edge, split that edge at its
  midpoint first, then reduce to the basic case;
- if both short edges are features, use the illustrated pentagon insertion to
  reduce to the basic case; and
- one special feature configuration is fixed by a direct flip without a split.

Thus feature edges are not universally frozen. The paper permits controlled
feature-edge splitting while preserving the feature curve. Its figures are
topological templates rather than complete predicates: they do not specify
feature-provenance updates, corner/junction rules, manifold checks, or all
degenerate configurations.

### Small-angle improvement by vertex removal

For each of the first `k` triangles whose minimum angle is below `beta_min`,
collapse the edge opposite that minimum angle, if the collapse is legal, and
locally smooth the affected region. If `L_s` contains fewer than `k`
triangles, the implementation temporarily raises `beta_min` so that `k`
collapse candidates exist and can balance the `k` insertions.

The paper does not define "legal" collapse. A production interpretation must
at least require the link condition, no duplicate/non-manifold result, no
fold-over, feature and boundary provenance preservation, and acceptable
geometric error. It also does not state what happens when fewer than `k`
candidates pass legality, so exact vertex-budget preservation is a procedural
intent rather than a proved invariant for all inputs.

### Valence optimization and smoothing

Interior edges are flipped to reduce the squared valence error, with target
valence 6 for interior vertices and 4 for boundary vertices. The paper then
applies three to five tangential smoothing iterations. For vertex `v_i`, with
incident triangles `N(v_i)`, triangle centroid `p_j`, triangle weight `w_j`,
and unit vertex normal `n_i`, equation (1) is

```text
c_i = sum_{j in N(v_i)} w_j p_j / sum_{j in N(v_i)} w_j
p_i <- c_i - n_i n_i^T (c_i - p_i).
```

Smoothing is limited to two or three rings when the affected set is small;
otherwise it is global. After every smoothing iteration, vertices are
projected back to the input surface. The paper does not state the weights used
in the reported tests or define an inversion/error acceptance test for an
individual move.

## Optional error-aware operators

The fast standard operators may oversmooth detailed regions. The paper offers
optional feature-sensitive variants, but these reduce observed error rather
than enforce a bound.

### Error-aware smoothing

The tangential update vector `u_i` is repeatedly projected through the planes
of adjacent facet normals and back to the vertex normal plane. Repeating this
composition `d` times shrinks the step in high normal-variation regions; in
the stated limit `d -> infinity`, the update tends to zero. The construction
also uses the projected point and nearby steepest points on source vertices or
edges. This is a soft feature response, not a semantic feature constraint and
not an error envelope.

### Error-aware collapse

The paper defines a vertex intensity in `[0, 1]`:

```text
Phi_i = min_{j in N(v_i)} cos(angle(n_i^(f_j), n_i^v))^m,
m = 3.
```

It permits collapsing `v_i` toward `v_j` under the printed condition

```text
Phi_i - Phi_j > -Psi (Phi_i^2 - 0.5).
```

The paper does not define or tune `Psi` in the surrounding text. This
criterion therefore cannot be implemented reproducibly from the main paper
alone and must not be treated as a hard feature-preservation guarantee.

### Error-aware flip

A flip is allowed only when the angle between the two incident face normals is
below a threshold `Theta`; the reported implementation uses `Theta = 10 deg`.
This suppresses connectivity changes across sharp folds. It does not replace
explicit user/patch feature labels.

## Acceptance, convergence, and guarantees

The authors state that a local operation is accepted only when it improves the
triggering small angle or reduces the triggering large angle. They describe
this as an algorithmic convergence guarantee. That statement is narrower than
the pseudocode's global termination condition:

- the same operation can worsen neighboring triangles;
- the paper's plots contain the resulting spikes;
- smoothing can modify more angles after local acceptance; and
- the limit tests explicitly contain inputs and requested bounds for which the
  algorithm does not converge.

Consequently the paper demonstrates empirical convergence for its normal test
settings but does not prove finite termination with every angle in the target
interval. A production engine needs an operation budget, stagnation detector,
cycle signature, best-so-far rollback, and an explicit infeasible result.

The paper provides no hard Hausdorff bound, exact target-count proof under
failed collapses, self-intersection guarantee, or proof that tight angle bounds
are feasible for a fixed topology, feature set, and vertex budget.

## Experimental evidence

The implementation used Visual Studio 2015 on Windows 10 and a single 4.2 GHz
CPU with 8 GB RAM. It compares against RAR, MAI, MPS, FPO, SPP, CVT, NOB, and
Instant Field-Aligned Meshes using minimum/maximum angles, average minimum
angle, triangle regularity, valence-6 percentage, RMS distance, Hausdorff
distance, and runtime.

Main reported observations:

- With standard operators and bounds `[35 deg, 86 deg]`, Table 1 reports zero
  triangles outside both bounds for all listed post-processed examples.
- Error-aware tests loosen the bounds to `[30 deg, 90 deg]`; they generally
  reduce approximation error but trade away angle regularity.
- Standard operation runtime is reported in the same order of magnitude as
  real-time adaptive remeshing. Error-aware operators are slower.
- The default fast setting is `k = 20%` of the current large-angle triangle
  count; error-aware remeshing uses `k = 5`. Smaller `k` improves quality but
  costs time, while larger `k` can harm vertex distribution and fidelity.
- On the vase-lion example, the method post-processes about 6.5k-vertex
  outputs from several remeshers while retaining approximately the same
  vertex count and meeting the angle interval.

These results are strong evidence that the paired local post-process is useful,
but they are not enough to claim dominance under AutoTessell's CFD workloads:
there is no ablation of each legality predicate, no adversarial topology set,
no deterministic-repeatability report, and no validation of boundary/patch
semantics used by CFD cases.

## Limit tests and explicit limitations

- On the smooth 2k-vertex Venus body, tightening from `[35 deg, 86 deg]`
  eventually fails at `[46 deg, 80 deg]` and `[40 deg, 76 deg]`.
- On the thin-feature Elk model with bounds `[30 deg, 90 deg]`, decreasing the
  budget from 2k vertices eventually fails at 800 vertices.
- Better valence and angle quality can increase Hausdorff distance.
- Thin, long features combined with a small vertex budget are difficult.
- Tiny sharp features in the vase-lion hair cannot retain low error under the
  default angle bounds; loosening the bounds is necessary.
- Selecting the minimum number of points for a tolerance is left open.
- The relation between angle and valence energies is left open.
- GPU acceleration, anisotropic remeshing, and massive-model performance are
  future work.

## Difference from the current Native Tri implementation

The current implementation in `core/preprocessor/native_remesh/isotropic.py`
and `face.py` shares only the baseline split/collapse/flip/relocate vocabulary.
Important differences are:

- Native Tri splits the longest face edge only when it exceeds `4L/3`; it does
  not target a maximum-angle queue or perform Wang's split-plus-angle-optimal-
  flip insertion.
- Native Tri collapses every conflict-free edge shorter than `4L/5` toward its
  midpoint; it does not collapse the edge opposite a selected minimum angle.
- Individual split, collapse, and flip candidates are not transactionally
  tested for link condition, fold-over, local angle improvement, or geometric
  error before commit. `face.py` rejects the whole final result after global
  gates instead.
- The flip stage optimizes valence only. It has neither the large-angle local
  candidate score nor the optional `10 deg` dihedral flip gate.
- Native Tri has no `beta_min`, `beta_max`, large/small-angle diagnostics,
  angle-violation queue, paired `k`, exact target vertex count, stagnation
  detector, or infeasibility result.
- Its advertised adaptive sizing is one global target-length shrink based on
  the fraction of detected feature vertices, not the spatial curvature-radius
  field used in this paper.
- `face.py` projects to source triangles only after the complete remesh. The
  paper projects after each smoothing iteration, before later topology
  operations can build on drifted geometry.
- Native Tri freezes detected feature vertices and protected edges. Wang et
  al. instead provide feature-specific split/flip templates, including
  controlled subdivision of a feature edge. Full locking can leave large
  angles unresolved at features.
- Native Tri accepts only closed watertight input, while the paper also
  demonstrates a model with boundary. Supporting boundaries would require a
  separate, explicit contract rather than silently relaxing the current gate.
- Native Tri's final scalar triangle-quality gate cannot substitute for
  separate minimum- and maximum-angle bounds: the same scalar quality can hide
  different angle extremes.

The paper's operator sequence is therefore best added as an optional,
transactional post-process after a robust baseline remesh, not claimed as
already implemented by the current length-control loop.

## AutoTessell decision

Adopt the paired bad-angle queue and local operation templates, subject to
stronger predicates than the paper specifies. Keep angle targets soft unless a
run actually reaches and verifies them. Preserve semantic features as hard
constraints, and use normal variation only as a secondary weight. Do not copy
the paper's convergence, error, or exact-budget language as a universal
guarantee.

## Falsifiable implementation cards

### `TRI-ANGLE-PAIR1` - transactional paired angle optimizer

- Add deterministic large- and small-angle priority queues after baseline
  remeshing. Tie-break by angle violation, stable face provenance, then local
  vertex IDs.
- A large-angle candidate implements midpoint split plus enumeration of the
  local legal flips and commits only the candidate with the best affected
  angle score.
- A small-angle candidate collapses the edge opposite the minimum angle.
- Every commit must pass link, manifold, orientation, semantic-feature,
  two-sided local error, and non-regressing local worst-angle guards.
- Falsification: fail the card if any accepted candidate breaks a gate, if two
  runs produce different connectivity, or if paired successful operations
  change the vertex count.

### `TRI-ANGLE-BOUNDS1` - explicit verified angle contract

- Add `min_angle_target_deg`, `max_angle_target_deg`, operation limit,
  stagnation limit, and best-so-far state to the public configuration and
  diagnostics.
- Report counts and extrema on both sides of the interval. Return an explicit
  `INFEASIBLE_OR_STALLED` outcome when the limits are exhausted; never spin on
  Algorithm 1's unbounded `until` condition.
- Falsification: on the paper-style normal suite, the verified output contains
  no angle outside the requested feasible interval; on the Venus-tight and
  Elk-low-budget limit cases, the engine terminates deterministically and
  reports failure rather than hanging or misreporting success.

### `TRI-FEATURE-ANGLE1` - feature-aware angle templates

- Retain immutable semantic feature provenance across split/collapse/flip.
  Implement the four Figure 4 feature configurations as guarded templates,
  with feature-edge splitting permitted but feature deletion forbidden.
- Keep feature corners fixed; allow valid degree-two feature vertices to move
  only along the source feature curve.
- Falsification: sharp-joint, thin-feature, and boundary fixtures retain all
  semantic feature chains and patch labels while reducing angle violations;
  any lost chain, moved corner, cross-feature flip, or mislabeled child edge
  fails the card.

### `TRI-ANGLE-AB1` - evidence before default enablement

- Compare baseline Native Tri against baseline plus the new post-process at
  fixed vertex budgets on smooth, sharp, thin-feature, noisy, high-genus, and
  CFD patch-boundary fixtures.
- Primary metrics: minimum angle, maximum angle, out-of-bound triangle count,
  symmetric distance, feature drift, topology failures, runtime, and
  deterministic hash.
- Promotion rule: reduce angle violations without worsening topology failures,
  feature drift, or the configured distance gate; publish negative cases as
  infeasible rather than weakening the guards.
