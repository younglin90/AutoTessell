# Ledoux, Le Goff, Owen, Staten & Weill 2013 - A Constraint-Based System to Ensure the Preservation of Sharp Geometric Features in Hexahedral Meshes

## Bibliographic record

- Franck Ledoux (CEA-DAM), Nicolas Le Goff (CEA-DAM), Steve J. Owen (Sandia), Matthew L. Staten
  (Sandia), Jean-Christophe Weill (CEA-DAM), *A Constraint-Based System to Ensure the Preservation
  of Sharp Geometric Features in Hexahedral Meshes*, Proceedings of the 21st International Meshing
  Roundtable (IMR 21), pp. 315-332, 2013.
- DOI: `10.1007/978-3-642-33573-0_19`
- Status: `FULL_READ` (18/18 PDF pages = journal pp. 315-332, 2026-07-25). Note: the paper was
  screened at 16 pages; the actual PDF has 18 pages (title verified against the PDF text, not
  assumed from the screening record).
- Visual verification: figures were extracted as embedded page images and inspected inline while
  reading (Figs. 1-3 topological definitions, Fig. 4 fundamental-sheet levels, Figs. 6/9 curve
  labeling and the search-tree worked example, Figs. 10-13 the two worked results). All are legible
  and consistent with the extracted text.
- Nature of paper: **algorithm + worked examples, no quantitative validation**. Section 4 shows two
  qualitative results (a diamond-shaped solid and a "hook" model) with rendered meshes and sheet
  sets, but reports zero numeric quality metrics, no timings, and no before/after comparison table.

## Relationship to the already-read Ledoux 2010 paper (important correction)

This paper is **not** a direct geometric-guidance sequel to
`docs/references/literature/native_hex/ledoux2010_sheet_operations.md` (Ledoux & Shepherd,
*Topological modifications of hexahedral meshes via sheet operations*, EwC 2010, pp. 433-447,
reference [7] here). That 2010 paper is cited only once, as the source of the general sheet-op
catalog (extraction/pillowing/chord-collapse) for context.

The concept this 2013 paper actually builds on - "fundamental mesh" and "fundamental sheet" - comes
from a **different, sibling 2010 paper**: Ledoux & Shepherd, *Topological and geometrical properties
of hexahedral meshes*, EwC 2010, pp. 419-432 (reference [6] here, published in the same journal issue
as the sheet-operations paper but not the same article, and **not yet read** in this literature set).
This 2013 paper re-derives/re-states the fundamental-sheet definitions itself (Sect. 2, Defs. 1-4), so
it is fully self-contained for our purposes, but the citation trail means "the direct follow-up to
Ledoux 2010" is really two branches: the sheet-*operations* paper we already read supplies the
mechanical vocabulary (pillowing), while the fundamental-*mesh* paper (unread, ref [6]) supplies the
formal target this paper's algorithm converges toward. Only **pillowing/inflation** is used as the
concrete operation in this paper - sheet extraction and chord collapse from the 2010 sheet-ops paper
are never invoked.

## Mechanism

**(1) "A posteriori" precisely defined.** The technique is applied *after* an initial hexahedral mesh
M already exists (built by any inside-out/octree-style or THex-splitting generator) and after M's
boundary nodes/edges/faces have already been classified onto the CAD B-Rep `G = (S, C, V)` (geometric
surfaces, curves, vertices; Definition 1, "geometric association"). "A posteriori" = a mesh-improvement
post-process, not a generation-time algorithm, and the reference it corrects *against* is the **CAD
topology and its dihedral-angle geometry**, not a target quality number - the goal is to make M's
sheet structure match the CAD model's curve/vertex topology (a "fundamental mesh" of G, Sect. 2.3).

**(2) What decides which sheet operation to apply where.** This is the paper's actual contribution,
and it is entirely new relative to the 2010 papers:

- Build a weighted graph from the CAD model's vertices/curves. For each geometric curve `c`, compute
  an *ideal* label `w_g` in {1,2,3,4} from the maximal dihedral angle along `c`'s mesh edges:
  label 1 if angle < 3π/4, 2 if in [3π/4, 3π/2), 3 if in [3π/2, 7π/4), 4 if ≥ 7π/4 (p.322). The label
  is literally "how many fundamental chords should surround this curve," i.e. a direct dihedral-angle
  → hex-count-at-the-edge mapping.
- At each 3-, 4-, or 5-valent geometric vertex, only a fixed, enumerated set of curve-label
  combinations is topologically valid for a hex mesh (Table 1, e.g. "1-1-1" → 1 hexahedron at the
  corner, "2-2-2-2" → 4 hexahedra, etc.). Assigning labels independently per curve will generally
  conflict at shared vertices.
- This is formalized as an integer minimization `F = min Σ λ_{wg-wc}` over all curves (Eq. 1), with a
  hand-chosen, heavily asymmetric penalty schedule (`λ0=0, λ_{-1}=1, λ_{-2}=2, λ_{-3}=3, λ1=1,
  λ2=10^3, λ3=10^6`) that strongly forbids *reducing* a curve's chord count below its ideal (which can
  produce degenerate/inverted corner hexahedra) while tolerating an *increase* (extra, non-optimal but
  valid hexahedra).
- Solved by a depth-first branch-and-bound search tree, one geometric vertex at a time, expanding only
  the valid local configurations from Table 1 and pruning any child whose partial cost already exceeds
  the best complete solution found (Lemma 1: F is monotonically non-decreasing down the tree, so
  pruning is sound). Lemma 2 proves the trivial "label everything 2" assignment is always a valid
  fallback, so the search always terminates with *some* answer.
- Once every curve has a final label, a deterministic rule table (p.327-328, four cases keyed by the
  labels of a surface's incident curves) determines which surfaces get a level-1 sheet, which get a
  level-2 sheet, and which curves need extra level-3 sheets, and defines the *path of mesh faces* (a
  2-manifold) that must be inflated for each.
- The actual mesh edit is then "an adaptation of the pillowing algorithm [Mitchell & Tautges 1995]":
  each defined face path is inflated into one new hex layer. No other sheet operation (extraction,
  chord collapse, dicing) is used or evaluated.

**(3) Guarantees.** The labeling/solving stage is proven to always terminate with a valid (if
not optimal) result (Lemma 2) and the search always finds the F-minimal valid labeling reachable from
the branch-and-bound tree (Lemma 1 underwrites correctness of the pruning, not global optimality of
the heuristic penalty choice itself, which is admitted to be arbitrary: "This cost term can be set
freely"). The paper states, without proof, "once the set of faces is defined, the sheet insertion
process always works" (footnote 4 on the same page immediately qualifies this: *"getting a robust
sheet insertion process with mesh classification (i.e. geometry association) is technically difficult
to implement"* - i.e. keeping Definition-1 geometric association correct on the newly inflated faces
is an acknowledged open practical problem, not something proven solved).

## Experiments

Two qualitative examples only (Sect. 4): a diamond-shaped solid (two opposite 4-valent vertices,
eight 3-valent vertices) and a "hook" model, both starting from a THex mesh (each tet of a tet mesh
split into 4 hexes - not from an octree/inside-out mesh, despite the motivating discussion being about
octree methods). For each, the paper shows rendered meshes and the extracted level-1/level-2/level-3
sheet sets (Figs. 11-13). **No quality metric of any kind is reported** - no Jacobian, no skew/
orthogonality number, no aspect ratio, no Hausdorff/surface-deviation number, no element count, no
timing, no before/after comparison. The stated results are "the resolution of the constraint system
always finishes as expected and proved" and a qualitative "first results allow us to assess the
adequacy of the approach." This paper therefore does **not** close the quantitative gap flagged
against Ledoux 2010 - it only replaces "no geometric guidance at all" with "a specific, well-defined,
purely topological/angular guidance rule," while remaining just as silent on measured quality outcome.

## Limitations (author-stated)

- No quantitative validation anywhere (see above) - theory + two qualitative demonstrations only.
- "The definition of the set of faces to inflate depends on the base mesh and it should be improved
  for inner sheets when the initial mesh is too coarse" - the face-path construction for interior
  (level-2/level-3) sheets is base-mesh-dependent and not robust for coarse input.
- Interior sheets must form a 2-manifold and must not propagate out of the domain; this is described
  as a live risk, not a solved invariant.
- "Some level 2 and level 3 fundamental sheets could be connected inside the domain. It is currently
  not handled" - the authors state there is no known theoretical obstruction but call it unimplemented
  "technical work."
- Footnote 4: robust sheet insertion **with correct mesh classification** (i.e., correctly
  re-associating new faces/nodes with `S`/`C`/`V` after insertion) is called "technically difficult to
  implement" - an open practical gap, explicitly flagged by the authors themselves.
- **Single-domain only.** Section 5 states multi-domain geometries are future work: "The resolution
  of the constraint system will remain unchanged as fundamental sheets should match between adjacent
  domains, while the definition of the sheets to insert will have to be done on all the domains and no
  longer on a single one." Multi-component/bracket-style damage (multiple bodies, shared or
  independent patches) is **not addressed** in this paper - it is explicitly out of scope, left as an
  unimplemented extension.
- The penalty weights (`λ`) that drive the whole optimization are admitted to be an arbitrary, freely
  tunable choice, not derived from any quality model.

## AutoTessell applicability

Context: `core/generator/native_hex/octree.py` and `core/generator/native_hex/mesher.py` (see the
Maréchal 2009 note in this same directory for current adaptive-transition state), plus the sheet-ops
groundwork already scoped in `ledoux2010_sheet_operations.md` (HEX-SHEET-1/2 cards, per-wall pillowing
for boundary layers). This paper adds a concrete, CAD-derived decision rule for exactly the question
those cards left open: *how many* chords/hexahedra should surround a given sharp edge, and *is the
current octree output under- or over-provisioned there*.

- **Boundary-preservation verdict: compatible with our frozen/pinned-boundary invariant.** The
  technique never repositions an existing boundary vertex. It only inflates (pillows) a chosen 2-manifold
  face path into a brand-new hex layer, which by construction adds new interior structure without
  moving the geometry already classified on `S`/`C`/`V`. This is the same topology-only property
  already established for pillowing in `ledoux2010_sheet_operations.md`. The one caveat: after
  inflation, the *new* faces/nodes must be (re-)classified onto the CAD boundary correctly, and the
  paper itself flags this re-classification step as the hard, unproven part (footnote 4) - our own
  wall-fit-snap lane would need to own this step, not assume it comes for free.
- **Applicability to isolated-singleton vs. multi-component damage.** The dihedral-angle curve-labeling
  and vertex-configuration solver operate on a single CAD body's curve/vertex graph; the paper is
  explicit that multi-domain assembly cases are unimplemented future work. This maps directly onto our
  own "isolated coherent region" vs. "bracket-style, 7-components/6-patches" distinction: the technique
  as published is only ready for the single-component case. Extending it to our multi-patch bracket
  case would require, at minimum, matching fundamental sheets across shared patch boundaries - exactly
  the unsolved extension the authors describe.
- **No standalone quality claim can be borrowed.** Because the paper reports zero quality numbers, any
  AutoTessell card built on this must supply its own before/after measurement (skew, non-orthogonality,
  wall_dev) - the same discipline already required for the sheet-ops cards.

## Falsifiable implementation cards

### HEX-LEDOUX13-1 - CAD dihedral-angle curve-label diagnostic (no mesh edit)

- For every sharp edge/curve group already classified during native_hex's boundary recovery, compute
  the maximal dihedral angle and the ideal label `w_g` in {1,2,3,4} per the paper's thresholds, plus the
  actual current chord count at that curve in the generated mesh.
- Pass: report, per sharp curve, `(ideal_label, actual_chord_count, deficit/surplus)`; report is purely
  diagnostic, no mesh is modified. This is a read-only quality-report addition, safe to land regardless
  of the pillowing work below.
- Stop rule: if dihedral-angle extraction is already noisy/unstable on our CAD-derived STL boundaries
  (faceted geometry has no true dihedral angle), bucket by feature-edge type (ridge/corner tag already
  used elsewhere in `core/analyzer/`) instead of raw angle before trusting the label.

### HEX-LEDOUX13-2 - constrained labeling + single-sheet pillow insertion (single-component only)

- Implement the vertex-valence validity table (Table 1, 3/4/5-valent cases) and the depth-first
  branch-and-bound labeling solver against a single coherent CAD body's curve/vertex graph (reuse the
  HEX-SHEET-2 pillowing primitive from `ledoux2010_sheet_operations.md` as the insertion mechanism).
- Target: sharp edges flagged by HEX-LEDOUX13-1 as under-provisioned (actual chord count below ideal
  label) on a single-component test part.
- Pass: after insertion, checkMesh stays clean and all-hex; the target curve's chord count matches or
  exceeds its ideal label; wall_dev_max and skew gates are re-measured (not assumed) before/after, since
  the source paper supplies no evidence either way.
- Stop rule: do not attempt this on multi-component/bracket geometry - the paper's own scope excludes
  it, and cross-patch sheet matching is unimplemented in the source algorithm.

### HEX-LEDOUX13-3 - re-classification transaction for inflated faces

- Address the paper's own flagged gap (footnote 4): after HEX-LEDOUX13-2 inflates a face path, verify
  and record the geometric association (Definition 1: which CAD surface/curve/vertex each new
  node/edge/face belongs to) as an explicit, checked step rather than an implicit side effect.
- Pass: every newly inserted boundary node/edge/face has a recorded CAD classification; a synthetic test
  that inflates a corner sheet on a simple faceted solid (e.g. a chamfered cube) shows the new layer's
  outer faces classified onto the correct original surfaces, not left unclassified or misclassified.

## Snowball references (max 5)

1. Ledoux, F., Shepherd, J. 2010, *Topological and geometrical properties of hexahedral meshes*, Eng
   Comput 26:419-432 - the actual source of the "fundamental mesh"/"fundamental sheet" definitions this
   paper builds on; not yet read in this literature set, highest-priority next read to get the full
   formal foundation instead of this paper's restated subset.
2. Mitchell, S.A., Tautges, T.J. 1995, *Pillowing doublets: refining a mesh to ensure that faces share
   at most one edge*, IMR 4, pp. 231-240 - the pillowing/inflation algorithm actually used as the
   mechanical operation here.
3. Merkley, K., Ernst, C., Shepherd, J.F., Borden, M.J. 2007/2008, *Methods and applications of
   generalized sheet insertion for hexahedral meshing*, IMR 16, pp. 233-250 - already flagged in the
   2010 sheet-ops note as the quality-driven half that both 2010/2013 papers omit; still the
   highest-priority read for actual geometric-quality guidance on sheet insertion.
4. Kowalski, N., Ledoux, F., Staten, M.L., Owen, S.J. 2011, *Fun sheet matching: Towards automatic block
   decomposition for hexahedral meshes*, Eng Comput - directly relevant to the multi-domain/matching
   extension this 2013 paper defers to future work.
5. Qian, J., Zhang, Y. 2010, *Sharp feature preservation in octree-based hexahedral mesh generation for
   CAD assembly models*, IMR 19, pp. 243-262 - explicitly an assembly (multi-component) variant of the
   same sharp-feature-preservation problem, i.e. the paper most likely to cover the multi-component gap
   this 2013 paper leaves open.

## Decision

Use this paper as the **geometric decision rule** for where/how many sheets to pillow near sharp CAD
edges (dihedral-angle labeling + vertex-valence constraint solving), layered on top of the pillowing
mechanics already scoped from `ledoux2010_sheet_operations.md`. Do not cite it as evidence that the
resulting mesh is geometrically better - it reports no quality metric at all, so any improvement claim
must come from our own HEX-LEDOUX13-2/3 measurements. Do not apply it to multi-component/bracket
geometry - that case is explicitly future work in the source paper, not a solved capability.
