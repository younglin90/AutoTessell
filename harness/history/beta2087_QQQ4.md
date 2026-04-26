# CARD QQQ4 (beta2087) — BL local thickness adaptation 스켈레톤

**target_engine**: tet (BL)
**모티프**: Loseille & Löhner 2013 §4 — local thickness adaptation (advancing layer, 시퀀스 #3 스켈레톤)

## 이론적 근거

- 현 BL thickness 는 globally fixed (per-vertex scale 만 존재). collision 검출된 prism 영역은 thin (×0.5) 로 줄여 정합 보장이 산업 mesher 표준.
- 본 카드는 **스켈레톤** — local thickness factor 인프라만 추가, default OFF (`_BL_QQQ4_LOCAL_THICKNESS=False`).
- 다음 카드 (QQQ5) 에서 collision_mask 와 wiring 후 활성화.
- novelty 2, rigor 3, impact 3 → 합 8.

## 변경

- 파일: `core/layers/native_bl.py` (단일)
- 위치 1: 모듈 상수 `_BL_QQQ4_LOCAL_THICKNESS = False` (top-level).
- 위치 2: helper `_local_thickness_factor(collision_mask, n_vertices, thin_factor=0.5) -> np.ndarray`.
  - collision_mask True 인 vertex 는 `thin_factor`, 나머지는 1.0.
  - 반환 shape (n_vertices,) per-vertex factor.
- 호출 site 추가 없음 (스켈레톤). default OFF guard 만.

## 검증 명령

```bash
timeout 60 python3 -c "from core.layers.native_bl import _local_thickness_factor; import numpy as np; m=np.array([True,False,True]); f=_local_thickness_factor(m,3); assert f.tolist()==[0.5,1.0,0.5]; print('OK')"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py -q
```

## 합격 기준

- 회귀 PASS (1328 tests baseline 동등).
- bench 시간 ≤ 720s (현 58.8s 대비 여유).
- BL 영향 없음 (스켈레톤, default OFF, BL 합격 분포 동등).
- 추가 import / 외부 의존 없음.
