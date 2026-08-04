# Chen, Yang, Sun 2026 (CJA) - Edge-Subdivision-Based Adaptive Refinement for Unstructured Meshes with Element Quality Control

## Bibliographic record

- Weihao CHEN, Xiaobin YANG, Gang SUN, *Edge-subdivision-based adaptive refinement for
  unstructured meshes with element quality control*, Chinese Journal of Aeronautics,
  2026, article 104154 (Journal Pre-proof, in press).
- Affiliation: Department of Aeronautics & Astronautics, Fudan University, Shanghai.
- DOI: `10.1016/j.cja.2026.104154`. Received 5 Sep 2025, revised 9 Mar 2026, accepted
  9 Mar 2026.
- Local PDF: `docs/references/papers/source/pdf/46_chen_2026_cja_hanging_node_transition.pdf`.
- **Status: `FULL_READ`, 2026-07-25. Honest page accounting: the PDF has 37 pages total
  (confirmed by `pypdf` page-tree count, cross-checked against `pdftotext` form-feed
  count), not 161 as the task brief assumed — that number does not match this file.**
  Breakdown: page 1 = Elsevier pre-proof cover/metadata sheet (title, authors, DOI,
  boilerplate only); pages 2-32 = the full article body, sections 1-6 plus references
  (journal-numbered pages ·1·-·31·); pages 33-35 = Appendix A, three pages of
  conversion-required-topology figure galleries (Figs. A1-A4, one-line captions only,
  no additional prose — skim-classified, not deep-read, because there is nothing to
  deep-read beyond the caption text already extracted); pages 36-37 = Declaration of
  Interest administrative page. All 37 pages were opened and their extracted text
  reviewed; there is no separate 161-page supplement bundled in this file.
- Not related to the already-read `chen2026_hex_quality.md` note (Chen/Zheng/Liao/Gao,
  Engineering with Computers, DOI `10.1007/s00366-025-02241-w`, QHED/ScoreCHE hex
  distribution census) — different authors, different journal, different problem
  (hex-dominant *generation* distribution metric vs. h-*adaptive-refinement* hanging-node
  topology + quality control). No content overlap between the two notes.

## Problem and claimed scope

This is **not** an octree-based all-hex mesh *generation* paper like Maréchal 2009 /
Gao 2019 / Zhang 2013 / Pitzalis 2021 / Livesu 2022. It targets **solution-adaptive
h-refinement of an already-existing conforming unstructured mesh** in a CFD solver
loop: flag target elements from an error indicator, subdivide them, and resolve the
hanging nodes this creates on neighboring ("transition") elements so the mesh stays
conforming and uses only standard element types (tet/pyramid/prism/hex — no
polyhedra). The paper's two headline problems are exactly the two pain points named in
the task: (1) **excessive refinement propagation** into non-target regions caused by
having too few known hanging-node subdivision templates, and (2) **rapid mesh-quality
degradation** caused by anisotropic subdivision of already low-quality transition
elements — which the abstract states in almost the same words as our own damage
pattern ("hanging node adjacent cell has poor quality").

## Algorithm read from the paper

1. **Isotropic subdivision of target (flagged) elements.** All edges of a target
   element are bisected (Figs. 1-2); this is claimed to bound geometric degradation
   because sub-element quality stays comparable to the parent.
2. **Hanging-node topology enumeration and classification.** Every element that
   gains hanging nodes from a neighbor's subdivision is classified by its "topology"
   (which of its edges are split). Topologies split into:
   - **Subdivision-allowed** types — have a hard-coded subdivision template that
     directly resolves the hanging nodes into standard sub-elements.
   - **Conversion-required** types — either would produce non-standard polyhedra
     (strictly forbidden) or unacceptably distorted standard elements (tolerated only
     up to a point); these are converted into a subdivision-allowed type by
     **additional edge subdivision**, choosing the option that (a) guarantees
     sub-element quality and (b) subdivides the fewest extra edges (Fig. 5).
   - Coverage achieved: tetrahedra 11/11 topologies (6 allowed + 5 conversion-required,
     exhaustive — small edge count makes this tractable); pyramids 69/69 (10 + 59);
     prisms 103/103 (26 + 77); **hexahedra: only 170 of the combinatorially possible
     4095 configurations are enumerated (30 allowed + 140 conversion-required) — the
     paper explicitly states full hex enumeration is intractable**, and every
     unenumerated hex topology falls back to "subdivide all 12 edges" (labeled H12),
     i.e. full isotropic subdivision as the universal fallback. Configuration count
     formula given: for an element with `m` edges, total hanging-node configurations
     `= sum_{n=1}^{m-1} C(m,n)` → 63 (tet), 255 (pyramid), 511 (prism), 4095 (hex).
3. **Element quality control gate on transition elements** (the paper's other named
   contribution). Three metrics, each in a bounded range:
   - **Warpage** `= 1 - min(n1·n3, n2·n4)` of a quad face's corner normals, in `[0,1]`;
     volume-element warpage = max over its quad faces; tets have none by construction.
   - **Skewness**, normalized equiangular form
     `= max((θmax-θideal)/(180-θideal), (θideal-θmin)/θideal)`, range `[0,1]`; ideal
     dihedral angles 70.53° (tet), 90° (hex), 63.43° (pyramid base-to-lateral), and a
     two-part 90°/60° criterion for prisms.
   - **Aspect ratio**: `circumradius/inradius / 2` for triangles (generalizing to the
     max over faces for volume elements), or the principal-axis ratio for quads;
     range `[1, +inf)`.
   Gate: a transition element is only allowed **anisotropic** (hanging-node-driven)
   subdivision if `warpage < τw AND skewness < τs AND aspect_ratio < τa`; otherwise it
   is forced through **isotropic** subdivision instead (all edges split), which the
   paper shows empirically does not worsen skewness/aspect ratio and actively reduces
   warpage of the resulting faces (Fig. 12). Thresholds used in experiments:
   `τw=0.6, τs=0.75, τa=15` for a hybrid tet/prism mesh (citing Verdict-library and
   ANSYS acceptable-range references for the first two; the aspect-ratio bound is
   raised from the usual tet bound of 3 specifically to tolerate prism boundary
   layers, then hand-tuned by trial).
4. **Refinement procedure** (Fig. 13): flag → isotropic-subdivide targets → collect
   newly hanging-node-bearing neighbors into a "pending element set" → iterate: for
   each pending element, check quality gate first (fail → force isotropic, which can
   cascade new hanging nodes to further neighbors), else check topology (allowed →
   subdivide directly; conversion-required → convert then subdivide) → repeat until
   the pending set is empty → done. Complexity argued as O(N) worst case (each element
   can be reprocessed at most `#edges` times, each O(1)); practically far less than N.
5. **Boundary-layer refinement with layer preservation.** Restricting transitional
   conversion to only three prism templates (Pr2T2, Pr4T5, Pr6T3) guarantees any
   prism in a stack normal to the wall can be resolved without ever creating a
   lateral hanging node — because adjacent layers stay fully connected through
   top/bottom prism faces regardless of how neighboring layers are subdivided. This
   lets the method preserve full or partial (per-layer) boundary-layer structure
   while refining tangentially, analogous templates given for hex BL stacks
   (H2T1, H4T2, H4T3, H6T4, H8T4).
6. **Coarsening** is refinement's inverse via a parent-child rollback data structure;
   implemented conceptually (Fig. 14) but **not validated with numerical examples** —
   the paper's own future-work list says so explicitly.

## Assumptions, guarantees, limits

- **No formal validity or positive-Jacobian proof anywhere.** All safety is
  heuristic/empirical: threshold-gated fallback to isotropic subdivision, backed by
  before/after measurements on real CFD meshes, not a constructive guarantee. This is
  a materially weaker guarantee tier than Livesu 2022 (exhaustive 20-transition / 8+5
  atomic scheme, constructive all-hex proof for balanced+paired grids) or Gao 2019
  (dual conversion is inversion-free "by construction" for its axis-aligned
  frustum/trapezoid cases).
- **Hex hanging-node enumeration is admittedly incomplete** (170/4095, ~4%); anything
  outside that set is handled by full isotropic subdivision (H12) as a blunt,
  guaranteed-safe fallback that trades element count for guaranteed conformity.
- **Domain assumption differs from AutoTessell's octree-generation lane**: this method
  refines an *existing conforming mesh* element-by-element via edge bisection; it does
  not build a mesh from an octree from scratch, has no notion of octree balancing/
  pairing, and never produces or reasons about polyhedral transition cells (unlike
  Maréchal/Gao/Pitzalis/Livesu, whose all-hex path is a dual-of-polyhedral-primal
  construction). The topology tables are therefore not a drop-in replacement for an
  octree transition-scheme lookup table.
- **Empirical evidence the quality-gate mechanism works** (Table 4, hybrid
  tet/prism ONERA M6 case, two refinements): without quality control, max skewness
  rose to 0.989 and max aspect ratio to 162.26, with minimum mesh orthogonality
  collapsing to 1.18e-6; with quality control (thresholds above), max skewness 0.967,
  max aspect ratio 131.84, minimum orthogonality 5.03e-6 — roughly 4x better floor
  orthogonality, at the cost of slightly more transition elements (Table 3: 15.80%
  vs 14.70% of mesh on the second refinement). For the pure-hex ONERA M6 case run
  *without* quality control (Table 2), orthogonality catastrophically collapses from
  0.088 to 7.93e-13 after two refinements — a directly measured demonstration of the
  paper's central quality-degradation claim, on a hex-dominated mesh, which is close
  in spirit to AutoTessell's own native_hex transition-cell damage.
- **Stricter thresholds are explicitly a trade-off, not a free win**: Tables 5-7 show
  tightening any one threshold monotonically increases the number of transition
  (and hence sub-)elements while capping the worst-metric value — the paper
  explicitly warns against over-tightening because it can flip more of the mesh into
  anisotropic-then-isotropic cascades and increase the *proportion* of low-quality
  elements even as the worst case improves.
- Feature/geometry preservation, projection, and CAD-surface fitting are entirely out
  of scope — this is a bulk-interior CFD solver mesh refinement method, with no
  boundary-projection or feature-matching machinery at all (contrast Gao 2019's
  corner/curve/patch provenance machinery).

## Experiments

Three aerodynamic RANS cases (ONERA M6 wing hex mesh; ONERA M6 hybrid tet-prism mesh;
nacelle hybrid tet-prism mesh with boundary-layer preservation; NASA CRM-WBH hybrid
mesh), each refined 1-2 times using a pressure-gradient error indicator, with
before/after pressure-coefficient comparisons against experimental/reference data
(Schmitt & Charpin 1979; Diskin et al. 2018) showing improved accuracy with
refinement. Mesh sizes are large (up to ~10.3M elements). All quantitative quality
data (Tables 1-8) is on the ONERA M6 cases; nacelle and CRM cases are qualitative
(pictures + pressure profiles) only, used to demonstrate boundary-layer preservation
and applicability to complex CAD geometry respectively. No comparison against any
other named refinement method (Biswas & Strawn, Kallinderis, etc.) — all comparisons
are internal (with/without quality control, with/without full-layer preservation).

## Delta vs. already-read corpus

- **vs. Zhang 2013 / Maréchal 2009 / Gao 2019 / Pitzalis 2021 / Livesu 2022** (octree
  all-hex generation lane): no methodological overlap in the generation mechanism —
  those papers build hex meshes from scratch via octree + dual/primal conversion with
  constructive all-hex proofs; this paper refines an existing arbitrary-element mesh
  via direct edge-bisection templates with no such proof. The overlap is only
  conceptual: both lanes must resolve "hanging nodes on adjacent cells" and both
  observe that naive/anisotropic resolution damages element quality. This paper is
  the first in the read corpus to supply a **named, threshold-based, before/after
  quantified quality-gate mechanism** specifically for *that* damage mode, which the
  octree lane papers do not offer (they gate on topological validity, not per-cell
  shape metrics during the transition-subdivision decision).
- **vs. chen2026_hex_quality.md** (QHED/ScoreCHE, EWC): confirmed unrelated as noted
  above — no shared authors, methods, or metrics; do not conflate in any future
  cross-referencing.
- **Novel-to-corpus finding worth carrying forward regardless of code overlap**: the
  quantitative orthogonality collapse (0.088 → 7.93e-13, six orders of magnitude, in a
  pure-hex mesh refined without quality control) is a striking, directly citable
  number for why *any* hanging-node transition mechanism needs an explicit shape
  gate — useful supporting evidence for AutoTessell's own bracket/cylinder/sphere/gear
  observations even though the generation mechanisms differ.

## AutoTessell applicability

Relevant code: `core/generator/native_hex/octree.py` (adaptive transition cells,
level-grid 2:1 balance), `core/generator/native_hex/mesher.py` (adaptive cell writer,
quality summary), `core/evaluator/native_checker.py` (non-orthogonality/skewness/
aspect-ratio measurement — the same three quality families this paper uses, already
present in our evaluator under different names).

This paper does not hand us a hex transition template set we can port (its own hex
enumeration is admittedly a ~4% partial sample, and its domain — refining an existing
generic-element mesh — does not match our octree-from-scratch generation). What it
does hand us is a **validated pattern**: gate the *decision* of how to resolve a
hanging-node-adjacent cell on the cell's own pre-transition shape metrics, with a
guaranteed-safe (if expensive) fallback, and *measure* orthogonality/skewness/aspect
before and after to prove the gate helps. That pattern is directly transplantable onto
our octree transition-cell pipeline regardless of whether we eventually adopt
Livesu 2022's dual scheme set (HEX-OCT-2) for the topological side.

### HEX-TRANS-1 - quality-gated transition-cell handling

- Before finalizing a hanging-node-adjacent (transition) cell in
  `core/generator/native_hex/octree.py`, compute its warpage/skewness/aspect-ratio
  (or reuse the evaluator's non-orthogonality/skewness/aspect-ratio measures) on the
  *candidate* transition result and compare against thresholds (start from the
  paper's `τw=0.6, τs=0.75, τa=15` as a first calibration point, tune against our own
  mesh corpus). If the candidate fails the gate, fall back to a safer transition
  (more symmetric subdivision / one more level of local refinement) instead of
  accepting the generic split-face polyhedron as-is.
- Pass: on the bracket/cylinder/sphere/gear benchmark set, log gated-vs-accepted
  transition-cell counts and the worst-case orthogonality/skewness/aspect ratio
  before vs. after the gate is enabled; the gate must strictly not make any of these
  worse, and should demonstrably raise the worst-case orthogonality (paper's own
  hex case improved the floor by ~4x with an equivalent gate).
- Falsification: if enabling the gate changes nothing (no cells ever fail it, or the
  fallback path is never exercised) on our known-damaged shapes, the "hanging node
  adjacent cell has poor quality" diagnosis needs re-examination — the damage may
  come from a different stage (e.g. boundary snap/projection) rather than the
  transition-subdivision decision itself.

### HEX-TRANS-2 - hanging-node-adjacency damage census (diagnostic, precedes HEX-TRANS-1)

- Extend `core/evaluator/native_checker.py`'s quality report with a per-cell flag
  for "is this cell adjacent to an octree level change / hanging-node face" and
  cross-tabulate that flag against non-orthogonality/skewness/aspect-ratio bins.
- Pass: produces a table (like the paper's Tables 2/4) showing whether our own
  bracket/cylinder/sphere/gear quality damage is concentrated on hanging-node-adjacent
  cells (confirming the paper's damage mechanism applies to us) or spread more
  broadly (meaning HEX-TRANS-1 alone would not fix the observed damage, and the
  Elsheikh 2014 ECR/HexOpt refutation's post-snap explanation is the dominant factor
  instead). This is a cheap, purely-diagnostic card that should run *before*
  committing engineering time to HEX-TRANS-1.

### HEX-TRANS-3 - boundary-layer stack-aware transition restriction (lower priority)

- Port the structural idea (not the specific prism templates, which assume a
  different element-subdivision scheme than ours) that boundary-layer stacks can be
  refined tangentially without lateral hanging nodes by restricting which transition
  outcomes are accepted per stacked cell, and that partial (per-layer) preservation
  is achievable by scoping the restriction to specific layers. Relevant to any future
  interaction between `core/layers/native_bl.py` and adaptive octree refinement,
  where boundary-layer cells are exactly the aspect-ratio-sensitive population most
  vulnerable to hanging-node transition damage per project lessons-learned.
- Pass: define upfront before implementing — no current AutoTessell code path
  refines an already-generated BL stack, so this card is speculative/future-facing;
  do not implement until a concrete adaptive-BL-refinement use case exists.

## Snowball references (<=5)

1. Sahni, Jansen, Shephard, et al. 2008, *Adaptive boundary layer meshing for viscous
   flow simulations*, Eng Comput 24(3):267-85 — cited as the boundary-layer refinement
   baseline this paper's layer-preservation contribution improves on; worth checking
   against `core/layers/native_bl.py` design.
2. Kallinderis, Kavouklis 2005, *A dynamic adaptation scheme for general 3-D hybrid
   meshes*, CMAME 194:5019-50 — cited as prior art on hybrid-mesh hanging-node
   handling with fewer topologies enumerated; useful contrast case for HEX-TRANS-2.
3. Shewchuk 2002, *What is a good linear element? Interpolation, conditioning, and
   quality measures*, IMR — the theoretical grounding the paper cites for why
   geometry-based quality metrics matter; useful shared reference with our evaluator's
   own quality-metric rationale.
4. Stimpson, Ernst, Knupp, et al. 2007, *The Verdict library reference manual*, Sandia
   report — source of the warpage/aspect-ratio range definitions and acceptable
   thresholds used here; likely already indirectly present via Knupp 2001 in our
   corpus, worth cross-checking definitions match `native_checker.py`.
5. Biswas, Strawn 1996/1998, *Mesh quality control for multiply-refined tetrahedral
   grids* / *Tetrahedral and hexahedral mesh adaptation for CFD problems*, cited
   repeatedly as the "few template" baseline this paper argues against (only 3-4
   allowed tet topologies causing over-propagation) — useful negative baseline for
   any future propagation-rate benchmark.

## Decision

Use this paper only for the transition-cell **quality-gate pattern** and its
quantified evidence that ungated anisotropic subdivision near hanging nodes collapses
orthogonality by orders of magnitude — directly relevant supporting evidence for our
own damage pattern. Do not treat its hex hanging-node topology tables as a usable
template library (they are a ~4%-complete sample for a different problem domain, refining
an existing mesh rather than octree-generating one). Run HEX-TRANS-2 (diagnostic
census) before committing to HEX-TRANS-1 (the actual gate implementation) to confirm
the damage mechanism transfers to our octree-transition setting rather than assuming it.
