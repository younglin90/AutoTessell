# Gate 3 native Poly dual marker triage L0 — 2026-07-31

## Scope

Four `tests/test_native_poly_dual.py` skip branches already used the
deterministic `SPHERE_STL.exists()` fixture precondition.  This card changes
only their skip text to
`sphere.stl missing: deterministic native-poly-dual fixture precondition`.

Test body, fixture path, input, threshold, engine behavior, routing, and
coverage remain unchanged.

## Result

Gate 3 marker inventory remains 96 rows.  Exact unresolved DEFER rows decrease
from 8 to 4.  Gate 3 remains not-PASS until every remaining DEFER row has an
explicit validated disposition and full automated validation evidence.

## Owner and retest

- Owner: native Poly dual release-validation lane.
- Retest: run the four node tests with `tests/benchmarks/sphere.stl` present,
  then run `tests/test_gate3_marker_inventory.py`.
- Rollback: restore only these reason strings if fixture detection becomes
  non-deterministic; do not weaken or remove the tests.

## Validation observation

The marker-inventory test passes.  With `sphere.stl` present, all four focused
dual tests enter their normal bodies and currently fail upstream at
`generate_native_tet`: `native_tet source_topology_rejected`.  This result is
outside this reason-only card: no skip branch executes, and the card changes no
tet, dual, fixture, or assertion behavior.  Keep Gate 3 DEFER and retest after
the Tet topology-validation lane restores this baseline.
