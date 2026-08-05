# CARD BETA2831 (beta2831) — BVH leaf 평가를 active-query 전체로 벡터화 (결과 불변 순수 성능)

**target_engine**: tet
**모티프**: Ericson 2005 §5.1.5 point-triangle closest — leaf 브로드캐스트 batch (fTetWild envelope/Hausdorff 가속)

## 이론적 근거 — 실측 프로파일 데이터 (cProfile, sphere.stl / draft / N=2000 / P4C=0)

정본 경로 그대로 계측: `PipelineOrchestrator().run(... quality=draft, tier=native_tet,
max_cells=2000, target_cells=2000)` (= `scripts/bench_native_tet_matrix.py::_worker`) 를
`cProfile` 로 감쌈. 프로파일 wall 87.8s (cProfile overhead 로 축소; 미프로파일 ~143s).
verdict=PASS 확인 (결과 정상).

**병목 top (tottime self / cumtime):**

| 함수 | ncalls | tottime(self) | cumtime | 비고 |
|---|---|---|---|---|
| `core/utils/aabb.py:81 _closest_points_on_triangles_batch` | **660,077** | **39.06s** | 57.48s | 단일 최대 |
| `aabb.py:323 closest_points_all_shared` | 16 | 2.59s | **62.38s** | 위 함수의 유일 호출자 |
| `hausdorff.py:71 hausdorff_vs_input` | 4 | — | 48.21s | 위 경로 소비 |
| `envelope.py:87 contains_points` (relocate) | 8 | — | 14.24s | 위 경로 소비 |
| `flip.py:251 flip_faces_23` | 18 | 0.81s | 5.20s | 차순위 (1/10 규모) |

- **결론**: `closest_points_all_shared` 가 profiled wall 의 **~71%** (62.4/87.8). 그 내부
  `_closest_points_on_triangles_batch` self 만 39s. numpy 자식(einsum 4.0M, reduce 4.1M,
  norm 0.93M, cross 0.11M, zeros_like 0.66M) 도 전부 이 함수 안. 차순위(flip)는 1/10 규모.
- **근본 원인**: `closest_points_all_shared` 의 leaf 분기(aabb.py:383)가
  `for qi in active_idx:` 로 **query 1개씩** `_closest_points_on_triangles_batch(points[qi],
  tri_pts)` 를 호출 → (query, leaf) 쌍마다 1회 = 660,077회. 각 호출은 leaf 내 k(≤8)개
  삼각형에만 벡터화되어, einsum/zeros_like/argmin 의 **per-call 오버헤드가 실제 산술을
  압도**한다 (8×3 배열에 einsum 6회).

**핵심 아이디어 (결과 불변):** leaf 방문 시 active query 전체(M개)를 한 번에 브로드캐스트로
평가. 산술 총량은 동일(M×k point-triangle test), 제거되는 것은 per-call 오버헤드뿐.
- 현: 660k회 × (einsum(8,3)×6 + zeros_like + argmin) → 호출당 오버헤드 ~59µs.
- 후: leaf 당 1회 × einsum(M,k,3) → 호출 수 ~100× 감소, 오버헤드 amortize.

**결과 동일성 보장 (bit-exact):**
1. 공식 동일 — Ericson §5.1.5 를 (M,k) 로 브로드캐스트, `p-A` 등 elementwise·einsum
   `mkj,mkj->mk` 는 per-query `kj,kj->k` 와 IEEE 동일 연산·동일 순서.
2. 삼각형 순서 보존 → `np.argmin(axis=1)` 의 first-min tie-break 동일.
3. leaf 간 갱신은 기존 strict `<` (`ds[j] < best_d[qi]`) 유지 → 먼저 방문한 leaf 가
   동점 유지, traversal 순서 불변 → `best_d/best_cp/best_ti` 전부 동일.
- **레퍼런스**: Ericson 2005 §5.1.5; 기존 `_closest_points_batch_legacy`(aabb.py:409)
  가 독립 oracle 로 존재 → 등가성 회귀 테스트에 사용.

**혁신성 평가**: novelty 1 / rigor 2 / impact 3 = **6**. (순수 성능이나 3개 TIMEOUT
형상을 벽 안으로 들여 산업 표준 벤치 커버리지를 회복 — impact 높음.)

## 변경

- 파일: **`core/utils/aabb.py`** (단일 파일)
- 함수: `closest_points_all_shared` leaf 분기 (line ~375-392) + 신규 헬퍼
  `_closest_points_on_triangles_matrix(pts (M,3), tri_pts (k,3,3)) -> (cps (M,k,3),
  ds (M,k))`.
- 핵심 변경 (≤70줄):
  1. `_closest_points_on_triangles_matrix` 신설 — `_closest_points_on_triangles_batch`
     의 einsum 을 `"mkj,mkj->mk"`, 마스크를 (M,k) 2D 로 승격. 반환 (M,k) 거리·(M,k,3) cp.
  2. leaf 분기: `active_idx = np.where(sub_active)[0]` 뒤 `for qi` 루프 삭제. 대신
     `cps_mk, ds_mk = _matrix(points[active_idx], tri_pts)` 1회 → `j = ds_mk.argmin(1)`
     → `dmin = ds_mk[arange, j]` → `upd = dmin < best_d[active_idx]` 마스크로
     `best_d/best_cp/best_ti` 를 벡터 갱신 (기존 strict-< 의미 보존).
  3. 기존 `_closest_points_on_triangles_batch` 및 `_closest_points_batch_legacy` 는
     **그대로 유지** (oracle·backward-compat).
- 단조 가드: 알고리즘 결과가 legacy 경로와 **bit-exact** 여야 함 (아래 등가 테스트가 게이트).
  성능은 개선만 허용, 회귀 시 revert.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
# 1) 결과 등가성 — 신 경로 == legacy 경로 bit-exact (신규 테스트)
timeout 90 python3 -m pytest tests/test_aabb_leaf_batch_equiv.py -q
# 2) solid 4-불변식 회귀 (정본 스모크)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 120 python3 scripts/smoke_native_tet.py 2000
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 120 python3 scripts/smoke_native_cylinder.py
```

신규 테스트 `tests/test_aabb_leaf_batch_equiv.py` 요지: 랜덤 삼각형 soup + 랜덤 query
(및 축상 근접점)에 대해 `bvh.closest_points_all_shared(P)` 의 `(cp, d, ti)` 3반환이
`bvh._closest_points_batch_legacy(P)` 와 `np.array_equal` (거리·인덱스 완전 일치,
cp 는 `allclose(atol=0)` = 동일 비트) 임을 assert.

## 합격 기준 (validator 가 평가)

- **결과 불변**: 등가 테스트 PASS (cp/d/ti 가 legacy 와 완전 일치) — 필수.
- **solid 4-불변식**: 두 스모크 모두 SMOKE OK (surface/void/vol/degen 종전과 동일).
- **성능**: `closest_points_all_shared` cumtime 이 동일 sphere.stl 프로파일에서
  62.4s → **≤ 20s** (≥3× 단축). 파생 지표로 sphere.stl 이 `bench_native_tet_matrix`
  120s 벽 안에서 **PASS** (기존 TIMEOUT). bench threshold/스크립트 변경 금지.
- **품질 지표 동등**: sphere/cube/cylinder 의 skew·nonOrtho·cells 가 종전과 동일
  (결과 불변이므로 변화 없어야 정상).
- BL 영향 없음 (거리 커널 결과 불변 → 하류 전부 불변).

## 카드 시퀀스 위치

- "native_tet 곡면-폐곡면 경로 성능 정상화" 시퀀스의 **1/3** (실측 병목 = closest-point).
- 다음 카드 후보 (PASS 후):
  - BETA2832 — `flip_faces_23`/`flip_edges_44` 의 `_face_map_vectorized`(82회 1.2s)
    재구축 중복 제거 (차순위 병목, 결과 불변).
  - BETA2833 — `hausdorff_vs_input` 를 rebudget best pass 에서만 1회 호출 (현 4회 중
    버려지는 pass 의 측정 제거; 결과 채택 로직 불변 확인 후).
