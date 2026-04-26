# CARD UUU7 (beta2112) — face split 후 1-pass Laplacian cleanup

**target_engine**: tet
**모티프**: Hu 2018 fTetWild §3.1 + 자체 — face split 후 cleanup (시퀀스 #7)

## 이론적 근거 (≤8줄)
- UUU6 의 `_apply_face_split` 는 긴 edge midpoint 에 새 vertex 를 삽입.
- midpoint 는 곡률 무시 → 결과 face aspect ratio 가 큼.
- 새 vertex 위치를 1-ring 인접 vertex 의 uniform Laplacian 평균으로 1-pass 이동.
- 단조 가드: 이동 후 Hausdorff envelope 위반 시 원래 midpoint 로 롤백.
- novelty 1 (smoothing 적용), rigor 2 (envelope 가드), impact 2 (split face 품질) → 합 5.

## 변경
- 파일: core/preprocessor/native_remesh/__init__.py
- 함수: `_apply_face_split` (line ~151)
- 핵심 변경:
  1. split 결과 새 vertex index 수집 (midpoint 삽입 시점 기록).
  2. 새 vertex 별 1-ring 이웃 평균 좌표 계산 → 이동.
  3. envelope (hausdorff_tol) 위반 시 원위치 복귀.

## 검증 명령
```bash
timeout 60 python3 -c "from core.preprocessor.native_remesh import _apply_face_split; print('OK')"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 720s
- tet metric (worst mq) 동등 또는 +0.005 이상
- BL 영향 없음 (BL 합격 분포 동등)
- novelty+rigor+impact ≥ 5
