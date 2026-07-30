# Native Hex Literature Evidence Matrix

Status date: 2026-07-23. This ledger is scoped to `native_hex`; the central bibliography (`../master_bibliography.csv`) carries the matching FULL_READ rows for this corpus.

## Full-read corpus

| Paper | Coverage | Pages | DOI | Evidence status | Production decision |
|---|---|---:|---|---|---|
| Maréchal 2009 | octree/grid, all-hex dual transitions, sharp features | 19/19 | `10.1007/978-3-642-04319-2_5` | full text + 3 rendered pages | adopt sizing/provenance; current transition is not equivalent |
| Zhang et al. 2013 | 2-refinement octree/RD-tree all-hex meshing; feature preservation; strong balance | 13/13 | `10.1016/j.cma.2012.12.020` | full text + rendered core algorithm excerpts | candidate for direct octree-template replacement; compare hanging-node propagation and boundary feature retention against HybridOctree_Hex |
| Nieser et al. 2011 | frame field, singularities, global parameterization | 10/10 | `10.1111/j.1467-8659.2011.02014.x` | full text + 3 rendered pages | long-term research; reject as next production path |
| Gao et al. 2017 | frame/position field, hex-dominant polyhedral agglomeration | 13/13 | `10.1145/3072959.3073676` | full text + 3 rendered pages | medium-term architecture after topology/validity kernel |
| Knupp 2001 | global l1 untangling objective, corner-Jacobian inversion definition, beta positivity margin | 8/8 | `10.1007/s003660170006` | full text | subsumed by Edge-Cone Rectification 2015 + HexOpt for the optimization machinery; keep the volume-scaled beta-margin acceptance gate (HEX-UNTANGLE-1) and failure-as-topology-diagnostic rule (persistent untangler failure implicates connectivity, not the optimizer) |
| Ledoux & Shepherd 2010 | STC dual, sheet extraction / pillowing / chord collapse with preconditions, atomic ops, existence theorems | 15/15 | `10.1007/s00366-009-0145-2` | full text + 2 rendered pages | adopt as the topological contract for a sheet-ops repair lane: sheet extraction and chord collapse as surgical wall-skew repair, pillowing as the per-patch BL insertion primitive; all three provably all-hex-preserving; topology-only paper — no experiments, no quality data, geometric placement is ours |
| Qian & Zhang 2010 | B-rep curve/patch ownership, non-manifold shared-patch handling, two-step pillowing | 18/18 | `10.1007/978-3-642-15414-0_15` | full text + rendered first page | use as provenance and local-pillow precondition evidence only: critical points fixed; curve/patch membership explicit; shared patch needs component-aware matching. Reject direct global two-layer port because it moves prior boundary nodes and sharply increases cells; any local adaptation is surface-hash/wall_dev/positive-Jacobian gated |
| Yamakawa & Shimada 2002 (HEXHOOP) | hex/prism/pyramid/tet → all-hex core+cap hoop templates, Schneiders pyramid solution | 18/18 | `10.1007/s003660200019` | full text | reference-only: ~49-60x cell multiplication, systematic ~0.4 scaled-Jacobian mode from converted non-hex elements, patent-pending flag; wrong input class for our polyhedral octree transitions — Pitzalis 2021 is strictly better for grid-based transitions; cite as the honest price tag for rejecting hex-dominant → all-hex conversion (HEX-ALLHEX-1) |
| Chen 2026 | hex-dominant generation via sweep decomposition + QHED hex-distribution metric | 23/23 | `10.1007/s00366-025-02241-w` | full text | adopt the QHED/ScoreCHE census metric as a post-hoc distribution score (HEX-HD-5); generation pipeline not portable — B-rep input, commercial CAD kernel (HyperMesh booleans + sweeper), hour-scale PSO bottleneck |
| Gao, Shen, Panozzo 2019 | octree + dual all-hex conversion, scaffold, corner/curve/patch feature mapping, SLIM padding/untangling/fitting | 15/15 | `10.1111/cgf.13795` | full text + 5 rendered pages; code vendored in-repo (`Feature-Preserving-Octree-Hex-Meshing/`, full pipeline implemented) | adopt the feature-mapping recipe for the Phase-3 provenance card — corner→nearest vertex assigned once, curve→Dijkstra-with-cuts over `l/2` samples, patch→bidirectional correspondence, then tangent-slide only (implementable, code available); adopt the targeted refine-on-deviation loop idea for the wall_dev gate; vendored binary = test oracle only — do NOT port global SLIM/scaffold/padding (minutes-to-hours, up to 60 GB); honesty caveat: corner-positive SJ is necessary but NOT sufficient for trilinear bijectivity (5/202 outputs non-bijective) — gates must say "positive corner SJ", not "valid hex" |
| Pitzalis et al. 2021 | ILP-based generalized pairing (minimal grid refinement) for adaptive grids | 13/13 | `10.1145/3478513.3480508` | full text (Korean note); code open (Gurobi dependency) | **misnomer corrected: this is NOT the template paper** — transition templates/schemes are Livesu 2022; Pitzalis 2021 is the pairing ILP *preprocessing* that prepares the grid with minimal extra refinement. Quantified: GP+WB grid growth 2.1x vs octree-rule SB 3.3x (194/202 wins, 0 losses, 13.6K vs 24.4K added cells). ILP is a performance optimization, not a correctness requirement — octree-rule pairing (OP+WB, 2.9x) already suffices to install the Livesu schemes, so adoption can be staged |
| Livesu et al. 2022 | the actual scheme/template paper: 20-transition complete enumeration, 8+5 atomic dual schemes, dualization | 13/13 | `10.1145/3494456` | full text (arXiv v1); schemes in CinoLib (MIT) | adopt as the HEX-OCT-2 Option-A core: constructive proof of pure-hex conversion for balanced (strong or weak) + **paired** grids; singular edge valence bounded ≤6 (strong) / ≤7 (weak); weak balancing saves ~15% cells avg. Topological all-hex is proved, **positive Jacobian is NOT** — boundary projection is external, ECR untangling assumed as post-pass. Judgment rule: no dual-scheme all-hex claim unless the grid is balanced+paired — our engine has no pairing check/refinement stage, so no all-hex claim until one exists |
| Livesu et al. 2015 (ECR) | edge-cone rectification: connectivity-fixed hex untangling + quality via local-global QP/penalty | 11/11 | `10.1145/2766905` | full text; results archive on project page | port target for the post-snap quality lane, two stages: interior-only frozen-surface ECR first, then tangent-plane sliding. Frozen boundaries are supported and degrade gracefully, but cells with ≥3 boundary faces are provably unfixable frozen (Fig 11) — that class needs pillowing, not more smoothing; **tangent-plane sliding (Eq 21) is the wall_dev-compatible mode** (first-order zero normal motion, corners/features pinned). MSJ/cone-angle ↔ OpenFOAM-skew correlation is assumed, unverified — run HEX-ECR-1/HEX-ECR-4 diagnostics before any solver code. No inversion-free guarantee (empirical) |
| Tong & Zhang 2024 (HexOpt) | post-optimization: ReHQJ energy + augmented-Lagrangian surface constraint + L-BFGS/Armijo | 10/10 | arXiv `2410.11656` (journal DOI unverified) | full text; code open (CMU-CBML/HexOpt) | primary design for the Phase-1 sliding lane. **The surface constraint is SLIDING closest-point, recomputed every iteration** — vertices preserve membership on the surface (PostMaxDist = 0), not snapped positions; admissible for the wall_dev gate provided (a) the gate is checked at Θ-stage convergence (soft ρ start leaves mid-iterates transiently off-surface) and (b) feature corners/edges come from **our own feature classification** (their automatic feature path-finding is their reported weak spot). ECR-vs-HexOpt bake-off required — their superiority claim over ECR is prose, no side-by-side table; η=0.5 vs 0.9 backtracking discrepancy must be resolved from source before port |
| Staten, Shepherd, Ledoux, Shimada 2010 (Hexahedral Mesh Matching), IJNME 82(12):1475-1509 | hex-mesh matching: depth-bounded sheet extraction / pillowing / dicing / column collapse to convert a non-conforming hex-to-hex interface into a conforming one | 35/35 | `10.1002/nme.2800` | full text (verified journal year 2010; online-first/copyright 2009) | adopt as the **primary mechanism** for native_hex's post-snap singleton-bad-face repair, but only when gated by **our own OpenFOAM skew metric**, never the paper's scaled Jacobian (`staten2010_mesh_matching.md`, HEX-MATCH-1/2) — the paper proves all-hex topology preservation by construction but proves no positive-Jacobian/quality floor and its own worst example drops min SJ 0.9914→0.4691 when locality is prioritized. Bracket's 7-component/6-patch damage is **explicitly outside the paper's demonstrated and claimed scope** (restricted to single-surface interfaces; multi-surface interfaces are the paper's own stated future work) — HEX-MATCH-3 is a required, separate, uncertain-outcome research spike, not an assumed extension |
| Daines & Lobos 2018 (Repairing Octree Boundary Transition Regions), SCCC 2018 | iterative bounded node-re-projection repair of invalid boundary elements in an 8-split mixed-element (tet/pyramid/wedge/hex) octree transition | 8/8 | `10.1109/SCCC.2018.8705233` | full text | **not directly portable** — our native_hex transition cells are pure-hex/hex-dominant, not the paper's mixed tet/pyramid/wedge/hex family its `J_ENS` metric is defined over (round-2 gap-search caveat confirmed, not resolved). Reuse only the **iteration-bounded (cap 3) re-snap loop structure** and the **measure-collateral-neighbor-damage discipline** as secondary diagnostic patterns (`daines2018_octree_transition_repair.md`, HEX-DAINES-1/2); HEX-DAINES-3 (whole-mesh single-pass labeling, bracket-relevant) is explicitly unvalidated — the source's own test domains are single-component smooth organic shapes, the opposite of the bracket's multi-component sharp-corner damage |
| Ledoux, Le Goff, Owen, Staten, Weill 2013 (Constraint-Based Sharp-Feature Preservation), IMR21 | a posteriori dihedral-angle curve-labeling + vertex-valence branch-and-bound constraint solver deciding how many chords/hexahedra should surround a sharp CAD edge, then pillows the resulting face path | 18/18 | `10.1007/978-3-642-33573-0_19` | full text | **secondary geometric decision-rule donor**, not a primary mechanism: use the dihedral-angle/chord-count labeling as an input alongside our own skew measurement to choose WHERE pillowing helps sharp-feature preservation (`ledoux2013_cad_topology_correction.md`, HEX-LEDOUX13-1/2/3) — never as a replacement for the skew gate, since the paper reports zero quality metrics of any kind. Never moves existing boundary vertices (pillow-only), consistent with our frozen-boundary invariant. **Multi-component/bracket geometry is explicitly out of scope** (Section 5, stated future work) — do not apply there |
| Chen, Gao, Zhu 2016 (Improved Hexahedral Mesh Matching Algorithm), EwC 32:207-230 | topological `ΔV`/`ΔH` (edge-valence irregularity / hex-count variance) sheet-choice metric to pick the cheapest-to-predict assistant sheet during Staten-2010-style local sheet extraction | 24/24 | `10.1007/s00366-015-0414-1` | full text (verified journal year 2016; online-first 2015) | reuse only the **cheap local candidate-enumeration architecture** (enumerate existing sheets + inflatable quad sets local to a flagged bad face, pre-score cheaply, execute one real op) — the `ΔV`/EEVS topological metric itself is **rejected** as our repair-pass objective; substitute our own OpenFOAM skew/non-orthogonality delta instead (`chen2016_quality_sheet_choice.md`, HEX-SHEETCHOICE-1, amended per the 2026-07-25 synthesis below). The paper's own data is negative evidence for `ΔV`: min scaled Jacobian still degrades to 0.18–0.37 across its 4 examples despite `ΔV`-guided selection being active throughout, and its one head-to-head comparison shows the `ΔV`-guided algorithm scoring *slightly worse* than the original heuristic-only Staten 2010 algorithm. HEX-SHEETCHOICE-3 (doublet-avoidance guard for self-intersecting columns) stands independently as a reusable topology-preservation primitive |
| Zhao, Xu, Xiao, Wu, Gu, Liu, Pang 2023/2024 (Bc-hexmatching), EwC 40:2209-2226 | base-complex-localized mesh matching (column-collapse depth-bounding on the singularity/sheet skeleton) + a follow-up SLIM-based stitching-energy vertex optimization to clean up interface inversions | 18/18 | `10.1007/s00366-023-01908-6` | full text | **different trigger condition** (inter-part interface gluing between two independently-generated hex meshes, not intra-mesh singleton repair) — do not cite as bracket validation; its multi-component demo (Example 5) is sequential pairwise gluing, not simultaneous multi-cluster intra-mesh repair. Reusable only as **secondary technique donors**: depth-bounded base-complex localization as a generic repair-scope bound (HEX-ZHAO-1) and the SLIM stitching energy as an inversion-cleanup pass after any local topology-changing repair (HEX-ZHAO-2) (`zhao2023_bc_hexmatching.md`). HEX-ZHAO-3 (full sequential multi-patch pipeline) is explicitly out of current scope, contingent on AutoTessell ever adopting domain-decomposition generation |

No inaccessible paper in this batch. The 2026-07-23 batch (Knupp, Ledoux, HEXHOOP, Chen) cleared four of the five paywalled entries from the forward sweep's download queue. The 2026-07-25 round-2 batch (Staten 2010, Daines 2018, Ledoux 2013, Chen 2016, Zhao 2023/2024) cleared all five P0/P1 candidates from `gap_search_transition_repair_round2_2026-07-25.md`'s FULL_READ queue.

## 2026-07-25 round 2 synthesis — HEX-MATCH primary mechanism

Across all 7 recent full-reads this campaign (Elsheikh 2014, Chen 2026 CJA — both from round 1's gap search — plus the 5 above), the converged design for native_hex's post-snap quality lane is:

**Staten 2010's depth-bounded local mesh-matching architecture** (pillow / sheet extraction / column collapse — the same operator catalog already scoped topologically in `ledoux2010_sheet_operations.md`), **gated by our own OpenFOAM skew metric, not any borrowed metric** (neither scaled/MSJ Jacobian nor Chen 2016's topological `ΔV`). This is not a preference — it is forced by three independent findings converging on the same conclusion:

1. **`HEX-ECR-4`** (this project's own measurement, `native_hex_literature_integrated_development_plan_2026-07-23.md` Phase 1): MSJ-vs-OpenFOAM-skew Spearman correlation is strong on average (ρ = -0.886 to -0.476 across 4 shapes) but **worst-tail Jaccard overlap is only 5.0%-32.4%** (pooled 13.1%) — MSJ flags a different set of "worst" faces than our skew gate does.
2. **Chen 2016's own experimental data** (`chen2016_quality_sheet_choice.md`): `ΔV`-guided assistant-sheet selection still lets minimum scaled Jacobian degrade to 0.18-0.37 across its 4 worked examples, and in its one head-to-head comparison against the original (unguided) Staten 2010 algorithm, the "improved," metric-guided version scores *slightly worse*.
3. **Staten 2010's own unmitigated result** (`staten2010_mesh_matching.md`): the paper's worst worked example (prioritizing locality) drops minimum scaled Jacobian 0.9914 → 0.4691 with no floor check or rollback anywhere in Algorithm 1.

No literature-borrowed proxy metric is trustworthy for our specific failure mode. The fix is the **same guarded-transaction pattern already validated 6+ times this session in native_tet/native_poly**: simulate the candidate operation, measure with our own metric on the affected neighborhood only, reject if it doesn't strictly improve, never partially apply.

**Scope split** (do not conflate the two damage topologies):

- **Cylinder/sphere/gear (isolated singleton bad faces):** Staten's demonstrated scale (single dual column/sheet, depth-1/2 local edit) fits directly. This is the primary target — `HEX-MATCH-1/2`.
- **Bracket (7-connected-component/6-patch damage):** NOT validated by any of the 7 full-read papers. Ledoux 2013 explicitly excludes multi-component geometry as future work; Staten 2010 restricts its input requirements to single-surface interfaces; Zhao 2023/2024's multi-component demonstration is sequential pairwise inter-part gluing, not our intra-mesh multi-cluster case. Must be its own separate, flagged-uncertain experiment (`HEX-MATCH-3`), never assumed to work via the same mechanism.
- **Daines 2018** is NOT directly portable (its whole problem is specific to the 8-split mixed tet/pyramid/wedge/hex octree family, not our pure-hex Maréchal-style dual) but its **iteration-bounded (cap 3) labeling loop concept** and its **honest reporting of collateral neighbor-quality damage** are worth keeping as a secondary diagnostic pattern (`HEX-DAINES-1/2`).
- **Zhao 2023/2024's SLIM/Gao-2017 stitching energy** is a candidate for cleaning up any inversions introduced by a local repair, independent of the main mechanism (`HEX-ZHAO-2`).
- **Ledoux 2013's dihedral-angle/chord-count geometric decision rule** is a candidate for choosing WHERE pillowing helps sharp-feature preservation specifically, as a secondary input alongside our skew measurement, not a replacement for it (`HEX-LEDOUX13-1/2/3`).

## Forward sweep outcome (2026-07-23)

`forward_citation_sweep_2026-07-23.md` screened 22 candidates across four axes (octree templates, untangling, sheet operations, hex-dominant honesty) and declared saturation. P0 adoption directions with access status:

- **Pitzalis et al. 2021** (`10.1145/3478513.3480508`, open PDF + open code) — octree-template replacement candidate over Zhang 2013: conforming all-hex templates on *weakly balanced* adaptive grids, fewer refinement propagations. Companion theory: Livesu et al. 2022 Optimal Dual Schemes (`10.1145/3494456`, open via arXiv) decides when the dual path may claim all-hex (HEX-OCT-2 decision input).
- **Edge-Cone Rectification 2015** (`10.1145/2766905`, open project page) + **HexOpt** (arXiv `2410.11656`, open; journal DOI unverified) — the post-snap boundary-skew lane: positive-Jacobian enforcement and surface-constrained scaled-Jacobian optimization. Confirmed by the Knupp full read to strictly dominate the classic untangling objective.
- **Gao, Shen, Panozzo 2019** (`10.1111/cgf.13795`, open author PDF; code vendored in-repo at `Feature-Preserving-Octree-Hex-Meshing/`) — feature preservation + positive-SJ-by-construction; unblocks the ridge/corner provenance card.
- The prior remaining-paywall entry, **Qian & Zhang 2010**, was supplied and fully read on 2026-07-27 (`qian2010_sharp_feature_octree.md`). No unread item remains from that queue.

Full-read verification notes against the sweep's screening claims: the sweep's "P0 pair subsumes Knupp" claim is confirmed with two survivals (beta margin, topology diagnostic); the sweep listed Chen 2026 as a 66-page manuscript but the published PDF is 23 pages, all read. The 2026-07-24 P0 batch (Gao 2019, Pitzalis 2021, Livesu 2022, ECR 2015, HexOpt) additionally corrected the sweep's Pitzalis entry: "installs conforming all-hex templates" is inaccurate — the templates are Livesu 2022's; Pitzalis 2021 contributes the ILP pairing preprocessing (see full-read rows above).

## Current engine audit

| Contract | Current evidence | Literature requirement | Verdict |
|---|---|---|---|
| Surface input | `generate_native_hex(vertices, faces, ...)`; empty rejected; GWN/boolean containment; optional in-engine surface remesh | clean surface; CubeCover/Gao additionally require a tet volume | surface contract exists; frame paths need explicit tet composition |
| Uniform path | axis-aligned grid + centroid-inside filter, optional snap | spatial grid methods are robust but boundary-limited | viable draft baseline; can lose thin/boundary-cut regions |
| Adaptive path | fine grid, surface distance/features, 2:1 levels, split coarse faces, generic writer | Maréchal needs pairing + directional primal cuts + dual for all-hex; HEXHOOP-class conversion of the transitions is ruled out (wrong input class, 49-60x cost) | conforming polyhedral transition, not proven all-hex; precise gap per the Pitzalis/Livesu reads: (1) no pairing check/refinement stage, (2) no proven dual scheme set — the all-hex route, if pursued, is Livesu 2022 dual schemes + a pairing stage (octree-rule first, Pitzalis 2021 ILP as later optimization), not template conversion |
| Cell identity | adaptive result reports cell count and generic quality only | Gao reports hex number/volume fractions and irregular cells; Chen 2026 QHED adds distribution (ScoreCHE adjacency + cluster census) | census still missing, but the methodology gap is closed: HEX-HD-1 counts + HEX-HD-5 ScoreCHE/cluster BFS give the truthful census contract to implement |
| Feature recovery | nearest triangle/feature snapping with local guards | stable boundary face/ridge/corner targets + constrained projection | partial geometric snap; provenance/topology absent |
| Quality | negative volume, non-orthogonality, skewness, aspect; some local revert | Maréchal element objective; Gao topology invariant but admits invalid geometry; Knupp 2001: positivity should carry a volume-scaled margin, not just > 0 | useful gate; generic cell validity and self-intersection need transactional checks; upgrade the neg-vol gate to a beta-margin criterion (HEX-UNTANGLE-1) |
| Frame field | absent | 24-way cube symmetry, singularity graph, boundary alignment | absent |
| Agglomeration | absent | classified collapse/dissolve/split with topology invariant | absent |
| BL linkage | `post_layers_engine=auto` selects `native_hex_bl`; Cycle38 measured that its outward extrusion displaces the authoritative wall by the requested total thickness, so positive requests now fail closed before writing | all-hex buffer topology for Maréchal; Reberol 2023 fixes the input boundary and moves/untangles only interior layer geometry; mixed layers acceptable only if reported | `BL=0` remains an exact no-op; positive all-hex BL support remains open behind a source-surface hard guard; the next primitive must use a fixed outer boundary and an inward interface transaction |
| Patch provenance | single surface defaults to `defaultWall`; boolean surfaces can classify named patches | BL must select exact wall patches and preserve source intent | acceptable default; multi-source contract present but needs end-to-end tests |

Existing octree tests verify cell production, file creation, refinement counts, and surface-distance helpers. They do not enumerate cell shells. `test_native_hex_sphere_produces_only_hexahedra` explicitly uses an indirect face-count plausibility check because `NativeMeshChecker` has no cell-type census; its name therefore overstates its assertion.

## Architecture decision

Maintain two explicit engines, not one ambiguous `native_hex` label:

1. `octree_hex_dominant`: production near-term. Axis-aligned cells, generic polyhedral transition allowed. Must report exact cell-type/volume ratios, boundary error, and validity.
2. `field_hex_dominant`: research/medium-term. Native-tet input, quaternion orientation field, integer position field, transactional agglomeration.

Optional third target only after proof:

3. `octree_all_hex`: Maréchal-style pairing, directional primal cuts, dual construction, topology buffer layers, constrained projection.

CubeCover remains a topology/parameterization reference. Its manual meta-mesh and possible flipped parameterization make it unsuitable as automatic default.

## Ranked implementation cards

| Rank | Card | Measurable completion |
|---:|---|---|
| P0 | HEX-HD-1 truthful cell census | exact type/volume totals; adaptive output no longer called all-hex without evidence |
| P0 | HEX-OCT-3 surface intersection + local thickness | no vanished thin component; two cells across thickness when budget permits; explicit budget failure |
| P0 | adaptive generic-cell validity | zero negative volume/self-intersection; cell shell closed; face owner count 1/2 |
| P1 | stable face/ridge/corner provenance | ridge/corner test keeps target identity through all snap iterations |
| P1 | hex/BL contract | auto route explicitly returns mixed cells or uses wired guarded quad-to-hex BL; reports post-BL type ratios |
| P1 | HEX-OCT-2 transition choice | either real dual all-hex tests pass or engine/documentation declares polyhedral transitions |
| P2 | HEX-HD-2 topology transaction kernel | local face-circle/cell-sphere invariants after every accepted edit |
| P2 | HEX-HD-3 orientation/position field prototype | deterministic cube/tube/torus tests; decreasing energy; boundary alignment |
| P3 | CubeCover-like global parameterization | positive mapped tet determinants and pure-hex extraction on small canonical cases |

### Consolidated candidate cards from the 2026-07-23 batch

Falsifiable cards defined in the four new full-read notes (full pass/stop criteria live in each note; no overlap with the ranked table above — these extend it):

| Card | Source note | One-line contract |
|---|---|---|
| HEX-SHEET-1 | `ledoux2010_sheet_operations.md` | sheet extraction (seed-edge traversal + simultaneous collapse + geometric-feature guard) to delete a worst wall-adjacent layer; pass = conforming all-hex, skew below 3.0 gate, wall_dev < 0.02; stop if bad cells do not form one coherent sheet |
| HEX-SHEET-2 | `ledoux2010_sheet_operations.md` | pillowing as per-patch BL primitive: verify manifold quad set, inflate to hexes, place nodes at first-layer height; pass = all-hex, one boundary face per wall hex, skew gate holds after relaxation |
| HEX-UNTANGLE-1 | `knupp2001_untangling.md` | replace `negative_volumes == 0` acceptance with `min corner Jacobian >= beta * local mean cell volume` (local, not Knupp's global Vbar); falsified if every passing mesh already clears any reasonable beta |
| HEX-ALLHEX-1 | `yamakawa2002_hexhoop.md` | conversion-cost gate for any future all-hex conversion pass: adoption requires multiplication < 8x and no secondary scaled-Jacobian mode below 0.5, reported with provenance-split histograms — bounds HEXHOOP itself cannot meet (60x, 0.4 mode) |
| HEX-HD-5 | `chen2026_hex_quality.md` | ScoreCHE + hex cluster census (BFS over hex-hex faces) on top of the HEX-HD-1 truthful census: report `score_che`, `n_hex_clusters`, `largest_cluster_frac`; all-hex cube must score 1.0 / 1 cluster |
| HEX-ECR-1 | `livesu2015_edge_cone_rectification.md` | cone feasibility census (diagnostic, no solver): per-directed-edge worst cone angle histogram on the post-snap mesh; falsified if worst-skew faces do not coincide with worst-α cones |
| HEX-ECR-2 | `livesu2015_edge_cone_rectification.md` | interior-only ECR with surface hard-frozen; pass = zero negative volumes, wall_dev bit-identical, boundary skew ≤ 2.84; stop rule routes to HEX-ECR-3 if the frozen ring dominates |
| HEX-ECR-3 | `livesu2015_edge_cone_rectification.md` | tangent-plane sliding mode (Eq 21 vertex classes: wall=tangent plane, feature=tangent line, corner=pinned; β sweep); pass = skew < 2.84 with wall_dev_max < 0.02 hard veto |
| HEX-ECR-4 | `livesu2015_edge_cone_rectification.md` | metric bridge diagnostic: scatter min corner-tet SJ vs OpenFOAM per-face skew on ≥3 bench meshes; if no monotone-ish bad-tail relation, ECR gains must be re-scored under our checker before further porting |
| HEXOPT-REFINE-1 | `tong_hexopt.md` | plan-wording correction: HexOpt targets are recomputed closest points every iteration — vertices move on the *surface* (sliding), not on fixed wall-fit targets; bench must test both the frozen and sliding contracts |
| HEXOPT-IMPL-1 | `tong_hexopt.md` | ReHQJ energy port (QJ=J/ē for J≤0, QSJ=SJ·ē² for 0<SJ≤Θ, ē constant in gradient); pass = untangles a synthetically tangled cube grid and gradient is scale-invariant under x0.01/x100 rescale |
| HEXOPT-IMPL-2 | `tong_hexopt.md` | AL + Θ-continuation schedule (Θ: 0→+0.01 warm-started, ρ doubling, λ update); stage gate = ΣReSJ = Nh·Θ AND max‖x−x^t‖ ≤ our wall_dev gate (not blindly 1e-8); pass = boundary skew strictly decreases with wall_dev held at every exported stage |
| HEXOPT-IMPL-3 | `tong_hexopt.md` | resolve the η=0.5 (text) vs 0.9 (Algorithm 2.2) backtracking discrepancy from CMU-CBML/HexOpt source before porting; pass = constant documented with a source citation |

### Consolidated candidate cards from the 2026-07-25 round 2 batch

Falsifiable cards defined in the 5 round-2 full-read notes (full pass/stop criteria live in each note; renamed with distinct `HEX-MATCH`/`HEX-DAINES`/`HEX-LEDOUX13`/`HEX-SHEETCHOICE`/`HEX-ZHAO` prefixes specifically to avoid collision with the pre-existing `HEX-TRANS-1/2/3` names already used — non-identically — in both `elsheikh2014_octree_transition_preconditioning.md` and `chen2026_cja_hanging_node_transition.md`):

| Card | Source note | One-line contract |
|---|---|---|
| HEX-MATCH-1 | `staten2010_mesh_matching.md` | depth-bounded local repair for one flagged bad hex: identify its dual column/sheet membership (reuse `HEX-SHEET-1` traversal machinery), attempt a depth-1 pillow insertion or single column collapse, smooth only within `depth` of the bad cell; pass = bad cell's metric clears the gate, no cell outside the depth-bounded neighborhood changes, cell-count delta stays small; stop if the dual column is self-intersecting (doublet risk) — fall back to extraction-with-guard or leave flagged |
| HEX-MATCH-2 | `staten2010_mesh_matching.md` | quality-gated repair transaction: perform the trial pillow/extract/collapse within depth N, measure **our own OpenFOAM skew/non-orthogonality metric** (never scaled Jacobian) on the affected neighborhood only, commit only if it does not regress below the existing gate, else increase depth (capped) or abandon and report; replaces Staten's un-verified "smooth and hope" ending (Algorithm 1 line 35) with an explicit floor check |
| HEX-MATCH-3 | `staten2010_mesh_matching.md` | research-only spike (no engine code): test whether independently applying HEX-MATCH-1/2 to each of the bracket's 7 connected bad components is sufficient, or whether cross-component sheet sharing causes conflicting edits; pass/stop rule = if any two components' selected sheets/columns overlap, document the conflict and do not proceed to implementation without a serialization order or Zhao 2023/2024's base-complex approach first — **not validated by any source paper**, flagged uncertain-outcome |
| HEX-DAINES-1 | `daines2018_octree_transition_repair.md` | bounded iterative boundary re-snap loop (secondary/diagnostic): label nodes of cells below our skew/negative-Jacobian gate, re-run boundary-snap restricted to those nodes plus newly-implicated neighbors, recompute quality, repeat; stop rule ported directly: **cap at 3 iterations** (paper measured propagating, not converging, damage beyond that) |
| HEX-DAINES-2 | `daines2018_octree_transition_repair.md` | measure collateral damage to good neighbors, not just bad-cell resolution rate: run any HEX-DAINES-1-style repair at both a strict and a loose quality threshold and report before/after skew of cells *adjacent to* the repair, not just the repaired cells — a repair that "succeeds" narrowly but silently degrades neighbors is a false positive under our measurement-first rule |
| HEX-DAINES-3 | `daines2018_octree_transition_repair.md` | whole-mesh single-pass labeling for multi-component damage (bracket-relevant, **unverified**): process all 7 bracket clusters under the same shared 3-iteration budget rather than 3-per-component; explicit non-claim — the source's own test domains are single-component smooth organic shapes, do not assume the pattern transfers without separate measurement |
| HEX-LEDOUX13-1 | `ledoux2013_cad_topology_correction.md` | CAD dihedral-angle curve-label diagnostic (no mesh edit): for every sharp edge/curve group, compute the maximal dihedral angle and ideal label `w_g` in {1,2,3,4}, plus actual current chord count; pass = report `(ideal_label, actual_chord_count, deficit/surplus)` per curve, purely diagnostic; stop rule = bucket by feature-edge type instead of raw angle if dihedral extraction is noisy on faceted STL boundaries |
| HEX-LEDOUX13-2 | `ledoux2013_cad_topology_correction.md` | constrained labeling + single-sheet pillow insertion (single-component only): implement the vertex-valence validity table + branch-and-bound labeling solver against a single coherent CAD body, using the HEX-SHEET-2 pillowing primitive as the insertion mechanism, targeting sharp edges flagged under-provisioned by HEX-LEDOUX13-1; pass = checkMesh stays clean and all-hex, chord count matches/exceeds ideal label, wall_dev_max and skew re-measured (not assumed); stop = never on multi-component/bracket geometry |
| HEX-LEDOUX13-3 | `ledoux2013_cad_topology_correction.md` | re-classification transaction for inflated faces: after HEX-LEDOUX13-2 inflates a face path, explicitly verify and record the CAD geometric association (surface/curve/vertex) of every new node/edge/face rather than leaving it implicit; pass = a synthetic chamfered-cube test shows the new layer's outer faces correctly classified, not left unclassified/misclassified |
| HEX-SHEETCHOICE-1 | `chen2016_quality_sheet_choice.md` | reuse the enumeration architecture, replace the metric: implement candidate enumeration (existing sheets + inflatable quad sets local to a flagged bad face), rank and commit only against **our own OpenFOAM skew delta** (per the 2026-07-25 synthesis above) — do **not** implement `ΔV`/EEVS at all; pass = repair pass considers >1 candidate per bad face when >1 exists, commits only the candidate that actually reduces the flagged face's skew |
| HEX-SHEETCHOICE-2 | `chen2016_quality_sheet_choice.md` | falsify (or confirm) valence-irregularity as a cheap pre-filter (diagnostic only, no engine change): compute `ValVar`/`ΔV`-style edge-valence irregularity on the existing 4-shape ECR-4 dataset's flagged bad faces, measure Spearman correlation and worst-tail Jaccard overlap against our OpenFOAM skew metric exactly as done for MSJ; pass/stop = if it correlates no better than MSJ's -0.886/-0.476 range and 5-32% overlap band, do not adopt `ΔV` as a repair-pass metric — HEX-SHEETCHOICE-1 proceeds as specified regardless |
| HEX-SHEETCHOICE-3 | `chen2016_quality_sheet_choice.md` | doublet-avoidance guard for self-intersecting local operations: never collapse a self-intersecting column directly; translate local self-intersecting extraction into local self-intersecting inflation instead, as a reusable primitive inside any repair pass touching sheets/columns near a bad face; pass = a synthetic self-intersecting-sheet fixture is detected and rejected/rerouted before any topology mutation commits; prerequisite = HEX-MATCH-1's dual/sheet-traversal machinery must exist first — this stands independently of the SHEETCHOICE-1/2 metric decision above |
| HEX-ZHAO-1 | `zhao2023_bc_hexmatching.md` | depth-bounded base-complex localization as a generic repair-scope bound: borrow the column-collapse-to-keep-a-sheet-within-depth-`d` construction as the scope-limiting primitive for any dual-sheet repair near an isolated octree-transition singleton, replacing ad-hoc N-ring cell selection; pass = verify a base-complex-localized repair only ever touches cells within the specified depth (base-complex distance, not Euclidean/BFS) across ≥3 depth settings, report affected-cell count per depth |
| HEX-ZHAO-2 | `zhao2023_bc_hexmatching.md` | SLIM-based post-repair stitching energy to remove inversions: reuse Gao et al. 2017's `E = E_D + λ_t E_S + λ_f E_F` (distortion + point-pair stitching + boundary-feature deviation), solved via SLIM, as the vertex-position cleanup pass after a topology-changing singleton repair; pass = apply to native_hex's own singleton-repair output (cylinder/sphere/gear), report MSJ/ASJ before/after, zero negative scaled Jacobians after — matching the paper's own empirical (not proven) result pattern |
| HEX-ZHAO-3 | `zhao2023_bc_hexmatching.md` | sequential pairwise multi-patch matching (lower priority, **out of current scope**): only relevant if AutoTessell ever adopts domain-decomposition hex generation; adopts the full simplify→match→inflate→segment-match→SLIM-stitch pipeline using the demonstrated sequential-pairwise pattern; explicitly not a solved answer for the bracket's damage inside a single already-generated mesh |

**Bracket-relevance caveat (applies to every card above touching multi-component damage):** HEX-MATCH-3, HEX-DAINES-3, and HEX-ZHAO-1/2/3 transplant only mechanisms or scope-bounding primitives — none of the 5 round-2 papers validates a many-cluster-at-once intra-mesh repair strategy for the bracket's 7-component/6-patch damage. Treat bracket applicability as unmeasured until HEX-MATCH-3's own spike runs.

## Falsification rules

- `2:1 balance` alone never supports an `all-hex` claim.
- `manifold` never implies positive Jacobian or no self-intersection.
- `hex ratio` never substitutes for per-cell validity.
- nearest-surface projection never establishes a Hausdorff bound without bidirectional envelope checks.
- code comments naming Hexotic, snappyHexMesh, TetWild, or T-Rex never establish algorithmic equivalence.
- post-BL result must be classified again; pre-BL hex dominance cannot be carried forward implicitly.

## Next literature queue

Batch 2 (2026-07-23) cleared the previous queue: Ito 2009, Sokolov 2016, HexEx, plus HybridOctree_Hex, Ray 2016, HexHex, and the Pietroni survey are FULL_READ (`batch2_core_papers.md`, master bibliography). The 2026-07-24 P0 batch cleared the sweep's top five: Gao 2019, Pitzalis 2021, Livesu 2022, ECR 2015, and HexOpt are FULL_READ (rows above). Remaining queue (all open access unless noted):

- Maréchal 2016, All hexahedral boundary layers generation, Procedia Eng. 163 — dual-approach + BL junction; direct contact point with our Tier-4 BL pass (Livesu 2022 snowball, priority pick).
- Ray et al. 2018, Hex-dominant meshing: Mind the gap! DOI: `10.1016/j.cad.2018.04.012`.
- Pellerin et al. 2018, tet-combination enumeration. DOI: `10.1016/j.cad.2018.05.004`.
- Cherchi et al. 2019, Selective Padding + Mitchell/Tautges 1995, Pillowing doublets (pair for the boundary-repair lane).
- Qian, Zhang 2010, sharp-feature pillowing. DOI: `10.1007/978-3-642-15414-0_15` (`FULL_READ`, 18/18 pages, user-supplied 2026-07-27; see `qian2010_sharp_feature_octree.md`).

## 2026-07-26 HEX-SHEET-2 layer-wide shrink-set falsification

The report-only census (`core/generator/native_hex/sheet_diagnostic.py`,
`scripts/diag_hex_sheet2.py`) measured the proposed `S = all physical-boundary
quad owner cells` and its `S`/core interface `Q` on the actual fine pre-BL
native_hex cylinder, sphere, and gear meshes at `max_cells=8000`.

| Shape | `S` / nonhex | `Q` quad / nonquad | edge incidence | components / open / nonmanifold | boundary / interface faces per `S` cell | `Q` vertices also on physical boundary |
| --- | --- | --- | --- | --- | --- | ---: |
| cylinder | 1640 / 0 | 1816 / 0 | `{2:3632}` | 1 / 0 / 0 | `{1:1096,2:496,3:48}` / `{0:112,1:1240,2:288}` | 380 |
| sphere | 968 / 0 | 1560 / 0 | `{2:3120}` | 1 / 0 / 0 | `{1:360,2:288,3:320}` / `{1:528,2:288,3:152}` | 756 |
| gear | 2594 / 0 | 2152 / 0 | `{2:4304}` | 1 / 0 / 0 | `{1:1733,2:570,3:208,4:64,5:19}` / `{0:858,1:1352,2:352,3:32}` | 363 |

Measured conclusion: the Ledoux manifold-quad precondition passes, but the
AutoTessell wall-cell incidence contract (one physical-boundary face and one
interface face per shrink cell) fails on every shape, and `Q` is not
vertex-disjoint from the physical boundary. The proposed point/cell growth was
`+1818/+1816`, `+1562/+1560`, and `+2144/+2152`, respectively, but was not
executed. The all-wall-owner layer-wide pillow is therefore rejected before
topology implementation; no production flag or mesh-editing path was added.

## 2026-07-26 HEX-PATCH-LAYER-DIAG1 strict subset census

| Card | Input / mode | Strict contract | Measured result | Decision |
|---|---|---|---|---|
| HEX-PATCH-LAYER-DIAG1 | actual cached fine pre-BL cylinder/sphere/gear, `max_cells=8000` | exactly one physical-boundary face per S cell; exactly one two-owner quad Q per S cell; same patch/provenance; Q vertices disjoint from physical-boundary vertices; per-subset Q closed and manifold | cylinder 544/544 eligible S/Q in 6 components, sphere 24/24 in 6, gear 888/888 in 22; strict Q open edges 272/48/656; non-manifold edges 0/0/0; physical-boundary Q vertices 0/0/0 | **KILL** — zero valid subsets and zero approved pillow operations |

The `.npz` cache has no boundary-file patch metadata. For this measurement,
patch identity is reconstructed by the same deterministic feature-dihedral
grouping used by the writer, while the current native_hex single-source
provenance is explicitly `defaultWall`. This keeps the test honest about what
is measured: a writer-equivalent patch label plus known source provenance, not
invented multi-source labels.

The strict edge-incidence result is evaluated separately for each exact
patch/provenance component. A raw union of Q faces can make adjacent openings
appear paired across a patch boundary; accepting that union would violate the
same-patch requirement. Component summaries are: cylinder `wall_0` = four
32/32 components, `wall_2` and `wall_4` = one 208/208 component each; sphere
`wall_0` = six 4/4 components; gear = two 420/420, four 4/4, and sixteen 2/2
components. All are open and none is non-manifold.

The predicted operation is report-only `pillow` per candidate component
(hypothetical point/cell growth `+686/+544`, `+54/+24`, `+1228/+888`), with
approved operation count `0/0/0`. Two repeated analyses of each cache blob
returned identical reports and did not mutate the arrays. No wall_dev/skew
gate was changed, no production flag or topology edit was added, and the card
does not propose a follow-up implementation card because no valid subset
exists.

## 2026-07-26 HEX-TRANSITION-PROVENANCE-DIAG1

The new opt-in report-only census records builder-side grid origin/target level
metadata and the writer boundary. It does not change generated points/cells or
enable a repair path. With `max_cells=8000`, fine pre-BL measurements were:

| Shape | builder / writer cells | level histogram | generic template | transition cells / faces | feature segments / refined cells | writer metadata forwarded |
| --- | ---: | --- | --- | ---: | ---: | --- |
| cylinder | 6320 / 6320 | `{4: 6320}` | `{uniform: 6320}` | 0 / 0 | 64 / 61 | no |
| sphere | 4224 / 4224 | `{4: 4224}` | `{uniform: 4224}` | 0 / 0 | 0 / 0 | no |
| gear | 4920 / 4914 | `{4: 4920}` | `{uniform: 4920}` | 0 / 0 | 592 / 0 | no |

At this exact benchmark setting all emitted builder cells are level 4; the
existing `n_coarse`/`n_fine` summary counters are approximate counters and do
not establish that mixed-level transition cells reached the output. Therefore
the current three meshes cannot be used to justify a transition-sheet quality
repair. The generic writer receives final connectivity but not authoritative
octree lineage, transition-chain/hanging-node data, emitted template identity,
feature provenance, or boundary patch/source provenance. `HEX-TRANSITION-DIAG1`
remains `BLOCKED` for this reason.

The gear path loses six cells at the existing generic-writer degenerate-cell
filter. This is a separate `HEX-WRITER-DEGENERATE-DROP-DIAG1` audit target,
not evidence that a transition repair is needed. Two repeated provenance runs
were deterministic and did not mutate input arrays. Relevant native_hex tests
passed (`55 passed`; targeted provenance group `4 passed`). No production flag,
surface gate, snap behavior, or quality gate was changed.

## 2026-07-26 HEX-OCT-ADAPTIVE-TRANSITION-REALIZATION-DIAG1

The finest-first `block_sz == 1` condition was isolated behind
`AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION`, default OFF. With the flag ON, a
4×4×4 synthetic input requesting `{1: 8, 2: 56}` emitted `{1: 1, 2: 56}`
cells, one transition cell, three transition directions, and 12
coarse→fine interface faces. Face incidence was `{1:87, 2:132}` and the
generic template histogram was `{t21:1, uniform:56}`.

Forced-ON real-shape integration was rejected: builder populations became
cylinder `2463`, sphere `2684`, and gear `4542`, while five native_hex
permanent-gate assertions failed, including curved-wall fidelity, boundary
skew, fine negative-volume, and adaptive cell-budget behavior. The mechanism
is therefore retained only as a default-OFF experimental lane. The default
path remains green (`57 passed`).

Realization is now observed, but transition quality is not certified. The next
card is `HEX-OCT-TRANSITION-QUALITY-1`: measure signed volume, face warpage,
local skew, boundary face-set, and writer cell drops on the opt-in output before
any default change or repair-template work.

### 2026-07-26 HEX-OCT-TRANSITION-QUALITY-1 result (measured, production promotion rejected)

Added the opt-in report-only census
`core/generator/native_hex/transition_quality.py`, the real-shape runner
`scripts/diag_hex_transition_quality1.py`, and one synthetic regression case.
The census records emitted signed volume, orientation-free volume, face
warpage, canonical face skew, boundary face keys/area, face incidence, and
builder-to-writer cell drops. It never repairs, rejects, or reorders cells.

| Shape | transition cells/faces | builder→writer cells | writer drops | boundary area builder→writer | boundary set |
|---|---:|---:|---:|---:|---|
| cylinder | 173/229 | 2463→2445 | 18 | 11.535→11.782881 | changed |
| sphere | 63/111 | 2684→2684 | 0 | 32.780→26.667228 | equal |
| gear | 11/36 | 4542→4534 | 8 | 14.608957→14.321374 | changed |

Transition-cell skew p95/max was cylinder `2.123554/133.752485`, sphere
`1.268530/1.620019`, and gear `1.149741/1.422732`. Transition-cell warpage
p95/max was cylinder `1.0/1.0`, sphere `0.219133/0.219133`, and gear `0.0/0.0`.
The builder had 0/0/5 negative emitted signed volumes for cylinder/sphere/gear;
the writer had 0/0/4. The orientation-free volume baseline remains separate
and is not used to hide signed-winding failures.

The synthetic `{level 1: 8, level 2: 56}` fixture reported one transition cell,
three transition faces, 12 coarse-to-fine interface faces, and face incidence
`{1:87,2:132}`. Therefore transition realization is observed, but the real
opt-in output is not quality-certified. The mixed-level flag remains
default-OFF. Targeted tests passed (`3 passed`), and the full native_hex file
group passed (`113 passed in 141.77s`). The next card is writer-boundary and
face-winding contract isolation, not a repair-template port.

### 2026-07-26 HEX-OCT-TRANSITION-WRITER-1 result (measured, writer exonerated)

The report-only census now mirrors the generic writer's visible degenerate-face
contract and compares predicted drop IDs with the actual writer result. The
match was exact on both real shapes that lost cells:

| Shape | predicted/actual drops | predicted exposed / actual added boundary keys | removed boundary keys | boundary count |
|---|---:|---:|---:|---:|
| cylinder | 18/18 | 60/60 | 44 | 3699→3715 |
| sphere | 0/0 | 0/0 | 0 | unchanged |
| gear | 8/8 | 23/23 | 19 | 4738→4742 |

The first cylinder example is builder cell 145, face 5,
`[1113,1134,1135,1114]`; after snap its four points are two coincident pairs
and the face area is exactly 0.0 (`writer_area_eps≈3e-24`). The first gear
example is cell 329, face 3, `[1937,1938,2225,2224]`, with the same two-pair
coincidence. These drops therefore arise before writer filtering, and the
boundary changes are the deterministic owner reclassification caused by
removing those cells.

Decision: **measured, writer exonerated**. No writer filtering relaxation or
boundary change was made. The next root-cause card is to bisect builder →
iterative snap → wall-fit → skew-relax and identify which upstream stage first
creates the zero-area transition faces.

### 2026-07-26 HEX-OCT-WALLFIT-FACE-AREA-GUARD-1 result (partial, default-OFF)

The stage-bisected diagnosis showed cylinder and gear first acquired writer
drop candidates at `after_wall_fit`; iterative snap remained at zero predicted
drops. An opt-in `_wall_fit_snap` face-area guard was then tested under
`AUTO_TESSELL_HEX_WALLFIT_FACE_AREA_GUARD=1`. It rejects/backtracks a candidate
when any incident face becomes zero-area, while preserving the existing sign,
volume, distance, and envelope checks.

| Shape | writer drops | boundary set | transition skew p95/max | transition warpage p95/max |
|---|---:|---|---:|---:|
| cylinder | 0 (18→0) | equal | 2.150564/133.752485 | 1.0/1.0 |
| gear | 0 (8→0) | equal | 3.279938/11.460936 | 0.888786/1.0 |

The guard prevents the boundary/topology loss but does not restore acceptable
transition quality; gear's builder-side five negative emitted signed volumes
also remain. It is therefore a **partial diagnostic candidate**, kept
default-OFF, not a production quality fix. The next card must measure a
transition-aware wall-fit quality constraint rather than relaxing the writer or
claiming the face-area guard solves the transition problem.

### 2026-07-26 HEX-TRANS-2 result (measured, falsified)

The report-only cross-tab compared boundary faces with canonical skew `>=2.0`
against builder metadata-labelled transition cells and a broader transition-
vertex adjacency proxy. Conditions were actual cylinder/sphere/gear fine
pre-BL runs at `max_cells=8000`, mixed-level realization ON, default wall-fit,
and face-area guard OFF. The proxy is not an authoritative hanging-node chain
label because the current output does not carry that lineage.

| Shape | stage | bad boundary faces | transition owner | owner rate | transition-vertex adjacent | vertex rate |
|---|---|---:|---:|---:|---:|---:|
| cylinder | after wall-fit/final | 550 | 36 | 6.545% | 168 | 30.545% |
| sphere | after wall-fit/final | 960 | 0 | 0% | 0 | 0% |
| gear | after wall-fit/final | 135 | 10 | 7.407% | 22 | 16.296% |

Before snap and after iterative snap all three shapes had zero bad boundary
faces under this threshold; the counts appeared at wall-fit and did not change
in the final stage. The corresponding total boundary populations were
cylinder `588/1705`, sphere `267/677`, and gear `63/275` for transition-owner /
transition-vertex-adjacent faces.

Decision: **measured, falsified** for a transition-local concentration
hypothesis. Most bad faces are outside even the broad transition-vertex proxy,
and sphere has no overlap at all. Do not implement a transition-only repair or
dispatch from this result. The next measurement is a report-only wall-fit
candidate quality transaction over the actual affected neighborhood, with
transition labels retained only as an analysis axis.

The counts are not directly comparable with the earlier wave-0 `85/676`
measurement because the threshold and output lane differ.

### 2026-07-26 HEX-WALLFIT-CANDIDATE-QUALITY-1 result (measured, regression observed)

An opt-in audit was inserted around each `_wall_fit_snap` boundary-vertex
projection. It records incident-cell canonical skew, face warpage, emitted
signed volume, orientation-free volume, global boundary keys, and boundary
area, but does not participate in acceptance or rollback. The diagnostic flag is
`AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG=1`.

At `max_cells=500`, mixed-level realization ON, default wall-fit, and
face-area guard OFF, the wall-fit candidate census was:

| Shape | candidates | full/partial/reject | trial regressions | applied regressions | area changes | max applied skew Δ | max applied warpage Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| cylinder | 128 | 128/0/0 | 128 | 128 | 128 | +1.5313 | +0.4064 |
| sphere | 128 | 128/0/0 | 104 | 104 | 128 | +1.4238 | +0.0571 |
| gear | 271 | 241/12/18 | 207 | 186 | 238 | +1.2518 | +0.7688 |

Boundary face keys stayed equal for all candidates; area changed because the
operation is a boundary-vertex relocation. Maximum absolute area changes were
cylinder `0.01118`, sphere `0.05576`, and gear `0.01892`.

A larger cylinder `max_cells=2000` census yielded `560` candidates,
`358/179/23` full/partial/reject, `515` trial regressions, `481` applied
regressions, and `521` area changes. Its skew maximum was an unstable
near-zero-normal-distance outlier (`2.7756e13`), so no absolute quality gate is
derived from it.

Decision: **measured, quality regression observed**. Existing wall-fit guards
protect distance, envelope, and non-inversion, but do not prevent local skew or
warpage regression. This agrees with HEX-TRANS-2's falsification of a
transition-only concentration. No quality transaction was enabled. The next
card is `HEX-WALLFIT-QUALITY-TRANSACTION-1`: first normalize the skew
denominator and confirm signed-volume orientation, then measure a relative
candidate transaction with surface-area tolerance before any default change.

#### HEX-WALLFIT-QUALITY-TRANSACTION-1 contract precheck

The canonical skew implementation in `NativeMeshChecker` and
`match_diagnostic._quad_skewness` uses the same `max(abs(normal_dist), 1e-30)`
denominator. On the small cylinder census the minimum trial `|normal_dist|` was
`0.0149533` and near-zero count was zero, yet the applied maximum skew delta was
`+1.5313`. Thus that observed regression is not explained by denominator
collapse alone. The larger-run `2.7756e13` value is retained as a separate
denominator-sensitive outlier and is not a gate candidate.

The actual `_wall_fit_snap` no-inversion decision compares native generic
face-signs against a pre-projection reference. The centroid-fan signed-volume
sum in the report-only audit depends on stored face winding and is not promoted
to a production sign gate. The transaction card must use the existing face-sign
contract and a relative quality comparison, not replace it with the audit sum.

### 2026-07-26 HEX-WALLFIT-QUALITY-TRANSACTION-1 result (measured, too restrictive)

The report-only audit computed two hypothetical monotone policies without
changing candidate acceptance: strict max skew/max warpage non-regression, and
p95 skew/p95 warpage non-regression. `combined` requires both.

| Shape | candidates | strict non-regressing | p95 non-regressing | combined | max relative boundary-area change |
|---|---:|---:|---:|---:|---:|
| cylinder | 128 | 0 | 0 | 0 | 0.2266% |
| sphere | 128 | 24 | 0 | 0 | 0.3641% |
| gear | 271 | 85 | 66 | 66 | 0.1702% |

Boundary face-key changes remained zero. The measurements are the low-budget
`max_cells=500` mixed-level opt-in wall-fit stage census; pipeline final success
was not used as evidence for this candidate-level report.

Decision: **measured, naive monotone transaction is too restrictive**. A
quality-only rollback would reject every measured cylinder candidate and could
block the surface-distance improvement that motivated wall-fit. No transaction
was enabled. The next card must cross-tab each candidate's surface-distance /
wall-deviation improvement against its local skew/warpage delta, then define a
relative trade-off if the data supports one. No literature threshold is ported
without that measurement.

### 2026-07-26 HEX-WALLFIT-QUALITY-TRANSACTION-1 surface-distance cross-tab

The audit additionally recorded the actual wall-fit surface-distance reduction
`d_before - d_after` for each accepted full/partial candidate. It remained
report-only.

| Shape | candidates | strict non-regressing | p95 non-regressing | combined | distance-improved | distance-improved + quality regression |
|---|---:|---:|---:|---:|---:|---:|
| cylinder | 128 | 0 | 0 | 0 | 128 | 128 |
| sphere | 128 | 24 | 0 | 0 | 128 | 104 |
| gear | 271 | 85 | 66 | 66 | 253 | 186 |

Total distance reductions were cylinder `5.2117`, sphere `10.8663`, and gear
`16.9085`; maximum single-candidate reductions were `0.06122`, `0.17648`, and
`0.10862`. Boundary face keys remained equal for every distance-improved
candidate.

Decision: **measured, quality-only rollback conflicts with surface fitting**.
Every measured cylinder distance improvement had a local quality regression.
Do not add a monotone quality gate. The next diagnostic must cross-tab the final
wall deviation/surface fidelity benefit against candidate local quality delta on
representative mesh sizes before any Pareto-style transaction is considered.

## 2026-07-26 continuation — HEX-WALLFIT-FINAL-GATE-CROSS1

The report-only diagnostic now prints the final checker/evaluator values from
the same run that produced candidate-level wall-fit snapshots. No candidate
acceptance or gate decision was changed.

| shape / max_cells | candidates | distance improved | distance improved + local regression | combined local non-regressing | final verdict | final cells | max boundary skew | negative volumes | surface area deviation |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| cylinder / 500 | 128 | 128 | 128 | 0 | FAIL | 412 | 2.73027 | 0 | 4.59347% |
| sphere / 500 | 128 | 128 | 104 | 0 | FAIL | 276 | 2.85183 | 0 | 10.0102% |
| gear / 500 | 271 | 253 | 186 | 66 | FAIL | 408 | 1.38997 | 0 | 11.4375% |
| cylinder / 2000 | 560 | 537 | 481 | 49 | FAIL | 1384 | 125.761 | 0 | 87.0928% |

The 500-cell runs retained `negative_volumes=0` and final boundary skew below
the permanent `3.0` threshold, but the overall evaluator verdict remained FAIL
because its other criteria also apply. At 2000 cells, the cylinder's final
boundary skew rose to `125.761` with zero negative volumes. This connects the
candidate-level local regression to a real final-gate failure at scale, but does
not identify a transition-specific cause. The combined hypothetical local
quality policy would accept only `49/560` cylinder candidates while rejecting
most of the `537` candidates that improved surface distance.

Decision: **measured, final-gate connection established; quality-only rollback
rejected**. Do not change the production wall-fit transaction or permanent
thresholds. Open a separate large-budget scale/root-cause card; preserve the
opt-in diagnostic and its deterministic output.

## 2026-07-26 continuation — HEX-OCT-MIXED-LEVEL-ROOTCAUSE-1

The large-budget cylinder was isolated with candidate-quality logging OFF.

| condition | cells / census | final boundary skew | negative volumes | surface area deviation | verdict |
|---|---|---:|---:|---:|---|
| mixed OFF, wall-fit ON | 1781 hex | 3.20865 | 0 | 0.2637% | PASS_WITH_WARNINGS |
| mixed ON, wall-fit OFF | 1363 hex + 22 other | 1.16279 | 0 | 93.4942% | FAIL |
| mixed ON, wall-fit ON | 1363 hex + 22 other | 125.761 | 0 | 87.0928% | FAIL |
| mixed OFF, wall-fit OFF | 1781 hex | 0.974374 | 0 | 15.3787% | FAIL |

Mixed-level is already broken at builder time: `before_snap` has `22`
transition cells, `1479` boundary faces, and `2` report-only signed-negative
cells. `_build_nlevel_cells` splits only the coarse cell face into sub-quads
when it sees a finer neighbor; it does not construct the matching fine-side
transition face/template. This is a nonconforming transition realization, not a
writer-only defect. Wall-fit then amplifies the malformed mixed-level geometry
into the `125.761` final skew case.

Decision: **measured, root cause found**. Keep mixed-level realization and
face-area/quality experiments default-OFF. Open `HEX-OCT-TRANSITION-TEMPLATE-1`
for a separately gated conforming transition implementation; no wall-fit
rollback is authorized as a workaround.

## 2026-07-26 correction — HEX-OCT-TRANSITION-WINDING-1

The earlier “fine-side partition is absent” interpretation is superseded. A
direct synthetic audit shows that, for the 2:1 case, coarse sub-quad keys match
the ordinary fine-neighbor quad keys. The concrete defect was cyclic winding:
all `_sub_quads_on_face` tables were reversed relative to `_HEX_FACES`.

The helper now reverses each sub-quad once at its boundary. The synthetic
transition cell changed from one negative report-only signed volume to zero;
face incidence stayed `{1:87, 2:132}` and targeted transition tests are `4
passed`. On the real mixed cylinder, builder negative signed count changed
`2→0`; with wall-fit OFF the writer emits `1385` cells without drops. The
remaining mixed-level surface/quality failure remains: area deviation `93.4942%`
with wall-fit OFF, and final skew `125.761` / area deviation `87.7568%` with
wall-fit ON.

Decision: **winding correctness subcard measured and fixed; broader transition
quality root cause remains open**. This does not justify default mixed-level
promotion or an all-hex claim, and it does not authorize wall-fit rollback.

### 2026-07-26 HEX-WALLFIT-SURFACE-TRADEOFF-1 result (measured, benefit confirmed)

The same report-only run measured the full wall-fit stage's boundary-vertex
distance to the input surface.

| Shape | boundary vertices | mean before→after | p95 before→after | max before→after |
|---|---:|---|---|---|
| cylinder | 380 | `0.027915→0.014200` | `0.061217→0.003791` | `0.373194→0.373194` |
| sphere | 334 | `0.078905→0.046371` | `0.562459→0.562459` | `0.995472→0.995472` |
| gear | 672 | `0.026542→0.001380` | `0.096807→0.005295` | `0.108621→0.019445` |

Decision: **measured, surface-fidelity benefit confirmed**. Wall-fit improves
mean/p95 surface distance while some incident-cell skew/warpage regresses.
Quality-only rollback conflicts with the surface contract, so no transaction or
new absolute threshold is enabled. The next validation connects candidate local
deltas to the existing final wall-dev/skew gates at representative mesh sizes.

## 2026-07-27 — HEX-OCT-MIXED-LEVEL-COVERAGE-1

The mixed-level surface failure was reproduced and traced to two builder
conditions, not to the generic writer. A finer leaf could mark only the block
origin as covered, leaving other cells in that block un-emitted. Separately,
the coarse cell inspected one neighbor index rather than the whole
face-adjacent slab, missing fine neighbors away from that index. A cylinder
example had `(4,6,6)=4`, `(5,6,6)=3`, `(4,7,6)=3`; the first cell was consumed,
the other cells were skipped, and an internal face became boundary.

The opt-in fix promotes mixed target blocks to finest leaves, safely fills any
remaining partial covered block, and uses the complete adjacent face slab to
choose sub-quad splitting. It does not change the default flag or permanent
gates.

| measurement | before | after |
|---|---:|---:|
| synthetic transition tests | 4 passed | 5 passed |
| synthetic internal boundary holes | observed | 0 |
| real builder inner-looking boundary faces | 155 | 0 |
| real 2,000-cell pipeline cells | 1383–1385 | 1655 |
| signed-negative cells | 2 | 0 |
| writer drops | 2 / malformed prediction | 0 |
| writer boundary face-set | not preserved | equal (`True`) |
| final boundary skew | 125.761 | 3.20865134 |
| surface area deviation | 87.09–93.49% | 0.263700907% |

Final result: `PASS_WITH_WARNINGS`, negative volumes `0`, min volume
`0.00014462409`, max warpage `0.05652146`, boundary area
`4.68488421` vs input `4.69727095`, writer boundary-area delta `-1.13e-9`.
The remaining `3.20865134` skew is above the permanent `3.0` threshold and is
tracked separately as a large-budget quality card. Direct repeated builder
runs produced identical points and cell faces. Native_hex tests: `118 passed`.

Decision: **measured and implemented; mixed-level coverage/topology root cause
closed, scale-quality root cause remains open**. No all-hex claim or default
mixed-level promotion is justified yet.

## 2026-07-27 — HEX-OCT-SCALE-QUALITY-1

After the mixed-level coverage fix, builder-side bad boundary skew is zero;
the remaining bad faces are introduced by `_wall_fit_snap`. Direct comparison
gave `0→80` bad boundary faces (full pipeline: `85`), with zero transition-owner
and zero transition-vertex-adjacent bad faces.

| condition | cells | max boundary skew | area deviation | bad faces | verdict |
|---|---:|---:|---:|---:|---|
| mixed ON + wall-fit ON | 1655 | `3.20865134` | `0.263700907%` | 85 | PASS_WITH_WARNINGS |
| mixed ON + wall-fit OFF | 1655 | `0.974373881` | `15.3787224%` | 0 | FAIL |

The direct wall-fit audit measured `496` distance-improving candidates; `376`
had a local quality regression, `120` were strict local-quality
non-regressions, and `104` passed the combined p95 non-regression test. Boundary
keys never changed. Mean surface distance improved
`0.0167231→0.0007091`; p95 improved `0.0490482→0.00376990`.

Decision: **measured, root cause narrowed but not repaired**. A quality-only
rollback would discard most surface-fidelity benefit, so no production rule or
permanent threshold is changed. Keep `HEX-OCT-SCALE-QUALITY-1` open for a
surface-constrained Pareto/literature-supported repair.

## 2026-07-27 — HEX-WALLFIT-PARETO-1 literature-integrated measurement card

The remaining wall-fit issue is a multi-objective trade-off, not an isolated
transition-template defect. In the representative cylinder, wall-fit ON is
`1655 cells / skew 3.20865134 / area deviation 0.263700907% / 85 bad faces`;
OFF is `1655 cells / skew 0.974373881 / area deviation 15.3787224% / 0 bad
faces`. The candidate audit found `496/496` distance improvements, `376`
local-quality regressions, `120` strict local-quality non-regressions, and
`104` combined p95 non-regressions. Boundary face keys remained equal.

The follow-up literature card is recorded in
`wallfit_pareto_quality_repair_2026-07-27.md`. P0/P1 candidates include
Elsheikh 2014 (`10.1016/j.advengsoft.2014.05.005`), Chen et al. 2026
(`10.1016/j.cja.2026.104154`), HexOpt (`10.1016/j.cad.2026.104073`),
Shepherd et al. 2006, Zhang & Zhao 2010 (`10.1016/j.cagd.2010.05.003`),
Wang et al. 2015 (`10.1016/j.cad.2014.09.003`), and Zheng et al. 2025
(`10.1016/j.cad.2024.103825`). Huang et al. 2022
(`10.1016/j.gmod.2022.101136`) and edge-angle optimization 2018
(`10.1016/j.cag.2017.07.002`) remain context because their boundary-relaxing
behavior conflicts with the frozen surface contract.

Decision: **measured, literature-integrated, implementation deferred**. The
next card is report-only candidate-level Pareto measurement across
cylinder/sphere/gear/bracket. Existing face-key, area, signed-volume,
wall-deviation, skew, and determinism gates remain hard; no default or
permanent threshold is relaxed.

### First Pareto measurement — cylinder

The current `max_cells=2000` full-pipeline diagnostic recorded `350`
candidates and `117` non-dominated candidates. Boundary key changes and
negative-volume increases were both `0`; strict, p95, and combined quality
non-regressions were each `16`. Surface distance mean/p95 changed from
`0.0120959802/0.0380725043` to `0.0005450396/0.0024877153`. The final result
was `1655 cells`, `PASS_WITH_WARNINGS`, skew `3.20865134`, negative volumes
`0`, and area deviation `0.263700907%`.

Decision: **report-only measurement valid; repair rule still open**. The
frontier is not a sufficient acceptance rule because most distance-improving
candidates still regress local quality. Sphere, gear, and bracket remain
required before shape-adaptive dispatch can be considered.

### Three-shape Pareto extension

At the same `max_cells=2000` diagnostic setting:

| shape | final cells | final max boundary skew | candidates | frontier | strict / p95 / combined |
|---|---:|---:|---:|---:|---:|
| cylinder | 1655 | 3.20865134 | 350 | 117 | 16 / 16 / 16 |
| sphere | 1057 | 14.7384497 | 404 | 157 | 36 / 36 / 36 |
| gear | 1296 | 27.0814284 | 531 | 67 | 117 / 108 / 99 |
| bracket | 538 | 19332.7157 | 342 | 41 | 133 / 118 / 115 |

Final negative volumes were `0` and boundary-key changes were `0` in all four
runs. The Pareto frontier is shape-dependent and every final skew is above
the permanent `3.0` gate, so a global threshold or shape dispatch is not
supported. **Measured, implementation deferred.**

## 2026-07-27 — Phase-0 report-only revalidation

The existing Phase-0 metrics were revalidated without changing mesh generation
or acceptance. The cube analytic fixture remains `100% hex`,
`score_che=1.0`, one hex cluster, total volume `1.0`, and β-margin pass. A
synthetic positive-volume cell with one corner Jacobian `0.01` reports a
relative margin ratio below a diagnostic `beta=0.1` and fails only the
report-only β check. This confirms that the margin distinguishes a thin corner
from the cube baseline; no permanent negative-volume gate was changed.

Verification: Phase-0 metrics/transition/provenance/realization/wall-fit tests
`16 passed`; core native-hex regression subset `66 passed`. The existing
permanent gates and default mixed-level/wall-fit flags are unchanged.

## 2026-07-31 — HEX-BL-FIXED-OUTER-INWARD-SHELL-L0-1

A critic rejected commit `5dedfe79`; it must not be merged alone. Its broad
closed-all-quad admission, incomplete generic self-intersection dependency,
and sequential five-file promotion exceeded the evidence.

A second critic rejected commit `4011b195`; it also must not be merged alone.
Directory-level promotion lacked inter-process ownership, so another invocation
could treat a live stage as crash residue. The remediated path holds one
exclusive non-blocking Linux `flock` on the existing `constant` directory inode
from recovery through validation, commit, and controlled cleanup. Mutating
transaction APIs require a live same-inode lock proof. Contention changes no
authoritative or transaction state; process death releases the lock for the
next invocation's recovery. Directory locking creates no cleanup artifact.

The remediated default-OFF path mechanically admits only one axis-aligned
rectangular base hex: 1 cell, 8 finite Cartesian corners, 6 selected boundary
quads/planes, and 12 edges with incidence two. Unit-cube one/three layers and a
non-unit `2x3x4` box pass with source drift `0`, negative volumes `0`, positive
signed-volume/corner-Jacobian gates, and exact lineage. The fixed analytic
limit is `total < 0.90 * 0.5 * minimum_side`; equality/near-collapse, rotated
box, two-cell input, and partial selection are refused before construction.

Promotion now copies and validates the entire original `polyMesh`, then uses a
strict UUID marker, same-filesystem file/directory `fsync`, and atomic directory
renames. Recovery tests cover staging, both rename windows, committed cleanup,
invalid token/symlink, and ambiguous topology without speculative deletion.

Evidence and literature scope are in
`hex_fixed_outer_inward_shell_l0_2026-07-31.md`. Decision:
**EXPERIMENTAL_KEEP, default OFF**. This one-AABB-box result does not promote
general all-quad/CAD boundary layers or Gate 7.

## 2026-07-31 — HEX-BL-ORIENTED-BOX-CONTRACT-1

The default-OFF fixed-outer path now replaces its AABB-only geometry test with
a C++23 oriented-orthogonal-box certificate. The source topology remains exact:
eight corner roles, twelve cube-edge roles, and six `(axis, side)` face roles
must each be bijective. The inward constructor, strict thickness limit,
signed-volume/corner-Jacobian gates, provenance, lock, and atomic transaction
are unchanged.

The project writer's `%.9g` round-trip produced normalized orthogonality residual
`1.1032821337527498e-9` on an arbitrary rotated `2x3x4` box. The frozen
serialization envelope is `8*sqrt(epsilon)=1.1920928955078125e-7`; direct tests
immediately below and above it prevent later threshold drift.

Rotated unit-box BL1 and rotated `2x3x4` BL3 requests changed from `0/2` fulfilled
to `2/2`, with source drift `0`, invalid/inverted cells `0`, exact point `8/8`
and face `6/6` provenance, and identical three-run hashes. A `1e-3` shear and a
`1e-9` side are deterministic byte-preserving refusals. Axis-aligned BL1/BL3
five-file hashes remain exactly
`468d49b2c27caeede8ef21248a43bb6ec253bc7720a0f8d234dcdf914a50d959` and
`9e8d079c973291cac6627c697e47bee1dd0128fe51a549ad0e5fe0517705fdcc`.

Decision: **L1_PASS / EXPERIMENTAL_KEEP, default OFF**. Full native-Hex files:
`241 passed`. General CAD, multi-cell cores, non-orthogonal cells, partial
patches, ridge/corner topology, narrow-gap collision, and Gate 7 remain open.
Full evidence: `hex_oriented_box_inward_shell_2026-07-31.md`.
