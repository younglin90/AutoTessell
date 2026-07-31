# Gate 3 native Poly marker triage L0 — 2026-07-31

## Scope

Five `tests/test_native_poly.py` skip branches already used the deterministic
`SPHERE_STL.exists()` fixture precondition.  This card changes only their skip
text to `sphere.stl missing: deterministic native-poly fixture precondition`.

Test body, fixture path, input, threshold, engine behavior, routing, and
coverage remain unchanged.

## Result

Gate 3 marker inventory remains 96 rows.  Exact unresolved DEFER rows decrease
from 13 to 8.  Gate 3 remains not-PASS until every remaining DEFER row has an
explicit validated disposition and full automated validation evidence.

## Owner and retest

- Owner: native Poly release-validation lane.
- Retest: run the five node tests with `tests/benchmarks/sphere.stl` present,
  then run `tests/test_gate3_marker_inventory.py`.
- Rollback: restore only these reason strings if fixture detection becomes
  non-deterministic; do not weaken or remove the tests.
