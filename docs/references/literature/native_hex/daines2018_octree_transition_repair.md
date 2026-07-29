# Daines & Lobos 2018 - Repairing Octree Boundary Transition Regions Composed of Different Types of Elements

## Bibliographic record

- Esteban Daines, Claudio Lobos, *Repairing Octree Boundary Transition Regions Composed
  of Different Types of Elements*, 37th International Conference of the Chilean Computer
  Science Society (SCCC), 2018.
- DOI: `10.1109/SCCC.2018.8705233` (Crossref-confirmed, title/author/venue match exact).
- Title and year verified directly from the PDF's own header/footer (`978-1-5386-9233-2/18/... ©2018 IEEE`),
  not just from the citation record.
- Status: `FULL_READ` (8/8 pages of the retrieved PDF, 2026-07-25). Note: the task brief
  that requested this note cited "11 pages"; the PDF as delivered to this read is an
  8-page two-column IEEE paper (title page through References, no appendix). All visible
  text, all 16 figures, all 6 tables, and the full reference list were read; the page-count
  discrepancy is noted for the record but does not indicate any missing content — the
  paper ends at "References" with no further material.

## Problem and claimed scope

Two octree-to-volume-mesh families exist: 27-split octrees can produce a **pure-hexahedral**
transition (cited to Schneiders 1996 / Zhang & Bajaj 2006 / Ito, Shih & Soni 2009), while
**8-split** octrees can only resolve fine/coarse transitions by introducing **mixed
elements** (tetrahedra, quadrilateral-base pyramids, wedges, hexahedra) via one of 325
enumerated transition patterns (Gonzalez & Lobos 2014 tech report). This paper addresses
only the 8-split, mixed-element family, built on the authors' own prior mixed-element
octree mesher (Lobos & Gonzalez 2015, `10.1002/cnm.2725` — already in our corpus per the
round-2 gap-search doc).

The specific failure mode: an octant that sits at a **fine/coarse transition and also at
the domain boundary** must have both a transition pattern and a surface pattern applied
to it. Applying a surface pattern to an octant already split into transition-pattern
elements can leave inverted or near-flat elements. The paper states this affects **less
than 0.01% of total elements**, but "if one invalid element exists in the mesh, a
simulation cannot be performed" — i.e., the practical bar is zero invalid elements, not a
statistical quality threshold. This 0.01% framing is a close topological analogue of our
own damage census (isolated singleton bad faces on cylinder/sphere/gear).

## Mechanism (read from Figs. 5, 11, 12 and Section IV)

The **baseline** generation algorithm (Fig. 5, pre-existing, not this paper's
contribution) is:
1. Build the balanced octree, apply transition patterns.
2. Find boundary nodes; project *inside-and-close* nodes onto Ω (the surface).
3. Apply surface patterns (this is where the invalid elements above can appear).
4. Find boundary nodes again; project any node still *outside* Ω onto Ω.

The paper's contribution (Fig. 12, `GENERATE_MESH` with repair) inserts an **outer
iteration loop around the entire boundary-treatment stage**, not a standalone post-hoc
pass on a finished mesh:
- `GET_LABELED_NODES(mesh, T)` (Fig. 11) scans **every element in the whole mesh** and
  collects the nodes of any element whose quality is below threshold `T` (measured with
  `J_ENS`, defined below). This is a single global sweep, not a per-cluster/per-component
  operation.
- Each iteration: reset `mesh <- imesh` (the octree + transition-pattern state, *before*
  any prior projection), then re-run the boundary-node projection step — but this time
  also force-project **every node ever labeled bad in a previous iteration**, in addition
  to the original inside-and-close criterion. Then re-apply surface patterns, re-run the
  outside-node projection, and re-scan for newly-bad elements.
- Stop when `GET_LABELED_NODES` returns empty (success) or the iteration cap `I` is hit
  (failure, returns `null`). The paper recommends **I = 3** based on empirical failure
  patterns (see Guarantees below).

**Quality metric used to drive labeling:** the paper cannot use a single Scaled Jacobian
(`J_S`) across element types because the "perfect element" is only orthogonal for the
hexahedron; tetrahedron/pyramid/wedge need a per-type normalization constant `k^e`
(`k^T = sqrt(2)/2`, `k^P = sqrt(6)/3`, `k^W = sqrt(3)/2`, derived by inscribing each shape
in a cone circumscribed on a regular tetrahedron). This yields the **Element Normalized
Scaled Jacobian (`J_ENS`)**, with the same interval semantics as `J_S`: `<0` inverted,
`[0, 0.03)` invalid, `[0.03, 0.2)` questionable, `[0.2, 1]` good. For a pure hexahedron
`k^e = 1` and `J_ENS` degenerates back to plain `J_S` — the metric itself is not
mixed-element-specific, only its normalization constants are.

## Guarantees (explicit, from Section VII / Tables I-VI)

No formal proof of convergence or validity is offered anywhere in the paper — this is an
empirical, iterate-and-measure technique, consistent with this project's own
measurement-first discipline.

- At the strict "eliminate invalid elements" threshold (`T = 0.03`, matching the
  inverted/invalid boundary the paper itself defines), **36 of 37 test instances
  succeeded** (only `cortex_5_6` failed, hitting the 5-iteration cap with elements still
  below 0).
- At a looser threshold (`T = 0.05`, i.e., also chasing "questionable" elements up toward
  "good"), **more instances failed**, and several successful cases showed **measurable
  degradation of hexahedra/wedge aspect ratio** (Table III: e.g. `cortex_5_3` hex AR
  stays flat but wedge AR drops from 0.316 to 0.189; `cortex_5_6` hex AR drops from 0.354
  to 0.151). The paper's own conclusion: **do not use this technique for general quality
  improvement** — "it can drastically affect adjacent elements of acceptable quality." It
  is a validity-repair tool, not a quality-improvement tool.
- Recommended cap of **I = 3 iterations**: 2nd iteration projects the originally-invalid
  elements' nodes, 3rd iteration projects the neighbors those projections newly damaged;
  beyond that, damage is observed to propagate rather than converge ("could exponentially
  propagate the deformations"). This is a directly reusable, falsifiable stopping rule.
- Runtime: repair cost is bounded — time-per-iteration is ~30-82% of the original
  meshing runtime (Table I, `T/it` column), so a 3-iteration repair costs at most ~2-2.5x
  the base generation time, not a large multiple.
- No claim about geometry/CAD-feature preservation quality beyond the AR measurement; no
  Hausdorff-distance or surface-deviation metric is reported (Fig. 16 is a qualitative
  before/after picture only, not a numeric result).

## Experiments

Two organic, single-component, smooth-boundary biomedical domains: liver and brain
cortex (Fig. 13), each with 5-6 hand-picked Regions-Of-Interest (Figs. 14-15) used to
force fine/coarse transitions at the boundary via a 3-level RL scheme (`region > surface >
all`, differing by exactly 1 level each). 37 total instances (7 RL/ROI combinations shown
in the paper's own tables x multiple domains/RLs referenced as "similar results" but not
tabulated). No sharp-feature, multi-component, or multi-patch domain is tested — both
domains are single watertight organic blobs. The companion paper in the same venue
(Arenas & Lobos 2018, sharp-feature detection) is explicitly a *different, uncombined*
mechanism, not evaluated together with this repair technique here.

## Limitations (as stated or directly inferable)

- **Element family mismatch with our engine.** This paper's whole problem exists only
  because the 8-split octree produces mixed tet/pyramid/wedge/hex elements at
  transitions. AutoTessell's `native_hex` targets a Maréchal-style **pure-hex dual**
  construction (`marechal2009_octree_all_hex.md`) — a 27-split-family topology by the
  taxonomy this paper itself draws. The paper does **not** test or claim its repair
  applies to a pure-hex dual mesh; it is demonstrated exclusively on mixed elements.
- **Not tested on sharp/concave-corner geometry.** The intro flags concave regions as the
  highest-risk zone for invalid elements, but the two test domains (liver, cortex) are
  smooth organic shapes with no sharp edges — the exact geometry class our bracket
  shape (with sharp corners) would stress is absent from the evaluation.
- **Not tested on multi-component/multi-patch damage.** Both domains are single
  connected components. The mechanism's node-labeling step is architecturally
  whole-mesh (not per-component), so it does not *require* single-component input, but
  there is zero empirical evidence at the bracket's damage scale (7 connected components
  across 6 patches).
- **Requires generator-internal state, not a standalone post-process on a finished
  mesh.** Every iteration resets to the pre-projection octree state (`imesh`) and
  re-runs `APPLY_SURFACE_PATTERNS` plus boundary reclassification against Ω. This needs
  the original surface Ω, the boundary-octant classification logic, and the
  transition/surface pattern application code all available at repair time — it is a
  loop wrapped around the mesher's own boundary stage, not a checker-and-fixer CLI stage
  that could run on an already-written OpenFOAM polyMesh.
- Runtime and mesh-quality behavior "of this approach" (raising the ROI to encompass all
  of Ω as a last resort) is explicitly flagged by the authors as needing "further study" —
  i.e., even the authors do not consider the paper's own fallback path fully
  characterized.

## AutoTessell applicability

**Direct code port: no.** Our native_hex boundary-transition damage lives in a pure-hex
(or hex-dominant polyhedral) mesh, not the mixed tet/pyramid/wedge/hex elements this
paper's `J_ENS` metric and surface-pattern collision are defined over. The verdict
requested by the round-2 gap-search doc is: **confirmed, not refuted** — this paper does
not demonstrate applicability to a pure-hex octree-to-hex transition, only to the 8-split
mixed-element family.

**Locality: partially matches, but is not depth-bounded.** The repair is local in that it
only touches boundary octants and does not regenerate the whole mesh, matching our need
better than a generic MSJ untangler. But unlike the mesh-matching family's explicit depth
parameter, this method's footprint is *iteration-bounded* (recommended cap 3), not
*geometrically bounded* — the set of affected nodes can grow each iteration as
newly-invalidated neighbors get added to the must-project set. For our own
cylinder/sphere/gear singleton-face damage this distinction likely does not matter (one
or two iterations should suffice, matching most of the paper's own 2-iteration
successes). For the bracket's 7-component/6-patch damage it matters more, since nothing
in the paper measures whether iteration count scales with the number of disjoint bad-cell
clusters.

**Portable pattern (the real transferable value), 2 candidate cards plus a measurement
protocol:**

### HEX-DAINES-1 - bounded iterative boundary re-snap loop

- Adapt the *loop structure*, not the mixed-element math: after wall-fit-snap, label all
  nodes belonging to cells below our OpenFOAM skew/negative-Jacobian gate; re-run the
  boundary-snap step restricted to those labeled nodes plus any newly-implicated
  neighbors; recompute quality; repeat. Use plain scaled-Jacobian (`J_S`, `k^e = 1`) since
  our cells are hex, not the mixed-type `J_ENS` normalization.
- Stop rule ported directly from the paper's empirical finding: **cap at 3 iterations**;
  do not iterate further hoping for convergence, since the paper measured propagating
  damage rather than convergence beyond that point.
- Pass: cylinder/sphere/gear singleton-bad-face cases resolve in <=2 iterations with zero
  new bad cells elsewhere (mirrors the paper's own 2-iteration success mode in Table I);
  report iteration count and residual invalid-cell count per run, exactly like the
  paper's Table I/II format.

### HEX-DAINES-2 - measure collateral damage to good neighbors, not just bad-cell resolution rate

- The paper's real methodological contribution is Tables III-V: it measures **aspect-ratio
  degradation of previously-good neighbor elements**, not just whether the originally-bad
  cells got fixed. Our current bad-cell census tracks only the damaged cells themselves.
- Adopt a two-tier threshold discipline mirroring the paper's `T=0.03` vs `T=0.05` runs:
  one strict "must fix" gate (paper's invalid cutoff) and a second, looser gate used only
  to *measure* whether chasing extra quality damages neighbors (paper's finding: yes, it
  does, in most successful `T=0.05` cases).
- Pass: run any HEX-DAINES-1-style repair at both thresholds on our 4 shapes and report
  before/after skew of the cells adjacent to the repair, not just the repaired cells —
  a repair that "succeeds" by this paper's narrow definition but silently degrades
  neighbors would be a false positive under our own measurement-first rule.

### HEX-DAINES-3 - whole-mesh single-pass labeling for multi-component damage (bracket-relevant, unverified)

- Port the architectural choice that `GET_LABELED_NODES` scans the *entire* mesh in one
  pass regardless of how many disconnected bad-cell clusters exist, rather than looping
  per connected component. Applied to the bracket's 7-component/6-patch damage, this
  means processing all seven clusters under the **same shared 3-iteration budget**, not
  3 iterations multiplied per component (which would multiply the propagating-damage risk
  the paper itself warns about).
- Stop rule / explicit non-claim: this card is **not validated by this source** — the
  paper's own test domains are single-component smooth organic shapes, the opposite of
  the bracket's multi-component sharp-corner damage. Do not assume the 3-iteration cap or
  the 97% (36/37) success rate transfers to that geometry class; measure it separately
  before trusting it.

## Snowball references (from this paper's own bibliography, most relevant to the gap)

1. Lobos & Gonzalez (2015), *Mixed-element octree: a meshing technique toward fast and
   real-time simulations in biomedical applications*, IJNME Biomedical Engng 31(12).
   `10.1002/cnm.2725` — the base 8-split mixed-element generator this paper repairs;
   already in our corpus (round-2 gap-search table B).
2. Gonzalez & Lobos (2014), *A set of mixed-element transition patterns for adaptive 3d
   meshing*, UTFSM Tech. Rep. 2014/01 — defines the 325 enumerated transition patterns
   referenced in Section I; needed to understand what "transition pattern" concretely
   produces before any attempt to translate the repair logic.
3. Lobos (2013), *A set of mixed-elements patterns for domain boundary approximation in
   hexahedral meshes*, MMVR20, Studies in Health Technology and Informatics 184 — defines
   the "surface pattern" step (Fig. 5, line 8) whose collision with transition patterns is
   the root cause this paper repairs.
4. Lobos (2015), *Towards a unified measurement of quality for mixed-elements*, UTFSM
   Tech. Rep. 2015/01 — source of the `J_ENS` metric and the per-element-type
   normalization constants `k^e` used throughout Section II.
5. Bucki, Lobos, Payan, Hitschfeld (2011), *Jacobian-based repair method for finite
   element meshes after registration*, Engineering with Computers 27(3):285-297 — cited
   by the authors themselves (ref [15]) as an alternative node-relaxation-based quality
   technique that, unlike this paper's approach, does not remove flat/invalid elements
   and instead achieves validity via larger neighbor distortion — a useful contrast case
   for any future "which repair strategy trades off what" comparison.

## Decision

Do not port this paper's element-quality metric or mixed-element mechanism directly —
our engine's transition cells are pure-hex/hex-dominant, not the tet/pyramid/wedge/hex
mix this paper's `J_ENS` and surface-pattern collision are defined over, so the round-2
caveat is confirmed rather than resolved. Reuse the *iterative bounded re-snap with a
3-iteration cap* pattern (HEX-DAINES-1) and the *measure collateral neighbor damage, not
just resolution rate* discipline (HEX-DAINES-2) as directly transferable, falsifiable
protocol elements. Treat multi-component applicability (HEX-DAINES-3, relevant to the
bracket) as an open, unmeasured question this source does not answer — the paper's own
test domains are single-component and smooth, the opposite of the bracket's damage
profile.
