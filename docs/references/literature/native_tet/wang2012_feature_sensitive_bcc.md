# Wang & Yu — Feature-Sensitive Tetrahedral Mesh Generation with Guaranteed Quality (2012)

**Title:** Feature-sensitive tetrahedral mesh generation with guaranteed quality
**Authors:** Jun Wang, Zeyun Yu (Univ. of Wisconsin–Milwaukee)
**Year / Venue:** 2012, Computer-Aided Design 44(5):400–412
**DOI:** `10.1016/j.cad.2012.01.002`
**Pages read:** 13/13 (full article; the "54-page" count in the task brief was incorrect — the PDF is the 13-page journal article)
**Status:** FULL_READ (PDF: `papers/pdf/08_wang_2012_feature_sensitive_bcc.pdf`, text-extracted via PyMuPDF)
**Date:** 2026-07-23

## Core algorithm

Input: an arbitrary closed surface mesh S (no quality requirement — self-intersecting /
non-manifold inputs are tolerated because the method only queries signed distance and
edge–surface intersections). Output: an adaptive tetrahedral mesh whose boundary
*approximates* S (S is NOT preserved). Four-step pipeline:

1. **Adaptive octree subdivision** of a cubic bounding box of S, driven by Euclidean
   distance transformation. Refinement gets deeper toward the surface; a conforming
   constraint keeps the depth-disparity between face-adjacent leaf nodes ≤ 1
   (2:1-balanced octree). Boundary adaptivity uses two criteria per octant ("octron"):
   - Stop if the octant contains no surface triangle.
   - Flatness metric over the normals N = {n_i} of triangles inside the octant:

     `f = max_{0<i,j<m} (n_i − n_j)`   (Eq. 1)

     If f exceeds a threshold, subdivide further. Result: denser tets in high-curvature
     regions (this is the entire "feature sensitivity" mechanism — curvature-proxy
     refinement, not sharp-feature capture).

2. **BCC lattice construction** on the octree leaves. Standard BCC: cell-center node
   connected to the 8 cell corners and 6 neighboring centers. Two transition cases:
   - *0-depth-disparity:* if all four edge-adjacent leaves of a face edge share a depth,
     use the classic BCC tet (two face-adjacent centers + the edge's two endpoints);
     otherwise build two BCC tets using the edge midpoint (Fig. 3(a),(b)).
   - *1-depth-disparity:* split the common quadrilateral face along its diagonal into
     two triangles; each leaf center + one split triangle forms a BCC tet (Fig. 3(c)).

3. **Sign computation + cutting-point snapping.** Each lattice vertex gets a sign from
   the distance transform: `+` inside, `−` outside, `0` on S. All-`+` tets are kept
   (regular interior BCC tets, min dihedral exactly 45°); all-`−` tets are dropped.
   For each lattice edge with opposite endpoint signs, compute the cutting
   (intersection) point p, marching-cubes style. Small marching-cube angles arise when
   a cutting point is "too close" to a lattice vertex, so snap: for p on edge v1v2,

   `λ1 = ‖p − v1‖ / ‖v1 − v2‖`,  `λ2 = ‖p − v2‖ / ‖v1 − v2‖`

   If λ1 < λ (threshold) set the scalar of v1 to zero (snap p onto v1); symmetric for
   λ2/v2; else keep p. Snapping trades boundary smoothness for dihedral quality.

4. **Optimal decomposition of boundary polyhedra.** The inside part of each cut BCC
   tet is one of a finite stencil set (Fig. 5, cases (a)–(i)). Ambiguity lives on
   quadrilateral faces with two cutting points: for triangle (a,b,c) with cutting
   points p1 on ab, p2 on ac, compute `λ1 = ‖p1−a‖/‖b−a‖`, `λ2 = ‖p2−a‖/‖c−a‖`; split
   the quad along diagonal p2–b if λ1 < λ2, else along p1–c (Fig. 7). Case (c) needs an
   extra tie-break: when the λ ordering leaves two decompositions of the residual
   5-vertex polyhedron, pick the diagonal whose resulting dihedral angle
   (∠(5–68–7) vs ∠(6–57–8)) is larger (Fig. 8).

Post-pass: normal-based surface smoothing [ref 36] to reduce snapping bumpiness,
**restricted so no vertex move may worsen any dihedral angle** (the guarantee survives
only because of this restriction).

## Theoretical guarantees — what is proved vs reported

- **Claimed bound: min dihedral angle > 5.71° (exactly 5.717038°) at λ = 0.2.**
- **The bound is established by a computer-aided proof, not a closed-form analytic
  proof.** Each generated tet has vertices either on lattice vertices or on lattice
  edges restricted (by snapping) to the sub-segment ef with ‖af‖/‖ad‖ = ‖de‖/‖ad‖ = λ.
  They sample each such segment with n_s = 200 points and enumerate up to n_s^4 vertex
  placements per stencil (3 symmetry-reduced BCC tet cases, Fig. 11), taking the
  worst case per stencil (Fig. 12: per-case minima 8.13°, 6.72°, 6.32°, 6.34°, 5.717°,
  45.0°). So strictly: the bound is *verified on a 200-point discretization* of the
  continuous configuration space; there is no continuity/interval argument in the paper
  closing the gap between samples. Treat it as an extremely strong empirical
  certificate, not a theorem in the Labelle–Shewchuk sense (whose isosurface-stuffing
  bound 10.7° is also computer-verified but over exact interval arithmetic per their
  paper — Wang–Yu do not state such rigor).
- **The bound is λ-dependent and roughly linear in λ** (Table 1): λ = 0.1 → 2.862°,
  0.2 → 5.717°, 0.3 → 8.565°, 0.4 → 11.422°, 0.5 → 14.312°. Larger λ ⇒ better angles
  but bumpier boundary (snapping moves more surface samples).
- **Assumptions required for the bound:** (i) 2:1-balanced conforming octree with the
  exact BCC transition templates of Sec. 2.1; (ii) snapping applied with the chosen λ
  before decomposition; (iii) the optimal stencil decomposition rules of Sec. 2.3;
  (iv) post-smoothing restricted to non-worsening moves. The bound says nothing about
  fidelity to S — it holds precisely because the boundary is free to deviate.
- Conclusion additionally claims "> 10° if a uniform mesh is generated on the boundary"
  — stated without a table/derivation; treat as reported, not proved.
- Interior regular BCC tets have min dihedral 45° exactly (this part is classic and
  analytic).

## Experiments

- Implementation: Visual C++/OpenGL, 1.8 GHz PC, 2 GB RAM. Main parameter: max octree
  depth (6 "always yields good results").
- Models: Greek sculpture (dihedral range 8.63°–148.29°), 2CMP molecule (all dihedrals
  > 7.21°), Stanford bunny, armadillo, dinosaur, dragon, molecule, teeth, heart,
  high-genus models (genus 2–4), hand/horse; exterior (bounding-box/sphere) meshes for
  aircraft, cow, 1TIM — i.e., external-flow-style domains are demonstrated.
- Comparison vs TetGen (quality switch on) and Netgen (defaults): Wang–Yu histograms
  peak at 60° and 90° (BCC signature); TetGen/Netgen peak near 60° but with min
  dihedrals "very small (even close to zero in some cases)". Vertex counts comparable
  or lower (e.g. armadillo 31,855 vs TetGen 44,084; teeth 16,180 vs Netgen 38,426 /
  TetGen 56,530).
- Fidelity: Hausdorff distance via Metro; TetGen best (it preserves the input surface),
  Wang–Yu ≈ Netgen; "good" but strictly worse than surface-preserving methods.
- Timing (Table 2, total s): bunny 12.8 (TetGen 6.7, Netgen 19.2); dragon 466.9
  (TetGen 108.9, Netgen fail); heart (817k tets) 543.7 where both TetGen and Netgen
  FAIL. Octree subdivision dominates ~98% of their runtime; the meshing step itself is
  seconds.

## Limitations

**Stated by the authors:**
- Boundary of the output is only an approximation of the input surface; "our method is
  inappropriate if the input surface mesh is required to be precisely preserved."
- Cannot preserve sharp edges/corners; a dual-contouring variant they tried recovers
  features but collapses nearby dihedral angles to "very small values."
- Snapping ⇄ smoothness trade-off; smoothing only partially recovers surface quality.
- Guarantee measured only in min dihedral; other quality metrics not addressed.

**Inferred for CFD / AutoTessell use:**
- Violates AutoTessell's #1 invariant (surface preservation): the output boundary is a
  resampled lattice cut, so patch boundaries, CAD feature curves, and named surfaces
  are destroyed. Usable at most as an interior/scaffold strategy, never as the
  boundary-conforming product.
- Isotropic BCC elements near walls: no boundary-layer anisotropy; near-wall resolution
  is octree-step-quantized, and the snapped boundary introduces normal-direction noise
  that would pollute wall-distance and y+ computations.
- 5.71° min dihedral is far below CFD-grade targets; the value of the paper is the
  *floor* plus the 60°/90° bulk, not the floor alone.
- Flatness metric (Eq. 1) is a normal-spread proxy — blind to thin gaps/thin walls at
  scales below the leaf size (distance transform sign can tunnel through thin sheets).
- Octree-subdivision cost dominates; a naive port inherits a heavy preprocessing bill.

## AutoTessell applicability

Our `native_tet` is fTetWild-style (envelope + incremental triangle insertion + local
ops), which is philosophically opposite (surface-preserving, optimization-based, no
angle floor) to Wang–Yu (surface-approximating, template-based, angle floor). The
transferable assets are the *local mechanisms*: λ-snapping, worst-dihedral-aware
diagonal selection, BCC interior scaffolding, and the sampled worst-case certification
harness. Candidate cards:

- **`TET-BCC-DIAG-OPT`** — Mechanism: port the quad-face diagonal selection rule
  (λ-comparison + explicit dihedral comparison tie-break, Figs. 7–8) into our
  wedge/prism decomposition paths. Target: open problem (c) thin-disk/needle legacy
  wedge path, and secondarily (b) since wedge splits currently pick diagonals without a
  dihedral objective. Acceptance: on the thin-disk/needle regression set, worst
  dihedral from wedge splits improves and no case regresses; decomposition remains
  deterministic. Risk: low — purely local, no surface motion.
- **`TET-BCC-SNAP-LAMBDA`** — Mechanism: λ-threshold vertex snapping during incremental
  insertion: when a surface-insertion point lands within λ (relative to edge length) of
  an existing mesh vertex, snap to the vertex (within envelope ε) instead of splitting,
  preventing near-degenerate children at birth. Target: (b) dual_torus
  structurally-coplanar wedge slivers (FSL, 61 unflippable) — many are born from
  near-vertex splits. Acceptance: FSL unflippable wedge count < 61 on dual_torus with
  envelope check still passing and surface Hausdorff unchanged within ε. Risk: medium —
  snapping moves the tracked surface; must be gated by the envelope test per snap.
- **`TET-BCC-SEED-INTERIOR`** — Mechanism: seed the interior (strictly inside the
  envelope, distance-filtered like the sign test here) with BCC lattice points before
  local-op optimization, so the bulk starts at the 45°/60°/90° BCC quality and local
  ops only fight near the boundary. Target: (a) near-wall skew on cylinder/naca —
  a regular graded interior gives smoothing a good anchor, complementing the
  Garimella offset-ring seeding already landed. Acceptance: interior dihedral histogram
  develops 60°/90° peaks; cylinder/naca near-wall skew metric (CYLSKEW) does not
  regress and mean quality improves. Risk: medium — interaction with sizing field and
  insertion order; guard with a feature flag.
- **`TET-BCC-CERT-HARNESS`** — Mechanism: reimplement the paper's computer-aided
  worst-case search (sample cutting-point positions on n_s-point grids, enumerate
  template vertex placements, report per-template min dihedral) as a test harness over
  our own split/wedge templates. Target: (b)/(c) — it would have flagged the FSL
  coplanar wedge template as having *no* positive angle floor before it shipped.
  Acceptance: harness enumerates every decomposition template in `native_tet` and
  prints a certified-by-sampling floor per template; CI fails if a template's floor is
  0. Risk: none at runtime (test-only); cost is harness authoring.

## References worth snowballing (max 5)

1. Labelle & Shewchuk 2007, "Isosurface stuffing: fast tetrahedral meshes with good
   dihedral angles", ACM TOG 26(3) — the direct predecessor with the stronger
   (10.7°, 164.8°) uniform bound; DOI not printed in the paper (standard:
   `10.1145/1276377.1276448`). Highest priority.
2. Molino, Bridson, Teran, Fedkiw 2003, "A crystalline, red green strategy for meshing
   highly deformable objects with tetrahedra", 12th IMR — origin of BCC red–green
   meshing; no DOI printed.
3. Ju, Losasso, Schaefer, Warren 2002, "Dual contouring of hermite data", ACM TOG
   21(3) — the sharp-feature route the authors tried and rejected; DOI not printed
   (standard: `10.1145/566654.566586`).
4. Tournois, Wormser, Alliez, Desbrun 2009, "Interleaving Delaunay refinement and
   optimization…", ACM TOG 28(3) — the optimization-interleaving alternative closest to
   our local-ops loop; DOI not printed (standard: `10.1145/1531326.1531381`).
5. Ito, Shih, Soni 2009, "Octree-based reasonable-quality hexahedral mesh generation
   using a new set of refinement templates", IJNME 77 — template + buffer-layer idea
   relevant to native_hex too; DOI not printed (standard: `10.1002/nme.2470`).
