# Gate 3 dynamic marker triage L0 — 2026-07-31

## Stabilized markers

Three dynamic skip reasons were only reporting a path or a fixed bootstrap
state.  Their conditions and behavior remain unchanged; only their reason text
is made stable for the Gate 3 inventory.

- GUI visual baseline absent: bootstrap PNG is written, then rerun is required.
- Poly face geometry `cube.stl` absent: deterministic fixture precondition.
- Tet Phase G benchmark STL absent: deterministic fixture precondition.

No test body, fixture location, input, threshold, engine behavior, or routing
changes in this card.

## Exact retained DEFER

`tests/test_native_poly_facegeom.py:172` remains dynamic by design:
`cube_primal` skips only when its required native-Tet primal generation returns
failure or no tets.  The failure message is runtime evidence, not a static
fixture precondition.  Replacing it with a static reason would hide which
upstream Tet contract failed.

- Owner: native Tet topology-validation lane and native Poly face-geometry lane.
- Retest condition: `generate_native_tet(cube.stl, seed_density=10,
  target_cells=200)` succeeds with non-null tets, then run the face-geometry
  real-shape tests and Gate 3 marker inventory.
- Fail-closed rule: retain this DEFER until that normal-body validation passes;
  do not remove, weaken, or convert the skip into a pass.

## Result

Gate 3 marker inventory remains 96 rows.  Exact unresolved DEFER rows reduce
from 4 to 1.  Gate 3 remains not-PASS pending this retained upstream contract
and full automated validation evidence.
