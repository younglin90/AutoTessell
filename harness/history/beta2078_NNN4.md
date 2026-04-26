# CARD NNN4 (beta2078) — Steiner 후 interior AMIPS smoothing post-pass

**target_engine**: tet
**모티프**: Klingner 2008 §3.5 + TetWild §3.5 — Steiner 후 free interior vertex 미세조정

## 이론적 근거

- NNN3 의 Steiner vertex (cycle1 200 + cycle2 200) 는 sliver circumcenter 에 그대로 박힘 — locally suboptimal.
- 이들은 free (surface lock 외) → AMIPS analytic gradient 가 1-ring energy 최소화 위치로 이동.
- surface_lock_ids = arange(n_surface_in) 으로 입력 surface vertex 만 lock → Hausdorff 보존.
- alpha=1.0 단일 stage, n_iter=1 (보수적).
- 단조 가드: pre/post worst-mq + mean-mq 둘 다 비감소 시에만 채택, 아니면 revert.
- HHH1/III1/JJJ1 AVOID 는 BSP 직후 컨텍스트 (interior vertex 적음) — NNN3 직후는 interior 400+ free 추가된 다른 컨텍스트.
- novelty 1, rigor 3, impact 2 → 합 6.

## 변경

- 파일: core/generator/native_tet/mesher.py
- 위치: NNN3 cycle 2 블록 직후 (line ~2130 except 다음, 외곽 try 내부)
- 핵심 변경:
  1. env gate `AUTO_TESSELL_NNN4_AMIPS` (default "1") 분기.
  2. `surface_lock_ids = np.arange(int(n_surface_in), dtype=np.int64)`.
  3. `pre_q = tet_shape_quality(final_pts, final_tets)`; pre_min/pre_mean 캡처.
  4. `from core.generator.native_tet.amips import smooth_amips_analytic`
     `_res, smoothed_pts = smooth_amips_analytic(final_pts, final_tets, locked_vertex_ids=surface_lock_ids, n_iter=1, alpha=1.0)`.
  5. `post_q = tet_shape_quality(smoothed_pts, final_tets)` → `post_q.min() >= pre_min - 1e-12 and post_q.mean() >= pre_mean - 1e-12` 일 때만 `final_pts = smoothed_pts` 채택, 아니면 revert.
  6. `log.info("native_tet_nnn4_post_steiner_amips", pre_min=..., post_min=..., pre_mean=..., post_mean=..., accepted=bool)`.
  7. except → `log.warning("native_tet_nnn4_skipped", reason=str(exc)[:120])` (silent skip 금지).

## 검증 명령

```bash
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py tests/test_native_tet_sizing.py tests/test_cdt_check.py -q
```

## 합격 기준

- 회귀 PASS (위 5개 suite 전부).
- bench_thingi10k 시간 ≤ 720s.
- tet worst mq ≥ 0.050 (NNN3 의 0.055 - 0.005 tolerance).
- mean mq 단조 비감소 (NNN3 baseline 대비).
- hex/poly fail 0.
- bench.txt log 에 "native_tet_nnn4_post_steiner_amips" 출현.
