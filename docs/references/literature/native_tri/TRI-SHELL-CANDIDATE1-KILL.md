# TRI-SHELL-CANDIDATE1 — KILL record

Date: 2026-07-26
Status: **killed; no production change retained**

## Decision

The candidate was a deterministic static AABB BVH for the existing shell
provenance query. It re-applied the legacy AABB predicate to the broad-phase
leaf set and sorted source-face indices, so its candidate tuples, source
payload attribution, ambiguity handling, projection coordinates, and report
values were bit-exactly equivalent to the existing brute-force path on the
verification corpus. It was nevertheless slower on every required fixture.

The implementation, tests, and temporary benchmark harness were removed after
the measurement. There is no `AUTO_TESSELL_TRI_SHELL_CANDIDATE1` production
flag and the existing brute-force candidate scan remains unchanged. Shell
checkpoint containment and all transaction semantics are therefore untouched.

## Measurement

WSL2 Ubuntu, Python 3.12, one process, three timed query repeats per fixture;
the reported query value is the median full face-centroid provenance census.
Shell construction was measured separately. The cylinder used the established
`local_scale_fraction=0.2`; cube and sphere used `0.5`.

| Fixture | V / F | Brute query (s) | Indexed query (s) | Brute / indexed | Candidate sets | Attribution | Repeat |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| cube | 8 / 12 | 0.009166 | 0.009695 | 0.945x | exact | exact | exact |
| cylinder | 66 / 128 | 0.112518 | 0.126529 | 0.889x | exact | exact | exact |
| sphere | 642 / 1280 | 1.266975 | 1.394708 | 0.908x | exact | exact | exact |

All three indexed reports matched the brute-force reports, including mapped,
ambiguous, and unmapped counts. The indexed report repeated value-identically
for all timed repeats. Because no real speedup was measured, the candidate is
rejected under the native-tri measurement-first rule rather than retained as
unexercised complexity.

## Verification

The candidate equivalence suite passed 26 tests before rollback. After removal,
the retained native-tri and Shewchuk predicate regressions must remain the
acceptance check for this KILL record:

```text
python3 -m pytest -q tests/test_native_tri_operator_loop.py \
  tests/test_native_tri_shell_provenance.py tests/test_predicates.py \
  tests/test_predicates_exact.py tests/test_predicates_insphere.py \
  tests/test_predicates_staged.py tests/test_shewchuk_predicates.py
```
