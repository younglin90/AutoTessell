# Cheng & Dey 2003 - Quality Meshing with Weighted Delaunay Refinement

## Bibliography and access

- Siu-Wing Cheng and Tamal K. Dey, *SIAM Journal on Computing*, Vol. 33, No. 1,
  pp. 69-93, 2003.
- DOI: https://doi.org/10.1137/S0097539703418808
- PDF read: `docs/references/papers/source/pdf/09_cheng_2003_weighted_delaunay_refinement.pdf`
- Status: `FULL_READ` (25/25 pages), 2026-07-23. Full text extracted and read:
  definitions, algorithm `QualMesh`, all lemmas/theorems (3.2-3.7, 4.1-4.3,
  5.1-5.2, 6.1-6.6, 7.1-7.12), proofs, and conclusions.

## One-line summary

First **deterministic** algorithm producing a boundary-conforming 3D Delaunay
mesh with bounded radius-edge ratio and **no slivers**, by interleaving
Ruppert/Shewchuk Delaunay refinement with the Cheng et al. 2000 weight-pumping
technique — the refinement stage pre-clears enough room around every vertex that
the final pumping stage can never challenge the boundary.

## Definitions and contract

- Quality is measured by two ratios: `rho(tau) = R/L` (circumradius / shortest
  edge; *skinny* if `rho > rho0`) and `sigma(tau) = V/L^3` (normalized volume;
  *sliver* if `rho <= rho0` and `sigma <= sigma0`).
- Input is a **PLC** (vertices, segments, facets) bounding a convex volume (any
  PLC is boxed and the box meshed; unwanted tets discarded afterwards).
- **Hard input assumption: no input angle is acute** — every angle between two
  segments sharing a vertex, a segment and a facet, or two facets sharing a
  vertex or segment must be `>= pi/2`.
- Weighted point `x` with weight `X^2` is a sphere of radius `X`; weighted
  distance `pi(x,y) = ||x-y||^2 - X^2 - Y^2`; `pi = 0` means orthogonal. The
  *smallest orthosphere* replaces the circumsphere; a tet is weighted Delaunay
  if its orthosphere is further-than-orthogonal from all other weighted points.
- **Encroachment is redefined in weighted terms**: a weighted point `p`
  encroaches a weighted-subsegment/subfacet if `p` is *closer than orthogonal*
  to its smallest orthosphere.
- **Vertex gap property** (the load-bearing invariant): every vertex `u` uses
  weight at most `omega0^2 f(u)^2` (f = local feature size) and its Euclidean
  nearest-neighbor distance is at least `2 omega0 f(u)`, with
  `omega0 = 1/(2(1+C1))`, `C1 = 7 sqrt(2) rho0 / (rho0 - 4)`. Hence pumped
  spheres never intersect each other.

## Algorithm: QualMesh

Two stages. Stage one runs on the **unweighted** Delaunay triangulation; only
the encroachment *checks* use hypothetical weighted vertices. Stage two
(pumping) is the only place the weighted Delaunay triangulation is actually
built.

Step 2 applies rules with strict priority (Rule i only if no Rule j < i
applies):

- **Rule 1 (subsegment refinement).** Encroached subsegment -> insert its
  midpoint.
- **Rule 2 (subfacet refinement).** Encroached subfacet -> insert circumcenter
  of the subfacet containing the encroacher's projection (Lemma 3.6 guarantees
  one exists), unless that center encroaches a subsegment, in which case reject
  and fall back to Rule 1.
- **Rule 3 (tetrahedron refinement).** Tet with `rho > rho0` -> insert its
  circumcenter `z`; if `z` encroaches a subsegment/subfacet, reject `z` and
  split that element via Rule 1/2 instead. (Identical to Shewchuk.)
- **Rule 4 (weighted encroachment — the new rule).** Take a vertex `v` incident
  to a sliver (`sigma <= sigma0`). Form the *hypothetical* weighted vertex `v`
  with the **maximum pumping weight** `omega0^2 f(v)^2`. If this inflated
  sphere encroaches (weighted sense) any subsegment/subfacet not on `v`'s own
  segment/facet, refine that boundary element via Rule 1/2. No weight is
  actually stored; Rule 4 only *simulates* worst-case pumping to trigger
  protective boundary refinement.

Step 3 (**pumping**): once no rule applies, for each vertex `v` incident to a
sliver, sweep its weight through `[0, omega0^2 f(v)^2]` until no sliver is
incident to `v`, maintaining the weighted Delaunay triangulation (flips at
discrete weight events). The claim — proved as Theorem 7.2 — is that no pumped
vertex can now encroach any weighted-subsegment or weighted-subfacet, so the
boundary survives pumping untouched.

Key supporting lemmas: Lemma 3.2/3.3 (orthocenters stay inside their
segment/facet/domain when nothing is encroached), Lemma 3.4/3.5 (non-acute
input angles prevent cross-element encroachment — this is exactly where the
`>= 90 degrees` assumption is consumed), Lemma 3.6 (projection-containing
encroached subfacet exists), Lemmas 4.1-4.3 + 5.1-5.2 (insertion-radius
recurrences and the `f(x)/C_i` lower bounds, requiring `rho0 > 4`), Lemma 7.5
(`N(v) <= 2 sqrt(2) f(v)` at end of refinement, so the pumping interval
`[0, omega0^2 f(p)^2]` contains `[0, omega0^2 N(p)^2 / 8]`, which is enough for
the exudation argument).

## Difference from Cheng et al. 2000 (sliver exudation)

| Aspect | Cheng et al. 2000 | Cheng & Dey 2003 |
|---|---|---|
| Domain | **Periodic point sets only** — no boundaries | Bounded PLC domains with boundary conformity |
| Weight interval | `[0, omega^2 N(v)^2]` (nearest-neighbor based) | `[0, omega0^2 f(v)^2]` (local-feature-size based); Lemma 7.5 bridges the two |
| Boundary handling | None (this was the open problem) | Rule 4 pre-refines the boundary until the *maximum possible* weight cannot encroach it; Theorem 7.2 then proves pumping is boundary-safe |
| Precondition supply | Assumes a ratio-property Delaunay mesh is given | Generates the ratio-property mesh itself (Rules 1-3) and interleaves that generation with sliver-preparation (Rule 4) in one loop |
| Determinism vs. alternatives | Deterministic but boundary-free | First deterministic boundary-conforming result; contrast Li & Teng 2001, which handles boundaries by *randomized* point insertion near sliver circumcenters (adds points; this paper pumps instead of adding points wherever possible) |
| Finite-set machinery | Claim 7 for periodic sets | Lemma 6.6: finite-set analogue, needing the extra hypothesis that every orthocenter lies inside `Conv V` (discharged by Lemma 3.3(iii) + Theorem 7.2) |

So the 2003 paper is not a new sliver-removal mechanism — the pumping engine,
forbidden-interval argument, and constants are imported wholesale from 2000
(Claims 4, 7, 10, 11, 13 are cited directly). The contribution is the
**encroachment-simulation rule and the proof chain that makes exudation legal
next to a boundary**.

## Theoretical guarantees (exact statements and assumptions)

- **Theorem 3.7 (complexity):** `O(N^2)` total time, `N` = output vertex count.
- **Theorem 7.1 (termination + gradedness):** follows from Lemma 5.2's lower
  bound `||u-v|| >= f(u)/(1+C1)` and a packing argument. Requires `rho0 > 4`
  (the constants `C1 > C2 > C3 > sqrt(2)` blow up as `rho0 -> 4`).
- **Theorem 7.2 (conformity):** at completion no weighted-subsegment or
  weighted-subfacet is encroached, so the weighted Delaunay mesh **contains the
  input segments (as unions of subsegments) and facets (as unions of
  weighted-subfacets)** — boundary conformity survives pumping.
- **Theorem 7.6 (no sliver):** there exists `sigma0 > 0` such that every output
  tet has `sigma > sigma0`; combined with the post-pumping ratio property
  `rho'` (Lemma 6.6) every output tet has bounded aspect ratio. The proof is
  the forbidden-interval argument: a sliver `pqrs` survives pumping of `p` only
  while `P^2` lies in an interval of width `O(sigma0 N(p)^2)`; at most
  `delta0^3` slivers touch `p` (constant vertex degree, Lemma 7.4), so choosing
  `sigma0 < omega0^2 / (8 k' delta0^3)` leaves a sliver-free weight available.
- **Theorem 7.12 (size optimality):** output size is within a constant factor
  of **any** bounded-aspect-ratio mesh of the same domain (Mitchell-Vavasis +
  Ruppert style argument via `int dx/f(x)^3`).

**Which bad-tet classes are and are not eliminated.** In the ratio taxonomy the
`rho <= rho'` bound kills needles, caps, and all large-circumradius shapes,
and `sigma > sigma0` kills the flat sliver/wedge class that survives radius-edge
control. Formally *no* degenerate class survives. The catch, stated bluntly by
the authors themselves: "the constants derived for the theory are miserably
unsatisfactory for all practical purposes" — `rho0 > 4` is already coarse
(radius-edge 4 admits terrible tets) and `sigma0` is "extremely small", so the
theorem excludes only near-exactly-degenerate slivers. The practical hope rests
on Edelsbrunner & Guoy's experiments (exudation empirically achieves > 5-degree
angles except near boundaries). Also note the output is a **weighted** Delaunay
mesh: cells are ordinary tets, but the connectivity is a regular triangulation,
not the unweighted Delaunay of its vertices.

## Practicality assessment

**This is not a bounded post-pass on an arbitrary existing tet mesh.** It
requires owning the entire construction end to end:

1. The mesh must be Delaunay throughout stage one — Rules 1-4 are defined via
   circumsphere/orthosphere emptiness and priority-ordered global queues.
2. Sliver safety is only proved because Rule 4 refined the boundary *before*
   pumping; running Step 3 alone on a mesh that never saw Rule 4 has no
   boundary-safety guarantee (this is exactly the pre-2003 open problem).
3. `f(v)` (local feature size against the input PLC) must be computed per
   Rule-4 application — `O(n)` each, fine in theory, awkward in practice. The
   conclusions propose the practical dodge: skip `f(v)`, grow the weight
   gradually, and watch tet quality at the discrete flip events.
4. Pumping needs an incremental weighted-Delaunay (regular triangulation)
   maintenance kernel with weight-driven flips — a data structure native_tet
   does not currently have.

What *is* extractable as a bounded local operation: the **pumping move
itself** — for one interior vertex, sweeping a weight and re-deriving the star's
regular triangulation is a local, rollbackable operation (the star has constant
size under a ratio property, Lemmas 7.3/7.4), and the forbidden-interval
formula `H(P) = H(0) - P^2/(2D)` gives a closed-form per-sliver diagnostic.

## Limitations for CFD / AutoTessell use

- **Boundary tessellation is not preserved.** Rules 1, 2, and 4 insert Steiner
  vertices *on* input segments and facets, and facet triangulations are the 2D
  (weighted) Delaunay of whatever vertices land there — so the input surface
  triangulation is refined and re-triangulated. Planar facet *geometry* is
  preserved exactly (points stay on the facet), but AutoTessell's #1 invariant
  is exact preservation of the pre-meshing surface mesh, which this algorithm
  violates by design. A curved CAD surface represented as many small facets
  makes it worse: each facet boundary is a constraint edge, and adjacent facets
  meet at dihedral angles that are almost never `>= 90 degrees`.
- **The non-acute input angle assumption is fatal for real CAD.** Real parts
  have acute feature angles everywhere; the entire Lemma 3.4/3.5 termination
  chain collapses without it. (Later literature — Cheng-Dey-Ramos-Ray SVR,
  Shewchuk's CDT work — attacks this, but not this paper.)
- Convex-domain requirement (box trick) means internal-flow domains are meshed
  and clipped, generating then discarding work outside the region of interest.
- Guaranteed `sigma0` is far below CFD-usable dihedral-angle thresholds; the
  theorem is a non-degeneracy certificate, not a quality target.
- Uniform `omega0` and global priority queues assume isotropic sizing; no
  anisotropy, no boundary-layer awareness.

## AutoTessell applicability

native_tet is an fTetWild-style engine (epsilon-envelope + incremental triangle
insertion + local improvement ops), **not** a Delaunay-refinement engine, so
QualMesh cannot be adopted wholesale. The prior evidence-matrix assessment —
"treat as future sliver-robust path after exact boundary protection; not yet
ready for baseline engine" — **survives and is strengthened** by full reading:
the boundary-conformity machinery is precisely the part we cannot use (it
mutates the surface), while the interior pumping move is the part we can.

Open problems the paper speaks to: (a) CYLSKEW near-wall skew, (b) the 61
structurally coplanar-flat **unflippable** wedge slivers on dual_torus (FSL
sequence), (c) thin-disk/needle fallback. Pumping is interesting for (b)
because a weight sweep explores regular-triangulation connectivity of a vertex
star that the 2-3/3-2/edge-swap repertoire may not reach, and the paper proves
slivers only survive inside measure-`O(sigma0 N^2)` weight intervals.

### Candidate cards

#### TET-WDEL-1 - Interior-only local pumping pass for locked slivers

- **Mechanism:** for each sliver whose vertices are all interior (no vertex on
  the tracked surface), pick the sliver vertex `p` with the largest clearance,
  sweep weight `P^2` through `[0, omega^2 N(p)^2]` (`omega ~ 0.3`), rebuild the
  regular triangulation of `p`'s star at each flip event, and accept the first
  weight where no incident tet has `sigma <= sigma0` — subject to: all new tets
  exact-positive, tracked surface untouched, min dihedral not worsened outside
  the star. Atomic rollback on failure. Final mesh stores unweighted vertices
  (the weight only selects connectivity, as in exudation).
- **Target:** FSL sequence — the 61 unflippable wedge slivers on dual_torus,
  the interior subset first.
- **Acceptance signal:** FSL count strictly below 61 with zero surface-face
  hash changes and no regression in the global quality histogram.
- **Risk:** the 61 wedges may be boundary-pinned (the paper itself shows the
  boundary is where exudation fails), in which case interior-only pumping hits
  none of them; local regular triangulation of a star may disagree with a
  global one — must validate the cavity is star-shaped w.r.t. `p`.

#### TET-WDEL-2 - Forbidden-interval sliver classifier (diagnostic only)

- **Mechanism:** implement the closed-form interval test from Theorem 7.6's
  proof: for sliver `pqrs`, `H(P) = H(0) - P^2/(2D)` with `D` = distance of `p`
  from plane `qrs`; compute per vertex the union of forbidden subintervals over
  its incident slivers and report whether a sliver-free weight exists in
  `[0, omega^2 N(p)^2]`. Classify each residual sliver as PUMPABLE vs LOCKED
  (no vertex has a free subinterval, or all vertices are surface-pinned).
- **Target:** turns FSL-61 and the CYLSKEW near-wall population from anecdotes
  into a measured taxonomy; routes LOCKED cases to collapse/split fallback and
  PUMPABLE cases to TET-WDEL-1.
- **Acceptance signal:** classifier runs on dual_torus and CYLSKEW outputs and
  its PUMPABLE predictions agree with actual TET-WDEL-1 outcomes >= 90%.
- **Risk:** low (read-only); main risk is the formula assuming Delaunay-like
  stars — on a non-Delaunay fTetWild mesh the interval is a heuristic, so the
  card must report prediction accuracy, not assume it.

#### TET-WDEL-3 - Clearance-triggered near-wall refinement (Rule-4 transplant)

- **Mechanism:** adapt Rule 4's *idea* (simulate the worst-case repair
  perturbation before attempting repair): for a near-wall sliver vertex `v`,
  compute the clearance ball radius `omega * dist(v, surface)`; if the repair
  that TET-WDEL-1 / smoothing would need exceeds this clearance, do not perturb
  toward the wall — instead insert one interior Steiner point at the sliver's
  orthocenter/circumcenter projected to the interior, then rerun local ops.
- **Target:** CYLSKEW sequence — near-wall skew where local ops currently
  thrash against the frozen surface.
- **Acceptance signal:** CYLSKEW p99 skew improves with bounded point-count
  growth (< 2% extra vertices) and exact surface preservation.
- **Risk:** medium — point insertion near walls can cascade (the paper controls
  this with the full insertion-radius machinery we will not have); must be
  budget-capped per region with rollback.

## References worth snowballing

1. Li & Teng 2001, *Generating well-shaped Delaunay meshes in 3D* (SODA) — the
   randomized boundary-safe alternative; its point-placement near sliver
   circumcenters is closer to what an insertion-based engine can adopt.
2. Edelsbrunner & Guoy 2001, *An experimental study of sliver exudation* (IMR)
   — the only empirical data on pumping effectiveness; quantifies the
   near-boundary survivor population that motivates this whole paper.
3. Edelsbrunner, Li, Miller, et al. 2000, *Smoothing cleans up slivers* (STOC)
   — perturbation instead of weights; yields an *unweighted* sliver-free DT,
   possibly friendlier to downstream tooling.
4. Talmor 1997 (CMU thesis), *Well-Spaced Points for Numerical Methods* — the
   ratio-property lemmas (6.2-6.4 here) reused by every paper in this line.
5. Mitchell & Vavasis 2000, *Quality mesh generation in higher dimensions*
   (SIAM J. Comput.) — source of the size-optimality proof technique
   (Theorem 7.12).
