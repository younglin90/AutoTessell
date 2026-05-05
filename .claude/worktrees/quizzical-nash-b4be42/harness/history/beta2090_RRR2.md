# CARD RRR2 (beta2090) — worst-percentile targeted AMIPS smoothing

**target_engine**: tet
**모티프**: Klingner 2008 §3.5 — quality histogram-based targeted smoothing (시퀀스 #2)

## 이론적 근거
- p5 (하위 5%) shape_q 가 임계 0.05 미만이면 worst tet (q < 0.05) 만 식별.
- 그 tet 4 vertex 의 union 중 surface lock 제외 → free interior set.
- 그 외 모든 vertex 를 lock 한 채 `smooth_amips_analytic(..., n_iter=1, alpha=1.0)` 호출.
- 단조 가드: post_min ≥ pre_min 그리고 post_mean ≥ pre_mean 둘 다 만족 시에만 채택.
- novelty 1, rigor 3, impact 2 → 합 6.

## 변경
- 파일: core/generator/native_tet/quality.py
  - 위치 1 (line 300): `_RRR1_QUALITY_HISTOGRAM: bool = False` → `True`.
- 파일: core/generator/native_tet/mesher.py
  - 위치 2 (line 2169 직후, NNN4 except 블록 바로 다음): RRR2 블록 추가 (~50줄).

### 정확한 시그니처 발췌
```python
# amips.py:172
def smooth_amips_analytic(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    locked_vertex_ids: np.ndarray | None = None,
    n_iter: int = 3,
    alpha: float = 1.0,
    step_init: float = 0.1,
    step_min: float = 1e-6,
) -> tuple[AMIPSResult, np.ndarray]: ...

# quality.py:54
def tet_shape_quality(pts: np.ndarray, tets: np.ndarray) -> np.ndarray: ...
# returns per-tet shape quality ∈ [0,1].

# quality.py:303
def _quality_percentiles(pts: np.ndarray, tets: np.ndarray) -> dict:
    # returns {"shape_q": {"p50","p90","p95","p99"}, "aspect": ..., "min_dihedral_deg": ...}
```
주의: `_quality_percentiles` 는 p95/p99 (상위) 를 반환. shape_q 는 작을수록 나쁨이므로 RRR2 에서는
`np.percentile(sq, 5)` (p5) 를 직접 계산해야 한다.

### RRR2 블록 (mesher.py NNN4 직후 삽입)
1. `if os.environ.get("AUTO_TESSELL_RRR2_TARGETED", "1") != "0":` 가드 + try/except.
2. `from core.generator.native_tet.quality import _RRR1_QUALITY_HISTOGRAM, tet_shape_quality`
   `from core.generator.native_tet.amips import smooth_amips_analytic`
3. `if not _RRR1_QUALITY_HISTOGRAM: skip` (안전 가드).
4. `q_per_tet = tet_shape_quality(final_pts, final_tets)`; `p5 = float(np.percentile(q_per_tet, 5))`.
5. `if p5 >= 0.05: log + skip`.
6. `worst_mask = q_per_tet < 0.05`; `worst_v = np.unique(final_tets[worst_mask].ravel())`.
7. `n_surface_in = int(V.shape[0])`; `is_surface = worst_v < n_surface_in`.
   `free_v = worst_v[~is_surface]` (interior only).
8. `if free_v.size == 0: skip`.
9. `all_ids = np.arange(final_pts.shape[0], dtype=np.int64)`; `lock_ids = np.setdiff1d(all_ids, free_v)`.
10. `pre_min, pre_mean = float(q_per_tet.min()), float(q_per_tet.mean())`.
11. `_res, sm_pts = smooth_amips_analytic(final_pts, final_tets, locked_vertex_ids=lock_ids, n_iter=1, alpha=1.0)`.
12. `post_q = tet_shape_quality(sm_pts, final_tets)`.
13. `accepted = bool(post_q.min() >= pre_min - 1e-12 and post_q.mean() >= pre_mean - 1e-12)`.
14. `if accepted: final_pts = sm_pts`.
15. `log.info("native_tet_rrr2_targeted_amips", p5=p5, n_worst=int(worst_mask.sum()), n_free=int(free_v.size), pre_min=pre_min, post_min=float(post_q.min()), pre_mean=pre_mean, post_mean=float(post_q.mean()), accepted=accepted)`.
16. `except Exception as exc: log.warning("native_tet_rrr2_skipped", reason=str(exc)[:120])`.

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_tet.quality import _quality_percentiles, _RRR1_QUALITY_HISTOGRAM; print('OK', _RRR1_QUALITY_HISTOGRAM)"
timeout 120 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py -q
```

## 합격 기준
- 회귀 PASS.
- bench 시간 ≤ 720s.
- tet worst mq ≥ 0.077 (0.082 - 0.005).
- mean shape_q 단조 비감소.
- BL 합격 분포 동등.
