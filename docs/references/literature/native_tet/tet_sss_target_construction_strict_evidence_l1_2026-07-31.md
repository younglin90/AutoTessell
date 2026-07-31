# Tet SSS target-construction strict evidence L1 — 2026-07-31

## Scope

`MEASURED / CORRECTNESS_KEEP`.  This card adds two pass-0 observer checkpoints
only: `sss_pass0_pre_quality` and `sss_pass0_post_target_construction`.  Both
report the unmodified candidate point/tet arrays.  No relocation policy,
quality threshold, topology operation, writer, routing, C++ code, or
third-party code changes.

## Three-repeat sphere evidence

Fixture: `tests/benchmarks/sphere.stl`, target 2000, phase-B/phase-C/BSP/edge
recovery disabled.  In all three independent runs:

| Checkpoint | Inverted tets | Same-side internal faces | Strict source audit |
| --- | ---: | ---: | --- |
| `sss_pass0_pre_quality` | 350 | 116 | PASS |
| `sss_pass0_post_target_construction` | 350 | 116 | PASS |
| `pre_sss_pass0_relocate` | 350 | 116 | PASS |
| `post_sss_pass0_relocate_pre_accept` | 352 | 108 | FAIL |

Target construction does not create the first strict-source loss.  The first
observed loss remains the post-relocation candidate checkpoint.  This evidence
does not authorize a relocation bypass or any production policy change.
