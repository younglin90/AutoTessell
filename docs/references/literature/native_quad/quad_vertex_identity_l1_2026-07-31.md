# QUAD-VERTEX-IDENTITY-L1 evidence

Date: 2026-07-31

Promotion target: `L1_PASS / EXPERIMENTAL_KEEP`

Mechanism: reject vertex arrays at the public quad boundary unless every input
coordinate is exactly representable by the native float64 ABI. Shape, finite,
numeric-kind, integer range, and bounds-aware dtype round-trip checks run before
native dispatch. Non-ndarray array-like inputs are first materialized as object
arrays so NumPy common-dtype coercion cannot erase the original scalar values;
each Python or NumPy scalar is then classified and converted exactly. The mesh
algorithm, topology policy, quality thresholds, target-cell behavior, routing,
and C++ implementation are unchanged.

## Research and provenance

- Weng et al., *Curve resampling based high-quality high-order unstructured
  quadrilateral mesh generation*, 2026, arXiv:2603.22780. Full text read. Its
  explicit boundary/interface geometric-error constraints support treating
  coordinate identity as a hard gate rather than a quality trade-off.
- Sajovic and Knez, *trueform: Fast And Robust Mesh CSG Via Topological
  Aggregation*, 2026, arXiv:2607.15905. Full text read. It documents that exact
  computation can still be invalidated when results are materialized with
  floating-point rounding.
- CGAL 6.3, *Exact Predicates Inexact Constructions Kernel* and polygon-mesh
  processing documentation, official documentation read at
  <https://doc.cgal.org/latest/Kernel_23/classCGAL_1_1Exact__predicates__inexact__constructions__kernel.html>.
  CGAL is GPL/LGPL by file or commercial and remains reference-only.
- `hcebke/libQEx`, GPL-3.0 or commercial; `hjiang/QuadriFlow`, MIT; and
  `wjakob/instant-meshes`, BSD-3-Clause were inspected as design references.
  No code, dependency, generated output, or implementation detail was copied.

The paper below was not present in the project-local literature repository.
On 2026-07-31 its official SIAM page exposed free PDF access.  It remains a
reference-only source until the user-provided archive copy is stored locally:

- DOI `10.1137/1.9781611979138.18`, Yiming Zhu, Qiankun Nie, Siquan Sun, Siyu
  Fang, Na Lei, Zhongxuan Luo, Hang Si, and Xianfeng Gu, *Surface Quadrilateral
  Mesh Generation Based on Weierstrass ℘ Function*, 2026, SIAM International
  Meshing Roundtable.

## Frozen baseline and acceptance

An actual two-triangle rectangle used signed-int64 x coordinates
`2^53 + 1` and `2^53 + 3`. The pre-card public route silently rounded these to
`2^53` and `2^53 + 4`, doubling the rectangle width from 2 to 4 while reporting
success. Three of three deterministic runs false-passed.

An adversarial review of the initial implementation found a second ingress:
mixed Python nested lists such as `[[2^53 + 1, 0.0, ...], ...]` were coerced to
float64 by `np.asarray` before the dtype round trip could inspect the integers.
Two lossy mixed-list fixtures and one bool/float fixture reached native dispatch
in the critic baseline (`3 failed, 15 passed`). This finding rejected the first
commit for integration and expanded the same boundary mechanism; it did not add
a second mesh algorithm or relax an acceptance gate.

Primary acceptance: false-success rate `3/3 -> 0/3`, with zero native calls and
zero artifacts. Secondary acceptance: lossy signed/unsigned integers and
extended-precision floats fail identically; valid float64 hashes and diagnostics
remain exact; float32 and exactly representable integers remain supported; input
buffers remain unchanged; native-present and native-absent paths agree.

## Result

- Lossy int64, uint64, and longdouble fixtures: `3/3` fail closed before native
  dispatch; native calls `0`; input bytes unchanged; artifacts `0`.
- Boolean, string, complex, and object arrays fail closed as ambiguous/non-real
  payloads; native calls `0`; warnings `0`.
- Lossy mixed Python integer/float lists at `2^53` and uint64 scale fail before
  native dispatch. Mixed bool/float and complex/float lists also fail before
  dispatch. Valid nested integer/float lists preserve the permanent hashes.
- Exactly representable int32, int64, float32, and float64 inputs retain exact
  coordinates and topology.
- Permanent valid-path hashes remain exact:
  - vertices: `dbc3917f0b890feff0f06cfc14b37405f5c9a97349d99036d1e782a7a2058a81`;
  - triangles: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
  - quads: `7eaad883b75863afc7d1028d04846b9d3b0de09f79e0fbc355edde84c8e0b279`.
- Owning and non-C-contiguous float64 inputs are isolated from result mutation.
  A defensive copy occurs only when conversion shares input memory; integer,
  float32, longdouble, and non-C float64 conversions reuse their already
  independent C-order buffer.
- Focused native-absent suite: `18 passed`; native-present quad/remesh suite:
  `107 passed`; three repeated focused runs are identical.
- Ruff and Black pass. Strict focused mypy reports no new error in the decoder;
  repository/import typing debt prevents a clean project result and remains
  outside this card.

This card changes no input coordinates, topology, boundary, feature, physical
group, provenance ordering, target-cell control, or boundary-layer behavior.
`vendor/dependencies/` is unchanged.
