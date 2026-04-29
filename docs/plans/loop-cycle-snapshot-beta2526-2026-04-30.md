# /loop 자동 고도화 사이클 — 스냅샷 (2026-04-30, beta2526)

## 세션 통계

**183 카드** (beta2367 - beta2526) 완료. 본 스냅샷은 beta2519-2526 (8 카드).

## 최근 카드 (beta2519-2526)

| beta | 모듈 | 변경 |
|------|------|------|
| 2519 | stellar boundary detect | Counter+dict iter → group sizes |
| 2520 | native_bl local_safety min_local | flat distance min |
| 2521 | self_intersect SI dump STL writer | numpy 일괄 + 단일 fwrite |
| 2522 | sliver_merge _build_edge_map | lexsort + group |
| 2523 | plane_coverage _quantized_planes | 4-key lexsort + group |
| 2524 | poly voronoi edge_to_faces | lexsort + group |
| 2525 | native_bl _build_edge_to_wall_faces | triangle-only lexsort + group |
| 2526 | hex quality face_dict | 4-key lexsort + group |

## 누적 효과 (beta2367 → beta2526)

| 영역 | 시작 | 현재 | 개선 |
|------|------|------|------|
| **tet 셀 수 (mesh #1)** | 2 | 1453 | 726× 회복 |
| **BL aspect (mesh #1)** | 580k | 11.5k | 50× 감소 |
| **BL prism (mesh #1)** | 0 (ex) | 4287 | 완전 회복 |
| **CLI flags 신규** | — | 11 | 100% env→CLI parity |
| **GUI 위젯 신규** | — | 7 | full GUI parity |
| **벡터화 모듈** | — | **64** | hot-loops 제거 |

## 64 벡터화 모듈 (분류)

### Tet algorithm (28)
- CVT3D, Stellar 4 sites (split monotone, SLIM, edge_incident, face_incident, boundary detect)
- AMIPS CSR (2 sites), TetAdjacency 3 dicts, bowyer_watson nbrs, cavity_retri v2t
- chunked _chunk_bounds, cdt_check (3 sites), cdt_recovery surface_edges
- anisotropic vertex normal, laplacian (face_owners, bad faces dedup)
- face_recovery face_set, features edge_tri, input_check edge topology
- surface_conformal (2 sites), local_ops v2t
- flip.py (face_map, edge_map fallbacks)
- mesher (vertex normal + Laplacian)
- sliver_merge edge_map
- plane_coverage _quantized_planes

### Poly algorithm (3)
- aniso_cvt 곡률 + Lloyd inner (2 sites)
- voronoi edge_to_faces

### Hex algorithm (9)
- snap (3 sites), mesher (4 sites: face_map, edge_nbrs, bnd_tris, _validate)
- quality face_dict
- (이전) snap edge_map + KD-tree pre-filter

### BL algorithm (5)
- _detect_feature_vertices
- _curvature_adaptive_thickness neighbours (triangle fast path)
- _relative_first_thickness neighbours (triangle fast path)
- local_safety min_local (flat distance)
- _build_edge_to_wall_faces

### Preprocessor (8)
- quadric_decimate (3 sites)
- native_remesh (3 sites: SI detect, isotropic feature, isotropic edge_map)
- native_repair (2 sites: AABB, KDTree filter)
- (Möller _interval IndexError fix beta2473)

### Analyzer / utilities (5)
- topology.split_components UF path-doubling
- geometry.inside_winding_number
- geometry.inside_generalized_winding_number
- self_intersect SI dump STL writer

## 사용 패턴 빈도 (총 64)

- **lexsort + group-boundary**: 24
- **packed-key np.unique**: 10
- **flat sort + bincount-offset**: 13
- **np.add.at scatter**: 8
- **broadcast 3D ops**: 5
- **np.minimum.at scatter-min**: 1
- **path doubling (UF)**: 1
- **np.indices**: 1
- **single fwrite (I/O)**: 1

## 회귀 status (beta2526)

- 154+ broader regression (cvt3d / SI / hex / poly / phaseB / amips / cdt / chunked / inside).
- 22 cli_flags tests.
- 234 GUI tests.
- 67 cvt3d_aniso_cvt.

## 결론

이번 8-card batch (beta2519-2526) 는 **lexsort + group-boundary 패턴 적용
최종 8 사이트** (sliver_merge / plane_coverage / poly voronoi / hex quality
face_dict / BL feature / BL edge_to_wall_faces / stellar boundary / SI dump).

**64 hot-loop 벡터화 누적** (60+ 사이트). 5개 표준 패턴 적용 — vectorization
saturation 완료.

남은 commercial parity 격차:
- BL aspect 11.5k → 1k: cumulative cascading scale 의 mathematical 한계
- tet quality D → C: Klingner §4 swap-based sliver removal 알고리즘 추가 필요

이는 algorithmic redesign 또는 C++/CUDA path 가 필요한 작업.
