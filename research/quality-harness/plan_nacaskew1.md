# NACASKEW1 - NACA apex feasible-region diagnosis

Measurement only. One `generate_native_tet` call, `target_cells=2000`,
`AUTO_TESSELL_P4C_PYTETWILD=0`. All experiments used independent in-memory copies of
the same parsed tet topology. No production files were changed.

## Setup

- Current dirty-tree baseline: 3968 cells, not the supplied 4010-cell reference run.
  Quality signature remains the same class: boundary skew 60.399, internal skew 34.808,
  non-orthogonality 89.976, zero inversions.
- Worst 30 boundary faces all had three surface vertices and one interior apex, but they
  shared only **four unique apexes**. Each apex therefore serves several competing
  boundary-face normal lines.
- Degenerate means `abs(signed_vol6) / 6 < 1e-9`.
- Volume ratio below is signed-volume-aligned relative to this run's baseline. Baseline
  tet volume was 0.008237170; input STL volume was 0.008218867, ratio 1.002227.
- Surface vertices remained bitwise fixed in every experiment.

## Results

| Method | Cells | Moved | Max displacement | Boundary skew | Internal skew | Non-ortho | Inversions | Degen | Volume ratio | Surface move |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 3968 | 0 | 0 | 60.399 | 34.808 | 89.976 | 0 | 7 | 1.000000 | 0 |
| A: tangential recenter | 3968 | 4 | 0.0562 | **60.097** | 34.774 | 89.982 | 0 | 8 | 1.000111 | 0 |
| B: feasible-region SLSQP | 3968 | 4 | 0.0562 | **8,862,376.332** | 34.808 | 90.000 | 0 | 17 | 1.000235 | 0 |
| Apex-collapse copy | 3946 | 0 | 0 | **1.688e28** | 41.770 | 90.000 | 72 | 38 | 0.997223 | 0 |

### A - tangential recenter

For each current worst candidate face, displacement was the projection of
`face_centroid - apex` onto that face's tangent plane. Three sequential sweeps used
orientation-preserving backtracking over every incident tet. Ten of 12 attempted moves
were accepted.

Result: boundary skew improved only 0.302 (0.50%), remained above 50, and one additional
degenerate tet appeared. Sequential moves toward one face's normal line conflict with
other worst faces sharing the same apex.

### B - feasible-region QP

Each incident tet signed volume was represented as an affine function of the apex.
SLSQP minimized squared distance to the selected boundary-face normal line subject to
sign-preserving half-spaces. Margin was scale-relative
`min(1e-8 * local_edge_scale^3, 0.05 * current_abs_vol6)`, keeping the current point
feasible. A tiny distance-to-current regularizer selected among equal line-distance
solutions. All 12 solves were feasible and accepted.

Result: no sign inversion, but the optimizer consumed volume margin, raised degen from
7 to 17, and nearly collapsed normal distance on competing faces. Boundary skew became
8.86e6. Feasibility by signed volume alone is insufficient.

### Apex-collapse copy

Because neither A nor B reached boundary skew below 50, an optimistic topology-copy
simulation collapsed each of the four shared apexes to the best of its three boundary
face vertices. Candidate choice prioritized fewer inversions, fewer degenerates, then
lower global boundary skew. Duplicate-vertex and duplicate cells were removed.

- Four collapses removed 20 duplicate-vertex cells and two duplicate cells: 3968 ->
  3946 cells.
- Aligned volume fell 0.278%.
- Boundary faces changed 696 -> 699; symmetric difference was 3 faces.
- Bad boundary edges changed 0 -> 5; nonmanifold faces changed 0 -> 3.
- 72 surviving tets inverted and 38 became degenerate. Boundary skew became effectively
  singular (`1.688e28`). Zero geometric surface displacement hides severe topology
  damage.

## Recommendation

Do **not** add A, B, or direct apex-to-surface collapse to production. Evidence rejects
single-face objectives: 30 worst faces are coupled through only four apexes. Signed-volume
feasibility does not protect normal distance, degeneracy, non-orthogonality, or adjacent
face skew. Any next experiment must optimize all incident boundary faces jointly and
explicitly constrain face normal distance and tet quality, or replace the complete apex
star with guarded cavity retriangulation. Direct edge collapse is not a viable shortcut.

Reproduction: `python3 research/quality-harness/_naca_feasible_probe.py`.
