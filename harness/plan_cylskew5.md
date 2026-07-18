# CARD CYLSKEW5 - Clean raw proxy retained as explicit opt-in

**Target engine:** native tet

## Empirical pivot

CYLSKEW4's raw-Delaunay proxy was dominated by zero-volume tetrahedra. Cylinder
OFF/ON raw skew was `3.93e28/5.56e28`, so the selector reverted even though the
forced final mesh improved from skew/non-orthogonality `44.9/89.2` to
`40.8/88.7`.

Filtering tetrahedra with
`abs(volume) > bbox_diag^3 * 1e-12` produced these measured proxy outcomes:

| Canonical case | OFF proxy | ON proxy | Decision |
|---|---:|---:|---|
| Cylinder | `69.47 / 88.80` | `69.47 / 88.80` | KEEP |
| Cube, N=500 | `2.38 / 61.87` | `8.23 / 80.94` | REVERT |
| Sphere, target=2000, edge `0.573-0.810` | OFF dominates | ON worsens | REVERT |

The proxy filter correctly identifies the cylinder candidate. Advisor E2E then
rejected default activation because the selected full seed set has no acceptable
speed/quality tradeoff:

| Cylinder variant | Cells | Skew / non-orthogonality | Time |
|---|---:|---:|---:|
| OFF | 1847 | `44.9 / 89.2` | `1.5s` |
| Full 66 seeds | 2296 | `40.8 / 88.7` | `4.6s` |
| Stride 2 / 3 / 4 / 6 / 8 | - | skew remains `44.944` | `1.73 / 1.56 / 1.45 / 1.42 / 1.46s` |

Full seeds cost about 3x. Subsampling recovers speed but loses the quality gain,
so no tested variant is a Pareto win. Cleaned proxy support remains available
only through explicit opt-in.

## Implementation contract

- `_raw_proxy_metrics` computes scale-relative tet volumes, excludes non-finite
  and near-zero tets, then calls the existing skew and non-orthogonality proxies.
- No valid tetrahedra, proxy exceptions, or non-finite metrics return an empty
  metric mapping. The existing monotone selector therefore reverts fail-closed.
- `AUTO_TESSELL_TET_OFFSET_RING=0/off/false` disables the feature.
- `AUTO_TESSELL_TET_OFFSET_RING=1/on/true` forces it regardless of input size.
- Unset disables the feature exactly, preserving the OFF seed path.
- Explicit `auto` enables it only for `V <= 1000` and `F <= 2000`. This bounds
  the offset generator's observed `O(V^2)` work while keeping activation
  intentional.
- Selection logs include mode, decision, OFF/ON raw and valid tet counts, and
  both metrics.

## Acceptance

- Focused unit tests prove zero-volume exclusion, empty/non-finite fail-safe
  behavior, unset-OFF behavior, exact mode aliases, forced size bypass, and
  inclusive explicit-auto caps.
- Canonical clean-proxy fixtures select cylinder KEEP and cube/sphere REVERT.
- Default behavior must match OFF. No default quality improvement is claimed.
- Long sphere E2E is intentionally excluded from this card.
- Existing selector tolerances and downstream meshing remain unchanged.

## Validation evidence

- Revised focused unit suite: `15 passed`.
- Cleaned proxy measurement with feature enabled: decision `KEEP`; OFF raw/valid
  tets `1228/1070`, ON raw/valid tets `1592/1418`.
- Advisor E2E rejected default activation: OFF was `1.5s`; full 66 seeds were
  `4.6s`; stride subsampling retained OFF skew. Unset therefore resolves to
  `off`, and CYLSKEW5 makes no default quality claim.
- Long sphere E2E was not run, per scope.
