# Dapogny, Dobrzynski and Frey - Three-Dimensional Adaptive Domain Remeshing, Implicit Domain Meshing, and Applications to Free and Moving Boundary Problems

## Bibliography and access

- Charles Dapogny, Cecile Dobrzynski, Pascal Frey.
- *Journal of Computational Physics*, 262 (2014). The mmg/mmgs/mmg3d (v5)
  reference paper.
- DOI: `10.1016/j.jcp.2014.01.005`.
- Open access: HAL `hal-00804636`,
  `https://hal.sorbonne-universite.fr/hal-00804636/file/domrem2.pdf`.
- Local full text: `docs/references/papers/source/pdf/44_dapogny_2014_mmg.pdf`.
- SHA-256:
  `2083a639c9d9aa931742292e789c612fa30014e404286222fe26b5c84d191055`.
- Review status: `FULL_READ` on 2026-07-23. Pages 25/25 (HAL cover + 24
  paper pages) were text-extracted; PDF pages 3, 4, 6, 7, 9, and 10 were
  rendered at 2x resolution and the quality function, the four remeshing
  parameters, the Bezier control-point rules, the central-coefficient
  formula, the Hausdorff convex-hull bound (3), the internal-swap
  construction, Theorem 1, and the curvature size formula were visually
  checked against the extraction.

## Problem and contract

Remesh an input conforming tetrahedral mesh `T` of a domain `Omega` -
possibly dramatically ill-shaped or undersampled - into a new mesh `T~`
that (a) approximates the ideal boundary `dOmega` within Hausdorff
tolerance `eps`, (b) is well-shaped for FE/FV computation, and (c) conforms
to an isotropic size field. The deliberate design decision is to remesh
**surface and volume simultaneously** with local operators that map valid
mesh to valid mesh, because generating a tet mesh from a sole surface
triangulation is judged too fragile, and because a horrible volume mesh can
hide behind a nice surface mesh. Input is only vertices + tetrahedra;
optional extra data (triangle labels, vertex normals) is honored when
supplied. Four user parameters: `eps` (geometric tolerance = the `hausd`
parameter of the mmg software), `hmin`, `hmax` (edge-length security
bounds), `hgrad` (gradation ratio, typical 1.2-1.3).

Tetrahedron quality is `Q(K) = alpha * Vol(K) / (sum_{i=1..6}
||e_i||^2)^{3/2}` with the paper printing `alpha = 144*sqrt(3)` and
claiming `Q(K) <= 1` with equality iff regular. Direct computation on a
regular tetrahedron gives 2 with that constant (`alpha = 72*sqrt(3)` yields
1); treat the printed constant as an erratum-level normalization slip - the
ordering, which is all the algorithm uses, is unaffected.

## Local geometric support (the "ideal surface" model)

`dOmega` is unknown; the paper explicitly rejects building one global
parametrization up front (too costly) and instead reconstructs a **local
cubic Bezier model per surface triangle, on demand, from the current
mesh**. This is the single most consequential design choice in the paper:

- Per triangle `T = (a0 a1 a2)`, a triangular Bezier cubic `sigma(T^)` with
  10 control points (Eq. 2), reminiscent of PN triangles (Vlachos 2001).
- Vertex control points = the triangle vertices (interpolating model).
- Edge control points: constrained to the reconstructed tangent planes at
  the vertices (normals from area-weighted incident-face average), with the
  remaining freedom fixed by a weak-geodesic heuristic: the boundary-curve
  end tangent is the projection of the opposite edge direction onto the
  tangent plane, with norm `||a2-a1||/3`. Consequence stated as Remark 1:
  the curve model of a shared edge is **identical from both adjacent
  triangles** - edge-model consistency by construction, per-edge data only.
- Central control point: the quadratic-reproduction choice
  `b111 = m + (m-v)/2` (does not affect boundary curves).
- Ridge vertices carry two normals (one per smooth side) plus a tangent
  vector; the same machinery builds curve models for feature edges.

The authors are candid that the model is rebuilt from `S_Tk`, the
*current* triangulation at step `k`, so the "ideal surface" silently
depends on the evolving mesh; only "some heuristics" keep the local support
from drifting across steps. There is no accumulated error budget.

## Hausdorff gate semantics (`hausd`)

The geometric acceptance check for any surface operation is: every new
surface triangle `T` must satisfy `d_H(T, sigma(T^)) <= eps` against its
*own freshly built* local cubic model, evaluated through the convex-hull
bound

```text
d_H(T, sigma(T^)) <= max_{l=0,1,2; i+j+k=3} d(a_l, b_ijk),        (3)
```

with the analogous per-edge bound for boundary curves. Semantics that
matter for us:

- **Symmetric in form, local in scope**: Eq. (3) bounds the two-sided
  Hausdorff distance between the flat triangle and its curved model, but
  only pairwise triangle-vs-model - never new-surface-vs-original-input.
- **Not accumulated**: unlike Borouchaki-Frey 2005 (`h(K')` budgets that
  survive successive collapses), an mmg-accepted triangle is within `eps`
  of a model reconstructed from the mesh *as it currently stands*. Repeated
  operations can drift the realized surface beyond `eps` from the original
  input; the paper offers no bound on this, only the model-consistency
  heuristics of section 3.2. This is the price of not storing the input.
- **Cheap and conservative locally**: the convex-hull bound needs only
  vertex-to-control-point distances - no sampling, no projection - and
  over-estimates, so it errs on the safe side *per operation*.
- The same quantity also *drives refinement*: in the rough phase, a surface
  edge is split when its Hausdorff gap to its curve model exceeds `eps`
  (or its length exceeds `hmax`).

## Operator set and gates

Four classical operators, each in a surface and an internal variant, each
behind systematic validity checks ("if no particular attention is paid,
these operators may invalidate T, degrade the geometric approximation, or
degrade mesh quality"):

1. **Edge split.** Surface edge: new point placed on the Bezier curve at
   `t = 1/2` (on the model, not the chord - splitting always improves the
   geometric approximation under the model assumption). Internal edge:
   Euclidean midpoint. Rough phases mark all offending edges first, then
   split by tetrahedron patterns (re-iterating for multiply-marked
   elements, skipping splits that would invalidate the mesh); one-by-one
   splitting was observed to breed ill-shaped elements. The fine phase
   reverts to careful one-by-one splits.
2. **Edge collapse.** Class-preservation prohibitions: never collapse a
   surface point onto an interior point, a ridge point onto a non-ridge
   surface point, never remove a required vertex (some checks
   application-dependent). Surface collapse gates: Hausdorff bound (3)
   against `eps` for every new surface triangle, anti-folding checks on
   `S_T`, and validity of all affected support tetrahedra. Internal
   collapse gates: no inverted element in `B(p) \ Sh(pq)`.
3. **Edge swap.** Surface: the unique 2-2 swap, gated on consistency with
   the reconstructed geometry, the Hausdorff tolerance, and tet validity.
   Internal: instead of enumerating the Catalan-many retriangulations of
   the shell pseudo-polygon, mmg swaps by **split-then-collapse**: insert
   the midpoint `m` of `pq` (creating all `m a_i` connections), then try
   collapsing `m` onto each pseudo-polygon vertex `a_1..a_n` in turn,
   keeping the first valid result. Elegant reuse of the two other
   operators' guard machinery; result depends on candidate order.
4. **Node relocation.** Surface vertex: project the surface ball onto the
   tangent plane, take the centroid of the projection, lift back to the
   local cubic model. Internal vertex: ball centroid. Gate: no invalidated
   element and quality must actually improve.

Empirically ranked importance (section 4.3): for *domain* (volume)
remeshing the internal+surface **edge swap is indispensable** - without it
the collapse operator starves in ill-shaped configurations and quality
stalls (ablation below); relocation does not rescue bad elements but
substantially raises average quality; tetrahedra degenerate far more
readily than triangles, so gates must be stricter than in pure surface
remeshing.

## Metric machinery (isotropic only)

- Scalar size field `h` stored at vertices. Edge-length conformity is the
  unit-mesh contract via the integrated length
  `l_h(pq) = int_0^1 ||pq|| / h(p + t(q-p)) dt ~ 1` - exactly Frey-Alauzet
  2005 Eq. (16) specialized to `M = h^{-2} I`.
- Surface size from curvature via Theorem 1
  (`d_H(dOmega, S_T) <= (1/2)((d-1)/d)^2 max_T max_x max_{y,z in T}
  <|H(d_Omega)(x)| yz, yz>`, `H(d_Omega)` = Hessian of the signed
  distance = second fundamental form on `dOmega`), giving

  ```text
  h(x) = sqrt( 9*eps / (2 * max(|k1(x)|, |k2(x)|)) ),
  ```

  truncated to `[hmin, hmax]`. Interior vertices: `h = hmax`. A
  user/error-estimate size map `m(x)` can be composed on top.
- **Gradation** by truncating `h` until every edge satisfies
  `|h(p) - h(q)| / ||pq|| <= log(hgrad)` (heuristic of Li-Remacle 2004),
  which implies the ratio bound (1) on adjacent edges of a unit mesh.
- **No anisotropy, no metric intersection, no simultaneous reduction** in
  this paper: the conclusion states the algorithm "is only able to deal
  with isotropic size prescriptions" and names the anisotropic extension
  as future work (citing Dobrzynski-Frey 2008 for the volume part). So mmg
  2014 implements the Frey 2005 *length/unit-mesh/gradation* contract but
  not the tensor algebra; our shared-sizing plan is a superset of what
  this paper ships.

## Global strategy (5 steps)

1. Analyze `S_T`: classify features, reconstruct normals/tangents.
2. Rough geometric sampling (5-6 sweeps): pattern-split surface edges
   violating `hmax` or the `eps` Hausdorff gap, pattern-split internal
   edges, then collapse sweeps, then swap sweeps - until
   `d_H(S_T1, dOmega) <= eps`.
3. Only now build the size function `h` (needs a decent surface first,
   since `h` uses curvature of the reconstructed model).
4. Rough size conformity: same loop measured in `l_h`, loose band
   `[0.3, 2.5]`, stricter quality control than step 2.
5. Fine pass: one-by-one splits, collapses, swaps, plus relocation, band
   `[0.7, 1.3]`, strictest quality-degradation control.

The staged loosening (geometry first, size second, quality polish last,
with progressively tighter bands and gates) is the practical schedule that
lets mmg start from near-degenerate inputs.

## Feature / reference-edge model

Classification (section 3.1), computed once in step 1 from the input:

1. **Ridges**: edges whose dihedral angle between adjacent triangles
   exceeds a threshold. Ridge vertices carry two one-sided normals plus a
   curve tangent.
2. **Reference edges**: edges at the interface of two triangles carrying
   *different labels* (e.g. FE/FV boundary-condition patches). This is
   patch provenance as a first-class edge type - the reason this paper
   anchors our CFD patch-preservation topic.
3. **Singular points**: endpoints of >= 3 special edges; frozen (never
   moved or removed).
4. **Required entities**: user-pinned, untouchable.
5. Ordinary entities.
6. **Non-manifold edges/vertices** (added in section 5.2 for embedded
   subdomain meshing, where the outer boundary mesh `E` and the internal
   interface mesh `I` intersect): treated like ridges, with a curve tangent
   and a side-dependent normal.

Preservation is enforced *combinatorially by the collapse prohibitions*
(class hierarchy: interior < surface < ridge/reference < singular/required)
and *geometrically by the curve models*: feature edges get their own Bezier
curve model and per-curve Hausdorff gate, and split points on a feature
edge land on the curve model. So features are preserved through operations
by per-entity type tags plus locally reconstructed curve geometry - there
is no persistent link back to the *input* feature polyline, and hence no
accumulated bound on feature-curve drift (same non-accumulation caveat as
the surface gate).

## Implicit-domain meshing and level-set pipeline (cross-engine note)

Relevant to our L3 voxel/SDF reconstruction path
(`core/preprocessor/l3_ai_surface_repair`, `core/utils/surface_nets.py`),
not to native_tri proper:

- **Marching tetrahedra + remesh**: given a P1 level-set `phi` on a mesh of
  a box `D`, cut every sign-crossing tet by the 4 splitting patterns to
  discretize the zero set exactly (conforming but horribly shaped), then
  run the *same* domain remesher on the result, treating outer boundary and
  interface (`E` and `I`) uniformly - interface entities are just more
  constrained because more tets touch them. Non-manifold classification
  handles `E`-`I` intersection curves. This "cut then heal with the
  standard operator loop" architecture is directly comparable to our
  surface-nets-then-remesh route and is the production-validated version
  of it.
- **Mesh generation from invalid triangulations** (section 6): embed a
  self-intersecting, non-orientable surface (Venus model) in a box,
  compute an approximate signed distance on an anisotropically adapted
  mesh (Dapogny-Frey 2012) with `d_H(zero-set, dOmega) <= eps'`, then mesh
  the negative subdomain implicitly. Total 10 min 9 s, final average
  quality 0.77. **Admitted defect (Remark 1)**: ridges and singular points
  are inaccurately reproduced because the P1 signed distance cannot
  represent them unless they are explicitly discretized into the support
  mesh first - named as ongoing work. Identical failure mode to any SDF /
  voxel reconstruction, ours included: implicit routes lose sharp features
  unless features are meshed into the support.
- **Moving boundary loop** (section 7): mesh -> signed distance -> solve
  velocity on the *same* mesh -> advect level set -> re-cut -> remesh, per
  time step; validated on 3D shape optimization (optimal mast, 50 its,
  ~15k vertices/mesh, ~40 min laptop) and a rising-bubble bifluid Stokes
  flow with per-time-step readaptation. The key property: mechanics and
  advection share one mesh, no cross-mesh projection.

## Experimental evidence

- `model02` CAD part from a degenerate STL-derived tet mesh (almost no
  interior points): 1,254 -> 8,424 vertices in seconds; average quality
  0.0479 -> 0.7737, worst element 1e-6 -> 0.19.
- **Swap ablation** on the same case: without edge swap the run takes
  100.65 s, balloons to 46,222 vertices, average quality 0.07, worst 2e-6
  - i.e. collapse alone cannot escape ill-shaped configurations; swap is
  what unlocks them.
- Interpolation-error adaptation of `tanh` layers: 4 remesh rounds,
  73,701 vertices, average quality 0.77, 2 min 46 s.
- Venus and moving-boundary cases as above. No adversarial-topology suite,
  no termination/robustness statistics, no timing on modern hardware.

## Robustness and limitations the authors admit

- Isotropic size only; anisotropic domain remeshing is future work.
- The local surface model depends on the current mesh; consistency across
  remeshing steps is heuristic, with no global error accumulation bound.
- Ridge/singular-feature loss in the implicit pipeline (Remark 1).
- Sharp-feature *recovery* (when prescribed on an input contour) is listed
  as open in the mesh-generation application.
- All gates (element validity, folding, quality) are floating-point
  geometric checks; exact predicates are never discussed. Validity means
  "no inverted element" numerically, with no symbolic perturbation or
  filtered arithmetic - the classical mmg fragility under near-degeneracy.
- No termination proof for the sweep loops, no determinism statement
  (sweep order and the first-valid rule in internal swap are
  order-dependent), no topology-preservation argument beyond the collapse
  prohibitions.

## What our native tri/tet engine should copy vs do differently

Copy:

- The **operator quartet with per-class gates** and the collapse class
  hierarchy (interior < surface < ridge/reference < singular/required) -
  it is exactly the per-entity provenance skeleton our patch-preservation
  invariant needs, proven in production.
- The **split-then-collapse internal swap**: one guard implementation
  serves three operators; a cheap route to shell remeshing without
  Catalan enumeration.
- The **staged global schedule** (geometry sampling -> size field -> rough
  conformity -> fine polish with widening gate strictness and narrowing
  length bands) and the late construction of the curvature size field.
- The **convex-hull Hausdorff bound (3)** as the *fast reject/accept
  pre-filter*: control-point distances only, conservative, no sampling.
- Curvature sizing `h = sqrt(9 eps / (2 max|k_i|))` with `[hmin, hmax]`
  clamping and the `log(hgrad)` gradation truncation - drop-in compatible
  with the Frey 2005 unit-length contract we already adopted.
- Simultaneous surface+volume remeshing rather than surface-then-fill,
  and the swap-ablation lesson: budget for massive swapping in the volume
  phase.
- The marching-tetrahedra cut + heal architecture for the L3 implicit
  route, including non-manifold entity classes for embedded interfaces.

Do differently:

- **Accumulate the envelope.** Replace the current-mesh-relative Hausdorff
  gate with a per-face accumulated budget against the *original input*
  (Borouchaki-Frey 2005 style, our `TRI-ENV-ACCUM1`), or at minimum pair
  mmg's local gate with a final two-sided audit against the input. mmg's
  `hausd` alone cannot bound total drift.
- **Persistent feature provenance.** Keep an explicit link from every
  feature vertex/edge to the input feature polyline (curve id + parameter),
  not just a type tag plus a locally rebuilt Bezier curve, so feature
  drift is measurable and boundable.
- **Exact/filtered validity predicates.** mmg's FP tolerance checks are
  the known fragility; our engine should gate collapses/relocations with
  robust orientation predicates (as the TetWild lineage does) and keep
  mmg-style checks only as fast pre-filters.
- **Determinism.** Fix sweep order, candidate order in the internal swap,
  and tie-breaks; mmg leaves them unspecified.
- **Anisotropy from day one**: carry the full SPD tensor field of the
  Frey 2005 algebra (`SIZING-METRIC-ALG1`) instead of the scalar `h`, so
  the surface remesher, BL, and volume transition share one contract; mmg
  2014 shows the isotropic degenerate case works end-to-end.
- Report worst-element and drift statistics per stage; the paper's
  evidence style (average quality only) hides tail behavior.

## High-value references from this paper

- Dapogny and Frey (2012), *Computation of the signed distance function to
  a discrete contour on adapted triangulation*, Calcolo 49(3): the
  SDF-on-adapted-mesh ingredient of the implicit route (L3-relevant).
- Frey (2000), *About Surface Remeshing*, 9th IMR: the surface operator
  set this paper compresses; the mmgs ancestor.
- Li, Remacle, Chevaugeon, Shephard (2004), *Anisotropic Mesh Gradation
  Control*, 13th IMR: the `log(hgrad)` truncation heuristic.
- Vlachos, Peters, Boyd, Mitchell (2001), *Curved PN Triangles*: the local
  cubic model the surface support is built on.
- Dobrzynski and Frey (2008), *Anisotropic Delaunay mesh adaptation for
  unsteady simulations*, 17th IMR: the named path to the anisotropic
  volume extension (became mmg3d's aniso mode).
