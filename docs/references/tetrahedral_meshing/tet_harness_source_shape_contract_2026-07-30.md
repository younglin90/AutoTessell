# Native Tet Harness Source-Shape Contract — 2026-07-30

## Card

`TET-HARNESS-SOURCE-SHAPE-FAIL-CLOSED-1`

Primary metric: a harness-success result must have a freshly measured final
source-surface contract, not only a strict writer success or a viable
non-orthogonality value.

## Decision

`NativeTetResult` source metrics are produced before later local mutators,
duplicate-tet cleanup, orientation validation, and final polyMesh sync.  The
harness therefore remeasures its final `tet_points`/`tets` using existing
`measure_source_surface_metrics` before evaluator/best-case/copy handling.

- missing arrays, measurement exception, non-finite, or sentinel-like negative
  metrics: reject with a fixed reason;
- normalized symmetric Hausdorff: `<= 0.05`, matching the standard evaluator;
- repeated-coplanar source groups only: plane and area coverage each `>= 0.80`,
  matching the native-tet B-grade contract;
- non-planar source: no plane-coverage floor; finite final measurement and the
  Hausdorff contract still apply;
- rejected candidate: delete its temporary case, do not invoke the checker,
  do not replace a prior source-valid best, and do not copy output.

No topology rule, geometry repair, target-cell rebudgeting, or boundary-layer
behavior changes in this card.

## L1 cube evidence

Input: `tests/benchmarks/cube.stl`; draft harness; `target_cells=500`;
`seed_density=10`; `sliver_quality_threshold=0.02`; `max_iter=1`.

| metric | result |
|---|---:|
| strict final writer | accepted |
| candidate cells / points | 763 / 189 |
| final relative Hausdorff | 0.049830696267310334 |
| final plane coverage | 0.0 |
| final plane-area coverage | 0.6933725645168424 |
| harness result | rejected: `planar_source_coverage_below_b_grade` |
| copied case output | 0 entries |

The target is `+52.6%` high and remains a deferred Gate-6 issue.  This card
does not reinterpret that target error as a source-shape pass.

## Verification

L0 mock coverage proves: stale-good `NativeTetResult` fields cannot override
bad final remeasurement; unavailable, exception, non-finite, Hausdorff, and
planar-coverage failures reject; non-planar source avoids the planar-only
floor; an only-invalid candidate leaves no output; and a later invalid
candidate cannot replace a prior source-valid best.

```bash
python3 -m pytest -q tests/test_native_tet_harness.py -k 'source_shape_contract or source_invalid_candidate or prior_source_valid_best'
```

Focused source/topology bundle:

```bash
python3 -m pytest -q tests/test_native_tet_rescue_gate.py tests/test_native_tet_result_consistency.py tests/test_native_tet_harness.py -k 'not harness_hits_target_cells_at_draft_max_iter_1'
```

Result: `30 passed, 1 deselected in 37.15s`.

The excluded target contract was also run and failed at `3579 / 2000 = 1.7895`
outside its `[0.75, 1.45]` band.  It is recorded as deferred Gate-6 evidence:
this card neither changes its rebudget mechanism nor loosens its assertion.

## Sources and provenance

- `core/evaluator/report.py`: existing standard `hard_hausdorff = 0.05`.
- `core/generator/native_tet/mesher.py`: existing B-grade `0.80` plane and
  area thresholds.
- `core/generator/native_tet/surface_transaction_gate.py`: existing final
  source-metric measurement implementation.

Independent integration only; no external or third-party code was copied.
