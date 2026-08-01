# Native strict artifact audit — 2026-08-01

The independent `autotessell/strict-volume-topology/v1` audit was run over
existing written artifacts. It reads the output `polyMesh` after generation;
these are not in-memory generator metrics.

| artifact | cells | duplicate faces | non-manifold faces | open local cell edges | inverted cells | boundary valid | result |
|---|---:|---:|---:|---:|---:|---|---|
| `tests/stl/01_easy_cube_case` | 6,162 | 0 | 0 | 26,383 | 0 | no; 53,634 non-manifold edges | FAIL |
| `tests/stl/02_medium_cylinder_case` | 830 | 0 | 0 | 0 | 0 | yes | PASS |
| `tests/stl/05_ultra_knot_case` | 6,978 | 0 | 0 | 0 | 0 | no; 1 non-manifold edge | FAIL |
| `tests/benchmarks/sphere_case` | 4,009 | 0 | 0 | 0 | 0 | yes | PASS |
| `tests/stl/thingi10k_bench20/easy_100643_case` | — | — | — | — | — | missing artifact | UNVERIFIED |
| `tests/stl/thingi10k_bench20/easy_100034_case` | — | — | — | — | — | missing artifact | UNVERIFIED |

The strict release corpus therefore remains open. In particular, the cube
artifact cannot support a native release claim even though its checker reports
zero inverted cells. The positive cylinder/sphere observations are useful
regressions, but are not a substitute for the complete multi-engine matrix,
source authority, feature/patch/physical-group provenance, boundary-layer, and
repeatability evidence.
