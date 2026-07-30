# Common first-failure CVT wiring validation

Date: 2026-07-31

Card: `COMMON-FIRST-FAILURE-CVT-WIRING-1`

Promotion state: `CORRECTNESS_KEEP`. This card changes one stale test only. It
does not change production code, mesh output, thresholds, routing, dependencies,
or `third_party/`.

## Bounded baseline

The current `e23bab67` head reproduced the known low-cost failures with one
thread per numerical library:

- `tests/test_native_boolean_families.py`: `5 failed` in `2.46 s`;
- WildMesh draft parameters: `stop_quality=10`, stale expectation `20`;
- WildMesh annular axis section: `usable_count=0`, expectation `3`;
- `test_p4c_fallback_monotone_guard_wired`: failed because `_accept_fb` no
  longer exists;
- Boolean E2E: eight tests collected, not executed because the known timeout is
  outside this bounded first-failure card.

The deterministic CVT failure was selected first because it is the smallest
root cause and requires no production change. Git history shows the failing
source-string assertions came from April commit `6c9990002`. The hardened
`_p4c_candidate_meets_acceptance_l0` helper and call wiring were added and
strengthened in July (`fee82ef19`, `6ce92dd04`, `61d91e44`, `7d5d513c`).

## Root cause and change

The old test searched the complete module text for local variable
`_accept_fb`, an inline quality comparison, and an inline cell-count floor.
Production now routes the candidate through a stronger helper that requires:

1. exact source-vertex presence;
2. exact source-component/topology preservation;
3. strict mean-quality improvement;
4. `max(50, old_cell_count // 4)` candidate cell floor.

The behavioral L0 suite already covers accepted and rejected source/topology
cases. The stale wiring test now uses Python AST and `inspect.signature` to
verify the helper signature, exact source/candidate array arguments, quality
and cell-count keyword wiring, assignment to `_accept`, and the same value in
the tier log. It no longer depends on whitespace or line wrapping.

## Acceptance and rollback

- focused formerly failing node: `1 passed`, repeated three times;
- hardened behavioral L0: `7 passed`;
- complete CVT plus behavioral L0: `74 passed`;
- changed-range Black: PASS;
- changed-region Ruff: no finding; the file retains unrelated legacy import
  ordering findings outside this function;
- `git diff --check`: PASS;
- production and `third_party/` diffs: empty.

Rollback conditions: any production or threshold change, deletion or skipping
of the original test, loss of source/topology/cell/quality wiring assertions,
behavioral L0 regression, or new CVT-file failure.

The two WildMesh failures, five Boolean-family failures, and Boolean E2E timeout
remain visible follow-up cards. No release gate is promoted by this change.
