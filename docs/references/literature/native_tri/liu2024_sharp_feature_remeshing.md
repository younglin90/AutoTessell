# Liu et al. - Surface Remeshing with Sharp-Feature Preservation via Iterative Sample-Point Identification

## Bibliography and access

- Jingjing Liu, Yuyou Yao, Yue Fei, Gaofeng Zhang, Liping Zheng.
- Exact title: *Surface remeshing with preservation of sharp features through
  iterative identification and optimization of sample points*.
- *Computers & Graphics*, 121, 103949, 2024. Received 20 October 2023,
  revised 29 April 2024, accepted 21 May 2024, online 31 May 2024.
- DOI: `10.1016/j.cag.2024.103949`.
- Local full text:
  `papers/pdf/26_liu_2024_sharp_feature_remeshing.pdf`.
- Review status: `FULL_READ` on 2026-07-23. Pages 11/11 (the local PDF is the
  11-page published journal version, not a 60-page manuscript). All pages were
  text-extracted with PyMuPDF and read in full: title/authors/DOI, Algorithms
  1-3, Eqs. (1)-(3), parameter study, Tables 1-2, limitations, and the
  29-entry reference list were all covered.

## Problem and contract

Given a raw **manifold** triangle mesh `M` with sharp features (CAD-like
creases), produce a high-quality isotropic remesh whose sample points near
features are constrained onto the original feature edges, so the output
preserves feature curves without the two classic failure modes:

1. **Predetermination methods** (fixed feature samples placed before
   optimization, e.g. Alliez 2005, VoroCrust) yield narrow triangles near
   feature edges because feature samples never participate in smoothing.
2. **Smoothing/implicit methods** (MAI feature-intensity, CREVO) can lose
   features on complex inputs because nothing hard-constrains samples to the
   feature polyline.

The proposal: keep an ordinary CVT-style optimizer (GPU RTF) for bulk samples,
but **re-decide feature membership of every sample point in every iteration**
from its projection distance to the input feature edges, plus a continuity
repair pass. Output connectivity is extracted at the end by RVD-based
reconnection (Yan 2009).

Important premise correction: the paper does **not** avoid dihedral-threshold
feature tagging. Feature edges are detected up front by a plain
adjacent-facet-normal angle test with a fixed default threshold. What is
"iterative" is the **sample-point-to-feature assignment**, not feature
detection itself.

## Pipeline and key equations

**Stage 1 - static feature extraction.** Traverse every edge of `M`; the edge
is a feature edge when the adjacent-facet normal angle `theta_e >= theta# = 45
degrees`. Feature vertices are classified by feature degree (number of
incident feature edges):

```text
d_f(v) = 1  -> feature boundary vertex   (pinned)
d_f(v) = 2  -> ordinary feature vertex   (slidable along the curve)
d_f(v) >= 3 -> feature corner vertex     (pinned)                      (Eq. 1)
```

Corner and boundary vertices are inserted directly as sample points and are
**never moved** in the optimization. Feature edges are then grouped into
curve segments delimited by "feature index vertices" (corners/boundaries);
closed rings without any corner get two artificial corners (first detected
vertex and its farthest vertex), then each half-ring is subdivided again so
every group has a unique index vertex - this grouping exists to parallelize
per-curve work on the GPU and to give each sample a curve identity.

**Stage 2 - iterative loop** (Algorithm 1), repeated until the count of large
feature-edge gaps `N_G` is zero:

1. Optimize ordinary samples `S_down` by RTF (GPU CVT on restricted tangent
   faces, Yao 2023).
2. **Dynamic feature-sample identification** (Algorithm 2): for each sample
   `s_i`, find `k`-nearest feature vertices, project `s_i` onto the feature
   edges containing them, keep the nearest projection `s_i^p` that lies
   **within** the edge segment (projections onto edge extensions are
   rejected). `s_i` becomes a feature sample iff

   ```text
   d_i < D_i = delta * dbar_i,   delta = 0.3,                        (Eq. 2)
   ```

   where `dbar_i` is the average distance from `s_i` to its `m = 8` nearest
   sample points (a local sizing proxy). Identified feature samples are moved
   exactly to `s_i^p`, i.e. **onto the input feature polyline**.
3. **Feature-edge continuity preservation** (Algorithm 3):
   - *Gap filling:* for each feature sample, if the distance to its adjacent
     feature sample along the curve exceeds `D_gap = lambda * dbar_i`
     (`lambda = 1.4`), recruit the nearest ordinary sample whose projection
     falls inside the gap and project it onto the feature edge (ordinary
     samples projecting outside the gap are skipped; the next-nearest is
     tried).
   - *Ostracism of edge-close samples:* an ordinary sample `s_p` with
     projection distance `d_near < D_near = sigma * |e_p|` (`sigma = 0.75`,
     `|e_p|` the feature-edge length) is pushed away perpendicular to the
     feature edge to distance `sigma * |e_p|`; near a corner vertex the
     push direction is tilted away from the corner with a weight
     `||s_p - s_p^p|| / (sigma * |e_p|)` toward `(v_cor - s_p^p)` so the
     deviated point does not land in another edge's exclusion zone (Eq. 3,
     two-case formula).
   - Finally each feature sample is relaxed to the centroid of its two
     adjacent reconstructed feature edges - a 1-D CVT along the curve.

**Stage 3 - extraction.** RVD-based reconnection (Yan 2009) turns optimized
samples into the output mesh. The extraction step itself has **no feature
awareness** - this is the source of the paper's main failure mode.

Parameter rationale: `delta = 0.3` (larger converges faster but overcrowds
the feature line), `lambda = 1.4` (smaller is safer but slower; features held
in all their tests at `lambda <= 1.4`), `sigma = 0.75` (started from the
equilateral-height 0.866 but 0.75 empirically gave better global quality).
Quality metric `Q_t = 6/sqrt(3) * A_t / (S_t * E_t)` (area, half-perimeter,
longest edge).

## Exact-vs-approximate preservation verdict

- Feature sample points are placed **exactly on the input feature polyline**
  (orthogonal projection onto the original feature edges, with segment-bounds
  check). Corners and curve endpoints are pinned exactly. So positionally the
  vertex-on-curve contract holds with respect to the **discrete input
  polyline** (there is no underlying smooth-curve geometry; fidelity to CAD
  curves is only as good as the input tessellation).
- However, the **feature-edge connectivity of the output is reconstructed,
  not carried**: the output crease exists only if RVD reconnection happens to
  connect consecutive on-curve samples. The gap/ostracism loop (`N_G = 0`
  stop rule) is a heuristic that makes this likely, not guaranteed; the paper
  itself shows extraction-stage feature loss between narrow feature edges
  (Fig. 11) and offers no convergence or termination proof for the loop.
- Verdict: **exact point placement, approximate (best-effort) edge
  provenance**. This fails AutoTessell's hard per-edge provenance gate unless
  the extraction step is replaced by one that consumes curve identity.

## Experimental evidence

Windows 10, i7-9700K, RTX 2080 Ti, CUDA 10.0. Models from AIM@Shape and
Stanford: Disc, Joint, Finedraw, Flower, Gear (CAD-like), Horse, Lion
(organic). All defaults `theta# = 45deg, delta = 0.3, lambda = 1.4,
sigma = 0.75`.

- Own results (Table 1): e.g. Gear input `Q_min 0.000, theta_min 0.013deg`
  -> output at 20k samples `Q_min 0.329, Q_avg 0.883, theta_min 13.8deg,
  d_H 0.225e-2, RMS 0.167e-3`. Outputs cluster at `Q_avg 0.87-0.92`,
  `theta_min.avg ~ 50-53deg`, but `Q_min 0.32-0.48` and `theta_min
  13.8-21.8deg` - no minimum-angle guarantee.
- Comparison (Table 2, Joint / Fandisk / Crimp vs RTF, MAI, VoroCrust,
  CREVO): the method wins or places second on `d_H` and `RMS` (Joint:
  `d_H 0.155e-2`, `RMS 0.337e-3`, best of all five) and is **1-2 orders of
  magnitude faster** (Joint 1.88 s vs MAI 84.8 s, VoroCrust 141.1 s, CREVO
  54.4 s) thanks to the GPU. But `Q_min`/`theta_min` are consistently worse
  than CREVO (Fandisk: ours `theta_min 21.8deg` vs CREVO `40.0deg`) - hard
  on-curve projection destroys local CVT regularity near creases; the paper
  admits this "slight degradation".
- MAI and CREVO both visibly lose features on the Crimp model; VoroCrust
  keeps features but with thin triangles near creases (`Q_min 0.142` on
  Fandisk). This triangulates well with our Hu 2016 note: intensity-based
  soft weighting is not a preservation guarantee.
- No noise-robustness experiment exists. All inputs are clean (if
  badly-shaped) tessellations; the 45-degree dihedral detector and the
  distance-based identification were never stressed with scanner noise.
  Horse/Lion only show the method does not harm feature-free organic meshes.

## Limitations and claim boundary

- Feature detection is a fixed-threshold dihedral test and the authors call
  it "not perfect": a **cone apex has feature degree 0** (all incident
  dihedral angles small) and is silently lost (Fig. 8). They punt to
  curvature-based detection as future work.
- **Non-manifold meshes are out of contract** (multi-face common edges break
  the edge-based detector); FEM meshes likewise.
- **Narrow feature-to-feature regions fail at extraction**: RVD cells can
  bridge two close feature edges, so the reconstructed crease breaks
  (Fig. 11). The proposed fix (feature-aware extraction) is future work.
- No convergence proof for the `N_G = 0` loop; no determinism statement
  (GPU-parallel recruit-nearest races are not discussed).
- No topology/self-intersection/watertightness invariant is stated anywhere;
  fidelity is audited only by sampled `d_H`/RMS after the fact.
- Quality floor is empirical, not enforced: `theta_min` down to 13.2deg on
  Joint. The relative ranking (worse `Q_min` than local-operator methods) is
  acknowledged.
- All parameters are global constants tuned on the test set; no per-feature
  or curvature-adaptive scaling.

## Delta vs the feature-skeleton approach (Vorsatz 2003 / TRI-FEATURE-SKELETON1)

- **Same taxonomy**, independently rediscovered: corner (`d_f >= 3`, pinned)
  / curve vertex (`d_f = 2`, slides along curve via 1-D CVT centroid) /
  boundary (`d_f = 1`, pinned) maps 1:1 to skeleton corners / bone vertices
  / skeleton constraints, and matches Dunyach 2013's corner-line
  distinction.
- **Membership is dynamic, not static**: the skeleton fixes which mesh
  vertices are feature vertices up front; Liu re-elects feature *samples*
  from the current point distribution every iteration (Eq. 2) and can
  recruit ordinary samples into gaps or expel crowded ones. This is the
  paper's genuine novelty and directly fixes the skeleton approach's known
  weakness of under/over-sampled bones after resampling.
- **Weaker on the edge contract**: the skeleton protects bone *edges*
  combinatorially through every operation; Liu protects only *points* and
  regenerates edges at extraction, which is where it fails (Fig. 11).
  For AutoTessell the synthesis is clear: adopt Liu's dynamic election +
  gap-fill/ostracism spacing control **inside** a skeleton that still owns
  edge provenance, rather than replacing the skeleton.
- Also note the per-curve grouping with unique index vertices: that is a
  ready-made parallel decomposition and a natural provenance key (sample ->
  curve group -> input edge chain) that the skeleton card can reuse.

## AutoTessell applicability

- `core/preprocessor/native_remesh/isotropic.py` currently freezes feature
  vertices and snaps to nearest original vertices. Liu shows a strictly
  better middle ground at near-zero extra cost: project-to-feature-polyline
  (continuous position on the chain, not vertex quantization) plus 1-D CVT
  relaxation along the chain, with corners pinned per Eq. (1).
- The **ostracism rule is the cheapest known fix for thin near-crease
  triangles**: pushing non-feature points to `0.75 * local-edge-length`
  clearance is a one-line guard that VoroCrust-style outputs lack, and it is
  what buys Liu its `Q_avg ~ 0.9` right up to the crease.
- The **gap threshold** `lambda * local-spacing` gives a falsifiable spacing
  invariant for feature chains: adjacent on-curve samples must satisfy
  `d <= 1.4 * dbar`. That is a measurable surface-gate quantity.
- Do **not** adopt the reconstruct-edges-at-extraction design: it is the
  single point where the method loses its own contract. AutoTessell's gate
  requires per-edge provenance; on-curve point placement must be paired with
  constrained connectivity (feature chain edges emitted directly from
  consecutive on-curve samples of the same curve group).
- Dihedral detection at fixed 45 degrees is weaker than what we already plan
  (Hu 2016 feature intensity; cone-apex counterexample here is a concrete
  regression test to keep).

## Falsifiable implementation cards

(Existing cards checked in `evidence_matrix.md` and sibling notes:
`TRI-FEATURE-SAMPLE1`, `TRI-FEATURE-SLIDE1`, `TRI-FEATURE-ANGLE1`,
`TRI-FEATURE-SKELETON1`, `TRI-FEATURE-CURVE1` - no overlap below.)

1. `TRI-FEATURE-DYNID1`: inside the skeleton-owned feature chains, re-elect
   feature samples dynamically per iteration by projection distance
   `d_i < 0.3 * dbar_i` (Eq. 2) with segment-bounds rejection, recruit
   nearest ordinary samples into chain gaps larger than `1.4 * dbar_i`, and
   relax on-chain samples by 1-D CVT with corners pinned. Pass only if (a)
   every chain satisfies the spacing invariant `d_adjacent <= 1.4 * dbar` at
   convergence, (b) the loop terminates deterministically on all bench
   models, and (c) feature-edge provenance (sample -> curve group -> input
   edge) survives with zero broken chains - measured against the Fig.-11
   narrow-feature failure case reproduced synthetically.
2. `TRI-FEATURE-CLEAR1`: add the ostracism guard - any non-feature vertex
   whose distance to a feature chain is below `sigma * local feature-edge
   length` (start `sigma = 0.75`) is displaced along Eq. (3), including the
   corner-tilt case. Accept only if near-crease minimum triangle quality
   improves (target: `Q_min` within one band of the mesh-interior `Q_min`)
   without increasing Hausdorff error, benchmarked on Fandisk/Joint-class
   inputs against the guard-off baseline.

## High-value references from this paper (snowball)

- Yao et al. (2023), *RTF: GPU restricted tangent face remeshing*, CAGD
  104:102216 - the bulk optimizer; the GPU speed story lives here.
- Zhang et al. (2022), *CREVO: constrained evolutionary vertex
  optimization*, CGF 41(2) - best-in-class `Q_min`/`theta_min` competitor;
  candidate for our minimum-angle gate.
- Abdelkader et al. (2020), *VoroCrust*, ACM TOG 39(3) - sphere-pair seed
  feature capture; already vendored as reference in the repo.
- Yan and Wonka (2013), *Gap processing for adaptive maximal Poisson-disk
  sampling*, ACM TOG 32(5) - the predecessor gap-elimination machinery.
- Khan et al. (2020), *Surface remeshing: a systematic literature review*,
  IEEE TVCG 28(3) - the survey the quality metrics are drawn from.
