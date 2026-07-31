# Native tri / quad / tri-quad build inventory — L0

## Clean-install C++23 inventory

The `AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE=ON` profile installs exactly the
eight targets in `native_build_contract.json`:

| Product evidence | Installed C++23 module | Public diagnostic |
| --- | --- | --- |
| triangle source topology | `native_metrics` | `triangle_surface_topology_audit` |
| strict fixed-vertex quad pair | `native_metrics` | `strict_quad_pair_preflight` |
| common native validity/quality support | `native_bl`, `native_hex_quality`, `native_polymesh`, `native_snap`, `native_surface_padding`, `native_tet_predicates`, `native_tet_qopt` | ABI ledger in `native_build_contract.json` |

## Runtime-disconnected diagnostic

`native_surface_product` is the only current report-only tri/quad/tri-quad
diagnostic target. Its separate contract records `shipping=false` and
`runtime=report_only_default_off`. The target remains
`BUILD_NATIVE_SURFACE_PRODUCT=OFF`, is absent from the install/evidence target
list and wheel CMake definitions, locally classifies immutable topology only,
and always returns `product_accepted=false`. It is not product acceptance
evidence.

## Fail-closed evidence

`tests/test_native_product_build_inventory.py` requires the CMake first-party
target set to equal the exact eight-module ABI contract and rejects inclusion
of the runtime-disconnected diagnostic in either the install list or wheel
profile. The staged-install verifier then proves the resulting eight regular
binaries, ABI, hashes, and source identity.
