# Shewchuk - Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates

## Bibliography and access

- Jonathan Richard Shewchuk.
- *Discrete & Computational Geometry*, 18(3), 305-363, October 1997.
  DOI: `10.1007/PL00009321`.
- Read from the author's open-access report form CMU-CS-96-140R (October 1,
  1997), which the author states is the DCG article; downloaded from
  Shewchuk's Berkeley publication page (`robustr.pdf`, listed as "PDF (556k,
  55 pages)" for the DCG 18(3):305-363 entry), linked from the canonical
  access path recorded in `citation_snowball_batch2.md`
  (https://www.cs.cmu.edu/~quake/robust.html).
- Local copy: `docs/references/papers/source/pdf/38_shewchuk_1997_robust_predicates.pdf`.
  SHA-256: `5f047fd41666e53f6015497f68e42152e3a9d8d04556ab27f8b6fc92c74117d7`
  (556,447 bytes, 59 PDF pages = cover + abstract + 55 report pages).
- Reference C code `predicates.c` is public domain, linked from the same page;
  already vendored in this repository at `core/utils/_shewchuk/predicates.c`.
- Review status: `FULL_READ` on 2026-07-23. All 59 PDF pages were
  text-extracted and read. Honest accounting: the extraction garbled inline
  math glyphs (the PDF embeds PS-derived fonts), so the correctness proofs of
  Sections 2.2-2.7 (Lemmata 1-5, Theorems 6-24) and Appendices A-B were read
  at section level - every theorem statement, algorithm pseudocode, and claim
  was read, but the formula-by-formula proof algebra was followed structurally
  rather than symbol-exactly. Number-critical pages were additionally rendered
  at 2.2x and visually verified: page 3 (expansion definitions, exponent-range
  guarantee), page 41 (Table 1, ORIENT2D error bounds and their derivation),
  page 44 (Table 3, ORIENT3D bounds; Table 4 timings), page 45 (Table 5,
  INCIRCLE bounds; Table 6 timings), page 43 (Figure 22, ORIENT3D adaptive
  dataflow). All error-bound coefficients quoted below are from those renders,
  not from memory or from `predicates.c`.

## Problem and contract

Geometric algorithms driven by sign-of-determinant tests (orientation,
incircle) hang, crash, or emit invalid output when hardware floating-point
returns a wrong sign near degeneracy. The paper's own motivating failure is a
Delaunay divide-and-conquer merge in which orientation tests placed a point
between two lines while an inconsistent INCIRCLE result claimed it inside a
circumcircle - a *mutually contradictory* test set, which is what actually
kills combinatorial algorithms (Section 4.1's key lesson: internal consistency
may be required even when the user does not need exact output).

The contract offered: four predicates - ORIENT2D, ORIENT3D, INCIRCLE,
INSPHERE - that return the exact sign of the corresponding determinant for
**arbitrary IEEE 754 single or double precision floating-point inputs** (not
just bounded integers), with running time that adapts to the conditioning of
the input. Hardware assumptions: radix-2 floating-point with exact rounding
(round-to-nearest), round-to-even tiebreaking for the fast summation path, and
no overflow/underflow - the four predicates neither overflow nor underflow if
input exponents lie in `[-142, 201]` in double precision (verified on rendered
page 3). Exponent range extension is explicitly left unsolved.

Scope boundary stated by the author: exact arithmetic robustifies algorithms
with geometric input and *purely combinatorial output* (hulls, triangulations).
Algorithms that construct new geometric objects (intersection points,
successive constructions) escalate in bit complexity and may need rational or
symbolic machinery (LEDA-style) - exact sign evaluation alone is not a panacea.

## Arithmetic core: expansions and primitives

An arbitrary-precision value is a **multiple-component expansion**
`x = x_n + ... + x_2 + x_1`, each component an ordinary p-bit float, sorted by
increasing magnitude, and **nonoverlapping** (formally: x and y nonoverlap if
there are integers r, s with `x = r 2^s` and `|y| < 2^s`, or vice versa). Sign
of an expansion = sign of its largest component; crude approximation = largest
component. Two stronger properties matter: **nonadjacent** (no two components
overlap even after doubling one of them) and the intermediate **strongly
nonoverlapping** (nonoverlapping; no component adjacent to two others; any
adjacent pair are both powers of two). The central design difference from
multiple-digit libraries (MPFUN): roundoff is *allowed to happen* and then
recovered exactly after the fact, and no normalization to fixed digit
positions is enforced - which is why conversion in/out is free (any double is
a length-1 expansion) and small-precision work is fast.

Primitives (all proved exact under the stated hardware model; `⊕ ⊖ ⊗` denote
rounded hardware ops):

- **FAST-TWO-SUM(a, b)**, Dekker, requires `|a| >= |b|`, 3 flops:
  `x = a ⊕ b; b_virtual = x ⊖ a; y = b ⊖ b_virtual; return (x, y)` with
  `a + b = x + y` exactly, x, y nonoverlapping, `y` the roundoff of `x`.
- **TWO-SUM(a, b)**, Knuth, no magnitude precondition, 6 flops branch-free:
  `x = a ⊕ b; b_v = x ⊖ a; a_v = x ⊖ b_v; b_r = b ⊖ b_v; a_r = a ⊖ a_v;
  y = a_r ⊕ b_r`. Empirically faster than a compare + FAST-TWO-SUM on
  pipelined CPUs because it avoids a branch (the paper measures both ways and
  warns the winner is machine/compiler dependent).
- **SPLIT(a, s)**, Dekker/Veltkamp: `c = (2^s + 1) ⊗ a; a_big = c ⊖ a;
  a_hi = c ⊖ a_big; a_lo = a ⊖ a_hi` - splits a p-bit value into a
  (p-s)-bit high part and an (s-1)-bit low part; the sign bit of `a_lo` is
  what lets 53 (odd) split into two 26-bit halves.
- **TWO-PRODUCT(a, b)**, 17 flops: `x = a ⊗ b`; SPLIT both operands at
  `s = ceil(p/2)`; peel off the three cross products with exact subtractions;
  the tail is `y = (a_lo ⊗ b_lo) ⊖ err3`, giving `a b = x + y` exactly.

Expansion-level algorithms (the paper's key new theorems are 13, 19, 24):

- **GROW-EXPANSION** (Thm 10): expansion + one component via a TWO-SUM chain.
- **EXPANSION-SUM** (Thm 12): m+n components in O(mn); preserves
  nonoverlapping *and* nonadjacent; fully unrollable (no conditionals), so it
  wins for small fixed-size sums and is used inside the predicates.
- **FAST-EXPANSION-SUM** (Thm 13): merge both inputs by magnitude, then one
  TWO-SUM per component - O(m+n), 6 flops/component plus merge comparisons.
  Preserves only the strongly nonoverlapping invariant, and its proof
  **requires round-to-even**; Appendix B constructs an explicit failure when
  round-toward-zero and round-to-even results are mixed. Counterexamples show
  it preserves neither plain nonoverlapping nor nonadjacency.
- **LINEAR-EXPANSION-SUM** (Thm 24, Appendix A): 9 flops/component, tiebreak-
  rule independent; the stated substitute on hardware without round-to-even.
- **SCALE-EXPANSION** (Thm 19): expansion times one float; TWO-PRODUCT per
  component interleaved with TWO-SUM/FAST-TWO-SUM; output nonoverlapping,
  strongly-nonoverlapping-preserving (Cor 22), so it composes with
  FAST-EXPANSION-SUM.
- **COMPRESS** (Thm 23): two sweeps (largest-to-smallest, then back) so the
  largest component approximates the whole expansion to `< ulp(largest)`; the
  cheap **APPROXIMATE** variant (sum smallest-to-largest) errs `< 1 ulp` and
  is what the predicates use to build stage C.
- Zero elimination in all array-based routines is emphasized as almost always
  profitable; in practice exact ORIENT2D expansions run 2-6 components, not
  the worst-case 16.

Distillation (summing k floats: balanced tree of expansion sums), expansion
comparison (subtract and take sign), and iterative division are sketched in
Section 2.8; division is exact only to requested precision, not closed form.

## Adaptivity mechanism (stages A/B/C/D)

Any +/-/x expression is expanded symbolically by writing each bottom-level
operation as `approximate + roundoff` (`x_i + y_i` with `|y_i| <= eps |x_i|`,
`eps = 2^-p`, i.e. 2^-53 in double). Expanding the whole expression as a
polynomial in the roundoff variables groups terms by how many roundoff factors
they carry: `T_0 + T_1 + T_2 + ...` where `T_k` has magnitude `O(eps^k)`.
Successive approximations gain one epsilon order per stage, and each stage
*reuses* the exact intermediate results of the previous one - work is refined,
never discarded (with the exception of the cheap correctional terms). The
recommended variant (used in all four predicates) computes at each stage the
exact partial sum plus a floating-point *correctional term* for the next order
rather than lazily tracking every roundoff leaf, which the paper found faster
than both the naive ladder and the maximally lazy ladder.

Concretely in ORIENT2D (Figure 21, Table 1 - coefficients verified from the
rendered page; `x_5, x_6` are the two cross-product terms of the translated
determinant, `detsum = |x_5| ⊕ |x_6|`):

- **Stage A**: plain double evaluation of the translated determinant plus a
  *runtime* error bound; sign certified iff `|A| >= (3eps + 16eps^2) ⊗
  detsum`. This stage is exactly a Fortune-Van-Wyk-style floating-point
  filter, and in applications it answers the overwhelming majority of calls.
- **Stage B**: the O(eps)-accurate 4-component expansion that is *exact* when
  the initial coordinate translations `(a_x - c_x)` etc. incur no roundoff.
  ORIENT2D explicitly tests whether the translations were exact (Sterbenz
  Lemma 5: subtraction of values within a factor of two is exact) - the
  common case in real triangulations, illustrated by the shaded-triangle
  Figure 20. Bound for the compressed approximation B':
  `(2eps + 12eps^2) ⊗ detsum`.
- **Stage C**: B' plus a floating-point correctional term capturing the
  translation roundoff; certified iff
  `|C| >= (3eps + 8eps^2) ⊗ |B'| ⊕ (9eps^2 + 64eps^3) ⊗ detsum`.
- **Stage D**: the exact determinant (<= 16 components for ORIENT2D, <= 192
  for ORIENT3D). No intermediate stage between C and D: empirically, a
  determinant that survives to C without certification is nearly always
  exactly zero, so further approximation stages would be wasted.

ORIENT3D bounds (Table 3): A `(7eps + 56eps^2) ⊗ (alpha_a ⊕ alpha_b ⊕
alpha_c)`, B' `(3eps + 28eps^2) ⊗ (...)`, C `(3eps + 8eps^2) ⊗ |B'| ⊕
(26eps^2 + 288eps^3) ⊗ (...)`, where the alphas are per-cofactor permanents of
absolute values of the translated coordinates. INCIRCLE (Table 5): A
`(10eps + 96eps^2)`, B' `(4eps + 48eps^2)`, C `(3eps + 8eps^2) ⊗ |B'| ⊕
(44eps^2 + 576eps^3)`, same permanent structure with squared terms. All
coefficients are deliberately rounded up to p-bit-representable values and
computed once at initialization; the derivation multiplies the true bound by
`(1 + eps)^2` to absorb the roundoff of evaluating the bound itself. A
pleasing consequence of the translated form: the bounds vanish when all points
share an x- or y-coordinate (or a plane coordinate in 3D), so axis-aligned
degenerate inputs are certified by stage A alone.

**Why the common case stays at float speed:** stage A costs one hardware
determinant plus a few absolute values and one comparison (measured 0.28 us vs
0.15 us for the raw float test in ORIENT2D, i.e. roughly 2x raw float, and
5-30x cheaper than any exact path); stages B-D are entered only when the
runtime bound - which tracks the *relative* coordinates, hence is vastly
tighter than any static bound - cannot certify the sign. In the 2D Delaunay
benchmark (1M uniform random points), 9,497,314 ORIENT2D calls ended at A,
121,081 at B, 118 at C, 3 at D; robust vs approximate total program time was
61.7 s vs 57.3 s (~8% overhead; up to ~30% on adversarial inputs). In 3D the
overhead is larger (~35% random; 11x on cospherical inputs) - but the
approximate version *failed to terminate* on a tilted-grid input because
roundoff corrupted the mesh, the paper's strongest practical argument.

## Predicate constructions

All four predicates evaluate sign of a determinant; only the sign matters.

- ORIENT2D(a,b,c): 2x2 determinant of translated differences (positive = ccw).
- ORIENT3D(a,b,c,d): 3x3 determinant of rows `(a - d), (b - d), (c - d)`
  (positive = d below the ccw-oriented plane abc; left-hand rule stated).
- INCIRCLE(a,b,c,d): 3x3 determinant with rows `(a_x-d_x, a_y-d_y,
  (a_x-d_x)^2 + (a_y-d_y)^2)` etc.; positive = d inside the oriented circle.
- INSPHERE(a,b,c,d,e): the analogous 4x4 translated determinant; positive = e
  inside the oriented sphere. Zero iff cospherical.

Two formulation choices are analyzed: the untranslated (n+1)x(n+1) determinant
(Expressions 6/8) versus the translated nxn form (Expressions 7/9). Translated
forms cost ~25-50% more in the exact tail but have errors driven by *relative*
coordinates, which makes stage-A/B/C bounds far tighter; translation is often
exact (Lemma 5), which stage B exploits. The paper picks the translated form
for all adaptive predicates. Determinants are evaluated by dynamic-programming
cofactor expansion (all 2x2 minors of the first two columns, then 3x3, ...),
the cheapest route for <= 5x5; the technique is stated not to scale to large
matrices (Clarkson's approach recommended beyond ~10x10).

Adaptivity is not sign-only: Section 6 sketches an adaptive circumcenter
computation with relative error <= 1% by running ORIENT2D-style stages until
the *relative* error bound of numerator and denominator is met - directly
relevant wherever AutoTessell needs certified-accuracy constructions (e.g.,
Steiner point placement) rather than certified signs.

Timings (DEC Alpha 3000/700, Tables 2/4/6/7): exact ORIENT2D 6.6-8.4 us vs
MPFUN 92.9 us (~13x); exact ORIENT3D ~8x over MPFUN; INSPHERE exact 324-480
us. LN-generated integer predicates are ~2-4x faster in the exact tail but
carry a much larger static error bound and only two adaptive stages, so the
four-stage floating-point predicates win in three of four whole-application
comparisons.

## Portability caveats (Section 5, plus what changed since 1997)

Stated by the paper:

1. **Extended-precision registers (x87)**: 80-bit internal arithmetic breaks
   the roundoff-recovery identities. `volatile` forcing is slow and still
   suffers **double rounding** (extended then double), whose error may not be
   representable in p bits (Priest). The recommended fix is setting the FPU
   control word to round to double precision - compiler/OS specific.
2. **Compiler optimization**: any optimizer that "simplifies"
   `b_virtual = x - a` to `b` under real-number algebra silently destroys the
   algorithms. Correct floating-point language semantics are mandatory.
3. **Tiebreaking**: FAST-EXPANSION-SUM requires round-to-even (IEEE default);
   on round-toward-zero hardware substitute LINEAR-EXPANSION-SUM. The paper
   conjectures (unproven) the predicates work under any tiebreak rule via a
   "weakly nonoverlapping" property.
4. **Exponent range**: no overflow/underflow handling; double-precision inputs
   must keep exponents within `[-142, 201]` for the four predicates.
   Extremely small inputs (denormal-adjacent) are outside the contract.

Modern (2026) reassessment for a C++23 native kernel - our analysis, not the
paper's: x86-64 SSE2 and AArch64 both round directly to double, so caveat 1 is
dead on mainstream targets (it survives only on 32-bit x87 builds). The live
hazards today are (a) **FMA contraction**: a compiler contracting `a*b - x`
into `fma(a, b, -x)` changes TWO-PRODUCT's tail; GCC/Clang default
`-ffp-contract=fast` on many targets, so predicate translation units must pin
`-ffp-contract=off` (or `#pragma STDC FP_CONTRACT OFF`) and must never be
compiled with `-ffast-math`/`-funsafe-math-optimizations`; conversely, on
hardware guaranteed to have FMA, TWO-PRODUCT can be *replaced* by the cheaper
exact `y = fma(a, b, -x)` (2 flops vs 17) - a post-1997 improvement the paper
predates; (b) nondefault rounding modes set by other code (caveat 3
generalizes: the expansions assume round-to-nearest-even globally); (c)
`long double` is platform-inconsistent (80-bit x86, 128-bit or plain double on
ARM), so no stage may rely on it.

## Contract versus indirect predicates (Attene 2020 - sibling note)

Shewchuk's contract, stated precisely: the predicates take **explicitly
represented p-bit floating-point points** and return the exact sign of a
polynomial in those inputs. Nothing is guaranteed about points that exist only
as results of constructions (an intersection point, a circumcenter): to use
these predicates on a constructed point one must first round it to doubles,
and the predicate then answers exactly about the *rounded* point - the
original robustness question re-enters through that rounding. Section 4.1
acknowledges this openly (line intersection needs rational arithmetic; bit
complexity of chained constructions escalates; LEDA-style symbolic reals are
the escape hatch). The indirect-predicate line (Attene 2020, screened in batch
2 section B) exists precisely to close this gap by evaluating predicates whose
arguments are implicit constructions; the comparison itself belongs in that
note. What must be preserved from Shewchuk regardless: the expansion
primitives above are the arithmetic substrate both approaches share.

## Limitations and claim boundary

- Sign-exactness is conditional on the hardware/compiler contract of Section 5;
  none of it is verifiable from inside the algorithm at runtime. A production
  kernel needs a startup self-check (the vendored `exactinit()` computes
  epsilon/splitter but does not verify exact rounding or contraction).
- The exponent-range precondition `[-142, 201]` is not checked at runtime by
  the reference code; inputs outside it silently void the guarantee.
- FAST-EXPANSION-SUM's correctness proof leans on round-to-even; the
  any-tiebreak claim is an explicit conjecture, not a theorem.
- Adaptivity does not scale to large determinants (polynomial term explosion);
  fine for the <= 5x5 predicates used in remeshing, irrelevant beyond.
- INSPHERE stage D is computed from scratch rather than incrementally
  ("programmer laziness") - the reference implementation is not uniformly
  optimal; C is usually sufficient in practice.
- Static bounds tables cover double precision; single-precision inputs are
  accepted (converted) but the bound constants are precision-specific.
- Exact arithmetic guarantees consistent *answers*, not meaningful *inputs*:
  degeneracy handling (exact zeros) still needs a policy layer (symbolic
  perturbation is out of scope of this paper).

## AutoTessell code mapping

- `core/utils/_shewchuk/predicates.c` - the paper's public-domain reference
  code, already vendored; `core/utils/_shewchuk/__init__.py` compiles it
  on first import with `cc -O2 -fPIC -shared` and exposes only
  `orient3d`/`insphere` via ctypes. Two gaps against Section 5: the build
  line pins no `-ffp-contract=off` (safe on plain SSE2 x86-64, *unsafe* on
  AArch64 or `-march=native` FMA targets), and failure degrades silently to
  `None`. `orient2d`/`incircle` are compiled but not exported.
- `core/utils/predicates_staged.py` - a Python 3-stage filter that cites this
  paper. Its stage-1 bound (`7 * 2^-53 * max(prod of abs-coordinate sums, 1.0)`)
  is *not* the paper's certified bound: the paper's stage-A coefficient is
  `(3eps + 16eps^2)` (2D) / `(7eps + 56eps^2)` (3D) times the *permanent of
  the translated coordinates*, and the `max(..., 1.0)` floor makes the filter
  needlessly reject small-coordinate inputs into slower stages. Its stage 2
  (`np.float128`) is platform-dependent (plain double on some ARM builds) and
  its stage-2 bound (`bound * 1e-4`) is heuristic, not certified. The final
  Fraction stage is exact, so correctness holds, but the filter economics are
  far from the paper's.
- For the planned C++23 native tri kernels, the decision points are: adopt
  the four reference predicates as the transactional gate layer; add
  `orient2d` export; pin contraction/fast-math flags in the build; optionally
  modernize TWO-PRODUCT with `std::fma`; and reuse the runtime-permanent
  stage-A bound pattern for any new custom predicate rather than static
  bounds.

## Applicability to native-tri cards

This paper is the predicate substrate under every transactional gate in the
tri plan; it does not itself define any mesh operation.

- `TRI-COLLAPSE-SAFE1` (borouchaki2005 note): the mandatory orientation /
  fold-over / positive-area guards are ORIENT2D (in local parameterization)
  and ORIENT3D (tet sign against a reference normal or offset point); exact
  sign is what makes "strictly positive-area, consistently oriented" a
  checkable invariant rather than an epsilon test.
- `TRI-ENV-ACCUM1` / `TRI-ENV-BIDIR1`: the "exact or interval-conservative
  audit" both cards require can be built as ORIENT3D-style adaptive
  expressions; the Wang 2020 fast-envelope gate (`TRI-ERROR-GATE1` upgrade
  path, batch 2 section B) is itself implemented on filtered exact predicates
  of this family.
- `TRI-FEATURE-CURVE1`: side-of-plane and cone-membership tests at feature
  junctions reduce to orientation signs when they must be crisp.
- `TRI-RELAX-DETERMINISTIC1`: byte-identical replay across runs and platforms
  is only achievable if every geometric branch decision is exact; filtered
  predicates make determinism a compile-flag discipline instead of a tolerance
  discipline.
- INCIRCLE/INSPHERE are needed only if a Delaunay legalization pass (edge
  flips toward local Delaunay) is adopted in the surface engine or its
  parameter-space operations; orientation alone suffices for the currently
  planned fold-over and envelope gates.

## Recommendation: vendor, do not port

Vendor the existing public-domain `predicates.c` (already in-tree) as the
canonical layer and wrap it for C++23; do not re-derive the expansions by
hand. The correctness proofs are long, the tiebreak/strongly-nonoverlapping
subtleties are easy to violate silently (Appendix B), and the reference code
embodies exactly the proven algorithms. Native effort is better spent on (a)
build hygiene (`-ffp-contract=off`, no fast-math, startup self-test), (b) an
FMA TWO-PRODUCT variant behind a feature test, (c) batch/SIMD-friendly stage-A
filtering, and (d) any *new* predicates beyond the four (e.g., envelope
distance signs), for which Levy's PCK (batch 2) is the generator route.

## High-value references from this paper

- Priest (1991/1992), *Algorithms for Arbitrary Precision Floating Point
  Arithmetic* + thesis: the general-radix foundation these algorithms
  specialize and accelerate; the double-rounding analysis lives here.
- Dekker (1971), *A Floating-Point Technique for Extending the Available
  Precision*: FAST-TWO-SUM, SPLIT, and the Veltkamp product.
- Fortune and Van Wyk (1996), *Static Analysis Yields Efficient Exact Integer
  Arithmetic for Computational Geometry*: the LN expression compiler and the
  floating-point-filter idea stage A generalizes.
- Fortune (1989), *Stable Maintenance of Point Set Triangulations in Two
  Dimensions*: the robust/stable/parsimonious taxonomy and the degree bounds
  quoted in Section 4.1.
- Goldberg (1991), *What Every Computer Scientist Should Know About
  Floating-Point Arithmetic*: the IEEE 754 background contract (formats,
  exact rounding) the whole paper assumes.
