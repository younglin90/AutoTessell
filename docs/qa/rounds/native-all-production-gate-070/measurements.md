# Round 070 measurements

## Card 070-A — actual persisted-child binding

Status: implementation and focused verification passed for the bounded
receipt-bound Tet route; release status remains `partial` because this test
uses a synthetic tetra receipt and does not establish CAD/STL corpus
authority.

| Gate | Result |
| --- | --- |
| Fresh C++ persisted-volume child on stage | PASS |
| Fresh C++ persisted-volume child after destination publish | PASS |
| Source boundary coverage and directed-cycle binding | PASS |
| Duplicate/non-manifold/inverted persisted topology | 0 / 0 / 0 |
| Minimum persisted Tet volume | `1/6` |
| Maximum aspect ratio | `1.4142135623730951` |
| Maximum non-orthogonality | `0.0` degrees |
| Maximum skewness | `0.47140452079103157` |
| Disk receipt graph `source_output_exact` | PASS |
| BL=0 requested/actual schedule | `0 / 0` |
| BL>=1 without writer-owned geometry | REFUSED (`positive_bl_child_requires_writer_geometry`) |

Focused command:

```text
PYTHONPATH=auto_tessell_core/build pytest -q \
  tests/test_native_tet_production_receipt_live.py \
  tests/test_native_tet_production_receipt_ingress.py \
  tests/test_native_tet_persisted_volume_child_cpp23.py \
  tests/test_native_tet_persisted_volume_aqte_binding_cpp23_v2.py
```

Result: `10 passed`.

## Failures corrected during the card

1. `seal_stage` initially failed because pybind11 could not convert a Python
   string directly to `std::filesystem::path`; a string-to-path wrapper was
   added and rebuilt.
2. The receipt graph oracle was not built in the focused build; the required
   `native_tet_receipt_graph` and `native_tet_receipt_graph_1_to_n` targets
   were built.
3. The post-publish audit reused the pre-publish stage pathname for the
   sidecar. The audit now rebinds the contract filename under the current
   stage/destination root, so the destination child is genuinely exercised.

## Explicit remaining evidence gap

The current v2 sidecar route records receipt-level source and semantic
digests, but the live fixture does not provide authoritative CAD/STL bytes,
feature/patch/component ledgers, or a positive boundary-layer writer ledger.
Therefore this card is not a release claim for Native Tet, surface meshing,
or any other native engine. Those routes remain follow-up cards.
