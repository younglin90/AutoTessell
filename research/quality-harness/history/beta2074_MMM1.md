# CARD MMM1 (beta2074) — flip cycle 2회 반복 (multi-pass)

**target_engine**: tet
**모티프**: Joe 1995 + Klingner 2008 — multi-pass flip cycle 로 잔여 sliver 제거

## 이론적 근거
- KKK1 의 1차 flip cycle (23/32/44) 후, connectivity 변화로 새로 노출된 sliver 존재.
- 2차 cycle 에서 1차에 잡히지 않은 face/edge 가 flip 가능 (Joe 1995 §4 multi-pass 수렴).
- Vertex 위치 변경 X → worst-mq regression 위험 없음 (LLL1 collapse 실패와 대조).
- 단조 가드: post min_q ≥ pre × 0.99 AND post mean_q ≥ pre × 0.99 (KKK1 동등 패턴).
- 점수: novelty 1, rigor 2, impact 1 → 합 4. consecutive_fails=1 회복용 안전 카드.

## 변경
- 파일: core/generator/native_tet/mesher.py
- 함수: generate_native_tet (KKK1 cycle 끝 직후, line ~1900)
- 핵심 변경:
  1. KKK1 cycle (flip_23 + flip_32 + flip_44) 종료 직후 동일 패턴 1회 더 반복.
  2. 각 호출 후 단조 가드 (min_q × 0.99, mean_q × 0.99) 적용.
  3. log: `native_tet_mmm1` (n_flips_23/32/44, mq_before/after, min_q_before/after).

## 검증 명령 (unit_tester)
```bash
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py -q
```

## 합격 기준 (validator)
- 회귀 PASS (위 3 파일 + smoke).
- bench 시간 ≤ 600s (현 54.8s 충분한 margin).
- tet worst mq ≥ 0.071 (baseline 0.076 × 0.99 가드 하한).
- tet mean/best mq 단조 비감소 (best 0.236 기준).
- hex/poly 영향 없음 (BL 분포 동등).
