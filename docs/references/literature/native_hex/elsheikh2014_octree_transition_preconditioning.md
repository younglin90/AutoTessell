# Elsheikh 2014 - A Consistent Octree Hanging Node Elimination Algorithm for Hexahedral Mesh Generation

## Bibliographic record

- Ahmed H. Elsheikh, Mustafa Elsheikh, *A consistent octree hanging node elimination
  algorithm for hexahedral mesh generation*, Advances in Engineering Software 75
  (2014) 86-100.
- DOI: `10.1016/j.advengsoft.2014.05.005`
- Status: `FULL_READ` (15/15 pages, 2026-07-25).
- Note: the source file is a 15-page Elsevier journal article, not the 87-page
  document implied by the filename/briefing. `pdfinfo`/PyMuPDF metadata confirm
  `page_count=15`, title, author, and the journal page range (86-100) matching the
  DOI. No pages were skipped.

## Problem and claimed scope

Octree-based hex mesh generation produces hanging nodes wherever a coarse cell is
adjacent to a more-refined region. The paper's stated goal is a **template-based**
algorithm that (a) eliminates every hanging node, (b) keeps the mesh all-hexahedral,
(c) avoids the excessive/uncontrolled refinement that plain "solid refine anything
unmatched" schemes (Schneiders et al.) fall into at concave refinement interfaces,
and (d) stays simpler to implement than sheet-based pillowing (Schneiders 2000;
Tchon et al. 2004; Zhang, Liang, Xu 2013 = ref. [22]). It explicitly targets **3D
concave refinement regions** (an element with 3+ refined neighbors meeting at a
vertex/edge) as the hard case existing template libraries handle poorly.

## Algorithm read from the paper

The algorithm runs **during octree-to-hex construction, before any boundary
projection/snapping** — it operates purely on the *refinement field* (which octree
leaves are marked "refine") and the resulting *hanging-node topology*, not on an
already-generated hex mesh with measured cell-quality damage.

1. **Sibling refinement** (Algorithm 2, a topological pre-pass): if any one child of
   an octree parent is marked for refinement, mark *all* its siblings for
   refinement too. This alone collapses the number of distinct "edges-with-hanging-
   nodes" incident patterns per hex from 144 (all 2-colorings of 12 edges modulo
   cube symmetry) down to **7 canonical cases** (1E, 2E, 3E, 4E, 5E, 7E, 9E; Fig. 6).
   It also fixes staircase-shaped refinement fields that would otherwise force
   asymmetric, order-dependent template insertion (Fig. 17/18).
2. **Gap filling** (Algorithm 3): recursively refine any coarse band that is
   narrowly sandwiched between two refined regions (identified via the level1
   decoupling-node pattern on a parent's central child, Fig. 20), repeated until no
   gaps remain. Prevents inserting non-regular/low-quality templates into gaps that
   are too narrow to accommodate a transition layer.
3. **Decoupling-node marking and analysis** (Algorithm 1): after 1-2, classify
   nodes as `level0` (co-dimension-3, i.e. true 3D concave interaction — patterns
   3E/5E/9E, Fig. 9) or `level1` (2D concave region embedded in 3D — patterns
   2E/7E, Fig. 10). `level0` takes precedence over `level1`; a node can be both.
   Loop over every hex; any hex whose incident decoupling nodes do **not** match
   one of the accepted local configurations (Fig. 11) is marked for full/solid
   refinement, then gap filling is re-run and the loop repeats until convergence.
4. **Decoupling templates** (Fig. 3): a vertex template and an edge template, each
   inserting a closed loop **in the mesh dual** around the node (or around a
   connected run of `level1` edge-nodes) — this is topological surgery that changes
   *element connectivity/count* locally but adds **no new hanging nodes**. Applied
   to all `level0` nodes first, then to remaining `level1` node/edge cases.
5. **Refinement templates** (Fig. 4, essentially Schneiders et al.'s edge/face/solid
   templates): applied last, now that step 3-4 guarantee every remaining hex
   matches one of only two patterns (1E, 4E) that these templates can resolve.
6. Quality is improved *afterward*, out of scope of the topological algorithm
   proper: 5 Laplacian smoothing iterations + Mesquite's feasible-Newton shape
   improvement wrapper (mean-ratio metric, ℓ2 objective), measured with the Verdict
   scaled-Jacobian metric.

## Assumptions, guarantees, limits

- All templates map hex-to-hex; the mesh stays strictly all-hexahedral throughout
  (no polyhedra are ever introduced) — this is a structural property of the
  template set, not something separately proven.
- No formal proof of positive-Jacobian validity or of convergence of the decoupling
  loop is given. Validity evidence is empirical: scaled-Jacobian histograms on 3
  test cases (2D-embedded concave field, 3D concave field, plus a mechanical-jack
  and a tooth STL) after Laplacian + Mesquite smoothing — minimum scaled Jacobian
  0.32 (2D-embedded case, vs. 0.28 for Ito et al. 2009's method on the same field)
  and 0.316 (3D concave case). **These are post-smoothing numbers, not raw
  as-generated transition-cell quality** — the paper does not report what quality
  the templates alone (pre-smoothing) achieve.
- Explicitly validated for **one level of refinement difference** only. The
  authors flag multi-level interaction as future work: when refinement levels are
  close together, the Gap Filling step can over-refine trying to regularize the
  field, and they were (at time of writing) investigating a pillowing-style
  decoupling layer instead of full refinement for that case (unresolved in this
  paper).
- Cases that don't match Fig. 11's decoupling-node configurations fall back to full
  (solid) refinement — same fallback Schneiders et al. use, just triggered far less
  often thanks to steps 1-3.
- No boundary/geometry handling in this paper: feature snapping, sharp-edge
  recovery, and surface projection are explicitly deferred to other work (cites
  Maréchal 2009 directly, ref. [6]).
- Symmetric refinement fields produce symmetric output meshes — an explicit
  advantage over directional/order-dependent methods (Parrish et al. 2008; Ito
  et al. 2009), which the paper demonstrates produce asymmetric, order-dependent
  results on the same 2D concave test field (Fig. 2).

## Relationship to Zhang 2013 / Pitzalis 2021 / Livesu 2022 (template/pairing lineage)

This is **not a post-processing complement** to the already-read template/pairing
papers — it is a direct **alternative generation-time mechanism for the same
problem** (constructing valid octree-to-hex transition topology), pitched
specifically against Zhang, Liang, Xu 2013 (cited as ref. [22] and discussed by
name in both the Introduction and Conclusions). Zhang 2013's fix for the same
concave-interaction problem is a **pillowing layer** inserted at the transition;
Elsheikh 2014's fix is the **decoupling-template** insertion described above. The
paper's own framing: "this preconditioning is similar to pillowing at transition
layers used in [22]. However, our method is template-based which is arguably
easier to implement than pillowing." So relative to Zhang/Pitzalis/Livesu, this
paper sits at the *same* stage of the pipeline (primal transition-topology
construction from an octree), offering a template-only alternative to sheet-based
pillowing — it is a substitute mechanism, not a downstream quality pass layered on
top of theirs.

## AutoTessell code comparison

Relevant code:

- `core/generator/native_hex/octree.py:1109` (`_balance_octree_2to1_nodes`): BFS
  2:1 level balance — analogous to a *prerequisite* the paper also assumes, but
  not sibling refinement.
- `core/generator/native_hex/octree.py:1053` (`_add_buffer_layer_between_levels`):
  upgrades one ring of level-(L-2) cells adjacent to a level-(L-1)/level-L
  boundary to L-1, i.e. a fixed-width geometric buffer band (snappyHexMesh
  `nBufferCellsNoExtrude` equivalent). This is a *different* mechanism from
  sibling refinement/gap filling: it thickens the transition band uniformly by
  distance, it does not look at edge-marking patterns or concave-node topology.
- `core/generator/native_hex/octree.py:125` ("Conformal transition face 생성"):
  builds coarse/fine boundary faces directly (multi-level sub-quad split per the
  Maréchal note's finding), i.e. transition cells are still generic polyhedra with
  more than six faces, not hex-to-hex templates.
- No occurrence of sibling-refinement, decoupling-node, or gap-filling concepts
  anywhere in `core/generator/native_hex/` (grep for
  `hanging|sibling|decoupl|transition|gap_fill` only matches comments/labels, no
  matching algorithm).

### Present matches

- 2:1 balance and an optional geometric buffer band both exist and serve a similar
  smoothing-the-transition-band intent.
- Post-generation mesh quality is measured (non-orthogonality, skewness, aspect
  ratio, negative volume) — comparable in spirit to the paper's post-hoc
  Laplacian+Mesquite+scaled-Jacobian evaluation, though native_hex has no
  smoothing/shape-improvement pass equivalent to Mesquite's feasible-Newton step.

### Material gaps

- **No sibling-refinement pre-pass.** native_hex's octree can produce exactly the
  144-case combinatorial mess (or worse, a staircase pattern per Fig. 17) that
  this paper's step 1 exists to eliminate before any transition cell is built.
- **No decoupling-node classification or decoupling templates.** There is no
  concept of `level0`/`level1` concave-interaction nodes, no vertex/edge dual-loop
  insertion, and no distinction between "this hanging-node configuration has a
  known-good template" vs. "fall back to full refinement." Current code instead
  always builds a generic multi-face polyhedron at any coarse/fine boundary,
  regardless of whether the local configuration is a benign 1E/4E case or a genuine
  3D concave interaction.
- **No gap-filling pass** for narrow coarse bands between two refined regions —
  the geometric buffer-layer pass (`_add_buffer_layer_between_levels`) thickens
  transition width by distance, but does not detect/eliminate a coarse band that
  is topologically squeezed between refined regions on the specific
  central-child pattern the paper checks (Fig. 20).
- The algorithm's own conclusion (Fig. 30, the "mechanical jack tip" discussion)
  describes exactly the geometry class our own damage census is seeing: a single
  layer of coarse cells surrounded by refined regions, where naive hanging-node
  elimination would split that layer into 3 sub-layers of irregular quality unless
  the field is preconditioned first. This maps directly onto the singleton-vs-
  cluster damage split (see below).

## Applicability to the observed damage pattern

This paper is upstream of boundary snapping, not a post-snap corrective pass — it
constructs the transition topology as part of generation, before the surface is
recovered. It therefore cannot be inserted as-is into a "post-snap quality lane."
What it *does* give us is a plausible root-cause account for the damage-topology
census (isolated singleton bad faces for cylinder/sphere/gear vs. 7 connected
components across 6 patches for bracket):

- Primitive shapes (cylinder/sphere/gear) mostly generate **isolated,
  non-interacting** hanging-node patterns from curvature-driven local refinement —
  these correspond to the paper's simple 1E/4E/2E-style single-node cases, which
  even a naive polyhedron-based transition can usually get through without
  cascading damage, so surviving bad faces stay singletons.
- The bracket has **multiple concave feature interactions** (fillets, corner
  junctions, holes close to each other) — exactly the `level0`/3D-concave-region
  signature (Fig. 8/Fig. 30) the paper singles out as the case existing
  algorithms handle worst, producing connected clusters of poor-quality cells
  precisely because several transition regions interact rather than staying
  independent. That the bracket's damage is multi-patch and multi-component while
  the primitives' is not is consistent with this classification, though it is a
  plausibility argument from the paper's own failure analysis, not something we
  measured directly against our octree.

Because the mechanism is a generation-time topology fix, not a repair pass, its
AutoTessell application is a candidate **redesign of the transition-cell
construction step itself**, positioned as an alternative to (or an upgrade of) the
Maréchal all-hex dual construction already tracked as `HEX-OCT-2` in
`marechal2009_octree_all_hex.md` — not a new post-snap quality-repair mechanism to
sit alongside the (empirically refuted) ECR/HexOpt untangling pass.

## Falsifiable implementation cards

### HEX-TRANS-1 - sibling refinement pre-pass

- Before building any transition face/cell, force full refinement of all 26 (or 7,
  for an octree-of-8) siblings whenever one sibling is marked refined, iterated to
  a fixed point.
- Pass: on the current bracket/cylinder/sphere/gear octree refinement fields,
  recount the distinct edge-hanging-node patterns per boundary cell; expect
  collapse toward the paper's 7 canonical cases (measure before/after, do not
  assume the reduction — the paper's counting argument assumes cube symmetry that
  a non-cubic octant grid may not fully preserve).
- Expected current result: some fraction of transition cells expose patterns
  outside the 7-case set today; this test quantifies "how far from conditioned"
  the current octree is before any decoupling work is attempted.

### HEX-TRANS-2 - decoupling-node classification and templates

- Implement the `level0`/`level1` node marking (Figs. 9-10-11) and the vertex/edge
  decoupling templates (Fig. 3) as a topology-editing pass on the octree hanging-
  node graph, applied after HEX-TRANS-1 and before any hex-generation/polyhedron
  fallback.
- Pass: re-run the bracket damage census after the pass; expect the 7-connected-
  component/6-patch signature to shrink (fewer, smaller connected clusters) since
  decoupling should stop 3D concave regions from cascading into merged transition
  polyhedra. Stop rule: if cluster count/size does not improve on the bracket case,
  the singleton-vs-cluster hypothesis above is falsified and this card should not
  be advertised as the bracket fix.
- This card is generation-time and structural — it is not compatible with being
  bolted onto the existing "split coarse face into sub-quads, write as generic
  polyhedron" code path; it requires the transition region to be built from actual
  hex-to-hex templates (shared prerequisite with `HEX-OCT-2`).

### HEX-TRANS-3 - gap filling for squeezed coarse bands

- Detect the central-child decoupling-node pattern (Fig. 20) that marks a coarse
  band as narrowly squeezed between two refined regions; refine that band
  recursively until no such pattern remains, before transition-cell construction.
- Pass: construct a synthetic "thin coarse band between two fine bands" octree
  fixture (analogous to Fig. 19/mechanical-jack-tip, Fig. 30); confirm the pass
  eliminates the squeezed band without infinite recursion, and that the resulting
  transition cells pass the existing quality checker at a higher rate than the
  current `_add_buffer_layer_between_levels` band-thickening approach on the same
  fixture.

## Decision

Read for the sibling-refinement / gap-filling / decoupling-template lineage as an
**alternative generation-time mechanism** for octree-to-hex transition topology,
positioned against Zhang 2013's pillowing approach, not as a post-snap
quality-repair technique. Do not cite it as a fix compatible with the current
post-snap quality lane without first re-architecting transition-cell construction
per `HEX-TRANS-2`/`HEX-OCT-2`; its damage-topology account (isolated singletons vs.
multi-component clusters) is a plausible but unverified explanation for the
bracket-vs-primitives split observed in our own census.
