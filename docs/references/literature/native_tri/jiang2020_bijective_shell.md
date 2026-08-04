# Jiang et al. - Bijective Projection in a Shell

## Bibliography and access

- Zhongshi Jiang, Teseo Schneider, Denis Zorin, and Daniele Panozzo,
  New York University.
- *ACM Transactions on Graphics*, 39(6), Article 1, 18 pages, December 2020
  (SIGGRAPH Asia 2020).
- DOI: `10.1145/3414685.3417769`.
- Open access: NYU GCL author copy,
  `https://cims.nyu.edu/gcl/papers/2020-BijectivePrism.pdf`.
- Local full text: `docs/references/papers/source/pdf/42_jiang_2020_bijective_shell.pdf`
  (SHA-256 `3d2c43f7909015a26b54cfdef3c9518cae9007290981712b0b2ac39a8efb02dd`).
- Reference implementation:
  `https://github.com/jiangzhongshi/bijective-projection-shell` (C++; Eigen,
  CGAL, Geogram, libigl).
- Review status: `FULL_READ` on 2026-07-23. Pages 18/18 text-extracted and
  read: body pp. 1-14, references pp. 15-16, appendices A-E pp. 17-18.
  Unlike the high-order successor (Liu 2024), **all proofs are inside this
  PDF** (Appendix A: Theorems 3.2/3.5/3.6/3.7 and Proposition 3.4;
  Appendix B: singular extension; Appendix C: QP reduction; Appendix D:
  nonlinear prism bijectivity; Appendix E: double-slab rationale). Figures
  interpreted from extracted captions and inline numbers, not re-rendered.
- Snowball placement: `citation_snowball_batch2.md` row P0 — parent of
  Liu 2024 (`liu2024_bijective_shell_projection.md`) and sibling of
  Zhu 2026 BijectiveRemesh.

## Problem and contract

Convert a **self-intersection-free, orientable, manifold** triangle mesh
`T` into a generalized prismatic shell `S = {(B, M, T_top), F}` (bottom,
middle, top surfaces sharing prism connectivity) equipped with a projection
operator `P` such that *any* "section" of the shell — a mesh contained in
`S` whose face normals have strictly positive dot product with the shell's
vector field — is **bijectively mapped to the middle surface**, and hence
to any other section by composing `P⁻¹∘P` (their Fig. 7). The shell is a
static certified domain: containment + the normal condition are checked
per remeshing operation, and the resulting correspondence is independent
of the edit sequence. Attributes (boundary conditions, colors, UVs,
displacements) transfer through the middle surface as a common
parametrization domain embedded in ambient space.

Input filter used in their experiments (the honest input contract):
intersection-free (no non-adjacent triangle within a `1e-10` ball of any
vertex, all dihedral angles `> 0.1` degrees), orientable, manifold, no
zero-area triangles (`1e-16` tolerance).

## Shell structure and projection definition

- **Generalized prism:** top vertices `t1,t2,t3`, bottom `b1,b2,b3`,
  middle `m_i = alpha_i*t_i + (1-alpha_i)*b_i` with per-vertex
  `alpha_i in [0,1]`. Each prism has a **top slab** and **bottom slab**
  (middle-to-top, bottom-to-middle).
- **Tetrahedral decomposition:** each prism splits into 6 tets (3 per
  slab) using the Dompierre et al. 1999 patterns, made consistent across
  neighboring prisms with the Garimella-Shephard 2000 total-vertex-order
  trick (rising edge if `v1 < v2`). The **double slab** (Appendix E)
  exists so the middle surface, and thus the projection target, is
  independent of which decomposition is chosen.
- **Vector field (Eq. 1):** piecewise constant per tet:
  `V(p) = t_i - b_i`, where `i` is the pillar edge of the tet containing
  `p`. Explicitly **discontinuous across tet boundaries** — this is
  exactly the defect Liu 2024 fixes with a barycentric-interpolated field.
- **Projection `P(p)`:** trace the integral polyline of `V` from `p` to
  the middle surface (ray-per-tet walk, their Fig. 5). Returns
  `(prism id, barycentric (alpha,beta) on the middle triangle, offset h in
  [-1,1])`. The **inverse is explicit** — trace the field backwards; no
  root-finding (contrast Phong projection, which needs a quadric solve).
- **Section (Def. 3.1):** mesh whose intersection with each prism is a
  simply connected patch, boundary loop only on the prism side walls
  (never crossing top/bottom), with `n(p) . V(p) > 0` at every point.
  Top/bottom surfaces of the *shell* may self-intersect globally;
  projection is per prism, so overlapping regions only affect
  `is_inside(p)` (they simply exclude overlaps).

## Bijection contract and proof status

- **Theorem 3.2 (proved, Appendix A.1):** if all 6 tets of a prism have
  positive volume, `P` is a bijection between any section of the prism
  and its middle triangle. Proof maps the prism affinely to a reference
  prism where `V` becomes the constant `e_z` and cites Lipman 2014 for
  the positive-projected-area argument.
- **Validity (Def. 3.3):** to be independent of vertex/face numbering,
  the shell must satisfy **I1** — positivity of **24 tetrahedra** (all 6
  decompositions) — and **I2** — `T` is a section for all 6
  decompositions. This is the 24-positive-tetrahedra condition that
  Liu 2024 reports is too easily violated for *curved* shells (fine for
  linear).
- **Theorem 3.5 + Proposition 3.4 (proved, A.2/A.3):** for a closed,
  orientable, intersection-free mesh with no singular vertices, a
  strictly positive per-vertex thickness always exists — the
  **construction-success guarantee mechanism**. Proof: for small enough
  `delta`, all 12 dominant tet-volume terms are `delta * det(...)` with
  determinants positive whenever `C*N_i > 0`.
- **Theorem 3.6 (proved, A.4):** after topological beveling, the input
  is a section of the initial shell.
- **Theorem 3.7 (proved, A.5):** sufficient conditions for a local
  operation to preserve sectionhood — this is the license for the
  per-operation check list below. Proof uses Floater 2003 convex
  combination maps.
- **Appendix D (proved):** the standard isoparametric prismatic FE map
  is also bijective under I1 — the checked-corner-determinant expansion
  (`det Jf` linear in `u,v`, quadratic in `eta`, all corner terms are
  the vol1..vol12 determinants).
- **Exactness:** I1 uses **Shewchuk exact orientation predicates**;
  containment uses the Guigue-Devillers tri-tri overlap test, which is
  itself built on orientation predicates (exact-realizable). The
  projection operator "could be evaluated exactly using rational
  arithmetic" — the *construction and checks* are predicate-exact as
  shipped, the *evaluation* of `P` is floating point with measured
  round-trip error `~1e-8` (vs `~1e-5` for Phong projection, and Phong
  additionally fails outright on some faces; their Fig. 20). So: exact
  combinatorial certificate, FP-but-tight numeric transfer, upgradeable
  to fully exact.

## Construction algorithm

1. **Extrusion directions:** per vertex solve
   `max_d min_f n_f . d, s.t. n_f . d >= eps, ||d|| = 1` over the 1-ring
   — reduced (Appendix C) to the QP `min ||x||^2 s.t. Cx >= 1`,
   `d = x/||x||`, discarding solutions with `||x|| > 1/eps`. Solvable
   with OSQP/NASOQ or **exactly** (Gärtner-Schönherr). This is the
   tolerance-free answer to the BL-meshing "most normal normal" problem
   (Aubry-Löhner).
2. **Singularities:** vertices where the QP is infeasible. Rare per
   vertex (0.01%) but **8% of Thingi10k models have at least one**
   (feature points where >2 ridge lines meet, or pocket artifacts).
   Handling: **pinch** the shell to zero thickness there (degenerate
   4-tet prism, point excluded from the section definition — the vertex
   is frozen during any remeshing). Alternative for boundary-layer-type
   uses: a Boolean/corefinement fill that keeps nonzero thickness but
   loses bijectivity near the singularity (everything in the filled
   region projects *to* the singular point).
3. **Initial thickness:** ray-cast along `+N`/`-N` to first
   self-collision (capped at user `delta_max`), build top/bottom, then
   tri-tri overlap tests against `T` with iterative **20% shrinking**
   per offending triangle until intersection-free. Top and bottom
   thicknesses are independent per vertex.
4. **Topological beveling:** where the input's own 1-ring dihedral
   angles make `T` fail I2 against a neighboring prism's pillar, refine
   `T` **without changing geometry** using bevel patterns (their
   Fig. 9, barycentric `t = 0.2`), copying pillar directions from the
   nearest corner. This is a *stability* mechanism: assigning each edge
   to one incident triangle instead would be unstable under FP
   perturbation of coordinates.
5. **Shell optimization:** local ops on the shell = ops on the middle
   surface extruded through the field: edge collapse / split / flip and
   vertex smoothing decomposed into **pan** (move top+bottom together,
   minimize MIPS of middle surface), **rotate** (re-align direction to
   neighbor average), **zoom** (thickness to 1.5x neighbor average,
   capped at target). Energy: MIPS on the middle surface
   (scale-invariant, so coarsening is not penalized). Scheduling: inner
   loop = flip (MIPS-decreasing, valence-aware) → smooth → collapse
   (reject if MIPS > 30); outer loop until face-count decrease < 0.01%;
   then 20 polish iterations of flip+smooth. Smoothing does bisection
   line search on I1 only (the other checks are too expensive to
   bisect).
6. **Boundaries (open meshes):** boundary vertices that cannot extrude
   validly (rare; STL rounding noise) are pinched as singularities; all
   remaining boundary vertices are **frozen** during optimization.
   Explicitly noted: applications may freeze *additional* interior
   vertices "to exactly represent a corner of a CAD model" — the hook
   AutoTessell needs for feature corners.

## Per-operation validity checks (the remeshing gate)

Every shell-optimization op — and every op of a remesher running
*inside* the shell — is accepted only if:

1. **Manifoldness:** link condition of Dey et al. 1999 on the middle
   surface (topology preservation).
2. **I1 positivity:** 24 tet volumes positive, via **exact orientation
   predicates** (Shewchuk).
3. **Containment:** top and bottom surfaces do not intersect `T`
   (Guigue-Devillers tri-tri overlap, accelerated with a **static AABB
   tree on `T`** — static because shell self-intersection is tolerated).
   Note the containment logic is *indirect*: `T` cannot leave the shell
   without crossing top or bottom, so non-intersection of the caps with
   `T` plus Theorem 3.7 implies `T` stays a section.
4. **Normal condition:** for each prism keep the list of `T`-triangles
   overlapping its convex hull (an octahedron), and test each of their
   normals against **all three pillars** of the prism (positive dot
   products).
5. **Optional distortion bound:** max unsigned angle between overlapping
   `T`-face normals and `V` must not increase past **89.95 degrees**
   (not needed for bijectivity; keeps the map well-conditioned).

Remeshing integration (Section 5): they patched the Dunyach et al. 2013
isotropic remesher with an `is_section` check after every operation —
described as needing only "minimal modifications" but **code-level
access** to the host remesher. Guaranteed side effect: a section is
automatically **self-intersection-free** (bijective image of `T`), so
the shell gate subsumes El Topo-style collision gating within its
certified region. Their QSlim experiment: target 100 faces, shell
version stagnates at 136 faces but with zero self-intersections or
flipped triangles (plain QSlim reaches 100 with both defects).

## Cost and robustness numbers

- **Robustness: 5018/5018 Thingi10k + 5545/5545 ABC succeeded (100%)**
  — after pre-filtering both datasets to the input contract (manifold,
  orientable, intersection-free, no zero-area). No evidence about dirty
  input; triangle soups are explicitly unsupported.
- Output complexity: prisms number **7% (Thingi10k) / 2% (ABC)** of
  input triangle count. Memory ≤ 4.7 GB.
- **Construction time: mean 5 min 59 s; median ~3 min; 75th percentile
  6 min 15 s; worst 8.6 h** (Xeon E5-2690 v2 @ 3.0 GHz, 2020 cluster
  node). Liu 2024 measured this same pipeline as their init and put the
  high-order build at 3.29-4.64x *slower* than this.
- Default thickness: **10% of bbox longest edge** for generic use;
  **2%** when used to bound geometric error for volumetric PDE proxies.
  Thickness is the *only* user parameter. Thicker = richer section
  space (more aggressive coarsening possible); thinner = tighter
  geometric-fidelity bound (their Fig. 16: at 0.2% thickness a 596k-face
  model needs 7776 prisms vs 676 at 100%).
- Per-op and transfer overhead: not micro-benchmarked in the paper
  ("slower than classical surface mesh adaptation... not suitable for
  interactive applications"); Liu 2024's comparison table implies
  linear-shell remeshing and transfer are the baseline (their high-order
  transfer is 1.18-2.14x slower than this).
- Round-trip FP transfer error ≤ ~1e-8 (three orders better than Phong).

## What Liu 2024 adds — and whether CFD needs it

1. **Smooth projection field:** here `V` is piecewise constant per tet,
   discontinuous across tet/prism boundaries → transferred *continuous*
   fields (displacements, sizing) get gradient kinks where the section
   crosses prism walls. Liu 2024 replaces it with a globally continuous
   barycentric field. **For AutoTessell's CFD contract the transferred
   payload is mostly discrete** — patch IDs, boundary-condition tags,
   feature membership — which are insensitive to field smoothness;
   transfer *accuracy* is comparable between the two (Liu Fig. 21).
   Only a transferred continuous sizing/y+ field would notice.
2. **More uniform shell space:** the linear shell can pinch interior
   room in high-curvature regions; Liu Fig. 19 shows a Hausdorff-bounded
   remesh violating a 1% linear shell while fitting the 1% high-order
   one. Practical mitigation here: larger thickness or accepting more
   op rejections. This is a real but secondary concern for fine-tier
   quality; not a correctness issue.
3. Verdict unchanged from the Liu note: **linear shell first** (all
   proofs in-paper, predicate-exact checks, 3-5x cheaper, open-source
   reference); high-order only if sizing-field transfer artifacts or
   pinched remeshing space are demonstrated on CFD benches.

## Applicability to AutoTessell cards

- **TRI-SHELL-DOMAIN1 — confirmed, with refinements.** The card's
  "containment + normal-vs-field checks with exact linear predicates"
  matches the paper, but the concrete check list is the five items
  above; containment is implemented as *cap-vs-input non-intersection*
  (not point-in-shell queries), and I2 requires the **24-tet/all-6-
  decomposition** form plus **topological beveling** at init — a card
  implementation that skips beveling will spuriously fail I2 on meshes
  with bad dihedral angles, and one that checks a single decomposition
  is order-dependent. Add to the card: singularity pinching (8% of
  real-world models need it) and boundary-vertex freezing are mandatory
  for the claimed 100% construction rate; the acceptance criterion
  "every accepted remesh stays within epsilon" holds by construction
  since sections cannot cross the caps (per-vertex thickness ≤ target).
- **TRI-SHELL-PROVENANCE1 — confirmed.** `P(p) -> (pid, alpha, beta, h)`
  is exactly the provenance datum: the (static, optimized) middle
  surface is the common domain, and input→middle→output composition is
  edit-sequence independent (Theorem 3.7 holds op-by-op; the shell never
  changes during remeshing). The self-intersection-free-by-construction
  property of sections strengthens the card: provenance and
  intersection-safety come from one mechanism. Caveats to encode in the
  card: bijectivity excludes pinched singular points (isolated, frozen)
  and, for open meshes, frozen boundaries; if the input self-intersects
  the guarantee degrades to local injectivity (matches the mesh_type
  fallback philosophy, but provenance claims must then be scoped).
- **Feature/CFD gap (both cards):** the shell bounds distance and a
  normal half-space, **not feature alignment** — no crease/patch-curve
  constraint exists in the paper. The paper's own suggestion (freeze
  chosen vertices to pin CAD corners) plus TRI-FEATURE-CURVE1's curve
  constraints must supply this on top of the shell gate.
- **Boundary-layer bonus:** the extrusion-direction QP + pinching +
  Boolean fill is directly reusable prior art for
  `core/layers/native_bl.py` (their Section 2.2 explicitly frames CFD
  boundary layers as shells without bijections).

## High-value references from this paper

- Garimella and Shephard (2000), *Boundary layer mesh generation for
  viscous flow simulations*: source of the consistent prism
  tetrahedralization trick and the CFD-BL framing — dual-use for
  `native_bl.py`.
- Aubry and Löhner (2008), *On the 'most normal' normal* (+ Part 2,
  2015): the extrusion-direction problem this paper's exact QP
  supersedes; useful contrast for tolerance-free direction fields.
- Guigue and Devillers (2003), *Fast and robust triangle-triangle
  overlap test using orientation predicates*: the exact containment
  predicate to port for the shell gate.
- Dompierre, Labbé, Vallet, Camarero (1999), *How to Subdivide Pyramids,
  Prisms, and Hexahedra into Tetrahedra*: the decomposition patterns
  underlying I1's 24-tet condition.
- Mandad, Cohen-Steiner, Alliez (2015), *Isotopic approximation within a
  tolerance volume*: the closest prior tolerance-volume meshing with
  isotopy but no transfer map — the comparison arm for what the
  bijection adds over pure containment.
