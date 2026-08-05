# Native metrics build-contract audit repair — L0

## Diagnosis

The exact public-pybind ABI scanner found two public functions in
`native_metrics_bind.cpp` that were missing from the shipped ABI ledger:

- `triangle_surface_topology_audit`
- `strict_quad_pair_preflight`

Both are active opt-in C++23 cross-checks with existing focused parity tests.
They strictly require C-contiguous `float64` / `int64` inputs through their
pybind `noconvert()` arguments.  Source inspection found no ABI, validation,
or ownership defect; the contract alone was stale.

## Narrow correction

Add the existing two public symbols to `native_metrics` in
`native_build_contract.json`, plus a static regression that records their
strict no-conversion binding.  No native algorithm, Python route/default,
output, mesh data, or `vendor/dependencies/` source changes.

## Evidence scope

The correction makes the release ABI ledger truthful.  It does not alter the
default-OFF policy or independently certify shape preservation, provenance,
target cell count, boundary layers, or any generated mesh product.
