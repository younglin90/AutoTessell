# Native hex local-front C++23 kernel

Date: 2026-07-31

Card: `HEX-LOCAL-FRONT-CPP23-1`

Promotion state: `EXPERIMENTAL_KEEP`, report-only. The kernel has no production
import, routing, writer, or boundary-layer activation path. It does not pass
Gate 7 and does not fill the inner all-hex core.

## Frozen source and provenance

The behavioral source is the independent AutoTessell Python experiment at
commit `1b4850f3679e6c240a1a6751a3c8ca7d5721ae7f`. The integration lane verified
the complete read-only bundle at
`/mnt/d/AutoTessell-cleanup-backup-20260730/research-bundles/hex41-local-front-prototype/pivot-1b4850f3.bundle`,
SHA-256
`5182aab19a85548c4b3f1055b12dd56f057588b19d42068ef41a8e87ef560592`.
The bundle is evidence, not a runtime or build dependency. The C++ code is an
independent implementation of the frozen input/output contract; prototype
source was not copied.

Reberol et al., *Robust Topological Construction of All-hexahedral Boundary
Layer Meshes*, ACM TOMS 49(1), 2023, DOI `10.1145/3577196`, informs only the
fixed-boundary and fail-closed acceptance principles. No paper or external
implementation source, constant, data structure, or generated artifact was
copied. Direct dependencies are pybind11 (BSD-3-Clause) and the C++ standard
library. `vendor/dependencies/` is unchanged.

## Exact API and validation contract

The existing first-party `native_hex_quality` C++23 target now exposes:

`local_front_backtrack_steps(outer_points, outer_quads, unit_inward_normals,
initial_step, geometry_tolerance, determinant_tolerance,
maximum_iterations=32)`.

Inputs require exact C-contiguous `float64`, `int64`, and `float64` arrays.
`py::arg().noconvert()` rejects implicit dtype and stride copies. Before the
output array is allocated, the binding validates:

- non-empty `(V,3)`, `(H,4)`, `(V,3)` shapes and multiplication overflow;
- finite outer coordinates and normals;
- normal length within `256*double epsilon` of one;
- in-range quad ids and four distinct vertices per quad;
- finite `initial_step > geometry_tolerance > 0`;
- finite non-negative determinant tolerance;
- `maximum_iterations` in `[1,64]`; and
- finite initial inner-front coordinates.

The only geometric output is a new contiguous local-step array. All inputs are
read through const spans and remain byte-identical.

## C++23 data path

`native_hex_quality_local_front.hpp` is a pure standard-library kernel. It uses const
`std::span` inputs, a writable span over the already allocated NumPy output,
`constexpr` five-tet and corner-neighbor tables, `std::array` stack cells, and
one scalar result. The GIL is released for the numerical loop.

The kernel allocates one contiguous inner-coordinate buffer, one hex-failure
byte mask, and one affected-vertex byte mask. They are reused for every
iteration. It allocates no cell-connectivity array, set, map, Python object, or
per-iteration heap object. The sequential vertex transform and sequential hex
audit preserve cache locality. There is no input copy and only one Python
output allocation.

For `I` backtracks, `V` front vertices, and `H` shell hexes:

- time: `O(I*(V+H))`;
- auxiliary storage: `O(V+H)`;
- iteration cap: 64, default 32.

## Frozen parity result

The independent test-only Python reference and C++23 result are bitwise equal
for every local step.

| Fixture | Requested | Initial | Iterations | Reduced vertices | Minimum step | Raw negative | Bad corner hexes | Final contacts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cube | `0.1` | `0.1` | 0 | 0 | `0.1` | 0 | 0 | 0 |
| hard bracket | `0.05` | `0.01818845869286433` | 8 | 740 | `7.104866676900129e-05` | 0 | 0 | 0 |

The hard-bracket requested-thickness baseline remains 1,248 hexes, 160 raw
negative hexes, 4,161 non-adjacent inner-front intersections, and four
conservative coplanar pairs. The final minimum signed corner determinant is
`7.581467097331643e-12`. The final conservative contact pair is zero, so a
verified coplanar overlap cannot be hidden. Three native calls return identical
arrays and counters. Outer coordinates, quad topology, source coordinate/face
arrays, source file hash, and normal inputs remain byte-identical.

## Performance and verification

The frozen 1,248-hex backtracking kernel was warmed once and measured five
times with all BLAS/OpenMP thread counts fixed at one. Surface preparation and
the separate contact audit were excluded from both sides.

- C++23 median: `0.0006939940 s`;
- independent Python median: `0.0325426470 s`;
- ratio: `0.0213257x` (`46.89x` faster).

Raw samples, in execution order:

- C++: `0.0007368759979726747`, `0.0006861410001874901`,
  `0.0006950870010768995`, `0.0006939939994481392`,
  `0.0006890180011396296` seconds;
- Python: `0.03276007100066636`, `0.03257362000294961`,
  `0.032542647000809666`, `0.030357672003447078`,
  `0.02600884099956602` seconds.

Reproduction command, run from the repository root after building the branch's
`native_hex_quality` target into `/tmp/autotessell-hex42-build`:

```bash
AUTOTESSELL_EXT_BUILD_DIR=/tmp/autotessell-hex42-build \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=. \
python3 - <<'PY'
import importlib.util
import statistics
import time
from pathlib import Path

test_path = Path("tests/test_native_hex_local_front_cpp23.py")
spec = importlib.util.spec_from_file_location("hex42_test", test_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
arguments = module._fixture(Path("tests/stl/03_hard_bracket.stl"), 0.05)[:6]
native = module._native_or_skip()

def cpp():
    return native.local_front_backtrack_steps(*arguments, 32)

def python():
    return module._python_reference(*arguments, 32)

cpp()
python()

def samples(function):
    values = []
    for _ in range(5):
        start = time.perf_counter()
        function()
        values.append(time.perf_counter() - start)
    return values

cpp_samples = samples(cpp)
python_samples = samples(python)
print("cpp", cpp_samples, "median", statistics.median(cpp_samples))
print("python", python_samples, "median", statistics.median(python_samples))
print("ratio", statistics.median(cpp_samples) / statistics.median(python_samples))
PY
```

Timer: CPython `perf_counter`, implemented by
`clock_gettime(CLOCK_MONOTONIC)`, monotonic/non-adjustable, reported resolution
`1e-9 s`. Host: AMD Ryzen Threadripper PRO 5975WX 32-Cores, 64 logical CPUs,
WSL2 Linux `6.6.87.2-microsoft-standard-WSL2`, no CPU affinity pinning. The
benchmark process used one OpenMP/BLAS thread; no other campaign lane was
started by this card during sampling.

This passes the predeclared `C++ <= 0.75x Python` acceptance gate and the
stronger `0.5x` evidence target.

- GCC 13.3, Release C++23, `-Wall -Wextra -Wpedantic -Werror`, `j1`: PASS;
- direct parity, deterministic fixture, and ABI validation tests: PASS;
- exact native ABI contract and source-evidence manifest: required before
  integration;
- `vendor/dependencies/`, production Python imports, routing, writer, and CMake target
  changes: zero.

## Limits

The C++ kernel ports only the validated backtracking loop. Source quadization,
authoritative provenance, opposite-front clearance, and final contact checks
remain independent pre/postconditions. The hard-bracket sidecar has one
synthetic entity and does not prove authoritative CAD ridge semantics. The
256-fold local thickness variation has no practical CFD-quality acceptance
contract. Production promotion remains forbidden until those contracts and an
all-hex core/interface solution exist.
