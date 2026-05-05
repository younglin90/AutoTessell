# CARD NNN3 (beta2077) — Steiner iterative insertion (cycle 2)

**target_engine**: tet
**모티프**: TetWild §3.3 Steiner iterative insertion (시퀀스 #3)

## 이론적 근거

- NNN2b (cycle 1) 단일 패스 후 worst mq=0.055. cycle 1 에서 만든 새 vertex 가 잔여 sliver candidate 로 노출됨.
- cycle 2 = NNN2b 와 동일 로직 1 회 더 (sliver 식별 → circumcenter → envelope → Delaunay → 단조 가드).
- 단조 가드 (post_min ≥ pre_min AND post_mean ≥ pre_mean) 로 회귀 봉쇄. 향상 없으면 자동 skip.
- max_inserts=200 유지 (안전).
- 점수: novelty 2, rigor 2, impact 3 → 합 7.

## 변경

- 파일: `core/generator/native_tet/mesher.py`
- 위치: line 2055 (NNN2b `log.info("native_tet_nnn2", ...)` 종료 직후, `except Exception as exc:` 위) 에 NNN3 cycle 2 블록 삽입.
- 핵심 변경 (≤80 줄):
  1. `if os.environ.get("AUTO_TESSELL_NNN3_INSERT", "1") != "0":` 가드.
  2. NNN2b 와 동일 패턴: pre_q, sliver_mask<0.05, top200, circumcenter linear solve, envelope mask, Delaunay, centroid envelope keep, 단조 가드 (worst+mean).
  3. log key: `native_tet_nnn3`, count 변수 `n_inserted_iter2`. pre_min/post_min/pre_mean/post_mean 출력.
  4. 변수명 `final_pts`, `final_tets`, `envelope` 동일 사용 (NNN2b 가 갱신한 값 그대로 입력).
  5. cycle 1 에서 변경 없으면 cycle 2 의 sliver_mask 가 동일 → 가드로 자연 skip.

### NNN2b raw 발췌 (maker 가 패턴 복제용 — 변수명 동일 유지)

```python
from core.generator.native_tet.quality import tet_shape_quality
from scipy.spatial import Delaunay

pre_q_arr = tet_shape_quality(final_pts, final_tets)
pre_min = float(pre_q_arr.min())
pre_mean = float(pre_q_arr.mean())

sliver_mask = pre_q_arr < 0.05
n_worst = min(200, int(sliver_mask.sum()))
worst_idx = np.argsort(pre_q_arr)[:n_worst]

cands = []
for ti in worst_idx:
    tet_pts = final_pts[final_tets[ti]]
    try:
        A = 2.0 * (tet_pts[1:] - tet_pts[0])
        b = np.sum(tet_pts[1:] ** 2, axis=1) - np.sum(tet_pts[0] ** 2)
        cc = np.linalg.lstsq(A, b, rcond=None)[0]
    except Exception:
        cc = tet_pts.mean(axis=0)
    cands.append(cc)

if cands:
    cands = np.array(cands)
    try:
        mask_inside = envelope.contains_points(cands)
    except Exception:
        mask_inside = np.ones(len(cands), dtype=bool)
    if mask_inside.any():
        trial_pts = np.vstack([final_pts, cands[mask_inside]])
        new_tets = Delaunay(trial_pts).simplices
        centroids = trial_pts[new_tets].mean(axis=1)
        try:
            keep = envelope.contains_points(centroids)
        except Exception:
            keep = np.ones(len(new_tets), dtype=bool)
        new_tets_inside = new_tets[keep]
        if len(new_tets_inside) > 0:
            post_q_arr = tet_shape_quality(trial_pts, new_tets_inside)
            if (post_q_arr.min() >= pre_min - 1e-12
                and post_q_arr.mean() >= pre_mean - 1e-12):
                final_pts, final_tets = trial_pts, new_tets_inside
                n_inserted = int(mask_inside.sum())
```

NNN3 블록은 위 패턴 그대로 1회 복제 (cycle 2). log event 만 `native_tet_nnn3`, count 변수 `n_inserted_iter2`.

## 검증 명령

```bash
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py tests/test_native_tet_sizing.py tests/test_cdt_check.py -q
```

## 합격 기준

- 회귀 PASS.
- bench 시간 ≤ 720s.
- tet worst mq ≥ 0.071 (현 0.055 향상 또는 단조 가드 통과 동등).
- mean / best 단조 비퇴행.
- hex / poly fail 0.
- bench.txt 에 `native_tet_nnn3` + `n_inserted_iter2` 카운트.
- BL 영향 없음 (BL 합격 분포 동등).
