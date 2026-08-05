# G-series 카드 — BETA2602+ 잔여 SOTA 격차 메우기 (2026-04-30)

## Context

BETA2601 까지 52+ 카드 (P1+P2+P3+AI+E1/E3+F4 CCMIO 등) 완료.
현재 187+ tests PASS, ML pipeline live, 6-block binary .ccm + CCMIO HDF5 완성.

**남은 SOTA 격차** (이전 로드맵 기준):
1. BL aspect 11.5k → 1k 미달성 (per-vertex thickness 알고리즘 redesign)
2. Mixed-element mesh (tet+hex+pyramid 인터페이스) 부재
3. AI-V1.A 10k+ Thingi10K samples 미수집 (현재 1.4k)
4. ML smoothing 실 효과 -delta (작은 dataset 한계)
5. CUDA .cu kernel 부재 (현재 torch.compile 만)
6. GUI 실시간 quality metric 부재
7. CLI 통합 안내 부재
8. CGNS HDF5 호환 layer 부재

## Goal

**잔여 SOTA 격차 8개 중 측정 가능한 6개 메우기**. 각 카드 = atomic edit + 회귀 PASS.

## Scope

- `core/layers/native_bl.py` — BL aspect 알고리즘
- `core/generator/native_*` — mixed-element 인터페이스
- `core/generator/native_ai/` — ML 학습 강화
- `core/utils/` — CGNS layer
- `scripts/` — 자동화 스크립트
- `desktop/qt_app/` — GUI 메트릭
- `cli/` — CLI 통합 가이드
- `tests/` — 회귀 테스트

## Metric

- **카드 완료 수** (10 카드 목표).
- **회귀 PASS** (≥187 tests).
- **ML pipeline 효과** (verify_ml_effect 의 min_q delta — 1k+ samples 학습 후 양의 delta 목표).

## Direction

higher is better (cards completed + tests passing).

## Verify

```bash
# unit regression (~30s)
timeout 120 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_hex.py \
    tests/test_native_poly.py tests/test_native_ai.py tests/test_cvt3d_aniso_cvt.py \
    tests/test_self_intersect.py tests/test_native_repair.py tests/test_native_hex_snap.py -q

# ML retrain + verify (~5-10s)
python3 scripts/collect_ml_dataset.py --max-meshes 20  # if STL 사용 가능
python3 scripts/train_quality_predictor.py --epochs 50
python3 scripts/verify_ml_effect.py
```

## 카드 (G1-G10)

| ID | 카드 | 시간 | 변경 파일 | 효과 |
|----|------|------|----------|------|
| **G1** | BL per-vertex first_thickness aspect-aware scaling | 1h | `core/layers/native_bl.py` (~30 줄) | aspect_max ↓ |
| **G2** | mixed-element pyramid interface helper | 1h | `core/layers/mixed_pyramid.py` (NEW ~120 줄) | tet+hex 호환성 |
| **G3** | AI-V1.A larger dataset 자동 수집 (35+ STLs) | 1h | `scripts/collect_ml_dataset.py` (확장) | 1.4k → 7k+ samples |
| **G4** | AI-V1.B retrain + ml_effect re-verify | 30min | (자동 트리거) | min_q delta 양수 목표 |
| **G5** | CGNS HDF5 호환 layer (CFD 표준) | 1.5h | `core/utils/cgns_writer.py` (NEW ~250 줄) | NASA/ANSYS Fluent import 가능 |
| **G6** | GUI 실시간 quality metric panel | 1h | `desktop/qt_app/main_window.py` (~50 줄) | 사용자 즉시 메트릭 시각화 |
| **G7** | CLI ML model 통합 옵션 | 30min | `cli/run.py` (~20 줄) | `--ml-smooth-model` flag |
| **G8** | bench_difficulty_tiers 빠른 모드 | 30min | `tests/stl/bench_difficulty_tiers.py` (~30 줄) | --quick (5 STL × tet only) |
| **G9** | docs/guides/usage.md 통합 사용 가이드 | 30min | `docs/guides/usage.md` (NEW) | 사용자 전체 워크플로 가이드 |
| **G10** | 최종 통합 회귀 + 결과 정리 | 30min | (commit only) | 187+ tests PASS 재확인 |

총: ~7-8 시간 작업, 10 카드, atomic edits.

## 합격 기준

각 카드 끝마다:
1. unit regression PASS (≥ baseline)
2. git commit (BETA2602-BETA2611)
3. 다음 카드 진행

연속 3 카드 fail 시 plan 중단 + 사용자 보고.

## 의존성

```
G1 (independent)  ─┐
G2 (independent)  ─┤
G3 → G4 (G3 needed first)
G5 (independent)  ─┤
G6, G7, G8, G9 (independent)
G10 (last — final check)
```

병렬 가능 카드 많음 — 시퀀셜 진행 (BETA 순서대로).
