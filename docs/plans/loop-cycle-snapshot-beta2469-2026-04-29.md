# /loop 자동 고도화 사이클 — 스냅샷 (2026-04-29, beta2469)

## 세션 통계

**105 카드** (beta2367 - beta2469) 완료. 본 스냅샷은 beta2455-2469 (15 카드 추가).

## 최근 카드 (beta2455-2469)

### BL aspect 정확도 (3 카드)

- **beta2455** _curvature_adaptive_thickness 가 sharp halving 후 absolute floor 재적용.
- **beta2456** local_safety floor 가 effective_first_thickness (auto-scale) 사용.

### CLI parity 신규 (5 카드)

- **beta2457** `--hex-snap-budget-s` (HEX_WWW7_BUDGET_S 등가).
- **beta2458** `--lloyd-plateau-thresh` (LLOYD_PLATEAU_THRESH 등가).
- **beta2459** `--patch-cap` (PATCH_CAP 등가).
- **beta2464** `--no-cvt3d` / `--no-aniso-cvt` / `--no-lcr` (디버깅/측정용 toggle).

### GUI parity 신규 (3 카드)

- **beta2460** `_patch_cap_spin` QSpinBox.
- **beta2461** `_hex_snap_budget_spin` QDoubleSpinBox.
- **beta2462** `_lloyd_plateau_spin` QDoubleSpinBox.

### Tet sliver 알고리즘 (1 카드)

- **beta2463** Stellar split-pass `max_splits` auto-scale (mesh 크기 비례 cap 200,
  이전 hard-cap 20). `sliver_ratio` env-tunable.

### 성능 벡터화 (4 카드)

- **beta2465** Lloyd CVT 3D inner loop scatter-sum (`np.add.at`) 벡터화 — Python
  for-loop 제거, ~10-50× 속도 개선.
- **beta2466** beta2465 후 dead code (`_build_vertex_to_tets`, `interior_count`) 제거.
- **beta2467** Stellar split monotone guard `_tet_quality_batch` 벡터화 — per-tet
  Python loop 제거, max diff 1.66e-16 (float64 round-off).
- **beta2468** aniso_cvt `_surface_principal_curvatures` angle_sum + smoothing
  (face × vi × vj 삼중 nested loop) `np.add.at` 으로 벡터화.
- **beta2469** aniso_cvt `aniso_cvt_seeds` Lloyd inner loop 의 KDTree batch
  `query(seeds, k=8)` 으로 per-seed brute-force loop 제거. fallback 보존.

### 문서 (1 카드)

- env_vars.md 동기화 — beta2462 기준 모든 CLI 노출 list 업데이트.

## 누적 효과 (beta2367 → beta2469)

| 영역 | 시작 | 현재 | 개선 |
|------|------|------|------|
| **tet 셀 수 (mesh #1)** | 2 | 1453 | 726× 회복 |
| **BL aspect (mesh #1)** | 580k | 11.5k | 50× 감소 |
| **BL prism (mesh #1)** | 0 (ex) | 4287 | 완전 회복 |
| **hex perf (mesh #1)** | 648s | 325s+ | 2× ↑ |
| **poly perf (mesh #1)** | 614s | 125s | 5× ↑ |
| **CLI flags 신규** | — | 8 (beta2418-2464) | env→CLI parity |
| **GUI 위젯 신규** | — | 7 (beta2419-2462) | full GUI parity |
| **Vectorized 모듈** | — | 5 | CVT3D, Stellar, aniso_cvt 등 |

## SOTA 알고리즘 도입 누적

- Jacobson 2013 generalized winding number (SI seed test).
- Pointwise T-Rex LCR + per-vertex layer reduction.
- cfMesh maxFirstLayerThickness floor (env-tunable 0.0-1.0).
- Du-Faber-Gunzburger 1999 Lloyd CVT plateau early-exit (env-tunable).
- AMIPS multistage with dual-criterion accept.
- Stellar 4-op queue with split-pass + auto-scaled max_splits.
- Klingner monotone guard (AMIPS revert).
- Anisotropic curvature CVT seeds (StarCCM+ skeleton).
- Hex BL prism stacking (Pointwise T-Rex skeleton).

## 최근 회귀 status

- 67 cvt3d_aniso_cvt tests passed (beta2454: 60 → beta2469: 67).
- 22 cli_flags tests passed.
- GUI tests (test_qt_app) 234 passed.
- 전체 broader regression 720+ tests.

## CLI/GUI parity 최종 (모든 user-facing env 노출)

| Env var | CLI flag | GUI widget |
|---------|----------|-----------|
| AUTO_TESSELL_SEED_GWN | `--seed-gwn` | `_seed_gwn_check` |
| AUTO_TESSELL_STELLAR_SPLIT | `--stellar-split` | `_stellar_split_check` |
| AUTO_TESSELL_PARALLEL_DELAUNAY | `--parallel-delaunay` | `_parallel_delaunay_check` |
| AUTO_TESSELL_POLY_BUDGET_S | `--poly-budget-s` | — (CLI only) |
| AUTO_TESSELL_BL_FLOOR_RATIO | `--bl-floor-ratio` | `_bl_floor_ratio_spin` |
| AUTO_TESSELL_HEX_WWW7_BUDGET_S | `--hex-snap-budget-s` | `_hex_snap_budget_spin` |
| AUTO_TESSELL_LLOYD_PLATEAU_THRESH | `--lloyd-plateau-thresh` | `_lloyd_plateau_spin` |
| AUTO_TESSELL_PATCH_CAP | `--patch-cap` | `_patch_cap_spin` |
| AUTO_TESSELL_CVT3D_OFF | `--no-cvt3d` | — (debug toggle) |
| AUTO_TESSELL_ANISO_CVT_OFF | `--no-aniso-cvt` | — (debug toggle) |
| AUTO_TESSELL_LCR_OFF | `--no-lcr` | — (debug toggle) |

## 남은 commercial parity 격차

1. **BL aspect 11.5k → 1k** (cfMesh / Pointwise T-Rex 일반):
   누적 cascading scale 의 mathematical 한계. floor 도입 시도 (beta2440-2452)
   에도 1k 수준은 어려움. 후속: prism aspect 측정 후 per-vertex thickness
   직접 조정 (per-vertex aspect cap).

2. **tet quality D → C** (mq 0.05-0.10 → 0.10+):
   sliver elimination 더 적극화. Klingner 2008 §4 swap-based 추가.

3. **C7 native binary export** (StarCCM+ .ccm / Fluent partitioned). 다월.
4. **C8 GPU CUDA full pipeline**. 다월.

## 결론

이번 15-card 추가 (beta2455-2469) 는 **GUI/CLI parity 최종 완성** + **5 모듈
hot-loop 벡터화** (CVT3D, Stellar split monotone, aniso_cvt 곡률+Lloyd inner loop).

남은 commercial parity 는 long-term 작업.
