# Liu et al. - Smooth Bijective Projection in a High-order Shell

## Bibliography and access

- Shibo Liu, Yang Ji, Jia-Peng Guo, Ligang Liu, and Xiao-Ming Fu (corresponding),
  University of Science and Technology of China.
- *ACM Transactions on Graphics*, 43(4), Article 59, 13 pages, July 2024
  (SIGGRAPH 2024 journal track).
- DOI: `10.1145/3658207`.
- Local full text: `docs/references/papers/source/pdf/31_liu_2024_bijective_shell_projection.pdf`.
- Review status: `FULL_READ` on 2026-07-23. Honest page accounting: the local
  PDF contains **13 pages total** (the task brief's "385 pages" warning did not
  match this file). All 13 pages were text-extracted and read: main paper body
  pp. 1-12 plus references pp. 12-13. **Not read:** the supplementary material
  containing the proofs of Propositions 1-5 and the displacement-map encoding
  details — it is *not included* in this PDF, so every "proof provided in the
  supplementary material" claim is recorded below as *stated-proved,
  unverified locally*. Figures were interpreted from extracted captions and
  inline numbers, not visually rendered.
- Snowball placement: `citation_snowball_batch2.md` row P1 in the
  bijective-shell family (Jiang 2020 linear shell is the P0 parent; Zhu 2026
  BijectiveRemesh is the P0 sibling).

## Problem and contract

Jiang et al. 2020 build a *linear* prismatic shell around an input triangle
mesh `I`: any admissible mesh `R` inside the shell is connected to `I` by a
bijective projection, giving edit-sequence-independent attribute transfer.
Two defects motivate this paper:

1. The linear shell's per-prism piecewise-constant projection direction is
   **discontinuous across prism boundaries** — transferred attributes are
   nonsmooth where `R` crosses prism walls, worst in high-curvature regions
   (their Fig. 2).
2. The linear shell space is **non-uniform**: although top-bottom distance is
   bounded by twice the thickness, interior facet-to-input distance can be far
   smaller, leaving almost no room to remesh in pinched areas (their Fig. 3).

Contract of this paper: given a **self-intersection-free, orientable,
manifold** triangle mesh `I` and a thickness `epsilon`, construct a
*high-order* shell whose projection operator is **continuous (smooth)** and
whose constrained space is empirically more uniform, while retaining the
bijection guarantee.

## Shell structure and key equations

Each prism `P` is bounded by three **Bezier triangles of order n** (top,
middle, bottom; order 3 in practice) and three side surfaces **trimmed from
bilinear surfaces** `B_j`. Each prism carries a linear triangle `t_linear`
with vertices `v_1,v_2,v_3` (identical to the middle surface's corner
vertices) and per-vertex direction vectors `d_1,d_2,d_3`. The projection
vector field is the barycentric interpolation

```text
d(v) = u1*d1 + u2*d2 + u3*d3,   (u1,u2,u3) barycentric on t_linear,   (1)
```

which is **globally continuous** because it depends only on the shared linear
mesh `L` and shared vertex vectors — this is the entire smoothness mechanism.
Three structural conditions define validity:

1. **Conformance**: Bezier-triangle edges lie *exactly* on the bilinear side
   surfaces (so adjacent prisms seal without gaps).
2. **Alignment**: the vector field aligns with one isoparametric direction of
   the bilinear side surfaces.
3. **Angle**: `angle(d_j, normal(t_linear)) < pi/2`.

**Proposition 1 (edge-on-bilinear placement).** For a cubic Bezier edge with
control points `p1..p4` on the bilinear surface spanned by `v1,v2,d1,d2`,
with `x1 = v1 + t_hat*d1 = p1`, `x2 = v2 + t_hat*d2`:

```text
p2 = (2/3)x1 + (1/3)x2 + beta*d1,
p3 = (1/3)x1 + (2/3)x2 + beta*d2 + (l/3)*d1,        (2)
```

with free scalars `beta` (bulge) and `l` (end offset). Equation (2) is the
image of the parametric-domain quadratic `(t, beta*t(1-t) + l*t^2)` under the
bilinear map; the same construction generalizes to any order. A cubic Bezier
triangle keeps 6 free DOF for surface fitting after edge constraints.

**Proposition 2 (top/bottom placement).** Explicit offsets of the top and
bottom edge control points from the middle ones (scaled by per-vertex
temporary thicknesses `eps+_j`, `eps-_j`) make the top-minus-middle and
middle-minus-bottom curves equal a scalar profile times the interpolated
vector `(1-t)d1 + t*d2`, while both offset curves remain on the bilinear
surface. This ties the three sheets to the *same* vector field.

**Proposition 3 (bijectivity sufficient condition, per prism).** The
prismatic isoparametric transformation is bijective if:

- **(I1)** each line `v_i + t*d_i` does not intersect the trimmed bilinear
  patch opposite to it, and adjacent trimmed patches are not tangent at their
  intersection; and
- **(I2)** the angle between the normals of the top/middle/bottom Bezier
  triangles and the vector field is `< 90 degrees`.

The authors claim a new **sufficient and necessary** condition for prismatic
elements in the supplementary (contrast: Jiang 2020's 24-positive-tetrahedra
condition, which they report is too easily violated for curved shells;
Knabner-Summ 2001 conditions are impractical).

**Proposition 4 (projection bijection).** If Proposition 3 holds, projection
along the vector field is a **bijection between any two surfaces inside the
shell whose normals have positive dot product with the field at every
point**. This is the provenance mechanism: `I` and any admissible remeshed
`R` are in structural 1-1 correspondence regardless of the edit sequence.

**Proposition 5 (point query).** For `p` inside a valid prism, the cubic
equation for `t` (find `t` with `p` on triangle `v_j + t*d_j`) has exactly
one usable real root (smallest positive or largest negative depending on
orientation), enabling robust inverse-barycentric vector lookup.

## Shell construction algorithm

Interior-point strategy: start from a state satisfying **all hard
constraints**, only ever accept local operations that keep them satisfied.

- **Hard constraints:** enclosing (`I` between bottom surface `B` and top
  surface `T`), angle (input normal vs field `<= pi/2` everywhere on `I`),
  thickness (prism length `<= epsilon`).
- **Objectives:** `E = E_angle + E_quality + E_constraint` where

```text
E_angle   = (1/N_t) * sum_t (1/m) * sum_i sin^2(angle(d(s_i), n(x_i)))   (5)
E_quality = sum_{t_middle} Integral E_MIPS^2(u) du,
            E_MIPS(u) = ||J(u)||_F * ||J(u)^-1||_F                        (6)
E_constraint = 0 if feasible, infinity otherwise (barrier)                (7)
```

- **Initialization:** run Jiang 2020 to get a dense *linear* shell at
  `eps_init = epsilon/10`, optimize it to `eps_opt = epsilon/5`, take its
  middle surface as `L`, its middle-to-top vertex offsets as the vectors,
  order-elevate to `n` without geometry change. This start state is feasible
  by construction.
- **Loop (Alg. 1, max 30 rounds):** per round: (a) **collapse edges**
  (complexity; shortest curved middle-edge first; accepted even if energy
  rises, rejected only on constraint violation), (b) **optimize prism
  geometries** — vertex position on `I` and vector `d` per vertex, via
  **differential evolution** because rebuilding Bezier triangles makes `E`
  non-differentiable, (c) **flip edges** (accept iff `E` decreases; longest
  curved edge first), (d) **zoom prisms** — enlarge vector/thickness toward
  one-ring average scaled by `rho = 1.5`, clamped at `epsilon`.
- **Middle-surface fitting:** sample `t_linear`, project samples along the
  field onto `I`, then least-squares fit the middle Bezier control points
  subject to the linear equality constraints (2) — a small equality-
  constrained QP per triangle.
- **Checks (all conservative linearizations):**
  - *Enclosing:* convex hulls of top/bottom Bezier triangles vs `I`
    intersection tests, with adaptive Bezier subdivision up to 3 levels
    before declaring violation.
  - *Normal (angle):* enclose the prism in an octahedron to gather nearby
    input triangles, then test their normals against `d_1,d_2,d_3` (the
    field is a barycentric combination, so vertex-vector tests govern).
  - *Validity (Prop. 3):* (I1) via convex hull of each bilinear patch (4
    triangles) reducing to line-triangle / triangle-triangle overlap tests on
    `Orient3d`-class predicates; (I2) via the convex-hull property of the
    quartic Bezier triangle representing the cubic patch normal. These
    linearizations are **sufficient-only with an admitted gap** — valid
    shells may be rejected; the fix is to subdivide until they pass.

**Variants.** Open boundaries: boundary vertices become zero-thickness frozen
singularities (prism degenerates to pyramid/tet; Prop. 3 still applies).
Self-intersecting input: falls back to **local injectivity only** with local
intersection checks — the global bijection claim is dropped, same as
Jiang 2020.

## Remeshing inside the shell and attribute transfer

Remeshing `R` (init `R = I`) uses standard operators (collapse, split, flip,
relocate) with **explicit per-operation rejection checks** — the same
pattern as El Topo, but the checks certify *shell containment* and the
*normal-vs-field angle*, not mutual collisions:

1. `R` stays inside `S` (enclosing check);
2. every `R` normal makes `< pi/2` with the field (normal check, run on 4
   midpoint sub-prisms so vector bounds are tighter and normals get more
   freedom).

Transfer: locate prism (coarse: 3x-subdivided control net treated as a linear
shell with Jiang 2020's locator; fine: Prop. 5 vector query, hopping to the
adjacent prism when the root test fails), then project along the field.
Applications shown: solving PDEs (heat-method geodesics) on a remeshed
high-quality mesh and pulling the field back bijectively; boolean-union
remeshing with color/correspondence retention; displacement-map detail
encoding; vector-field transfer; deformation transfer; feed into
Khanteimouri-Campen 2023 for curved tet meshing.

## Guarantee analysis: proved vs empirical

- **Bijection (Props. 3-4): conditional, stated-proved.** Proofs live in the
  supplementary material, which is *not in the local PDF* — not verified
  here. The guarantee is per-prism and conditional on checks passing plus
  the positive normal-dot-field condition on both surfaces.
- **Checks are conservative linearizations** (convex hulls), so acceptance
  errs on the safe side *mathematically*; but the implementation runs
  **tolerance-based floating-point, not exact arithmetic** — the authors
  state explicitly that validity checks "do not guarantee accuracy" as
  implemented, while noting the linearized predicates *could* be made exact
  (Shewchuk-style) at a performance cost. So the end-to-end guarantee is
  *exact-realizable but not machine-verified as shipped*.
- **Projection evaluation** (cubic root solving, barycentric inversion)
  accumulates floating-point error; the authors flag small projection
  deviation as an open issue.
- **Smoothness:** the field is continuous by construction (Eq. 1); the
  resulting improvement in transferred-attribute smoothness is demonstrated
  empirically (Figs. 2, 20, 21), not quantified by a formal continuity class
  of the composite projection map.
- **Uniform shell space: empirical only.** Stated verbatim as having "no
  theory to guarantee that this space is always uniform."
- **Robustness: empirical.** 100% shell-construction success on 8300+
  models — but the datasets were **pre-filtered to manifold,
  intersection-free, orientable** meshes, so this is not evidence about dirty
  input.

## Experimental evidence

- Datasets: subsets of Thingi10K and ABC, >8300 meshes, all manifold /
  intersection-free / orientable. C++ implementation, i7-4790K, 16 GB RAM.
  Single user parameter: thickness, default `epsilon = 2%` of bbox longest
  edge.
- Output complexity: prism count is ~5% (Thingi10k) and ~2% (ABC) of input
  triangle count.
- Cost: **mean 652 s** per shell; median < 250 s; 75th percentile 622 s;
  linear-shell init is 21% of total. Squirrel (12,592 faces): 273 s.
  Thingi10k ID 78481 (596,736 faces): 1,824 s. Time is dominated by edge
  collapse (48-67%) and differential-evolution geometry optimization
  (27-42%); flips are negligible.
- Versus Jiang 2020 (same thickness): shell construction is **3.29x (ABC) /
  4.64x (Thingi10k) slower**; remeshing inside the shell is comparable
  (0.96x / 0.79x — high-order rejects more in collision checks but accepts
  more in normal checks); attribute transfer 1.18x / 2.14x slower.
- Transfer accuracy (Fig. 21): error distributions of linear vs high-order
  projection are **similar in magnitude**; the high-order one has smoother
  error isolines. The honest stated conclusion: because the remeshed mesh
  sits within a thin shell, *both* projections give small, comparable error —
  the win is smoothness, not accuracy.
- Ablations: thickness vs sparsity (prism count saturates as thickness
  grows); input triangulation quality (noisy inputs force denser shells);
  `eps_opt` choice (larger keeps shell linear-ish, smaller costs time);
  zoom ratio `rho` (1.2-5.0 changes shell evenness more than runtime).
- Fig. 19 (key for us): a mesh remeshed with a 0.1% Hausdorff bound and *no
  shell* subsequently **intersects a 1% linear shell but fits inside the 1%
  high-order shell** — a sampled-Hausdorff bound alone does not certify
  shell containment, and the uniform space matters.

## Limitations and claim boundary

- Rejects non-manifold and non-orientable input outright; self-intersecting
  input degrades the guarantee to local injectivity.
- Existing remeshers must be **modified at code level** to insert the
  per-operation checks, and the rejections can break the host algorithm's
  own guarantees (their example: QSlim's target vertex count).
- Construction is slow (minutes per model on average) and admits it; the
  cost sits in constraint checks and repeated Bezier rebuilds demanded by
  the derivative-free optimizer.
- Floating-point tolerance checks in the shipped implementation; exactness
  is a described option, not a delivered property.
- No formal uniformity guarantee; the middle-surface fit is a "simple
  fitting process" with acknowledged room for better constructions.
- No feature-edge/crease story at all: nothing constrains the remeshed mesh
  to preserve sharp feature curves — the shell bounds *distance* and *normal
  half-space*, not feature alignment. (Feature handling must come from the
  remesher, e.g. Zhang et al. 2022.)
- Attribute-transfer error to the *input-solved* field cannot be reduced by
  optimizing projection distortion (their own analysis) — remeshing changes
  the discrete operator, and no quantitative relation ties the two solves.

## What this buys over El Topo-style and Hu-style gates (AutoTessell)

AutoTessell's #1 invariant is exact surface preservation/provenance, and the
current TRI error-gate design (TRI-ERROR-GATE1, TRI-ENV-ACCUM1,
TRI-ENV-BIDIR1) is Hu/Borouchaki-flavored: accumulated or sampled distance
budgets checked per operation.

- **vs El Topo per-op collision checks:** El Topo certifies the evolving
  surface never self-intersects, but says nothing about distance to, or
  correspondence with, the *input*; drift accumulates silently. The shell
  gives a static, edit-sequence-independent certificate: containment in `S`
  plus the normal condition implies both a two-sided distance bound
  (`<= epsilon` per prism by the thickness constraint) *and* a bijection to
  `I`. Self-intersection of `R` is also excluded within the certified region
  because a bijective image of `I` cannot self-intersect.
- **vs Hu-style sampled Hausdorff gates:** sampling can miss maxima between
  samples, is one-sided per direction, and provides *no correspondence* —
  after 10k operations you know the surface is close, but not *which patch
  of the input each output face came from*. The shell's projection is exactly
  that missing provenance map: patch labels, CAD face IDs, boundary-condition
  tags, and sizing fields transfer bijectively and smoothly. Fig. 19 is
  direct evidence that a sampled-Hausdorff-bounded remesh can still violate
  shell containment.
- **Cost of the upgrade:** shell construction is heavy (minutes), and the
  high-order variant is 3-5x the linear one for comparable transfer
  *accuracy* — the high-order win is smoothness of transferred continuous
  fields and a more uniform remeshing space. For CFD surface prep, where
  transferred attributes are mostly discrete (patch IDs, feature tags) plus
  occasional sizing fields, **Jiang 2020's linear shell is the right first
  target; this paper is the upgrade path** if nonsmooth transfer of sizing/
  y+ fields or pinched remeshing space proves to be a real problem.
- **Interaction with our operators:** the per-op check pattern maps directly
  onto `core/preprocessor/native_remesh/isotropic.py` and
  `quadric_decimate.py` accept/reject hooks — the same slot where
  TRI-ENV-ACCUM1's budget check would go. A shell gate *replaces* the
  accumulated-budget bookkeeping with two geometric predicates per op, at
  the price of a build-once preprocessing step.

## Falsifiable implementation cards

(No existing `TRI-SHELL-*` cards in `evidence_matrix.md`; these do not
duplicate TRI-ENV-ACCUM1/BIDIR1 (accumulated/sampled budgets),
TRI-NORMAL-CONE1 (per-vertex reference normal cones), or TRI-COLLAPSE-SAFE1
(topological guards) — they test the *static certified domain* alternative.)

1. `TRI-SHELL-DOMAIN1`: implement a linear prismatic shell (Jiang 2020
   construction, this paper's per-op check pattern) as a static certified
   domain for native_tri remeshing: per-operation containment + normal-vs-
   field checks with exact-arithmetic linear predicates (Orient3d class),
   rejecting any violating op. Accept only if, on an adversarial suite
   (thin gaps, high curvature, near-tangent sheets), every accepted remesh
   stays within the declared `epsilon` under an independent dense Hausdorff
   audit *and* the bijectivity predicates never pass on a constructed-invalid
   prism. Benchmark wall-time overhead vs the TRI-ENV-ACCUM1 accumulated-
   budget gate on the same operation streams.
2. `TRI-SHELL-PROVENANCE1`: use the shell's bijective projection to carry
   per-face provenance (CAD patch ID, boundary-condition tag, feature-curve
   membership) from input to remeshed surface. Pass only if every output
   face maps to a unique input region, patch-boundary pullbacks close into
   consistent loops, and provenance survives an arbitrary interleaving of
   collapse/split/flip/relocate — i.e., the result is independent of the
   edit sequence, which no accumulated-budget design can promise.
3. `TRI-SHELL-COST1`: three-way gate bake-off on the CFD STL bench set —
   (a) Hu-style sampled Hausdorff gate, (b) linear-shell gate, (c) high-order
   shell gate (this paper) — measuring build time, per-op check time,
   rejection rates, final Hausdorff, and transferred sizing-field smoothness
   (max gradient jump across output edges). Adopt (c) over (b) only if it
   measurably reduces sizing-field transfer artifacts on high-curvature CFD
   models within a <=2x total-time budget; otherwise standardize on (b) for
   the fine-quality tier.

## High-value references from this paper

- Jiang, Schneider, Zorin, Panozzo (2020), *Bijective Projection in a Shell*
  (`10.1145/3414685.3417769`): the linear-shell foundation — construction,
  24-tetrahedra bijectivity condition, prism location; the practical first
  target for AutoTessell. (Already P0 in batch 2.)
- Jiang, Zhang, Hu, Schneider, Zorin, Panozzo (2021), *Bijective and Coarse
  High-Order Tetrahedral Meshes*: the other "high-order shell" (curved
  mid-surface, flat top/bottom) used for curved tet meshing — the volume-mesh
  sibling of this paper.
- Zhang, Wang, Guo, Chai, Liu, Fu (2022), *Constrained Remeshing Using
  Evolutionary Vertex Optimization* (`10.1111/cgf.14471`): the remesher this
  group runs inside shells; source of the differential-evolution vertex
  optimizer. (Already P1 in batch 2.)
- Khanteimouri, Campen (2023), *3D Bezier Guarding: Boundary-Conforming
  Curved Tetrahedral Meshing*: downstream consumer of the middle Bezier
  surface; relevant if AutoTessell ever emits curved boundaries.
- Liu, Gillespie, Chislett, Sharp, Jacobson, Crane (2023), *Surface
  Simplification Using Intrinsic Error Metrics*: the main *alternative*
  provenance mechanism — per-operation correspondence tracking — useful as
  the comparison arm for TRI-SHELL-PROVENANCE1.
