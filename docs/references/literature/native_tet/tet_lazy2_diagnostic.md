# TET-LAZY-2: read-only lazy-flip diagnosis

Status: diagnostic-only, default OFF, serial and deterministic.

## Scope

This card measures the frozen-boundary portion of Dassi et al., *Tetrahedral
mesh improvement using moving mesh smoothing, lazy searching flips, and RBF
surface reconstruction* ([arXiv:1703.07007](https://arxiv.org/abs/1703.07007),
2017 preprint / 2018 journal publication). It uses the existing native-tet
`general_edge_removal(..., exhaustive=False)` helper as the smallest candidate
generator. No production mesher wiring, surface vertex position, boundary
projection, RBF reconstruction, or parallel path is involved.

The diagnostic enumerates sorted interior edge rings, simulates each candidate
on a private tet-array copy, and records the local cavity before and after. It
alternates Dassi's two criteria by round:

1. angle round: improve the cavity minimum dihedral and reduce the cavity
   maximum dihedral without regressing either;
2. aspect round: reduce the maximum `sqrt(2/3) * L / h` aspect ratio.

The inherited `general_edge_removal` minimum-quality threshold (`1e-4`) is
fixed and is not relaxed. The diagnostic additionally refuses a candidate when
the old cavity orientation is not uniform or the new signed-volume signs do
not match it. This is intentional: the current helper already preserves
absolute-volume tiling, but a raw fan candidate can still expose mixed signed
volume signs. Such a candidate is evidence for a future orientation fix, not a
production acceptance.

## Evidence recorded per candidate

Each candidate record contains:

- edge and owner tet IDs in deterministic order;
- before/after cavity tet rows;
- raw signed volume-6 arrays and signs, non-degeneracy, absolute-volume sum,
  and tiling delta;
- per-tet native shape quality, min/max dihedral, and Dassi aspect ratio;
- exact local cavity boundary face-set before/after;
- global boundary face-set digests, counts, area equality, and invariant result;
- criterion result, guard reasons, and whether the candidate entered only the
  simulated sequence.

After all bounded rounds, the complete simulated sequence is compared against
the baseline. If final global quality regresses or fails to improve, the report
marks `sequence_decision=rollback`. Even a `would_accept` result remains
measurement-only and does not return or install edited tets.

## Required input data

The runner is `scripts/diagnose_native_tet_lazy_flip2.py` and accepts an NPZ
with:

- required `points` `(N, 3)` float array and `tets` `(M, 4)` integer array;
- aliases `pts` and `cells` are accepted;
- optional `--n-surface-vertices`, needed only for the surface-prefix digest.

Example:

```text
python scripts/diagnose_native_tet_lazy_flip2.py mesh.npz \
  --n-surface-vertices 320 --output tet_lazy2.json
```

The bounded default is 2 rounds, 128 edges per round, and one no-progress
retry per edge. Increase those limits only for an explicitly recorded
measurement; keep the output JSON with the mesh provenance/checksum.

## Interpretation boundary

This card can distinguish a candidate blocked by the existing quality gate,
local boundary mismatch, absolute-volume failure, mixed signed-volume
orientation, or the dual criterion. It cannot establish that deeper Dassi
search would solve a flat wedge, and it does not change the 61-wedge FSL
production result. A future implementation would need a separately reviewed
orientation-preserving candidate constructor and new tests before any wiring
could be considered.
