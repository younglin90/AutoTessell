# Native Hex C++23 Feature-Edge Extraction

Date: 2026-07-30

Card: `HEX-FEATURE-EDGE-CPP23-1`

Scope: exact-result-preserving performance replacement; no routing, threshold,
surface, topology, or provenance contract change.

## Research basis and provenance

- CGAL 6.2, *Polygon Mesh Processing: Feature Detection Functions*, official
  documentation:
  <https://doc.cgal.org/latest/Polygon_mesh_processing/group__PMP__detect__features__grp.html>.
  The documented contract marks sharp edges from a face-normal angle bound and
  then uses feature separation/patch incidence. This supports retaining an
  explicit angle-bound edge classification and deterministic edge identity.
- CGAL is an external GPL/commercial project. Its implementation is not used,
  copied, linked, or added as a dependency. The code in this card is an
  independent first-party implementation based on the existing AutoTessell
  Python oracle and flat-array contract.
- Existing project full read: Qian and Zhang (2010), *Sharp Feature
  Preservation in Octree-Based Hexahedral Mesh Generation for CAD Assembly
  Models*, DOI `10.1007/978-3-642-15414-0_15`, recorded in
  `qian2010_sharp_feature_octree.md`. Its feature ownership ordering reinforces
  that feature classification must remain deterministic and must precede
  topology/snap decisions. No paper code is copied.

## Frozen contract

The native ABI consumes exact C-contiguous `float64[V,3]` vertices and
`int64[F,3]` faces plus a finite angle in degrees. It returns
`float64[M,2,3]` segments and `float64[M]` weights. Invalid dtype/layout,
non-finite coordinates/angle, and negative or out-of-range indices fail closed.
An absent module/function uses the retained Python oracle. Once the callable
native kernel is present, kernel exceptions or malformed output propagate;
they are never hidden by a silent Python fallback. The wrapper also requires
raw ndarray outputs with exact float64 dtype, C-contiguous layout, valid shapes,
and finite values; it performs no coercing copy.

For valid input, output follows the Python oracle exactly:

- canonical endpoint order and lexicographic segment order;
- one-owner boundary edge: feature, weight `1.5`;
- two-owner edge: feature only when `dot(n0,n1) < cos(angle)`; weight
  `1 + (1 - dot(n0,n1))`;
- more than two owners: ignored, preserving the current non-manifold policy;
- zero-area face normals become zero, preserving current zero-area behavior;
- `_seg_weight` remains attached by the Python ndarray wrapper.

The C++23 kernel preallocates one contiguous `EdgeRecord` array of size `3F`,
computes normals once, lexicographically sorts records, counts feature runs in
one linear scan, reserves exact output capacity, and emits them in a second
linear scan. Complexity remains `O(F log F)` time and `O(F)` space, while
Python dictionaries, per-edge lists, scalar NumPy dispatch, and output-vector
reallocation are removed. The GIL is released only after complete shape,
finite, bounds, and overflow validation.

## Baseline and acceptance

Representative fixture: planar `240 x 240` quad grid, `58,081` vertices,
`115,200` triangles, `960` boundary feature segments.

Before implementation, four Python runs were
`0.8249/0.8114/0.8145/0.8044 s`; warm median `0.8114 s`. `cProfile` recorded
`1,727,186` calls, including `172,320` scalar `np.clip` calls. Tracemalloc peak
was `98.56 MiB`; isolated process maximum RSS, including interpreter/import and
input construction, was `170,856 KiB`.

Final fixed-path, alternating-order measurement used one warmup and seven runs:
Python median `0.829629 s`; native median `0.020881 s`; native p95
`0.021397 s`; speedup `39.73x`; segment bytes and weights exact. It passes the
declared `>=4x`, native median `<=0.203 s` acceptance threshold. An earlier run
under unrelated GCC load still measured `27.73x`, so the conclusion is not
dependent on the cleanest timing window.

Matched isolated subprocesses measured maximum RSS `169,448 KiB` for the
Python oracle and `73,220 KiB` for the native path, a `56.79%` reduction. Both
figures include interpreter/import and identical fixture construction.

Required verification:

1. open patch, closed cube, threshold-neighbour, reversed/disconnected,
   zero-area, duplicate/non-manifold, and empty parity;
2. strict ABI rejection for dtype/layout/finite/bounds violations;
3. three exact deterministic repeats;
4. WWW8 octree refinement and WWW7 feature snap output parity;
5. no topology/provenance/validity regression;
6. GCC 13 C++23 release build with warnings as errors;
7. focused native snap/native hex regression and `git diff --check`.

Verification result: focused native snap/surface snap `42 passed`; all
`test_native_hex*.py` plus native snap extension `200 passed, 9 skipped`.
GCC 13.3 C++23 release build passed with `-Werror`; `git diff --check`, Black,
Ruff, and the isolated strict-mypy benchmark check passed. Promotion remains
`L1_PASS / EXPERIMENTAL_KEEP`: this performance card does not claim L2/L3 mesh
quality closure or change a permanent threshold. No change to `third_party/`,
dependency inventory, engine defaults, routing, or mesh output.
