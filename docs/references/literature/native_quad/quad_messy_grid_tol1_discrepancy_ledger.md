# QUAD-MESSY-GRID-TOL1: POSY discrepancy ledger

Status: `ABSTRACT_READ`, measured and report-only. No tolerance is defined in
this card.

Ray's public abstract says that extracting quads from a grid-preserving map is
straightforward in the ideal case, while practical inputs deviate from that
ideal. It motivates specifying those deviations and representing them as
operations on a discrete structure before designing a robust extractor. The
source is [Ray, *On Quad Mesh Extraction From Messy Grid Preserving Maps*]
(https://arxiv.org/abs/2507.15404). The paper's full text was not read for this
card; therefore no acceptance range is inferred from it.

## Scope and measurement contract

This card consumes the immutable `QUAD-POSY1` candidate ledger. It records
observations only:

- A **position singularity face** has at least one candidate whose rotated
  integer offsets have a non-zero regularity residual.
- A **position singularity candidate** is one such branch candidate. The
  residual is the exact integer 2-vector `(sum_x, sum_y)` already emitted by
  POSY; its L1 norm is recorded without a cutoff.
- A **branch offset** is the exact positive pairwise difference between the
  admissible orientation-index labels. The labels use quarter-turn units, so
  the explicit `(-2, +2)` representation of `-1/2` and `+1/2` has offset span
  `4`.
- A **branch loss** is an exact set difference between source-ledger branch
  labels and POSY candidate labels. For half-index branches, only labels `-2`
  and `+2` are counted. No branch is selected or repaired.

The ledger is not a tolerance test. It does not decide whether a map is
acceptable, and it does not implement extraction, integer balancing, SAT,
min-cost flow, inversion cleanup, or generation.

## Measured result

Configuration: the existing real STL assets, `n_sweeps=20`, `seed=0`, and the
QUAD-MULTIRES1 field (`multires=True`). `local integer L1` is the sum over all
candidate residuals; `max L1` is the largest candidate residual norm. `branch
span total` sums each face's branch span.

| Shape | Faces | Position-singularity faces | Position-singularity candidates | Local integer L1 | Max L1 | Branch entries | Branch span total / max | ±1/2 source faces | Expected / observed ±1/2 branches | ±1/2 branch loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cube | 12 | 12 | 16 | 39 | 4 | 4 | 4 / 1 | 0 | 0 / 0 | 0 |
| cylinder | 512 | 427 | 443 | 867 | 4 | 16 | 16 / 1 | 0 | 0 / 0 | 0 |
| bracket | 416 | 331 | 385 | 889 | 4 | 54 | 108 / 4 | 18 | 50 / 50 | 0 |

The bracket is the only measured asset with half-index source branches. All
36 expected `-2`/`+2` labels are present in the POSY candidates, so the
branch-option loss is measured as zero. Other branch labels on those same
faces are included in the general branch-entry count but not in this half-index
count. This is preservation of the audit
branch set, not resolution: the 18 half-index source faces remain unresolved,
and no positive `+1/2` branch is selected on their behalf.

The integer residual remains substantial in the same measurement: 331 of 416
bracket faces are position-singularity faces, with aggregate candidate L1
residual 889. These are measurements to carry into a future extraction study,
not a proposed tolerance or a reason to mutate the mesh.

## Repeatability and OFF behavior

`tests/test_native_quad_messy_grid_tol.py` verifies:

- a repeated bracket run produces equal frozen ledgers and identical protocol-5
  pickle bytes;
- synthetic `(-2, +2)` branches retain both labels, while a deliberately
  truncated candidate view reports the exact missing label;
- default POSY-OFF and explicit `AUTO_TESSELL_QUAD_POSY1=0` preserve identical
  remesh vertex and face bytes.

The discrepancy view has no production caller. Existing quad extraction,
generation, fallback, and remesh behavior are unchanged.
