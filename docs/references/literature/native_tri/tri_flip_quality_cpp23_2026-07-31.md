# TRI-FLIP-QUALITY-CPP23-1 evidence

Date: 2026-07-31

Promotion target: `L1_PASS / EXPERIMENTAL_KEEP`

Mechanism: one C++23 batch primitive for the existing local triangle
mean-ratio quality census.  Only the four old/new triangles consulted by a
flip proposal move from scalar NumPy calls to one native call.  Candidate
generation, ordering, link/fold-over/exact-orientation guards, the `1e-12`
improvement threshold, routing, geometry, topology, and target-cell behavior
are unchanged.

## Primary literature

- Patrick M. Knupp, *Algebraic Mesh Quality Metrics*, SIAM Journal on
  Scientific Computing 23(1), 2001, DOI
  [10.1137/S1064827500371499](https://doi.org/10.1137/S1064827500371499).
  The official SIAM record was accessible.  It establishes algebraic shape
  metrics and their relation to condition/mean-ratio measures.  This card does
  not adopt a new metric; it preserves AutoTessell's existing normalized
  triangle mean-ratio formula exactly at the decision level.
- Patrick M. Knupp et al., *The Verdict Geometric Quality Library*, Sandia
  report SAND2007-1751, DOI
  [10.2172/901967](https://doi.org/10.2172/901967).  The official OSTI record
  and report were accessible.  Verdict's relevant engineering result is that
  multiple element metrics can share coordinate calculations in one C++
  evaluation.  The report is design evidence only.

No paper required by this card was inaccessible.

## Active public implementation review

- [sandialabs/verdict](https://github.com/sandialabs/verdict), master head
  `220188cf8707dd79119d0c3658afd2b3612dda5b` from `git ls-remote` on
  2026-07-31.  Its license is a permissive three-clause BSD-style license.
  Repository documentation describes C++ quality functions for 2D/3D
  elements and combined evaluation.  It is a reference only: no Verdict code,
  formula implementation, generated output, dependency, or binary was copied.
- [CGAL](https://github.com/CGAL/cgal) remains a current production geometry
  reference, but its mesh-processing packages have package-specific GPL or
  commercial terms.  No CGAL code or dependency was used.

The retained implementation is independent first-party C++23 and remains
inside the native-core provenance boundary.

## Frozen baseline, acceptance, and rollback

Fixture: `tests/benchmarks/cylinder.stl`, one guarded transaction round,
`smooth=False`, median of five alternating Python/native runs after warmup,
Python 3.12, GCC 13.3 release build.

Predeclared primary acceptance:

- end-to-end speedup at least `1.25x`;
- native median no greater than `0.62 s`;
- exact report sequence, accept/reject decisions, and output vertex/face
  hashes across three runs.

The lower-than-default performance ratio is deliberate: cProfile attributed
`0.399 / 1.300 s` (`30.7%`) to the owned scalar quality primitive, so a `3x`
whole-round target violates this card's Amdahl ceiling.  Secondary acceptance
is at least `10x` for a deterministic 50,000-triangle direct batch.

Rollback conditions: any report/decision/hash difference, source mutation,
invalid or non-finite result, malformed native ABI acceptance, nondeterminism,
build warning, primary threshold miss, or `vendor/dependencies/` change.

Reproduce:

```bash
PYTHONPATH=. AUTOTESSELL_EXT_BUILD_DIR=<release-build> \
python3 tests/stl/bench_native_tri_flip_quality.py --repeats 5

PYTHONPATH=. AUTOTESSELL_EXT_BUILD_DIR=<release-build> \
python3 tests/stl/bench_native_tri_triangle_quality.py \
  --triangles 50000 --repeats 5
```

## Result

- End-to-end Python median: `0.761070473 s`.
- End-to-end native median: `0.539815467 s`.
- End-to-end speedup: `1.40987x`; both primary thresholds pass.
- Reports: `222`; accepted: `204`; Python/native sequence identical.
- Output vertex SHA-256:
  `3339268edf9671568a319d040aa2ea2fdd75d6ba6a7b24958cbf391f4f9df47c`.
- Output face SHA-256:
  `ac78dcf565f5596bab24065072dee990059155498d17e8e589eb2b3fe5cc9d37`.
- Direct Python median: `1.130393828 s` for 50,000 triangles.
- Direct native median: `0.000381299 s`; speedup `2964.59x`.
- Direct maximum absolute floating difference: `4.44e-16`; downstream flip
  decisions and final arrays are exact.
- Three transaction repeats preserve the report sequence and both final
  hashes.  Input vertex and face arrays remain byte-identical.
- Strict native ABI accepts only C-contiguous `float64 (N,3,3)`.  Extension
  absence uses the independent scalar Python oracle.  A loaded extension with
  malformed dtype, shape, layout, range, or non-finite output fails closed.

Validation:

- focused C++ parity/fail-closed/three-run suite: `11 passed`;
- native Tri suites: `66 passed`;
- native Quad and build-contract regression: `127 passed`;
- full native build-evidence and wheel-contract suite: `7 passed`;
- unique tests across the final regression commands: `199 passed`;
- isolated release build completed without compiler warnings;
- `git diff --check` passed.
