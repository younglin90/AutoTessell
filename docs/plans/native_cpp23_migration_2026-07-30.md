# Native C++23 Migration Plan

## Goal and non-negotiable contracts

AutoTessell moves from Python compute kernels to an independently implemented
C++23 native core.  Python remains a thin CLI, UI, configuration, and binding
layer until those interfaces can be replaced without losing compatibility.

Every port must preserve, before performance is considered:

1. input coordinates and surface envelope;
2. feature, boundary, hole, component, topology, physical-group, and provenance
   identity;
3. zero inverted/negative/invalid output elements;
4. deterministic topology and provenance hashes;
5. target-cell and boundary-layer reporting semantics, including layer zero.

No `third_party/` source is modified.  GPL adapters remain outside the future
MIT-eligible native-core boundary.  New native code is first-party and records
its provenance independently.

## Current architecture inventory

- First-party Python: roughly 419 core modules plus CLI/backend/desktop scripts.
- First-party native extension sources: metrics, polyMesh topology, snapping,
  surface padding, hex quality, tetrahedral predicates, and tet QOPT.
- Before this card, the build exposed only five native targets.  The existing
  `native_tet_predicates_bind.cpp` and `native_tet_qopt_bind.cpp` were not CMake
  targets, so 18 extension checks were skipped.
- Largest compute-heavy Python modules are boundary layers, native tet meshing,
  stellar/tet optimization, poly Voronoi/dual construction, native hex meshing,
  tri/quad operator loops, evaluator kernels, and polyMesh I/O.
- GUI, API routing, schemas, and reporting contain substantial Python but are
  not first performance targets.  Porting orchestration before kernels would
  increase ABI surface without reducing the dominant cost.

## Evidence from the first card

- Clean native-only build before: five targets, `38.87 s`, peak RSS
  `471,720 KiB`.
- Clean native-only build after: seven targets, `52.85 s`, peak RSS
  `649,904 KiB`; the increase is the two newly compiled modules, not runtime
  memory evidence.
- Tet predicate/QOPT extension and focused topology suites: `79 passed`.
- Guarded smoothing, 4,096 points / 20,250 tets / two iterations / seven repeats:
  Python median `0.104483 s`; C++ median `0.013313 s`; speedup `7.85x`; maximum
  coordinate difference `3.33e-16`; counters identical.
- Fused quality snapshot, 24,000 points / 80,000 tets / five repeats: Python
  median `0.103394 s`; C++ median `0.015934 s`; speedup `6.49x`; maximum relative
  reported-metric difference `3.53e-11`.

## Porting order

Each item is an independent card with baseline, parity corpus, benchmark,
rollback threshold, provenance note, and post-merge regression run.

1. **Build and ABI contract**
   - CMake 3.20 minimum: this is the first CMake version that understands the
     C++23 standard level.
   - Exact Python interpreter selection, pybind11 3.x declaration, seven native
     targets, warning-clean release build, and platform matrix.
2. **Evaluator and mesh I/O kernels**
   - Keep topology in native flat storage from reader through quality evaluation.
   - Remove Python list materialization for triangle-only and CSR topology paths.
   - Port remaining parser/writer loops and expose zero-copy read-only views.
3. **Tet topology and optimization**
   - Move face/edge maps, recovery queues, strict-topology audits, candidate
     transactions, smoothing, and quality selection into one native state object.
   - Targeted recovery moves from repeated scans toward an incrementally updated
     canonical face/edge index.
4. **Boundary layers**
   - Port collision detection, front adjacency, thickness/growth scheduling,
     self-intersection checks, and local layer reduction.
   - Preserve wall/patch provenance and exact layer-zero semantics.
5. **Poly meshing**
   - Port seed filtering, restricted Voronoi/dual adjacency, face
     canonicalization, classification, and writer connectivity.
6. **Hex meshing**
   - Port lattice sizing, octree state, transition templates, wall fitting,
     matching/repair, and layer handoff while retaining source certificates.
7. **Tri/quad surface operators**
   - Port adjacency, protected-feature constraints, operator evaluation,
     transaction rollback, and deterministic pairing.
8. **Pipeline consolidation**
   - Replace Python data shuttling with opaque native mesh/state handles.
   - Keep Python only for stable API/CLI/UI adapters, then evaluate a native CLI.

## Data layout and algorithm rules

| Area | Current risk | Native target |
|---|---|---|
| Adjacency | nested dict/list/set allocations | flat CSR offsets + contiguous indices |
| Canonical faces/edges | hash-node allocation and unstable traversal | packed canonical keys, sort/scan, stable IDs |
| Point/cell data | repeated NumPy gathers and temporaries | contiguous views; AoS for per-cell geometry, SoA for field-wide sweeps |
| Scratch storage | allocation inside inner loops | reserved reusable buffers; `std::pmr` only after measured benefit |
| Ownership | Python↔C++ copies and returned containers | borrowed `std::span` views, direct NumPy output buffers, RVO/move ownership |
| Small topology tables | runtime construction | `constexpr std::array` edge/face/template tables |
| Failure state | exception/fallback ambiguity | typed status/result plus explicit Python exception mapping |

Use `std::span` for non-owning contiguous input.  Use `std::mdspan` only after
the supported compiler/library matrix proves the C++23 implementation exists;
language standard adoption does not guarantee library availability.  A local
compatibility layer must not introduce a new unreviewed dependency.

For each kernel, state time and space complexity before implementation.  The
first smoothing conversion replaces per-vertex vectors plus per-candidate
incident allocations with one flat CSR graph.  Its target complexity is
`O(T log T + I(E + T))` time and `O(V + E + T)` auxiliary space; the sort is
performed once, outside the iteration loop.  The fused quality kernel performs
one sequential tet pass and avoids multiple `T x 4 x 3` NumPy temporaries.

## Copy, allocation, cache, and parallelism policy

- Pass large native objects by `const&` or `std::span`; pass small scalar/POD
  values by value.
- Do not add `std::move` to local return values where it inhibits NRVO.  Move
  only at real ownership-transfer boundaries.
- Reserve containers from known mesh counts.  Replace node-based containers in
  hot loops with flat sorted vectors or CSR unless profiling proves otherwise.
- Reuse workspaces across iterations.  No heap allocation in the innermost
  point/face/cell loop.
- Release the Python GIL only after all Python objects/buffers are acquired and
  validation is complete; reacquire it before creating Python dictionaries or
  exceptions.
- Parallel reductions must have deterministic partitions and merge order.
  Thread-count changes may not change topology/provenance hashes.

## Compiler optimization policy

- C++23 is required for first-party native targets; compiler extensions are off.
- Release starts with portable `-O3` or `/O2`.  IPO/LTO is enabled only after
  `CheckIPOSupported` succeeds for that exact toolchain/configuration.
- PGO is a later release card using the representative mesh corpus; generated
  profiles are artifacts, never source.
- `-march=native` is benchmark/developer-only, never a portable release default.
- `-ffast-math` is forbidden for robust predicates, shape/validity gates, and
  provenance-critical geometry.  Vectorization must preserve declared numeric
  tolerances and sign decisions.
- `constexpr`, `inline`, and `noexcept` are applied to small pure primitives when
  they improve the generated code or contract; they are not decorative targets.

## Acceptance and rollback

For every C++ port:

1. run Python/native parity on normal, degenerate, empty, invalid, mixed-scale,
   and large representative inputs;
2. verify exact topology/provenance hashes where the contract requires identity;
3. verify surface envelope and all shape invariants;
4. verify zero inversion/negative volume and explicit errors for bad input;
5. run at least three deterministic repeats;
6. report median wall time and peak RSS after warm-up;
7. reject a port with unexplained metric drift, shape/topology drift, higher
   asymptotic complexity, or a material performance/memory regression;
8. keep a Python fallback only while packaging/platform coverage remains
   incomplete, and make fallback use explicit and observable.

## Boundary-layer spatial-search card

The first profiled boundary-layer card replaces two dense `N x N` NumPy
matrices in `_nearby_opposite_front_mask` with a first-party C++23 uniform-grid
hash.  Cell size equals the exact query radius, so checking the 27 adjacent
cells is complete for Euclidean radius pairs.  Flat `point_keys`, `next`, and
collision arrays retain cache locality; the hash table stores one head per
occupied cell and reserves capacity before insertion.  Expected complexity is
`O(N + k)` time and `O(N)` space under ordinary hash occupancy, versus
`O(N^2)` time and space for the prior dense route.  A bounded block fallback
and SciPy KD-tree fallback remain for builds without the native module.

On two separated 50-by-50 fronts (`5,000` vertices), the C++ median is
`0.001875 s` versus `0.362497 s` for the bounded Python fallback (`193.3x`),
with identical collision masks.  The prior dense route required 25 million
pair entries and about 1 GB of simultaneous dot/delta/distance/mask storage;
the native route allocates no dense pair array.

## Primary technical sources

- WG21 P0009R18, `mdspan`, adopted for C++23:
  <https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2022/p0009r18.html>
- CMake C++ standard property and CMake 3.20 C++23 support:
  <https://cmake.org/cmake/help/latest/prop_tgt/CXX_STANDARD.html>
- CMake `CheckIPOSupported`:
  <https://cmake.org/cmake/help/latest/module/CheckIPOSupported.html>
- pybind11 3.0 upgrade/ABI guidance:
  <https://pybind11.readthedocs.io/en/stable/upgrade.html>
- pybind11 NumPy buffer and direct-access guidance:
  <https://pybind11.readthedocs.io/en/stable/advanced/pycpp/numpy.html>
- Teschner et al., optimized spatial hashing for collision detection:
  <https://www.research-collection.ethz.ch/entities/publication/f29bfb28-ee5f-4a7e-9905-f787e138bb81>
- SciPy radius-pair query contract used by the optional fallback:
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.KDTree.query_pairs.html>
