# POLY-L3-IMMUTABLE-SHARDED-CORPUS-1 Evidence

Date: 2026-07-31

Status: runner implementation; actual four-shard campaign execution is
deliberately deferred to the parent validation lane after a system-load check.

## Scope and hypothesis

The native-poly regression family currently collects 26 test modules and 225
pytest node IDs.  Prior aggregate runs exceeded 300 seconds and could leave
child processes alive after the controlling shell timed out.  A historical
sphere-only dual test needed 171.34 seconds.  Those failures made an aggregate
timeout ambiguous: later modules had no result, and a single slow process hid
the rest of the corpus.

This card adds validation infrastructure only.  It does not change mesh code,
test thresholds, fixtures, routing, dependencies, or `vendor/dependencies/`.  The
runner fixes a clean Git HEAD and tree, collects the unchanged tests, assigns
modules to stable shards, and executes every module in its own POSIX process
group.  A timeout kills that process group, records `timeout`, and continues
with the next module.  Shard merging rejects any HEAD/tree mismatch, missing or
duplicate shard, missing or duplicate module, node-ID gap, count mismatch, or
unknown result classification.

Primary metric: `accounted collected node IDs / collected node IDs`.  The
acceptance target is `225 / 225 = 100%` on one immutable HEAD/tree.  Accounting
success is not release success: `failed`, `timeout`, `runner_error`,
`process_leak`, `xpassed`, `skipped`, or `passed_with_skips` keeps the merged
L3 result false.  Only all-module `passed` permits `release_pass=true`.

## Fail-closed contracts

- Refuse a dirty repository before collection or execution.
- Verify HEAD, tree, and clean tracked/untracked state before and after every
  module.
- Force `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, and
  `MKL_NUM_THREADS=1`.
- Preserve module-scoped fixtures by isolating at module granularity rather
  than rerunning every node separately.
- Use a 240-second default module timeout.  This does not weaken a test: any
  timeout is a failing classification and remains visible in merged evidence.
- Request pytest's exact `-rX` summary and record anchored `XPASS` node IDs.
  JUnit's normal pass counters alone cannot distinguish a non-strict XPASS;
  any detected XPASS is therefore a release-failing `xpassed` classification.
- Store generated manifests and shard evidence only under ignored
  `autoresearch-results/poly-l3/`.
- Exclude only the runner's own synthetic contract test from the product corpus
  to prevent recursive self-execution.  All declared native-poly,
  native-polymesh, tier-native-poly, and Poly boundary-layer module families
  are discovered automatically.

## Verification plan

The focused synthetic suite covers clean/dirty/head-move identity checks,
whole-process-group timeout cleanup, PASS/FAIL/TIMEOUT/SKIP/error
classification, real non-strict XPASS rejection, duplicate and missing shards,
duplicate and missing node IDs, identity drift, discovery, and collection gaps.

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  ../AutoTessell/.venv/bin/python -m pytest -q \
  tests/test_native_poly_l3_corpus_runner.py

../AutoTessell/.venv/bin/python scripts/run_native_poly_l3_corpus.py \
  --collect-only

# Parent validation lane schedules these one at a time after checking load.
../AutoTessell/.venv/bin/python scripts/run_native_poly_l3_corpus.py \
  --shard-index 0 --shard-count 4 --timeout-sec 240

../AutoTessell/.venv/bin/python scripts/run_native_poly_l3_corpus.py \
  --merge autoresearch-results/poly-l3/shard-*.json
```

## Promotion boundary

The runner may land as `L0_PASS / CORRECTNESS_KEEP` after focused synthetic
tests and immutable-head collection pass.  It cannot promote native-poly to L3
or release-ready status until all four real shards run at the same HEAD/tree,
merge with 100% node accounting, and contain only `passed` modules.  Existing
shape, topology, validity, provenance, target-cell, and boundary-layer gates
remain unchanged.
