# Chen 2026 - Hex-Dominant Meshing with High-Quality Hexahedral Element Distribution

## Bibliographic record

- Hao Chen, Zhihao Zheng, Yizhou Liao, Shuming Gao, *An approach to hex-dominant
  meshing with high-quality hexahedral element distribution*, Engineering with
  Computers 42:2, 2026. Received 2025-09-26, published online 2026-01-08.
- DOI: `10.1007/s00366-025-02241-w`
- Affiliation: State Key Lab of CAD&CG, Zhejiang University (Shuming Gao group — same
  group as Wu/Gao sweep decomposition and Zheng 2020 dual-surface block decomposition).
- Local PDF: `papers/pdf/30_chen_2026_hex_quality.pdf`
- Status: `FULL_READ` (23/23 pages, 2026-07-23). Note: the screening queue listed this
  as a 66-page manuscript; the actual published PDF is 23 pages, all read.
- Forward-sweep provenance: filed under section 4 (hex-dominant honesty) of
  `forward_citation_sweep_2026-07-23.md` as P2/CONTEXT; this read confirms that filing.

## Problem and claimed scope

Existing hex-dominant generators optimize hex *proportion* and per-element quality but
ignore *where* the hexes end up. Industrial users prefer meshes whose hexahedra form
large, connected, well-shaped clusters (e.g. a swept slab of pure hex) over the same hex
fraction scattered as isolated cells. The paper (1) defines a new metric **QHED**
(hexahedral element distribution quality) for this property, and (2) proposes a
decomposition-first generation pipeline that maximizes it: identify sweepable regions
via frame-field analysis, convert them to strictly sweepable volumes via OBB
optimization, sweep them all-hex, and fill the rest with boundary-constrained tet
aggregation. Contributions are generation **and** a census-style metric — it is both a
generator paper and a reporting-metric paper.

## The QHED metric (the honesty-lane payload)

`QHED = ScoreCHE * ScoreQHC`, both in [0,1]:

- **ScoreCHE** (connectivity of all hex elements):
  `ScoreCHE = (1 / (6|H|)) * sum_{h in H} |Nei(h)|`
  where `Nei(h)` is the set of hexes face-adjacent to hex `h`. Boundary quad faces on
  the model surface count a *virtual* external neighbor, so a pure all-hex mesh scores
  exactly 1.0 and fully isolated hexes score low. Interpretation: mean fraction of a
  hex's 6 faces that are hex-hex (or true-boundary) faces.
- **ScoreQHC** (quality of hexahedral clusters): a hexahedral *cluster* is a maximal
  face-connected component of hex cells. Size-weighted over clusters j:
  `ScoreQHC = sum_j (|cluster_j| / |H|) * (0.5 * Score_topo^j + 0.5 * Score_smoo^j)`
  - `Score_topo^j = 1 / (1 + |Cav(cluster_j)|)` — penalizes internal cavities (pockets
    of non-hex cells fully inside a cluster).
  - `Score_smoo^j = 1 - |E_concave^j| / |E_itf^j|` — fraction of concave edges on the
    interface between the cluster and non-hex regions (irregular, jagged cluster
    boundaries score low).

This is a pure post-hoc census computable from cell-type labels + face adjacency; it
needs no knowledge of how the mesh was generated.

## Generation algorithm read from the paper

Inputs: B-rep model **and** a feature-constrained tet mesh of it. Output: conformal
hybrid mesh H = {hex, prism, tet}.

1. **Frame field**: boundary-aligned smooth frame field on tet cell centers, solved with
   Gao et al. 2017's code (Dirichlet energy over frame permutations, boundary normal
   locked to an axis of the frame).
2. **Sweepable-region identification** (contribution 2): key observation — inside a
   strictly sweepable volume, one frame component is invariant and equal to the sweep
   direction. Per tet, local frame variation `phi_i^k = mean over 1-ring of
   angle(R_{i<-j} R_j(k), R_i(k))`. A tet is a *constituent* of a sweepable region if
   some component's variation < eps_r (adaptive: `eps_r = (l_avg / 0.1) * 5e-4` in
   normalized space; 0 / 1 / 3 sweep directions possible, never exactly 2 by
   orthogonality). BFS region growing from constituent seeds with direction-consistency
   criteria clusters single-direction and triple-direction regions; triple-direction
   regions are then merged into an adjacent single-direction region chosen by
   `argmin (0.25 * E_area + 0.75 * E_nei)` (interface-area ratio + adjacent-region
   count). Claimed advantage over boundary-based sweep detection (Wu 2014): uses volume
   information, finds sweepable regions invisible from the boundary alone.
3. **Interface reconstruction via OBB optimization** (contribution 3): region interfaces
   generally violate the strictly-sweepable constraint (cap faces || sweep dir, side
   faces perpendicular). New interfaces are constrained planar with normals from the
   allowed set; positioning of all cut planes of a region simultaneously is reformulated
   as optimizing one oriented bounding box (fixed orientation, variables = extents after
   affine transform to AABB). Energy: `E = 1*E_vol + 10*(-E_bnd) + 100*E_ang +
   100*E_dist + 50*E_gft` — volume mismatch, boundary-feature snap reward, sigmoid
   penalties on min dihedral angle (theta_thres = 20 deg) and min face distance
   (d_thres = target size lambda), and a binary grafting-configuration penalty. Hard
   constraint: OBB must not intersect bounding boxes of "violation patches" (boundary
   areas whose normal breaks sweepability). Solved with a feature-initialized,
   gradient-informed Particle Swarm Optimization. Boolean intersection (CAD kernel)
   of the optimal OBB with the model yields the closed strictly sweepable volume.
4. **Meshing with inter-volume consistency**: sweepable volumes are swept all-hex
   (HyperMesh's commercial sweeper via Tcl scripting). Grafting between adjacent swept
   volumes is resolved by offsetting the graft surface by `2*lambda` and carving a thin
   *transition zone*, which is treated as unsweepable. Unsweepable volumes: interface
   quads are split to triangles and imposed as constraints in TetGen CDT (feature edges
   also constrained), then Pellerin et al. 2018's tet-combination aggregation runs with
   *interface-priority* selection (hex candidates containing interface-quad edges are
   picked first) to keep edges aligned across the boundary. Node-conformal everywhere.
   Target size `lambda = 1.5 *` average input edge length.

## Experiments

- 44-model table (MAMBO library, HexMe models, Wu examples, custom parts). Reported per
  model: hex proportion by count and by volume, hex SJ min/avg/max, tet and prism
  proportions with min SJ, QHED, and separate timings for volume construction (VC) and
  mesh generation (MG).
- Ranges: hex fraction by count 16.8% (Mambo_M5) to 100% (cylinder, B2, B17, B35);
  QHED 0.41-1.00. Sweep-friendly parts reach Phex >= 99% with QHED 0.99-1.00. Min hex
  SJ can be poor (0.01 on several models) — the honesty of reporting min/avg/max per
  cell type is itself notable.
- Vs Pellerin 2018 aggregation alone (Table 2): cylinder — Pellerin 0.64% hex by count
  / 3.43% by volume, QHED 0.3; ours 100/100, QHED 1.0. Mambo_S1 — Pellerin 0.32/2.27,
  QHED 0.26; ours 99.94/99.98, QHED 1.0. (Pellerin fractions are startlingly low
  because the input tet mesh structure limits recombination.)
- Vs Ray et al. 2018: qualitative only (no mesh data available); their global
  parameterization wins on generalized-sweepable shapes the strict-sweep detector
  rejects.
- Timing (Ryzen 7, 16 GB): VC dominates — over 80% of total runtime; worst case
  Fusee 29,856 s (~8.3 h) for VC vs 74 s for meshing. PSO-based OBB optimization is the
  acknowledged bottleneck.

## Assumptions, guarantees, limits

- Needs a B-rep **and** a CAD kernel for boolean splits — the pipeline drives
  HyperMesh via Tcl for both solid splitting and sweeping. Not reproducible natively.
- Strictly unidirectional sweeps only. Pseudo/generalized sweepable regions (frame
  deviation slightly above eps_r but short of orthogonal) are unhandled by design
  (their own footnote) and fall to the aggregation path.
- The commercial sweeper itself occasionally emits non-hex chains (prisms) inside
  "all-hex" swept volumes — even here, the census is measured, not assumed.
- No formal quality guarantee: min SJ down to 0.01 in the table; QHED is a descriptive
  metric, not a validity gate. No inversion/validity discussion beyond SJ reporting.
- eps_r presumes the tet mesh is fine enough to resolve all features.
- No open code; datasets not released ("no datasets generated or analysed").

## Overlap with the read hex corpus

- **Gao 2017** (field-guided agglomeration): used as the frame-field backend; Chen's
  critique — global field smoothing scatters non-hex elements into regions that were
  locally perfectly sweepable — is the paper's motivating observation and is the same
  failure mode our HEX-HD-1 census is meant to expose.
- **Pellerin 2018**: used verbatim as the unsweepable-volume aggregator; Chen adds only
  interface-priority candidate ordering. Confirms the sweep's view that Pellerin is the
  combinatorial census/recombination kernel of record.
- **Ray 2018 "Mind the gap"**: complementary reporting philosophy; Chen extends the
  "quantify the non-hex remainder" idea from *how much* to *where/how clustered*.
- **Zhang 2013 / Maréchal 2009 / Pitzalis 2021 / Tong 2024** (octree lane): no overlap —
  no octree, no transition templates; irrelevant to lane (c).
- **LoopyCuts / HexDom**: alternative decomposition-first competitors discussed in
  related work only.

## AutoTessell applicability verdict

- **Lane (a) hex-dominant honesty — ADOPT THE METRIC.** QHED is exactly the missing
  second axis of our honesty contract: HEX-OCT-1/HEX-HD-1 report *how much* hex
  (count + volume fraction); QHED reports *how usefully distributed* it is. ScoreCHE is
  a few lines over the face-adjacency we already build in the polyMesh writer;
  cluster labeling is one BFS over hex-hex faces. Concave-edge and cavity terms are
  slightly more work but optional (report ScoreCHE first). This directly upgrades
  `core/generator/native_hex/mesher.py` written-mesh summary and the evaluator report.
- **Lane (b) post-snap boundary skew — not relevant.** No untangling/smoothing content.
- **Lane (c) octree transition validity — not relevant.**
- **Generation pipeline — DO NOT PORT.** Depends on B-rep input, a commercial CAD
  kernel (booleans + sweeper), frame-field infrastructure we deliberately deferred, and
  a PSO stage with hour-scale runtimes. Our native_hex path is octree-based, not
  decomposition-based. Keep as a benchmark reference: its Table 1 gives realistic
  Phex/QHED expectations per geometry class (sweep-friendly parts should approach
  Phex ~ 100 / QHED ~ 1.0; genuinely complex parts sit at Phex 17-76 / QHED 0.4-0.85).

## Falsifiable implementation cards

### HEX-HD-5 - QHED distribution score in the census (extends HEX-HD-1/HEX-OCT-1, no dupe)

- After the truthful cell-type census, compute ScoreCHE (mean hex-hex face-adjacency
  fraction with virtual boundary neighbors, Eq. 2) and hex-cluster count via BFS on
  hex-hex shared faces; report `score_che`, `n_hex_clusters`, `largest_cluster_frac`
  alongside `hex_count`/`hex_volume_fraction`. Optionally add ScoreQHC terms later.
- Pass: uniform all-hex cube mesh scores ScoreCHE = 1.0 with 1 cluster; the same mesh
  with every second cell relabeled non-hex scores near the isolated-cell floor; values
  are deterministic and sum-consistent with the census.
- Expected current adaptive result: the native_hex adaptive path's polyhedral
  transition cells will fragment the hex region into multiple clusters and pull
  ScoreCHE visibly below 1.0 — making the distribution cost of Option-B transitions
  (HEX-OCT-2) measurable, not just the hex ratio.

No second card: the generation pipeline is out of scope (commercial-kernel dependency),
and boundary-skew/octree lanes get nothing from this paper. Existing HEX-SHEET-1/2,
HEX-UNTANGLE-1, HEX-ALLHEX-1 are untouched — no overlap.

## Snowball references (<=5)

1. Beaufort, Reberol, Kalmykov, Liu, Ledoux, Bommes (2022), "Hex me if you can", CGF
   41(5) — DOI `10.1111/cgf.14608`. The HexMe benchmark set used here (HexMe_N01/N05/
   S07); candidate standard test corpus for our hex engine benchmarks.
2. Wu, Gao (2014), "Automatic swept volume decomposition based on sweep directions
   extraction", Procedia Eng 82:136-148 — DOI `10.1016/j.proeng.2014.10.379`. The
   boundary-based sweep detector Chen improves on; simplest sweep-recognition baseline.
3. Jankovich, Benzley, Shepherd, Mitchell (1999), "The graft tool: an all-hexahedral
   transition algorithm for creating a multi-directional swept volume mesh", IJNME.
   Names and solves the grafting problem Chen sidesteps with transition zones.
4. Baudouin, Remacle, Marchandise, Henrotte, Geuzaine (2014), "A frontal approach to
   hex-dominant mesh generation", AMSES 1:8 — DOI `10.1186/2213-7467-1-8`. The
   frame-field + advancing-front hex-dominant lineage ("Carrier" in Chen's text);
   fills the gap between Gao 2017 and Pellerin 2018 in our hex-dominant map.
5. Zheng, Wang, Gao, Liao, Ding (2020), "Automatic block decomposition based on dual
   surfaces", CAD 127:102883 — DOI `10.1016/j.cad.2020.102883`. Same group's pure-hex
   decomposition predecessor; context for why they relaxed to hex-dominant.

## Decision

Use this paper for the census/reporting contract only: add QHED-style distribution
metrics (ScoreCHE + cluster stats) on top of the truthful cell-type census, and use its
Table 1 as external calibration for what Phex/QHED a given geometry class should
achieve. Do not pursue its sweep-decomposition pipeline — wrong architecture for our
native octree engine and hard-blocked on commercial CAD dependencies.
