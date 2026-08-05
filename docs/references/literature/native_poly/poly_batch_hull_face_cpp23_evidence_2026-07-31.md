# POLY-C39-CPP23-BATCH-HULL-FACE-ASSEMBLY-1 Evidence

Date: 2026-07-31

Base: `bc379d248bf24e23572387d9672ecae29c877f4c`

Scope: replace the Python post-`scipy.spatial.ConvexHull` plane grouping,
polygon ordering, quantized dual-point indexing, and cap-label census with one
first-party C++23 batch kernel. Convex-hull construction remains unchanged.
No source geometry, topology contract, routing, target-cell policy,
boundary-layer policy, dependency, or `vendor/dependencies/` file changes.

## Frozen hypothesis and acceptance

The old path repeatedly allocated small NumPy arrays for every hull simplex and
face. Staging one cell batch as contiguous CSR arrays permits flat-vector
assembly, reserved output storage, and one Python/native transition while
retaining the exact legacy result.

Primary metric: alternating five-pair end-to-end `tet_to_poly_dual` wall time on
the fixed seed-density sphere primal (`669` points, `1631` tetrahedra).

- exactness: all five polyMesh files, topology/provenance, and mesh digest equal
  the frozen Python result
- validity: negative/inverted cells remain zero
- end-to-end acceptance: at least `1.35x` and at most `1.50 s`
- isolated block acceptance: at least `3.0x`
- peak-RSS acceptance: at most `+10%`
- rollback: any result-byte drift, malformed-ABI fallback, shape/provenance
  drift, invalid cell, nondeterminism, performance miss, external-code
  provenance, or unauthorized `vendor/dependencies/` change

## Baseline and hotspot

The frozen primal hash is
`84856e4ffa7654beb46a0f894baa05d3a314508501d6d470d9be26de38ed7d6c`.
The Python dual produced `669` cells, `5473` points, zero invalid/negative
stars, and mesh digest
`c972331abbb502f25942adbf69143478f600339330d3f0def8064abc8eb4806a`.
Five baseline runs were `1.995380/1.920086/1.988138/1.966567/1.973244 s`;
median `1.973244 s`.

In a representative `2.1017 s` warm run, the old per-face path made `22,108`
`np.cross`, `20,555` `np.stack`, `74,778` `np.round`, `42,390` norm, and
`20,555` `argsort` calls. `_add_point` was called `72,829` times. The measured
block was therefore selected without changing SciPy hull construction.

## Independent C++23 implementation

`native_polymesh.assemble_dual_hull_faces` accepts contiguous point, simplex,
plane-equation, offset, and source-label arrays. It preserves first-seen plane
group order, legacy nearest-even `1e-10` quantization, label tie-breaking, and
cell-local face order. Flat `std::vector`/`std::span` storage, capacity
reservation, and a quantized-key hash remove the Python per-simplex/per-face
allocation loop. Count, product, offset, index, and label bounds are validated
in both Python and C++ before access.

The Python caller keeps all input arrays alive while the GIL is released. The
released native region does not touch Python objects. Returned arrays are
C-contiguous and own moved vector storage through capsules. A missing optional
symbol uses the exact Python oracle. A deliberate native refusal also uses that
oracle and records `python_native_refusal`; stale or malformed ABI output fails
closed.

NumPy `atan2` distinguishes signed zero at its negative-axis branch cut. Raw
C++ ordering therefore differed only by cyclic start on `166/20,555` sphere
faces. The native kernel now flags this narrow ambiguity, and Python recomputes
only flagged face rings with the independent legacy oracle. After repair,
every staged array, all topology/provenance, and the final digest are exact.

## Result

Alternating five-pair direct-block medians were `0.369283 s` native versus
`1.577315 s` Python: `4.271x` speedup. Alternating five-pair end-to-end medians
were `0.852586 s` native versus `1.944262 s` legacy: `2.280x` speedup. All ten
end-to-end outputs matched the frozen digest exactly. Isolated peak RSS was
`120,320 KiB` native versus `117,696 KiB` legacy, a `+2.23%` change.

Focused tests cover independent-oracle byte parity, signed-zero ordering,
label ties, three-run determinism, strict dtypes, malformed offsets/indices,
overflow, refusal fallback, output lifetime/contiguity, and stale-ABI
fail-closed behavior. The focused kernel suite passes `6/6`. Existing native
face-geometry and classified topology/provenance parity tests also pass. With
the isolated `native_metrics` checker module enabled, the bounded hull,
dual, boundary-semantics, dual-point, native-extension, primal-conformity, and
star-validity regression set passes `74/74 in 54.33 s`.

The frozen performance claim is also an executable hard gate rather than a
document-only assertion. The gate clears ambient `AUTO_TESSELL_*` campaign
overrides, regenerates the sphere primal with the declared `seed_density=8`
configuration, and fails closed unless its typed-array digest is exactly
`84856e4ffa7654beb46a0f894baa05d3a314508501d6d470d9be26de38ed7d6c`.
It then forces the real `assemble_dual_hull_faces` symbol and an otherwise
identical native module with only that symbol hidden, so both C++23 and Python
assembly routes consume copied views of the same frozen primal. Both routes,
plus a second native repeat, produce `669` cells, `5473` points, zero invalid
star cells/sub-tets, byte-identical `points/faces/owner/neighbour/boundary`, and
the exact final digest
`c972331abbb502f25942adbf69143478f600339330d3f0def8064abc8eb4806a`.
The bounded command passes `1/1 in 22.32 s` with one OpenMP/BLAS thread:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
PYTHONPATH=/tmp/autotessell_poly39_build:$PWD \
../AutoTessell/.venv/bin/python -m pytest -q \
tests/test_native_poly_hull_face_assembly.py::test_frozen_sphere_native_and_python_assembly_are_byte_exact
```

The broader `test_native_poly*.py` plus target/writer run exceeded its declared
300-second budget, so it is not claimed as a pass. A separated
parser/target/writer subset returned `58 passed, 1 failed in 2.78 s`; the sole
failure is a pre-existing stale writer assertion that omits the already-returned
boundary `type: wall` field. This card changes none of that test, writer, or
parser path. It remains parent-campaign integration debt rather than a relaxed
card threshold.

A fresh isolated GCC 13.3 Release build of `native_polymesh` passes with C++23,
`-Wall -Wextra -Wpedantic -Werror`, one build job, and all unrelated optional
native modules disabled. Repository build products were not created.

## Research and provenance

- O. Sahni et al., *GALE: GPU-accelerated localized element-based mesh
  operations*, arXiv `2507.15230v3` (2025): accessible full text; supports
  batched localized connectivity processing, preallocation, and treating data
  integration as a measured stage.
- A. Mahmoud et al., *Dynamic Mesh Processing on GPUs: Algorithmic Design and
  Performance Analysis*, DOI `10.1145/3731162` (2025): official abstract and
  institutional record accessible; supports contiguous patch-local processing
  and guarded rollback. Full publisher PDF was not accessible.
- N. R. Wyman et al., *MINT: A Mesh INTegration Framework*, DOI
  `10.2514/6.2025-0686` (2025): official ORNL abstract accessible; full text was
  not accessible through the publisher or project repository. The full paper
  remains requested for evidence review.

Current source audits were reference-only: geometry-central
`019669dd` (MIT), pmp-library `2a2ad502` (MIT), Geogram `b6f545a1`
(BSD-3-Clause), libigl `477e15a3` (MPL-2.0/mixed), and Axom `a322ef5e`
(BSD-3-Clause). No external implementation, generated artifact, fixture, or
dependency was copied. The kernel was independently authored from the frozen
AutoTessell semantics and general published batching ideas. The current GPL
project license is unchanged; future MIT native-core separation remains
possible under the project policy.

## Promotion status

The card satisfies its correctness, performance, memory, build, and focused
regression criteria: `L1_PASS / RUNTIME_READY`. Full release-gate promotion
remains pending the parent campaign's complete Poly regression, corpus, and
integration scans.
