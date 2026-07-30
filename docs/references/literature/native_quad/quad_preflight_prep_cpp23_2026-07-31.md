# QUAD-PREFLIGHT-PREP-CPP23-1 evidence

Date: 2026-07-31

Promotion target: `L1_PASS / EXPERIMENTAL_KEEP`

Mechanism: exact-result-preserving C++23 fusion of the existing triangle-surface
preflight, boundary/feature/wall classification, and unprotected face-pair
preparation. The pair-quality selector, thresholds, greedy policy, output
assembly, routing, and target-cell behavior are unchanged.

## Research and provenance

- CGAL 6.2, `PMPPolygonSoupOrientationVisitor`, official documentation read at
  <https://doc.cgal.org/latest/Polygon_mesh_processing/classPMPPolygonSoupOrientationVisitor.html>.
  It separately reports edges with more than two incident polygons and vertices
  whose links have multiple connected components. CGAL source is GPL/LGPL by
  file or commercial; no source, dependency, or generated output was reused.
- Mario Botsch and Leif Kobbelt, *A Remeshing Approach to Multiresolution
  Modeling*, Eurographics SGP 2004. The official Eurographics/RWTH full text was
  accessible. It motivates robust handling of degenerate faces and efficient
  mesh data access, but supplies no replacement for AutoTessell's topology,
  orientation, feature, or provenance gates.
- `nmwsharp/geometry-central`, GitHub head
  `019669ddabda05e0f71fa3587cfb3c1dadf19cb8` on 2026-07-31, MIT. Its dense
  element-data model is a design reference only. No implementation was copied.
- `CGAL/cgal`, GitHub head
  `5c6c586f2c32935e1a8282c6846f3f4a8eb3c317` on 2026-07-31. It remains a
  reference-only GPL/LGPL/commercial project outside the native-core boundary.

No paper required by this card was inaccessible. `third_party/` was not changed.

## Frozen baseline and acceptance

Fixture: deterministic planar `60 x 60` grid, `3,721` vertices, `7,200`
triangles, `10,680` interior pair candidates, GCC 13.3 Release C++23, Python
3.12. The baseline uses the pre-card Python preparation with the already-native
validator and pair-quality selector. Measurements include pybind input checking
and the complete public `native_quad_dominant_remesh` route. Alternating-order
median, five repeats:

- baseline public route: `0.223395300 s`;
- hypothesis: one contiguous `3F` edge record array, one contiguous `3F` link
  record array, sort/run incidence, compact face normals, and flat output arrays
  remove the C++ edge-map to Python-dict to C++-array round trip;
- primary acceptance: at least `3x` public-route speedup and absolute median at
  most `0.08 s`;
- rollback: any input mutation, topology/orientation/feature/wall mismatch,
  output connectivity/order/provenance/hash change, malformed native-output
  acceptance, nondeterminism, artifact creation, strict-build warning, or
  primary-metric miss.

Reproduce:

```bash
PYTHONPATH=. AUTOTESSELL_EXT_BUILD_DIR=<release-build> \
python3 tests/stl/bench_native_quad_pair_quality.py \
  --size 60 --repeats 5 --trace-memory
```

## Result

- Strict-wrapper public median: `0.051048960 s`.
- Preflight public speedup: `4.376x`; the absolute `0.08 s` budget passes.
- A separate three-repeat memory run measured `0.214291393 -> 0.046591538 s`
  (`4.599x`) and traced Python peak `4,657,868 -> 4,141,654` bytes (`11.08%`
  lower). NumPy result-model allocations remain in the route.
- Output hashes are exact:
  - vertices: `9b0fdcce659eebe739a726dd443951bb6abedbc7ef364d28f69e65e83403485b`;
  - triangles: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
  - quads: `7b13aba2846ff2a6e114f3f7250dd2e52b70dac1f83e4e19194537b415316c05`.
- Python fallback remains the independent oracle. Native output is only two
  contiguous arrays: face pairs `(K,2)` and fixed diagnostics `(5,)`.
- The wrapper independently proves every returned pair is an actual shared
  input edge and is neither a declared wall edge nor a feature edge. Invented,
  protected, duplicate, out-of-range, malformed-array, and inconsistent-count
  payloads fail closed without fallback.
- Exact signed-int64 wall decoding, duplicate-wall canonicalization, empty/open/
  disconnected valid surfaces, duplicate/degenerate/zero-area faces,
  inconsistent orientation, non-manifold edge, non-manifold vertex link, and
  threshold comparison parity pass.
- Focused suite: `54 passed`; wider quad/remesh suite: `88 passed`; native build
  contract suite: `7 passed`. Strict GCC 13.3 C++23 build reports zero warnings.

This card moves no vertices and creates no files. Three repeated public results
have identical coordinates, connectivity, diagnostics, and provenance ordering.
It is retained as `L1_PASS / EXPERIMENTAL_KEEP`; campaign-wide shape and release
gates remain open.
