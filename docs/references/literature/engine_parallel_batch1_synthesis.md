# Native Meshing Engines — Parallel Literature Batch 1 Synthesis

Date: 2026-07-23. Scope: native surface quad/quad-dominant, tetrahedral,
hexahedral/hex-dominant, and general polyhedral engines. Four tracks ran in
parallel. This batch fully read 13 primary papers (230 pages total) and compared
their algorithms and guarantees directly with the current code. No selected
paper was inaccessible.

## Evidence and engine verdicts

| Engine | Full-read evidence | Current implementation truth | Architecture decision | First hard milestone |
| --- | --- | --- | --- | --- |
| Surface quad | Alliez 2003; Jakob 2015; Huang 2018 | deterministic, guarded adjacent-triangle pair merger; not an independent quadrangulator | metric + 4-RoSy + 4-PoSy + transactional extraction; pair merger remains fallback | field/singularity ledger and conforming extraction passing topology/fidelity gates |
| Volume tet | Shewchuk 1998; Si 2015; Hu et al. 2020 | mixed heuristics do not inherit TetGen or fTetWild guarantees | separate clean-PLC CDT and imperfect-soup Wild engines; share predicates/adjacency/quality | protected CDT recovery/local-CDT certificate and Wild triangle-envelope transaction |
| Volume hex | Maréchal 2009; Nieser et al. 2011; Gao et al. 2017 | adaptive transitions are generic polyhedra, not proven all-hex; frame path absent | explicitly separate octree hex-dominant, field hex-dominant, and future proven all-hex | truthful cell-type/volume census plus generic-cell shell/volume/self-intersection validity |
| Volume poly | Abdelkader et al. 2020; Garimella et al. 2013; Sorgente et al. 2022, 2023 | jittered lattice is not VoroCrust; Lloyd label is not restricted-cell CVT; centroid/convex-hull dual loses topology and labels | separate conforming Voronoi and classified primal-dual/agglomeration routes | validity vector, no-cell-drop invariant, and complete patch/material classification |

## Required surface-to-volume contract

Every volume engine consumes a *certified surface artifact*, not an untyped
triangle array. The artifact must carry:

1. stable vertex/edge/face identifiers and source-face/barycentric provenance;
2. patch, material, wall, ridge, corner, periodic, and interface classes;
3. oriented manifold components, open-boundary and self-intersection findings,
   and explicit repair history;
4. local size/metric field, feature protection radii, and boundary-layer intent;
5. two-sided fidelity budget and measured/certified coverage;
6. deterministic content hash and the assumptions the surface actually meets.

The dispatcher chooses a contract, never silently upgrades a weak surface:

- `PLC_EXACT`: valid protected complex for Native Tet CDT.
- `SOUP_EPSILON`: imperfect triangles plus tolerance/region semantics for Native
  Tet Wild.
- `QUAD_FIELD`: quad/quad-dominant surface with singularity and patch ledger for
  compatible hex or boundary-layer paths.
- `LABELED_SURFACE`: watertight classified boundary for octree hex-dominant and
  poly routes.

Output validation is again engine-independent: closed owner-neighbor topology,
positive oriented volume, cell-shell validity, boundary/feature label coverage,
bidirectional surface fidelity, exact cell-type/volume census, quality vector,
determinism, runtime, memory, and explicit heuristic/unsupported flags.

## Implementation sequence

### Phase 0 — truthful contracts and measurement

- Stop calling triangle pairing a complete quad engine.
- Stop calling adaptive generic-poly transitions all-hex.
- Report the exact engine/route, cell types, volume fractions, assumptions,
  fallback, and post-boundary-layer types.
- Build common surface provenance and common volume validity/census kernels.

Stop condition: adversarial fixtures cannot pass under a false engine or cell
type label; every fallback is visible in the result schema.

### Phase 1 — feasibility before optimization

- Quad: metric and 4-RoSy field, feature-side/corner rules, singularity ledger.
- Tet CDT: protected constraints and local-CDT certificate.
- Tet Wild: incremental triangle transaction, cover/retry, triangle envelope.
- Hex octree: surface-intersection/local-thickness refinement and generic-cell
  validity.
- Poly: star-kernel/degeneration/combinatorial quality vector, no-drop invariant,
  complete entity classification.

Stop condition: topology, orientation, provenance, and fidelity tests pass on
cube, sphere, torus, sharp wedge, thin wall, nested components, multi-patch,
non-manifold, and deliberately invalid inputs.

### Phase 2 — real engine capability

- Quad: 4-PoSy and transactional conforming extraction.
- Tet: constrained refinement, feature-localized debt, AMIPS/sliver transactions.
- Hex: field-guided position field and topology-preserving agglomeration prototype.
- Poly: generalized classified dual and constrained 3-D agglomeration.

Stop condition: quality improves without any Phase-1 regression, across a
preregistered benchmark matrix and deterministic seeds.

### Phase 3 — expensive global/topological optimization

- Quad: min-cost-flow position-singularity reduction and bounded inversion solve.
- Hex: Maréchal-style all-hex dual transitions or CubeCover-like global
  parameterization only when their stronger assumptions are mechanically met.
- Poly: VoroCrust boundary protection/paired seeds and restricted-cell CVT.

Stop condition: each path beats the simpler production path on its declared
quality/cost target while preserving every hard contract.

## Immediate development queue

1. Common cell-type census and polyhedral validity kernel.
2. Common surface provenance/fidelity artifact and dispatcher contracts.
3. In parallel: `QUAD-ROSY1`, `TET-CDT-1/2`, `TET-WILD-1/3`, `HEX-HD-1`,
   `HEX-OCT-3`, `POLY-QUALITY-VECTOR1`, `POLY-NO-DROP-HOLES1`.
4. Cross-engine benchmark harness that records route, fallback, quality,
   fidelity, topology, determinism, runtime, and memory in one schema.

The engines should improve separately because their algorithms and assumptions
differ, but they must share the hard surface-volume contract, predicate/validity
infrastructure, provenance, metrics, and benchmark ledger.
