# CARD BETA2258_VVV9H2_DIAG_HOOK (beta2258) — Klingner edge-contract diagnostic hook (VVV12 try-block)

**target_engine**: tet
**모티프**: Klingner & Shewchuk 2008 §4.1 (short-edge contraction) — evidence collection in VVV12 sliver path.

## 이론적 근거

- **문제 정의**: R192/VVV9H #1 PASS 시 `_klingner_edge_contract_candidates` skeleton 추가 (stellar.py:1336),
  default OFF, no caller. 실제 hard mesh 에서 candidate edge 가 **얼마나 검출되는지 evidence 부재**.
  VVV12 sliver pass (V/L³ < 1e-3) 가 이미 sliver 검출 경로 — Klingner §4.1 의 "short edge ≈ sliver
  근접" hypothesis 검증 자연 위치.
- **핵심 아이디어** (option (a) — 권장):
  1. mesher.py VVV12 try-block 내 `_n_sliver_pre >= 1` gate 직후 (line ~2933, VVV9F 블록 옆)
     `_klingner_edge_contract_candidates(final_pts, final_tets, q_max=0.2, l_max_factor=0.4,
     max_candidates=200)` 호출, 결과 discard.
  2. log key `native_tet_vvv9h_diag` (n_candidates, n_safe=len(cands), n_quality_improving=
     |{c: c[2] >= pre_worst_q}|, q_max, l_max_factor, wall_ms, mode="dry_run").
  3. default OFF gate `_VVV9H_DIAG: bool = False` (R193 PASS 후 R194 에서 True 전환 가능).
- **단조 보장**: helper 는 mesh 무변경 (시뮬+revert), gate False 시 코드패스 미진입 → metric ±0 보장.
- **레퍼런스**: Klingner & Shewchuk 2008 §4.1 (short-edge contraction), 본 repo stellar.py:1336.
- **혁신성**: novelty=1, rigor=2 (gate+discard), impact=2 (R195 action helper evidence 토대) → 합 5.

## 변경

- 파일: `core/generator/native_tet/mesher.py` (단일 파일)
- 위치: VVV12 try-block 내, VVV9F dryrun 블록 직후 (line ~2954 직전)
- 핵심 (≤30줄):
  1. `_VVV9H_DIAG: bool = False` 선언.
  2. gate `if _VVV9H_DIAG and _n_sliver_pre >= 1:` 진입.
  3. `from ...stellar import _klingner_edge_contract_candidates as _kecc_dr` 지연 import.
  4. `_t0 = time.perf_counter(); _cands = _kecc_dr(final_pts, final_tets, q_max=0.2,
     l_max_factor=0.4, max_candidates=200)`.
  5. `_n_qi = sum(1 for c in _cands if c[2] >= _pre_worst_q)` (pre_worst_q 는 기존 snapshot 재활용).
  6. `log.info("native_tet_vvv9h_diag", n_candidates=len(_cands), n_safe=len(_cands),
     n_quality_improving=_n_qi, q_max=0.2, l_max_factor=0.4, wall_ms=..., mode="dry_run")`.
  7. `except Exception as exc: log.warning("native_tet_vvv9h_skipped", reason=str(exc)[:120])`.
- 단조 가드: `_VVV9H_DIAG=False` (default) → 진입 0 → mesh 무변경 → metric ±0.
- AVOID 준수: KKK1/LLL1 (edge contract direct apply 금지) — 본 카드는 enum/log only, mesh mutation 0.

## 검증 명령

```bash
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py tests/test_native_tet_hausdorff.py -q
```

## 합격 기준

- 회귀 PASS (4 testfile, 35+ tests).
- bench 시간 ≤ 59.1 + 15% = 68.0s (gate False 이므로 사실상 ±0).
- tet metric: worst_q ≥ 0.2069 - 0.005, mean_q ±0.005, A/B/C/D = 0/0/2/3 동등.
- BL 합격 분포 동등 (5/5).
- diff ≤ 80줄 (단일 파일).

## 카드 시퀀스 위치

VVV9H (Klingner 2008 §4.1 short-edge contraction) 시퀀스:
- #1 (R192 PASS): candidate enum helper skeleton (stellar.py:1336).
- **#2 (R193, 본 카드)**: diagnostic hook in VVV12 (gate OFF, evidence collection).
- #3 (R194 후보): _VVV9H_DIAG=True 1-round PASS 후 evidence 분석 → 액션 helper 설계 근거.
- #4 (R195 후보): `_apply_edge_contract_topK` action helper in stellar.py (default OFF, no caller).
- #5 (R196 후보): VVV12 wire (sliver-gated, post>=pre 강제, top_k=3).
- #6 (R197 후보): default ON + 합격 기준 강화 (worst_q +0.005).

총 6 카드 예상, 본 카드는 #2.
