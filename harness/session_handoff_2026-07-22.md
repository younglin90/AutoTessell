# AutoTessell Handoff - 2026-07-22

## New Session Prompt

Use this prompt to continue in a new Codex session:

```text
이전 AutoTessell 작업을 이어서 진행해줘.

환경:
- Workspace: /home/younglin90/work/claude_code/AutoTessell
- Shell: WSL Ubuntu via `wsl.exe -d Ubuntu -e bash -lc 'cd /home/younglin90/work/claude_code/AutoTessell && ...'`
- Current branch at handoff: master, HEAD da9a183f
- AGENTS.md 규칙 준수: caveman ultra, Track B 삭제 유지, native C/C++ 성능/품질 개선 목표 유지.
- 절대 `git reset --hard`, `git checkout --`, 대량 삭제 금지. 기존 dirty 변경은 사용자/이전 작업물로 보고 보존.

먼저 읽을 파일:
- harness/session_handoff_2026-07-22.md
- docs/references/tetrahedral_meshing/native_tet_gap_reduction_plan_2026-07-21.md
- docs/references/tetrahedral_meshing/cdt_notes_2026-07-22.md
- docs/references/hex_meshing/native_hex_dominant_upgrade_plan_2026-07-22.md
- docs/references/poly_meshing/native_poly_upgrade_plan_2026-07-22.md

현재 목표:
1. Native tet 우선:
   - CDT blocker counts 기준으로 `CDT2-SHELL` 구현.
   - ready missing edge 대상 bounded shell cavity insertion.
   - no_cavity는 `CDT3-NOCAVITY`로 분리.
2. Native hex-dominant:
   - `HEXDOM-REPORT1`: `native_tier_patch_stats_unavailable error="'type'"` 수정.
   - `HEXDOM-DIST1` E2E 확대 검증.
3. Native poly:
   - `tests/test_native_poly_solid_volume.py` cylinder boundary/volume 기존 실패 3개 조사/수정.
   - `POLY-TOPO1` provenance helper를 실제 writer/dual 경로로 확대.

최근 통과 guard:
- native tet guard with CDT/MFRC/Stellar: 166 passed.
- hex/poly/tier/tet integration guard: 142 passed.
- hex E2E cube 2000: PASS, 1.400482s, cells 2197, points 2744, negative 0, non-ortho 0.0, skew ~3.6e-16.

현재 dirty worktree 큼. 변경 파일을 섞어 revert하지 말고, scope별로 작은 검증 후 커밋 후보를 나눠라.
```

## Worktree State

Snapshot at handoff:

- Branch: `master`
- HEAD: `da9a183f`
- `git status --short`: 218 entries
- tracked dirty files: 122
- untracked paths: 237

Do not interpret all dirty files as current-session edits. Many were already dirty before the latest native tet/hex/poly work.

## Latest Implemented Scope

### Native tet

Files changed or added in latest research-backed tet scope:

- `core/generator/native_tet/cdt_recovery.py`
- `core/generator/native_tet/mesher.py`
- `core/generator/native_tet/stellar.py`
- `core/generator/native_tet/mfrc.py`
- `tests/test_native_tet_cdt_recovery.py`
- `tests/test_native_tet_mfrc.py`
- `tests/test_native_tet_stellar.py`
- `scripts/verify_native_tet_replacement_matrix.py`
- `docs/references/tetrahedral_meshing/cdt_notes_2026-07-22.md`
- `docs/references/tetrahedral_meshing/mfrc_notes_2026-07-22.md`
- `docs/references/tetrahedral_meshing/stellar_notes_2026-07-22.md`
- `docs/references/tetrahedral_meshing/native_tet_gap_reduction_plan_2026-07-21.md`

Implemented:

- `CDT1`: `diagnose_cdt_recovery_blockers()`.
- CDT plateau diagnostic JSON/log path.
- Matrix verifier CDT diagnostic fields and CDT strength options.
- `MFRC1`: bounded edge-ring multi-face reconstruction helper.
- `STELLAR1`: QOPT-gated edge midpoint cleanup helper.

CDT blocker counts from hard cases:

- `03_hard_bracket`: missing 604, duplicate 15, no_cavity 70, ready 115.
- `pipe.step`: missing 1388, duplicate 2, no_cavity 99, ready 99.
- `04_extreme_gear`: missing 1446, duplicate 10, no_cavity 40, ready 150.
- `mixed scale_aniso`: missing 244, no_cavity 59, protected_encroachment 1, ready 140.

Next tet cards:

- `CDT2-SHELL`: ready missing edge 대상 bounded shell cavity insertion.
- `CDT3-NOCAVITY`: no_cavity 대상 local star/shell cavity expansion.

### Native hex-dominant

Files changed in latest hex scope:

- `core/generator/native_hex/mesher.py`
- `core/generator/native_hex/octree.py`
- `core/generator/native_hex/snap.py` from earlier worker scope
- `tests/test_native_hex.py`
- `tests/test_native_hex_octree.py`
- `tests/test_native_hex_snap.py` from earlier worker scope
- `docs/references/hex_meshing/native_hex_dominant_upgrade_plan_2026-07-22.md`

Implemented:

- `HEXDOM-WALL1`: strict wall-only BL intent/classifier.
- `HEXDOM-FINAL1`: adaptive/uniform common finalization summary and adaptive report fields.
- `HEXDOM-DIST1`: exact point-to-triangle distance for adaptive surface band plus bounded triangle-AABB overlap diagnostic.
- Hex E2E benchmark doc section.

Latest hex validation:

- `tests/test_native_hex.py tests/test_native_hex_snap.py tests/test_native_hex_octree.py`: 58 passed.
- `test_hex_dominant_cube_smoke`: 1 passed.
- `scripts/smoke_native_hex.py 2000`: PASS.
- curved/negative-volume focused tests: 4 passed.

Next hex card:

- `HEXDOM-REPORT1`: fix `native_tier_patch_stats_unavailable error="'type'"` in common finalization/report parser. Likely scope: `core/generator/_tier_native_common.py`, so it is outside hex-only worker scope.

### Native poly

Files changed or added in latest poly scope:

- `core/generator/native_poly/voronoi.py`
- `core/generator/native_poly/patch_roles.py`
- `tests/test_native_poly.py`
- `docs/references/poly_meshing/native_poly_upgrade_plan_2026-07-22.md`

Implemented:

- `POLY-WALL1`: typed patch role/provenance resolver and wall-only BL eligibility.
- `POLY-BL1`: direct Voronoi prism BL default off. Experimental only via `AUTO_TESSELL_POLY_DIRECT_VORONOI_BL=1`.
- `POLY-TOPO1`: face provenance diagnostics and protected patch-interface edges.

Latest poly validation:

- `tests/test_native_poly.py`: 21 passed in worker.
- `tests/test_native_poly_harness_edge.py tests/test_native_poly_dual.py`: 12 passed.
- tier post routing/BL phase2: 40 passed.

Known poly unresolved:

- `tests/test_native_poly_solid_volume.py` has existing cylinder boundary/volume gate failures, reported as preexisting by worker.
- Last `POLY-SOLIDVOL` worker was shut down without final result. Treat as not done.

## Last Combined Validations

Commands recently passed:

```bash
python3 -m pytest \
  tests/test_native_hex.py \
  tests/test_native_hex_snap.py \
  tests/test_native_hex_octree.py \
  tests/test_native_poly.py \
  tests/test_native_poly_harness_edge.py \
  tests/test_native_poly_dual.py \
  tests/test_tier_layers_post_routing.py \
  tests/test_tier_layers_post_bl_phase2.py \
  tests/test_native_tet_cdt_recovery.py \
  tests/test_native_tet_mfrc.py \
  tests/test_native_tet_stellar.py -q
```

Result:

```text
142 passed in 84.07s
```

Native tet broader guard passed earlier:

```text
166 passed in 310.95s
```

Autoresearch guard:

```text
no_autoresearch_continue_guard
```

## Dirty File Handling

Do not run broad cleanup commands. Use this policy:

1. Keep existing dirty files untouched unless directly in the active card scope.
2. Before edits, run `git status --short <scoped paths>`.
3. After edits, run focused tests and `git diff --check -- <scoped paths>`.
4. Commit candidates should be split by scope:
   - tet CDT/MFRC/Stellar diagnostics
   - hex WALL/FINAL/DIST/report
   - poly WALL/BL/TOPO/solid-volume
   - docs/handoff
5. Do not include desktop/docs/global roadmap churn unless user explicitly wants all dirty state committed.

## Suggested Next Commands

Native tet CDT:

```bash
python3 -m pytest tests/test_native_tet_cdt_recovery.py tests/test_native_tet_mfrc.py tests/test_native_tet_stellar.py -q
python3 scripts/verify_native_tet_replacement_matrix.py \
  --run-root /tmp/autotessell_cdt2_shell_focus_v1 \
  --source tests/stl/03_hard_bracket.stl \
  --source tests/benchmarks/pipe.step \
  --source tests/stl/04_extreme_gear.stl \
  --max-cells 2000 --bl-layers 3 --timeout 600
```

Hex:

```bash
python3 -m pytest tests/test_native_hex.py tests/test_native_hex_snap.py tests/test_native_hex_octree.py -q
```

Poly:

```bash
python3 -m pytest tests/test_native_poly_solid_volume.py -q
python3 -m pytest tests/test_native_poly.py tests/test_native_poly_harness_edge.py tests/test_native_poly_dual.py -q
```
