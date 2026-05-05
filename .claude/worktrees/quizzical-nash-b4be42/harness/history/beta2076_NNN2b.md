# CARD NNN2b (beta2076) — Steiner circumcenter insertion (R10 fix)

**target_engine**: tet
**모티프**: TetWild §3.3 — Steiner point insertion at sliver circumcenters (envelope-validated). R10 fail (subscript on dataclass) 회피.

## 이론적 근거

NNN1c (R9 PASS) 가 사용한 `tet_shape_quality(pts, tets) -> np.ndarray` 와 동일 함수만 사용.
`snapshot(...)` 는 dataclass (속성 `.min_q`, `.mean_q`) — subscript 금지.
R10 NNN2 는 `_qsnap_eee()` 결과에 `["min"]` subscript 시도 → AttributeError.
NNN2b 는 ndarray 반환 함수만 indexing 한다.

## 검증된 시그니처 (raw 발췌)

```
# core/generator/native_tet/quality.py:54
def tet_shape_quality(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """per-tet shape quality ∈ [0,1]. 정사면체 ≈ 1."""
    # ... returns q (ndarray, shape (n_tets,))

# core/generator/native_tet/quality.py  @dataclass QualitySnapshot
#   min_q: float
#   mean_q: float
#   median_q: float
#   max_aspect: float
#   (subscript 불가 — .min_q / .mean_q 속성 접근만)

# snapshot(pts, tets) -> QualitySnapshot   ← NNN2b 에서 사용 금지
```

## 변경

- 파일: `core/generator/native_tet/mesher.py`
- 위치: NNN1 dry-run 블록 (line 1960-1979) **직후**, outer `try/except` (line ~1980) **이전**.
- 새 블록: `if os.environ.get("AUTO_TESSELL_NNN2_INSERT", "1") != "0":` ... internal `try/except`.

### 핵심 변경 (≤80 lines)

1. `from core.generator.native_tet.quality import tet_shape_quality` 재사용 (NNN1c 동일).
2. `pre_q_arr = tet_shape_quality(final_pts, final_tets)` — ndarray.
3. `pre_min = float(pre_q_arr.min()); pre_mean = float(pre_q_arr.mean())`.
4. sliver mask `pre_q_arr < 0.05`, worst-first `np.argsort(pre_q_arr)[: min(200, int(sliver_mask.sum()))]`.
5. 각 worst tet 의 circumcenter 계산: 4-pts → linear solve (helper 있으면 사용); 실패 시 centroid fallback.
6. `mask_inside = envelope.contains_points(cands)` 로 inside 만 채택.
7. `trial_pts = np.vstack([final_pts, cands[mask_inside]])`.
8. `from scipy.spatial import Delaunay; new_tets = Delaunay(trial_pts).simplices`.
9. winding-based drop: new tet centroid `envelope.contains_points` 로 외부 제거.
10. `post_q_arr = tet_shape_quality(trial_pts, new_tets_inside)` — ndarray.
11. **단조 비감소 채택**: `if post_q_arr.min() >= pre_min - 1e-12 and post_q_arr.mean() >= pre_mean - 1e-12:` → `final_pts, final_tets = trial_pts, new_tets_inside; n_inserted = int(mask_inside.sum())` else `n_inserted = 0`.
12. `log.info("native_tet_nnn2", n_inserted=n_inserted, pre_min=pre_min, post_min=float(post_q_arr.min()), pre_mean=pre_mean, post_mean=float(post_q_arr.mean()))`.
13. 전체 블록을 `try/except Exception as exc: log.warning("native_tet_nnn2_failed", reason=str(exc)[:200])` 으로 감싼다 — bench 중단 절대 금지.

### 금지 사항 (R7-R10 패턴 회피)

- `snapshot(...)["min"]` 또는 `_qsnap_eee()["..."]` subscript 금지.
- `QualitySnapshot` dataclass subscript 금지 — `.min_q` / `.mean_q` 속성만.
- `tet_shape_quality` 외 다른 quality 함수 신규 import 금지.
- 변경 줄수 ≤ 80.

## 검증 명령

```bash
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py tests/test_native_tet_sizing.py tests/test_cdt_check.py -q
```

## 합격 기준

- 회귀 PASS (위 5 파일).
- bench 시간 ≤ 720s.
- tet metric 단조: `worst ≥ 0.071` (pre 0.055 대비 단조 비감소).
- bench.txt 에 `native_tet_nnn2` log + `n_inserted` 필드 노출.
- BL 합격 분포 동등.
- subscript 오류 (TypeError/AttributeError) 미발생 — bench 정상 종료.
