# AutoTessell — Compact Project Context

CAD/mesh input to OpenFOAM `polyMesh`. Native-first: self-implemented engines run
first; external engines are reference/fallback only. Never add an external dependency
without a written self-implementation plan.

## Pipeline

`Analyzer -> Preprocessor -> Strategist -> Generator -> Evaluator`

- Surface: L1 repair -> L2 remesh -> L3 reconstruction. Volume meshing requires a
  watertight manifold surface.
- Volume: `native_tet`, `native_hex`, `native_poly`; optional boundary-layer pass.
- No automatic Generator/Evaluator retry. Tier failure returns `TierAttempt`; generator
  may try another tier.

## Essential paths

- `core/analyzer/`: readers, geometry/topology analysis
- `core/preprocessor/`: surface repair/remesh
- `core/generator/`: native engines, tiers, pipeline
- `core/layers/`: boundary layers
- `core/evaluator/`: invariants and quality
- `core/pipeline/orchestrator.py`: end-to-end driver
- `core/utils/`: predicates, geometry, export
- `tests/`: tests and benchmark fixtures
- `docs/references/literature/<engine>/`: plans, evidence matrices, paper notes
- `agents/specs/`: detailed contracts

## Non-negotiable rules

1. Preserve pre-meshing input surface exactly unless a plan explicitly authorizes a
   measured surface-moving card.
2. Measure first. One card, one mechanism, small diff. New mechanisms default OFF.
3. Verify in order: L0 minimal -> L1 canonical -> L2 target-hard -> L3 regression.
4. Never relax permanent surface, topology, orientation, provenance, determinism, or
   quality gates to force PASS.
5. Preserve unrelated dirty-tree work. No destructive Git commands. Use path-scoped
   stash only when isolation is required.
6. Before each improvement round, inspect relevant full-read notes/evidence plus primary
   literature and public reference implementations. Before reporting an inaccessible DOI,
   search the local PDF manifests and archive; never request a listed paper again.
7. Parallelization/performance follows correctness.

## Load only when relevant

- Python edit: `.claude/rules/coding-style.md`
- Native-engine card or validation: `.claude/rules/verification-ladder.md`
- Workers/subagents: `.claude/rules/execution-model.md`
- Windows/WSL, workers, fallbacks, heavy pytest: `.claude/rules/lessons-learned.md`
- User reporting: `.claude/rules/communication.md`
- Engine work: relevant development plan, evidence matrix, then engine ROADMAP section

Do not reread unrelated engine plans or all rules every turn. Reuse already-read context
until files change.

## Common commands

```bash
auto-tessell run input.stl -o case --mesh-type tet --quality draft
auto-tessell run input.stl -o case --tier native_hex --auto-retry off
python tests/verify_goal.py
python tests/bench_quality_matrix.py
```

Current product state and priorities: `ROADMAP.md`. Version history: `CHANGELOG.md`.
Robustness design: `ROBUSTNESS_REPORT.md`.
