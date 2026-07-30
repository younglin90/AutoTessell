# QUAD-SIMILARITY-NORMALIZATION-CPP23-1 evidence

Date: 2026-07-31

Promotion target: `L2_TARGET_PASS / RUNTIME_READY`

## Hypothesis and fixed contract

The native Quad preflight and quality selector used absolute `1e-30` geometry
checks and formed products in the input coordinate range.  A well-conditioned
planar patch therefore underflowed to a false zero-area verdict at small scales
and overflowed to a false quality rejection at large scales.

The single mechanism is a local positive similarity normalization.  Each
triangle or quad is scaled twice by exact powers of two: first into a finite
coordinate range, then relative to its first vertex into a finite local range.
Only the normal and dimensionless quality calculations use these temporary
coordinates.  Input/output coordinates, topology, thresholds, candidate order,
greedy policy, provenance, routing, and target-cell behavior are unchanged.
The independent Python oracle implements the same arithmetic contract.

Frozen primary fixture: one planar two-triangle square at scales
`1e-150`, `1e-18`, `1e-16`, `1e-15`, `1e-14`, `1`, `1e14`, and `1e150`.

Predeclared acceptance:

- all eight scales emit exactly one quad and zero remaining triangles;
- native and Python oracle topology and diagnostics are exactly equal;
- three native repeats have identical vertex, triangle, quad, and diagnostic
  signatures;
- source vertices and triangles remain byte-identical;
- degenerate, duplicate, non-manifold, and inconsistently oriented inputs
  remain fail-closed at micro, ordinary, and mega scales;
- warpage, concavity, feature, and protected-wall gates remain unchanged;
- the ordinary `60 x 60` grid preserves frozen output hashes;
- fused public-route median remains at most `0.02116 s`, a 15% cap over the
  frozen `0.018399720 s` baseline;
- GCC 13.3 Release C++23 `-Wall -Wextra -Wpedantic -Werror` builds cleanly;
- `third_party/` remains unchanged.

Rollback conditions were any source mutation, ordinary-scale output or metric
change, topology/provenance mismatch, invalid acceptance, native/oracle
disagreement, nondeterminism, build warning, performance-cap miss, or
`third_party/` edit.

## Research and provenance

- Tinko Bartels, Vissarion Fisikopoulos, and Martin Weiser, *Fast
  floating-point filters for robust predicates*, BIT Numerical Mathematics 63,
  31 (2023), DOI
  [10.1007/s10543-023-00975-x](https://doi.org/10.1007/s10543-023-00975-x).
  The full open-access paper was read.  Its explicit treatment of overflow and
  underflow supports range-safe evaluation; its generated predicate framework
  was not copied or added as a dependency.
- Jonathan Richard Shewchuk, *Adaptive Precision Floating-Point Arithmetic and
  Fast Robust Geometric Predicates*, Discrete & Computational Geometry 18
  (1997), DOI
  [10.1007/PL00009321](https://doi.org/10.1007/PL00009321).  The local archived
  full text `papers/pdf/38_shewchuk_1997_robust_predicates.pdf` and the author's
  public PDF were available.  The paper establishes why range failure can
  invalidate discrete geometric decisions.  No implementation was copied.
- The official [CGAL repository](https://github.com/CGAL/cgal) and exact-kernel
  documentation were reviewed as reference-only.  CGAL has package-specific
  LGPL/GPL/commercial licensing and was not copied, linked, or added.
- Peter M. Schmidt and Leif Kobbelt, *Single Edge Collapse Quad-Dominant Mesh
  Reduction*, ACM Transactions on Graphics (2025), DOI
  [10.1145/3731143](https://doi.org/10.1145/3731143).  The publisher abstract
  was visible, but the full text returned HTTP 403 and no matching DOI or title
  was present in the project PDF archive/manifests.  This inaccessible paper
  supplied no algorithm or code.

The retained implementation is independent first-party C++23/Python.  No code,
generated output, binary, or dependency was imported from these references.

## Frozen baseline

Both the current native extension and extension-absent Python oracle produced:

| Scale class | Scales | Accepted |
| --- | --- | ---: |
| underflow/absolute-threshold failure | `1e-150`, `1e-18`, `1e-16`, `1e-15` | 0/4 |
| ordinary | `1e-14`, `1`, `1e14` | 3/3 |
| overflow quality failure | `1e150` | 0/1 |

Primary baseline: `3/8` accepted.  The micro cases raised
`surface contains a zero-area triangle`; the mega case returned
`no_valid_pair_accepted` after non-finite intermediate norms.

The frozen `60 x 60` grid baseline was:

- fused public-route median: `0.018399720 s`;
- vertices: `3,721`;
- triangles: `7,200`;
- candidate pairs: `10,680`;
- accepted quads: `3,600`.

## Result

Primary result: `3/8 -> 8/8` accepted.

- Every scale emitted one quad and zero triangles.
- Native and Python oracle topology and full diagnostics were exactly equal at
  every scale.
- Three native repeats at every scale had identical SHA-256 signatures and
  diagnostics.
- Output vertices were byte-identical to each scaled input; input vertex and
  triangle arrays were not mutated.
- The 12 scale-adverse invalid-input combinations retained the exact native and
  oracle failure messages for degenerate, duplicate, non-manifold, and
  inconsistent-orientation cases.
- Micro/mega warped, protected-wall, and 90-degree feature fixtures remained
  rejected with exact native/oracle parity.
- The previous `1e300` square overflow-regression fixture now emits one valid
  quad with finite quality instead of conservatively rejecting a
  well-conditioned input.

The ordinary `60 x 60` grid preserved the frozen hashes:

- vertex SHA-256:
  `9b0fdcce659eebe739a726dd443951bb6abedbc7ef364d28f69e65e83403485b`;
- triangle SHA-256:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
- quad SHA-256:
  `7b13aba2846ff2a6e114f3f7250dd2e52b70dac1f83e4e19194537b415316c05`.

Post-change fused public-route median was `0.020220057 s`, a `9.89%`
increase and below the frozen `0.02116 s` cap.  The card changes no mesh target,
boundary-layer, or feature/wall threshold.

## Validation

- fresh GCC 13.3 Release C++23 Werror native-metrics build: pass, zero warnings;
- focused scale/invalid/gate suite: `15 passed`;
- native Quad dominant + fused transaction + scale suite: `76 passed`;
- expanded Quad diagnostics, face-remesh, native-build, and wheel contracts:
  `168 passed`;
- Black and Ruff on changed Python files: pass;
- strict MyPy remains blocked by pre-existing project/import typing errors; no
  new helper-level MyPy error was introduced under `--follow-imports=skip`;
- `git diff --check`: pass;
- `third_party/` diff: empty.

Status: `L2_TARGET_PASS / RUNTIME_READY`.  Full campaign L3 and post-merge
validation remain integration-lane work; this is not a release-ready claim.
