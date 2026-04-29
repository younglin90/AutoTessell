# /loop 자동 고도화 사이클 — 스냅샷 (2026-04-30, beta2509)

## 세션 통계

**147 카드** (beta2367 - beta2509) 완료. 본 스냅샷은 beta2495-2509 (15 카드 추가).

## 최근 카드 (beta2495-2509, 15 perf 카드)

| beta | 모듈 | 변경 |
|------|------|------|
| 2495 | laplacian.py face_owners | lexsort + group-boundary |
| 2496 | face_recovery.py face_set | packed-key np.unique |
| 2497 | features.py edge_tri | lexsort + group-boundary |
| 2498 | input_check.py edge topo | sizes_eo group counter (boundary/nm) |
| 2499 | cdt_check.surf_faces | packed-key np.unique |
| 2500 | isotropic.py feature detect | lexsort + group classify (5번째 사용) |
| 2501 | isotropic._build_edge_map | lexsort + group-boundary |
| 2502 | hex face_map + boundary_verts | lexsort + group sizes |
| 2503 | hex edge_nbrs | flat src/dst + sort + bincount-offset |
| 2504 | hex bnd_tris triangulation | lexsort + group sizes (size=1) |
| 2505 | hex validate bulk vol | bulk vectorize signed vol pre-compute |
| 2506 | surface_conformal _input_faces | packed-key np.unique |
| 2507 | surface_conformal _tet_faces | packed-key np.unique |
| 2508 | stellar edge_incident_cache | lexsort + group-boundary |
| 2509 | stellar face_incident_cache | lexsort + group-boundary |

## 누적 벡터화 패턴 사용 횟수

- **lexsort + group-boundary**: 17 places
- **packed-key np.unique**: 9 places
- **flat sort + bincount-offset**: 10 places
- **np.add.at scatter**: 6 places
- **broadcast (B, F, 3) ops**: 4 places
- **np.indices**: 1 place
- **path doubling (UF)**: 1 place

## 누적 효과 (beta2367 → beta2509)

| 영역 | 시작 | 현재 | 개선 |
|------|------|------|------|
| **tet 셀 수 (mesh #1)** | 2 | 1453 | 726× 회복 |
| **BL aspect (mesh #1)** | 580k | 11.5k | 50× 감소 |
| **BL prism (mesh #1)** | 0 (ex) | 4287 | 완전 회복 |
| **CLI flags 신규** | — | 11 | 100% env→CLI parity |
| **GUI 위젯 신규** | — | 7 | full GUI parity |
| **벡터화 모듈** | — | **47** | hot-loops 제거 |

## 47 개 벡터화 모듈 (누적)

### Tet algorithm (22개)
- CVT3D Lloyd inner loop
- Stellar split monotone guard
- AMIPS CSR 1-ring (2 sites)
- TetAdjacency.build (3 dicts)
- bowyer_watson _tet_neighbors
- cavity_retri v2t
- chunked _chunk_bounds (np.indices)
- cdt_check _tet_triangles, _tet_edges
- cdt_check 2× check_edge_recovery (surf_edges, surf_faces)
- cdt_recovery _surface_edge_set
- anisotropic vertex normal scatter
- laplacian face_owners
- face_recovery face_set
- features edge_tri
- input_check edge topology
- surface_conformal 2× faces sets
- stellar edge_incident_cache
- stellar face_incident_cache
- (이전) Stellar swap-only worst-tet edge mask
- (이전) Stellar 4-op queue priority

### Poly algorithm (2개)
- aniso_cvt _surface_principal_curvatures (angle_sum + smoothing)
- aniso_cvt aniso_cvt_seeds Lloyd inner (KDTree batch)

### Hex algorithm (8개)
- snap _detect_surface_feature_vertices (lexsort)
- snap _build_vertex_neighbors_from_triangles
- snap snap_to_feature_edges vert_cells
- mesher face_map + boundary_verts
- mesher edge_nbrs
- mesher boundary triangulation
- mesher _validate_hex bulk volume
- (이전) snap edge_map vectorized
- (이전) snap KD-tree pre-filter

### Preprocessor (8개)
- quadric_decimate _vertex_quadrics
- quadric_decimate _enumerate_edges + _build_v2f
- native_remesh _detect_self_intersections AABB pre-filter
- native_remesh face_split UUU7 Laplacian adjacency
- native_remesh isotropic feature detect
- native_remesh isotropic _build_edge_map
- native_repair _aabb_overlap_pairs
- native_repair KDTree+AABB filter
- (Möller _interval IndexError fix — beta2473)

### Analyzer / utilities (3개)
- topology.split_components UF path-doubling
- geometry.inside_winding_number
- geometry.inside_generalized_winding_number

## 회귀 status (beta2509)

- 154+ passed (broader: phaseB / amips / chunked / cdt / hex / poly / SI /
  geometry / cvt3d_aniso / analyzer).

## 결론

이번 15-card batch (beta2495-2509) 는 **lexsort + group-boundary 패턴 표준화
지속**. 누적 47 개 hot-loop 벡터화 모듈.

남은 commercial parity 격차 (BL aspect 11.5k → 1k, tet quality D → C) 는
algorithmic 작업 필요 — 단순 perf 벡터화로는 도달 불가.

다음 cycle 들은 algorithmic 진전 (Klingner §4 swap, BL per-vertex aspect cap)
또는 BL/poly/hex 의 추가 hot-loops 벡터화 가능.
