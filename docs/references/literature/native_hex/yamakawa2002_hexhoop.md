# Yamakawa & Shimada 2002 - HEXHOOP: Modular Templates for Converting a Hex-Dominant Mesh to an ALL-Hex Mesh

## Bibliographic record

- Soji Yamakawa and Kenji Shimada, *HEXHOOP: Modular Templates for Converting a Hex-Dominant Mesh to an ALL-Hex Mesh*, Engineering with Computers 18: 211-228, 2002 (Springer-Verlag London).
- DOI: `10.1007/s003660200019`
- Local PDF: `docs/references/papers/source/pdf/29_yamakawa_2002_hexhoop.pdf`
- Status: `FULL_READ` (18/18 pages, 2026-07-23).
- Note: the paper is marked **patent pending** (front page footnote). Any direct implementation should check patent status first; the 1995/1998 whisker-weaving patent US5768156 cited in the references shows this group's ecosystem did patent meshing methods.

## Problem and claimed scope

Input: any hex-dominant mesh made of exactly four element types - hex, prism, pyramid, tet - with conforming interfaces (triangles and quadrilaterals). Output: an all-hex mesh, produced fully automatically by per-element template substitution while preserving interface conformity (every interior quad shared by exactly two hexes).

Two previously open sub-problems are solved:

1. **Schneiders' Open Problem** - dice a pyramid whose bottom quad has a rectangular (4-quad) pattern and whose triangular faces have 3-quad patterns. No valid published solution existed (Carboner's attempt leaves interior faces shared by one hex only).
2. **Mixed-pattern hex/prism templates** - a hex or prism whose exterior faces mix *rectangular patterns* (quad split into 4 quads, hex-neighbor compatible) and *triangular patterns* (quad split into 3 quads, matching a diced tet/pyramid/prism triangle side). Mitchell's Geode template solved this only partially: its irregular side faces restrict it to closed shell-like layers.

## Template system read from the paper

### Background dicing templates (known, used as-is)

- hex -> 8 hexes (volume center + 6 face centers + 12 edge midpoints);
- tet -> 4 hexes (volume center + 4 face centers + 6 edge midpoints);
- prism -> 6 hexes (volume center + 5 face centers + 9 edge midpoints).

All three induce the 2D all-quad templates on their faces: triangle -> 3 quads, quad -> 4 quads. The missing piece was the pyramid and the mixed-pattern hex/prism.

### Core + cap modular construction (Sections 3-4)

A hex has six faces, each rectangular- or triangular-patterned: 10 topologically distinct combinations (0-6 triangular faces; 2/3/4 triangular faces each split into two arrangements, Fig. 5). Only two had known solutions. HEXHOOP covers all ten.

- **Core**: an all-hex sub-template with two *wing faces* (which become two opposite exterior faces of the hex) and four *slots*. A `n1 x n2` *rectangular core* is a swept structured grid; a *triangular core* sweeps a triangular pattern across the wings (e.g. `4x4`, `4x2`, `2x2`).
- **Cap**: an all-hex sub-template with T-faces (exterior, patterned rectangular or triangular), B-faces (mate to a core slot), and F-faces (mate to neighboring caps). Built by marching a triangular (or rectangular) pattern through a 4-hex block, joining the two ends into a ring segment, filling the enclosed *pipe* with extra hexes, then deforming. A cap is characterized by `(ns, nf, pattern)`.
- **Hoop**: four caps (three for a prism) are arranged in a ring so that every irregular F-face is matched cap-to-cap *inside* the template and never exposed. This is the key move that removes Geode's shell-only restriction.
- **Assembly conditions** (node-table length matching):
  - Condition 1: `ns` of cap p equals the core's slot subdivision (`n1` for slots 0-1, `n2` for slots 2-3);
  - Condition 2: all four caps share the same `nf`.
  Exterior T-face pattern (rect vs tri) plays no role in assembly - patterns can be mixed freely, which is the paper's central claim.
- **Double hoop core** (Sec. 5.1): the one combination not reachable with standard cores (three triangular + three rectangular faces, Fig. 5(g)) needs a core with one triangular and one rectangular wing, built by collapsing the waist of a previously assembled HEXHOOP template - hence two nested hoops.
- **Prism templates** (Sec. 5.2): triangular wing faces, three-cap hoop, `2x`/`4x` prism cores.

### Pyramid / Schneiders' Open Problem (Sec. 6)

Two constructive solutions, both by assembling deformed HEXHOOP templates plus diced prisms/tets; both give explicit closed-form coordinate transformations (piecewise-linear in |x|, |y|) for the deformation. Validity argument is purely combinatorial: at every attachment step each interior face is shared by exactly two hexes. There is no per-element positive-Jacobian proof for the deformed configuration.

### Post-processing (Sec. 7)

1. **Cap suppression** - two adjacent HEXHOOP templates sharing T-faces can delete the facing cap pair (joins nodes), removing `4*nf*ns + 2*ns` elements; also improves quality since cap elements are the worst.
2. **Volume equalization** - per-node move minimizing `sum_i J_ei(n)^2` (corner Jacobian = local volume), a 3x3 linear solve per node.
3. **Exhaustive method** - per-node 27-candidate stencil search (step = avg incident edge length / 20) maximizing the min *scaled Jacobian* over the node and its three element-corner partners. Used when equalization fails (non-uniform sizes, high aspect ratio).

## Coverage and limits

- **Convertible**: every hex-dominant mesh in the hex/prism/pyramid/tet class with conforming tri/quad interfaces. All ten rect/tri face combinations of a hex; prisms via three-cap hoops; pyramids and tets via dicing plus the derived templates. Unlike Geode, no restriction on input configuration.
- **Not addressed**: general polyhedral cells (our octree transition cells with split faces are NOT in the hex/prism/pyramid/tet class - HEXHOOP does not apply to them as-is); non-conforming/hanging-node interfaces; geometric boundary fidelity (new boundary nodes fall on original faces/edges, so planar patches are preserved, but curved-surface re-projection is never discussed); sharp features are never mentioned in the paper - feature preservation is inherited from, and limited by, the input hex-dominant mesh.
- **Cell-count blowup** (Sec. 9, explicit numbers): with `n1 = n2 = nf = 4` everywhere, the final all-hex mesh has ~**60x** the input element count. `nf >= 4` is *mandatory* wherever a tet is adjacent to a quad face (cap structure requirement), so the hypothetical `nf = 2` (<8x) case is unreachable in general; per-element optimal `(n1, n2)` selection is left as future work.
- **Quality after conversion** (Sec. 8): all examples pass a topological validity check (no gaps/overlaps). Aspect-ratio histograms peak sharply at 1.0. Scaled-Jacobian histograms are **bimodal, ~0.4 and ~1.0**: the 0.4 population comes from template elements inside converted non-hex elements. Evidence: an 87%-non-hex input shows a clear 0.4 peak; a 27%-non-hex input shows almost none. Example scale: 11 input elements (3 hex + 1 prism + 4 pyramids + 3 tets) -> 542 hexes (~49x).
- **No inversion-free guarantee**: validity claims are topological plus experimental. Smoothing (Sec. 7.2-7.3) *improves* the min Jacobian; nothing bounds it above zero, and distorted input elements provably produce distorted template hexes (Sec. 9).

## AutoTessell applicability

Context: native_hex "hex-dominant honesty" lane. Our adaptive octree path writes conforming polyhedral transition cells (coarse cube faces split into sub-quads, written via the generic polyhedral writer, `core/generator/native_hex/mesher.py:1557`), which the evidence matrix rules NOT proven all-hex.

1. **HEXHOOP does not solve our transition problem.** Our transition cells are polyhedra with >6 faces from hanging-node face splits - outside HEXHOOP's hex/prism/pyramid/tet input class. Converting them would first require re-expressing transitions as pyramid/tet mixtures (e.g. Schneiders-style grid conversion), then paying the ~49-60x template multiplication. Pitzalis et al. 2021 (`10.1145/3478513.3480508`) install conforming **all-hex** templates directly on weakly balanced adaptive grids with modest cell increase and open-source code, and Livesu et al. 2022 (`10.1145/3494456`) provide the accompanying theory of which grids admit pure-hex conversion. For grid/octree transitions Pitzalis 2021 is **strictly better** than the HEXHOOP route: native problem class, far lower multiplication, no 0.4-Jacobian cap population, no patent flag.
2. **Where HEXHOOP is genuinely relevant**: if the engine ever emits a true hex/prism/pyramid/tet hybrid - e.g. the BL path inserting prisms under hex walls (`core/generator/native_hex/mesher.py:434`) - and an all-hex product claim is wanted, HEXHOOP is the classical existence proof that such a conversion is always possible, and its cost numbers (60x, bimodal 0.4 Jacobians) are the honest price tag to quote for rejecting that route.
3. **Reusable pieces regardless of verdict**: the scaled-Jacobian corner metric and the two cheap smoothers (volume equalization 3x3 solve; 27-stencil min-scaled-Jacobian ascent) are engine-agnostic and could back a post-write quality pass; the paper's bimodal-histogram diagnostic is a good template-quality fingerprint for any conversion we might evaluate.
4. **Honesty lane support**: the paper's own experimental framing (validity checked by a utility program; quality reported as full histograms split by element provenance) is exactly the census-first reporting HEX-HD-1 demands - report measured cell types, never infer all-hex from the method name.

### Verdict: **reference-only**

Do not implement HEXHOOP. Reasons: (a) wrong input class for our octree transitions; (b) 49-60x cell multiplication with a systematic ~0.4 scaled-Jacobian population is unacceptable against our quality gates; (c) patent-pending flag; (d) Pitzalis 2021 + Livesu 2022 dominate it for the grid-based case we actually have. Keep it as the citation for (i) why hex-dominant -> all-hex conversion is not a free lunch and (ii) the pyramid-conformity background when BL prisms meet hex cells.

## Falsifiable implementation card

### HEX-ALLHEX-1 - conversion-cost gate for any future all-hex conversion pass

- If an all-hex conversion of hex-dominant/hybrid output is ever proposed, it must be benchmarked against this paper's numbers before adoption.
- Pass: on a representative adaptive-cube and BL-on-cube case, the candidate reports (1) cell multiplication factor, (2) min and histogram of scaled Jacobian split by provenance (hex-derived vs non-hex-derived), (3) a topological conformity check (every interior face shared by exactly two cells). Adoption requires multiplication < 8x and no secondary Jacobian mode below 0.5 - both bounds HEXHOOP itself cannot meet by its own account (60x, 0.4 mode).
- Stop rule: a conversion pass that only reports "all-hex: yes" without the provenance-split histogram is rejected under the hex-dominant honesty rule.

## Snowball references (<=5)

1. Mitchell 1998, *The all-hex geode-template for conforming a diced tetrahedral mesh to any diced hexahedral mesh*, 7th IMR, 295-305 - the direct predecessor HEXHOOP generalizes; explains the shell-only restriction.
2. Schneiders 1996, *A grid-based algorithm for the generation of hexahedral element meshes*, EWC 12, 168-177 - grid overlay hex meshing; origin of the boundary-quality criticism our octree path must also answer.
3. Owen, Canann, Saigal 1997, *Pyramid elements for maintaining tetrahedra to hexahedra conformability*, ASME AMD-220, 123-129 - why pyramids exist at hex/tet interfaces; relevant to BL prism/hex mixing.
4. Owen & Saigal 2000, *H-Morph: an indirect approach to advancing front hex meshing*, IJNME 49, 289-312 - the hex-dominant generator class HEXHOOP consumes.
5. Yamakawa & Shimada 2002, *Hex-dominant mesh generation with directionality control via packing rectangular solid cells*, GMP 2002, 107-118 - the authors' companion hex-dominant generator used for the paper's inputs.
