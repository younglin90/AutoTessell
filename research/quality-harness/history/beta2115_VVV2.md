# CARD VVV2 (beta2115) — Stellar queue 활성 (build + log only)

**target_engine**: tet
**모티프**: Klingner & Shewchuk 2008 §3 — Stellar 4-op queue 활성 (시퀀스 #2, log only)

## 이론적 근거
- VVV1 에서 `_build_op_queue` / `_apply_op_queue` skeleton + `_VVV1_STELLAR_QUEUE=False`
  helper 만 추가 (R56 PASS). 본 카드는 flag 를 True 로 전환하고 mesher.py 의 final_pts/
  final_tets 확정 직후 (boundary_clip 직전) `_build_op_queue` 1 회 호출 → queue 길이 + 최저
  quality 만 log. `_apply_op_queue` 호출은 다음 카드 (VVV3) 로 분리.
- Read-only build → 메쉬 위상/좌표 불변. 회귀/품질 metric 동등 보장.
- novelty 1, rigor 2, impact 1 → 합 4 (skeleton → 활성 최소 단계).

## raw 시그니처 발췌 (stellar.py)
```python
_VVV1_STELLAR_QUEUE: bool = False  # → True

def _build_op_queue(pts: np.ndarray, tets: np.ndarray) -> list[dict]:
    # 반환: [{"quality": float, "tet_idx": int, "candidate_ops": list[str]}, ...] 오름차순
```

## mesher.py 호출 위치 (line ~2260)
RRR2 블록 끝 (line ~2240), `if enable_boundary_clip:` (line 2262) 직전.

## 변경
- 파일 1: `core/generator/native_tet/stellar.py`
  - line 10: `_VVV1_STELLAR_QUEUE: bool = False` → `True`
- 파일 2: `core/generator/native_tet/mesher.py`
  - line ~2260 (RRR2 블록 끝, `if enable_boundary_clip:` 직전) 에 삽입:
    ```python
    # VVV2 — Stellar queue build (log only, no apply)
    if os.environ.get("AUTO_TESSELL_VVV2_QUEUE", "1") != "0":
        try:
            from core.generator.native_tet.stellar import (
                _VVV1_STELLAR_QUEUE, _build_op_queue,
            )
            if _VVV1_STELLAR_QUEUE:
                _q = _build_op_queue(final_pts, final_tets)
                _worst = float(_q[0]["quality"]) if _q else 0.0
                log.info(
                    "native_tet_stellar_queue",
                    n_queue=len(_q),
                    worst_q=_worst,
                )
        except Exception as exc:
            log.debug("native_tet_stellar_queue_skipped", reason=str(exc))
    ```
- 변경 라인: ≤22 (mesher 18 + stellar 1)

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_tet.stellar import _build_op_queue, _VVV1_STELLAR_QUEUE; print('OK', _VVV1_STELLAR_QUEUE)"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py -q
```

## 합격 기준
- 회귀 PASS (test_native_tet_amips.py 전체)
- bench 시간 ≤ 720s (현재 57.9s 대비 충분 여유)
- tet metric (worst_mq=0.082, grade C/D) 동등 — read-only 이므로 변동 0
- BL 영향 없음 (poly/hex 미영향)
- log 에 `native_tet_stellar_queue` event 1 회 출력 + n_queue ≥ 1
