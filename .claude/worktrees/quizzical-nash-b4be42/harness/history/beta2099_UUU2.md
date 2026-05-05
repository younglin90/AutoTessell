# CARD UUU2 (beta2099) — self-intersect 탐지 활성 (식별만)

**target_engine**: tet
**모티프**: Hu 2018 fTetWild §3.1 — self-intersect 활성 (시퀀스 #2, 식별만)

## 이론적 근거 (≤8줄)
- R39 UUU1 PASS: `_detect_self_intersections` + `_moller_tri_tri` skeleton 도입 (default OFF).
- 본 카드는 flag 활성 + mesher 진입부에서 1회 호출, 결과는 log 만 (cleanup 미적용).
- novelty 1 (활성), rigor 2 (Möller 1997 정확), impact 2 (다음 cleanup 카드 기반) → 합 5.
- Möller tri-tri 는 인접 삼각형 (공유 edge/vertex) 제외 + AABB pre-filter.
- 다음 카드 UUU3 에서 실제 cleanup (split/snap) 적용 예정.

## UUU1 helper raw 시그니처 발췌
```python
# core/preprocessor/native_remesh/__init__.py
_UUU1_SI_DETECT = False  # → True 로 변경

def _detect_self_intersections(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Triangle AABB pair 탐색 → Möller tri-tri intersect → intersecting face index pair (M,2) 반환."""
    # AABB pre-filter + 공유 edge/vertex skip + _moller_tri_tri
    # returns shape (M, 2) intp pairs

def _moller_tri_tri(t1: np.ndarray, t2: np.ndarray) -> bool:
    """Möller 1997 triangle-triangle intersection (no coplanar handling)."""

__all__ = ["isotropic_remesh", "lloyd_cvt", "_UUU1_SI_DETECT", "_detect_self_intersections"]
```

## 변경
- 파일 1: `core/preprocessor/native_remesh/__init__.py`
  - line 27: `_UUU1_SI_DETECT = False` → `True`.
- 파일 2: `core/generator/native_tet/mesher.py` (입력 처리 진입부, `_prog("start", ...)` ~line 194 직후)
  - import: `from core.preprocessor.native_remesh import _UUU1_SI_DETECT, _detect_self_intersections`
  - try/except wrap, log only:
    ```python
    try:
        if _UUU1_SI_DETECT:
            si_pairs = _detect_self_intersections(V, F)
            log.info("native_tet_uuu2_si_detect", n_si=int(len(si_pairs)))
    except Exception as exc:
        log.debug("native_tet_uuu2_si_detect_skipped", reason=str(exc))
    ```

## 검증 명령
```bash
timeout 60 python3 -c "from core.preprocessor.native_remesh import _detect_self_intersections, _UUU1_SI_DETECT; print('OK', _UUU1_SI_DETECT)"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py -q
```

## 합격 기준
- 회귀 PASS
- bench ≤ 720s (기존 57.6s)
- tet metric 변화 없음 (식별만, mq 0.082 stable)
- bench.txt 에 `native_tet_uuu2_si_detect` + `n_si=<int>` 노출
- BL 영향 없음
