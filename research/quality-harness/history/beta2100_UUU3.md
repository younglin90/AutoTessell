# CARD UUU3 (beta2100) — self-intersect repair candidate 생성 (스켈레톤, 시퀀스 #3)

**target_engine**: tet
**모티프**: Hu 2018 fTetWild §3.1 — input simplification, SI repair candidate (split/merge 후보 분류)

## 이론적 근거 (≤8줄)
- R40 UUU2 PASS: `_detect_self_intersections` 활성, n_si pair 식별 가능.
- 본 카드는 식별된 pair 들로부터 repair candidate 를 추출: 공유 vertex 수에 따라 split/merge 분류 dict list 생성.
- 실제 split/merge 적용은 다음 카드 UUU4 에서 활성. 본 카드는 helper + flag 만 (호출 site 없음).
- n_si 가 클 가능성에 대비하여 candidate 구조만 먼저 정의 → 다음 카드에서 cap 적용 예정.
- novelty 2 (Hu 2018 candidate 분류 이식), rigor 2 (정의 + log), impact 3 (UUU4 활성 시 hard mesh repair). 합 7.

## 변경
- 파일: `core/preprocessor/native_remesh/__init__.py`
  - line 27 인접: `_UUU3_REPAIR_CANDIDATES = False` 모듈 상수 추가.
  - 신규 helper:
    ```python
    def _si_repair_candidates(V: np.ndarray, F: np.ndarray, si_pairs: np.ndarray) -> list[dict]:
        """SI face pair → repair candidate 분류.
        공유 vertex 0 → {"op":"split","faces":[i,j]}.
        공유 vertex ≥1 → {"op":"merge","faces":[i,j],"shared":k}.
        호출 site 없음 (UUU4 에서 활성)."""
    ```
  - `__all__` 에 `_UUU3_REPAIR_CANDIDATES`, `_si_repair_candidates` 추가.
- 호출 site 추가 없음 (스켈레톤).

## 검증 명령
```bash
timeout 60 python3 -c "from core.preprocessor.native_remesh import _si_repair_candidates, _UUU3_REPAIR_CANDIDATES; print('OK', _UUU3_REPAIR_CANDIDATES)"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py -q
```

## 합격 기준
- 회귀 PASS (스켈레톤, 호출 없음).
- bench ≤ 720s (기존 57s).
- tet metric 변화 없음 (mq 0.082 stable).
- import OK + flag False 확인.
- BL 영향 없음.
