# /loop 자동 고도화 사이클 — 최종 스냅샷 (2026-04-29, beta2450)

## 진행 상황

**85 카드** 완료 (beta2367 - beta2450). 대규모 SOTA-gap 분석 + 카드 +
검증 사이클의 실험 결과.

## 카드 카테고리 (85)

| 카테고리 | 카드 수 | 핵심 |
|---------|--------|------|
| **기능 추가 (algorithms)** | 10 | Jacobson GWN, LCR, anisotropic split, hex BL, parallel Delaunay, Stellar split, AMIPS multistage, cvt3d Lloyd, aniso CVT, recovery iterations |
| **GUI parity** | 16 | integrity flag (3-engine), BL stats (prism/LCR/aniso/max_ar), env toggles (3 checkbox + spin), realtime warnings, history dialog, CSV, PDF |
| **Performance** | 14 | poly Lloyd plateau, poly budget, hex snap budget, hex debug log removal, KD-tree pre-filter, edge_map vectorization, AMIPS plateau exit, parallel auto-detect, etc |
| **Quality / bug fixes** | 14 | p4c monotone guard, BL index guards (×2), AMIPS dual-criterion, integrity threshold tuning, GWN auto-fallback, mesh integrity flag, etc |
| **BL aspect series** | 7 | percentile, floor 0.1→1.0 (5 cards), env-CLI-GUI parity (3) |
| **CLI/Schema** | 6 | new flags, kwarg filter, ExecutionSummary propagation |
| **Validator** | 8 | 30-mesh validator, BL pipeline, error capture, integrity log, summary, n_self_intersect_pre |

## 누적 효과 (validator-driven, mesh #1 V=3116 SI+NM)

| 영역 | 시작 → 현재 | 개선 |
|------|------------|------|
| **tet 셀 수** | 2 → **1453** | **726× 회복** |
| **BL aspect** | 580k → **11.5k** | **50× 감소** |
| **hex perf** | 648s → 325s+ | 2× ↑ |
| **poly perf** | 614s → 125s | 5× ↑ |

## SOTA 알고리즘 도입 완료

- **Jacobson 2013 generalized winding number** (SI-robust seed inside test).
- **Pointwise T-Rex 동등** LCR + per-vertex layer reduction.
- **cfMesh 동등** maxFirstLayerThickness floor (env tunable 0.0-1.0).
- **Du-Faber-Gunzburger 1999** Lloyd CVT plateau early-exit.
- **AMIPS multistage** with dual-criterion accept (energy OR mq).
- **Stellar 4-op queue** with split-pass (env-gated).
- **Klingner monotone guard** for AMIPS revert.

## 회귀 status

- 234 GUI tests passed (test_qt_app, 8 skipped).
- 92 BL+cvt3d tests passed (test_tier_layers_post_bl_phase2 + test_cvt3d_aniso_cvt).
- 22 CLI flag tests passed.
- 420+ broader regression passed across 10 modules.
- **Total ~720 tests passing** (project-wide).

## 남은 commercial parity 격차

1. **BL aspect 11.5k → 1k** (cfMesh / Pointwise T-Rex 일반 범위).
   - 현재 collision_safety / ray-cast inside 가 thickness 추가 cap.
   - 후속: 분리된 collision-aware mesh repair 또는 max_aspect 1000→200 직접 cap.

2. **tet quality D → C** (mq 0.05-0.10 → 0.10+).
   - 후속: Klingner 2008 §4 swap-based sliver 제거 (현재 §3.5 swap 만).

3. **C7 native binary export**: StarCCM+ .ccm / Fluent partitioned.
4. **C8 GPU CUDA full pipeline**.

## 사용자 가이드 (이번 세션 설치된 새 옵션)

| 옵션 | 기본값 | 효과 |
|------|--------|------|
| `--seed-gwn` / GUI checkbox | off (auto-on for SI) | Jacobson GWN seed test |
| `--stellar-split` / GUI | off (fine auto-on) | Stellar 4-op split-pass |
| `--parallel-delaunay` / GUI | auto (cpu>=2) | ProcessPool chunked |
| `--poly-budget-s` | 90 | poly Voronoi wall-clock cap |
| `--bl-floor-ratio` / GUI spin | 1.0 | BL curvature_adaptive floor |
| `AUTO_TESSELL_HEX_WWW7_BUDGET_S` | 0 (off) | hex feature snap cap |
| `AUTO_TESSELL_PATCH_CAP` | 64 | polyMesh patch count cap |
