# Gate 3 marker inventory — L0 DEFER

Scope: native tet / hex / poly / tri / quad / surface product, native routing,
CLI, desktop, GUI, Qt, and UI test files selected by the ledger's glob set.

The deterministic AST inventory currently records 96 explicit skip/xfail/flaky
markers. Its canonical SHA-256 and the exact list of 21 unexplained markers are
in `tests/gate3_marker_defer_l0.json`.

Gate 3 status for this slice is **DEFER**, not PASS. The 21 deferred rows are:

- `tests/test_native_hex.py`: 8 `pytest.skip` calls with no explicit reason.
- `tests/test_native_poly.py` and `tests/test_native_poly_dual.py`: 9
  `pytest.skip` calls with no explicit reason.
- `tests/test_gui_visual.py`, `tests/test_native_poly_facegeom.py`, and
  `tests/test_native_tet_phaseG.py`: 4 dynamic reasons that cannot be audited
  statically.

The inventory test fails closed if any marker, location, marker reason, or
scope changes. This card does not weaken, delete, or alter any existing test.
Future cards must either replace each deferred marker with verified coverage or
record a stable explicit reason and update the ledger under review.
