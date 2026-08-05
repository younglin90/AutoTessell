# Wang, Schneider, Hu, Attene, Panozzo - Exact and Efficient Polyhedral Envelope Containment Check

## Bibliography and access

- Bolun Wang (Beihang University / NYU), Teseo Schneider (NYU), Yixin Hu
  (NYU), Marco Attene (CNR-IMATI), Daniele Panozzo (NYU).
- *ACM Transactions on Graphics*, 39(4), Article 1, 14 pages, SIGGRAPH 2020.
- DOI: `10.1145/3386569.3392426`.
- Open-access PDF: NYU GCL author copy
  `https://cims.nyu.edu/gcl/papers/2020-Fast-Envelope.pdf` (CNR IRIS
  postprint also open). NYU Faculty Digital Archive handle `2451/61221`
  hosts the benchmark data (meshes, QSlim queries, fTetWild queries), not
  the paper.
- Local copy: `docs/references/papers/source/pdf/41_wang_2020_exact_envelope.pdf`,
  SHA-256 `48376b1ae72fd9567b48d170938e361572134628c268361b07dd4e176044752d`.
- Reference implementation: `https://github.com/wangbolun300/fast-envelope`
  (open source; a partial port also entered CGAL 5.3).
- Review status: `FULL_READ` on 2026-07-23. Pages 14/14 text-extracted;
  pages 1, 5, and 9 rendered and visually checked against the extraction
  (title/DOI, prism construction + Proposition 3.1, LPI predicate filters).

## Problem and contract

Given a triangle soup `M` (arbitrary connectivity, possibly intersecting,
possibly shared vertices) and a tolerance `eps`, decide whether a query
triangle `T` lies entirely inside an envelope of `M`. Existing pipelines
(TetWild/fTetWild, Cheng et al. 2019, Hu et al. 2017) answer this with
sampled point-to-surface distances, which is inexact: cost and memory grow
as `eps` shrinks, and — worse — an inexact check breaks the remeshing
invariant "everything currently tracked is inside the envelope." A triangle
accepted by the sampled check can be split and its children then *fail* the
same check, putting the algorithm in an inconsistent state; the practical
symptom is locked triangles and over-refinement (their Figure 3, Figure 22,
Appendix A).

The paper's move: do not test the Euclidean `L2` `eps`-envelope at all.
Instead build a *polyhedral* envelope `PS` that is provably contained in the
`L2` `eps`-envelope, and test containment in `PS` **exactly**. Exactness is
transferred to a slightly smaller, non-Euclidean set; conservativeness with
respect to the true `eps`-offset is preserved.

## Stage 1: envelope construction (per-triangle convex prisms)

One convex polyhedron `P` per input triangle; `PS` is the (never explicitly
realized) Boolean union of these open polyhedra.

For a triangle at offset distance `delta`:

- `T_floor` and `T_ceil`: planes parallel to `T` at distance `delta` above
  and below.
- Three side planes orthogonal to `T`, parallel to each edge at distance
  `delta`.
- For every **acute (or right) vertex**, one extra cutting plane at distance
  `delta` from the vertex, orthogonal to the line from the vertex to the
  triangle barycenter — without it, prism corners can be arbitrarily far
  from a sliver's sharp vertex. Obtuse vertices need no cut.

So 7-8 half-spaces per polyhedron. Each `P` is stored only as its list of
half-spaces, each half-space encoded as a *triplet of points* (never as
plane coefficients, never as an explicit polytope — floating-point vertices
of a realized polytope would not be exactly coplanar and could make it
concave).

**Proposition 3.1:** with `delta = eps / sqrt(3)` every point of `P` is
within `eps` of its triangle (worst case: barycenter degenerating onto an
edge gives in-plane excess `omega = sqrt(2)*delta`, total
`d = sqrt(omega^2 + delta^2) = eps`).

The construction is generic: any set of convex polyhedra works. Variants
demonstrated: per-triangle Minkowski sums with denser sphere approximations
(tighter `L2` approximation, more faces, slower queries — Figure 18), and
**adaptive per-triangle `eps`** (Figures 16-17: tight envelope only near
close features or sharp regions; keeps components from merging without
globally refining).

## Stage 2: containment test

`T` is inside `PS` iff `T \ P_1 \ ... \ P_n = empty`. Carving this out with
rational arithmetic works but coordinates cascade (each subtraction's output
feeds the next), so instead they prove **Theorem 3.2**: `T` is contained in
`PS` iff

- `C1` — each vertex of `T` is inside some `P` (strict interior);
- `C2` — every intersection point of an edge of `T` with a facet of some
  `P` is strictly inside at least one *other* polyhedron;
- `C3` — every point `T ∩ F^l_{Pi} ∩ F^m_{Pj}` (triangle plane against a
  pair of envelope facets) is strictly inside at least one polyhedron
  distinct from `Pi` and `Pj`.

All three reduce to `orient3d` sign evaluations against half-space planes.
`C1` uses the standard exact `orient3d`. `C2`/`C3` would need coordinates of
intersection points, which are not floating-point representable (their
Appendix B: the point `(1/3,1/3,1/3)` already breaks a naive check); instead
the intersection points stay **implicit**:

- `orient3d_LPI` (Line-Plane Intersection): 8 input points — 2 for the
  edge, 3 for the facet plane, 3 for the reference plane. The orientation
  determinant is rewritten, multiplied by `beta^3` (`beta` = denominator of
  the intersection parameter) into a division-free homogeneous polynomial
  `O*`; `sign(O) = sign(beta)-corrected sign(O*)`.
- `orient3d_TPI` (Three-Planes Intersection): 12 input points (three plane
  triplets + reference plane), same homogenization trick.

This is exactly the *indirect predicate* pattern formalized in Attene 2020
(`docs/references/papers/source/pdf/39_attene_2020_indirect_predicates.pdf`) — that paper is the
predicate layer beneath this one. Evaluation ladder per predicate call:

1. semi-static filter (Meyer-Pion FPG-style; explicit epsilon constants and
   `delta_i` max-terms are printed in the paper, Section 4) — plain double
   arithmetic;
2. on filter failure: interval arithmetic (custom self-contained type);
3. on interval ambiguity: floating-point expansions (Joldes et al. 2016) —
   error-free, final answer.

Division-free formulation is what makes steps 1-3 possible at all.

**Acceleration** (~100x combined over the direct Theorem 3.2 loop):
(a) AABB-tree prefilter of candidate polyhedra (Geogram); (b) an all-float
conservative rejection pass — after `C1`, polyhedra whose facets provably do
not intersect `T` are dropped (~30% further reduction), ambiguous cases
conservatively kept, and facet check order re-sorted so likely-deciding
(intersecting) facets are tested first; (c) an incremental *covering*
strategy from the proof of Theorem 3.2 — grow a covering set `C` of
polyhedra over the edges then the interior of `T`, only generating new
implicit intersection points when a point is not already covered by `C`.
Reference scale: naive rational is 100x slower than the predicate version
and 10,000x slower than the accelerated algorithm.

## Exactness contract (what exactly is certified)

- **Exact**: the answer "T is contained in `PS`" has zero error — it is the
  true Boolean answer for the polyhedral set, degenerate configurations
  included. Points *on* the boundary of `PS` count as outside (open
  polyhedra), which is the conservative direction.
- **Conservative w.r.t. the true `eps`-offset**: `PS` is a strict subset of
  the `L2` `eps`-envelope (Proposition 3.1), so `IN` certifies
  `every point of T is within eps of M`. This certificate survives
  arbitrary later subdivision of `T`: sub-triangles of a contained triangle
  are contained by set inclusion — the invariant sampling breaks is
  structurally restored.
- **One-sided**: `OUT` does *not* certify that `T` violates the `eps`
  tolerance. Over large flat regions of `M` the polyhedral envelope is only
  `delta = eps/sqrt(3)` thick, so a triangle between `eps/sqrt(3)` and
  `eps` away is falsely rejected; the envelope-to-`L2`-volume ratio is
  about `1/sqrt(3)` (paper states ratio ~ `sqrt(3)`). Practical effect:
  slightly denser outputs than sampled checks at the same nominal `eps`
  (their QSlim experiment, Figure 20). Recovering tightness costs query
  time via denser polyhedra (Figure 18). There is no exact test of the true
  `L2` envelope in this method — stated as the main limitation.

## Cost

- Setup: average initialization 0.03 s over Thingi10k, up to 1.2 s on large
  models (vs 0.004 s sampling, 0.04 s HB [Tang et al. 2009]); amortized by
  queries. No `eps`-dependence in construction.
- Query: roughly constant in `eps` (~5e-5 s in their single-model sweep,
  Figure 14). Sampling explodes exponentially below `eps ~ 1e-6` and is
  unusable there; HB degrades in both time and memory as `eps` shrinks and
  has high per-query variance (up to 70x slower on its worst query).
  For *large* envelopes sampling is the fastest of the three.
- Memory: `eps`-independent; Thingi10k max 1.44 GB (vs 0.46 GB sampling,
  1.91 GB HB) — overhead is the stored polyhedra plus the AABB tree.
- In fTetWild: query cost flat from `eps = 1e-2` down to `1e-8`
  (Figure 23; sampling exceeds 24 h below `1e-4`-`1e-6`); total meshing
  time changes only through output density. In Cheng et al. 2019 remeshing
  it is on par with Metro sampling at loose `eps` and *faster* at tight
  `eps` because it eliminates the "push the mesh back into the envelope"
  repair pass. Removing fTetWild's multi-stage sampled check (Hu et al.
  2018 Section 3.4) also removed over-refinement: 895,518 -> 50,781 tets on
  their Figure 22 model.

## Integration pattern (where the check is called)

Identical drop-in position to our current sampled gate: inside every local
operation (collapse / split / swap / smooth / vertex relocation), the
proposed post-operation triangles are tested and the operation is rejected
on `OUT`. Their integrations (Cheng et al. 2019, envelope-constrained
QSlim, fTetWild) replaced only the containment call; the host algorithms
were otherwise untouched. QSlim modifications for envelope mode: collapse
only to endpoints, reject envelope-violating collapses, stop when no valid
collapse remains.

## Limitations

- Cannot directly test the true `L2` envelope; conservativeness costs up to
  a `sqrt(3)` effective thinning on flat geometry (densification trades this
  against query time).
- Input is a triangle soup, so open boundaries, non-manifold edges, and
  self-intersections are all *accepted as input* (per-triangle prisms need
  no topology) — but the envelope near an open boundary simply ends at the
  boundary triangle's prism: there is no notion of capping or of signed
  inside/outside. The check certifies proximity, never topology,
  orientation, or intersection-freedom of the query surface.
- Tiny `eps` is the method's strong regime, not a weakness — but `eps`
  below floating-point feature scale still degenerates prisms; the paper
  runs down to `1e-8` x bbox successfully and reports nothing smaller.
- Boundary-of-envelope points count as outside; queries exactly on `∂PS`
  (e.g., untouched input triangles under `delta -> 0`) can be rejected.
- Predicate constants (semi-static filter epsilons) are hand-derived per
  polynomial; porting to a different numeric layout means re-deriving them
  (FPG-style tooling exists — Levy's PCK is the batch-2 route).

## Applicability to AutoTessell

**Primary: tier-2 error gate for the TRI surface engine's error contract**
(`TRI-ERROR-GATE1` upgrade path in
`docs/references/literature/native_tri/citation_snowball_batch2.md`).
Borouchaki 2005's accumulated bound and the sampled audit both leave a
sampled/approximate hole (`TRI-ENV-ACCUM1` / `TRI-ENV-BIDIR1` cards in
`borouchaki2005_envelope.md`); this paper closes the *output-to-input*
direction exactly: an `IN` verdict is a machine-checkable certificate that
a candidate triangle is within `eps`, stable under any later local
operation. Note it does not bound the *input-to-output* direction
(coverage/omission of input geometry) — a two-sided Hausdorff claim still
needs the input-side audit.

**Cross-engine note — native_tet envelope upgrade (flagged, out of tri
scope):** `core/generator/native_tet/envelope.py` implements the fTetWild
envelope as a sampled point-to-surface BVH distance check
(`contains_point`/`contains_points` over `TriangleBVH`) and already cites
this paper in its docstring without implementing it. That is precisely the
inexact check whose invariant-breaking failure mode (locking,
over-refinement, `eps`-dependent cost) this paper documents inside fTetWild
itself. A port of the prism construction + C1/C2/C3 test with LPI/TPI
predicates would replace both the sampled check and any relax-eps healing
heuristics. Requires: exact `orient3d` (Shewchuk/Geogram — see
`docs/references/papers/source/pdf/38_shewchuk_1997_robust_predicates.pdf`), the two custom
predicates with their filter ladder, and expansion arithmetic. This is a
meaningful native-first predicate-layer investment; recommend scheduling it
as its own card rather than folding it into the tri work.

**Vendor-vs-port:** reference implementation `fast-envelope` is open source
(C++, depends on Eigen + Geogram predicates; a variant is in CGAL 5.3).
Under the native-first policy the LPI/TPI predicates and the prism
construction are portable — the predicate polynomials, filter constants,
and the algorithm are fully printed in the paper (Section 4), and the
indirect-predicate machinery is independently specified in Attene 2020,
which we already hold. Vendoring `fast-envelope` under `vendor/dependencies/` as a
reference oracle for differential testing of a native port fits existing
repo practice.

## High-value snowball references (max 5)

1. M. Tang, M. Lee, Y. J. Kim (2009), *Interactive Hausdorff Distance
   Computation for General Polygonal Models* — the HB baseline: true
   two-sided bounds via query-triangle subdivision; the exact-in-principle
   alternative that degrades at tight `eps`.
2. A. Meyer, S. Pion (2008), *FPG: A Code Generator for Fast and Certified
   Geometric Predicates* — the semi-static filter derivation used for every
   epsilon constant in Section 4; needed to re-derive filters for any
   native-port predicate variant.
3. M. Joldes, O. Marty, J.-M. Muller, V. Popescu (2016), *Arithmetic
   Algorithms for Extended Precision Using Floating-Point Expansions* — the
   error-free fallback tier of the filter ladder.
4. M. Campen, L. Kobbelt (2010), *Polygonal Boundary Evaluation of
   Minkowski Sums and Swept Volumes* — the strongest explicit-envelope
   competitor; also the prior TPI-style plane-based exact check the paper
   contrasts (plane-coefficient vs point-triplet representation).
5. H. Si, J. R. Shewchuk (2014), *Incrementally Constructing and Updating
   Constrained Delaunay Tetrahedralizations with Finite-Precision
   Coordinates* — the cited evidence for why realized floating-point
   polytopes go concave, motivating the never-realize-`P` design rule.
