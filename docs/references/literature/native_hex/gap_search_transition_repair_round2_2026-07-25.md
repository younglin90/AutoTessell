# Native Hex gap search round 2: post-snap local repair of octree transition/hanging-node regions

**Date:** 2026-07-25
**Scope:** documentation-only snowball search; no engine or gate changes. Continues
`gap_search_transition_sheet_provenance_2026-07-25.md` after both of that round's P0
full-reads (Elsheikh 2014, Chen 2026 CJA) turned out **not** to close the gap: Elsheikh
2014 is a generation-time pre-pass (competes with Zhang2013/Pitzalis2021/Livesu2022 in
the octree-template lane), and Chen 2026 CJA's quality-gate pattern is portable but its
own mechanism is edge-bisection h-refinement of an *already-conforming* mesh, not
octree-from-scratch generation, and its hex hanging-node table is only ~4% complete.

**Precise gap restated:** a mechanism that takes an *already-generated* octree-to-hex
mesh (post wall-fit-snap) and repairs the specific cells near octree transition/
hanging-node regions **without** regenerating the whole mesh and **without** a generic
MSJ-type untangling objective (ECR/HexOpt already empirically refuted across 4 shapes,
0-32% worst-tail overlap with our OpenFOAM skew metric).

## Screening protocol

Same labels as round 1 (`evidence_matrix.md`, `gap_search_transition_sheet_provenance_2026-07-25.md`):
P0/P1/P2 priority, INCLUDE/CONTEXT/EXCLUDE decision, OPEN/ABSTRACT_ONLY access. A DOI is
recorded only after it was independently confirmed against Crossref/Semantic Scholar
metadata (title + authors + venue match) — every DOI below was checked this way; none
are invented.

## Search strategy executed

1. Forward/backward citation snowball from Elsheikh 2014 (via Semantic Scholar's
   citation graph — 8 citing papers found, none new/relevant beyond what round 1 already
   had) and from Chen 2026 CJA's own backward references (5 snowball refs already listed
   in `chen2026_cja_hanging_node_transition.md`; none is a post-hoc hex repair method).
2. Direct searches for "hex mesh local repair hanging node", "octree transition element
   quality improvement post-hoc", "hex mesh pillowing near hanging node",
   "template-local hex re-meshing quality", "hex sheet insertion targeted repair
   octree", "boundary layer octree hex quality correction".
3. Ledoux & Shepherd 2010 forward-citation / author-lineage check specifically for
   sheet ops applied to boundary/transition regions (not generic sheets). Found by
   following the **author**, not a citation graph: Ledoux et al. published a direct
   a posteriori follow-up (2012/2013, IMR21) that Ledoux 2010 itself never cites forward
   to (it postdates Ledoux 2010) and round 1 missed because it only pulled Ledoux 2010's
   own backward references.
4. Commercial/production mesher literature: found a Sandia patent (assignee National
   Technology and Engineering Solutions of Sandia, i.e. the CUBIT lineage) that
   operationalizes exactly a locally-scoped, depth-bounded sheet-operation repair — the
   "mesh matching" family, with an original 2008 IMR paper, a 2010 IJNME journal
   version, a 2016 quality-driven improvement, and a 2023/2024 base-complex-driven
   improvement.

**Screening count this round: 12 new records** (plus DOI-reconfirmation of Ledoux 2010's
already-read forward lineage). Two consecutive follow-up searches (`boundary layer
octree hex quality correction` / cfMesh-snappyHexMesh literature, and `octree hex
transition cell targeted quality repair 2024 2025`) returned only papers already in the
corpus (HybridOctree_Hex, Element-Saving Hex 3-Refinement Templates) — no fourth
mechanism family emerged after the three found in this round, so the round stops here
per the stated stop rule.

## A. Mesh matching — local, depth-bounded sheet-operation repair (NEW mechanism family)

This is the strongest new finding. "Mesh matching" reconciles two **non-conforming**
regions of an all-hex mesh by applying pillowing / sheet extraction / dicing / column
collapse **only within a bounded local neighborhood** of the mismatch, controlled by an
explicit depth parameter — not a generic MSJ-style global untangler, and not a
from-scratch regeneration. It was designed for gluing two independently-meshed
hex volumes at a shared interface, but the mechanism itself (repair a bounded local
region until dual-chord/topology mismatch resolves) is exactly the shape of the
octree-transition problem: our damage census shows isolated singleton bad faces
(cylinder/sphere/gear) vs. 7 connected components across 6 patches (bracket) — a
depth-bounded local repair is a plausible match for both damage topologies, unlike a
global optimizer.

| Priority | Decision | Candidate | DOI / access | Why it matters |
|---|---|---|---|---|
| P0 | INCLUDE | Staten, Shepherd, Shimada (2008), *Mesh Matching — Creating Conforming Interfaces between Hexahedral Meshes*, IMR17 | `10.1007/978-3-540-87921-3_28` — Crossref-confirmed; **OSTI OPEN** full PDF at `osti.gov/servlets/purl/1145637` (scanned/encoded PDF, not machine-text-extractable by our tooling, but freely downloadable) | Original mesh-matching algorithm: pillowing, sheet extraction, dicing, column collapse applied only to the mismatched interface region. Direct topological ancestor of the patent below. |
| P0 | INCLUDE | Staten, Shepherd, Ledoux, Shimada (2010), *Hexahedral Mesh Matching: Converting non-conforming hexahedral-to-hexahedral interfaces into conforming interfaces*, Int. J. Numer. Meth. Engng 82(12):1475-1509 | `10.1002/nme.2800` — Crossref-confirmed; Wiley, ABSTRACT_ONLY (journal paywall; likely the fuller version of the IMR17 paper above) | Journal-length version with the full algorithm and (per patent text below) explicit locality control via a depth parameter — the extended proofs/examples the conference paper omits. |
| P0 | INCLUDE | Staten, Shepherd, Ledoux, Shimada, Merkley, Carbonera, US Patent **8,390,620 B1** (filed 2009-03-04, granted 2013-03-05), *Technique for converting non-conforming hexahedral-to-hexahedral interfaces into conforming interfaces*, assignee National Technology and Engineering Solutions of Sandia LLC | Google Patents, **OPEN** (`patents.google.com/patent/US8390620B1/en`) | Fetched and read directly (not abstract-only). States explicitly: **"locality of the changes is maintained through use of an input depth parameter and column collapse operations"** — this is the direct primary-source answer to search-strategy item 4 (does production mesher literature document a named local "transition repair" step distinct from both pre-pass conditioning and generic untangling — yes). Also states honestly: **"in some circumstances, the quality of the modified elements may be reduced from the initial mesh quality"** and recommends smoothing afterward — no formal quality guarantee, consistent with this project's measurement-first stance (do not assume it helps; measure). |
| P1 | INCLUDE | Chen, Gao, Zhu (2016), *An improved hexahedral mesh matching algorithm*, Engineering with Computers 32(2):207-230 | `10.1007/s00366-015-0414-1` — Crossref-confirmed; ABSTRACT_ONLY | Adds a **mesh-quality-evaluation method to prioritize which sheet to extract** during matching (not just topology-first) plus a "partition chord set" for interfaces with internal loops and a local self-intersecting-sheet inflation fix. The quality-driven extraction choice is the missing geometric-guidance half that Ledoux 2010 itself said it lacked (`ledoux2010_sheet_operations.md`: "supplies zero geometric guidance"). |
| P1 | INCLUDE | Zhao, Xu, Xiao, Wu, Gu, Liu, Pang (2024, online 2023), *Bc-hexmatching: an improved hexahedral mesh matching approach based on base-complex structure*, Engineering with Computers 40(4):2209-2226 | `10.1007/s00366-023-01908-6` — Crossref-confirmed; ABSTRACT_ONLY | Most recent (2023/2024) refinement of the matching family: operates on the **base-complex** (singularity/sheet skeleton) rather than raw sheets, then solves a follow-up optimization to place matched-interface vertices. Evidence the "mesh matching" lineage is still an active, improving research line, not a dead 2008 method. |
| P2 | CONTEXT | Kowalski, Ledoux, Staten, Owen (2011), *Fun sheet matching: towards automatic block decomposition for hexahedral meshes*, Engineering with Computers 27(3) | `10.1007/s00366-010-0207-5` — Crossref-confirmed via Semantic Scholar; ABSTRACT_ONLY, 0 recorded citations | Applies sheet-matching to **generate** a block decomposition (structured-block generation), not to repair an existing octree transition mesh — same author group, different (generation-time) problem, kept as lineage context only. |

## B. Direct octree-boundary-transition-region repair (post-hoc, node-level)

| Priority | Decision | Candidate | DOI / access | Why it matters |
|---|---|---|---|---|
| P0 | INCLUDE | Daines, Lobos (2018), *Repairing Octree Boundary Transition Regions Composed of Different Types of Elements*, SCCC 2018 (37th Intl. Conf. Chilean Computer Science Society) | `10.1109/SCCC.2018.8705233` — Crossref-confirmed; IEEE Xplore, ABSTRACT_ONLY (IEEE Xplore blocked our automated fetch with HTTP 418; no open PDF found via ResearchGate/author page) | Title is a near-exact match to this round's search target. Introduces a **node projection technique specifically to repair invalid boundary elements of octree transition regions**, stated to resolve problem elements "without affecting neighboring mesh components" (i.e., locally, not globally). Caveat: this octree variant (8-split) produces **mixed tet/pyramid/prism/hex elements** at the boundary, not pure hex — the repair target is validity of mixed elements, and whether the node-projection mechanism transfers to an all-hex octree-to-hex transition needs the full read to confirm. |
| P1 | CONTEXT | Arenas, Lobos (2018), *Detection and representation of sharp features in octree-based meshes using different types of elements*, SCCC 2018 | `10.1109/SCCC.2018.8705249` — resolves (companion paper, same venue/authors group); ABSTRACT_ONLY | Companion paper from the same lab/venue: sharp-feature detection for the same mixed-element octree family. Relevant only as supporting context for whether Daines & Lobos 2018's repair respects feature/curve provenance — not a repair mechanism itself. |
| P2 | CONTEXT | Lobos et al. (2015), *Mixed-element Octree: a meshing technique toward fast and real-time simulations in biomedical applications*, Int. J. Numer. Meth. Biomed. Engng | `10.1002/cnm.2725` — resolves via PubMed record 26011778 | Earlier paper from the same group establishing the mixed-element octree baseline that Daines & Lobos 2018 repairs; needed to understand what "boundary transition region" means in their specific octree variant before the FULL_READ. |

## C. A posteriori, feature/provenance-constrained boundary correction (direct Ledoux 2010 follow-up)

This directly answers search-strategy item 3: Ledoux 2010 (`ledoux2010_sheet_operations.md`,
already FULL_READ) does have a follow-up that applies its sheet-operations theory to a
*post-hoc, geometry-constrained* boundary-quality pass — found via the **author's own
subsequent paper**, not a citation-graph forward link (round 1's citation-graph search
missed it because it postdates Ledoux 2010 and neither paper cites the other directly in
the snippets available; the connection is via shared authorship and explicit continuity
of the "fundamental mesh" concept from Ledoux 2010 Corollary 2).

| Priority | Decision | Candidate | DOI / access | Why it matters |
|---|---|---|---|---|
| P0 | INCLUDE | Ledoux, Le Goff, Owen, Staten, Weill (2013, publication dated 2012 by Semantic Scholar), *A Constraint-Based System to Ensure the Preservation of Sharp Geometric Features in Hexahedral Meshes*, IMR21 | `10.1007/978-3-642-33573-0_19` — Crossref-confirmed; Springer, ABSTRACT_ONLY (paywalled; no HAL/CEA open deposit found) | Search-engine snippet (not yet FULL_READ) describes it as **"an a posteriori technique based on the notion of the fundamental mesh to improve mesh quality near the boundary, using a constraint problem defined on the topology of the CAD model."** This is precisely the missing geometric/provenance-aware half of Ledoux 2010's sheet-operations theory (Ledoux 2010's own Decision note says it "supplies zero geometric guidance" and defers exactly this to a later paper) and is authored by the same core group (Ledoux, Staten) as the mesh-matching family in section A — the two families likely share vocabulary and may be the same underlying constraint-solving machinery aimed at two different trigger conditions (non-conforming interface vs. boundary feature loss). 11 recorded citations (Semantic Scholar), i.e. not a dead-end paper. |

## D. Adjacent / excluded

| Priority | Decision | Candidate | DOI / access | Why it matters |
|---|---|---|---|---|
| P1 | CONTEXT | Marschner, Palmer, Zhang, Solomon (2020), *Hexahedral Mesh Repair via Sum-of-Squares Relaxation*, Computer Graphics Forum (SGP) 39(5):133-147 | `10.1111/cgf.14074` — Crossref-confirmed; **OPEN** author PDF `dpa1mer.github.io/sos-hex-repair/sos-hex-repair.pdf` (too large for our fetch tool but confirmed open and downloadable; code at `github.com/zoemarschner/SOS-hex`) | A genuinely different (SOS-relaxation, not MSJ-descent) validity-repair technique, but per its GitHub README it targets **Jacobian invalidity/degeneracy**, not skew, and there is no stated octree/transition-region specificity — it reads as another member of the already-refuted "generic untangling objective" family (different math, same failure mode as ECR/HexOpt: our own damage has zero negative volumes already, so a validity-repair tool has nothing to fix). Kept as context, not promoted to a card candidate, without a FULL_READ needed to justify the exclusion — the stated scope (validity, not skew) is enough to rule it out against our specific gap. |
| P2 | EXCLUDE | Tong, Zhang, *Element-Saving Hexahedral 3-Refinement Templates* (arXiv:2512.14862, Dec 2025/Jan 2026) | arXiv, OPEN | Generation-time 3-refinement template scheme (moderately-balanced condition to reduce over-refinement); same family as Elsheikh 2014/Pitzalis 2021/Livesu 2022 in the octree-template lane, not a post-snap repair. No indication (per available abstract) that it addresses already-generated-mesh repair. |
| P2 | EXCLUDE | *MCHex: Marching Cubes Based Adaptive Hexahedral Mesh Generation with Guaranteed Positive Jacobian* (arXiv:2511.02064, Nov 2025) | arXiv, OPEN | Generation-time method (marching-cubes-based, not octree-dual-based); positive-Jacobian-by-construction claim is a generation guarantee, not a post-hoc repair of an existing octree mesh's transition cells. |

## Inaccessible DOI / download queue

No claim above is promoted past ABSTRACT_ONLY until the FULL_READ note exists.

| Candidate | DOI / URL | Needed decision |
|---|---|---|
| Staten, Shepherd, Ledoux, Shimada 2010 (IJNME) | `10.1002/nme.2800` | Confirm the depth-parameter locality mechanism (already read from the patent text) matches the peer-reviewed algorithm description 1:1, and extract the worked examples/quality data (if any) the patent omits. |
| Daines, Lobos 2018 (SCCC) | `10.1109/SCCC.2018.8705233` | Does the node-projection repair generalize from mixed tet/pyramid/prism/hex boundary elements to a pure hex-to-hex transition? What is the "resolved without affecting neighboring components" guarantee formally — is it depth-bounded like mesh matching, or single-node-only? |
| Ledoux, Le Goff, Owen, Staten, Weill 2013 (IMR21) | `10.1007/978-3-642-33573-0_19` | Extract the exact "fundamental mesh" constraint formulation and whether its a posteriori correction is stated to be local/bounded (like mesh matching) or a global constraint-solve pass; does it move boundary vertices or only insert/extract sheets? |
| Chen, Gao, Zhu 2016 (EwC) | `10.1007/s00366-015-0414-1` | Extract the mesh-quality-evaluation criterion used to choose which sheet to extract — this is the candidate geometric-guidance rule to pair with our own skew metric. |
| Zhao et al. 2023/2024 (EwC, Bc-hexmatching) | `10.1007/s00366-023-01908-6` | Confirm whether the base-complex reformulation changes the locality/depth-bound property, and whether its follow-up vertex-position optimization moves boundary nodes (wall-fit-contract risk). |

## Recommended FULL_READ order

1. **US Patent 8,390,620** — already read in full (primary source, not abstract) via
   Google Patents; re-cite directly, no further read needed. Establishes the
   depth-bounded locality property as a *documented, granted, production-lineage*
   mechanism, independent of any journal paywall.
2. **Daines & Lobos 2018** — closest possible title match to "octree boundary
   transition region repair"; resolves whether the node-projection technique is
   hex-transferable.
3. **Staten et al. 2010 (IJNME journal version)** — the full mesh-matching algorithm
   with proofs/examples the patent and IMR17 conference paper compress.
4. **Ledoux et al. 2013 (IMR21, constraint-based fundamental mesh)** — the
   provenance/feature-aware post-hoc half; read together with #3 since both are
   Ledoux/Staten-authored and may share solver machinery.
5. **Chen, Gao, Zhu 2016** — the quality-evaluation-guided sheet-choice rule, the
   most directly reusable "geometric guidance" component for pairing with our own
   OpenFOAM skew metric.
6. **Zhao et al. 2023/2024 (Bc-hexmatching)** — only if #3-5 leave open questions
   about scaling the depth-bounded repair to many disjoint bad-cell clusters at once
   (relevant to the bracket's 7-component/6-patch damage pattern).

## Saturation verdict

**This round closes the literature gap to an actionable shortlist; it does not need a
third broad snowball round.** Three genuinely new mechanism families were found beyond
round 1's three (pre-pass conditioning / hanging-node quality gate / feature-aware sheet
optimizer):

1. **Mesh matching** — local, depth-bounded pillowing/extraction/dicing/column-collapse,
   patented and still being actively improved (2008 -> 2023/2024), with an explicit,
   honestly-stated non-guarantee on quality (matches this project's measurement-first
   discipline rather than contradicting it).
2. **Node-projection repair of octree boundary transition elements** (Daines & Lobos
   2018) — a title-level exact match to the stated gap, pending confirmation it applies
   to pure-hex (not just mixed-element) transitions.
3. **A posteriori, CAD-topology-constrained fundamental-mesh correction** (Ledoux et al.
   2013) — the geometric-guidance complement Ledoux 2010 explicitly said it lacked,
   from the same author group.

Two follow-up searches after finding these three returned no fourth family (only
already-known generation-time template papers), meeting the stated stop rule.

**Do not open an implementation card yet.** All three P0 families above are still
ABSTRACT_ONLY or patent-text-only (one primary source read, the patent; the rest need
the FULL_READ pass in the recommended order). The patent's own stated risk ("quality of
the modified elements may be reduced") means even mesh matching needs the same
measurement discipline this plan has applied to every other candidate (Wave 0 skew map,
HEX-ECR-1/4-style diagnostics) before any code is written — do not assume locality alone
implies quality improvement.

## Source URLs checked

- https://www.sciencedirect.com/science/article/abs/pii/S0965997814000817
- https://ieeexplore.ieee.org/iel7/8698742/8705150/08705233.pdf
- https://ieeexplore.ieee.org/document/8705249
- https://api.semanticscholar.org/graph/v1/paper/DOI:10.1109/sccc.2018.8705233
- https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.advengsoft.2014.05.005/citations
- https://api.semanticscholar.org/graph/v1/paper/DOI:10.1007/978-3-642-33573-0_19
- https://api.semanticscholar.org/graph/v1/paper/DOI:10.1111/cgf.14074
- https://api.semanticscholar.org/graph/v1/paper/DOI:10.1007/s00366-010-0207-5
- https://api.crossref.org/works/10.1002/nme.2800
- https://api.crossref.org/works/10.1007/s00366-015-0414-1
- https://api.crossref.org/works/10.1007/s00366-023-01908-6
- https://api.crossref.org/works/10.1007/978-3-540-87921-3_28
- https://api.crossref.org/works/10.1109/sccc.2018.8705233
- https://api.crossref.org/works/10.1007/978-3-642-33573-0_19
- https://patents.google.com/patent/US8390620B1/en
- https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8390620
- https://www.osti.gov/servlets/purl/1145637
- https://dpa1mer.github.io/sos-hex-repair/sos-hex-repair.pdf
- https://github.com/zoemarschner/SOS-hex
- https://link.springer.com/article/10.1007/s00366-010-0207-5
- https://link.springer.com/chapter/10.1007/978-3-642-33573-0_19
- https://arxiv.org/abs/2512.14862
- https://arxiv.org/html/2511.02064
