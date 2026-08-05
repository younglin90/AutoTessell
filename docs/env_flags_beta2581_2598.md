# Auto-Tessell — beta2581-2598 environment flags & ML models

beta2581 (P1 sprint) 부터 beta2598 (E3 GPU envelope wire) 까지 추가된 18 카드의
환경변수 + model 사용법 모음.

## env flags 요약 (default OFF)

| 환경변수 | 카드 | 기본값 | 효과 |
|---------|------|--------|------|
| `AUTO_TESSELL_HEX_SMALL_FLOOR` | P1.1 | 50 | hex small-bbox auto-escalate floor |
| `AUTO_TESSELL_STELLAR_SPLIT` | P2.1 | **1 (ON)** | Stellar 4-op split-pass — D 셀 회복 |
| `AUTO_TESSELL_CVT3D_QUALITY_WEIGHT` | P3.1 | 0 | Lloyd CVT 3D quality-weighted target |
| `AUTO_TESSELL_LCR_AUTO_REDUCE` | P3.3 | 0 | BL global num_layers majority reduction |
| `AUTO_TESSELL_BL_ANISO_SPLIT` | P3.4 | 0 | 실 prism layer-uniform subdivide |
| `AUTO_TESSELL_BL_ANISO_SPLIT_THRESH` | P3.4 | 4.0 | aspect threshold (위 flag 의 동작 임계) |
| `AUTO_TESSELL_HEX_CASTELL_MAX` | E1 | (auto) | castellated max_refine override |
| `AUTO_TESSELL_GPU_ENVELOPE` | E3 | 0 | Envelope.contains_points GPU fast-path |
| `AUTO_TESSELL_ML_SMOOTH_MODEL` | AI-V1.C | (path) | ML tet smoothing predictor model 경로 |
| `AUTO_TESSELL_BL_PREDICT_MODEL` | AI-V3.C | (path) | BL collision predictor model 경로 |

## ML model 학습 + 배포 (D1-D6)

```bash
# 1. dataset 수집 (~30s — 7 STL × 200 sample)
python3 scripts/collect_ml_dataset.py --stl-dir /tmp/ml_train_stls --n-samples-per-mesh 200 --max-meshes 7

# 2. quality predictor 학습 (~5s, CUDA)
python3 scripts/train_quality_predictor.py --epochs 50

# 3. BL collision dataset
python3 scripts/collect_bl_dataset.py

# 4. BL predictor 학습
python3 scripts/train_bl_predictor.py --epochs 50

# 5. 활성화
export AUTO_TESSELL_ML_SMOOTH_MODEL=assets/models/ml_smooth_model.pt
export AUTO_TESSELL_BL_PREDICT_MODEL=assets/models/bl_predictor.pt
auto-tessell run input.stl --mesh-type tet --quality fine ...
```

## GUI advanced panel

PySide6 GUI 의 advanced panel 에 5 신규 입력 노출 (beta2594):
- QCheckBox × 3: CVT3D_QWEIGHT / LCR_AUTO_REDUCE / BL_ANISO_SPLIT
- QLineEdit × 2: ML_SMOOTH_MODEL / BL_PREDICT_MODEL (path)

## SOTA 격차 vs 카드 매핑

| SOTA 격차 | 해결 카드 |
|----------|----------|
| Tet quality grade A (Klingner §4 sliver swap) | P1.3 + P2.1 + P3.1 + AI-V1.C |
| Hex small-bbox skewness | P1.1 + E1 (castellated auto-scale) |
| Poly extreme tier 회복 | P1.2 + P2.6 |
| BL aspect 1k 미달 | P3.3 + P3.4 + AI-V3.C |
| GPU envelope speedup | C8-2.1.2 (Eberly + compile) + E3 |
| StarCCM+ binary export | C7-1.3 (native variant 6-block) |

## 검증된 ML pipeline

| Pipeline | 검증 결과 |
|---------|----------|
| `predict_quality_batch` | val_loss 0.005 (CUDA) — 5.5k MLP (20→1) |
| `predict_bl_collision_distances` | val_loss 0.002 (CUDA) — 5k MLP (12→1) |
| `gpu_envelope_check_accurate` | (0,0,0)→z=1 평면 거리 1.0 정확 (Eberly + compile) |
| `Envelope.contains_points` (GPU) | inside/outside 정확 판별 (env=1 시) |

## 회귀 status (BETA2598 기준)

- **226+ tests PASS** (tet/hex/poly/ai/cvt3d/SI/repair/snap/BL helpers).
- preexisting 2건 (BLConfig defaults stale) — 무관.
