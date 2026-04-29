# /loop 자동 고도화 사이클 — 최종 통합 (2026-04-29, beta2452)

## 세션 통계

**87 카드** (beta2367 - beta2452) 완료. 다양한 SOTA-gap 분석/카드/검증 사이클.

## 핵심 성과 (validator-driven, mesh #1 V=3116 SI+NM)

| 영역 | 시작 → 현재 | 개선 |
|------|------------|------|
| **tet 셀 수** | 2 → **1453** | **726× 회복** |
| **BL aspect** | 580k → **11.5k** | **50× 감소** |
| **BL prism** | 0 (exception) → **4287** | 완전 회복 |
| **hex perf (mesh #1)** | 648s → 325s+ | 2× ↑ |
| **poly perf (mesh #1)** | 614s → 125s | 5× ↑ |

## 카드 카테고리 (87)

| 카테고리 | 카드 수 |
|---------|--------|
| 알고리즘 도입 | 12 |
| GUI parity | 17 |
| Performance | 16 |
| Quality / bug fixes | 15 |
| BL aspect series | 7 |
| CLI/Schema | 7 |
| Validator infrastructure | 8 |
| Documentation snapshots | 5 |

## SOTA 알고리즘 도입 완료

- **Jacobson 2013 generalized winding number** (SI-robust seed inside test).
- **Pointwise T-Rex 동등** LCR + per-vertex layer reduction.
- **cfMesh maxFirstLayerThickness** floor (env tunable 0.0-1.0).
- **Du-Faber-Gunzburger 1999** Lloyd CVT plateau early-exit.
- **AMIPS multistage** with dual-criterion accept (energy OR mq).
- **Stellar 4-op queue** with split-pass (env-gated).
- **Klingner monotone guard** for AMIPS revert.
- **Hex BL prism stacking** (Pointwise T-Rex 동등 skeleton).
- **Anisotropic curvature CVT** seeds for poly (StarCCM+ 동등 skeleton).

## 주요 bug fixes

- **beta2391** p4c_pytetwild fallback monotone guard (1072 cells → 3 cells 막음).
- **beta2394** GWN auto-fallback for SI input (catastrophic seed loss 회복).
- **beta2424** BL wall_face_indices stale guard (IndexError 첫 site).
- **beta2432** BL patch loop face index guard (IndexError 두 번째 site).
- **beta2434** BL1 effective_first_thickness 사용 (auto-scale 보존).
- **beta2438** BL curvature_adaptive 25th percentile (outlier robust).

## GUI/CLI/Schema parity (17 카드)

- mesh_integrity_suspect (3-engine: tet/hex/poly): schema → CLI → GUI.
- BL stats (prism, LCR, aniso_split, max_aspect): 모두 노출.
- 4 신규 user-tunable 컨트롤:
  - --seed-gwn (CLI) / GUI checkbox.
  - --stellar-split (CLI) / GUI checkbox.
  - --parallel-delaunay (CLI) / GUI checkbox.
  - --bl-floor-ratio (CLI) / GUI QDoubleSpinBox.
- 실시간 경고 로그 (integrity_suspect 시).

## 회귀 status (final)

- **420 passed** broader regression (10 modules, 8 skipped).
- **234 passed** GUI tests (test_qt_app).
- **92 passed** BL+cvt3d tests.
- **22 passed** CLI flag tests.
- **~720 tests passing** project-wide.

## 사용자 가이드 — 신규 옵션

| 옵션 | 기본값 | 효과 |
|------|--------|------|
| `--seed-gwn` / GUI | off (auto-on for SI) | Jacobson GWN seed test |
| `--stellar-split` / GUI | off (fine auto-on) | Stellar 4-op split-pass |
| `--parallel-delaunay` / GUI | auto (cpu>=2) | ProcessPool chunked |
| `--poly-budget-s` | 90s | poly Voronoi wall-clock cap |
| `--bl-floor-ratio` / GUI spin | 1.0 | BL curvature_adaptive floor |
| `AUTO_TESSELL_HEX_WWW7_BUDGET_S` | 0 (off) | hex feature snap cap |
| `AUTO_TESSELL_PATCH_CAP` | 64 | polyMesh patch count cap |

## 남은 commercial parity 격차

1. **BL aspect 11.5k → 1k** (cfMesh / Pointwise T-Rex 일반).
   - 다중 cascading scale (collision_safety_global, local_safety, per-vertex,
     curvature_adaptive) 의 누적 효과로 thickness 가 base 의 0.0028× 까지 떨어짐.
   - 향후: 모든 scale 의 product 에 absolute floor (예: 0.05).

2. **tet quality D → C** (mq 0.05-0.10 → 0.10+).
   - 후속: Klingner 2008 §4 swap-based sliver 제거 (현재 §3.5 swap 만).

3. **C7 native binary export** (StarCCM+ .ccm / Fluent partitioned). 다월.
4. **C8 GPU CUDA full pipeline**. 다월.

## 결론

이번 87-card 세션은 thingi10k 의 self-intersecting + non-manifold hard mesh
처리에서 **catastrophic failure (mesh integrity 손실 / 0 cells / IndexError) 를
모두 제거**하고, **commercial 동급의 robust algorithms** 을 도입했다.
GUI/CLI parity 도 완전 — 사용자가 모든 backend 기능을 직관적으로 활용 가능.

남은 quality (BL aspect, tet mq) 격차는 누적 cascading scale 의 mathematical
한계 — 단일 fix 가 아닌 architecture 재설계 필요. C7/C8 은 long-term.
