# HEX-WALLFIT-LOCAL-SCALE-BATCH-CPP23-1

## Scope and provenance

First-party clean-room C++23 implementation. It computes only the existing
wall-fit local edge-scale definition. No external source code, generated code,
mesh output, or implementation-derived constants were copied. `third_party/`
is unchanged. Current project GPL terms remain unchanged; the implementation
has no new dependency and remains separable for a future MIT native core.

## Sources checked before implementation

- Hua Tong and Yongjie Jessica Zhang, “HexOpt: Efficient and robust
  hexahedral mesh optimization using Rectified Hybrid Quadratic Jacobian and
  geometry-aware mapping,” *Computer-Aided Design* (2026), DOI
  `10.1016/j.cad.2026.104073`. The paper motivates strict input-surface and
  feature-class preservation. Algorithmic context only; no code reused.
- OpenFOAM v2606 official repository and snappyHexMesh snapping documentation.
  The documented projection, quality validation, and reversible rollback
  sequence supports AutoTessell's existing shape/validity priority. GPLv3-or-
  later source; reference only, no code reused.
- CGAL 6.2 AABB Tree manual and official license page. Closest-point queries
  are relevant context, but the AABB Tree package is GPL. No dependency or
  code reused.
- pybind11 official repository/documentation. Existing BSD-style dependency;
  used only through its established NumPy binding and GIL APIs.
- AlgoHex official GitHub repository. AGPL-3.0; excluded from implementation.

No inaccessible DOI was encountered for this card.

## Frozen baseline and acceptance

Fresh GCC 13.3 Release C++23 build, structured 16³ cube, 4,096 cells, 1,538
boundary vertices:

- `_wall_fit_snap` median: 0.451690 s over seven runs.
- Python local-scale median: 0.249417 s over eleven runs.
- `np.linalg.norm` calls in profiled wall-fit: 139,971; cumulative 0.285 s.
- Nested-cell pybind conversion plus native signed-volume proxy: 0.005080 s.

Predeclared gates:

- whole wall-fit median speedup at least 1.70x;
- native whole wall-fit median at most 0.30 s;
- isolated local-scale speedup at least 20x;
- no peak-memory regression;
- bitwise-exact local scales, mesh points, statistics, topology, provenance,
  and deterministic hashes;
- zero new negative, inverted, or degenerate cells.

Any gate failure, loaded-ABI fallback, output divergence, or permanent-test
regression requires rollback. Target-cell, boundary-layer, projection,
incident topology, quality thresholds, and writer behavior are outside scope.

## Result

Final alternating benchmark, twelve whole-stage samples and five memory
samples per route:

- whole wall-fit: 0.481632 s to 0.213631 s, 2.2545x;
- isolated local scale: 0.269581 s to 0.005217 s, 51.68x;
- Python traced peak: 5,096,184 bytes for both routes;
- output SHA-256: `4676f7ac25abd3d70baf4fb74a0c2b1106ac0243c2f3aabfbf1c8c46a8f53880`;
- 1,538 full snaps, zero partial snaps, zero rejects, exact statistics;
- structured and deterministically perturbed local-scale vectors bitwise exact;
- focused and expanded regression: 110 tests passed, including cylinder
  standard/fine wall fidelity, negative-volume, strict-writer, topology, and
  provenance coverage.

The legacy loop recomputed every incident cell's full face-edge set for every
boundary vertex. The native kernel computes each cell maximum once, then
updates its boundary vertices. Time changes from repeated boundary-incidence
edge traversal to one cell-edge traversal plus one cell-vertex traversal.
Transient native storage is one point-index-to-output-slot vector; output and
authoritative Python topology remain unchanged.
