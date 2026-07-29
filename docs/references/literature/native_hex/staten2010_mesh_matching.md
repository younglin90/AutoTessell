# Staten, Shepherd, Ledoux, Shimada 2010 - Hexahedral Mesh Matching

## Bibliographic record

- Matthew L. Staten (Sandia/CMU), Jason F. Shepherd (Sandia), Franck Ledoux (CEA, DAM,
  DIF), Kenji Shimada (CMU), *Hexahedral Mesh Matching: Converting non-conforming
  hexahedral-to-hexahedral interfaces into conforming interfaces*, International Journal
  for Numerical Methods in Engineering 82(12):1475-1509.
- DOI: `10.1002/nme.2800`.
- **Verified year: 2010** (the journal's own header/citation line: "Int. J. Numer. Meth.
  Engng **2010**; 82:1475-1509"). **Discrepancy from the task brief:** the repo filename
  and the gap-search doc both label this "staten2009" / "2010" ambiguously. The actual
  publication timeline is: received 9 Mar 2009, revised 24 Sep 2009, accepted 21 Oct
  2009, published online 3 Dec 2009, copyright line "(c) 2009 John Wiley & Sons, Ltd."
  — but the citable journal issue (volume 82) is dated **2010**. Both years appear on the
  first page simultaneously; 2010 is the correct citation year, 2009 is the online-first/
  copyright year. Treat "staten2009" in the filename as referring to the online-first
  date, not the volume year.
- **Page-count discrepancy from the task brief:** the brief states the PDF is 17 pages.
  The actual PDF spans journal pages 1475-1509 inclusive = **35 pages**, and all 35 were
  read.
- Status: `FULL_READ` (35/35 pages, 2026-07-25).
- Companion/predecessor already in this repo: `ledoux2010_sheet_operations.md` (Ledoux &
  Shepherd, same sheet/chord/column vocabulary, no quality data, "supplies zero
  geometric guidance" — this paper is the first attempt to supply that guidance for one
  specific trigger condition, non-conforming interfaces).
- Predecessor conference paper (not yet read, same algorithm, shorter): Staten, Shepherd,
  Shimada 2008, IMR17, `10.1007/978-3-540-87921-3_28` (open PDF at
  `osti.gov/servlets/purl/1145637`).
- Sandia patent already screened at abstract level in the round-2 gap search: US 8,390,620 B1
  (filed 2009-03-04, granted 2013-03-05), same author group. This paper is confirmed to be
  its peer-reviewed theoretical basis — the patent's stated depth-parameter/column-collapse
  locality mechanism and its "quality may be reduced" caveat both trace directly to
  Sections 4.3 and 6 of this paper (see Limitations below).

## Problem and claimed scope

Two independently-generated (or independently-swept) all-hexahedral meshes MA, MB on
adjacent geometric surfaces SA, SB frequently end up with **different quadrilateral
topology** on the shared interface (non-conforming interface). Instead of an artificial
constraint (tied contact, multi-point constraint, mortar formulation — all of which break
inter-element continuity), Mesh Matching **locally edits the hexahedral topology on one or
both sides** until the two interface quad meshes are topologically identical, so the
interface nodes can be merged into one conforming mesh. The paper restricts its worked
examples to manual, two-volume, single-surface interfaces "for proof of concept," and
explicitly lists automation, larger assemblies, and parallel processing as future work.

## Background restated from the paper (shared with Ledoux 2010)

- Primal mesh M=(H,F,E,N); dual D=(S,C,V): sheets (dual surfaces, primal = one logical
  hex layer along one of the 3 logical edge directions), chords (dual curves, primal =
  one logical hex column, formed at the intersection of two sheets or a sheet
  self-intersection), dual vertices (single hex elements, intersection of 3 sheets or a
  sheet+chord).
- Sheets/chords can be **regular**, **self-intersecting**, **self-touching**, or both
  (Definitions 2-5); self-intersecting/self-touching structures correlate with poor
  element quality and should generally be avoided during matching.
- Three modification operators used by Mesh Matching: **sheet extraction** (collapse a
  sheet's edges, removing a whole hex layer — always possible but risks doublets /
  geometric-associativity violations if node valence is low or edges span two different
  geometric curves), **sheet insertion** via **pillowing** (shrink-set based; always
  valid and produces a regular sheet if the shrink set is only face-connected hexes) or
  **dicing** (splits an existing sheet's edges to duplicate it — can only copy topology
  that already exists, cannot create new topology, cannot make self-touching sheets), and
  **column/chord collapse** (merge one pair of opposite nodes per quad along a hex
  column — the most surgical op, removes one column rather than a full layer; collapsing
  a self-intersecting column creates doublets and "should be avoided").
- Section 3 is new relative to Ledoux 2010: **generalized sheet insertion** ("sheet
  inflation"), a superset of pillowing+dicing that can insert arbitrary self-touching and
  self-intersecting sheets via inflatable quad sets and n-NMEsets (non-manifold edge
  sets, n=3 or 4 in practice), plus a post-processing "column open" to convert a
  self-touching result into self-intersecting. This closes the "no known implementation
  of a fully general sheet insertion" gap Ledoux 2010 flagged, but the main Mesh Matching
  algorithm (Section 4) is described using ordinary pillowing/dicing/extraction/column
  collapse — sheet inflation is presented as a completeness result, not something the
  worked examples actually exercise.

## The Mesh Matching algorithm (answers Q1)

**Input requirements (Section 4.1):**

1. Two geometric surfaces SA, SB that are topologically identical (same number of
   boundary curves/loops/vertices) and geometrically similar (max separation between
   paired curves/vertices < tolerance beta) — imprint via "Grafting" first if not.
2. Freedom to modify hex elements on one or both sides; all changes can be forced onto
   one side if the other side's mesh must not change (e.g. it already has a boundary
   layer, or a specific mesh is required by physics).
3. **An integer "depth" parameter** indicating how many hex layers into the adjacent
   volumes a modification is allowed to propagate. This is the exact mechanism the patent
   screening flagged: depth bounds the **pillow shrink set** and the **sheet-inflation
   quad set** (propagation stops after `depth` layers), and separately selects which
   **column to collapse** when an extraction sheet's natural path wanders far from the
   interface and needs to be redirected back to a local path (Section 4.3, citing
   Woodbury 2008's localized-coarsening column-collapse technique).

**Region selection / bounding.** The "region" being matched is not an arbitrary blob —
it is defined algebraically on the **quadrilateral dual of the interface surface**:
DA=(CA,VA), DB=(CB,VB). Two chords ci in CA and cj in CB are **equivalent** (Definition
11) if their maximum separation distance is less than a tolerance delta *and* they
consistently intersect the same already-matched chord pairs — chord count need not match,
only spatial proximity and consistent crossing pattern. The whole procedure (Algorithm 1)
is: (a) greedily pre-pair every chord that already has a geometrically equivalent
counterpart; (b) push every leftover unpaired chord from each side into a work-set
(Omega_A, Omega_B); (c) loop while either work-set is non-empty: pick an unpaired chord
for **extraction** (candidates: low-quality/self-intersecting/self-touching/
high-curvature sheets, sheets that stay local to the interface, sheets that disrupt an
otherwise regular grid — never a sheet whose extraction would violate geometric
associativity or create a doublet), then try to **insert** a new sheet (pillow or dice)
matching one of the other side's leftover chords; repeat symmetrically for the other
side; (d) once every chord is paired, fuse each paired-sheet pair by merging interface
nodes, then **smooth all nodes local to the interface** (curve, surface, and volume
nodes) as the final step. Extraction and insertion alternate, which keeps the total
element-count change moderate (final density approximates the average of the two
original densities when both sides are modifiable).

**Composition of operations used:** pillowing (new sheet, always regular/valid),
dicing (new sheet, but only a duplicate of an existing one), sheet extraction (remove a
sheet), column collapse (redirect an extraction sheet's path to stay local, using the
depth parameter to pick which column). "What decides the target correction" is therefore
almost entirely **topological/spatial**: match if geometrically close and consistently
intersecting, extract low-quality/self-intersecting/far-reaching sheets first, keep
changes local by depth-bounding pillow sets and by column-collapsing wandering
extraction paths. There is **no analog of an OpenFOAM-style skew/non-orthogonality
metric** anywhere in the paper — the one quantitative quality measure used throughout
(for reporting only, not for making decisions inside Algorithm 1) is Knupp's **scaled
Jacobian** [ref 36]. Quality only enters the decision process as an informal heuristic
("prefer to extract sheets with less-than-ideal element quality") — Algorithm 1 itself
has no formal quality objective or optimization step, and the paper states outcomes are
non-unique and order-dependent.

## Validity theory (answers Q2)

Theorem 1 (restated, originally proved by Ledoux & Shepherd) proves only **topological
transformation existence**: any hex mesh M of geometry G can be converted into any other
hex mesh M' of the same G via a finite sequence of sheet insertions/extractions — proved
constructively here as "union M with M', then subtract M," which in practice means
"insert every sheet of M' into M, then extract every sheet of M." Corollary 1 specializes
this to Mesh Matching: a conforming interface can *always* be reached given the Section
4.1 input requirements. This is an **existence proof only** — it establishes that all-hex
topology (H,F,E,N staying a valid primal/dual pair) is preserved by construction for every
individual operator (pillowing, extraction, dicing, column collapse each map dual sheet
arrangement -> dual sheet arrangement by definition), but:

- **No positive-Jacobian guarantee is proven.** The paper is explicit that quality is
  empirical, not guaranteed: "As with any mesh modification procedure, the quality of the
  modified elements may be reduced from the initial mesh quality" (Introduction), and
  results are reported as measured minimum/average scaled Jacobian per example, never as
  a theorem.
- Two specific, named failure modes are called out as **not** covered by the topology
  proof: (1) sheet extraction merging nodes with conflicting geometric associativity
  (different curves/surfaces) is invalid and must be guarded against; (2) low node
  valence during extraction, or collapsing a **self-intersecting** column, "can lead to
  doublets, resulting in ill-shaped elements with zero or negative scaled Jacobians."
  These are explicit, named exceptions to "always works," and the paper's mitigation is
  procedural avoidance (don't pick those sheets/columns), not a proof that avoidance is
  always achievable.

So: all-hex topology is preserved by construction (strong, proven); positive Jacobian /
element validity is not proven and is explicitly flagged as at-risk under two named
conditions (empirical, example-based only).

## Does the paper confirm the patent's quality-drop caveat, and what's the mitigation? (answers Q3)

Yes — confirmed and quantified, not just asserted. Section 6 states plainly: "Element
quality degrades as the differences in the initial meshes increases. Initially large
transitions in element size result in more element skew and twist." The five worked
examples report minimum scaled Jacobian before/after:

| Example | Before (min SJ) | After (min SJ) | Note |
|---|---|---|---|
| #1, two volumes, both modifiable | 0.6496-0.7754 | 0.5737-0.5906 | element count within 2% |
| #2, one side, non-local (global) | 0.9914 | 0.9852 | quality nearly preserved, but far-reaching changes |
| #2, one side, local | 0.9914 | 0.4691 | quality sacrificed to keep changes local |
| #2, both sides | 0.9914 | 0.5199 | moderate element-count increase, moderate quality drop |
| #3, stiffener/corner-plate, one side fixed | 0.6619 | 0.7146 | quality *improved* here (mesh had been coarse) |
| #4, same model, 2.3:1 density mismatch | 0.6619 | 0.4924 | larger mismatch -> larger drop |
| #5, lung-airway end-cap template | 0.4088 | 0.4113 | near neutral (already low-quality base mesh) |

Mitigations the paper actually specifies (not hand-waved): (a) a mandatory final
**smoothing pass** over every node local to the interface (curve, surface, and volume
nodes — Algorithm 1 line 35, citing 6 separate smoothing references); (b) the heuristic
sheet-selection rule (prefer extracting self-intersecting/self-touching/high-curvature
sheets, avoid doublet-creating extractions); (c) the **depth parameter** itself, since
keeping changes local trades quality for locality (Example #2's "one side-local" case is
the worst-quality result of the whole paper, 0.4691, specifically because locality was
prioritized over quality); (d) modifying **both** sides instead of one side moderates
element-count growth and gives "a smoother transition in element size." None of these is
a quality-floor guarantee or a retry/rollback mechanism — there is no threshold check or
undo step in Algorithm 1. This is exactly the gap the round-2 search flagged: the
mitigation is "smooth afterward and hope," not "verify a floor and back off," which is
consistent with (and refines) the patent's abstract-level caveat.

## Applicability to AutoTessell's two damage patterns (answers Q5)

Context: `native_hex` octree engine's post-repair damage census shows two distinct
topologies — isolated **singleton bad faces** (cylinder/sphere/gear) vs. **7 connected
components across 6 patches** (bracket).

- **Singleton bad faces — plausible fit.** A single bad hex sits at the intersection of
  (generically) three dual sheets (Definition, Case 1) or fewer if it touches self-
  intersections. The paper's primitives are exactly column/sheet-scale: a depth-1 or
  depth-2 pillow shrink set, or a single column collapse, is a bounded local edit whose
  natural extent matches a singleton bad cell. This is squarely inside what the paper
  demonstrates (Example #1's pillow/dice/extract insertions each modify a handful of
  hexes near one chord).
- **7-connected-component/6-patch damage — outside the paper's demonstrated and even
  claimed scope.** The paper's own input requirements (4.1) assume **one** interface
  surface pair per invocation ("we restrict our focus to... single surface interfaces");
  Section 6's future-work list explicitly flags multi-surface interfaces as unsolved
  ("Multiple surface interfaces will require special handling to preserve geometric
  curves adjacent to more than one of the interface surfaces. In addition, assembly
  models may introduce cyclic dependencies... requiring special processing"). A
  6-patch/7-component damage pattern is structurally closer to that flagged
  multi-surface case than to any worked example here. Running the Section-4.3 loop
  independently per component is a plausible extension, but the paper gives no
  guarantee that independently-repaired components don't conflict (e.g. two components
  sharing a sheet) — that would need the union/subtraction algebra of Sections 2.2.4-2.2.5
  applied deliberately, which the paper never demonstrates for more than a two-volume
  case.
- Net: Mesh Matching's *mechanism* (bounded local sheet/column edits, depth-controlled)
  is the right shape for singleton repairs; it is a research extension, not an
  off-the-shelf fit, for the bracket's multi-patch damage.

## Experiments summary

Five worked examples (all manual, done in Cubit): (1) two-volume model, sweep-topology
mismatch, 4500+1664 -> 4749+1523 elements, min SJ 0.78/0.65 -> 0.57/0.59; (2) synthetic
quarter-cylinder wedge comparing global vs. local vs. both-sides matching strategies
(table above); (3) I-beam stiffener/corner-plate, stiffener frozen, corner plate density
increased via pillowing only, min SJ actually improved 0.66->0.71; (4) same model with a
2.3:1 density mismatch, corner plate min SJ drops to 0.49; (5) lung-airway bifurcation
template with 3 mismatched end-cap topologies, matched to one target topology, then
copied/rotated 254 times to build an 8-generation airway (30740->31276 elements,
0.4088->0.4113) — demonstrating the method is also useful for making a *single* template
self-consistent for reuse-by-copying, not only for gluing two different meshes.

## Limitations (paper's own, plus round-2-relevant ones)

- All examples are **manual** (interactive Cubit tool use); automation is stated future
  work, not delivered here.
- No formal Jacobian/validity guarantee (see Validity theory above); quality degrades
  measurably and unpredictably with initial mesh-density mismatch.
- Multi-surface / assembly-scale interfaces (more than one shared surface pair, possible
  cyclic dependencies) are explicitly unsolved.
- Chord-pairing and operation order are non-unique; results are order-dependent, so the
  method is not reproducible/deterministic without additional tie-breaking rules (which
  the paper does not supply).
- No metric-driven sheet-selection rule; purely heuristic (self-intersection/curvature/
  locality), which the 2016 Chen/Gao/Zhu follow-up (already flagged in the round-2 gap
  search, `10.1007/s00366-015-0414-1`) is reported to fix by adding an explicit
  quality-evaluation-guided extraction choice — the natural next paper to pair with this
  one before implementation.

## AutoTessell candidate cards

### HEX-MATCH-1 - depth-bounded local repair for a single bad hex

- For one flagged bad hex (negative/near-zero scaled Jacobian or OpenFOAM skew above
  gate) in native_hex output, identify its dual column/sheet membership (reuse the
  Ledoux 2010 sheet-traversal machinery already scoped in `HEX-SHEET-1`), then attempt a
  depth-1 pillow insertion or a single column collapse to re-route the local topology,
  followed by smoothing restricted to nodes within `depth` of the bad cell.
- Pass: bad cell's quality metric moves above the gate; no cell outside the depth-bounded
  neighborhood changes; total cell-count delta stays within a small percentage (mirror
  the paper's "within 2%" result for a comparable single-defect case).
- Stop rule: if the bad cell's dual column is self-intersecting (doublet risk per the
  paper's own caveat), do not collapse it — fall back to extraction-with-guard or leave
  the cell flagged for a different repair lane.

### HEX-MATCH-2 - quality-gated repair transaction (mitigates the paper's own caveat)

- Operationalize the paper's "depth parameter" as a literal bounded transaction: perform
  the trial pillow/extract/collapse within depth N, measure **our own OpenFOAM
  skew/non-orthogonality metric** (not the paper's scaled Jacobian, per the project's
  measurement-first policy) on the affected neighborhood only, commit only if it does not
  regress below the existing gate; otherwise increase depth by 1 (up to a cap) or abandon
  and report.
- Pass: on a mesh with a mix of self-intersecting and regular candidate sheets, the
  transaction never commits a regression; abandoned repairs are reported with a
  diagnostic distinguishing "no valid local operation found" from "found but rejected on
  quality."
- This directly replaces the paper's un-verified "smooth and hope" ending (Algorithm 1
  line 35) with an explicit floor check, closing exactly the gap the patent's caveat and
  this paper's own Example #2 ("one side-local", worst result in the paper) expose.

### HEX-MATCH-3 - multi-component extension spike (bracket-style damage)

- Research-only card (no engine code) to test whether independently applying
  HEX-MATCH-1/2 to each of the bracket's 7 connected bad components in turn is
  sufficient, or whether cross-component sheet sharing (a single dual sheet threading
  through two nominally separate bad components) causes conflicting edits — the paper
  itself never demonstrates more than a two-volume, single-interface case and explicitly
  flags multi-surface interfaces as unsolved.
- Pass/stop rule: run all 7 single-component repairs independently on a snapshot; if any
  two components' selected sheets/columns overlap, document the conflict and do not
  proceed to implementation without either (a) a serialization order that avoids
  reprocessing a shared sheet twice, or (b) reading Zhao et al. 2023/2024's
  base-complex reformulation (`10.1007/s00366-023-01908-6`, already in the round-2 gap
  search queue) for a principled multi-region approach first.

## Snowball references (max 5)

1. Ledoux, Shepherd (2009/2010), *Topological modifications of hexahedral meshes via
   sheet operations: a theoretical study*, Engineering with Computers 26:433-447,
   `10.1007/s00366-009-0145-2` — already `FULL_READ` in this repo
   (`ledoux2010_sheet_operations.md`); this paper's Theorem 1 restates that paper's
   existence proof and its whole operator catalog is shared.
2. Staten, Shepherd, Shimada (2008), *Mesh Matching-creating conforming interfaces
   between hexahedral meshes*, IMR17, `10.1007/978-3-540-87921-3_28` — the original
   conference version of this same algorithm; open PDF via OSTI
   (`osti.gov/servlets/purl/1145637`), already flagged P0 INCLUDE in the round-2 gap
   search.
3. Merkley, Ernst, Shepherd, Borden (2007), *Methods and applications of generalized
   sheet insertion for hexahedral meshing*, IMR16 — the quality-driven geometric half
   that both this paper and Ledoux 2010 lean on but do not themselves supply.
4. Woodbury, Shepherd, Staten, Benzley (2008), *Localized coarsening of conforming
   all-hexahedral meshes*, IMR17, cited directly in Section 4.3 as the source of the
   column-collapse technique used to redirect a far-reaching extraction sheet back to a
   local path — the exact mechanism behind the patent's "column collapse operations"
   locality claim.
5. Knupp (2003), *Algebraic mesh quality metrics for unstructured initial meshes*,
   Finite Elements in Analysis and Design 39:217-241 — defines the scaled-Jacobian
   quality metric used in every quantitative result table in this paper (Tables I-V).

## Decision

Confirmed as the peer-reviewed theoretical basis for US Patent 8,390,620's depth-bounded
locality mechanism. Use it for the region-bounding contract (depth parameter + column
collapse to keep sheet paths local) and for the operation vocabulary (pillow/dice/extract/
collapse), but do not cite it as evidence that local repair preserves or improves quality
— it explicitly reports the opposite in its worst-case example (0.9914 -> 0.4691, "one
side-local" in Example #2) and never proves a positive-Jacobian floor. Pair with Chen,
Gao, Zhu (2016) before implementing any sheet-selection heuristic, since this paper's own
selection rule is unweighted/heuristic, not metric-driven. HEX-MATCH-1/2 fit the
singleton-bad-face damage pattern; HEX-MATCH-3 is a required research spike, not an
implementation card, before touching the bracket's multi-component damage.
