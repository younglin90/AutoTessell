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
| Yamakawa & Shimada 2002 (HEXHOOP) | hex/prism/pyramid/tet → all-hex core+cap hoop templates, Schneiders pyramid solution | 18/18 | `10.1007/s003660200019` | full text | reference-only: ~49-60x cell multiplication, systematic ~0.4 scaled-Jacobian mode from converted non-hex elements, patent-pending flag; wrong input class for our polyhedral octree transitions — Pitzalis 2021 is strictly better for grid-based transitions; cite as the honest price tag for rejecting hex-dominant → all-hex conversion (HEX-ALLHEX-1) |
| Chen 2026 | hex-dominant generation via sweep decomposition + QHED hex-distribution metric | 23/23 | `10.1007/s00366-025-02241-w` | full text | adopt the QHED/ScoreCHE census metric as a post-hoc distribution score (HEX-HD-5); generation pipeline not portable — B-rep input, commercial CAD kernel (HyperMesh booleans + sweeper), hour-scale PSO bottleneck |
| Gao, Shen, Panozzo 2019 | octree + dual all-hex conversion, scaffold, corner/curve/patch feature mapping, SLIM padding/untangling/fitting | 15/15 | `10.1111/cgf.13795` | full text + 5 rendered pages; code vendored in-repo (`Feature-Preserving-Octree-Hex-Meshing/`, full pipeline implemented) | adopt the feature-mapping recipe for the Phase-3 provenance card — corner→nearest vertex assigned once, curve→Dijkstra-with-cuts over `l/2` samples, patch→bidirectional correspondence, then tangent-slide only (implementable, code available); adopt the targeted refine-on-deviation loop idea for the wall_dev gate; vendored binary = test oracle only — do NOT port global SLIM/scaffold/padding (minutes-to-hours, up to 60 GB); honesty caveat: corner-positive SJ is necessary but NOT sufficient for trilinear bijectivity (5/202 outputs non-bijective) — gates must say "positive corner SJ", not "valid hex" |
| Pitzalis et al. 2021 | ILP-based generalized pairing (minimal grid refinement) for adaptive grids | 13/13 | `10.1145/3478513.3480508` | full text (Korean note); code open (Gurobi dependency) | **misnomer corrected: this is NOT the template paper** — transition templates/schemes are Livesu 2022; Pitzalis 2021 is the pairing ILP *preprocessing* that prepares the grid with minimal extra refinement. Quantified: GP+WB grid growth 2.1x vs octree-rule SB 3.3x (194/202 wins, 0 losses, 13.6K vs 24.4K added cells). ILP is a performance optimization, not a correctness requirement — octree-rule pairing (OP+WB, 2.9x) already suffices to install the Livesu schemes, so adoption can be staged |
| Livesu et al. 2022 | the actual scheme/template paper: 20-transition complete enumeration, 8+5 atomic dual schemes, dualization | 13/13 | `10.1145/3494456` | full text (arXiv v1); schemes in CinoLib (MIT) | adopt as the HEX-OCT-2 Option-A core: constructive proof of pure-hex conversion for balanced (strong or weak) + **paired** grids; singular edge valence bounded ≤6 (strong) / ≤7 (weak); weak balancing saves ~15% cells avg. Topological all-hex is proved, **positive Jacobian is NOT** — boundary projection is external, ECR untangling assumed as post-pass. Judgment rule: no dual-scheme all-hex claim unless the grid is balanced+paired — our engine has no pairing check/refinement stage, so no all-hex claim until one exists |
| Livesu et al. 2015 (ECR) | edge-cone rectification: connectivity-fixed hex untangling + quality via local-global QP/penalty | 11/11 | `10.1145/2766905` | full text; results archive on project page | port target for the post-snap quality lane, two stages: interior-only frozen-surface ECR first, then tangent-plane sliding. Frozen boundaries are supported and degrade gracefully, but cells with ≥3 boundary faces are provably unfixable frozen (Fig 11) — that class needs pillowing, not more smoothing; **tangent-plane sliding (Eq 21) is the wall_dev-compatible mode** (first-order zero normal motion, corners/features pinned). MSJ/cone-angle ↔ OpenFOAM-skew correlation is assumed, unverified — run HEX-ECR-1/HEX-ECR-4 diagnostics before any solver code. No inversion-free guarantee (empirical) |
| Tong & Zhang 2024 (HexOpt) | post-optimization: ReHQJ energy + augmented-Lagrangian surface constraint + L-BFGS/Armijo | 10/10 | arXiv `2410.11656` (journal DOI unverified) | full text; code open (CMU-CBML/HexOpt) | primary design for the Phase-1 sliding lane. **The surface constraint is SLIDING closest-point, recomputed every iteration** — vertices preserve membership on the surface (PostMaxDist = 0), not snapped positions; admissible for the wall_dev gate provided (a) the gate is checked at Θ-stage convergence (soft ρ start leaves mid-iterates transiently off-surface) and (b) feature corners/edges come from **our own feature classification** (their automatic feature path-finding is their reported weak spot). ECR-vs-HexOpt bake-off required — their superiority claim over ECR is prose, no side-by-side table; η=0.5 vs 0.9 backtracking discrepancy must be resolved from source before port |

No inaccessible paper in this batch. The 2026-07-23 batch (Knupp, Ledoux, HEXHOOP, Chen) cleared four of the five paywalled entries from the forward sweep's download queue.

## Forward sweep outcome (2026-07-23)

`forward_citation_sweep_2026-07-23.md` screened 22 candidates across four axes (octree templates, untangling, sheet operations, hex-dominant honesty) and declared saturation. P0 adoption directions with access status:

- **Pitzalis et al. 2021** (`10.1145/3478513.3480508`, open PDF + open code) — octree-template replacement candidate over Zhang 2013: conforming all-hex templates on *weakly balanced* adaptive grids, fewer refinement propagations. Companion theory: Livesu et al. 2022 Optimal Dual Schemes (`10.1145/3494456`, open via arXiv) decides when the dual path may claim all-hex (HEX-OCT-2 decision input).
- **Edge-Cone Rectification 2015** (`10.1145/2766905`, open project page) + **HexOpt** (arXiv `2410.11656`, open; journal DOI unverified) — the post-snap boundary-skew lane: positive-Jacobian enforcement and surface-constrained scaled-Jacobian optimization. Confirmed by the Knupp full read to strictly dominate the classic untangling objective.
- **Gao, Shen, Panozzo 2019** (`10.1111/cgf.13795`, open author PDF; code vendored in-repo at `Feature-Preserving-Octree-Hex-Meshing/`) — feature preservation + positive-SJ-by-construction; unblocks the ridge/corner provenance card.
- Remaining unread paywalled queue: **Qian & Zhang 2010 only** (`10.1007/978-3-642-15414-0_15`, P2 — pillowing-at-features, superseded for our purposes by Gao 2019).

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
| BL linkage | `post_layers_engine=auto` selects generic `native_bl`; `native_hex_bl.extrude_hex_bl` is test-only | all-hex buffer topology for Maréchal; mixed layers acceptable only if reported; Ledoux 2010: pillowing is the provably all-hex-preserving per-patch layer-insertion primitive | current hex route may add prism cells; all-hex claim invalid after BL; pillowing (HEX-SHEET-2) is the literature-backed route to an all-hex BL |
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
- Qian, Zhang 2010, sharp-feature pillowing. DOI: `10.1007/978-3-642-15414-0_15` (paywalled — sole remaining download-queue entry, P2).

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
