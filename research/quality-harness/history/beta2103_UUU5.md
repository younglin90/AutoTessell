# CARD UUU5 (beta2103) — native_tet input face split helper (skeleton, default OFF)

**target_engine**: tet
**모티프**: Hu 2018 fTetWild §3.1 — input face split (시퀀스 #5)

## 이론적 근거
- UUU4 의 candidate 리스트에서 op=="split" 만 골라 face split.
- face split: triangle (a,b,c) 의 self-intersect edge midpoint 추가 → 2 triangle 분할.
- mesher 의 입력 F 자체를 변경하므로 tet 결과에 영향, 위험 큼.
- 본 카드는 **helper 정의 + 모듈 상수 default OFF**. 호출 site 없음 (UUU6 에서 활성).
- 단조 가드 (UUU6 활성 시): worst_mq ≥ pre×0.99, mean_mq ≥ pre×0.99, hausdorff_rel ≤ pre×1.10.
- max_split=20 매우 보수적.
- novelty 3, rigor 3, impact 3 → 합 9 (paper-worthy).

## 변경
- 파일: `core/preprocessor/native_remesh/__init__.py`
- 위치 1: 모듈 상수 `_UUU5_FACE_SPLIT = False` (default OFF) 추가.
- 위치 2: helper `_apply_face_split(V, F, candidates, max_split=20) -> (V_new, F_new, n_split)` 정의.
  1. candidates 중 `op=="split"` 만 필터.
  2. 최대 `max_split` 개로 truncate.
  3. 각 split 마다 face 의 가장 긴 edge midpoint 를 V 에 추가, F 를 (a,b,m)+(a,m,c) 로 교체.
  4. 호출 site 없음 (UUU6 활성 카드에서 mesher entry 에 삽입 예정).
- `__all__` 에 `_UUU5_FACE_SPLIT`, `_apply_face_split` 추가.

## 검증 명령
```bash
timeout 60 python3 -c "from core.preprocessor.native_remesh import _apply_face_split, _UUU5_FACE_SPLIT; print('OK', _UUU5_FACE_SPLIT)"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py -q
```

## 합격 기준
- 회귀 PASS (스켈레톤, 호출 site 없음).
- bench 시간 ≤ 720s.
- mq/hausdorff 영향 없음 (default OFF).
- `_UUU5_FACE_SPLIT is False` 확인.
