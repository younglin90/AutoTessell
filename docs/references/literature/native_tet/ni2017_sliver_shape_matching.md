# Ni et al. — Sliver-Suppressing Tetrahedral Mesh Optimization with Gradient-Based Shape Matching Energy (2017)

**Authors:** Saifeng Ni, Zichun Zhong, Yang Liu, Wenping Wang, Zhonggui Chen, Xiaohu Guo
**Venue:** Computer Aided Geometric Design (CAGD), accepted manuscript (COMAID 1598)
**DOI:** `10.1016/j.cagd.2017.02.004`
**Pages read:** 30/30 (accepted-manuscript PDF: `papers/pdf/12_ni_2017_sliver_shape_matching.pdf`; full text extracted to `papers/md/12_ni_2017_extract.txt`)
**Status:** FULL_READ — 2026-07-23

## Core Algorithm

### Shape-matching framework

Represent every d-simplex by a d×d matrix; compare it to a user-specified
template simplex (regular simplex for isotropic meshing) via the affine map
between the two matrices, and minimize the squared Frobenius norm of that map.
Frobenius norm is rotation-invariant but scale-sensitive, so the energy encodes
both shape AND size — the global optimum is "all simplices regular and the same
size".

**Edge-based Shape Matching (ESM)** — the traditional algebraic-metric choice
(Knupp lineage): represent τ₃ by its edge matrix T₃ = [e01 e02 e03], template
by T̂₃; affine map J₃ = T₃T̂₃⁻¹. For a regular template with edge length â:

    E_esm(τ₃) = trace(J₃ᵀJ₃) = (1 / 2â²) · Σ_{0≤i<j≤3} eᵢⱼᵀeᵢⱼ        (Eq. 3)

ESM **cannot suppress slivers**: a sliver has bounded edge lengths but
near-zero heights, so its ESM energy stays moderate.

**Gradient-based Shape Matching (GSM)** — the paper's contribution: represent
τ₃ by the gradients of its linear (barycentric) shape functions ∇ωᵢ instead of
its edges. ∇ωᵢ points from the opposite face Sᵢ toward vertex vᵢ with length
|∇ωᵢ| = |Sᵢ|/|τ₃| = 1/hᵢ (inverse height). Affine map D₃ satisfies
D₃[∇ω̂₀ ∇ω̂₁ ∇ω̂₂] = [∇ω₀ ∇ω₁ ∇ω₂]. For a regular template of edge â:

    E_gsm(τ₃) = trace(D₃ᵀD₃)
              = (â²/18) · (Σ_{i=0..3} |Sᵢ|²) / |τ₃|²
              = (â²/2)  ·  Σ_{i=0..3} 1/hᵢ²                            (Eq. 8)

i.e. **sum of inverse squared heights** (|Sᵢ| = face areas, |τ₃| = volume).
Total mesh energy (Eq. 9) is the average of Eq. 8 over all tets.

**Key algebraic identity (Eq. 13):** D₃ = J₃⁻ᵀ. So with singular values
λ₁,λ₂,λ₃ of J₃:

    E_esm = λ₁² + λ₂² + λ₃²          E_gsm = 1/λ₁² + 1/λ₂² + 1/λ₃²    (Eqs. 14–15)

Both are minimized at λ₁=λ₂=λ₃, but GSM diverges as any single λᵢ→0 — this is
the sliver barrier. (Note: ESM + GSM = symmetric Dirichlet energy; GSM is
exactly its inverse half.)

### Gradient / Hessian derivation sketch

Per-simplex energy is a rational function E = c_d · p(v)/q(v) with, for d=3,
p = Σ|Sᵢ|² (sum of squared face areas) and q = |τ₃|² (squared volume) — both
polynomial in vertex coordinates. Gradient and Hessian follow from the
quotient rule (Eqs. 18–19), assembled over the one-ring T_v of each vertex.
Per-vertex Newton step v* = v − α h⁻¹g (Eq. 16); the energy is non-convex in
the one-ring, so backtracking line search is run in both ±Ψ directions, with
α_init capped at the largest one-ring-interior move. Vertices are updated
one-by-one in descending order of |αh⁻¹g| (worst vertex first). Line search
rejects any step that increases energy or inverts a simplex — **the energy
itself has no inversion barrier** (E_gsm is finite for an inverted tet with
nonzero heights); non-inversion is enforced procedurally.

### Boundary handling — ⚠ VIOLATES AutoTessell's #1 invariant

The method **resamples and moves boundary vertices**:

1. Boundary vertex count N_b is *estimated* from area/volume via a BCC-lattice
   model (Eq. 21) — the input surface tessellation is discarded, not preserved.
2. Sharp-feature-curve vertices are optimized with a 1-simplex GSM (Eq. 10–11),
   sliding along the curve tangent then projecting to the closest curve point
   (Eq. 22).
3. Surface vertices move in their tangent planes then project to the closest
   point on the underlying surface (Eq. 23).
4. Interior vertices are then optimized with boundary fixed.

For AutoTessell (pre-meshing surface must be preserved *exactly*), steps 1–3
are unusable as-is. The importable part is step 4: interior-vertex GSM
smoothing with the boundary hard-pinned, plus the GSM score as a quality gate.
Any adoption card must strip the boundary resampling/projection entirely.

### Connectivity update (interleaved)

Alternates with smoothing for 50 outer rounds (Alg. 1; per round only the
worst ~N/4 free vertices get Newton updates, then a full connectivity pass).
Tet connectivity ops: **2-3 flip, 3-2 flip, 4-4 flip, plus edge removal and
multi-face removal** (Shewchuk's two discrete topological-optimization
algorithms, ref [27]). An op is accepted iff the *average GSM energy per
simplex* decreases (flips change tet counts, so per-tet averaging matters).
Surface edges on sharp features / boundary are never flipped. Initial tet mesh
from TetGen. **No vertex insertion or removal — N is fixed by the user.**

## GSM vs AMIPS (what it changes for native_tet)

native_tet currently optimizes 3D AMIPS (fTetWild lineage):
E_amips = trace(JᵀJ)/det(J)^{2/3} = (Σλᵢ²)/(λ₁λ₂λ₃)^{2/3}. Precise contrasts:

| Property | AMIPS (current) | GSM (this paper) |
|---|---|---|
| Formula in singular values | (Σλᵢ²)/(Πλᵢ)^{2/3} | Σ 1/λᵢ² |
| Barrier strength as one λ→0 (others ≈1) | ~ λ_min^{-2/3} | ~ λ_min^{-2} — **much steeper** |
| Scale invariance | Yes (conformal; sizing handled separately by sizing field) | No — scale-sensitive; also drives uniform sizing toward template size |
| Inversion barrier | Yes (det^{2/3} undefined/complex for det<0; fTetWild keeps orientation) | **No** — finite on inverted tets; inversion prevented only by line-search rejection |
| What it directly penalizes | shape distortion relative to regular tet | small *heights* (1/hᵢ²) — the literal geometric defect of a sliver |
| Congruent with Delaunay | No (fTetWild: BSP+improvement) | No (explicitly stated; flips driven by energy, not Delaunay) |

**Bottom line for the single most important question:** GSM does not find
sliver classes AMIPS is blind to — both energies diverge on every
near-degenerate tet (any tet with a near-zero height has λ_min→0, which blows
up both). What GSM changes is (a) a *quadratically* steeper barrier in λ_min,
so gradient magnitude near degeneracy is far larger → stronger push out of
near-flat configurations during smoothing, and (b) coupling of size into the
energy, which is a liability under a graded sizing field unless the
metric-space mapping (Sec. 3, anisotropic extension) normalizes it. GSM is
also cheaper to evaluate as a *score* (face areas + volume; no det^{2/3}, no
orientation branch) — good fit for a secondary gate. Conversely GSM's missing
inversion barrier means it must never replace AMIPS as the primary smoothing
objective without keeping the signed-volume guard.

## Sliver taxonomy coverage

The paper reproduces the Freitag–Knupp bad-tet taxonomy (Fig. 3): spear,
spindle, spike, splinter, **wedge**, sliver, spade, cap, spire. Claim: all of
these have at least one small or uneven height, so E_gsm = (â²/2)Σ1/hᵢ² is
large on every class — the suppression argument is uniform across the
taxonomy, **empirical, not a proof** (no θ_min lower-bound theorem anywhere in
the paper; Fig. 10a shows θ_min is not even monotone during optimization).

**Verdict on our FSL problem (61 structurally coplanar-flat UNFLIPPABLE wedges
on dual_torus):** this method does **not** cure that class without insertion.
Its only tools are (i) vertex smoothing and (ii) flips/edge-removal/multi-face
removal; vertex count is fixed. If a wedge is unflippable and all its vertices
are boundary-pinned (our invariant forbids the paper's tangential boundary
sliding), GSM has zero degrees of freedom on it. Where it *can* help:

- wedges with ≥1 interior vertex: the 1/h² gradient (direction = ∇ωᵢ, i.e.
  the normal of the opposite face) is exactly the "pull the vertex off the
  plane" direction, with much larger magnitude than the AMIPS gradient — may
  rescue near-flat-but-not-structural cases before they lock in;
- the connectivity arsenal includes **edge removal and multi-face removal**
  [27], which are strictly stronger than 2-3/3-2/4-4 flips. If our
  "unflippable" classification was established against basic flips only, it is
  worth re-testing the 61 wedges against multi-face removal before concluding
  insertion is mandatory.

For truly structural coplanar wedges with all-boundary vertices, insertion
remains the only cure — consistent with our prior assessment.

## Experiments (models, numbers)

Setup: C++, Xeon E5645 2.40 GHz; baselines = CGAL's Perturb [23], Exude [21],
Lloyd/CVT, ODT smoothers; initializations = random / Particle / Lloyd / ODT;
metrics = θ_min, θ_max, mean-of-min dihedral, radius ratio γ = 3·r_in/r_circ,
and counts of tets with min dihedral < 10°/20°/30°/40°. 50 outer rounds.

Highlights from Tab. 1:

- **Duck (isotropic, 10k verts, ~52k tets):** Init θ 0.22°/179°. GSM alone
  25.93°/137.6°. **Particle+GSM 32°/123.8°, γ_min 0.632, zero tets below 30°**,
  99 below 40°. Best CGAL combo (Particle+Perturb) only 27.4°/142°, 77 tets
  <30°. Exude leaves θ_min 16.3°.
- **Fandisk (sharp features, 18k verts, ~91k tets):** Particle+GSM
  29.6°/132.2°, 0 tets <20°, 1 tet <30°. Perturb/Exude leave θ_min ~15.5–15.7°.
- **Sphere (adaptive scaling field):** Particle+GSM 30.2°/130°, 0 <30°.
- **Sphere (anisotropic, measured in metric space):** GSM 16.5°/150.5°;
  Particle+GSM 21.5°/142.5° — noticeably weaker than isotropic.
- **Teddy robustness (2k–30k verts):** Particle+GSM θ_min stable at
  30.9°–34.5°, γ_mean 0.907–0.921 across all resolutions.
- **Cost:** GSM is 2–3 orders of magnitude slower than CGAL local opts —
  Duck: GSM 1769 s vs Exude 3.66 s / Perturb 5.99 s; Sphere-adaptive GSM
  7841 s. Serial per-vertex Newton, global strategy; authors defer GPU/parallel
  to future work.
- Dihedral-angle histograms (Figs. 4–9): GSM curves are visibly narrower and
  pulled away from both 0° and 180° vs every baseline; combined pipelines
  (Particle+GSM) are the best in every figure.

## Limitations

Stated:
- Slow (global optimization, sequential worst-first Newton, 50 rounds);
  efficiency and GPU parallelization left as future work.
- θ_min/θ_max not directly optimized — not monotone during the run (Fig. 10).

Inferred:
- **Boundary is resampled and slid along the surface** — incompatible with
  exact-surface preservation without modification (see above).
- No inversion barrier in the energy; validity rests on line-search rejection.
- Fixed vertex budget N: no refinement, so configurations that are
  combinatorially impossible at the given vertex set (our FSL wedges) cannot
  be fixed.
- No theoretical quality guarantee; results are empirical, initialization-
  dependent (Particle init consistently best; random init plateaus lower).
- Scale-coupled energy exerts uniform-sizing pressure; adaptive/anisotropic
  cases require the metric-space mapping and show weaker θ_min (16.5°–21.5°).
- Comparison set is CGAL-only; no comparison against Klingner–Shewchuk
  aggressive improvement or TetWild-class methods.

## AutoTessell applicability

Evidence matrix row (`docs/references/literature/native_tet/evidence_matrix.md`,
Ni 2017): *introduce shape-barrier score as secondary gate; pair with
dihedral + signed-volume gate before rollback.*

Candidate cards:

- **TET-SHAPE-1 — GSM score as secondary quality gate.**
  Mechanism: compute per-tet E_gsm = (â²/18)·Σ|Sᵢ|²/V² (â = local target edge
  from sizing field so the score is size-normalized); use it as the
  shape-barrier score in the accept/rollback gate, paired with the existing
  dihedral and signed-volume gates. Cheap: 4 face areas + 1 volume, no SVD,
  no orientation branch.
  Target: all native_tet improvement passes; first consumer = CYLSKEW
  near-wall rollback decisions.
  Acceptance signal: gate flags every tet the dihedral gate flags plus
  near-degenerate tets the dihedral histogram bins miss; no increase in false
  rollbacks on the bench matrix.
  Risk: low — read-only scoring; threshold calibration needed per sizing field.

- **TET-SHAPE-2 — GSM-blended interior smoothing pass.**
  Mechanism: for interior vertices only (boundary hard-pinned, dropping the
  paper's Eq. 22/23 sliding), add a one-ring Newton smoothing pass on
  E = AMIPS + β·GSM (or pure GSM as a post-pass after AMIPS converges),
  worst-vertex-first ordering, line search rejecting energy increase and
  inversion. The 1/h² term gives a much steeper push off near-flat
  configurations than AMIPS's λ^{-2/3} barrier.
  Target: naca residual skew ~60.3 and CYLSKEW near-wall interior vertices,
  where AMIPS smoothing has plateaued.
  Acceptance signal: max skew on naca drops below 60; CYLSKEW near-wall
  min-dihedral count <30° decreases; surface hash unchanged; zero negative
  volumes.
  Risk: medium — GSM's size coupling can fight the graded sizing field
  (normalize â per element); keep AMIPS/signed-volume guard since GSM alone
  has no inversion barrier.

- **TET-SHAPE-3 — multi-face removal re-test on FSL wedges, then
  GSM-gradient-directed insertion.**
  Mechanism: (a) re-run the 61 dual_torus wedges against edge removal +
  multi-face removal (Shewchuk [27]) — strictly stronger than the 2-3/3-2/4-4
  flips the "unflippable" label may have been established against, and
  accepted under a per-tet-average GSM decrease criterion as in this paper;
  (b) for survivors, insert a Steiner point placed along the GSM gradient
  direction ∇ωᵢ (normal of the flat wedge's base plane) — the direction that
  maximally increases the vanishing height per unit motion.
  Target: FSL 61 coplanar-flat wedges on dual_torus.
  Acceptance signal: wedge count → 0; surface untouched; cell-count increase
  bounded (< #wedges × cavity size).
  Risk: medium-high — insertion changes cell counts and needs local cavity
  retetrahedralization; (a) alone is cheap and should run first.

## References worth snowballing (max 5)

1. **[27] Shewchuk — "Two discrete optimization algorithms for the topological
   improvement of tetrahedral meshes"** (unpublished manuscript): edge removal
   + multi-face removal — directly relevant to the FSL "unflippable" question.
2. **[25] Freitag & Knupp 2002 — condition-number optimization, IJNME 53(6)**:
   source of the bad-tet taxonomy and the competing algebraic metric
   (condition number = another function of the λᵢ; compare barriers).
3. **[3] Shewchuk 2002 — "What is a good linear element?" (IMR 11)**:
   theoretical grounding for why gradient/interpolation error motivates
   height-based penalties.
4. **[23] Tournois, Srinivasan, Alliez 2009 — Perturbing slivers in 3D
   Delaunay meshes (IMR 18)**: the CGAL Perturb baseline; the local
   sliver-perturbation alternative that is 100–1000× faster.
5. **[16] Zhong et al. 2013 — Particle-based anisotropic surface meshing
   (TOG 32(4))**: the initialization that dominates every GSM experiment;
   candidate pre-conditioner if GSM-style smoothing is adopted.
