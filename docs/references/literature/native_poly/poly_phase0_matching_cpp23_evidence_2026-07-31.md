# POLY-PHASE0-MATCHING-CPP23-1 Evidence

Date: 2026-07-31

Base: `eacd9ba20f05dc699a1443cb2ca039a56145c550`

Scope: report-only Phase-0 face-pairing evaluation. No mesh point, face,
owner, neighbour, boundary, routing, acceptance threshold, target-cell,
boundary-layer, source-geometry, provenance, or `third_party/` change.

## Frozen hypothesis and acceptance

The existing exact subset dynamic program has exponential state count. A
seed-10 sphere dual contains cells with 13 to 37 incident faces, so the
report-only face-pairing metric prevents the otherwise valid mesh checker and
harness from terminating within their product budget.

Primary metric: wall time of `NativeMeshChecker` on the deterministic sphere
`seed_density=10` dual.

- baseline: CPU-active after 180 seconds; timed out after every permanent
  checker kernel had returned
- acceptance: at most 15 seconds, at least 12x faster than the timeout lower
  bound
- correctness: native result matches the exhaustive oracle for every tested
  size from 0 through 14 within relative/absolute `1e-12`
- invariants: all non-pairing checker fields and all five polyMesh hashes are
  identical; three exact repeats are identical
- rollback: any parity failure, order dependence, nontermination, permanent
  field/hash change, runtime above 15 seconds, external-code provenance, or
  `third_party/`/build-contract change

Promotion target: `L1_PASS / CORRECTNESS_KEEP`. The metric remains report-only.

## Bottleneck isolation

The exact seed-10 dual contains 698 cells, 5,737 points, and 7,072 faces. Its
incident-face distribution is minimum 13, median 14, p95 25, maximum 37.
Instrumented checker stages before Phase 0 were:

- face geometry/topology: `0.000169 s`
- combined cell metrics/topology: `0.001294 s`
- oriented-volume audit: `0.000037 s`
- non-orthogonality: `0.000098 s`
- internal skewness: `0.000034 s`
- boundary skewness: `0.000044 s`
- cell volumes: `0.000074 s`
- face concavity/warpage: `1.27448 s`
- face weight/volume ratio: `0.000083 s`
- minimum determinant estimate: `0.000054 s`

The next call was `compute_poly_phase0_metrics`. The recursive
`_minimum_pairing_sum` did not return before 180 seconds. Replacing only that
call at runtime with an O(n) diagnostic placeholder made the complete checker
finish in `2.56881 s`, with `mesh_ok=true` and zero negative volumes. This
isolates the exponential pairing search as the dominant blocker; the
placeholder was never committed and its pairing values were not accepted.

## Exact reduction and implementation

For area vectors `v_i`, the existing objective charges a single vertex
`s_i = |v_i|` or a pair `p_ij = |v_i + v_j|`. The triangle inequality gives
`p_ij <= s_i + s_j`. Starting from the all-single cost, pairing `(i,j)` saves

`w_ij = s_i + s_j - p_ij >= 0`.

Therefore the original minimum is exactly

`sum_i s_i - maximum_weight_matching({w_ij})`.

An odd population receives one dummy vertex with zero saving. A positive
constant added to every complete-graph edge forces a full matching without
changing the ordering among full matchings. The first-party C++23 kernel uses
an Edmonds/Galil primal-dual alternating forest with odd-cycle contraction and
expansion. Runtime is O(V^3); dense edge storage and blossom membership use
O(V^2) memory. The current report contract caps one cell at 256 faces.

Reduced costs use signed 64-bit integers. Savings are normalized onto
`2^50` integer levels, while the returned objective is summed from the original
double-precision savings selected by the matching. For at most 256 faces, the
maximum selection error introduced by quantization is bounded by
`128 / 2^50` times the largest saving, approximately `1.14e-13 * max_saving`.
The observed worst scaled difference over the extended oracle census was
`3.67e-15`.

The same polynomial kernel replaces the pre-existing exponential helper in
the native triangle Phase-0 path. Python keeps the original exhaustive dynamic
program as the optional-extension fallback and small-input oracle.

## Result

The exact sphere checker completed three times in `2.61946`, `2.44775`, and
`2.42832` seconds. Maximum time is `2.61946 s`, at least `68.7x` faster than
the 180-second baseline lower bound and below the 15-second absolute budget.
All three `CheckMeshResult` models were identical. Comparison with the
diagnostic placeholder found zero differences outside the four report-only
pairing fields. The exact residual summary was minimum `0.3917213277568076`,
mean `0.5891820192404242`, p95 `0.6839077376030276`, and maximum
`0.7207268742090998`.

The checker retained `mesh_ok=true`, zero negative volumes, and the frozen
`698 / 5737 / 7072` cell/point/face counts. The five files remained
byte-identical before and after all checker runs:

- `points`: `2e3b1e019bef087c64339de7936e78ab8484267bbab041d84ffa02ce69ff2e31`
- `faces`: `3050040d48e9a144c5de712df6d5b86dbf808c1443f3ff220713d22f992689c5`
- `owner`: `af6ef1e577e70d98e1d8879635518f56b4fdefa43647e7f6c595ec32949b1348`
- `neighbour`: `7445996b56e79b95e9e3d0988524ddebd925fec2cb8cee191b7a7af6405c8ee9`
- `boundary`: `664e998bab2128870add6f3de60761c89a1336343f1faa118461d7af0d617812`

The previously timed-out sphere validity and harness tests now pass together:
`2 passed in 25.89 s`.

Native/exhaustive parity passed 1,500 deterministic cases spanning every size
from 0 through 14, Gaussian, scaled `1e-12` to `1e12`, near-collinear,
antipodal, and rounded tie-heavy families. Dense 37- and 64-vector tests,
equal weights, antipodal duplicates, near ties, and eight permutations per
case terminate deterministically.

## Primary research, GitHub audit, and license boundary

- Jack Edmonds, *Maximum Matching and a Polyhedron with 0,1-Vertices*, 1965,
  DOI `10.6028/JRES.069B.013`: maximum-weight matching polytope and primal-dual
  basis. Official NIST full text was accessible.
- Jack Edmonds, *Paths, Trees, and Flowers*, 1965, DOI
  `10.4153/CJM-1965-045-4`: alternating paths and blossom contraction.
- Zvi Galil, *Efficient Algorithms for Finding Maximum Matching in Graphs*,
  ACM Computing Surveys 18(1), 1986, DOI `10.1145/6462.6502`: O(V^3)
  weighted general matching organization.
- Official Boost Graph documentation confirms the O(V^3) general undirected
  weighted-matching contract and integer reduced-cost formulation. Boost is
  BSL-1.0, permissive and binary-distribution friendly.
- Boost was rejected as a dependency and code source. The installed Boost
  1.83 predates the 2025 replacement: official `boostorg/graph` issue #399
  records wrong answers, assertions, segmentation faults, and nontermination
  whose rate grows with graph density. Further nontermination and memory fixes
  continued through 2026. Requiring a newer Boost would break the current
  clean build; copying its implementation would violate this card's
  first-party provenance goal.

The C++23 implementation was independently authored from the published
algorithm descriptions. No Boost, NetworkX, competitive-programming, or other
implementation source was copied. No external dependency, generated artifact,
or `third_party/` file was added or modified. Future MIT native-core separation
remains possible.

## Verification status

Fresh isolated `native_metrics` builds with GCC 13.3.0, C++23, Release,
`-Wall -Wextra -Wpedantic -Werror`. Focused Phase-0 and matching tests pass
`18/18`. After rebasing over the Cycle-36 fused native-quad transaction, the
full relevant native metrics, Phase-0, dual, polyMesh, star fail-closed,
harness, and quad-transaction selection passes `102/102 in 39.18 s`; its two
warnings are the pre-existing all-NaN reduction fixture warnings. Ruff, Black,
and `git diff --check` pass. Strict focused mypy reports five pre-existing
`no-any-return` diagnostics in `polymesh_reader.py` and the unchanged
`_juretic_psi` return expression; it reports no diagnostic in the new matching
wrapper, kernel test, or exhaustive oracle.
