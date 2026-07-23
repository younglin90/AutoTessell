# Native Tet code and surface-input contract audit

## Scope

Read-only audit of `core/generator/native_tet/`, the preprocessor gate, and the
generator handoff, against Shewchuk 1998, Si 2015, and Hu et al. 2020.

## Surface contract actually present

- The surface preprocessor tries L1 repair, then L2 remesh, then optional lossy
  voxel/L3 reconstruction. Passing means watertight and manifold
  (`core/preprocessor/pipeline.py:212-293`, `334-365`).
- Failure is not a hard generator stop. It records a warning and proceeds; after
  all tiers fail, the orchestrator may reconstruct a watertight surface and retry
  (`core/pipeline/orchestrator.py:516-555`).
- Native Tet itself performs duplicate, zero-area, boundary-edge,
  nonmanifold-edge, and approximate self-intersection diagnostics, but most are
  warnings (`core/generator/native_tet/input_check.py:254-329`).

Therefore there are two distinct contracts and they must not be conflated:

1. **PLC/CDT mode:** clean constraint complex, exact feature and region
   semantics; suitable for TetGen-style guarantees.
2. **Soup/envelope mode:** imperfect triangles, approximate tracked surface and
   explicitly heuristic volume classification; suitable for fTetWild semantics.

One automatic path cannot inherit both sets of guarantees.

## Major evidence gaps

| Area | Current behavior | Evidence-based gap |
|---|---|---|
| CDT recovery | midpoint/subdivision samples plus global re-Delaunay | no protected PLC, `F_e`, recursive flip transaction, local-Delaunay/visibility certificate |
| Face recovery | membership accounting | current function does not change connectivity |
| fTetWild insertion | one-shot BSP point proposal plus Bowyer-Watson | no incremental triangle transaction, subdivision table, cover provenance, rejection retry |
| Envelope | closest distance for boundary vertices | cannot certify triangle containment or Hausdorff distance |
| Surface mobility | all original surface vertices locked | prevents tolerance-driven defect healing central to fTetWild |
| Refinement proof | size thresholds and iteration caps | no insertion-radius/encroachment invariant, so no Shewchuk/TetGen termination theorem |
| Slivers | several empirical filters/smoothers | radius-edge/volume proxies do not prove dihedral bounds; cell deletion must remain void-free |
| Inside/outside | automatic robust classifier | semantics and known open/nested failure modes are not explicit API choices |

## Proposed engine split

### Native Tet CDT

For watertight/manifold PLC-compatible input. Preserve tagged segments and
subfaces. Use filtered exact predicates, protected constraints, edge/face
recovery transactions, constrained refinement, and relaxed insertion radius near
small angles. Output gate includes constraint coverage and local CDT validity.

### Native Tet Wild

For imperfect soup. Use an epsilon-envelope, incremental per-triangle insertion,
cover provenance, atomic rollback, rejected-face retry, AMIPS transactions, and
an explicit volume-classification mode. Output gate distinguishes validity,
coverage, tolerance, and heuristic region semantics.

## Shared acceptance metrics

- exact-positive orientation and zero degenerate tetrahedra;
- boundary is a combinatorial 2-manifold when a solid is requested;
- symmetric surface-distance report with sampling/error bounds;
- protected segment/face coverage for CDT mode, tracked-cover ratio for Wild;
- min/1st-percentile dihedral, max dihedral, radius-edge, AMIPS, volume-edge;
- cell count, runtime, peak memory, deterministic seed/hash;
- explicit unsupported-assumption and heuristic flags.
