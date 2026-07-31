# CAD XDE Metadata Authority — 2026-07-31

## Card

- Lane: common CAD ingress; contract/test only.
- Primary metric: explicit XDE face-layer coverage on an authoritative runtime
  fixture.
- Baseline: 0/6 faces.
- Acceptance: 6/6 faces; legacy `(vertices, faces)` exact; colors remain display
  metadata; assembly paths remain identity metadata; physical-group and boundary-
  condition authority remain false.
- Rollback: geometry/order/color-derived semantic labels, ambiguous face mapping,
  missing explicit layer treated as known, production routing, meshing/writer
  behavior, committed generated STEP binary, or `third_party/` change.

## Runtime and corpus diagnosis

Installed OCP 7.8.1.1 exposes `STEPCAFControl`, `TDocStd`, and `XCAFDoc` name,
layer, color, shape, and assembly APIs. The existing six STEP fixtures each
contain one generic translator root and no assembly, subshape label, layer, or
color metadata. They therefore remain semantically unknown.

No external binary fixture is committed. Tests build small OCP shapes in memory,
write STEP to pytest `tmp_path`, read them through XDE, and discard them with the
temporary directory.

## Authoritative runtime fixtures

Styled box:

- B-Rep faces: 6
- explicit named XDE layers recovered: 6/6
- XDE surface colors recovered: 6/6
- face-level names recovered: 0/6
- layer authority: true
- physical-group/BC authority: false

Named two-part assembly:

- assembly roots: 1/1
- component instance identities: 2/2
- referred part identities: 2/2
- face assembly-path coverage: 12/12
- assembly identity authority: true
- physical-group/BC authority: false

The STEPCAF round trip does not preserve the generated face-level names in this
configuration. The contract therefore leaves them unknown. A color is
authoritative display metadata only. A named XDE layer is authoritative grouping
metadata, but it is not a wall/inlet/outlet/physical-group declaration. Promotion
requires a separate explicit user or importer mapping contract.

## Contract result

The optional provenance payload adds per-B-Rep-face layer sets, surface colors,
and assembly paths with independent authority flags and a deterministic metadata
hash. It traverses XDE and the B-Rep from the same STEPCAF transfer and maps by
actual OCP shape identity. It never maps labels from geometry or traversal order.
Any incomplete or ambiguous labeled-face mapping fails closed.

## Adverse XDE authority fixtures

Runtime `tmp_path` STEP fixtures exercise the XDE reader's error branches
without committing a generated CAD binary.  A narrow OCP monkeypatch injects
only the adverse metadata relation after the ordinary writer has produced the
source file:

- an XDE face label resolving outside the B-Rep face map;
- two distinct explicit layer declarations for one B-Rep face;
- two conflicting surface colors for one B-Rep face;
- two assembly identities resolving to the same B-Rep face; and
- a component with no referred shape.

Each case raises its specific `ValueError` before a provenance payload is
returned.  The legacy `load_cad_native` vertex and triangle arrays are compared
before and after the rejected optional traversal and remain exact.  Layer
membership is now fail-closed on conflicting repeated declarations; it never
selects one declaration by traversal order.  Physical-group authority remains
false in every accepting and rejecting path.

Legacy `load_cad_native(path, fmt) -> (V, F)` remains unchanged. The optional
payload stays disconnected from production routing, meshing, writers, patch
assignment, target-cell control, and boundary-layer generation.

## Reproduction

```bash
pytest -q tests/test_cad_xde_physical_authority.py -o addopts='' \
  --disable-warnings --maxfail=1
pytest -q tests/test_native_hex_cad_front_contract.py \
  tests/test_cad_reader_native.py -o addopts='' \
  --disable-warnings --maxfail=1
git diff --check
```
