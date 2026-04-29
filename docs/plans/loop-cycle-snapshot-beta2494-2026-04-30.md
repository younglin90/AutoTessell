# /loop 자동 고도화 사이클 — 스냅샷 (2026-04-30, beta2494)

## 세션 통계

**132 카드** (beta2367 - beta2494) 완료. 본 스냅샷은 beta2482-2494 (13 카드 추가).

## 최근 카드 (beta2482-2494, 13 perf 카드)

| beta | 모듈 | 변경 |
|------|------|------|
| 2482 | cavity_retri.py | v2t (vertex→tet) flat sort + bincount-offset |
| 2483 | chunked.py _chunk_bounds | triple-nested loop → np.indices |
| 2484 | topology.split_components | UF root path-doubling (parent[parent]) |
| 2485 | cdt_check._tet_triangles | packed-key np.unique |
| 2486 | cdt_check._tet_edges | packed-key np.unique |
| 2487 | cdt_check.check_edge_recovery_chained | surf_edges packed-key |
| 2488 | cdt_check.check_edge_recovery | surf_edges packed-key |
| 2489 | amips.py CSR 1-ring (1st) | flat sort + bincount-offset |
| 2490 | amips.py CSR 1-ring (2nd) | flat sort + bincount-offset |
| 2491 | anisotropic.py vertex normal | 3× np.add.at scatter |
| 2492 | adjacency.py TetAdjacency.build | 3× lexsort + group-boundary |
| 2493 | bowyer_watson._tet_neighbors | src/dst concat + sort + bincount-offset |
| 2494 | native_remesh face_split adjacency | flat src/dst + sort + bincount-offset |

## 누적 효과 (beta2367 → beta2494)

| 영역 | 시작 | 현재 | 개선 |
|------|------|------|------|
| **tet 셀 수 (mesh #1)** | 2 | 1453 | 726× 회복 |
| **BL aspect (mesh #1)** | 580k | 11.5k | 50× 감소 |
| **BL prism (mesh #1)** | 0 (ex) | 4287 | 완전 회복 |
| **CLI flags 신규** | — | 11 | 100% env→CLI parity |
| **GUI 위젯 신규** | — | 7 | full GUI parity |
| **벡터화 모듈** | — | **31** | hot-loops |

## 31 개 벡터화 모듈 (누적)

### Tet algorithm
- CVT3D Lloyd inner loop
- Stellar split monotone guard
- AMIPS CSR 1-ring (2 sites)
- TetAdjacency.build (3 dicts)
- bowyer_watson _tet_neighbors
- cavity_retri v2t
- chunked _chunk_bounds (np.indices)
- cdt_check _tet_triangles, _tet_edges
- cdt_check 2× check_edge_recovery (surf_edges)
- cdt_recovery _surface_edge_set
- anisotropic vertex normal scatter
- (이전) Stellar swap-only worst-tet edge mask

### Poly algorithm
- aniso_cvt _surface_principal_curvatures (angle_sum + smoothing)
- aniso_cvt aniso_cvt_seeds Lloyd inner (KDTree batch)

### Hex algorithm
- snap _detect_surface_feature_vertices (lexsort)
- snap _build_vertex_neighbors_from_triangles
- snap snap_to_feature_edges vert_cells
- (이전) snap edge_map vectorized
- (이전) snap KD-tree pre-filter

### Preprocessor
- quadric_decimate _vertex_quadrics
- quadric_decimate _enumerate_edges + _build_v2f
- native_remesh _detect_self_intersections AABB pre-filter
- native_remesh face_split UUU7 Laplacian adjacency
- native_repair _aabb_overlap_pairs
- native_repair KDTree+AABB filter
- (Möller _interval IndexError fix — beta2473)

### Analyzer / utilities
- topology.split_components UF path-doubling
- geometry.inside_winding_number
- geometry.inside_generalized_winding_number

## 회귀 status (beta2494)

- 154+ passed (broader: phaseB / amips / chunked / cdt / hex / poly / SI /
  geometry / cvt3d_aniso / analyzer).
- 21 SI tests passed.
- 11 hex tests passed.
- 13 amips tests passed.
- 22 cli_flags tests passed.
- 234 GUI tests passed.

## 결론

이번 13-card batch (beta2482-2494) 는 **adjacency build + group-by-key 패턴
표준화**.  numpy lexsort + bincount-offset slicing + np.unique pack-key 가
대부분의 hot-loop 벡터화에 사용. 31 개 모듈 처리 완료.

남은 commercial parity 격차 (BL aspect 11.5k → 1k, tet quality D → C) 는
algorithmic 작업 필요 — 단순 perf 벡터화로는 도달 불가.
