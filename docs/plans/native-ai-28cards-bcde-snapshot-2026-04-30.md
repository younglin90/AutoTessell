# native_ai 28-card B/C/D/E Snapshot (2026-04-30, beta2578)

## 사용자 결정 → 결과

원 요청: 표 6 항목 + native_ai + B/C/D/E 동시 진행.

**달성**:
- 표 6 항목 entry point 완성
- native_ai 모듈 + V1/V2/V3/V4 + AI-V1.1.1/1.2/1.3 real impl
- **B (AI-V1.4)** + **C (AI-V3.1)** + **D (C8-2.1.2)** + **E (C7-1.3)** 모두 first card 시작
- **CUDA backend 4 영역 모두 동작 확인**
- 29 native_ai unit tests PASS

## 28 카드 (beta2552-2578) 세션 요약

### Foundation (10 카드)

| beta | 영역 | 내용 |
|------|------|------|
| 2552 | native_ai skeleton | mesh_type dispatch API |
| 2553 | BL3 ratio env | 3a.1 |
| 2554 | tests 6 | basic |
| 2555 | tier_native_ai | pipeline 통합 |
| 2556 | strategist | tier_selector 등록 |
| 2557 | Qt GUI | engine list |
| 2564 | tests 12 (확장) | ML predictor + GPU env |
| 2566 | snapshot 1 | 16 카드 |
| 2568 | tests 17 (V1.1+V4) | feature + diffusion |
| 2576 | snapshot 2 | 26 카드 |

### AI-V1 series (8 카드, end-to-end 작동)

| beta | 카드 | 동작 |
|------|------|------|
| 2559 | V1 skeleton | predictor MLP 20→1 |
| 2560 | V1 wire | mesher hookup |
| 2567 | V1.1 stub | extract_tet_features |
| 2569 | V1.1.1 real | context_8 1-ring stats |
| 2570 | V1.1.2 real | dataset .npz save |
| 2571 | tests | dataset gen |
| 2572 | V1.1.3 real | train_quality_predictor |
| 2573 | V1.2 real | load + predict |
| 2574 | tests | train + inference end-to-end |
| 2575 | V1.3 real | swap candidate score |

End-to-end: gen → train (CUDA, val_loss 0.047) → save → load → predict (true 0.573 → pred 0.525).

### AI-V2/V3/V4 (3 카드)

| beta | 카드 | 내용 |
|------|------|------|
| 2558 | V2 wire | MeshGPT L3 (existing pipeline 자동 활성) |
| 2562 | V3 skeleton | BL collision predictor MLP 12→1 |
| 2565 | V4 stub | DDPM tet generator architecture sketch |

### B/C/D/E 4 영역 동시 진입 (3 카드)

| beta | 영역 | 내용 |
|------|------|------|
| 2577 | **B+C+D+E kickoff** | 4 영역 first card 동시 commit |
| 2578 | tests | 5 단위 테스트 추가 (24→29) |

#### 영역별 동작 검증

| 영역 | 모듈 | 동작 결과 |
|------|------|----------|
| **B** AI-V1.4 production ML | `bench_ml_pipeline.py` | 100 samples × 3 epochs, val_loss 0.047, **torch_cuda** |
| **C** AI-V3.1 BL collision dataset | `bl_collision_data.py` | (4, 12) features + finite gaps |
| **D** C8-2.1.2 GPU point-to-tri | `gpu_point_to_tri.py` | 20 query × 5 face → mean_dist 0.301, **torch_cuda** |
| **E** C7-1.3 binary .ccm | `mesh_exporter_starccm.py` | magic + size header + point block 작성 (Siemens 비공개 포맷) |

### C7/C8 (2 카드)

| beta | 카드 | 내용 |
|------|------|------|
| 2561 | C7-1.2 ASCII .ccm.txt | zone dump writer |
| 2563 | C8-2.1 GPU envelope | torch.cdist (CUDA 동작) |

## 사용 방법 (확장)

```python
from core.generator.native_ai import (
    # Volume mesh
    generate_native_ai_volume, AIVolumeConfig,
    # ML training
    generate_dataset_from_meshes, train_quality_predictor,
    load_trained_predictor, predict_quality_batch,
    # Production bench (B)
    run_ml_pipeline_bench,
    # BL collision (C)
    extract_bl_collision_features, generate_bl_collision_dataset,
    # GPU envelope + point-to-tri (C8 = D)
    gpu_envelope_check, gpu_point_to_tri_distance,
    # Swap score (V1.3)
    score_swap_candidates, select_top_k_swaps,
)
```

## 회귀 status

- **29 native_ai unit tests PASS** (config / dispatch / ML pipeline / BL / GPU / diffusion stub / B-E first cards)
- 237 Qt + 8 skipped PASS
- 31 native_tet regression PASS

## 잔여 multi-week 카드 (B/C/D/E 다음 단계)

| 영역 | 다음 카드 | 시간 |
|------|----------|------|
| B | Thingi10K real iteration → 10k+ samples | 1-2일 |
| C | BL collision predictor train (5k samples) + native_bl wire | 1-2주 |
| D | GPU pt-to-tri full Eberly 7-region (현재 simplified) | 1-2주 |
| D | custom .cu kernel via triton 또는 nvcc | 2-3개월 |
| E | StarCCM+ binary .ccm spec reverse-engineering | 1-2개월 |
| E | StarCCM+ 실제 simulation 검증 | 1개월 |

## 결론

- 사용자 표 6 항목 + B/C/D/E 모두 entry point 마련
- native_ai = full ML pipeline + 4 production stubs + CUDA 검증
- 28 카드 / 1 세션 / 29 tests PASS / regression clean
- 잔여 multi-week 작업 = 5-10 dedicated weeks
