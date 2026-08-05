# CARD NNN1c (beta2075) — Steiner dry-run sliver detection (재시도 #2)

**target_engine**: tet
**모티프**: TetWild §3.3 Steiner dry-run — sliver candidate 카운트 (실제 삽입 X). 안전한 read-only 진단 패스.

## 이론적 근거 / 사고 분석

- R7 NNN1: `import os` 누락 — top-level import 누락으로 NameError → 회귀 fail.
- R8 NNN1b: `QualitySnapshot.q_per_tet` 없는 attribute 접근 — silent except 로 모든 run 에서 skip, log 0건.
- 교훈: **시그니처 추측 금지**. except 절은 reason 을 반드시 log 에 남겨 다음 round 에서 진단 가능해야 함.
- 본 카드는 read-only — final_tets/final_pts 변경 X. metric 동등성 보장.

## 확인된 시그니처 (raw, 추측 금지)

```
core/generator/native_tet/quality.py:54
  def tet_shape_quality(pts: np.ndarray, tets: np.ndarray) -> np.ndarray
  # per-tet quality ∈ [0,1] array. (NOT a snapshot attribute.)

core/generator/native_tet/quality.py:38  @dataclass class QualitySnapshot
  fields: n_tets, min_q, mean_q, median_q, max_aspect, mean_aspect,
          min_dihedral_deg, median_dihedral_deg, vol_weighted_mean_q,
          p10_q, p10_dihedral_deg
  # NOTE: q_per_tet 필드는 존재하지 않음. per-tet array 가 필요하면
  #       tet_shape_quality(pts, tets) 를 직접 호출.

core/generator/native_tet/envelope.py:87
  def Envelope.contains_points(self, pts: np.ndarray) -> np.ndarray
  # pts shape (N,3) → bool array (N,). centroid 검사용.

core/generator/native_tet/mesher.py:1900-1956
  MMM1 try-block 끝: line 1956 (except Exception as exc 후 log.warning).
  뒤이어 line 1957 의 except 는 KKK1 wrapper.
```

## 변경

- 파일: `core/generator/native_tet/mesher.py`
- 함수: `generate_native_tet` 내부 — MMM1 종료 직후 (line 1956 `log.warning("native_tet_mmm1_skipped"...)` 다음, line 1957 KKK1 except 직전).

### 핵심 변경 (≤40 줄)

1. **import 추가**: 파일 상단 (line 4 `import time` 다음). `import os` — 이미 있으면 스킵 (사전 grep 확인 필수).
2. **NNN1 dry-run block**: MMM1 try/except 끝난 직후 새 try/except 블록. 함수 내 lazy import 로 `tet_shape_quality` 사용 (envelope 객체는 scope 에 이미 존재하는 변수 활용 — 없으면 fallback).
   - `q_arr = tet_shape_quality(final_pts, final_tets)` (per-tet array, shape (N,))
   - `sliver_mask = q_arr < 0.05` (TetWild 기본 threshold)
   - `n_sliver = int(sliver_mask.sum())`
   - `n_sliver_inside`: envelope 변수가 함수 scope 에 있으면 sliver tet centroid 의 contains_points 호출, 없으면 `n_sliver` 그대로 (보수적).
   - **read-only**: final_tets/final_pts 변경 절대 X.
3. **log 강제**: `log.info("native_tet_nnn1_dry_run", n_sliver=n_sliver, n_sliver_inside=n_sliver_inside, threshold=0.05)`.
4. **except silent skip 금지**: `except Exception as exc: log.warning("native_tet_nnn1_failed", reason=str(exc)[:200])` — reason 반드시 기록 (R8 사고 재발 방지).
5. env flag: `if os.environ.get("AUTO_TESSELL_NNN1_DRYRUN", "1") != "0":` 로 wrap (런타임 토글).

## 검증 명령 (unit_tester)

```bash
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py tests/test_native_tet_sizing.py tests/test_cdt_check.py -q
```

## 합격 기준 (validator)

- 회귀 PASS (위 5 파일 전부).
- bench 시간 ≤ 600s × 1.15 = 690s.
- tet metric 동등 (worst ≥ 0.071, best ≥ 0.230 — read-only 이므로 정확히 동일해야 정상).
- bench.txt 또는 stderr 에 `native_tet_nnn1_dry_run` log 1건 이상 존재 + `n_sliver` 카운트 출력.
- `native_tet_nnn1_failed` log 가 보이면 즉시 FAIL (silent skip 금지 정책).
