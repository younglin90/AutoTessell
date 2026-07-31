# Tet whole-SSS bypass feasibility — 2026-07-31

## Scope

`MEASURED / DEFER`.  Test-only workers set
`AUTO_TESSELL_P3_SSS_REVIVAL=0` and compare with explicit current mode (`=1`)
on the sphere fixture.  No production source, algorithm, threshold, writer,
routing, C++, or third-party code is changed.

Fixture: `tests/benchmarks/sphere.stl`, target 2000, phase-B/phase-C/BSP/edge
recovery disabled.  Three isolated runs per mode produced identical full JSON
evidence hashes within each mode.

## Evidence

| Metric | Current SSS | Whole SSS disabled |
| --- | ---: | ---: |
| First source-audit failure | `post_sss_pass0_relocate_pre_accept` | none through `pre_cvt3d` |
| Final cells | 2164 | 2166 |
| Final mean shape quality | 0.258325 | 0.257465 |
| Final minimum shape quality | 0.009868 | 0.009659 |
| Final inverted tets | 0 | 0 |
| Final same-side internal faces | 108 | 108 |
| Strict-valid result | false | false |
| Writer artifact | false | false |

Whole SSS disabling avoids the observed source-provenance transition, but it
does not remove the residual strict internal-face debt or create a writable
mesh.  It also lowers final mean and minimum quality on this fixture.

## Decision

Do **not** change production policy to disable SSS.  This is localization
evidence only.  Any later repair must preserve the source audit while resolving
the remaining 108 same-side internal faces and retaining valid quality.
