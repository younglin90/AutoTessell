# Native Hex build-contract local-front repair — L0

## Diagnosis

`native_hex_quality.local_front_numeric_admission` was already a real public
pybind symbol and an opt-in numeric cross-check for
`core/generator/native_hex/local_front_admission_l0.py`.  The source registered
it with `source_face_ids.noconvert()`, and the existing C++ contract test checks
`int64` and non-contiguous input rejection.  The shipped
`native_build_contract.json` omitted the symbol, making the exact ABI evidence
test fail.

## Narrow correction

Add the existing public symbol to the `native_hex_quality` contract.  No C++
algorithm, argument validation, data ownership, native opt-in setting, Python
routing, shell generation, mesh output, or third-party source changes.

## Evidence

- Baseline: `tests/test_native_build_evidence.py` failed only because
  `local_front_numeric_admission` was exposed but uncontracted.
- Post-correction: exact public-symbol contract test and the focused Hex
  local-front C++ tests pass after an explicit clean Release build.

This is ABI evidence alignment only.  It does not certify source geometry,
feature/patch provenance, product topology, target cell count, or boundary
layer output.
