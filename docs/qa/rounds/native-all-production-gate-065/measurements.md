# Measurements - native-all-production-gate-065

## Commands and results

| Check | Command/result | Evidence |
| --- | --- | --- |
| C++ configure | `cmake -S auto_tessell_core -B auto_tessell_core/build -DBUILD_NATIVE_TRANSACTION_INTENT=ON -DBUILD_NATIVE_TRANSACTION_EXECUTOR=ON` | Configure succeeded; OCCT remains fail-closed because `AUTOTESSELL_OCCT_SDK_ROOT` is unset. |
| C++ build | `cmake --build auto_tessell_core/build --target native_transaction_executor native_transaction_intent native_quality_witness native_wall_edge_metric_corridor -j2` | All four targets built successfully. |
| fresh default | Fresh configure CMakeCache | `BUILD_NATIVE_TRANSACTION_EXECUTOR:BOOL=OFF`; the executor is not product-default-on. |
| 065 executor/adapter | `pytest -q tests/test_native_transaction_executor_v1_cpp23.py tests/test_native_transaction_executor_adapter.py` | **10 passed**. |
| prior gates | Intent, corridor and quality-witness regression files | **25 passed**; no failures. |
| combined focused gate | All 065 and 062/063/064 focused files | **35 passed in 4.50 s**. |

## State-machine evidence

- BL=0: actual layer count 0, layer work 0, empty layer rows; candidate/reread/publish completed with generated entity count 2 and one writer call in the harness.
- BL=1: actual layer count 1, positive measure, and roles `{wall, front, side}`; candidate/reread/publish completed.
- Rejected states: inverted topology, missing BL role, authority topology mutation, corridor layer/hash mismatch, disk UID tamper, publish before reread, and capability reuse all returned `accepted=false`, `candidate_discarded=true`, `rollback_required=true` where applicable.
- Deterministic artifact digest: staged and `disk_reread` stages produce the same canonical artifact digest because stage is normalized before hashing.
- Harness quality witness values were signed non-orthogonality `0.0`, skewness `0.0`, family aspect ratio `1.0`, and positive measure `1.0`. These are transaction-boundary fixtures, not claims about actual mesh quality.

## Failures corrected during the card

1. The first focused run skipped because the intent extension was not built in the current CMake cache; the explicit intent target was configured and built.
2. BL=1 begin failed because a pybind11 conditional expression attempted to coerce a receipt string through `py::none()`. An explicit `if/else` assignment fixed the type boundary.
3. Fresh CMake verification initially lacked the pybind11 directory; rerunning with the installed `pybind11_DIR` completed and recorded the default-off cache value.

No actual Native Tet/Hex/Poly/Tri/Strict Quad/TRI+QUAD/surface writer artifact was produced by this card. Therefore no cell/face count, skewness, aspect-ratio, or non-orthogonality release claim is made.
