# Chen et al. — Improved Boundary Constrained Tetrahedral Mesh Generation by Shell Transformation (2017)

**Title:** Improved boundary constrained tetrahedral mesh generation by shell transformation
**Authors:** Jianjun Chen, Jianjing Zheng, Yao Zheng, Hang Si, Oubay Hassan, Kenneth Morgan
**Year / Venue:** 2017, Applied Mathematical Modelling 51, pp. 764–790
**DOI:** `10.1016/j.apm.2017.07.011`
**Pages read:** 27/27 (full PDF incl. appendix proofs and references)
**Status:** FULL_READ (project PDF: `papers/pdf/10_chen_2017_shell_transformation.pdf`)
**Date:** 2026-07-23

## Core algorithm

### What a shell is (paper-specific definition — differs from the usual one)

- Classically a *shell* is the set of tets meeting at one edge (the **supporting edge**;
  faces adjacent to it are **supporting faces**). Chen et al. redefine a shell as a
  **polyhedron** that can be filled with a mesh of tets all meeting at one edge; that
  filling is a **covering mesh** of the shell. The **degree** of a covering mesh = number
  of tets sharing the supporting edge.
- The boundary polygon of a shell orthogonal to the supporting edge `ab` is the **skirt
  polygon** `P = {p1..pm}`.

### Shell transformation vs plain 2-3 / 3-2 / 4-4 flips and edge removal

- Classic **edge removal** (Shewchuk 2002) fully triangulates the skirt polygon and
  removes the supporting edge entirely — all-or-nothing. Basic 2-3/3-2/4-4 flips are
  special cases involving 2–4 tets.
- **Shell transformation** allows a **partial triangulation**: an untriangulated **core**
  (a simple cycle `Pc` of the skirt polygon) may remain, still filled by tets around the
  supporting edge. The shell is *partially reduced* if the new degree n < old degree m,
  *completely reduced* if n = 0 (edge removed). The 3-2 flip is the n = 0, m = 3 special
  case.
- Optimality: a dynamic program (Klincsek-style, Algorithm 2 `fillInMatrices`) computes
  optimal triangulations `K_opt(i,j)` of every skirt-polygon ring `R(i,j)` in O(m^3)-style
  matrix fill; then all valid partial triangulations are enumerated as **simple cycles of a
  triangulation graph** (graph edge `<pi,pj>` exists iff `Mq(i,j) > 0`). Each candidate
  cycle is scored with a lexicographic **quality vector** `Qv = V(Q, Q', Q'')`:
  - `Q(K)`: either Q1 = worst tet quality in K (Eq. 5), or Q2 = `N_big − I(K, Bc)` where
    `I` counts intersections between K and lost boundary constraints (Eq. 6) — i.e. the
    flip can directly optimize *fewer boundary intersections* instead of element shape;
  - `Q'(K)`: 1 iff K removes the target face f (the face the parent recursion wants gone);
  - `Q''(K)`: `N_big − n`, preferring smaller residual degree.
  The old covering mesh is replaced only if the new vector compares strictly better —
  a built-in monotone accept/rollback rule.

### Recursive shell search (Algorithm 1, `recursiveST(e, f, l, l_max)`)

- If a single shell transformation cannot fully reduce the shell of edge `e`, the
  remaining supporting faces are attacked via their **link edges** (the two non-supporting
  edges of a supporting face). For each remaining supporting face `f_i`,
  `pickRecursiveLinkEdge` selects a link edge `e'` and recurses `recursiveST(e', f_i,
  l+1, l_max)`; removing `e'` removes `f_i`, shrinking the shell of `e`. If the shell of
  `e` shrank, the routine restarts on `e` at the same level.
- This expands an **edge tree** rooted at the input edge; in practice hundreds of shells /
  thousands of tets can participate in one call — far larger neighborhoods than Joe's
  composite flips, hence better local optima.
- Recursion filters in `pickRecursiveLinkEdge`: (1) never return a boundary edge (so
  recovered constraints are never destroyed); (2) return nothing if the tets around `f_i`
  overlap the shells of ancestor edges (prevents cyclic rewrites); (3) only return a
  **reflex edge** (locally concave configuration — the only case where recursion can help).
- **Termination / budget controls:** hard depth cap `l_max`; output validity requires all
  positive volumes and no supporting faces around any ancestor edge; optional boundary
  validity conditions BRC1–BRC4 (must not intersect a given boundary edge/face; must not
  intersect boundary edges/faces *more than the input mesh* — a monotone non-worsening
  budget). The outer driver (Algorithm 5) starts with `l_max = 0` and increments it each
  sweep, stopping when all edges are recovered or the mesh metric fails to improve for
  **3 consecutive iterations**.

### Where Steiner insertion is still unavoidable

- Recovery without Steiner points is impossible in general (Schönhardt / Chazelle
  polyhedra; deciding tetrahedralizability is NP-complete; Steiner lower bound is
  quadratic in the worst case). The flip phase is a *preprocessing heuristic*; the main
  procedure (Chen et al. 2011, ref [15]) still inserts Steiner points at intersection
  positions of lost constraints when flips stall. Remaining survivors after suppression sit
  next to **indecomposable polyhedra** (Goerigk & Si 2015) and cannot be flipped away.

## Boundary recovery pipeline (Section 4)

1. Delaunay of boundary points (Bowyer–Watson) inside an outer box.
2. **Preprocessing (new):** edge recovery then face recovery by recursive shell
   transformations only — no point insert/remove.
   - Edge recovery = two passes of Algorithm 5: pass 1 uses BRC1 + Q1 with vector order
     `[Q', Q'', Q]` (kill intersections of the edge being recovered); pass 2 swaps in
     BRC3 + Q2 with order `[Q, Q', Q'']` (reduce *global* intersection count), using a
     hash table of intersected entities to keep BRC3 affordable.
   - Face recovery: same two-pass structure with BRC2 then BRC4, removing mesh edges that
     pierce face interiors (face-boundary intersections were already handled by edge
     recovery).
3. **Main procedure:** conforming recovery by Steiner insertion at intersections, then
   constrained recovery by moving Steiner points off the boundary (ref [15]). The appendix
   proves finite termination of this point-splitting scheme (edge-added / face-added point
   splitting via 2-way / n-way ball cuttings, Lemmas 1–4, Theorems 1–3) — under exact
   arithmetic; the proofs explicitly ignore floating-point round-off.
4. **Postprocessing (new):** for each surviving Steiner point, use recursive ST to remove
   its adjacent edges until a "Christmas tree" configuration forms, then delete the point
   directly. Repeated until no more gains.
5. **On failure:** if the visibility neighborhood `U2(S)` is numerically too small
   (bad ball boundary — tiny or near-360° dihedrals), the 1D bisection search for split
   positions fails; fallback is a 3D optimization-based search (Escobar-style), then
   cavity enlargement per Delaunay criteria. Excessive Steiner counts remain the
   documented real-world failure mode (accumulated round-off breaks predicates).

## Experiments

- **Stretched-triangle benchmark (7 models):** Cami1a, Cami1, Mohne, Thepart,
  Boeing_part, Thru-mazewheel, B747. Steiner points inserted (constrained recovery):
  | Model | Ours | TetGen 1.5 | GHS3D 4.2-2 | GHS3D old | Liu & Baida |
  |---|---|---|---|---|---|
  | Cami1a | 0 | 1 | 13 | NP | NP |
  | Cami1 | 1 | 2 | Fail | NP | NP |
  | Mohne | 1 | 3 | 35 | Fail | 26 |
  | Thepart | 0 | 0 | 4 | 24 | 6 |
  | Boeing_part | 5 | 4 | 22 | Fail | 25 |
  | Thru-mazewheel | 4 | 5 | 41 | 18 | 13 |
  | B747 | 0 | 0 | Fail | NP | NP |
  Ours ≈ TetGen (each wins some), both 5–10x fewer Steiner points than GHS3D / Liu.
  **Timing:** TetGen fastest (0.05–0.33 s); ours 0.4–6.3 s (the DP + partial enumeration
  is not free); GHS3D slowest (1.35–11.9 s, 2 fails).
- **Convergence anatomy (Cami1):** lost edges 243 → 13 as `l_max` goes 0→9 in pass 1
  (intersections 1505 → 39); pass 2 lands at 10 lost edges, each intersected once; main
  procedure inserts 10 Steiner points, suppression leaves **1**. `n2`/`n3` can rise
  transiently (new entities not yet hashed) — the metric is not strictly monotone per
  sweep, only trendwise.
- **F16 aircraft (CFD):** sequential — 170k boundary faces, 3.9M tets, **0 Steiner
  points**, boundary recovery 0.59 s of 257 s total. Parallel — 32 cores, 242 subdomains,
  122.5M tets; domain decomposition injects 1843 small dihedral angles at interfaces, yet
  still **0 Steiner points**; recovery averages 0.68 s/core. The older recovery ([13,15])
  "occasionally failed" on these subdomains.
- **Store-separation local remeshing (moving boundary):** 16 remeshing calls, all
  boundaries recovered in the preprocessing step alone (the hole-expansion backup was
  never triggered); recovery 0.11 s of 1.2 s per remesh.

## Limitations

Stated:
- Slower than TetGen's recovery (optimal/partial DP overhead); authors suggest a hybrid —
  cheap flips first, optimal shell transformation only for stubborn residuals.
- Appendix termination proofs assume exact arithmetic; robustness under round-off is
  explicitly out of scope, and Steiner-heavy regions remain the failure mode.
- No claim of Steiner-free recovery in general — indecomposable polyhedra block full
  suppression.

Inferred for CFD use (AutoTessell):
- The flip search optimizes *topological* objectives (intersection count, degree); Q1
  worst-quality is only one selectable metric — aggressive shell rewrites can trade shape
  quality for recoverability, so a post-recovery quality pass remains mandatory.
- Lexicographic vector comparison + BRC conditions are cheap to check but the DP is
  per-shell O(m^3); on skirt polygons of degree 10+ arising near boundary-layer anisotropy
  this cost is real (their own timing table shows it).
- Nothing here addresses sliver *quality* classes (our FSL coplanar wedges) directly —
  it addresses whether constraints can be recovered without point pollution. Wedge slivers
  whose skirt polygons are geometrically flat will simply yield no valid better covering
  mesh (all candidates have `Q ≤ 0`) and the transformation correctly refuses.

## AutoTessell applicability (native_tet)

Context: `native_tet` is an fTetWild-style engine (Hu 2020 FULL_READ); Si 2015 (TetGen)
is FULL_READ and its recovery = protected CDT + recursive flips/edge removal + Steiner
suppression. The evidence matrix row for Chen 2017 (ABSTRACT_ONLY) said: "apply only as a
boundary-recovery recovery policy, bounded by local neighborhood rollback and budget
caps." The full read **confirms and strengthens** that: the paper itself *is* a bounded
policy — `l_max` schedule, 3-strike improvement stall, BRC monotonicity conditions, and
lexicographic accept-only-if-better are exactly the rollback/budget machinery we wanted.

**What Chen 2017 adds beyond Si 2015 / TetGen:**
1. TetGen's n-to-m flip reduces a shell "in an arbitrary manner"; Chen adds an **optimal**
   selection among all partial triangulations via DP + triangulation-graph cycle
   enumeration, scored by a pluggable lexicographic quality vector — in particular the
   Q2 metric that lets flips *directly minimize constraint intersections*, which TetGen's
   recovery does not optimize for.
2. A **more aggressive recursion policy** (reflex-edge-guided link-edge descent with
   ancestor-overlap guards) that recovers more constraints flip-only: measurably fewer
   or equal Steiner points than TetGen on 5/7 hard models, and 0 Steiner points on
   full CFD workloads where the classic method intermittently failed.
3. **Partial reduction** as a first-class outcome (leave a core, still count it as
   progress via `Q''`), letting a stuck edge-removal contribute instead of failing.
4. Appendix: finite-termination proofs for constrained Steiner-point splitting
   (2-way/n-way ball cuttings) — a correctness skeleton Si 2015 does not spell out in
   this form.

Where it does *not* move us: no envelope/epsilon surface semantics (fTetWild covers
that), no sliver-quality guarantee, exact-arithmetic assumptions, and it presumes a
Delaunay + constraint-recovery pipeline — so in `native_tet` it belongs in the
**recovery/repair lane**, not the main insertion loop.

### Candidate cards

| Card | Mechanism | Target problem | Acceptance signal | Risk |
|---|---|---|---|---|
| `TET-SHELL-1` recursive shell transform for constraint recovery | Implement `shellTransformation` (DP fill + simple-cycle enumeration + lexicographic Qv) and `recursiveST` with reflex-edge filter, ancestor-overlap guard, `l_max` escalation 0..N, 3-strike stall exit; BRC1/BRC3 validity | Boundary faces/edges lost after BSP/insertion that today trigger Steiner-style point pollution or fallback | On the bench suite, count of unrecovered constraint edges after flip-only pass drops vs current flip pass; zero recovered-constraint regressions (BRC monotonicity holds); bounded runtime via l_max cap | O(m^3) DP per shell on high-degree shells; implementation complexity of partial-triangulation bookkeeping; must not run inside envelope-critical fTetWild ops without surface-distance check |
| `TET-SHELL-2` intersection-metric flip objective (Q2) | Add `Q2 = N_big − I(K, Bc)` covering-mesh scoring with the paper's edge/face intersection-share accounting + hash table of intersected entities; use vector order `[Q, Q', Q'']` in a second recovery sweep | Near-wall skew (CYLSKEW) and recovery stalls where shape-based flips plateau but constraint intersections could still be reduced | `n2`-style global intersection count strictly decreases across sweeps on CYLSKEW-class cases; surviving Steiner/fallback insertions reduced; no increase in worst-dihedral beyond tolerance after post-pass | Intersection counting cost (needs the hash-table optimization); transient metric rises (paper's own Table 3) require trendwise not per-step gating |
| `TET-SHELL-3` Christmas-tree Steiner/vertex suppression | Post-recovery pass: for each unwanted interior point, recursiveST its adjacent edges until the ball becomes a "Christmas tree", then delete the point; repeat until no gain | Thin-disk/needle fallback artifacts and interior helper points left by repair passes that degrade local sizing | Removed-point count > 0 on fallback-path meshes with no negative-volume or envelope violation; FSL wedge count on dual_torus does not increase (expected neutral-to-positive; the 61 unflippable wedges are a geometry limit, not a topology one) | Aggressive flipping to reach the tree config can transiently worsen quality; needs transaction rollback if final vector not better; indecomposable neighborhoods will refuse — must budget attempts |

## References worth snowballing (max 5)

1. **Liu, Chen & Chen 2007** [14] — "Boundary recovery after 3D Delaunay tetrahedralization
   without adding extra nodes" (SPR routine): the exhaustive small-polyhedron alternative
   when shells stall; complements ST for ≤40-face cavities.
2. **Shewchuk 2002 (unpublished)** [33] — "Two discrete optimization algorithms for the
   topological improvement of tetrahedral meshes": the edge-removal DP that ST generalizes.
3. **Chen et al. 2011** [15] — "Three-dimensional constrained boundary recovery with an
   enhanced Steiner point suppression procedure": the main procedure this paper wraps;
   needed to implement the full pipeline.
4. **Goerigk & Si 2015** [37] — "On indecomposable polyhedra and the number of Steiner
   points": characterizes exactly where suppression must give up (typed-blocker design).
5. **George, Borouchaki & Saltel 2003** [5] — "'Ultimate' robustness in meshing an
   arbitrary polyhedron": the GHS3D point-splitting baseline the comparisons are against.
