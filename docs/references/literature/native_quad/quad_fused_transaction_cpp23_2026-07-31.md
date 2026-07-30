# QUAD-FUSED-TRANSACTION-CPP23-1 evidence

Date: 2026-07-31

Promotion target: `L1_PASS / EXPERIMENTAL_KEEP`

Mechanism: one C++23 transaction composes the already-native topology
preflight and greedy quality selector, assembles unconsumed triangles, and
crosses the Python boundary once.  The Python wrapper keeps an independent,
vectorized provenance audit and the scalar implementation remains the
extension-absent oracle.  Candidate generation, encounter order, quality
formula, thresholds, greedy policy, geometry, routing, and target-cell
behavior are unchanged.

## Latest research and provenance review

- Haoxuan Zhang, Haisheng Li, Xinyu Wu, and Nan Li, *Surface Structured
  Quadrilateral Mesh Generation Based on Topology Consistent-Preserved Patch
  Segmentation*, 2025, DOI
  [10.1002/nme.7644](https://doi.org/10.1002/nme.7644).  The official publisher
  abstract was accessible on 2026-07-31; the full text was not accessible.
  Its topology-consistent objective supports treating topology as a hard gate,
  but no algorithm or implementation was used.
- Yiming Zhu, Na Lei, Xiaopeng Zheng, Zhongxuan Luo, Hang Si, and Xianfeng Gu,
  *Quadrilateral Mesh Generation for Open Surfaces with Negative Euler
  Characteristics Based on Symmetric Abel Differentials*, SIAM IMR 2025, DOI
  [10.1137/1.9781611978575.6](https://doi.org/10.1137/1.9781611978575.6).
  The official abstract was accessible; the chapter/PDF required paid or
  institutional access.  The abstract reinforces explicit boundary and
  topology handling.  No method was adopted.
- Jingwei Huang et al., *QuadriFlow: A Scalable and Robust Method for
  Quadrangulation*, DOI
  [10.1111/cgf.13498](https://doi.org/10.1111/cgf.13498).  The paper was already
  locally reviewed.  The official
  [QuadriFlow repository](https://github.com/hjwdzh/QuadriFlow) master head was
  `810b7a0967c35b0dc85b4464e3835e26a756c967` on 2026-07-31 and is MIT.  Its
  documented contract starts from a manifold triangle mesh and treats sharp
  preservation and watertight flip removal explicitly.  No code, generated
  output, dependency, or binary was copied.
- [libQEx](https://github.com/hcebke/libQEx) head
  `517dcaa0cc87646baa89e52cfc8e23766776f6d5` is GPL-3.0.  Its robust extraction
  discussion is reference-only and remains outside the future MIT native-core
  boundary.

The two inaccessible full texts and their access reasons must remain in the
campaign DOI ledger.  The retained implementation is independent first-party
C++23.  `third_party/` is unchanged.

## Frozen baseline and acceptance

Fixture: deterministic planar `60 x 60` grid, `3,721` vertices, `7,200`
triangles, `10,680` candidate pairs, and `3,600` accepted quads.  Python 3.12,
GCC 13.3 Release C++23, alternating order, median of seven after warmup.

Before production edits:

- current native public-route median: `0.052478419 s`;
- cProfile, ten routes: `0.784 s` total;
- strict scalar triangle-index decode: `0.256 s`;
- native-preparation boundary/audit: `0.280 s`;
- native-selection boundary/audit: `0.225 s`;
- actual native preflight and selection kernels: about `0.051 s` total across
  ten calls.

Predeclared acceptance:

- primary public-route speedup at least `1.8x`;
- primary fused median no greater than `0.030 s`;
- fused route versus full Python oracle at least `20x`;
- exact input/output arrays, diagnostics, candidate decisions, and hashes;
- identical results across three runs.

Rollback: any source mutation; topology, wall, feature, orientation, quality,
ordering, or provenance mismatch; malformed payload acceptance; invalid or
non-finite output; nondeterminism; build warning; performance miss; or
`third_party/` change.

Reproduce after a Release native build:

```bash
PYTHONPATH=. AUTOTESSELL_EXT_BUILD_DIR=<release-build> \
python3 tests/stl/bench_native_quad_pair_quality.py --size 60 --repeats 7
```

## Result

- Fused public-route median: `0.018677954 s`.
- Frozen-baseline speedup: `2.810x`; both primary thresholds pass.
- Full Python public oracle median: `2.238914949 s`; fused speedup `119.87x`.
- A post-change split-native route with the new vectorized independent audits
  measured `0.019429108 s`; the one-call fusion contributes another `1.040x`.
  Most end-to-end gain comes from removing the former per-index/per-pair Python
  scalar scans while retaining equivalent vectorized hard gates.
- Output vertex SHA-256:
  `9b0fdcce659eebe739a726dd443951bb6abedbc7ef364d28f69e65e83403485b`.
- Output triangle SHA-256:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- Output quad SHA-256:
  `7b13aba2846ff2a6e114f3f7250dd2e52b70dac1f83e4e19194537b415316c05`.
- The wrapper independently verifies exact array ABI, shared input edges,
  protected wall/feature exclusion, accepted-pair uniqueness/order, oriented
  quad provenance, source-face consumption, remaining-triangle ordering,
  finite quality ranges, and fixed diagnostics.
- Exact `int64` input takes the strict contiguous fast path.  Other exact
  integral inputs retain the existing scalar decoder; float, bool, string,
  infinity, and signed-int64 overflow remain fail-closed.
- Three public runs preserve coordinates, connectivity, diagnostics, hashes,
  and both source arrays exactly.

Validation:

- focused transaction/ABI/provenance suite: `8 passed`;
- existing native Quad suites plus contract: `127 passed`;
- face-remesh, build-evidence, and wheel-contract suites: `20 passed`;
- combined unique regression selection: `153 passed`;
- isolated GCC 13.3 `-std=c++23 -O3 -Wall -Wextra -Wpedantic` Release build:
  zero warnings;
- Ruff and `git diff --check`: pass.
