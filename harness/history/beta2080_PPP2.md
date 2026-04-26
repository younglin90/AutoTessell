# CARD PPP2 (beta2080) — native_poly Lp weighted centroid 실제 계산 + best-of-N p=4 후보

**target_engine**: poly
**모티프**: Lévy & Liu 2010 §3 — Lp CVT energy gradient, Lp weighted centroid 실제 구현

## 이론적 근거

- Lp CVT energy: E_p = Σ_i ∫_{Ω_i} ||x - s_i||^p dx. Gradient = 0 → Lp weighted centroid.
- 근사 Lp weighted centroid (region vertex 기반):
  - c_p = (Σ w_k * v_k) / (Σ w_k), w_k = ||v_k - s_i||^(p-2).
  - p=2 → 등가중 mean (현 동작). p=4 → 멀리 있는 vertex 강조 → anisotropic / sliver-prone region 에서 유리.
- best-of-N 에 voronoi(p=4) 후보를 추가하고, 단조 가드 (grade 우세 시에만 채택) 는 기존 _grade_score 정렬로 자동 충족.
- 기여도: novelty 2 (실제 Lp 계산), rigor 3 (Lévy & Liu §3), impact 3 (poly grade A 강건성). 합 8.

## 변경
- 파일: core/generator/native_poly/voronoi.py
- 위치 1: `_lloyd_3d_iteration` (line 134) — `lp_p > 2` 분기를 weighted centroid 로 교체.
- 위치 2: `_generate_native_poly_voronoi_inner` 시그니처/호출 — `lp_p` 인자 전파.
- 위치 3: `generate_native_poly_voronoi` best-of-N (line ~196) — voronoi(p=4) 후보 추가.
- 핵심 변경:
  1. `_lloyd_3d_iteration` lp_p 분기:
     ```
     if lp_p == 2.0:
         centroid = vor.vertices[region].mean(axis=0)
     else:
         vs = vor.vertices[region]
         d = np.linalg.norm(vs - seeds_inside[si], axis=1)
         w = np.power(np.maximum(d, 1e-12), lp_p - 2.0)
         centroid = (w[:, None] * vs).sum(axis=0) / w.sum()
         if not np.all(np.isfinite(centroid)):
             centroid = vs.mean(axis=0)
     ```
  2. `_generate_native_poly_voronoi_inner` 에 `lp_p: float = 2.0` 인자 추가, line 410/418 의 `_lloyd_3d_iteration(..., lp_p=lp_p)` 로 전달.
  3. best-of-N 루프 직후, 성공한 voronoi attempt 의 cur_seed 로 lp_p=4.0 한 번 더 호출:
     ```
     r_p4 = _generate_native_poly_voronoi_inner(
         vertices, faces, case_dir,
         target_edge_length=target_edge_length,
         seed_density=cur_seed, n_lloyd=n_lloyd, lp_p=4.0,
     )
     if r_p4.success and r_p4.n_cells > 2:
         candidates.append((_grade_score(r_p4.quality_grade), r_p4, f"voronoi_p4(sd={cur_seed})"))
     ```

## 검증 명령
```bash
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- 회귀 PASS (poly 관련 테스트 그린).
- bench 시간 ≤ 720s (현 57.7s 대비 충분 마진).
- poly grade 분포 동등 또는 우세 (현 A=5/5 유지).
- BL 영향 없음 (poly BL 미연동).
- best_of_n 로그 `chosen` 필드로 voronoi_p4 채택률 추적 가능.
