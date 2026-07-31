# TET-CVT-ROLLBACK-FEASIBILITY-L1

Date: 2026-07-31
State: `L1_PASS / CORRECTNESS_KEEP`; test instrumentation only.

## Hypothesis

An unchanged CVT invocation can be inspected in an isolated subprocess to
determine whether its exact pre-CVT arrays are already source-preserving and
strict-writer eligible, and whether its exact post-CVT candidate remains so.
The comparison must not select the pre-CVT arrays as a runtime fallback.

## Evidence contract

For every observed CVT call, this card records exact C-order point/tet hashes,
strict same-side and ambiguity debt, source-face preservation, component
bijection, and the existing `audit_tet_boundary(...).valid` result.  The
report-only `strict_writer_eligible` field means existing boundary validity,
component bijection, and source-face preservation hold.  It is not a writer
invocation, success certificate, or relaxed acceptance rule.

The test patches `cvt3d.lloyd_cvt_3d` only inside its own subprocess.  It takes
pre-call copies, calls the original function unchanged, then compares those
copies to the original returned candidate.  Generator decisions, strict
refusal, writer behavior, transactions, routing, thresholds, and target policy
remain untouched.

## Result interpretation

`source_preserving_pre_cvt_candidate_exists=true` is evidence only: it says an
exact pre-CVT snapshot passes the stated existing report predicate.  It never
authorizes rollback, output, relaxation, or fallback.  Any unavailable CVT
call, invalid candidate, ambiguous comparison, timeout, or failed generator
result remains `DEFER` for implementation work.

Cube and sphere run three isolated repeats with existing 2,000-cell settings.
All runs must preserve failure and zero `constant/polyMesh` artifact.  No
release, quality, target-cell, boundary-layer, or repair claim follows.

## Provenance and rollback

The design extends existing AutoTessell strict-audit provenance diagnostics;
no external code is copied.  Remove this card if it observes or mutates a
different CVT call, labels a failed candidate eligible, changes original call
arguments/results, or changes writer/refusal behavior.
