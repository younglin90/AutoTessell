# Ledoux & Shepherd 2010 - Topological Modifications of Hexahedral Meshes via Sheet Operations

## Bibliographic record

- Franck Ledoux (CEA-DAM), Jason Shepherd (Sandia), *Topological modifications of hexahedral meshes via sheet operations: a theoretical study*, Engineering with Computers 26:433-447, 2010.
- DOI: `10.1007/s00366-009-0145-2`
- Status: `FULL_READ` (15/15 PDF pages, journal pp. 433-447, 2026-07-23).
- Visual verification: pages 4 and 5 rendered and inspected. Fig. 4 (pillowing: ring sheet inserted into a circular quad mesh), Fig. 5/6 (face/chord collapse: two intersecting sheets cut and reconnected into non-intersecting sheets) are legible and agree with extracted text.
- Nature of paper: **survey + formalization + existence proofs**. There are no experiments, no meshes generated, no quality metrics, and no timings anywhere in the paper. Section 5 states explicitly: "we show what is the result and not how to obtain this result."

## Dual framework (Sect. 2)

The dual of a hex mesh is the Spatial Twist Continuum (STC): each hex -> dual vertex, quad face -> dual edge, edge -> dual face, node -> dual region. A column of hexes (traversal via one pair of opposite faces) dualizes to a **chord**; a layer (two pairs) dualizes to a **sheet** (surface). Definition 1 formalizes a *simple sheet arrangement* (S, C, V): every dual vertex is the intersection of three sheets, every chord the intersection of two sheets, every sheet crossed by at least one other, and around every chord the ordered cycle of half-sheets alternates {s1a, s2a, s1b, s2b} (self-intersecting case: same sheet twice). Definition 2: a hex-mesh dual is a nonempty simple sheet arrangement. Sheet diagrams (per-sheet intersection pictures) are the working notation.

## Operation catalog with preconditions (Sect. 3)

### Sheet extraction (from Borden et al. 2002)

Remove one whole layer of hexes.

1. *Define the sheet*: one mesh edge corresponds to exactly one dual sheet, so a single seed edge plus iterative primal traversal (opposite edges through quads/hexes) enumerates all edges of the sheet.
2. *Collapse the edges*: merge the two nodes of every sheet edge. When multiple edges reduce to a single node, all merges must be performed **simultaneously** to keep topology correct.

Precondition / validity guard: the merged node pair must not lie on **opposing geometric features** — e.g. nodes classified on two different geometric curves must not merge, or the mesh degenerates or stops conforming to the geometric topology. This is the only stated guard; with it, the result is again an all-hex conforming mesh (dual: Definition 5, S' = S - {s} plus removal of its chords/vertices).

### Sheet insertion — pillowing (from Mitchell & Tautges 1995) and dicing

Add one whole layer of hexes. Pillowing procedure (Fig. 4):

1. Identify a **manifold set of quadrilaterals** inside the existing mesh; it defines a half-space splitting the hexes into two sets (the "shrink set" boundary).
2. Separate the two sets, creating a gap.
3. Reconnect with a new hex layer: insert an edge between each separated node pair — equivalently, **inflate each quad of the manifold set into one hex**.

Validity guarantee: because the quad set is manifold, inflation creates **no degenerate hexes**. Limits of generality: pillowing cannot insert a *self-intersecting* sheet; dicing can only copy a sheet that already exists (parallel copy); the paper states there is **no known implementation of a fully general sheet insertion**. Dual: Definition 4 (S' = S + {s} plus new chords/vertices).

### Chord collapse (face collapse propagated along a chord)

Merge the two opposite node pairs of a quad (face collapse, Fig. 5) consistently for **every hex along a chord**. Effect in the dual (Fig. 6): the two sheets s1, s2 intersecting along the chord are cut along it and reconnected as s1', s2' that no longer intersect — or fuse into a single sheet. Properties from Definition 6:

- s1 may equal s2 (collapsing a self-intersection chord) and s1' may equal s2' (fusion).
- Chords that crossed the collapsed chord are split or fused; there are **two ways** to reconnect, so chord collapse is **non-deterministic** — two different valid arrangements can result.
- Removes exactly the hexes of the chord (a column, not a full layer) — the most surgical of the three ops.

### Atomic operations (Tautges et al.) — context

Three irreducible dual ops: **atomic pillow** (AP: inflate one quad into a 2-hex sheet), **face shrink** (FS: cross two sheets along a dual edge; primal = 4-hex torus), **face open-collapse** (FOC: open two dual edges bounding a face and reconnect, fusing two sheets). Known incompleteness: the set cannot change hex-count **parity**; a Boy-surface insertion [Jurkova 2008] was attempted but its primal realization is incomplete. Carbonera's algorithm on one hex always changes parity without touching the boundary. Atomic ops are not allowed to modify a mesh boundary — boundary-crossing sheet insertion requires a temporary **ghost layer** of hexes around the mesh.

### Flipping operations (Bern & Eppstein) — context

Hypercube-induced local exchanges of hex "pockets". Very local; drawback stated: they ignore global sheet structure and "quickly degenerate the dual mesh structure."

## Theory (Sects. 4-7)

- **Sect. 4**: every sheet operation decomposes into a sequence of atomic ops. Chord collapse = FOC to turn end hexes into "knives" + repeated FOC + inverse-AP to delete each knife. Pillowing = AP to seed a 2-hex sheet + FS sequence to inflate it around the target region (+ FOC to traverse dual edges). Sheet extraction = inverse of pillowing/dicing sequence.
- **Sect. 6**: set operations — union (non-unique; realized as a series of sheet insertions) and difference (series of extractions, requires arrangement inclusion) of sheet arrangements; connects to mesh matching (Staten et al.).
- **Theorem 1**: any hex mesh M of a geometric object converts to any other hex mesh M' of the same object by a series of sheet insertions and extractions. **Existence only — no algorithm.** The shared boundary is *not* preserved during the transformation, only restored at the end.
- **Corollary 2**: any hex mesh can be transformed so its boundary sheets form a *fundamental mesh* (one sheet per geometric surface, one chord per curve; Definition 10 in primal terms).

## Experiments

None. Purely theoretical. No quality data, no element counts, no implementation reported in this paper. For quality-driven use of these ops the paper defers to Merkley et al. 2007 [12] and Shepherd & Johnson 2008 [18].

## Limitations

- No geometric quality analysis at all: node placement after pillowing/extraction/collapse is out of scope, so the paper cannot say whether an op improves or worsens skew — that depends entirely on the smoothing/placement step that follows.
- No algorithms for the general case: general sheet insertion is unimplemented; Theorem 1 is non-constructive; chord collapse is non-deterministic.
- Sheet extraction's feature guard is stated but not turned into a complete decidable precondition (self-intersecting sheets and boundary sheets need care).
- Atomic-op set is known incomplete (parity), and atomic ops cannot touch the boundary without ghost layers.

## AutoTessell applicability

Context: native_hex octree engine, per-vertex wall-fit snap + partial backtracking (fine `wall_dev_max` 0.008, gate < 0.02), interior relaxation for post-snap boundary skew (2.84 vs gate 3.0). Sweep flagged sheet ops as a surgical fix for skew concentrated near walls.

- **Wall-skew verdict**: pillowing does not intrinsically create or relieve thin-cell skew — it is topology-only. What it *does* provide is degrees of freedom: inflating a wall-adjacent quad layer converts the boundary hexes' constraint pattern (each boundary hex gets exactly one boundary face — the same buffer-layer property Maréchal enforces), which is what lets subsequent smoothing remove skew. Conversely, our current skew concentration is a **node-placement** problem (snap-induced), and the two ops that directly delete bad topology are **sheet extraction** (remove a whole degenerate wall layer) and **chord collapse** (remove one column of bad hexes — the most surgical option, at the cost of non-determinism and neighbor chord rewiring).
- **All-hex honesty**: all three sheet ops map all-hex mesh -> all-hex mesh by construction (dual stays a simple sheet arrangement, Definitions 4-6). None introduce polyhedra. Safe for the all-hex lane, *provided* the extraction feature guard is enforced — merging nodes across two geometric curves is exactly the failure mode our wall-fit snap lane would hit on ridged geometry.
- **Implementability**: sheet extraction is the most implementation-ready (seed edge -> traversal -> simultaneous merge + feature guard). Pillowing is next (manifold quad set -> inflate); our octree already produces the structured layers that make sheet identification trivial. Chord collapse needs the non-determinism resolved by a quality tiebreak. Section 5-7 formalisms are useful as invariant checks, not as algorithms.
- **Future per-patch BL**: pillowing *is* the canonical per-patch boundary-layer insertion primitive — pillow the hexes adjacent to one wall patch, then place the new layer nodes at the desired first-cell height. The manifold-quad-set precondition is exactly the per-patch selection contract. Repeated pillowing = multi-layer BL. This aligns with Merkley 2007 ("generalized sheet insertion"), the natural next read for the quality/geometry half this paper omits.

## Falsifiable implementation cards

### HEX-SHEET-1 - sheet extraction for post-snap wall skew

- Implement seed-edge sheet traversal + simultaneous edge collapse with the geometric-feature guard (never merge nodes classified on different curves/patches).
- Target: on a mesh where post-snap skew > gate concentrates in one wall-adjacent layer, extract that sheet and re-relax.
- Pass: output remains conforming all-hex (checkMesh clean, hex census 100%), max skew drops below 3.0 gate, wall_dev stays < 0.02, and no source geometric curve loses its node classification.
- Stop rule: if the offending cells do not form a single coherent sheet (skew scattered across layers), extraction is the wrong tool — fall back to chord collapse or relaxation.

### HEX-SHEET-2 - pillowing as per-patch BL primitive

- Implement pillowing: select the manifold quad set separating wall-patch-adjacent hexes from the interior, inflate each quad into a hex, place new nodes at prescribed first-layer height along averaged normals.
- Pass: (a) manifoldness of the quad set is verified before inflation and non-manifold selections are rejected with a diagnostic; (b) result is all-hex with every wall-adjacent hex having exactly one boundary face; (c) inserted layer respects wall_dev_max and does not push interior skew above gate after one relaxation pass.
- Expected risk: the *paper* guarantees only topology; the geometric placement step is ours, and a thin first layer will re-create high skew unless relaxation treats the pillow layer anisotropically.

## Snowball references (max 5)

1. Borden, Benzley, Shepherd 2002, *Coarsening and sheet extraction for all-hexahedral meshes*, IMR 11 — the sheet extraction algorithm itself (edge traversal + collapse details).
2. Mitchell, Tautges 1995, *Pillowing doublets: refining a mesh to ensure that faces share at most one edge*, IMR 4 — original pillowing algorithm.
3. Merkley, Ernst, Shepherd, Borden 2007, *Methods and applications of generalized sheet insertion for hexahedral meshing*, IMR 16 — the quality-driven, geometric half that this paper omits; highest-priority next read for the skew lane.
4. Tautges, Knoop 2003, *Topology modification of hexahedral meshes using atomic dual-based operations*, IMR 12 — atomic op definitions (AP/FS/FOC).
5. Shepherd, Johnson 2008, *Hexahedral mesh generation constraints*, Eng Comput 24(3):195-213 — constraint framework linking sheet structure to mesh quality.

## Decision

Use this paper as the **topological contract** for a sheet-ops repair lane: it proves extraction/pillowing/chord-collapse preserve all-hex conformity and gives their exact preconditions, but it supplies zero geometric guidance. Pair it with Merkley 2007 before implementing quality-driven insertion. Do not cite it as evidence that pillowing improves (or harms) wall skew — that claim must come from our own HEX-SHEET-1/2 experiments.

## HEX-PATCH-LAYER-DIAG1 follow-up measurement (2026-07-26)

The first patch-aware follow-up to the rejected all-wall-owner shrink set was
run in report-only mode on the actual fine pre-BL native_hex cylinder, sphere,
and gear caches. Candidate S cells were required to be clean hexes with
exactly one physical-boundary face and exactly one Q face against the original
wall-owner complement. Candidates were then partitioned by the writer's
deterministic feature-patch label plus the current single-source `defaultWall`
provenance. Q vertices on the physical boundary were rejected, and each
same-label connected component was required to have quad faces with edge
incidence exactly two.

The strict census retained 544/544 S/Q on cylinder, 24/24 on sphere, and
888/888 on gear. It found 6, 6, and 22 same-patch components respectively.
Their strict Q edge histograms were `{1:272,2:952}`, `{1:48,2:24}`, and
`{1:656,2:1448}`: open-edge counts were 272, 48, and 656; non-manifold counts
were zero on all three. Q vertices on the physical boundary were zero after
the cell filter. Therefore the Ledoux manifold-quad precondition still fails
for every individually labelled subset, even though a raw cross-patch union
can hide some openings by pairing edges from different labels.

**Decision:** `HEX-PATCH-LAYER-DIAG1` is KILLED. The predicted pillow operation
was recorded only (hypothetical point/cell growth `+686/+544`, `+54/+24`, and
`+1228/+888`); zero operations were approved or executed. This measurement
does not weaken Ledoux's theorem: it falsifies the availability of a valid
per-patch Q set in these cached meshes under the theorem's manifold
precondition. No production pillowing or sheet extraction is justified, no
next operation card is proposed, and the existing wall_dev/skew gates remain
unchanged.
