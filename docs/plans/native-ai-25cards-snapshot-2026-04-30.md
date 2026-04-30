# native_ai 25-card Phase 5 — Final Snapshot (2026-04-30, beta2575)

## 사용자 요청 → 결과 요약

원 요청: 표 6 항목 (C1/C5/C7/C8/BL aspect/tet D→C) 미흡점 모두 해결 + native_ai 모듈.

**최종 상태**:
- C1, C5: ✅ 이미 P4D fallback / parallel.py 로 달성
- C7 StarCCM+: 🟡 ASCII zone dump skeleton
- C8 GPU: 🟡 torch.cdist envelope kernel **CUDA 동작 확인**
- BL aspect 3a.1: 🟡 BL3 ratio env-gated
- tet D→C: 🟡 AI-V1 ML smoothing **end-to-end 작동** (gen→train→save→load→predict)
- **native_ai**: ✅ skeleton + V1.1.1/V1.2/V1.3 real impl + V2/V3/V4 stub + tests

## 25 카드 누적 (beta2552-2575)

### Core Infrastructure (8 카드)

| beta | 카드 | 상태 |
|------|------|------|
| 2552 | native_ai skeleton | ✅ |
| 2553 | BL3 ratio env (3a.1) | ✅ |
| 2554 | 6 unit tests | ✅ |
| 2555 | tier_native_ai pipeline | ✅ |
| 2556 | strategist tier_selector | ✅ |
| 2557 | Qt GUI engine list | ✅ |
| 2564 | tests 12 (확장) | ✅ |
| 2566 | snapshot doc 1 | ✅ |

### AI-V1 ML-tet smoothing (8 카드, end-to-end 작동)

| beta | 카드 | 내용 |
|------|------|------|
| 2559 | AI-V1 skeleton | predictor MLP 20→1 sigmoid (5.5k params) |
| 2560 | AI-V1 wire | mesher hookup |
| 2567 | AI-V1.1 stub | extract_tet_features (Klingner quality 실제 계산) |
| 2569 | AI-V1.1.1 real | context_8 1-ring stats (incident/face area/dihedral) |
| 2570 | AI-V1.1.2 real | generate_dataset_from_meshes (.npz save/load) |
| 2572 | AI-V1.1.3 real | train_quality_predictor (Adam + MSE + val_split) |
| 2573 | AI-V1.2 real | load_trained_predictor + predict_quality_batch |
| 2575 | AI-V1.3 real | score_swap_candidates + select_top_k_swaps |

**End-to-end 검증**: gen→train→save→load→predict 동작. true=0.573 → pred=0.525 (5 epochs, CUDA).

### AI-V2/V3/V4 (3 카드, skeleton)

| beta | 카드 | 내용 |
|------|------|------|
| 2558 | AI-V2 wire | MeshGPT L3 surface repair 자동 활성 (`ai_surface_repair=True`) |
| 2562 | AI-V3 skeleton | ml_bl_collision predictor (12→1 MLP, 5k params, 30s→200ms target) |
| 2565 | AI-V4 stub | DDPM tet generator architecture sketch (research) |

### C7/C8 (2 카드)

| beta | 카드 | 내용 |
|------|------|------|
| 2561 | C7-1.2 StarCCM+ | ASCII .ccm.txt zone dump writer (binary 별도 카드) |
| 2563 | C8-2.1 GPU envelope | torch.cdist envelope check, **CUDA backend 실제 동작** |

### Tests (2 카드)

| beta | 카드 | 내용 |
|------|------|------|
| 2568 | tests V1.1+V4 | feature extraction + diffusion stub 테스트 (12→17) |
| 2571 | tests dataset gen | mesh → npz pipeline 테스트 (17→20) |
| 2574 | tests train+infer | end-to-end train/predict 자동 검증 (20→24) |

## 사용 방법

### Python

```python
from core.generator.native_ai import (
    generate_native_ai_volume, AIVolumeConfig,
    generate_dataset_from_meshes,
    train_quality_predictor,
    load_trained_predictor, predict_quality_batch,
    score_swap_candidates, select_top_k_swaps,
    gpu_envelope_check,
)

# (1) Volume mesh 생성 (AI dispatch — 현재 native_* 위임)
cfg = AIVolumeConfig(
    mesh_type="tet", enable_bl=True,
    ai_surface_repair=True,    # AI-V2 MeshGPT L3 자동
    ai_smoothing=True,         # AI-V1 ML smoothing wire (model 있으면)
)
r = generate_native_ai_volume(V, F, work_dir, cfg)

# (2) ML 학습 pipeline (AI-V1.1.1 ~ V1.2)
generate_dataset_from_meshes("/tmp/d.npz", mesh_pts_list, mesh_tets_list, samples_per_mesh=100)
train_quality_predictor("/tmp/d.npz", "/tmp/m.pt", epochs=50)
model = load_trained_predictor("/tmp/m.pt")
preds = predict_quality_batch(model, coords_array, context_array)

# (3) GPU envelope check (C8-2.1)
inside_mask, result = gpu_envelope_check(query_pts, surf_pts, surf_faces, eps=0.01)

# (4) Swap candidate ML score (AI-V1.3)
result = score_swap_candidates(model, pts, candidates_list)
top_k = select_top_k_swaps(result.scores, k=10, min_score=0.5)
```

### CLI

```bash
auto-tessell run input.stl --tier ai --mesh-type tet --quality fine
```

### Qt GUI

엔진 콤보 → "Native AI (v0.5 skeleton)" → "Native AI · mesh_type dispatch".

## 회귀 status

- **24 native_ai unit tests PASS** (config / dispatch / ML / training / inference / GPU / diffusion stub)
- 237 Qt + 8 skipped PASS
- 31 native_tet regression PASS

## CUDA 동작 확인 사항

✅ GPU envelope check: torch_cuda backend, 10× speedup estimate
✅ ML training: torch_cuda backend, 5 epochs train_loss 0.032 / val_loss 0.055
✅ ML inference: torch_cuda backend, true 0.573 → pred 0.525

## 잔여 multi-week 카드

| 카드 | 시간 | 비고 |
|------|------|------|
| AI-V1.4 | 1주 | 실제 swap_score 기반 Klingner §4 swap 통합 |
| AI-V3.1~V3.3 | 2-3주 | BL collision dataset / train / native_bl wire |
| AI-V2 production | 1주 | MeshGPT/MeshAnything 의 actual GPU 학습 활용 |
| C7-1.3 binary .ccm | 1-2개월 | format reverse-engineering |
| C8-2.1.2 CUDA kernel | 2-3주 | custom point-to-tri kernel |
| C8-2.1.3 GPU KD-tree | 2-3개월 | gpu-octree research |
| AI-V4 production | 다월 | DDPM tet generator 학습 + inference |

## 결론

- **표 6 항목 모두 entry point 마련** (C1/C5 이미 달성, C7/C8/BL/tet-D→C 는 actionable skeleton)
- **native_ai 모듈** = 기존 native_tet/hex/poly 와 동등 인터페이스 + AI 통합 hook
- **End-to-end ML pipeline 동작**: gen→train→save→load→predict (CUDA backend)
- 총 25 카드 / 1 세션 / 24 unit tests PASS / regression clean
- 잔여 multi-week 카드 = 5-10 dedicated weeks (사용자 별도 phase 결정 시 시작)
