# CARD UUU4 (beta2101) — repair candidates 활성 + log only

**target_engine**: tet
**모티프**: Hu 2018 §3.1 — repair candidates 활성 (시퀀스 #4, log only)

## 이론적 근거
- UUU3 helper `_si_repair_candidates(V, F, si_pairs)` 가 이미 등록됨 (호출 site 없음).
- flag `_UUU3_REPAIR_CANDIDATES`: False → True.
- mesher.py UUU2 직후 (line ~204) 에 호출 추가, log only — 실제 split/merge 미적용.
- 산출물: `log.info("native_tet_uuu4_candidates", n_candidates=N, n_split=..., n_merge=...)`.
- 다음 카드 UUU5 에서 candidate 기반 face split 활성.
- novelty 1, rigor 2, impact 2 → 합 5.

## 변경
- 파일 1: `core/preprocessor/native_remesh/__init__.py`
  - line 28: `_UUU3_REPAIR_CANDIDATES = False` → `_UUU3_REPAIR_CANDIDATES = True`.
- 파일 2: `core/generator/native_tet/mesher.py`
  - 함수: `tetrahedralize` (UUU2 블록 직후, line ~204).
  - 핵심 변경:
    1. import 확장: `from core.preprocessor.native_remesh import _UUU1_SI_DETECT, _detect_self_intersections, _UUU3_REPAIR_CANDIDATES, _si_repair_candidates`.
    2. UUU2 try 블록 내부, `si_pairs` 계산 + log.info 직후에 분기 추가:
       ```python
       if _UUU3_REPAIR_CANDIDATES and len(si_pairs) > 0:
           cands = _si_repair_candidates(V, F, si_pairs)
           n_split = sum(1 for c in cands if c["op"] == "split")
           n_merge = sum(1 for c in cands if c["op"] == "merge")
           log.info("native_tet_uuu4_candidates",
                    n_candidates=len(cands), n_split=n_split, n_merge=n_merge)
       ```
    3. except 절은 기존 `native_tet_uuu2_si_detect_skipped` 그대로 흡수.

### 참고: UUU3 helper raw 시그니처 (이미 등록)
```python
def _si_repair_candidates(V: np.ndarray, F: np.ndarray, si_pairs: np.ndarray) -> list[dict]:
    # 공유 vertex 0 → {"op":"split","faces":[i,j]}
    # 공유 vertex ≥1 → {"op":"merge","faces":[i,j],"shared":k}
```
호출부 인자: `(V, F, si_pairs)` — UUU2 의 `si_pairs = _detect_self_intersections(V, F)` 결과 그대로 재사용.

## 검증 명령
```bash
timeout 60 python3 -c "from core.preprocessor.native_remesh import _si_repair_candidates, _UUU3_REPAIR_CANDIDATES; print('OK', _UUU3_REPAIR_CANDIDATES)"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py -q
```

## 합격 기준
- 회귀 PASS.
- bench 시간 ≤ 720s.
- tet metric (worst mq, grade) 변화 없음 (log only, 토폴로지 무변경).
- bench.txt / 로그에 `native_tet_uuu4_candidates` event + n_candidates 카운트 1건 이상 출현.
- BL 합격 분포 동등.
