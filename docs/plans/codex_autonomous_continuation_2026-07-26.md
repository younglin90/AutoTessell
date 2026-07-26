# Codex Autonomous Continuation Prompt (2026-07-26)

This file is a self-contained prompt to hand to Codex so it can continue the
AutoTessell native-engine improvement campaign autonomously, round after
round, without needing a human to re-explain context each time. Paste the
"PROMPT START" .. "PROMPT END" block into Codex as-is. Everything above/below
that block is orientation for the human pasting it in, not part of the prompt.

---

## PROMPT START

You are continuing a long-running literature-grounded improvement campaign on
AutoTessell, a CAD/mesh -> OpenFOAM polyMesh generator. Read
`CLAUDE.md` (repo root) first for the project's architecture and
`.claude/rules/*.md` for coding style, communication conventions, and known
gotchas (lessons-learned.md especially — read it before touching anything).

### Core philosophy (do not violate)

- **Native-first.** External mesh libraries (TetWild/fTetWild, snappyHexMesh,
  cfMesh, pymeshfix, pyACVD, geogram) are reference-only. Self-implemented
  engines run first; only meshes that fail to reach grade A fall back to an
  external lib. Never add a new external dependency without a written
  "reference -> self-implementation plan" first (native-first policy in
  `.claude/rules/coding-style.md`).
- **Surface preservation is the #1 invariant.** No card may move a boundary
  vertex or change the boundary face set/area unless the card is EXPLICITLY
  about boundary motion (e.g. `TET-FLOW-1`) and does so via an exact
  re-projection step. Every other card treats the boundary as frozen.
- **Guarded-transaction pattern (used everywhere, non-negotiable):** simulate
  a candidate mesh operation on a scratch copy, measure it with the metric
  that actually matches the invariant being protected (never a borrowed/
  generic proxy — e.g. use the project's OWN canonical boundary-skewness
  formula, not an invented one), and reject the WHOLE candidate if it
  regresses — never partially apply an edit. If a repair fails partway
  through construction, the mesh must come back byte-identical to before the
  attempt.
- **Diagnostic-before-mutation.** Every new mechanism lands first as a
  log-only / zero-mesh-mutation diagnostic module that measures whether the
  literature's claim holds on OUR real shapes, before any mesh-editing code
  is written. See `core/generator/native_tet/boundary_invariant.py`,
  `core/generator/native_hex/match_diagnostic.py`,
  `core/preprocessor/native_remesh/rosy_diagnostic.py` as the canonical
  examples of this pattern.
- **Exact predicates only for topology/inversion decisions.** Use the
  vendored Shewchuk `orient3d`/`insphere` (`core/utils/_shewchuk/`) for any
  accept/reject decision about mesh validity — never a floating-point signed
  volume shortcut. A float value may be used as a conservative PRE-reject,
  never to ACCEPT.
- **Every new/risky mechanism is gated behind an explicit
  `AUTO_TESSELL_<ENGINE>_<CARD>=1` env var, default OFF**, until it has been
  measured on multiple real shapes and the Advisor (a human or a review pass)
  explicitly decides to flip the default. Do not flip a default yourself in
  the same round you land the mechanism — that is a separate decision with
  its own justification.
- **Report findings honestly, including negative results.** Several of the
  most valuable cards this campaign has produced were "this mechanism does
  not work, here is the measured proof" (see poly's agglomeration KILL,
  hex's column-collapse-is-structurally-impossible finding). Do not force a
  positive result. A well-measured negative result that closes off a dead
  end is exactly as valuable as a positive one.

### Workflow discipline

1. Each of the 5 engines — `native_tet`, `native_hex`, `native_poly`,
   `native_tri` (surface triangle remeshing), `native_quad` (surface
   quad-dominant remeshing) — has its own literature-integrated development
   plan doc at
   `docs/references/literature/native_<engine>/native_<engine>_literature_integrated_development_plan_2026-07-23.md`
   (native_quad currently only has `evidence_matrix.md`, no separate plan
   doc yet — create one if the card sequence grows enough to warrant it).
   These docs are **append-only** — never rewrite history, only add new
   dated sections at the point in the doc that makes sense (usually right
   after the card sequence entry it resolves). The END of each doc has the
   most recent state; always read the whole doc, but weight the tail most.
2. Before implementing a card: read the target engine's plan doc in full,
   read `evidence_matrix.md` in the same directory for the FULL_READ paper
   list and per-paper candidate cards, and read the specific literature note
   (`docs/references/literature/native_<engine>/<author><year>_<topic>.md`)
   for the paper the card is based on. Do not re-derive equations from
   memory — port the paper's actual equations, and say so explicitly in the
   new module's docstring, including any deliberate scope reduction versus
   the full paper.
3. Pick the next card per the plan doc's OWN stated priority order, not by
   guessing. If the doc is ambiguous about what's next, prefer whichever
   option (a) has the strongest existing literature backing, (b) is
   diagnostic-only or has the smallest blast radius, (c) does not require
   surgery on a file known to carry large pre-existing uncommitted content
   (see the git-hygiene section below). State your tiebreak reasoning
   explicitly in the commit message if you had to use one.
4. Implement following the guarded-transaction / diagnostic-first discipline
   above. Measure on REAL benchmark shapes used by prior cards in that
   engine (check `tests/stl/` and the plan doc's own prior measurement
   tables for which fixtures have continuity — e.g. native_tet's
   naca0012/dual_torus, native_hex's cylinder/sphere/gear, native_poly's
   cube/cylinder, native_quad's cube/cylinder/bracket), not only synthetic
   toys, though synthetic cases are good for unit tests of specific
   invariants (e.g. hand-computable index values, forced degenerate cases).
5. Write unit tests covering: the new mechanism's core correctness claim
   (often an analytic/hand-computable check, e.g. Poincare-Hopf for a
   rotationally-symmetric field, exact volume-tiling identities for
   flips/collapses), a forced-failure/rollback path (prove the transaction
   really reverts to byte-identical state on rejection), and at least one
   real-shape smoke test.
6. Run the FULL relevant regression suite for that engine before considering
   the card done — not just the new tests. Confirm zero regressions.
7. Append a dated result section to the plan doc (`## YYYY-MM-DD <CARD> result
   (measured...)`), following the existing format in that doc: what was
   built, the measured before/after table, any bug found+fixed (with the
   specific before/after numbers, not just a description), documented scope
   reductions, and a recommendation for the next card.
8. Commit with a detailed message (see git-hygiene section for the exact
   commit-splitting procedure this repo needs). Do NOT squash multiple
   cards into one commit — one card, one commit (plus its own doc-update
   commit if the plan doc needed pre-existing-WIP cleanup first, see below).

### Git hygiene — READ CAREFULLY, this repo has sharp edges

- This repo is accessed via a Windows/WSL filesystem bridge
  (`\\wsl.localhost\ubuntu\...` from Windows, `/home/.../` natively in WSL).
  **Always do git operations from WSL native** (`wsl.exe -d ubuntu -- bash -c
  "cd /home/younglin90/work/claude_code/AutoTessell && ..."` or run directly
  if you already have a WSL/Linux shell) — the Windows-side bridge breaks on
  `tessell-mesh/build_make/lib/libgeogram.so*` (`lstat: Function not
  implemented`) and produces spurious CRLF-vs-LF diffs.
- **`git status` in this repo will show MANY modified files that are pure
  CRLF-line-ending noise, not real content**, left over from files having
  been touched by both Windows-side and WSL-side tools across this whole
  campaign. Before touching ANY file that shows as modified and you did not
  just edit yourself: run `git diff --numstat -- <file>` — if insertions
  equal deletions (or very close), and `grep -c $'\r' <file>` on the working
  copy is large while `git show HEAD:<file> | grep -c $'\r'` is 0 (or vice
  versa), it is CRLF noise. Two ways to handle it:
  - If you need to edit that file yourself: normalize it first with `sed -i
    's/\r$//' <file>`, confirm the diff drops to only the real pre-existing
    content (compare with `git diff --ignore-cr-at-eol --numstat`), commit
    that pre-existing content as its OWN small doc/cleanup commit ("docs:
    commit pre-existing uncommitted <X> section" or similar), THEN make your
    real edit and commit that separately. This has repeatedly recovered
    genuine multi-hundred-line uncommitted work (plan-doc sections, in one
    case) that would otherwise sit at permanent risk of loss.
  - If a file you must touch (typically `core/generator/native_tet/mesher.py`
    or `core/generator/native_hex/mesher.py`, the two hot integration points)
    mixes CRLF noise WITH large unrelated pre-existing real WIP you should
    NOT commit (someone else's in-progress work): do NOT `git add` the whole
    file. Instead isolate your own hunk via blob surgery: get
    `git show HEAD:<file> > /tmp/head.py`, extract just your intended
    addition from `git diff --ignore-cr-at-eol -- <file>` (find the exact
    `@@ -old,n +old,m @@` hunk, extract only the `+` lines that are yours,
    strip the leading `+`), splice them into the HEAD copy at the correct
    line, verify with `diff` that the result differs from HEAD by ONLY your
    intended lines, `git hash-object -w /tmp/new.py`, then
    `git update-index --cacheinfo 100644,<blob-sha>,<path>` to stage exactly
    that blob without touching the working tree file (which keeps the other
    WIP intact and uncommitted, undisturbed). This is the ONLY safe way to
    add a ~20-40 line wiring hunk to `mesher.py` without either destroying
    someone else's uncommitted work or accidentally committing it
    half-baked.
- **NEVER run `git reset --hard`, `git checkout -- <file>`, or `git clean`
  as a way to "clean up" this repo's noisy status, and never as an abort
  fallback for a failed `git stash pop` / `git merge --abort`.** A past
  session did exactly this and permanently destroyed a large uncommitted
  work-in-progress layer in `core/generator/native_tet/tier_native_tet.py`
  that had no git trace to recover from. If a merge/stash operation fails
  or you're unsure what state the tree is in, STOP, run `git status` and
  `git diff --stat`, and figure out precisely what would be destroyed before
  doing anything destructive. When in doubt, make a throwaway commit on a
  scratch branch to snapshot the current state before proceeding.
- Multi-line commit messages containing backticks (`` ` ``) must be written
  to a temp file and committed with `git commit -F <file>` — backticks
  inside a `git commit -m "..."` invocation passed through nested shell
  quoting (Windows tool -> WSL -> bash -c) get interpreted as command
  substitution and corrupt the message (or crash the command outright).
- `native_tet` work happens directly in the main repo directory (no separate
  worktree — it's the most actively developed engine and splitting it out
  added more friction than it saved). `native_hex`, `native_poly`,
  `native_tri`, and `native_quad` each have their own git worktree:
  `../AutoTessell-hex`, `../AutoTessell-poly`, `../AutoTessell-tri`,
  `../AutoTessell-quad` (siblings of the main `AutoTessell` directory).
  Before starting work in one of these worktrees, always sync it to the
  latest master first: check `git status --short` is clean, then
  `git reset --hard $(git -C ../AutoTessell rev-parse master)` (only if
  clean — if it shows anything uncommitted, STOP, do not discard it).
  After finishing a card in a worktree: commit there, then
  `git -C /home/.../AutoTessell merge --no-ff <worktree-commit-sha> -m
  "Merge native_<engine> <card>"` from the main repo to bring it into
  master. If the merge fails on "local changes would be overwritten", it is
  almost always the CRLF-noise situation above — normalize with `sed -i
  's/\r$//'` (or isolate+commit real pre-existing content first) and retry.
- Prefer `--no-ff` merges so each engine's card stays visible as its own
  commit in `git log`, not squashed into the merge.

### Testing gotchas

- **Windows-side Python and WSL-native Python are different interpreters
  with different installed packages** (`igl`, `pyacvd` exist in the WSL venv
  only). If a card touches those, always verify via WSL native Python, and
  say explicitly which environment you tested in.
- **`generate_native_tet` called twice in one pytest process on a heavy mesh
  (10k+ cells) can crash the interpreter** with a non-deterministic access
  violation. Use a module-scoped fixture so a test file calls it once and
  shares the result, if you need multiple assertions against one heavy mesh.
- **`pytetwild`/fTetWild segfaults in fork-spawned worker pools** — the
  bench scripts force `AUTO_TESSELL_P4C_PYTETWILD=0` at worker entry for
  this reason; main/CLI/GUI keep it on (default). NOTE (2026-07-26 finding,
  not yet resolved): `generate_native_tet` on simple fixtures like `cube.stl`
  with default `seed_density`/`target_cells` was observed returning a
  DIFFERENT tet count across consecutive runs with the pytetwild fallback
  active (nondeterministic), vs. a fully deterministic (but much coarser)
  result with `AUTO_TESSELL_P4C_PYTETWILD=0`. This means any card that
  measures "before/after" numbers on an end-to-end STL pipeline run (as
  opposed to directly on a fixed, already-generated tet primal) may be
  comparing against a nondeterministic baseline. Investigate and fix this
  before trusting absolute-number comparisons from end-to-end pipeline runs;
  comparisons that share one fixed captured primal across variants (as most
  diagnostic modules already do) are not affected.
- Windows console is cp949 and cannot encode em-dash/degree/middle-dot in
  print output — reconfigure stdout/stderr to UTF-8 at process start in any
  cross-platform script, and pass `encoding="utf-8"` to file I/O.

### Current state per engine (as of commit `4b7b33fc`, 2026-07-26)

**native_tet** (works in main repo, no worktree):
- Landed: `FSL Wave 1` (`4c4a621a`) — Dassi 2018 lazy edge-removal, resolved
  60/61 core-unflippable wedges on dual_torus. Gated
  `AUTO_TESSELL_FSL_WAVE1`, default OFF.
- Landed: `TET-FLOW-2` (`b722acb0`) — Leng 2013 penalized active-set interior
  smoothing. Gated `AUTO_TESSELL_TET_FLOW2`, default OFF (works well on
  naca0012/cylinder but has a downstream-divergence caveat with the
  surface-snap-restore pass — read the commit message / plan doc section 9
  in full before flipping the default).
- Next per plan doc section 9.4: `TET-MM-1`/`TET-SHAPE-2` (distribution
  axis) or `TET-LAZY-2`/`TET-FLOW-3` (worst-case axis), measured alone
  before any stacking.
- Known orphans (tests exist, implementation does not — do not assume these
  work): `tests/test_native_tet_shape_gate.py` (imports
  `quality.tet_gsm_score`, `TET-SHAPE-1`),
  `tests/test_native_tet_bcc_cert_harness.py` references
  `validate.classify_flat_sliver_wdel2` (`TET-WDEL-2`). Both untracked in
  git. Either implement the missing cards or delete the orphan tests — do
  not leave them silently failing collection.

**native_hex** (worktree: `../AutoTessell-hex`):
- Landed: `HEX-MATCH-1` (`0e727b2a`) diagnostic + `HEX-MATCH-2` (`1f61ebbe`)
  pillow-repair implementation. Gated `AUTO_TESSELL_HEX_MATCH2`, default OFF.
- Key finding: column collapse is structurally impossible for any column
  HEX-MATCH-1 traces (every chord starts at a boundary quad, so collapse
  always merges surface nodes). Single-cell pillow shrink-set works
  geometrically but the quality gate rejects ~99% of candidates because
  inflating all 6 faces of one cell radiates bad non-orthogonality onto the
  rung faces.
- Next: a LAYER-WIDE pillow shrink set (all boundary cells at once,
  interface = the manifold quad set separating them from the interior) per
  Ledoux 2010 / Mitchell & Tautges 1995 — scoped in the plan as
  `HEX-SHEET-2` / the per-patch BL primitive. Do NOT run `HEX-MATCH-3` (the
  bracket multi-component spike) until this lands and actually commits
  something — measuring conflict behavior of a near-zero-commit mechanism is
  uninformative.

**native_poly** (worktree: `../AutoTessell-poly`):
- Landed: `POLY-AGGLOM-CFD1` (killed) + `POLY-AGGLOM-FACEGEOM1` (`7abe77bc`,
  confirms the kill is structural, not a facet-union construction artifact).
  Agglomeration (all forms: GRAPH1/PAIR1/VSTAR1/RTREE1/SHAPE1/LOOKAHEAD1) is
  demoted to reference-only. polydual remains the production path.
- Next per recommendation: `POLY-NO-DROP-HOLES1` (Phase 1 contract card,
  `core/evaluator/quality.py:369-432` cell-drop logic, small blast radius).
- Open item to resolve before trusting repair-lane baselines: a
  route-attribution discrepancy on cylinder surface-area deviation (15.5%
  measured via a direct `tet_to_poly_dual` call vs. 0.154% recorded at the
  production `tier_native_poly` gate) — likely a route/pipeline-stage
  difference, not a real regression, but confirm before optimizing against
  either number.
- Also see the pytetwild-nondeterminism finding in the testing-gotchas
  section above — this engine's two most recent cards both measured on
  end-to-end STL-generated primals and may be affected for absolute (not
  relative/shared-primal) comparisons.

**native_tri** (worktree: `../AutoTessell-tri`):
- Landed: `TRI-SHELL-DOMAIN1` (`8620aeef`) — Jiang 2020 linear bijective
  shell as a per-round containment checkpoint. Landed: an O(F^3)-class
  performance fix in `operator_loop.py`'s guards (merged into master),
  240x speedup on a 1280-face sphere, verified bit-exact against the
  pre-fix implementation.
- Remaining known bottleneck (flagged, not fixed — needs candidate-selection
  redesign, not a scope-preserving optimization): the split/collapse
  `while True` loops in `run_one_round` re-evaluate every edge each
  iteration, O(E^2*F) when those operators are actually firing (not just the
  guards). Tracked as a follow-up task; pick it up if it blocks a future
  card that needs split/collapse active on a real-size mesh.
- No explicit "next card" recorded yet beyond that follow-up — read the plan
  doc's card sequence for what comes after Phase 3 (shell domain).

**native_quad** (worktree: `../AutoTessell-quad`):
- Landed: `QUAD-ROSY1` (`0ac7088a`) — Jakob 2015 4-RoSy orientation field
  diagnostic, gated by Poincare-Hopf as a falsifiable correctness check.
  Landed: `QUAD-MULTIRES1` (`5d885836`) — coarse-to-fine relaxation.
  Negative result: multires does NOT close the bracket shape's
  extrinsic/intrinsic ±1/2-index-face disagreement (18 vs 4 faces) — proven
  to be a geometric property of sharp edges, not an optimizer-stall
  artifact. It DOES give ~580x lower run-to-run variance and mildly reduces
  singularity count on smoother shapes (cylinder).
- Next: `QUAD-SINGULARITY1` (explicit ambiguous-face ledger) BEFORE
  `QUAD-POSY1` — a 4-PoSy integer-offset ledger built on the current
  ambiguous field would reproduce Huang 2018's own ~20% watertightness
  failure mode.
- Known orphan: `core/preprocessor/native_remesh/quad_dominant.py` and its
  test are UNTRACKED in git (never committed) and currently BROKEN (test
  imports `QuadDominantConfig`, which does not exist in
  `native_remesh/__init__.py`). The evidence_matrix.md's description of it
  as a "working conservative fallback" is stale. Fix or formally deprecate
  it before any card depends on it as a fallback path.

**2026-07-26 QUAD-POSY1 result (measured, report-only; candidate policy KILL).**

- Added `core/preprocessor/native_remesh/posy_diagnostic.py` and
  `tests/test_native_quad_posy_diagnostic.py`. The immutable ledger records
  per-face integer offsets, quarter-turn rotations, regularity residuals,
  orientation determinants, position-singularity counts, and explicit branch
  options. It consumes the existing multiresolution 4-RoSy/singularity ledger
  without changing that field or any mesh path.
- Multiresolution A/B (`20` total sweeps, seed `0`) on the real assets:

  | Shape | faces | candidates | position singularities | inversions | unresolved |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | cube | 12 | 16 | 12 | 3 | 4 |
  | cylinder | 512 | 528 | 427 | 14 | 16 |
  | bracket | 416 | 484 | 331 | 8 | 54 |

- Single-resolution A/B was also measured: cube `12/3/4`, cylinder
  `401/13/16`, and bracket `336/9/56` for position singularities/inversions/
  unresolved entries. Multiresolution does not consistently reduce integer
  regularity failures and leaves the known bracket half-index branches
  unresolved.
- **KILL:** these candidates do not support a safe integer-offset policy or
  any default-on mesh mutation. The card remains report-only; no extraction,
  generation, fallback, or production caller was wired. The optional helper
  recognizes `AUTO_TESSELL_QUAD_POSY1=1` but is default OFF and has no effect
  unless a future report hook calls it. The exact requested integrated native
  quad plan filename was absent from this worktree and Git history at start;
  this result is recorded here and in the quad evidence matrix/changelog.

### How to run a round

Pick an order (recommended: surface engines first since they gate volume
quality — `quad -> tri -> tet -> hex -> poly` — but any consistent order is
fine). For each engine in turn:

1. Sync its worktree to latest master (main-repo directory for tet needs no
   sync step, just `git status --short` to confirm no stray uncommitted
   changes before starting).
2. Read that engine's plan doc tail + evidence_matrix.md + the specific
   literature note for the next card.
3. Implement, test, measure, per the discipline above.
4. Run the full engine-specific regression suite. Zero regressions required.
5. Append the dated result section to the plan doc.
6. Commit (handling any pre-existing CRLF/WIP noise per the git-hygiene
   section). Merge worktree commits into master with `--no-ff`.
7. Move to the next engine.

After a full round across all 5 engines, write a short summary (which cards
landed, which flags are still default-OFF and why, what the next card per
engine is) and either stop for human review or begin the next round,
whichever the operating mode calls for. If running unattended for multiple
rounds, err toward MORE diagnostic/measurement cards and FEWER default-flag
flips — flipping a default from OFF to ON is a production-behavior decision
that should accumulate strong multi-shape evidence first, not happen inside
the same autonomous pass that just landed the card.

## PROMPT END

---

## Notes for the human pasting this in

- This reflects state as of commit `4b7b33fc` (2026-07-26). If significant
  time has passed, tell Codex to re-derive "current state per engine" from
  each plan doc's tail rather than trusting the summary above verbatim — it
  will go stale.
- The "flip a default ON" decision was deliberately left as a human-in-the-
  loop gate in every card landed this session. If you want Codex to be able
  to flip defaults autonomously after enough evidence accumulates, say so
  explicitly and give it a concrete bar (e.g. "3+ real shapes, zero
  regressions, zero caveats about downstream divergence").
- If Codex reports a data-loss risk (large uncommitted pre-existing content
  on a file it needs to touch) it cannot resolve with the blob-surgery
  procedure above, tell it to stop and ask rather than guess.
