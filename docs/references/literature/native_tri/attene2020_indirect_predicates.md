# Attene - Indirect Predicates for Geometric Constructions

## Bibliography and access

- Marco Attene, CNR-IMATI, Genova.
- *Computer-Aided Design*, 126, article 102856, 2020.
- DOI: `10.1016/j.cad.2020.102856`.
- Local full text: `docs/references/papers/source/pdf/39_attene_2020_indirect_predicates.pdf`
  (author post-print, arXiv:2105.09772v2, 23 Jan 2025, 9 pages; the page
  footer states "Authors post-print - Elsevier").
- SHA-256:
  `8504bb1e1dc029afbec1ae54374008a0b3e47cd3b888c6a3408a6528b721942e`.
- Review status: `FULL_READ` on 2026-07-23. Pages 9/9 text-extracted and
  read in full: abstract, filtering background, algorithm classification,
  the four rewritten predicates, computation models, code generation,
  all five experiment tables, conclusions, references, and Appendix A
  (semi-static filter with caching) were all covered.

## Problem and contract

Filtered exact predicates (Shewchuk 1997, Geogram) guarantee correct signs
only when every predicate argument is an *input* value stored as an exact
double. The moment an algorithm feeds a predicate an *intermediate
construction* — e.g. the intersection point of two segments — the rounded
FP coordinates of that construction poison the predicate regardless of how
robustly the predicate itself is implemented.

The paper classifies algorithms by construction depth:

1. **Class 1** — predicates only on input points (Delaunay, convex hull,
   Voronoi). Solved by classical filtering.
2. **Class 2** — predicates on input points *or* on constructions computed
   directly from input points (constrained Delaunay of intersecting
   segments, Minkowski sums, mesh booleans, exact mesh repair). This is
   the paper's target.
3. **Class 3+** — cascaded constructions built from other constructions.
   Explicitly *not* covered.

The contribution: an **indirect predicate** receives implicit parameters in
unevaluated form (the primitive elements that define the construction, not
its rounded coordinates), folds the construction's polynomial into the
predicate's polynomial, and evaluates the combined expression through the
usual filter cascade. Correctness is exact; cost stays near plain FP.

## Implicit-point representation

An implicit point is a **polynomial fraction with a shared denominator**:
`i = (lambda_x/d, lambda_y/d, lambda_z/d)`, i.e. homogeneous coordinates
`(lambda_x, lambda_y, lambda_z, d)` where every component is a polynomial
in explicit input coordinates. Constructions worked out in the paper:

- **2D line-line intersection (SSI-style):** four explicit points (two per
  line) give `lambda_x, lambda_y, d`; `d = 0` iff the lines are parallel
  or a defining pair is degenerate.
- **3D line-plane intersection (LPI):** five explicit points (two on the
  line `q1,q2`, three on the plane `r,s,t`); `d` is the determinant
  `|q1-q2; s-r; t-r|`, zero iff line parallel to plane, `q1 = q2`, or
  `r,s,t` collinear/coincident.

Predicates rewritten over such points: `orient2d` (numerator degree grows,
denominator `D' = d1^2 d2 d3` in the all-implicit case), `incircle`
(`D' = (d1 d2 d3 d4)^2`), `orient2d3d` (orient2d on the dominant-axis
projection of coplanar 3D points — exactly the projection trick our
surface code needs), and `orient3d` (`D' = d` with one implicit point).
Squared denominators can be dropped outright; otherwise only the *signs*
of the `d`'s are needed (count negatives, flip the numerator sign if odd).
Degeneracy handling is mandatory: every evaluation first certifies that no
`d` is zero (implicit point undefined) before trusting the numerator.

The public `Indirect_Predicates` open-source implementation grew out of
this paper (header-only C++; `genericPoint` with explicit/LPI/TPI
specializations; used by Cherchi et al. 2020 mesh arrangements and the
Wang et al. 2020 fast-envelope check that batch 2 ranks P0). The paper
itself demonstrates only line-line and line-plane; three-plane
intersection (TPI) and any additional predicates in the repo postdate the
paper text and must be verified against the repository, including its
license and compiler-flag requirements, before vendoring.

## Filtering cascade and when each stage fires

Three computation models, tried strictly in order; the predicate returns
at the first model that certifies its result:

1. **FP + semi-static filter.** Compute the `d`'s in doubles; a
   Meyer-Pion-style semi-static filter certifies each sign. If all pass,
   compute the `lambda`'s, evaluate the numerator, filter again. A filter
   failure on a `d` means precision cannot even exclude that the implicit
   point is undefined — abandon the model immediately.
2. **Interval arithmetic (dynamic filter).** CPU rounding mode is switched
   to toward-infinity for the block and restored afterward. Same
   structure: `d` intervals must exclude zero, then the numerator interval
   must exclude zero.
3. **Expansion arithmetic (exact).** Shewchuk-style FP expansions evaluate
   the polynomial exactly. Here a `d` that is *exactly* zero means the
   predicate is undefined (caller must handle); a zero numerator is a
   legitimate degenerate answer.

A purely static filter is discussed but dismissed as too loose without
global input bounds; the practical cascade starts semi-static.

**Appendix A filter detail:** the semi-static threshold is
`delta(1) * B(v1..vn)` where `delta(1)` is a compile-time constant per
expression and `B` is a runtime product of magnitude factors. Attene
replaces the product `b1 b2 ... bk` with `beta^k`, `beta = max(b_i)` — a
deliberate overestimate so that **one cached scalar per implicit point**
bounds all of its `lambda`'s and `d`. Filter constants are produced by an
extended FPG-style code generator that emits all three model
implementations plus the cascade driver from a text formula; hand-writing
these instances is called out as tedious and error-prone.

**Caching policy (Table 3):** caching `lambda`/`d` for the FP and interval
models makes the Delaunay benchmark nearly 2x faster for +23% memory
(7.17 s / 414 MB no-cache vs 3.82 s / 510 MB at 100% implicit points).
Caching expansions for the exact model costs more than it saves
(1168 MB) — do not cache exact values.

**Per-configuration instances:** a naive all-implicit implementation with
`d = 1` for explicit points wrecks the filters. Instead one instance per
explicit/implicit input pattern is generated; symmetry reduces orient2d's
eight patterns to four (EEE, IEE, IIE, III).

## Cost evidence

Delaunay triangulation of 1M points, i7-4770 (times in s, peak MB):

- **Indirect vs direct baseline:** 0% implicit 1.80 s / 269 MB; 100%
  implicit random 3.82 s / 510 MB (2D) and 4.30 s / 655 MB (3D). Overhead
  is at most ~2x time in 2D, ~2.5x in 3D, and degrades *gradually* with
  the fraction of implicit points — sparse implicit points are nearly
  free.
- **Adversarial grids** (Exp 1.3/2.3, forcing heavy exact evaluation):
  27.2 s (2D) and 75.1 s (3D) at 100% implicit — slower, but memory stays
  at non-degenerate levels because exact values are never cached.
- **Vs CGAL:** with all-explicit input CGAL EPICK is faster than the
  genericPoint library (1.16 s vs 1.80 s at 1M) — indirect predicates are
  not a win for class-1 workloads. But once implicit points force CGAL
  onto the lazy-exact kernel, indirect predicates are **3.86x to 11.7x
  faster with up to 3.5x less memory**, and CGAL crashed on the fully
  degenerate 3D grid (Exp 2.3, 100%).
- Background rates quoted: interval arithmetic alone is 3-8x slower than
  plain FP; predicate call counts scale ~4.8M orient2d + 13.3M incircle
  per 1M-point run.

## What this unlocks beyond Shewchuk, and limits

Shewchuk's predicates answer questions about points whose doubles are the
ground truth. Remeshing constantly *creates* points — edge-plane splits,
segment-segment feature intersections, cavity co-refinement — and any
exact decision *involving such a point before it is rounded and committed*
is outside Shewchuk's contract. Indirect predicates close exactly that
gap for constructions expressible as polynomial fractions of input
coordinates.

Stated limits (conclusions section):

- **Polynomial-fraction constructions only.** 3D constrained Delaunay
  Steiner points involve irrational numbers (TetGen) — not representable.
  Anything passing through a `sqrt` (unit normals, distances, curved or
  closest-point-on-curve projections) is out; note a *plane* foot-point
  projection is rational and thus in scope.
- **No cascading.** Implicit points defined from other implicit points
  (class 3) blow up expression degree until filters are useless.
- **Snap rounding is unsolved in 3D.** Exact combinatorics over implicit
  points still must be rounded to doubles for any FP-consuming consumer
  (our polyMesh writer); that rounding can re-introduce self-intersections
  and no practical guaranteed 3D snap-rounding exists. Exactness of the
  decision process does not certify the rounded output mesh.
- Numerical robustness is orthogonal to degeneracy handling (simulation
  of simplicity); both are still needed.

## Applicability to the native-tri gate stack

- **Direct (Shewchuk/staged) predicates suffice** for every check whose
  arguments are committed mesh vertices: link-condition orientation
  tests, fold-over checks after a *committed* relocation, in-sphere tests
  in cavity retriangulation over existing vertices. Keep
  `core/utils/predicates_staged.py` as the route for these.
- **Indirect predicates are the right tool** for decisions *during* an
  operation about a candidate constructed point, before rounding:
  1. Edge-split at a feature-plane or envelope-face crossing — test the
     LPI point against link triangles (orient3d, IEE instance) exactly.
  2. Feature-curve handling — ordering and sidedness of segment-segment
     intersection points along a crease (2D SSI + orient2d3d).
  3. The `TRI-ERROR-GATE1` upgrade path — the Wang et al. 2020 exact
     polyhedral-envelope check is built on precisely this predicate
     layer; adopting fast-envelope implies adopting (or vendoring)
     indirect predicates underneath.
  4. Future boolean/merge features — Cherchi-style arrangements are the
     canonical class-2 consumer.
- **Interplay with projection/relocation:** our smoothing and
  quadric-projection relocations produce coordinates through iterative
  and irrational math — indirect predicates cannot represent those. The
  correct pattern is: compute the relocated position approximately,
  commit it as an explicit double, then re-verify all gates with direct
  predicates. Reserve indirect predicates for the rational constructions
  (splits, plane projections, linear intersections), and never label an
  irrational construction as exact.
- **Snap-once discipline:** if a stage keeps points implicit (e.g. a
  future arrangement/boolean stage), round exactly once at stage exit and
  run a full direct-predicate validity audit on the rounded mesh, because
  of the 3D snap-rounding gap.

## Vendor-vs-port recommendation

**Vendor the reference implementation; do not hand-port.** Rationale:

- The paper itself states that hand-writing filtered instances is
  error-prone and uses a *code generator* to produce the semi-static
  constants (`delta(1)`, e.g. `1.048458195263004e-13` for the sample
  orient2d-IEE instance) — values that cannot be safely re-derived by
  eyeballing. A manual Python port would either omit the filters (losing
  the whole performance argument) or risk silently wrong constants
  (losing exactness).
- The cascade depends on strict IEEE-754 semantics and runtime FP
  rounding-mode switching (toward-infinity for the interval stage) —
  compiler fast-math must be disabled; this is native-extension
  territory, aligned with the existing `core/utils/_shewchuk` C bundle
  and the C++23 toolchain.
- B+C policy fit: treat `Indirect_Predicates` like the Shewchuk C file —
  a small, self-contained, header-only exact-arithmetic core bundled
  under `core/utils/`, wrapped for batch calls like
  `native_tet/_native`. Port-to-Python remains possible later using
  `fractions.Fraction` for the exact stage only (correct but slow), which
  is an acceptable pure-Python fallback tier, mirroring
  `predicates_exact.py`.
- Before bundling: confirm the repository license (copyleft terms would
  force the same isolation discipline used for GPL reference code) and
  the exact compiler-flag requirements; the paper does not state them.

## AutoTessell code mapping

- `core/utils/predicates_staged.py` — already a 3-stage cascade
  (double + error bound → float128 → Fraction/Shewchuk-C), i.e. the
  class-1 direct layer. It has no notion of implicit arguments; every
  caller passes rounded coordinates.
- `core/utils/_shewchuk/` — bundled public-domain Shewchuk C predicates
  (orient3d/insphere). The natural sibling location for a bundled
  indirect-predicates core.
- `core/utils/predicates_exact.py` — Fraction-based exact signs; would
  serve as the slow pure-Python exact stage of any ported indirect
  predicate.
- `core/generator/native_tet/cdt_recovery.py`, `edge_recovery.py`,
  `bsp_insert.py` — edge/face recovery creates segment-face intersection
  Steiner points; today those are rounded before any subsequent orient3d,
  which is exactly the class-2 hole this paper closes. Beware the
  paper's own caveat that full 3D CDT Steiner constructions can be
  irrational — only the rational subset qualifies.
- Native-tri (planned): split-point insertion, feature-graph
  intersection ordering, and the fast-envelope gate are the three
  consumers to design against this layer from day one.

## Falsifiable implementation cards

1. `TRI-IPRED-VENDOR1`: bundle the indirect-predicates core (LPI + SSI
   points; orient2d, orient3d, orient2d3d, incircle) as a native
   extension with batch APIs. Pass only if a differential test of >= 1e7
   random and adversarial (near-parallel, near-degenerate, grid)
   configurations agrees with a Fraction-based oracle on every sign, and
   the FP-stage hit rate on random input exceeds 99%.
2. `TRI-IPRED-SPLITGATE1`: route candidate edge-split points defined by
   line-plane intersection through indirect orient3d for link validity
   before rounding. Pass only if no committed split ever flips a link
   orientation after rounding, measured against the direct-predicate
   re-audit on the rounded mesh.
3. `TRI-IPRED-CACHE1`: implement per-implicit-point caching of
   `lambda`/`d` for FP and interval stages only (single `beta` scalar per
   point, per Appendix A). Accept only if the cached path is >= 1.5x
   faster than uncached on an implicit-heavy benchmark with <= 30%
   memory increase, and exact-stage values are verified uncached.
4. `TRI-IPRED-SNAP-AUDIT1`: any stage that operates on implicit points
   must end with a snap-and-audit barrier: round all implicit points
   once, then re-run self-intersection, orientation, and manifoldness
   checks with direct predicates. Pass only if every downstream consumer
   reads only audited explicit coordinates.
5. `TRI-IPRED-SCOPE1`: maintain an explicit whitelist of constructions
   allowed into indirect predicates (rational only: linear
   intersections, plane foot-points). Reject at API level any point
   whose provenance includes normalization, sqrt, or iterative
   projection. Pass only if the whitelist is enforced by type, not by
   convention.

## High-value references from this paper

- Meyer and Pion (2008), *FPG: A Code Generator for Fast and Certified
  Geometric Predicates*: the semi-static filter generator this paper
  extends; needed to regenerate or verify filter constants.
- Broennimann, Burnikel, Pion (1998), *Interval Arithmetic Yields
  Efficient Dynamic Filters*: the dynamic-filter stage and its 3-8x cost
  figure.
- Joldes, Marty, Muller, Popescu (2016), *Arithmetic Algorithms for
  Extended Precision Using Floating-Point Expansions*: the modern account
  of the expansion arithmetic used in the exact stage.
- Pion and Fabri (2011), *A Generic Lazy Evaluation Scheme for Exact
  Geometric Computations*: the CGAL lazy-exact baseline that indirect
  predicates beat by 3.86-11.7x; defines the alternative design.
- Devillers, Lazard, Lenhart (2018), *3D Snap Rounding*: the unsolved
  output-rounding problem that bounds what exact combinatorics can
  promise our polyMesh writer.
