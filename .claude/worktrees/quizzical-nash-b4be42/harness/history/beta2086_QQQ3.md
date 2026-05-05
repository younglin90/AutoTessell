# CARD QQQ3 (beta2086) — front-collision check vectorize + max_pairs guard

**target_engine**: tet (BL)
**모티프**: Garimella 2003 §3 + 자체 — collision detection 효율화 (cosine 기반 O(N²)→numpy 1회 + max_pairs)

## 이론적 근거 (≤10줄)

- R23 QQQ2b FAIL 원인: `_check_prism_front_collision` 가 prism 마다 O(N) 반복 → vertex≥1k 에서 quadratic 90s 초과.
- 해결: front_normals (N×3) 의 self-dot product 행렬을 `np.einsum('ij,kj->ik', n, n)` 1회 연산.
- |dot| > 0.5 이며 i<j 인 (i,j) 쌍만 반대 방향 후보 → 거의 반대 방향(반대 normal) 만 collision.
- max_check_pairs=200 가드: n_prism > 200 이면 dot 행렬에서 가장 음(-) 인 200쌍만 검사.
- O(N²) 메모리는 N≤5k 까지 안전 (200MB 미만), 그 이상은 max_pairs 잘라냄.
- novelty 2 (vectorized cosine pruning), rigor 2 (numpy einsum + bound), impact 2 (90s→<5s) → 합 6.

## 변경

- 파일: `core/layers/native_bl.py` (단일)
- 함수: `_check_prism_front_collision` (line ~57) — 알고리즘 vectorize 구현
- 핵심:
  1. `dots = front_normals @ front_normals.T` (N×N), `np.fill_diagonal(dots, 0)`
  2. mask `dots < -0.5` (거의 반대방향) → 후보 (i,j) 쌍 추출, `i<j` 만
  3. `max_check_pairs=200`: 후보 > 200 이면 dots 가장 음수 200 쌍만 (`np.argpartition`)
  4. 각 후보 (i,j) 에 대해 `np.linalg.norm(front_points[i]-front_points[j])` < step 이면 collision True 반환
  5. flag `_BL_QQQ1_FRONT_COLLISION = True` 활성화 (호출부 R23 와 동일 매핑 유지)

## 검증 명령

```bash
timeout 60 python3 -c "from core.layers.native_bl import _check_prism_front_collision; import numpy as np; n=np.random.randn(1500,3); n/=np.linalg.norm(n,axis=1,keepdims=True); p=np.random.randn(1500,3); print(_check_prism_front_collision(n,p,0.01))"
timeout 120 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py -q
```

## 합격 기준

- 회귀 PASS (3 테스트 파일)
- bench 시간 ≤ 720s
- collision check N=1500 에서 < 5s 완료
- tet+BL / hex+BL / poly+BL fail 0
- BL 합격 분포 동등 또는 향상
