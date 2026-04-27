# CARD BETA2261_VVV9H5_APPLY_DRYRUN_WIRE (beta2261) — VVV9H #5 wire apply helper as dryrun

**target_engine**: tet
**모티프**: Klingner & Shewchuk 2008 §4.1 short-edge contraction — apply path dryrun wire (R184/R190 pattern: helper invoked, return discarded, evidence-only log)

## 이론적 근거 (≤30줄)

- **문제 정의**: VVV9H 시퀀스 #4 (R195) 에서 `_apply_klingner_edge_contract_topK` 가 `stellar.py:1434` 에 추가됐으나 mesher 에서 호출되지 않아 evidence 가 0. 다음 단계는 mesher VVV12 try-block 에서 helper 를 *호출* 하되 결과 (new_pts, new_tets, stats) 를 *discard* 하여 메쉬 무변경 + 실측 통계 (n_apply_attempted, n_apply_accepted, wall_ms) 수집.
- **본 카드의 핵심**:
  1. mesher.py VVV9H3 diag hook 직후 (line ~2980) 에 `_VVV9H_APPLY_DRYRUN: bool = False` gate 추가.
  2. gate ON + `_n_sliver_pre >= 1` + `len(_cands) >= 1` 시 `_apply_klingner_edge_contract_topK(final_pts, final_tets, _cands, k=10)` 호출.
  3. 반환값 `(_new_pts, _new_tets, _stats)` discard — `final_pts/final_tets` 미터치.
  4. log key `native_tet_vvv9h4_dryrun` 에 `n_apply_attempted=10, n_apply_accepted=_stats['n_applied'], n_reverted, n_conflict, wall_ms` 노출.
- **단조 보장**: gate=False (default OFF) → R195 대비 runtime 0 byte 차이. `mesh ±0` 자명.
- **레퍼런스**: Klingner & Shewchuk 2008 §4.1; R184 (VVV9D dryrun wire) / R190 (VVV9F6 dryrun ON) 패턴 동일.
- **혁신성**: novelty 1 (skel→wire), rigor 3 (gate OFF 무변경), impact 2 (다음 R197 gate flip 시 곧바로 evidence 산출). 합 6 ≥ 5 OK.

## 변경

- 파일: `core/generator/native_tet/mesher.py` (단일 파일, ≤25줄)
- 위치: line ~2980 (VVV9H3 diag try-block 직후, VVV12 outer except 직전)
- 핵심 변경:
  1. `_VVV9H_APPLY_DRYRUN: bool = False` gate (default OFF).
  2. `if _VVV9H_APPLY_DRYRUN and _n_sliver_pre >= 1 and len(_cands) >= 1:`
  3. `from core.generator.native_tet.stellar import _apply_klingner_edge_contract_topK as _akec_dr`
  4. `_t0 = time.perf_counter(); _np, _nt, _st = _akec_dr(final_pts, final_tets, _cands, k=10); _wall_ms = int((time.perf_counter()-_t0)*1000)`
  5. `log.info("native_tet_vvv9h4_dryrun", n_apply_attempted=10, n_apply_accepted=int(_st.get("n_applied",0)), n_reverted=int(_st.get("n_reverted",0)), n_conflict=int(_st.get("n_conflict",0)), wall_ms=_wall_ms, mode="dry_run")`
  6. `except Exception as exc: log.warning("native_tet_vvv9h4_skipped", reason=str(exc)[:120])`
- 주의: `_cands` 는 R193 hook 의 try-block 안에서 정의되므로 본 코드도 동일 try-block 안에 nest 또는 재계산. **권장: 동일 try-block 끝 부분에 추가** → `_cands` 가 in-scope.

## 검증 명령

```bash
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py tests/test_native_tet_hausdorff.py -q
```

## 합격 기준

- 회귀 31/31 PASS (gate OFF → 코드 경로 미진입)
- worst_mq 0.2069 ±0.005
- mesh 무변경 (`final_pts/final_tets` 미터치)
- bench ≤62s (R195 대비 ±0)
- BL_OK 5/5

## AVOID 마커 준수

- smooth_amips_analytic BSP 직후 X (HHH1/III1/JJJ1)
- collapse_short_edges KKK1 flip 후 X (LLL1)
- flip_edges_54 default-ON without strict per-flip guard X (VVV5)
- Steiner cavity insertion non-Delaunay X (VVV4/VVV4b)
→ 본 카드는 gate OFF apply-helper wire only — 모든 AVOID 와 무관.

## 카드 시퀀스 위치

- VVV9H 시퀀스 (Klingner §4.1 edge contract): #1 candidates(R192) → #2 diag hook(R193) → #3 diag ON(R194) → #4 apply skel(R195) → **#5 apply dryrun wire(R196=현)** → #6 dryrun ON (R197) → #7 default activate (R198+).
- 다음 카드: `BETA2262_VVV9H6_APPLY_DRYRUN_ON` — gate flip True, evidence 수집, mesh 무변경 (helper return discard).
