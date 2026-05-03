# CARD BETA2819_RRR3_EXTREME_WORST_LANE (beta2819) — RRR2 monotone guard에 D-cell extreme-worst lane 추가

**target_engine**: tet
**모티프**: Klingner & Shewchuk 2008 §3.5 + fTetWild §3.5 — worst-tet-priority relocation
acceptance, "min_q ≪ 1" 영역에서 mean-drop 없이 작은 worst 회복도 채택.

## 이론적 근거 (≤30줄)

- **문제 정의**: native_tet self-impl grade A=0/5 (20-bench 0/20), worst_mq=0.208.
  RRR2 (Klingner §3.5 worst-percentile AMIPS smoothing, mesher.py:2718-2824) 는
  현재 두 lane 으로 채택:
  - standard: `worst_drop ≤ 0.015 ∧ mean_gain ≥ -1e-12`
  - d_recovery: `min_gain ≥ 0.005 ∧ mean_gain ≥ -0.005`
  Hard mesh 에서 pre_min < 0.05 (D-cell extreme) 일 때 AMIPS 한 step 의 
  min_gain 이 0.001~0.004 범위에 자주 분포 — 두 lane 모두 거부 → grade
  upgrade 실패. Klingner §3.5 는 "any improvement to worst tet, with no global
  degradation" 을 권장하지만 현 임계는 0.005 hard floor.
- **본 카드 핵심 아이디어**: 세 번째 채택 lane 추가 (env-gated default ON):
  1. `accepted_extreme = (pre_min < 0.05) ∧ (min_gain ≥ 0.002) ∧ (mean_gain ≥ -1e-12)`
  2. 활성 조건이 `pre_min < 0.05` (extreme-worst regime) 으로 한정 → low-quality
     mesh 만 영향, normal mesh 는 standard/d_recovery 만 적용 (회귀 0).
  3. mean_gain `-1e-12` (사실상 no-drop) 으로 strict — global 단조 보장.
  4. env `AUTO_TESSELL_RRR3_EXTREME=0` 으로 OFF 가능.
- **수렴/안정성**: standard lane 의 worst_drop tol (0.015) 과 달리 extreme lane 은
  min_gain >0 강제 → worst monotone increasing. mean strictly non-decreasing
  → 전역 mean × per-tet AMIPS energy 둘 다 감소. fTetWild §3.5 envelope 제약은
  smooth_amips_analytic 내부 lock_ids 로 이미 보장.
- **레퍼런스**: Klingner 2008 §3.5 (Table 4 worst-q smoothing acceptance), 
  fTetWild Hu 2020 §3.5, mesher.py:2786-2808 (RRR2 기존 두 lane).
- **혁신성 평가**: novelty=2 (기존 두 lane 외 third regime-conditional lane) /
  rigor=2 (mean strict no-drop + pre_min<0.05 한정 + worst monotone) / 
  impact=2 (tet A 0→2~3/20 expected, 49 round 정체 escape). 합=6.

## 변경

- 파일: `core/generator/native_tet/mesher.py` (단일)
- 함수: `_run_native_tet_pipeline` 내부 RRR2 acceptance block (line ~2799-2810)
- 핵심 변경 (≤25줄):
  1. `accepted_extreme` 계산 추가 (3 줄 + 주석).
  2. `accepted = bool(accepted_standard or accepted_d_recovery or accepted_extreme)`.
  3. log dict 에 `accepted_extreme=bool(accepted_extreme)` 필드 추가 (진단용).
  4. env gate `AUTO_TESSELL_RRR3_EXTREME` 검사 (default "1", "0" 시 false).
- 단조 가드: extreme lane 은 `pre_min < 0.05` ∧ `min_gain ≥ 0.002` ∧ 
  `mean_gain ≥ -1e-12` 세 조건 모두 만족해야 채택. mean strict non-drop
  → 전역 평균 단조. log.info 에 채택 lane 명시.

## 검증 명령

```bash
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py tests/test_native_tet_hausdorff.py -q
```

## 합격 기준

- 회귀 PASS (4 test files all pass)
- bench 시간 ≤ 75s (기존 59.1s + 15.9s margin)
- worst_mq ≥ 0.200 (현재 0.208 baseline, 단조-safe; ≥ 0.208 권장)
- BL_OK ≥ 5/5 (현재 5/5 유지)
- tet grade A: 현재 0/5 → ≥ 0/5 monotone (개선 시 +1~2/5 bonus, 의무 아님)
- env OFF (`AUTO_TESSELL_RRR3_EXTREME=0`) 시 정확히 baseline 재현
- syntax 무오류 + log.info 에 `accepted_extreme` field 노출

## 카드 시퀀스 위치

- RRR (RRR1=histogram diag, RRR2=targeted AMIPS, **RRR3=extreme-worst lane**) 
  시퀀스의 #3, Klingner §3.5 acceptance-criteria refinement 라인.
- 현 시퀀스 #1/3 (skeleton+default ON, hard regime only).
- 다음 카드 후보 (PASS 후):
  - `BETA2820_RRR3_RAISE_ITER` — extreme regime 에서만 n_iter 2→3 raise (D-cell 회복 강화).
  - `BETA2820_RRR3_BENCH_DRIVE` — 20-sample bench 실행 + grade A delta 측정.
  - `BETA2820_VVV9N_REVIVE` — VVV9N evidence 라인 ON 측정 (rotate to N series).
- 5+ round tet stagnation 시 hex/poly 로 rotate (rotate_targets 활용).
