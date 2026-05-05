# CARD UUU1 (beta2098) — native_tet input self-intersect detect skeleton

**target_engine**: tet (input pre-processing)
**모티프**: Hu 2018 fTetWild §3.1 — input simplification / self-intersect detect (시퀀스 #1, 스켈레톤)

## 이론적 근거
- native_tet 의 hard mesh worst tet (mq ~0.082) 본질적 원인이 input surface
  self-intersect 에 있을 가능성. fTetWild 는 §3.1 에서 입력의 self-intersect 를
  사전 검출/분할 후 BSP 진입.
- 본 카드 (스켈레톤): self-intersect 검출 helper 만 추가, default OFF, 호출 안 함.
- 다음 카드 (UUU2): 검출 활성 + segment 분할 cleanup.
- novelty 2, rigor 3, impact 3 → 합 8.

## 변경
- 파일: core/preprocessor/native_remesh/__init__.py
- 핵심 변경 (≤80줄):
  1. 모듈 상수 `_UUU1_SI_DETECT = False` 추가
  2. helper `_detect_self_intersections(V: np.ndarray, F: np.ndarray) -> np.ndarray`
     정의: triangle AABB pair 탐색 → Möller tri-tri intersect → intersecting
     face index pair (M,2) 반환. 호출 사이트 없음.
  3. 모듈 어디에서도 호출하지 않음 (다음 카드에서 활성).

## 검증 명령
```bash
timeout 60 python3 -c "from core.preprocessor.native_remesh import _detect_self_intersections; import numpy as np; V=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float); F=np.array([[0,1,2],[0,1,3]],int); print('OK', _detect_self_intersections(V,F).shape)"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 720s (영향 없음, 스켈레톤)
- tet worst mq 동등 (호출 안 하므로 변동 없음)
- BL 영향 없음
