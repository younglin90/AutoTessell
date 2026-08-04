# Brochu and Bridson - Robust Topological Operations for Dynamic Explicit Surfaces (El Topo)

## Bibliography and access

- Tyson Brochu and Robert Bridson, University of British Columbia.
- *SIAM Journal on Scientific Computing*, 31(4), 2472-2493, 2009.
- DOI: `10.1137/080737617`.
- Local full text (author copy, UBC):
  `docs/references/papers/source/pdf/40_brochu_2009_eltopo.pdf`
  (SHA-256 `f833318e8ec9af6e6e19bd3c0429f5a413bf03b1d6e79e814418f4fabacc387f`,
  downloaded from `https://www.cs.ubc.ca/~rbridson/docs/brochu-sisc2009-eltopo.pdf`).
- Review status: `FULL_READ` on 2026-07-23. Pages 24/24 of the author PDF were
  text-extracted and read: abstract and introduction (pp. 1-3), method
  (pp. 3-14), numerical examples and performance (pp. 14-22), conclusions and
  references (pp. 22-24). Figures were interpreted from captions and inline
  text, not visually rendered.
- Snowball placement: `citation_snowball_batch2.md` section B, P0 — "the
  clearest published precedent for AutoTessell's per-operation guarded-commit
  design." Public-domain C++ implementation (El Topo) released by the authors.

## Problem and contract

Track a dynamic explicit surface — a consistently oriented triangle mesh
`q(t) = (x(t), T(t))` moving under a user-supplied velocity field — through
mesh maintenance and topological change without ever entering a tangled
(self-intersecting) state. The design inversion that defines the paper:
instead of untangling after the fact (Glimm-style grid-based front tracking),
**require that every mesh operation leave the mesh in a consistent,
non-intersecting state**. Every candidate operation is interference-tested
before commit; unsafe non-critical operations are rolled back (deferred to a
later step), and the one unavoidable operation — vertex advection — gets
robust collision *response* that minimally perturbs positions to guarantee
validity.

Input contract: no boundary edges (relaxed in section 4.4 for open surfaces),
no two triangles sharing the same three vertices, non-manifold edges allowed
only with an even number of incident triangles pairable by consistent
orientation — i.e. the mesh must bound an open set. Guarantee: if the current
mesh is intersection-free, the output mesh is intersection-free, even if the
intermediate predicted mesh is not.

## Interference detection machinery (CCD and friends)

Three detector classes, used by different operations:

1. **Static intersection detection**: does the mesh self-intersect *now*?
   Decomposed into edge-vs-triangle penetration tests plus explicit handling
   of degenerate incidences (edge hitting an edge or vertex exactly). A static
   point-in-tetrahedron test is also used (edge flip).
2. **Static proximity detection**: elements closer than a user tolerance
   `eps_p`. Returns closest-point barycentric coordinates `a`, a signed
   combination `abar` giving the distance vector `d = ||sum_i abar_i x_pi||`,
   and a collision normal `n`.
3. **Continuous collision detection (CCD)**: point-triangle and edge-edge
   collisions for vertices moving on *linear* trajectories between the
   configurations at `t_n` and `t_n + dt`. Returns collision time, normal,
   contact barycentric coordinates, and relative displacement.

The CCD is **not** the classic cubic-solver test (Provot/Bridson 2002).
El Topo uses the companion technical report (Brochu and Bridson, UBC
TR-2009-03): augment the spatial coordinates with a time dimension and apply
**numerically robust computational-geometry predicates in space-time**. The
predicates use only multiplication and addition, so a forward error analysis
bounds the maximum accumulated round-off; degenerate configurations are then
identified and handled **without user-tuned error tolerances**. Claimed
property: *no false negatives* (every real collision is detected); false
positives occur only when the accumulated numerical error exceeds the
magnitude of the computed result. This is a conservative filtered
floating-point scheme, not exact arithmetic — see the exactness caveats
below.

## Per-operation transaction model

Each local operation follows a check-before-commit pattern, with three
distinct fallback shapes:

- **Edge split** (edge longer than `alpha`): insert the new vertex at the
  edge *midpoint* — which provably introduces no new intersection — then
  treat the move from midpoint to the butterfly-subdivision position as a
  **pseudo-motion** of the new vertex (with its incident elements) against a
  static mesh, checked by CCD. On collision, *revert to the midpoint*. The
  split therefore always succeeds; only the curvature-preserving offset is
  transactional. Non-manifold edges are not split.
- **Edge flip** (non-Delaunay edge): purely static checks — no existing edge
  may intersect the two new triangles, and no vertex may lie inside the
  tetrahedron formed by the two old plus two new triangles. Additionally
  rejected if the enclosed-volume change exceeds `gamma` (default
  `0.1 xi^3`, tightened for thin surfaces) or if the new edge is not shorter
  by a minimum amount (anti-oscillation). On failure the flip is simply not
  performed. Up to five sweeps over all edges.
- **Edge collapse** (edge shorter than `beta`): both endpoints get the same
  predicted position (butterfly subdivision, or the ridge endpoint when a
  quadric-metric-tensor eigen-decomposition classifies one endpoint as
  on a ridge/crease); pseudo-motion CCD as for splits. On collision, retry
  with the edge midpoint as target; if that also collides, **abandon the
  collapse** — there is no safe fallback position. Rollback here is "do
  nothing and hope a later step succeeds."
- **Null-space smoothing** (Jiao's quadric-tensor Laplacian, moving vertices
  only in the tensor null space so ridges/corners are preserved): treated as
  a global pseudo-trajectory and passed through the *full collision
  resolution pipeline* rather than accept/reject.
- **Merging/zippering** (topology change): edge pairs closer than a
  tolerance, sorted by increasing separation; delete the two triangles
  incident on each edge, creating two 4-edge hole loops, and connect them
  with eight new triangles from a closed-form template. Static intersection
  tests check the new triangles against the mesh and each other, **treating
  degenerate cases as intersections for safety**. On failure, the new
  triangles are discarded and the original triangles are restored — an
  explicit rollback of a compound operation.
- **Separation** is emergent, not an operator: collapses/flips can create
  zero-volume two-triangle "tetrahedra" (deleted) and singular vertices
  (incident triangle fan disconnected), which are duplicated per connected
  component and nudged slightly toward their component centroids so no two
  vertices coincide. Degenerate-tet deletion plus duplicate-and-separate is
  what actually pinches surfaces apart.
- **Vertex advection** (the time step itself) is the only non-rejectable
  operation, resolved in three phases from cloth simulation: (1) proximity
  repulsion impulses sized to restore `eps_p` separation over the step —
  explicitly credited with keeping later floating-point collision handling
  away from degenerate geometry; (2) up to three sweeps of individual
  impulse-based CCD resolution zeroing relative normal velocities; (3) a
  fail-safe **impact zone** solve (Harmon et al.): all still-colliding
  elements are grouped, and one constrained minimization
  `min ||u' - u||^2_M  s.t.  C u' = 0` is solved via the Lagrange system
  `C M^-1 C^T lambda = C u`, iterated with re-detection until no collisions
  remain. Termination is argued because each added constraint reduces the
  dimension of the solution space, "assuming adequately accurate linear
  solves."
- **End-of-step audit**: a full static edge-triangle intersection test over
  the mesh — described as a development-time programming-error check, not a
  required part of the method.

## Guarantees versus gaps

Certified invariant: **the mesh is intersection-free and orientation-
consistent (boundary of an open set) at the end of every step**, given an
intersection-free input mesh — through motion, refinement, coarsening,
smoothing, merging, and separation.

Explicitly *not* certified:

- **Distance to the initial/reference surface.** There is no envelope, no
  accumulated error budget, no correspondence to any reference geometry.
  Per-flip volume change is bounded by `gamma` and experiments report small
  global volume drift (0.18% Enright, 0.92% curl noise), but positional
  drift accumulates silently and unboundedly in principle.
- **Element quality.** Split/flip/collapse/smooth are best-effort; any of
  them may be rejected by the safety gates, so no minimum angle or aspect
  ratio is guaranteed. The authors call quality maintenance orthogonal to
  their contribution.
- **Feature preservation.** Ridge/corner handling (quadric tensor null
  space, collapse-to-ridge-vertex) is heuristic, with no feature-graph
  invariant.
- **Accuracy under collision response.** Each response perturbs positions by
  O(dt); first-order convergence is *posited* (collision events assumed a
  measure-zero set in the limit), observed in the experiments, and honestly
  flagged as potentially carrying a large constant when impact zones grow.
  Topological change itself caps any method at first order (the level set
  comparison shows the same).

Exactness caveats (El Topo predates indirect predicates, Attene 2020):

- The space-time CCD predicates are **filtered floating-point with a forward
  error bound** — conservative (false positives possible) rather than exact;
  there is no exact-arithmetic fallback stage in this paper.
- Tolerance floating-point appears at: the proximity threshold `eps_p`
  (user-set separation goal); the volume-change cap `gamma` and minimum
  flip-improvement threshold (user-tuned); the merge-candidate distance
  tolerance; the "very slight" centroid nudge of duplicated singular
  vertices; and the accuracy assumption on the impact-zone linear solves.
- Degenerate zippering configurations are conservatively treated as
  intersections (safe direction), and non-manifold edges are simply skipped
  by split/collapse — robustness by avoidance, not by exact resolution.

## Cost

Single core, 2.4 GHz Core2 Duo, unoptimized C++. Normal-direction example
per time step: at 23,372-56,390 triangles, mesh improvement 2.08 s, topology
0.85 s, velocity 0.62 s, collision handling 1.41 s — i.e. the safety
machinery (improvement checks + collisions) dominates. Broad phase is a
regular grid of bounding boxes per element type; candidate counts scale
linearly but wall time only near-linearly, named as the main bottleneck and
first future-work item. Whole runs: Enright test 597 s; curl noise up to
381k triangles, 608 min. Explicit-vs-level-set headline: comparable
first-order accuracy, with the explicit method resolving thin sheets far
below grid resolution (curl noise) that a comparably sized grid cannot
represent at all.

## Applicability to AutoTessell and interplay with the bijective shell

What our guarded Botsch loop (`core/preprocessor/native_remesh/isotropic.py`,
`quadric_decimate.py`) should take from El Topo is the **transaction
skeleton**, per operation:

1. a *safe default* whenever one exists (midpoint split), so the operation
   degrades instead of failing;
2. the **pseudo-motion trick**: any relocation — smoothing target, projected
   vertex, subdivision offset — is checked as a CCD trajectory against the
   static rest of the mesh, which covers "tunneling" cases that a static
   post-check of the final position misses;
3. compound-operation rollback with explicit state restoration (zippering);
4. ordering by severity (nearest merge candidates first) and bounded sweeps
   with an improvement threshold to kill oscillation;
5. a cheap end-of-run static intersection audit as a development invariant.

**Interplay verdict vs the bijective-shell static certificate
(`liu2024_bijective_shell_projection.md`, Jiang 2020): complementary in
role, redundant only in one narrow regime.** The two certify disjoint
invariants: El Topo certifies *the evolving surface never self-intersects*
but knows nothing about distance to, or correspondence with, the input;
the shell certifies *containment within epsilon of the input plus a
bijection to it*, and within the certified region self-intersection of the
remeshed surface is excluded for free (a bijective image of an
intersection-free surface cannot self-intersect). Hence:

- For **static native-tri remeshing entirely inside a valid shell** — the
  Phase-1 target — the shell gate *subsumes* El Topo's invariant, and
  per-op CCD would be redundant as a certificate. El Topo survives there as
  the transaction *pattern* (accept/reject slot, safe fallbacks, rollback),
  with shell containment + normal checks as the predicate inside it —
  exactly how Liu et al. themselves structure their in-shell remesher.
- El Topo-style collision machinery remains **necessary where the shell does
  not exist or does not apply**: (a) L1/L2 repair on dirty input — shell
  construction *requires* an intersection-free manifold input, so getting to
  that state is El Topo's territory (its self-intersection-free maintenance
  under motion, merging, and separation is precisely a repair primitive);
  (b) any true surface *motion* — offsetting, boundary-layer inflation
  fronts (`core/layers/native_bl.py`), morphing — where the surface
  legitimately leaves any static shell; (c) topological merge/pinch events,
  which the shell framework forbids outright (input and output must be
  homeomorphic through the bijection).
- Upgrade note: where we do adopt per-op collision checks, the predicate
  layer should be Attene-2020-era indirect/exact predicates rather than
  El Topo's forward-error-filtered space-time tests — same architecture,
  stronger arithmetic, per the batch-2 reading order (this paper, then
  Wang 2020 fast envelope, then Attene 2020).

Concrete card impact: `TRI-COLLAPSE-SAFE1`'s self-intersection guard should
be specified as an El Topo pseudo-motion CCD (both endpoints to target),
not a static final-position test; `TRI-SHELL-DOMAIN1` keeps its shell
predicates but inherits the safe-fallback/rollback transaction shape
documented here.

## High-value references from this paper

- Brochu and Bridson (2009), *Numerically Robust Continuous Collision
  Detection for Dynamic Explicit Surfaces*, UBC TR-2009-03: the space-time
  predicate CCD this paper depends on; must-read companion before any
  native CCD implementation.
- Bridson, Fedkiw, Anderson (2002), *Robust Treatment of Collisions, Contact
  and Friction for Cloth Animation*: origin of the repulsion + impulse +
  fail-safe collision pipeline adopted here.
- Harmon, Vouga, Tamstorf, Grinspun (2008), *Robust Treatment of
  Simultaneous Collisions*: the impact-zone simultaneous solve used as the
  fail-safe.
- Jiao (2007), *Face Offsetting: A Unified Framework for Explicit Moving
  Interfaces*: source of null-space smoothing and the entropy-satisfying
  normal motion used in the experiments.
- Jiao, Colombi, Ni, Hart (2006), *Anisotropic Mesh Adaptation for Evolving
  Triangulated Surfaces*: the anisotropic upgrade path the authors name for
  the same four maintenance operations.
