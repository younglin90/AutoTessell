# Gate 3 native Hex marker triage L0 — 2026-07-31

## Scope

`tests/test_native_hex.py` had eight `pytest.skip()` calls with no reason.
Each already had a deterministic fixture-presence precondition:

- `SPHERE_STL.exists()` for `sphere.stl` tests.
- `CUBE_STL.exists()` for `cube.stl` tests.

This card changes only the skip text.  Test body, fixture path, input, threshold,
engine behavior, routing, and coverage are unchanged.

## Result

Every affected branch now reports an explicit, stable reason:

- `sphere.stl missing: deterministic native-hex fixture precondition`
- `cube.stl missing: deterministic native-hex fixture precondition`

Gate 3 marker inventory remains 96 rows.  Exact unresolved DEFER rows decrease
from 21 to 13.  Gate 3 remains not-PASS until every remaining DEFER row has an
explicit validated disposition and full automated validation evidence.

## Owner and retest

- Owner: native Hex release-validation lane.
- Retest: run the eight node tests with both benchmark fixtures present, then run
  `tests/test_gate3_marker_inventory.py`.
- Rollback: restore only these reason strings if fixture detection becomes
  non-deterministic; do not weaken or remove the tests.
