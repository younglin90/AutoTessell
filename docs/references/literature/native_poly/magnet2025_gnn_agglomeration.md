# MAGNET: An Open-Source Library for Mesh Agglomeration by Graph Neural Networks

## Bibliography and access

- Paola F. Antonietti, Matteo Caldana, Ilario Mazzieri, and Andrea Re Fraschini
  (MOX, Politecnico di Milano).
- *Engineering with Computers* 41 (2025), 4825-4850.
- DOI: `10.1007/s00366-025-02223-y` — Open Access (CC BY 4.0).
- Code: `github.com/lymphlib/magnet` (LGPLv3). Received 2025-07-07, published
  2025-10-27.
- Status: `FULL_READ` (26/26 pages, 2026-07-23). Note: the screening index listed
  this PDF as 76 pages; the actual file is the 26-page journal article. Text was
  extracted per page with pypdf; figures (4-20) were not rendered, so figure-only
  quantitative details (box-plot values, Fig. 6 timing curves) are described
  qualitatively as in the prose.
- Companion line: this is the library/tooling paper for the 3D GNN agglomeration
  work of Antonietti-Corti-Martinelli (arXiv:2406.10587), which remains OPEN.

## Problem and method

Mesh agglomeration (merging fine polytopal cells into coarser connected polytopal
elements, for coarse grids / adaptivity / multigrid hierarchies) is reframed as
partitioning the **dual graph**: one node per mesh element, one edge per shared
face (3D) or edge (2D). The target objective is the **normalized cut**

- `cut(S) = |{(vi,vj) in E : vi in S, vj not in S}|`
- `vol(S) = sum over vi in S of deg(vi)`
- `NC(S1..SM) = sum_i cut(Si)/vol(Si)`   (Eq. 1)

Balanced min-cut partitioning is NP-complete; MAGNET compares GNN heuristics
against METIS and k-means inside one framework, with pluggable "agglomeration
modes" (direct k-way, recursive-bisection by Nref / target size / multiplicative
factor, segregated per-material, partial coarsen, multilevel recursive bisection
with greedy heavy-edge matching + refiner).

### GNN models (what the network predicts)

- **SAGE-Base** — 4 SAGEConv layers + 4 linear layers, tanh activations, final
  softmax. Input: node features = element centroid coordinates + element measure
  (4 features in 3D, 3 in 2D), normalized to zero mean/unit variance and rotated
  so the widest direction aligns with x. Output: `Y in R^{N x 2}` = per-node
  probability of belonging to each half of a **bisection**. Loss = expected
  normalized cut (differentiable relaxation, GAP-style). Any partition count is
  reached by recursive bisection with the single model. 2D: 64/32 units, 800
  mixed meshes, Adam, 300 epochs, lr 1e-5. 3D: 128/64 units, 400 tet meshes (100
  unit cubes + 300 random cube portions), 400 epochs, lr 1e-4, random-rotation
  augmentation.
- **SAGE-Heterogeneous** — adds one scalar "physical group" feature p in [0,1]
  and a loss penalty `a/|V| * sum (P ⊙ Y)` (Eq. 2) against merging across
  materials. Handles at most two physical groups; more groups require the
  segregated mode. Sensitivity study: `a > 0.5` needed for consistent
  heterogeneity preservation.
- **RL Partitioner** — A2C actor-critic; state = current one-hot partition,
  action = flip one node, reward = decrease in NC; episode length `|V|/2`
  (grow S2 from one min-degree seed to half the nodes). One GNN forward pass
  per action (expensive).
- **RL Refiner** — lightweight actor-critic used after uncoarsening in the
  multilevel mode; runs only on the k-hop subgraph around the cut (k = 2-4),
  episode length = cut size, plus imbalance penalty
  `b (Vol(S1)-Vol(S2))^2 / Vol(V)` with b = 0.35. Trained on ~5000 2D meshes.

Post-processing: any partition class with multiple connected components is split
into separate elements (connectivity is **not** guaranteed by the GNNs), then
geometric merging of cells happens as a separate shared step. Dual-graph
adjacency is built in average-case linear time with a face-to-cell hash map
(Algorithm 1).

## Quality metrics (element-wise, all in [0,1] — Eqs. 3-9)

- **Circle Ratio** `CR(P) = max{r : B(r) ⊂ P} / min{r : B(r) ⊃ P}` (roundness).
- **Area-Perimeter Ratio** (2D) `APR(P) = 4π|P| / |∂P|^2` (isoperimetric
  quotient).
- **Sphericity** (3D) `Ψ(P) = (36π |P|^2)^{1/3} / |∂P|` (3D analogue of APR).
- **Uniformity Factor** `UF(P) = diam(P)/h`, `h = max_P diam(P)` (diameter
  similarity).
- **Volume Difference** `VD(P) = |Vol(P) - V̂| / V̂`, `V̂ = mean volume`;
  reported as `ṼD(P) = 1/(1+VD(P))` (1 = perfectly uniform volumes).
- **Heterogeneity Preservation** `HP(P) = max{p̄, 1-p̄}`, `p̄ = mean physical
  tag over the fine cells of P` (1 = single-material agglomerate).

These are fully deterministic and independent of the ML machinery — the most
directly reusable part of the paper.

## Experiments

- **Is the evidence genuinely 3D volume agglomeration with cells as elements?**
  Yes, for the agglomeration itself: Test 4 (hybrid cube, 27,484 cells = 23,874
  tets + 3249 hexes + 361 pyramids; k-means only), Test 5 (human brain, 123,383
  tets; METIS / k-means / SAGE-Base / multilevel+RL-Refiner), Test 6
  (Garuda-Vishnu statue, 615,229 tets; genus-rich topology). Cells are the dual
  graph nodes; output is polyhedral agglomerates written via VTK. **But** the
  PDE verification (Sect. 5, lymph PolyDG: Poisson + heat equation) is 2D only;
  3D evidence is quality-metric box plots without a 3D solve. The RL models are
  trained on 2D data and the authors state bigger RL models "should be trained
  to perform better in the three-dimensional case."
- **Deterministic baselines and the actual margin.** The paper's own conclusion
  is that GNNs produce meshes "of comparable quality" — the ML margin on
  quality is essentially zero. Specifics: k-means is clearly the best on CR and
  UF in 2D (it is a geometric clusterer); METIS is the best on volume
  uniformity (hard balance constraint + volume node weights); SAGE-Base bisects
  along straight lines, giving squared corners and *lower* APR; the RL coarse
  partitioner is "slightly worse across the board." In the 3D brain, k-means
  and SAGE-Base produce disconnected agglomerates (post-split leaves tiny
  elements, lowering UF); the multilevel+RL-Refiner mode mostly repairs this.
  On the statue, METIS with volume weights *failed* to partition and needed
  unit weights (a robustness data point for both sides).
- **Runtime/scalability** (Fig. 6, Colab Xeon 2.20 GHz + Nvidia T4): METIS
  k-way is much cheaper than METIS bisect; k-means k-way scales worst as k and
  cell count grow; GNN-on-CPU is asymptotically comparable to METIS bisect;
  GNN-on-GPU has a large fixed cost but becomes the cheapest method beyond
  roughly 1e4 cells. The claimed ML advantage is GPU throughput, not quality.
- **PolyDG convergence (2D):** agglomerated meshes achieve the theoretical
  orders (L2: l+1, dG: l); measured 4.40/3.34 (vs 4/3) on Nref-swept meshes and
  4.13/3.08 when element shape is held comparable. An odd/even-Nref parity
  effect (square vs 2:1 rectangular elements) causes oscillating L2 error.

## Limitations

- **No shape-regularity guarantees — explicitly none.** No star-shapedness or
  aspect-ratio bound is enforced or proven; quality is only measured a
  posteriori. Element connectivity itself must be repaired post hoc.
- The domain boundary is not represented in the model: agglomerates can span
  boundary-condition discontinuities, producing numerical oscillations, and
  "MAGNET has no way to guarantee this does not happen." No feature/patch/crease
  preservation of any kind.
- Agglomerated elements accumulate many faces/edges (cost in DG assembly); face
  and edge coarsening is future work.
- Heterogeneous GNN limited to two materials; segregated mode is expensive with
  many inclusions.
- 3D validation is metric-only (no 3D PDE solve); RL models under-trained
  for 3D; GNN quality gains over METIS/k-means are not demonstrated.

## AutoTessell applicability (AI-advisory constraint)

This paper is naturally compatible with the project's rule that AI hints never
own acceptance: agglomeration here is a *proposal* (a node classification), and
everything downstream — connectivity split, geometric merging, quality metrics —
is deterministic. For `native_poly` route-2:

- The honest reading is that **deterministic partitioners suffice**: METIS-style
  multilevel bisection or centroid k-means with a connectivity-split guard match
  the GNN on every quality metric in the paper's own data. A GNN advisor would
  only add value for (a) heterogeneity-aware agglomeration and (b) GPU-scale
  throughput — neither is a current AutoTessell bottleneck.
- The **metric suite (CR, Ψ, UF, ṼD, HP)** is the reusable core: element-wise,
  deterministic, [0,1]-normalized, and defined for arbitrary polyhedra. It slots
  directly into `core/evaluator/native_checker.py`-style gates for any future
  cell-merging/coarsening pass, independent of who proposed the merge.
- The **connectivity-split post-check** (partition class → connected components
  via face adjacency → split) is a cheap deterministic gate AutoTessell should
  apply to *any* clustering-derived cell grouping.
- Negative lesson to carry: agglomeration that ignores boundary classification
  breaks solution quality at boundary discontinuities — reinforces the
  Garimella-style entity-classification contract already noted in
  `garimella2013_general_dual.md` as the right foundation for poly merging.

## Falsifiable implementation cards

### `POLY-AGG-METRIC1` (deterministic reuse)

Implement element-wise CR (inscribed/circumscribed sphere ratio), sphericity
`Ψ = (36π V^2)^{1/3} / A`, UF, and ṼD for polyhedral cells in the native
evaluator, and report their per-mesh distributions for `native_poly` output.
Pass if unit fixtures reproduce analytic values (sphere-like cell Ψ→1, cube
Ψ = (π/6)^{1/3} ≈ 0.806, uniform grid ṼD = 1, UF = 1) and the metrics are
invariant under rigid transform and uniform scale.

### `POLY-AGG-CONNSPLIT1` (deterministic reuse)

Add a face-adjacency connected-component guard to any cell-grouping/merging
step: build the dual adjacency with the hash-map algorithm (linear average
case), split every proposed group into its connected components before merging.
Pass if no emitted merged cell has a disconnected dual subgraph, and if a
fixture with a deliberately disconnected proposal yields exactly one cell per
component with total volume conserved.

## Snowball references (≤5)

1. Antonietti, Corti, Martinelli (2024) — *Polytopal mesh agglomeration via
   geometrical deep learning for 3D heterogeneous domains*, arXiv:2406.10587 —
   the 3D methodology companion (already OPEN in our queue).
2. Antonietti, Farenga, Manuzzi, Martinelli, Saverio (2024) — *Agglomeration of
   polygonal grids using GNNs with applications to multigrid solvers*, Comput.
   Math. Appl. 154:45-57 — the 2D GNN agglomeration origin.
3. Feder, Cangiani, Heltai (2025) — *R3MG: R-tree based agglomeration of
   polytopal grids*, J. Comput. Phys. 526:113773 — a fully deterministic
   agglomeration alternative; likely more relevant than the GNN line under our
   AI-advisory policy.
4. Gatti, Hu, Smidt, Ng, Ghysels (2022) — *Graph partitioning and sparse matrix
   ordering using reinforcement learning and GNNs*, JMLR 23 — source of the RL
   partition/refine framework.
5. Sorgente, Biasotti, Manzini, Spagnuolo (2022) — *Polyhedral mesh quality
   indicator for the virtual element method*, Comput. Math. Appl. 114:151-160 —
   deeper 3D poly quality-metric theory behind Sect. 3.5.
