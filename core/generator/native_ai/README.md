# native_ai — Volume AI Mesh Generation

AI-assisted volume mesh (tet/hex/poly + BL) 모듈. native_tet / native_hex / native_poly 와 동등 인터페이스.

## 현재 상태 (2026-04, skeleton)

기존 native_* engine 으로 100% 위임. AI 적용 0%. ML 통합은 단계적.

## API

```python
from core.generator.native_ai import (
    generate_native_ai_volume,
    AIVolumeConfig,
)

cfg = AIVolumeConfig(
    mesh_type="tet",        # tet / hex / poly
    quality_level="standard",
    seed_density=8,
    enable_bl=True,
    bl_num_layers=3,
    # AI flags (현재 모두 미사용)
    ai_smoothing=False,
    ai_surface_repair=False,
    ai_collision_predict=False,
)
r = generate_native_ai_volume(V, F, work_dir, cfg)
print(r.n_cells, r.grade, r.backend, r.ai_applied)
```

## 로드맵

| 카드 | 변경 | 시간 |
|------|------|------|
| AI-V1 | ML-based tet smoothing (Klingner §4 swap + neural quality predictor) | 2-3주 |
| AI-V2 | MeshGPT/MeshAnything L3 integration → after-cleanup native_tet | 1주 |
| AI-V3 | ML-based BL collision predict (gap detection net) | 2주 |
| AI-V4 | Diffusion-based volume gen (research, no production lib) | 다월 |

## 참조 연구

- **MeshGPT** (Siddiqui et al., 2024) — surface autoregressive gen.
- **MeshAnything V2** (Chen et al., 2024) — surface 8K+ tri.
- **DeepCAD** — CAD reconstruction (not direct volume).
- **NeuralMesh / DiffusionNet** — surface deformation.
- **MeshSDF** — implicit surface, indirect volume potential.
- **ML-tet smoothing** (Nature Comp Sci 2023) — quality optimization.

## 정책

CLAUDE.md "외부 lib 신규 의존 금지" 정책 준수:
- torch (이미 의존) 만 사용
- meshgpt-pytorch / MeshAnythingV2 (이미 L3 fallback 으로 의존) 재사용
- 신규 ML lib 추가는 별도 검토

## 테스트

`tests/test_native_ai.py` (TBD) — skeleton API parity 검증.
