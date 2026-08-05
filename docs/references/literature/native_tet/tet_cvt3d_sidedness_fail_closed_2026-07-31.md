# CVT3D Strict-Topology Fail-Closed Transaction

Date: 2026-07-31

Card: `TET-CVT3D-SIDEDNESS-FAIL-CLOSED-1`

## Defect and narrow hypothesis

The JJ3 transaction already rolls back its own unsafe smoothing candidate.
Tracing the next persistent topology transition on the frozen native cube
showed that the first `lloyd_cvt_3d` candidate can remove degenerates and
ambiguity while introducing definite same-side internal faces.  Quality gain
cannot pay for a strict topology regression.

The implementation therefore treats each accepted CVT output, including the
optional quality-weighted second pass, as an atomic candidate.  It commits
only when both same-side and ambiguous internal-face debts independently do
not increase.  An unsafe candidate returns the exact pre-CVT array objects
and immediately returns a failed `NativeTetResult`.  No later mutation,
writer invocation, repair, source movement, threshold change, or cell
deletion is allowed on that path.

## Frozen cube, target 2,000

At the first CVT transition:

| metric | pre-CVT | CVT candidate | returned result |
| --- | ---: | ---: | ---: |
| points | 300 | 300 | 300 |
| cells | 1,286 | 1,286 | 1,286 |
| same-side internal faces | 0 | 4 | 0 |
| ambiguous internal faces | 20 | 0 | 20 |
| degenerate tets | 5 | 0 | 5 |
| inverted tets | 34 | 34 | 34 |
| polyMesh artifact | 0 | not written | 0 |

The candidate is rejected because `0 -> 4` same-side faces violates the
independent nonincrease rule.  It is a truthful strict-topology refusal, not
a valid mesh claim.  Requested-cell tracking remains deferred behind topology.

## Canonical checks

- L0 hand-built two-tet cavity: unsafe geometry-only candidate rolls back the
  exact pre-candidate objects and SHA-256; safe candidate commits its exact
  objects.
- L1 cube target 2,000: exact report is `same 0 -> 4`, `ambiguous 20 -> 0`,
  `degenerate 5 -> 0`, `n_moved=411`; no writer artifact.
- L1 cube target 10,000: CVT candidate `same 4 -> 12`, `ambiguous 128 -> 0`,
  `degenerate 32 -> 0` rolls back and stops before `post_nnn_cvt`.
- L1 cylinder target 2,000: three deterministic runs remain valid with
  353 points, 1,140 cells, zero same-side/ambiguous/duplicate/non-manifold/
  inverted/degenerate counts and unchanged point/connectivity hashes.
- L1 sphere: the non-worsening CVT candidate remains on its existing
  fail-closed strict-topology route; no new regression in the focused suite.

Focused command:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /home/younglin90/work/claude_code/AutoTessell/.venv/bin/python -m pytest -q \
  tests/test_native_tet_cvt3d_sidedness_transaction.py \
  tests/test_native_tet_result_consistency.py \
  tests/test_native_tet_final_strict_topology_checkpoint.py
```

Result: `7 passed in 51.47s`.

## Research and provenance

WildMeshing Toolkit's documented per-operation invariants and rollback model
remain reference-only (MIT, https://github.com/wildmeshing/wildmeshing-toolkit).
CGAL's tetrahedral-remeshing validity requirements remain reference-only
(GPL, https://doc.cgal.org/latest/Tetrahedral_remeshing/index.html).  The
implementation is a project-local composition of the existing internal-face
audit; no external code or dependency was copied, and `vendor/dependencies/` is
unchanged.

## Promotion and remaining blocker

Status: `L1_PASS / CORRECTNESS_KEEP`.  This is safety infrastructure, not a
quality or target-cell solver.  Cube's pre-CVT mesh still has 5 degenerates,
34 inverted tets, and 20 ambiguous faces; it is correctly refused.  The next
card must address one earlier representation or local validity mechanism
without weakening the independent strict topology contract.
