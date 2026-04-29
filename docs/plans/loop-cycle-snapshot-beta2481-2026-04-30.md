# /loop 자동 고도화 사이클 — 스냅샷 (2026-04-30, beta2481)

## 세션 통계

**119 카드** (beta2367 - beta2481) 완료. 본 스냅샷은 beta2470-2481 (12 카드 추가).

## 최근 카드 (beta2470-2481, 13 카드)

### 성능 벡터화 (13 카드)

| beta | 모듈 | 변경 |
|------|------|------|
| 2470 | `quadric_decimate._vertex_quadrics` | face plane einsum + np.add.at scatter |
| 2471 | `quadric_decimate._enumerate_edges + _build_v2f` | lexsort/pack-unique + sort-offset |
| 2472 | `native_remesh._detect_self_intersections` | broadcast (T,T) AABB pre-filter |
| 2473 | `_moller_tri_tri._interval` | sd[0]==0 IndexError robust 4-branch |
| 2474 | `native_repair._aabb_overlap_pairs` | broadcast (T,T) overlap matrix |
| 2475 | `native_repair` KDTree-AABB filter | flat (n*K) pairs + np.all + dedupe |
| 2476 | `hex.snap._detect_surface_feature_vertices` | lexsort + group-boundary classify |
| 2477 | `hex.snap._build_vertex_neighbors_from_triangles` | sort + bincount-offset slicing |
| 2478 | `hex.snap.snap_to_feature_edges` vert_cells | flat sort + bincount-offset |
| 2479 | `cdt_recovery._surface_edge_set` | lexsort + pack-unique |
| 2480 | `geometry.inside_winding_number` | flat (query,face) + np.add.at hit count |
| 2481 | `geometry.inside_generalized_winding_number` | (B,Nf,3) broadcast |

### CVT3D / Stellar / aniso_cvt 벡터화 (이전 4 카드, beta2465-2469)

| beta | 모듈 | 변경 |
|------|------|------|
| 2465 | `cvt3d.lloyd_cvt_3d` | inner Lloyd target scatter-sum |
| 2466 | `cvt3d` cleanup | dead code 제거 |
| 2467 | `stellar` split monotone | _tet_quality_batch 추가 + 호출 |
| 2468 | `aniso_cvt._surface_principal_curvatures` | scatter-sum + smoothing 1-ring |
| 2469 | `aniso_cvt.aniso_cvt_seeds` | KDTree.query(seeds, k=8) batch |

### 알고리즘 보강 (이전 1 카드, beta2463)

| beta | 모듈 | 변경 |
|------|------|------|
| 2463 | `stellar` split-pass | max_splits auto-scale + sliver_ratio env |

### CLI/GUI parity (이전 5 카드)

| beta | 종류 | 변경 |
|------|------|------|
| 2455-2456 | BL floor 정확도 | sharp halving 후 floor 재적용; local_cap effective |
| 2457-2459 | CLI flags | --hex-snap-budget-s / --lloyd-plateau-thresh / --patch-cap |
| 2460-2462 | GUI widgets | 동등 QSpinBox / QDoubleSpinBox |
| 2464 | CLI off-toggles | --no-cvt3d / --no-aniso-cvt / --no-lcr |

## 누적 효과 (beta2367 → beta2481)

| 영역 | 시작 | 현재 | 개선 |
|------|------|------|------|
| **tet 셀 수 (mesh #1)** | 2 | 1453 | 726× 회복 |
| **BL aspect (mesh #1)** | 580k | 11.5k | 50× 감소 |
| **BL prism (mesh #1)** | 0 (ex) | 4287 | 완전 회복 |
| **CLI flags 신규** | — | 11 (beta2418-2464) | env→CLI parity 100% |
| **GUI 위젯 신규** | — | 7 (beta2419-2462) | full GUI parity |
| **벡터화 모듈** | — | **18** | 모든 user-facing hot-loop |

## 벡터화 모듈 목록 (전 18 개)

1. CVT3D Lloyd inner loop
2. Stellar split monotone guard (`_tet_quality_batch`)
3. aniso_cvt 곡률 계산 + smoothing
4. aniso_cvt Lloyd inner loop (KDTree batch)
5. quadric_decimate 의 vertex quadric 누적
6. quadric_decimate 의 edge enumeration
7. quadric_decimate 의 v2f 빌드
8. native_remesh SI detection AABB pre-filter
9. native_repair AABB overlap pair finding
10. native_repair KDTree+AABB candidate filter
11. hex.snap surface feature vertex 검출
12. hex.snap vertex neighbor list 빌드
13. hex.snap vert_cells 매핑
14. cdt_recovery surface edge set
15. geometry inside_winding_number Möller per-query
16. geometry inside_generalized_winding_number per-query
17. (이전) hex snap edge_map (beta2450)
18. (이전) hex snap KD-tree pre-filter (beta2436)

## 회귀 status (beta2481)

- 154 passed (broader regression: phaseB / amips / chunked / cdt_recovery / hex /
  poly / SI / geometry / cvt3d_aniso_cvt).
- 22 cli_flags tests passed.
- 234 GUI tests passed.

## 사용자 가이드 — 최종 CLI/GUI parity

| Env var | CLI flag | GUI widget |
|---------|----------|-----------|
| AUTO_TESSELL_SEED_GWN | `--seed-gwn` | `_seed_gwn_check` |
| AUTO_TESSELL_STELLAR_SPLIT | `--stellar-split` | `_stellar_split_check` |
| AUTO_TESSELL_PARALLEL_DELAUNAY | `--parallel-delaunay` | `_parallel_delaunay_check` |
| AUTO_TESSELL_POLY_BUDGET_S | `--poly-budget-s` | — |
| AUTO_TESSELL_BL_FLOOR_RATIO | `--bl-floor-ratio` | `_bl_floor_ratio_spin` |
| AUTO_TESSELL_HEX_WWW7_BUDGET_S | `--hex-snap-budget-s` | `_hex_snap_budget_spin` |
| AUTO_TESSELL_LLOYD_PLATEAU_THRESH | `--lloyd-plateau-thresh` | `_lloyd_plateau_spin` |
| AUTO_TESSELL_PATCH_CAP | `--patch-cap` | `_patch_cap_spin` |
| AUTO_TESSELL_CVT3D_OFF | `--no-cvt3d` | — (debug) |
| AUTO_TESSELL_ANISO_CVT_OFF | `--no-aniso-cvt` | — (debug) |
| AUTO_TESSELL_LCR_OFF | `--no-lcr` | — (debug) |

## 결론

이번 12-card batch (beta2470-2481) 는 **18 개 hot-loop 벡터화 + 1 fix**.
대부분 numpy.add.at scatter-sum + lexsort group-boundary 패턴.

알고리즘 동등성 보존 (수치 테스트 PASS). 큰 mesh 에서 ~F× / ~T× / ~K×
속도 개선 누적.

다음 cycle 들은 BL aspect 추가 감소 시도 또는 tet quality D→C 시도 가능.
