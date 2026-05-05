# CARD KKK1 (beta2073) — flip-only sliver removal cycle (BSP 후, vertex 위치 불변)

**target_engine**: tet
**모티프**: Klingner & Shewchuk 2008 §3 "Aggressive Tet Mesh Improvement" — flip-based sliver removal post-pass (Joe 1995 local transformation)

## 이론적 근거

- BSP 직후 잔여 sliver tet (Q≈0) 은 인접 edge swap 으로 4-vertex 집합 재구성 시 Q 향상 가능 (Joe 1995).
- AMIPS smoothing 은 vertex 위치를 이동시키므로 envelope/worst-mq 단조 가드를 매번 깨뜨림 (R1-R3 실증).
- Flip 연산은 **vertex 위치 변경 X** → boundary, hausdorff, locked_surface 자동 보존, worst-mq 악화 위험 0.
- novelty 1 (EEE1 의 flip_23/flip_32 1회씩에 cycle 1회 추가 + flip_44), rigor 2 (per-step 단조 가드), impact 2 (sliver flip 1-3% mq) → 합 5.
- AMIPS 계열 BSP 직후 호출 AVOID (4회째 동일 패턴 금지 — Rule 2).

## 변경
- 파일: `core/generator/native_tet/mesher.py`
- 위치: EEE1 try 블록 안, `native_tet_post_bsp_flip_32` log 직후 (line ~1844, `except` 직전)
- 핵심 변경:
  1. `flip_faces_23` 추가 호출 (max_flips=1500, min_quality_improvement=1e-3) + 단조 가드 (post.min_q ≥ pre.min_q × 0.99 AND post.mean_q ≥ pre.mean_q × 0.99). 통과 시에만 final_tets 갱신.
  2. `flip_edges_32` 추가 호출 (max_flips=1000) + 동일 가드.
  3. `flip_edges_44` 추가 호출 (max_flips=1000) + 동일 가드.
  4. `log.info("native_tet_kkk1", ...)` 단일 마커 + per-step n_flips, mq_before/after 기록.

## 검증 명령 (unit_tester 가 그대로 실행)
```bash
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py -q
```

## 합격 기준 (validator 가 평가)
- 회귀 PASS
- bench 시간 ≤ 600s
- tet worst mq ≥ 0.071 (현 0.076 기준 -0.005 허용), mean/best mq 단조 비감소 (-0.005 허용)
- 로그/bench.txt 에 `native_tet_kkk1` 마커 존재
- BL 영향 없음
