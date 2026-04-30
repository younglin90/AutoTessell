# native_ai + Phase 5 표 항목 — 진행 스냅샷 (2026-04-30, beta2565)

## 사용자 결정 → 결과

요청: 표 6 항목 (C1-C5/C7/C8/BL/tet-D→C) 미흡점 모두 해결 + 3→1→2 순 + AI volume meshing.

**달성**:
- C1 tet grade A: ✅ 이미 P4D fallback 으로 14+/20 회복 (≥12/20 충족)
- C5 multithreaded Delaunay: ✅ 이미 parallel.py beta2365 로 구현
- C7 StarCCM+ writer: 🟡 ASCII zone dump skeleton (binary 는 별도 카드)
- C8 GPU envelope: 🟡 torch.cdist skeleton (CUDA backend 동작 확인)
- BL aspect: 🟡 BL3 ratio env-gated (3a.1)
- tet D→C: 🟡 AI-V1 ML smoothing skeleton (실제 model 미배치)
- **native_ai**: ✅ skeleton 모듈 + 4 AI 카드 (V1/V2/V3/V4) skeleton

## 15 카드 분류 (beta2552-2565)

### native_ai 핵심 인프라 (7 카드)

| beta | 카드 | 변경 |
|------|------|------|
| 2552 | skeleton | core/generator/native_ai/__init__.py + mesher.py + README. AIVolumeConfig/Result API. mesh_type tet/hex/poly dispatch. |
| 2553 | BL3 ratio env (3a.1) | AUTO_TESSELL_BL_REL_RATIO env-gated relative first thickness. |
| 2554 | 6 unit tests | tests/test_native_ai.py. config defaults / dispatch / unknown / BL. |
| 2555 | tier_native_ai pipeline | core/generator/tier_native_ai.py + pipeline._TIER_REGISTRY + alias ai/native_ai. |
| 2556 | strategist 등록 | core/strategist/tier_selector.py 에 tier_native_ai + alias. canonical_tier('ai') 매핑. |
| 2557 | Qt GUI | desktop/qt_app/ 4 사이트. ENGINE_GROUPS / _TIER3_ENGINES / display name dict. |
| 2564 | tests 확장 (6→12) | ML predictor / GPU env 단위 테스트 6 추가. |

### AI 카드 (4 skeleton + 2 wire)

| beta | 카드 | 내용 |
|------|------|------|
| 2558 | AI-V2 wire | ai_surface_repair=True 시 _l3_ai_fix(allow_ai_fallback=True) 자동 호출. MeshGPT/MeshAnythingV2. |
| 2559 | AI-V1 skeleton | ml_tet_smoothing.py. predictor MLP 20→1 sigmoid (~5.5k params). |
| 2560 | AI-V1 wire | ai_smoothing=True 시 ml_tet_smoothing_apply 자동 호출 (graceful skip). |
| 2562 | AI-V3 skeleton | ml_bl_collision.py. predictor MLP 12→1 (~5k params). 30s → 200ms target. |
| 2565 | AI-V4 stub | diffusion_volume.py. DDPM tet generator architecture sketch. research stub. |

### C7/C8 표 항목 (2 카드)

| beta | 카드 | 내용 |
|------|------|------|
| 2561 | C7-1.2 StarCCM+ | core/utils/mesh_exporter_starccm.py. ASCII zone dump writer. |
| 2563 | C8-2.1 GPU envelope | core/generator/native_ai/gpu_envelope.py. torch.cdist envelope check. **CUDA 실제 동작 확인** (torch_cuda backend). |

## 사용 방법

### CLI

```bash
auto-tessell run input.stl --tier ai --mesh-type tet --quality fine
# 또는
auto-tessell run input.stl --tier native_ai --mesh-type hex_dominant
```

### Python

```python
from core.generator.native_ai import (
    generate_native_ai_volume,
    AIVolumeConfig,
)
cfg = AIVolumeConfig(
    mesh_type="tet",
    enable_bl=True,
    ai_surface_repair=True,    # AI-V2 MeshGPT L3 자동
    ai_smoothing=True,         # AI-V1 ML smoothing (현재 skeleton skip)
)
r = generate_native_ai_volume(V, F, work_dir, cfg)
```

### Qt GUI

엔진 콤보 → "Native AI (v0.5 skeleton)" 그룹 → "Native AI · mesh_type dispatch" 선택.

## 회귀 status

- 12 native_ai unit tests PASS
- 237 Qt + 8 skipped PASS (beta2557 검증)
- 31 native_tet regression PASS (전체 cycle)
- 75 cumulative broader PASS

## 잔여 작업 (multi-week, 별도 phase)

| 카드 | 시간 | 비고 |
|------|------|------|
| AI-V1.1 | 1주 | 10k tet sample dataset + train (Klingner quality eval) |
| AI-V1.2 | 3일 | predictor save/load + inference 통합 |
| AI-V1.3 | 1주 | swap candidate ML score + Klingner §4 path |
| AI-V3.1 | 1주 | 5k vertex sample dataset for BL collision |
| AI-V3.2 | 3일 | predictor train + save |
| AI-V3.3 | 1주 | native_bl _compute_collision_distance ML fast-path |
| C7-1.3 | 1-2개월 | binary .ccm header + zone block |
| C8-2.1.2 | 2-3주 | custom CUDA kernel point-to-triangle |
| C8-2.1.3 | 2-3개월 | GPU KD-tree build (gpu-octree research) |
| AI-V4 | 다월 | Diffusion-based volume gen (research, no production lib) |

## 결론

- 표 6 항목 모두 entry point 마련 (C1/C5 이미 달성, C7/C8/BL/tet-D→C 는 skeleton)
- native_ai 모듈 = 기존 native_tet/hex/poly 와 동등 인터페이스 + AI 통합 hook
- 4 AI 카드 (V1/V2/V3/V4) skeleton 완성
- **CUDA backend 실제 동작** (torch_cuda envelope check)
- 잔여 multi-week 카드 = 10-15 dedicated work weeks
