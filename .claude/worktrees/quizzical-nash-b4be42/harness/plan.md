# CARD BETA2291_VVV9P3_DIAG_ON (R226) — VVV9P #3 multi-face removal diag flip ON (sliver+worst guard)

**target_engine**: tet
**모티프**: Klingner & Shewchuk 2008 §3.2 multi-face removal (read-only diag, sliver-pre + worst_mq guard)

## 이론적 근거 (≤30줄)

- **문제**: VVV9P #1 (R224) `_multi_face_removal_candidates` helper 추가, #2 (R225) diag hook gate OFF + sliver-pre>=1 wall safety. 이번 단계는 gate flip True 로 evidence 수집 활성. 셀-레벨 변경 없음 (helper 결과 discard).
- **핵심 아이디어**:
  1. mesher.py:3138 `_VVV9P_DIAG=False` → `True` (1줄 flip).
  2. 기존 wall safety `_n_sliver_pre >= 1 and _worst_pre < 0.10` 그대로 유지 (R225 #2 guard, sliver-pre>=1 + worst<0.10).
  3. 호출 시 `k_worst=64, q_thr=0.3` 로 dry-run 후보 수집, helper 결과 candidate 만 emit (mesh state 미변경).
  4. log key `native_tet_vvv9p_diag` per-fid (n_candidates, top_quality, wall_ms, mode="dry_run").
- **레퍼런스**: Klingner & Shewchuk 2008 §3.2 "Multi-face removal" — 슬리버 셀 5-face → 3-face 단순화 후보 enumeration (read-only).
- **혁신성** (3+2+1=6, ≥5):
  - novelty 3 (multi-face removal evidence-driven activation).
  - rigor 2 (sliver-pre>=1 + worst<0.10 이중 wall safety, monotone safe).
  - impact 1 (gate flip-only, mesh unchanged → 향후 apply 카드의 calibration 데이터).

## 변경

- 파일: core/generator/native_tet/mesher.py (단일 파일, ≤2 LOC delta)
- 함수: `_apply_vvv12` 내부 try-block (line ~3138)
- 핵심 변경:
  1. line 3138: `_VVV9P_DIAG: bool = False  # R226 카드에서 ON` → `_VVV9P_DIAG: bool = True  # R226 ON (gate flip True)`
- 단조 가드: helper 결과 discard (mesh state 미변경 → pre/post mesh metric 동일 보장). sliver-pre>=1 + worst<0.10 wall safety guard 그대로 유지.
- AVOID 준수: smooth_amips_analytic / collapse_short_edges / flip_edges_54 default-ON 미접촉.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py tests/test_native_tet_hausdorff.py -q
```

## 합격 기준 (validator 가 평가)

- 회귀 0 (35/35 PASS 유지)
- bench 시간 ≤ 67.59s + 15% (≈77.7s)
- worst_mq 0.208 ±0.005 (mesh unchanged 보장)
- BL_OK 5/5 stable
- log emit `native_tet_vvv9p_diag` per-fid 확인 (sliver-pre>=1 + worst<0.10 fid 한정)
- AVOID 패턴 미접촉

## 카드 시퀀스 위치

- VVV9P (Klingner §3.2 multi-face removal) 시퀀스의 #3/N (helper #1 → diag-hook OFF #2 → diag-ON #3).
- 다음 카드 후보: BETA2292_VVV9P4_APPLY_DRYRUN_HOOK (apply path skeleton, gate OFF, single-face removal simulation).
