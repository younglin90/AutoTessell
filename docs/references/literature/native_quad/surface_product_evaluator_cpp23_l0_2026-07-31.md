# Native surface product evaluator — L0 C++23 card

## Scope

- Hypothesis: a C++23, no-copy reader can deterministically classify immutable
  triangle `(T, 3)` and quad `(Q, 4)` topology locally as `tri`, `quad`,
  `tri_quad`, or `invalid` while preserving every caller buffer byte.
- Primary metric: exact, repeatable local classification for valid immutable
  topology arrays and `invalid` for locally malformed rows.
- Acceptance: three identical reports for each local class; no input mutation;
  duplicate or out-of-range labels never become locally valid.  Product
  acceptance remains fail-closed.
- Rollback: remove this isolated default-OFF target if an explicit target build
  fails or any input is copied, converted, routed, repaired, or written.

## Contract and provenance

`native_surface_product` is a first-party independent implementation.  It uses
only C++23 standard-library views and pybind11's public NumPy binding API; no
external mesher code, generated mesh, or GPL/AGPL engine implementation is
copied.  Its explicit contract is
`auto_tessell_core/native_surface_product_build_contract.json`.

The CMake option `BUILD_NATIVE_SURFACE_PRODUCT` is `OFF` by default.  The target
is deliberately absent from the shipped first-party wheel inventory.  There is
no Python import, routing, default, fallback, mesh mutation, geometry repair,
or writer integration in this card.

## Deliberately relaxed strictness

L0 checks only what immutable face-array topology can prove locally:

- exact `int64`, read-only, C-contiguous shape `(T,3)` / `(Q,4)`;
- non-negative, in-range labels;
- distinct labels inside every triangle or quad row.

It does **not** claim or certify global manifoldness, orientation,
surface-envelope preservation, feature preservation, patch or physical-group
provenance, planarity, or mesh validity.  Every report therefore has
`product_accepted=false` and
`product_rejection=source_product_certificate_required`.  A future integration
must supply and verify a complete source-product certificate before it can
promote a product or relax any shape-preservation gate.

## Verification

L0 tests cover each class, empty/duplicate/out-of-range rejection, wrong dtype,
writable and non-contiguous arrays, byte preservation, and three-run report
determinism.  An explicit Release build uses only:

```bash
cmake -S auto_tessell_core -B /tmp/autotessell-surface-product-release \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_NATIVE_SURFACE_PRODUCT=ON
cmake --build /tmp/autotessell-surface-product-release --target native_surface_product -j2
AUTOTESSELL_SURFACE_PRODUCT_BUILD_DIR=/tmp/autotessell-surface-product-release \
  python -m pytest -q tests/test_native_surface_product_evaluator_cpp23.py
```

No target-cell or boundary-layer behavior is changed or claimed by L0.
