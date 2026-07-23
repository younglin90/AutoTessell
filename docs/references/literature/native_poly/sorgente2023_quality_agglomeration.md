# Mesh Quality Agglomeration Algorithm for the Virtual Element Method Applied to Discrete Fracture Networks

## Bibliography and access

- Tommaso Sorgente, Fabio Vicini, Stefano Berrone, Silvia Biasotti,
  Gianmarco Manzini, and Michela Spagnuolo.
- *Calcolo* 60, Article 27, 2023.
- DOI: `10.1007/s10092-023-00517-5`
- Open-access full text:
  <https://link.springer.com/content/pdf/10.1007/s10092-023-00517-5.pdf>
- Status: `FULL_READ` (27/27 pages).
- Visual check: pages 8, 16, 20, and 24 were rendered and inspected. The graph-cut
  sequence, quantitative table, realistic network, and limitations were legible and
  consistent with extracted text.

## Scope and algorithm

The paper agglomerates two-dimensional polygonal meshes embedded as planar
fractures in 3D. It does **not** validate a three-dimensional volume-cell
agglomerator. Its transferable idea is a constrained cell-adjacency labeling
problem driven by solver-aware quality.

For adjacent elements `E,E'`, the data cost is `1-rho(E union E')`; self cost is
zero and non-adjacent cost is one. A smoothness term penalizes different labels on
adjacent elements. Parameter `lambda` balances conservative versus aggressive
agglomeration. The mesh becomes a graph, one node per element and one edge per
adjacency. Constrained mesh edges are removed from this graph so graph cut cannot
merge across them. Alpha-beta swap minimizes the multi-label energy. Elements
with a common final label are merged, followed by removal of aligned edges while
preserving constrained nodes/edges.

## Results

- `lambda = 0.25` removed roughly 30% of elements; `lambda = 1` removed roughly
  65%-70% in the two tested fracture networks.
- For VEM order one, degrees of freedom changed little because vertices dominate.
  At orders two/three, aggressive agglomeration reduced DOFs by about 50%.
- Optimal convergence rates were retained. Errors increased modestly at equal
  refinement, while comparison at equal DOFs remained competitive.
- Assembly/solve cost and in some cases stiffness conditioning improved because
  small edges and elongated cells were removed.
- Each fracture is optimized independently, suggesting natural distributed
  parallelism for this specific DFN setting.

## Guarantees and limitations

- Graph cut reaches a local energy minimum, not a global geometric optimum.
- The energy only evaluates pair unions. It never directly scores
  `E union E' union E''`; small elements can survive around constrained interfaces.
- The quality indicator and experiments are VEM-specific and two-dimensional.
- Direct transfer to CFD volume meshes requires 3D boolean-union topology,
  star-kernel validity, face planarity, patch/material constraints, and conservative
  owner-neighbor reconstruction.

## Current-code gap

- Native Poly contains smoothing, degenerate-cell dropping, and candidate scoring,
  but no explicit cell agglomeration engine.
- `collapse_short_face_edges` merges vertex endpoints globally by union-find,
  without a cell-union validity transaction or protected patch/interface graph.
- `patch_roles.py` already exposes useful protected interface edges. The same
  provenance should become hard graph barriers for future cell/face merges.
- A volume agglomerator must not inherit the paper's 2D quality function blindly;
  it should use the 3D vector in `POLY-QUALITY-VECTOR1` plus OpenFOAM metrics.

## Falsifiable implementation cards

### `POLY-AGGLOM-GRAPH1`

Build a deterministic cell-adjacency graph with hard barriers for external patch
changes, material interfaces, non-manifold features, boundary-layer zones, and
user-protected entities. Pass if no proposed label spans a barrier and graph output
is identical across thread counts and input ordering.

### `POLY-AGGLOM-PAIR1`

Implement transactional adjacent-cell union with exact shared-face cancellation,
coplanar-face consolidation, and validity/quality simulation before commit. Pass if
Euler/topology, total volume, patch ownership, owner-neighbor pairing, and minimum
validity remain invariant or improve after every accepted merge.

### `POLY-AGGLOM-LOOKAHEAD1`

Compare pair-only selection with bounded 2- and 3-hop lookahead. Pass only if
lookahead reduces pathological small-cell tails at fixed output count without
worsening runtime beyond the declared budget or any hard mesh contract.

### `POLY-AGGLOM-CFD1`

Run equal-cell and equal-DOF comparisons against the unagglomerated primal mesh on
diffusion, advection, and pressure-velocity cases. Required report: discretization
error, matrix condition estimate, solver iterations, wall time, memory, worst/p99
non-orthogonality, skewness, and conservation residual. No "poly is better" claim
is accepted from element-count reduction alone.

