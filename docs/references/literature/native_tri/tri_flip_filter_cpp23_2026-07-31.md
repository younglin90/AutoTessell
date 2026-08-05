# TRI-FLIP-FILTER-CPP23-1 evidence

Date: 2026-07-31

Promotion target: `L1_PASS / EXPERIMENTAL_KEEP`

Mechanism: one serial C++23 kernel evaluates every flip candidate against the
same frozen mesh state.  It builds face/edge incidence, valence, and boundary
counts once, then returns a Boolean mask in the supplied edge order.  Python
retains candidate ordering, minimum-edge selection, the actual flip builder,
and all transaction, link, fold-over, exact-orientation, shape, and provenance
gates.  The production default is unchanged: the kernel is used only with the
explicit `AUTO_TESSELL_TRI_FLIP_FILTER_CPP23=1` experimental opt-in.  Missing,
empty, `0`, or any other value uses the scalar Python oracle; extension absence
also falls back to that oracle.

## Research and provenance

- Mario Botsch and Leif Kobbelt, *A Remeshing Approach to Multiresolution
  Modeling*, SGP 2004, DOI
  [10.2312/SGP/SGP04/189-196](https://doi.org/10.2312/SGP/SGP04/189-196).
  The official Eurographics full text was accessible.  It supports guarded
  local edge operations and valence regularization.  This card changes no
  remeshing rule.
- Zhongshi Jiang et al., *The Wild Meshing Toolkit*, ACM TOG 41(6), 2022, DOI
  [10.1145/3550454.3555513](https://doi.org/10.1145/3550454.3555513).
  The paper was accessible.  Its explicit invariants, rollback, and batched
  operation design support separating a candidate filter from the committing
  transaction.  The public
  [wildmeshing-toolkit](https://github.com/wildmeshing/wildmeshing-toolkit)
  repository head reviewed was
  `c8f19c13a0f616299aeab34f4200e5a86d66dfc6` and is MIT.  Its parallel
  execution is not adopted because this route requires exact deterministic
  candidate order.
- [geometry-central](https://github.com/nmwsharp/geometry-central) head
  `019669ddabda05e0f71fa3587cfb3c1dadf19cb8` is MIT.  Dense surface-mesh data
  and local modification structures were reviewed as design references only.
- [CGAL Polygon Mesh Processing 6.2](https://doc.cgal.org/latest/Polygon_mesh_processing/)
  and [MMG](https://github.com/MmgTools/mmg) head
  `8ed2259164fa4c90be6301d247ecb1db7bd61228` were reference-only.  CGAL has
  package-specific GPL/commercial terms; MMG has LGPL/GPL terms.  No source,
  generated output, dependency, or binary was copied.
- MMG's algorithmic paper, C. Dapogny et al., *Three-dimensional adaptive
  domain remeshing, implicit domain meshing, and applications to free and
  moving boundary problems*, JCP 262, 2014, DOI
  [10.1016/j.jcp.2014.01.005](https://doi.org/10.1016/j.jcp.2014.01.005), was
  accessible as bibliographic and abstract evidence.

No DOI required by this card was inaccessible.  The retained code is an
independent first-party implementation.  `vendor/dependencies/` is unchanged.

## Frozen baseline and acceptance

Fixture: `tests/benchmarks/cylinder.stl`, one round, `smooth=False`, Python
3.12, GCC 13.3 C++23 Release build, one BLAS/OpenMP thread, median of seven
runs after warmup.

Before implementation, cProfile attributed the largest remaining Tri Python
cost to `should_flip_edge`: `1,836` frozen-state calls per round.  The
underlying `_build_flip_candidate` ran `1,882` times: `1,836` filter calls plus
`46` real flip transactions.  It allocated one full vertex and face copy per
call, or `3,764` full Python arrays.

Predeclared acceptance, with the baseline attribution correction approved
before final validation:

- direct frozen-state filter speedup at least `3x`;
- public cylinder round speedup at least `1.15x` and median at most `0.47 s`;
- peak RSS no more than `5%` above the scalar route;
- filter candidate copy pairs `1,836 -> 0` and full-array allocations
  `3,672 -> 0`;
- the required `46` actual flip transactions remain unchanged, making the
  whole-round counts `1,882 -> 46` and `3,764 -> 92`;
- edge-by-edge scalar/native parity and exact cube/sphere/cylinder report
  sequence, accepted count, input bytes, output hashes, and three-run
  determinism;
- default/OFF/invalid-value scalar equivalence, strict malformed-ABI failure
  while opted in, and extension-absent fallback.

Rollback: any decision, order, hash, topology, shape, feature, boundary,
provenance, or transaction-gate mismatch; malformed result acceptance;
nondeterminism; invalid element; build warning; primary performance miss; or
`vendor/dependencies/` change.

Complexity for one frozen-state scan changes from repeated full candidate
construction and whole-mesh valence rescans, effectively
`O(E * (F log F + V))` time with `O(V + F)` transient copies per candidate, to
`O(F + E)` expected time and `O(V + F + E)` space.  The native kernel stores
flat incidence/count data once and performs constant-size local valence deltas.

## Result

- Public scalar median: `0.512485236 s`.
- Public native median: `0.307059165 s`; speedup `1.669x`.
- Direct frozen-state median: `0.021045120 s` scalar versus
  `0.000323817 s` native; speedup `64.99x`.
- Scalar peak RSS: `52,224 KiB`; native peak RSS: `44,544 KiB`, a `14.7%`
  reduction.
- Reports: `222`; accepted: `204`; order and decisions exact.
- Vertex SHA-256:
  `3339268edf9671568a319d040aa2ea2fdd75d6ba6a7b24958cbf391f4f9df47c`.
- Face SHA-256:
  `ac78dcf565f5596bab24065072dee990059155498d17e8e589eb2b3fe5cc9d37`.
- Cube, sphere, and cylinder frozen-state masks had zero scalar/native edge
  mismatches.  Full-round signatures and both hashes matched the fallback and
  three native repeats.
- A fixed-seed randomized planar-grid sweep checked `16,450` additional edges
  with zero scalar/native decision mismatches.
- The mask does not mutate input arrays.  An existing-diagonal proposal can
  remain a scalar-identical positive filter result, but the unchanged actual
  flip transaction rejects it at the link gate.  No safety gate moved into or
  out of the filter.

Validation:

- focused parity, fallback, malformed-ABI, allocation, existing-diagonal, and
  default/OFF/invalid-value, and three-run suite: `17 passed`;
- combined native Tri, native Quad, build-evidence, and wheel-contract
  regression: `256 passed`;
- isolated GCC 13.3 `-std=c++23 -O3 -Wall -Wextra -Wpedantic -Werror` Release
  build with `-j1`: zero warnings;
- new benchmark/test files: Black and Ruff pass;
- `git diff --check` and `vendor/dependencies/` diff: pass / zero.

Reproduce:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
AUTO_TESSELL_TRI_FLIP_FILTER_CPP23=1 \
PYTHONPATH=. AUTOTESSELL_EXT_BUILD_DIR=<release-build> \
python3 tests/stl/bench_native_tri_flip_filter.py \
  --mode scalar --repeats 7

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
AUTO_TESSELL_TRI_FLIP_FILTER_CPP23=1 \
PYTHONPATH=. AUTOTESSELL_EXT_BUILD_DIR=<release-build> \
python3 tests/stl/bench_native_tri_flip_filter.py \
  --mode native --repeats 7
```
