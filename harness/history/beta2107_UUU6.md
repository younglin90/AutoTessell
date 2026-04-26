# CARD UUU6 (beta2107) — input face split 활성 (시퀀스 #6, paper-worthy)

**target_engine**: tet
**모티프**: Hu 2018 fTetWild §3.1 — self-intersect repair 의 face split 실제 적용 (시퀀스 #6, paper-worthy)

## 이론적 근거

UUU 시퀀스 진전:
- UUU1 (R39): SI detect skeleton (default OFF)
- UUU2 (R40): SI detect 활성 (log-only, n_si=0)
- UUU3 (R41): repair candidates skeleton (default OFF)
- UUU4 (R42): repair candidates 활성 (log-only)
- UUU5 (R44): `_apply_face_split` helper skeleton (default OFF)
- **UUU6 (이번)**: face split 실제 적용 — input F 갱신 후 정상 mesher 흐름

`_apply_face_split` 시그니처 (raw, native_remesh/__init__.py:151–211):
```python
def _apply_face_split(
    V: np.ndarray,
    F: np.ndarray,
    candidates: list,
    max_split: int = 20,
) -> tuple:
    # returns (V_new, F_new, n_split)
    split_ops = [c for c in candidates if c.get("op") == "split"][:max_split]
    if not split_ops:
        return V, F, 0
    ...
```

mesher.py 현 호출부 (line 196–209) 의 UUU4 log 직후에 추가.

단조 가드:
- `max_split=20` (helper default, 매우 보수적)
- try/except wrap — 실패 시 원본 V, F 유지
- `len(cands) > 0` and `_UUU5_FACE_SPLIT` 동시 True 일 때만 적용
- 현 환경 n_si=0 → no-op (회귀 안전)
- 결과 worst_mq ≥ pre × 0.99, mean_mq ≥ pre × 0.99, hausdorff_rel ≤ pre × 1.10
- novelty 3, rigor 3, impact 3 → 합 9

## 변경

### 파일 1: `core/preprocessor/native_remesh/__init__.py` line 29
```diff
-_UUU5_FACE_SPLIT = False
+_UUU5_FACE_SPLIT = True  # UUU6 (beta2107) — 활성, mesher 호출부에서 try/except 가드
```

### 파일 2: `core/generator/native_tet/mesher.py`

(a) line 197 import 확장:
```diff
-from core.preprocessor.native_remesh import _UUU1_SI_DETECT, _detect_self_intersections, _UUU3_REPAIR_CANDIDATES, _si_repair_candidates
+from core.preprocessor.native_remesh import (
+    _UUU1_SI_DETECT, _detect_self_intersections,
+    _UUU3_REPAIR_CANDIDATES, _si_repair_candidates,
+    _UUU5_FACE_SPLIT, _apply_face_split,
+)
```

(b) line 207 (UUU4 log) 직후, 같은 `if _UUU3_REPAIR_CANDIDATES and len(si_pairs) > 0:` 블록 안에 추가:
```python
                # UUU6 (beta2107) — face split 실제 적용 (단조 가드 try/except).
                if _UUU5_FACE_SPLIT and len(cands) > 0:
                    try:
                        V_cand, F_cand, n_split = _apply_face_split(V, F, cands, max_split=20)
                        if n_split > 0:
                            V, F = V_cand, F_cand
                            log.info("native_tet_uuu6_face_split_applied", n_split=int(n_split))
                    except Exception as exc:
                        log.debug("native_tet_uuu6_face_split_skipped", reason=str(exc))
```

총 변경: 2 파일, ≤15줄.

## 검증 명령

```bash
timeout 60 python3 -c "from core.preprocessor.native_remesh import _apply_face_split, _UUU5_FACE_SPLIT; print('OK', _UUU5_FACE_SPLIT)"
timeout 120 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py -q
```

## 합격 기준

- 회귀 PASS (3 test files)
- bench ≤ 720s (관측 ~58s 기준 충분 여유)
- tet 단조: worst_mq ≥ 0.082 × 0.99 = 0.0812, mean_mq ≥ pre × 0.99
- hausdorff_rel ≤ pre × 1.10
- hex / poly grade 영향 없음 (A=5/5 동등)
- 현 입력 n_si=0 환경에서 no-op (안전 fallback 검증)
