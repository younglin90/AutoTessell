# Native Tet Strict-Topology Contract Calibration — 2026-07-30

## Card

`TET-STRICT-TOPOLOGY-CONTRACT-CALIBRATION-1`

The cylinder regression previously treated an exact final count of `1495` as
strict-topology acceptance.  That count is not a topology invariant: later
valid cleanup can change it while preserving the repaired boundary and strict
writer contract.

## Acceptance

The regression now requires a positive result, applied duplicate-group repair,
positive duplicate/removal evidence, positive pre-repair non-manifold faces,
boundary preservation, zero post-repair topology defects, and writer/result
cell-count consistency with tetrahedron encoding for every written cell.

Observed current baseline: `1493` cells after repair.  Cell count remains
Gate-6 target-following evidence, not a strict-topology pass condition.  True
three-or-more face incidence remains rejected; this card does not alter the
generator, writer, topology audit, or target-cell policy.
