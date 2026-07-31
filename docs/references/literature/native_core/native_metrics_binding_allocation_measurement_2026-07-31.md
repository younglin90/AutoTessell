# native_metrics Python-boundary allocation measurement — 2026-07-31

## Scope

`MEASURED / CORRECTNESS_KEEP`.  This card adds a benchmark and validity test
only.  It does not modify `native_metrics`, C++ algorithms, mesh output, or
third-party code.

## Method

`tests/bench_native_metrics_binding_allocation.py` calls the existing
`aabb_overlap_pairs` binding on 100,000 intentionally disjoint AABBs.  It uses
three equivalent inputs:

- C-contiguous `float64` baseline;
- strided `float64` input;
- C-contiguous `float32` input.

The binding declares `py::array_t<double, c_style | forcecast>` for both
arrays.  Each benchmark result records a median of nine calls and Python
`tracemalloc` peak bytes.  Inputs are compared byte-for-byte after every run;
the expected result has zero overlap pairs.

Run only against a known native build, for example:

```bash
AUTOTESSELL_EXT_BUILD_DIR=/path/to/auto_tessell_core/build \
python3 tests/bench_native_metrics_binding_allocation.py
```

## Observed sample

WSL Ubuntu, CPython 3.12, and the current external `native_metrics` build were
used for three 100,000-AABB samples (nine calls per layout).  The table reports
the median of those three samples.  The disjoint output contained zero pairs
for every layout, and neither input array changed.

| Input layout | Median call time | `tracemalloc` peak |
| --- | ---: | ---: |
| C-contiguous `float64` | 2.62 ms | 427 B |
| Strided `float64` | 7.64 ms | 4,800,522 B |
| C-contiguous `float32` | 1.90 ms | 4,800,522 B |

This is a single hardware-specific sample, not a release threshold.  The
strided and `float32` cases show materially higher Python-traced temporary
memory than the contiguous `float64` contract path.

## Interpretation limits

`tracemalloc` reports Python-traced allocation, not complete C++ allocator or
RSS usage.  It is useful for reproducible boundary comparison, but does not
prove the number of native allocations.  `forcecast` makes a copy *possible*
for strided/dtype-mismatched inputs; this benchmark must not be interpreted as
permission to remove coercion, relax dtype/layout contracts, or change output.

## Next decision

Use a separate refactor card only if repeated measurements show material
end-to-end cost on a representative mesh corpus.  That card must compare
contiguous `float64` input fast paths against the current fallback, measure
wall time and process peak RSS, preserve deterministic outputs, and retain a
safe coercion path for invalid layouts.
