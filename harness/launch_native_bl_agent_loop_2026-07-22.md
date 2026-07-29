# New Session Launcher: Five Native Engine Autoresearch

Paste this full block into a new Agent-enabled session when a separate foreground
session is desired. In this current session, use it as the execution contract.

```text
Run AutoTessell native-engine autoresearch for five independent lanes:

1. 3D surface mesh: native tri, with wall-edge boundary-layer support.
2. 3D surface mesh: native quad dom, with wall-edge boundary-layer support.
3. 3D volume mesh: native tet, with wall-face boundary-layer support.
4. 3D volume mesh: native hex dom, with wall-face boundary-layer support.
5. 3D volume mesh: native polyhed, with wall-face boundary-layer support.

Use the `codex-autoresearch` skill. Read its `SKILL.md`,
`references/workflow.md`, and `references/experiment.md` completely before any
write. Also read `AGENTS.md`, `CLAUDE.md`, `.claude/rules/execution-model.md`,
`.claude/rules/coding-style.md`, and these research docs when present:

- `docs/references/surface_remeshing/native_surface_upgrade_plan_2026-07-22.md`
- `docs/references/tetrahedral_meshing/native_tet_gap_reduction_plan_2026-07-21.md`
- `docs/references/hex_meshing/native_hex_dominant_upgrade_plan_2026-07-22.md`
- `docs/references/poly_meshing/native_poly_upgrade_plan_2026-07-22.md`
- `docs/references/boundary_layers/native_bl_harness_research_2026-07-22.md`

Isolation:

- Do not reset, checkout, stash, clean, stage, or edit the user's dirty root worktree.
- Do not reuse another lane's worktree, branch, metric output, temporary directory,
  or `autoresearch-results/`.
- The existing native tet/BL run
  `/home/younglin90/work/claude_code/AutoTessell-autoresearch-bl-v2` remains
  separate unless the lane is explicitly assigned to continue that exact run.
- Each lane gets a clean Git worktree, named branch, committed metric driver,
  validated baseline, and separate controller history.
- Workers can edit only their allocated scope.

Agent topology:

- Planner phase first: `gpt-5.6-sol`, reasoning `high`.
- Worker phase after planner cards: `gpt-5.6-terra`, reasoning `medium`.
- If only four total agent slots exist, run planner waves:
  surface planner first, volume planner second, then run at most three Terra
  workers concurrently and queue the remaining lanes.
- Keep one supervisor/validator in the main session.

Planner phase:

For every lane, the planner must inspect current code, browse primary papers/repos,
and produce a concise card naming:

- baseline branch/SHA and worktree path,
- exact source scope,
- corpus,
- deterministic verify command,
- metric name/direction/baseline/target,
- guard command,
- hard gates,
- accepted algorithm ideas,
- license/copy constraints,
- first falsifiable hypothesis.

Source policy:

- `native_tri`: actively port MIT/BSD-compatible local-operator remeshing ideas from
  PMP, Geogram, Cinolib. Feature preservation and envelope gates are mandatory.
- `native_quad_dom`: adopt Instant Meshes field-aligned architecture first.
  Use QuadriFlow/libigl as algorithm references. Copy only after license check.
- `native_tet`: prioritize invariant-guarded split/collapse/flip/smooth,
  feature-constrained boundary motion, shell-cavity recovery, and BL validity.
- `native_hex_dom`: prioritize semantic wall-only BL shell, sparse exact octree
  surface band, common finalization, feature-edge hex-path mapping, and first-ring
  scaled-Jacobian line search.
- `native_polyhed`: prioritize wall-only prism shell, tet-core dualization,
  VoroCrust-style paired boundary sites, signed-pyramid validity, true-poly family
  share, and provenance-preserving writer. Do not use hex fallback to improve poly score.
- MeshCNN/AI is advisory only: classify feature/wall-edge risk, then deterministic
  native algorithms pass or reject. No trained-model claim without data/eval.
- If a paper cannot be accessed, report DOI and the missing section needed.

Metrics:

- `native_tri`: `passing_cases`, higher better, target `16`.
- `native_quad_dom`: `passing_cases`, higher better, target `16`.
- `native_tet_volume_gate_failures`: lower better, target `0`.
- `native_hex_dom_volume_gate_failures`: lower better, target `0`.
- `native_polyhed_volume_gate_failures`: lower better, target `0`.

Common surface hard gates:

- no volume output,
- closed input remains watertight/manifold,
- open/non-manifold fixture rejected or repaired with recorded topology changes,
- degenerate/flipped faces = 0,
- feature drift within envelope,
- deterministic output over two runs,
- wall-edge BL only on semantic wall edges.

Common volume hard gates:

- generated mesh is the requested native family, not fallback,
- negative volumes = 0,
- duplicate/non-manifold topology = 0,
- family share: tet >= 90%, hex >= 70%, true poly >= 95%,
- requested wall BL coverage = 100%,
- non-wall BL count = 0,
- every prism corner signed Jacobian > 0,
- `max_non_orthogonality <= 70` compatibility, rank toward `<= 65`,
- internal `max_skewness <= 4`, boundary skew reported separately,
- `minDeterminant >= 0.001`,
- `minFaceWeight >= 0.05`,
- `minVolRatio >= 0.01`,
- patch provenance preserved,
- wall-face BL only on semantic wall faces.

Autoresearch loop:

1. Create/verify clean lane worktree.
2. For surface lanes, create and commit the common surface scaffold first:
   `core/surface_mesh`, `core/evaluator/surface_checker.py`,
   `scripts/bench_native_surface.py`, and `tests/test_surface_mesh_contract.py`.
3. Write and commit the metric driver before `autoresearch.py init`.
4. Run the baseline command twice. If nondeterministic, fix the metric first.
5. Initialize via `codex-autoresearch`.
6. For each iteration, change exactly one coherent hypothesis.
7. Call `autoresearch.py finish --repo <lane-worktree> --description <short>`.
8. Keep only strict metric improvement with passing guard.
9. Continue until controller records target reached, user stops, or true external blocker.

Validator:

- Inspect raw metric logs, not worker prose.
- Check Git scope, retained commit diff, guard logs, repeated verify output, and artifacts.
- Reject threshold widening, skipped corpus cases, disabled BL, reduced layer count,
  fallback substitution, synthetic report fields, or root-worktree edits.

Termination:

- A lane completes only when its controller status is `complete`, metric is `0`,
  guards pass, and validator evidence exists.
- Leave worktrees as isolated merge candidates. Do not merge into root unless user
  explicitly asks.
```
