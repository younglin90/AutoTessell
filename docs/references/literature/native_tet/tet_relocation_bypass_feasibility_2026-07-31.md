# Tet SSS pass-0 relocation bypass feasibility — 2026-07-31

## Scope

`MEASURED / DEFER`.  `tests/test_native_tet_relocation_bypass_feasibility.py`
temporarily monkeypatches only the first
`envelope_relocate._envelope_bounded_relocate` call.  `current` delegates to
the original function; `bypass` returns a copy of its pre-relocation points.
The patch is restored with `finally`.  No production, C++, routing, or
third-party file changes.

Fixture: `tests/benchmarks/sphere.stl`, target 2000, phase-B/phase-C/BSP/edge
recovery disabled.  Each mode ran in three independent subprocesses.

## Pass-0 evidence

| Metric | Current relocation | First-pass bypass |
| --- | ---: | ---: |
| Moved vertices | 636 | 0 |
| Maximum displacement | 0.0165498437 | 0 |
| Strict source audit before | PASS | PASS |
| Strict source audit after | FAIL | PASS |
| Missing source vertices after | 636 | 0 |
| Missing source faces after | 1280 | 0 |
| Unowned candidate faces after | 1280 | 0 |
| Inverted tets before/after | 350 / 352 | 350 / 350 |
| Same-side internal faces before/after | 116 / 108 | 116 / 116 |
| Mean shape quality before/after | 0.255975 / 0.257496 | 0.255975 / 0.255975 |
| Minimum shape quality before/after | 0.001569 / 0.000404 | 0.001569 / 0.001569 |
| Maximum aspect before/after | 662.613 / 2455.820 | 662.613 / 662.613 |

Relocation gains 0.001521 mean quality, but creates immediate strict-source
loss and worsens the worst quality/aspect metrics.  Bypass proves this first
call is the source-loss transition on this fixture.

## Final output evidence

| Metric | Current relocation | First-pass bypass |
| --- | ---: | ---: |
| Cells | 2164 | 2166 |
| Final mean quality | 0.258325 | 0.257465 |
| Final minimum quality | 0.009868 | 0.009659 |
| Final inverted tets | 0 | 0 |
| Final same-side internal faces | 108 | 108 |
| Strict-valid result | false | false |
| Writer artifact | false | false |

All three repeats produced identical point/tet hashes inside each mode.

## Decision

Do **not** change production policy to bypass pass-0 relocation.  Although the
bypass preserves source ownership at that immediate boundary, it leaves the
pre-existing invalidity and does not produce a strict-valid result or writer
artifact.  The current run also remains invalid.  A later card may only retain
this diagnostic as a localization proof; any production proposal needs a
separate mechanism that resolves the residual internal-face debt while keeping
the source audit PASS.
