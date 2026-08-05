# First-party native C++23 static boundary audit — 2026-07-31

## Scope and status

`CORRECTNESS_KEEP / static evidence only`.  This card changes no C++ source,
algorithm, mesh output, Python routing, dependency, or `vendor/dependencies/` file.
The inventory covers the eight shipped first-party extensions named in
`auto_tessell_core/native_build_contract.json`.

## Build-standard result

`CMakeLists.txt` has a legacy global `CMAKE_CXX_STANDARD 17`, but every shipped
first-party target calls `autotessell_configure_first_party_native`, which
requests `cxx_std_23` and disables C++ extensions.  Therefore the effective
first-party target contract is C++23, while the global default is a future
configuration-drift risk rather than proof of a shipped target built as C++17.

## Deterministic source inventory

Counts are source lines containing the token, not allocation measurements.
`forcecast` can allocate for incompatible/non-contiguous NumPy inputs;
`std::vector` can allocate but may reserve, reuse, or be small; `request()` is
a buffer-view call and does not itself prove a copy.

| Module | Bind LOC | `forcecast` lines | `std::vector` lines | `request()` lines | `mutable_data` lines |
| --- | ---: | ---: | ---: | ---: | ---: |
| native_metrics | 4861 | 69 | 89 | 0 | 5 |
| native_tet_predicates | 2886 | 20 | 71 | 8 | 0 |
| native_polymesh | 1985 | 11 | 49 | 0 | 4 |
| native_hex_quality | 1132 | 12 | 19 | 1 | 1 |
| native_bl | 907 | 13 | 18 | 0 | 3 |
| native_tet_qopt | 807 | 22 | 38 | 0 | 0 |
| native_snap | 512 | 9 | 3 | 0 | 0 |
| native_surface_padding | 271 | 1 | 14 | 1 | 0 |

## Prioritized measurement cards

1. `native_metrics`: highest Python-boundary conversion and vector inventory;
   profile contiguous read-only arrays against dtype/layout-mismatched arrays,
   then separate output allocation from input coercion.
2. `native_tet_qopt` and `native_tet_predicates`: high forcecast/vector density
   on topology-sensitive paths; preserve exact predicates and do not change
   acceptance while evaluating spans, views, reserve policy, or reusable
   workspace candidates.
3. `native_polymesh`: vector-heavy topology construction; measure peak memory
   and allocator calls before proposing CSR/PMR/workspace changes.
4. `native_hex_quality` and `native_bl`: evaluate batch hot paths only after a
   representative Hex/BL corpus records baseline time and peak memory.

No static count proves an avoidable copy.  A future refactor card must declare
one hot function, contiguous/dtype fixture, baseline timing, peak memory,
determinism hash, shape/provenance result, and rollback condition before making
any C++ change.
